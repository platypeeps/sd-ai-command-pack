"""Task controls and workspace reads, backed by the dashboard's operations.

These verbs do not need a checkout. ``--here`` explicitly associates a new
task with the registered repository containing the current directory.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import pathlib
import stat
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


#: What `register` calls that a build predating it does not carry, as
#: `(module suffix, attribute)`.
#:
#: The import above cannot stand in for this. `sd_db.workflow` has existed for
#: a long time and imports cleanly on every build; `register_work_item` is new
#: inside it. Checking only that the module arrived would turn a stale library
#: into an `AttributeError` raised from the middle of an open write
#: transaction -- a traceback, at the one moment this file is careful never to
#: produce one. Named, both of them, so the remedy is a sentence rather than a
#: stack.
REGISTER_NEEDS = (("workflow", "register_work_item"), ("repos", "registered_for"))


def _register_library(sd_db):
    """The two modules `register` writes through, or a refusal naming the gap."""

    import importlib  # noqa: PLC0415 - only this verb needs it

    found = {}
    missing = []
    for module_name, attribute in REGISTER_NEEDS:
        try:
            module = importlib.import_module(f"sd_db.{module_name}")
        except ImportError:
            missing.append(f"sd_db.{module_name}")
            continue
        if not hasattr(module, attribute):
            missing.append(f"sd_db.{module_name}.{attribute}")
            continue
        found[module_name] = module
    if missing:
        raise WorkRefusal(
            "the installed sd_db cannot register work items; it is missing "
            + ", ".join(missing)
            + ". Install the current system/local-sd-db build with the pack's "
            "installer (`sd-install`), which provisions it from the `system` "
            "checkout at its tag, then run this again."
        )
    return found["workflow"], found["repos"]


def _frontmatter(prd: pathlib.Path) -> tuple[str, str]:
    """`title:` and `created:`, or a refusal naming the file and what it lacks."""

    try:
        from sd_db.sources.frontmatter import FrontmatterError  # noqa: PLC0415
        from sd_db.sources.frontmatter import read as read_frontmatter  # noqa: PLC0415
    except ImportError as error:
        raise WorkRefusal(
            "the installed sd_db cannot read work-item frontmatter; install "
            "the current system/local-sd-db build"
        ) from error
    try:
        front, _ = read_frontmatter(prd.read_text(encoding="utf-8"))
    except (FrontmatterError, OSError, UnicodeError) as failure:
        raise WorkRefusal(f"{prd}: {failure}") from failure
    title, created = front.get("title"), front.get("created")
    if not title or not created:
        raise WorkRefusal(
            f"{prd} needs `title:` and `created:` in its frontmatter; "
            "the row takes its name and its date from the file, not from you")
    return str(title), str(created)


def _register(sd_db, connection, args, who: str) -> Any:
    """Make the row that owns a `docs/work` folder already on disk.

    The folder is the input and git is the rest of it: the title and date come
    from the frontmatter, the branch and commit from the checkout, and the
    status is always `planning`, because an item nobody has started is what a
    new folder is. Nothing here decides anything, which is why it takes no
    flags beyond the path.

    There is no repository argument, for the reason `sd-status` has none
    (R10-D6): the repository is the one enclosing the working directory. A row
    whose path resolved against a checkout the caller was not standing in
    would name a file nobody can read.
    """

    workflow, repos = _register_library(sd_db)
    root = sd_lib.repo_root()
    if root is None:
        raise WorkRefusal("register requires a Git checkout")
    prd = (root / args.path).resolve()
    try:
        relative = prd.relative_to(root).as_posix()
    except ValueError:
        raise WorkRefusal(f"{args.path} is outside {root}") from None
    if not prd.is_file():
        raise WorkRefusal(f"no file at {prd}")
    title, created = _frontmatter(prd)
    # The repository this checkout *is*, not the directory it sits in. A
    # runner clone carries the same files at another path, and resolving by
    # path alone refuses every run made from one.
    origin = sd_lib.git_output(["remote", "get-url", "origin"], root)
    repo = repos.registered_for(connection, str(root), origin or None)
    commit = sd_lib.git_output(
        ["log", "-1", "--format=%H", "--", relative], root)
    return workflow.register_work_item(
        connection, repo=repo, path=relative, title=title, created_at=created,
        branch=sd_lib.git_output(["rev-parse", "--abbrev-ref", "HEAD"], root),
        source_commit=commit or None, who=who,
    )


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
        # `register` is the one verb that can do nothing and still succeed.
        # Registering twice is deliberately not an error -- the unique index
        # makes the second call safe -- but a caller who cannot tell the two
        # apart will read "here is the row" as "I just made it".
        if value.get("created") is False:
            print("already registered; nothing changed")
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
        elif action == "register":
            result = _register(sd_db, connection, args, who)
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


def _contribution_library():
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.contributions as contributions
    except ImportError as error:
        raise WorkRefusal(
            "the installed sd_db lacks contribution controls; install the current "
            "system/local-sd-db build"
        ) from error
    return sd_db, contributions


def _contribution_changes(path: str) -> dict[str, Any]:
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON number: {value}")

    try:
        # Nonblocking open also makes FIFO input refuse instead of waiting for a writer.
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("input must be a regular file")
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError("input exceeds 65536 bytes")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        return value
    except (OSError, ValueError, RecursionError) as error:
        raise WorkRefusal(f"contribution input refused: {error}") from error


def _emit_contributions(value: Any, *, machine: bool) -> None:
    if machine:
        print(json.dumps(value, ensure_ascii=False))
        return
    if isinstance(value, dict) and "item" in value:
        _emit(value, machine=False)
        print(f"contribution: item:{value['item']['id']}")
        return
    rows = value if isinstance(value, list) else [value.get("contribution")]
    for row in rows:
        if row is None:
            continue
        print(f"{row['key']}  {row['lane']}  {row['title']}")
        print(f"  local: {row.get('local_status')} · external: {row.get('external_state')}"
              f" · freshness: {row.get('freshness')}")
        print(f"  evidence_verified: {json.dumps(row.get('evidence_verified', False))}")
        for field in ("url", "local_clone", "local_branch", "tested_commit", "blocked_on", "depends_on",
                      "evidence", "reasons", "event_ids", "attention_sources"):
            if row.get(field):
                print(f"  {field}: {json.dumps(row[field], ensure_ascii=False)}")
    if not rows:
        print("No contributions.")
    if isinstance(value, dict):
        print(f"key: {value['key']}")
        for field in ("attention", "notifications"):
            print(f"{field}: {json.dumps(value.get(field), ensure_ascii=False)}")
        print(f"revision: {value['revision']}")


def run_contribution(args: argparse.Namespace) -> int:
    changes = _contribution_changes(args.file) if args.verb in {"add", "edit"} else None
    sd_db, contributions = _contribution_library()
    connection = None
    try:
        connection = sd_handoff_rows.connect(sd_db, write=args.verb not in {"list", "show"})
        who = getpass.getuser()
        result: Any
        if args.verb == "add":
            result = contributions.capture(connection, title=args.title, changes=changes, who=who)
        elif args.verb == "edit":
            result = contributions.configure(
                connection, args.item, changes, who=who, expected_revision=args.if_revision)
        elif args.verb == "list":
            result = contributions.projection(connection)
        elif args.verb in {"show", "ack"}:
            if args.verb == "show":
                result = contributions.snapshot(connection, args.key)
            else:
                result = contributions.acknowledge(
                    connection, args.key, args.event, who=who, expected_revision=args.if_revision)
            result = {**result, "contribution": next(
                (row for row in contributions.projection(connection)
                 if row["key"] == result["key"] or f"item:{row.get('item_id')}" == result["key"]
                 or any(source["key"] == result["key"] for source in row.get("attention_sources", []))),
                None,
            )}
        else:
            raise WorkRefusal(f"unknown contribution operation: {args.verb}")
        _emit_contributions(result, machine=args.json)
        return 0
    except sd_db.SdDbError as error:
        raise WorkRefusal(str(error)) from error
    finally:
        if connection is not None:
            connection.close()


def _register_contributions(verbs: Any) -> None:
    group = verbs.add_parser("contribution", help="track local work and upstream contribution attention")
    actions = group.add_subparsers(dest="verb", required=True)
    for action in ("add", "edit", "list", "show", "ack"):
        parser = actions.add_parser(action)
        parser.add_argument("--json", action="store_true", help="machine-readable")
        parser.set_defaults(handler=run_contribution)
        if action in {"add", "edit"}:
            parser.add_argument("--file", required=True, help="contribution changes as JSON (maximum 64 KiB)")
            if action == "add":
                parser.add_argument("title")
            else:
                parser.add_argument("item", type=int)
                parser.add_argument("--if-revision", help="item revision from sd store item")
        if action in {"show", "ack"}:
            parser.add_argument("key", help="item:ID or github:https://github.com/OWNER/REPO/pull/NUMBER")
        if action == "ack":
            parser.add_argument("--event", action="append", required=True, help="observed event ID; repeat as needed")
            parser.add_argument("--if-revision", required=True, help="checkpoint revision from contribution show")


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
    _register_contributions(verbs)
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
    register_verb = working.add_parser(
        "register", help="make the row that owns a docs/work folder on disk")
    register_verb.add_argument(
        "path", help="docs/work/<item>/prd.md, relative to the repository")
    _output(register_verb, "register")

    deliver = working.add_parser("deliver", help="verify a delivery commit and complete its item")
    deliver.add_argument("item", type=int)
    deliver.add_argument("commit", help="full commit SHA carrying the item's Delivers trailer")
    _output(deliver, "deliver", revision=True)
