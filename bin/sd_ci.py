"""`sd ci local`: switch the repository the caller stands in to local CI (sd:1914).

`repo.ci = local` (sd:1843) tells `sd-ship merge` to run `sd-check` at the
reviewed head and post `sd/local-gate`. The row alone is half the switch: the
repository still runs its workflows, and its protection still requires the
contexts they produced, which no longer arrive. This verb makes the three
changes together, each read live and each skipped when it already holds:

  * `repo.ci` becomes `local`, through `sd_db.repos.set_ci` -- the writer
    `sd-db.sh repo ci` uses, on the row `registered_for` resolves, so a
    worktree switches its repository;
  * `sd/local-gate` becomes the one required status check, `strict` on, in
    whichever mechanism the default branch uses. A classic protection object
    that requires checks has its `required_status_checks` replaced. Every
    active repository ruleset with a `required_status_checks` rule has that
    rule's parameters replaced and every other rule kept. When nothing
    requires a check yet, the first active repository ruleset gains the rule.
    A branch protected only classically, with no required checks, refuses:
    GitHub offers no write for that sub-object alone, and rewriting the whole
    protection object from a read is lossy. An organization ruleset cannot be
    changed from here, and the plan names it;
  * Actions: a private repository has Actions disabled outright, because the
    runner minutes are what stopped. A public repository keeps Actions on,
    because CodeQL, Dependabot and Copilot run as *dynamic* workflows (path
    `dynamic/...`) that no file declares, and only the workflows its files
    declare are disabled one by one.

The contexts the old workflows produced are dropped from the required set and
named: under `ci = local` they never report again, and a required context that
never reports blocks every merge.

The run is a dry run unless `--apply` is given, and a dry run writes nothing
anywhere: it opens the database read-only and makes only `GET` calls. Every
write is preceded by a read that decides it, so a second `--apply` finds
nothing to do. The verb needs `admin` on the repository and refuses, before
any write, when the token lacks it.

One thing the verb cannot reach: a pull request whose head already carries a
failed check run -- a workflow that ran before the switch, or one GitHub
failed for billing -- still refuses to merge. Under protection GitHub reports
it `unstable` rather than `clean`; under a declared gap `every_check` requires
every check run at the head to pass. The remedy is a fresh commit on the
branch (an empty one will do): with the workflows off, nothing runs on it, and
the local gate is the only check it carries.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import subprocess
import sys
from typing import Any, Callable
from urllib.parse import quote

import sd_fleet
import sd_lib
import sd_protection

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_REFUSED = 3

PREFIX = sd_lib.REPOSITORY_QUERY
CONTEXT = sd_lib.LOCAL_GATE_CONTEXT
#: Workflows GitHub runs from no file in the tree: CodeQL default setup,
#: Dependabot updates, Copilot. Their path starts here, and they stay on.
DYNAMIC_PREFIX = "dynamic/"
WORKFLOW_PAGE = 100
#: The fields `PUT repos/{o}/{r}/rulesets/{id}` accepts; the read carries more.
RULESET_FIELDS = ("name", "target", "enforcement", "bypass_actors", "conditions", "rules")

#: `(method, path, body)` -> `(status, payload)`; status 0 is "gh could not answer".
Call = Callable[[str, str, Any], tuple[int, Any]]


class CiRefusal(Exception):
    """The switch cannot go ahead; the message names why."""


def gh_call(root: pathlib.Path) -> Call:
    """`gh api` in `root`, which fills `{owner}/{repo}` from its remote."""

    def call(method: str, path: str, body: Any = None) -> tuple[int, Any]:
        argv = ["gh", "api", "-X", method, path]
        if body is not None:
            argv += ["--input", "-"]
        try:
            completed = subprocess.run(argv, cwd=str(root), input=None if body is None else json.dumps(body),
                                       capture_output=True, text=True, timeout=sd_lib.GH_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            return 0, {"message": f"gh could not be run: {error}"}
        if completed.returncode != 0:
            said = (completed.stderr or completed.stdout).strip().splitlines()
            line = said[0] if said else f"gh api {path} exited {completed.returncode}"
            match = re.search(r"^(?:gh: )?(.*?)\s*\(HTTP (\d{3})\)$", line)
            return (int(match[2]), {"message": match[1]}) if match else (0, {"message": line})
        try:
            return 200, json.loads(completed.stdout) if completed.stdout.strip() else None
        except json.JSONDecodeError as error:
            return 0, {"message": f"gh api {path} did not answer in JSON: {error}"}

    return call


@dataclasses.dataclass
class Step:
    """One setting: `ok` holds already, `change` would be written, `note` is advice."""

    state: str
    subject: str
    detail: str
    write: Callable[[], None] | None = None

    def record(self) -> dict[str, str]:
        return {"state": self.state, "subject": self.subject, "detail": self.detail}


@dataclasses.dataclass
class Plan:
    repository: str
    branch: str
    private: bool
    steps: list[Step]

    @property
    def changes(self) -> list[Step]:
        return [step for step in self.steps if step.state == "change"]


# --- repo.ci -------------------------------------------------------------


def ci_step(root: pathlib.Path, database: pathlib.Path | None) -> Step:
    """The `repo.ci` row: read here, written by the returned step."""
    if sd_lib.import_sd_db().module is None:
        raise CiRefusal("the sd_db library is not importable, so repo.ci cannot be read or set")
    from sd_db import repos  # noqa: PLC0415
    from sd_db.database import connect, default_path  # noqa: PLC0415

    path = database or default_path()
    connection = connect(path, write=False)
    try:
        origin = sd_lib.git_output(["config", "--get", "remote.origin.url"], root)
        target = repos.registered_for(connection, str(root.resolve()), origin)
        row = sd_lib.repo_row(connection, target)
        if row is None:
            raise CiRefusal(f"{target} is not a registered repository; run `sd-db.sh repo add {target}`")
        current = row["ci"] if "ci" in row.keys() else None
    finally:
        connection.close()
    if current is None:
        raise CiRefusal("this database has no repo.ci column; upgrade the sd_db library")
    if current == "local":
        return Step("ok", "repo.ci", f"local for {target}")

    def set_local() -> None:
        connection = connect(path)
        try:
            repos.set_ci(connection, target, "local")
        finally:
            connection.close()

    return Step("change", "repo.ci", f"{current} -> local for {target}", set_local)


# --- the required check ----------------------------------------------------


def _contexts(entries: Any) -> list[str]:
    return [str(entry.get("context")) for entry in entries or [] if isinstance(entry, dict)]


def _dropped(contexts: list[str]) -> str:
    others = sorted(set(contexts) - {CONTEXT})
    return f"; drops {', '.join(others)}" if others else ""


def classic_step(call: Call, branch: str, classic: dict) -> Step:
    checks = classic.get("required_status_checks") or {}
    contexts = _contexts(checks.get("checks")) or list(checks.get("contexts") or [])
    where = f"classic protection on {branch}"
    if checks.get("strict") is True and contexts == [CONTEXT]:
        return Step("ok", where, f"requires {CONTEXT}, strict")
    path = f"{PREFIX}/branches/{quote(branch, safe='')}/protection/required_status_checks"

    def patch_checks() -> None:
        status, body = call("PATCH", path, {"strict": True, "checks": [{"context": CONTEXT}]})
        if status != 200:
            raise CiRefusal(f"{where}: the required checks could not be set: {sd_fleet._said(status, body)}")

    return Step("change", where, f"require {CONTEXT}, strict{_dropped(contexts)}", patch_checks)


def ruleset_step(call: Call, ruleset: dict, *, add: bool) -> Step:
    """Point `ruleset`'s status-check rule at the gate, adding the rule when `add`."""
    rules = [dict(rule) for rule in ruleset.get("rules") or [] if isinstance(rule, dict)]
    rule = next((rule for rule in rules if rule.get("type") == "required_status_checks"), None)
    where = f"ruleset {ruleset.get('name')} (#{ruleset.get('id')})"
    parameters = dict((rule or {}).get("parameters") or {})
    contexts = _contexts(parameters.get("required_status_checks"))
    if rule is not None and parameters.get("strict_required_status_checks_policy") is True and contexts == [CONTEXT]:
        return Step("ok", where, f"requires {CONTEXT}, strict")
    parameters["required_status_checks"] = [{"context": CONTEXT}]
    parameters["strict_required_status_checks_policy"] = True
    if rule is None:
        rules.append({"type": "required_status_checks", "parameters": parameters})
    else:
        rule["parameters"] = parameters
    body = {field: ruleset[field] for field in RULESET_FIELDS if field in ruleset}
    body["rules"] = rules
    path = sd_protection.ruleset_path(PREFIX, int(ruleset["id"]))

    def put_ruleset() -> None:
        status, answer = call("PUT", path, body)
        if status != 200:
            raise CiRefusal(f"{where}: the rule could not be written: {sd_fleet._said(status, answer)}")

    kept = len(rules) - 1
    verb = "add a status-check rule requiring" if add else "require"
    return Step("change", where, f"{verb} {CONTEXT}, strict{_dropped(contexts)}; keeps {kept} other rule(s)", put_ruleset)


