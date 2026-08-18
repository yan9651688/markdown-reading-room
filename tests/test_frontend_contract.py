from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "assets" / "app" / "static"


class FrontendContractTests(unittest.TestCase):
    def test_javascript_element_ids_exist_in_html(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        html_ids = set(re.findall(r'\bid="([^"]+)"', html))
        requested_ids = set(re.findall(r'getElementById\("([^"]+)"\)', javascript))
        self.assertEqual(requested_ids - html_ids, set())

    def test_v02_interaction_contract_is_present(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("搜索全部来源的标题与正文", html)
        self.assertIn('data-library-view="recent"', html)
        self.assertIn('data-library-view="favorites"', html)
        self.assertIn("md-reader-scroll-positions", javascript)
        self.assertIn("/api/search", javascript)

    def test_v03_theme_center_contract_is_present(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        appearance = (STATIC / "appearance.js").read_text(encoding="utf-8")
        stylesheet = (STATIC / "app.css").read_text(encoding="utf-8")
        self.assertEqual(html.count('class="theme-card"'), 5)
        for theme in ("ink", "github", "notion", "codex", "claude"):
            self.assertIn(f'data-reading-theme="{theme}"', html)
            self.assertIn(f':root[data-reading-theme="{theme}"]', stylesheet)
            self.assertIn(f':root[data-reading-theme="{theme}"][data-theme="dark"]', stylesheet)
        for mode in ("system", "light", "dark"):
            self.assertIn(f'data-color-mode="{mode}"', html)
        self.assertIn("md-reader-theme-style", javascript)
        self.assertIn("md-reader-color-mode", javascript)
        self.assertIn("prefers-color-scheme: dark", appearance)
        self.assertIn('.theme-card[data-reading-theme]', javascript)
        self.assertLess(html.index('<script src="/appearance.js"'), html.index('<link rel="stylesheet"'))

    def test_v04_multi_library_contract_is_present(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        stylesheet = (STATIC / "app.css").read_text(encoding="utf-8")
        self.assertIn('id="librarySources"', html)
        self.assertIn('id="documentSource"', html)
        self.assertIn("md-reader-library-filter", javascript)
        self.assertIn("library=${encodeURIComponent(state.libraryFilter)}", javascript)
        self.assertIn('node.type === "library"', javascript)
        self.assertIn("splitLibraryPath", javascript)
        self.assertIn(".library-source", stylesheet)
        self.assertIn(".tree-library-heading", stylesheet)
        self.assertIn('[data-source-tone="7"]', stylesheet)

    def test_v042_shared_runtime_contract_is_present(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        runtime = (STATIC / "runtime.js").read_text(encoding="utf-8")
        server = (ROOT / "assets" / "app" / "server.py").read_text(encoding="utf-8")
        deployer = (ROOT / "scripts" / "deploy.py").read_text(encoding="utf-8")
        for source in (html, javascript, server, deployer):
            self.assertIn("0.4.2", source)
        self.assertLess(html.index('<script src="/runtime.js"'), html.index('<script src="/app.js"'))
        self.assertIn('id="addLibraryButton"', html)
        self.assertIn('id="emptyAddLibraryButton"', html)
        self.assertIn("MarkdownRuntime", javascript)
        for command in (
            "get_config",
            "get_tree",
            "search_documents",
            "read_document",
            "resolve_asset_path",
            "discover_libraries",
            "pick_discovery_root",
            "pick_libraries",
            "add_discovered_libraries",
            "remove_library",
        ):
            self.assertIn(f'"{command}"', runtime)

    def test_desktop_source_discovery_contract_is_present(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        stylesheet = (STATIC / "app.css").read_text(encoding="utf-8")
        for element_id in (
            "discoverLibraryButton",
            "discoveryView",
            "startDiscoveryButton",
            "scanFolderButton",
            "manualFolderButton",
            "discoveryCandidates",
            "discoveryReferences",
            "addDiscoveredButton",
        ):
            self.assertIn(f'id="{element_id}"', html)
        self.assertIn("添加文档目录", html)
        self.assertIn("仅在本机读取，不会修改文件", html)
        self.assertIn("选择目录", html)
        self.assertNotIn("Local Source Discovery", html)
        self.assertNotIn("discovery-kicker", html)
        self.assertIn("renderDiscoveryPayload", javascript)
        self.assertIn("candidate.confidence === \"high\"", javascript)
        self.assertIn('`添加 ${count} 个目录`', javascript)
        self.assertIn('state.currentView === "discovery"', javascript)
        self.assertIn(
            'const enteringDiscovery = state.currentView !== "discovery" || elements.discoveryView.hidden',
            javascript,
        )
        self.assertIn(
            'if (enteringDiscovery) requestAnimationFrame(() => { elements.readerPane.scrollTop = 0; });',
            javascript,
        )
        self.assertIn(
            'if (state.currentView !== "discovery" || elements.discoveryView.hidden) {',
            javascript,
        )
        self.assertIn(".discovery-candidate", stylesheet)
        self.assertIn(".is-discovery-view", stylesheet)

    def test_agent_artifact_inbox_contract_is_present(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        stylesheet = (STATIC / "app.css").read_text(encoding="utf-8")
        for element_id in (
            "inboxView",
            "inboxPendingCount",
            "inboxChangeCount",
            "inboxApprovedCount",
            "inboxList",
            "documentReviewState",
            "approveButton",
            "followupButton",
        ):
            self.assertIn(f'id="{element_id}"', html)
        for filter_name in ("pending", "new", "updated", "approved", "all"):
            self.assertIn(f'data-inbox-filter="{filter_name}"', html)
        self.assertIn("文档更新", html)
        self.assertIn("确认当前版本", html)
        self.assertNotIn("Agent Artifact Inbox", html)
        self.assertNotIn("等待你验收的工作", html)
        self.assertNotIn("inbox-kicker", html)
        self.assertIn("moyue-artifact-snapshot-v1", javascript)
        self.assertIn("moyue-review-states-v1", javascript)
        self.assertIn("reconcileArtifactSnapshot", javascript)
        self.assertIn("setReviewDisposition", javascript)
        self.assertIn('elements.inboxList.classList.toggle("has-items"', javascript)
        self.assertIn('const enteringInbox = state.currentView !== "inbox" || elements.inboxView.hidden', javascript)
        self.assertIn('if (state.currentView === "inbox") {\n        renderInbox();', javascript)
        self.assertIn(".artifact-card", stylesheet)
        self.assertIn('[data-review-status="approved"]', stylesheet)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_javascript_syntax(self) -> None:
        for script in ("appearance.js", "runtime.js", "app.js"):
            subprocess.run(["node", "--check", str(STATIC / script)], check=True)


if __name__ == "__main__":
    unittest.main()
