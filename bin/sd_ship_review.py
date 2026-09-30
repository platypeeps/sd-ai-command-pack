"""Shared review gates after explicit identity resolution.

This context performs no item lookup and constructs no publication client.
Adapters supply identity and history; the existing provider executable owns routing.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Callable

import sd_lib
import sd_review_request
import sd_ship_bindings
import sd_ship_dispositions
from sd_ship_history import (
    AUTOMATIC_CODE_REVIEW_PASSES,
    completed_depth,
    digest,
    reservation,
)
from sd_ship_remote import Refusal, completed_process
from sd_ship_workflow import success


class ReviewTimeout(Exception):
    def __init__(self, diagnostic: dict):
        self.diagnostic = diagnostic
        super().__init__("local review watchdog expired")


def is_ancestor(root: pathlib.Path, previous: str, head: str) -> bool:
    """Whether `previous` is reachable from `head`.

    `--is-ancestor` answers by exit status and prints nothing, so the raising
    `git` helper rendered "not an ancestor" as a bare, retryable "git failed"
    (sd:1348). Only exit 1 means "no"; any other failure, a timeout or a
    missing git still raises that retryable runtime refusal, because a git
    that cannot answer is not evidence of a rewritten history. The caller
    owns the refusal that names the heads.
    """
    argv = ["git", "merge-base", "--is-ancestor", previous, head]
    return completed_process(root, argv, answers=frozenset({0, 1})).returncode == 0


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


def own_patch_id(root: pathlib.Path, head: str, base_ref: str) -> str | None:
    """`git patch-id --stable` of the branch's own change, fork..head, or None.

    Bytes, not text: a diff of a non-UTF-8 file must still hash. `--binary`
    puts binary content in the hash; without it only an `index` line names
    it, and patch-id ignores that line. Any git failure is None, and None
    carries nothing forward.
    """
    fork = sd_lib.git_output(["merge-base", head, base_ref], root)
    if not fork:
        return None
    try:
        diff = subprocess.run(["git", "diff", "--binary", "--full-index", "--no-renames", "--no-color",
                               "--no-ext-diff", "--no-textconv", fork, head],
                              cwd=root, capture_output=True, timeout=120, check=False)
        if diff.returncode or not diff.stdout:
            return None
        hashed = subprocess.run(["git", "patch-id", "--stable"], cwd=root, input=diff.stdout,
                                capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    words = hashed.stdout.decode("ascii", "replace").split()
    return words[0] if hashed.returncode == 0 and words else None


def clean_merges(root: pathlib.Path, reviewed: str, head: str, base_ref: str) -> list[str] | None:
    """The commits `head` adds to `reviewed`, when each is a clean merge-in of the base.

    Every commit the base does not already hold must have exactly two
    parents, the second held by the base, and a tree that is git's own
    conflict-free merge of them. A resolved conflict, an edit folded into
    the merge, or any ordinary commit returns None.
    """
    listed = sd_lib.git_output(["rev-list", "--parents", head, f"^{reviewed}", f"^{base_ref}"], root)
    if not listed:
        return None
    merges = []
    for line in listed.splitlines():
        commit, *parents = line.split()
        if len(parents) != 2 or not is_ancestor(root, parents[1], base_ref):
            return None
        merged = sd_lib.git_output(["merge-tree", "--write-tree", "--no-messages", *parents], root)
        if not merged or merged != sd_lib.git_output(["rev-parse", f"{commit}^{{tree}}"], root):
            return None
        merges.append(commit)
    return merges


def carry_forward(root: pathlib.Path, reviewed: str, head: str, base_ref: str) -> dict | None:
    """sd:1485. Why a review of `reviewed` still covers `head`, or None.

    A catch-up merge moves the head, and a review of the old head used to
    count as stale. It still covers the branch when `reviewed` is an
    ancestor, every commit since is a clean merge-in of the base
    (`clean_merges`), and the branch's own patch-id against the base is
    unchanged. A base change inside the branch's diff context moves that
    patch-id, so it is reviewed again. A rebase is not carried: no merge
    commit shows that nothing else changed.
    """
    if reviewed == head or not is_ancestor(root, reviewed, head):
        return None
    merges = clean_merges(root, reviewed, head, base_ref)
    if merges is None:
        return None
    before = own_patch_id(root, reviewed, base_ref)
    if before is None or before != own_patch_id(root, head, base_ref):
        return None
    return {"from": reviewed, "to": head, "patch_id": before, "merges": merges}


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
    # The per-file manifest stored beside `binding`, so a moved binding names
    # what moved (sd:1834). None where a test seam supplies a bare digest.
    manifest: Callable[[pathlib.Path], dict] | None = None


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
            carried = self.state.get("review_carry_forward") or {}
            if carried.get("to") and carried.get("to") == self.state.get("reviewed_head"):
                result["review_carry_forward"] = carried
        return result

    def review_inputs(self, head: str) -> dict:
        passes = self.history.native(self.state)
        waived = self.state.get("empty_diff") or {}
        if not passes and waived.get("head") == head and empty_branch_base(self.root, head) == waived.get("base"):
            return {"status": "clean", "findings": [], "subject": {"base": waived["base"], "head": head, "paths": []}}
        if not passes:
            raise Refusal("no completed local review receipt for this head")
        if self.state.get("binding") != self.runtime.binding(self.root):
            raise self.binding_refusal()
        subject = self.carried_from(head, passes[-1])
        report = complete_report(passes[-1], subject, subject if subject != head else self.state.get("reviewed_head"))
        validate_provider_selection(report, passes[-1].get("requested_provider"), completed=True)
        self.history.validate_coverage(self.state, report)
        validate_findings(report)
        return report

    def carried_from(self, head: str, last: dict) -> str:
        """The head the last pass reviewed, when a recorded carry covers `head` (sd:1485), else `head`."""
        carried = self.state.get("review_carry_forward") or {}
        if (carried.get("to") == head and carried.get("from") == last.get("head")
                and self.state.get("reviewed_head") == head
                and (last.get("report") or {}).get("status") in ("clean", "advisory")):
            return carried["from"]
        return head

    def carried_review(self, head: str) -> bool:
        """sd:1485. Carry the last cleared review to a clean merge-in of the base.

        Only a clean or advisory receipt: a blocking one is cleared by
        dispositions bound to its own head. `carry_forward` decides; the
        receipt records what it found, and the output names it.
        """
        passes, base = self.history.native(self.state), self.state.get("base")
        if not passes or not base or not self.state.get("reviewed_head"):
            return False
        report = passes[-1].get("report") or {}
        if report.get("status") not in ("clean", "advisory") or not completed_depth(report) or self.binding_moved():
            return False
        carried = carry_forward(self.root, passes[-1]["head"], head, f"refs/remotes/origin/{base}")
        if carried is None:
            return False
        self.save(reviewed_head=head, review_carry_forward={**carried, "recorded_at": self.runtime.clock()})
        self.check_review(head)
        print(f"sd-ship: {head[:12]} adds only clean merges of origin/{base} to reviewed {carried['from'][:12]}, "
              "and the branch's own patch-id is unchanged; its review carries forward, no provider called",
              file=sys.stderr)
        return True

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

    def binding_changes(self) -> list[tuple[str, str]]:
        """What moved since the stored manifest, by entry and class (sd:1246).

        Called only once the digests differ: the digest decides, and this
        names. Gate and check entries ride along, marked, never decisive.
        """
        manifest = getattr(self.runtime, "manifest", None)
        if manifest is None:
            return []
        return sd_ship_bindings.binding_change(self.state.get("binding_manifest"), manifest(self.root))

    def binding_refusal(self) -> Refusal:
        detail = sd_ship_bindings.describe_change(self.binding_changes())
        return Refusal("review tools or repository policy changed after review" + (f": {detail}" if detail else ""),
                       code="review_binding_moved", boundary="review", state="operator_decision",
                       next_action="Run sd-ship prepare again; it re-reviews this head in full (sd:1390).")

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
        pins by making the binding read itself raise, not every subprocess.
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
        return not retry and self.carried_review(head)

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
            if not is_ancestor(self.root, previous, head):
                raise Refusal(
                    f"reviewed head {previous} is not an ancestor of the offered head {head} on {self.branch}; "
                    "an amend or a rebase after a review orphans the reviewed head, and a review of a "
                    "commit the branch cannot reach is not evidence about the branch",
                    code="reviewed_head_orphaned", boundary="review", state="operator_decision",
                    next_action=f"Restore a history that contains {previous}: after an amend, run "
                                f"`git reset --soft {previous}`, commit the change on top, then prepare again. "
                                "An unchanged retry refuses the same way.")

    def authorship_start(self) -> str:
        """Where this branch's commits begin, for trailer and vendor reads."""
        passes = self.state.get("passes") or []
        if not passes:
            return self.state["empty_diff"]["base"]
        return passes[-1]["report"].get("authorship_base") or passes[0]["report"]["subject"]["base"]

    def gate_check_base(self) -> str | None:
        """The base sd-review runs the gate check against, or None (sd:2041).

        Under `repo.ci = local` the merge gate runs this same check again; run
        it as the gate does, so its receipt answers there.
        """
        if self.state.get("base") and sd_lib.repo_ci(self.connection, self.root) == "local":
            return self.state["base"]
        return None

    def request_verifies_fix(self, passes: list[dict], head: str) -> bool:
        """sd:2147. Whether a post-cap request reviews the diff since the last reviewed head.

        That is the subject an automatic pass would take at this head. A
        request used to review the whole branch unconditionally, so a branch
        whose fix deltas each fit the review input cap outgrew it on the one
        pass the operator asked for (ui-design #19: 2.1 MB over 85 files).
        The whole branch is still reviewed where a fix verification has no
        sound base: no completed pass to verify, the same head again (an
        empty range), a moved review binding, or an imported history whose
        every native pass is a full-branch continuation. A catch-up merge is
        read after this, by `caught_up_pass`, as it is for an automatic pass.
        """
        if not passes or self.history.requires_continuation(self.state):
            return False
        last = passes[-1]
        if last["head"] == head or reservation(last):
            return False
        return not self.binding_moved()

    def caught_up_pass(self, passes: list[dict], head: str, whole: bool) -> dict | None:
        """Where the base was merged in since the last pass, when it was (sd:2023).

        From the previous head, the range then holds every commit the base
        brought in, and a fix verification would review code this branch never
        touched, so the pass is full-branch. Read from git ancestry, not from
        the `--catch-up` flag: a prepare that fails after the merge, or a merge
        done by hand, must be scoped the same way on the next run.
        """
        base = self.state.get("base")
        if not passes or whole or not base:
            return None
        previous = passes[-1]["head"]
        fork = sd_lib.git_output(["merge-base", head, f"refs/remotes/origin/{base}"], self.root)
        if not fork or is_ancestor(self.root, fork, previous):
            return None
        return {"from": previous, "base": fork}

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
        # sd:2147. A request verifies the fix like the automatic pass it
        # follows, where one would; only a request with no such pass reviews
        # the whole branch again.
        whole = additional and not self.request_verifies_fix(passes, head)
        if self.reusable_review(head, prior, retry, additional):
            return
        self.validate_dispatch(head, prior, retry, additional)
        # Only past the cap check, so a spent item refuses before the manifest
        # is read. A re-review forced by a moved binding is a full-branch pass,
        # not a fix verification: `--base <previous head>` would be this same
        # head and would review an empty range, which is a rubber stamp rather
        # than a review. It resumes the complete prior history so no earlier
        # blocker is dropped, exactly as a whole-branch post-cap request does.
        moved = not additional and self.binding_moved()
        caught_up = self.caught_up_pass(passes, head, whole)
        full = whole or moved or caught_up is not None
        if full:
            prior = self.history.aggregate(self.state)
        base = passes[-1]["head"] if passes and not (retry or full) else None
        argv = sd_review_request.review_argv(self.runtime.bin_dir, self.database, self.args, base, gate_check=self.gate_check_base())
        requested = getattr(self.args, "provider", None)
        passes.append({"head": head, "started_at": self.runtime.clock(), "base": base, "retry": retry,
                       "requested_provider": requested})
        if request:
            passes[-1]["additional_review_request"] = request
        if caught_up is not None:
            passes[-1]["catch_up"] = caught_up
        if moved:
            passes[-1]["review_binding_change"] = {"head": head, "recorded_at": self.runtime.clock(),
                                                   "superseded_binding": self.state.get("binding"),
                                                   "changed": [list(row) for row in self.binding_changes()]}
        with tempfile.TemporaryDirectory(prefix="sd-ship-verify-") as directory:
            if prior:
                prior_path = pathlib.Path(directory) / "prior-review.json"
                prior_path.write_text(json.dumps(prior, sort_keys=True), encoding="utf-8")
                argv += ["--resume-report" if retry or full else "--verify-report", str(prior_path)]
            result = self.execute_review(argv, head, passes)
        self.record_review(result, head, passes)

    def preflight_diagnostic(self, planned: subprocess.CompletedProcess,
                             kind: str = "invalid_timing_plan", stage: str = "planning") -> dict:
        diagnostic: dict = {"kind": kind, "stage": stage, "exit_code": planned.returncode}
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
            # What dispatch overwrites, so a released gate failure can put it back.
            self.superseded = {key: self.state.get(key, ABSENT) for key in DISPATCH_FIELDS}
            bound: dict[str, Any] = {"binding": self.runtime.binding(self.root)}
            if self.runtime.manifest is not None:
                bound["binding_manifest"] = self.runtime.manifest(self.root)
            self.save(passes=passes, phase="reviewing", head=head, **bound, review_preflight_error=None, review_clearance=None)
            stage = "execution"
            return self.runtime.process(self.root, argv + ["--expected-timing", digest(plan)], timeout=plan["execution_seconds"])
        except ReviewTimeout as error:
            diagnostic = withhold_raw(dict(error.diagnostic, stage=stage), head)
            if stage == "planning":
                self.save(review_preflight_error=diagnostic)
            else:
                passes[-1].update(execution_error=diagnostic, exit_code=124)
                self.save(passes=passes, reviewed_head=None, phase="reviewed")
            raise Refusal(f"local review {stage} watchdog expired after {error.diagnostic['allowed_seconds']}s; "
                          + ("no provider pass reserved; " if stage == "planning" else f"reserved pass retained{consumed(passes)}; ")
                          + "bounded diagnostics remain in the item ship receipt") from None

    def release_gate_failure(self, report: dict, head: str, passes: list[dict]) -> None:
        """Drop the pass a gate failure reserved, and refuse with the gate's words.

        The reservation is removed rather than kept as an incomplete pass: it
        reviewed nothing, so it has no findings to carry forward, and keeping
        it charged the cap and made the next prepare demand `--retry-review`
        for a review that never started. The gate's output stays in the
        receipt under `review_preflight_error`, the field a failure before
        dispatch already uses.

        Removing the pass is not enough to undo the dispatch: `execute_review`
        stored the current tool and policy binding before the gate ran. Left
        in place, a re-review forced by a moved binding would, after its gate
        failed, read as bound to the new policy, and the next prepare would
        stop re-reviewing (found by the local review of sd:1475). Every field dispatch overwrote
        goes back to what it was.
        """
        check = report.get("check") or {}
        detail = str(check.get("detail") or "")[-self.runtime.diagnostic_bytes:]
        checks = gate_diagnostics(check, self.runtime.diagnostic_bytes)
        self.release_pass(passes, {"kind": "gate_failed", "stage": "check", "head": head,
                                   "exit_code": check.get("exit_code"), "detail": detail, "checks": checks})
        failed = next((c for c in checks if c["status"] == "fail"), {})
        evidence = detail.strip() or (failed.get("stderr") or failed.get("stdout") or failed.get("reason") or "").strip()
        raise Refusal(f"the repository gate failed before any reviewer was asked; no review pass was spent: "
                      f"{evidence[-500:] or 'see the item ship receipt'}",
                      code="gate_failed", boundary="runtime", state="retryable_failure",
                      next_action="Fix the gate, or rerun prepare when the machine is less loaded "
                                  "(--review-timeout raises the limit); the next prepare reviews normally.")

    def release_pass(self, passes: list[dict], diagnostic: dict) -> None:
        """Drop the pass just reserved and put back every field its dispatch overwrote."""
        passes.pop()
        for key, value in self.superseded.items():
            if value is ABSENT:
                self.state.pop(key, None)
        self.save(passes=passes, **{key: value for key, value in self.superseded.items() if value is not ABSENT},
                  review_preflight_error=diagnostic)

    def release_unreviewed_request(self, report: dict, head: str, passes: list[dict], exit_code: int) -> None:
        """sd:2147. A post-cap pass that reviewed nothing does not spend the operator's request.

        The request buys one review. A pass in which no reviewer completed
        and none left a finding -- every reviewer refused the input, failed,
        or answered without citing the subject -- bought none, and keeping it
        made the operator renew with a history digest for a review that never
        happened. It is released the way a gate failure is, and what the
        reviewers said stays under `review_preflight_error`. A pass that kept
        a finding, or a watchdog or unreadable receipt whose evidence cannot
        say it reviewed nothing, stays spent.
        """
        self.release_pass(passes, {"kind": "additional_review_unreviewed", "stage": "execution", "head": head,
                                   "exit_code": exit_code, "status": report.get("status"),
                                   "detail": failed_outcomes(report)[-self.runtime.diagnostic_bytes:]})
        raise Refusal(f"local review {report.get('status')}: 0/{report.get('requested_reviews', 0)} completed"
                      f"{failed_outcomes(report)}; nothing was reviewed, so the operator request was not consumed",
                      code="review_unreviewed", boundary="review", state="operator_decision",
                      next_action="Resolve the reviewers' refusals, then repeat the same --additional-review-for request.")

    def record_review(self, result: subprocess.CompletedProcess, head: str, passes: list[dict]) -> None:
        try:
            report = json.loads(result.stdout)
        except ValueError:
            report = None
        if not isinstance(report, dict):
            # Keep what the reviewer process said: without its exit code and
            # output tails, a crash in sd-review and a provider failure read
            # the same (#590's first MiniMax pass).
            error = self.preflight_diagnostic(result, "invalid_receipt", "execution")
            written = write_raw(f"{head[:12]}-invalid-receipt", {"head": head, "exit_code": result.returncode,
                                                                 "stdout": result.stdout, "stderr": result.stderr})
            if written:
                error["raw_capture"] = written
            withhold_raw(error, head)
            passes[-1].update(execution_error=error, exit_code=result.returncode)
            self.save(passes=passes, reviewed_head=None, phase="reviewed")
            raise Refusal(f"local review emitted no valid receipt (sd-review exit {result.returncode}); "
                          f"its reserved pass remains recorded{consumed(passes)}; "
                          "bounded diagnostics remain in the item ship receipt")
        stash_raw_responses(report, head)
        if unreviewed_gate_failure(report, result.returncode):
            self.release_gate_failure(report, head, passes)
        request = passes[-1].get("additional_review_request")
        if request and unreviewed(report, result.returncode):
            self.release_unreviewed_request(report, head, passes, result.returncode)
        passes[-1]["report"] = report
        passes[-1]["exit_code"] = result.returncode
        self.save(passes=passes, reviewed_head=head if result.returncode == 0 else None, phase="reviewed")
        try:
            validate_provider_selection(report, passes[-1].get("requested_provider"), completed=completed_depth(report))
        except Refusal:
            self.save(reviewed_head=None)
            raise
        if result.returncode:
            raise Refusal(f"local review {report.get('status')}: {report.get('completed_reviews', 0)}/{report.get('requested_reviews', 0)} completed"
                          f"{failed_outcomes(report)}{REQUEST_CONSUMED if request else ''}; see item ship receipt")
        self.check_review(head)
        if self.runtime.current_head(self.root) != head:
            raise Refusal("HEAD or checkout changed during local checks and review")


