"""Unit cover for the branch-protection guard in `bin/sd_ship_remote.py`.

`tests/test_sd_ship.py` drives `GitHub.protection` end to end, through a real
bare Git fixture and an HTTP double, and its fixture always answers with a
protection document whose `required_pull_request_reviews` is an object. So the
guard that refuses a document where it is *not* an object had no test at all:
it was the one refusal in that method nothing reached, while the three around
it were exercised (sd:852, found by the review of sd:957).

That branch does not need the end-to-end rig to be reached -- it is a decision
about one field of one JSON document -- so this module stubs the single API
call the method makes and reads the refusal back. No network, no `gh`, no Git.
"""

from __future__ import annotations

import pathlib
import sys
import unittest
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import sd_ship_remote  # noqa: E402 - after the path insert


def protection_document(**changes: Any) -> dict:
    """A protection document that passes every guard in `GitHub.protection`.

    Each test changes exactly the field it is about, so a refusal it sees is
    the refusal for that field and not one the fixture happened to trip.
    """
    value: dict[str, Any] = {
        "enforce_admins": {"enabled": True},
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "required_status_checks": {"strict": True, "contexts": ["check"]},
    }
    value.update(changes)
    return value


class StubbedGitHub(sd_ship_remote.GitHub):
    """The real adapter with its one outbound call answered from memory."""

    def __init__(self, answer: Any):
        super().__init__(ROOT, "fixture/repo")
        self.answer = answer
        self.requested: list[str] = []

    def api(self, path: str, *, method: str = "GET", body: dict | None = None) -> Any:
        self.requested.append(path)
        return self.answer


class ProtectionCase(unittest.TestCase):
    def test_a_protection_document_without_a_reviews_object_is_refused_by_name(self) -> None:
        """Every non-object shape of `required_pull_request_reviews` refuses.

        Absent, null, and the JSON scalars and arrays a misconfigured or
        future GitHub could put there. The document is otherwise valid, so
        nothing else in the method can raise: the message asserted here can
        only come from the `required_pull_request_reviews` guard.
        """
        absent = protection_document()
        del absent["required_pull_request_reviews"]
        for label, value in (
            ("absent", absent),
            ("null", protection_document(required_pull_request_reviews=None)),
            ("array", protection_document(required_pull_request_reviews=[])),
            ("populated array", protection_document(required_pull_request_reviews=[{"x": 1}])),
            ("string", protection_document(required_pull_request_reviews="required")),
            ("boolean", protection_document(required_pull_request_reviews=True)),
            ("number", protection_document(required_pull_request_reviews=0)),
        ):
            with self.subTest(shape=label):
                remote = StubbedGitHub(value)
                with self.assertRaisesRegex(
                    sd_ship_remote.Refusal,
                    r"^branch protection does not require pull requests$",
                ):
                    remote.protection("main")
                self.assertEqual(
                    remote.requested, ["repos/fixture/repo/branches/main/protection"])

    def test_a_document_that_does_require_pull_requests_is_returned_unchanged(self) -> None:
        """The guard refuses a shape, not every document: the valid one passes."""
        value = protection_document()
        self.assertIs(StubbedGitHub(value).protection("main"), value)


if __name__ == "__main__":
    unittest.main()
