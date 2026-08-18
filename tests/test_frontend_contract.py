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
        self.assertIn("搜索标题、路径和正文", html)
        self.assertIn('data-library-view="recent"', html)
        self.assertIn('data-library-view="favorites"', html)
        self.assertIn("md-reader-scroll-positions", javascript)
        self.assertIn("/api/search", javascript)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_javascript_syntax(self) -> None:
        subprocess.run(["node", "--check", str(STATIC / "app.js")], check=True)


if __name__ == "__main__":
    unittest.main()
