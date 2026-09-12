#!/usr/bin/env python3
"""The Dependabot guard `sd-review setup-github` emits, and the `--check` diff.

Seven consumers hand-wrote a Dependabot `ignore:` entry for the review-route
pin, in six wordings, five of them reciting a fix commit and a pull request
number beside the real pin -- prose that was stale the day the pin moved past
the commit it cited. Nothing in the pack had ever emitted the entry, so "diff
the file against what the pack writes" was a diff against nothing. This module
is the one copy: `bin/sd_setup_github.py` writes it beside the workflow, and
`--check` reads both back.

Text in, text out. Nothing here opens a file for writing -- the installer is
the one writer in the lane, and `tests/test_sd_review_boundary.py` counts its
write sites -- and nothing here parses YAML: a consumer's `dependabot.yml`
carries comments the pack does not own, and a round-trip through a YAML
library would drop them. The transform finds the github-actions entry, its
`ignore:` list and the one item naming the action by indentation, and touches
those lines and no others.
"""

from __future__ import annotations

import difflib
import pathlib
import re
from typing import Mapping, TextIO

DEPENDABOT_RELATIVE_PATH = pathlib.Path(".github") / "dependabot.yml"
DEPENDENCY = "platypeeps/sd-ai-command-pack/actions/review-route"

# The guard: a comment and one list item in the consumer's `ignore:` list. It
# names no incident, pull request or SHA on purpose. The reason it exists is
# in actions/review-route/README.md and is cited by path, so this text has
# nothing in it that the next pin move can make false.
GUARD_LINES = (
    "# The sd-ai-command-pack pin is set by hand, not by Dependabot. The action",
    "# runs the pack's own code out of the pinned checkout, so a bump is a",
    "# behaviour change across the whole pack, not a version number. Bump it",
    "# deliberately, in its own commit, with",
    "# `sd-review setup-github --pin <sha> --force`. Why the guard exists is",
    "# recorded in the pack at actions/review-route/README.md; this comment",
    "# names no incident, pull request or SHA on purpose, so that it does not",
    "# go stale the next time the pin moves.",
    f'- dependency-name: "{DEPENDENCY}"',
)

_ENTRY = re.compile(r"""^\s*- package-ecosystem:\s*["']?github-actions["']?\s*$""")
_ANY_ENTRY = re.compile(r"^\s*- package-ecosystem:")
_GUARD_ITEM = re.compile(rf"""dependency-name:\s*["']?{re.escape(DEPENDENCY)}["']?\s*$""")
_PIN = re.compile(rf"^\s*(?:- )?uses:\s*{re.escape(DEPENDENCY)}@([0-9a-fA-F]{{7,40}})\b", re.M)


class GuardError(Exception):
    """The file has no place for the guard; the message names why."""


def guard_block(indent: str) -> str:
    """The guard at one indentation, newline-terminated."""

    return "".join(f"{indent}{line}\n" for line in GUARD_LINES)


def _entry(indent: str) -> str:
    """One github-actions entry, `- ` at `indent`, carrying the guard."""

    return (
        f'{indent}- package-ecosystem: "github-actions"\n'
        f'{indent}  directory: "/"\n'
        f"{indent}  schedule:\n"
        f'{indent}    interval: "weekly"\n'
        f"{indent}  open-pull-requests-limit: 5\n"
        f"{indent}  ignore:\n" + guard_block(indent + "    ")
    )


def minimal_file() -> str:
    """The whole file, for a repository that has none."""

    return "version: 2\nupdates:\n" + _entry("  ")


def read_pin(workflow: str) -> str | None:
    """The commit the tracked workflow pins the action to, or None."""

    found = _PIN.search(workflow)
    return found.group(1) if found else None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _end(lines: list[str], start: int, floor: int) -> int:
    """First index after `start` whose non-blank line sits shallower than `floor`."""

    for index in range(start + 1, len(lines)):
        if lines[index].strip() and _indent(lines[index]) < floor:
            return index
    return len(lines)


def _trim(lines: list[str], start: int, stop: int) -> int:
    """`stop` moved back over trailing blank lines, never past `start`."""

    while stop > start and not lines[stop - 1].strip():
        stop -= 1
    return stop


