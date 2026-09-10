"""CLI parity for the shared catalog and isolated skill workflow."""

from __future__ import annotations

import argparse
import datetime
import getpass
import json
import pathlib
from typing import Any

import sd_handoff_rows

TRIAL_DAYS = 30
CONTRIB_DIR = "contrib"
SKILLS_DIR = "skills"
SKILL_FILE = "SKILL.md"
PATHS_FILE = "paths.json"


class SkillRefusal(Exception):
    """A skill request that cannot safely be queued."""


def checkout() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def available(root: pathlib.Path) -> list[str]:
    return sorted(path.parent.name for path in (root / CONTRIB_DIR).glob("*/SKILL.md"))


def expiry(started: datetime.datetime | None = None) -> str:
    return ((started or datetime.datetime.now(datetime.UTC)) + datetime.timedelta(days=TRIAL_DAYS)).isoformat(timespec="seconds")


def run(args: argparse.Namespace) -> int:
    sd_db = sd_handoff_rows.library()
    try:
        from sd_db import skills_catalog
    except ImportError:
        raise SkillRefusal("install the current shared library for skill controls") from None
    connection = sd_handoff_rows.connect(sd_db, write=args.verb != "list")
    try:
        options = {"root": checkout()}
        if args.verb == "list":
            result = skills_catalog.catalog(connection, **options)
        elif args.verb == "try":
            result = skills_catalog.trial(connection, args.name, expected_revision=getattr(args, "if_revision", None), **options)
        elif args.verb == "apply":
            from sd_db import workflow
            revision = args.if_revision or workflow.item_state(connection, args.item)["revision"]
            result = skills_catalog.apply_proposals(connection, args.item, args.notes, expected_revision=revision, who=getpass.getuser())
        else:
            result = skills_catalog.request(connection, args.name, args.verb, expected_revision=getattr(args, "if_revision", None),
                path_name=getattr(args, "path", None), who=getpass.getuser(), **options)
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False))
        elif args.verb == "list":
            for skill in result["skills"]:
                print(f"{skill['name']}  {skill['status']}  {skill['description']}")
        elif args.verb == "try":
            print(f"{args.name} on trial until {result['trial']['expires'][:10]}")
            print("Run sd-install to render it. The trial does not change installed files by itself.")
        else:
            print(f"Queued item #{result['item']['id']}: {result['item']['title']}")
        return 0
    except (sd_db.SdDbError, ValueError, OSError) as error:
        raise SkillRefusal(str(error)) from error
    finally:
        connection.close()


skill_try = run
skill_list = run
skill_promote = run
skill_demote = run


def register_extra(verbs: Any) -> None:
    review = verbs.add_parser("review", help="queue one independent review of a skill")
    review.add_argument("name")
    applying = verbs.add_parser("apply", help="queue one isolated change from accepted proposal notes")
    applying.add_argument("item", type=int)
    applying.add_argument("notes", nargs="+", type=int)
    for parser in (review, applying):
        parser.add_argument("--if-revision")
        parser.add_argument("--json", action="store_true")
        parser.set_defaults(handler=run)
