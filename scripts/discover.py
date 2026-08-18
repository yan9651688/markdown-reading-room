#!/usr/bin/env python3
"""Discover likely Markdown library roots without modifying user files."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".tools",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "target",
    "venv",
}
PROJECT_MARKER_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "package.json",
    "pyproject.toml",
}
PROJECT_MARKER_DIRECTORIES = {".git", ".codex", ".claude", "docs", "documentation", "notes"}


@dataclass(frozen=True)
class Candidate:
    name: str
    path: str
    markdownCount: int
    confidence: str
    kind: str
    reason: str
    truncated: bool = False

    def deploy_argument(self) -> str:
        return f'--library "{self.name}={self.path}"'


@dataclass(frozen=True)
class ReferencePath:
    name: str
    path: str
    exists: bool
    markdownCount: int
    hint: str
    truncated: bool = False


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass


def normalized_path(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    return os.path.normcase(str(resolved))


def count_markdown(
    root: Path,
    *,
    max_depth: int = 10,
    max_directories: int = 6000,
    max_files: int = 20_000,
) -> tuple[int, bool]:
    """Count supported Markdown files with bounded, symlink-free traversal."""
    if not root.is_dir():
        return 0, False
    count = 0
    directories = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        directories += 1
        if directories > max_directories:
            return count, True
        try:
            entries = list(os.scandir(directory))
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if entry.name.casefold() in IGNORED_DIRECTORIES or entry.is_symlink():
                continue
            try:
                if entry.is_file(follow_symlinks=False):
                    if Path(entry.name).suffix.casefold() in MARKDOWN_EXTENSIONS:
                        count += 1
                        if count >= max_files:
                            return count, True
                elif depth < max_depth and entry.is_dir(follow_symlinks=False):
                    stack.append((Path(entry.path), depth + 1))
            except (OSError, PermissionError):
                continue
    return count, False


def has_direct_markdown(directory: Path) -> bool:
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if (
                    not entry.is_symlink()
                    and entry.is_file(follow_symlinks=False)
                    and Path(entry.name).suffix.casefold() in MARKDOWN_EXTENSIONS
                ):
                    return True
        return False
    except (OSError, PermissionError):
        return False


def has_project_signal(directory: Path) -> bool:
    if any((directory / marker).is_file() for marker in PROJECT_MARKER_FILES):
        return True
    for marker in PROJECT_MARKER_DIRECTORIES:
        path = directory / marker
        if not path.is_dir():
            continue
        if marker in {".git", ".codex", ".claude"}:
            return True
        count, _ = count_markdown(path, max_depth=3, max_directories=400, max_files=1)
        if count:
            return True
    return has_direct_markdown(directory)


def is_reader_package(directory: Path) -> bool:
    return (
        (directory / "SKILL.md").is_file()
        and (directory / "scripts" / "deploy.py").is_file()
        and (directory / "assets" / "app" / "server.py").is_file()
    )


def iter_project_roots(search_root: Path, max_depth: int = 2) -> list[Path]:
    if not search_root.is_dir():
        return []
    roots: list[Path] = []
    queue: list[tuple[Path, int]] = [(search_root, 0)]
    while queue:
        directory, depth = queue.pop(0)
        if is_reader_package(directory):
            continue
        if has_project_signal(directory):
            roots.append(directory)
            continue
        if depth >= max_depth:
            continue
        try:
            children = sorted(
                (
                    Path(entry.path)
                    for entry in os.scandir(directory)
                    if entry.is_dir(follow_symlinks=False)
                    and not entry.is_symlink()
                    and entry.name.casefold() not in IGNORED_DIRECTORIES
                    and not entry.name.startswith(".")
                ),
                key=lambda path: path.name.casefold(),
            )
        except (OSError, PermissionError):
            continue
        queue.extend((child, depth + 1) for child in children)
    return roots


def known_agent_locations(home: Path) -> list[tuple[str, Path, str]]:
    return [
        ("Codex Skills", home / ".codex" / "skills", "Codex 常见技能目录"),
        ("Claude Skills", home / ".claude" / "skills", "Claude 常见技能目录"),
        ("通用 Agent Skills", home / ".agents" / "skills", "通用 Agent 常见技能目录"),
        ("Gemini Skills", home / ".gemini" / "skills", "Gemini 常见技能目录"),
        ("Cursor Rules", home / ".cursor" / "rules", "Cursor 常见规则目录"),
    ]


def common_reference_locations(
    home: Path,
    cwd: Path,
    environment: Mapping[str, str],
) -> list[tuple[str, Path, str]]:
    values = [
        ("当前工作目录", cwd, "Agent 当前正在处理的项目可能位于这里"),
        ("Documents", home / "Documents", "项目文档和工作资料的常见位置"),
        ("Desktop", home / "Desktop", "临时项目和导出文档的常见位置"),
        ("Projects", home / "Projects", "代码项目的常见位置"),
        ("Workspace", home / "Workspace", "工作区的常见位置"),
    ]
    one_drive = environment.get("OneDrive") or environment.get("ONEDRIVE")
    if one_drive:
        root = Path(one_drive).expanduser()
        values.extend(
            [
                ("OneDrive Documents", root / "Documents", "OneDrive 同步文档目录"),
                ("OneDrive Desktop", root / "Desktop", "OneDrive 同步桌面目录"),
            ]
        )
    return values


def discover_sources(
    *,
    home: Path | None = None,
    cwd: Path | None = None,
    scan_roots: list[Path] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    selected_home = (home or Path.home()).expanduser().resolve()
    selected_cwd = (cwd or Path.cwd()).expanduser().resolve()
    selected_environment = environment if environment is not None else os.environ
    explicit_roots = [path.expanduser().resolve() for path in (scan_roots or [])]

    candidates: dict[str, Candidate] = {}
    references: dict[str, ReferencePath] = {}

    def add_reference(name: str, path: Path, hint: str, *, count_depth: int = 3) -> None:
        key = normalized_path(path)
        if key in references:
            return
        exists = path.is_dir()
        count, truncated = count_markdown(
            path,
            max_depth=count_depth,
            max_directories=1200,
            max_files=5000,
        ) if exists else (0, False)
        references[key] = ReferencePath(name, str(path), exists, count, hint, truncated)

    for name, path, reason in known_agent_locations(selected_home):
        add_reference(name, path, reason, count_depth=8)
        count, truncated = count_markdown(path) if path.is_dir() else (0, False)
        if count:
            key = normalized_path(path)
            candidates[key] = Candidate(name, str(path.resolve()), count, "high", "agent", reason, truncated)

    for name, path, hint in common_reference_locations(selected_home, selected_cwd, selected_environment):
        if is_reader_package(path):
            continue
        add_reference(name, path, hint)

    project_search_roots: list[tuple[Path, str]] = []
    if not is_reader_package(selected_cwd):
        project_search_roots.append((selected_cwd, "当前工作目录中的 Markdown 项目"))
    project_search_roots.extend((root, "用户指定搜索范围中的 Markdown 项目") for root in explicit_roots)

    searched: set[str] = set()
    for search_root, reason in project_search_roots:
        root_key = normalized_path(search_root)
        if root_key in searched or not search_root.is_dir():
            continue
        searched.add(root_key)
        add_reference(search_root.name or str(search_root), search_root, reason, count_depth=5)
        for project_root in iter_project_roots(search_root):
            key = normalized_path(project_root)
            if key in candidates:
                continue
            count, truncated = count_markdown(project_root)
            if not count:
                continue
            name = project_root.name or "项目文档"
            candidates[key] = Candidate(
                f"{name} 文档",
                str(project_root.resolve()),
                count,
                "medium",
                "project",
                reason,
                truncated,
            )

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda item: (0 if item.confidence == "high" else 1, item.name.casefold(), item.path.casefold()),
    )
    ordered_references = sorted(
        references.values(),
        key=lambda item: (0 if item.exists else 1, item.name.casefold(), item.path.casefold()),
    )
    return {
        "format": 1,
        "readOnly": True,
        "candidates": [dict(asdict(item), deployArgument=item.deploy_argument()) for item in ordered_candidates],
        "references": [asdict(item) for item in ordered_references],
    }


def format_count(count: int, truncated: bool) -> str:
    return f"{count}{'+' if truncated else ''} 篇 Markdown"


def print_human_report(report: dict[str, object]) -> None:
    candidates = report["candidates"]
    references = report["references"]
    assert isinstance(candidates, list)
    assert isinstance(references, list)
    print("目录发现完成（只读，未添加或修改任何文件）\n")
    if candidates:
        print("发现的候选来源：")
        for index, item in enumerate(candidates, 1):
            assert isinstance(item, dict)
            confidence = "高可信" if item["confidence"] == "high" else "建议确认"
            print(f"[{index}] {item['name']} · {format_count(int(item['markdownCount']), bool(item['truncated']))} · {confidence}")
            print(f"    {item['path']}")
            print(f"    {item['reason']}")
            print(f"    {item['deployArgument']}")
    else:
        print("暂未发现可直接推荐的 Markdown 来源。")

    print("\n可提供给用户参考的位置：")
    for item in references:
        assert isinstance(item, dict)
        status = format_count(int(item["markdownCount"]), bool(item["truncated"])) if item["exists"] else "目录不存在"
        print(f"- {item['name']}: {item['path']}（{status}）")
        print(f"  {item['hint']}")
    print("\n下一步：把候选目录和数量展示给用户，获得确认后再传给 deploy.py。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读发现可能的 Markdown 文档目录")
    parser.add_argument("--scan-root", action="append", type=Path, help="额外检查的项目父目录，可重复")
    parser.add_argument("--home", type=Path, help="覆盖用户主目录，主要用于代部署或测试")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出，便于 Agent 解析")
    return parser


def main() -> int:
    configure_console()
    args = build_parser().parse_args()
    missing = [path for path in (args.scan_root or []) if not path.expanduser().is_dir()]
    if missing:
        raise SystemExit(f"搜索目录不存在: {missing[0].expanduser()}")
    report = discover_sources(home=args.home, scan_roots=args.scan_root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
