"""Item-backed identity fields, output, and acceptance-key compatibility."""

from dataclasses import dataclass

from sd_ship_identity import ReviewIdentity


@dataclass(frozen=True)
class ItemIdentity(ReviewIdentity):
    item: int

    def _acceptance_namespace(self, review_key: str) -> str:
        # Item enumeration reads literal ship: keys, not this separate namespace.
        return "ship-adjudication:" + review_key.removeprefix("ship:")

    def _identity_bindings(self, state: dict) -> dict:
        return {"item": self.item}

    def _identity_output(self, state: dict) -> dict:
        return {"item": self.item, "head": state.get("head"), "reviewed_head": state.get("reviewed_head"),
                "pull_request": state.get("pull_request"), "deliver": state.get("deliver", False),
                "warnings": state.get("warnings", []), "review_clearance": state.get("review_clearance")}
