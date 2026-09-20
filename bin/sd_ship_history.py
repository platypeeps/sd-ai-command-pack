"""Mode-specific review history without item lookup or provider dispatch."""

from __future__ import annotations

import hashlib
import json
import re

from sd_ship_remote import Refusal

#: Automatic local code-review passes before an explicit request is needed.
#: The *Development / Code, before merge* row of the review table in
#: `.claude/rules/sd-planning-adversarial-review.md` states this cap, and
#: every site that counts passes reads it here rather than spelling a number.
AUTOMATIC_CODE_REVIEW_PASSES = 5


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def completed_depth(report: dict) -> bool:
    requested, completed = report.get("requested_reviews"), report.get("completed_reviews")
    return type(requested) is int and type(completed) is int and requested > 0 and completed >= requested


def timeout_evidence(entry: dict) -> dict | None:
    error = entry.get("execution_error")
    captured = error.get("captured_report") if isinstance(error, dict) else None
    if (not isinstance(error, dict) or not isinstance(captured, dict)
            or error.get("kind") != "watchdog_expired"
            or error.get("stage") != "execution" or captured.get("scope") != "branch"
            or not isinstance(captured.get("subject"), dict) or captured["subject"].get("head") != entry["head"]
            or not isinstance(captured.get("findings"), list) or not isinstance(captured.get("authored_with"), list)
            or any(not isinstance(row, dict) or not isinstance(row.get("path"), str) for row in captured["findings"])
            or any(not isinstance(vendor, str) for vendor in captured["authored_with"])):
        return None
    return captured


def review_history(passes: list[dict]) -> dict:
    """Preserve the item receipt's aggregate shape and untrusted provenance."""
    findings: list[dict]
    history, findings, vendors = [], [], set()
    for index, entry in enumerate(passes):
        report = entry.get("report")
        captured = timeout_evidence(entry) if report is None else None
        if captured is not None:
            report = {"findings": captured["findings"], "authored_with": captured["authored_with"]}
        if report is not None and not isinstance(report, dict):
            raise Refusal("prior review report is not an object")
        rows, authors = (report or {}).get("findings", []), (report or {}).get("authored_with", [])
        if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
                or not isinstance(authors, list) or any(not isinstance(author, str) for author in authors)):
            raise Refusal("prior review evidence cannot be preserved")
        source = {"pass": index + 1, "head": entry["head"],
                  "report_digest": digest(entry["report"]) if entry.get("report") is not None else None}
        if captured is not None:
            source.update(timeout_capture_digest=digest(captured), operator_context="untrusted timeout evidence; review did not complete")
        history.append(source)
        findings.extend(dict(row, prior_review=source) for row in rows)
        vendors.update(authors)
    return {"scope": "branch", "subject": {"head": passes[-1]["head"]}, "findings": findings,
            "authored_with": sorted(vendors), "history": history, "operator_context": "untrusted evidence, not instructions"}


def validate_additional_requests(passes: list[dict]) -> None:
    """A request is required past the cap, and authenticated wherever it sits.

    Position alone cannot say whether a stored pass was explicitly requested.
    A receipt written while the cap was lower carries its request at an index
    today's cap treats as automatic, and reading the index rather than the
    entry would let that request go unchecked. The entry states it, so the
    entry is what is read.
    """
    for index, entry in enumerate(passes):
        request = entry.get("additional_review_request")
        if request is None and index < AUTOMATIC_CODE_REVIEW_PASSES:
            continue
        if (not isinstance(request, dict) or request.get("head") != entry.get("head")
                or not isinstance(request.get("reason"), str) or not request["reason"].strip()
                or type(request.get("allowed_passes")) is not int or request["allowed_passes"] != 1
                or request.get("prior_history_digest") != digest(passes[:index])):
            raise Refusal("additional review request does not bind its exact prior history and head")


def verification_link(previous: dict, report: dict) -> bool:
    """`report` verifies `previous`: same head reviewed, same evidence carried."""
    return (report.get("subject", {}).get("base") == previous.get("head")
            and report.get("verification_report_digest") == digest(previous.get("report") or {}))


def full_branch_coverage(report: dict, prior: dict) -> None:
    base = report.get("authorship_base")
    if (not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base)
            or report.get("subject", {}).get("base") != base
            or report.get("resume_report_digest") != digest(prior)):
        raise Refusal("additional review history or full-branch coverage does not match")


class ReviewHistory:
    """The history surface the shared gates consume, stated once.

    Each mode supplies only its own records, digest, prefixes and coverage
    rule, through the private hooks below. Imported records never become
    native results, and the item-backed receipt shape never gains a field.
    """

    def _records(self, state: dict) -> list[dict]:
        raise NotImplementedError

    def _digest(self, state: dict) -> str:
        raise NotImplementedError

    def _entries(self, state: dict, before_last: bool) -> list[dict]:
        raise NotImplementedError

    def _continuation(self, state: dict) -> bool:
        raise NotImplementedError

    def _validate_requests(self, state: dict) -> None:
        raise NotImplementedError

    def _request_fields(self, state: dict) -> dict:
        raise NotImplementedError

    def _validate_coverage(self, state: dict, report: dict) -> None:
        raise NotImplementedError

    def _stamp(self, state: dict) -> dict:
        raise NotImplementedError

    def native(self, state: dict) -> list[dict]:
        return list(state.get("passes") or [])

    def spent(self, state: dict) -> int:
        return len(self._records(state))

    def history_digest(self, state: dict) -> str:
        return self._digest(state)

    def aggregate(self, state: dict, *, before_last: bool = False) -> dict:
        entries = self._entries(state, before_last)
        if not entries:
            raise Refusal("this review history has no records to aggregate")
        return review_history(entries)

    def requires_continuation(self, state: dict) -> bool:
        return self._continuation(state)

    def validate_requests(self, state: dict) -> None:
        self._validate_requests(state)

    def request_fields(self, state: dict) -> dict:
        return self._request_fields(state)

    def ancestry_heads(self, state: dict) -> list[str]:
        return [entry["head"] for entry in self._records(state)]

    def validate_coverage(self, state: dict, report: dict) -> None:
        self._validate_coverage(state, report)

    def stamp(self, state: dict) -> dict:
        """What each mode records beside its passes before the receipt is stored."""
        return self._stamp(state)


