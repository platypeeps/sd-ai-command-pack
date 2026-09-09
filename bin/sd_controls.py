"""Thin provider and report commands; state and validation stay in sd_db."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from typing import Any

import sd_handoff_rows
from sd_work import WorkRefusal


def run(args: argparse.Namespace) -> int:
    sd_db = sd_handoff_rows.library()
    try:
        from sd_db import provider_controls, reporting, workflow
    except ImportError:
        raise WorkRefusal("install the current shared library for provider and report controls") from None
    connection = sd_handoff_rows.connect(sd_db, write=args.control_action != "list")
    try:
        if args.control_group == "providers":
            if args.control_action == "list":
                result = provider_controls.snapshot(connection)
            else:
                source = Path(args.file)
                if source.stat().st_size > 65536:
                    raise ValueError("provider proposal exceeds 64 KiB")
                proposal = json.loads(source.read_text())
                if not isinstance(proposal, dict) or set(proposal) != {"revision", "enabled", "orders"}:
                    raise ValueError("provider proposal needs revision, enabled flags and both role orders")
                result = provider_controls.configure(connection, enabled=proposal["enabled"], orders=proposal["orders"],
                    expected_revision=proposal["revision"], who=getpass.getuser())
        elif args.control_action == "list":
            result = reporting.reports(connection)
        elif args.control_action == "acknowledge":
            revision = args.if_revision or workflow.item_state(connection, args.item)["revision"]
            result = reporting.acknowledge(connection, args.item, expected_revision=revision, who=getpass.getuser())
        else:
            result = reporting.ingest_log(connection, job=args.job, run_id=args.run_id, started=args.started,
                ended=args.ended, exit_code=args.exit_code, log_path=args.log, offset=args.offset)
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
        return 0
    except (sd_db.SdDbError, ValueError, KeyError, OSError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def register(groups: Any) -> None:
    for name in ("providers", "reports"):
        group = groups.add_parser(name, help=f"inspect and control {name} through the workflow database")
        verbs = group.add_subparsers(dest="verb", required=True)
        for action in (("list", "configure") if name == "providers" else ("list", "ingest", "acknowledge")):
            command = verbs.add_parser(action)
            command.set_defaults(handler=run, control_group=name, control_action=action)
            command.add_argument("--json", action="store_true")
            if action == "configure":
                command.add_argument("--file", required=True, help="JSON containing revision, enabled flags and both role orders")
            if action == "acknowledge":
                command.add_argument("item", type=int)
                command.add_argument("--if-revision")
            if action == "ingest":
                command.add_argument("job")
                for option in ("run-id", "started", "ended", "log"):
                    command.add_argument("--" + option, required=True)
                command.add_argument("--exit-code", type=int, required=True)
                command.add_argument("--offset", type=int, default=0)
