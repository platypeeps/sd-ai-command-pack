#!/usr/bin/env python3
"""Build a repo-local Obsidian knowledge-base symlink folder.

The update-spec workflow uses this helper to expose repository knowledge files
to Obsidian without copying content into the repo. It maintains a generated
`.obsidian-kb/` folder, a dashboard of the current links, and the matching
ignore entry in either `.gitignore` or `.git/info/exclude` for local-only
installs. Generated links are intentionally limited to documentation,
repository maps, Trellis spec/context files, and project manifests; caches,
secrets, source trees, build output, and Trellis workspace state stay out.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


KB_DIR = Path(".obsidian-kb")
KB_DASHBOARD = Path("Dashboard.md")
GITIGNORE_ENTRY = ".obsidian-kb/"
LOCAL_ONLY_MARKER_FILE = Path(".sd-ai-command-pack/local-only.txt")
KB_IGNORE_BLOCK_START = "# sd-ai-command-pack obsidian-kb start"
KB_IGNORE_BLOCK_END = "# sd-ai-command-pack obsidian-kb end"
DASHBOARD_MARKER = "<!-- SD-AI-COMMAND-PACK:OBSIDIAN-KB-DASHBOARD -->"
DOC_SUFFIXES = {".adoc", ".md", ".mdx", ".rst", ".txt"}
MAP_SUFFIXES = DOC_SUFFIXES | {".json", ".xml", ".yaml", ".yml"}
ROOT_DOC_PREFIXES = (
    "AGENTS",
    "ARCHITECTURE",
    "CHANGELOG",
    "CONTRIBUTING",
    "DECISION",
    "DECISIONS",
    "DEVELOPMENT",
    "HANDOFF",
    "README",
    "ROADMAP",
)
PROJECT_MANIFESTS = {
    "Cargo.toml",
    "Gemfile",
    "Justfile",
    "Makefile",
    "Package.swift",
    "build.gradle",
    "composer.json",
    "deno.json",
    "deno.jsonc",
    "go.mod",
    "go.work",
    "lerna.json",
    "mix.exs",
    "nx.json",
    "package.json",
    "pnpm-workspace.yaml",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "rush.json",
    "settings.gradle",
    "turbo.json",
    "workspace.json",
}
EXCLUDED_PARTS = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".obsidian",
    ".obsidian-kb",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "target",
    "vendor",
    "venv",
}


def repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    print(
        "warning: not inside a git repository; using the current directory as "
        "the repo root.",
        file=sys.stderr,
    )
    return Path.cwd().resolve()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_excluded(path: Path) -> bool:
    parts = path.parts
    if any(part in EXCLUDED_PARTS for part in parts):
        return True
    return len(parts) >= 2 and parts[0] == ".trellis" and parts[1] == "workspace"


def is_named_doc(path: Path) -> bool:
    upper_name = path.name.upper()
    if path.suffix and path.suffix.lower() not in DOC_SUFFIXES:
        return False
    return (
        any(
            upper_name == prefix
            or upper_name.startswith(f"{prefix}.")
            or upper_name.startswith(f"{prefix}-")
            or upper_name.startswith(f"{prefix}_")
            for prefix in ROOT_DOC_PREFIXES
        )
    )


def is_docs_file(path: Path) -> bool:
    return path.parts[:1] == ("docs",) and path.suffix.lower() in DOC_SUFFIXES


def is_trellis_knowledge(path: Path) -> bool:
    return path in {
        Path(".trellis/config.yaml"),
        Path(".trellis/config.yml"),
        Path(".trellis/workflow.md"),
    } or (
        len(path.parts) >= 3
        and path.parts[0] == ".trellis"
        and path.parts[1] == "spec"
        and path.suffix.lower() in DOC_SUFFIXES
    )


def is_repo_map(path: Path) -> bool:
    lower_name = path.name.lower()
    return (
        ("repomix" in lower_name or "repospec" in lower_name or "repo-map" in lower_name)
        and path.suffix.lower() in MAP_SUFFIXES
    )


def is_project_manifest(path: Path) -> bool:
    return path.name in PROJECT_MANIFESTS


def is_relevant(path: Path) -> bool:
    return (
        is_named_doc(path)
        or is_docs_file(path)
        or is_trellis_knowledge(path)
        or is_repo_map(path)
        or is_project_manifest(path)
    )


def discover_sources(root: Path) -> list[Path]:
    sources: list[Path] = []
    for current_dir, dirnames, filenames in os.walk(root):
        current = Path(current_dir)
        relative_dir = current.relative_to(root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not is_excluded(relative_dir / dirname)
        ]
        for filename in filenames:
            candidate = current / filename
            relative = candidate.relative_to(root)
            if is_excluded(relative):
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if is_relevant(relative):
                sources.append(relative)
    return sorted(set(sources), key=lambda path: path.as_posix())


def _entry_ignores_kb(entry: str) -> bool:
    stripped = entry.strip()
    if not stripped or stripped.startswith("#"):
        return False
    normalized = stripped.lstrip("/").rstrip("/")
    if normalized.endswith("/*"):
        normalized = normalized[:-2]
    return normalized == KB_DIR.as_posix()


def kb_ignore_block() -> str:
    return "\n".join(
        (
            KB_IGNORE_BLOCK_START,
            "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py. DO NOT EDIT MANUALLY.",
            "# Generated Obsidian KB symlink folder; source docs remain in normal repo paths.",
            GITIGNORE_ENTRY,
            KB_IGNORE_BLOCK_END,
        )
    ) + "\n"


def _remove_unmanaged_kb_entries(current: str) -> tuple[str, bool]:
    lines = current.splitlines(keepends=True)
    kept: list[str] = []
    removed = False
    for line in lines:
        if _entry_ignores_kb(line):
            removed = True
            continue
        kept.append(line)
    return "".join(kept), removed


def merge_kb_ignore_block(current: str) -> tuple[str, bool]:
    block = kb_ignore_block()
    start_index = current.find(KB_IGNORE_BLOCK_START)
    end_index = current.find(KB_IGNORE_BLOCK_END)
    has_start = start_index != -1
    has_end = end_index != -1
    if has_start != has_end or (has_start and end_index < start_index):
        raise SystemExit(
            "error: ignore file has incomplete sd-ai-command-pack "
            "obsidian-kb markers"
        )
    if has_start:
        replace_end = end_index + len(KB_IGNORE_BLOCK_END)
        if replace_end < len(current) and current[replace_end] == "\n":
            replace_end += 1
        return current[:start_index] + block + current[replace_end:], True

    prefix, had_unmanaged_entry = _remove_unmanaged_kb_entries(current)
    if not prefix:
        return block, had_unmanaged_entry
    if not prefix.endswith("\n"):
        prefix += "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    return prefix + block, had_unmanaged_entry


def read_text_if_present(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape")
    except FileNotFoundError:
        return None


def ignore_present_state(*, local: bool) -> str:
    return "local-exclude present" if local else "present"


def ignore_change_state(*, local: bool, had_existing_entry: bool) -> str:
    status = "updated" if had_existing_entry else "added"
    return f"local-exclude {status}" if local else status


def ensure_ignore_file(path: Path, *, local: bool) -> str:
    original = read_text_if_present(path) or ""
    merged, had_existing_entry = merge_kb_ignore_block(original)
    if merged == original:
        return ignore_present_state(local=local)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged, encoding="utf-8", errors="surrogateescape")
    return ignore_change_state(local=local, had_existing_entry=had_existing_entry)


def git_info_exclude_path(root: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "info/exclude"],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    return path


def ensure_local_exclude(root: Path) -> str:
    exclude = git_info_exclude_path(root)
    if exclude is None:
        return ensure_repo_gitignore(root)
    return ensure_ignore_file(exclude, local=True)


def ensure_repo_gitignore(root: Path) -> str:
    return ensure_ignore_file(root / ".gitignore", local=False)


def ensure_gitignore(root: Path) -> str:
    if (root / LOCAL_ONLY_MARKER_FILE).is_file():
        return ensure_local_exclude(root)
    return ensure_repo_gitignore(root)


def planned_ignore_file_state(path: Path, *, local: bool) -> str:
    original = read_text_if_present(path) or ""
    merged, had_existing_entry = merge_kb_ignore_block(original)
    if merged == original:
        return ignore_present_state(local=local)
    return ignore_change_state(local=local, had_existing_entry=had_existing_entry)


def planned_gitignore_state(root: Path) -> str:
    if (root / LOCAL_ONLY_MARKER_FILE).is_file():
        exclude = git_info_exclude_path(root)
        if exclude is None:
            return planned_ignore_file_state(root / ".gitignore", local=False)
        return planned_ignore_file_state(exclude, local=True)
    return planned_ignore_file_state(root / ".gitignore", local=False)


def expected_link_target(root: Path, relative_source: Path) -> str:
    source = root / relative_source
    link = root / KB_DIR / relative_source
    return os.path.relpath(source, link.parent)


def collect_link_state(root: Path, sources: list[Path]) -> tuple[int, int, list[str]]:
    kb_root = root / KB_DIR
    wanted = set(sources)
    present = 0
    stale = 0
    issues: list[str] = []

    if kb_root.exists():
        for candidate in sorted(kb_root.rglob("*"), reverse=True):
            if not candidate.is_symlink():
                continue
            relative_candidate = candidate.relative_to(kb_root)
            if relative_candidate in wanted or relative_candidate == KB_DASHBOARD:
                continue
            current = os.readlink(candidate)
            if os.path.isabs(current) or not is_within(candidate.parent / current, root):
                continue
            stale += 1

    for relative_source in sources:
        link = kb_root / relative_source
        target = expected_link_target(root, relative_source)
        if link.is_symlink():
            current = os.readlink(link)
            if current == target:
                present += 1
                continue
            if os.path.isabs(current) or not is_within(link.parent / current, root):
                issues.append(f"{relative_source.as_posix()} has a user-owned symlink")
                continue
            issues.append(f"{relative_source.as_posix()} points at {current!r}")
        elif link.exists():
            issues.append(f"{relative_source.as_posix()} is occupied by a non-symlink")
        else:
            issues.append(f"{relative_source.as_posix()} is missing")

    return present, stale, issues


def prune_stale_symlinks(kb_root: Path, wanted: set[Path], root: Path) -> int:
    if not kb_root.exists():
        return 0
    removed = 0
    for candidate in sorted(kb_root.rglob("*"), reverse=True):
        if candidate.is_symlink():
            relative_candidate = candidate.relative_to(kb_root)
            if relative_candidate in wanted or relative_candidate == KB_DASHBOARD:
                continue
            current = os.readlink(candidate)
            # Only prune links this tool would have created (relative target
            # resolving inside the repo); leave user-placed links untouched.
            if os.path.isabs(current) or not is_within(
                candidate.parent / current, root
            ):
                continue
            candidate.unlink()
            removed += 1
        elif candidate.is_dir() and not any(candidate.iterdir()):
            candidate.rmdir()
    return removed


def markdown_link_text(path: Path) -> str:
    return path.name.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def markdown_link_target(path: Path) -> str:
    return quote(path.as_posix(), safe="/._-~")


def dashboard_content(root: Path, sources: list[Path]) -> str:
    lines = [
        "# Obsidian KB Dashboard",
        "",
        DASHBOARD_MARKER,
        "",
        "Generated by `scripts/sd-ai-command-pack-update-spec-kb.py`.",
        f"Repository: `{root.name}`",
        "",
    ]

    if not sources:
        lines.extend(
            [
                "No repository knowledge links were found.",
                "",
            ]
        )
        return "\n".join(lines)

    current_parent: Path | None = None
    for source in sources:
        parent = source.parent
        if parent != current_parent:
            if current_parent is not None:
                lines.append("")
            heading = "Repository root" if parent == Path(".") else parent.as_posix()
            lines.append(f"## {heading}")
            lines.append("")
            current_parent = parent
        lines.append(
            f"- [{markdown_link_text(source)}]({markdown_link_target(source)})"
        )

    lines.append("")
    return "\n".join(lines)


def write_dashboard(
    kb_root: Path,
    root: Path,
    sources: list[Path],
) -> tuple[str, str | None]:
    dashboard = kb_root / KB_DASHBOARD
    content = dashboard_content(root, sources)

    if dashboard.is_symlink():
        return "conflict", f"{KB_DASHBOARD.as_posix()} is a symlink"
    if dashboard.exists() and not dashboard.is_file():
        return "conflict", f"{KB_DASHBOARD.as_posix()} is not a file"
    current = read_text_if_present(dashboard)
    if current is not None:
        if current == content:
            return "present", None
        if DASHBOARD_MARKER not in current:
            return (
                "conflict",
                f"{KB_DASHBOARD.as_posix()} exists and is not generated by this tool",
            )
        dashboard.write_text(content, encoding="utf-8", errors="surrogateescape")
        return "updated", None

    dashboard.write_text(content, encoding="utf-8", errors="surrogateescape")
    return "created", None


def planned_dashboard_state(
    kb_root: Path,
    root: Path,
    sources: list[Path],
) -> tuple[str, str | None]:
    dashboard = kb_root / KB_DASHBOARD
    content = dashboard_content(root, sources)

    if dashboard.is_symlink():
        return "conflict", f"{KB_DASHBOARD.as_posix()} is a symlink"
    if dashboard.exists() and not dashboard.is_file():
        return "conflict", f"{KB_DASHBOARD.as_posix()} is not a file"
    current = read_text_if_present(dashboard)
    if current is not None:
        if current == content:
            return "present", None
        if DASHBOARD_MARKER not in current:
            return (
                "conflict",
                f"{KB_DASHBOARD.as_posix()} exists and is not generated by this tool",
            )
        return "updated", None

    return "created", None


def create_links(root: Path, sources: list[Path]) -> tuple[int, int, list[str]]:
    kb_root = root / KB_DIR
    kb_root.mkdir(parents=True, exist_ok=True)
    wanted = set(sources)
    removed = prune_stale_symlinks(kb_root, wanted, root)
    linked = 0
    conflicts: list[str] = []

    for relative_source in sources:
        source = root / relative_source
        link = kb_root / relative_source
        link.parent.mkdir(parents=True, exist_ok=True)
        relative_target = os.path.relpath(source, link.parent)

        if link.is_symlink():
            current = os.readlink(link)
            if current == relative_target:
                linked += 1
                continue
            # Only replace links that look tool-created: a relative target that
            # resolves back inside the repo. Anything else (absolute target, or
            # a link escaping the repo) is treated as a user-owned conflict and
            # left untouched rather than silently destroyed.
            if os.path.isabs(current) or not is_within(link.parent / current, root):
                conflicts.append(relative_source.as_posix())
                continue
            link.unlink()
        elif link.exists():
            conflicts.append(relative_source.as_posix())
            continue

        # Defense-in-depth: never create a link whose target escapes the repo.
        if not is_within(link.parent / relative_target, root):
            conflicts.append(relative_source.as_posix())
            continue
        link.symlink_to(relative_target)
        linked += 1

    return linked, removed, conflicts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build or verify the repo-local .obsidian-kb symlink folder used by "
            "the SD AI command pack update-spec workflow."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="report the planned refresh without writing files",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify the generated folder and ignore entry are current without writing files",
    )
    return parser.parse_args(argv)


def report_kb_state(
    *,
    root: Path,
    mode: str | None,
    gitignore_state: str,
    symlinks: int,
    stale: int,
    dashboard_state: str,
    conflicts: list[str],
) -> None:
    print(f"Obsidian KB: {KB_DIR}")
    if mode is not None:
        print(f"mode: {mode}")
    print(f"gitignore: {gitignore_state}")
    print(f"symlinks: {symlinks}")
    print(f"stale symlinks removed: {stale}")
    print(f"dashboard: {dashboard_state}")
    if conflicts:
        print("conflicts:")
        for conflict in conflicts:
            print(f"  - {conflict}")
    else:
        print("conflicts: none")
    source = shlex.quote(str(root / KB_DIR))
    target = shlex.quote(f"/absolute/path/to/vault/{root.name}-KB")
    print("vault link example: " f"ln -s {source} {target}")


def dry_run(root: Path) -> int:
    sources = discover_sources(root)
    present, stale, link_issues = collect_link_state(root, sources)
    dashboard_state, dashboard_conflict = planned_dashboard_state(
        root / KB_DIR,
        root,
        sources,
    )
    conflicts = [
        issue for issue in link_issues if not issue.endswith(" is missing")
    ]
    if dashboard_conflict is not None:
        conflicts.append(dashboard_conflict)

    report_kb_state(
        root=root,
        mode="dry-run",
        gitignore_state=f"would be {planned_gitignore_state(root)}",
        symlinks=present,
        stale=stale,
        dashboard_state=f"would be {dashboard_state}",
        conflicts=conflicts,
    )
    print(f"planned symlinks: {len(sources)}")
    return 0


def check_current(root: Path) -> int:
    sources = discover_sources(root)
    present, stale, link_issues = collect_link_state(root, sources)
    gitignore_state = planned_gitignore_state(root)
    dashboard_state, dashboard_conflict = planned_dashboard_state(
        root / KB_DIR,
        root,
        sources,
    )

    conflicts = list(link_issues)
    if dashboard_conflict is not None:
        conflicts.append(dashboard_conflict)
    if gitignore_state not in {"present", "local-exclude present"}:
        conflicts.append(f"ignore entry is not current: {gitignore_state}")
    if stale:
        conflicts.append(f"{stale} stale generated symlink(s) would be removed")
    if dashboard_state != "present":
        conflicts.append(f"dashboard is not current: {dashboard_state}")

    report_kb_state(
        root=root,
        mode="check",
        gitignore_state=gitignore_state,
        symlinks=present,
        stale=stale,
        dashboard_state=dashboard_state,
        conflicts=conflicts,
    )
    print(f"expected symlinks: {len(sources)}")
    return 1 if conflicts else 0


def refresh(root: Path) -> int:
    try:
        gitignore_state = ensure_gitignore(root)
        sources = discover_sources(root)
        linked, removed, conflicts = create_links(root, sources)
        dashboard_state, dashboard_conflict = write_dashboard(
            root / KB_DIR,
            root,
            sources,
        )
        if dashboard_conflict is not None:
            conflicts.append(dashboard_conflict)
    except OSError as error:
        print(f"error: failed to refresh {KB_DIR}: {error}", file=sys.stderr)
        return 2

    report_kb_state(
        root=root,
        mode=None,
        gitignore_state=gitignore_state,
        symlinks=linked,
        stale=removed,
        dashboard_state=dashboard_state,
        conflicts=conflicts,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()

    try:
        if args.dry_run:
            return dry_run(root)
        if args.check:
            return check_current(root)
        return refresh(root)
    except OSError as error:
        print(f"error: failed to inspect {KB_DIR}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
