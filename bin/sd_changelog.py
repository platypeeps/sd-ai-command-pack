"""Changelog entries as workflow-database rows (sd:2783, steps 1 and 2).

A pull request in an opted-in repository states its entry in a `## Changelog`
section of its body, and `sd-ship merge` stores that entry as one checkpoint
row in the `state` table, so feature branches stop sharing `CHANGELOG.md`.
The design is in `docs/work/2026-10-05-changelog-in-database/design.md`.

Step 1 is the section parser, the privacy check, the row key, the idempotent
writer and the reader. Step 2 is `sd changelog`: `render` writes the marked
region of `CHANGELOG.md` from the rows and git alone, `show` prints it, and
`import` writes a row from a squash message that has none. Render refuses a
merged entry with no row (ruling Q6) and any row a privacy pattern matches,
and with no pattern file it refuses (Q7). `sd-ship` calls none of it yet.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import itertools
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

import sd_lib

#: The `state` key prefix; the key is `<PREFIX><owner/name>:<pull request>`.
PREFIX = "sd-changelog:v1:"
#: The six Keep a Changelog subsections, in the order render writes them.
SECTIONS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")
#: The explicit no-entry answer (ruling Q1).
NONE = "none"
#: Above every UTF-8 character, so `key < prefix + TOP` closes a range scan.
TOP = "\U0010ffff"
TIMEOUT_SECONDS = 60
#: The file render writes, at the repository root, and its marked region.
FILE = "CHANGELOG.md"
BEGIN = "<!-- sd-changelog:begin -->"
END = "<!-- sd-changelog:end -->"

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,2})(?!#)(?:[ \t]+(.*?))?[ \t#]*$")
#: The first code-span backtick run or comment opener in a line.
_INLINE = re.compile(r"`+|<!--")
#: A trailer line as git reads one: a token, a colon, a value.
_TRAILER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*:[ \t]+\S")
_BULLET = re.compile(r"^[-*+][ \t]+(\S.*)$")
#: The number GitHub's squash subject ends in, `Title (#123)`.
_SUBJECT = re.compile(r"\(#([0-9]+)\)\s*$")
_ITEM = re.compile(r"^Item:[ \t]*(sd:[0-9]+)[ \t]*$", re.MULTILINE)
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?")


class ChangelogError(ValueError):
    """A refusal; `code` is the machine-readable reason a caller reports."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _heading(line: str) -> str | None:
    """The text of a level-1 or level-2 ATX heading, or None."""
    match = _HEADING.match(line)
    return None if match is None else (match.group(2) or "")


def _fence(fence: str, line: str) -> str:
    """The fence open after `line`, given the one open before it ("" for none).

    Only a run of the opening fence's character, at least as long and with no
    info string, closes a fence.
    """
    match = _FENCE.match(line)
    if match is None:
        return fence
    run, info = match.group(1), match.group(2)
    if not fence:
        return run
    return "" if run[0] == fence[0] and len(run) >= len(fence) and not info.strip() else fence


def _uncomment(body: str) -> str:
    """`body` without its HTML comments; one inside a code fence or a code span is text.

    A comment that spans lines joins the text before it to the text after it,
    and a fence marker inside a comment opens nothing. A run of backticks with
    no closing run of the same length is literal, as CommonMark reads it.
    """
    out: list[str] = []
    fence, comment = "", False
    for line in body.splitlines():
        if not comment and (fence or _FENCE.match(line)):
            fence = _fence(fence, line)
            out.append(line)
            continue
        joined, kept, rest = comment, [], line
        while rest:
            if comment:
                end = rest.find("-->")
                rest, comment = ("", True) if end < 0 else (rest[end + 3:], False)
                continue
            match = _INLINE.search(rest)
            if match is None:
                kept.append(rest)
                break
            kept.append(rest[:match.start()])
            if match.group() == "<!--":
                rest, comment = rest[match.end():], True
                continue
            close = re.compile(f"(?<!`){match.group()}(?!`)").search(rest, match.end())
            end = match.end() if close is None else close.end()
            kept.append(rest[match.start():end])
            rest = rest[end:]
        if joined:
            out[-1] += "".join(kept)
        else:
            out.append("".join(kept))
    return "\n".join(out)


