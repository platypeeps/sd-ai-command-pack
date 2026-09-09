"""Task controls and workspace reads, backed by the dashboard's operations.

These verbs do not need a checkout. ``--here`` explicitly associates a new
task with the registered repository containing the current directory.
"""

from __future__ import annotations

import argparse
import getpass
import json
from typing import Any

import sd_handoff_rows
import sd_lib


class WorkRefusal(Exception):
    """A workflow operation was refused without changing its state."""


def _library():
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.workflow as workflow
    except ImportError as error:
        raise WorkRefusal(
            "the installed sd_db lacks workflow controls; install the current "
            "system/local-sd-db build"
        ) from error
    return sd_db, workflow


def _emit(value: Any, *, machine: bool) -> None:
    if machine:
        print(json.dumps(value, ensure_ascii=False))
        return
    rows = value if isinstance(value, list) else [value["item"]]
    if not rows:
        print("No items.")
    for row in rows:
        priority = f" · P{row['priority']}" if row.get("priority") else ""
        due = f" · due {row['due']}" if row.get("due") else ""
        print(f"#{row['id']}  {row['status']}  {row['title']}{priority}{due}")
    if isinstance(value, dict):
        for note in value.get("notes", []):
            resolved = " · resolved" if note.get("resolved_at") else ""
            print(f"  note #{note['id']} · {note['kind']}{resolved}: {note['body']}")
        print(f"revision: {value['revision']}")


def run(args: argparse.Namespace) -> int:
    sd_db, workflow = _library()
    write = args.work_action not in {"today", "items", "item"}
    connection = sd_handoff_rows.connect(sd_db, write=write)
    try:
        action = args.work_action
        who = getpass.getuser()
        revision = getattr(args, "if_revision", None)
        result: Any
        if action == "today":
            result = [dict(row) for row in sd_db.reads.today_items(connection)]
        elif action == "items":
            result = [dict(row) for row in sd_db.reads.backlog_items(connection)]
            result = [row for row in result
                      if (not args.open or row["status"] != "done")
                      and (not args.kind or row["kind"] == args.kind)
                      and (not args.status or row["status"] == args.status)]
        elif action == "item":
            result = workflow.item_state(connection, args.item)
        elif action == "add":
            repo = None
            if args.here:
                root = sd_lib.repo_root()
                if root is None:
                    raise WorkRefusal("--here requires a Git checkout")
                repo = str(root.resolve())
            result = workflow.capture_task(
                connection, title=args.title, body=args.body, priority=args.priority,
                due=args.due, repo=repo, who=who,
            )
        elif action == "edit":
            changes = {field: getattr(args, field) for field in
                       ("title", "body", "priority", "due")
                       if getattr(args, field) is not None}
            if args.clear_priority:
                changes["priority"] = None
            if args.clear_due:
                changes["due"] = None
            if not changes:
                raise WorkRefusal("edit requires a field to change")
            result = workflow.edit_item(
                connection, args.item, changes, who=who, expected_revision=revision)
        elif action == "status":
            result = workflow.change_status(
                connection, args.item, args.status, who=who,
                expected_revision=revision, reason=args.reason)
        elif action == "note":
            result = workflow.add_item_note(
                connection, args.item, body=args.body, kind=args.kind, who=who,
                expected_revision=revision)
        elif action == "resolve":
            result = workflow.resolve_item_note(
                connection, args.note, who=who, expected_revision=revision)
        elif action in {"relink", "cancel", "deliver"}:
            import sd_db.progress as progress

            if action == "relink":
                result = progress.relink_artifact(
                    connection, args.item, args.path, who=who, expected_revision=revision)
            elif action == "cancel":
                result = progress.cancel_work(
                    connection, args.item, reason=args.reason, who=who,
                    expected_revision=revision)
            else:
                result = progress.deliver_work(
                    connection, args.item, args.commit, who=who,
                    expected_revision=revision)
        else:
            raise WorkRefusal(f"unknown workflow operation: {action}")
        _emit(result, machine=args.json)
        return 0
    except sd_db.SdDbError as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def _output(parser: argparse.ArgumentParser, action: str, *, revision: bool = False) -> None:
    parser.add_argument("--json", action="store_true", help="machine-readable")
    if revision:
        parser.add_argument("--if-revision", help="refuse if the item changed since this revision")
    parser.set_defaults(handler=run, work_action=action)


def register(groups: Any, store: Any) -> None:
    """Extend the existing parser, preserving the plugin note-store verbs."""
    today = groups.add_parser("today", help="due and active work, in dashboard order")
    _output(today, "today")

    items = store.add_parser("items", help="workspace items from the shared database")
    items.add_argument("--open", action="store_true", help="exclude done items")
    items.add_argument("--kind", help="filter by item kind")
    items.add_argument("--status", help="filter by workflow status")
    _output(items, "items")
    item = store.add_parser("item", help="one workspace item, notes, and revision")
    item.add_argument("item", type=int)
    _output(item, "item")

    task = groups.add_parser("task", help="capture and manage work without files or GitHub")
    verbs = task.add_subparsers(dest="verb", required=True)
    add = verbs.add_parser("add", help="capture a standalone task")
    add.add_argument("title")
    add.add_argument("--body", default="")
    add.add_argument("--priority", type=int, choices=range(1, 5))
    add.add_argument("--due", help="YYYY-MM-DD")
    add.add_argument("--here", action="store_true", help="associate with this registered checkout")
    _output(add, "add")

    edit = verbs.add_parser("edit", help="change a task's details")
    edit.add_argument("item", type=int)
    edit.add_argument("--title")
    edit.add_argument("--body")
    priority = edit.add_mutually_exclusive_group()
    priority.add_argument("--priority", type=int, choices=range(1, 5))
    priority.add_argument("--clear-priority", action="store_true")
    due = edit.add_mutually_exclusive_group()
    due.add_argument("--due", help="YYYY-MM-DD")
    due.add_argument("--clear-due", action="store_true")
    _output(edit, "edit", revision=True)

    status = verbs.add_parser("status", help="change status with an atomic history entry")
    status.add_argument("item", type=int)
    status.add_argument("status")
    status.add_argument("--reason")
    _output(status, "status", revision=True)

    note = verbs.add_parser("note", help="add an item note or follow-up")
    note.add_argument("item", type=int)
    note.add_argument("--body", required=True)
    note.add_argument("--kind", default="comment",
                      choices=("comment", "followup", "question", "decision", "proposal"),
                      help="note kind (default: comment)")
    _output(note, "note", revision=True)
    resolve = verbs.add_parser("resolve", help="resolve an item note")
    resolve.add_argument("note", type=int)
    _output(resolve, "resolve", revision=True)

    work = groups.add_parser("work", help="maintain artifact links and verified completion")
    working = work.add_subparsers(dest="verb", required=True)
    relink = working.add_parser("relink", help="link a moved artifact without changing item identity")
    relink.add_argument("item", type=int)
    relink.add_argument("path", help="existing artifact path relative to the item's repository")
    _output(relink, "relink", revision=True)
    cancel = working.add_parser("cancel", help="record a deliberate cancellation, with a reason")
    cancel.add_argument("item", type=int)
    cancel.add_argument("--reason", required=True)
    _output(cancel, "cancel", revision=True)
    deliver = working.add_parser("deliver", help="verify a delivery commit and complete its item")
    deliver.add_argument("item", type=int)
    deliver.add_argument("commit", help="full commit SHA carrying the item's Delivers trailer")
    _output(deliver, "deliver", revision=True)