def read_protection(call: Call, branch: str) -> tuple[dict | None, list[dict]]:
    """The classic protection object, or None, and the active rulesets on `branch`."""
    fetch: sd_protection.Fetch = lambda path: call("GET", path, None)  # noqa: E731
    status, classic = fetch(f"{PREFIX}/branches/{quote(branch, safe='')}/protection")
    limited = status == 403 and sd_protection.plan_limited(sd_fleet._said(status, classic))
    if status == 404 or limited:
        classic = None
    elif status != 200 or not isinstance(classic, dict):
        raise CiRefusal(f"classic protection on {branch} could not be read: {sd_fleet._said(status, classic)}")
    read = sd_protection.read_rulesets(fetch, PREFIX, branch)
    if read["error"]:
        raise CiRefusal(f"the rulesets on {branch} could not be read: {read['error']}")
    return classic, [ruleset for _, ruleset in sorted(read["rulesets"].items()) if ruleset.get("enforcement") == "active"]


def _requires_checks(ruleset: dict) -> bool:
    return any(rule.get("type") == "required_status_checks" for rule in ruleset.get("rules") or [])


def check_steps(call: Call, branch: str) -> list[Step]:
    """Where `sd/local-gate` becomes required: classic, rulesets, or nowhere."""
    classic, active = read_protection(call, branch)
    ours = [ruleset for ruleset in active if ruleset.get("source_type", "Repository") == "Repository"]
    requiring = [ruleset for ruleset in ours if _requires_checks(ruleset)]
    steps = [Step("note", f"ruleset {ruleset.get('name')} (#{ruleset.get('id')})",
                  f"belongs to {ruleset.get('source') or 'the organization'}; change its status checks there")
             for ruleset in active if ruleset not in ours and _requires_checks(ruleset)]
    classic_requires = classic is not None and bool(classic.get("required_status_checks"))
    if classic is not None and classic_requires:
        steps.append(classic_step(call, branch, classic))
    steps += [ruleset_step(call, ruleset, add=False) for ruleset in requiring]
    if classic_requires or requiring:
        return steps
    if ours:
        return steps + [ruleset_step(call, ours[0], add=True)]
    if classic is not None:
        raise CiRefusal(f"classic protection on {branch} requires no status check, and GitHub offers no write for "
                        f"that part alone; add {CONTEXT} as a required check in the branch settings, then rerun")
    return steps + [Step("ok", f"{branch}", f"unprotected: sd-ship merge requires {CONTEXT} under the declared gap")]


