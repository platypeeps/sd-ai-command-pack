"""`sd note list <item>` and `sd note resolve <id>`: the note verbs other surfaces name.

`sd_db.brief`'s cut trailer tells a resuming session to run `sd note list
<item>`, and the dashboard's control prints `sd note resolve <id>`. Both are
`bin/sd` verbs, so both have to live where `bin/sd` can import them, and a
suffixless `bin/sd-note` cannot be imported. The handlers are here once;
`bin/sd-note` keeps its own parser, its `add`, and calls these for the other
two, so the two spellings cannot drift.

The module is `sd_notes` and not `sd_note` on purpose: the tests load
`bin/sd-note` under the name `sd_note`, and a module of that name imported
from inside it would be handed the half-executed caller.

`list` prints one item's whole history, every kind, resolved or not, in
`sd_db.item_notes`'s order. It filters nothing, which is what keeps it from
being a second brief.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import sd_handoff_rows

#: SQLite's INTEGER is signed 64-bit. A larger id cannot name a row, and
#: binding one raises `OverflowError` out of the driver, which reached the
#: operator as a traceback.
LARGEST_ID = 2**63 - 1


def item_id(text: str) -> int:
    """An item id as the brief prints it, `sd:234`, or bare, `234`."""
    digits = text[3:] if text.startswith("sd:") else text
    if not digits.isdigit():
        raise argparse.ArgumentTypeError(f"not an item id: {text!r} (expected 234 or sd:234)")
    value = int(digits)
    if value > LARGEST_ID:
        raise argparse.ArgumentTypeError(f"not an item id: {text!r} (larger than any row id)")
    return value


def note_id(text: str) -> int:
    """A note id as `sd-note add` printed it."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a note id: {text!r}") from None
    if abs(value) > LARGEST_ID:
        raise argparse.ArgumentTypeError(f"not a note id: {text!r} (larger than any row id)")
    return value


def note_lines(note) -> list[str]:
    """One note as the brief draws one, plus when it was resolved.

    `sd_db.brief` keeps its line renderer private, so this is the same shape
    and not the same function: kind, id and date in the brackets, the body's
    first line after them and its other lines indented under it.
    """
    head = f"- [{note['kind']} #{note['id']} {str(note['timestamp'])[:10]}"
    if note["resolved_at"]:
        head += f", resolved {str(note['resolved_at'])[:10]}"
    first, _, rest = str(note["body"]).strip().partition("\n")
    return [f"{head}] {first}", *(f"  {line}" for line in rest.splitlines())]


def cmd_resolve(args, out=None, err=None) -> int:
    out = sys.stdout if out is None else out
    sd_db = sd_handoff_rows.library()
    connection = sd_handoff_rows.connect(sd_db, write=True)
    try:
        sd_db.resolve_note(connection, args.note)
    finally:
        connection.close()
    # `resolve_note` is a no-op on an id that is absent or already closed, and
    # says which. Reporting "resolved" either way would be a lie only in the
    # case nobody can act on, so the line names the id and not an outcome.
    print(f"resolved note {args.note}", file=out)
    return 0


def cmd_list(args, out=None, err=None) -> int:
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    sd_db = sd_handoff_rows.library()
    connection = sd_handoff_rows.connect(sd_db)
    try:
        item = sd_db.item_by_id(connection, args.item)
        if item is None:
            print(f"no item sd:{args.item} in the database", file=err)
            return 1
        notes = sd_db.item_notes(connection, args.item)
    finally:
        connection.close()
    title = f"sd:{item['id']} {item['title']} ({item['status']})"
    if not notes:
        print(f"{title}: no notes", file=out)
        return 0
    noun = "note" if len(notes) == 1 else "notes"
    print(f"{title}: {len(notes)} {noun}, oldest first", file=out)
    for note in notes:
        for line in note_lines(note):
            print(line, file=out)
    return 0


def add_verbs(verbs: Any) -> None:
    """`resolve` and `list` on a subparser set, for `bin/sd` and `bin/sd-note` alike."""
    close = verbs.add_parser("resolve", help="close a followup by its id")
    close.add_argument("note", type=note_id, help="the id the write printed")
    close.set_defaults(handler=cmd_resolve)
    listing = verbs.add_parser("list", help="print every note on one item, oldest first")
    listing.add_argument("item", type=item_id, help="the item id, as 234 or sd:234")
    listing.set_defaults(handler=cmd_list)


def register_note_group(groups: Any) -> None:
    group = groups.add_parser("note", help="list an item's notes and resolve one")
    add_verbs(group.add_subparsers(dest="verb", required=True))
