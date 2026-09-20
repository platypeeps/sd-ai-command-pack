"""Unit cover for the branch-protection guards in `bin/sd_ship_remote.py`.

`GitHub.protection` raises five refusals, one per guard, in a fixed order:
the body is not an object; `enforce_admins` is not enabled; there is no
`required_pull_request_reviews` object; the status checks are not strict or
name nothing; a bypass allowance lists someone. `tests/test_sd_ship.py`
drives the method end to end, through a real bare Git fixture and an HTTP
double, but its fixture answers with one valid document and its tests vary
one field of it: the `enforce_admins` guard is reached there, and nothing
else is. The test that sets the double's protection to `None` reads a 404
through `api_status`, which `protection` refuses by status before any guard
sees a body, so the first guard was credited to a test that never executes it (sd:929,
measured with coverage on this file; sd:852 had added the reviews guard
alone and called the other three covered).

None of these guards needs the end-to-end rig to be reached -- each is a
decision about one field of one JSON document -- so this module stubs the
single API call the method makes and reads the refusal back. No network, no
`gh`, no Git. Every test hands the method a document that is valid in every
field but the one it is about, so the message it asserts can only come from
that field's guard. The merge's comparison of its two reads of the document
needs the rig, and is driven in `tests/test_sd_ship_disposition_guards.py`.

`GitHub.ready` is stubbed the same way for the two refusals sd:10 criterion 13
names: a pull request whose head or base moved after the local review, and a
reviewed branch that is behind the default branch. The first is decided on the
pull-request document alone and makes no call; the second is decided on the
one `compare` call the method makes before it looks at check runs.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest
from types import MappingProxyType
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

    def api_status(self, path: str) -> tuple[int, Any]:
        # `protection` reads the object through the status-bearing call since
        # sd:1110, so a 404 can be an answer; every document here is a 200.
        self.requested.append(path)
        return 200, self.answer


class ProtectionCase(unittest.TestCase):
    def assert_refused(self, value: Any, message: str) -> None:
        """`value`, served as the protection document, refuses with `message`.

        The pattern is anchored at both ends, so a refusal from a different
        guard, or a longer sentence wrapping this one, fails the assertion.
        """
        remote = StubbedGitHub(value)
        with self.assertRaisesRegex(sd_ship_remote.Refusal, rf"^{re.escape(message)}$"):
            remote.protection("main")
        self.assertEqual(remote.requested, ["repos/fixture/repo/branches/main/protection"])

    def test_a_body_that_is_not_an_object_is_refused_as_unobserved(self) -> None:
        """A protection document is an object or it is nothing.

        A list, a scalar, or `null` parsed from the transport is not a
        document whose fields can be read, and the method says so before it
        reads any: the refusal names the observation, not a field. This is
        the guard `tests/test_sd_ship.py` credited to its `protection = None`
        case, which the double answers with a 404 the transport refuses
        first, so the guard was never reached from there.
        """
        for label, value in (
            ("null", None),
            ("array", []),
            ("populated array", [protection_document()]),
            ("string", "protected"),
            ("boolean", True),
            ("number", 1),
        ):
            with self.subTest(shape=label):
                self.assert_refused(value, "branch protection could not be observed")

    def test_a_document_that_does_not_enforce_administrators_is_refused_by_name(self) -> None:
        """`enforce_admins.enabled` is `true` or the branch is not protected
        from the people who can merge to it: `false`, absent, and any
        near-miss of `true` refuse alike."""
        absent = protection_document()
        del absent["enforce_admins"]
        for label, value in (
            ("disabled", protection_document(enforce_admins={"enabled": False})),
            ("absent", absent),
            ("empty object", protection_document(enforce_admins={})),
            ("enabled is a string", protection_document(enforce_admins={"enabled": "true"})),
            ("enabled is one", protection_document(enforce_admins={"enabled": 1})),
        ):
            with self.subTest(shape=label):
                self.assert_refused(value, "branch protection does not enforce administrators")

    def test_a_document_without_strict_named_checks_is_refused_by_name(self) -> None:
        """Both halves of the CI rule refuse on their own: checks that are
        not strict, and strict checks that name nothing in either the legacy
        `contexts` list or the app-bound `checks` list. A document with no
        `required_status_checks` at all is both."""
        absent = protection_document()
        del absent["required_status_checks"]
        for label, value in (
            ("not strict", protection_document(
                required_status_checks={"strict": False, "contexts": ["check"]})),
            ("strict absent", protection_document(
                required_status_checks={"contexts": ["check"]})),
            ("strict but nothing named", protection_document(
                required_status_checks={"strict": True, "contexts": [], "checks": []})),
            ("strict with neither list", protection_document(
                required_status_checks={"strict": True})),
            ("required_status_checks absent", absent),
            ("required_status_checks null", protection_document(required_status_checks=None)),
        ):
            with self.subTest(shape=label):
                self.assert_refused(value, "branch protection requires strict, named CI checks")

    def test_a_document_with_a_bypass_allowance_is_refused_by_name(self) -> None:
        """One user, one team, or one app allowed past the review rule is a
        review rule that does not hold, and the refusal names the allowance.
        Empty allowance lists are the shape GitHub serves for "nobody", and
        those pass."""
        for label, allowances in (
            ("one user", {"users": [{"login": "someone"}]}),
            ("one team", {"teams": [{"slug": "maintainers"}]}),
            ("one app", {"apps": [{"slug": "bot"}]}),
            ("one user beside empty lists", {"users": [{"login": "someone"}], "teams": [], "apps": []}),
        ):
            with self.subTest(shape=label):
                reviews = {"required_approving_review_count": 1, "bypass_pull_request_allowances": allowances}
                self.assert_refused(
                    protection_document(required_pull_request_reviews=reviews),
                    "pull-request protection has bypass allowances")

    def test_the_guards_fire_in_order_so_each_refusal_names_the_first_fault(self) -> None:
        """Two faults in one document refuse for the earlier guard.

        The order is the method's: the object check before administrators
        before reviews before checks before allowances. A caller reading the
        message can act on it knowing there may be more behind it, but never
        that a later guard was consulted first.

        The object check is pinned against being *moved* and not only
        deleted, which the shapes in
        `test_a_body_that_is_not_an_object_is_refused_as_unobserved` cannot
        do: none of them answers `.get`, so a later guard reading their
        fields raises rather than refusing, and the refusal that guard would
        have made is never seen. A mapping proxy is not a `dict` and does
        answer `.get`, so with the object check moved below them the field
        guards would read its fields and refuse for one of those instead.
        Its `enforce_admins` is disabled, so that is the sentence a reordered
        method would produce, and it is not the one asserted here.
        """
        self.assert_refused(MappingProxyType(protection_document(enforce_admins={"enabled": False})),
                            "branch protection could not be observed")
        both = protection_document(enforce_admins={"enabled": False})
        del both["required_pull_request_reviews"]
        self.assert_refused(both, "branch protection does not enforce administrators")
        both = protection_document(required_status_checks={"strict": False, "contexts": ["check"]})
        del both["required_pull_request_reviews"]
        self.assert_refused(both, "branch protection does not require pull requests")
        reviews = {"bypass_pull_request_allowances": {"users": [{"login": "someone"}]}}
        both = protection_document(required_pull_request_reviews=reviews,
                                   required_status_checks={"strict": True, "contexts": []})
        self.assert_refused(both, "branch protection requires strict, named CI checks")

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

    def test_a_document_that_passes_every_guard_is_returned_unchanged(self) -> None:
        """The guards refuse shapes, not every document: the valid ones pass.

        The fixture's document, one whose CI rule names its checks in the
        app-bound `checks` list and not in `contexts`, and one whose
        allowance lists are present and empty. The object handed back is the
        one the transport parsed, so the merge's second read compares against
        exactly what GitHub said.
        """
        for label, value in (
            ("fixture", protection_document()),
            ("app-bound checks only", protection_document(
                required_status_checks={"strict": True, "checks": [{"context": "check", "app_id": 7}]})),
            ("empty allowance lists", protection_document(required_pull_request_reviews={
                "required_approving_review_count": 1,
                "bypass_pull_request_allowances": {"users": [], "teams": [], "apps": []}})),
        ):
            with self.subTest(shape=label):
                self.assertIs(StubbedGitHub(value).protection("main"), value)


HEAD = "0123456789abcdef0123456789abcdef01234567"


def pull_document(**changes: Any) -> dict:
    """A pull-request document that passes every guard of `GitHub.ready` up
    to the `compare` call: open, not a draft, at `HEAD` on `main`, from the
    stubbed repository, and confirmed mergeable and clean by GitHub."""
    value: dict[str, Any] = {
        "merged": False,
        "state": "open",
        "draft": False,
        "head": {"sha": HEAD, "repo": {"full_name": "fixture/repo"}},
        "base": {"ref": "main"},
        "mergeable": True,
        "mergeable_state": "clean",
    }
    value.update(changes)
    return value


class ReadyCase(unittest.TestCase):
    """The moved-default-branch clause of sd:10 criterion 13: a default branch
    that moves after the review is refused, not integrated, and each refusal
    is asserted by its message."""

    def assert_ready_refused(self, pull: dict, answer: Any, message: str) -> list[str]:
        remote = StubbedGitHub(answer)
        with self.assertRaisesRegex(sd_ship_remote.Refusal, rf"^{re.escape(message)}$"):
            remote.ready(pull, HEAD, "main", protection_document())
        return remote.requested

    def test_a_head_that_moved_after_the_local_review_is_refused_by_name(self) -> None:
        """The pull request's head is no longer the reviewed commit. The
        refusal is decided on the document, before any further call."""
        moved = pull_document(head={"sha": "f" * 40, "repo": {"full_name": "fixture/repo"}})
        requested = self.assert_ready_refused(
            moved, {"behind_by": 0}, "pull-request head or default base moved after local review")
        self.assertEqual(requested, [])

    def test_a_base_that_moved_after_the_local_review_is_refused_by_name(self) -> None:
        """The pull request now targets a branch other than the default the
        review was made against. Same refusal, same silence on the wire."""
        moved = pull_document(base={"ref": "release"})
        requested = self.assert_ready_refused(
            moved, {"behind_by": 0}, "pull-request head or default base moved after local review")
        self.assertEqual(requested, [])

    def test_a_reviewed_branch_behind_the_default_branch_is_refused_by_name(self) -> None:
        """The document is fine, so the method asks GitHub how the reviewed
        head compares with the default branch. Any answer but `behind_by: 0`
        refuses: a branch the default has moved past, and a comparison that
        does not say."""
        for label, answer in (("behind by three", {"behind_by": 3}), ("no behind_by", {"ahead_by": 1})):
            with self.subTest(shape=label):
                requested = self.assert_ready_refused(
                    pull_document(), answer, "the reviewed branch is behind the current default branch")
                self.assertEqual(requested, [f"repos/fixture/repo/compare/main...{HEAD}"])

    def test_a_branch_level_with_the_default_passes_the_comparison_guard(self) -> None:
        """`behind_by: 0` passes, so the next refusal comes from the check-run
        inventory, which the stub answers with the same non-list document.
        That pins the guard's order: the comparison is consulted before the
        check runs, and a level branch is not refused by it."""
        requested = self.assert_ready_refused(
            pull_document(), {"behind_by": 0}, "GitHub did not enumerate "
            f"repos/fixture/repo/commits/{HEAD}/check-runs?filter=latest")
        self.assertEqual(requested[0], f"repos/fixture/repo/compare/main...{HEAD}")


if __name__ == "__main__":
    unittest.main()
