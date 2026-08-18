#!/usr/bin/env python3
"""Read-only local web server for browsing a directory of Markdown files."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mimetypes
import os
import re
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
APP_VERSION = "0.2.1"
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
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_SEARCH_QUERY = 120
MAX_SEARCH_RESULTS = 50
INDEX_WORKERS = min(8, max(2, os.cpu_count() or 2))
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.expanduser().resolve())

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


@dataclass(frozen=True)
class FileRecord:
    path: str
    name: str
    filename: str
    mtime: int
    size: int


@dataclass(frozen=True)
class SearchDocument:
    path: str
    name: str
    filename: str
    title: str
    text: str
    searchable: str
    mtime: int
    size: int
    indexed: bool


def scan_tree(config: AppConfig) -> tuple[list[dict[str, Any]], str, int, dict[str, FileRecord]]:
    fingerprint = hashlib.sha256()
    file_count = 0
    records: dict[str, FileRecord] = {}

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
            records[relative] = FileRecord(
                path=relative,
                name=path.stem,
                filename=entry.name,
                mtime=stat.st_mtime_ns,
                size=stat.st_size,
            )
        return folders + files

    nodes = walk(config.root)
    return nodes, fingerprint.hexdigest()[:20], file_count, records


def decode_markdown(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def markdown_search_text(source: str, fallback_title: str) -> tuple[str, str]:
    body = source
    frontmatter_title = ""
    frontmatter = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)", body)
    if frontmatter:
        title_match = re.search(r"^title\s*:\s*(.+?)\s*$", frontmatter.group(1), flags=re.IGNORECASE | re.MULTILINE)
        if title_match:
            frontmatter_title = title_match.group(1).strip().strip("\"'")
        body = body[frontmatter.end() :]

    heading = re.search(r"^#\s+(.+?)\s*$", body, flags=re.MULTILINE)
    title = frontmatter_title or (heading.group(1).strip() if heading else fallback_title)
    plain = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", body)
    plain = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", plain)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = re.sub(r"^\s{0,3}(?:#{1,6}|>|[-+*]\s|\d+[.)]\s)", "", plain, flags=re.MULTILINE)
    plain = re.sub(r"[`*_~|]", "", plain)
    plain = re.sub(r"\s+", " ", html.unescape(plain)).strip()
    return title, plain


def build_search_document(config: AppConfig, record: FileRecord) -> SearchDocument:
    title = record.name
    text = ""
    indexed = record.size <= MAX_INDEX_BYTES
    if indexed:
        try:
            raw = config.safe_path(record.path).read_bytes()
            title, text = markdown_search_text(decode_markdown(raw), record.name)
        except (OSError, PermissionError):
            indexed = False
    searchable = " ".join((record.path, record.filename, record.name, title, text)).casefold()
    return SearchDocument(
        path=record.path,
        name=record.name,
        filename=record.filename,
        title=title,
        text=text,
        searchable=searchable,
        mtime=record.mtime,
        size=record.size,
        indexed=indexed,
    )


def search_snippet(text: str, terms: list[str], radius: int = 76) -> str:
    if not text:
        return ""
    folded = text.casefold()
    positions = [folded.find(term) for term in terms]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - radius)
    end = min(len(text), center + radius * 2)
    snippet = text[start:end].strip()
    if start:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet


class LibraryIndex:
    """Cache the directory tree and a lightweight read-only full-text index."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._nodes: list[dict[str, Any]] = []
        self._version = ""
        self._file_count = 0
        self._documents: dict[str, SearchDocument] = {}
        self._scan_ms = 0.0
        self._last_error = ""

    def start(self) -> None:
        self.refresh()
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="markdown-library-index", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        interval = max(0.8, self.config.poll_ms / 1000)
        while not self._stop_event.wait(interval):
            try:
                self.refresh()
            except Exception as exc:  # keep the last valid snapshot available
                with self._lock:
                    self._last_error = str(exc)

    def refresh(self) -> bool:
        with self._refresh_lock:
            started = time.perf_counter()
            nodes, version, file_count, records = scan_tree(self.config)
            with self._lock:
                previous_version = self._version
                previous_documents = self._documents

            documents: dict[str, SearchDocument] = {}
            changed_records: list[FileRecord] = []
            for path, record in records.items():
                previous = previous_documents.get(path)
                if previous and previous.mtime == record.mtime and previous.size == record.size:
                    documents[path] = previous
                else:
                    changed_records.append(record)

            if len(changed_records) < 4:
                changed_documents = [build_search_document(self.config, record) for record in changed_records]
            else:
                with ThreadPoolExecutor(max_workers=min(INDEX_WORKERS, len(changed_records))) as executor:
                    changed_documents = list(executor.map(lambda record: build_search_document(self.config, record), changed_records))
            documents.update((document.path, document) for document in changed_documents)

            elapsed_ms = (time.perf_counter() - started) * 1000
            with self._lock:
                self._nodes = nodes
                self._version = version
                self._file_count = file_count
                self._documents = documents
                self._scan_ms = elapsed_ms
                self._last_error = ""
            return version != previous_version

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "nodes": self._nodes,
                "version": self._version,
                "fileCount": self._file_count,
                "indexedCount": sum(1 for document in self._documents.values() if document.indexed),
                "scanMs": round(self._scan_ms, 1),
                "error": self._last_error,
            }

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        normalized = " ".join(query.split()).casefold()
        if not normalized:
            return []
        terms = [term for term in normalized.split(" ") if term]
        with self._lock:
            documents = list(self._documents.values())

        ranked: list[tuple[int, SearchDocument]] = []
        for document in documents:
            if any(term not in document.searchable for term in terms):
                continue
            title = document.title.casefold()
            filename = document.filename.casefold()
            path = document.path.casefold()
            body = document.text.casefold()
            score = 0
            for term in terms:
                if term in title:
                    score += 120
                if term in filename:
                    score += 90
                if term in path:
                    score += 45
                score += min(body.count(term), 8) * 12
            if normalized in title:
                score += 80
            if normalized in body:
                score += 30
            ranked.append((score, document))

        ranked.sort(key=lambda item: (-item[0], natural_key(item[1].path)))
        results = []
        for score, document in ranked[: max(1, min(limit, MAX_SEARCH_RESULTS))]:
            results.append(
                {
                    "path": document.path,
                    "name": document.name,
                    "title": document.title,
                    "snippet": search_snippet(document.text, terms),
                    "mtime": document.mtime,
                    "size": document.size,
                    "score": score,
                    "indexed": document.indexed,
                }
            )
        return results