def _untrailed(lines: list[str]) -> list[str]:
    """`lines` without the trailer paragraphs that end them.

    A squash message ends in `sd-ship`'s `Work:` line and its trailer block,
    after the body's last section; they are no part of a `## Changelog`
    section that comes last.
    """
    while True:
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        start = len(lines)
        while start and lines[start - 1].strip():
            start -= 1
        paragraph = lines[start:]
        if not paragraph or not _TRAILER.match(paragraph[0]) or not all(
                _TRAILER.match(line) or line[:1] in (" ", "\t") for line in paragraph):
            return lines
        lines = lines[:start]


def _section(body: str) -> list[str]:
    """The lines of the one `## Changelog` section, outside code fences.

    A heading inside a fence or an HTML comment is an example, not the
    section. The section runs to the next level-1 or level-2 heading, and
    trailer paragraphs that end the body are not part of it.
    """
    sections: list[list[str]] = []
    fence, inside = "", False
    for line in _untrailed(_uncomment(body).split("\n")):
        before, fence = fence, _fence(fence, line)
        heading = None if before or fence or _FENCE.match(line) else _heading(line)
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


def _continue(entry: dict[str, Any], line: str) -> None:
    """Add `line` to `entry`'s text, less up to two spaces of indent."""
    indent = len(line) - len(line.lstrip(" "))
    entry["text"] += "\n" + line[min(indent, 2):]


def _entries(lines: list[str]) -> list[dict[str, Any]]:
    """`{section, text}` per bullet; continuation lines lose two spaces of indent.

    A blank line inside a bullet stays when an indented line follows it.

    A fence opens only as a continuation of a bullet, and every line up to its
    close, blank or `### `-shaped, is that bullet's text.
    """
    entries: list[dict[str, Any]] = []
    section, counted, after_text, fence = None, 0, False, ""
    for number, line in enumerate(lines, 1):
        stripped = line.rstrip()
        bullet = _BULLET.match(stripped)
        before, fence = fence, _fence(fence, line)
        if before:
            _continue(entries[-1], stripped)
        elif not stripped:
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
            if not after_text:  # an indented paragraph after a blank line keeps its break
                entries[-1]["text"] += "\n"
            _continue(entries[-1], stripped)
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
    text = "\n".join(_section(body))
    return [] if text.strip() == NONE else _entries(text.split("\n"))


def section_digest(body: str) -> str:
    """sha256 of `body`'s `## Changelog` section; a body and its squash message give the same digest."""
    return hashlib.sha256("\n".join(_section(body)).strip().encode("utf-8")).hexdigest()


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


def _store() -> Any:
    """`sd_db.ship`, reached through `sd_lib.import_sd_db` as every `bin/` module reaches `sd_db`."""
    imported = sd_lib.import_sd_db()
    if imported.module is None:
        raise RuntimeError(str(imported.problem))
    from sd_db import ship  # noqa: PLC0415

    return ship


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
    ship = _store()
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
    ship = _store()
    prefix = f"{PREFIX}{slug.lower()}:"
    keys = connection.execute("SELECT DISTINCT key FROM state WHERE kind = 'checkpoint' AND key >= ? AND key < ?",
                              (prefix, prefix + TOP)).fetchall()
    found = [ship.read(connection, key)[1] for (key,) in keys]
    return sorted(found, key=lambda row: row["pull_request"])


# --- `sd changelog render|show|import` (step 2) ------------------------------


@dataclasses.dataclass(frozen=True)
class History:
    """The base's first-parent history, as render selects and cross-checks against it."""

    base: str
    #: The first-parent commits after the newest `v*` tag, newest first.
    after: tuple[str, ...]
    #: Every first-parent commit of the base, the tag's included.
    on_base: frozenset[str]
    #: `after`'s commit messages, by sha.
    messages: dict[str, str]
    #: The base commit's committer date, `YYYY-MM-DD` in UTC.
    date: str


def _git(root: pathlib.Path, args: list[str], what: str) -> str:
    answer = sd_lib.git_output(args, root)
    if answer is None:
        raise ChangelogError("changelog_git", f"git could not {what}")
    return answer


