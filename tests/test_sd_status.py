"""Fixtures for bin/sd-status: the whole report, and the gaps it must name.

Two levels, deliberately. The subprocess tests run the executable the way an
operator does, so an exit code under test is an exit code a caller sees. The
in-process tests reach for `workflow_checks` and `_protection_gaps` directly,
because "which enforcement legs are missing" is a pure function of two objects
and deserves to be tested as one rather than through six fake HTTP responses.

The fake `gh`, the fixture repository and the read-only digest come from
`tests.test_sd_pr_state`; there is one copy of them and this module imports it.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.machinery
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any

from tests.test_sd_pr_state import BIN, SD_STATUS, ToolFixture, tree_digest

SD_HANDOFF = BIN / "sd-handoff"


def _load(name: str, module_name: str) -> Any:
    path = BIN / name
    loader = importlib.machinery.SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_file_location(module_name, str(path), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return module


status = _load("sd-status", "sd_status_under_test")

WORKFLOW = """\
name: Tests
on:
  pull_request:
  push:
    branches: [main]
jobs:
  unittest:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            python-version: "3.10"
          - os: macos-latest
            python-version: "3.13"
    steps:
      - run: make test
  shell-coverage:
    name: Shell coverage
    runs-on: ubuntu-latest
    steps:
      - run: make shell
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: make lint
"""

PRD = """\
---
title: {title}
status: {status}
created: 2026-08-01
{extra}---

