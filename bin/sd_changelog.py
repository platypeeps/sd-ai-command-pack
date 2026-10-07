"""Changelog entries as workflow-database rows (sd:2783, step 1).

A pull request in an opted-in repository states its entry in a `## Changelog`
section of its body, and `sd-ship merge` stores that entry as one checkpoint
row in the `state` table, so feature branches stop sharing `CHANGELOG.md`.
The design is in `docs/work/2026-10-05-changelog-in-database/design.md`.

This module holds the parts with no side effect but the row write: the section
parser, the privacy check, the row key, the idempotent writer and the reader.
Nothing calls them yet; `sd-ship` and `sd changelog` do in later steps.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
from typing import Any

#: The `state` key prefix; the key is `<PREFIX><owner/name>:<pull request>`.
PREFIX = "sd-changelog:v1:"
#: The six Keep a Changelog subsections, in the order render writes them.
SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
#: The explicit no-entry answer (ruling Q1).
NONE = "none"
#: Above every UTF-8 character, so `key < prefix + TOP` closes a range scan.
TOP = "\U0010ffff"
TIMEOUT_SECONDS = 60

_FENCE = re.compile(r"^ {0,3}(```|~~~)")
_HEADING = re.compile(r"^ {0,3}(#{1,2})(?!#)(?:[ \t]+(.*?))?[ \t#]*$")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BULLET = re.compile(r"^[-*+][ \t]+(\S.*)$")


class ChangelogError(ValueError):
    """A refusal; `code` is the machine-readable reason a caller reports."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _heading(line: str) -> str | None:
    """The text of a level-1 or level-2 ATX heading, or None."""
    match = _HEADING.match(line)
    return None if match is None else (match.group(2) or "")


def _section(body: str) -> list[str]:
    """The lines of the one `## Changelog` section, outside code fences.

    A heading inside a fence is an example, not the section. The section runs
    to the next level-1 or level-2 heading.
    """
    sections: list[list[str]] = []
    fenced = inside = False
    for line in body.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else _heading(line)
        if heading is not None:
            inside = heading.strip().lower() == "changelog"
            if inside:
                sections.append([])
        elif inside:
            sections[-1].append(line)
    if not sections:
        raise ChangelogError("changelog_missing", "the pull request body has no `## Changelog` section")
    if len(sections) > 1:
        raise ChangelogError("changelog_invalid", "the pull request body has more than one `## Changelog` section")
    return sections[0]


def _invalid(number: int, reason: str) -> ChangelogError:
    return ChangelogError("changelog_invalid", f"`## Changelog` line {number}: {reason}")


def _entries(lines: list[str]) -> list[dict[str, Any]]:
    """`{section, text}` per bullet; continuation lines lose two spaces of indent."""
    entries: list[dict[str, Any]] = []
    section, counted, after_text = None, 0, False
    for number, line in enumerate(lines, 1):
        stripped = line.rstrip()
        bullet = _BULLET.match(stripped)
        if not stripped:
            after_text = False
        elif stripped.startswith("### "):
            if section is not None and counted == len(entries):
                raise _invalid(number, f"`### {section}` has no bullet")
            section, counted = stripped[4:].strip(), len(entries)
            if section not in SECTIONS:
                raise _invalid(number, f"unknown subsection `{section}`; use one of {', '.join(SECTIONS)}")
            after_text = False
        elif bullet and section is not None:
            entries.append({"section": section, "text": bullet.group(1)})
            after_text = True
        elif len(entries) > counted and (after_text or line[:1] in (" ", "\t")):
            indent = len(stripped) - len(stripped.lstrip(" "))
            entries[-1]["text"] += "\n" + stripped[min(indent, 2):]
            after_text = True
        else:
            raise _invalid(number, "text outside a `### <subsection>` bullet")
    if section is None:
        raise ChangelogError("changelog_invalid", "`## Changelog` is empty; write `none` or a `### <subsection>` bullet")
    if counted == len(entries):
        raise _invalid(len(lines), f"`### {section}` has no bullet")
    return entries


