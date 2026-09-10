"""The queue's CLI gateway. Durable lifecycle operations belong to sd_db."""

from __future__ import annotations

import argparse
import getpass
import json

import sd_handoff_rows
import sd_lib
from sd_work import WorkRefusal


def commands(args: argparse.Namespace) -> int:
    sd_handoff_rows.library()
    try:
        from sd_db.runner_palette import main
    except ImportError:
        raise WorkRefusal("install the current system/local-sd-db build for command requests") from None
    try:
        return main(args.palette_args)
    except SystemExit as error:
        return int(error.code or 0)


def service(args):
    sd_db = sd_handoff_rows.library()
    from sd_db import runner, runner_controls
    connection = sd_handoff_rows.connect(sd_db, write=False)
    try:
        current = runner.queue_state(connection, args.assignment)
        revision = getattr(args, "if_revision", None) or current["revision"]
        historical = getattr(args, "run", None)
        if historical is None:
            result = runner_controls.control(connection, args.assignment, args.runner_action,
                expected_revision=revision, destination=getattr(args, "destination", None))
        else:
            selected = runner.attempt(connection, args.assignment, historical)
            database = sd_db.database.default_path()
            installation = runner_controls.service_installation(database=database)
            result = runner_controls.invoke_service(installation, args.runner_action, args.assignment,
                revision=revision, run=selected["id"], destination=args.destination, historical_run=historical)
        print(json.dumps(result, indent=2))
        return 0
    except (sd_db.SdDbError, OSError, ValueError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def run(args: argparse.Namespace) -> int:
    sd_db = sd_handoff_rows.library()
    try:
        from sd_db import runner
    except ImportError:
        raise WorkRefusal("install the current system/local-sd-db build for runner controls") from None
    connection = sd_handoff_rows.connect(sd_db, write=args.runner_action not in {"status", "get", "list"})
    try:
        action = args.runner_action
        result: list[dict] | dict
        if action == "enqueue":
            result = runner.enqueue(connection, args.items, parallel=args.parallel, role=args.role,
                                    scope=args.scope, budget_minutes=args.budget_minutes, who=getpass.getuser())
        elif action == "status":
            result = runner.heartbeat_state(connection)
        elif action == "list":
            result = {"queued": runner.queued(connection), "active": runner.active_runs(connection)}
        elif action == "get":
            result = runner.queue_state(connection, args.assignment)
        elif action == "prepare":
            from sd_db.runner_controls import configure_item
            from sd_db.workflow import item_state
            root = sd_lib.repo_root()
            if root is None:
                raise WorkRefusal("runner prepare requires a Git checkout")
            current = item_state(connection, args.item)
            result = configure_item(connection, args.item, repo=str(root), branch=args.branch,
                                    expected_revision=args.if_revision or current["revision"], who=getpass.getuser())
        else:
            state = runner.queue_state(connection, args.assignment)
            if action == "cancel" and state["status"] == "running":
                args.if_revision = args.if_revision or state["revision"]
                return service(args)
            operation = runner.request_cancel if action == "cancel" else runner.requeue
            result = operation(connection, args.assignment, expected_revision=args.if_revision or state["revision"], who=getpass.getuser())
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
        return 1 if isinstance(result, dict) and result.get("ok") is False else 0
    except (sd_db.SdDbError, ValueError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def register(groups) -> None:
    create = groups.add_parser("run", help="queue isolated assignments for selected database items")
    lanes = create.add_mutually_exclusive_group(required=True)
    lanes.add_argument("--sequential", action="store_true")
    lanes.add_argument("--parallel", action="store_true")
    create.add_argument("items", type=int, nargs="+")
    create.add_argument("--role", choices=("author", "reviewer", "exec"), default="author")
    create.add_argument("--scope", default="item")
    create.add_argument("--budget-minutes", type=int, default=90)
    create.add_argument("--json", action="store_true")
    create.set_defaults(handler=run, runner_action="enqueue")
    group = groups.add_parser("runner", help="inspect the queue and control owned assignments")
    verbs = group.add_subparsers(dest="verb", required=True)
    palette = verbs.add_parser("commands", add_help=False, help="registered command requests and execution evidence")
    palette.add_argument("palette_args", nargs=argparse.REMAINDER)
    palette.set_defaults(handler=commands)
    prepare = verbs.add_parser("prepare", help="prepare an item branch in the current repository")
    prepare.add_argument("item", type=int)
    prepare.add_argument("--branch", required=True)
    prepare.add_argument("--if-revision")
    prepare.add_argument("--json", action="store_true")
    prepare.set_defaults(handler=run, runner_action="prepare")
    for action in ("status", "list", "get", "cancel", "requeue"):
        command = verbs.add_parser(action)
        command.add_argument("--json", action="store_true")
        command.set_defaults(handler=run, runner_action=action)
        if action in {"get", "cancel", "requeue"}:
            command.add_argument("assignment", type=int)
        if action in {"cancel", "requeue"}:
            command.add_argument("--if-revision")
    worktree = groups.add_parser("worktree", help="recover or resume a preserved runner clone")
    actions = worktree.add_subparsers(dest="verb", required=True)
    for action in ("restore", "resume"):
        command = actions.add_parser(action)
        command.add_argument("assignment", type=int)
        command.set_defaults(handler=service, runner_action=action)
        if action == "restore":
            command.add_argument("--run", type=int)
            command.add_argument("--destination", required=True)
        command.add_argument("--if-revision")
