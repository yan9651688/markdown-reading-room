#!/usr/bin/env python3
"""Deploy the bundled Markdown reader to a user-selected directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
APP_TEMPLATE = SKILL_DIR / "assets" / "app"
MARKER_NAME = ".markdown-reader-install.json"
APP_VERSION = "0.4.1"
SOURCE_TONE_COUNT = 8


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def unique_library_id(value: str, index: int, used: set[str]) -> str:
    candidate = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-_")
    if not candidate:
        candidate = f"library-{index + 1}"
    base = candidate
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def parse_library_spec(value: str) -> tuple[str, Path]:
    name, separator, raw_path = value.partition("=")
    if not separator or not name.strip() or not raw_path.strip():
        raise SystemExit(f"文档库参数格式错误: {value!r}，请使用 名称=绝对路径")
    return name.strip(), Path(raw_path.strip())


def load_existing_config(output: Path) -> dict[str, object]:
    path = output / "reader.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"现有 reader.json 无法读取: {exc}") from exc
    return value if isinstance(value, dict) else {}


def collect_libraries(args: argparse.Namespace, existing: dict[str, object]) -> list[dict[str, object]]:
    raw_entries: list[dict[str, object]] = []
    if args.content:
        content = args.content.expanduser().resolve()
        raw_entries.append({"name": content.name or "主文档库", "root": content})
    for specification in args.library or []:
        name, root = parse_library_spec(specification)
        raw_entries.append({"name": name, "root": root})

    if not raw_entries:
        configured = existing.get("libraries")
        if isinstance(configured, list) and configured:
            raw_entries.extend(item for item in configured if isinstance(item, dict))
        elif existing.get("root"):
            root = Path(str(existing["root"])).expanduser()
            raw_entries.append({"id": "main", "name": root.name or "文档目录", "root": root})

    if not raw_entries:
        raise SystemExit(
            "请至少使用一次 --content 或 --library 指定 Markdown 文档库。"
            "如果不知道目录，请先运行 scripts/discover.py。"
        )

    used_ids: set[str] = set()
    libraries: list[dict[str, object]] = []
    for index, entry in enumerate(raw_entries):
        root_value = entry.get("root") or entry.get("path")
        if not root_value:
            raise SystemExit("文档库配置缺少 root")
        root = Path(str(root_value)).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"Markdown 内容目录不存在: {root}")
        name = str(entry.get("name") or root.name or f"文档库 {index + 1}").strip()
        library_id = unique_library_id(str(entry.get("id") or name), index, used_ids)
        try:
            tone = int(entry.get("tone", index)) % SOURCE_TONE_COUNT
        except (TypeError, ValueError):
            tone = index % SOURCE_TONE_COUNT
        libraries.append({"id": library_id, "name": name, "root": str(root), "tone": tone})
    return libraries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="部署 Markdown 阅读室",
        epilog="不知道 Markdown 在哪里时，先运行 python scripts/discover.py 查看候选和参考目录。",
    )
    parser.add_argument("--content", type=Path, help="兼容旧版：主 Markdown 根目录")
    parser.add_argument("--library", action="append", help="文档库，格式为 名称=绝对路径，可重复")
    parser.add_argument("--output", required=True, type=Path, help="阅读站程序安装目录")
    parser.add_argument("--title", help="网页标题，默认使用内容目录名")
    parser.add_argument("--host", help="监听地址，默认仅本机访问")
    parser.add_argument("--port", type=int, help="端口，默认 4173")
    parser.add_argument("--poll-ms", type=int, help="自动刷新间隔，单位毫秒")
    parser.add_argument("--exclude", action="append", help="额外忽略的目录名，可重复")
    return parser


def main() -> int:
    configure_console()
    args = build_parser().parse_args()
    output = args.output.expanduser().resolve()
    if not APP_TEMPLATE.is_dir():
        raise SystemExit(f"技能包不完整，缺少应用模板: {APP_TEMPLATE}")

    existing_config: dict[str, object] = {}
    if output.exists():
        marker = output / MARKER_NAME
        has_content = any(output.iterdir())
        if has_content and not marker.is_file():
            raise SystemExit(f"输出目录不是 Markdown 阅读室安装目录，已停止覆盖: {output}")
        if marker.is_file():
            existing_config = load_existing_config(output)

    libraries = collect_libraries(args, existing_config)
    host = args.host or str(existing_config.get("host") or "127.0.0.1")
    port = args.port if args.port is not None else int(existing_config.get("port") or 4173)
    poll_ms = args.poll_ms if args.poll_ms is not None else int(existing_config.get("pollMs") or 2200)
    excludes = args.exclude if args.exclude is not None else list(existing_config.get("excludes") or [])
    if not 1 <= port <= 65535:
        raise SystemExit("端口必须在 1 到 65535 之间")

    output.mkdir(parents=True, exist_ok=True)

    shutil.copytree(APP_TEMPLATE, output, dirs_exist_ok=True)
    title = args.title or str(existing_config.get("title") or "")
    if not title:
        title = (
            f"{libraries[0]['name']} · Markdown 阅读室"
            if len(libraries) == 1
            else "我的 Agent 文档书架"
        )
    config = {
        "root": libraries[0]["root"],
        "libraries": libraries,
        "title": title,
        "host": host,
        "port": port,
        "pollMs": max(800, min(poll_ms, 60_000)),
        "extensions": [".md", ".markdown", ".mdown", ".mkd"],
        "excludes": excludes,
    }
    write_text(output / "reader.json", json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    write_text(
        output / MARKER_NAME,
        json.dumps(
            {"skill": "serve-markdown-library", "format": 3, "version": APP_VERSION},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )

    windows_launcher = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Python 3。请先安装 Python 3，再重新运行。
  pause
  exit /b 1
)
python server.py --config reader.json --open
if errorlevel 1 pause
"""
    posix_launcher = """#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3。请先安装 Python 3，再重新运行。" >&2
  exit 1
fi
exec python3 "$SCRIPT_DIR/server.py" --config "$SCRIPT_DIR/reader.json" --open
"""
    write_text(output / "start-reader.bat", windows_launcher.replace("\n", "\r\n"))
    write_text(output / "start-reader.sh", posix_launcher)
    try:
        os.chmod(output / "start-reader.sh", 0o755)
        os.chmod(output / "server.py", 0o755)
    except OSError:
        pass

    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print("Markdown 阅读室部署完成")
    print(f"文档来源: {len(libraries)} 个")
    for library in libraries:
        print(f"  - {library['name']}: {library['root']}")
    print(f"安装目录: {output}")
    print(f"访问地址: http://{display_host}:{port}")
    print("Windows 启动: 双击 start-reader.bat")
    print("macOS/Linux 启动: 运行 ./start-reader.sh")
    if host in {"0.0.0.0", "::"}:
        print("安全提示: 已启用局域网访问。服务没有账号认证，请勿直接暴露到公网。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
