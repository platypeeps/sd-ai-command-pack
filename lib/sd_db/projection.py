"""The experiments projection: the items sd writes as rows into the team's experiments databases (sd:3982).

The design is `docs/work/2026-10-14-experiments-projection/design.md`. An
item opts in through its designation, `fields.experiments`, the item analogue
of a document's `notion=`:

    {"as": "experiment", "since": "2026-10-14T20:30:00+00:00"}
    {"as": "task", "of": 4021, "since": "2026-10-14T20:31:00+00:00"}

`as: off` stops the projection and keeps `row`, so a later designation
resumes on the same row. `row` is the Notion page id of the row, recorded by
`record_row` after a create or pinned with `row:ID`.

The rest of the designation is the guard's state, written by the plan and by
`record_row` and never by hand: `written` holds, per sd-owned field, the value
sd last wrote and saw confirmed; `writing` and `creating` are the intents a
plan recorded, each bound to its generation (the request fingerprint) and the
designation it was planned under; `confirmed` is the generation last
confirmed; `yielded` lists the fields a person holds.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from .database import transaction
from .errors import SdDbError

#: The item field the designation lives in.
FIELD = "experiments"

#: What a designation makes of an item, and the table each target is in.
AS = ("experiment", "task", "off")
TARGETS = {"experiment": "experiments", "task": "tasks"}

#: The keys a designation may hold: the operator's, then the guard's.
KEYS = ("as", "of", "since", "row", "url", "written", "writing", "creating", "confirmed", "yielded")

#: The guard's state, dropped together when the row changes: values sd wrote
#: to one row say nothing about another.
STATE = ("url", "written", "writing", "creating", "confirmed", "yielded")

#: Item status to the `Status` select, both databases. A cancelled item is `done`.
STATUS = {"planning": "Todo", "ready": "Todo", "in_progress": "In Progress",
          "ready_to_send": "In Progress", "blocked": "Blocked", "done": "Done"}

#: Item status to the `Stage` select, seeded at create only (Q3). A `work-idea` is an Idea whatever its status.
STAGE = {"planning": "Scoping", "ready": "Scoping", "in_progress": "Running",
         "ready_to_send": "Running", "blocked": "Running", "done": "Evaluating"}
IDEA_KIND = "work-idea"
IDEA_STAGE = "Idea"

#: Item priority to the tasks database's `Priority` select, seeded at create only. No priority is empty.
PRIORITY = {1: "High", 2: "Medium", 3: "Low", 4: "Low"}

#: A Notion page id, compact or hyphenated, ending a URL's path or alone.
PAGE_ID = re.compile(r"(?:^|[/-])([0-9a-fA-F]{8}-?(?:[0-9a-fA-F]{4}-?){3}[0-9a-fA-F]{12})$")


class ProjectionRefusal(SdDbError):
    """A designation, plan or record that cannot be applied; nothing was written."""


def row_id(value: Any) -> str:
    """The page id `value` names, as a lowercase hyphenated UUID, or `""` when it names none.

    One spelling, so a compact id, a hyphenated one and a page URL ending in
    either compare equal. A query string and a fragment are not the path.
    """
    if not isinstance(value, str):
        return ""
    path = re.split(r"[?#]", value.strip(), maxsplit=1)[0].rstrip("/")
    found = PAGE_ID.search(path)
    return str(uuid.UUID(found.group(1))) if found else ""


def status_value(status: str) -> str:
    """The `Status` option for an item status."""
    return STATUS[status]


def stage_value(kind: str, status: str) -> str:
    """The `Stage` option an experiment row is seeded with."""
    return IDEA_STAGE if kind == IDEA_KIND else STAGE[status]


def priority_value(priority: Any) -> str | None:
    """The `Priority` option a task row is seeded with, or None for none."""
    return PRIORITY.get(priority) if type(priority) is int else None


def _intent(name: str, value: Any) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("generation"), str) \
            or not isinstance(value.get("designation"), dict):
        raise ProjectionRefusal(f"experiments.{name} must be an intent with a generation and a designation")


def validate(value: Any) -> dict[str, Any]:
    """`value` as a designation, or `ProjectionRefusal` naming what is wrong.

    Returns a copy, so a caller never stores the object it was handed.
    """
    if not isinstance(value, dict):
        raise ProjectionRefusal(f"the experiments designation must be an object, not {type(value).__name__}")
    unknown = sorted(set(value) - set(KEYS))
    if unknown:
        raise ProjectionRefusal(f"experiments: {unknown[0]!r} is not a designation key")
    out = dict(value)
    if out.get("as") not in AS:
        raise ProjectionRefusal(f"experiments.as must be experiment, task or off, not {out.get('as')!r}")
    of = out.get("of")
    if out["as"] == "task":
        if type(of) is not int or of < 1:
            raise ProjectionRefusal(f"experiments.of must name the experiment's item for a task, not {of!r}")
    elif of is not None:
        raise ProjectionRefusal(f"experiments.of names an experiment only for a task, not for {out['as']}")
    if not isinstance(out.get("since"), str) or not out["since"]:
        raise ProjectionRefusal("experiments.since must be the time of the last designation change")
    if out.get("row") is not None:
        if row_id(out["row"]) != out["row"]:
            raise ProjectionRefusal(f"experiments.row must be a Notion page id, not {out['row']!r}")
    for name in ("writing", "creating"):
        if out.get(name) is not None:
            _intent(name, out[name])
    if not isinstance(out.get("written", {}), dict):
        raise ProjectionRefusal("experiments.written must map each field to the value sd last wrote")
    yielded = out.get("yielded", [])
    if not isinstance(yielded, list) or any(not isinstance(field, str) for field in yielded):
        raise ProjectionRefusal("experiments.yielded must list field names")
    for name in ("url", "confirmed"):
        if out.get(name) is not None and not isinstance(out[name], str):
            raise ProjectionRefusal(f"experiments.{name} must be text")
    return out


def _fields(connection: sqlite3.Connection, item: int) -> tuple[sqlite3.Row, dict[str, Any]]:
    """The item row and its fields, or a refusal: a restore open, no such item, fields unreadable.

    The refusals `channels.record_url` makes, for the same reasons.
    """
    from .writes import unresolved_state

    if type(item) is not int or item < 1:
        raise ProjectionRefusal(f"item must be an sd item number, not {item!r}")
    if unresolved_state(connection, "restore"):
        raise ProjectionRefusal("a restore is unresolved, so the item rows may be older than the receipts; "
                                "resolve the restore, then run again")
    row = connection.execute("SELECT * FROM item WHERE id = ?", (item,)).fetchone()
    if row is None:
        raise ProjectionRefusal(f"sd:{item} is not an item in this database")
    try:
        fields = json.loads(row["fields"]) if row["fields"] else {}
    except ValueError as error:
        raise ProjectionRefusal(f"sd:{item}'s fields are not JSON ({error}); left as they are") from error
    if not isinstance(fields, dict):
        raise ProjectionRefusal(f"sd:{item}'s fields are not an object; left as they are")
    return row, fields


def designation(fields: dict[str, Any], item: int) -> dict[str, Any] | None:
    """The item's designation, validated, or None when it has none."""
    if fields.get(FIELD) is None:
        return None
    try:
        return validate(fields[FIELD])
    except ProjectionRefusal as refusal:
        raise ProjectionRefusal(f"sd:{item}: {refusal}") from None


