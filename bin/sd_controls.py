"""Thin provider and report commands; state and validation stay in sd_db."""

from __future__ import annotations

import argparse
import getpass
import inspect
import json
import os
from pathlib import Path
from typing import Any

import sd_handoff_rows
from sd_work import WorkRefusal

#: What the bulk apply records as the acting program, beside the login name
#: `getpass.getuser()` gives as the principal and the name the caller states.
BULK_PROGRAM = "sd reports acknowledge"

#: The flags that belong to `--all-clean`. With an item id each is refused,
#: because the single-item branch would otherwise ignore it: `--who tester`
#: would acknowledge under the login name, which is the defect sd:755 removes.
BULK_FLAGS = ("before", "apply", "if_plan", "who")

#: The flags that belong to an item id, refused with `--all-clean` for the
#: same reason in the other direction: the bulk verb checks a plan, not a
#: revision, and never resolves a followup, so a flag it read and ignored
#: would let the caller believe it did.
ITEM_FLAGS = ("if_revision", "resolve_ingest_followups")


def bulk_cutoff(args: argparse.Namespace, reporting: Any) -> str | None:
    """The stamped cutoff of a bulk acknowledge, or None for the single-item verb.

    Every refusal here fires before the store is opened, so a refused call
    can write nothing. The caller gives exactly one of an item id and
    `--all-clean`; the item flags do not go with `--all-clean` and the bulk
    flags do not go with an item id; the bulk form needs `--before`; an apply
    needs both the plan and a stated name (design D4), and neither belongs
    without `--apply`.
    The date goes through `reporting.cutoff`, so the value passed on is the
    one stamp both surfaces write, and a bad one is the helper's refusal.
    """
    if args.control_action != "acknowledge":
        return None
    given = [f"--{flag.replace('_', '-')}" for flag in BULK_FLAGS if getattr(args, flag) not in (None, False)]
    if (args.item is None) == (not args.all_clean):
        raise WorkRefusal("give exactly one of an item id and --all-clean")
    if args.item is not None:
        if given:
            raise WorkRefusal(f"{', '.join(given)}: only with --all-clean, not with an item id")
        return None
    stray = [f"--{flag.replace('_', '-')}" for flag in ITEM_FLAGS if getattr(args, flag) not in (None, False)]
    if stray:
        raise WorkRefusal(f"{', '.join(stray)}: only with an item id, not with --all-clean")
    if args.before is None:
        raise WorkRefusal("--all-clean needs --before DATE")
    if args.apply and (args.if_plan is None or args.who is None):
        raise WorkRefusal("--apply needs --if-plan TOKEN from the dry run and --who NAME")
    if not args.apply and (args.if_plan is not None or args.who is not None):
        raise WorkRefusal("--if-plan and --who go with --apply; leave both off for the dry run")
    return reporting.cutoff(args.before)


def bulk_preview(result: dict[str, Any]) -> str:
    """The dry run for a person: the rows, then the apply command to paste.

    The last line is the exact apply, with the stamped `before` and the plan
    filled in and `--who NAME` left for the caller. With no plan there is no
    apply that could succeed, and the last line says so instead.
    """
    lines = [f"clean reports before {result['before']}: {result['count']} selected, "
             f"{result['declined_count']} declined"]
    lines += [f"  selected #{row['id']}  {row['created_at']}  {row['title']}" for row in result["selected"]]
    lines += [f"  declined #{row['id']}: {row['why']}" for row in result["declined"]]
    if result["plan"] is None:
        lines.append(f"no apply: a bulk acknowledge moves between 1 and {result['max_batch']} reports")
    else:
        lines.append(f"sd reports acknowledge --all-clean --before {result['before']} --apply "
                     f"--if-plan {result['plan']} --who NAME")
    return "\n".join(lines)


