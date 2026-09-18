"""Shared review gates after explicit identity resolution.

This context performs no item lookup and constructs no publication client.
Adapters supply identity and history; the existing provider executable owns routing.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

import sd_ship_dispositions
from sd_ship_history import completed_depth, digest
from sd_ship_remote import Refusal, git


class ReviewTimeout(Exception):
    def __init__(self, diagnostic: dict):
        self.diagnostic = diagnostic
        super().__init__("local review watchdog expired")


@dataclass(frozen=True)
class ReviewRuntime:
    binding: Callable[[pathlib.Path], str]
    process: Callable[..., subprocess.CompletedProcess]
    current_head: Callable[[pathlib.Path], str]
    clock: Callable[[], str]
    timing_plan: Callable[[subprocess.CompletedProcess], dict]
    bin_dir: pathlib.Path
    setup_seconds: int
    diagnostic_bytes: int


def complete_report(last: dict, head: str, reviewed_head: str | None) -> dict:
    report = last.get("report") or {}
    blocked = report.get("status") == "blocking"
    if (last.get("head") != head or report.get("subject", {}).get("head") != head
            or (reviewed_head != head and not blocked)
            or report.get("status") not in ("clean", "advisory", "blocking")
            or (report.get("check") or {}).get("status") != "pass"
            or not completed_depth(report)):
        raise Refusal("local review receipt is incomplete or does not name this exact head")
    if blocked and (last.get("exit_code") != 1 or last.get("execution_error")
                    or report.get("scope") != "branch" or report.get("dry_run") or report.get("explain_only")):
        raise Refusal("local review receipt is incomplete or does not name this exact head")
    return report


def validate_findings(report: dict) -> None:
    findings = report.get("findings")
    if not isinstance(findings, list) or any(not isinstance(row, dict) or row.get("disposition") not in ("blocking", "advisory") for row in findings):
        raise Refusal("local review findings are malformed")
    if report.get("status") != "blocking" and any(row["disposition"] == "blocking" for row in findings):
        raise Refusal("local review status contradicts its blocking findings")


class SharedReview:
    def __init__(self, root: pathlib.Path, connection, database: pathlib.Path, args, *, store,
                 repository: str, branch: str, head: str, key: str, revision, state: dict,
                 identity: Any, history: Any, runtime: ReviewRuntime):
        self.store, self.root, self.connection, self.args = store, root, connection, args
        self.database, self.repository, self.branch = database, repository, branch
        self.source_head, self.key, self.revision, self.state = head, key, revision, state
        self.identity, self.history, self.runtime = identity, history, runtime

    def save(self, **updates) -> None:
        self.state.update(updates)
        self.revision = self.store.save(self.connection, self.key, self.revision, self.history.stamp(self.state))

    def result(self, phase: str, **extra) -> dict:
        return self.identity.result_fields(phase, self.state, self.runtime.clock(), extra)

    def review_inputs(self, head: str) -> dict:
        passes = self.history.native(self.state)
        if not passes:
            raise Refusal("no completed local review receipt for this head")
        if self.state.get("binding") != self.runtime.binding(self.root):
            raise Refusal("review tools or repository policy changed after review")
        report = complete_report(passes[-1], head, self.state.get("reviewed_head"))
        self.history.validate_coverage(self.state, report)
        validate_findings(report)
        return report

    def check_review(self, head: str, *, refresh_adjudication: bool = False) -> dict | None:
        if self.review_inputs(head)["status"] == "blocking":
            clearance = sd_ship_dispositions.accepted(self, head)
            if not refresh_adjudication and self.state.get("review_clearance") != clearance:
                raise Refusal("accepted dispositions changed; prepare again before publishing or merging")
            return clearance
        return None

    def adjudicate(self) -> dict:
        return sd_ship_dispositions.adjudicate(self)

    def additional_request(self, head: str, passes: list[dict]) -> dict | None:
        if passes != self.history.native(self.state):
            raise Refusal("additional review must use the complete stored native history")
        args = self.args
        if all(value is None for value in (args.additional_review_for, args.request_reason, args.review_history_digest)):
            return None
        reason = (args.request_reason or "").strip()
        if (args.additional_review_for != head or not reason or args.retry_review
                or args.path or args.message_file or args.author):
            raise Refusal("additional review needs an exact committed head and nonempty reason, without retry or commit flags")
        self.request_history(args.review_history_digest)
        if self.runtime.current_head(self.root) != head:
            raise Refusal("additional review must name the clean current HEAD")
        return {"head": head, "reason": reason, "recorded_at": self.runtime.clock(), "allowed_passes": 1,
                "prior_history_digest": self.history.history_digest(self.state),
                "operator_context": "untrusted assertion, not proof of user approval", **self.history.request_fields(self.state)}

    def request_history(self, supplied_digest: str | None) -> None:
        spent = self.history.spent(self.state)
        continuation = self.history.requires_continuation(self.state)
        history_digest = self.history.history_digest(self.state)
        if spent < 2 and not continuation:
            raise Refusal("additional review requires two spent passes")
        if spent == 2 and not continuation and supplied_digest is not None:
            raise Refusal("--review-history-digest renews only after at least three spent passes")
        if (spent >= 3 or continuation) and supplied_digest != history_digest:
            raise Refusal(f"renewal requires --review-history-digest {history_digest} for the complete current history; each digest is spent once")
        self.history.validate_requests(self.state)
        self.history.aggregate(self.state)

    def reusable_review(self, head: str, prior: dict, retry: bool, additional: bool) -> bool:
        if additional:
            return False
        if not retry and prior.get("status") == "blocking" and prior.get("subject", {}).get("head") == head:
            clearance = self.check_review(head, refresh_adjudication=True)
            self.save(reviewed_head=head, review_clearance=clearance)
            return True
        if self.state.get("reviewed_head") == head and (not retry or completed_depth(prior)):
            self.check_review(head)
            return True
        return False

    def validate_dispatch(self, head: str, prior: dict, retry: bool, additional: bool) -> None:
        passes = self.history.native(self.state)
        if not additional and (self.history.spent(self.state) >= 2 or self.history.requires_continuation(self.state)):
            raise Refusal("one code review and one fix verification are spent; further review requires an explicit new request")
        if retry and (not passes or completed_depth(prior)):
            raise Refusal("--retry-review can continue only an incomplete initial review")
        if passes and not retry and not additional:
            if not completed_depth(prior):
                raise Refusal("the preceding review did not complete its requested depth; use --retry-review for a full-branch retry")
            if passes[-1].get("head") == head:
                raise Refusal("this head was already reviewed; address its findings before the fix verification")
        for previous in self.history.ancestry_heads(self.state):
            git(self.root, "merge-base", "--is-ancestor", previous, head)

    def review(self, head: str) -> None:
        passes = self.history.native(self.state)
        prior = self.history.prior(self.state)
        retry = bool(self.args.retry_review)
        request = self.additional_request(head, passes)
        additional = request is not None
        if additional:
            prior = self.history.aggregate(self.state)
        if self.reusable_review(head, prior, retry, additional):
            return
        self.validate_dispatch(head, prior, retry, additional)
        base = passes[-1]["head"] if passes and not (retry or additional) else None
        argv = [sys.executable, str(self.runtime.bin_dir / "sd-review"), "--scope", "branch", "--challenge", "--json", "--database", str(self.database)]
        if base:
            argv += ["--base", base]
        passes.append({"head": head, "started_at": self.runtime.clock(), "base": base, "retry": retry})
        if request:
            passes[-1]["additional_review_request"] = request
        with tempfile.TemporaryDirectory(prefix="sd-ship-verify-") as directory:
            if prior:
                prior_path = pathlib.Path(directory) / "prior-review.json"
                prior_path.write_text(json.dumps(prior, sort_keys=True))
                argv += ["--resume-report" if retry or additional else "--verify-report", str(prior_path)]
            result = self.execute_review(argv, head, passes)
        self.record_review(result, head, passes)

    def preflight_diagnostic(self, planned: subprocess.CompletedProcess) -> dict:
        diagnostic: dict = {"kind": "invalid_timing_plan", "stage": "planning", "exit_code": planned.returncode}
        limit = self.runtime.diagnostic_bytes
        for name in ("stdout", "stderr"):
            data = getattr(planned, name).encode("utf-8", "replace")
            diagnostic[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                "tail": data[-limit:].decode("utf-8", "replace"), "truncated": len(data) > limit}
        return diagnostic

    def execute_review(self, argv: list[str], head: str, passes: list[dict]) -> subprocess.CompletedProcess:
        stage = "planning"
        try:
            planned = self.runtime.process(self.root, argv + ["--explain"], timeout=self.runtime.setup_seconds)
            try:
                plan = self.runtime.timing_plan(planned)
            except Refusal:
                self.save(review_preflight_error=self.preflight_diagnostic(planned))
                raise
            self.save(passes=passes, phase="reviewing", head=head, binding=self.runtime.binding(self.root), review_preflight_error=None, review_clearance=None)
            stage = "execution"
            return self.runtime.process(self.root, argv + ["--expected-timing", digest(plan)], timeout=plan["execution_seconds"])
        except ReviewTimeout as error:
            if stage == "planning":
                self.save(review_preflight_error=dict(error.diagnostic, stage=stage))
            else:
                passes[-1].update(execution_error=dict(error.diagnostic, stage=stage), exit_code=124)
                self.save(passes=passes, reviewed_head=None, phase="reviewed")
            raise Refusal(f"local review {stage} watchdog expired after {error.diagnostic['allowed_seconds']}s; "
                          + ("no provider pass reserved; " if stage == "planning" else "reserved pass retained; ")
                          + "bounded diagnostics remain in the item ship receipt") from None

    def record_review(self, result: subprocess.CompletedProcess, head: str, passes: list[dict]) -> None:
        try:
            report = json.loads(result.stdout)
        except ValueError:
            raise Refusal("local review emitted no valid receipt; its reserved pass remains recorded") from None
        if not isinstance(report, dict):
            raise Refusal("local review emitted no valid receipt; its reserved pass remains recorded")
        passes[-1]["report"] = report
        passes[-1]["exit_code"] = result.returncode
        self.save(passes=passes, reviewed_head=head if result.returncode == 0 else None, phase="reviewed")
        if result.returncode:
            raise Refusal(f"local review {report.get('status')}: {report.get('completed_reviews', 0)}/{report.get('requested_reviews', 0)} completed; see item ship receipt")
        self.check_review(head)
        if self.runtime.current_head(self.root) != head:
            raise Refusal("HEAD or checkout changed during local checks and review")
