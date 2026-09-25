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

import sd_protection  # noqa: E402 - after the path insert
import sd_ship_remote  # noqa: E402


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
DEPLOY_KEY = {"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}
DEPLOY_KEY_WORDS = "main (#42) [pull_request, required_status_checks]: DeployKey (always)"


def acceptance(gap: str, **state: Any) -> dict:
    """One `accepted_gaps` entry as `.github/sd-status.json` carries it."""
    return {"id": gap, "state": state, "because": "autocommit", "since": "2026-09-23", "until": "later"}


BYPASS_ACCEPTED = acceptance("bypass", bypass=[DEPLOY_KEY_WORDS])
STRICT_ACCEPTED = acceptance("strict", strict=False, bypass=[DEPLOY_KEY_WORDS])
NOT_PROTECTED = (404, {"message": "Branch not protected"})
PLAN_LIMITED = (403, {"message": "Upgrade to GitHub Pro or make this repository public to enable this feature."})


class PathStubbedGitHub(sd_ship_remote.GitHub):
    """The adapter with each path answered on its own, so `/protection` can
    be a 404 while `/rules/branches/main` is a 200 with rules."""

    def __init__(self, answers: dict[str, tuple[int, Any]], declaration: dict | None = None,
                 acceptances: list[dict] | None = None):
        super().__init__(ROOT, "fixture/repo")
        self.answers = answers
        self.declaration = declaration
        self.acceptances_at_head = acceptances or []
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

    def accepted_gaps(self, head: str) -> list[dict]:
        return self.acceptances_at_head


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
               declaration: dict | None = None, acceptances: list[dict] | None = None) -> PathStubbedGitHub:
        answers = {f"{self.PREFIX}/branches/main/protection": classic}
        if rules is not None:
            answers.update(self.paged(rules))
        if ruleset is not None:
            answers[f"{self.PREFIX}/rulesets/42"] = (200, ruleset)
        return PathStubbedGitHub(answers, declaration, acceptances)

    def paged(self, rules: list) -> dict[str, tuple[int, Any]]:
        """`rules` as the endpoint pages them, `PAGE_SIZE` a page, with the
        empty page after a full last one. The bare, pre-pagination path is
        answered with page one as well: a reader that stops after one
        request then sees a full page rather than a 404, which is what
        makes the pagination test fail for the right reason on such a
        reader instead of on a route it never had."""
        size = sd_protection.PAGE_SIZE
        pages = [rules[start:start + size] for start in range(0, len(rules), size)] or [[]]
        if len(pages[-1]) == size:
            pages.append([])
        answers: dict[str, tuple[int, Any]] = {
            sd_protection.rules_path(self.PREFIX, "main", number): (200, page) for number, page in enumerate(pages, 1)}
        answers[f"{self.PREFIX}/rules/branches/main"] = (200, pages[0])
        return answers

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
                                            sd_protection.rules_path(self.PREFIX, "main", 1),
                                            f"{self.PREFIX}/rulesets/42"])
        # A second read of the same remote is the same object, which is what
        # `still_gated`'s equality compares.
        self.assertEqual(self.remote(ruleset_rules()).gate("main", HEAD), value)

    def test_every_page_of_rules_is_read_before_they_are_reduced(self) -> None:
        """The rules endpoint answers `PAGE_SIZE` rules a page. A reader that
        took the first page for the whole list would miss the gating rules on
        the second and see a weaker branch than the real one -- Path B and a
        refusal for want of a declaration, where the truth is Path A. So a
        full first page costs a second request, and the second page's rules
        are what the gate validates."""
        size = sd_protection.PAGE_SIZE
        filler = [{"type": "tag_name_pattern", "ruleset_id": 42, "parameters": {"pattern": f"v{n}"}}
                  for n in range(size)]
        remote = self.remote(filler + ruleset_rules())
        value = remote.gate("main", HEAD)
        rules_requests = [path for path in remote.requested if "/rules/branches/" in path]
        self.assertGreater(len(rules_requests), 1)
        self.assertEqual(rules_requests, [sd_protection.rules_path(self.PREFIX, "main", 1),
                                          sd_protection.rules_path(self.PREFIX, "main", 2)])
        self.assertEqual(value["required_status_checks"]["contexts"], ["check"])
        self.assertEqual(value["required_pull_request_reviews"]["required_approving_review_count"], 1)
        # Exactly one full page: the reader asks once more and is told the end.
        exact = self.remote(filler[3:] + ruleset_rules())
        self.assertEqual(exact.gate("main", HEAD)["required_status_checks"]["contexts"], ["check"])
        self.assertEqual(len([path for path in exact.requested if "/rules/branches/" in path]), 2)

    def test_a_rules_list_that_never_comes_back_short_is_a_refusal_not_a_hang(self) -> None:
        full = [{"type": "deletion", "ruleset_id": 42}] * sd_protection.PAGE_SIZE

        class Endless(PathStubbedGitHub):
            def api_status(self, path: str) -> tuple[int, Any]:
                if "/rules/branches/" not in path:
                    return super().api_status(path)
                self.requested.append(path)
                return 200, full

        remote = Endless({f"{self.PREFIX}/branches/main/protection": NOT_PROTECTED}, DECLARATION)
        error = self.refused(remote, rf"^branch rulesets ran past {sd_protection.MAX_PAGES} pages")
        self.assertEqual(error.workflow["blocker"]["code"], "prerequisite_failed")
        self.assertEqual(len(remote.requested), 1 + sd_protection.MAX_PAGES)

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

    def test_a_ruleset_with_bypass_actors_is_refused_naming_the_ruleset_and_the_actor(self) -> None:
        """Any actor: a gate an app can walk past is no more authority than
        one an admin can. The refusal names who, so the fix is the right
        ruleset entry and not the admin setting the old words pointed at."""
        for actors, words in (
            ([{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
             r"RepositoryRole 5 \(always\)"),
            ([{"actor_id": 77, "actor_type": "Integration", "bypass_mode": "pull_request"}],
             r"Integration 77 \(pull_request\)"),
        ):
            with self.subTest(actors=actors):
                bypass = dict(RULESET, name="release", bypass_actors=actors)
                error = self.refused(self.remote(ruleset_rules(), bypass),
                                     rf"^ruleset release \(#42\) can be bypassed by {words}$")
                self.assertEqual(error.workflow["blocker"]["code"], "protection_required")

    def test_an_undeclared_deploy_key_bypass_refuses_as_any_actor_does(self) -> None:
        """sd:1451's refusal, kept: without a declaration a deploy key that
        can walk past the ruleset is refused by name like any other actor."""
        error = self.refused(self.remote(ruleset_rules(), dict(RULESET, bypass_actors=[DEPLOY_KEY])),
                             r"^ruleset main \(#42\) can be bypassed by DeployKey \(always\)$")
        self.assertEqual(error.workflow["blocker"]["code"], "protection_required")

    def test_a_declared_deploy_key_bypass_merges_and_travels_on_the_object(self) -> None:
        """The reviewed commit's `bypass` acceptance lists the deploy key in
        `sd-status`'s words -- two rules in brackets, as platypeeps/system's
        ruleset carries since its `pull_request` rule -- so the gate grants,
        and the object the receipt records names the entry it honoured."""
        value = self.remote(ruleset_rules(), dict(RULESET, bypass_actors=[DEPLOY_KEY]),
                            acceptances=[BYPASS_ACCEPTED]).gate("main", HEAD)
        self.assertEqual(value["accepted_gaps"], [{key: BYPASS_ACCEPTED[key] for key in ("id", "state", "since", "until")}])
        self.assertEqual(value["source"], "ruleset")
        self.assertEqual(sd_protection.bypass_words(value), [DEPLOY_KEY_WORDS])
        # No bypass, nothing honoured: a firm ruleset's object is unchanged.
        self.assertNotIn("accepted_gaps", self.remote(ruleset_rules(), acceptances=[BYPASS_ACCEPTED]).gate("main", HEAD))

    def test_a_declared_bypass_list_must_equal_the_live_one(self) -> None:
        """Exact match, both ways: the one-rule words system declared before
        its ruleset grew a `pull_request` rule, and a list naming a second
        key that is not there, each leave the live bypass undeclared."""
        one_rule = "main (#42) [required_status_checks]: DeployKey (always)"
        for label, listed in (("rules moved", [one_rule]), ("extra entry", sorted([DEPLOY_KEY_WORDS, one_rule]))):
            with self.subTest(label):
                self.refused(self.remote(ruleset_rules(), dict(RULESET, bypass_actors=[DEPLOY_KEY]),
                                         acceptances=[acceptance("bypass", bypass=listed)]),
                             r"^ruleset main \(#42\) can be bypassed by DeployKey \(always\)$")
        # Another gap's entry pinning the same list accepts that gap, not this one.
        self.refused(self.remote(ruleset_rules(), dict(RULESET, bypass_actors=[DEPLOY_KEY]),
                                 acceptances=[STRICT_ACCEPTED]),
                     r"^ruleset main \(#42\) can be bypassed by DeployKey \(always\)$")

    def test_a_declared_deploy_key_does_not_cover_another_actor_type_or_mode(self) -> None:
        """The declaration never widens: a role or an app beside the key
        refuses even when the declared list names it too, since only a deploy
        key can be declared, and the key in a mode the list does not name
        refuses because the list no longer equals the live one."""
        role = {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        app_words = "main (#42) [pull_request, required_status_checks]: Integration 77 (pull_request)"
        for label, actors, listed, words in (
            ("role beside the key", [DEPLOY_KEY, role], [DEPLOY_KEY_WORDS],
             r"DeployKey \(always\), RepositoryRole 5 \(always\)"),
            ("role alone", [role], [DEPLOY_KEY_WORDS], r"RepositoryRole 5 \(always\)"),
            ("app declared beside the key", [DEPLOY_KEY, INTEGRATION], sorted([DEPLOY_KEY_WORDS, app_words]),
             r"DeployKey \(always\), Integration 77 \(pull_request\)"),
            ("key in another mode", [dict(DEPLOY_KEY, bypass_mode="pull_request")], [DEPLOY_KEY_WORDS],
             r"DeployKey \(pull_request\)"),
        ):
            with self.subTest(label):
                error = self.refused(self.remote(ruleset_rules(), dict(RULESET, bypass_actors=actors),
                                                 acceptances=[acceptance("bypass", bypass=listed)]),
                                     rf"^ruleset main \(#42\) can be bypassed by {words}$")
                self.assertEqual(error.workflow["blocker"]["code"], "protection_required")

    def test_a_declared_strict_gap_is_honoured_only_on_its_exact_state(self) -> None:
        """platypeeps/system's shape: named checks without `strict`, and the
        deploy key. Both acceptances matching, the gate grants and records
        both. A `strict` entry pinning another bypass list, one that does not
        pin `strict` at all, or checks with no name, still refuse."""
        lax = ruleset_rules()
        lax[2]["parameters"]["strict_required_status_checks_policy"] = False
        keyed = dict(RULESET, bypass_actors=[DEPLOY_KEY])
        value = self.remote(lax, keyed, acceptances=[BYPASS_ACCEPTED, STRICT_ACCEPTED]).gate("main", HEAD)
        self.assertEqual([gap["id"] for gap in value["accepted_gaps"]], ["bypass", "strict"])
        self.assertFalse(value["required_status_checks"]["strict"])
        # Firm and lax, with no bypass: `strict` pinning `bypass: []` is that state.
        firm = self.remote(lax, acceptances=[acceptance("strict", strict=False, bypass=[])]).gate("main", HEAD)
        self.assertEqual([gap["id"] for gap in firm["accepted_gaps"]], ["strict"])
        unnamed = [dict(rule) for rule in lax]
        unnamed[2] = {**lax[2], "parameters": {**lax[2]["parameters"], "required_status_checks": []}}
        for label, rules, accepted in (
            ("strict not accepted", lax, [BYPASS_ACCEPTED]),
            ("another bypass list", lax, [BYPASS_ACCEPTED, acceptance("strict", strict=False, bypass=[])]),
            ("strict not pinned", lax, [BYPASS_ACCEPTED, acceptance("strict", bypass=[DEPLOY_KEY_WORDS])]),
            ("strict pinned true", lax, [BYPASS_ACCEPTED, acceptance("strict", strict=True, bypass=[DEPLOY_KEY_WORDS])]),
            ("no named checks", unnamed, [BYPASS_ACCEPTED, STRICT_ACCEPTED]),
        ):
            with self.subTest(label):
                self.refused(self.remote(rules, keyed, acceptances=accepted),
                             r"^ruleset protection requires strict, named CI checks$")

    def test_no_declaration_accepts_a_missing_pull_request_rule(self) -> None:
        """The refusal sd:1451 does not touch: a ruleset with no
        `pull_request` rule refuses whatever the head accepts."""
        self.refused(self.remote(ruleset_rules(pull_request=None), dict(RULESET, bypass_actors=[DEPLOY_KEY]),
                                 acceptances=[acceptance("bypass", bypass=[
                                     "main (#42) [required_status_checks]: DeployKey (always)"]),
                                     acceptance("reviews", required_pull_request_reviews=False)]),
                     r"^ruleset protection does not require pull requests$")

    def test_a_bypass_list_not_shown_is_unknown_and_refuses_while_an_empty_one_validates(self) -> None:
        """GitHub returns `bypass_actors` only to a caller who can edit the
        ruleset: absent on log-distiller read with `maintain`, `[]` on
        mezmo-world-simulator read with `admin` (2026-09-22). The pair is the
        proof the default was not merely inverted: `[]` is nobody and
        validates; absent, or `null`, is unknown and refuses, as a failed
        prerequisite and not as a protection defect, because what is missing
        is the token's view and not the ruleset's rule."""
        shown = self.remote(ruleset_rules(), RULESET).gate("main", HEAD)
        self.assertEqual(shown["enforce_admins"], {"enabled": True})
        self.assertEqual(shown["rulesets"][0]["bypass_actors"], [])
        for withheld in ({"id": 42, "name": "main", "enforcement": "active"}, dict(RULESET, bypass_actors=None)):
            with self.subTest(ruleset=withheld):
                error = self.refused(self.remote(ruleset_rules(), withheld),
                                     r"^ruleset main \(#42\) did not show its bypass actors, "
                                     r"so whether anyone can bypass it is unknown$")
                self.assertEqual(error.workflow["blocker"]["code"], "prerequisite_failed")
                self.assertIn("token that can edit it", error.workflow["next_action"])
                # The synthesized object keeps the state apart from both
                # answers, so a report reads it as unknown too.
                value = sd_protection.synthesize(ruleset_rules(), {42: withheld})
                self.assertEqual(value["enforce_admins"], {"enabled": None})
                self.assertIsNone(value["rulesets"][0]["bypass_actors"])

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
        error = self.refused(unreadable, rf"^no route for {re.escape(sd_protection.rules_path(self.PREFIX, 'main', 1))} "
                                         r"\(HTTP 404\)$")
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



# --------------------------------------------------------------------------
# Classic protection and rulesets together (sd:1419)
# --------------------------------------------------------------------------

INTEGRATION = {"actor_id": 77, "actor_type": "Integration", "bypass_mode": "pull_request"}
ORG_ADMIN = {"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}


class ClassicAndRulesetCase(unittest.TestCase):
    """`GitHub.gate` when classic answers 200 *and* a ruleset applies.

    Before sd:1419 a 200 was the whole answer and the rulesets were never
    read. GitHub layers the two, strictest per rule, and the operator's
    decisions of 2026-09-24 settle the rest: a bypass refuses only when it
    removes the last firm source of a rule (Q2), a stricter rule a bypass
    can skip is advisory and never grants (Q3), and administrators are
    enforced on a rule when any source imposing it binds them (Q1).
    """

    PREFIX = RulesetCase.PREFIX
    remote = RulesetCase.remote
    paged = RulesetCase.paged
    refused = RulesetCase.refused

    def both(self, classic: dict | None = None, rules: list | None = None, ruleset: dict | None = RULESET,
             **kwargs: Any) -> PathStubbedGitHub:
        return self.remote(ruleset_rules() if rules is None else rules, ruleset,
                           classic=(200, protection_document() if classic is None else classic), **kwargs)

    def test_classic_with_no_ruleset_is_the_classic_object_unchanged(self) -> None:
        for rules in ([], [{"type": "deletion", "ruleset_id": 42}]):
            with self.subTest(rules=rules):
                self.assertEqual(self.both(rules=rules).gate("main", HEAD), protection_document())

    def test_the_same_rules_in_both_are_one_combined_requirement(self) -> None:
        value = self.both().gate("main", HEAD)
        self.assertEqual(value["source"], "combined")
        self.assertEqual(value["sources"], {"pull_request": ["classic", "ruleset:42"],
                                            "required_status_checks": ["classic", "ruleset:42"]})
        self.assertEqual(value["enforce_admins"], {"enabled": True})
        self.assertEqual(value["required_pull_request_reviews"]["required_approving_review_count"], 1)
        self.assertEqual(value["required_status_checks"],
                         {"strict": True, "contexts": ["check"], "checks": [{"context": "check", "app_id": 7}]})
        self.assertEqual((value["advisory"], value["bypass_info"]), ([], []))
        self.assertEqual(self.both().gate("main", HEAD), value)

    def test_a_ruleset_bypass_beside_firm_classic_is_information_not_a_refusal(self) -> None:
        """Classic still enforces both rules on everyone, so the app that can
        walk past the ruleset walks into classic: nothing it removes is the
        last enforcement. The same holds for a list GitHub did not show."""
        for ruleset, words in ((dict(RULESET, bypass_actors=[INTEGRATION]),
                                "main (#42) [pull_request, required_status_checks]: Integration 77 (pull_request)"),
                               ({"id": 42, "name": "main", "enforcement": "active"},
                                "main (#42) [pull_request, required_status_checks]: bypass_actors not shown")):
            with self.subTest(ruleset=ruleset):
                value = self.both(ruleset=ruleset).gate("main", HEAD)
                self.assertEqual(value["bypass_info"], [words])
                self.assertEqual(value["enforce_admins"], {"enabled": True})

    def test_a_ruleset_bypass_that_removes_the_last_enforcement_refuses(self) -> None:
        """Classic requires reviews only; the checks come from the ruleset
        alone, and the app can bypass it: the checks rule has no firm
        source, so the bypass is decisive and the refusal names it."""
        classic = protection_document()
        del classic["required_status_checks"]
        self.refused(self.both(classic, ruleset=dict(RULESET, bypass_actors=[INTEGRATION])),
                     r"^ruleset main \(#42\) can be bypassed by Integration 77 \(pull_request\)$")
        self.refused(self.both(classic, ruleset={"id": 42, "name": "main", "enforcement": "active"}),
                     r"^ruleset main \(#42\) did not show its bypass actors")
        # The same ruleset without the bypass is firm, and the gate grants.
        self.assertEqual(self.both(classic).gate("main", HEAD)["firm"]["required_status_checks"], ["ruleset:42"])

    def test_a_stricter_bypassable_ruleset_is_advisory_and_never_grants(self) -> None:
        """The ruleset asks for strict checks and two approvals, and an app
        can bypass it. Classic asks for one approval and lax checks. The
        effective requirement is classic's, so the lax checks still refuse,
        and the stricter asks are named as advisory."""
        rules = ruleset_rules()
        rules[1]["parameters"]["required_approving_review_count"] = 2
        lax = protection_document(required_status_checks={"strict": False, "contexts": ["check"]})
        remote = self.both(lax, rules, dict(RULESET, bypass_actors=[INTEGRATION]))
        self.refused(remote, r"^branch protection requires strict, named CI checks$")
        value = sd_protection.combine(lax, rules, {42: dict(RULESET, bypass_actors=[INTEGRATION])})
        self.assertEqual(value["required_pull_request_reviews"]["required_approving_review_count"], 1)
        self.assertFalse(value["required_status_checks"]["strict"])
        self.assertEqual(len(value["advisory"]), 2)
        self.assertIn("main (#42) [pull_request] asks for more than the firm sources", value["advisory"][0])
        # Firm, the same ruleset is the requirement: two approvals, strict.
        firm = self.both(lax, rules).gate("main", HEAD)
        self.assertEqual(firm["required_pull_request_reviews"]["required_approving_review_count"], 2)
        self.assertTrue(firm["required_status_checks"]["strict"])
        self.assertEqual(firm["advisory"], [])

    def test_admins_are_enforced_per_rule_by_any_source_that_binds_them(self) -> None:
        """Q1. Classic exempts admins; a firm ruleset carrying both rules
        binds them on both, so they are enforced. Carrying only the review
        rule, it leaves the checks rule to classic alone, which exempts them,
        and the gate refuses as it does today."""
        exempt = protection_document(enforce_admins={"enabled": False})
        value = self.both(exempt).gate("main", HEAD)
        self.assertEqual(value["enforce_admins"], {"enabled": True})
        self.assertEqual(value["admins"], {"pull_request": True, "required_status_checks": True})
        partial = self.both(exempt, ruleset_rules(required_status_checks=None))
        self.refused(partial, r"^branch protection does not enforce administrators$")
        self.assertEqual(sd_protection.combine(exempt, ruleset_rules(required_status_checks=None), {42: RULESET})
                         ["admins"], {"pull_request": True, "required_status_checks": False})

    def test_an_admin_bypass_on_the_ruleset_beside_classic_enforcing_admins_is_information(self) -> None:
        value = self.both(ruleset=dict(RULESET, bypass_actors=[ORG_ADMIN])).gate("main", HEAD)
        self.assertEqual(value["enforce_admins"], {"enabled": True})
        self.assertEqual(sd_protection.bypass_words(value, True), [])
        self.assertEqual(value["bypass_info"],
                         ["main (#42) [pull_request, required_status_checks]: OrganizationAdmin 1 (always)"])
        # Both sources exempting admins is enforce_admins off.
        both_off = self.both(protection_document(enforce_admins={"enabled": False}),
                             ruleset=dict(RULESET, bypass_actors=[ORG_ADMIN]))
        self.refused(both_off, r"can be bypassed by OrganizationAdmin 1 \(always\)$")

    def test_a_rules_read_that_fails_keeps_the_classic_gate(self) -> None:
        remote = self.remote(None, None, classic=(200, protection_document()))
        self.assertEqual(remote.gate("main", HEAD), protection_document())


if __name__ == "__main__":
    unittest.main()