#: What a refusal adds when the pass it kept was an explicit post-cap request (sd:2147).
REQUEST_CONSUMED = "; the operator request was consumed"


def consumed(passes: list[dict]) -> str:
    return REQUEST_CONSUMED if passes and passes[-1].get("additional_review_request") else ""


def unreviewed(report: dict, exit_code: int) -> bool:
    """sd:2147. A failed pass in which no reviewer completed and no finding survived.

    Read from a whole receipt only: one that names the reviewers it asked,
    each with a failed outcome. A report missing those fields cannot say it
    reviewed nothing, so its pass stays spent.
    """
    outcomes = report.get("outcomes")
    requested = report.get("requested_reviews")
    return (exit_code != 0 and report.get("status") in ("refused", "rate_limited", "unavailable")
            and type(requested) is int and requested > 0 and report.get("completed_reviews") == 0
            and report.get("reviewed_by") == [] and report.get("findings") == []
            and isinstance(outcomes, list) and bool(outcomes)
            and all(isinstance(row, dict) and row.get("status") not in ANSWERED for row in outcomes))


#: The receipt fields `execute_review` overwrites when it dispatches a pass.
DISPATCH_FIELDS = ("phase", "head", "binding", "binding_manifest", "review_clearance")
ABSENT = object()


def gate_diagnostics(check: dict, limit: int) -> list[dict]:
    """sd:1484. What each gate check said, bounded, for a receipt that outlives the pass.

    `check.detail` is sd-check's own stderr, which is empty when a test or a
    lint fails: that output is in each check's `stdout` and `stderr`. Keeping
    only `detail` left a receipt that said the gate failed and not why. At
    most one record per name sd-check runs, each stream cut to its last
    `limit` characters, where a failure summary ends.
    """
    records = check.get("checks")
    if not isinstance(records, list):
        return []
    # A docs-only run (sd:2072) adds one `docs` row after the three names; it is the one that ran.
    docs = [record for record in records[len(sd_lib.CHECK_NAMES):] if isinstance(record, dict)
            and record.get("name") == "docs"][:1]
    return [{"name": record.get("name"), "status": record.get("status"), "exit_code": record.get("exit_code"),
             "reason": str(record.get("reason") or "")[-limit:],
             "stdout": str(record.get("stdout") or "")[-limit:], "stderr": str(record.get("stderr") or "")[-limit:]}
            for record in [*records[:len(sd_lib.CHECK_NAMES)], *docs] if isinstance(record, dict)]


