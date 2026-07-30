#!/usr/bin/env python3
"""Classify whether an exact CI head is a verified bookkeeping successor."""

# REHEARSAL ARTIFACT -- A-038 AC1. This comment exists only to make this file's
# blob differ from the base branch's, which is the condition the identity guard
# in .github/workflows/tests.yml tests. Delete this branch after the rehearsal.

from __future__ import annotations

import argparse
import json
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

SCHEMA_VERSION = 1
MAX_CHANGED_PATHS = 1000
MAX_COMMITS = 100
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
MAX_PATH_BYTES = 300
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RAW_DIFF_RE = re.compile(
    rb"^:([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40,64}) "
    rb"([0-9a-f]{40,64}) ([A-Z])$"
)
ALLOWED_PATH_PREFIXES = (".trellis/tasks/", ".trellis/workspace/")
ALLOWED_TREE_MODES = {"000000", "100644"}


class ScopeClassifierError(RuntimeError):
    """Raised when the classifier itself cannot produce a trustworthy decision."""


class HistoryIneligible(ValueError):
    """Raised when bounded history evidence safely selects full CI."""


@dataclass(frozen=True)
class PriorEvidence:
    run_id: int
    check_run_id: int
    scope: str


@dataclass(frozen=True)
class HistoryEvidence:
    commit_count: int
    changed_paths: tuple[str, ...]
    validation_mode: str


def _bounded_sha(value: str) -> str | None:
    return value if SHA_RE.fullmatch(value) else None


def _decision(
    *,
    mode: str,
    reason_code: str,
    before_sha: str,
    after_sha: str,
    evidence_scope: str,
    prior: PriorEvidence | None = None,
    history: HistoryEvidence | None = None,
    disallowed_paths: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": "bookkeeping-ci-scope",
        "mode": mode,
        "reasonCode": reason_code,
        "beforeSha": _bounded_sha(before_sha),
        "afterSha": _bounded_sha(after_sha),
        "evidenceRunId": prior.run_id if prior else None,
        "evidenceCheckRunId": prior.check_run_id if prior else None,
        "evidenceScope": evidence_scope,
        "validationMode": history.validation_mode if history else "none",
        "commitCount": history.commit_count if history else 0,
        "changedPaths": list(history.changed_paths) if history else [],
        "disallowedPaths": list(disallowed_paths[:20]),
    }


