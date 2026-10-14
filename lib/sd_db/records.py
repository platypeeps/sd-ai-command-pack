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

**The vault gets a read-only mirror (sd:3976).** `render` writes each row
back to its note's path, with `status` from `stage` and a `mirror-hash` of
the rest of the file, and one HTML page per base under `docs/dashboard/`.
A file it did not write, or one changed since, is a hand edit: it stays, and
the render reports it. It runs after each committed write, for that kind,
and on demand (`sd-db records render`); a write never fails for its render.

**The vault stays the source until the flip.** While the plugin's driver is
`vault`, the next import would overwrite a row edited here with its note, so
both writers refuse until the driver says `db`.
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
from typing import Any

from .database import refuse_hub_only, transaction
from .publication_render import _fence_closer, md_to_html
from .sources import MigrationRefused
from .sources.frontmatter import FrontmatterError
from .sources.frontmatter import read as read_frontmatter
from .sources.vault import DUE, NOT_FIELDS, SOURCE, plugin_entries, store_root
from .workflow import MissingItem, WorkflowError, _checked_state, _text, item_state
from .writes import _transition, add_note, create_item, now, record_state, set_item_fields, unresolved_state

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
    #: or None when it names none. The mirror writes only here.
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
    _refuse_before_flip(rules)
    values = _checked_fields(rules, fields or {})
    if "dateCreated" in rules.fields and not values.get("dateCreated"):
        # Every vault note carries it; without it the mirror note would import with no date.
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


# ---------------------------------------------------------------- mirror

#: The `heartbeat` state row each render records: `{at, ok, kinds, written, refused, reason}`.
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
    """What one render did: the kinds, the files written, the files refused, and why it stopped."""

    kinds: list[str]
    written: list[str] = field(default_factory=list)
    #: `(path under the root, reason)`: a hand edit, a file with no row, a row that would not read back.
    refused: list[tuple[str, str]] = field(default_factory=list)
    #: Why the render stopped or never started; `None` when it ran to the end.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None and not self.refused

    def why(self) -> str:
        if self.reason is not None:
            return self.reason
        path, reason = self.refused[0]
        return f"{len(self.refused)} file(s) refused, first {path}: {reason}"


def render(connection: sqlite3.Connection, *, home: Path | str, environ: dict[str, str] | None = None,
           kinds: list[str] | None = None, entries: list[dict[str, Any]] | None = None) -> Mirror:
    """Write the mirror of `kinds`, by default every kind a plugin on the `db` driver declares.

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
    """In the write's transaction: whether the mirror was caught up, then a heartbeat saying it is not.

    A process stopped between the commit and the render leaves that failed
    heartbeat, so the next write renders every kind and Health shows the gap.
    """
    caught_up = _last_beat_ok(connection)
    _beat(connection, Mirror(kinds=[rules.kind], reason=f"a {rules.kind} write is committed and not yet rendered"))
    return caught_up


def _mirror_after(connection: sqlite3.Connection, rules: Rules, caught_up: bool) -> None:
    """The render after a committed write. It prints and records a failure and never raises.

    When the mirror was not caught up before the write, it renders every kind,
    so the next write catches up whichever kind a failure left behind.
    """
    try:
        if connection.in_transaction:
            raise RecordRefused("the write is inside the caller's open transaction, so it is not committed yet")
        refuse_hub_only(connection, "the records mirror")
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


def _last_beat_ok(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT body FROM state WHERE kind = 'heartbeat' AND key = ? ORDER BY id DESC LIMIT 1",
                             (MIRROR_KEY,)).fetchone()
    return row is not None and json.loads(row["body"] or "{}").get("ok") is True


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
        "refused": [{"path": path, "reason": reason} for path, reason in mirror.refused],
        "reason": mirror.reason})
    return mirror


def _render(connection: sqlite3.Connection, rules: list[Rules], mirror: Mirror) -> None:
    """Every refusal of the whole render first, then each kind's notes, strays and page.

    The base folder must exist: under a missing `$OBSIDIAN_VAULT` the root is
    a default path, and a render there would build a second vault nobody reads.
    """
    if unresolved_state(connection, "restore"):
        raise RecordRefused("a restore is unresolved, so the rows may be older than the mirror; "
                            "re-apply edits from the mirror, then resume the restore")
    roots = []
    for one in rules:
        if one.driver != "db":
            raise RecordRefused(f"plugin {one.prefix}'s `store.driver` is {one.driver!r}, so the vault is "
                                f"still the source of {one.kind} notes and nothing renders over them")
        root = one.vault
        if root is None:
            raise RecordRefused(f"plugin {one.prefix} keeps its notes under {one.root}, which is not set")
        if not (root / one.base).is_dir():
            # An unset or wrong root names a folder that is not the vault; creating it hides that.
            raise RecordRefused(f"{root / one.base} is not a directory; the {one.kind} base is where plugin "
                                f"{one.prefix}'s `store.bases` says it is, and the mirror creates no vault")
        roots.append(root)
    for one, root in zip(rules, roots, strict=True):
        rows = list_rows(connection, one.kind)
        for row in rows:
            try:
                _mirror_note(root, one, row, mirror)
            except RecordRefused as refusal:
                mirror.refused.append((row["path"] or f"item {row['id']}", str(refusal)))
        _strays(root, one, rows, mirror)
        page = f"docs/dashboard/base-{one.kind}.html"
        if _replace(root / page, _page(root, one, rows).encode("utf-8")):
            mirror.written.append(page)


def _mirror_note(root: Path, rules: Rules, row: dict[str, Any], mirror: Mirror) -> None:
    """Write one row's note, unless the file there is a hand edit."""
    relative = row["path"] or ""
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or path.suffix != ".md" or \
            path.parts[:len(PurePosixPath(rules.base).parts)] != PurePosixPath(rules.base).parts:
        raise RecordRefused(f"item {row['id']}'s path {relative!r} is not a note under {rules.base}")
    target = root / relative
    try:
        held: bytes | None = target.read_bytes()
    except FileNotFoundError:
        held = None
    if held is not None:
        problem = _hand_edit(row, held)
        if problem:
            raise RecordRefused(problem)
    if _replace(target, _note(rules, row).encode("utf-8"), held=held):
        mirror.written.append(relative)