def _store(connection: sqlite3.Connection, item: int, fields: dict[str, Any], value: dict[str, Any]) -> None:
    from .writes import now

    fields[FIELD] = value
    connection.execute("UPDATE item SET fields = ?, updated_at = ? WHERE id = ?",
                       (json.dumps(fields, sort_keys=True), now(), item))


def _parse(specs: list[str]) -> tuple[tuple[str, int | None] | None, str | None]:
    """`--experiment` values as (as, of) and a row change: a row id, `new`, or None."""
    shape: tuple[str, int | None] | None = None
    row: str | None = None
    for spec in specs:
        text = spec.strip()
        if text in ("yes", "off") or text.startswith("of:"):
            if shape is not None:
                raise ProjectionRefusal("give one of yes, of:M or off")
            if text.startswith("of:"):
                number = text[3:].removeprefix("sd:")
                if not number.isdigit() or int(number) < 1:
                    raise ProjectionRefusal(f"of: must name an item number, such as of:4021, not {text!r}")
                shape = ("task", int(number))
            else:
                shape = ("experiment" if text == "yes" else "off", None)
        elif text == "new" or text.startswith("row:"):
            if row is not None:
                raise ProjectionRefusal("give one of row:ID or new")
            row = "new" if text == "new" else row_id(text[4:])
            if not row:
                raise ProjectionRefusal(f"row: must name a Notion page id or URL, not {text!r}")
        else:
            raise ProjectionRefusal(f"--experiment takes yes, of:M, row:ID, new or off, not {spec!r}")
    return shape, row


