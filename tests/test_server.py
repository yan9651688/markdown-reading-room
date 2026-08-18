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
        self.assertEqual(self.get_json("/health")["version"], "0.2.0")
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


if __name__ == "__main__":
    unittest.main()
