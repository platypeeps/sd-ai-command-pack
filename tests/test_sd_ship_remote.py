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


# --------------------------------------------------------------------------
# Rulesets: the second mechanism the gate reads (sd:1327, sd:1323)
# --------------------------------------------------------------------------

RULESET = {"id": 42, "name": "main", "enforcement": "active", "bypass_actors": []}


def ruleset_rules(**changes: Any) -> list[dict]:
    """The rules `repos/{slug}/rules/branches/main` lists for a ruleset that
    gates a merge the way the classic fixture does: a review rule and a
    strict, app-bound check. Shaped as answerbook/log-distiller's `main`
    answered on 2026-09-22, ids and names aside."""
    rules: dict[str, dict] = {
        "deletion": {"type": "deletion", "ruleset_id": 42},
        "pull_request": {"type": "pull_request", "ruleset_id": 42,
                         "parameters": {"required_approving_review_count": 1, "dismiss_stale_reviews_on_push": False,
                                        "require_code_owner_review": False, "require_last_push_approval": False,
                                        "allowed_merge_methods": ["squash"]}},
        "required_status_checks": {"type": "required_status_checks", "ruleset_id": 42,
                                   "parameters": {"strict_required_status_checks_policy": True,
                                                  "do_not_enforce_on_create": False,
                                                  "required_status_checks": [{"context": "check", "integration_id": 7}]}},
    }
    for name, value in changes.items():
        if value is None:
            del rules[name]
        else:
            rules[name] = value
    return list(rules.values())


DECLARATION = {"declared_gap": "unprotected", "until": "a second account exists"}
NOT_PROTECTED = (404, {"message": "Branch not protected"})
PLAN_LIMITED = (403, {"message": "Upgrade to GitHub Pro or make this repository public to enable this feature."})


class PathStubbedGitHub(sd_ship_remote.GitHub):
    """The adapter with each path answered on its own, so `/protection` can
    be a 404 while `/rules/branches/main` is a 200 with rules."""

    def __init__(self, answers: dict[str, tuple[int, Any]], declaration: dict | None = None):
        super().__init__(ROOT, "fixture/repo")
        self.answers = answers
        self.declaration = declaration
        self.requested: list[str] = []

    def api_status(self, path: str) -> tuple[int, Any]:
        self.requested.append(path)
        return self.answers.get(path, (404, {"message": f"no route for {path}"}))

    def api(self, path: str, *, method: str = "GET", body: dict | None = None) -> Any:
        return self.api_status(path)[1]

    def declared_gap(self, head: str) -> dict | None:
        self.declaration_faults = [] if self.declaration else [
            ".github/sd-status.json at 0123456789ab carries no `unprotected` entry pinning branch_protection: false"]
        return self.declaration


