"""Routine briefs: the Markdown briefs scheduled vault routines write, as `item` rows (sd:3459).

One brief is one row of kind `report`, `source` `brief`, `external_id` and
`title` its stem, `<YYYY-MM-DD> - <Series>`. It is filed `done` and stays
`done`: the quiet-report rule keeps it off work views, and the Reports
list and its verbs leave it alone (`reporting`). `body` is `{"text": <the
whole file>}`; `fields.brief` holds what a page shows without reading the
text: series, day, when it was first filed, words, a lead and the text's
sha256. `sd_db.brief` is the session brief, a different thing.

**The row is the source of truth.** No file replaces a row that exists and
differs. `add` takes one only with a flag: `extend` when the row's text is a
strict prefix of the file (a routine appending its findings), `replace`
whatever the row holds (the operator's flag). `import_folder` adds missing
stems, lists every other difference as a conflict, and takes a file only for
a stem the operator names. No counter or time decides it: a restore rolls
those back with the rows.

`sd_db.records` holds the mirror rule a vault copy is written and read by:
`hashed` adds the `mirror-hash` line, and `unhashed` and `hash_holds` read it.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from . import repos
from .database import transaction
from .records import _closing, hash_holds, unhashed
from .reporting import MAX_REPORT
from .workflow import MissingItem, WorkflowError, _text, item_state
from .writes import add_note, create_item, item_by_external, now, set_item_fields

SOURCE = "brief"

#: `<YYYY-MM-DD> - <Series>`: the stem a wikilink names a brief by.
STEM = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}) - (\S(?:.*\S)?)")

#: How much of the body, whitespace folded, a row keeps to show without its text.
LEAD = 200

#: What a conflict says about the vault copy, by `records.hash_holds`.
COPY = {True: "its mirror-hash matches: a copy the render wrote",
        False: "its mirror-hash does not match: a hand edit",
        None: "no mirror-hash: a hand edit or an unrendered note"}


class BriefRefused(WorkflowError):
    """A brief verb refused; nothing was written."""


class BriefUnusable(BriefRefused):
    """The file or stem is not a brief: refused before any write (`sd` exits 2)."""


class BriefConflict(BriefRefused):
    """The stem's row holds other text, and nothing allowed the file to replace it."""


