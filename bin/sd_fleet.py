"""`sd fleet stamp`: lay the auto-merge fleet's shared files, one repository at a time.

Every repository whose `repo.runner_merge` row says `auto` is merged by the
runner through `sd-ship`, and `sd-ship merge` under a declared gap needs four
things the repository itself carries (sd:1326, decision D5 on sd:1334):

  * the review-route workflow at the pack's current pin, and its Dependabot
    guard -- the same text `sd-review setup-github` writes, from
    `bin/sd_setup_github.py`, not a second copy;
  * a check workflow, because `every_check` refuses a head nothing validated
    and a repository with no `pull_request` workflow has nothing to run;
  * the `unprotected` entry in `.github/sd-status.json`, in the plain
    "no protection by decision" form;
  * the `CLAUDE.local.md` block, rendered by `bin/sd_install.py`, and
    `docs/dashboard/` ignored and present for generated HTML.

The verb is idempotent: it renders what each file should hold and diffs that
against what the file holds, so a second run over a stamped repository finds
nothing, and the same run after a pin moves is the pin bump. `--dry-run`
prints the diff per repository and writes nothing anywhere.

A dry run walks the auto rows read-only. Tracked files are read at each
checkout's `origin/HEAD` -- the branch a stamp pull request would target, not
whatever the operator has checked out -- and the untracked two
(`CLAUDE.local.md`, the `docs/dashboard/` directory) from the checkout itself.
Nothing here fetches: a stale `origin/HEAD` gives a stale diff, and the header
names the commit it read so the reader can tell.

A write takes no path (R10-D6): it stamps the checkout the caller stands in,
which must be a checkout of an auto repository. Tracked files are written only
on a feature branch; on the default branch the write lays the untracked files
and says the rest needs a worktree.

Employer repositories -- any owner not in `OWNERS` -- are adapted, never
changed in their settings: they keep their protection, so they get no
`unprotected` declaration, and the dry run says so rather than going quiet.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import pathlib
import sys
from typing import Any, Callable, Iterable

import sd_lib
import sd_setup_github
import sd_setup_guard

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3

#: The owners whose repositories the operator owns outright. Any other owner
#: is an employer's, and its protection stands (sd:1334, D2 kept those).
OWNERS = ("platypeeps", "sdelmas")
PACK_SLUG = sd_setup_github.ACTION_REPOSITORY

ROUTE_PATH = str(sd_setup_github.WORKFLOW_RELATIVE_PATH)
DEPENDABOT_PATH = str(sd_setup_guard.DEPENDABOT_RELATIVE_PATH)
CHECK_PATH = ".github/workflows/sd-check.yml"
STATUS_PATH = ".github/sd-status.json"
GITIGNORE_PATH = ".gitignore"
LOCAL_BLOCK_PATH = "CLAUDE.local.md"
DASHBOARD_DIR = "docs/dashboard"
DASHBOARD_IGNORES = frozenset({
    "docs/dashboard", "docs/dashboard/", "/docs/dashboard", "/docs/dashboard/",
    "docs/dashboard/*", "/docs/dashboard/*",
})

#: The one `unprotected` acceptance the fleet carries. Plain on purpose: a
#: `because` that cites a ruleset goes false when the ruleset is deleted, which
#: is how rwbp-website's came to name one D2 had removed (sd:1326 note).
UNPROTECTED_ENTRY: dict[str, Any] = {
    "id": "unprotected",
    "state": {"branch_protection": False},
    "because": (
        "No protection by decision 2026-09-22 (sd:1334 D2). One operator owns this repository; "
        "sd-ship merge requires every check run, every status and a pull_request run of every "
        "workflow at the reviewed head in place of a required-checks list."
    ),
    "since": "2026-09-22",
    "until": "a second account with push or merge rights on this repository exists",
}


def check_workflow_text() -> str:
    """The check workflow a repository with no `pull_request` workflow gets.

    The floor, and it says so: it proves a `pull_request` run happened at the
    head and that the diff carries no whitespace error or conflict marker. It
    runs no repository's tests, because a stamp that guessed a toolchain would
    go red on every repository it guessed wrong. A repository with its own
    `pull_request` workflow never gets this one.
    """

    return f"""\
# Laid by `sd fleet stamp` (sd-ai-command-pack) in a repository that had no
# pull_request workflow. `sd-ship merge` under a declared gap requires a
# successful pull_request run of every workflow at the head, and refuses a head
# nothing validated; this is the run.
#
# What it checks: the pull request's diff against its base has no whitespace
# error and no conflict marker (`git diff --check`). It runs none of this
# repository's own tests. Add a workflow that does, and this one can go.
name: sd check

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read

