#!/usr/bin/env python3
"""Build a clean skill ZIP from the source repository."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = "serve-markdown-library"
INCLUDED_FILES = (
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("scripts/deploy.py"),
)
INCLUDED_TREES = (Path("assets/app"),)


def iter_release_files() -> list[Path]:
    files = list(INCLUDED_FILES)
    for tree in INCLUDED_TREES:
        files.extend(path.relative_to(REPO_ROOT) for path in (REPO_ROOT / tree).rglob("*") if path.is_file())
    return sorted(set(files), key=lambda path: path.as_posix())


def main() -> int:
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
