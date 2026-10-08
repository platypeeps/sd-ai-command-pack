"""Keep both sides of a CHANGELOG.md conflict that only adds (sd:2174).

A `--catch-up` merge stopped on `CHANGELOG.md` almost every time in the pack:
the branch and the base had each added an entry at the top of the same
section, and every hand resolution was to keep both. This resolves exactly
that case and nothing else. The conflict must be the merge's only unmerged
path, `CHANGELOG.md` at the root, and every hunk must have an empty base, so
neither side edited or removed a line the other still has. The branch's
entries come first, then the base's, with one blank line between them.

Each assumption is checked, not taken: the three stages are one regular-file
mode (a symlink's target reads as text and would merge), the working copy is a
regular file written without following a link, no attribute converts it on
checkout or add, and the text is UTF-8 with LF endings. Anything else takes
the ordinary abort path.

Not `merge=union`: it needs a tracked `.gitattributes`, and it drops the
blank line between two entries, so the result is one run-on list item.
"""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import tempfile

PATH = "CHANGELOG.md"
#: Longer than any line a changelog writes, so a Markdown setext underline
#: (`=======`) is never read as a conflict marker.
MARKER_SIZE = 32
OURS, BASE, SPLIT, THEIRS = ("<" * MARKER_SIZE + " ", "|" * MARKER_SIZE + " ", "=" * MARKER_SIZE,
                             ">" * MARKER_SIZE + " ")
TIMEOUT_SECONDS = 60
#: The file modes a merge may rewrite as text; a symlink (120000) or a
#: gitlink (160000) stores a target, not content.
REGULAR_MODES = {"100644", "100755"}
#: Attributes under which the working copy is not the blob's bytes, so text
#: written from the blobs would be converted again, or wrongly, by `git add`.
CONVERTING = ("filter", "working-tree-encoding", "ident", "eol")


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=TIMEOUT_SECONDS,
                          check=False)  # fixed argv, no shell


def _stages(root: pathlib.Path) -> dict[int, str] | None:
    """The blob of each stage when `CHANGELOG.md` is the only unmerged path.

    None unless all three stages exist with one regular-file mode: a mode
    conflict is a decision, and a symlink's target would merge as text.
    """
    listed = _git(root, "ls-files", "--unmerged", "-z")
    if listed.returncode != 0:
        return None
    stages, modes = {}, set()
    for entry in filter(None, listed.stdout.decode("utf-8", "surrogateescape").split("\0")):
        meta, path = entry.split("\t", 1)
        if path != PATH:
            return None
        mode, blob, stage = meta.split()
        stages[int(stage)] = blob
        modes.add(mode)
    return stages if set(stages) == {1, 2, 3} and len(modes) == 1 and modes <= REGULAR_MODES else None


def _plain(root: pathlib.Path) -> bool:
    """Whether the working copy is a regular file that git stores byte for byte."""
    try:
        if not stat.S_ISREG(os.lstat(root / PATH).st_mode):
            return False
    except OSError:
        return False
    checked = _git(root, "check-attr", "-z", *CONVERTING, "--", PATH)
    if checked.returncode != 0:
        return False
    fields = checked.stdout.decode("utf-8", "surrogateescape").split("\0")
    return all(value in ("unspecified", "unset") or (name == "eol" and value == "lf")
               for name, value in zip(fields[1::3], fields[2::3], strict=True))


def _lines(text: str) -> list[str]:
    """`text` split after each LF only; `splitlines` also splits on U+2028 and others."""
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _write(path: pathlib.Path, text: str) -> bool:
    """Replace a regular file's content, refusing to follow a link put there since."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    except OSError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
        stream.write(text)
    return True


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
    if stages is None or not _plain(root):
        return False
    with tempfile.TemporaryDirectory(prefix="sd-changelog-merge-") as directory:
        files = []
        for stage in (2, 1, 3):
            blob = _git(root, "cat-file", "blob", stages[stage])
            if blob.returncode != 0 or b"\r" in blob.stdout:
                return False  # a CRLF changelog would get LF separators
            path = pathlib.Path(directory) / str(stage)
            path.write_bytes(blob.stdout)
            files.append(str(path))
        merged = _git(root, "merge-file", "-p", "--diff3", f"--marker-size={MARKER_SIZE}",
                      "-L", "ours", "-L", "base", "-L", "theirs", *files)
    # The exit code counts the conflicts, capped at 127; 0 has none to resolve,
    # and an error (binary input, say) exits 255 with nothing on stdout.
    if not 0 < merged.returncode <= 127:
        return False
    try:
        lines = _lines(merged.stdout.decode("utf-8"))
    except UnicodeDecodeError:
        return False
    # Nothing is written unless a conflict hunk parses: an empty resolution
    # of output with no hunk would stage an emptied CHANGELOG.md.
    if not any(line.startswith(OURS) for line in lines):
        return False
    resolved = _keep_both(lines)
    if resolved is None:
        return False
    return _write(root / PATH, "".join(resolved)) and _git(root, "add", "--", PATH).returncode == 0