concurrency:
  group: sd-check-${{{{ github.event.pull_request.number }}}}
  cancel-in-progress: true

jobs:
  check:
    name: check
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Check out the pull request
        uses: {sd_setup_github.CHECKOUT_ACTION} # {sd_setup_github.CHECKOUT_VERSION}
        with:
          ref: refs/pull/${{{{ github.event.pull_request.number }}}}/head
          fetch-depth: 0
          persist-credentials: false
      - name: The diff has no whitespace errors or conflict markers
        env:
          BASE_REF: ${{{{ github.base_ref }}}}
        run: git diff --check "origin/${{BASE_REF}}...HEAD"
"""


class FleetRefusal(Exception):
    """The invocation cannot go ahead; the message names why."""


@dataclasses.dataclass
class Change:
    path: str
    where: str  # "tracked" (a pull request carries it) or "local" (the checkout's own)
    before: str | None
    after: str
    directory: bool = False

    def diff(self) -> str:
        if self.directory:
            return f"+ directory {self.path}/ (local, untracked)\n"
        return "".join(difflib.unified_diff(
            (self.before or "").splitlines(keepends=True), self.after.splitlines(keepends=True),
            fromfile="/dev/null" if self.before is None else f"a/{self.path}",
            tofile=f"b/{self.path}"))


@dataclasses.dataclass
class Plan:
    root: str
    slug: str
    base: str
    changes: list[Change] = dataclasses.field(default_factory=list)
    adapted: list[str] = dataclasses.field(default_factory=list)
    refused: list[str] = dataclasses.field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {"repo": self.root, "slug": self.slug, "base": self.base,
                "changes": [{"path": c.path, "where": c.where,
                             "action": "create" if c.before is None else "update",
                             "diff": c.diff()} for c in self.changes],
                "adapted": self.adapted, "refused": self.refused}


class Tree:
    """Tracked files as one tree holds them: a commit, or a worktree on disk."""

    def __init__(self, root: pathlib.Path, commit: str | None) -> None:
        self.root, self.commit = root, commit

    def text_at(self, rel: str) -> str | None:
        if self.commit is None:
            path = self.root / rel
            return path.read_text(encoding="utf-8") if path.is_file() else None
        kind = sd_lib.git_output(["cat-file", "-t", f"{self.commit}:{rel}"], self.root)
        if kind != "blob":
            return None
        return _git_show(self.root, f"{self.commit}:{rel}")

    def workflows(self) -> list[str]:
        directory = ".github/workflows"
        if self.commit is None:
            found = sorted(p.name for p in (self.root / directory).glob("*") if p.is_file())
        else:
            listing = sd_lib.git_output(["ls-tree", "--name-only", "-z", self.commit, f"{directory}/"],
                                        self.root) or ""
            found = sorted(name.rsplit("/", 1)[-1] for name in listing.split("\0") if name)
        return [f"{directory}/{name}" for name in found if name.endswith((".yml", ".yaml"))]


def _git_show(root: pathlib.Path, spec: str) -> str | None:
    """`git show` without the strip `git_output` applies: file bytes are the diff."""
    import subprocess  # noqa: PLC0415 - one call site

    try:
        done = subprocess.run(["git", "-C", str(root), "show", spec], capture_output=True,  # nosec B603 B607
                              text=True, timeout=sd_lib.GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def owner_slug(remote: str | None) -> str:
    """`owner/name` for a github.com origin, lower-cased; "" for anything else."""
    value = (remote or "").strip()
    for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
        if value.lower().startswith(prefix):
            return value[len(prefix):].strip("/").removesuffix(".git").lower()
    return ""


def default_ref(root: pathlib.Path) -> str | None:
    """The commit `origin/HEAD` names, falling back to `origin/main` then `origin/master`."""
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        commit = sd_lib.git_output(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root)
        if commit:
            return commit
    return None


def pack_pin(given: str | None) -> str:
    """The pin consumers get: `--pin`, else the pack checkout's `origin/HEAD` commit.

    Not the pack's `HEAD`, which `sd-review setup-github` uses for one
    repository: a fleet stamp run from a feature branch would pin every
    repository to a commit no consumer can fetch.
    """
    if given:
        return given
    commit = default_ref(sd_setup_github.pack_root())
    if not commit:
        raise FleetRefusal("cannot read the pack checkout's origin/HEAD; pass --pin <sha>")
    return commit


def status_text(current: str | None) -> str:
    """`.github/sd-status.json` with the one `unprotected` entry in the plain form.

    Every other entry, and every other key, stays as written. Raises
    ValueError on a file that is not the object the schema describes.
    """
    data: dict[str, Any] = {} if current is None else json.loads(current)
    if not isinstance(data, dict) or not isinstance(data.get("accepted_gaps", []), list):
        raise ValueError("not an object with an accepted_gaps list")
    gaps = [gap for gap in data.get("accepted_gaps", []) if not (isinstance(gap, dict) and gap.get("id") == "unprotected")]
    data["accepted_gaps"] = [*gaps, dict(UNPROTECTED_ENTRY)]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def gitignore_text(current: str | None) -> str:
    """`.gitignore` with `docs/dashboard/` ignored; unchanged when a line already does."""
    text = current or ""
    if any(line.strip() in DASHBOARD_IGNORES for line in text.splitlines()):
        return text
    separator = "" if not text or text.endswith("\n") else "\n"
    return f"{text}{separator}# Generated HTML the local dashboard serves; never committed.\n{DASHBOARD_DIR}/\n"


def pull_request_workflows(tree: Tree, *, besides: Iterable[str]) -> list[str]:
    """Workflows in `tree` that run on `pull_request`, other than the ones named."""
    skip = set(besides)
    found = []
    for path in tree.workflows():
        if path in skip:
            continue
        lines = sd_lib.yaml_lines(tree.text_at(path) or "")
        if "pull_request" in sd_lib.workflow_triggers(lines):
            found.append(path)
    return found


def tracked_changes(plan: Plan, tree: Tree, propose: Callable[[str, str], None], *, pin: str,
                    owned: bool, self_install: bool) -> None:
    """The tracked half of a plan: route, guard, check, declaration, ignore line."""
    legacy = [rel for rel in sd_setup_github.LEGACY_ROUTER_PATHS if tree.text_at(rel) is not None]
    if legacy:
        plan.refused.append(f"{ROUTE_PATH}: the sd-github-review footprint is still here ({', '.join(legacy)}); "
                            "run `sd-review setup-github --remove-legacy` in this repository first")
    else:
        propose(ROUTE_PATH, sd_setup_github.workflow_text(
            sd_setup_github.action_reference(None if self_install else pin)))
        if not self_install:
            try:
                propose(DEPENDABOT_PATH, sd_setup_guard.rendered(tree.text_at(DEPENDABOT_PATH)))
            except sd_setup_guard.GuardError as error:
                plan.refused.append(f"{DEPENDABOT_PATH}: {error}")

    # Check workflow, only where nothing else validates a pull request.
    others = pull_request_workflows(tree, besides=(ROUTE_PATH, CHECK_PATH))
    if others and tree.text_at(CHECK_PATH) is None:
        plan.adapted.append(f"{CHECK_PATH}: not laid; {', '.join(others)} already run on pull_request")
    else:
        propose(CHECK_PATH, check_workflow_text())

    # The declared gap, on owned repositories only.
    if not owned:
        plan.adapted.append(f"{STATUS_PATH}: not declared; {plan.slug or 'this remote'} is not an operator-owned "
                            "repository, so its protection stands")
    else:
        try:
            propose(STATUS_PATH, status_text(tree.text_at(STATUS_PATH)))
        except ValueError as error:
            plan.refused.append(f"{STATUS_PATH}: unreadable ({error}); fix it by hand, then re-run")

    propose(GITIGNORE_PATH, gitignore_text(tree.text_at(GITIGNORE_PATH)))


def plan_repo(root: pathlib.Path, remote: str | None, *, pin: str, tree: Tree,
              local_block: Callable[[str], str], tracked: Callable[[pathlib.Path, str], bool]) -> Plan:
    """What stamping `root` would change, rendered and diffed; writes nothing.

    `local_block` renders the `CLAUDE.local.md` text from the current text,
    and `tracked` answers whether a path is tracked in `root`; both are
    `bin/sd_install.py`'s, handed in so the planner holds no second copy.
    """
    slug = owner_slug(remote)
    plan = Plan(root=str(root), slug=slug or (remote or ""), base=tree.commit or f"worktree {tree.root}")
    owned = slug.split("/", 1)[0] in OWNERS if slug else False
    self_install = slug == PACK_SLUG

    def propose(path: str, after: str, where: str = "tracked", before: str | None = None) -> None:
        current = tree.text_at(path) if where == "tracked" else before
        if current != after:
            plan.changes.append(Change(path, where, current, after))

    # A guest or minimal repository carries none of the framework's tracked
    # files (R10-D5), so nothing tracked is proposed there at all; its
    # untracked block is still the operator's to keep current.
    try:
        mode = sd_lib.written_mode(root)
    except sd_lib.ConfigError as error:
        plan.refused.append(f"tracked files: {LOCAL_BLOCK_PATH} is unreadable ({error})")
    else:
        if mode in sd_lib.SETTLED_MODES:
            plan.refused.append(f"tracked files: the local block says mode {mode}; a {mode} repository "
                                "carries none of the framework's files")
        else:
            tracked_changes(plan, tree, propose, pin=pin, owned=owned, self_install=self_install)

    # The checkout's own, untracked files.
    if tracked(root, LOCAL_BLOCK_PATH):
        plan.refused.append(f"{LOCAL_BLOCK_PATH}: tracked in this repository; the block goes only into an "
                            "untracked file")
    else:
        target = root / LOCAL_BLOCK_PATH
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        try:
            propose(LOCAL_BLOCK_PATH, local_block(current or ""), where="local", before=current)
        except SystemExit as error:  # the installer's refusal for a half-open block
            plan.refused.append(f"{LOCAL_BLOCK_PATH}: {str(error.code).removeprefix('error: ')}")
    if not (root / DASHBOARD_DIR).is_dir():
        plan.changes.append(Change(DASHBOARD_DIR, "local", None, "", directory=True))
    return plan


def auto_rows() -> list[tuple[pathlib.Path, str | None]]:
    """`(checkout, remote)` for every repository row whose `runner_merge` is `auto`."""
    import sd_handoff_rows  # noqa: PLC0415 - the library is optional until this verb runs

    sd_db = sd_handoff_rows.library()
    from sd_db.repos import registered  # noqa: PLC0415

    connection = sd_handoff_rows.connect(sd_db, write=False)
    try:
        rows = registered(connection)
    finally:
        connection.close()
    return [(sd_lib.repo_disk(row["path"]), row["remote"]) for row in rows if row["runner_merge"] == "auto"]


def _installer() -> Any:
    import sd_install  # noqa: PLC0415 - large, and only this verb needs it

    return sd_install


def selected(rows: list[tuple[pathlib.Path, str | None]], wanted: list[str]) -> list[tuple[pathlib.Path, str | None]]:
    """The rows `--only` names by `owner/name`; every row when it names none."""
    if not wanted:
        return rows
    chosen = []
    for name in wanted:
        match = [row for row in rows if owner_slug(row[1]) == name.lower()]
        if not match:
            raise FleetRefusal(f"{name} is not a runner_merge=auto repository row; the stamp covers only those")
        chosen += match
    return chosen


def here(rows: list[tuple[pathlib.Path, str | None]], cwd: pathlib.Path) -> tuple[pathlib.Path, str | None, bool]:
    """The checkout a write lands in: the one the caller stands in (R10-D6).

    It must be a checkout of an auto row's repository -- matched by origin,
    so a worktree of a registered checkout qualifies. The third value says
    whether its HEAD is a feature branch, the only place tracked files go.
    """
    top = sd_lib.repo_root(cwd)
    if top is None:
        raise FleetRefusal(f"{cwd} is not inside a git repository")
    slug = owner_slug(sd_lib.git_output(["config", "--get", "remote.origin.url"], top))
    match = [row for row in rows if slug and owner_slug(row[1]) == slug]
    if not match:
        raise FleetRefusal(f"{top} is not a checkout of a runner_merge=auto repository; the stamp covers only those")
    branch = sd_lib.git_output(["symbolic-ref", "--quiet", "--short", "HEAD"], top)
    default = (sd_lib.git_output(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], top)
               or "origin/main").removeprefix("origin/")
    return top, match[0][1], bool(branch) and branch != default


def render_plans(plans: list[Plan], stream: Any, *, dry_run: bool) -> None:
    write = stream.write
    for plan in plans:
        count = len(plan.changes)
        write(f"== {plan.root} ({plan.slug}) at {plan.base[:12]}: "
              f"{count} change{'s' if count != 1 else ''}\n")
        for change in plan.changes:
            write(change.diff())
        for line in plan.adapted:
            write(f"   adapted  {line}\n")
        for line in plan.refused:
            write(f"   refused  {line}\n")
    changing = [plan for plan in plans if plan.changes]
    write(f"\nsd fleet stamp{' --dry-run' if dry_run else ''}: {len(plans)} repositories, "
          f"{len(changing)} with changes, {len(plans) - len(changing)} unchanged, "
          f"{sum(len(plan.refused) for plan in plans)} refused\n")
    for plan in plans:
        files = ", ".join(change.path for change in plan.changes) or "none"
        flag = f"  refused: {len(plan.refused)}" if plan.refused else ""
        write(f"  {plan.slug or plan.root}: {files}{flag}\n")
    if dry_run:
        write("dry run: nothing was written\n")


def apply(plan: Plan, root: pathlib.Path) -> None:
    """Write one plan into `root`, the checkout the caller stands in."""
    for change in plan.changes:
        target = root / change.path
        if change.directory:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.after, encoding="utf-8")


Rows = Callable[[], list[tuple[pathlib.Path, str | None]]]
Planner = Callable[[pathlib.Path, str | None, Tree], Plan]


def dry_run_plans(rows: list[tuple[pathlib.Path, str | None]], planned: Planner) -> list[Plan]:
    """Every row read at its `origin/HEAD`; a row with nothing to read is refused, not skipped."""
    plans = []
    for root, remote in rows:
        commit = default_ref(root) if (root / ".git").exists() else None
        if commit is None:
            plan = Plan(root=str(root), slug=owner_slug(remote), base="-")
            plan.refused.append(f"no checkout at {root}" if not (root / ".git").exists()
                                else "no origin/HEAD, origin/main or origin/master to diff against")
            plans.append(plan)
            continue
        plans.append(planned(root, remote, Tree(root, commit)))
    return plans


def write_here(rows: list[tuple[pathlib.Path, str | None]], cwd: pathlib.Path, planned: Planner) -> Plan:
    """Plan and write the checkout the caller stands in; tracked files on a feature branch only."""
    root, remote, feature = here(rows, cwd)
    plan = planned(root, remote, Tree(root, None))
    if not feature:
        held = [change.path for change in plan.changes if change.where == "tracked"]
        plan.changes = [change for change in plan.changes if change.where != "tracked"]
        if held:
            plan.adapted.append(f"tracked files not written ({', '.join(held)}): this checkout is on its "
                                "default branch; run from a worktree on a feature branch")
    if not plan.refused:
        apply(plan, root)
    return plan


def fleet_stamp(args: argparse.Namespace, *, rows: Rows = auto_rows, stream: Any = None,
                cwd: pathlib.Path | None = None) -> int:
    """Plan every selected repository, print the plans, and write only on a write run.

    A dry run walks the auto rows and reads each at its `origin/HEAD`. A
    write acts on the checkout the caller stands in and nowhere else: no
    option names another checkout (R10-D6). On the default branch it writes
    the untracked files only and says the tracked ones need a feature branch.
    """
    stream = stream or sys.stdout
    if not args.dry_run and args.only:
        raise FleetRefusal("--only selects for a dry run; a write stamps the checkout you stand in")
    pin = pack_pin(args.pin)
    installer = _installer()

    def planned(root: pathlib.Path, remote: str | None, tree: Tree) -> Plan:
        return plan_repo(root, remote, pin=pin, tree=tree,
                         local_block=lambda text: installer.local_block_text(text)[0],
                         tracked=installer.path_is_tracked)

    if args.dry_run:
        plans = dry_run_plans(selected(rows(), args.only), planned)
    else:
        plans = [write_here(rows(), cwd or pathlib.Path.cwd(), planned)]
    if args.json:
        stream.write(json.dumps({"dry_run": bool(args.dry_run), "pin": pin,
                                 "repos": [plan.as_json() for plan in plans]}, indent=2) + "\n")
    else:
        render_plans(plans, stream, dry_run=args.dry_run)
    return EXIT_REFUSED if any(plan.refused for plan in plans) else EXIT_OK


def run_fleet_stamp(args: argparse.Namespace) -> int:
    try:
        return fleet_stamp(args)
    except FleetRefusal as refusal:
        print(f"sd fleet stamp: {refusal}", file=sys.stderr)
        return EXIT_USAGE


def register_fleet(groups: Any) -> None:
    fleet = groups.add_parser("fleet", help="lay the runner_merge=auto fleet's shared files")
    verbs = fleet.add_subparsers(dest="verb", required=True)
    stamper = verbs.add_parser(
        "stamp",
        help="route and check workflows, the sd-status declaration and the CLAUDE.local.md block, per auto repo")
    stamper.add_argument("--dry-run", action="store_true",
                         help="print each repository's diff against its origin/HEAD; write nothing")
    stamper.add_argument("--only", action="append", default=[], metavar="OWNER/NAME",
                         help="dry run: one auto repository by its GitHub name (repeatable); default: every one")
    stamper.add_argument("--pin", metavar="SHA", help="pin the route action here instead of the pack's origin/HEAD")
    stamper.add_argument("--json", action="store_true", help="emit one machine-readable object")
    stamper.set_defaults(handler=run_fleet_stamp)
