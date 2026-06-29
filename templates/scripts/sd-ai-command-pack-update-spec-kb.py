#!/usr/bin/env python3
"""Build a repo-local Obsidian knowledge-base symlink folder."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


KB_DIR = Path(".obsidian-kb")
GITIGNORE_ENTRY = ".obsidian-kb/"
LOCAL_ONLY_MARKER_FILE = Path(".sd-ai-command-pack/local-only.txt")
KB_IGNORE_BLOCK_START = "# sd-ai-command-pack obsidian-kb start"
KB_IGNORE_BLOCK_END = "# sd-ai-command-pack obsidian-kb end"
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
            "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py.",
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


def ensure_ignore_file(path: Path, *, local: bool) -> str:
    original = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    merged, had_existing_entry = merge_kb_ignore_block(original)
    if merged == original:
        return "local-exclude present" if local else "present"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged, encoding="utf-8", errors="replace")
    status = "updated" if had_existing_entry else "added"
    if local:
        return f"local-exclude {status}"
    return status


def git_info_exclude_path(root: Path) -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "info/exclude"],
        cwd=root,
        text=True,
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


def prune_stale_symlinks(kb_root: Path, wanted: set[Path], root: Path) -> int:
    if not kb_root.exists():
        return 0
    removed = 0
    for candidate in sorted(kb_root.rglob("*"), reverse=True):
        if candidate.is_symlink():
            if candidate.relative_to(kb_root) in wanted:
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


def main() -> int:
    root = repo_root()
    os.chdir(root)

    try:
        gitignore_state = ensure_gitignore(root)
        sources = discover_sources(root)
        linked, removed, conflicts = create_links(root, sources)
    except OSError as error:
        print(f"error: failed to refresh {KB_DIR}: {error}", file=sys.stderr)
        return 2

    print(f"Obsidian KB: {KB_DIR}")
    print(f"gitignore: {gitignore_state}")
    print(f"symlinks: {linked}")
    print(f"stale symlinks removed: {removed}")
    if conflicts:
        print("conflicts:")
        for conflict in conflicts:
            print(f"  - {conflict}")
    else:
        print("conflicts: none")
    print(
        "vault link example: "
        f"ln -s {root / KB_DIR} /absolute/path/to/vault/{root.name}-KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