#: Statuses of a reviewer that answered usably; any other outcome names its cause.
ANSWERED = ("clean", "findings")


def failed_outcomes(report: dict, limit: int = 600) -> str:
    """The failed reviewers' own details, so a refusal names why (sd:1805).

    "0/1 completed" alone sent the operator to the receipt to learn that kimi
    spent its whole max_tokens reasoning. sd-review writes each detail from
    counts and its own sentences, never model text; bounded all the same.
    """
    details = [str(row["detail"]) for row in report.get("outcomes") or []
               if isinstance(row, dict) and row.get("status") not in ANSWERED and row.get("detail")]
    text = "; ".join(details)
    return f" ({text[:limit]}{'...' if len(text) > limit else ''})" if text else ""


def unreviewed_gate_failure(report: dict, exit_code: int) -> bool:
    """sd:1475. The repository gate failed and no reviewer was asked.

    sd-review stops at the gate and returns before any provider dispatch, so
    such a run verified nothing and cost nothing. Every clause has to hold: a
    report that names an outcome, a reviewer or a completed review asked
    someone, and that run keeps its pass as it always has.
    """
    return (exit_code != 0 and report.get("status") == "gate_failed"
            and (report.get("check") or {}).get("status") == "fail"
            and not report.get("outcomes") and not report.get("reviewed_by")
            and not report.get("completed_reviews") and not report.get("findings"))