def _note(rules: Rules, row: dict[str, Any]) -> str:
    """The row as a note: its fields and `status` as frontmatter, the body verbatim, the hash last.

    The note must read back as the row, as the import reads it, or a
    rollback's import would land another row from it: anything else refuses.
    """
    fields = {name: value for name, value in row["fields"].items() if name != "kind"}
    matter = "\n".join(_frontmatter_line(name, value) for name, value in {**fields, "status": row["stage"]}.items())
    content = f"---\n{matter}\n---\n{row['body']}\n"
    try:
        found, body = read_frontmatter(content)
    except FrontmatterError as error:
        found, body = {"unreadable": str(error)}, None
    if found != {**fields, "status": row["stage"]} or body != row["body"]:
        raise RecordRefused(f"item {row['id']} would not read back from its note, since the frontmatter "
                            f"reader has no form for one of its values; kept as it is")
    # The import's payload beyond the fields: title, created and due (`sources.vault.Reader.freeze`).
    due = str(fields.get(rules.due) or "").strip() or None if rules.due else None
    payload = (str(fields.get("title") or PurePosixPath(row["path"] or "").stem).strip(),
               str(fields.get("dateCreated") or "").strip(), due)
    if payload != (row["title"], row["created_at"], row["due"]):
        raise RecordRefused(f"item {row['id']} would not read back from its note: its title, created date "
                            f"or due date is not the one its fields give; kept as it is")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"---\n{matter}\nmirror-hash: {digest}\n---\n{row['body']}\n"


def _frontmatter_line(name: str, value: Any) -> str:
    if value is None:
        return f"{name}:"
    if isinstance(value, list):
        return "\n".join([f"{name}:", *(f"  - {_frontmatter_value(item)}" for item in value)])
    return f"{name}: {_frontmatter_value(value)}"


#: Words a YAML 1.1 or 1.2 reader turns into a bool, a null or a float when bare.
YAML_WORDS = {"y", "n", "yes", "no", "true", "false", "on", "off", "null", "~", ".inf", "-.inf", "+.inf", ".nan"}
#: Bare text a YAML reader may read as a number, a date or a time: digits, signs, dots, colons, `_`, `e`, `x`.
NUMBER_LIKE = re.compile(r"[-+.]?[0-9][0-9a-zA-Z_.:+-]*")
#: Bare numbers and dates that stay bare, so Obsidian keeps them number and date properties.
TYPED = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?|[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _frontmatter_value(value: Any) -> str:
    """The text as a YAML scalar that the importer's reader and a YAML reader both read back as it is.

    Bare when YAML reads it as the same string, or as the number or date it
    is. Else in double quotes, or single when it holds `"` or `\\`: the
    importer's reader strips the quotes and unescapes nothing, so a text
    that needs both kinds has no form, and the row refuses.
    """
    text = str(value)
    if any(ord(char) < 32 or char == "\x7f" for char in text):
        raise RecordRefused(f"{text!r} holds a control character, so it would not read back from a note")
    if TYPED.fullmatch(text) or not (
            text != text.strip() or text[:1] in "-?:,[]{}#&*!|>'\"%@`" or ": " in text or " #" in text
            or text.endswith(":") or text.lower() in YAML_WORDS or NUMBER_LIKE.fullmatch(text)):
        return text
    if '"' not in text and "\\" not in text:
        return f'"{text}"'
    if "'" not in text:
        return f"'{text}'"
    raise RecordRefused(f"{text!r} needs quotes and holds both kinds, so it would not read back from a note")


def _hand_edit(row: dict[str, Any], held: bytes) -> str | None:
    """Why the file at a row's path may not be overwritten, or None.

    A file with a `mirror-hash` may be when the hash is its own content's. A
    file without one may be when it reads as the row: the import payload of
    the note equals the row's, so nothing in it is newer.
    """
    try:
        text = held.decode("utf-8")
        matter, body = read_frontmatter(text)
    except (UnicodeDecodeError, FrontmatterError):
        return "it is not a note the renderer can read: a hand edit, kept"
    if "mirror-hash" in matter:
        value = matter["mirror-hash"]
        rest = text.replace(f"mirror-hash: {value}\n", "", 1) if isinstance(value, str) else text
        if isinstance(value, str) and hashlib.sha256(rest.encode("utf-8")).hexdigest() == value:
            return None
        return "it differs from its mirror-hash: a hand edit, kept"
    fields = {name: value for name, value in matter.items() if name != "status"}
    if fields == {name: value for name, value in row["fields"].items() if name != "kind"} \
            and str(matter.get("status") or "").strip() == row["stage"] and body == row["body"]:
        return None
    return "it has no mirror-hash and differs from its row: a hand edit or a note changed since the import, kept"


def _strays(root: Path, rules: Rules, rows: list[dict[str, Any]], mirror: Mirror) -> None:
    """Report every note in the base folder no row holds, compared as macOS compares names."""
    held = {_file_key(row["path"] or "") for row in rows}
    for path in sorted((root / rules.base).rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        if _file_key(relative) not in held:
            mirror.refused.append((relative, "no row holds this file; kept: add it as a row or delete it"))


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