def _run_git(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ScopeClassifierError("git command could not start") from exc


def _git_stdout(repo: Path, args: Sequence[str]) -> bytes:
    result = _run_git(repo, args)
    if result.returncode != 0:
        raise ScopeClassifierError(
            f"git {' '.join(args[:2])} failed with exit status {result.returncode}"
        )
    return result.stdout


def _commit_exists(repo: Path, sha: str) -> bool:
    return _run_git(repo, ["cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0


def _safe_path(path: str) -> bool:
    if not path or len(path.encode("utf-8")) > MAX_PATH_BYTES:
        return False
    if (
        path.startswith("/")
        or "\\" in path
        or "//" in path
        or any(ord(character) < 32 or ord(character) == 127 for character in path)
    ):
        return False
    parts = PurePosixPath(path).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def _decode_paths(raw: bytes) -> tuple[str, ...]:
    try:
        paths = tuple(item.decode("utf-8", errors="strict") for item in raw.split(b"\0") if item)
    except UnicodeDecodeError as exc:
        raise HistoryIneligible("changed_path_non_utf8") from exc
    if len(paths) > MAX_CHANGED_PATHS:
        raise HistoryIneligible("changed_path_set_oversized")
    return paths


def _raw_tree_entries(repo: Path, before_sha: str, after_sha: str) -> dict[str, tuple[str, str, str]]:
    raw = _git_stdout(
        repo,
        ["diff", "--raw", "--no-renames", "--no-abbrev", "-z", before_sha, after_sha, "--"],
    )
    tokens = raw.split(b"\0")
    entries: dict[str, tuple[str, str, str]] = {}
    index = 0
    while index < len(tokens) and tokens[index]:
        header = tokens[index]
        index += 1
        if index >= len(tokens) or not tokens[index]:
            raise ScopeClassifierError("git returned a malformed raw diff")
        match = RAW_DIFF_RE.fullmatch(header)
        if match is None:
            raise ScopeClassifierError("git returned an unsupported raw diff record")
        try:
            path = tokens[index].decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ScopeClassifierError("git returned a non-UTF-8 raw diff path") from exc
        index += 1
        if path in entries:
            raise ScopeClassifierError("git returned a duplicate raw diff path")
        entries[path] = (
            match.group(1).decode("ascii"),
            match.group(2).decode("ascii"),
            match.group(5).decode("ascii"),
        )
    return entries


def classify_history(repo: Path, before_sha: str, after_sha: str) -> tuple[HistoryEvidence | None, str, tuple[str, ...]]:
    if not SHA_RE.fullmatch(before_sha):
        return None, "before_sha_invalid", ()
    if not SHA_RE.fullmatch(after_sha):
        return None, "after_sha_invalid", ()
    if not _commit_exists(repo, before_sha) or not _commit_exists(repo, after_sha):
        return None, "commit_object_unavailable", ()

    checked_out = _git_stdout(repo, ["rev-parse", "--verify", "HEAD^{commit}"]).decode("ascii").strip()
    if checked_out != after_sha:
        return None, "after_head_mismatch", ()

    ancestry = _run_git(repo, ["merge-base", "--is-ancestor", before_sha, after_sha])
    if ancestry.returncode == 1:
        return None, "history_not_ancestor", ()
    if ancestry.returncode != 0:
        raise ScopeClassifierError("git merge-base could not inspect ancestry")

    commits_text = _git_stdout(
        repo,
        ["rev-list", "--parents", "--reverse", f"{before_sha}..{after_sha}"],
    ).decode("ascii", errors="strict")
    commit_rows = [line.split() for line in commits_text.splitlines() if line.strip()]
    if not commit_rows:
        return None, "empty_commit_range", ()
    if len(commit_rows) > MAX_COMMITS:
        return None, "history_oversized", ()
    if any(len(row) != 2 for row in commit_rows):
        return None, "history_contains_merge", ()

    try:
        paths = _decode_paths(
            _git_stdout(
                repo,
                [
                    "diff",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    before_sha,
                    after_sha,
                    "--",
                ],
            )
        )
    except HistoryIneligible as exc:
        return None, str(exc), ()
    if not paths:
        return None, "empty_changed_path_set", ()
    unsafe_paths = tuple(path for path in paths if not _safe_path(path))
    if unsafe_paths:
        return None, "changed_path_invalid", unsafe_paths
    disallowed = tuple(
        path for path in paths if not path.startswith(ALLOWED_PATH_PREFIXES)
    )
    if disallowed:
        return None, "changed_path_not_bookkeeping", disallowed

    entries = _raw_tree_entries(repo, before_sha, after_sha)
    if set(entries) != set(paths):
        raise ScopeClassifierError("git path and tree-mode evidence disagree")
    unsafe_entries = tuple(
        path
        for path, (old_mode, new_mode, change_type) in entries.items()
        if old_mode not in ALLOWED_TREE_MODES
        or new_mode not in ALLOWED_TREE_MODES
        or change_type not in {"A", "M", "D"}
    )
    if unsafe_entries:
        return None, "tree_entry_unsafe", unsafe_entries

    has_archive = any(path.startswith(".trellis/tasks/archive/") for path in paths)
    has_workspace = any(path.startswith(".trellis/workspace/") for path in paths)
    validation_mode = "completion" if has_archive else "planning" if has_workspace else "none"
    return (
        HistoryEvidence(
            commit_count=len(commit_rows),
            changed_paths=tuple(sorted(paths)),
            validation_mode=validation_mode,
        ),
        "verified_bookkeeping_delta",
        (),
    )


def _load_evidence(path: Path, collection_key: str) -> list[Any]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError("evidence file is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("evidence path is not a regular file")
    if metadata.st_size > MAX_EVIDENCE_BYTES:
        raise ValueError("evidence file is oversized")
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("evidence file is not valid JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get(collection_key), list):
        raise ValueError("evidence JSON has an invalid shape")
    return payload[collection_key]


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def find_prior_evidence(
    *,
    runs: Sequence[Any],
    checks: Sequence[Any],
    before_sha: str,
    event_name: str,
    pr_number: int | None,
    protected_ref: str,
) -> PriorEvidence | None:
    scope = f"pull_request:{pr_number}" if event_name == "pull_request" else f"ref:{protected_ref}"
    matching_runs: list[tuple[int, dict[str, Any]]] = []
    for item in runs:
        if not isinstance(item, dict):
            continue
        run_id = _positive_int(item.get("id"))
        if run_id is None:
            continue
        if (
            item.get("name") != "Tests"
            or item.get("path") != ".github/workflows/tests.yml"
            or item.get("head_sha") != before_sha
            or item.get("status") != "completed"
            or item.get("conclusion") != "success"
            or item.get("event") != event_name
        ):
            continue
        if event_name == "pull_request":
            pull_requests = item.get("pull_requests")
            if not isinstance(pull_requests, list) or not any(
                isinstance(pr, dict) and pr.get("number") == pr_number
                for pr in pull_requests
            ):
                continue
        elif item.get("head_branch") != protected_ref.removeprefix("refs/heads/"):
            continue
        matching_runs.append((run_id, item))

    for run_id, _run in sorted(matching_runs, key=lambda row: row[0], reverse=True):
        marker = f"/actions/runs/{run_id}/"
        matching_checks: list[int] = []
        for item in checks:
            if not isinstance(item, dict):
                continue
            check_id = _positive_int(item.get("id"))
            app = item.get("app")
            if (
                check_id is None
                or item.get("name") != "CI Result"
                or item.get("head_sha") != before_sha
                or item.get("status") != "completed"
                or item.get("conclusion") != "success"
                or not isinstance(app, dict)
                or app.get("slug") != "github-actions"
                or not isinstance(item.get("details_url"), str)
                or marker not in item["details_url"]
            ):
                continue
            matching_checks.append(check_id)
        if matching_checks:
            return PriorEvidence(
                run_id=run_id,
                check_run_id=max(matching_checks),
                scope=scope,
            )
    return None


def classify(args: argparse.Namespace) -> dict[str, Any]:
    before_sha = args.before_sha.lower()
    after_sha = args.after_sha.lower()
    if args.event_name == "pull_request":
        scope = f"pull_request:{args.pr_number}" if args.pr_number else "pull_request:unknown"
        if args.event_action != "synchronize":
            return _decision(
                mode="full",
                reason_code="pull_request_action_not_synchronize",
                before_sha=before_sha,
                after_sha=after_sha,
                evidence_scope=scope,
            )
        if args.pr_number is None or args.pr_number <= 0:
            return _decision(
                mode="full",
                reason_code="pull_request_identity_invalid",
                before_sha=before_sha,
                after_sha=after_sha,
                evidence_scope=scope,
            )
    elif args.event_name == "push":
        scope = f"ref:{args.protected_ref}"
        if args.protected_ref != "refs/heads/main":
            return _decision(
                mode="full",
                reason_code="push_ref_not_supported",
                before_sha=before_sha,
                after_sha=after_sha,
                evidence_scope=scope,
            )
    else:
        return _decision(
            mode="full",
            reason_code="event_not_supported",
            before_sha=before_sha,
            after_sha=after_sha,
            evidence_scope=f"event:{args.event_name or 'unknown'}",
        )

    history, history_reason, disallowed = classify_history(
        args.repo.resolve(), before_sha, after_sha
    )
    if history is None:
        return _decision(
            mode="full",
            reason_code=history_reason,
            before_sha=before_sha,
            after_sha=after_sha,
            evidence_scope=scope,
            disallowed_paths=disallowed,
        )

    if not args.evidence_available:
        return _decision(
            mode="full",
            reason_code="prior_evidence_unavailable",
            before_sha=before_sha,
            after_sha=after_sha,
            evidence_scope=scope,
            history=history,
        )
    try:
        runs = _load_evidence(args.runs_json, "workflow_runs")
        checks = _load_evidence(args.checks_json, "check_runs")
    except ValueError:
        return _decision(
            mode="full",
            reason_code="prior_evidence_invalid",
            before_sha=before_sha,
            after_sha=after_sha,
            evidence_scope=scope,
            history=history,
        )

    prior = find_prior_evidence(
        runs=runs,
        checks=checks,
        before_sha=before_sha,
        event_name=args.event_name,
        pr_number=args.pr_number,
        protected_ref=args.protected_ref,
    )
    if prior is None:
        return _decision(
            mode="full",
            reason_code="prior_success_missing",
            before_sha=before_sha,
            after_sha=after_sha,
            evidence_scope=scope,
            history=history,
        )
    return _decision(
        mode="bookkeeping",
        reason_code="verified_bookkeeping_successor",
        before_sha=before_sha,
        after_sha=after_sha,
        evidence_scope=scope,
        prior=prior,
        history=history,
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select full or bookkeeping CI for one exact GitHub event head."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--event-name", required=True, choices=("pull_request", "push"))
    parser.add_argument("--event-action", default="")
    parser.add_argument("--before-sha", required=True)
    parser.add_argument("--after-sha", required=True)
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--protected-ref", default="refs/heads/main")
    parser.add_argument("--runs-json", type=Path, required=True)
    parser.add_argument("--checks-json", type=Path, required=True)
    parser.add_argument(
        "--evidence-available",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if not args.repo.is_dir():
            raise ScopeClassifierError("repository path is not a directory")
        decision = classify(args)
    except ScopeClassifierError as exc:
        print(f"bookkeeping CI scope error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(decision, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
