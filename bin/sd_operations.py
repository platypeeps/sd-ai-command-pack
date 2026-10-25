"""Observe jobs, services and assignments, and request supported operations."""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import subprocess
import sys
from pathlib import Path
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


BIN = Path(__file__).resolve().parent
GATE_SECONDS = 15


def build_modules() -> tuple[Any, Any, Any]:
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.build as build
        import sd_db.build_run as build_run
    except ImportError:
        raise WorkRefusal("update this pack checkout, whose lib/ is the sd_db bin/ runs for builds") from None
    return sd_db, build, build_run


def log_root() -> Path | None:
    """`sd.bulk_storage_root`, where each run's logs go as `<root>/<repository>/build/`; None when unset."""
    import sd_lib
    value = sd_lib.core_setting("bulk_storage_root")
    return Path(os.path.expanduser(value)) if value else None


def gate_load() -> tuple[float | None, float | None]:
    """The five-minute load and its cap from `sd gate status --json`; (None, None) when unread."""
    try:
        done = subprocess.run([sys.executable, str(BIN / "sd"), "gate", "status", "--json"], capture_output=True,
                              text=True, timeout=GATE_SECONDS, check=False, stdin=subprocess.DEVNULL)
        answer = json.loads(done.stdout) if done.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None, None
    load, cap = (answer.get("load"), answer.get("load_max")) if isinstance(answer, dict) else (None, None)
    if not (isinstance(load, list) and len(load) >= 2 and isinstance(load[1], (int, float)) and math.isfinite(load[1])
            and isinstance(cap, (int, float)) and math.isfinite(cap)):
        return None, None
    return float(load[1]), float(cap)


def interactive_builders(connection: Any, now: str, key: Any) -> list[dict] | None:
    """One `{repo, session_id}` per interactive builder, as the dashboard counts them; None when not counted.

    `repo` is the registered repository the session's cwd lies in, else None
    (it counts against the machine only).
    """
    sys.path.insert(0, str(BIN.parent / "dashboard"))
    try:
        from sd_dashboard import claude_sessions
        document = claude_sessions.document(connection, now=now)
        if document["builders"]["running"] is None:
            return None
        repos = [row["path"] for row in connection.execute("SELECT path FROM repo")]
        found = []
        for session in document["sessions"] or []:
            count = sum(1 for agent in session["agents"] if agent["builder"] and agent["state"] != "idle")
            count += 1 if session["builder"] and session["status"] != "idle" else 0
            cwd = key(str(Path(session["cwd"]).resolve())) if session.get("cwd") else ""
            repo = next((path for path in repos if cwd and (cwd == path or cwd.startswith(path.rstrip("/") + "/"))),
                        None)
            found += [{"repo": repo, "session_id": session["id"]}] * count
        return found
    except Exception:  # noqa: BLE001 -- any failure is "not counted", which claims nothing
        return None
    finally:
        sys.path.remove(str(BIN.parent / "dashboard"))


def tools(build_run: Any) -> Any:
    return build_run.Tools(claude=["claude"], review=[str(BIN / "sd-review")], ship=[str(BIN / "sd-ship")],
                           lint=[str(BIN / "sd-docs-lint")])


def dispatch_builds(args: argparse.Namespace) -> int:
    """`sd assignments dispatch`: one build-dispatch tick (pack sd:6094)."""
    import sd_lib
    sd_db, build, build_run = build_modules()
    why = ""
    try:
        root = log_root()
    except sd_lib.ConfigError as error:  # a malformed setting is unread: no claim, but the reap and watch run
        root, why = None, f"{error}, so a build run has no log folder"
    if root is None and not why:
        why = "sd.bulk_storage_root is unset, so a build run has no log folder"
    elif root is not None and not (root.is_dir() and os.access(root, os.W_OK)):
        why = f"the log folder {root} is not writable"
    load, load_cap = gate_load()
    connection = sd_handoff_rows.connect(sd_db, write=True)
    try:
        def spawn(ident: str) -> None:
            if root is None:
                return
            repo = build.run(connection, ident)["repo"]
            build_run.spawn([sys.executable, str(BIN / "sd"), "assignments", "supervise", ident],
                            log=build_run.log_dir(root, repo) / f"{ident}.supervisor.log")

        def lane(row: dict, item: int) -> dict | None:
            return build_run.lane_entry(tools(build_run).ship, build_run.paths.expand(row["repo"]), item)

        result = build_run.dispatch(connection, owner="build-dispatch", load=load, load_cap=load_cap,
                                    interactive=interactive_builders(connection, build_run.now(), build_run.paths.key),
                                    spawn=spawn, lane=lane, why=why)
    except (sd_db.SdDbError, ValueError, OSError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False) if args.json else
          f"reaped {len(result['reaped'])}, moved {len(result['moved'])}, claimed {len(result['claimed'])}, "
          f"spawned {len(result['spawned'])}" + (f"; no claim: {result['why']}" if result["why"] else ""))
    return 0


def supervise_build(args: argparse.Namespace) -> int:
    """`sd assignments supervise RUN`: walk one build run to the lane; the tick starts it in its own session."""
    import sd_lib
    sd_db, _, build_run = build_modules()
    try:
        root = log_root()
    except sd_lib.ConfigError as error:
        raise WorkRefusal(str(error)) from error
    if root is None:
        raise WorkRefusal("sd.bulk_storage_root is unset, so a build run has no log folder")
    connection = sd_handoff_rows.connect(sd_db, write=True)
    try:
        result = build_run.Supervisor(connection, args.run, tools=tools(build_run), log_root=root).run()
    except (sd_db.SdDbError, ValueError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()
    print(json.dumps(result, ensure_ascii=False))
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
            parser = verbs.add_parser("dispatch", help="one build-dispatch tick: reap, watch the lane, claim, spawn")
            parser.set_defaults(handler=dispatch_builds)
            parser.add_argument("--json", action="store_true")
            parser = verbs.add_parser("supervise", help="supervise one build run to the lane; the tick starts it")
            parser.set_defaults(handler=supervise_build)
            parser.add_argument("run", help="the build run id")
