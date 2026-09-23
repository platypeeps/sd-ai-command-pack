"""GitHub transport and fresh merge guards, with no progress tracking writes."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import sd_lib
from sd_ship_workflow import blocked

COPILOT_REVIEWER = "copilot-pull-request-reviewer[bot]"
COPILOT_LOGINS = frozenset({COPILOT_REVIEWER, "copilot-pull-request-reviewer", "copilot"})


class Refusal(Exception):
    """A failed or uncertain prerequisite; never authority to merge."""

    def __init__(self, message: str, *, code: str = "prerequisite_failed", boundary: str = "policy",
                 next_action: str = "Inspect the error and resolve the failed prerequisite.",
                 state: str = "policy_block", approval_required: bool = False):
        self.workflow = blocked(code, boundary, next_action, state=state, approval_required=approval_required)
        super().__init__(message)


def run(root: Path, argv: list[str], *, input: str | None = None, timeout: int = 60) -> str:
    try:
        result = subprocess.run(argv, cwd=root, input=input, text=True,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal(f"{argv[0]} could not finish: {error}", code="command_unavailable", boundary="runtime",
                      state="retryable_failure", next_action="Restore command access, then retry this command.") from None
    if result.returncode:
        raise Refusal((result.stderr or result.stdout or f"{argv[0]} failed").strip()[:2000],
                      code="command_failed", boundary="runtime", state="retryable_failure",
                      next_action="Inspect the command error, resolve its cause, then retry.")
    return result.stdout.strip()


def git(root: Path, *args: str) -> str:
    return run(root, ["git", *args])


def slug(remote: str) -> str:
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?", remote)
    if not match:
        raise Refusal("origin must identify one github.com repository")
    return match[1].lower()


class GitHub:
    def __init__(self, root: Path, repository: str):
        self.root, self.repository = root, repository
        self.prefix = f"repos/{repository}"
        #: What the remote last said to `owned`, so the caller that catches
        #: its refusal can write the demotion note with the same reason.
        self.answer: sd_lib.RemoteAnswer | None = None
        #: The repository object `owned` last read, kept only while it names
        #: this repository, is not a fork and grants admin. `None` otherwise,
        #: including before the first call. `sd-ship`'s merge gate merges
        #: against it when the repository row overrides the co-ownership
        #: answer, so it must never stand for a repository those three
        #: clauses did not clear (sd:1347).
        self.metadata: dict | None = None
        #: Why the last `declared_gap` read found no declaration, for the refusal.
        self.declaration_faults: list[str] = []

    def api(self, path: str, *, method: str = "GET", body: dict | None = None) -> Any:
        argv = ["gh", "api", path, "--method", method]
        if body is not None:
            argv += ["--input", "-"]
        try:
            return json.loads(run(self.root, argv, input=json.dumps(body) if body is not None else None))
        except ValueError:
            raise Refusal("GitHub returned unreadable JSON") from None

    def api_status(self, path: str) -> tuple[int, Any]:
        """`(HTTP status, body)` for a GET whose non-2xx answer is still an answer.

        `api` folds every failure into one refusal, which is right everywhere
        but the protection endpoint: there a 404 means "no protection object",
        a fact the declared-gap rule reads, while a 401, 403 or 5xx means
        "could not observe", which must stay a refusal. The status comes from
        the response line `gh api --include` prints, not from the wording of
        gh's stderr, so a reworded message cannot turn a refusal into a fact.
        """
        argv = ["gh", "api", "--include", path, "--method", "GET"]
        try:
            result = subprocess.run(argv, cwd=self.root, text=True, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            raise Refusal(f"gh could not finish: {error}", code="command_unavailable", boundary="runtime",
                          state="retryable_failure", next_action="Restore command access, then retry this command.") from None
        head, _, body = result.stdout.partition("\n\n")
        match = re.match(r"HTTP/[\d.]+ (\d{3})", head)
        if not match:
            raise Refusal((result.stderr or "gh api returned no HTTP status line").strip()[:2000],
                          code="command_failed", boundary="runtime", state="retryable_failure",
                          next_action="Inspect the command error, resolve its cause, then retry.")
        try:
            return int(match[1]), json.loads(body)
        except ValueError:
            raise Refusal("GitHub returned unreadable JSON") from None

    def pages(self, path: str, field: str | None = None) -> list:
        result = []
        for page in range(1, 101):
            value = self.api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
            rows = value.get(field) if field and isinstance(value, dict) else value
            if not isinstance(rows, list):
                raise Refusal(f"GitHub did not enumerate {path}")
            result.extend(rows)
            if len(rows) < 100:
                return result
        raise Refusal(f"GitHub inventory exceeded the bounded pagination limit: {path}")

    def owned(self) -> dict:
        """Reuse WORKFLOW's three-question predicate with complete pagination."""
        metadata: dict = {}

        def ask(path: str, _root: Path):
            nonlocal metadata
            try:
                path = path.replace("{owner}/{repo}", self.repository)
                if path.endswith("/collaborators"):
                    people = self.pages(path)
                    if any(not isinstance(person, dict) or not isinstance(person.get("permissions"), dict)
                           or type(person["permissions"].get("push")) is not bool for person in people):
                        raise Refusal("GitHub collaborator permissions are incomplete")
                    return people, ""
                value = self.api(path)
                if path == self.prefix:
                    metadata = value
                return value, ""
            except Refusal as error:
                return None, str(error)

        answer = self.answer = sd_lib.remote_permits_full(self.root, ask=ask)
        # Identity, fork and admin are separated from the answer itself so the
        # caller that catches this refusal can still see a repository these
        # three clauses cleared. The disjunction below is unchanged: the same
        # calls refuse, with the same reason (sd:1347).
        self.metadata = metadata if (str(metadata.get("full_name", "")).lower() == self.repository
                                     and metadata.get("fork") is False
                                     and metadata.get("permissions", {}).get("admin") is True) else None
        if not answer.full or self.metadata is None:
            raise Refusal(answer.reason or "GitHub ownership did not match origin", code="ownership_refused",
                          next_action="Resolve repository ownership or use the existing authorized manual workflow.")
        return metadata

    def pull(self, number: int) -> dict:
        value = self.api(f"{self.prefix}/pulls/{number}")
        if not isinstance(value, dict) or value.get("number") != number:
            raise Refusal("GitHub did not return the requested pull request")
        return value

    @staticmethod
    def is_copilot(record: object) -> bool:
        if not isinstance(record, dict):
            return False
        user = record.get("user")
        login = str(user.get("login") or "").lower() if isinstance(user, dict) else ""
        return login in COPILOT_LOGINS

    @classmethod
    def copilot_reviews(cls, reviews: list) -> list[dict]:
        return [review for review in reviews if cls.is_copilot(review)]

    @classmethod
    def copilot_comments(cls, comments: list) -> list[dict]:
        return [comment for comment in comments if cls.is_copilot(comment)]

    @staticmethod
    def copilot_requested(pull: dict) -> bool:
        requested = pull.get("requested_reviewers") or []
        return any(isinstance(reviewer, dict)
                   and str(reviewer.get("login") or "").lower() in COPILOT_LOGINS
                   for reviewer in requested)

    @classmethod
    def copilot_review_status(cls, pull: dict, reviews: list, head: str) -> str:
        """Return the exact-head Copilot review state without another request."""
        for review in cls.copilot_reviews(reviews):
            state = str(review.get("state") or "").upper()
            if (review.get("commit_id") == head
                    and bool(review.get("submitted_at")) and state not in ("", "PENDING")):
                return "completed"
        if cls.copilot_requested(pull):
            return "pending"
        return "absent"

    def request_copilot_review(self, number: int) -> None:
        """Request one Copilot review through GitHub's reviewer endpoint."""
        self.api(f"{self.prefix}/pulls/{number}/requested_reviewers", method="POST",
                 body={"reviewers": [COPILOT_REVIEWER]})

    def protection_observed(self, base: str) -> tuple[int, Any]:
        return self.api_status(f"{self.prefix}/branches/{quote(base, safe='')}/protection")

    def protection(self, base: str) -> dict:
        status, value = self.protection_observed(base)
        if status != 200:
            message = value.get("message") if isinstance(value, dict) else None
            raise Refusal(f"{message or 'branch protection could not be observed'} (HTTP {status})")
        return self.validate_protection(value)

    @staticmethod
    def validate_protection(value: Any) -> dict:
        if not isinstance(value, dict):
            raise Refusal("branch protection could not be observed")
        checks = value.get("required_status_checks") or {}
        if value.get("enforce_admins", {}).get("enabled") is not True:
            raise Refusal("branch protection does not enforce administrators", code="protection_required",
                          next_action="Restore required branch protection; this command cannot bypass it.")
        if not isinstance(value.get("required_pull_request_reviews"), dict):
            raise Refusal("branch protection does not require pull requests")
        if checks.get("strict") is not True or not (checks.get("contexts") or checks.get("checks")):
            raise Refusal("branch protection requires strict, named CI checks")
        allowances = value["required_pull_request_reviews"].get("bypass_pull_request_allowances") or {}
        if any(allowances.get(name) for name in ("users", "teams", "apps")):
            raise Refusal("pull-request protection has bypass allowances")
        return value

    def declared_gap(self, head: str) -> dict | None:
        """The `unprotected` acceptance at `head`, or `None` with the reasons.

        Read from the reviewed commit and never from the working tree: a
        declaration nobody reviewed cannot let a merge through. One parser,
        `sd_lib.parse_acknowledgements`, is what `sd-status` reads the working
        tree with. The entry must name the id *and* pin exactly the fact this
        branch state has, `{"branch_protection": false}`; an entry for another
        gap that pins the same fact accepts that gap, not this one.
        """
        where = sd_lib.ACKNOWLEDGEMENT_RELATIVE_PATH.as_posix()
        try:
            text = git(self.root, "show", f"{head}:{where}")
        except Refusal:
            self.declaration_faults = [f"{where} is not in the tree at {head[:12]}"]
            return None
        entries, problems = sd_lib.parse_acknowledgements(text)
        if problems:
            self.declaration_faults = problems
            return None
        for entry in entries:
            if entry["id"] == "unprotected" and entry["state"] == {"branch_protection": False}:
                self.declaration_faults = []
                return {"declared_gap": entry["id"], "until": entry["until"]}
        self.declaration_faults = [f"{where} at {head[:12]} carries no `unprotected` entry pinning branch_protection: false"]
        return None

    def gate(self, base: str, head: str) -> dict:
        """What stands between this merge and `main`: the object, or the gap.

        Only HTTP 404 is "absent". Anything else that is not 200 is "could
        not observe" and refuses as `protection` always has.
        """
        status, value = self.protection_observed(base)
        declaration = self.declared_gap(head)
        if status == 200:
            if declaration is not None:
                raise Refusal(f"{sd_lib.ACKNOWLEDGEMENT_RELATIVE_PATH} at {head[:12]} declares main unprotected, "
                              "but GitHub returns a protection object; the declaration does not match the observed state")
            return self.validate_protection(value)
        if status == 404 and declaration is not None:
            return declaration
        message = value.get("message") if isinstance(value, dict) else None
        detail = "; ".join(self.declaration_faults) if status == 404 else ""
        raise Refusal(f"{message or 'branch protection could not be observed'} (HTTP {status})"
                      + (f"; {detail}" if detail else ""),
                      code="protection_required" if status == 404 else "prerequisite_failed",
                      next_action="Restore branch protection, or declare the accepted gap in "
                                  f"{sd_lib.ACKNOWLEDGEMENT_RELATIVE_PATH} at the reviewed commit.")

    def expected_workflows(self, head: str) -> list[tuple[str, str]]:
        """`(path, name)` for every workflow at `head` whose `on` includes `pull_request`.

        Enumerated from the tree at merge time, `AGENTS.md`'s doctrine: a
        workflow added at `head` is expected at `head`, one deleted there is
        not, and the working tree has no say. `pull_request_target` is left
        out on purpose: its runs carry that event name and never match the
        `event=pull_request` query, so expecting one would refuse every merge.
        A `branches`, `paths` or `types` filter under the trigger is not
        read: the item's requirement 2 makes a workflow that did not run for
        the event a refusal naming it, never a pass, and reconstructing
        GitHub's scheduling here would be a second matcher whose every
        divergence from the real one is a merge without the run (the
        verification pass found two in one attempt). A trigger that is not
        spelled like an event name is a construct this reader could not
        resolve, and that refuses rather than drops the file.
        """
        directory = ".github/workflows"
        try:
            listing = git(self.root, "ls-tree", "--name-only", head, f"{directory}/")
        except Refusal:
            return []
        expected = []
        for path in sorted(line.strip() for line in listing.splitlines() if line.strip()):
            if not path.endswith((".yml", ".yaml")):
                continue
            lines = sd_lib.yaml_lines(git(self.root, "show", f"{head}:{path}"))
            triggers = sd_lib.workflow_triggers(lines)
            block = sd_lib.workflow_trigger_block(lines)
            unresolved = sorted(name for name in triggers if not sd_lib.EVENT_NAME_RE.match(name))
            unresolved += sorted(line.strip() for line in sd_lib.yaml_unreadable(block or []))
            if not triggers or unresolved:
                raise Refusal(f"{path} at {head[:12]}: could not read its triggers"
                              + (f" ({', '.join(repr(name) for name in unresolved)})" if unresolved else "")
                              + ", so whether it validates a pull request is unknown", code="ci_missing", boundary="ci")
            if "pull_request" in triggers:
                expected.append((path, sd_lib.yaml_field(lines, "name") or path.rsplit("/", 1)[-1]))
        return expected

    def every_check(self, head: str) -> None:
        """The substitute for required checks under a declared gap: all of them.

        Every check run `filter=latest` reports at `head` must have completed
        `success`, `neutral` or `skipped`; the newest status per context must
        be `success`; the set must not be empty; and every workflow at `head`
        that runs on `pull_request` must have a completed, successful run for
        that event at this exact SHA, so a commit the Tests workflow never ran
        on cannot pass on an advisory check alone.
        """
        runs = self.pages(f"{self.prefix}/commits/{head}/check-runs?filter=latest", "check_runs")
        statuses = self.pages(f"{self.prefix}/commits/{head}/statuses")
        if not runs and not statuses:
            raise Refusal(f"nothing validated {head}: no check run and no status exists for it", code="ci_missing",
                          next_action="Run the repository's checks for this exact head, then retry merge.", boundary="ci", state="retryable_failure")
        for entry in runs:
            if (entry.get("head_sha") != head or entry.get("status") != "completed"
                    or entry.get("conclusion") not in ("success", "neutral", "skipped")):
                raise Refusal(f"CI is not passing on {head}: {entry.get('name')}", code="ci_not_passing",
                              next_action="Wait for or fix exact-head CI, then retry merge.", boundary="ci", state="retryable_failure")
        newest: dict[str, dict] = {}
        for entry in statuses:  # newest first, so the first record per context is the current one
            newest.setdefault(str(entry.get("context")), entry)
        for context, entry in newest.items():
            if entry.get("sha", head) != head or entry.get("state") != "success":
                raise Refusal(f"status is not passing on {head}: {context}", code="ci_not_passing",
                              next_action="Wait for or fix exact-head CI, then retry merge.", boundary="ci", state="retryable_failure")
        pull_request_runs = self.pages(f"{self.prefix}/actions/runs?head_sha={head}&event=pull_request", "workflow_runs")
        for path, name in self.expected_workflows(head):
            if not any(run.get("path") == path and run.get("head_sha") == head and run.get("event") == "pull_request"
                       and run.get("status") == "completed" and run.get("conclusion") == "success"
                       for run in pull_request_runs):
                raise Refusal(f"workflow {name} ({path}) has no successful pull_request run on {head}", code="ci_missing",
                              next_action="Run the workflow for this exact head, then retry merge.", boundary="ci", state="retryable_failure")

    def commits_behind(self, base: str, head: str) -> int | None:
        """How many commits of `base` are missing from `head`, GitHub's count."""
        return self.api(f"{self.prefix}/compare/{quote(base, safe='')}...{head}").get("behind_by")

    def ready(self, pull: dict, head: str, base: str, protection: dict) -> None:
        if pull.get("merged") is True or pull.get("state") != "open" or pull.get("draft") is not False:
            raise Refusal("pull request is not open and ready")
        if pull.get("head", {}).get("sha") != head or pull.get("base", {}).get("ref") != base:
            raise Refusal("pull-request head or default base moved after local review")
        if str(pull.get("head", {}).get("repo", {}).get("full_name", "")).lower() != self.repository:
            raise Refusal("pull request comes from a different repository")
        if pull.get("mergeable") is not True or pull.get("mergeable_state") != "clean":
            raise Refusal("GitHub has not confirmed all required merge rules are satisfied")
        if self.commits_behind(base, head) != 0:
            raise Refusal("the reviewed branch is behind the current default branch")
        if "declared_gap" in protection:
            self.every_check(head)
            return
        runs = self.pages(f"{self.prefix}/commits/{head}/check-runs?filter=latest", "check_runs")
        statuses = self.pages(f"{self.prefix}/commits/{head}/statuses")
        required = protection["required_status_checks"]
        bindings = {entry["context"]: entry.get("app_id", -1) for entry in required.get("checks", [])}
        for context in required.get("contexts", []):
            bindings.setdefault(context, -1)
        for context, app in bindings.items():
            matching = [entry for entry in runs if entry.get("name") == context
                        and (app in (-1, None) or entry.get("app", {}).get("id") == app)]
            legacy = [entry for entry in statuses if entry.get("context") == context] if app in (-1, None) else []
            # The statuses endpoint is newest first. A successful old rerun
            # cannot mask a failed or pending current run of the same check.
            if any(entry.get("head_sha") != head or entry.get("status") != "completed"
                   or entry.get("conclusion") not in ("success", "neutral", "skipped") for entry in matching):
                raise Refusal(f"required CI is not passing on {head}: {context}", code="ci_not_passing",
                              boundary="ci", state="retryable_failure", next_action="Wait for or fix exact-head CI, then retry merge.")
            if legacy and (legacy[0].get("sha", head) != head or legacy[0].get("state") != "success"):
                raise Refusal(f"required status is not passing on {head}: {context}")
            if not matching and not legacy:
                raise Refusal(f"required CI has no current result on {head}: {context}", code="ci_missing",
                              boundary="ci", state="retryable_failure", next_action="Run the required check for this exact head, then retry merge.")
