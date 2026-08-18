#!/usr/bin/env python3
"""Build a clean skill ZIP from the source repository."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = "serve-markdown-library"
INCLUDED_FILES = (
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("scripts/deploy.py"),
    Path("scripts/discover.py"),
)
INCLUDED_TREES = (Path("assets/app"),)
EXCLUDED_PARTS = {"__pycache__", ".DS_Store", "Thumbs.db"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


def is_release_file(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    return path.is_file() and not any(part in EXCLUDED_PARTS for part in relative.parts) and path.suffix not in EXCLUDED_SUFFIXES


def iter_release_files() -> list[Path]:
    files = list(INCLUDED_FILES)
    for tree in INCLUDED_TREES:
        files.extend(path.relative_to(REPO_ROOT) for path in (REPO_ROOT / tree).rglob("*") if is_release_file(path))
    return sorted(set(files), key=lambda path: path.as_posix())


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description="构建可分发的 Markdown 阅读室 Skill ZIP")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist" / "Markdown阅读室-Skill.zip")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in iter_release_files():
            source = REPO_ROOT / relative
            archive.write(source, Path(PACKAGE_ROOT) / relative)

    print(f"已生成: {output}")
    print(f"文件数: {len(iter_release_files())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
