"""CLI parity for the shared catalog and isolated skill workflow."""

from __future__ import annotations

import argparse
import datetime
import getpass
import json
import pathlib
from typing import Any

import sd_handoff_rows
from sd_notes import ITEM_HELP, item_id

TRIAL_DAYS = 30
CONTRIB_DIR = "contrib"
SKILLS_DIR = "skills"
SKILL_FILE = "SKILL.md"
PATHS_FILE = "paths.json"


class SkillRefusal(Exception):
    """A skill request that cannot safely be filed."""


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
                used = (f"  uses={sum(use['count'] for use in skill['uses'])}  last={(skill['last'] or 'never')[:10]}"
                        if getattr(args, "usage", False) else "")
                print(f"{skill['name']}  {skill['status']}{used}  {skill['description']}")
        elif args.verb == "try":
            print(f"{args.name} on trial until {result['trial']['expires'][:10]}")
            print("Run sd-install to render it. The trial does not change installed files by itself.")
        else:
            print(f"Filed item #{result['item']['id']}: {result['item']['title']}")
        return 0
    except (sd_db.SdDbError, ValueError, OSError) as error:
        raise SkillRefusal(str(error)) from error
    finally:
        connection.close()


def intake_connection(write: bool):
    """The workflow database, which holds the tracked repositories as one setting row; and its error class."""
    sd_db = sd_handoff_rows.library()
    return sd_handoff_rows.connect(sd_db, write=write), sd_db.SdDbError


def skill_intake(args: argparse.Namespace) -> int:
    """`sd skill intake`: deferred, because only this verb fetches from GitHub."""
    import sqlite3  # noqa: PLC0415

    import sd_skill_intake  # noqa: PLC0415 - loads sd-skill-adopt as a sibling

    listing = [name for name in ("tracked", "track", "untrack", "refresh") if getattr(args, name)]
    if len(listing) + bool(args.source) != 1:
        raise SkillRefusal("give one of a source, --tracked, --track URL, --untrack URL or --refresh URL")
    if args.rollback and (listing or args.source.startswith("https://")):
        raise SkillRefusal("--rollback takes the name of an installed skill, as the report printed it")
    if listing and args.approve:
        raise SkillRefusal("--approve installs one skill: give its URL, as the refresh printed it")
    if listing and args.scope and not args.track:
        raise SkillRefusal("--scope goes with a source or --track")
    try:
        if not listing:
            return sd_skill_intake.run_intake(args, checkout(), pathlib.Path.home())
        connection, database_error = intake_connection(write=not args.tracked)
    except (sd_skill_intake.IntakeError, sd_handoff_rows.RowsRefusal, OSError) as error:
        raise SkillRefusal(str(error)) from error
    try:
        return sd_skill_intake.run_tracking(args, connection, checkout(), pathlib.Path.home())
    except (sd_skill_intake.IntakeError, database_error, sqlite3.Error, OSError) as error:
        raise SkillRefusal(str(error)) from error
    finally:
        connection.close()


skill_try = run
skill_list = run
skill_promote = run
skill_demote = run


def register_extra(verbs: Any) -> None:
    review = verbs.add_parser("review", help="file one independent review of a skill")
    review.add_argument("name")
    applying = verbs.add_parser("apply", help="queue one isolated change from accepted proposal notes")
    applying.add_argument("item", type=item_id, help=ITEM_HELP)
    applying.add_argument("notes", nargs="+", type=int)
    intake = verbs.add_parser(
        "intake",
        help="judge a GitHub skill, or re-import an installed one, against the installed set; install only on approval")
    intake.add_argument("source", nargs="?",
                        help="a https://github.com/ skill URL, or the name of a skill installed from one")
    tracking = intake.add_mutually_exclusive_group()
    tracking.add_argument("--tracked", action="store_true",
                          help="list the tracked source repositories and the skills adopted from each")
    tracking.add_argument("--track", metavar="URL", help="track a https://github.com/<owner>/<repo> repository")
    tracking.add_argument("--untrack", metavar="URL", help="stop tracking a repository; its installed skills stay")
    tracking.add_argument("--refresh", metavar="URL",
                          help="judge every skill of a tracked repository at its default branch; installs nothing")
    intake.add_argument("--scope", choices=("pack", "user"),
                        help="pack: contrib/ with the sd- prefix (default for a URL); user: ~/.claude/skills")
    intake.add_argument("--approve", metavar="REVISION",
                        help="install the revision the report printed; without it nothing is installed")
    intake.add_argument("--rollback", action="store_true",
                        help="swap an installed skill with the copy its last install replaced; "
                             "with --approve REVISION it writes")
    intake.add_argument("--json", action="store_true")
    intake.set_defaults(handler=skill_intake)
    for parser in (review, applying):
        parser.add_argument("--if-revision")
        parser.add_argument("--json", action="store_true")
        parser.set_defaults(handler=run)
