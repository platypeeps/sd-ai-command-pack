"""Keep both sides of a CHANGELOG.md conflict that only adds (sd:2174).

A `--catch-up` merge stopped on `CHANGELOG.md` almost every time in the pack:
the branch and the base had each added an entry at the top of the same
section, and every hand resolution was to keep both. This resolves exactly
that case and nothing else. The conflict must be the merge's only unmerged
path, `CHANGELOG.md` at the root, and every hunk must have an empty base, so
neither side edited or removed a line the other still has. The branch's
entries come first, then the base's, with one blank line between them.

Not `merge=union`: it needs a tracked `.gitattributes`, and it drops the
blank line between two entries, so the result is one run-on list item.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile

PATH = "CHANGELOG.md"
#: Longer than any line a changelog writes, so a Markdown setext underline
#: (`=======`) is never read as a conflict marker.
MARKER_SIZE = 32
OURS, BASE, SPLIT, THEIRS = ("<" * MARKER_SIZE + " ", "|" * MARKER_SIZE + " ", "=" * MARKER_SIZE,
                             ">" * MARKER_SIZE + " ")
TIMEOUT_SECONDS = 60


def keep_both_note(base: str) -> str:
    """The receipt warning a resolved catch-up carries."""
    return (f"catch-up resolved a {PATH} conflict keep-both: this branch's entries first, "
            f"then origin/{base}'s (sd:2174)")


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=TIMEOUT_SECONDS,
                          check=False)  # fixed argv, no shell


def _stages(root: pathlib.Path) -> dict[int, str] | None:
    """The blob of each stage when `CHANGELOG.md` is the only unmerged path."""
    listed = _git(root, "ls-files", "--unmerged", "-z")
    if listed.returncode != 0:
        return None
    stages = {}
    for entry in filter(None, listed.stdout.decode("utf-8", "surrogateescape").split("\0")):
        meta, path = entry.split("\t", 1)
        if path != PATH:
            return None
        _mode, blob, stage = meta.split()
        stages[int(stage)] = blob
    return stages if set(stages) == {1, 2, 3} else None


def _blank(line: str) -> bool:
    return not line.strip()


def _trim(lines: list[str]) -> tuple[list[str], bool, bool]:
    """The lines without edge blank lines, and whether each edge had one."""
    start, end = 0, len(lines)
    while start < end and _blank(lines[start]):
        start += 1
    while end > start and _blank(lines[end - 1]):
        end -= 1
    return lines[start:end], start > 0, end < len(lines)


def _resolution(hunk: dict[str, list[str]]) -> tuple[list[str], bool, bool] | None:
    """One hunk as ours then theirs, and whether a blank line leads and trails it.

    None when the hunk has a base: one side edited what the other kept.
    """
    if any(not _blank(text) for text in hunk["base"]):
        return None
    ours, theirs = _trim(hunk["ours"]), _trim(hunk["theirs"])
    cores = [side[0] for side in (ours, theirs) if side[0]]
    lines = [line for index, core in enumerate(cores) for line in ["\n"] * (index > 0) + core]
    return lines, bool(lines) and (ours[1] or theirs[1]), bool(lines) and (ours[2] or theirs[2])


def _keep_both(merged: list[str]) -> list[str] | None:
    """`merged` (diff3 output) with each conflict resolved ours then theirs.

    A blank line at a hunk's edge is written once: never a second one beside
    the context's own, so two entries never end up two blank lines apart.
    """
    out: list[str] = []
    hunk: dict[str, list[str]] | None = None
    part, trailing = "", False
    for line in merged:
        bare = line.rstrip("\n")
        if hunk is None and bare.startswith(OURS):
            hunk, part = {"ours": [], "base": [], "theirs": []}, "ours"
        elif hunk is not None and (bare.startswith(BASE) or bare == SPLIT):
            part = "base" if bare.startswith(BASE) else "theirs"
        elif hunk is not None and bare.startswith(THEIRS):
            resolution = _resolution(hunk)
            if resolution is None:
                return None
            lines, leading, trailing = resolution
            out.extend(["\n"] * (leading and bool(out) and not _blank(out[-1])) + lines + ["\n"] * trailing)
            hunk = None
        elif hunk is not None:
            hunk[part].append(line if line.endswith("\n") else line + "\n")
        else:
            if not (trailing and _blank(line)):  # the resolution already wrote this blank line
                out.append(line)
            trailing = False
    return None if hunk is not None else out


def resolve_keep_both(root: pathlib.Path) -> bool:
    """Resolve and stage a keep-both `CHANGELOG.md`; False, touching nothing, otherwise."""
    stages = _stages(root)
    if stages is None:
        return False
    with tempfile.TemporaryDirectory(prefix="sd-changelog-merge-") as directory:
        files = []
        for stage in (2, 1, 3):
            blob = _git(root, "cat-file", "blob", stages[stage])
            if blob.returncode != 0:
                return False
            path = pathlib.Path(directory) / str(stage)
            path.write_bytes(blob.stdout)
            files.append(str(path))
        merged = _git(root, "merge-file", "-p", "--diff3", f"--marker-size={MARKER_SIZE}",
                      "-L", "ours", "-L", "base", "-L", "theirs", *files)
    if merged.returncode <= 0:
        return False  # 0 has no conflict to resolve; a negative code is an error
    resolved = _keep_both(merged.stdout.decode("utf-8").splitlines(keepends=True))
    if resolved is None:
        return False
    (root / PATH).write_text("".join(resolved), encoding="utf-8")
    return _git(root, "add", "--", PATH).returncode == 0
