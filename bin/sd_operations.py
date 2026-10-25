"""Observe jobs, services and assignments, and request supported operations."""

from __future__ import annotations

import argparse
import getpass
import json
from typing import Any

import sd_handoff_rows
from sd_notes import ITEM_HELP, item_id
from sd_work import WorkRefusal


def service_result(connection: Any, args: argparse.Namespace) -> Any:
    try:
        import sd_db.services as services
    except ImportError:
        raise WorkRefusal("update this pack checkout, whose lib/ is the sd_db bin/ runs for service controls") from None
    if args.operation == "list":
        return services.inventory(connection)["services"]
    state = services.service_state(connection, args.identity)
    if args.operation == "get":
        return state
    operation = {"start": services.start_service, "stop": services.stop_service,
                 "restart": services.restart_service}[args.operation]
    return operation(connection, args.identity,
                     expected_revision=args.if_revision or state["revision"],
                     who=getpass.getuser())


def run(args: argparse.Namespace) -> int:
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.operations as operations
    except ImportError:
        raise WorkRefusal("update this pack checkout, whose lib/ is the sd_db bin/ runs for job controls") from None
    write = args.operation in {"retry", "cancel", "start", "stop", "restart"}
    connection = sd_handoff_rows.connect(sd_db, write=write)
    try:
        result: Any
        jobs = args.operation_group == "jobs"
        if args.operation_group == "services":
            result = service_result(connection, args)
        elif args.operation == "list":
            result = operations.inventory(connection)[args.operation_group]
        else:
            state = (operations.job_state(connection, args.identity) if jobs
                     else operations.assignment_state(connection, int(args.identity)))
            if args.operation == "get":
                result = state
            else:
                revision = args.if_revision or state["revision"]
                if jobs:
                    operation = operations.retry_job if args.operation == "retry" else operations.cancel_job
                    result = operation(connection, args.identity, expected_revision=revision,
                                       who=getpass.getuser())
                else:
                    result = operations.cancel_assignment(connection, int(args.identity),
                                                          expected_revision=revision, who=getpass.getuser())
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        elif isinstance(result, list):
            if not result:
                print(f"No {args.operation_group}.")
            for entry in result:
                if args.operation_group == "services":
                    print(f"{entry['id']}  {entry['state']}")
                elif jobs:
                    print(f"{entry['name']}  {entry['state']}")
                else:
                    print(f"#{entry['id']}  {entry['status']}  {entry['role']}  {entry['title']}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if isinstance(result, dict) and result.get("request", {}).get("status") in {"failed", "unknown"} else 0
    except (sd_db.SdDbError, ValueError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def queue_builds(args: argparse.Namespace) -> int:
    """`sd assignments build`: the Build press, one queued build assignment per item (pack sd:6093)."""
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.build as build
    except ImportError:
        raise WorkRefusal("update this pack checkout, whose lib/ is the sd_db bin/ runs for builds") from None
    connection = sd_handoff_rows.connect(sd_db, write=True)
    try:
        queued = build.queue(connection, args.items, who=getpass.getuser())
    except (sd_db.SdDbError, ValueError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()
    if args.json:
        print(json.dumps(queued, ensure_ascii=False))
    for entry in [] if args.json else queued:
        print(f"#{entry['id']}  {entry['status']}  build  sd:{entry['item']}")
    return 0


def register(groups: Any) -> None:
    for name in ("jobs", "assignments", "services"):
        group = groups.add_parser(name, help=f"inspect {name} and request supported controls")
        verbs = group.add_subparsers(dest="verb", required=True)
        actions = {"jobs": ("list", "get", "retry", "cancel"),
                   "assignments": ("list", "get", "cancel"),
                   "services": ("list", "get", "start", "stop", "restart")}[name]
        for action in actions:
            parser = verbs.add_parser(action)
            parser.set_defaults(handler=run, operation_group=name, operation=action)
            parser.add_argument("--json", action="store_true")
            if action != "list":
                parser.add_argument("identity", help={"jobs": "registered job name",
                    "assignments": "assignment ID", "services": "launchd label (get also accepts system:LABEL)"}[name])
            if action in {"retry", "cancel", "start", "stop", "restart"}:
                parser.add_argument("--if-revision", help="require the exact revision you inspected")
        if name == "assignments":
            parser = verbs.add_parser("build", help="queue a build of each ready item; the whole selection or none")
            parser.set_defaults(handler=queue_builds)
            parser.add_argument("items", nargs="+", type=item_id, help=ITEM_HELP)
            parser.add_argument("--json", action="store_true")