def _parent_check(connection: sqlite3.Connection, item: int, of: int) -> None:
    """A task's experiment: another item, designated `experiment`; and `item` is no experiment's parent."""
    if of == item:
        raise ProjectionRefusal(f"sd:{item} cannot be a task of itself")
    _, parent_fields = _fields(connection, of)
    parent = designation(parent_fields, of)
    if parent is None or parent["as"] != "experiment":
        raise ProjectionRefusal(f"sd:{of} is not designated experiment; designate it first "
                                f"with `sd task edit {of} --experiment yes`")
    for child, held in designated_rows(connection):
        if held["as"] == "task" and held.get("of") == item and child["id"] != item:
            raise ProjectionRefusal(f"sd:{item} is the experiment of task sd:{child['id']}; "
                                    "a task of a task is one level too deep")


def designate(connection: sqlite3.Connection, item: int, specs: list[str], *, who: str,
              expected_revision: str | None = None) -> dict:
    """Apply `sd task edit N --experiment ...` to item `item`, in one transaction.

    `yes` designates an experiment, `of:M` a task of experiment M, and `off`
    stops the projection keeping `row`. `row:ID` pins an existing row and
    `new` drops the pinned one, so the next drain creates one; either drops
    the guard's state, which belongs to the old row. `since` moves with every
    change. An equal designation writes nothing. Returns the item's state.
    """
    from .workflow import StaleItem, item_state
    from .writes import add_note

    if not specs:
        raise ProjectionRefusal("--experiment needs a value: yes, of:M, row:ID, new or off")
    shape, row = _parse(specs)
    with transaction(connection):
        if expected_revision is not None and item_state(connection, item)["revision"] != expected_revision:
            raise StaleItem(f"item {item} changed; reload it before applying this change")
        _, fields = _fields(connection, item)
        held = designation(fields, item)
        if held is None and shape is None:
            raise ProjectionRefusal(f"sd:{item} is not designated; give yes or of:M with row:ID or new")
        value = dict(held or {})
        if shape is not None:
            value["as"], of = shape
            value.pop("of", None)
            if of is not None:
                _parent_check(connection, item, of)
                value["of"] = of
        if row is not None:
            pinned = None if row == "new" else row
            if pinned != value.get("row") or row == "new":
                for key in STATE:
                    value.pop(key, None)
            value["row"] = pinned
            if pinned is None:
                value.pop("row")
        same = held is not None and all(held.get(key) == value.get(key) for key in KEYS if key != "since")
        if same:
            return item_state(connection, item)
        # To the microsecond: an off and back within one second is still a change of designation.
        value["since"] = datetime.now(UTC).isoformat(timespec="microseconds")
        _store(connection, item, fields, validate(value))
        add_note(connection, item, "comment", f"Updated experiments by {who}", session=who)
    return item_state(connection, item)


