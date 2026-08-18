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
APP_VERSION = "0.4.1"
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
SOURCE_TONE_COUNT = 8
SAFE_STATIC_FILES = {
    "": "index.html",
    "/": "index.html",
    "/index.html": "index.html",
    "/app.css": "app.css",
    "/appearance.js": "appearance.js",
    "/app.js": "app.js",
    "/favicon.svg": "favicon.svg",
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
class LibrarySource:
    id: str
    name: str
    root: Path
    tone: int = 0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.id):
            raise ValueError(f"文档库 ID 不合法: {self.id}")
        resolved = self.root.expanduser().resolve()
        object.__setattr__(self, "root", resolved)
        object.__setattr__(self, "name", self.name.strip() or resolved.name or self.id)
        object.__setattr__(self, "tone", int(self.tone) % SOURCE_TONE_COUNT)


@dataclass(frozen=True)
class AppConfig:
    root: Path
    title: str
    poll_ms: int
    extensions: frozenset[str]
    excludes: frozenset[str]
    libraries: tuple[LibrarySource, ...] = ()

    def __post_init__(self) -> None:
        resolved_root = self.root.expanduser().resolve()
        libraries = tuple(self.libraries) or (
            LibrarySource("main", resolved_root.name or "文档目录", resolved_root, 0),
        )
        identifiers = [source.id for source in libraries]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("文档库 ID 不能重复")
        object.__setattr__(self, "root", libraries[0].root)
        object.__setattr__(self, "libraries", libraries)

    @property
    def primary_library(self) -> LibrarySource:
        return self.libraries[0]

    def library(self, library_id: str) -> LibrarySource | None:
        return next((source for source in self.libraries if source.id == library_id), None)

    def virtual_path(self, source: LibrarySource, relative: str) -> str:
        normalized = relative.replace("\\", "/").lstrip("/")
        if source.id == self.primary_library.id:
            return normalized
        return f"@{source.id}/{normalized}" if normalized else f"@{source.id}"

    def resolve_path(self, relative: str) -> tuple[LibrarySource, str, Path]:
        normalized = unquote(relative).replace("\\", "/").lstrip("/")
        source = self.primary_library
        local_relative = normalized
        if normalized.startswith("@"):
            namespace, separator, remainder = normalized.partition("/")
            selected = self.library(namespace[1:])
            if selected is not None:
                source = selected
                local_relative = remainder if separator else ""
        if any(part in self.excludes for part in Path(local_relative).parts):
            raise PermissionError("路径位于已忽略的目录中")
        candidate = (source.root / local_relative).resolve()
        try:
            candidate.relative_to(source.root)
        except ValueError as exc:
            raise PermissionError("路径超出所属文档库") from exc
        return source, local_relative, candidate

    def safe_path(self, relative: str) -> Path:
        return self.resolve_path(relative)[2]


@dataclass(frozen=True)
class FileRecord:
    path: str
    relative_path: str
    name: str
    filename: str
    mtime: int
    size: int
    library_id: str
    library_name: str
    library_tone: int


@dataclass(frozen=True)
class SearchDocument:
    path: str
    relative_path: str
    name: str
    filename: str
    title: str
    text: str
    searchable: str
    mtime: int
    size: int
    indexed: bool
    library_id: str
    library_name: str
    library_tone: int


