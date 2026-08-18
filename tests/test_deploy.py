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
            self.assertEqual(config["title"], "测试阅读室")
            self.assertEqual(marker["format"], 2)
            self.assertTrue((output / "static" / "app.js").is_file())
            self.assertTrue((output / "start-reader.bat").is_file())


if __name__ == "__main__":
    unittest.main()