def record_row(connection: sqlite3.Connection, item: int, fingerprint: str, url: str, who: str) -> str:
    """Confirm the plan of generation `fingerprint` on item `item`, whose row is at `url`.

    The drain's `delivered` for a `notion-row` request. One transaction:

    - An intent bound to `fingerprint` and planned under the current
      designation: record `row` and `url`, move `writing` to `written`,
      clear `creating`, set `confirmed`, and add one note when the URL is new.
      Returns `recorded`.
    - No intent outstanding, `confirmed` equal to `fingerprint` and `row`
      equal to the URL's id: `unchanged`, so a re-run after a failed receipt
      finishes.
    - Anything else refuses and writes nothing.
    """
    from .writes import add_note

    given = row_id(url)
    if not given:
        raise ProjectionRefusal(f"{url!r} names no Notion page id")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ProjectionRefusal("give the fingerprint of the generation drained")
    with transaction(connection):
        _, fields = _fields(connection, item)
        held = designation(fields, item)
        if held is None:
            raise ProjectionRefusal(f"sd:{item} is not designated; nothing to record")
        writing = held.get("writing") if (held.get("writing") or {}).get("generation") == fingerprint else None
        creating = held.get("creating") if (held.get("creating") or {}).get("generation") == fingerprint else None
        intent = writing or creating
        if intent is None:
            if not held.get("writing") and not held.get("creating") and held.get("confirmed") == fingerprint \
                    and held.get("row") == given:
                return "unchanged"
            raise ProjectionRefusal(f"sd:{item} has no plan outstanding for {fingerprint[:12]}; run project and "
                                    "plan again")
        planned = intent["designation"]
        moved = [key for key in ("as", "of", "since") if planned.get(key) != held.get(key)]
        if planned.get("row") != held.get("row"):
            moved.append("row")
        if moved:
            raise ProjectionRefusal(f"sd:{item}'s designation moved since the plan ({', '.join(moved)}); "
                                    "the next plan drops that intent")
        if held.get("row") is not None and held["row"] != given:
            raise ProjectionRefusal(f"the URL names row {given}, and sd:{item}'s designation names "
                                    f"{held['row']}; nothing recorded")
        created = held.get("url") != url
        value = dict(held)
        value["written"] = {**held.get("written", {}), **(writing or {}).get("values", {})}
        value.update(row=given, url=url, confirmed=fingerprint)
        value.pop("writing", None)
        value.pop("creating", None)
        _store(connection, item, fields, validate(value))
        if created:
            target = intent.get("target") or TARGETS.get(held["as"], "experiments")
            add_note(connection, item, "comment", f"Projected to {target}: {url}", session=who)
    return "recorded"


# The queue and the plan (E2). Nothing below reaches Notion: `project` writes a
# request per designated item, the drain fetches the row, and `plan` decides
# from that fetch what the drain writes.

#: Every property sd writes, per target, with its Notion type. The first is the title.
PROPERTIES = {
    "experiments": {"Experiment": "title", "Status": "select", "Stage": "select"},
    "tasks": {"Task": "title", "Status": "select", "Experiment": "relation", "Due": "date", "Priority": "select"},
}

#: The sd-owned properties: written on every plan, under the guard. The rest of `PROPERTIES` are seeds.
OWNED = {"experiments": ("Status",), "tasks": ("Status", "Experiment", "Due")}

#: The options each select must offer: every value the maps can write there.
OPTIONS = {"Status": tuple(dict.fromkeys(STATUS.values())),
           "Stage": (IDEA_STAGE, *dict.fromkeys(STAGE.values())),
           "Priority": tuple(dict.fromkeys(PRIORITY.values()))}

#: Notion types a select may be read as: the team's `Status` is a select, and Notion's own status type
#: takes an option by name the same way.
SELECTS = ("select", "status")

#: The one line the row's body holds, written at create (Q2). The drain's search after an interrupted
#: create matches its first words.
POINTER = "Projected from sd:{item}. sd keeps Status current; edit anything else."


def _empty(value: Any) -> Any:
    """One spelling for a live or wanted value: None for empty, a sorted id list for a relation."""
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, list):
        return sorted(row_id(entry) or str(entry) for entry in value)
    return value.strip() if isinstance(value, str) else value


