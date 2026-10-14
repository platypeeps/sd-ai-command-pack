"""Vault base rows, read and written once the database is their source (sd:3973).

Five Obsidian bases land in `item` through the vault import: kind `idea`,
`source` `vault`, the plugin kind in `fields.kind`, the ladder word in
`stage`. From the flip of the plugin's `store.driver` to `db` on, these
functions are how a row changes; the vault holds only a rendered mirror.

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
line: the import stores the note's body as it is, and so does every write here.

**Each write is one transaction.** The row, its notes and its status change
commit together or not at all, so a stopped write leaves nothing to finish.

**The vault stays the source until the flip.** While the plugin's driver is
`vault`, the next import would overwrite a row edited here with its note, so
both writers refuse until the driver says `db`.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .database import transaction
from .sources import MigrationRefused
from .sources.vault import NOT_FIELDS, SOURCE, plugin_entries
from .workflow import MissingItem, WorkflowError, _checked_state, _text, item_state
from .writes import _transition, add_note, create_item, set_item_fields

#: Keys a caller may not set in `fields`: `status` is `stage`, `mirror-hash`
#: is the mirror file's, `kind` is the declared kind.
RESERVED_FIELDS = NOT_FIELDS | {"kind"}


class RecordRefused(WorkflowError):
    """A base row write the kind's rules do not allow, or one whose rules are unknown."""


@dataclass(frozen=True)
class Rules:
    """One kind's rules, as the pack's plugin list reports them."""

    kind: str
    prefix: str
    driver: str
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
    for entry in entries:
        problem = entry.get("manifestError") or entry.get("dashboardError") or (
            None if entry.get("readable") else entry.get("why") or "unreadable")
        if problem:
            raise RecordRefused(f"the plugin at {entry.get('root')} cannot be read, so the rules of "
                                f"kind {kind!r} cannot be known: {problem}")
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
            kind=kind, prefix=str(entry["prefix"]), driver=str(store["driver"]),
            base=str(store["bases"][kind]), stages=dict(entry["workflow"][kind]["status"]),
            fields=tuple(declared["fields"]), initial=str(declared["initial-status"]),
            transitions=declared.get("transitions"), human_only=dict(declared.get("human-only") or {}),
            protected=tuple(declared.get("protected-fields") or ()),
            unique=tuple(declared.get("unique-fields") or ()), floor=dict(declared.get("floor") or {}),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RecordRefused(f"the pack's rules for kind {kind!r} are missing {error}") from None


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
    store verbs use; two rows of one kind with that stem refuse as ambiguous.
    """
    if item is None:
        if kind is None or title is None:
            raise RecordRefused("name a base row by its id, or by its kind and title")
        held = [row["id"] for row in list_rows(connection, kind)
                if PurePosixPath(row["path"] or "").stem == title]
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
    _refuse_before_flip(rules)
    values = _checked_fields(rules, fields or {})
    for name in rules.floor:
        _refuse_below_floor(rules, name, values.get(name))
    stage = rules.initial if stage is None else stage
    _refuse_move(rules, rules.initial, stage)
    if not isinstance(body, str):
        raise RecordRefused("body must be Markdown text")
    title = _file_title(title)
    path = f"{rules.base}/{title}.md"
    identity = f"{rules.kind}:{path}"
    with transaction(connection):
        _refuse_taken(connection, path)
        _refuse_duplicate(connection, rules, values, skip=None)
        item = create_item(connection, kind="idea", title=title, status=rules.stages[stage],
                           source=SOURCE, external_id=identity, path=path, stage=stage,
                           fields={**values, "kind": rules.kind}, body={"markdown": body}, session=who)
        return get_row(connection, item)


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
    _refuse_before_flip(rules)
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
            columns["fields"] = {**held, **changes}
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
        return get_row(connection, item)


def _refuse_before_flip(rules: Rules) -> None:
    if rules.driver != "db":
        raise RecordRefused(f"plugin {rules.prefix}'s `store.driver` is {rules.driver!r}, so the vault is "
                            f"still the source of {rules.kind} rows and the next import would overwrite this "
                            f"write; write the note instead")


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


def _refuse_taken(connection: sqlite3.Connection, path: str) -> None:
    """A row's file name is one vault-wide wikilink target, and macOS file names ignore case."""
    name = PurePosixPath(path).name.casefold()
    for row in connection.execute("SELECT id, path FROM item WHERE source = ?", (SOURCE,)):
        if PurePosixPath(row["path"] or "").name.casefold() == name:
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
