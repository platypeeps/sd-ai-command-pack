"""Vault base rows, read and written once the database is their source (sd:3973).

Five Obsidian bases landed in `item` through the vault import, since removed
(sd:4627): kind `idea`, `source` `vault`, the plugin kind in `fields.kind`, the
ladder word in `stage`. These functions are how a row changes; the vault
holds no base notes (sd:5133), only one HTML page per base.

**The plugin owns the rules.** `rules_for(kind)` reads them from the pack's
plugin list, which validated them: the kind's fields, its stage graph, its
floors and unique fields, its human-only stages and protected fields, its
base folder, and the `workflow` map from each ladder word to an item status.
A second validator here would be a copy of the pack's rules in another file.
The pack's `db` driver enforces `human-only` and `protected-fields` for
agents; the dashboard is the operator and may make those moves, so these
functions leave both to their callers.

**A row moves by stage.** `edit_row` sets `stage` and the status the map
gives it, writes a `comment` note `Stage <from> -> <to> by <who>`, and calls
`_transition` when the status changes, as `writing.change_stage` does. The
public status writers refuse a vault row (`writes.refuse_base_status`).

**Bodies are stored verbatim.** Nothing reads, strips or rewrites a body
line: every write here stores the body as given.

**Each write is one transaction.** The row, its notes and its status change
commit together or not at all, so a stopped write leaves nothing to finish.

**Each base gets a read-only HTML page (sd:3976).** `render` writes one page
per base under `<vault>/docs/dashboard/`. It wrote each row's note back into
the vault too, until the notes were retired (sd:5133). It runs after each
committed write, for that kind, and on demand (`sd-db records render`); a
write never fails for its render.

**A learning row can move to a Documents view (pack sd:6262).** `plan_documents`
is the match list, `move_documents` writes `fields.document-type` (`books` or
`videos`) for the plan the operator saw, and `return_documents` takes it off.
The field is the row's, not the kind's, so `edit_row` keeps it and never sets
it. A moved row leaves Tasks and Today (`reads.NOT_A_DOCUMENT`).

**Only the `db` driver writes.** A plugin list that still reports the removed
`vault` driver (an older installed pack) makes both writers refuse.
"""

from __future__ import annotations

import contextlib
import datetime
import functools
import hashlib
import html
import importlib.util
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .database import refuse_hub_only, transaction
from .publication_render import _fence_closer, md_to_html
from .reads import DOCUMENT_TYPE, document_view
from .sources import MigrationRefused
from .sources.vault import DUE, NOT_FIELDS, SOURCE, plugin_entries, store_root
from .workflow import MissingItem, WorkflowError, _checked_state, _text, item_state
from .writes import (
    _transition,
    add_note,
    create_item,
    now,
    record_state,
    set_item_fields,
)

#: Keys a caller may not set in `fields`: `status` is `stage`, `mirror-hash`
#: was the retired note mirror's, `kind` is the declared kind.
RESERVED_FIELDS = NOT_FIELDS | {"kind"}


class RecordRefused(WorkflowError):
    """A base row write the kind's rules do not allow, or one whose rules are unknown."""


@dataclass(frozen=True)
class Rules:
    """One kind's rules, as the pack's plugin list reports them."""

    kind: str
    prefix: str
    driver: str
    #: The plugin's `store.root`, such as `$OBSIDIAN_VAULT`; `base` is under it.
    root: str
    #: The kind's folder under the vault root; a new row's path starts with it.
    base: str
    #: The `workflow` map: ladder word -> item status.
    stages: dict[str, str]
    fields: tuple[str, ...]
    initial: str
    #: The stage graph, or None: a kind with no `transitions` moves freely.
    transitions: dict[str, list[str]] | None
    human_only: dict[str, str]
    protected: tuple[str, ...]
    unique: tuple[str, ...]
    floor: dict[str, float]
    #: The field the `workflow` block names as the due date, or None.
    due: str | None = None
    #: The folder `root` names under the environment the rules were read with,
    #: or None when it names none. The pages are written only here.
    vault: Path | None = None


# ---------------------------------------------------------------- rules