# --- Actions ---------------------------------------------------------------


def actions_steps(call: Call, private: bool) -> list[Step]:
    status, permissions = call("GET", f"{PREFIX}/actions/permissions", None)
    if status != 200 or not isinstance(permissions, dict):
        raise CiRefusal(f"the Actions permissions could not be read: {sd_fleet._said(status, permissions)}")
    enabled = permissions.get("enabled") is True
    if private:
        if not enabled:
            return [Step("ok", "Actions", "disabled")]

        def actions_off() -> None:
            answer_status, answer = call("PUT", f"{PREFIX}/actions/permissions", {"enabled": False})
            if answer_status != 200:
                raise CiRefusal(f"Actions could not be disabled: {sd_fleet._said(answer_status, answer)}")

        return [Step("change", "Actions", "disable for the whole repository (private)", actions_off)]
    if not enabled:
        return [Step("ok", "Actions", "disabled; a public repository may keep them on for its dynamic workflows")]
    status, listing = call("GET", f"{PREFIX}/actions/workflows?per_page={WORKFLOW_PAGE}", None)
    workflows = listing.get("workflows") if isinstance(listing, dict) else None
    if status != 200 or not isinstance(workflows, list):
        raise CiRefusal(f"the workflows could not be listed: {sd_fleet._said(status, listing)}")
    if int(listing.get("total_count") or 0) > len(workflows):
        raise CiRefusal(f"the repository has more than {WORKFLOW_PAGE} workflows; disable them by hand")
    steps = [Step("ok", "Actions", "enabled (public): dynamic workflows keep running")]
    for workflow in sorted(workflows, key=lambda entry: str(entry.get("path"))):
        path = str(workflow.get("path") or "")
        if path.startswith(DYNAMIC_PREFIX):
            continue
        subject = f"workflow {path}"
        if workflow.get("state") != "active":
            steps.append(Step("ok", subject, str(workflow.get("state"))))
            continue
        endpoint = f"{PREFIX}/actions/workflows/{workflow.get('id')}/disable"

        def disable_workflow(endpoint: str = endpoint, subject: str = subject) -> None:
            answer_status, answer = call("PUT", endpoint, None)
            if answer_status != 200:
                raise CiRefusal(f"{subject} could not be disabled: {sd_fleet._said(answer_status, answer)}")

        steps.append(Step("change", subject, "disable", disable_workflow))
    return steps


