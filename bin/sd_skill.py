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
PATHS_FILE = "paths.json"


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
    moment = started or datetime.datetime.now(datetime.UTC)
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

    paths_file = root / SKILLS_DIR / PATHS_FILE
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


# --------------------------------------------------------------------------
# Promotion and demotion: the two moves that change what installs
# --------------------------------------------------------------------------


def paths_edit(root: pathlib.Path, name: str, path_name: str, *, add: bool) -> list[str]:
    """Add or remove `name` in `skills/paths.json`. Returns the paths changed.

    The whole document is loaded and written back, not `read_paths`'s
    `data["paths"]`: the file opens with a `$comment` block stating why
    requirement 10 exists, and a writer that round-tripped only the paths would
    delete the reasoning its next reader needs. `json.dumps` preserves key
    order, so the block survives untouched.

    Removal sweeps every path. `paths.json`'s own comment says a skill may ride
    two, and demoting one that does while leaving the second naming a directory
    now in `contrib/` fails `make check` after the merge rather than here.
    """
    import json  # noqa: PLC0415 - two verbs in this module read the paths file

    document = root / SKILLS_DIR / PATHS_FILE
    if not document.is_file():
        raise SkillRefusal(f"no {document}; requirement 10 says a path names what installs")
    paths = (data := json.loads(document.read_text(encoding="utf-8")))["paths"]

    if add:
        if path_name not in paths:
            raise SkillRefusal(f"no path named {path_name}; the three are {', '.join(sorted(paths))}")
        if name in paths[path_name]["skills"]:
            raise SkillRefusal(f"the {path_name} path already names {name}")
        paths[path_name]["skills"] = sorted([*paths[path_name]["skills"], name])
        changed = [path_name]
    else:
        changed = [key for key, path in paths.items() if name in path.get("skills", [])]
        if not changed:
            raise SkillRefusal(f"no path names {name}, so there is nothing to demote it from")
        for key in changed:
            paths[key]["skills"] = [s for s in paths[key]["skills"] if s != name]

    document.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def move_in_a_pull_request(name: str, path_name: str, *, promoting: bool) -> int:
    """Branch, move the directory, edit the paths, push, open, say where.

    The half both directions share, which is all of it but the two names. The
    branch, the staging, the commit, the push and the pull request do not know
    which way the skill went, so writing them twice would write a copy. What
    the callers settle first is only that the move is legal.

    Each git step says which one failed. `sd_lib.git_output` answers None for
    every failure alike, and "the promotion failed" tells an operator nothing
    about whether to retry or to go fix a remote.
    """
    import sd_lib  # noqa: PLC0415 - see the module docstring

    root = checkout()
    # Before anything is written. A `git commit` on a dirty checkout sweeps
    # unrelated work into a pull request about one skill directory.
    if sd_lib.git_output(["--no-optional-locks", "status", "--porcelain"], root):
        raise SkillRefusal("this checkout has uncommitted changes; commit or stash them first")
    remote, base = sd_lib._upstream(root)  # noqa: SLF001 - the one reader of this fact
    if not remote:
        raise SkillRefusal("this checkout has no remote; a pull request needs somewhere to go")

    source, target = (CONTRIB_DIR, SKILLS_DIR) if promoting else (SKILLS_DIR, CONTRIB_DIR)
    branch = f"{'promote' if promoting else 'demote'}/{name}"
    if sd_lib.git_output(["checkout", "-b", branch], root) is None:
        raise SkillRefusal(f"cannot create branch {branch}; it may already exist")
    if sd_lib.git_output(["mv", f"{source}/{name}", f"{target}/{name}"], root) is None:
        raise SkillRefusal(f"git will not move {source}/{name} to {target}/{name}")
    changed = paths_edit(root, name, path_name, add=promoting)

    title = (
        f"feat(skill): promote {name} to the {path_name} path" if promoting
        else f"chore(skill): demote {name} to {CONTRIB_DIR}/"
    )
    body = (
        f"Moves `{source}/{name}/` to `{target}/{name}/` and "
        + (f"names it on the `{path_name}` path, so the installer renders it without a "
           "trial row." if promoting else
           f"drops it from {', '.join(f'`{key}`' for key in changed)}. It stays in git and "
           f"stops installing; `sd skill try {name}` brings it back for {TRIAL_DAYS} days.")
    )
    for argv, failed in (
        (["add", "--", f"{SKILLS_DIR}/{PATHS_FILE}"], "cannot stage the paths file"),
        (["commit", "--quiet", "-m", title], "git refused the commit"),
        (["push", "--set-upstream", remote, branch], f"cannot push {branch} to {remote}"),
    ):
        if sd_lib.git_output(argv, root) is None:
            raise SkillRefusal(failed)

    # The first write to GitHub anywhere in `bin/`. It goes through `gh_json`
    # unchanged, because `gh api --method POST` is the call shape every reader
    # there already makes: the timeout, the `OSError` guard and the JSON decode
    # are built. `gh pr create` would have needed a second runner for a command
    # that answers with a URL on stdout instead of with JSON.
    pr_state = sd_lib.sibling("sd_pr_state", "sd-pr-state")
    slug = pr_state.remote_slug(root)
    if not slug:
        raise SkillRefusal(f"{branch} is pushed, but {remote} is not a GitHub remote")
    payload, error = pr_state.gh_json(
        ["api", "--method", "POST", f"repos/{slug}/pulls", "-f", f"title={title}",
         "-f", f"body={body}", "-f", f"head={branch}", "-f", f"base={base}"],
        root,
    )
    if error:
        raise SkillRefusal(f"{branch} is pushed, but gh would not open the pull request: {error}")
    print((payload or {}).get("html_url") or f"pushed {branch}; gh reported no pull request URL")
    return 0


def skill_promote(args: argparse.Namespace) -> int:
    """Move one `contrib/` skill onto a path, in a pull request."""
    root = checkout()
    if not (root / CONTRIB_DIR / args.name / SKILL_FILE).is_file():
        listing = ", ".join(available(root)) or "nothing"
        raise SkillRefusal(f"no {CONTRIB_DIR}/{args.name}/{SKILL_FILE}; available: {listing}")
    if (root / SKILLS_DIR / args.name).exists():
        raise SkillRefusal(f"{SKILLS_DIR}/{args.name} already exists; promotion would overwrite it")
    return move_in_a_pull_request(args.name, args.path, promoting=True)


def skill_demote(args: argparse.Namespace) -> int:
    """Move one installed skill back to `contrib/`, in a pull request."""
    root = checkout()
    if not (root / SKILLS_DIR / args.name / SKILL_FILE).is_file():
        raise SkillRefusal(f"no {SKILLS_DIR}/{args.name}/{SKILL_FILE}; it is not on a path")
    if (root / CONTRIB_DIR / args.name).exists():
        raise SkillRefusal(f"{CONTRIB_DIR}/{args.name} already exists; demotion would overwrite it")
    return move_in_a_pull_request(args.name, "", promoting=False)