def _messages(root: pathlib.Path, span: str) -> dict[str, str]:
    """`{sha: message}` for the first-parent commits of `span`, newest first."""
    raw = _git(root, ["log", "--first-parent", "--format=%H%x1f%B%x1e", span], f"read the messages of {span}")
    found: dict[str, str] = {}
    for record in raw.split("\x1e"):
        sha, separator, message = record.strip().partition("\x1f")
        if separator:
            found[sha] = message
    return found


def _head(root: pathlib.Path, base: str) -> str:
    """The commit `base` names; a value git would read as an option names none."""
    head = None if base.startswith("-") else sd_lib.git_output(["rev-parse", "--verify", "--quiet",
                                                                f"{base}^{{commit}}"], root)
    if not head:
        raise ChangelogError("changelog_base", f"{base} names no commit")
    return head


def _history(root: pathlib.Path, base: str) -> History:
    """`base`'s first-parent history since its newest `v*` tag, read from git alone."""
    head = _head(root, base)
    tag = sd_lib.git_output(["describe", "--tags", "--match", "v*", "--abbrev=0", "--first-parent", head], root)
    messages = _messages(root, f"{tag}..{head}" if tag else head)
    on_base = _git(root, ["rev-list", "--first-parent", head], f"list the history of {base}").split()
    stamp = int(_git(root, ["log", "-1", "--format=%ct", head], f"date {base}"))
    date = datetime.datetime.fromtimestamp(stamp, datetime.UTC).strftime("%Y-%m-%d")
    return History(base, tuple(messages), frozenset(on_base), messages, date)


def _pull_request(message: str) -> int | None:
    """The number GitHub's squash subject ends in, `Title (#123)`, or None."""
    match = _SUBJECT.search(message.split("\n", 1)[0])
    return int(match[1]) if match else None


def _missing(found: History, chosen: list[tuple[int, dict[str, Any]]]) -> list[str]:
    """The commits after the tag whose message has an entry and that no selected row describes."""
    described = {row["merge_commit"] for _, row in chosen}
    missing = []
    for sha in found.after:
        if sha in described:
            continue
        try:
            if not parse_section(found.messages[sha]):
                continue
        except ChangelogError as error:
            if error.code == "changelog_missing":
                continue
        number = _pull_request(found.messages[sha])
        missing.append(f"#{number}" if number else sha[:12])
    return missing


def _select(stored: list[dict[str, Any]], found: History) -> tuple[list[tuple[int, dict[str, Any]]], list[str]]:
    """`(position, row)` for each row merged after the tag, and the rows not on the base, named.

    Position is the merge's first-parent index, 0 the newest, so neither the
    write order nor a clock decides the render order. A row merged before
    the tag is released and selects nothing; one not on the base at all is
    named, never rendered.
    """
    position = {sha: index for index, sha in enumerate(found.after)}
    chosen, skipped = [], []
    for row in stored:
        commit = row.get("merge_commit")
        if commit in position:
            chosen.append((position[commit], row))
        elif commit not in found.on_base:
            skipped.append(f"#{row.get('pull_request')} (merge commit {str(commit)[:12]} is not on {found.base})")
    return chosen, skipped


def _block(chosen: list[tuple[int, dict[str, Any]]]) -> list[str]:
    """The region's lines: by subsection in `SECTIONS` order, then the newest merge first.

    Each entry's text is verbatim, `(#<pr>)` closes its first line, and its
    continuation lines are indented two spaces.
    """
    ordered = sorted((SECTIONS.index(entry["section"]), position, index, row["pull_request"], entry["text"])
                     for position, row in chosen for index, entry in enumerate(row["entries"]))
    lines: list[str] = []
    for section, group in itertools.groupby(ordered, key=lambda entry: entry[0]):
        lines += ["", f"### {SECTIONS[section]}"]
        for *_, number, text in group:
            first, *rest = text.split("\n")
            lines += ["", f"- {first} (#{number})"] + [f"  {line}" if line else "" for line in rest]
    return lines + [""] if lines else []