class MarkdownReaderHandler(BaseHTTPRequestHandler):
    server_version = f"MarkdownReadingRoom/{APP_VERSION}"

    @property
    def config(self) -> AppConfig:
        return self.server.app_config  # type: ignore[attr-defined]

    @property
    def library_index(self) -> LibraryIndex:
        return self.server.library_index  # type: ignore[attr-defined]

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
            snapshot = self.library_index.snapshot()
            self.send_json(
                {
                    "ok": True,
                    "version": APP_VERSION,
                    "fileCount": snapshot["fileCount"],
                    "indexedCount": snapshot["indexedCount"],
                }
            )
            return
        if parsed.path == "/api/config":
            self.send_json(
                {
                    "title": self.config.title,
                    "rootName": self.config.root.name or str(self.config.root),
                    "pollMs": self.config.poll_ms,
                    "version": APP_VERSION,
                    "features": {"fullTextSearch": True, "readingState": True},
                }
            )
            return
        if parsed.path == "/api/tree":
            self.send_json(self.library_index.snapshot())
            return
        if parsed.path == "/api/search":
            self.serve_search(parse_qs(parsed.query))
            return
        if parsed.path == "/api/file":
            self.serve_markdown(parse_qs(parsed.query))
            return
        if parsed.path == "/api/asset":
            self.serve_asset(parse_qs(parsed.query))
            return
        self.serve_static(parsed.path)

    def serve_search(self, query: dict[str, list[str]]) -> None:
        phrase = (query.get("q") or [""])[0].strip()
        if len(phrase) > MAX_SEARCH_QUERY:
            self.send_error_json(HTTPStatus.BAD_REQUEST, f"搜索词不能超过 {MAX_SEARCH_QUERY} 个字符")
            return
        try:
            limit = int((query.get("limit") or ["20"])[0])
        except ValueError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "limit 必须是整数")
            return
        results = self.library_index.search(phrase, limit)
        self.send_json({"query": phrase, "count": len(results), "results": results})

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

        content = decode_markdown(raw)
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
    library_index = LibraryIndex(app_config)

    server = ThreadingHTTPServer((host, port), MarkdownReaderHandler)
    server.daemon_threads = True
    server.app_config = app_config  # type: ignore[attr-defined]
    server.library_index = library_index  # type: ignore[attr-defined]
    try:
        library_index.start()
    except Exception:
        server.server_close()
        raise
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
        library_index.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
