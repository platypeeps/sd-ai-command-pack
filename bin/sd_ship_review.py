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

import sd_lib
import sd_ship_dispositions
from sd_ship_history import AUTOMATIC_CODE_REVIEW_PASSES, completed_depth, digest
from sd_ship_remote import Refusal, git
from sd_ship_workflow import success


class ReviewTimeout(Exception):
    def __init__(self, diagnostic: dict):
        self.diagnostic = diagnostic
        super().__init__("local review watchdog expired")


def empty_branch_base(root: pathlib.Path, head: str) -> str | None:
    """sd:1405. The merge base when `head` changes no file against it, else None.

    An `sd attribute` repair branch is empty commits only. `sd-review` refuses
    such a subject as `subject_empty`, so the ship lane waives review for it.
    """
    for ref in ("origin/HEAD", "main", "master"):
        base = sd_lib.git_output(["merge-base", head, ref], root)
        if base:
            return base if sd_lib.git_output(["diff", "--name-only", "--no-renames", base, head], root) == "" else None
    return None


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


def validate_provider_selection(report: dict, requested: str | None, *, completed: bool = False) -> None:
    """An explicit pick authorizes no alternate candidate or completed reviewer."""
    if requested is None:
        return
    timing = report.get("timing")
    candidates = timing.get("candidates") if isinstance(timing, dict) else None
    valid = (isinstance(requested, str) and bool(requested) and report.get("providers") == [requested]
             and report.get("fallback_candidates") == [] and report.get("requested_reviews") == 1
             and isinstance(candidates, list) and len(candidates) == 1 and isinstance(candidates[0], dict)
             and candidates[0].get("name") == requested
             and (not completed or report.get("reviewed_by") == [requested]))
    if not valid:
        raise Refusal("local review does not match the requested reviewer; no fallback is permitted",
                      code="review_provider_mismatch", boundary="provider", state="operator_decision",
                      next_action="Inspect the complete reviewer plan and repeat the intended --provider selection.")


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
        result = self.identity.result_fields(phase, self.state, self.runtime.clock(), extra)
        result["workflow"] = success(phase, observed_only=bool(extra.get("observed_only")))
        passes = self.history.native(self.state)
        if passes:
            report = passes[-1].get("report") or {}
            result["review_selection"] = {"requested_provider": passes[-1].get("requested_provider"),
                                          "reviewed_by": report.get("reviewed_by", [])}
        return result

    def review_inputs(self, head: str) -> dict:
        passes = self.history.native(self.state)
        waived = self.state.get("empty_diff") or {}
        if not passes and waived.get("head") == head and empty_branch_base(self.root, head) == waived.get("base"):
            return {"status": "clean", "findings": [], "subject": {"base": waived["base"], "head": head, "paths": []}}
        if not passes:
            raise Refusal("no completed local review receipt for this head")
        if self.state.get("binding") != self.runtime.binding(self.root):
            raise Refusal("review tools or repository policy changed after review")
        report = complete_report(passes[-1], head, self.state.get("reviewed_head"))
        validate_provider_selection(report, passes[-1].get("requested_provider"), completed=True)
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
        cap = AUTOMATIC_CODE_REVIEW_PASSES
        spent = self.history.spent(self.state)
        continuation = self.history.requires_continuation(self.state)
        history_digest = self.history.history_digest(self.state)
        if spent < cap and not continuation:
            raise Refusal(f"additional review requires {cap} spent passes")
        if spent == cap and not continuation and supplied_digest is not None:
            raise Refusal(f"--review-history-digest renews only after at least {cap + 1} spent passes")
        if (spent > cap or continuation) and supplied_digest != history_digest:
            raise Refusal(f"renewal requires --review-history-digest {history_digest} for the complete current history; each digest is spent once")
        self.history.validate_requests(self.state)
        self.history.aggregate(self.state)

    def binding_moved(self) -> bool:
        """The stored receipt was produced by review tools or policy now gone.

        Reuse was decided on head equality alone and the receipt was then
        rejected on this manifest inside `review_inputs`, with nothing between
        them saying "the binding moved, therefore review again" -- so a branch
        whose review completed and whose head then stopped moving was bricked
        by the next unrelated landing on the default branch that touched a
        review tool file, with no verb able to clear it (sd:1390, live on
        #1140).

        Read lazily and memoized, never eagerly. `review_binding` reaches
        `sd_lib.main_worktree_root`, which shells out to `git rev-parse`, and
        the cap refusal below has to come first: a pass past the cap is
        refused before anything is dispatched or even asked, which is what
        `test_the_pass_after_the_cap_refuses_and_an_explicit_request_still_admits_it`
        pins by making every `subprocess.run` raise.
        """
        if not hasattr(self, "_binding_moved"):
            self._binding_moved = bool(self.history.native(self.state)) and self.state.get("binding") != self.runtime.binding(self.root)
        return self._binding_moved

    def reusable_review(self, head: str, prior: dict, retry: bool, additional: bool) -> bool:
        if additional:
            return False
        requested = getattr(self.args, "provider", None)
        if (requested is not None and prior.get("subject", {}).get("head") == head
                and completed_depth(prior) and prior.get("reviewed_by") != [requested]):
            raise Refusal("completed receipt does not match the requested reviewer; selection cannot replace review evidence",
                          code="review_provider_mismatch", boundary="provider", state="operator_decision",
                          next_action="Reuse the recorded reviewer, or obtain a permitted additional-review request.")
        # A receipt bound to tools or policy that have since changed is not
        # reusable. The manifest is read here, inside each path that would
        # otherwise reuse, rather than once above: each of these ends in
        # `check_review`, which refuses on exactly this manifest, so reuse was
        # being selected on head equality and then rejected on the binding.
        if not retry and prior.get("status") == "blocking" and prior.get("subject", {}).get("head") == head:
            if self.binding_moved():
                return False
            clearance = self.check_review(head, refresh_adjudication=True)
            self.save(reviewed_head=head, review_clearance=clearance)
            return True
        if self.state.get("reviewed_head") == head and (not retry or completed_depth(prior)):
            if self.binding_moved():
                return False
            self.check_review(head)
            return True
        return False

    def validate_dispatch(self, head: str, prior: dict, retry: bool, additional: bool) -> None:
        passes = self.history.native(self.state)
        if not additional and (self.history.spent(self.state) >= AUTOMATIC_CODE_REVIEW_PASSES
                               or self.history.requires_continuation(self.state)):
            raise Refusal(f"all {AUTOMATIC_CODE_REVIEW_PASSES} automatic code review passes are spent; "
                          "further review requires an explicit new request")
        if retry and (not passes or completed_depth(prior)):
            raise Refusal("--retry-review can continue only an incomplete review")
        # A moved binding re-reviews the branch at the head it already covered,
        # so neither refusal below applies: the fix-verification shape is not
        # what is being dispatched, and the already-reviewed head is the whole
        # point. Leaving them in place only moves the deadlock one line down.
        # The cap above still holds and is read first -- a re-review spends a
        # pass, and a pass past the cap is refused before the binding is even
        # asked for, which is why `binding_moved` is last in this condition.
        if passes and not retry and not additional and not self.binding_moved():
            if not completed_depth(prior):
                raise Refusal("the preceding review did not complete its requested depth; use --retry-review for a full-branch retry")
            if passes[-1].get("head") == head:
                raise Refusal("this head was already reviewed; address its findings before the fix verification")
        for previous in self.history.ancestry_heads(self.state):
            git(self.root, "merge-base", "--is-ancestor", previous, head)

    def authorship_start(self) -> str:
        """Where this branch's commits begin, for trailer and vendor reads."""
        passes = self.state.get("passes") or []
        if not passes:
            return self.state["empty_diff"]["base"]
        return passes[-1]["report"].get("authorship_base") or passes[0]["report"]["subject"]["base"]

    def review(self, head: str) -> None:
        passes = self.history.native(self.state)
        if not passes and (base := empty_branch_base(self.root, head)):
            print(f"sd-ship: {head[:12]} changes no file against {base[:12]}; local review skipped, no provider called",
                  file=sys.stderr)
            self.save(empty_diff={"head": head, "base": base}, reviewed_head=head)
            return
        prior = self.history.prior(self.state)
        retry = bool(self.args.retry_review)
        request = self.additional_request(head, passes)
        additional = request is not None
        if additional:
            prior = self.history.aggregate(self.state)
        if self.reusable_review(head, prior, retry, additional):
            return
        self.validate_dispatch(head, prior, retry, additional)
        # Only past the cap check, so a spent item refuses before the manifest
        # is read. A re-review forced by a moved binding is a full-branch pass,
        # not a fix verification: `--base <previous head>` would be this same
        # head and would review an empty range, which is a rubber stamp rather
        # than a review. It resumes the complete prior history so no earlier
        # blocker is dropped, exactly as a post-cap request does.
        moved = not additional and self.binding_moved()
        if moved:
            prior = self.history.aggregate(self.state)
        base = passes[-1]["head"] if passes and not (retry or additional or moved) else None
        argv = [sys.executable, str(self.runtime.bin_dir / "sd-review"), "--scope", "branch", "--challenge", "--json", "--database", str(self.database)]
        requested = getattr(self.args, "provider", None)
        if requested is not None:
            argv += ["--provider", requested]
        if getattr(self.args, "reuse_check", False):
            argv.append("--reuse-check")
        if base:
            argv += ["--base", base]
        passes.append({"head": head, "started_at": self.runtime.clock(), "base": base, "retry": retry,
                       "requested_provider": requested})
        if request:
            passes[-1]["additional_review_request"] = request
        if moved:
            passes[-1]["review_binding_change"] = {"head": head, "recorded_at": self.runtime.clock(),
                                                   "superseded_binding": self.state.get("binding")}
        with tempfile.TemporaryDirectory(prefix="sd-ship-verify-") as directory:
            if prior:
                prior_path = pathlib.Path(directory) / "prior-review.json"
                prior_path.write_text(json.dumps(prior, sort_keys=True))
                argv += ["--resume-report" if retry or additional or moved else "--verify-report", str(prior_path)]
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
                validate_review_readiness(planned)
                validate_provider_selection(json.loads(planned.stdout), passes[-1].get("requested_provider"))
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
        try:
            validate_provider_selection(report, passes[-1].get("requested_provider"), completed=completed_depth(report))
        except Refusal:
            self.save(reviewed_head=None)
            raise
        if result.returncode:
            raise Refusal(f"local review {report.get('status')}: {report.get('completed_reviews', 0)}/{report.get('requested_reviews', 0)} completed; see item ship receipt")
        self.check_review(head)
        if self.runtime.current_head(self.root) != head:
            raise Refusal("HEAD or checkout changed during local checks and review")


def validate_review_readiness(planned: subprocess.CompletedProcess) -> None:
    """Only live explain output needs readiness; stored historical reports retain their schema."""
    try:
        readiness = json.loads(planned.stdout)["readiness"]
        status, blockers = readiness["status"], readiness["blockers"]
        valid = (status in ("ready", "blocked") and isinstance(blockers, list)
                 and isinstance(readiness.get("warnings"), list)
                 and readiness.get("runtime_approval") == "not_observable"
                 and all(isinstance(row, dict) and all(isinstance(row.get(key), str) and row[key]
                         for key in ("code", "boundary", "next_action")) for row in blockers)
                 and (status == "ready") == (not blockers))
    except (ValueError, KeyError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise Refusal("local review emitted no valid readiness plan; no provider pass was reserved",
                      code="readiness_invalid", boundary="runtime", state="operator_decision",
                      next_action="Install matching review tools, then retry prepare.")
    if blockers:
        first = blockers[0]
        raise Refusal(f"local review readiness blocked: {first['code']}; no provider pass was reserved",
                      code=first["code"], boundary=first["boundary"], next_action=first["next_action"],
                      state="operator_decision", approval_required=first["code"] == "consent_missing")