class RulesetCase(unittest.TestCase):
    """`GitHub.gate` when classic protection answers 404 and a ruleset applies.

    Before sd:1327 the gate read `/protection` alone, so a ruleset-protected
    branch was "unprotected" and the gate demanded a declaration that was
    false. Now a 404 there is followed by the rules endpoint, and a ruleset
    that gates the merge is Path A, validated by the same guards as a classic
    object; one that gates nothing (`deletion` alone) is still Path B.
    """

    PREFIX = "repos/fixture/repo"

    def remote(self, rules: list | None, ruleset: dict | None = RULESET, *, classic=NOT_PROTECTED,
               declaration: dict | None = None) -> PathStubbedGitHub:
        answers = {f"{self.PREFIX}/branches/main/protection": classic}
        if rules is not None:
            answers[f"{self.PREFIX}/rules/branches/main"] = (200, rules)
        if ruleset is not None:
            answers[f"{self.PREFIX}/rulesets/42"] = (200, ruleset)
        return PathStubbedGitHub(answers, declaration)

    def refused(self, remote: PathStubbedGitHub, message: str) -> sd_ship_remote.Refusal:
        with self.assertRaisesRegex(sd_ship_remote.Refusal, message) as caught:
            remote.gate("main", HEAD)
        return caught.exception

    def test_a_ruleset_that_gates_the_merge_is_the_protection_object(self) -> None:
        """Path A through a ruleset: the object every later reader gets is
        shaped like the classic one, marked `source: ruleset`, and names the
        contributing ruleset. `ready` reads `required_status_checks.checks`
        with `app_id`, so `integration_id` lands there."""
        remote = self.remote(ruleset_rules())
        value = remote.gate("main", HEAD)
        self.assertEqual(value["source"], "ruleset")
        self.assertEqual([entry["id"] for entry in value["rulesets"]], [42])
        self.assertEqual(value["enforce_admins"], {"enabled": True})
        self.assertEqual(value["required_pull_request_reviews"]["required_approving_review_count"], 1)
        self.assertEqual(value["required_status_checks"],
                         {"strict": True, "contexts": ["check"], "checks": [{"context": "check", "app_id": 7}]})
        self.assertEqual(remote.requested, [f"{self.PREFIX}/branches/main/protection",
                                            f"{self.PREFIX}/rules/branches/main", f"{self.PREFIX}/rulesets/42"])
        # A second read of the same remote is the same object, which is what
        # `still_gated`'s equality compares.
        self.assertEqual(self.remote(ruleset_rules()).gate("main", HEAD), value)

    def test_a_ruleset_without_a_pull_request_rule_is_refused_by_name(self) -> None:
        self.refused(self.remote(ruleset_rules(pull_request=None)),
                     r"^ruleset protection does not require pull requests$")

    def test_a_ruleset_whose_checks_are_not_strict_is_refused_by_name(self) -> None:
        lax = ruleset_rules()
        lax[2]["parameters"]["strict_required_status_checks_policy"] = False
        self.refused(self.remote(lax), r"^ruleset protection requires strict, named CI checks$")
        unnamed = ruleset_rules()
        unnamed[2]["parameters"]["required_status_checks"] = []
        self.refused(self.remote(unnamed), r"^ruleset protection requires strict, named CI checks$")

    def test_a_ruleset_with_bypass_actors_is_refused_naming_the_ruleset(self) -> None:
        bypass = dict(RULESET, name="release", bypass_actors=[
            {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}])
        error = self.refused(self.remote(ruleset_rules(), bypass), r"^ruleset release \(#42\) has bypass actors$")
        self.assertEqual(error.workflow["blocker"]["code"], "protection_required")

    def test_a_ruleset_that_is_not_active_is_no_protection(self) -> None:
        """`evaluate` and `disabled` enforce nothing: Path B, as if no rule
        applied. Without a declaration that is today's refusal; with one the
        declaration is the gate."""
        for enforcement in ("evaluate", "disabled"):
            with self.subTest(enforcement=enforcement):
                idle = dict(RULESET, enforcement=enforcement)
                error = self.refused(self.remote(ruleset_rules(), idle), r"^Branch not protected \(HTTP 404\); ")
                self.assertEqual(error.workflow["blocker"]["code"], "protection_required")
                self.assertEqual(self.remote(ruleset_rules(), idle, declaration=DECLARATION).gate("main", HEAD),
                                 DECLARATION)

    def test_a_ruleset_that_gates_no_merge_leaves_the_declaration_true(self) -> None:
        """`deletion` and `non_fast_forward` alone -- answerbook/mezmo-world-simulator's
        ruleset 21772988 -- gate nothing a pull request must satisfy, so the
        branch is as unprotected as one with no ruleset: the declared gap holds."""
        rules = ruleset_rules(pull_request=None, required_status_checks=None)
        rules.append({"type": "non_fast_forward", "ruleset_id": 42})
        self.assertEqual(self.remote(rules, declaration=DECLARATION).gate("main", HEAD), DECLARATION)
        self.refused(self.remote(rules), r"^Branch not protected \(HTTP 404\); ")

    def test_a_declaration_beside_a_gating_ruleset_is_the_same_mismatch_as_beside_a_classic_object(self) -> None:
        error = self.refused(self.remote(ruleset_rules(), declaration=DECLARATION),
                             r"declares main unprotected, but a ruleset gates it \(main \(#42\)\)")
        # The same code the classic mismatch carries: the declaration is what
        # needs correcting, not the protection.
        self.assertEqual(error.workflow["blocker"]["code"], "prerequisite_failed")

    def test_no_rules_at_all_is_still_path_b(self) -> None:
        self.assertEqual(self.remote([], declaration=DECLARATION).gate("main", HEAD), DECLARATION)
        error = self.refused(self.remote([]), r"^Branch not protected \(HTTP 404\); .*carries no `unprotected` entry")
        self.assertEqual(error.workflow["blocker"]["code"], "protection_required")

    def test_rules_that_cannot_be_read_are_not_absence(self) -> None:
        """The rules endpoint answering anything but a 200 list, or a cited
        ruleset not answering, is "could not observe": a refusal, with or
        without a declaration, never Path B."""
        unreadable = self.remote(None, declaration=DECLARATION)
        error = self.refused(unreadable, r"^no route for repos/fixture/repo/rules/branches/main \(HTTP 404\)$")
        self.assertEqual(error.workflow["blocker"]["code"], "prerequisite_failed")
        gone = self.remote(ruleset_rules(), None, declaration=DECLARATION)
        error = self.refused(gone, r"^ruleset 42: no route for repos/fixture/repo/rulesets/42 \(HTTP 404\)$")
        self.assertEqual(error.workflow["blocker"]["code"], "prerequisite_failed")

    def test_a_plan_limited_403_is_feature_absent_not_permission_denied(self) -> None:
        """GitHub's `Upgrade to GitHub Pro` 403 says the plan has no branch
        protection. That is the fact a declared gap pins, so a declaration
        is honoured; without one the refusal is `plan_limited` and names
        both remedies. The rules endpoint is not read: the same plan has no
        rulesets either."""
        remote = self.remote(None, None, classic=PLAN_LIMITED)
        error = self.refused(remote, r"^Upgrade to GitHub Pro .* \(HTTP 403\)$")
        self.assertEqual(error.workflow["blocker"]["code"], "plan_limited")
        self.assertIn("plan does not offer branch protection", error.workflow["next_action"])
        self.assertIn("organization", error.workflow["next_action"])
        self.assertIn("declare the accepted gap", error.workflow["next_action"])
        self.assertEqual(remote.requested, [f"{self.PREFIX}/branches/main/protection"])
        self.assertEqual(self.remote(None, None, classic=PLAN_LIMITED, declaration=DECLARATION).gate("main", HEAD),
                         DECLARATION)

    def test_any_other_403_stays_a_failed_prerequisite(self) -> None:
        for message in ("Resource not accessible by integration", "Must have admin rights to Repository.",
                        "upgrade your token"):
            with self.subTest(message=message):
                remote = self.remote(None, None, classic=(403, {"message": message}), declaration=DECLARATION)
                error = self.refused(remote, rf"^{re.escape(message)} \(HTTP 403\)$")
                self.assertEqual(error.workflow["blocker"]["code"], "prerequisite_failed")


if __name__ == "__main__":
    unittest.main()