def acknowledge_reports(args: argparse.Namespace, connection: Any, reporting: Any, workflow: Any) -> dict[str, Any]:
    if args.all_clean:
        if args.apply:
            return reporting.acknowledge_clean(connection, before=args.before, expected_plan=args.if_plan,
                                               who=args.who, principal=getpass.getuser(), program=BULK_PROGRAM,
                                               session=os.environ.get("SD_SESSION"))
        return reporting.clean_reports(connection, before=args.before)
    revision = args.if_revision or workflow.item_state(connection, args.item)["revision"]
    # The keyword is passed only when the flag is on, so a library
    # from before system #394 still serves the plain verb. With the
    # flag on, that library would raise TypeError from inside the
    # call; the signature is read first so the refusal names the
    # remedy instead.
    keywords: dict[str, bool] = {}
    if args.resolve_ingest_followups:
        if "resolve_ingest_followups" not in inspect.signature(reporting.acknowledge).parameters:
            raise WorkRefusal("the installed sd_db takes no --resolve-ingest-followups; "
                              "run bin/sd_install.py --provision-library")
        keywords["resolve_ingest_followups"] = True
    return reporting.acknowledge(connection, args.item, expected_revision=revision, who=getpass.getuser(),
                                 **keywords)


def run(args: argparse.Namespace) -> int:
    sd_db = sd_handoff_rows.library()
    try:
        from sd_db import provider_controls, reporting, workflow
    except ImportError:
        raise WorkRefusal("install the current shared library for provider and report controls") from None
    try:
        before = bulk_cutoff(args, reporting)
    except sd_db.SdDbError as error:
        raise WorkRefusal(str(error)) from error
    if before is not None:
        args.before = before
    # The bulk dry run reads the way `list` does: `write=False` opens SQLite
    # with `mode=ro` and `query_only`, so nothing it does can write.
    connection = sd_handoff_rows.connect(sd_db, write=args.control_action != "list"
                                         and not (before is not None and not args.apply))
    try:
        if args.control_group == "providers":
            if args.control_action == "list":
                result = provider_controls.snapshot(connection)
            else:
                source = Path(args.file)
                if source.stat().st_size > 65536:
                    raise ValueError("provider proposal exceeds 64 KiB")
                proposal = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(proposal, dict) or set(proposal) != {"revision", "enabled", "orders"}:
                    raise ValueError("provider proposal needs revision, enabled flags and both role orders")
                result = provider_controls.configure(connection, enabled=proposal["enabled"], orders=proposal["orders"],
                    expected_revision=proposal["revision"], who=getpass.getuser())
        elif args.control_action == "list":
            result = reporting.reports(connection)
        elif args.control_action == "acknowledge":
            result = acknowledge_reports(args, connection, reporting, workflow)
            if before is not None and not args.apply and not args.json:
                print(bulk_preview(result))
                return 0
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
                command.add_argument("item", type=int, nargs="?")
                command.add_argument("--if-revision")
                command.add_argument("--all-clean", action="store_true",
                                     help="every clean planning report filed before --before, as retention "
                                          "would settle it: a dry run that writes nothing and prints the plan "
                                          "token; --apply moves exactly that plan or nothing")
                command.add_argument("--before", metavar="DATE",
                                     help="the cutoff, YYYY-MM-DD meaning 00:00 UTC, or that exact stamp")
                command.add_argument("--apply", action="store_true",
                                     help="move the previewed selection; needs --if-plan and --who")
                command.add_argument("--if-plan", metavar="TOKEN", help="the plan the dry run printed")
                command.add_argument("--who", metavar="NAME",
                                     help="the name recorded as acting, beside the login and this program")
                command.add_argument("--resolve-ingest-followups", action="store_true",
                                     help="also resolve the followup the ingest itself wrote for this report "
                                          "(session cron, the text derived from the report's own fields), in "
                                          "the same transaction; a followup a person wrote still blocks, and "
                                          "the refusal names `sd note resolve <id>` for each")
            if action == "ingest":
                command.add_argument("job")
                for option in ("run-id", "started", "ended", "log"):
                    command.add_argument("--" + option, required=True)
                command.add_argument("--exit-code", type=int, required=True)
                command.add_argument("--offset", type=int, default=0)