def parse_section(body: str) -> list[dict[str, Any]]:
    """The entries of `body`'s `## Changelog` section, in body order.

    An empty list for the one word `none`. Raises `ChangelogError` with code
    `changelog_missing` when the section is absent and `changelog_invalid`
    when it holds anything but `none` or `### <subsection>` bullets. HTML
    comments are dropped first, so the template's guidance never parses.
    """
    text = _COMMENT.sub("", "\n".join(_section(body)))
    return [] if text.strip() == NONE else _entries(text.split("\n"))


def private(text: str, patterns: list[str]) -> list[int]:
    """The 1-based numbers of the lines in `text` that match a privacy pattern.

    `patterns` are the lines of the pattern file: one extended regular
    expression each, blank and `#` lines skipped. `grep -E` matches them,
    as `local-leak-guard` does, so a POSIX class such as `[[:digit:]]` means
    the same here. No pattern at all raises `changelog_patterns_missing`: an
    empty set would pass every text unchecked.
    """
    usable = [pattern for pattern in patterns if pattern.strip() and not pattern.lstrip().startswith("#")]
    if not usable:
        raise ChangelogError("changelog_patterns_missing", "the privacy-pattern file holds no pattern")
    argv = ["grep", "-n", "-E"]
    for pattern in usable:
        argv += ["-e", pattern]
    done = subprocess.run(argv, input=text.encode("utf-8"), capture_output=True, timeout=TIMEOUT_SECONDS,
                          check=False)  # fixed argv, no shell
    if done.returncode not in (0, 1):
        raise ChangelogError("changelog_patterns_invalid",
                             "grep -E refused the privacy patterns: " + done.stderr.decode("utf-8", "replace").strip())
    return [int(line.split(b":", 1)[0]) for line in done.stdout.splitlines()]


def row_key(slug: str, pull_request: int) -> str:
    """`sd-changelog:v1:<owner/name>:<number>`, the slug in lower case."""
    if type(pull_request) is not int or pull_request <= 0:
        raise ValueError(f"a pull request number is a positive integer, not {pull_request!r}")
    return f"{PREFIX}{slug.lower()}:{pull_request}"


def write(connection: sqlite3.Connection, row: dict[str, Any]) -> int:
    """Store `row` as its pull request's newest revision; return the revision id.

    A row whose newest revision already has the same `merge_commit` and
    `body_digest` is left alone, so a rerun of the merge adds nothing. A
    changed digest is a correction and appends a revision.
    """
    from sd_db import ship  # noqa: PLC0415

    for field in ("merge_commit", "body_digest"):
        if not isinstance(row.get(field), str) or not row[field]:
            raise ValueError(f"a changelog row needs its {field}")
    row = {**row, "repository": str(row["repository"]).lower()}
    key = row_key(row["repository"], row["pull_request"])
    revision, current = ship.read(connection, key)
    if current.get("merge_commit") == row["merge_commit"] and current.get("body_digest") == row["body_digest"]:
        return revision
    return int(ship.save(connection, key, revision, row))


def rows(connection: sqlite3.Connection, slug: str) -> list[dict[str, Any]]:
    """The newest revision of each of `slug`'s rows, by pull request number.

    A range scan on the key, not `LIKE`: an `_` in a slug would match any
    character, and `owner/a_b` would read the rows of `owner/axb`.
    """
    from sd_db import ship  # noqa: PLC0415

    prefix = f"{PREFIX}{slug.lower()}:"
    keys = connection.execute("SELECT DISTINCT key FROM state WHERE kind = 'checkpoint' AND key >= ? AND key < ?",
                              (prefix, prefix + TOP)).fetchall()
    found = [ship.read(connection, key)[1] for (key,) in keys]
    return sorted(found, key=lambda row: row["pull_request"])
