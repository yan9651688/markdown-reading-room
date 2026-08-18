from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "assets" / "app"
sys.path.insert(0, str(APP_DIR))

import server as reader_server  # noqa: E402


class LibraryIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "产品").mkdir()
        (self.root / "产品" / "路线图.md").write_text(
            "---\ntitle: 墨阅产品路线图\n---\n\n# 路线图\n\n下一版本增加全文搜索、收藏和阅读位置记忆。\n",
            encoding="utf-8",
        )
        (self.root / "部署.md").write_text("# 部署说明\n\n运行 Python 服务并打开浏览器。\n", encoding="utf-8")
        self.config = reader_server.AppConfig(
            root=self.root,
            title="测试文档库",
            poll_ms=800,
            extensions=frozenset({".md"}),
            excludes=frozenset(reader_server.DEFAULT_EXCLUDES),
        )
        self.assertEqual(self.config.root, self.root.resolve())
        self.index = reader_server.LibraryIndex(self.config)
        self.index.refresh()

    def tearDown(self) -> None:
        self.index.stop()
        self.temp.cleanup()

    def test_tree_snapshot_and_full_text_search(self) -> None:
        snapshot = self.index.snapshot()
        self.assertEqual(snapshot["fileCount"], 2)
        self.assertEqual(snapshot["indexedCount"], 2)
        self.assertTrue(snapshot["version"])

        results = self.index.search("全文搜索")
        self.assertEqual(results[0]["path"], "产品/路线图.md")
        self.assertIn("全文搜索", results[0]["snippet"])

        title_results = self.index.search("墨阅产品")
        self.assertEqual(title_results[0]["title"], "墨阅产品路线图")

    def test_multiple_terms_must_all_match(self) -> None:
        self.assertEqual(len(self.index.search("收藏 位置")), 1)
        self.assertEqual(self.index.search("收藏 不存在的词"), [])

    def test_incremental_refresh_updates_and_removes_documents(self) -> None:
        target = self.root / "产品" / "路线图.md"
        target.write_text("# 新内容\n\n现在支持增量索引。\n", encoding="utf-8")
        self.assertTrue(self.index.refresh())
        self.assertEqual(self.index.search("全文搜索"), [])
        self.assertEqual(self.index.search("增量索引")[0]["path"], "产品/路线图.md")

        target.unlink()
        self.assertTrue(self.index.refresh())
        self.assertEqual(self.index.snapshot()["fileCount"], 1)
        self.assertEqual(self.index.search("增量索引"), [])

    def test_large_document_is_not_body_indexed_but_filename_is_searchable(self) -> None:
        target = self.root / "超大文档.md"
        with target.open("wb") as handle:
            handle.truncate(reader_server.MAX_INDEX_BYTES + 1)
        self.index.refresh()
        result = self.index.search("超大文档")[0]
        self.assertFalse(result["indexed"])
        self.assertEqual(result["path"], "超大文档.md")

    def test_safe_path_blocks_escape_and_excluded_directories(self) -> None:
        with self.assertRaises(PermissionError):
            self.config.safe_path("../secret.md")
        with self.assertRaises(PermissionError):
            self.config.safe_path(".git/config")


class MultiLibraryIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.codex = self.base / "codex"
        self.claude = self.base / "claude"
        self.codex.mkdir()
        self.claude.mkdir()
        (self.codex / "README.md").write_text("# Codex 记录\n\n共同关键词，来自 Codex。", encoding="utf-8")
        (self.claude / "README.md").write_text("# Claude 记录\n\n共同关键词，来自 Claude。", encoding="utf-8")
        libraries = (
            reader_server.LibrarySource("codex", "Codex", self.codex, 0),
            reader_server.LibrarySource("claude", "Claude", self.claude, 1),
        )
        self.config = reader_server.AppConfig(
            root=self.codex,
            title="Agent 文档",
            poll_ms=800,
            extensions=frozenset({".md"}),
            excludes=frozenset(reader_server.DEFAULT_EXCLUDES),
            libraries=libraries,
        )
        self.index = reader_server.LibraryIndex(self.config)
        self.index.refresh()

    def tearDown(self) -> None:
        self.index.stop()
        self.temp.cleanup()

    def test_duplicate_relative_paths_are_isolated_and_grouped(self) -> None:
        snapshot = self.index.snapshot()
        self.assertEqual(snapshot["fileCount"], 2)
        self.assertEqual([node["type"] for node in snapshot["nodes"]], ["library", "library"])
        self.assertEqual(snapshot["libraryCounts"], {"codex": 1, "claude": 1})
        self.assertEqual(snapshot["nodes"][0]["children"][0]["path"], "README.md")
        self.assertEqual(snapshot["nodes"][1]["children"][0]["path"], "@claude/README.md")

        results = self.index.search("共同关键词")
        self.assertEqual({result["libraryId"] for result in results}, {"codex", "claude"})
        filtered = self.index.search("共同关键词", library_id="claude")
        self.assertEqual([result["path"] for result in filtered], ["@claude/README.md"])

    def test_each_virtual_path_resolves_inside_its_own_library(self) -> None:
        source, relative, path = self.config.resolve_path("@claude/README.md")
        self.assertEqual(source.id, "claude")
        self.assertEqual(relative, "README.md")
        self.assertEqual(path, (self.claude / "README.md").resolve())
        with self.assertRaises(PermissionError):
            self.config.resolve_path("@claude/../codex/README.md")


class HttpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "说明.md").write_text("# 使用说明\n\n正文可以被搜索命中。\n", encoding="utf-8")
        self.config = reader_server.AppConfig(
            root=self.root,
            title="API 测试",
            poll_ms=800,
            extensions=frozenset({".md"}),
            excludes=frozenset(reader_server.DEFAULT_EXCLUDES),
        )
        self.index = reader_server.LibraryIndex(self.config)
        self.index.refresh()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), reader_server.MarkdownReaderHandler)
        self.server.daemon_threads = True
        self.server.app_config = self.config
        self.server.library_index = self.index
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.index.stop()
        self.temp.cleanup()

    def get_json(self, path: str) -> dict:
        with urllib.request.urlopen(self.base_url + path, timeout=3) as response:
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            return json.loads(response.read().decode("utf-8"))

    def test_health_tree_file_and_search_endpoints(self) -> None:
        self.assertEqual(self.get_json("/health")["version"], "0.4.2")
        config = self.get_json("/api/config")
        self.assertTrue(config["features"]["themeCenter"])
        self.assertTrue(config["features"]["multiLibrary"])
        self.assertEqual(config["libraries"][0]["id"], "main")
        self.assertEqual(self.get_json("/api/tree")["fileCount"], 1)
        query = urllib.parse.quote("搜索命中")
        results = self.get_json(f"/api/search?q={query}")["results"]
        self.assertEqual(results[0]["path"], "说明.md")
        path = urllib.parse.quote("说明.md")
        self.assertIn("使用说明", self.get_json(f"/api/file?path={path}")["content"])

    def test_search_rejects_overlong_query(self) -> None:
        query = urllib.parse.quote("x" * (reader_server.MAX_SEARCH_QUERY + 1))
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.get_json(f"/api/search?q={query}")
        self.assertEqual(context.exception.code, 400)

    def test_theme_bootstrap_and_favicon_are_served_with_safe_types(self) -> None:
        with urllib.request.urlopen(self.base_url + "/appearance.js", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(response.headers["Content-Type"].startswith("text/javascript"))
        with urllib.request.urlopen(self.base_url + "/runtime.js", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(response.headers["Content-Type"].startswith("text/javascript"))
        with urllib.request.urlopen(self.base_url + "/favicon.svg", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "image/svg+xml")


class MultiLibraryHttpApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        codex = base / "codex"
        claude = base / "claude"
        codex.mkdir()
        claude.mkdir()
        (codex / "同名.md").write_text("# Codex 文档\n\n跨库命中。", encoding="utf-8")
        (claude / "同名.md").write_text("# Claude 文档\n\n跨库命中。", encoding="utf-8")
        libraries = (
            reader_server.LibrarySource("codex", "Codex", codex, 0),
            reader_server.LibrarySource("claude", "Claude", claude, 1),
        )
        self.config = reader_server.AppConfig(
            root=codex,
            title="多来源 API",
            poll_ms=800,
            extensions=frozenset({".md"}),
            excludes=frozenset(reader_server.DEFAULT_EXCLUDES),
            libraries=libraries,
        )
        self.index = reader_server.LibraryIndex(self.config)
        self.index.refresh()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), reader_server.MarkdownReaderHandler)
        self.server.daemon_threads = True
        self.server.app_config = self.config
        self.server.library_index = self.index
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.index.stop()
        self.temp.cleanup()

    def get_json(self, path: str) -> dict:
        with urllib.request.urlopen(self.base_url + path, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_source_metadata_filter_and_namespaced_file_endpoint(self) -> None:
        config = self.get_json("/api/config")
        self.assertEqual([item["name"] for item in config["libraries"]], ["Codex", "Claude"])
        query = urllib.parse.quote("跨库命中")
        results = self.get_json(f"/api/search?q={query}")["results"]
        self.assertEqual({result["libraryId"] for result in results}, {"codex", "claude"})
        filtered = self.get_json(f"/api/search?q={query}&library=claude")["results"]
        self.assertEqual([result["path"] for result in filtered], ["@claude/同名.md"])
        path = urllib.parse.quote("@claude/同名.md")
        document = self.get_json(f"/api/file?path={path}")
        self.assertEqual(document["libraryName"], "Claude")
        self.assertIn("Claude 文档", document["content"])


if __name__ == "__main__":
    unittest.main()
