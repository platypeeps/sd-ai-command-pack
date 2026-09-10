"""The writing pack and dashboard share one database workflow."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
from typing import Any

import sd_handoff_rows
import sd_lib
from sd_work import WorkRefusal


def run(args: argparse.Namespace) -> int:
    sd_db = sd_handoff_rows.library()
    try:
        import sd_db.writing as writing
    except ImportError:
        raise WorkRefusal("install the current system/local-sd-db build for writing controls") from None
    root = sd_lib.repo_root()
    if root is None:
        raise WorkRefusal("writing controls require the writing Git checkout as the current directory")
    repo = str(root.resolve())
    action = args.writing_action
    write = action in {"cutover", "recover", "register", "stage", "metadata", "gate", "park",
                       "publication-claim", "publication-dispatch", "publication-receipt", "publication-reconcile", "publication-abandon", "publication-recover"} or (
        action == "import" and args.apply)
    connection = sd_handoff_rows.connect(sd_db, write=write)
    try:
        who = getpass.getuser()
        revision = getattr(args, "if_revision", None)
        result: Any
        if action == "list":
            result = writing.list_pieces(connection, repo, include_parked=args.all)
            if args.status:
                result = [row for row in result if row["stage"] == args.status]
        elif action == "import":
            result = (writing.import_pieces(connection, repo) if args.apply
                      else writing.cutover_preview(connection, repo))
        elif action == "verify":
            result = writing.verify_pieces(connection, repo)
        elif action == "cutover":
            result = writing.cutover_pieces(
                connection, repo, expected_fingerprint=args.expected_digest, who=who)
        elif action == "recover":
            result = writing.recover_cutover(connection, repo, who=who)
        elif action == "register":
            result = writing.import_piece(connection, repo, args.piece, path=args.path, who=who)
        else:
            row = writing.piece_for_key(connection, repo, args.piece)
            if row is None:
                raise WorkRefusal(f"no database piece {args.piece!r}; register or import it first")
            item = row["id"]
            if action.startswith("publication-"):
                from sd_db import publication

                def read_json(path):
                    source = Path(path)
                    if source.stat().st_size > 32 * 1024 * 1024:
                        raise WorkRefusal("publication input exceeds 32 MiB")
                    return json.loads(source.read_text(encoding="utf-8"))

                context = read_json(args.context_file) if getattr(args, "context_file", None) else None
                if action == "publication-render":
                    result = publication.render_payload(connection, item)
                elif action == "publication-recover":
                    result = publication.recover_journal(connection, item, repair_incomplete=args.repair_incomplete, who=who)
                elif action == "publication-claim":
                    result = publication.create_claim(connection, item, read_json(args.payload_file), context,
                                                      expected_revision=revision, who=who)
                elif action == "publication-status":
                    result = publication.claim_state(connection, item, args.claim, include_payload=args.include_payload)
                elif action == "publication-dispatch":
                    result = publication.dispatch(connection, item, args.claim, context, confirmed=args.confirmed, who=who)
                elif action == "publication-receipt":
                    result = publication.receipt(connection, item, args.claim, args.operation, read_json(args.receipt_file))
                elif action == "publication-reconcile":
                    result = publication.reconcile(connection, item, args.claim, context, read_json(args.evidence_file), who=who)
                else:
                    result = publication.abandon(connection, item, args.claim, reason=args.reason, leave=args.leave, who=who)
            elif action == "get":
                result = writing.piece_state(connection, item)
            elif action == "readiness":
                result = writing.readiness(connection, item)
            elif action == "stage":
                result = writing.change_stage(
                    connection, item, args.stage, who=who, correct=args.correct,
                    reason=args.reason, expected_revision=revision, confirmed=args.confirmed)
            elif action == "metadata":
                result = writing.update_piece_metadata(
                    connection, item, json.loads(args.changes_json), who=who,
                    expected_revision=revision)
            elif action == "park":
                result = writing.park_piece(connection, item, parked=not args.revive,
                                           who=who, expected_revision=revision)
            elif action == "gate":
                result = writing.record_gate(
                    connection, item, args.artifact, verdict=args.verdict,
                    findings=json.loads(args.findings_json), reason=args.reason,
                    who=who, expected_revision=revision, reviewed_digest=args.reviewed_digest)
            else:
                raise WorkRefusal(f"unknown writing operation: {action}")
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        elif isinstance(result, list):
            for entry in result:
                print(f"#{entry['id']}  {entry['stage']}  {entry['title']}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if action == "verify" and not result["ok"] else 0
    except (sd_db.SdDbError, ValueError, OSError) as error:
        raise WorkRefusal(str(error)) from error
    finally:
        connection.close()


def register(groups: Any) -> None:
    writing = groups.add_parser("writing", help="shared piece stages, evidence, and database cutover")
    verbs = writing.add_subparsers(dest="verb", required=True)
    for action in ("list", "get", "readiness", "import", "verify", "cutover", "recover", "register",
                   "stage", "metadata", "gate", "park", "publication-render", "publication-recover", "publication-claim", "publication-status",
                   "publication-dispatch", "publication-receipt", "publication-reconcile", "publication-abandon"):
        parser = verbs.add_parser(action)
        parser.set_defaults(handler=run, writing_action=action)
        parser.add_argument("--json", action="store_true")
        if action.startswith("publication-"):
            parser.add_argument("--piece", required=True)
            if action not in {"publication-claim", "publication-render", "publication-recover"}:
                parser.add_argument("--claim", required=True)
            if action in {"publication-claim", "publication-dispatch", "publication-reconcile"}:
                parser.add_argument("--context-file", required=True)
            if action == "publication-claim":
                parser.add_argument("--payload-file", required=True)
                parser.add_argument("--if-revision")
            elif action == "publication-recover":
                parser.add_argument("--repair-incomplete", action="store_true")
            elif action == "publication-status":
                parser.add_argument("--include-payload", action="store_true")
            elif action == "publication-dispatch":
                parser.add_argument("--confirmed", action="store_true")
            elif action == "publication-receipt":
                parser.add_argument("--operation", required=True)
                parser.add_argument("--receipt-file", required=True)
            elif action == "publication-reconcile":
                parser.add_argument("--evidence-file", required=True)
            elif action == "publication-abandon":
                parser.add_argument("--reason", required=True)
                parser.add_argument("--leave", action="store_true")
        elif action in {"get", "readiness", "register", "stage", "metadata", "gate", "park"}:
            parser.add_argument("--piece", required=True, help="YEAR/slug")
        if action in {"stage", "metadata", "gate", "park"}:
            parser.add_argument("--if-revision")
        if action == "list":
            parser.add_argument("--all", action="store_true", help="include parked pieces")
            parser.add_argument("--status", help="filter by writing stage")
        elif action == "import":
            parser.add_argument("--apply", action="store_true", help="write import rows; default previews only")
        elif action == "cutover":
            parser.add_argument("--expected-digest", required=True, help="fingerprint from the preview")
        elif action == "register":
            parser.add_argument("--path", help="relative index.md path for a parked piece")
        elif action == "stage":
            parser.add_argument("--stage", required=True)
            parser.add_argument("--correct", action="store_true")
            parser.add_argument("--reason")
            parser.add_argument("--confirmed", action="store_true",
                                help="confirm recording an existing publication, without publishing")
        elif action == "metadata":
            parser.add_argument("--changes-json", required=True)
        elif action == "park":
            parser.add_argument("--revive", action="store_true", help="return a parked piece to active work")
        elif action == "gate":
            parser.add_argument("--artifact", required=True, choices=("fact-check", "adversarial"))
            parser.add_argument("--verdict", required=True, choices=("pass", "fail"))
            parser.add_argument("--findings-json", default="[]")
            parser.add_argument("--reason", required=True)
            parser.add_argument("--reviewed-digest", help="draft digest actually reviewed, required for an unstamped report")