# --- the verb --------------------------------------------------------------


FRESH_COMMIT = ("an open pull request whose head already carries a failed check run (one that ran before the "
                "switch, or a billing-blocked one) still refuses to merge; push a fresh commit to it, an empty "
                "one will do, and nothing but the local gate checks it")


def switch_plan(root: pathlib.Path, call: Call, *, database: pathlib.Path | None = None) -> Plan:
    status, repo = call("GET", PREFIX, None)
    if status != 200 or not isinstance(repo, dict) or not repo.get("default_branch"):
        raise CiRefusal(f"the repository could not be read: {sd_fleet._said(status, repo)}")
    rights = repo.get("permissions")
    if not (isinstance(rights, dict) and rights.get("admin") is True):
        raise CiRefusal(f"{repo.get('full_name')}: this token has no admin on the repository, "
                        "so its protection and Actions cannot be changed")
    branch = str(repo["default_branch"])
    private = repo.get("private") is True
    steps = [ci_step(root, database)]
    steps += check_steps(call, branch)
    steps += actions_steps(call, private)
    steps.append(Step("note", "open pull requests", FRESH_COMMIT))
    return Plan(str(repo.get("full_name")), branch, private, steps)


def render_switch(result: Plan, stream: Any, *, applied: bool) -> None:
    visibility = "private" if result.private else "public"
    mode = "applied" if applied else "dry run; --apply writes"
    stream.write(f"sd ci local: {result.repository} ({visibility}), default branch {result.branch} -- {mode}\n")
    for step in result.steps:
        word = "changed" if applied and step.state == "change" else step.state
        stream.write(f"  {word:<8}{step.subject}: {step.detail}\n")
    count = len(result.changes)
    if applied:
        stream.write(f"{count} change(s) made.\n")
    elif count:
        stream.write(f"{count} change(s); run again with --apply to make them.\n")
    else:
        stream.write("Nothing to change.\n")


def ci_local(args: argparse.Namespace, *, call: Call | None = None, stream: Any = None) -> int:
    stream = stream or sys.stdout
    root = sd_lib.repo_root(None)
    if root is None:
        raise CiRefusal("the working directory is not inside a Git repository")
    call = call or gh_call(root)
    result = switch_plan(root, call, database=args.database)
    if args.apply:
        for step in result.changes:
            assert step.write is not None
            step.write()
    if args.json:
        stream.write(json.dumps({"repository": result.repository, "branch": result.branch,
                                 "private": result.private, "applied": bool(args.apply),
                                 "steps": [step.record() for step in result.steps]}, indent=2) + "\n")
    else:
        render_switch(result, stream, applied=bool(args.apply))
    return EXIT_OK


def run_ci_local(args: argparse.Namespace) -> int:
    try:
        return ci_local(args)
    except CiRefusal as refusal:
        print(f"sd ci local: {refusal}", file=sys.stderr)
        return EXIT_REFUSED


def register_ci(groups: Any) -> None:
    ci = groups.add_parser("ci", help="where a repository's checks run")
    verbs = ci.add_subparsers(dest="verb", required=True)
    local = verbs.add_parser(
        "local",
        help=f"switch this repository to local CI: repo.ci, required {CONTEXT}, Actions off; dry run by default")
    local.add_argument("--apply", action="store_true", help="make the changes; without it nothing is written")
    local.add_argument("--json", action="store_true", help="emit one machine-readable object")
    local.add_argument("--database", type=pathlib.Path, help="the sd database; defaults to the operator HOME")
    local.set_defaults(handler=run_ci_local)