def rules_for(kind: str, *, home: Path | str, environ: dict[str, str] | None = None,
              entries: list[dict[str, Any]] | None = None) -> Rules:
    """The rules of `kind`, from the installed pack's plugin list, or a refusal.

    `entries` is that list already read, else the pack is asked. Every
    answer short of one readable plugin declaring the kind with its rules
    refuses: an unreadable manifest or a pack that reports no rules is an
    unknown, not a kind without rules.
    """
    if entries is None:
        try:
            entries = plugin_entries(home=home, environ=environ)
        except MigrationRefused as error:
            raise RecordRefused(str(error)) from None
    found = [entry for entry in entries if kind in (entry.get("workflow") or {})]
    _refuse_unreadable(entries, f"the rules of kind {kind!r}")
    if len(found) != 1:
        raise RecordRefused(f"{len(found)} registered plugins declare a `workflow` for kind {kind!r}; "
                            f"a base row needs exactly one")
    entry = found[0]
    declared = (entry.get("rules") or {}).get(kind)
    if not isinstance(declared, dict):
        raise RecordRefused(f"the installed pack reports no `rules` for kind {kind!r}; "
                            f"it predates the `db` store driver, so install a newer pack")
    store = entry.get("store") or {}
    try:
        return Rules(
            kind=kind, prefix=str(entry["prefix"]), driver=str(store["driver"]), root=str(store["root"]),
            base=str(store["bases"][kind]), stages=dict(entry["workflow"][kind]["status"]),
            fields=tuple(declared["fields"]), initial=str(declared["initial-status"]),
            transitions=declared.get("transitions"), human_only=dict(declared.get("human-only") or {}),
            protected=tuple(declared.get("protected-fields") or ()),
            unique=tuple(declared.get("unique-fields") or ()), floor=dict(declared.get("floor") or {}),
            due=entry["workflow"][kind].get("due-field"), vault=_vault(store, str(entry["prefix"]), environ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RecordRefused(f"the pack's rules for kind {kind!r} are missing {error}") from None


def _vault(store: dict[str, Any], prefix: str, environ: dict[str, str] | None) -> Path | None:
    try:
        return store_root(store, prefix, environ)
    except MigrationRefused:
        return None


def _refuse_unreadable(entries: list[dict[str, Any]], what: str) -> None:
    """Any plugin the pack could not read may declare a kind, so `what` is unknown."""
    for entry in entries:
        problem = entry.get("manifestError") or entry.get("dashboardError") or (
            None if entry.get("readable") else entry.get("why") or "unreadable")
        if problem:
            raise RecordRefused(f"the plugin at {entry.get('root')} cannot be read, so {what} "
                                f"cannot be known: {problem}")


# ---------------------------------------------------------------- reads


def list_rows(connection: sqlite3.Connection, kind: str | None = None, *,
              stage: str | None = None) -> list[dict[str, Any]]:
    """The base rows, of one kind and one stage when given, oldest first."""
    query, values = "SELECT * FROM item WHERE source = ?", [SOURCE]
    if kind is not None:
        query += " AND json_extract(fields, '$.kind') = ?"
        values.append(kind)
    if stage is not None:
        query += " AND stage = ?"
        values.append(stage)
    return [_read(dict(row)) for row in connection.execute(query + " ORDER BY id", values)]


def get_row(connection: sqlite3.Connection, item: int | None = None, *, kind: str | None = None,
            title: str | None = None) -> dict[str, Any]:
    """One base row with its `revision`: by id, or by kind and file title.

    The file title is the stem of the row's path, the name a wikilink and the
    store verbs use, compared as macOS compares file names (`_file_key`); two
    rows of one kind with that stem refuse as ambiguous.
    """
    if item is None:
        if kind is None or title is None:
            raise RecordRefused("name a base row by its id, or by its kind and title")
        held = [row["id"] for row in list_rows(connection, kind)
                if _file_key(PurePosixPath(row["path"] or "").stem) == _file_key(title)]
        if not held:
            raise MissingItem(f"no {kind} row has the title {title!r}")
        if len(held) > 1:
            raise RecordRefused(f"{len(held)} {kind} rows have the title {title!r}: items {held}")
        item = held[0]
    state = item_state(connection, item)
    if state["item"]["source"] != SOURCE:
        raise RecordRefused(f"item {item} is not a base row from the vault")
    return {**_read(state["item"]), "revision": state["revision"]}


def _read(row: dict[str, Any]) -> dict[str, Any]:
    """A row with `fields` as a mapping and `body` as its Markdown."""
    return {**row, "fields": json.loads(row["fields"] or "{}"),
            "body": json.loads(row["body"] or "{}").get("markdown", "")}


# ---------------------------------------------------------------- writes


def add_row(connection: sqlite3.Connection, rules: Rules, *, title: str, who: str,
            fields: dict[str, Any] | None = None, body: str = "", stage: str | None = None) -> dict[str, Any]:
    """A new base row at `<base>/<title>.md`, at the kind's initial stage unless `stage` is given.

    `stage` other than the initial one must be a move the graph allows from
    it. Every floored field must be given. The body is stored as given.
    """
    who = _text(who, "who")
    _refuse_removed_driver(rules)
    values = _checked_fields(rules, fields or {})
    if "dateCreated" in rules.fields and not values.get("dateCreated"):
        # Every imported row carries it, and the page shows it.
        values["dateCreated"] = datetime.date.today().isoformat()
    for name in rules.floor:
        _refuse_below_floor(rules, name, values.get(name))
    stage = rules.initial if stage is None else stage
    _refuse_move(rules, rules.initial, stage)
    if not isinstance(body, str):
        raise RecordRefused("body must be Markdown text")
    title = _file_title(title)
    dates = _dates(rules, values)
    path = f"{rules.base}/{title}.md"
    identity = f"{rules.kind}:{path}"
    with transaction(connection):
        _refuse_taken(connection, path)
        _refuse_duplicate(connection, rules, values, skip=None)
        item = create_item(connection, kind="idea", title=title, status=rules.stages[stage],
                           source=SOURCE, external_id=identity, path=path, stage=stage,
                           fields={**values, "kind": rules.kind}, body={"markdown": body}, session=who,
                           due=dates.get("due"), created_at=dates.get("created_at"))
        row = get_row(connection, item)
        caught_up = _pending(connection, rules)
    _mirror_after(connection, rules, caught_up)
    return row


def edit_row(connection: sqlite3.Connection, item: int, rules: Rules, *, revision: str, who: str,
             stage: str | None = None, fields: dict[str, Any] | None = None,
             body: str | None = None) -> dict[str, Any]:
    """Move a base row's stage, set its fields, or replace its body, at `revision`.

    A stage move sets the mapped status through `_transition` and writes a
    `comment` note; a field or body change writes one too. A write that
    changes nothing writes nothing.
    """
    who = _text(who, "who")
    if not isinstance(revision, str):
        raise RecordRefused("an edit names the revision it was based on")
    _refuse_removed_driver(rules)
    changes = _checked_fields(rules, fields or {})
    for name, value in changes.items():
        if name in rules.floor:
            _refuse_below_floor(rules, name, value)
    if body is not None and not isinstance(body, str):
        raise RecordRefused("body must be Markdown text")
    with transaction(connection):
        row = _checked_state(connection, item, revision)["item"]
        held = json.loads(row["fields"] or "{}")
        if row["source"] != SOURCE or held.get("kind") != rules.kind:
            raise RecordRefused(f"item {item} is not a {rules.kind} row from the vault")
        current, target = row["stage"], row["stage"] if stage is None else stage
        if target != current:
            _refuse_move(rules, current, target)
        _refuse_duplicate(connection, rules, changes, skip=item)
        columns: dict[str, Any] = {"stage": target} if target != current else {}
        set_names = sorted(name for name in changes if name not in held or held[name] != changes[name])
        if set_names:
            columns.update(fields={**held, **changes}, **_dates(rules, {name: changes[name] for name in set_names}))
        if body is not None and body != json.loads(row["body"] or "{}").get("markdown"):
            columns["body"] = {"markdown": body}
            set_names.append("body")
        if not columns:
            return get_row(connection, item)
        set_item_fields(connection, item, **columns)
        if target != current:
            add_note(connection, item, "comment", f"Stage {current} -> {target} by {who}", session=who)
        if set_names:
            add_note(connection, item, "comment", f"Set {', '.join(set_names)} by {who}", session=who)
        if target != current and rules.stages[target] != row["status"]:
            _transition(connection, item, rules.stages[target], who=who, reason=f"stage {current} -> {target}")
        edited = get_row(connection, item)
        caught_up = _pending(connection, rules)
    _mirror_after(connection, rules, caught_up)
    return edited


def _refuse_removed_driver(rules: Rules) -> None:
    """A plugin list from an older installed pack can still report `vault`; the library writes only `db`."""
    if rules.driver != "db":
        raise RecordRefused(f"plugin {rules.prefix}'s `store.driver` is {rules.driver!r}, which was removed "
                            f"(sd:4627): set it to \"db\" and install a newer pack before writing "
                            f"{rules.kind} rows")


def _checked_fields(rules: Rules, fields: dict[str, Any]) -> dict[str, Any]:
    """`fields` when every key is declared and every value is frontmatter-shaped."""
    if not isinstance(fields, dict):
        raise RecordRefused("fields must be a mapping of field names to values")
    for name, value in fields.items():
        if name == "status":
            raise RecordRefused(f"a {rules.kind} row's status field is its stage; move the stage instead")
        if name in RESERVED_FIELDS or name not in rules.fields:
            raise RecordRefused(f"kind {rules.kind!r} declares no field {name!r} "
                                f"(it declares {', '.join(rules.fields)})")
        if not (value is None or _line(value) or (isinstance(value, list) and all(_line(v) for v in value))):
            raise RecordRefused(f"field {name!r} holds {value!r}; a field is one line of text, "
                                f"a list of them, or empty")
    return dict(fields)


def _dates(rules: Rules, values: dict[str, Any]) -> dict[str, Any]:
    """`due` and `created_at` from the fields given, as the import derives them from a note.

    The declared due field is `YYYY-MM-DD` or empty; `dateCreated`, when it
    holds text, is the row's `created_at` verbatim.
    """
    found: dict[str, Any] = {}
    if rules.due is not None and rules.due in values:
        value = values[rules.due]
        due = value.strip() if isinstance(value, str) else value
        try:
            if due and not (isinstance(due, str) and DUE.fullmatch(due) and datetime.date.fromisoformat(due)):
                raise ValueError(due)
        except ValueError:
            raise RecordRefused(f"plugin {rules.prefix} declares {rules.due!r} as the due date of "
                                f"{rules.kind}, and {value!r} is not YYYY-MM-DD") from None
        found["due"] = due or None
    created = values.get("dateCreated")
    if isinstance(created, str) and created.strip():
        found["created_at"] = created.strip()
    return found


def _line(value: Any) -> bool:
    return isinstance(value, str) and not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _refuse_below_floor(rules: Rules, name: str, value: Any) -> None:
    """`floor`, on the value the row will hold; an absent or non-number value refuses."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RecordRefused(f"`floor` bounds {name!r}, so its value must be a number, not {value!r}") from None
    if not math.isfinite(number) or number < rules.floor[name]:
        raise RecordRefused(f"`floor` puts {name!r} at {rules.floor[name]} or above; {value!r} is not")


def _refuse_move(rules: Rules, current: str, target: str) -> None:
    if target not in rules.stages:
        raise RecordRefused(f"plugin {rules.prefix}'s `workflow` map names no stage {target!r} for "
                            f"{rules.kind} (it names {', '.join(rules.stages)})")
    if rules.transitions is None or current == target:
        return
    allowed = rules.transitions.get(current, [])
    if target not in allowed:
        raise RecordRefused(f"`transitions` allows {current!r} -> {', '.join(sorted(allowed)) or 'nothing'}; "
                            f"{target!r} is not among them")


def _file_title(title: Any) -> str:
    """A title that names one file directly in the base folder."""
    title = _text(title, "title")
    if not _line(title) or "/" in title or "\\" in title or title.startswith("."):
        raise RecordRefused(f"title {title!r} must name one file: one line, no slash, no leading dot")
    return title


def _file_key(name: str) -> str:
    """A file name as macOS compares it: one Unicode normalization, and case ignored.

    `Café.md` composed and decomposed, or in another case, is one file there.
    """
    return unicodedata.normalize("NFC", name).casefold()


def _refuse_taken(connection: sqlite3.Connection, path: str) -> None:
    """A row's file name is one vault-wide wikilink target, compared by `_file_key`."""
    name = _file_key(PurePosixPath(path).name)
    for row in connection.execute("SELECT id, path FROM item WHERE source = ?", (SOURCE,)):
        if _file_key(PurePosixPath(row["path"] or "").name) == name:
            raise RecordRefused(f"item {row['id']} already has the file name {PurePosixPath(path).name!r} "
                                f"at {row['path']}; titles share one namespace across the vault")


def _refuse_duplicate(connection: sqlite3.Connection, rules: Rules, values: dict[str, Any],
                      *, skip: int | None) -> None:
    """`unique-fields` among the values given, against every other row of the kind as it is now."""
    wanted = {name: values[name] for name in rules.unique if values.get(name)}
    if not wanted:
        return
    for row in list_rows(connection, rules.kind):
        for name, value in wanted.items():
            if row["id"] != skip and row["fields"].get(name) == value:
                raise RecordRefused(f"`unique-fields` declares {name!r} unique and item {row['id']} "
                                    f"already holds {value!r}")


# ---------------------------------------------------------------- documents


#: The Documents views a learning row moves to (pack sd:6262), each with its label.
DOCUMENT_VIEWS = {"books": "Books", "videos": "Videos"}
#: A video note's title: its date, YouTube, the channel and the video's own title. The Videos view reads it too.
VIDEO_TITLE = re.compile(r"^(\d{4}-\d{2}-\d{2}) - YouTube - (.+?) - (.+)$")


@dataclass(frozen=True)
class DocumentMove:
    id: int
    view: str
    title: str


@dataclass(frozen=True)
class DocumentPlan:
    """The match list a dry run prints and a move applies.

    `moves` are the rows to move, videos first, each in id order. `moved` are
    the learning rows already in a view (id, view, title). `skipped` are rows
    titled as a video that are no learning row, which no Documents view reads
    (id, title). `candidates` are the learning books and articles the list does
    not name (id, content-type, title), for the operator to add with `--book`.
    """

    moves: tuple[DocumentMove, ...]
    moved: tuple[tuple[int, str, str], ...]
    skipped: tuple[tuple[int, str], ...]
    candidates: tuple[tuple[int, str, str], ...]

    @property
    def digest(self) -> str:
        """What the operator approved: the ids and their views, so `move_documents` moves that list or nothing."""
        names = json.dumps(sorted([move.id, move.view] for move in self.moves), separators=(",", ":"))
        return hashlib.sha256(names.encode()).hexdigest()[:16]


def plan_documents(connection: sqlite3.Connection, *, books: Iterable[int]) -> DocumentPlan:
    """The match list: learning rows titled as a YouTube video go to Videos, the rows `books` names go to Books.

    Books and articles carry no title to match, so only the operator's list moves one. A `books` id that is no
    learning row refuses the whole plan: the Books view reads learning rows only, so the row would show nowhere.
    """
    listed = list(dict.fromkeys(int(item) for item in books))
    rows = {row["id"]: row for row in list_rows(connection, "learning")}
    stray = [item for item in listed if item not in rows]
    if stray:
        raise RecordRefused(f"item {stray[0]} is not a learning row; the Books view reads learning rows only, "
                            f"so it would show nowhere")
    videos, named, moved, candidates = [], [], [], []
    for item, row in rows.items():
        held = document_view(row["fields"])
        if held:
            moved.append((item, held, row["title"]))
        elif item in listed:
            named.append(DocumentMove(item, "books", row["title"]))
        elif VIDEO_TITLE.match(row["title"] or ""):
            videos.append(DocumentMove(item, "videos", row["title"]))
        elif str(row["fields"].get("content-type") or "").lower() in ("book", "article"):
            candidates.append((item, str(row["fields"]["content-type"]).lower(), row["title"]))
    skipped = tuple((row["id"], row["title"]) for row in connection.execute("SELECT id, title FROM item ORDER BY id")
                    if row["id"] not in rows and VIDEO_TITLE.match(row["title"] or ""))
    return DocumentPlan(tuple(videos + named), tuple(moved), skipped, tuple(candidates))


def move_documents(connection: sqlite3.Connection, *, books: Iterable[int], plan: str,
                   who: str) -> DocumentPlan:
    """Move the rows `plan_documents` lists to their views, when its digest is still `plan`.

    One transaction: the plan is read again inside it, so a row filed or a list changed since the dry run refuses
    and moves nothing, and a write that fails partway rolls every row back. Each row gets `fields.document-type`
    and a `comment` note; its id, notes, stage and status stay.
    """
    with transaction(connection):
        found = plan_documents(connection, books=books)
        if found.digest != plan:
            raise RecordRefused(f"the match list changed since the dry run: plan {plan}, now {found.digest}; "
                                f"run the dry run again and check its list")
        for move in found.moves:
            held = json.loads(connection.execute("SELECT fields FROM item WHERE id = ?", (move.id,)).fetchone()[0])
            set_item_fields(connection, move.id, fields={**held, DOCUMENT_TYPE: move.view})
            add_note(connection, move.id, "comment",
                     f"Moved to Documents > {DOCUMENT_VIEWS[move.view]} by {who} (pack sd:6262): it leaves Tasks "
                     f"and Today; `sd-db records documents --undo {move.id}` moves it back", session=who)
    return found


def return_documents(connection: sqlite3.Connection, items: Iterable[int], *, who: str) -> list[int]:
    """Take `items` out of their Documents views, back to Tasks; refuse them all if one is in no view."""
    wanted = list(dict.fromkeys(int(item) for item in items))
    with transaction(connection):
        rows = {row["id"]: row for row in list_rows(connection, "learning")}
        for item in wanted:
            if item not in rows or not document_view(rows[item]["fields"]):
                raise RecordRefused(f"item {item} is in no Documents view; nothing moved back")
        for item in wanted:
            held = dict(rows[item]["fields"])
            view = held.pop(DOCUMENT_TYPE)
            set_item_fields(connection, item, fields=held)
            add_note(connection, item, "comment",
                     f"Moved back from Documents > {DOCUMENT_VIEWS.get(view, view)} by {who} (pack sd:6262)",
                     session=who)
    return wanted


# ---------------------------------------------------------------- the render

#: The `heartbeat` state row each render records: `{at, ok, kinds, written, reason}`.
MIRROR_KEY = "records-mirror"

#: Stages whose rows are table lines only on the HTML page (D3).
TABLE_ONLY = frozenset({"declined", "retired"})

#: A Meta Bind input, `INPUT[<widget>:<field>]`, with the backticks around it.
CONTROL = re.compile(r"`?INPUT\[[^\]\n]*:([\w-]+)\]`?")
#: `[[target]]`, `[[target|alias]]` and the `![[embed]]` form.
WIKILINK = re.compile(r"!?\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]")
#: An image `md_to_html` would mark missing, since it embeds local files only.
REMOTE_IMAGE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")


@dataclass
class Mirror:
    """What one render did: the kinds, the pages written, and why it stopped."""

    kinds: list[str]
    written: list[str] = field(default_factory=list)
    #: Empty since the notes were retired (sd:5133); the dashboard's render route still reads it.
    refused: list[tuple[str, str]] = field(default_factory=list)
    #: Why the render stopped or never started; `None` when it ran to the end.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None

    def why(self) -> str:
        return self.reason or ""


def render(connection: sqlite3.Connection, *, home: Path | str, environ: dict[str, str] | None = None,
           kinds: list[str] | None = None, entries: list[dict[str, Any]] | None = None) -> Mirror:
    """Write the pages of `kinds`, by default every kind a plugin on the `db` driver declares.

    Refuses with `HubOnly` off the hub, before it reads or records anything:
    a satellite's render would write a vault the hub's rows never see. Every
    other failure ends in the returned `Mirror` and its heartbeat.
    """
    refuse_hub_only(connection, "records render")
    env = dict(os.environ if environ is None else environ)
    try:
        if entries is None:
            entries = plugin_entries(home=home, environ=env)
        if kinds is None:
            _refuse_unreadable(entries, "the kinds on the `db` driver")
            kinds = sorted(kind for entry in entries if (entry.get("store") or {}).get("driver") == "db"
                           for kind in entry.get("workflow") or {})
        rules = [rules_for(kind, home=home, environ=env, entries=entries) for kind in kinds]
    except (MigrationRefused, RecordRefused) as error:
        return _beat(connection, Mirror(kinds=list(kinds or ()), reason=str(error)))
    return _mirrored(connection, rules)


def _pending(connection: sqlite3.Connection, rules: Rules) -> bool:
    """In the write's transaction: whether the pages were caught up, then a heartbeat saying they are not.

    A process stopped between the commit and the render leaves that failed
    heartbeat, so the next write renders every kind and Health shows the gap.
    """
    caught_up = _last_beat_ok(connection)
    _beat(connection, Mirror(kinds=[rules.kind], reason=f"a {rules.kind} write is committed and not yet rendered"))
    return caught_up


def _mirror_after(connection: sqlite3.Connection, rules: Rules, caught_up: bool) -> None:
    """The render after a committed write. It prints and records a failure and never raises.

    When the pages were not caught up before the write, it renders every kind,
    so the next write catches up whichever kind a failure left behind.
    """
    try:
        if connection.in_transaction:
            raise RecordRefused("the write is inside the caller's open transaction, so it is not committed yet")
        refuse_hub_only(connection, "the records render")
        if caught_up:
            mirror = _mirrored(connection, [rules])
        elif rules.vault is None:
            mirror = _mirrored(connection, [rules])  # refuses: the rules name no vault
        else:
            # Every kind, each under the vault the written kind's rules resolved.
            mirror = render(connection, home=Path.home(), environ={**os.environ, rules.root[1:]: str(rules.vault)})
    except Exception as error:  # a write never fails for its render
        mirror = Mirror(kinds=[rules.kind], reason=str(error) or type(error).__name__)
        with contextlib.suppress(Exception):
            _beat(connection, mirror)
    if not mirror.ok:
        print(f"mirror not updated: {mirror.why()}", file=sys.stderr)


def mirror_state(connection: sqlite3.Connection) -> tuple[str, dict[str, Any]] | None:
    """The last render's heartbeat as `(timestamp, body)`, or None when none ran: what the dashboard's Health shows."""
    row = connection.execute("SELECT timestamp, body FROM state WHERE kind = 'heartbeat' AND key = ? "
                             "ORDER BY id DESC LIMIT 1", (MIRROR_KEY,)).fetchone()
    return None if row is None else (row["timestamp"], json.loads(row["body"] or "{}"))


def _last_beat_ok(connection: sqlite3.Connection) -> bool:
    found = mirror_state(connection)
    return found is not None and found[1].get("ok") is True


def _mirrored(connection: sqlite3.Connection, rules: list[Rules]) -> Mirror:
    mirror = Mirror(kinds=[one.kind for one in rules])
    try:
        _render(connection, rules, mirror)
    except Exception as error:  # the heartbeat names it; an unknown is not a pass
        mirror.reason = str(error) or type(error).__name__
    return _beat(connection, mirror)


def _beat(connection: sqlite3.Connection, mirror: Mirror) -> Mirror:
    record_state(connection, "heartbeat", key=MIRROR_KEY, body={
        "at": now(), "ok": mirror.ok, "kinds": mirror.kinds, "written": len(mirror.written),
        "reason": mirror.reason})
    return mirror


def _render(connection: sqlite3.Connection, rules: list[Rules], mirror: Mirror) -> None:
    """Every refusal of the whole render first, then each kind's page.

    The vault root must exist: under a missing `$OBSIDIAN_VAULT` the root is
    a default path, and a render there would build a second vault nobody reads.
    """
    roots = []
    for one in rules:
        _refuse_removed_driver(one)
        root = one.vault
        if root is None:
            raise RecordRefused(f"plugin {one.prefix} keeps its pages under {one.root}, which is not set")
        if not root.is_dir():
            # An unset or wrong root names a folder that is not the vault; creating it hides that.
            raise RecordRefused(f"{root} is not a directory; plugin {one.prefix}'s `store.root` names the vault, "
                                f"and the render creates no vault")
        roots.append(root)
    for one, root in zip(rules, roots, strict=True):
        page = f"docs/dashboard/base-{one.kind}.html"
        if _replace(root / page, _page(root, one, list_rows(connection, one.kind)).encode("utf-8")):
            mirror.written.append(page)


#: `_replace` without a check of what the file held: the HTML pages, which nobody edits.
UNCHECKED = object()


def _replace(target: Path, data: bytes, *, held: object = UNCHECKED) -> bool:
    """Write `data` to `target` by temporary file and rename, only when the bytes differ.

    `held` is what the caller checked the file held (`None`: no file). The
    file is read again just before the rename, and a change since refuses:
    an Obsidian Sync edit that lands while the render runs stays. A file
    has no compare-and-swap, so an edit inside the last read and the rename
    is the one window left.
    """
    current: bytes | None = None
    with contextlib.suppress(FileNotFoundError):
        current = target.read_bytes()
    if current == data:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = target.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        if held is not UNCHECKED:
            with contextlib.suppress(FileNotFoundError):
                current = None
                current = target.read_bytes()
            if current != held:
                raise RecordRefused("it changed while the render ran: a hand edit, kept")
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    return True


# ---------------------------------------------------------------- the HTML page


@functools.cache
def _tokens_css() -> str:
    """The foundation's tokens, from the one copy the pack keeps (`bin/sd_research_tokens.py`)."""
    path = Path(__file__).resolve().parents[2] / "bin" / "sd_research_tokens.py"
    spec = importlib.util.spec_from_file_location("sd_research_tokens", path)
    if spec is None or spec.loader is None:
        raise RecordRefused(f"{path} cannot be loaded, so the page has no foundation tokens")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.FOUNDATION_TOKENS_CSS)


PAGE_CSS = """/* Hallmark · macrostructure: Long Document (ledger + reading column) · tone: instrument panel, calm
 * theme: ui-design foundation tokens, unchanged · anchor hue: none (neutral chrome, cyan links)
 * Static and script-free under the Documents policy: system fonts stand in for Plex. */
html, body { overflow-x: clip; }
body { margin: 0; background: var(--color-paper); color: var(--color-ink); font: var(--text-base)/1.5 var(--font-ui); }
main { max-width: var(--measure-list); margin: 0 auto; padding: var(--space-xl) var(--space-md) var(--space-3xl); }
h1 { font-size: var(--text-xl); font-weight: 600; margin: 0 0 var(--space-2xs); }
.meta { color: var(--color-muted); font-size: var(--text-sm); margin: 0 0 var(--space-lg); }
.data { font-family: var(--font-data); font-variant-numeric: tabular-nums; white-space: nowrap; }
a { color: var(--color-accent); }
a:focus-visible { outline: var(--rule-focus) solid var(--color-focus); outline-offset: 2px; }
table.rows { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.rows th { text-align: left; font: 600 var(--text-xs)/1.2 var(--font-label); color: var(--color-muted);
  padding: var(--space-xs); border-bottom: var(--rule-hair) solid var(--color-rule); }
.rows td { padding: var(--space-xs); height: var(--row); vertical-align: top; overflow-wrap: anywhere;
  border-bottom: var(--rule-hair) solid var(--color-rule-2); }
.empty { color: var(--color-muted); }
section.row { margin-top: var(--space-2xl); padding-top: var(--space-lg); border-top: var(--rule-hair) solid var(--color-rule); }
section.row > h2 { font-size: var(--text-lg); font-weight: 600; margin: 0 0 var(--space-sm); overflow-wrap: anywhere; }
dl.fields { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--space-3xs) var(--space-md);
  font-size: var(--text-sm); margin: 0 0 var(--space-md); }
dl.fields dt { color: var(--color-muted); font-family: var(--font-label); }
dl.fields dd { margin: 0; font-family: var(--font-data); overflow-wrap: anywhere; }
.body { max-width: var(--measure); color: var(--color-ink-2); }
.body h2, .body h3, .body h4, .body h5, .body h6 { font-size: var(--text-md); color: var(--color-ink); }
.body pre { background: var(--color-well); padding: var(--space-sm); overflow-x: auto; font: var(--text-sm)/1.45 var(--font-data); }
.body code { font-family: var(--font-data); }
.body table { border-collapse: collapse; border: 0; }
.body th, .body td { border: var(--rule-hair) solid var(--color-rule); }
@media (max-width: 700px) { .rows .optional { display: none; } }
"""


def _page(root: Path, rules: Rules, rows: list[dict[str, Any]]) -> str:
    """One base: a table of every row, then a section per row whose stage is not table-only."""
    name = html.escape(PurePosixPath(rules.base).name)
    newest = max((str(row["updated_at"]) for row in rows), default="")
    score = "score" in rules.fields
    head = ["Title", "Stage", *(["Score"] if score else []), "Created", "Item"]
    lines = [f"<tr><td>{_title_cell(row)}</td><td>{html.escape(row['stage'] or '')}</td>"
             + (f"<td class=\"data\">{html.escape(str(row['fields'].get('score') or ''))}</td>" if score else "")
             + f"<td class=\"data optional\">{html.escape(str(row['created_at'] or '')[:10])}</td>"
             f"<td class=\"data optional\">{row['id']}</td></tr>" for row in rows]
    table = ("<table class=\"rows\"><caption class=\"meta\">Every row, oldest first</caption><thead><tr>"
             + "".join(f"<th scope=\"col\">{label}</th>" for label in head) + "</tr></thead><tbody>"
             + "".join(lines) + "</tbody></table>") if rows else "<p class=\"empty\">No rows.</p>"
    sections = [_section(root, row) for row in rows if row["stage"] not in TABLE_ONLY]
    return ("<!doctype html>\n<html lang=\"en\" data-theme=\"system\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            # A body link to `javascript:` stays dead even opened from disk, with no served policy.
            "<meta http-equiv=\"Content-Security-Policy\" content=\"script-src 'none'; object-src 'none'\">"
            f"<title>{name} · base mirror</title><style>\n{_tokens_css()}\n{PAGE_CSS}</style></head>"
            f"<body><main><h1>{name}</h1><p class=\"meta\">Read-only mirror of the workflow database: "
            f"{len(rows)} row(s), the newest changed <span class=\"data\">{html.escape(newest)}</span>. "
            f"Move or edit a row on the dashboard.</p>\n{table}\n" + "\n".join(sections)
            + "\n</main></body></html>\n")


def _title_cell(row: dict[str, Any]) -> str:
    title = html.escape(row["title"] or "")
    return title if row["stage"] in TABLE_ONLY else f"<a href=\"#item-{row['id']}\">{title}</a>"


def _section(root: Path, row: dict[str, Any]) -> str:
    fields = "".join(f"<dt>{html.escape(name)}</dt><dd>{html.escape(_shown(value))}</dd>"
                     for name, value in row["fields"].items() if name != "kind")
    return (f"<section class=\"row\" id=\"item-{row['id']}\"><h2>{html.escape(row['title'] or '')}</h2>"
            f"<dl class=\"fields\"><dt>stage</dt><dd>{html.escape(row['stage'] or '')}</dd>{fields}</dl>"
            f"<div class=\"body\">{_body_html(root, row)}</div></section>")


def _shown(value: Any) -> str:
    if value is None or value == "":
        return "not set"
    return ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)


def _body_html(root: Path, row: dict[str, Any]) -> str:
    """The body through `md_to_html`, with the vault-only syntax drawn as text first.

    A Meta Bind status control goes, line and all: the stage column shows it.
    Any other control becomes its field's value, read-only. A wikilink becomes
    its alias or target, and a remote image a link. Code fences stay as written.
    """
    out: list[str] = []
    closing = None
    for line in row["body"].split("\n"):
        if closing is not None:
            closing = None if closing.fullmatch(line.strip()) else closing
            out.append(line)
            continue
        closing = _fence_closer(line.strip())
        if closing is not None:
            out.append(line)
            continue
        if any(control.group(1) == "status" for control in CONTROL.finditer(line)):
            continue
        line = CONTROL.sub(lambda control: _shown(row["fields"].get(control.group(1))), line)
        line = WIKILINK.sub(lambda link: (link.group(2) or link.group(1)).strip(), line)
        out.append(REMOTE_IMAGE.sub(lambda image: f"[{image.group(1) or image.group(2)}]({image.group(2)})", line))
    try:
        return md_to_html("\n".join(out), str((root / (row["path"] or "")).parent))
    except WorkflowError:
        return f"<pre>{html.escape(row['body'])}</pre>"