def wanted(connection: sqlite3.Connection, row: sqlite3.Row, held: dict[str, Any]) -> dict[str, Any]:
    """The sd-owned values item `row` wants on its row, `_empty` spelled."""
    values: dict[str, Any] = {"Status": status_value(row["status"])}
    if held["as"] == "task":
        _, parent_fields = _fields(connection, held["of"])
        parent = designation(parent_fields, held["of"])
        if parent is None or parent["as"] != "experiment":
            raise ProjectionRefusal(f"parent sd:{held['of']} is not designated experiment")
        values["Experiment"] = _empty([parent["row"]] if parent.get("row") else None)
        values["Due"] = _empty(row["due"])
    return values


def fingerprint(request: dict[str, Any]) -> str:
    """The generation of a request: the item, its designation, the database and the sd-owned values.

    Not the title, `Stage` or `Priority`: those are seeds, written once, so a change to one queues nothing.
    """
    import hashlib

    named = {key: request.get(key) for key in ("item", "as", "of", "since", "row", "database", "values")}
    return hashlib.sha256(json.dumps(named, sort_keys=True).encode("utf-8")).hexdigest()


def request_for(connection: sqlite3.Connection, row: sqlite3.Row, held: dict[str, Any],
                databases: dict[str, str]) -> dict[str, Any]:
    """The `notion-row` request item `row` asks for, with its fingerprint. Refuses an `off` designation."""
    from . import paths

    if held["as"] not in TARGETS:
        raise ProjectionRefusal(f"sd:{row['id']} is designated off")
    target = TARGETS[held["as"]]
    request = {
        "destination": "notion-row", "item": row["id"], "document": f"sd:{row['id']}",
        "as": held["as"], "of": held.get("of"), "since": held["since"], "row": held.get("row"),
        "database": databases[target], "target": target,
        # The disk path `sd-status` compares, as a research request carries.
        "repo": str(paths.expand(row["repo"])) if row["repo"] else "",
        "values": wanted(connection, row, held),
    }
    request["fingerprint"] = fingerprint(request)
    return request


def designated_rows(connection: sqlite3.Connection,
                    problems: list[str] | None = None) -> list[tuple[sqlite3.Row, dict[str, Any]]]:
    """Every item holding a designation, by id; one that cannot be read goes to `problems`."""
    found = []
    for row in connection.execute(
            "SELECT * FROM item WHERE fields LIKE ? ORDER BY id", (f'%"{FIELD}"%',)).fetchall():
        try:
            fields = json.loads(row["fields"])
            held = designation(fields, row["id"]) if isinstance(fields, dict) else None
        except (ValueError, ProjectionRefusal) as error:
            if problems is not None:
                problems.append(f"sd:{row['id']}: the designation cannot be read ({error})")
            continue
        if held is not None:
            found.append((row, held))
    return found


def _channels(connection: sqlite3.Connection, row: sqlite3.Row) -> None:
    """Refuse an item whose repo's channels setting leaves out `notion`, or cannot be read (sd:3462)."""
    if not row["repo"]:
        return
    from . import paths
    from .channels import outbound
    from .repos import repo_channels

    try:
        setting = outbound(repo_channels(connection, paths.expand(row["repo"])))
    except SdDbError as error:
        raise ProjectionRefusal(f"the channels setting of {row['repo']} cannot be read ({error}); "
                                "unknown is not a pass") from None
    if setting is not None and "notion" not in setting:
        raise ProjectionRefusal(f"the channels setting of {row['repo']} leaves out notion; not projected")