def _blocks(lines: list[str], first: int, stop: int, indent: int) -> list[tuple[int, int]]:
    """Each `- ` item at `indent` in `lines[first:stop]`, with its leading comments.

    A comment run sitting directly above an item, at the item's indentation,
    is the item's: that is where every hand-written guard put its reasoning,
    and replacing the line without the comment would leave the stale prose
    standing over the fresh item.
    """

    starts = []
    for index in range(first, stop):
        if _indent(lines[index]) == indent and lines[index].lstrip().startswith("- "):
            begin = index
            while begin > first and _indent(lines[begin - 1]) == indent and lines[begin - 1].lstrip().startswith("#"):
                begin -= 1
            starts.append(begin)
    return [
        (begin, _trim(lines, begin, starts[n + 1] if n + 1 < len(starts) else stop))
        for n, begin in enumerate(starts)
    ]


def _place(lines: list[str]) -> tuple[str, int, int, int]:
    """Where the guard goes: ('replace'|'append'|'ignore', at, until, indent).

    `replace` names the block the existing guard item occupies; `append` the
    index the guard is inserted at in an existing `ignore:` list; `ignore`
    the index a new `ignore:` key goes at, with the entry's key indentation.
    """

    start = next((i for i, line in enumerate(lines) if _ENTRY.match(line)), None)
    if start is None:
        raise GuardError("no github-actions entry")
    key = _indent(lines[start]) + 2
    stop = _end(lines, start, key)
    ignore = next(
        (i for i in range(start + 1, stop) if _indent(lines[i]) == key and lines[i].strip() == "ignore:"),
        None,
    )
    if ignore is None:
        return "ignore", _trim(lines, start, stop), stop, key
    first = next((i for i in range(ignore + 1, stop) if lines[i].strip()), stop)
    indent = _indent(lines[first]) if first < stop and _indent(lines[first]) > key else key + 2
    until = _end(lines, ignore, indent) if first < stop else ignore + 1
    for begin, end in _blocks(lines, ignore + 1, until, indent):
        if any(_GUARD_ITEM.search(line) for line in lines[begin:end]):
            return "replace", begin, end, indent
    return "append", _trim(lines, ignore + 1, until), until, indent


def guard_state(text: str | None) -> str:
    """'missing' (no file), 'absent' (no guard item), 'same' or 'differs'."""

    if text is None:
        return "missing"
    lines = text.splitlines()
    try:
        action, at, until, indent = _place(lines)
    except GuardError:
        return "absent"
    if action != "replace":
        return "absent"
    return "same" if lines[at:until] == guard_block(" " * indent).splitlines() else "differs"


def rendered(text: str | None) -> str:
    """`text` with the guard in place: the one the installer writes and `--check` expects.

    Idempotent: rendering a rendered file changes nothing, which is what lets
    `--check` say `same` by comparing this with the tracked bytes.
    """

    if text is None:
        return minimal_file()
    lines = text.splitlines()
    try:
        action, at, until, indent = _place(lines)
    except GuardError:
        entries = [i for i, line in enumerate(lines) if _ANY_ENTRY.match(line)]
        if not entries:
            raise GuardError(
                f"{DEPENDABOT_RELATIVE_PATH} has no `- package-ecosystem:` entry to put the "
                "guard beside; add an updates entry or remove the file"
            ) from None
        key = _indent(lines[entries[-1]]) + 2
        at = _trim(lines, entries[-1], _end(lines, entries[-1], key))
        new = _entry(" " * (key - 2)).splitlines()
        return "\n".join(lines[:at] + new + lines[at:]) + "\n"
    if action == "ignore":
        new = [" " * indent + "ignore:"] + guard_block(" " * (indent + 2)).splitlines()
        return "\n".join(lines[:at] + new + lines[at:]) + "\n"
    new = guard_block(" " * indent).splitlines()
    stop = until if action == "replace" else at
    return "\n".join(lines[:at] + new + lines[stop:]) + "\n"


def report_drift(root: pathlib.Path, expected: Mapping[pathlib.Path, str], stream: TextIO) -> int:
    """One line per file, `same <path>` or `DIFFERS <path>` plus a unified diff.

    `DIFFERS` is the word `machine-setup.sh status` greps for in the system
    repository, so a fleet sweep can count drift without parsing the diff.
    Exit 1 on any difference, 0 otherwise; nothing is written.
    """

    differs = 0
    for relative, text in expected.items():
        path = root / relative
        tracked = path.read_text(encoding="utf-8") if path.is_file() else ""
        if tracked == text:
            stream.write(f"same {relative}\n")
            continue
        differs += 1
        stream.write(f"DIFFERS {relative}\n")
        stream.writelines(
            difflib.unified_diff(
                tracked.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"{relative} (tracked)",
                tofile=f"{relative} (this build)",
            )
        )
    return 1 if differs else 0
