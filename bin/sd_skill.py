"""`sd skill` — the trial that decides whether a `contrib/` skill stays.

Requirement 10 splits the pack in two. `skills/` holds what a path names, and
the installer renders exactly that; `contrib/` holds everything else, in git
and not installed. Adopting is cheap because a `contrib/` skill costs nothing
to keep. Promotion costs a trial.

`sd skill try <name>` is that trial: thirty days on this machine, one row, and
an expiry the operator can read back. What decides the outcome is use, not
opinion — the `skill_use` rows the hooks write while the trial runs. A trial
that expires having earned none is removed by the next install run, which says
so. A trial that earned use is evidence for the promotion pull request.

`sd_db` is imported inside the handler rather than at module import, the same
way `sd_restore` does it and for the same reason: the library reaches this
virtualenv through the pack's own installer, and `sd` has to keep working for
every other verb on a machine where that has not run yet.
"""

from __future__ import annotations

import argparse
import datetime
import pathlib

#: Why the verb cannot run, when it cannot.
NOT_INSTALLED = (
    "sd_db is not installed in this virtualenv. `sd skill try` writes a trial "
    "row; install the library with the pack's installer (`sd-install`), which "
    "provisions it from the `system` checkout, then run this again."
)

#: Thirty days, from requirement 10. Named rather than inlined so the refusal
#: text and the expiry cannot disagree about the number.
TRIAL_DAYS = 30

class SkillRefusal(Exception):
    """Something the operator must settle before a trial can start."""


CONTRIB_DIR = "contrib"
SKILLS_DIR = "skills"
SKILL_FILE = "SKILL.md"


def checkout() -> pathlib.Path:
    """The pack checkout this file is in. Never a path a caller supplies.

    R10-D6: an sd-* command never accepts a path to somebody else's
    repository. The trial is about the skills this pack ships, so the checkout
    is derived from this file and there is no flag to point it elsewhere.
    """
    return pathlib.Path(__file__).resolve().parents[1]


def available(root: pathlib.Path) -> list[str]:
    """Every `contrib/` skill, in name order. Enumerated, never recited."""
    contrib = root / CONTRIB_DIR
    if not contrib.is_dir():
        return []
    return sorted(
        entry.name
        for entry in contrib.iterdir()
        if entry.is_dir() and (entry / SKILL_FILE).is_file()
    )


def expiry(started: datetime.datetime | None = None) -> str:
    """Thirty days out, in the one format the library compares rows as text."""
    # `timezone.utc` and not `datetime.UTC`: the latter is 3.11, and this
    # repository's mypy is pinned at 3.10, so the alias fails the lint on a
    # runtime that would accept it.
    moment = started or datetime.datetime.now(datetime.timezone.utc)
    return (moment + datetime.timedelta(days=TRIAL_DAYS)).isoformat(timespec="seconds")


def skill_try(args: argparse.Namespace) -> int:
    """Start a thirty-day trial of one `contrib/` skill, and print the date."""
    root = checkout()
    name = args.name
    if (root / SKILLS_DIR / name / SKILL_FILE).is_file():
        raise SkillRefusal(
            f"{name} is already on a path and installs without a trial; "
            f"{SKILLS_DIR}/{name} is what the installer renders"
        )
    if not (root / CONTRIB_DIR / name / SKILL_FILE).is_file():
        names = available(root)
        listing = ", ".join(names) if names else "nothing"
        raise SkillRefusal(f"no {CONTRIB_DIR}/{name}/{SKILL_FILE}; available: {listing}")

    try:
        import sd_db  # noqa: PLC0415 - see the module docstring
    except ImportError as problem:
        raise SkillRefusal(f"{NOT_INSTALLED} ({problem})") from problem

    path = sd_db.default_path()
    if not path.exists():
        raise SkillRefusal(f"no database at {path}; run `sd-db.sh init` first")
    connection = sd_db.connect(path)
    try:
        expires = expiry()
        sd_db.start_trial(connection, name, expires)
    finally:
        connection.close()

    # The date, not the timestamp. The operator reads this to know when to
    # expect the skill to go away, and a second-resolution stamp implies a
    # precision the removal -- which happens on the next install run, not at
    # the instant of expiry -- does not have.
    print(f"{name} on trial until {expires[:10]}")
    print("run `sd-install` to render it, and use it -- use is what decides")
    return 0


def skill_list(args: argparse.Namespace) -> int:
    """What is on a path, what is in `contrib/`, and what is on trial."""
    root = checkout()
    import json  # noqa: PLC0415 - only this verb reads the paths file

    paths_file = root / SKILLS_DIR / "paths.json"
    if not paths_file.is_file():
        raise SkillRefusal(f"no {paths_file}; requirement 10 says a path names what installs")
    paths = json.loads(paths_file.read_text(encoding="utf-8"))["paths"]

    trials: dict[str, str] = {}
    try:
        import sd_db  # noqa: PLC0415 - see the module docstring

        path = sd_db.default_path()
        if path.exists():
            connection = sd_db.connect(path)
            try:
                trials = {
                    row["skill"]: row["expires"][:10]
                    for row in sd_db.active_trials(connection)
                }
            finally:
                connection.close()
    except ImportError:
        # Reported once, at the end, rather than refusing: the paths are a
        # fact about the checkout and answering with them is better than
        # answering with nothing because a second repository is absent.
        trials = {}

    for name, path_data in paths.items():
        print(f"{name} — {path_data.get('summary', '')}")
        for skill in path_data.get("skills", []):
            print(f"  {skill}")
    contrib = available(root)
    print(f"contrib ({len(contrib)}) — in git, not installed")
    for skill in contrib:
        mark = f"  on trial until {trials[skill]}" if skill in trials else ""
        print(f"  {skill}{mark}")
    return 0
