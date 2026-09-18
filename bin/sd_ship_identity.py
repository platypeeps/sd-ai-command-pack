"""One review-identity protocol, shared by the item-backed and no-item modes.

The protocol is stated once here, so the acceptance key, acceptance bindings,
and result shape have a single implementation and neither mode can drift from
the other's contract. Each mode supplies only its own fields, through the
private hooks below; neither emulates the other with null or sentinel fields.
"""

from __future__ import annotations

# The acceptance digest refuses non-finite JSON; the history digest does not.
# Both modes bind acceptance with the stricter one, as the item path always did.
from sd_ship_dispositions import digest


class ReviewIdentity:
    def _acceptance_namespace(self, review_key: str) -> str:
        raise NotImplementedError

    def _identity_bindings(self, state: dict) -> dict:
        raise NotImplementedError

    def _identity_output(self, state: dict) -> dict:
        raise NotImplementedError

    def acceptance_key(self, review_key: str) -> str:
        return self._acceptance_namespace(review_key)

    def bindings(self, repository: str, branch: str, head: str, state: dict) -> dict:
        return {"repository": repository, "branch": branch, "head": head,
                "passes_digest": digest(state["passes"]), **self._identity_bindings(state)}

    def result_fields(self, phase: str, state: dict, observed_at: str, extra: dict) -> dict:
        return {"ok": True, "phase": phase, **self._identity_output(state),
                "observed_at": observed_at, **extra}