def _schema(live: dict[str, Any], target: str, names: tuple[str, ...] | list[str]) -> None:
    """Refuse a live schema that lacks, retypes or narrows a property this plan writes, naming it."""
    schema = live.get("schema")
    if not isinstance(schema, dict):
        raise ProjectionRefusal("the live file holds no schema; fetch the database before the plan")
    for name in names:
        kind = PROPERTIES[target][name]
        found = schema.get(name)
        if not isinstance(found, dict):
            raise ProjectionRefusal(f"{name}: the {target} database has no such property; fix Notion or the mapping")
        if found.get("type") not in (SELECTS if kind == "select" else (kind,)):
            raise ProjectionRefusal(f"{name}: the {target} database has it as {found.get('type')!r}, not {kind}")
        missing = [option for option in OPTIONS.get(name, ()) if option not in (found.get("options") or [])]
        if kind == "select" and missing:
            raise ProjectionRefusal(f"{name}: the {target} database has no option {missing[0]!r}; "
                                    "sd adds no option")


def _live_row(entry: Any, database: str, what: str) -> dict[str, Any]:
    """A fetched row: its id and parent, read, and its parent the request's database."""
    if not isinstance(entry, dict) or not row_id(entry.get("id")):
        raise ProjectionRefusal(f"the live file's {what} has no page id")
    parent = row_id(entry.get("parent"))
    if parent != database:
        raise ProjectionRefusal(f"the {what} {row_id(entry.get('id'))} is in database {parent or 'unknown'}, "
                                f"not {database}; never written across databases")
    if not isinstance(entry.get("properties"), dict):
        raise ProjectionRefusal(f"the live file's {what} holds no properties")
    return entry


def _question(item: int, reason: str, options: list[str]) -> ProjectionRefusal:
    """A refusal the drain turns into one question note on the item, unless one is open."""
    lines = "\n".join(f"Option: {option}" for option in options)
    return ProjectionRefusal(f"{reason}; file one question on sd:{item} unless one is open:\n{reason}\n{lines}")


def _shown(value: Any) -> str:
    if value is None:
        return "nothing"
    return ", ".join(value) if isinstance(value, list) else str(value)