#: Opt-in debugging (system #590): the directory that receives raw reviewer
#: output. sd-review puts a url reviewer's raw response in its diagnostic
#: only when this is set; sd-ship moves it here so the receipt keeps a path.
RAW_CAPTURE_ENV = "SD_REVIEW_RAW_DIR"


def write_raw(name: str, record: dict) -> str:
    """Write one owner-only JSON record under `SD_REVIEW_RAW_DIR`; return its path or the error."""
    directory = os.environ.get(RAW_CAPTURE_ENV, "")
    if not directory:
        return ""
    text = json.dumps(record, indent=1)
    path = pathlib.Path(directory).expanduser() / f"{name}-{hashlib.sha256(text.encode()).hexdigest()[:12]}.json"
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
            handle.write(text)
    except FileExistsError:
        pass
    except OSError as error:
        return f"not written: {error}"
    return str(path)


def stash_raw_responses(report: dict, head: str) -> None:
    """Replace each outcome's `raw_response` with the file that now holds it.

    Without the directory the field is dropped: model output never reaches
    the item's ship state."""
    for outcome in report.get("outcomes") or []:
        diagnostic = outcome.get("diagnostic") if isinstance(outcome, dict) else None
        if isinstance(diagnostic, dict) and "raw_response" in diagnostic:
            raw = diagnostic.pop("raw_response")
            written = write_raw(f"{head[:12]}-{outcome.get('backend', 'provider')}", {"head": head, **raw})
            if written:
                diagnostic["raw_capture"] = written


def withhold_raw(diagnostic: dict, head: str) -> dict:
    """Keep a reviewer's raw model text out of a diagnostic the ship state stores.

    Only with `SD_REVIEW_RAW_DIR` set does sd-review put `raw_response` in its
    output, and a truncated receipt or a watchdog kill can leave it in the
    stdout tail or the captured report. The tail is withheld (the private file
    holds the whole output) and a captured report's responses move to files.
    A watchdog kill hands over its whole output as `raw_output`, which is always
    removed here and written to its own file (sd:1588).
    """
    raw = diagnostic.pop("raw_output", None)
    if os.environ.get(RAW_CAPTURE_ENV):
        if isinstance(raw, dict):
            written = write_raw(f"{head[:12]}-watchdog", {"head": head, **raw})
            if written:
                diagnostic["raw_capture"] = written
        stdout = diagnostic.get("stdout")
        if isinstance(stdout, dict):
            diagnostic["stdout"] = {"withheld": "raw capture is on; stdout may carry model output",
                                    "bytes": stdout.get("bytes")}
        if isinstance(diagnostic.get("captured_report"), dict):
            stash_raw_responses(diagnostic["captured_report"], head)
    return diagnostic


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