def _place(text: str, lines: list[str], release: tuple[str, str] | None = None) -> str:
    """`text` with its marked region replaced by `lines`; nothing outside the region changes.

    With `release` as `(version, date)`, the lines go under `## <version> -
    <date>` after the region, and the region stays empty.
    """
    current = text.split("\n")
    if current.count(BEGIN) != 1 or current.count(END) != 1 or current.index(BEGIN) > current.index(END):
        raise ChangelogError("changelog_region", f"{FILE} needs one `{BEGIN}` line, then one `{END}` line")
    start, stop = current.index(BEGIN), current.index(END)
    if release is None:
        return "\n".join(current[:start + 1] + lines + current[stop:])
    version, date = release
    return "\n".join(current[:start + 1] + [END, "", f"## {version} - {date}"] + lines[:-1] + current[stop + 1:])


def privacy_patterns(environ: Mapping[str, str]) -> list[str]:
    """The lines of the privacy-pattern file, refused when it is absent or holds no usable pattern.

    `sd.privacy_patterns` names the file; unset reads `privacy-patterns` in
    the system tools' config folder, `$SYSTEM_TOOLS_CONFIG`, else
    `${XDG_CONFIG_HOME:-$HOME/.config}/system`, as `local-leak-guard` reads it.
    """
    configured = sd_lib.core_setting("privacy_patterns", dict(environ))
    if configured:
        path = pathlib.Path(configured).expanduser()
    else:
        config = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME") or "~", ".config")
        path = pathlib.Path(environ.get("SYSTEM_TOOLS_CONFIG") or os.path.join(config, "system")).expanduser()
        path /= "privacy-patterns"
    try:
        patterns = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ChangelogError("changelog_patterns_missing",
                             f"no readable privacy-pattern file at {path} ({error.__class__.__name__}); "
                             "copy it to this machine, or set sd.privacy_patterns") from None
    private("", patterns)  # refuses no usable pattern, and a pattern grep refuses
    return patterns


def _leaks(chosen: list[tuple[int, dict[str, Any]]], patterns: list[str]) -> list[str]:
    """Each selected row whose entry text matches a pattern, with line numbers and never the text."""
    leaks = []
    for _, row in chosen:
        lines = private("\n".join(entry["text"] for entry in row["entries"]), patterns) if row["entries"] else []
        if lines:
            leaks.append(f"#{row['pull_request']} entry line {', '.join(map(str, lines))}")
    return leaks


def _connect(database: pathlib.Path | None, *, write: bool) -> sqlite3.Connection:
    _store()
    import sd_db  # noqa: PLC0415

    try:
        return sd_db.connect(database, write=write)
    except Exception as error:  # the library's own refusals: no file, a newer schema, an unreachable hub
        raise ChangelogError("changelog_database", f"the workflow database could not be opened: {error}") from None


def _slug(root: pathlib.Path) -> str:
    match = sd_lib.GITHUB_ORIGIN.fullmatch(sd_lib.git_output(["config", "--get", "remote.origin.url"], root) or "")
    if not match:
        raise ChangelogError("changelog_origin", "origin must name one github.com repository")
    return f"{match[1]}/{match[2]}".lower()


def _rendered(args: argparse.Namespace, root: pathlib.Path, environ: Mapping[str, str]) -> tuple[list[str], History]:
    """The region's lines at `args.base`, after every refusal render owes (Q6, Q7)."""
    patterns = privacy_patterns(environ)
    found = _history(root, args.base)
    connection = _connect(args.database, write=False)
    try:
        stored = rows(connection, _slug(root))
    finally:
        connection.close()
    chosen, skipped = _select(stored, found)
    for name in skipped:
        print(f"sd changelog: skipped {name}", file=sys.stderr)
    missing = _missing(found, chosen)
    if missing:
        raise ChangelogError("changelog_rows_missing",
                             f"merged with a `## Changelog` entry and no row: {', '.join(missing)}; "
                             "run `sd changelog import <pr>` for each")
    leaks = _leaks(chosen, patterns)
    if leaks:
        raise ChangelogError("changelog_private", f"a privacy pattern matches {'; '.join(leaks)}")
    return _block(chosen), found


