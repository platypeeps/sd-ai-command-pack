"""GitHub transport and fresh merge guards, with no progress tracking writes."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import sd_lib


class Refusal(Exception):
    """A failed or uncertain prerequisite; never authority to merge."""


def run(root: Path, argv: list[str], *, input: str | None = None, timeout: int = 60) -> str:
    try:
        result = subprocess.run(argv, cwd=root, input=input, text=True,
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal(f"{argv[0]} could not finish: {error}") from None
    if result.returncode:
        raise Refusal((result.stderr or result.stdout or f"{argv[0]} failed").strip()[:2000])
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

    def api(self, path: str, *, method: str = "GET", body: dict | None = None) -> Any:
        argv = ["gh", "api", path, "--method", method]
        if body is not None:
            argv += ["--input", "-"]
        try:
            return json.loads(run(self.root, argv, input=json.dumps(body) if body is not None else None))
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

        answer = sd_lib.remote_permits_full(self.root, ask=ask)
        if (not answer.full or str(metadata.get("full_name", "")).lower() != self.repository
                or metadata.get("fork") is not False or metadata.get("permissions", {}).get("admin") is not True):
            raise Refusal(answer.reason or "GitHub ownership did not match origin")
        return metadata

    def pull(self, number: int) -> dict:
        value = self.api(f"{self.prefix}/pulls/{number}")
        if not isinstance(value, dict) or value.get("number") != number:
            raise Refusal("GitHub did not return the requested pull request")
        return value

    def protection(self, base: str) -> dict:
        value = self.api(f"{self.prefix}/branches/{quote(base, safe='')}/protection")
        if not isinstance(value, dict):
            raise Refusal("branch protection could not be observed")
        checks = value.get("required_status_checks") or {}
        if value.get("enforce_admins", {}).get("enabled") is not True:
            raise Refusal("branch protection does not enforce administrators")
        if not isinstance(value.get("required_pull_request_reviews"), dict):
            raise Refusal("branch protection does not require pull requests")
        if checks.get("strict") is not True or not (checks.get("contexts") or checks.get("checks")):
            raise Refusal("branch protection requires strict, named CI checks")
        allowances = value["required_pull_request_reviews"].get("bypass_pull_request_allowances") or {}
        if any(allowances.get(name) for name in ("users", "teams", "apps")):
            raise Refusal("pull-request protection has bypass allowances")
        return value

    def ready(self, pull: dict, head: str, base: str, protection: dict) -> None:
        if pull.get("merged") is True or pull.get("state") != "open" or pull.get("draft") is not False:
            raise Refusal("pull request is not open and ready")
        if pull.get("head", {}).get("sha") != head or pull.get("base", {}).get("ref") != base:
            raise Refusal("pull-request head or default base moved after local review")
        if str(pull.get("head", {}).get("repo", {}).get("full_name", "")).lower() != self.repository:
            raise Refusal("pull request comes from a different repository")
        if pull.get("mergeable") is not True or pull.get("mergeable_state") != "clean":
            raise Refusal("GitHub has not confirmed all required merge rules are satisfied")
        comparison = self.api(f"{self.prefix}/compare/{quote(base, safe='')}...{head}")
        if comparison.get("behind_by") != 0:
            raise Refusal("the reviewed branch is behind the current default branch")
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
                raise Refusal(f"required CI is not passing on {head}: {context}")
            if legacy and (legacy[0].get("sha", head) != head or legacy[0].get("state") != "success"):
                raise Refusal(f"required status is not passing on {head}: {context}")
            if not matching and not legacy:
                raise Refusal(f"required CI has no current result on {head}: {context}")
