"""Additive workflow state; legacy result fields and exit codes stay authoritative."""

from __future__ import annotations

import subprocess


def blocked(code: str, boundary: str, next_action: str, *, state: str = "policy_block",
            approval_required: bool = False) -> dict:
    return {"state": state, "blocker": {"code": code, "boundary": boundary,
            "retryable": state == "retryable_failure", "approval_required": approval_required},
            "next_action": next_action}


def failure(phase: str, error: Exception) -> dict:
    detail = getattr(error, "workflow", None)
    if detail is None:
        detail = blocked("prerequisite_failed", "policy", "Inspect the error and resolve the failed prerequisite.")
        if isinstance(error, (OSError, subprocess.SubprocessError)):
            detail = blocked("execution_failed", "runtime", "Restore the local runtime, then retry this command.",
                             state="retryable_failure")
    return {"ok": False, "manualRequired": True, "error": str(error),
            "workflow": {"schema_version": 1, "phase": phase, **detail}}


def success(phase: str, *, observed_only: bool = False) -> dict:
    actions = {"created": "Run sd-ship review with this review ID.",
               "reviewed": "Inspect findings, then prepare or adjudicate this review.",
               "ready_to_send": "Read exact-head CI, then run sd-ship merge with the same identity.",
               "merged": "Triage review findings and complete approved post-merge closeout. "
                         "Confirm exact deletion targets and obtain explicit approval before deleting anything."}
    action = ("Run sd-ship reconcile with the same identity." if observed_only and phase == "merged"
              else actions.get(phase, "Continue with the same review identity."))
    return {"schema_version": 1, "phase": phase, "state": "success", "blocker": None, "next_action": action}
