from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import discover  # noqa: E402


class DiscoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.codex = self.home / ".codex" / "skills"
        self.agents = self.home / ".agents" / "skills"
        self.codex.mkdir(parents=True)
        self.agents.mkdir(parents=True)
        (self.codex / "SKILL.md").write_text("# Codex", encoding="utf-8")
        (self.codex / "node_modules").mkdir()
        (self.codex / "node_modules" / "ignored.md").write_text("ignored", encoding="utf-8")
        (self.agents / "通用.md").write_text("# Agent", encoding="utf-8")

        self.projects = self.home / "Documents" / "Projects"
        client = self.projects / "client-a"
        (client / ".git").mkdir(parents=True)
        (client / "docs").mkdir()
        (client / "docs" / "方案.md").write_text("# 方案", encoding="utf-8")

        self.reader = self.base / "reader-package"
        (self.reader / "scripts").mkdir(parents=True)
        (self.reader / "assets" / "app").mkdir(parents=True)
        (self.reader / "SKILL.md").write_text("reader", encoding="utf-8")
        (self.reader / "scripts" / "deploy.py").write_text("", encoding="utf-8")
        (self.reader / "assets" / "app" / "server.py").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_discovers_known_agent_sources_and_confirmable_projects(self) -> None:
        before = sorted(str(path.relative_to(self.base)) for path in self.base.rglob("*"))
        report = discover.discover_sources(
            home=self.home,
            cwd=self.reader,
            scan_roots=[self.projects],
            environment={},
        )
        after = sorted(str(path.relative_to(self.base)) for path in self.base.rglob("*"))
        self.assertEqual(after, before)
        candidates = report["candidates"]
        by_name = {item["name"]: item for item in candidates}
        self.assertEqual(by_name["Codex Skills"]["markdownCount"], 1)
        self.assertEqual(by_name["通用 Agent Skills"]["markdownCount"], 1)
        self.assertEqual(by_name["client-a 文档"]["confidence"], "medium")
        self.assertIn('--library "Codex Skills=', by_name["Codex Skills"]["deployArgument"])
        self.assertFalse(any(item["path"] == str(self.reader) for item in candidates))

        references = {item["name"]: item for item in report["references"]}
        self.assertIn("Claude Skills", references)
        self.assertFalse(references["Claude Skills"]["exists"])

    def test_known_source_is_not_duplicated_when_used_as_scan_root(self) -> None:
        report = discover.discover_sources(
            home=self.home,
            cwd=self.reader,
            scan_roots=[self.codex],
            environment={},
        )
        paths = [item["path"] for item in report["candidates"]]
        self.assertEqual(paths.count(str(self.codex.resolve())), 1)

    def test_json_cli_is_machine_readable(self) -> None:
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "discover.py"),
                "--home",
                str(self.home),
                "--scan-root",
                str(self.projects),
                "--json",
            ],
            cwd=self.reader,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["readOnly"])
        self.assertGreaterEqual(len(payload["candidates"]), 3)


if __name__ == "__main__":
    unittest.main()
