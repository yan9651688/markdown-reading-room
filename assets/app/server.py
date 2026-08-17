#!/usr/bin/env python3
"""Read-only local web server for browsing a directory of Markdown files."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
DEFAULT_EXCLUDES = {".git", ".hg", ".svn", ".venv", "node_modules", "__pycache__"}
DEFAULT_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}
SAFE_ASSET_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".csv",
    ".docx",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".json",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".pdf",
    ".png",
    ".pptx",
    ".svg",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".xlsx",
    ".zip",
}
MAX_MARKDOWN_BYTES = 8 * 1024 * 1024
MAX_ASSET_BYTES = 64 * 1024 * 1024
SAFE_STATIC_FILES = {
    "": "index.html",
    "/": "index.html",
    "/index.html": "index.html",
    "/app.css": "app.css",
    "/app.js": "app.js",
    "/vendor/marked.umd.js": "vendor/marked.umd.js",
    "/vendor/purify.min.js": "vendor/purify.min.js",
}


def natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"无法读取配置文件 {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"配置文件必须是 JSON 对象: {path}")
    return value


@dataclass(frozen=True)
class AppConfig:
    root: Path
    title: str
    poll_ms: int
    extensions: frozenset[str]
    excludes: frozenset[str]

    def safe_path(self, relative: str) -> Path:
        normalized = unquote(relative).replace("\\", "/").lstrip("/")
        if any(part in self.excludes for part in Path(normalized).parts):
            raise PermissionError("路径位于已忽略的目录中")
        candidate = (self.root / normalized).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError("路径超出 Markdown 根目录") from exc
        return candidate


def scan_tree(config: AppConfig) -> tuple[list[dict[str, Any]], str, int]:
    fingerprint = hashlib.sha256()
    file_count = 0

    def walk(directory: Path) -> list[dict[str, Any]]:
        nonlocal file_count
        folders: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        try:
            entries = list(os.scandir(directory))
        except (OSError, PermissionError):
            return []

        entries.sort(key=lambda item: natural_key(item.name))
        for entry in entries:
            if entry.name in config.excludes or entry.is_symlink():
                continue
            path = Path(entry.path)
            relative = path.relative_to(config.root).as_posix()
            try:
                if entry.is_dir(follow_symlinks=False):
                    children = walk(path)
                    if children:
                        folders.append(
                            {
                                "type": "folder",
                                "name": entry.name,
                                "path": relative,
                                "children": children,
                            }
                        )
                    continue
                if not entry.is_file(follow_symlinks=False) or path.suffix.casefold() not in config.extensions:
                    continue
                stat = entry.stat(follow_symlinks=False)
            except (OSError, PermissionError):
                continue

            file_count += 1
            fingerprint.update(relative.encode("utf-8", errors="surrogatepass"))
            fingerprint.update(str(stat.st_mtime_ns).encode("ascii"))
            fingerprint.update(str(stat.st_size).encode("ascii"))
            files.append(
                {
                    "type": "file",
                    "name": path.stem,
                    "filename": entry.name,
                    "path": relative,
                    "mtime": stat.st_mtime_ns,
                    "size": stat.st_size,
                }
            )
        return folders + files

    nodes = walk(config.root)
    return nodes, fingerprint.hexdigest()[:20], file_count


class MarkdownReaderHandler(BaseHTTPRequestHandler):
    server_version = "MarkdownReadingRoom/1.0"

    @property
    def config(self) -> AppConfig:
        return self.server.app_config  # type: ignore[attr-defined]

    def log_message(self, message: str, *args: Any) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), message % args))

    def send_common_headers(self, content_type: str, length: int, cache: str = "no-store") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: http: https:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )

    def send_bytes(
        self,
        data: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        cache: str = "no-store",
    ) -> None:
        self.send_response(status)
        self.send_common_headers(content_type, len(data), cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json_bytes(payload), "application/json; charset=utf-8", status)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self.send_json({"ok": True})
            return
        if parsed.path == "/api/config":
            self.send_json(
                {
                    "title": self.config.title,
                    "rootName": self.config.root.name or str(self.config.root),
                    "pollMs": self.config.poll_ms,
                }
            )
            return
        if parsed.path == "/api/tree":
            nodes, version, file_count = scan_tree(self.config)
            self.send_json({"nodes": nodes, "version": version, "fileCount": file_count})
            return
        if parsed.path == "/api/file":
            self.serve_markdown(parse_qs(parsed.query))
            return
        if parsed.path == "/api/asset":
            self.serve_asset(parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def query_path(self, query: dict[str, list[str]]) -> tuple[str, Path]:
        values = query.get("path", [])
        if not values or not values[0]:
            raise ValueError("缺少 path 参数")
        relative = values[0].replace("\\", "/").lstrip("/")
        return relative, self.config.safe_path(relative)

    def serve_markdown(self, query: dict[str, list[str]]) -> None:
        try:
            relative, path = self.query_path(query)
            if path.suffix.casefold() not in self.config.extensions:
                raise PermissionError("不是允许的 Markdown 文件")
            stat = path.stat()
            if not path.is_file():
                raise FileNotFoundError
            if stat.st_size > MAX_MARKDOWN_BYTES:
                raise ValueError("Markdown 文件超过 8 MB，无法在浏览器中打开")
            raw = path.read_bytes()
        except FileNotFoundError:
            self.send_error_json(HTTPStatus.NOT_FOUND, "文件不存在或已被移动")
            return
        except PermissionError as exc:
            self.send_error_json(HTTPStatus.FORBIDDEN, str(exc))
            return
        except (OSError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("utf-8", errors="replace")
        self.send_json(
            {
                "path": relative,
                "filename": path.name,
                "name": path.stem,
                "content": content,
                "mtime": stat.st_mtime_ns,
                "size": stat.st_size,
            }
        )

    def serve_asset(self, query: dict[str, list[str]]) -> None:
        try:
            _, path = self.query_path(query)
            if path.suffix.casefold() not in SAFE_ASSET_EXTENSIONS:
                raise PermissionError("不允许通过阅读站访问这种文件")
            stat = path.stat()
            if not path.is_file():
                raise FileNotFoundError
            if stat.st_size > MAX_ASSET_BYTES:
                raise ValueError("资源文件超过 64 MB")
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error_json(HTTPStatus.NOT_FOUND, "资源不存在")
            return
        except PermissionError as exc:
            self.send_error_json(HTTPStatus.FORBIDDEN, str(exc))
            return
        except (OSError, ValueError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(data, content_type, cache="private, max-age=60")

    def serve_static(self, request_path: str) -> None:
        relative = SAFE_STATIC_FILES.get(request_path)
        if not relative:
            self.send_error_json(HTTPStatus.NOT_FOUND, "页面不存在")
            return
        path = STATIC_DIR / relative
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"缺少前端资源: {relative}")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in {".html", ".css", ".js"}:
            content_type += "; charset=utf-8"
        self.send_bytes(data, content_type, cache="no-cache")


def normalize_extensions(values: list[str] | None, config_values: Any) -> frozenset[str]:
    selected = values if values else config_values
    if not selected:
        return frozenset(DEFAULT_EXTENSIONS)
    if isinstance(selected, str):
        selected = selected.split(",")
    normalized = {value.casefold() if str(value).startswith(".") else f".{str(value).casefold()}" for value in selected}
    return frozenset(normalized)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动只读 Markdown 目录阅读站")
    parser.add_argument("--config", type=Path, help="reader.json 配置文件")
    parser.add_argument("--root", type=Path, help="Markdown 文件根目录")
    parser.add_argument("--title", help="页面标题")
    parser.add_argument("--host", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, help="端口，默认 4173")
    parser.add_argument("--poll-ms", type=int, help="目录刷新间隔，默认 2200 毫秒")
    parser.add_argument("--extension", action="append", help="允许的扩展名，可重复")
    parser.add_argument("--exclude", action="append", help="忽略的目录名，可重复")
    parser.add_argument("--open", action="store_true", help="启动后打开默认浏览器")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    default_config = APP_DIR / "reader.json"
    config_path = args.config.resolve() if args.config else default_config
    values = load_json(config_path) if config_path.exists() else {}

    root_value = args.root or values.get("root")
    if not root_value:
        raise SystemExit("请使用 --root 指定 Markdown 根目录，或在 reader.json 中配置 root。")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Markdown 根目录不存在: {root}")

    title = args.title or values.get("title") or f"{root.name} · Markdown 阅读室"
    host = args.host or values.get("host") or "127.0.0.1"
    port = args.port if args.port is not None else int(values.get("port", 4173))
    poll_ms = args.poll_ms if args.poll_ms is not None else int(values.get("pollMs", 2200))
    poll_ms = max(800, min(poll_ms, 60_000))
    extensions = normalize_extensions(args.extension, values.get("extensions"))
    excludes = frozenset(DEFAULT_EXCLUDES | set(values.get("excludes", [])) | set(args.exclude or []))
    app_config = AppConfig(root, str(title), poll_ms, extensions, excludes)

    server = ThreadingHTTPServer((host, port), MarkdownReaderHandler)
    server.daemon_threads = True
    server.app_config = app_config  # type: ignore[attr-defined]
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{server.server_port}"

    print("\nMarkdown 阅读室已启动")
    print(f"目录: {root}")
    print(f"地址: {url}")
    if host in {"0.0.0.0", "::"}:
        print("提示: 当前允许局域网访问。此服务不含登录认证，请勿直接暴露到公网。")
    print("按 Ctrl+C 停止服务。\n")

    if args.open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        print("\n正在停止 Markdown 阅读室...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
