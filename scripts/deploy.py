#!/usr/bin/env python3
"""Deploy the bundled Markdown reader to a user-selected directory."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
APP_TEMPLATE = SKILL_DIR / "assets" / "app"
MARKER_NAME = ".markdown-reader-install.json"
APP_VERSION = "0.2.1"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="部署 Markdown 阅读室")
    parser.add_argument("--content", required=True, type=Path, help="要阅读的 Markdown 根目录")
    parser.add_argument("--output", required=True, type=Path, help="阅读站程序安装目录")
    parser.add_argument("--title", help="网页标题，默认使用内容目录名")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机访问")
    parser.add_argument("--port", type=int, default=4173, help="端口，默认 4173")
    parser.add_argument("--poll-ms", type=int, default=2200, help="自动刷新间隔，单位毫秒")
    parser.add_argument("--exclude", action="append", default=[], help="额外忽略的目录名，可重复")
    return parser


def main() -> int:
    configure_console()
    args = build_parser().parse_args()
    content = args.content.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not content.is_dir():
        raise SystemExit(f"Markdown 内容目录不存在: {content}")
    if not APP_TEMPLATE.is_dir():
        raise SystemExit(f"技能包不完整，缺少应用模板: {APP_TEMPLATE}")
    if not 1 <= args.port <= 65535:
        raise SystemExit("端口必须在 1 到 65535 之间")

    if output.exists():
        marker = output / MARKER_NAME
        has_content = any(output.iterdir())
        if has_content and not marker.is_file():
            raise SystemExit(f"输出目录不是 Markdown 阅读室安装目录，已停止覆盖: {output}")
    output.mkdir(parents=True, exist_ok=True)

    shutil.copytree(APP_TEMPLATE, output, dirs_exist_ok=True)
    title = args.title or f"{content.name} · Markdown 阅读室"
    config = {
        "root": str(content),
        "title": title,
        "host": args.host,
        "port": args.port,
        "pollMs": max(800, min(args.poll_ms, 60_000)),
        "extensions": [".md", ".markdown", ".mdown", ".mkd"],
        "excludes": args.exclude,
    }
    write_text(output / "reader.json", json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    write_text(
        output / MARKER_NAME,
        json.dumps(
            {"skill": "serve-markdown-library", "format": 2, "version": APP_VERSION},
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

    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    print("Markdown 阅读室部署完成")
    print(f"内容目录: {content}")
    print(f"安装目录: {output}")
    print(f"访问地址: http://{display_host}:{args.port}")
    print("Windows 启动: 双击 start-reader.bat")
    print("macOS/Linux 启动: 运行 ./start-reader.sh")
    if args.host in {"0.0.0.0", "::"}:
        print("安全提示: 已启用局域网访问。服务没有账号认证，请勿直接暴露到公网。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
