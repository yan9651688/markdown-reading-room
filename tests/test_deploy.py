from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployTests(unittest.TestCase):
    def test_new_install_without_a_source_points_to_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "reader"
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "deploy.py"), "--output", str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=environment,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("scripts/discover.py", completed.stderr)

    def test_deploy_creates_a_runnable_reader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            content = base / "中文文档"
            output = base / "reader"
            content.mkdir()
            (content / "欢迎.md").write_text("# 欢迎", encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "ascii"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "deploy.py"),
                    "--content",
                    str(content),
                    "--output",
                    str(output),
                    "--title",
                    "测试阅读室",
                    "--port",
                    "43123",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            config = json.loads((output / "reader.json").read_text(encoding="utf-8"))
            marker = json.loads((output / ".markdown-reader-install.json").read_text(encoding="utf-8"))
            self.assertEqual(config["root"], str(content.resolve()))
            self.assertEqual(config["libraries"][0]["root"], str(content.resolve()))
            self.assertEqual(config["title"], "测试阅读室")
            self.assertEqual(marker["format"], 3)
            self.assertEqual(marker["version"], "0.4.1")
            self.assertTrue((output / "static" / "app.js").is_file())
            self.assertTrue((output / "start-reader.bat").is_file())

    def test_deploy_accepts_multiple_named_libraries_and_preserves_them_on_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            codex = base / "codex-docs"
            claude = base / "claude-docs"
            output = base / "reader"
            codex.mkdir()
            claude.mkdir()
            command = [
                sys.executable,
                str(ROOT / "scripts" / "deploy.py"),
                "--library",
                f"Codex={codex}",
                "--library",
                f"Claude={claude}",
                "--output",
                str(output),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            config = json.loads((output / "reader.json").read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in config["libraries"]], ["codex", "claude"])
            self.assertEqual([item["name"] for item in config["libraries"]], ["Codex", "Claude"])
            self.assertEqual(config["root"], str(codex.resolve()))

            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "deploy.py"), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            updated = json.loads((output / "reader.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["libraries"], config["libraries"])


if __name__ == "__main__":
    unittest.main()
