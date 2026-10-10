"""Additive workflow state; legacy result fields and exit codes stay authoritative."""

from __future__ import annotations

import subprocess


def blocked(code: str, boundary: str, next_action: str, *, state: str = "policy_block",
            approval_required: bool = False) -> dict:
    return {"state": state, "blocker": {"code": code, "boundary": boundary,
            "retryable": state == "retryable_failure", "approval_required": approval_required},
            "next_action": next_action}


#: `sd_db` faults of the hub's transport or build, by class name (sd:3239): a dropped session, a write
#: the hub says did not commit, and the refusals a hub upgrade leaves until the satellite's self-install
#: or the hub's restart. `UnknownOutcome` is not one: its write may have committed, so nothing reruns it.
HUB_FAULTS = frozenset({"HubUnreachable", "TransactionLost", "BuildMismatch", "HubRestartNeeded", "SchemaTooNew"})
#: The blocker code of a hub fault; the lane puts such an entry back for its next run.
HUB_UNAVAILABLE = "hub_unavailable"


def is_hub_fault(error: Exception) -> bool:
    """Whether `error` is one of `HUB_FAULTS`, read without importing `sd_db`."""
    return any(kind.__module__.startswith("sd_db.") and kind.__name__ in HUB_FAULTS for kind in type(error).__mro__)


def failure(phase: str, error: Exception) -> dict:
    detail = getattr(error, "workflow", None)
    if detail is None:
        detail = blocked("prerequisite_failed", "policy", "Inspect the error and resolve the failed prerequisite.")
        if is_hub_fault(error):
            detail = blocked(HUB_UNAVAILABLE, "runtime", "Retry this command when the sd hub answers again.",
                             state="retryable_failure")
        if isinstance(error, (OSError, subprocess.SubprocessError)):
            detail = blocked("execution_failed", "runtime", "Restore the local runtime, then retry this command.",
                             state="retryable_failure")
    return {**getattr(error, "details", {}), "ok": False, "manualRequired": True, "error": str(error),
            "workflow": {"schema_version": 1, "phase": phase, **detail}}


def success(phase: str, *, observed_only: bool = False) -> dict:
    actions = {"created": "Run sd-ship review with this review ID.",
               "reviewed": "Inspect findings, then prepare or adjudicate this review.",
               "ready_to_send": "Read exact-head CI, then run sd-ship merge with the same identity.",
               "merged": "Triage review findings and complete post-merge closeout. "
                         "Remove this PR's safe branches, stashes, refs and stale worktrees "
                         "after recording their object IDs."}
    action = ("Run sd-ship reconcile with the same identity." if observed_only and phase == "merged"
              else actions.get(phase, "Continue with the same review identity."))
    return {"schema_version": 1, "phase": phase, "state": "success", "blocker": None, "next_action": action}
