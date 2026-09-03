#!/usr/bin/env python3
"""Report whether the commits a research repo pins are still the commits upstream has.

A research document states what it was read from: ``owner/repo`` @ ``sha``. That pin is
typed by hand and nothing watches it, so a document can go on asserting a commit for weeks
after the source moved. This reads the pins back out of the markdown, finds each source's
checkout, and says which ones have drifted.

The list is never maintained anywhere: it is enumerated from the documents on every run,
so a source added to a brief shows up here without anyone remembering to register it.
Checkouts are matched by git remote URL rather than by directory name, because a vendored
clone is routinely named for its subject and not for its repository.

    research-kit pins [repo_dir ...]

Exit 0 always. This reports; it does not gate.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# `owner/name` @ `sha`  or  `name` @ `sha`
PIN = re.compile(r"`([A-Za-z0-9._/-]+)`\s*@\s*`([0-9a-f]{7,40})`")
FENCE = re.compile(r"^\s*```")
REMOTE = re.compile(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$")

SKIP_DIRS = {"build", ".git", "node_modules", "__pycache__"}
FILE_SUFFIXES = {".md", ".py", ".rs", ".ts", ".js", ".json", ".toml", ".yaml", ".yml"}
SEARCH_ROOT = Path(os.path.expanduser("~/repos"))


def git(repo, *args):
    """Run git in repo, returning stripped stdout, or None if the command failed."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def slug(checkout):
    """owner/name for a checkout, from its origin URL. Falls back to the directory name."""
    url = git(checkout, "remote", "get-url", "origin")
    if url:
        m = REMOTE.search(url.strip())
        if m:
            return m.group(1).lower()
    return Path(checkout).name.lower()


def collect_pins(repo):
    """Every (source, sha) the markdown asserts outside code fences, and who asserts it."""
    found: dict[tuple[str, str], set[str]] = {}
    for path in sorted(Path(repo).rglob("*.md")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        in_fence = False
        for line in text.splitlines():
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for name, sha in PIN.findall(line):
                # A pin names a repository, not a path inside one.
                if (name.endswith("/") or name.count("/") > 1
                        or Path(name).suffix in FILE_SUFFIXES):
                    continue
                found.setdefault((name, sha), set()).add(
                    path.relative_to(repo).as_posix()
                )
    return found


def build_index(repo):
    """Map owner/name and bare name to a checkout, for vendored and sibling clones."""
    index: dict[str, Path] = {}
    roots = list((Path(repo) / "vendor").glob("*"))
    if SEARCH_ROOT.is_dir():
        roots += list(SEARCH_ROOT.glob("*/*"))
    for path in roots:
        if not (path / ".git").exists():
            continue
        full = slug(path)
        index.setdefault(full, path)
        index.setdefault(full.split("/")[-1], path)
        index.setdefault(path.name.lower(), path)
    return index


def fetch_note(checkout):
    fh = Path(checkout) / ".git" / "FETCH_HEAD"
    if not fh.exists():
        return "never fetched"
    days = int((time.time() - fh.stat().st_mtime) // 86400)
    return "fetched today" if days == 0 else f"fetched {days}d ago"


def describe(checkout, sha):
    """Status of one pin against its checkout."""
    if checkout is None:
        return "no checkout", ""
    if git(checkout, "cat-file", "-e", f"{sha}^{{commit}}") is None:
        return "unknown commit", "not in this checkout — never fetched, or the wrong repo"

    tip = next(
        (r for r in ("origin/HEAD", "origin/main", "origin/master")
         if git(checkout, "rev-parse", "--verify", "-q", r)),
        "HEAD",
    )
    behind = git(checkout, "rev-list", "--count", f"{sha}..{tip}")
    note = f"{tip}, {fetch_note(checkout)}"
    if behind is None:
        return "unknown", note
    if behind == "0":
        return "current", note
    return f"behind {behind}", note


def report(repo):
    repo = Path(repo).resolve()
    print(f"== {repo.name}")
    pins = collect_pins(repo)
    if not pins:
        print("  no pinned commits found")
        return

    index = build_index(repo)

    # Collapse `ext-apps` and `modelcontextprotocol/ext-apps` onto one row.
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for (name, sha), files in pins.items():
        checkout = index.get(name.lower()) or index.get(name.split("/")[-1].lower())
        # Resolved sources key on their real repo; unresolved ones key on the bare
        # name, so `x` and `owner/x` still merge. The fuller name wins the label.
        key = slug(checkout) if checkout else name.split("/")[-1].lower()
        entry = merged.setdefault((key, sha), {"checkout": checkout, "files": set(), "label": ""})
        entry["files"] |= files
        label = slug(checkout) if checkout else name.lower()
        if len(label) > len(entry["label"]):
            entry["label"] = label

    rows = []
    for (_key, sha), entry in sorted(merged.items(), key=lambda kv: kv[1]["label"]):
        status, note = describe(entry["checkout"], sha)
        where = (
            str(entry["checkout"]).replace(os.path.expanduser("~"), "~")
            if entry["checkout"] else ""
        )
        rows.append((entry["label"], sha[:8], status, len(entry["files"]), where, note))

    w_id = max(len(r[0]) for r in rows)
    w_st = max(len(r[2]) for r in rows)
    for identity, sha, status, n, where, note in rows:
        cited = f"{n} doc" + ("s" if n != 1 else "")
        print(f"  {identity:<{w_id}}  {sha:<8}  {status:<{w_st}}  {cited:<7}  {where}")
        if note:
            print(f"  {'':<{w_id}}  {'':<8}  {'':<{w_st}}  {'':<7}  {note}")

    stale = [r for r in rows if r[2].startswith("behind")]
    missing = [r for r in rows if r[2] in ("no checkout", "unknown commit")]
    unfetched = [r for r in rows if "never fetched" in r[5]]
    if unfetched:
        print()
        print(f"  {len(unfetched)} checkout(s) have never been fetched. For those, \"current\"")
        print("  means current as of the clone, not as of upstream. Fetch before trusting it:")
        for _identity, _sha, _st, _n, where, _note in unfetched:
            print(f"    git -C {where} fetch")
    if stale:
        print()
        for identity, sha, status, _n, _w, _note in stale:
            print(f"  {identity} is {status}: documents assert {sha}, which is no longer the tip.")
        print("  Re-read the source, or say in Status that the pin is deliberate and dated.")
    if missing:
        print(f"\n  {len(missing)} pin(s) have no checkout here to check against.")


def main() -> int:
    # R10-D6: the repository is the one the caller is standing in. This took
    # `pins [repo_dir ...]` before the kit moved into the pack.
    report(os.getcwd())
    return 0


if __name__ == "__main__":
    sys.exit(main())