def _render(args: argparse.Namespace, root: pathlib.Path, environ: Mapping[str, str]) -> int:
    """`sd changelog render|show`: the region from the rows and git alone; exit 1 when `--check` differs."""
    lines, found = _rendered(args, root, environ)
    if args.verb == "show":
        if lines:
            print("\n".join(lines).strip("\n"))
        return 0
    path = root / FILE
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ChangelogError("changelog_region", f"{FILE} could not be read: {error}") from None
    rendered = _place(text, lines, (args.release, found.date) if args.release else None)
    if args.check:
        if rendered != text:
            print(f"sd changelog: {FILE} differs from `sd changelog render` at {args.base}", file=sys.stderr)
            return 1
        print(f"sd changelog: {FILE} matches `sd changelog render` at {args.base}")
        return 0
    if rendered != text:
        path.write_text(rendered, encoding="utf-8")
    print(f"sd changelog: {FILE} {'rendered' if rendered != text else 'unchanged'} at {args.base}")
    return 0


def _import_row(args: argparse.Namespace, root: pathlib.Path) -> int:
    """`sd changelog import <pr>`: the row for a squash on the base, written from its message (Q6)."""
    commits = _messages(root, _head(root, args.base))
    sha = next((sha for sha, message in commits.items() if _pull_request(message) == args.pull_request), None)
    if sha is None:
        raise ChangelogError("changelog_import", f"no first-parent commit of {args.base} ends its subject in "
                                                 f"(#{args.pull_request})")
    message = commits[sha]
    item = _ITEM.search(message)
    stamp = int(_git(root, ["log", "-1", "--format=%ct", sha], f"date {sha}"))
    row = {"repository": _slug(root), "pull_request": args.pull_request, "item": item[1] if item else None,
           "merge_commit": sha, "entries": parse_section(message), "body_digest": section_digest(message),
           "merged_at": datetime.datetime.fromtimestamp(stamp, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    connection = _connect(args.database, write=True)
    try:
        revision = write(connection, row)
    finally:
        connection.close()
    print(f"sd changelog: #{args.pull_request} from {sha[:12]} is revision {revision}, "
          f"{len(row['entries'])} entr{'y' if len(row['entries']) == 1 else 'ies'}")
    return 0


def run_changelog(args: argparse.Namespace) -> int:
    root = sd_lib.repo_root(None)
    try:
        if root is None:
            raise ChangelogError("changelog_git", "the working directory is not inside a Git repository")
        if args.verb == "import":
            return _import_row(args, root)
        return _render(args, root, os.environ)
    except (ChangelogError, RuntimeError, sd_lib.ConfigError) as error:
        print(f"sd changelog: {getattr(error, 'code', 'refused')}: {error}", file=sys.stderr)
        return 1


def register_changelog(groups: Any) -> None:
    changelog = groups.add_parser("changelog", help="render CHANGELOG.md's marked region from the database's entry "
                                                    "rows (sd:2783)")
    verbs = changelog.add_subparsers(dest="verb", required=True)
    renderer = verbs.add_parser("render", help=f"write the region of {FILE} from the rows merged since the newest "
                                               "v* tag; refuses a missing row or a privacy match")
    mode = renderer.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help=f"write nothing; exit 1 when {FILE} differs")
    mode.add_argument("--release", metavar="VERSION", type=_version,
                      help="put the entries under `## VERSION - <base date>` and leave the region empty")
    shower = verbs.add_parser("show", help="print the region render would write, and write nothing")
    importer = verbs.add_parser("import", help="write a merged pull request's row from its squash message")
    importer.add_argument("pull_request", type=_number, metavar="PR", help="the pull request number")
    for verb in (renderer, shower, importer):
        verb.add_argument("--base", default="HEAD", help="the commit whose first-parent history counts (default: HEAD)")
        verb.add_argument("--database", type=pathlib.Path, help="the workflow database (default: this machine's)")
        verb.set_defaults(handler=run_changelog)


def _version(value: str) -> str:
    if not _VERSION.fullmatch(value):
        raise argparse.ArgumentTypeError(f"{value!r} is no version such as 1.1.0")
    return value


def _number(value: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} is no pull request number")
    return int(value)