def scan_tree(
    config: AppConfig,
) -> tuple[list[dict[str, Any]], str, int, dict[str, FileRecord], dict[str, int]]:
    fingerprint = hashlib.sha256()
    file_count = 0
    records: dict[str, FileRecord] = {}

    library_counts: dict[str, int] = {}

    def walk(source: LibrarySource, directory: Path) -> list[dict[str, Any]]:
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
            relative = path.relative_to(source.root).as_posix()
            virtual_path = config.virtual_path(source, relative)
            try:
                if entry.is_dir(follow_symlinks=False):
                    children = walk(source, path)
                    if children:
                        folders.append(
                            {
                                "type": "folder",
                                "name": entry.name,
                                "path": virtual_path,
                                "relativePath": relative,
                                "libraryId": source.id,
                                "libraryName": source.name,
                                "libraryTone": source.tone,
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
            fingerprint.update(source.id.encode("utf-8"))
            fingerprint.update(relative.encode("utf-8", errors="surrogatepass"))
            fingerprint.update(str(stat.st_mtime_ns).encode("ascii"))
            fingerprint.update(str(stat.st_size).encode("ascii"))
            files.append(
                {
                    "type": "file",
                    "name": path.stem,
                    "filename": entry.name,
                    "path": virtual_path,
                    "relativePath": relative,
                    "mtime": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "libraryId": source.id,
                    "libraryName": source.name,
                    "libraryTone": source.tone,
                }
            )
            records[virtual_path] = FileRecord(
                path=virtual_path,
                relative_path=relative,
                name=path.stem,
                filename=entry.name,
                mtime=stat.st_mtime_ns,
                size=stat.st_size,
                library_id=source.id,
                library_name=source.name,
                library_tone=source.tone,
            )
        return folders + files

    nodes: list[dict[str, Any]] = []
    for source in config.libraries:
        before = file_count
        children = walk(source, source.root)
        count = file_count - before
        library_counts[source.id] = count
        fingerprint.update(source.id.encode("utf-8"))
        fingerprint.update(str(source.root).encode("utf-8", errors="surrogatepass"))
        nodes.append(
            {
                "type": "library",
                "id": source.id,
                "name": source.name,
                "path": f"@{source.id}",
                "tone": source.tone,
                "fileCount": count,
                "children": children,
            }
        )
    return nodes, fingerprint.hexdigest()[:20], file_count, records, library_counts


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
    searchable = " ".join(
        (record.library_name, record.relative_path, record.filename, record.name, title, text)
    ).casefold()
    return SearchDocument(
        path=record.path,
        relative_path=record.relative_path,
        name=record.name,
        filename=record.filename,
        title=title,
        text=text,
        searchable=searchable,
        mtime=record.mtime,
        size=record.size,
        indexed=indexed,
        library_id=record.library_id,
        library_name=record.library_name,
        library_tone=record.library_tone,
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
        self._library_counts: dict[str, int] = {}
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
            nodes, version, file_count, records, library_counts = scan_tree(self.config)
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
                self._library_counts = library_counts
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
                "libraryCounts": dict(self._library_counts),
                "indexedCount": sum(1 for document in self._documents.values() if document.indexed),
                "scanMs": round(self._scan_ms, 1),
                "error": self._last_error,
            }

    def search(self, query: str, limit: int = 20, library_id: str | None = None) -> list[dict[str, Any]]:
        normalized = " ".join(query.split()).casefold()
        if not normalized:
            return []
        terms = [term for term in normalized.split(" ") if term]
        with self._lock:
            documents = list(self._documents.values())

        ranked: list[tuple[int, SearchDocument]] = []
        for document in documents:
            if library_id and document.library_id != library_id:
                continue
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
                    "relativePath": document.relative_path,
                    "name": document.name,
                    "title": document.title,
                    "snippet": search_snippet(document.text, terms),
                    "mtime": document.mtime,
                    "size": document.size,
                    "score": score,
                    "indexed": document.indexed,
                    "libraryId": document.library_id,
                    "libraryName": document.library_name,
                    "libraryTone": document.library_tone,
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
            snapshot = self.library_index.snapshot()
            library_counts = snapshot["libraryCounts"]
            self.send_json(
                {
                    "title": self.config.title,
                    "rootName": (
                        self.config.primary_library.name
                        if len(self.config.libraries) == 1
                        else f"{len(self.config.libraries)} 个文档来源"
                    ),
                    "pollMs": self.config.poll_ms,
                    "version": APP_VERSION,
                    "libraries": [
                        {
                            "id": source.id,
                            "name": source.name,
                            "tone": source.tone,
                            "fileCount": library_counts.get(source.id, 0),
                            "primary": source.id == self.config.primary_library.id,
                        }
                        for source in self.config.libraries
                    ],
                    "features": {
                        "fullTextSearch": True,
                        "readingState": True,
                        "themeCenter": True,
                        "multiLibrary": True,
                    },
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
        library_id = (query.get("library") or [""])[0].strip()
        if library_id and self.config.library(library_id) is None:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "指定的文档来源不存在")
            return
        results = self.library_index.search(phrase, limit, library_id or None)
        self.send_json(
            {"query": phrase, "library": library_id or "all", "count": len(results), "results": results}
        )

    def query_path(self, query: dict[str, list[str]]) -> tuple[str, LibrarySource, str, Path]:
        values = query.get("path", [])
        if not values or not values[0]:
            raise ValueError("缺少 path 参数")
        source, relative, path = self.config.resolve_path(values[0])
        return self.config.virtual_path(source, relative), source, relative, path

    def serve_markdown(self, query: dict[str, list[str]]) -> None:
        try:
            virtual_path, source, relative, path = self.query_path(query)
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
                "path": virtual_path,
                "relativePath": relative,
                "filename": path.name,
                "name": path.stem,
                "content": content,
                "mtime": stat.st_mtime_ns,
                "size": stat.st_size,
                "libraryId": source.id,
                "libraryName": source.name,
                "libraryTone": source.tone,
            }
        )

    def serve_asset(self, query: dict[str, list[str]]) -> None:
        try:
            _, _, _, path = self.query_path(query)
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


def unique_library_id(value: str, index: int, used: set[str]) -> str:
    candidate = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-_")
    if not candidate or not candidate[0].isalnum():
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


def build_library_sources(args: argparse.Namespace, values: dict[str, Any]) -> tuple[LibrarySource, ...]:
    entries: list[dict[str, Any]] = []
    if args.library:
        if args.root:
            entries.append({"name": args.root.expanduser().name or "主文档库", "root": args.root})
        for specification in args.library:
            name, root = parse_library_spec(specification)
            entries.append({"name": name, "root": root})
    elif args.root:
        entries.append({"name": args.root.expanduser().name or "文档目录", "root": args.root})
    elif values.get("libraries"):
        configured = values["libraries"]
        if not isinstance(configured, list):
            raise SystemExit("reader.json 中的 libraries 必须是数组")
        for item in configured:
            if not isinstance(item, dict):
                raise SystemExit("reader.json 中每个文档库都必须是对象")
            root_value = item.get("root") or item.get("path")
            if not root_value:
                raise SystemExit("reader.json 中的文档库缺少 root")
            entries.append(dict(item, root=root_value))
    elif values.get("root"):
        root_value = values["root"]
        root_path = Path(root_value).expanduser()
        entries.append({"id": "main", "name": root_path.name or "文档目录", "root": root_value})

    if not entries:
        raise SystemExit("请使用 --root、--library，或在 reader.json 中配置 root/libraries。")

    used_ids: set[str] = set()
    sources: list[LibrarySource] = []
    for index, entry in enumerate(entries):
        root = Path(entry["root"]).expanduser().resolve()
        if not root.is_dir():
            raise SystemExit(f"Markdown 文档库不存在: {root}")
        name = str(entry.get("name") or root.name or f"文档库 {index + 1}").strip()
        source_id = unique_library_id(str(entry.get("id") or name), index, used_ids)
        try:
            tone = int(entry.get("tone", index))
        except (TypeError, ValueError):
            tone = index
        sources.append(LibrarySource(source_id, name, root, tone))
    return tuple(sources)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动只读 Markdown 目录阅读站")
    parser.add_argument("--config", type=Path, help="reader.json 配置文件")
    parser.add_argument("--root", type=Path, help="Markdown 文件根目录")
    parser.add_argument("--library", action="append", help="文档库，格式为 名称=绝对路径，可重复")
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

    libraries = build_library_sources(args, values)
    root = libraries[0].root
    default_title = (
        f"{libraries[0].name} · Markdown 阅读室"
        if len(libraries) == 1
        else "我的 Agent 文档书架"
    )
    title = args.title or values.get("title") or default_title
    host = args.host or values.get("host") or "127.0.0.1"
    port = args.port if args.port is not None else int(values.get("port", 4173))
    poll_ms = args.poll_ms if args.poll_ms is not None else int(values.get("pollMs", 2200))
    poll_ms = max(800, min(poll_ms, 60_000))
    extensions = normalize_extensions(args.extension, values.get("extensions"))
    excludes = frozenset(DEFAULT_EXCLUDES | set(values.get("excludes", [])) | set(args.exclude or []))
    app_config = AppConfig(root, str(title), poll_ms, extensions, excludes, libraries)
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
    print(f"文档来源: {len(libraries)} 个")
    for source in libraries:
        print(f"  - {source.name}: {source.root}")
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