def read_draft(path: Path) -> tuple[str, str]:
    """`(stem, text)` of a draft or note, or `BriefUnusable` naming the rule it breaks."""
    path = Path(path)
    if path.suffix != ".md":
        raise BriefUnusable(f"{path.name}: the file name must be `<YYYY-MM-DD> - <Series>.md`")
    with path.open("rb") as stream:
        data = stream.read(MAX_REPORT + 1)
    if len(data) > MAX_REPORT:
        raise BriefUnusable(f"{path.name}: over {MAX_REPORT} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BriefUnusable(f"{path.name}: not UTF-8 ({error.reason} at byte {error.start})") from None
    counts(path.stem, text)
    return path.stem, text


def counts(stem: str, text: str) -> dict[str, Any]:
    """The row's `fields.brief` but `at`, or `BriefUnusable`: a stem, a day that exists, frontmatter, a size."""
    found = STEM.fullmatch(stem) if isinstance(stem, str) else None
    try:
        day = datetime.date.fromisoformat(found[1]).isoformat() if found else None
    except ValueError:
        day = None
    if found is None or day is None:
        raise BriefUnusable(f"{stem}: the file name must be `<YYYY-MM-DD> - <Series>.md`, with a day that exists")
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_REPORT:
        raise BriefUnusable(f"{stem}: the text must be at most {MAX_REPORT} bytes")
    lines = text.split("\n")
    end = _closing(lines)
    if end is None:
        raise BriefUnusable(f"{stem}: the text must open with frontmatter between two `---` lines")
    body = " ".join("\n".join(lines[end + 1:]).split())
    return {"series": found[2], "day": day, "words": len(body.split()), "lead": body[:LEAD],
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def add(connection: sqlite3.Connection, stem: str, text: str, *, repo: str, who: str,
        mode: str | None = None, at: str | None = None) -> dict[str, Any]:
    """File one brief: `filed`, `unchanged`, `extended` or `replaced`, else `BriefConflict`.

    `repo` is the registered checkout that owns it, for a new row. `mode` is
    None, `extend` or `replace`. `at` is when it was first filed, now unless
    an import gives the note's time. A row's `at` never changes. Either
    replacing mode writes `body`, `fields` and one `comment` note in one
    transaction.
    """
    who = _text(who, "who")
    if mode not in (None, "extend", "replace"):
        raise BriefRefused(f"mode must be extend, replace or nothing, not {mode!r}")
    brief = counts(stem, text)
    with transaction(connection):
        row = item_by_external(connection, SOURCE, stem)
        if row is None:
            owner = repos.row_for(connection, repo)
            if owner is None:
                raise BriefRefused(f"{repo} is not a registered repository; register it with `sd-db repo add`")
            stamp = at or now()
            item = create_item(connection, kind="report", title=stem, status="done", repo=owner["path"],
                               source=SOURCE, external_id=stem, created_at=stamp, session=who,
                               fields={"attention": False, "brief": {**brief, "at": stamp}}, body={"text": text})
            result = "filed"
        else:
            item = row["id"]
            held = json.loads(row["body"] or "{}").get("text")
            fields = json.loads(row["fields"] or "{}")
            old = fields.get("brief") or {}
            if held == text:
                result = "unchanged"
            elif mode is None:
                raise BriefConflict(f"{stem}: the row holds other text; `sd reports brief show {stem}` prints it, "
                                    f"and only `--replace` takes the file over it")
            elif mode == "extend" and not (isinstance(held, str) and text.startswith(held)):
                raise BriefConflict(f"{stem}: the draft is not the row's text with more after it, so --extend "
                                    f"leaves the row; `sd reports brief show {stem}` prints it")
            else:
                result = "extended" if mode == "extend" else "replaced"
                fields["brief"] = {**brief, "at": old.get("at") or now()}
                set_item_fields(connection, item, fields=fields, body={"text": text})
                add_note(connection, item, "comment",
                         f"Brief replaced by {who}: {old.get('words', '?')} -> {brief['words']} words", session=who)
    return _answer(connection, item, result)


def _answer(connection: sqlite3.Connection, item: int, result: str) -> dict[str, Any]:
    """What `add` reports, read after its commit."""
    row = item_state(connection, item)["item"]
    return {"result": result, "item": item, "stem": row["title"], **json.loads(row["fields"])["brief"]}


def rows(connection: sqlite3.Connection, *, series: str | None = None, since: str | None = None,
         limit: int = 200) -> list[dict[str, Any]]:
    """Briefs newest first, by day then first filing, without their text: what a list or a page shows."""
    query = ("SELECT id, title, repo, created_at, updated_at, fields FROM item WHERE source = ? AND kind = 'report'")
    values: list[Any] = [SOURCE]
    if series is not None:
        query += " AND json_extract(fields, '$.brief.series') = ?"
        values.append(series)
    if since is not None:
        query += " AND json_extract(fields, '$.brief.day') >= ?"
        values.append(since)
    query += (" ORDER BY json_extract(fields, '$.brief.day') DESC, json_extract(fields, '$.brief.at') DESC, id DESC"
              " LIMIT ?")
    values.append(max(1, int(limit)))
    found = []
    for row in connection.execute(query, values):
        out = dict(row)
        out["brief"] = json.loads(out.pop("fields") or "{}").get("brief") or {}
        found.append(out)
    return found


def _held(connection: sqlite3.Connection, stem: str) -> str | None:
    """The sha256 the stem's row holds, read back; None when it has no row."""
    row = item_by_external(connection, SOURCE, stem)
    return None if row is None else json.loads(row["fields"] or "{}").get("brief", {}).get("sha256")


def show(connection: sqlite3.Connection, stem: str) -> str:
    """The stored Markdown of one brief."""
    row = item_by_external(connection, SOURCE, stem)
    if row is None:
        raise MissingItem(f"no brief has the stem {stem!r}")
    return str(json.loads(row["body"] or "{}").get("text", ""))


def import_folder(connection: sqlite3.Connection, folder: Path, *, repo: str, who: str,
                  replace: list[str] | tuple[str, ...] = ()) -> dict[str, Any]:
    """File each `*.md` in `folder`, each in its own transaction, and read them back.

    The `mirror-hash` line a render added is stripped first, so a copy that
    equals its row is `unchanged`. A missing stem is filed, with the note's
    modification time as `at`. A stem whose row differs is a conflict, kept
    as the row holds it and listed with what its copy is, unless it is named
    in `replace`. A file that is not a brief is refused by name and left.
    `verified` is the count read back with each row's sha256 the note's, or
    None when any conflict or mismatch is left. Renders nothing.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise BriefUnusable(f"{folder} is not a folder")
    notes = sorted(folder.glob("*.md"))
    stems = {path.stem for path in notes}
    unknown = sorted(set(replace) - stems)
    if unknown:
        raise BriefUnusable(f"--replace names {', '.join(unknown)}, which has no note in {folder}; "
                            f"name each stem as its note is called")
    result: dict[str, Any] = {"filed": [], "unchanged": 0, "replaced": [], "conflicts": [], "refused": [],
                              "verified": None}
    taken: dict[str, str] = {}
    for path in notes:
        try:
            stem, held = read_draft(path)
            text, _ = unhashed(held)
            counts(stem, text)
        except BriefUnusable as refusal:
            result["refused"].append({"name": path.name, "reason": str(refusal)})
            continue
        stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.UTC).isoformat(timespec="seconds")
        try:
            done = add(connection, stem, text, repo=repo, who=who, at=stamp,
                       mode="replace" if stem in replace else None)
        except BriefConflict:
            result["conflicts"].append({"stem": stem, "copy": COPY[hash_holds(held)]})
            continue
        if done["result"] == "filed":
            result["filed"].append(stem)
        elif done["result"] == "replaced":
            result["replaced"].append(stem)
        else:
            result["unchanged"] += 1
        taken[stem] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    matched = sum(1 for stem, digest in taken.items() if _held(connection, stem) == digest)
    if not result["conflicts"] and matched == len(taken):
        result["verified"] = matched
    return result