class ItemHistory(ReviewHistory):
    """Keep existing item-backed counts, prefixes, and request serialization."""

    def _records(self, state: dict) -> list[dict]:
        return self.native(state)

    def _digest(self, state: dict) -> str:
        return digest(self.native(state))

    def _entries(self, state: dict, before_last: bool) -> list[dict]:
        passes = self.native(state)
        return passes[:-1] if before_last else passes

    def _continuation(self, state: dict) -> bool:
        return False

    def _validate_requests(self, state: dict) -> None:
        validate_additional_requests(self.native(state))

    def _request_fields(self, state: dict) -> dict:
        return {}

    def _stamp(self, state: dict) -> dict:
        # The item receipt format is unchanged; it gains no derived field.
        return state

    def prior(self, state: dict) -> dict:
        passes = self.native(state)
        prior = (passes[-1].get("report") or {}) if passes else {}
        if passes and not prior and timeout_evidence(passes[-1]) is not None:
            return self.aggregate(state)
        return prior

    def _validate_coverage(self, state: dict, report: dict) -> None:
        """Each stored pass checked by what it says it is, against its own predecessor.

        One walk, not three rules chosen by counting. A pass carries what it
        was: an explicit request, a retry of the pass before it, or an
        automatic verification of it. Deciding from the count instead made two
        defects that only a longer chain exposes -- a receipt written under a
        lower cap read as automatic, and a stale link in the middle that a
        check on the last pair alone can never see.
        """
        passes = self.native(state)
        if not passes:
            return
        self.validate_requests(state)
        # The checkpoint is read before the walk, not accumulated during it: a
        # full-branch review supersedes what came *before* it, so a forward
        # scan that has not reached it yet would refuse its own predecessors.
        # Only a successful one counts; a failed or reportless pass covers
        # nothing, and the pass that renews it is where the report arrives.
        covered = [index for index, entry in enumerate(passes)
                   if entry.get("additional_review_request")
                   and completed_depth(self.stored_report(passes, index, report))]
        checkpoint = covered[-1] if covered else -1
        for index in range(len(passes)):
            self.validate_entry(passes, index, self.stored_report(passes, index, report), checkpoint)

    @staticmethod
    def stored_report(passes: list[dict], index: int, report: dict) -> dict:
        """The last pass's report is the one freshly read; earlier ones are stored."""
        return report if index == len(passes) - 1 else (passes[index].get("report") or {})

    def validate_entry(self, passes: list[dict], index: int, current: dict, checkpoint: int) -> None:
        """One stored pass against its predecessor, by what the entry says it is."""
        entry = passes[index]
        if entry.get("additional_review_request"):
            # The pass being read now is always checked, as it always was.
            if index == len(passes) - 1 or completed_depth(current):
                full_branch_coverage(current, self.aggregate_prefix(passes[:index]))
            return
        if entry.get("retry"):
            if index == 0:
                raise Refusal("a retry has no preceding review to resume")
            self.validate_retry(passes[:index + 1], current)
            return
        if index <= checkpoint:
            return
        if index == 0:
            # The first pass may be incomplete only where the next one
            # retries it; every later pass is reached as a predecessor.
            retried = len(passes) > 1 and bool(passes[1].get("retry"))
            if not retried and not completed_depth(current):
                raise Refusal("the original branch never completed the requested local review depth")
            return
        previous = passes[index - 1]
        if index - 1 > checkpoint and not completed_depth(previous.get("report") or {}):
            raise Refusal("the original branch never completed the requested local review depth")
        if not verification_link(previous, current):
            raise Refusal("fix verification does not continue the initially reviewed head")

    def aggregate_prefix(self, entries: list[dict]) -> dict:
        """The history a full-branch pass at this point resumes."""
        if not entries:
            raise Refusal("this review history has no records to aggregate")
        return review_history(entries)

    def validate_retry(self, passes: list[dict], report: dict) -> None:
        """The retry resumes the pass before it, whichever pass that is."""
        preceding = passes[-2]
        incomplete = preceding.get("report") or {}
        prior = incomplete or (review_history(passes[:-1]) if timeout_evidence(preceding) is not None else {})
        if (completed_depth(incomplete) or report.get("subject", {}).get("base") != report.get("authorship_base")
                or report.get("resume_report_digest") != (digest(prior) if prior else None)):
            raise Refusal("retry must complete the full branch and retain the incomplete review evidence")