def plan(connection: sqlite3.Connection, request: dict[str, Any], live: dict[str, Any] | None, *,
         databases: dict[str, str], who: str) -> dict[str, Any]:
    """The guard, in code: what the drain writes to the row for `request`, given the `live` fetch.

    `live` None is the drain's `--missing`: the pinned row was not found. One
    transaction. Refuses, writing nothing, a request that is not a fresh
    recompute of its item (stale), an item whose repo leaves `notion` out, a
    schema that does not fit the mapping, a row in another database, and a
    row it cannot identify. Otherwise records the intent on the item --
    `writing`, and `creating` for a create -- bound to the request's
    generation and the designation it was planned under, and returns the
    properties to write. An sd-owned field whose live value differs from
    `written` is refused and listed in `yielded`, with one note per episode.
    """
    from .writes import add_note

    item = request.get("item")
    if not isinstance(item, int) or isinstance(item, bool):
        raise ProjectionRefusal(f"stale: the request names no item ({item!r}); run project")
    with transaction(connection):
        row, fields = _fields(connection, item)
        held = designation(fields, item)
        if held is None or held["as"] not in TARGETS:
            raise ProjectionRefusal(f"stale: sd:{item} is no longer designated; run project")
        try:
            fresh = request_for(connection, row, held, databases)
        except ProjectionRefusal as refusal:
            raise ProjectionRefusal(f"stale: {refusal}; run project") from None
        if fresh["fingerprint"] != request.get("fingerprint"):
            raise ProjectionRefusal(f"stale: sd:{item} changed since project queued this request; run project")
        _channels(connection, row)
        target, database, values = fresh["target"], fresh["database"], fresh["values"]
        if live is None:
            if not held.get("row"):
                raise ProjectionRefusal(f"--missing names a pinned row, and sd:{item} pins none")
            raise _question(item, f"Row {held['row']} of sd:{item} was not found in the {target} database",
                            ["stop projecting it, `sd task edit %d --experiment off`" % item,
                             "create a new row, `sd task edit %d --experiment new`" % item])
        if target == "tasks" and values["Experiment"] is None:
            raise ProjectionRefusal(f"parent sd:{held['of']} has no row yet; drain experiments first")
        if row_id(live.get("database")) != database:
            raise ProjectionRefusal(f"the live schema is database {row_id(live.get('database')) or 'unknown'}, "
                                    f"and the request names {database}")
        value = dict(held)
        live_row = None
        if held.get("row"):
            live_row = _live_row(live.get("row"), database, "row")
            if row_id(live_row["id"]) != held["row"]:
                raise ProjectionRefusal(f"the live row is {row_id(live_row['id'])}, and sd:{item} pins {held['row']}")
        elif held.get("creating"):
            creating = held["creating"]
            if row_id(creating.get("database")) != database:
                raise _question(item, f"sd:{item} was being created in database {creating.get('database')}, and "
                                      f"the configured database is now {database}",
                                ["no row exists, create it, `sd task edit %d --experiment new`" % item,
                                 "this is the row, `sd task edit %d --experiment row:ID`" % item])
            if not isinstance(live.get("candidates"), list):
                raise ProjectionRefusal(f"search: an earlier create of sd:{item} may have landed; search the "
                                        f"{target} database for pages whose body opens with "
                                        f"`{POINTER.format(item=item).split(' sd keeps')[0]}` and plan again "
                                        "with them as candidates")
            candidates = [_live_row(entry, database, "candidate") for entry in live["candidates"]]
            if len(candidates) != 1:
                found = ", ".join(row_id(entry["id"]) for entry in candidates) or "none"
                raise _question(item, f"An earlier create of sd:{item} may have landed; rows found by the "
                                      f"pointer sd:{item}: {found}",
                                ["no row exists, create it, `sd task edit %d --experiment new`" % item,
                                 "this is the row, `sd task edit %d --experiment row:ID`" % item])
            live_row = candidates[0]
            value["row"] = row_id(live_row["id"])
            value.pop("creating")
        planned = {"as": held["as"], "of": held.get("of"), "since": held["since"], "row": value.get("row")}
        if live_row is None:
            _schema(live, target, list(PROPERTIES[target]))
            title = next(iter(PROPERTIES[target]))
            properties = {title: row["title"], **{name: given for name, given in values.items() if given is not None}}
            if target == "experiments":
                properties["Stage"] = stage_value(row["kind"], row["status"])
            elif priority_value(row["priority"]) is not None:
                properties["Priority"] = priority_value(row["priority"])
            value["creating"] = {"generation": fresh["fingerprint"], "database": database, "designation": planned,
                                 "target": target}
            writes = dict(values)
            result = {"action": "create", "database": database, "properties": properties,
                      "body": POINTER.format(item=item)}
        else:
            _schema(live, target, OWNED[target])
            unconfirmed = (held.get("writing") or {}).get("values", {})
            written = held.get("written", {})
            writes, yielded = {}, []
            for name in OWNED[target]:
                now_live, last = _empty(live_row["properties"].get(name)), _empty(written.get(name))
                if now_live == last:
                    if now_live != values[name]:
                        writes[name] = values[name]
                    continue
                yielded.append(name)
                if name not in held.get("yielded", []):
                    hand = f"set it to {_shown(last)}" if last is not None else "clear it"
                    own = ("; this may be sd's own unconfirmed write"
                           if name in unconfirmed and _empty(unconfirmed[name]) == now_live else "")
                    add_note(connection, item, "comment",
                             f"{name} on the {target} row is not sd's ({_shown(now_live)}; sd last wrote "
                             f"{_shown(last)}; {hand} to hand it back){own}", session=who)
            value["yielded"] = yielded
            if not yielded:
                value.pop("yielded")
            properties = dict(writes)
            result = {"action": "update", "row": value["row"], "properties": properties, "yielded": yielded}
        value["writing"] = {"generation": fresh["fingerprint"], "designation": planned, "values": writes,
                            "target": target}
        value.pop("confirmed", None)
        _store(connection, item, fields, validate(value))
    return {"item": item, "target": target, "fingerprint": fresh["fingerprint"], **result}
