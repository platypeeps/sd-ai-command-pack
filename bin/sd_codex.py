"""`sd skill scan` — the nightly parse of `~/.codex/sessions`.

Criterion 26 names four producers of `skill_use` rows, one per surface that
can see a skill being used. `bin/sd-skill-use` is the Claude one and writes
its row as the use happens. Codex has no hook surface, so its rows are read
back afterwards out of the rollout transcripts Codex keeps under
`~/.codex/sessions/<year>/<month>/<day>/rollout-<stamp>-<id>.jsonl`.

**What the criterion asked for is not what Codex records.** The clause reads
"a nightly parse of `~/.codex/sessions` for the same", where "the same" is a
typed `/sd-*` command. Codex has no slash-command surface for this pack:
`bin/sd_install.py:183-185` renders the Codex home as `~/.codex/skills/<name>/
SKILL.md`, a directory form, and there is no `~/.codex/prompts`. Across the
826 rollouts on the machine this was written against, no user turn begins
with `/` at all, while `~/.codex/skills/<name>/SKILL.md` is read by name over
a thousand times. So the realisable Codex signal is `path` and not `direct`.

Both are read here anyway. `direct` costs one branch, `bin/sd-skill-use`
already writes both modes on Claude, and a Codex that grows a prompt surface
later then needs no change. What it does not do is invent a mode: the SQL
constrains the column to the two values (`sd_db/schema/001_initial.sql:131`)
and this module writes those two.

**A use is a session, not a mention.** A skill read once is echoed by the
tool call, its output, and every later turn that quotes either, which is why
one skill reaches four figures of textual hits across a few dozen sessions.
The row this table wants is "this session used this skill this way", so a
`(session, skill, mode)` triple writes one row, stamped with the first
occurrence, and every later mention in that session is dropped.

**The stamp is when the session ran, never when the parse ran.**
`sd_db.record_skill_use` carries a `timestamp` parameter for exactly this
reader, and its docstring says why: stamping a week of sleep with the morning
that ended it files the whole week under one day.

**A watermark, and the collect that is allowed to move it.** `collect`
returns `ok` and a `reason`, and only an `ok` run advances the cursor. A run
that failed halfway leaves it where it was so the next run re-reads the
window rather than stepping over it -- the trade `sd_db.shadow_sync`'s
watermark makes, in the same `state` rows and with the same `resolved_at`
meaning "this cursor was written completely".

`sd_db` is imported inside the call rather than at module import, the way
`bin/sd_skill.py` and `bin/sd_restore.py` do it: the library reaches this
virtualenv through the pack's own installer, and `sd` keeps working for every
other verb on a machine where that has not run yet.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re

#: Why the verb cannot run, when it cannot.
NOT_INSTALLED = (
    "sd_db is not installed in this virtualenv. `sd skill scan` writes "
    "skill_use rows; install the library with the pack's installer "
    "(`sd-install`), which provisions it from the `system` checkout, then "
    "run this again."
)

#: The platform key, from the three `bin/sd_install.py:183-185` names.
SURFACE = "codex"

#: The `state` row this cursor lives in. `kind` is the schema's, `key` is ours.
WATERMARK = "watermark"
CURSOR_KEY = "codex-sessions"

SKILL_FILE = "SKILL.md"
SKILLS_DIR = "skills"

#: A day of slack on the file scan. A session that opened before midnight
#: writes records after it, so the day directory holding a record newer than
#: the cursor is not always the day directory the cursor names.
OVERLAP_DAYS = 1

#: `~/.codex/skills/<name>/SKILL.md`, anywhere in a record's text. The path
#: is matched rather than a field read: Codex reaches a skill by shelling out,
#: so the only place the name appears is inside a tool call's argument string.
PATH_USE = re.compile(r"/\.codex/" + SKILLS_DIR + r"/([A-Za-z0-9][\w.-]*)/" + SKILL_FILE)


class CodexRefusal(Exception):
    """Something the operator must settle before the scan can run."""


def sessions_root(environ: dict[str, str] | None = None) -> pathlib.Path:
    """`~/.codex/sessions`, honouring `CODEX_HOME` when Codex is relocated.

    Codex reads that variable itself, so a machine that sets it has moved the
    transcripts and a scan of the default path would report an empty surface
    rather than say it looked in the wrong place.
    """
    env = os.environ if environ is None else environ
    base = env.get("CODEX_HOME") or ""
    home = pathlib.Path(base) if base else pathlib.Path.home() / ".codex"
    return home / "sessions"


def _library():
    """Import `sd_db`, or refuse with the remedy rather than a traceback."""
    try:
        # May or may not be resolvable at type-check time: `sd_db` is built
        # into this virtualenv by the pack's installer, from the `system`
        # checkout, and this repository does not vendor it. `pyproject.toml`
        # carries the override rather than an inline ignore here.
        import sd_db  # noqa: PLC0415 - see the module docstring
    except ImportError as problem:
        raise CodexRefusal(f"{NOT_INSTALLED} ({problem})") from problem
    return sd_db


def _open(sd_db):
    """The database, or a refusal naming where it was looked for."""
    path = sd_db.default_path()
    if not path.exists():
        raise CodexRefusal(f"no database at {path}; run `sd-db.sh init` first")
    return sd_db.connect(path)


def read_cursor(sd_db, connection) -> str | None:
    """The newest record stamp a completed scan has recorded, or None.

    `sd_db.read_watermark` is the built reader and takes the tracker key, so
    the cursor shape is the one `shadow_sync` already writes and reads: only a
    row with `resolved_at` counts, because a row without it is a write that
    did not finish and resuming from half a cursor is how a window gets
    skipped.
    """
    try:
        return sd_db.read_watermark(connection, CURSOR_KEY)
    except Exception:  # noqa: BLE001 - an unreadable cursor is a full rescan
        return None


def write_cursor(sd_db, connection, through: str, scanned: int) -> None:
    """Move the cursor, and mark it complete in the same breath.

    Written with `record_state` and `resolve_state` rather than through
    `shadow_sync.write_watermark`, which is not exported and whose body is
    a tracker's collect window rather than a transcript position.
    """
    row = sd_db.record_state(
        connection,
        WATERMARK,
        key=CURSOR_KEY,
        body={"collected_at": through, "files": scanned},
    )
    sd_db.resolve_state(connection, row)


def rollouts(root: pathlib.Path, since: str | None) -> list[pathlib.Path]:
    """Every rollout file that could hold a record newer than `since`.

    The day directories are the filter and the file's own contents are the
    decision. Enumerating the tree is cheap; parsing eight hundred JSONL
    transcripts on every nightly is not, and the `<year>/<month>/<day>` layout
    is exactly the index needed to avoid it.

    A malformed directory name is kept rather than skipped. Guessing that a
    directory Codex wrote is not a date is how a scan silently stops seeing a
    surface, and a file that holds nothing new costs one parse.
    """
    if not root.is_dir():
        return []
    floor = ""
    if since:
        try:
            day = datetime.date.fromisoformat(since[:10])
        except ValueError:
            day = None
        if day is not None:
            floor = (day - datetime.timedelta(days=OVERLAP_DAYS)).isoformat()
    found = []
    for source in sorted(root.rglob("*.jsonl")):
        parts = source.parent.parts[-3:]
        stamp = "-".join(parts) if len(parts) == 3 else ""
        if floor and len(stamp) == 10 and stamp[4] == "-" and stamp < floor:
            continue
        found.append(source)
    return found


def uses_in(
    source: pathlib.Path, since: str | None
) -> tuple[str, dict[tuple[str, str], str]]:
    """One transcript's working directory, and its `(skill, mode)` first stamps.

    Unparseable lines are skipped rather than fatal, the trade
    `bin/sd_ledger.py:143-188` makes: a torn record costs one measurement, and
    a crash here costs the nightly. `errors="replace"` for the same reason it
    is there -- a damaged byte raises `UnicodeDecodeError`, which is a
    `ValueError` and would escape an `OSError` guard.

    Read line by line and not with `read_text`: a rollout is the whole history
    of a session and some are tens of megabytes.
    """
    seen: dict[tuple[str, str], str] = {}
    cwd = ""
    try:
        handle = source.open(encoding="utf-8", errors="replace")
    except OSError:
        return "", {}
    with handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            payload = record.get("payload")
            if isinstance(payload, dict) and not cwd:
                found = payload.get("cwd")
                if isinstance(found, str) and found:
                    cwd = found
            stamp = record.get("timestamp")
            if not isinstance(stamp, str) or (since and stamp <= since):
                continue
            for key in uses_of(record, line):
                seen.setdefault(key, stamp)
    return cwd, seen


def uses_of(record: dict, line: str) -> set[tuple[str, str]]:
    """Which skills one record shows used, and how. A derivation, not a copy.

    Two shapes, and the second is the one that fires in practice:

    * `direct` -- a user turn whose text opens with `/<name>`. Codex records
      a turn either as an `event_msg` with a `user_message` payload carrying
      `message`, or as a `response_item` `message` with `role: user` and a
      content list of `{"text": ...}` parts. Both are read; neither is the
      shape a Codex slash command would take, because Codex has no slash
      command for this pack today.
    * `path` -- `~/.codex/skills/<name>/SKILL.md` named anywhere in the
      record. Codex opens a skill by shelling out to read it, so the name is
      inside a tool call's argument string and there is no field to read.
      Matched against the raw line, which is what makes this cheap: the regex
      runs once per line instead of once per nested string.

    A `path` hit is taken from the line before the record is walked, so a
    transcript whose JSON is well-formed but whose shape Codex changes later
    keeps producing the mode that matters.
    """
    found = {(name, "path") for name in PATH_USE.findall(line)}
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return found
    text = None
    if payload.get("type") == "user_message":
        text = payload.get("message")
    elif payload.get("type") == "message" and payload.get("role") == "user":
        parts = [
            part["text"]
            for part in payload.get("content") or []
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        text = "\n".join(parts) if parts else None
    if not isinstance(text, str):
        return found
    first = text.strip().split(maxsplit=1)[:1]
    if first and first[0].startswith("/") and len(first[0]) > 1:
        found.add((first[0][1:], "direct"))
    return found


def collect(sd_db, connection, root: pathlib.Path, since: str | None) -> dict:
    """Read every rollout past the cursor and write one row per session use.

    Returns a report rather than raising, with `ok` saying whether the cursor
    may move. `dashboard/github.py:270-318` `collect` is the built shape and
    the reason is the same: a partial read that advanced the cursor would lose
    the window it failed on, permanently and silently.

    `cwd` is the session's own working directory as Codex recorded it, not a
    worktree root resolved with `git`. The sessions being read are historic
    and the directory may be gone; `bin/sd-skill-use` resolves because it runs
    inside the checkout it is describing.
    """
    report: dict = {
        "ok": True, "reason": "", "files": 0, "rows": 0,
        "skills": {}, "through": since or "",
    }
    for source in rollouts(root, since):
        report["files"] += 1
        try:
            cwd, seen = uses_in(source, since)
        except OSError as problem:
            report["ok"] = False
            report["reason"] = f"{source.name}: {problem}"
            return report
        for (skill, mode), stamp in sorted(seen.items()):
            try:
                sd_db.record_skill_use(
                    connection, skill, surface=SURFACE, mode=mode,
                    cwd=cwd or None, timestamp=stamp,
                )
            except Exception as problem:  # noqa: BLE001 - the cursor stays put
                report["ok"] = False
                report["reason"] = f"{skill}: {problem}"
                return report
            report["rows"] += 1
            report["skills"][skill] = report["skills"].get(skill, 0) + 1
            if stamp > report["through"]:
                report["through"] = stamp
    return report


def render(report: dict) -> list[str]:
    """The report as lines, busiest skill first and by name within a count."""
    lines = [
        f"{report['files']} transcript(s), {report['rows']} row(s) written"
    ]
    ranked = sorted(report["skills"].items(), key=lambda pair: (-pair[1], pair[0]))
    lines.extend(f"  {count:>4}  {skill}" for skill, count in ranked)
    if not report["ok"]:
        lines.append(f"stopped: {report['reason']}")
        lines.append("the cursor did not move; the next run re-reads this window")
    elif report["through"]:
        lines.append(f"read through {report['through']}")
    return lines


def skill_scan(args: argparse.Namespace) -> int:
    """Write the Codex surface's `skill_use` rows, and say what was written."""
    root = sessions_root()
    sd_db = _library()
    connection = _open(sd_db)
    try:
        since = None if args.all else read_cursor(sd_db, connection)
        report = collect(sd_db, connection, root, since)
        if report["ok"] and report["through"] and not args.dry_run:
            write_cursor(sd_db, connection, report["through"], report["files"])
    finally:
        connection.close()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    for line in render(report):
        print(line)
    # Zero either way. A nightly that found nothing is not a failure, and a
    # non-zero exit would make the scheduled run look broken on every quiet
    # day. A run that stopped says so on stdout and leaves the cursor put.
    return 0
