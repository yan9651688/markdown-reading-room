from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BuildReleaseTests(unittest.TestCase):
    def test_release_contains_only_runtime_skill_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "skill.zip"
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "ascii"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build_release.py"), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
            self.assertIn("serve-markdown-library/SKILL.md", names)
            self.assertIn("serve-markdown-library/assets/app/server.py", names)
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith((".pyc", ".pyo")) for name in names))
            self.assertFalse(any(name.startswith("serve-markdown-library/tests/") for name in names))


if __name__ == "__main__":
    unittest.main()