# {title}
"""


class WorkflowCheckNameTests(unittest.TestCase):
    """The names GitHub will report, derived from the file rather than guessed."""

    def setUp(self) -> None:
        self._fixture = ToolFixture("run")
        self._fixture.setUp()
        self.addCleanup(self._fixture.doCleanups)
        self.repo = self._fixture.repo
        self.workflows = self.repo / ".github" / "workflows"
        self.workflows.mkdir(parents=True)

    def write(self, name: str, body: str) -> None:
        (self.workflows / name).write_text(body, encoding="utf-8")

    def test_matrix_include_names_match_githubs_spelling(self) -> None:
        self.write("tests.yml", WORKFLOW)
        produced, notes = status.workflow_checks(self.repo)
        self.assertEqual(
            produced,
            {
                "unittest (ubuntu-latest, 3.10)",
                "unittest (macos-latest, 3.13)",
                "Shell coverage",
                "lint",
            },
        )
        self.assertEqual(notes, [])

    def test_plain_axes_cross_multiply_in_declaration_order(self) -> None:
        self.write(
            "axes.yml",
            "on: [pull_request]\n"
            "jobs:\n"
            "  build:\n"
            "    strategy:\n"
            "      matrix:\n"
            "        os: [linux, mac]\n"
            "        node: [20, 22]\n"
            "    steps:\n"
            "      - run: true\n",
        )
        produced, _ = status.workflow_checks(self.repo)
        self.assertEqual(
            produced,
            {
                "build (linux, 20)",
                "build (linux, 22)",
                "build (mac, 20)",
                "build (mac, 22)",
            },
        )

    def test_a_workflow_without_a_pull_request_trigger_produces_nothing(self) -> None:
        self.write(
            "nightly.yml",
            "on:\n  schedule:\n    - cron: '0 3 * * *'\njobs:\n  sweep:\n"
            "    steps:\n      - run: true\n",
        )
        produced, _ = status.workflow_checks(self.repo)
        self.assertEqual(produced, set())

    def test_a_reusable_workflow_call_is_a_note_not_a_guess(self) -> None:
        self.write(
            "call.yml",
            "on: [pull_request]\njobs:\n  shared:\n    uses: acme/ci/.github/workflows/x.yml@v1\n",
        )
        produced, notes = status.workflow_checks(self.repo)
        self.assertEqual(produced, set())
        self.assertTrue(any("reusable workflow" in note for note in notes))

    def test_an_unresolvable_expression_is_a_note_not_a_guess(self) -> None:
        self.write(
            "dyn.yml",
            "on: [pull_request]\njobs:\n  build:\n"
            "    name: build-${{ github.event_name }}\n    steps:\n      - run: true\n",
        )
        produced, notes = status.workflow_checks(self.repo)
        self.assertEqual(produced, set())
        self.assertTrue(any("expression" in note for note in notes))

    def test_a_conditional_job_is_reported_because_a_skip_pends_forever(self) -> None:
        self.write(
            "cond.yml",
            "on: [pull_request]\njobs:\n  build:\n"
            "    if: github.actor != 'bot'\n    steps:\n      - run: true\n",
        )
        produced, notes = status.workflow_checks(self.repo)
        self.assertEqual(produced, {"build"})
        self.assertTrue(any("conditional" in note for note in notes))

    def test_no_workflows_directory_is_stated_rather_than_silent(self) -> None:
        empty = self.repo / "empty"
        empty.mkdir()
        produced, notes = status.workflow_checks(empty)
        self.assertEqual(produced, set())
        self.assertTrue(any("no .github/workflows" in note for note in notes))


class ProtectionGapTests(unittest.TestCase):
    """Enforcement state, leg by leg. Presence is not enforcement."""

    def gaps(self, protection: dict[str, Any], produced: set[str]) -> list[str]:
        found, _ = status._protection_gaps(protection, "main", produced, [])
        return [gap["id"] for gap in found]

    def enforcing(self, **overrides: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "enforce_admins": {"enabled": True},
            "required_status_checks": {"strict": True, "contexts": ["lint"]},
            "required_pull_request_reviews": {"required_approving_review_count": 1},
        }
        record.update(overrides)
        return record

    def test_a_fully_enforcing_branch_has_no_gaps(self) -> None:
        self.assertEqual(self.gaps(self.enforcing(), {"lint"}), [])

    def test_admin_exemption_is_a_gap(self) -> None:
        found = self.gaps(self.enforcing(enforce_admins={"enabled": False}), {"lint"})
        self.assertEqual(found, ["enforce_admins"])

    def test_non_strict_checks_are_a_gap(self) -> None:
        protection = self.enforcing(
            required_status_checks={"strict": False, "contexts": ["lint"]}
        )
        self.assertEqual(self.gaps(protection, {"lint"}), ["strict"])

    def test_no_required_checks_at_all_is_a_gap(self) -> None:
        protection = self.enforcing(required_status_checks={})
        self.assertIn("required_checks", self.gaps(protection, set()))

    def test_a_required_context_no_workflow_produces_is_a_gap(self) -> None:
        protection = self.enforcing(
            required_status_checks={"strict": True, "contexts": ["lint", "ghost"]}
        )
        found, detail = status._protection_gaps(protection, "main", {"lint"}, [])
        self.assertEqual([gap["id"] for gap in found], ["required_not_produced"])
        self.assertEqual(detail["required_not_produced"], ["ghost"])

    def test_a_check_the_repo_runs_but_does_not_require_is_a_gap(self) -> None:
        found, detail = status._protection_gaps(
            self.enforcing(), "main", {"lint", "security"}, []
        )
        self.assertEqual([gap["id"] for gap in found], ["produced_not_required"])
        self.assertEqual(detail["produced_not_required"], ["security"])

    def test_a_missing_review_requirement_is_a_gap(self) -> None:
        protection = self.enforcing()
        del protection["required_pull_request_reviews"]
        self.assertEqual(self.gaps(protection, {"lint"}), ["reviews"])

    def test_zero_required_approvals_is_a_gap(self) -> None:
        protection = self.enforcing(
            required_pull_request_reviews={"required_approving_review_count": 0}
        )
        found, _ = status._protection_gaps(protection, "main", {"lint"}, [])
        self.assertEqual([gap["id"] for gap in found], ["reviews"])
        # Verbatim, not a substring. `implement.md` quotes this string as a
        # transcript of current behaviour, and a substring assertion let the
        # message be reworded with the quote left stale.
        self.assertEqual(
            found[0]["gap"],
            "a pull request is required but no approving review is: 0 approvals, so one with green CI self-merges",
        )
        # The distinction the old wording lost. Both branches report `reviews`,
        # so an assertion on the id alone passes whichever text is emitted --
        # and the two describe opposite states of the branch.
        self.assertNotIn("no pull-request review is required", found[0]["gap"])

    def test_a_missing_review_object_is_the_worse_gap_not_the_same_one(self) -> None:
        """Deleting the requirement does not leave behaviour identical.

        The `required_pull_request_reviews` object is what requires a pull
        request at all. Removing it to silence the 0-approvals row trips this
        branch instead, on a branch anybody can now push to directly. Written
        because the plan said the two were equivalent and acted on it.
        """
        protection = self.enforcing()
        # Absent, not empty: this is the shape the API returns for a branch
        # whose protection carries no review requirement at all.
        del protection["required_pull_request_reviews"]
        found, _ = status._protection_gaps(protection, "main", {"lint"}, [])
        self.assertEqual([gap["id"] for gap in found], ["reviews"])
        self.assertIn("no pull-request review is required on main", found[0]["gap"])


class AcknowledgementTests(unittest.TestCase):
    """`.github/sd-status.json`: what it accepts, and when it stops accepting.

    The one property worth more than the rest: an acknowledgement is keyed on
    the *observed protection state*, never on the gap id. `reviews` is emitted
    for two opposite states of the branch, so an entry keyed on the id would
    accept "nothing requires a pull request" while meaning "a pull request is
    required and asks for no approvals". Half of this class exists to hold
    that line.
    """

    ZERO_APPROVALS = {
        "id": "reviews",
        "state": {
            "required_pull_request_reviews": True,
            "required_approving_review_count": 0,
            "enforce_admins": True,
        },
        "because": "one maintainer, enforce_admins on",
        "since": "2026-09-01",
        "until": "a second account with merge rights exists",
    }

    def enforcing(self, **overrides: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "enforce_admins": {"enabled": True},
            "required_status_checks": {"strict": True, "contexts": ["lint"]},
            "required_pull_request_reviews": {"required_approving_review_count": 0},
        }
        record.update(overrides)
        return record

    def split(
        self, protection: dict[str, Any], entries: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        gaps, _ = status._protection_gaps(protection, "main", {"lint"}, [])
        return status._apply_acknowledgements(
            gaps, status._observed_state(protection), entries
        )

    def written(self, body: str) -> tuple[list[dict[str, Any]], list[str]]:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / ".github").mkdir()
            (root / ".github" / "sd-status.json").write_text(body, encoding="utf-8")
            return status.load_acknowledgements(root)

    def test_a_matching_acknowledgement_moves_the_finding_out_of_the_gaps(self) -> None:
        still_open, accepted = self.split(self.enforcing(), [self.ZERO_APPROVALS])
        self.assertEqual(still_open, [])
        self.assertEqual([entry["id"] for entry in accepted], ["reviews"])
        # The finding text travels with the acceptance rather than being
        # dropped: what was accepted has to stay readable.
        self.assertIn("0 approvals", accepted[0]["gap"])

    def test_an_acknowledgement_stops_applying_when_the_state_drifts(self) -> None:
        """The whole point. Accepting a state is not accepting an id forever.

        `enforce_admins` going off is half of what makes 0 approvals
        survivable here, so an entry that pinned it must not go on accepting
        the branch once it is gone.
        """
        protection = self.enforcing(enforce_admins={"enabled": False})
        still_open, accepted = self.split(protection, [self.ZERO_APPROVALS])
        self.assertEqual(accepted, [])
        ids = [gap["id"] for gap in still_open]
        self.assertIn("reviews", ids)
        stale = [gap for gap in still_open if gap["id"] == "reviews"][0]
        self.assertIn("no longer matches", stale["acknowledgement_stale"])
        self.assertIn("enforce_admins acknowledged True, observed False", stale["acknowledgement_stale"])

    def test_the_zero_approval_entry_never_accepts_the_missing_review_object(self) -> None:
        """The security case: both states are `reviews`, and only one is accepted.

        Deleting `required_pull_request_reviews` leaves a branch anybody can
        push to directly -- strictly worse than the state that was accepted.
        An acknowledgement matched on the id alone would silence exactly that.
        """
        protection = self.enforcing()
        del protection["required_pull_request_reviews"]
        still_open, accepted = self.split(protection, [self.ZERO_APPROVALS])
        self.assertEqual(accepted, [])
        self.assertEqual([gap["id"] for gap in still_open], ["reviews"])
        self.assertIn("no pull-request review is required on main", still_open[0]["gap"])
        self.assertIn("no longer matches", still_open[0]["acknowledgement_stale"])

    def test_an_unrelated_gap_is_untouched_by_an_acknowledgement(self) -> None:
        protection = self.enforcing(
            required_status_checks={"strict": False, "contexts": ["lint"]}
        )
        still_open, accepted = self.split(protection, [self.ZERO_APPROVALS])
        self.assertEqual([entry["id"] for entry in accepted], ["reviews"])
        self.assertEqual([gap["id"] for gap in still_open], ["strict"])

    def test_an_absent_file_accepts_nothing_and_is_not_a_fault(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            entries, problems = status.load_acknowledgements(pathlib.Path(directory))
        self.assertEqual((entries, problems), ([], []))

    def test_this_repos_own_file_loads_clean(self) -> None:
        entries, problems = status.load_acknowledgements(BIN.parent)
        self.assertEqual(problems, [])
        self.assertEqual([entry["id"] for entry in entries], ["reviews"])

    def test_an_empty_state_is_rejected_rather_than_accepting_the_id(self) -> None:
        # An entry with no facts would accept `reviews` whatever the branch
        # looked like, which is the shape this file must not be able to take.
        entry = dict(self.ZERO_APPROVALS, state={})
        entries, problems = self.written(json.dumps({"accepted_gaps": [entry]}))
        self.assertEqual(entries, [])
        self.assertTrue(any("must be a non-empty object" in problem for problem in problems))

    def test_a_fact_name_this_reader_cannot_observe_is_rejected(self) -> None:
        entry = dict(self.ZERO_APPROVALS, state={"requred_approving_review_count": 0})
        entries, problems = self.written(json.dumps({"accepted_gaps": [entry]}))
        self.assertEqual(entries, [])
        self.assertTrue(any("not an observable protection fact" in p for p in problems))

    def test_a_reason_and_an_end_condition_are_both_required(self) -> None:
        entry = {"id": "reviews", "state": {"enforce_admins": True}, "since": "2026-09-01"}
        entries, problems = self.written(json.dumps({"accepted_gaps": [entry]}))
        self.assertEqual(entries, [])
        self.assertTrue(any("missing because, until" in problem for problem in problems))

    def test_a_malformed_file_accepts_nothing_at_all(self) -> None:
        """Fail closed, and fail loudly. Never a partial application.

        One bad entry disables the file rather than the entry, because the
        author who wrote it meant all of it, and the failure direction that is
        safe is the one where every gap goes on printing.
        """
        entries, problems = self.written("{not json")
        self.assertEqual(entries, [])
        self.assertTrue(any("not valid JSON" in problem for problem in problems))

    def test_an_unknown_top_level_key_is_named(self) -> None:
        entries, problems = self.written(json.dumps({"accepted_gap": []}))
        self.assertEqual(entries, [])
        self.assertTrue(any("unknown key(s) accepted_gap" in problem for problem in problems))
        # `$schema` is named as known too. Listing only `accepted_gaps` would
        # read as though the schema pointer this repository's own file carries
        # were itself the mistake.
        self.assertTrue(any("known keys are $schema, accepted_gaps" in p for p in problems))


class MergeSettingsTests(unittest.TestCase):
    """The two r7 flags: what the merge button does when a human presses it."""

    def test_clean_settings_are_not_flagged(self) -> None:
        flags = status._merge_settings(
            {
                "squash_merge_commit_title": "PR_TITLE",
                "squash_merge_commit_message": "PR_BODY",
                "allow_rebase_merge": False,
            }
        )
        self.assertEqual([flag["flagged"] for flag in flags], [False, False])

    def test_commit_messages_and_rebase_are_both_flagged(self) -> None:
        flags = status._merge_settings(
            {
                "squash_merge_commit_title": "COMMIT_OR_PR_TITLE",
                "squash_merge_commit_message": "COMMIT_MESSAGES",
                "allow_rebase_merge": True,
            }
        )
        self.assertEqual([flag["id"] for flag in flags], ["squash_message", "rebase_merge"])
        self.assertEqual([flag["flagged"] for flag in flags], [True, True])


class StatusFixture(ToolFixture):
    """The full report, run as a subprocess against a fixture repository."""

    def item(self, name: str, *, status: str = "planning", extra: str = "") -> pathlib.Path:
        directory = self.repo / "docs" / "work" / name
        directory.mkdir(parents=True)
        (directory / "prd.md").write_text(
            PRD.format(title=name, status=status, extra=extra), encoding="utf-8"
        )
        return directory

    def report(self, *args: str) -> dict[str, Any]:
        return self.run_json(SD_STATUS, *args)


class ReportShapeTests(StatusFixture):
    def test_every_section_is_present(self) -> None:
        self.with_github(pulls=[])
        result = self.report()
        for key in (
            "pack",
            "work",
            "pull_requests",
            "setup",
            "protection",
            "handoff",
            "backends",
            "residue",
        ):
            self.assertIn(key, result)

    def test_the_pack_banner_names_the_checkout_the_tools_came_from(self) -> None:
        self.with_github(pulls=[])
        result = self.report()
        self.assertEqual(result["pack"]["root"], str(BIN.parent))
        completed = self.run_tool(SD_STATUS)
        self.assertIn(f"pack: {BIN.parent}", completed.stdout)

    def test_gaps_are_reported_not_raised(self) -> None:
        self.with_github(pulls=[], protection=None)
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("has no branch protection at all", completed.stdout)

    def test_pull_requests_come_from_the_same_code_path_as_sd_pr_state(self) -> None:
        self.with_github(
            pulls=[
                {
                    "number": 12,
                    "title": "One",
                    "headRefName": "task/one",
                    "baseRefName": "main",
                    "isDraft": True,
                    "mergeable": "MERGEABLE",
                    "mergeStateStatus": "BLOCKED",
                    "reviewDecision": "",
                    "headRepositoryOwner": {"login": "acme"},
                    "statusCheckRollup": [{"name": "lint", "conclusion": "SUCCESS"}],
                }
            ]
        )
        from tests.test_sd_pr_state import SD_PR_STATE

        combined = self.report()["pull_requests"]["pull_requests"]
        alone = self.run_json(SD_PR_STATE)["pull_requests"]
        self.assertEqual(combined, alone)
        self.assertIn("draft", self.run_tool(SD_STATUS).stdout)


class ProtectionSectionTests(StatusFixture):
    def test_this_repos_workflows_are_diffed_against_its_required_contexts(self) -> None:
        workflows = self.repo / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "tests.yml").write_text(WORKFLOW, encoding="utf-8")
        self.with_github(
            pulls=[],
            protection={
                "enforce_admins": {"enabled": True},
                "required_status_checks": {
                    "strict": True,
                    "contexts": [
                        "unittest (ubuntu-latest, 3.10)",
                        "unittest (macos-latest, 3.13)",
                        "Shell coverage",
                        "lint",
                    ],
                },
                "required_pull_request_reviews": {"required_approving_review_count": 1},
            },
        )
        section = self.report()["protection"]
        self.assertEqual(section["gaps"], [])
        self.assertEqual(section["detail"]["required_not_produced"], [])
        self.assertEqual(section["detail"]["produced_not_required"], [])
        self.assertIn("fully enforcing", self.run_tool(SD_STATUS).stdout)

    def test_an_unprotected_default_branch_is_one_named_gap(self) -> None:
        self.with_github(pulls=[], protection=None)
        section = self.report()["protection"]
        self.assertEqual([gap["id"] for gap in section["gaps"]], ["unprotected"])
        self.assertFalse(section["protected"])

    def test_admin_exemption_reaches_the_human_output(self) -> None:
        self.with_github(
            pulls=[],
            protection={
                "enforce_admins": {"enabled": False},
                "required_status_checks": {"strict": True, "contexts": []},
                "required_pull_request_reviews": {"required_approving_review_count": 1},
            },
        )
        completed = self.run_tool(SD_STATUS)
        self.assertIn("GAP [enforce_admins]", completed.stdout)
        self.assertIn("prose, not authority", completed.stdout)

    def acknowledge(self, *entries: dict[str, Any]) -> None:
        directory = self.repo / ".github"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "sd-status.json").write_text(
            json.dumps({"accepted_gaps": list(entries)}), encoding="utf-8"
        )

    ZERO_APPROVALS = AcknowledgementTests.ZERO_APPROVALS

    def test_an_accepted_finding_prints_as_accepted_and_leaves_the_gaps(self) -> None:
        self.acknowledge(self.ZERO_APPROVALS)
        self.with_github(
            pulls=[],
            protection={
                "enforce_admins": {"enabled": True},
                "required_status_checks": {"strict": True, "contexts": []},
                "required_pull_request_reviews": {"required_approving_review_count": 0},
            },
        )
        section = self.report()["protection"]
        # A consumer counting `gaps` sees none; one reading `accepted` sees the
        # decision. Neither has to know about the other to stay correct.
        self.assertEqual(section["gaps"], [])
        self.assertEqual([entry["id"] for entry in section["accepted"]], ["reviews"])
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ok  [reviews] accepted 2026-09-01: one maintainer", completed.stdout)
        self.assertIn("until a second account with merge rights exists", completed.stdout)
        # An accepted finding is not an absent one: the all-clear must not
        # print over the top of a state the repository wrote down.
        self.assertNotIn("fully enforcing", completed.stdout)

    def test_a_drifted_acknowledgement_prints_the_gap_and_says_it_no_longer_matches(self) -> None:
        self.acknowledge(self.ZERO_APPROVALS)
        self.with_github(
            pulls=[],
            protection={
                # The review object is gone: nothing requires a pull request
                # any more, which is the worse of the two `reviews` states.
                "enforce_admins": {"enabled": True},
                "required_status_checks": {"strict": True, "contexts": []},
            },
        )
        section = self.report()["protection"]
        self.assertEqual(section["accepted"], [])
        self.assertEqual([gap["id"] for gap in section["gaps"]], ["reviews"])
        completed = self.run_tool(SD_STATUS)
        self.assertIn("GAP [reviews] no pull-request review is required", completed.stdout)
        self.assertIn("no longer matches the live protection state", completed.stdout)

    def test_an_unreadable_acknowledgement_file_is_itself_a_gap(self) -> None:
        directory = self.repo / ".github"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "sd-status.json").write_text("[]", encoding="utf-8")
        self.with_github(
            pulls=[],
            protection={
                "enforce_admins": {"enabled": True},
                "required_status_checks": {"strict": True, "contexts": []},
                "required_pull_request_reviews": {"required_approving_review_count": 0},
            },
        )
        section = self.report()["protection"]
        self.assertEqual(
            [gap["id"] for gap in section["gaps"]], ["acknowledgements", "reviews"]
        )
        self.assertEqual(section["accepted"], [])

    def test_protection_degrades_with_no_github_remote(self) -> None:
        self.install_gh()
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no GitHub remote", completed.stdout)

    def test_a_broken_acknowledgement_file_reaches_the_terminal_without_github(self) -> None:
        """The one finding this branch can still make must not be `--json`-only.

        A malformed file is a fact about the checkout, not about GitHub. If it
        printed only when the protection object could be fetched, the file
        would silently accept nothing in exactly the situation -- no `gh`, no
        network -- where nobody is reading the JSON.
        """
        directory = self.repo / ".github"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "sd-status.json").write_text("{not json", encoding="utf-8")
        self.install_gh()
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("unavailable:", completed.stdout)
        self.assertIn("GAP [acknowledgements]", completed.stdout)
        self.assertIn("not valid JSON", completed.stdout)


class WorkItemTests(StatusFixture):
    def test_status_is_derived_and_counted(self) -> None:
        self.item("2026-08-01-alpha", status="planning")
        self.item("2026-08-02-beta", status="in_progress", extra="branch: task/beta\n")
        result = self.report()
        self.assertEqual(result["work"]["counts"], {"planning": 1, "in_progress": 1})
        self.assertEqual(result["work"]["active"], 2)

    def test_parked_is_read_from_the_items_own_frontmatter(self) -> None:
        self.item("2026-08-01-alpha")
        self.item("2026-08-02-stale", extra="parked: 2026-08-20 age-sweep\n")
        result = self.report("--parked")
        self.assertEqual(len(result["parked"]), 1)
        self.assertEqual(result["parked"][0]["parked"], "2026-08-20 age-sweep")
        self.assertEqual(result["parked"][0]["slug"], "stale")

    def test_parked_needs_no_ledger_anywhere(self) -> None:
        """Nothing outside the item directory records that it was parked."""
        self.item("2026-08-02-stale", extra="parked: 2026-08-20 age-sweep\n")
        listing = sorted(
            str(path.relative_to(self.repo))
            for path in (self.repo / "docs").rglob("*")
            if path.is_file()
        )
        self.assertEqual(listing, ["docs/work/2026-08-02-stale/prd.md"])
        self.assertEqual(len(self.report("--parked")["parked"]), 1)

    def test_no_parked_items_says_so(self) -> None:
        self.item("2026-08-01-alpha")
        completed = self.run_tool(SD_STATUS, "--parked")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no work item carries a `parked:` line", completed.stdout)

    def test_a_broken_frontmatter_status_is_an_inconsistency_not_a_crash(self) -> None:
        self.item("2026-08-01-alpha", status="sideways")
        result = self.report()
        entry = result["work"]["items"][0]
        self.assertEqual(entry["status"], "unknown")
        self.assertTrue(entry["inconsistencies"])


class HandoffTests(StatusFixture):
    """The packet is read. It is never consumed -- that is `--show`'s job."""

    def write_packet(self) -> pathlib.Path:
        completed = subprocess.run(
            [sys.executable, str(SD_HANDOFF), "--summary", "mid-refactor"],
            cwd=str(self.repo),
            env=self.env(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        found = sorted(
            (self.state / "sd-ai-command-pack" / "handoff").glob("*.json")
        )
        self.assertEqual(len(found), 1, completed.stdout)
        return found[0]

    def test_the_packet_is_reported_as_pending(self) -> None:
        self.write_packet()
        section = self.report()["handoff"]
        self.assertTrue(section["packet"]["pending"])
        self.assertEqual(section["packet"]["summary"], "mid-refactor")
        self.assertIsNone(section["packet"]["consumed"])

    def test_reading_leaves_the_file_byte_identical_and_unconsumed(self) -> None:
        path = self.write_packet()
        before = path.read_bytes()
        for _ in range(2):
            self.assertEqual(self.run_tool(SD_STATUS).returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertIsNone(json.loads(before)["consumed"])

    def test_an_already_consumed_packet_is_not_pending(self) -> None:
        path = self.write_packet()
        packet = json.loads(path.read_text(encoding="utf-8"))
        packet["consumed"] = "2026-08-29T00:00:00+00:00"
        path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        section = self.report()["handoff"]
        self.assertFalse(section["packet"]["pending"])
        self.assertIn("consumed at", section["packet"]["detail"])

    def test_no_packet_is_a_sentence_not_an_absence(self) -> None:
        completed = self.run_tool(SD_STATUS)
        self.assertIn("no packet written for this directory", completed.stdout)

    def test_lane_b_carriers_are_derived_from_origin_refs(self) -> None:
        upstream = self.base / "upstream.git"
        self.git("init", "-q", "--bare", str(upstream), cwd=self.base)
        self.git("remote", "add", "origin", str(upstream))
        self.git("checkout", "-q", "-b", "task/carry")
        (self.repo / "b.txt").write_text("two\n", encoding="utf-8")
        self.git("add", "b.txt")
        self.git("commit", "-q", "-m", "wip: half a thought")
        self.git("push", "-q", "origin", "task/carry")
        self.git("checkout", "-q", "main")
        carriers = self.report()["handoff"]["carriers"]
        self.assertEqual([entry["branch"] for entry in carriers], ["origin/task/carry"])
        self.assertIn("wip: half a thought", self.run_tool(SD_STATUS).stdout)


class ResidueTests(StatusFixture):
    def test_each_finding_carries_the_command_that_removes_it(self) -> None:
        (self.repo / ".trellis").mkdir()
        (self.repo / ".trellis" / "state.json").write_text("{}", encoding="utf-8")
        result = self.report()
        found = {entry["id"]: entry for entry in result["residue"]}
        self.assertIn("trellis", found)
        self.assertIn("rm -rf .trellis", found["trellis"]["remove"])
        self.assertIn("remove: ", self.run_tool(SD_STATUS).stdout)

    def test_a_clean_repository_reports_none(self) -> None:
        completed = self.run_tool(SD_STATUS)
        self.assertIn("none found", completed.stdout)

    def test_a_configured_hooks_path_is_residue(self) -> None:
        self.git("config", "core.hooksPath", ".githooks")
        found = {entry["id"]: entry for entry in self.report()["residue"]}
        self.assertIn("hooks-path", found)
        self.assertEqual(found["hooks-path"]["remove"], "git config --unset core.hooksPath")


class BackendTests(StatusFixture):
    def test_backends_are_reported_by_name_and_state_only(self) -> None:
        result = self.report()
        for entry in result["backends"]:
            self.assertEqual(set(entry), {"backend", "command", "state"})
            self.assertIn(entry["state"], ("present", "absent", "unauthenticated"))
        names = [entry["backend"] for entry in result["backends"]]
        self.assertIn("codex", names)
        self.assertIn("copilot", names)

    def test_an_empty_path_makes_every_backend_absent(self) -> None:
        result = self.report()
        states = {entry["backend"]: entry["state"] for entry in result["backends"]}
        # The fixture PATH holds git alone, so nothing else can be found.
        self.assertEqual(states["codex"], "absent")
        self.assertEqual(states["kimi"], "absent")


class RepoResolutionTests(StatusFixture):
    """R10-D6, asserted against the parser rather than only against --help."""

    def test_no_action_accepts_a_repository_path(self) -> None:
        for module, tool in (
            (status, "sd-status"),
            (_load("sd-pr-state", "sd_pr_state_under_test"), "sd-pr-state"),
        ):
            parser = module.build_parser()
            with self.subTest(tool=tool):
                for action in parser._actions:
                    self.assertTrue(
                        action.option_strings,
                        f"{tool} takes a positional argument: {action.dest}",
                    )
                    for option in action.option_strings:
                        self.assertNotIn(
                            option.lstrip("-"),
                            {
                                "repo",
                                "repo-path",
                                "path",
                                "root",
                                "dir",
                                "directory",
                                "cwd",
                                "checkout",
                                "worktree",
                                "fleet",
                                "all",
                                "all-repos",
                                "C",
                            },
                        )

    def test_there_is_no_fleet_walk(self) -> None:
        text = self.run_tool(SD_STATUS, "--help").stdout
        for word in ("fleet", "every installed", "all repos", "installed checkout"):
            self.assertNotIn(word, text.lower())


class IssueSectionTests(StatusFixture):
    """The `issues:` lines, which read the index and never collect.

    The fixture HOME is a temp directory, so `store.index_path()` resolves
    under it and a test can decide whether an index exists at all -- which is
    the distinction the section is built around: no index is a different answer
    from no issues, and reporting the second where the first is true is the kind
    of wrong that looks right.
    """

    def write_index(self, rows: list[dict]) -> None:
        # `sys.path` is restored: this module also exercises `sd-status`
        # in-process, and a leftover entry would let a later import resolve
        # differently depending on which test ran first.
        saved = list(sys.path)
        sys.path.insert(0, str(BIN.parent))
        try:
            from dashboard import store
        finally:
            sys.path[:] = saved

        path = self.home / ".cache" / "sd-ai-command-pack" / "index.sqlite"
        connection = store.connect(path)
        try:
            store.upsert_issues(connection, rows, "2026-08-31T00:00:00Z")
        finally:
            connection.close()

    @staticmethod
    def jira_row(key: str, why: list[str]) -> dict:
        """A row shaped the way `dashboard/jira.py` actually writes them.

        No repo, no number, a browse URL. The point of the Jira tests is what
        production rows look like, so the fixture has to look like one.
        """
        return {
            "tracker": "jira",
            "url": f"https://example.atlassian.net/browse/{key}",
            "repo": "",
            "number": None,
            "kind": "issue",
            "title": key,
            "state": "open",
            "author": "someone",
            "updated_at": "2026-08-30T00:00:00Z",
            "why": why,
        }

    @staticmethod
    def row(repo: str, number: int, why: list[str], *, tracker: str = "github") -> dict:
        return {
            "tracker": tracker,
            "url": f"https://github.com/{repo}/pull/{number}",
            "repo": repo,
            "number": number,
            "kind": "pull",
            "title": f"work on {number}",
            "state": "open",
            "author": "someone",
            "updated_at": "2026-08-30T00:00:00Z",
            "why": why,
        }

    def test_an_absent_index_says_so_rather_than_reporting_none(self) -> None:
        self.with_github(pulls=[])
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no index yet", completed.stdout)

    def test_rows_for_this_repo_are_split_by_whether_they_need_you(self) -> None:
        self.with_github(pulls=[])
        self.write_index(
            [
                self.row("acme/widget", 1, ["review-requested"]),
                self.row("acme/widget", 2, ["mentioned"]),
            ]
        )
        completed = self.run_tool(SD_STATUS)
        self.assertIn("needs you: 1", completed.stdout)
        self.assertIn("#1", completed.stdout)
        self.assertIn("other open: 1", completed.stdout)

    def test_another_repository_s_rows_are_not_shown(self) -> None:
        """The filter is the point; presence alone would pass without it."""
        self.with_github(pulls=[])
        self.write_index(
            [
                self.row("acme/widget", 1, ["assigned"]),
                self.row("other/thing", 99, ["assigned"]),
            ]
        )
        completed = self.run_tool(SD_STATUS)
        self.assertIn("needs you: 1", completed.stdout)
        self.assertNotIn("#99", completed.stdout, "another repository's issue leaked in")

    def test_a_jira_row_is_not_attributed_to_a_checkout(self) -> None:
        """Named gap: no committed fact ties a Jira project to a repository.

        A real Jira row, as `dashboard/jira.py` writes it: no repo slug at all.
        """
        self.with_github(pulls=[])
        self.write_index([self.jira_row("RS-9", ["assigned"])])
        completed = self.run_tool(SD_STATUS)
        self.assertIn("none open", completed.stdout)
        self.assertNotIn("RS-9", completed.stdout)

    def test_the_filter_is_on_the_tracker_and_not_only_on_the_slug(self) -> None:
        """Belt to the previous test's braces.

        A real Jira row carries no repo, so the test above would still pass if
        the filter were `repo == slug` alone. This one carries a matching slug
        and must still be excluded, which is only true while `tracker` is part
        of the filter.
        """
        self.with_github(pulls=[])
        self.write_index([self.row("acme/widget", 1, ["assigned"], tracker="jira")])
        completed = self.run_tool(SD_STATUS)
        self.assertIn("none open", completed.stdout)

    def test_a_copy_without_the_package_reports_rather_than_crashes(self) -> None:
        """`bin/` copied alone has no `dashboard` to import.

        The read-only suite runs exactly that copy, and it is how this coupling
        was found. Every other section here degrades to a reported reason when
        its reader is missing; this one has to as well, or one absent package
        takes the whole report down.
        """
        tools = self.base / "tools"
        shutil.copytree(BIN, tools, ignore=shutil.ignore_patterns("__pycache__"))
        self.with_github(pulls=[])
        completed = self.run_tool(tools / "sd-status")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("not importable from this checkout", completed.stdout)

    def test_the_section_is_in_the_json_report(self) -> None:
        self.with_github(pulls=[])
        self.write_index([self.row("acme/widget", 1, ["assigned"])])
        result = self.report()
        self.assertIn("issues", result)
        self.assertTrue(result["issues"]["available"])
        self.assertEqual(len(result["issues"]["needs_you"]), 1)


class ReadOnlyTests(StatusFixture):
    def test_nothing_under_the_temp_root_changes(self) -> None:
        self.with_github(pulls=[])
        self.item("2026-08-01-alpha")
        (self.repo / ".github" / "workflows").mkdir(parents=True)
        (self.repo / ".github" / "workflows" / "tests.yml").write_text(
            WORKFLOW, encoding="utf-8"
        )
        before = tree_digest(self.base)
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(tree_digest(self.base), before)

    def test_the_state_directory_is_never_created(self) -> None:
        self.with_github(pulls=[])
        self.run_tool(SD_STATUS)
        self.run_tool(SD_STATUS, "--json")
        self.run_tool(SD_STATUS, "--parked")
        self.assertFalse(self.state.exists())

    def test_the_working_tree_stays_clean(self) -> None:
        self.with_github(pulls=[])
        self.run_tool(SD_STATUS)
        self.assertEqual(self.git("status", "--porcelain").strip(), "")

    def test_the_tools_own_directory_is_not_written_to_either(self) -> None:
        """Importing a sibling module must not leave a `__pycache__` in bin/.

        The other read-only tests watch the *repository*, which is exactly
        where a tool that writes its own directory would go unnoticed. So this
        one runs a copy of bin/ and watches the copy.
        """
        tools = self.base / "tools"
        shutil.copytree(BIN, tools, ignore=shutil.ignore_patterns("__pycache__"))
        self.with_github(pulls=[])
        before = tree_digest(tools)
        for tool in ("sd-status", "sd-pr-state"):
            completed = self.run_tool(tools / tool)
            self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(tree_digest(tools), before)
        self.assertFalse((tools / "__pycache__").exists())


class InventoryFixture(StatusFixture):
    """The inventory producer, exercised in process against a fixture repo.

    In process rather than through the executable, because nothing renders the
    inventory yet: step 1 of this item lands the producer and the report is
    unchanged, so a subprocess assertion would have nothing to look at. The
    subprocess tests above still bracket the report, which is what says the
    producer stayed invisible.
    """

    #: Every age in this class is measured from one fixed day, never from the
    #: wall clock. `actionable_inventory` defaults `today` to `date.today()`,
    #: and an unpinned fixture drifts twice over: two calls that straddle
    #: midnight can order their rows differently, and a fixture item dated
    #: `2026-08-01` silently crosses `IDLE_DAYS` as real time passes and starts
    #: producing an `idle-planning` row no assertion here expects.
    TODAY = datetime.date(2026, 9, 7)

    def pull(self, **overrides: Any) -> dict[str, Any]:
        """A row shaped exactly as `sd-pr-state`'s `describe` returns one."""
        row = {
            "number": 7,
            "title": "One",
            "url": "https://github.com/acme/widget/pull/7",
            "head": "main",
            "base": "main",
            "draft": False,
            "mergeable": "MERGEABLE",
            "merge_state": "BLOCKED",
            "review_decision": "NONE",
            "checks": {"failure": 1},
            "checks_total": 1,
            "failing": ["lint"],
            "behind_by": 0,
        }
        row.update(overrides)
        return row

    def sections(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "work": status.work_section(self.repo),
            "pull_requests": {"repo": "acme/widget", "pull_requests": []},
            "protection": {"default_branch": "main", "gaps": [], "detail": {}},
            "issues": {"available": False, "needs_you": [], "other": []},
        }
        base.update(overrides)
        return base

    def rows(self, **overrides: Any) -> list[dict[str, Any]]:
        return status.actionable_inventory(
            self.repo, self.sections(**overrides), self.TODAY
        ).rows

    def by_check(self, rows: list[dict[str, Any]], check: str) -> list[dict[str, Any]]:
        return [row for row in rows if row["check"] == check]


class ClassTableTests(unittest.TestCase):
    """`CLASSES` is the enumeration, so the enumeration is what gets asserted."""

    def test_every_check_name_appears_exactly_once(self) -> None:
        names = [kind.check for kind in status.CLASSES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), len(status.BY_CHECK))

    def test_the_table_carries_the_twenty_one_checks_the_design_enumerates(self) -> None:
        # Pinned as a set, not a count: a count passes when a check is renamed
        # into a duplicate of another, which is the drift this table exists to
        # make impossible.
        self.assertEqual(
            {kind.check for kind in status.CLASSES},
            {
                "branch-already-merged", "in-progress-without-branch",
                "branch-unresolvable", "status-unreadable", "unresolved-concern",
                "pr-check-failing", "pr-check-missing", "dirty-tree-with-open-pr",
                "protection-gap", "accepted-gap-standing", "issue-needs-you",
                "pr-needs-action", "open-step", "unmerged-branch",
                "parked-concern", "idle-planning", "undated-planning",
                "issue-open", "source-marker", "unreadable-concern-row",
                "undisclosed-tool",
            },
        )

    def test_a_class_letter_is_one_lowercase_character(self) -> None:
        for kind in status.CLASSES:
            self.assertRegex(kind.letter, r"^[a-z]$")
            self.assertGreater(kind.rank, 0)
            self.assertTrue(kind.source and kind.what)

    def test_the_exclusions_are_stated_in_words_and_not_only_in_the_design(self) -> None:
        """`design.md:310` requires the report to print what it skipped."""
        self.assertTrue(status.EXCLUDED)
        for sentence in status.EXCLUDED:
            self.assertIsInstance(sentence, str)
            self.assertGreater(len(sentence.split()), 5)
        joined = " ".join(status.EXCLUDED)
        for skipped in ("archive", "parked", "Jira", "CHANGELOG.md"):
            self.assertIn(skipped, joined)


class ActionIdTests(unittest.TestCase):
    def test_two_checks_on_one_object_get_two_ids(self) -> None:
        """C-11's regression, at the level of the formula.

        A pull request can be `pr-check-failing` and `dirty-tree-with-open-pr`
        at once. Both are class `p`, so the rejected letter-keyed formula gives
        them one hash -- at four digits and at eight, which is why widening was
        no answer to it. Keyed on the check name they differ.
        """
        key = "acme/widget!7"
        pair = ("pr-check-failing", "dirty-tree-with-open-pr")
        rejected = {
            hashlib.sha1(f"p\0{key}".encode(), usedforsecurity=False).hexdigest()[:4]
            for _ in pair
        }
        self.assertEqual(len(rejected), 1, "the rejected formula collides, as C-11 says")
        self.assertEqual(len({status.action_id(check, key) for check in pair}), 2)

    def test_the_letter_is_a_display_prefix_and_the_hash_is_hex(self) -> None:
        for check, kind in status.BY_CHECK.items():
            found = status.action_id(check, "some/key")
            self.assertRegex(found, r"^[a-z][0-9a-f]{4}$")
            self.assertEqual(found[0], kind.letter)

    def test_the_same_data_gives_the_same_id_every_time(self) -> None:
        first = status.action_id("open-step", "alpha/prd.md#Steps#do it#0")
        second = status.action_id("open-step", "alpha/prd.md#Steps#do it#0")
        self.assertEqual(first, second)
        self.assertNotEqual(
            first, status.action_id("open-step", "alpha/prd.md#Steps#do it#1")
        )

    def test_a_check_the_table_does_not_carry_is_an_error_not_an_id(self) -> None:
        with self.assertRaises(KeyError):
            status.action_id("invented-check", "k")

    def test_colliding_rows_both_widen_to_eight_digits_and_say_so(self) -> None:
        rows = [
            status._row("open-step", "a", "a", "", ""),
            status._row("open-step", "b", "b", "", ""),
        ]
        rows[1]["id"] = rows[0]["id"]
        status._widen_collisions(rows)
        self.assertEqual(len({row["id"] for row in rows}), 2)
        for row in rows:
            self.assertRegex(row["id"], r"^[a-z][0-9a-f]{8}$")
            self.assertTrue(row["widened"])


class InventoryShapeTests(InventoryFixture):
    def test_every_row_carries_the_fields_the_three_sections_read(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress")
        for row in self.rows():
            self.assertEqual(set(row), {
                "id", "check", "letter", "key", "title", "detail", "suggest",
                "rank", "abnormal", "source", "age_days", "widened",
            })
            kind = status.BY_CHECK[row["check"]]
            self.assertEqual((row["rank"], row["abnormal"], row["source"]),
                             (kind.rank, kind.abnormal, kind.source))

    def test_the_ids_are_a_pure_function_of_the_data(self) -> None:
        """`implement.md`'s verification 5, run twice against one tree."""
        self.item("2026-08-01-alpha", status="in_progress")
        self.item("2026-08-02-beta")
        sections = self.sections()
        first = status.actionable_inventory(self.repo, sections, self.TODAY).rows
        second = status.actionable_inventory(self.repo, sections, self.TODAY).rows
        self.assertTrue(first)
        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        self.assertEqual(len({row["id"] for row in first}), len(first))

    def test_rows_come_out_ranked_by_class_then_age_then_id(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress")
        rows = self.rows()
        ordered = sorted(rows, key=lambda r: (r["rank"], -r["age_days"], r["id"]))
        self.assertEqual(rows, ordered)

    def test_nothing_renders_it_yet(self) -> None:
        """Step 1 is landable and invisible: the report is unchanged."""
        self.with_github(pulls=[])
        self.item("2026-08-01-alpha", status="in_progress")
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for absent in ("abnormalities", "pending", "open threads"):
            self.assertNotIn(f"\n{absent}\n", completed.stdout)
        self.assertNotIn("actions", self.report())


class WorkItemInventoryTests(InventoryFixture):
    def test_in_progress_with_no_branch_is_a_finding(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress")
        found = self.by_check(self.rows(), "in-progress-without-branch")
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["abnormal"])
        self.assertIn("2026-08-01-alpha", found[0]["detail"])

    def test_a_branch_no_ref_carries_is_a_finding_and_a_live_one_is_not(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress", extra="branch: gone/away\n")
        self.item("2026-08-02-beta", status="in_progress", extra="branch: here/now\n")
        self.git("branch", "here/now")
        found = self.by_check(self.rows(), "branch-unresolvable")
        self.assertEqual([row["title"] for row in found], ["alpha"])
        self.assertEqual(found[0]["key"], "2026-08-01-alpha")

    def test_a_planning_item_past_the_threshold_ages_into_a_finding(self) -> None:
        """`created:` is what ages an item, so the fixture writes its own."""
        ancient = self.repo / "docs" / "work" / "2026-01-01-ancient"
        ancient.mkdir(parents=True)
        (ancient / "prd.md").write_text(
            "---\ntitle: ancient\nstatus: planning\ncreated: 2026-01-01\n---\n",
            encoding="utf-8",
        )
        self.item("2026-08-01-alpha")
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        idle = self.by_check(rows, "idle-planning")
        self.assertEqual([row["key"] for row in idle], ["2026-01-01-ancient"])
        self.assertGreater(idle[0]["age_days"], status.IDLE_DAYS)

    def test_a_planning_item_with_no_date_anywhere_is_its_own_finding(self) -> None:
        directory = self.repo / "docs" / "work" / "undated-thing"
        directory.mkdir(parents=True)
        (directory / "prd.md").write_text(
            "---\ntitle: undated\nstatus: planning\n---\n\n# undated\n",
            encoding="utf-8",
        )
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        self.assertEqual(
            [row["title"] for row in self.by_check(rows, "undated-planning")],
            ["undated-thing"],
        )

    def test_parked_and_archived_items_contribute_no_rows(self) -> None:
        self.item("2026-01-01-parked", extra="parked: 2026-08-01 age-sweep\n")
        archived = self.repo / "docs" / "work" / "archive" / "2026-08"
        archived.mkdir(parents=True)
        (archived / "2026-01-01-old").mkdir()
        (archived / "2026-01-01-old" / "prd.md").write_text(
            PRD.format(title="old", status="planning", extra=""), encoding="utf-8"
        )
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        self.assertEqual([], [row for row in rows if "old" in row["key"]])
        self.assertEqual([], [row for row in rows if "parked" in row["key"]])


class OpenStepTests(InventoryFixture):
    def test_two_identical_boxes_under_one_heading_get_two_ids(self) -> None:
        """C-13: the ordinal is what stops one id naming two tasks."""
        directory = self.item("2026-08-01-alpha", status="in_progress")
        (directory / "implement.md").write_text(
            "# Steps\n\n- [ ] Run the check\n- [ ] Run the check\n- [x] Done\n",
            encoding="utf-8",
        )
        found = self.by_check(self.rows(), "open-step")
        self.assertEqual(len(found), 2)
        self.assertEqual(len({row["id"] for row in found}), 2)
        self.assertEqual({row["title"] for row in found}, {"Run the check"})

    def test_the_key_is_the_heading_and_not_the_line_number(self) -> None:
        directory = self.item("2026-08-01-alpha", status="in_progress")
        page = directory / "implement.md"
        page.write_text("# Steps\n\n- [ ] Run the check\n", encoding="utf-8")
        before = self.by_check(self.rows(), "open-step")[0]["id"]
        page.write_text(
            "# Steps\n\nA paragraph inserted above.\n\n- [ ] Run the check\n",
            encoding="utf-8",
        )
        self.assertEqual(before, self.by_check(self.rows(), "open-step")[0]["id"])

    def test_boxes_on_a_done_item_are_read_as_history(self) -> None:
        directory = self.item("2026-08-01-alpha", status="done")
        (directory / "implement.md").write_text(
            "# Steps\n\n- [ ] Run the check\n", encoding="utf-8"
        )
        self.assertEqual([], self.by_check(self.rows(), "open-step"))


class PullRequestInventoryTests(InventoryFixture):
    def test_two_checks_firing_on_one_pull_request_are_two_rows(self) -> None:
        """C-11's regression at the level of the inventory, not the formula."""
        (self.repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        pulls = {"repo": "acme/widget", "pull_requests": [self.pull()]}
        rows = self.by_check(self.rows(pull_requests=pulls), "pr-check-failing")
        rows += self.by_check(
            self.rows(pull_requests=pulls), "dirty-tree-with-open-pr"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["id"] for row in rows}), 2)
        self.assertEqual({row["key"] for row in rows}, {"acme/widget!7"})

    def test_a_pull_request_with_no_check_against_a_branch_that_requires_one(self) -> None:
        pulls = {
            "repo": "acme/widget",
            "pull_requests": [self.pull(failing=[], checks_total=0, checks={})],
        }
        protection = {
            "default_branch": "main", "gaps": [],
            "detail": {"required_contexts": ["Tests"]},
        }
        rows = self.rows(pull_requests=pulls, protection=protection)
        self.assertEqual(len(self.by_check(rows, "pr-check-missing")), 1)
        self.assertEqual(
            [], self.by_check(self.rows(pull_requests=pulls), "pr-check-missing")
        )

    def test_a_draft_is_not_waiting_on_anybody(self) -> None:
        pulls = {
            "repo": "acme/widget",
            "pull_requests": [self.pull(draft=True, failing=[])],
        }
        self.assertEqual([], self.by_check(self.rows(pull_requests=pulls),
                                           "pr-needs-action"))


class AdapterInventoryTests(InventoryFixture):
    def test_a_protection_gap_becomes_an_addressable_row(self) -> None:
        protection = {
            "default_branch": "main",
            "gaps": [{"id": "enforce_admins", "gap": "enforce_admins is off"}],
            "detail": {},
        }
        found = self.by_check(self.rows(protection=protection), "protection-gap")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["key"], "main#enforce_admins")
        self.assertIn(".github/sd-status.json", found[0]["suggest"])

    def test_an_indexed_issue_becomes_a_row_keyed_on_its_permanent_number(self) -> None:
        issues = {
            "available": True,
            "needs_you": [{
                "repo": "acme/widget", "number": 4, "title": "Fix it",
                "state": "open", "updated_at": "2026-09-01", "why": ["assigned"],
                "url": "https://github.com/acme/widget/issues/4",
            }],
            "other": [],
        }
        found = self.by_check(self.rows(issues=issues), "issue-needs-you")
        self.assertEqual([row["key"] for row in found], ["acme/widget#4"])

    def test_a_branch_on_origin_with_no_pull_request_is_an_open_thread(self) -> None:
        remote = self.base / "origin.git"
        self.git("init", "-q", "--bare", str(remote))
        self.set_origin(str(remote))
        self.git("branch", "task/one")
        self.git("push", "-q", "origin", "main", "task/one")
        self.git("fetch", "-q", "origin")
        found = self.by_check(self.rows(), "unmerged-branch")
        self.assertEqual([row["key"] for row in found], ["origin/task/one"])
        carried = {
            "repo": "acme/widget",
            "pull_requests": [self.pull(head="task/one")],
        }
        self.assertEqual(
            [], self.by_check(self.rows(pull_requests=carried), "unmerged-branch")
        )


class LowYieldProducerTests(InventoryFixture):
    def test_a_marker_in_tracked_source_is_found_and_one_in_docs_is_not(self) -> None:
        # Spelled in halves so this repository's own scan stays at zero, which
        # is the number `design.md` records for it.
        marker = "TO" + "DO"
        (self.repo / "bin").mkdir()
        (self.repo / "bin" / "thing.py").write_text(
            f"# {marker}: finish this\n", encoding="utf-8"
        )
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs" / "note.md").write_text(
            f"the {marker} convention\n", encoding="utf-8"
        )
        self.git("add", "bin/thing.py", "docs/note.md")
        self.git("commit", "-q", "-m", "markers")
        found = self.by_check(self.rows(), "source-marker")
        self.assertEqual(len(found), 1)
        self.assertIn("bin/thing.py", found[0]["detail"])

    def test_an_untracked_marker_is_not_a_finding(self) -> None:
        marker = "FIX" + "ME"
        (self.repo / "bin").mkdir()
        (self.repo / "bin" / "loose.py").write_text(
            f"# {marker}\n", encoding="utf-8"
        )
        self.assertEqual([], self.by_check(self.rows(), "source-marker"))

    def test_a_skill_naming_a_tool_that_is_not_built_is_a_row(self) -> None:
        skill = self.repo / "skills" / "sd-thing"
        skill.mkdir(parents=True)
        skill.parent.joinpath("sd-thing", "SKILL.md").write_text(
            "Run `bin/sd-thing`, which reads `bin/sd-built`.\n", encoding="utf-8"
        )
        (self.repo / "bin").mkdir(exist_ok=True)
        (self.repo / "bin" / "sd-built").write_text("#!/bin/sh\n", encoding="utf-8")
        found = self.by_check(self.rows(), "undisclosed-tool")
        self.assertEqual([row["title"] for row in found], ["bin/sd-thing"])
        self.assertFalse(found[0]["abnormal"])
        self.assertEqual(found[0]["key"], "skills/sd-thing/SKILL.md#bin/sd-thing")


class BranchLandedTests(StatusFixture):
    """`branch_landed`, against real git and injected pull-request rows.

    Real git because the whole point of the derivation is which git commands
    answer correctly in a repository that squash-merges, and a mocked `git`
    would be asserting the design rather than testing it.
    """

    def commit(self, path: str, text: str, message: str) -> str:
        (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / path).write_text(text, encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def squash_merge(self, branch: str) -> None:
        """What this repository does: one new commit, no ancestry to `branch`."""
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--squash", branch)
        self.git("commit", "-q", "-m", f"squash {branch}")

    def pull(self, **overrides: Any) -> dict[str, Any]:
        row = {
            "headRefName": "feature",
            "baseRefName": "main",
            "mergedAt": "2026-09-04T22:11:09Z",
            "headRefOid": self.git("rev-parse", "feature").strip(),
        }
        row.update(overrides)
        return row

    # -- tier 1 -------------------------------------------------------------

    def test_a_squash_merged_branch_is_landed_with_no_pull_requests_at_all(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.assertEqual(status.LANDED, status.branch_landed(self.repo, "feature", "main", []))

    def test_ancestry_alone_resolves_nothing_a_squash_merge_leaves(self) -> None:
        """C-1: the obvious test finds nothing in the repository it is for.

        Asserted rather than assumed, because the whole two-tier design rests
        on it. If this ever passes, this repository stopped squash-merging and
        the derivation above is answering a question nobody has.
        """
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "feature", "main"],
            cwd=str(self.repo), capture_output=True, text=True,
        )
        self.assertEqual(1, ancestor.returncode)
        self.assertEqual(
            status.LANDED, status.branch_landed(self.repo, "feature", "main", [])
        )

    def test_a_branch_whose_paths_main_has_since_edited_is_not_landed_by_tier_1(self) -> None:
        """The measured 40% false negative: tier 1 abstains, it does not lie."""
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.commit("b.txt", "two, edited later\n", "main moves on")
        self.assertEqual(
            status.NOT_LANDED, status.branch_landed(self.repo, "feature", "main", [])
        )

    def test_an_unmerged_branch_is_not_landed(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.git("checkout", "-q", "main")
        self.assertEqual(
            status.NOT_LANDED, status.branch_landed(self.repo, "feature", "main", [])
        )

    # -- tier 2, and C-19's two regressions ---------------------------------

    def test_tier_2_resolves_what_tier_1_misses(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.commit("b.txt", "two, edited later\n", "main moves on")
        self.assertEqual(
            status.LANDED,
            status.branch_landed(self.repo, "feature", "main", [self.pull()]),
        )

    def test_a_branch_extended_after_its_merge_is_not_landed(self) -> None:
        """C-19: the stale `mergedAt` must not overrule tier 1's correct no."""
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        merged_tip = self.git("rev-parse", "HEAD").strip()
        self.squash_merge("feature")
        self.commit("b.txt", "two, edited later\n", "main moves on")
        self.git("checkout", "-q", "feature")
        self.commit("c.txt", "three\n", "more work after the merge")
        self.git("checkout", "-q", "main")
        stale = self.pull(headRefOid=merged_tip)
        self.assertEqual(
            status.NOT_LANDED, status.branch_landed(self.repo, "feature", "main", [stale])
        )

    def test_a_pull_request_merged_into_another_base_does_not_count(self) -> None:
        """C-19: merged into `some-other-base` says nothing about `main`."""
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.commit("b.txt", "two, edited later\n", "main moves on")
        self.assertEqual(
            status.NOT_LANDED,
            status.branch_landed(
                self.repo, "feature", "main", [self.pull(baseRefName="release")]
            ),
        )

    def test_an_unmerged_pull_request_does_not_count(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.commit("b.txt", "two, edited later\n", "main moves on")
        self.assertEqual(
            status.NOT_LANDED,
            status.branch_landed(self.repo, "feature", "main", [self.pull(mergedAt=None)]),
        )

    # -- the third answer ---------------------------------------------------

    def test_no_pull_request_lookup_is_unknown_and_never_not_landed(self) -> None:
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.commit("b.txt", "two, edited later\n", "main moves on")
        answer = status.branch_landed(self.repo, "feature", "main", None)
        self.assertEqual(status.sd_lib.UNKNOWN, answer)
        self.assertEqual(status.GH_MERGED_QUERY, answer.repair)
        self.assertIn("headRefOid", answer.repair)

    def test_a_branch_git_cannot_resolve_is_unknown_with_the_repair(self) -> None:
        answer = status.branch_landed(self.repo, "no-such-branch", "main", [])
        self.assertEqual(status.sd_lib.UNKNOWN, answer)
        self.assertEqual(
            "git rev-parse --verify 'no-such-branch^{commit}'", answer.repair
        )

    def test_tier_1_fires_before_the_lookup_so_an_absent_gh_still_answers(self) -> None:
        """Positive evidence is offline, which is what makes tier 3 rare."""
        self.git("checkout", "-q", "-b", "feature")
        self.commit("b.txt", "two\n", "add b")
        self.squash_merge("feature")
        self.assertEqual(
            status.LANDED, status.branch_landed(self.repo, "feature", "main", None)
        )

    # -- C-12 ---------------------------------------------------------------

    def test_a_rename_the_default_branch_did_not_take_is_not_landed(self) -> None:
        """C-12: with rename detection on, this case reports landed and is wrong.

        The branch renames `a.txt` to `renamed.txt`. `main` gains an identical
        `renamed.txt` without removing `a.txt`, so the branch's *removal* never
        landed. `--no-renames` puts `a.txt` on both sides and the intersection
        is non-empty; with renames detected, `touched` holds `renamed.txt`
        alone and the two sets miss each other.
        """
        self.git("checkout", "-q", "-b", "feature")
        self.git("mv", "a.txt", "renamed.txt")
        self.git("commit", "-q", "-m", "rename a to renamed")
        self.git("checkout", "-q", "main")
        self.commit("renamed.txt", "one\n", "main adds a copy, keeps the original")
        self.assertEqual(
            status.NOT_LANDED, status.branch_landed(self.repo, "feature", "main", [])
        )


class BannerTests(InventoryFixture):
    """The three per-class states, and the one substring `prd.md:134` checks.

    Against real git for the same reason `BranchLandedTests` is: the state
    under test is produced by asking git a question, and a mock would assert
    the arrangement rather than the answer.
    """

    #: A `protection` section that says GitHub could not be read at all, which
    #: is what puts tier 2 out of reach and the merge class into `unchecked`.
    BLIND = {
        "default_branch": "main",
        "gaps": [],
        "detail": {},
        "available": False,
        "reason": "gh is not installed",
    }

    def inventory(self, **overrides: Any) -> Any:
        return status.actionable_inventory(
            self.repo, self.sections(**overrides), self.TODAY
        )

    def branch(self, name: str, *, land: bool) -> None:
        """A real branch off `main`, squash-merged back or left standing.

        Committed before any item file exists, so `git add -A` cannot sweep a
        `docs/work` fixture into the branch and change what the diff sees.
        """
        self.git("checkout", "-q", "-b", name)
        (self.repo / f"{name}.txt").write_text("work\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", f"work on {name}")
        self.git("checkout", "-q", "main")
        if land:
            self.git("merge", "-q", "--squash", name)
            self.git("commit", "-q", "-m", f"squash {name}")

    def state_of(self, result: dict[str, Any], check: str) -> dict[str, Any]:
        return next(row for row in result["classes"] if row["check"] == check)

    # -- the shape ----------------------------------------------------------

    def test_the_banner_lists_every_abnormal_class_and_only_those(self) -> None:
        """`CLASSES` is the enumeration; the banner does not keep a second one."""
        result = status.banner(self.inventory())
        self.assertEqual(
            [kind.check for kind in status.CLASSES if kind.abnormal],
            [row["check"] for row in result["classes"]],
        )

    def test_nothing_wrong_and_nothing_unread_is_the_only_way_to_say_clear(self) -> None:
        result = status.banner(self.inventory())
        self.assertEqual(0, result["unchecked_classes"])
        self.assertEqual([], result["findings"])
        self.assertIn("clear", result["summary"])
        self.assertEqual(
            {status.CLEAR}, {row["state"] for row in result["classes"]}
        )

    def test_a_class_that_fired_carries_its_own_count(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress")
        one = status.banner(self.inventory())
        self.assertEqual(
            "1 finding", self.state_of(one, "in-progress-without-branch")["label"]
        )
        self.assertIn("1 finding across 1 check;", one["summary"])
        self.item("2026-08-02-beta", status="in_progress")
        two = status.banner(self.inventory())
        self.assertEqual(
            "2 findings", self.state_of(two, "in-progress-without-branch")["label"]
        )
        self.assertIn("2 findings across 1 check;", two["summary"])

    # -- the third state ----------------------------------------------------

    def test_a_check_that_could_not_run_is_unchecked_and_the_word_clear_is_gone(
        self,
    ) -> None:
        """`prd.md:134`, in process: unchecked > 0 and `clear` not in summary.

        The acceptance criterion runs this through `--json` with `gh` taken
        off `PATH`; nothing renders the banner until step 4, so the same two
        assertions are made against the structure the renderer will read.
        """
        self.branch("feature", land=False)
        self.item("2026-08-01-alpha", status="in_progress", extra="branch: feature\n")
        result = status.banner(self.inventory(protection=self.BLIND))
        row = self.state_of(result, "branch-already-merged")
        self.assertEqual(status.UNCHECKED, row["state"])
        self.assertEqual("unchecked: gh is not installed", row["label"])
        self.assertEqual(1, result["unchecked_classes"])
        self.assertNotIn("clear", result["summary"])

    def test_an_unresolvable_branch_leaves_the_merge_check_clear(self) -> None:
        """The `elif` in `_work_rows`, and what it stops.

        A stale `branch:` field is a finding of its own class. Asked of
        `branch_landed` it would answer `unknown` -- and one such item would
        then mark the merge class unchecked on every run, for a reason that
        has nothing to do with whether GitHub could be read.
        """
        self.item(
            "2026-08-01-alpha", status="in_progress", extra="branch: gone-away\n"
        )
        inventory = self.inventory(protection=self.BLIND)
        self.assertEqual(
            ["branch-unresolvable"],
            [row["check"] for row in inventory.rows if row["check"].startswith("branch-")],
        )
        self.assertEqual({}, inventory.unchecked)
        result = status.banner(inventory)
        self.assertEqual(
            status.CLEAR, self.state_of(result, "branch-already-merged")["state"]
        )

    # -- the producer -------------------------------------------------------

    def test_a_landed_branch_is_a_finding_and_a_done_item_is_not(self) -> None:
        self.branch("feature", land=True)
        self.item("2026-08-01-alpha", status="in_progress", extra="branch: feature\n")
        fired = self.by_check(self.inventory().rows, "branch-already-merged")
        self.assertEqual(["2026-08-01-alpha"], [row["key"] for row in fired])
        self.assertIn("already in main", fired[0]["detail"])

    def test_a_done_item_whose_branch_landed_is_not_a_finding(self) -> None:
        self.branch("feature", land=True)
        self.item("2026-08-01-alpha", status="done", extra="branch: feature\n")
        self.assertEqual(
            [], self.by_check(self.inventory().rows, "branch-already-merged")
        )

    def test_the_repair_names_the_command_that_actually_ran(self) -> None:
        """The `--limit` was in the call and not in the sentence beside it.

        A repair is a command the reader is being told to run. Typed beside
        the argument vector instead of derived from it, it hands out a command
        that was never the one that failed -- which is the defect this file
        already fixed once, in `delivered`'s repairs.
        """
        seen: list[list[str]] = []

        def record(args: list[str], root: pathlib.Path) -> tuple[Any, str]:
            seen.append(args)
            return [], ""

        original = status.pr_state.gh_json
        status.pr_state.gh_json = record
        try:
            status.merged_pulls(self.repo, {"available": True})
        finally:
            status.pr_state.gh_json = original
        self.assertEqual([status.GH_MERGED_ARGS], seen)
        for token in status.GH_MERGED_ARGS:
            self.assertIn(token, status.GH_MERGED_QUERY)
        self.assertIn(str(status.MERGED_LIMIT), status.GH_MERGED_QUERY)

    def test_merged_pulls_hands_back_the_reason_github_could_not_be_read(self) -> None:
        self.assertEqual(
            status.Merged(None, "gh is not installed"),
            status.merged_pulls(self.repo, self.BLIND),
        )
        self.assertEqual(
            status.Merged(None, "GitHub is unreachable"),
            status.merged_pulls(self.repo, {"available": False}),
        )


class ConcernLedgerTests(InventoryFixture):
    """The ledger scanner, against real `git grep` over a real index.

    Real git because the scan *is* a `git grep`, and its two known traps --
    POSIX ERE rejecting `\\b`, and the space after a table pipe -- are
    properties of that program rather than of the design.
    """

    def ledger(self, name: str, body: str) -> str:
        """A `docs/work` page carrying a ledger, tracked so `git grep` sees it."""
        path = self.repo / "docs" / "work" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        self.git("add", "-A")
        return f"docs/work/{name}"

    def checks(self, rows: list[dict[str, Any]]) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for row in rows:
            found.setdefault(row["check"], []).append(row["key"])
        return found

    def scan(self, **overrides: Any) -> list[dict[str, Any]]:
        return [
            row for row in self.inventory(**overrides).rows
            if row["check"].endswith("-concern") or row["check"].endswith("-concern-row")
        ]

    def inventory(self, **overrides: Any) -> Any:
        return status.actionable_inventory(
            self.repo, self.sections(**overrides), self.TODAY
        )

    # -- `accepted`, the word that is also prose ----------------------------

    def test_accepted_beside_a_closing_word_does_not_open_the_row(self) -> None:
        """`accepted` read before `addressed` turns a closed row into a finding.

        Eight rows in this repo's own ledgers say `accepted` about something
        other than their disposition -- "validation accepted a codex
        provider" -- while closing themselves a few words later. Read as an
        opening word, the prose wins and the row reports as a defect.
        """
        self.ledger("2026-08-03-prose/prd.md", (
            "# prose\n\n"
            "- **C-9 -- the ninth** `addressed`: validation accepted a "
            "provider it should have refused.\n"
        ))
        self.assertEqual([], self.scan())

    def test_accepted_alone_parks_the_row_rather_than_opening_it(self) -> None:
        """An accepted concern is a decision that stands, not open work.

        `accepted-gap-standing` already says so for the file side, and is not
        abnormal. A ledger row saying only `accepted` describes the same
        state and must not land in the banner as a defect.
        """
        self.ledger("2026-08-04-standing/prd.md", (
            "# standing\n\n"
            "- **C-11 -- the eleventh** (high, ACCEPTED): the guard reads "
            "only the paths this change touches.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            {"parked-concern": ["docs/work/2026-08-04-standing/prd.md#C-11"]},
            found,
        )

    # -- both shapes --------------------------------------------------------

    def test_a_table_ledger_and_a_bullet_ledger_are_both_read(self) -> None:
        """One ledger is a markdown table and one is a bold bullet list.

        The space after the table pipe is C-18: `| C-7 | ... |` without ` *`
        in the anchor matches nothing, which is how an entire ledger table
        disappears in silence.
        """
        self.ledger("2026-08-01-table/prd.md", (
            "# table\n\n"
            "| id | disposition |\n| --- | --- |\n"
            "| C-1 | addressed |\n| C-2 | deferred |\n"
        ))
        self.ledger("2026-08-02-bullets/prd.md", (
            "# bullets\n\n"
            "- **C-1 -- the first** `addressed`.\n"
            "- **C-3 -- the third** left `unresolved`.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-table/prd.md#C-2",
             "docs/work/2026-08-02-bullets/prd.md#C-3"],
            sorted(found.get("unresolved-concern", [])),
        )

    # -- the precedence rules ----------------------------------------------

    def test_an_open_token_beats_a_closing_one_on_the_same_row(self) -> None:
        """`ACCEPTED and parked` is the common form, and such a row is parked.

        Under-reporting an open concern is the worst failure this can have, so
        the order is parked, then open, then closed, then standing.
        """
        self.ledger("2026-08-01-mixed/prd.md", (
            "# mixed\n\n"
            "- C-1 (high, ACCEPTED and parked): a security acceptance.\n"
            "- C-2: addressed, but the fix is deferred to a later item.\n"
            "- C-3: rebutted with evidence.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-mixed/prd.md#C-1"], found.get("parked-concern")
        )
        self.assertEqual(
            ["docs/work/2026-08-01-mixed/prd.md#C-2"], found.get("unresolved-concern")
        )
        self.assertNotIn("C-3", str(found))

    def test_a_table_row_outranks_a_prose_mention_of_the_same_concern(self) -> None:
        """Shape precedence, and what it stops.

        The ledger of record is the most structured row present. Without this
        rule a `## Log` sentence that merely begins with a `C-` id decides the
        concern's disposition -- measured on this item's own C-4, which is
        `rebutted` in its table and read as open from a Log line that mentions
        a *different* concern's parking.

        The Log comes first in the fixture on purpose. Rows of equal shape keep
        the one seen first, so a scanner with no precedence rule would keep the
        table row anyway if the table came first, and the test would pass
        against the broken code.
        """
        self.ledger("2026-08-01-both/prd.md", (
            "# both\n\n"
            "## Log\n\n"
            "C-4, C-8 and C-10 were rebutted; C-6 parked.\n\n"
            "## Review\n\n"
            "| id | disposition |\n| --- | --- |\n"
            "| C-4 | rebutted |\n"
        ))
        self.assertEqual([], self.scan())

    def test_a_bullet_row_outranks_a_prose_sentence_about_the_same_concern(
        self,
    ) -> None:
        """Bullet is its own tier, above prose.

        A bulleted row is a ledger entry; a sentence that happens to open with
        a `C-` id is not. Sharing a tier, which one decides the concern is
        settled by whichever line `git grep` returns first, so the prose is
        written above the row here -- exactly as the shape-precedence fixture
        does, and for the same reason.

        Found by review on #792. On the live corpus the three-tier and
        four-tier rules agree on every one of 530 concerns, so this is a latent
        defect removed rather than a live misclassification corrected.
        """
        self.ledger("2026-08-01-bullet/prd.md", (
            "# bullet\n\n"
            "## Log\n\n"
            "C-9 was raised while C-2 was still parked.\n\n"
            "## Review\n\n"
            "- C-9, minor: the count was off by one. Corrected.\n"
        ))
        self.assertEqual([], self.scan())

    def test_a_disposition_on_the_next_line_is_still_read(self) -> None:
        """Continuation absorption: dispositions wrap, and the row is one row."""
        self.ledger("2026-08-01-wrapped/prd.md", (
            "# wrapped\n\n"
            "- C-5, minor: the count in the third paragraph is off by one\n"
            "  under the criterion's own literal strings.\n"
            "  Corrected.\n\n"
            "- C-6, minor: a second row whose disposition never arrives\n"
            "  because the paragraph simply stops.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-wrapped/prd.md#C-6"],
            found.get("unreadable-concern-row"),
        )

    # -- never dropped ------------------------------------------------------

    def test_a_row_with_no_word_this_reader_carries_is_a_finding(self) -> None:
        """An unrecognised format inflates the count rather than emptying it.

        That is the failure the design was protecting against: parsing one
        format, finding nothing in the other three, and printing a clean
        banner. A row nobody can classify is abnormal on purpose.
        """
        path = self.ledger("2026-08-01-strange/prd.md", (
            "# strange\n\n- C-7: **Disputed, pending a second opinion.**\n"
        ))
        rows = self.scan()
        self.assertEqual(["unreadable-concern-row"], [row["check"] for row in rows])
        self.assertTrue(rows[0]["abnormal"])
        self.assertIn(f"{path}:3", rows[0]["detail"])

    def test_the_sixth_vocabulary_closes_rows_and_moves_nothing_else(self) -> None:
        """`Corrected`/`Recorded`/`Noted`/`superseded`/`Confirmed` were read.

        Closing words are checked last, so adding one can only ever reclassify
        a row nothing could read -- never an open one. This asserts both
        halves: the five close, and a row that also carries an open token
        stays open.
        """
        self.ledger("2026-08-01-sixth/prd.md", (
            "# sixth\n\n"
            "- C-1, minor: a line number was wrong. Corrected.\n"
            "- C-2, minor: the count is off. Recorded rather than recounted.\n"
            "- C-3, minor: the omission stands. Noted in the registry block.\n"
            "- C-4, minor: C-3 superseded here.\n"
            "- C-5: **Confirmed, design changed.**\n"
            "- C-6: Corrected in place, but the wider gap is deferred.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-sixth/prd.md#C-6"], found.get("unresolved-concern")
        )
        self.assertEqual([], found.get("unreadable-concern-row", []))

    # -- the keying ---------------------------------------------------------

    def test_one_c_id_in_two_items_is_two_concerns(self) -> None:
        """Keyed on the full path.

        A prototype keying on `split("/")[2]` collapsed 487 archived items
        into one bucket and lost `C-19` outright.
        """
        self.ledger("2026-08-01-alpha/prd.md", "# a\n\n- C-19: deferred.\n")
        self.ledger(
            "archive/2026-08/2026-08-02-beta/prd.md", "# b\n\n- C-19: deferred.\n"
        )
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-alpha/prd.md#C-19",
             "docs/work/archive/2026-08/2026-08-02-beta/prd.md#C-19"],
            sorted(found.get("unresolved-concern", [])),
        )

    def test_the_same_concern_written_three_times_is_one_row(self) -> None:
        """Dedupe by `(file, C-id)`: three rows about one concern, one id."""
        self.ledger("2026-08-01-repeat/prd.md", (
            "# repeat\n\n"
            "| id | disposition |\n| --- | --- |\n| C-8 | deferred |\n\n"
            "- C-8 re-raised in a later pass, no new disposition.\n\n"
            "- **C-8** deferred again.\n"
        ))
        self.assertEqual(1, len(self.scan()))

    def test_an_archived_ledger_is_read_though_its_boxes_are_not(self) -> None:
        """The one deliberate exception to the archive exclusion.

        A parked security acceptance outlives the item it was written in, so
        excluding it because its directory moved is the silent under-report
        this section exists to prevent.
        """
        self.ledger(
            "archive/2026-08/2026-08-26-adapter/prd.md",
            "# adapter\n\n- C-19 (high, ACCEPTED and parked): reads anywhere.\n",
        )
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/archive/2026-08/2026-08-26-adapter/prd.md#C-19"],
            found.get("parked-concern"),
        )


class AcceptedGapTests(InventoryFixture):
    """Step 3b: a written acceptance is listed, and is not an abnormality."""

    ENTRY = {
        "id": "required-checks",
        "state": "missing",
        "because": "the check is reported by an app nobody has installed",
        "since": "2026-07-01",
        "until": "the app is installed or the check is dropped",
    }

    def rows_for(self, *entries: dict[str, str]) -> list[dict[str, Any]]:
        sections = self.sections(protection={
            "default_branch": "main", "gaps": [], "detail": {},
            "accepted": list(entries),
        })
        return [
            row for row in
            status.actionable_inventory(self.repo, sections, self.TODAY).rows
            if row["check"] == "accepted-gap-standing"
        ]

    def test_an_accepted_gap_is_listed_and_is_not_abnormal(self) -> None:
        """A decision is not a defect; re-flagging one is how a banner becomes
        noise. It is listed because `until` is prose nothing re-evaluates."""
        rows = self.rows_for(self.ENTRY)
        self.assertEqual(["required-checks"], [row["key"] for row in rows])
        self.assertFalse(rows[0]["abnormal"])
        self.assertEqual(45, rows[0]["rank"])
        self.assertIn("2026-07-01", rows[0]["detail"])
        self.assertIn("the app is installed", rows[0]["suggest"])

    def test_an_accepted_gap_never_reaches_the_banner(self) -> None:
        inventory = status.actionable_inventory(
            self.repo,
            self.sections(protection={
                "default_branch": "main", "gaps": [], "detail": {},
                "accepted": [self.ENTRY],
            }),
            self.TODAY,
        )
        result = status.banner(inventory)
        self.assertEqual([], result["findings"])
        self.assertNotIn(
            "accepted-gap-standing", [row["check"] for row in result["classes"]]
        )


if __name__ == "__main__":
    unittest.main()
