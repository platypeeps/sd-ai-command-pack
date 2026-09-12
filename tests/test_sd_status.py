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
import io
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

from tests.test_sd_pr_state import BIN, SD_STATUS, ToolFixture, tree_digest

#: The other half of the pin in `SkillSurfaceTests`. Imported as the function
#: alone so this module collects its own tests and not that file's.
from tests.test_skill_frontmatter import surfaces as frontmatter_surfaces

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

    def test_an_aggregate_gate_written_to_always_report_is_not_flagged(self) -> None:
        """The idiom the note used to accuse of the opposite of what it does.

        `if: ${{ !cancelled() }}` is how a required aggregate context is meant
        to be written: it runs the job when the jobs it `needs` were skipped or
        failed, which is precisely the case the note warned would leave the
        context pending forever. Flagging it argued for deleting a working
        branch protection, so the expression is read now rather than merely
        noticed.
        """
        self.write(
            "ci.yml",
            "on: [pull_request]\njobs:\n  result:\n    name: CI Result\n"
            "    needs: [lint]\n    if: ${{ !cancelled() }}\n    steps:\n      - run: true\n",
        )
        produced, notes = status.workflow_checks(self.repo)
        self.assertEqual(produced, {"CI Result"})
        self.assertEqual([note for note in notes if "conditional" in note], [])

    def test_always_reports_too_and_is_recognised_however_it_is_spelled(self) -> None:
        """`always()` is the same guarantee, and spelling must not decide it.

        GitHub accepts a bare expression as well as a `${{ }}` one, treats the
        function name case-insensitively, and lets the author quote the value
        or space the `!` out from `cancelled()`. A reader that recognised one
        spelling and flagged the next would be the same defect with a smaller
        blast radius, so each form a real workflow uses is covered here.
        """
        for index, condition in enumerate(
            (
                "always()",
                "${{ always() }}",
                "${{ ALWAYS() }}",
                "'${{ !cancelled() }}'",
                "${{ ! cancelled() }}",
                "${{ !cancelled() }} # the aggregate gate",
            )
        ):
            with self.subTest(condition=condition):
                self.write(
                    f"gate{index}.yml",
                    "on: [pull_request]\njobs:\n  result:\n"
                    f"    if: {condition}\n    steps:\n      - run: true\n",
                )
                _, notes = status.workflow_checks(self.repo)
                self.assertEqual([note for note in notes if "conditional" in note], [])
                (self.workflows / f"gate{index}.yml").unlink()

    def test_a_condition_that_can_still_skip_the_job_is_still_flagged(self) -> None:
        """The other half: reading the expression must not amount to trusting it.

        Every one of these can leave the job skipped, and two of them mention
        the reporting functions -- `always() && ...` is skippable on the right
        operand, and a job that runs only when nothing was cancelled *on main*
        reports nothing on a pull request. A note that cleared them because the
        word appeared would be worse than the note it replaced.
        """
        for index, condition in enumerate(
            (
                "github.actor != 'bot'",
                "${{ always() && github.ref == 'refs/heads/main' }}",
                "${{ !cancelled() && github.event_name == 'push' }}",
                "${{ cancelled() }}",
                "${{ success() }}",
            )
        ):
            with self.subTest(condition=condition):
                self.write(
                    f"skip{index}.yml",
                    "on: [pull_request]\njobs:\n  build:\n"
                    f"    if: {condition}\n    steps:\n      - run: true\n",
                )
                _, notes = status.workflow_checks(self.repo)
                self.assertTrue(any("conditional" in note for note in notes))
                (self.workflows / f"skip{index}.yml").unlink()

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

    def test_the_schema_and_the_readers_vocabulary_name_the_same_facts(self) -> None:
        """Two recitations of one list, so this enumerates both rather than a third.

        `ACKNOWLEDGED_FACTS` decides what the reader accepts and the schema
        decides what an editor is told to write. They are separate files, so a
        fact added to one drifts from the other silently -- and the failure is
        the bad kind: the schema offers a key the loader rejects, or the loader
        accepts a key no author knows exists. Nothing here writes the expected
        list down; both sides are read from their own source.
        """
        schema = json.loads(
            (BIN.parent / ".github" / "sd-status.schema.json").read_text(encoding="utf-8")
        )
        state = schema["properties"]["accepted_gaps"]["items"]["properties"]["state"]
        self.assertEqual(sorted(state["properties"]), sorted(status.ACKNOWLEDGED_FACTS))
        # `additionalProperties: false` is what makes the schema half of this
        # agreement binding; without it the schema would accept anything and
        # only the loader would object, one commit later.
        self.assertIs(state["additionalProperties"], False)

    def test_absent_protection_is_a_distinct_observed_state_from_empty_protection(self) -> None:
        """The fact that separates "no object" from "an object enforcing nothing".

        Both reduce every other fact to the same falsy value, so without this
        one the two branch states are indistinguishable to an acknowledgement
        -- and they are not the same branch: one can be pushed to freely, the
        other has a protection object someone can tighten.
        """
        self.assertFalse(status._observed_state(None)["branch_protection"])
        self.assertTrue(status._observed_state({})["branch_protection"])
        absent = status._observed_state(None)
        empty = status._observed_state({})
        self.assertNotEqual(absent, empty)
        # ... and they differ in exactly that one fact, which is the point:
        # the other four genuinely are constants on both.
        differing = [key for key in absent if absent[key] != empty[key]]
        self.assertEqual(differing, ["branch_protection"])

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
        # The accepted id is deliberately not recited here. This repository's
        # entry has changed once already -- `reviews` was deleted when
        # protection was removed on 2026-09-12 and its `until` came true --
        # and a list naming the current id fails on the next such decision
        # while proving nothing the loader does not already enforce. The file
        # is tracked, so a new acceptance arrives as a reviewed diff, which is
        # where it is meant to be read.
        entries, problems = status.load_acknowledgements(BIN.parent)
        self.assertEqual(problems, [])

    def test_an_empty_state_is_rejected_rather_than_accepting_the_id(self) -> None:
        # An entry with no facts would accept `reviews` whatever the branch
        # looked like, which is the shape this file must not be able to take.
        entry = dict(self.ZERO_APPROVALS, state={})
        entries, problems = self.written(json.dumps({"accepted_gaps": [entry]}))
        self.assertEqual(entries, [])
        self.assertTrue(any("must be a non-empty object" in problem for problem in problems))

    def test_an_id_no_gap_can_emit_is_rejected_rather_than_accepting_nothing(self) -> None:
        """A typo in `id` used to load clean and accept nothing, silently.

        The loader checked that the id was a non-empty string and stopped
        there, so `unprotectd` passed, matched no finding, printed nothing, and
        left the gap it was written to accept printing on every run with no
        sign that an acknowledgement had been attempted. That is the failure
        mode this file exists to prevent, reintroduced one keystroke down, and
        it is rejected the same way an unobservable fact name already was.
        """
        for wrong in ("unprotectd", "enforce-admins", "squash_message", ""):
            with self.subTest(id=wrong):
                entry = dict(self.ZERO_APPROVALS, id=wrong)
                entries, problems = self.written(json.dumps({"accepted_gaps": [entry]}))
                self.assertEqual(entries, [])
                self.assertTrue(problems)
        # `squash_message` is in that list on purpose: it is a real id printed
        # by the report, on a merge-settings flag that never passes through
        # `_apply_acknowledgements`. An id that exists somewhere in the output
        # is still an id no acknowledgement can ever match, so the vocabulary
        # is the set of *acknowledgeable* findings, not every id in the file.
        entries, problems = self.written(
            json.dumps({"accepted_gaps": [dict(self.ZERO_APPROVALS, id="squash_message")]})
        )
        self.assertTrue(any("is not an acknowledgeable gap" in problem for problem in problems))

    def test_every_id_the_protection_section_emits_is_in_the_vocabulary(self) -> None:
        """The two halves are read from the code, not from a list written here.

        The ids were scattered string literals, which is how the loader came to
        validate a vocabulary nobody had written down. This drives the
        producers until each one fires and compares what came out against
        `ACKNOWLEDGEABLE_GAPS`, both directions: an id the producers can emit
        and the tuple omits would be unacceptable by acknowledgement, and a
        tuple member no producer emits would be a spelling an author could put
        in the file and never see applied.
        """
        emitted: set[str] = set()
        unprotected, _ = status._apply_acknowledgements(
            [{"id": "unprotected", "gap": "no protection at all"}],
            status._observed_state(None),
            [],
        )
        emitted.update(gap["id"] for gap in unprotected)
        for protection, produced in (
            ({}, set()),
            (self.enforcing(), {"lint", "a-check-nothing-requires"}),
            (self.enforcing(required_status_checks={"contexts": ["nobody-reports-this"]}), set()),
            (self.enforcing(required_pull_request_reviews=None), {"lint"}),
        ):
            gaps, _ = status._protection_gaps(protection, "main", produced, [])
            emitted.update(gap["id"] for gap in gaps)
        self.assertEqual(emitted, set(status.ACKNOWLEDGEABLE_GAPS))

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

    @staticmethod
    def headings(text: str) -> list[str]:
        """Section headings, which are the only lines starting at column 0.

        Derived from the output rather than declared, so a section added to
        `render()` is picked up by whoever compares two of these instead of
        being missed by both.
        """
        return [line for line in text.splitlines()
                if line and not line[0].isspace() and not line.startswith("sd-status:")]


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

    def test_the_section_skeleton_is_the_same_with_content_and_without(
        self,
    ) -> None:
        """Step 7(d): the shape of the report is not a function of its data.

        A reader learns where to look once. If a section vanished when it had
        nothing to say, "no open pull requests" and "this tool stopped
        reporting pull requests" would render identically -- as absence -- and
        only one of them is good news. Every section therefore prints its
        heading and says so in words underneath.

        Headings are read out of the rendered text rather than listed here.
        A hardcoded list would pass while the report grew a thirteenth section
        that neither run printed, which is the failure this compares two runs
        to avoid.

        The first run is empty of *items*, not of findings: the fixture's
        protection requires a `build` context no workflow here produces, so it
        carries one gap either way. `work items` is therefore the section that
        genuinely differs between the two runs, and it is what falsifies this
        -- teaching `_render_work` to skip its heading when the repository has
        no items fails the comparison.
        """
        self.with_github(pulls=[])
        empty = self.headings(self.run_tool(SD_STATUS).stdout)
        self.assertIn("work items", empty)

        self.item("2026-08-01-alpha", status="in_progress")
        self.item("2026-08-02-beta", status="planning")
        filled = self.headings(self.run_tool(SD_STATUS).stdout)
        self.assertEqual(empty, filled)

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

    UNPROTECTED = {
        "id": "unprotected",
        "state": {"branch_protection": False},
        "because": "sole operator, and no CI checks exist for protection to require",
        "since": "2026-09-11",
        "until": "a second account with push rights exists",
    }

    def test_an_accepted_unprotected_branch_prints_as_accepted(self) -> None:
        """The 404 branch returned before it ever applied the file.

        `unprotected` is the only gap a repository with no protection can be
        told about, so it is the one a repository that has decided against
        protection most needs to accept -- and it was the single finding the
        acknowledgement path could not reach. The file was read and its path
        was reported in `detail`, which is what made the omission look like a
        working feature: nothing was ever matched against it.
        """
        self.acknowledge(self.UNPROTECTED)
        self.with_github(pulls=[], protection=None)
        section = self.report()["protection"]
        self.assertEqual(section["gaps"], [])
        self.assertEqual([entry["id"] for entry in section["accepted"]], ["unprotected"])
        # Accepted is not protected. A consumer reading `protected` still gets
        # the fact about the branch, whatever the repository decided about it.
        self.assertFalse(section["protected"])
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            "ok  [unprotected] accepted 2026-09-11: sole operator", completed.stdout
        )
        self.assertIn("until a second account with push rights exists", completed.stdout)

    def test_an_unprotected_acknowledgement_naming_protection_does_not_apply(self) -> None:
        """`branch_protection` is a real pin here, and the other four cannot be.

        Every other fact in the vocabulary reduces a protection object. On this
        branch there is no object, so all four are constants whatever the
        branch looks like -- an entry pinning only those accepts the id
        unconditionally, which is the shape the non-empty `state` rule exists
        to forbid. `branch_protection` is the one fact that can be wrong here,
        so it is the one that can go stale.
        """
        self.acknowledge(dict(self.UNPROTECTED, state={"branch_protection": True}))
        self.with_github(pulls=[], protection=None)
        section = self.report()["protection"]
        self.assertEqual(section["accepted"], [])
        self.assertEqual([gap["id"] for gap in section["gaps"]], ["unprotected"])
        completed = self.run_tool(SD_STATUS)
        self.assertIn("GAP [unprotected]", completed.stdout)
        self.assertIn("no longer matches the live protection state", completed.stdout)

    def test_a_broken_acknowledgement_file_still_fails_closed_when_unprotected(self) -> None:
        """Failing closed has to hold on this branch too, not just the other one.

        A malformed file accepts nothing anywhere; the risk is that the branch
        which never applied acknowledgements also never reported why, leaving
        `unprotected` printing with no hint that the file meant to accept it.
        """
        directory = self.repo / ".github"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "sd-status.json").write_text("[]", encoding="utf-8")
        self.with_github(pulls=[], protection=None)
        section = self.report()["protection"]
        self.assertEqual(
            [gap["id"] for gap in section["gaps"]], ["acknowledgements", "unprotected"]
        )
        self.assertEqual(section["accepted"], [])

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

    def test_shared_database_supersedes_legacy_issue_cache_without_stalling_work(self) -> None:
        import sd_db

        self.with_github(pulls=[])
        self.write_index([self.row("acme/widget", 99, ["assigned"])])
        sd_db.initialise(home=self.home)
        connection = sd_db.connect(home=self.home)
        try:
            sd_db.writes.upsert_shadow(
                connection, tracker="github", repo="acme/widget", number=7,
                url="https://github.com/acme/widget/issues/7", title="External context",
                kind="issue", state="open")
        finally:
            connection.close()
        result = self.report()
        self.assertEqual(result["issues"]["source"], "database")
        self.assertEqual(result["issues"]["freshness"]["state"], "never")
        self.assertEqual([row["number"] for row in result["issues"]["other"]], [7])
        self.assertEqual(result["issues"]["needs_you"], [])
        self.assertFalse(any(row["check"].startswith("issue-") for row in result["actions"]))


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

    def test_the_report_now_carries_what_steps_one_to_three_produced(self) -> None:
        """Retires `test_nothing_renders_it_yet`, which step 4 falsified.

        Steps 1 to 3b built producers deliberately wired to nothing, and that
        test asserted the report was unchanged -- true then, and the check
        that said each step was landable on its own. Step 4 is the step that
        makes them visible, so the assertion inverts here rather than being
        loosened. `ReportSectionTests` pins the order and the wording; this
        one pins only that the executable an operator runs shows them at all,
        which the in-process tests cannot say.

        The `actions` key was asserted absent here until step 5 added it,
        which is the same inversion one step later and for the same reason.
        `ActionsCliTests` owns that surface now.
        """
        self.with_github(pulls=[])
        self.item("2026-08-01-alpha", status="in_progress")
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for present in ("abnormalities", "pending", "next", "open threads"):
            self.assertIn(f"\n{present}\n", completed.stdout)


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

    def ancient(self, name: str = "2026-01-01-ancient") -> pathlib.Path:
        """A planning item whose own date is 249 days before `TODAY`.

        Uncommitted and unrecorded, so the only thing dating it is the date it
        wrote on itself. Every idle test below starts here and then adds one
        piece of evidence that something has happened to it since.
        """
        directory = self.repo / "docs" / "work" / name
        directory.mkdir(parents=True)
        (directory / "prd.md").write_text(
            f"---\ntitle: {name}\nstatus: planning\ncreated: 2026-01-01\n---\n",
            encoding="utf-8",
        )
        return directory

    def committed(self, when: str) -> None:
        """Commit the item tree with a committer date this test chooses.

        `sd_sweep.touched` reads `%cs`, the *committer* date -- when the work
        entered this history rather than when it was first written, which is
        the question "has anything happened to this item" actually asks. Git
        takes it from the environment and from nowhere else, so a fixture that
        did not set it would be measuring the wall clock.
        """
        with mock.patch.dict(os.environ, {"GIT_COMMITTER_DATE": when}):
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "record the items")

    def test_a_planning_item_past_the_threshold_ages_into_a_finding(self) -> None:
        """`created:` is what ages an item, so the fixture writes its own.

        The control for the two tests under it: nothing has been committed and
        nothing recorded, so birth date and last activity are the same day and
        this fires either way. It passed before `idle-planning` changed its
        basis and passes after, which is what makes the two failures below
        evidence about the basis rather than about the fixture.
        """
        self.ancient()
        self.item("2026-08-01-alpha")
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        idle = self.by_check(rows, "idle-planning")
        self.assertEqual([row["key"] for row in idle], ["2026-01-01-ancient"])
        self.assertGreater(idle[0]["age_days"], status.IDLE_DAYS)

    def test_an_ancient_item_committed_to_this_week_is_not_idle(self) -> None:
        """sd:455: an item worked on two days ago is not one nobody has touched.

        The defect, in one item. `idle-planning` aged an item by the date it
        dated itself, so the number it printed could only ever go up: 21 of
        mezmo_benchmark's 24 planning items read past the threshold on birth
        dates while every one of them had been triaged live the day before.
        Its finding says the item has been planning for N days and its remedy
        is start it, park it or archive it -- all three of which assume
        neglect, and acting on them would have buried confirmed-live work.

        Fails against the old basis, which cannot see the commit at all.
        """
        self.ancient()
        self.committed("2026-09-05T12:00:00 +0000")
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        self.assertEqual([], self.by_check(rows, "idle-planning"))

    def test_a_stamp_only_the_database_carries_resets_the_clock(self) -> None:
        """The other half of sd:455, and the half git cannot answer.

        A `row` checkout records a triage decision as a note against the item
        and touches no file, so the item tree is byte-identical before and
        after -- which is why this fixture commits nothing. The four decision
        notes on mezmo_benchmark's items were exactly this shape.

        The stamp arrives on the work section, where `work_section` puts it
        from `WorkItem.activity`; `RowActivity` in `tests/test_sd_lib.py` is
        what checks the database actually fills it.
        """
        self.ancient()
        work = status.work_section(self.repo)
        for entry in work["items"]:
            entry["activity"] = "2026-09-06T09:14:00+00:00"
        self.assertEqual([], self.by_check(self.rows(work=work), "idle-planning"))

    def test_the_row_says_what_the_age_measures_rather_than_how_old_it_is(
        self,
    ) -> None:
        """The wording is the finding: "planning for N days" was the false half.

        An age measured from activity and described as an age since creation
        would be a second way of saying the wrong thing, so the detail line is
        pinned here rather than left to read like the old one.
        """
        self.ancient()
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        detail = self.by_check(rows, "idle-planning")[0]["detail"]
        self.assertIn("has had nothing recorded against it for 249 days", detail)

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

    def test_one_item_that_is_parked_and_archived_and_branched_at_once(
        self,
    ) -> None:
        """The real case, and the intersection rather than the union.

        `archive/2026-09/2026-08-21-port-integration-only-profile` carries
        `status: in_progress`, a `parked:` line, a `branch:` field and an
        `archive/` path all at once. The test above holds each condition on a
        *different* item, so neither ever meets the other: two items with one
        condition each cannot tell a reader that handles the intersection from
        one that double-counts it or raises on it.

        **The frontmatter's `in_progress` is not what the reader sees.**
        `sd_lib.py:701` returns `done` for any archived item without opening
        `prd.md`, so archiving decides the status and the declared one is never
        read. That is why every item here carries a `branch:` naming no ref:
        `branch-unresolvable` is the one check that fires regardless of status,
        so it is the only thing that can prove the archive guard is doing work.
        A fixture without it passes with that guard deleted, which is how this
        test was wrong on its first writing.

        The live item is the contrast that makes the rest able to fail. A
        producer that silently returned nothing would fail on it rather than
        pass four times over.
        """
        self.item("2026-08-01-live", status="in_progress")
        self.item("2026-08-02-parked", status="in_progress",
                  extra="parked: 2026-09-01 superseded\nbranch: feat/nope\n")
        archive = self.repo / "docs" / "work" / "archive" / "2026-09"
        for name, extra in (
            ("2026-08-03-filed", "branch: feat/nope\n"),
            ("2026-08-04-port", "parked: 2026-09-01 superseded\nbranch: feat/nope\n"),
        ):
            directory = archive / name
            directory.mkdir(parents=True)
            (directory / "prd.md").write_text(
                PRD.format(title=name, status="in_progress", extra=extra),
                encoding="utf-8",
            )
        rows = status.actionable_inventory(self.repo, self.sections(), self.TODAY).rows
        self.assertEqual(
            ["2026-08-01-live"],
            sorted({row["key"] for row in rows if "2026-08-0" in row["key"]}),
            "only the item carrying neither `parked:` nor an archive path may "
            "fire; the other three carry `branch:` to make the guard "
            "observable, which is not a fourth suppressor",
        )
        self.assertEqual(
            len(rows), len({(row["check"], row["key"]) for row in rows}),
            "no object may produce the same check twice",
        )


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

    def test_a_branch_origin_no_longer_carries_is_not_a_row(self) -> None:
        """sd:496: the ghost, and why `fetch --prune` is not the cure here.

        A remote-tracking ref outlives its branch the moment a pull request is
        squash-merged with `--delete-branch` by anything but this checkout.
        Observed on `origin/worktree-agent-a429ba188d801962d` after #839
        landed: `git ls-remote --heads origin <name>` printed nothing, and both
        actions the row named -- open a pull request for it, or delete it --
        had nothing to act on.

        `sd-status` cannot prune its way out, because pruning writes refs and
        this tool writes nothing, so it asks origin instead. The branch is
        deleted **in the bare repository directly** rather than with
        `git push --delete`, which removes the remote-tracking ref here as a
        side effect and would leave this fixture with no ghost to find.

        Fails before the cross-check, which reports `origin/task/gone`.
        """
        remote = self.base / "ghost.git"
        self.git("init", "-q", "--bare", str(remote))
        self.set_origin(str(remote))
        self.git("branch", "task/gone")
        self.git("push", "-q", "origin", "main", "task/gone")
        self.git("fetch", "-q", "origin")
        self.git("update-ref", "-d", "refs/heads/task/gone", cwd=remote)

        self.assertIn(
            "origin/task/gone",
            self.git("for-each-ref", "--format=%(refname:short)", "refs/remotes"),
            "the fixture is meant to leave a stale remote-tracking ref standing",
        )
        self.assertEqual([], self.by_check(self.rows(), "unmerged-branch"))

    def test_a_remote_that_cannot_be_asked_says_so_in_the_row(self) -> None:
        """Option (b), kept as the fallback rather than dropped for option (a).

        Offline, the refs are the only answer there is, and reporting nothing
        would trade a ghost for a blind spot. The row is still emitted and says
        what it was built from, and its suggestion names the prune ahead of the
        two actions that are unrunnable against a branch already gone.

        `unchecked` is not the vehicle: `unmerged-branch` is not abnormal and
        `banner` reports `unchecked` for abnormal classes only, so a reason
        recorded there is a reason nothing prints.
        """
        remote = self.base / "away.git"
        self.git("init", "-q", "--bare", str(remote))
        self.set_origin(str(remote))
        self.git("branch", "task/one")
        self.git("push", "-q", "origin", "main", "task/one")
        self.git("fetch", "-q", "origin")
        shutil.rmtree(remote)

        found = self.by_check(self.rows(), "unmerged-branch")
        self.assertEqual([row["key"] for row in found], ["origin/task/one"])
        self.assertIn(status.STALE_REFS, found[0]["detail"])
        self.assertIn("git fetch --prune", found[0]["suggest"])


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

    def test_a_contrib_skill_discloses_on_the_same_terms_as_a_shipped_one(
        self,
    ) -> None:
        """Both roots, or the class reports health over a tree it never read.

        `_tool_rows` used to glob `skills/` alone. `contrib/` is where every
        skill `sd skill try` can still reach lives, and two of them disclose a
        `bin/` command that is not built, so the class printed a count that
        described one half of the surface and read as the whole of it.

        Asserted as one fixture holding one skill in each root, because the
        defect was never "contrib is missed" in isolation -- it was the two
        roots being answered differently. A revert drops the `contrib/` row
        and leaves the `skills/` one, so this fails on exactly the change it
        guards.
        """
        for root, name in (("skills", "sd-shipped"), ("contrib", "sd-tried")):
            skill = self.repo / root / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                f"There is no `bin/{name}` yet.\n", encoding="utf-8"
            )
        (self.repo / "bin").mkdir(exist_ok=True)
        found = self.by_check(self.rows(), "undisclosed-tool")
        self.assertEqual(
            sorted(row["key"] for row in found),
            [
                "contrib/sd-tried/SKILL.md#bin/sd-tried",
                "skills/sd-shipped/SKILL.md#bin/sd-shipped",
            ],
        )

    def disclose(self, said: str) -> None:
        """One skill saying one thing, so a row is about the resolver alone."""
        skill = self.repo / "skills" / "sd-thing"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(said + "\n", encoding="utf-8")
        (self.repo / "bin").mkdir(exist_ok=True)

    def test_a_disclosure_quoting_a_real_module_path_is_not_a_row(self) -> None:
        """`_DISCLOSED_RE` stops at the `.`, so the suffix has to be restored.

        This is two of the six findings the literal test produced in this
        repository: `skills/sd-handoff` writes `bin/sd_handoff_rows.py` and
        `skills/sd-review` writes `bin/sd_setup_github.py`, both of which are
        the true paths of files that are on disk.
        """
        self.disclose("Rows come from `bin/sd_rows.py`.")
        (self.repo / "bin" / "sd_rows.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual([], self.by_check(self.rows(), "undisclosed-tool"))

    def test_a_module_sharing_a_stem_does_not_silence_a_missing_command(self) -> None:
        """A hyphenated tool is not built by an underscored module beside it.

        The regression guard. An earlier revision of `_tool_candidates` also
        tried `-` respelled `_`, on the theory that `bin/sd_suggest.py` builds
        `bin/sd-suggest`. It does not: such a module is an implementation
        detail `bin/sd` imports, and the command is a `sd <verb>` subcommand.
        The transform therefore gave two identically-worded disclosures
        opposite verdicts -- one silenced by a module that shares its stem, the
        other reported -- and the silenced one was true.

        Which surfaces disclose an absent binary is not written down here, for
        the reason `tests/test_permission_allowlist.py` gives about hand-kept
        lists: `tests/test_skill_frontmatter.py`'s `BinaryClaims` derives it at
        run time. This test's own fixture is synthetic, so it keeps working
        whichever surfaces those are.

        Fails if the `underscored` candidates come back, which is the point:
        the defect it guards was a silenced true finding, and a silenced
        finding leaves nothing in the report to notice.
        """
        self.disclose("There is no `bin/sd-rows` yet.")
        (self.repo / "bin" / "sd_rows.py").write_text("x = 1\n", encoding="utf-8")
        found = self.by_check(self.rows(), "undisclosed-tool")
        self.assertEqual([row["title"] for row in found], ["bin/sd-rows"])

    def test_a_tool_absent_in_every_spelling_survives_the_widening(self) -> None:
        """The failure mode of widening a resolver: silence, not noise.

        Three neighbours that a glob or a prefix test would accept, and none
        of them is a spelling of the disclosed name.
        """
        self.disclose("Planning will live in `bin/sd-gone`.")
        for name in ("sd-goneish", "sd_gone_helper.py", "sd-other"):
            (self.repo / "bin" / name).write_text("x = 1\n", encoding="utf-8")
        found = self.by_check(self.rows(), "undisclosed-tool")
        self.assertEqual([row["title"] for row in found], ["bin/sd-gone"])

    def test_a_directory_under_bin_is_not_a_built_tool(self) -> None:
        """`is_file`, not `exists`: a directory answers no disclosure."""
        self.disclose("Planning will live in `bin/sd-gone`.")
        (self.repo / "bin" / "sd-gone").mkdir()
        found = self.by_check(self.rows(), "undisclosed-tool")
        self.assertEqual([row["title"] for row in found], ["bin/sd-gone"])

    def test_the_candidates_are_the_name_and_the_name_with_its_suffix(self) -> None:
        """Pinned as a list: the shortness is the argument.

        Two candidates, and the second exists only because `_DISCLOSED_RE`
        truncates at the `.`. No respelling of `-` as `_` in either direction
        -- see `_tool_candidates` for why the transform cannot come back.
        """
        self.assertEqual(
            list(status._tool_candidates("sd-plan")), ["sd-plan", "sd-plan.py"]
        )
        self.assertEqual(
            list(status._tool_candidates("sd_plan")), ["sd_plan", "sd_plan.py"]
        )
        # Stated as a property too, so a third candidate cannot be added
        # later in a spelling this pin happens not to name.
        self.assertTrue(
            all("_" not in name for name in status._tool_candidates("sd-plan"))
        )


class SkillSurfaceTests(unittest.TestCase):
    """One answer to "what is a skill surface", pinned across the two readers.

    The pack had two, and they disagreed. `bin/sd-status` globbed `skills/`;
    `tests/test_skill_frontmatter.surfaces()` walked `skills/` and `contrib/`
    both. The producer's half was the wrong one, and the cost was not a
    cosmetic count -- `undisclosed-tool` asserted health over `contrib/`
    without opening it, which is the failure the banner refuses by never
    printing `clear` over an unchecked class.

    The single answer lives in `bin/`, not here. A check may not depend on the
    test suite: `bin/` ships and `tests/` does not, so the direction that
    survives installation is the suite reading the producer. What this file
    owes in return is the pin -- if either reader widens or narrows alone, the
    sets stop matching and this fails. Agreeing today without pinning the
    agreement is the same defect deferred to whoever adds the third root.
    """

    def test_the_producer_and_the_suite_enumerate_the_same_surfaces(self) -> None:
        root = BIN.parent
        produced = {p.relative_to(root) for p in status.skill_surfaces(root)}
        asserted = {p.relative_to(root) for p in frontmatter_surfaces()}
        self.assertEqual(produced, asserted)
        # Not vacuous: an enumeration that returned nothing would also match.
        self.assertTrue(any(p.parts[0] == "contrib" for p in produced))
        self.assertTrue(any(p.parts[0] == "skills" for p in produced))

    def test_a_directory_without_a_skill_file_is_not_a_surface(self) -> None:
        """`skills/_shared` is a real directory holding references, not a skill.

        The suite checks `is_file()` on the entrypoint; so must the producer,
        or the two sets differ by a directory that was never a surface.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            (root / "skills" / "_shared").mkdir(parents=True)
            (root / "contrib" / "sd-real").mkdir(parents=True)
            (root / "contrib" / "sd-real" / "SKILL.md").write_text(
                "x\n", encoding="utf-8"
            )
            self.assertEqual(
                [p.relative_to(root) for p in status.skill_surfaces(root)],
                [pathlib.Path("contrib/sd-real/SKILL.md")],
            )

    def test_a_missing_root_is_not_an_error(self) -> None:
        """A checkout without `contrib/` still reports on `skills/`."""
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            (root / "skills" / "sd-one").mkdir(parents=True)
            (root / "skills" / "sd-one" / "SKILL.md").write_text(
                "x\n", encoding="utf-8"
            )
            self.assertEqual(
                [p.relative_to(root) for p in status.skill_surfaces(root)],
                [pathlib.Path("skills/sd-one/SKILL.md")],
            )


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


class RowWorkItemInventoryTests(InventoryFixture):
    """Retired status files cannot be the repair for database-owned work."""

    ITEM = "2026-09-05-alpha"

    def setUp(self) -> None:
        super().setUp()
        import sd_db

        self.db = sd_db
        environment = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)
        self.db.initialise(home=self.home)

    def row_item(self, *, branch: str = "feature", missing: bool = False) -> pathlib.Path:
        directory = self.item(self.ITEM, extra=f"branch: {branch}\n")
        path = directory / "prd.md"
        path.write_text(path.read_text().replace("status: planning\n", ""))
        (directory.parent / ".status-source").write_text("row\n")
        connection = self.db.connect(home=self.home)
        try:
            self.db.upsert_repo(connection, str(self.repo), status_source="row")
            if not missing:
                self.db.upsert_item(
                    connection, source="docs/work",
                    external_id=f"{self.repo}::docs/work/{self.ITEM}/prd.md",
                    kind="work", title="alpha", status="in_progress", who="test",
                    repo=str(self.repo), branch=branch,
                )
        finally:
            connection.close()
        return directory

    def test_unmerged_feature_closing_trailer_is_not_already_merged(self) -> None:
        self.branch("feature", land=False)
        self.row_item()
        self.git("checkout", "-q", "feature")
        self.git("commit", "-q", "--allow-empty", "-m", f"Proposed delivery\n\nDelivers: {self.ITEM}")
        result = self.inventory(protection=self.BLIND)
        self.assertEqual([], self.by_check(result.rows, "branch-already-merged"))

    def test_row_closing_history_is_read_once_per_default_ref(self) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", "Delivered item\n\nCloses: item-0")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        work = {"status_source": status.sd_lib.FROM_ROW, "items": [
            {"path": f"docs/work/item-{index}", "slug": f"item-{index}",
             "status": "in_progress", "branch": "main", "archived": False, "parked": False}
            for index in range(40)]}
        with mock.patch.object(status.sd_lib, "upstream", return_value=("origin", "main")), \
                mock.patch.object(status.sd_lib, "git_output", wraps=status.sd_lib.git_output) as git_calls:
            rows = status._work_rows(self.repo, work, self.TODAY, "main", status.Merged(None, ""), {})
        walks = [call.args[0] for call in git_calls.call_args_list
                 if call.args[0][0] == "log" and "--grep" in call.args[0]]
        self.assertEqual([argv[-1] for argv in walks], ["main", "origin/main"])
        self.assertEqual([row["key"] for row in self.by_check(rows, "branch-already-merged")], ["item-0"])

    def test_quoted_closing_line_is_not_a_default_branch_trailer(self) -> None:
        self.branch("feature", land=True)
        self.row_item()
        self.git("commit", "-q", "--allow-empty", "-m", f"Quoted example\n\nCloses: {self.ITEM}\n\nThis is an example, not a delivery.")
        self.assertEqual([], self.by_check(self.inventory(protection=self.BLIND).rows, "branch-already-merged"))

    def test_an_ordinary_slice_merge_does_not_close_a_row_owned_item(self) -> None:
        self.branch("feature", land=True)
        self.row_item()
        result = self.inventory(protection=self.BLIND)
        self.assertEqual([], self.by_check(result.rows, "branch-already-merged"))
        self.assertNotIn("branch-already-merged", result.unchecked)

    def test_an_open_row_needs_no_github_lookup_to_check_a_slice(self) -> None:
        self.branch("feature", land=False)
        self.row_item()
        with mock.patch.object(status, "merged_pulls") as lookup:
            result = self.inventory(protection=self.BLIND)
        lookup.assert_not_called()
        self.assertEqual([], self.by_check(result.rows, "branch-already-merged"))
        self.assertNotIn("branch-already-merged", result.unchecked)

    def test_a_closing_trailer_reconciles_the_row_without_rewriting_frontmatter(self) -> None:
        self.branch("feature", land=True)
        self.row_item()
        self.git("commit", "-q", "--allow-empty", "-m", f"Deliver\n\nCloses: {self.ITEM}")
        # SQLite mode=ro may maintain these two lock files for a WAL database.
        # Main database bytes and every repository file still must be unchanged.
        lock_files = {"home/.local/share/sd/sd.db-wal", "home/.local/share/sd/sd.db-shm"}

        def snapshot():
            return {path: value for path, value in tree_digest(self.base).items()
                    if path not in lock_files}

        before = snapshot()
        result = self.inventory(protection=self.BLIND)
        found = self.by_check(result.rows, "branch-already-merged")
        self.assertEqual(1, len(found))
        self.assertIn(f"Closes: {self.ITEM}", found[0]["detail"])
        self.assertIn("database row", found[0]["suggest"])
        self.assertNotIn("set status:", found[0]["suggest"])
        self.assertEqual(before, snapshot())

    def test_a_missing_database_row_keeps_its_identity_and_source_in_the_repair(self) -> None:
        self.branch("feature", land=False)
        self.row_item(missing=True)
        found = self.by_check(self.inventory(protection=self.BLIND).rows, "status-unreadable")
        self.assertEqual(1, len(found))
        self.assertIn("database holds no docs/work row", found[0]["detail"])
        self.assertIn(f"{self.repo}::docs/work/{self.ITEM}/prd.md", found[0]["detail"])
        self.assertIn("database holds no docs/work row", found[0]["suggest"])
        self.assertNotIn("frontmatter", found[0]["suggest"])

    def test_an_unknown_git_fallback_keeps_the_failed_probe_and_its_repair(self) -> None:
        self.branch("feature", land=False)
        self.row_item()
        with mock.patch.object(self.db, "connect", side_effect=FileNotFoundError("no database")), \
             mock.patch.object(status.sd_lib, "delivered", return_value=status.sd_lib.Answer(
                 status.sd_lib.UNKNOWN, "git fetch --unshallow"
             )):
            work = status.work_section(self.repo)
            result = self.inventory(work=work, protection=self.BLIND)
        found = self.by_check(result.rows, "status-unreadable")
        self.assertEqual(1, len(found))
        self.assertIn("cannot see whether", found[0]["detail"])
        self.assertIn("git fetch --unshallow", found[0]["suggest"])
        self.assertNotIn("database row", found[0]["suggest"])
        self.assertNotIn("frontmatter", found[0]["suggest"])
        self.assertEqual("unknown", work["items"][0]["status"])
        checked = next(row for row in status.banner(result)["classes"]
                       if row["check"] == "status-unreadable")
        self.assertEqual(status.FINDINGS, checked["state"])

    def test_an_invalid_marker_is_repaired_instead_of_inventing_file_authority(self) -> None:
        directory = self.row_item(missing=True)
        (directory.parent / ".status-source").write_text("broken\n")
        found = self.by_check(self.inventory(protection=self.BLIND).rows, "status-unreadable")
        self.assertEqual(1, len(found))
        self.assertIn(".status-source says 'broken'", found[0]["detail"])
        self.assertIn(".status-source", found[0]["suggest"])
        self.assertNotIn("frontmatter", found[0]["suggest"])


class BannerTests(InventoryFixture):
    """The three per-class states, and the one substring `prd.md:134` checks.

    Against real git for the same reason `BranchLandedTests` is: the state
    under test is produced by asking git a question, and a mock would assert
    the arrangement rather than the answer.
    """

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
        self.assertNotIn("clear", result["summary"])
        # The count is not 1. A blind `protection` also puts every class that
        # declares it out of reach, which is sd:600 -- so the assertion names
        # the set rather than a number that would grow silently.
        self.assertEqual(
            {"branch-already-merged", "protection-gap", "pr-check-missing"},
            {row["check"] for row in result["classes"]
             if row["state"] == status.UNCHECKED},
        )

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
        # Narrowed to this test's subject. A blind `protection` does mark the
        # classes that read it, so an empty map would assert something this
        # test is not about and sd:600 says is wrong.
        self.assertNotIn("branch-already-merged", inventory.unchecked)
        result = status.banner(inventory)
        self.assertEqual(
            status.CLEAR, self.state_of(result, "branch-already-merged")["state"]
        )

    # -- sd:600: a class whose section could not be read ----------------------

    #: Which collected section each check reads, as the design states it and
    #: not as `CLASSES` happens to say today. A test that derives this from
    #: the table cannot catch a deleted or mistyped `needs` entry, because the
    #: expectation moves with the defect. Adding a dependency means adding it
    #: here and in `CLASSES`, and the two are asserted equal below.
    DECLARED_SECTIONS = {
        "pull_requests": {
            "pr-check-failing", "pr-check-missing", "dirty-tree-with-open-pr",
        },
        "protection": {"pr-check-missing", "protection-gap"},
    }

    def test_the_table_declares_exactly_the_dependencies_the_design_states(
        self,
    ) -> None:
        """`CLASSES` against the design, so a deleted `needs` entry is loud."""
        actual: dict[str, set[str]] = {}
        for kind in status.CLASSES:
            for name in kind.needs:
                actual.setdefault(name, set()).add(kind.check)
        self.assertEqual(self.DECLARED_SECTIONS, actual)

    def test_a_blind_section_marks_every_class_that_declares_it(self) -> None:
        """Every section any class declares, driven blind in turn.

        Derived from `CLASSES.needs`, never from a list of check names: the
        defect this replaces counted eleven of twelve classes clear on a
        machine that could not reach GitHub at all, because `unchecked` had
        exactly one producer.

        Driving only `protection` was not enough, and a mutation proved it:
        deleting all three `pull_requests` dependencies left this suite green
        at 211 passing, so the merge checks would have gone on reporting clear
        against a `pull_requests` section nothing could read.

        Deriving the expectation from `CLASSES.needs` does not fix that, and
        the same mutation proved that too. Blank an entry and the sections
        looped over and the checks expected shrink together, so the assertion
        agrees with whatever the table says. The expectation therefore comes
        from `DECLARED_SECTIONS`, which states the design.
        """
        for name, expected in sorted(self.DECLARED_SECTIONS.items()):
            with self.subTest(section=name):
                # Blind the section in place, so it keeps the shape its
                # producers expect and only the readability flag changes.
                blinded = dict(self.sections()[name], **{
                    "available": False, "reason": "gh is not installed"})
                inventory = self.inventory(**{name: blinded})
                self.assertLessEqual(expected, set(inventory.unchecked))
                for check in expected:
                    self.assertEqual(
                        "gh is not installed", inventory.unchecked[check])

    def test_a_class_that_needs_no_section_is_not_marked_unchecked(
        self,
    ) -> None:
        """The control. Without it the test above passes on a blanket mark.

        `in-progress-without-branch` reads work items and git and nothing
        else, so a blind `protection` must leave it exactly as it was.
        """
        self.item("2026-08-01-alpha", status="in_progress")
        blind = status.banner(self.inventory(protection=self.BLIND))
        self.assertEqual(
            status.FINDINGS,
            self.state_of(blind, "in-progress-without-branch")["state"],
        )
        self.assertNotIn("in-progress-without-branch", 
                         {row["check"] for row in blind["classes"]
                          if row["state"] == status.UNCHECKED})

    def test_a_readable_section_marks_nothing(self) -> None:
        """The second control: the success case still reports clear.

        A guard that marked on every run would satisfy both assertions above
        and report a healthy repository as blind forever.
        """
        result = status.banner(self.inventory())
        self.assertEqual(0, result["unchecked_classes"])
        self.assertIn("clear", result["summary"])

    def test_the_summary_cannot_say_clear_while_any_class_is_blind(self) -> None:
        """sd:4's criterion 14, as an executable check.

        `skills/sd-status/SKILL.md` states this three times in its Never list
        and the code did not do it: the banner said `all 12 checks clear` over
        a `protection` section carrying `available: False` and a reason.
        """
        summary = status.banner(self.inventory(protection=self.BLIND))["summary"]
        self.assertNotIn("clear", summary)
        self.assertIn("could not run", summary)

    def test_every_section_a_class_declares_is_a_section_that_exists(self) -> None:
        """A typo in `needs` would make a class silently never go blind.

        Compared against the section names the report actually assembles, so
        renaming a section breaks here rather than turning a check back into a
        silent pass.
        """
        declared = {name for kind in status.CLASSES for name in kind.needs}
        self.assertLessEqual(declared, set(self.sections()))

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
        four-tier rules agree on every one of 532 concerns, re-measured after
        `_ROW_START_RE` fixed absorption, so this is a latent defect removed
        rather than a live misclassification corrected.
        """
        self.ledger("2026-08-01-bullet/prd.md", (
            "# bullet\n\n"
            "## Log\n\n"
            "C-9 was raised while C-2 was still parked.\n\n"
            "## Review\n\n"
            "- C-9, minor: the count was off by one. Corrected.\n"
        ))
        self.assertEqual([], self.scan())

    def test_a_table_row_is_read_by_its_verdict_column_and_not_by_its_narrative(self) -> None:
        """C-11's shape: the verdict says addressed, the narrative says deferred.

        Every cell before the last is *about the defect*, so it carries the
        subject's vocabulary. Under tier order alone the narrative's `deferred`
        outranks the verdict's `addressed` and the row reads open -- which is
        the misread `_disposition` already documents for prose rows and fixes
        by reading the header first. A table row has no header to read, so it
        fell through unchanged until the last cell was read the same way.
        """

        self.ledger("2026-08-02-table/design.md", (
            "# table\n\n"
            "| id | sev | finding | disposition |\n"
            "|---|---|---|---|\n"
            "| C-11 | low | validation was deferred to a phase-2 refresh on the"
            " assumption the fix was in shipped text | **addressed** - D2d"
            " validates locally |\n"
        ))
        # Every row, not two named classes. Copilot's verification pass was
        # right that excluding `unresolved-concern` and `unreadable-concern-row`
        # leaves a misread free to land as `parked-concern` and still pass.
        # `addressed` is closed, and closed means this ledger yields nothing.
        self.assertEqual([], self.scan())

    def test_a_table_row_whose_verdict_column_is_open_stays_open(self) -> None:
        """The control, and the half that stops the fix from silencing rows.

        Without it the last-cell read could return anything and the test above
        would still pass. C-1's real shape: a deferral written *as* the
        verdict, which is open and has to stay open.
        """

        self.ledger("2026-08-03-deferred/design.md", (
            "# deferred\n\n"
            "| id | sev | finding | disposition |\n"
            "|---|---|---|---|\n"
            "| C-1 | critical | the installer flips a real registry entry,"
            " mutating the source checkout | **deferred** to"
            " 08-11-thin-candidate-loop-shape |\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-03-deferred/design.md#C-1"],
            found.get("unresolved-concern"),
        )

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

    def test_a_continuation_opening_with_a_cross_reference_is_not_a_new_row(self) -> None:
        """A row's argument is usually about another row, so its prose opens
        with one. Absorption must not read that as the next entry.

        Measured on C-120 of the solo-first item before this: the row says
        `Addressed` on its fifth line, its third line opens `C-100's rebuild`,
        and the row was reported as disposed in words nothing could read. The
        bullet below it is a real row and must still end absorption, or one
        entry's disposition would close the entry above it.
        """

        self.ledger("2026-08-01-crossref/prd.md", (
            "# crossref\n\n"
            "- C-8, blocking: the criterion's documentation clause was skipped.\n"
            "    C-100's rebuild derived the Touches from the runtime clauses\n"
            "    and dropped it. Addressed, and PR 1 is ordered before PR 6.\n"
            "- C-9, blocking: a second row whose disposition never arrives.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-crossref/prd.md#C-9"],
            found.get("unreadable-concern-row"),
            "C-8 closes on its own fifth line; C-9 carries no word at all",
        )

    def test_an_unindented_row_needs_no_marker_to_end_absorption(self) -> None:
        """The older archived ledgers write rows as bare prose at column zero.

        Requiring a bullet would make every one of those rows a continuation of
        the row above it, which is the opposite failure and a larger one.

        The disposition sits on the *second* row and the bare one comes first,
        so over-absorption changes the answer rather than preserving it. Put
        the other way round -- the closing word above, the bare row below --
        the second row is still found on its own and still reads as nothing,
        and the fixture passes whether the unindented branch is there or not.
        Found by review on #821: the first version of this test was written
        that way and guarded nothing.
        """

        self.ledger("2026-08-01-bare/prd.md", (
            "# bare\n\n"
            "C-1 identified the wrong anchor and nothing here says what became"
            " of it.\n"
            "C-2 is an argument-construction defect and only argv proves it."
            " Corrected.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-bare/prd.md#C-1"],
            found.get("unreadable-concern-row"),
        )

    def test_a_wrapped_sentence_is_not_a_ledger_row(self) -> None:
        """A concern named only in passing has no row, and reporting one
        invents a finding nobody can go and read.

        `CONCERN_ANCHOR` is anchored at the start of a line, so the only
        prose it can match is prose that happens to *wrap* onto a `C-` id.
        Real: `2026-09-04-the-plan-interview-is-one-sentence/design.md` has
        no C-9 row anywhere, and the only place the id appears in the file is
        the tail of the sentence below. 7 of the 627 hits collapse to 6 such
        rows of record, four reported as unreadable and two reported as
        parked from a word inside somebody else's paragraph.

        The rule is the wrap and not the prose shape, so the last two rows
        are the half that must not move: `C-3` opens a block and `C-4`
        follows a finished sentence, and both are bare prose rows of the kind
        `_ROW_START_RE` exists for. `C-1` is not a hit at all -- it sits
        mid-line, where the anchor cannot reach it -- which is the shape that
        makes this defect invisible until a sentence wraps.
        """
        self.ledger("2026-08-04-wrap/prd.md", (
            "# wrap\n\n"
            "The clause survived because it was the same fixed-string "
            "quoting that C-1 and\n"
            "C-2 earned. A criterion whose path names nothing checks "
            "nothing.\n\n"
            "C-3 identified the wrong anchor and nothing here says what "
            "became of it.\n"
            "C-4 is an argument-construction defect and only argv proves it."
            " Corrected.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-04-wrap/prd.md#C-3"],
            found.get("unreadable-concern-row"),
            "C-2 is the tail of a sentence, not a row; C-3 and C-4 are rows",
        )

    def test_a_bullet_that_is_not_a_row_still_ends_absorption(self) -> None:
        """A row's verdict comes from the row, and the bullet below it is a
        different bullet.

        Real, and the one row the boundary moves: C-89 of the solo-first
        item's `prd.md` writes no disposition word of its own, and was read
        as closed from `Recorded, not corrected here` in the bullet under it
        -- a bullet about criterion 4 naming a directory that is not there.
        Both halves are here: the row states its severity and its decision
        and never says what became of it, and the bullet below carries two
        closing words. Absorbing the second is how the first reads clean.
        """
        self.ledger("2026-08-01-foreign/prd.md", (
            "# foreign\n\n"
            "- C-3, blocking: the two issues stay open, and criterion 28's\n"
            "  clause is rewritten to assert the rows instead.\n"
            "- **The governed tree names a directory that is not there.**\n"
            "  The criterion lists `templates/`; there is no such directory.\n"
            "  Recorded, not corrected here.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-foreign/prd.md#C-3"],
            found.get("unreadable-concern-row"),
            "C-3 says nothing this reader carries; the bullet below is not "
            "its row and must not close it",
        )

    def test_a_wrap_onto_a_number_is_not_a_new_item(self) -> None:
        """The bullet boundary stops at bullets and deliberately not at
        numbered items.

        Real: C-107 of the solo-first item wraps `... was cited at line` onto
        `21. Line 21 is about rendered copies ...`, so the row's own
        continuation opens exactly like an ordered-list item. Widening the
        boundary to catch it costs the row its own `Addressed.` and makes a
        correctly-read row unreadable -- one more finding, no rescue, against
        a row that was already right. This fixture is that shape, and C-5
        below it is the row that must stay the only finding.
        """
        self.ledger("2026-08-01-numbered/prd.md", (
            "# numbered\n\n"
            "- C-4, material: the writes-nothing claim was cited at line\n"
            "  21. Line 21 is about rendered copies; the claim is line 34.\n"
            "  Addressed.\n"
            "- C-5, material: a row whose disposition never arrives.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-numbered/prd.md#C-5"],
            found.get("unreadable-concern-row"),
            "C-4 closes itself on its third line, across a wrap that opens "
            "with a number",
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

    def test_restated_closes_a_row_and_an_open_token_still_beats_it(self) -> None:
        """`Restated` is the seventh closing word, and the tier order holds.

        Measured whole-corpus: it rescues 3 of the 33 rows nothing could read
        and reclassifies none, taking the floor to 30 of 532. Two of the three
        are the real thing -- C-163 in the solo-first item ends `Restated as
        the work.` and C-172 ends `Restated as a bare-token shape`, and in
        both the sentence carrying the word is the disposition.

        The second row here is the half that is easy to lose: closing words
        are read after the open ones, so a row that restates *and* defers is
        still open. Under-reporting an open concern is the worst failure this
        feature can have, and a new closing word is exactly how it would
        happen.
        """
        self.ledger("2026-08-01-seventh/prd.md", (
            "# seventh\n\n"
            "- C-1, minor: the requirement read as a description of the file "
            "rather than as work. Restated as the work.\n"
            "- C-2, blocking: the criterion could not pass as written. "
            "Restated as a bare-token shape, but the vendor clause is "
            "deferred to a later pull request.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-01-seventh/prd.md#C-2"],
            found.get("unresolved-concern"),
        )
        self.assertEqual([], found.get("unreadable-concern-row", []))

    def test_supersedes_closes_the_row_superseded_missed_by_one(self) -> None:
        """`supersedes` is the inflection `superseded` does not cover.

        One row in the corpus, C-175 in the solo-first item, opens
        `supersedes C-173's split`. 1 rescue, 0 reclassifications. Carried as
        a literal rather than by stemming, which would fold `noted` into
        `note`/`notes`/`noting` to win it.
        """
        self.ledger("2026-08-01-inflected/prd.md", (
            "# inflected\n\n"
            "- C-1, blocking, supersedes C-2's split: the clause is PR 6's "
            "whole, not two files of eight.\n"
        ))
        self.assertEqual([], self.scan())

    def test_a_bold_header_disposes_the_row_its_own_prose_cannot(self) -> None:
        """A row's bold header is the row saying what it is, and it is read
        before the tiers see the prose after it.

        The prose after the header is *about the defect*, so it carries the
        subject's vocabulary -- a rule that defers, an unresolved path -- and
        under tier order alone any of those outranks an `addressed` written
        four words in. Measured: reading the header first moves 5 rows, every
        one `open` to `closed`, rescues none and loses none. Four are
        `**C-N -- <finding>. `addressed`.**` in the write-the-test-first item
        and the fifth is `**C-18 addressed**` in the consolidate-git item.
        Five of the fourteen rows this feature called open were this misread.

        The second row is the half that must not move: with no bold header
        there is nothing to read first, so the tiers decide as before and a
        row whose prose defers is still open. That is what keeps this rule
        off C-182, which says `accepted` before it says `Closed by
        normalizing at the write` and which earliest-match-wins would break.
        """
        self.ledger("2026-08-02-header/prd.md", (
            "# header\n\n"
            "- **C-1 -- the bound rule contradicted the classifier. "
            "`addressed`.** The safety rule said a bound closes `partial`, "
            "in the section admitting the question is unresolved.\n"
            "- C-2, blocking: the same finding without a header of its own, "
            "and the wider gap is deferred.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-02-header/prd.md#C-2"],
            found.get("unresolved-concern"),
            "C-1 is disposed in its header; C-2 has none and defers",
        )
        self.assertEqual([], found.get("unreadable-concern-row", []))

    def test_a_header_that_defers_opens_a_row_whose_prose_says_parked(self) -> None:
        """The header decides whatever it says -- this is not a closing rule.

        Tier order is preserved *inside* the header, so a header carrying
        both a closing and an open token reads open exactly as a whole row
        does. Were the header only allowed to close a row, it would be a way
        to dispose of a concern by writing the right word first, which is the
        failure the tier order exists to prevent moved one level in.

        The row below is the case that separates the two rules: its header
        defers and its body mentions something parked. `parked` is the first
        tier, so the whole-row read calls it parked and a close-only header
        rule would leave it there. The row's own header says the remainder is
        deferred, and open is both the honest answer and the louder one.
        """
        self.ledger("2026-08-03-deferring/prd.md", (
            "# deferring\n\n"
            "- **C-1 -- addressed in part, the remainder deferred.** The "
            "corrected clause landed; the rest waits behind the parked "
            "refresh C-2 describes.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-03-deferring/prd.md#C-1"],
            found.get("unresolved-concern"),
        )
        self.assertEqual([], found.get("parked-concern", []))

    def test_the_verbs_that_were_measured_and_refused_stay_unreadable(self) -> None:
        """`added` and `verified` are the two the counts argue for and the
        reading argues against, so the refusal is written down as a test.

        Whole-corpus, `added` rescues 7 rows and `verified` 2, both without
        reclassifying anything today -- which is why a count alone cannot
        decide this. Read instead: `added` appears in 41 row extents, 32 of
        them already closed and 2 already open, and `verified` in 36. Both
        sentences below are real, from C-20 in the write-the-test-first item
        and C-183 in the solo-first one, and in both the word describes the
        defect rather than disposing of it. They must keep reporting as rows
        this reader cannot classify.

        This one guards against an addition rather than a reversion: it fails
        the day either word joins `CLOSED_WORDS` on the strength of its
        rescue count.
        """
        self.ledger("2026-08-01-refused/prd.md", (
            "# refused\n\n"
            "- C-1 found a no-evidence exit written into the gate that was "
            "added to close a no-evidence hole.\n"
            "- C-2, material: the commit that claimed `make check exit 0` was "
            "verified by the weaker of the two runs.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            [
                "docs/work/2026-08-01-refused/prd.md#C-1",
                "docs/work/2026-08-01-refused/prd.md#C-2",
            ],
            sorted(found.get("unreadable-concern-row", [])),
        )

    # -- `parked`, the word that is also a field name -----------------------

    def test_a_backticked_field_name_does_not_park_a_row(self) -> None:
        """`parked` is this corpus's one verdict that is also its own field
        name, and the two are told apart by where the code span sits.

        A verdict written as code ends its clause; a name written as code is
        a noun with the rest of its phrase still to come. Both rows below are
        real. The first is C-162 of the solo-first item, which named
        `bin/sd-docs-lint` among the readers of the `archived` and `parked`
        fields and was reported as waiting on a trigger nobody re-reads --
        the most expensive misread this section has, because a disposed row
        reads as live work. The second is C-17 of the write-the-test-first
        item, whose disposition *is* the backticked word, and it must stay
        parked: 3 of the 7 backticked `parked`s in the corpus are that shape,
        and ignoring matches inside code spans wholesale loses all three.

        Whole-corpus: 4 rows move, every one `parked` to `closed`, none is
        made unreadable and `open` moves by zero.
        """
        self.ledger("2026-08-04-naming/prd.md", (
            "# naming\n\n"
            "- C-1, minor: `bin/sd-docs-lint:87-91` was listed among the "
            "readers of the `archived` and `parked` fields. It reads "
            "neither, and the line range is unrelated. Corrected.\n"
            "- **C-2** (the handoff had no operative pre-fix step) -- "
            "`parked`. The seam it describes no longer exists.\n"
        ))
        found = self.checks(self.scan())
        self.assertEqual(
            ["docs/work/2026-08-04-naming/prd.md#C-2"],
            found.get("parked-concern"),
            "C-1 names the field; C-2's whole disposition is the code span",
        )
        self.assertEqual([], found.get("unreadable-concern-row", []))

    def test_removed_is_a_disposition_this_reader_carries(self) -> None:
        """`removed` joins `CLOSED_WORDS`, and it comes in with the naming
        rule rather than on its own.

        C-162 of the solo-first item disposes itself `Removed from PR 2's
        reader enumeration`, and until the parked tier stopped reading the
        field name in its prose the row never reached this tier at all.
        Measured whole-corpus, its exposure is 16 row extents of 532 -- 13
        already closed, 1 parked, 2 nothing could read -- against `added`'s
        41 and `verified`'s 36, the figures that rejected those two. 1
        rescue, 0 reclassifications, 0 rows made unreadable.
        """
        self.ledger("2026-08-04-removed/prd.md", (
            "# removed\n\n"
            "- C-1, minor: the reader enumeration named a file that reads "
            "neither field. Removed from PR 2's enumeration.\n"
        ))
        self.assertEqual([], self.scan())

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


class ReportSectionTests(InventoryFixture):
    """The twelve headings, and the three the inventory feeds.

    Rendered rather than inspected. Step 1 through 3b built producers nothing
    printed, so every assertion up to here was about a structure; these are
    about the text an operator reads, which is where two defects that passed
    every structural test became visible at once.
    """

    def report(self, **overrides: Any) -> str:
        inventory = self.inventory(**overrides)
        result = {
            "repo": str(self.repo),
            "pack": {"root": str(self.repo), "branch": "main",
                     "head": "0000000", "dirty": False},
            "inventory": {"rows": inventory.rows, "unchecked": inventory.unchecked},
            "abnormalities": status.banner(inventory),
            "work": status.work_section(self.repo),
            "pull_requests": {"repo": "acme/widget", "pull_requests": [],
                              "available": False, "reason": "no gh"},
            "setup": {"mode": "full", "mode_error": "", "source": "",
                      "detected": 0, "entrypoints": {}},
            "protection": {"available": False, "reason": "no remote",
                           "gaps": [], "accepted": [], "detail": {}},
            "handoff": {"packet": {"pending": False, "detail": "none written"},
                        "carriers": []},
            "backends": [],
            "residue": [],
            "issues": {"available": False, "reason": "no index",
                       "needs_you": [], "other": []},
            "contributions": {"available": False, "reason": "no shared database", "rows": []},
        }
        stream = io.StringIO()
        status.render(result, stream)
        return stream.getvalue()

    def headings(self, text: str) -> list[str]:
        return [line for line in text.splitlines()
                if line and not line[0].isspace() and not line.startswith("sd-status:")]

    #: `design.md`'s skeleton, verbatim. The three new sections lead because
    #: the report is read top-down and the judgement is what the reader came
    #: for; the eight below keep the order they already had.
    ORDER = [
        "abnormalities", "pending", "next", "open threads", "work items",
        "contributions (this repo, shared database order)",
        "open pull requests", "detected setup",
        "issues (this repo, from the index)", "protection",
        "resumable handoffs", "backends", "legacy residue",
    ]

    # -- the skeleton -------------------------------------------------------

    def test_thirteen_headings_print_in_order_when_there_is_nothing_to_report(
        self,
    ) -> None:
        """The skeleton is fixed, so a missing section is a missing section.

        A report whose sections appear only when non-empty cannot be read for
        absence: the reader cannot tell "nothing found" from "not looked at",
        which is the same distinction the banner's third state exists to make.
        """
        self.assertEqual(self.ORDER, self.headings(self.report()))

    def test_the_same_thirteen_print_in_the_same_order_with_findings(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress")
        self.assertEqual(self.ORDER, self.headings(self.report()))

    # -- the summary sentence -----------------------------------------------

    def test_the_summary_does_not_call_checks_clear_beside_its_own_findings(
        self,
    ) -> None:
        """`all N checks clear` printed beside `1 finding` contradicts itself.

        The head and the tail describe the same twelve classes. Saying every
        one is clear while naming a class that fired hands a skimmer the
        opposite of the answer, and the tail is the half people skim.
        """
        self.item("2026-08-01-alpha", status="in_progress")
        summary = status.banner(self.inventory())["summary"]
        self.assertIn("1 finding across 1 check;", summary)
        self.assertIn("the other 11 checks clear", summary)
        self.assertNotIn("all 12 checks clear", summary)

    def test_nothing_found_still_says_all_of_them_are_clear(self) -> None:
        summary = status.banner(self.inventory())["summary"]
        self.assertEqual("no findings; all 12 checks clear", summary)

    def test_a_blind_class_keeps_the_word_out_even_when_others_fired(self) -> None:
        """The never-say-clear rule outranks the new middle tail.

        A run with findings *and* a class nobody could ask must not print the
        word at all: `the other N checks clear` would count the blind class
        among the clear ones, which is the under-report the third state
        exists to prevent.
        """
        self.branch("feature", land=False)
        self.item("2026-08-01-alpha", status="in_progress", extra="branch: feature\n")
        self.item("2026-08-02-beta", status="in_progress")
        summary = status.banner(self.inventory(protection=self.BLIND))["summary"]
        self.assertNotIn("clear", summary)
        self.assertIn("could not run", summary)

    # -- the banner is the judgement, not the list --------------------------

    def test_a_class_over_the_cap_elides_and_says_how_many(self) -> None:
        """Four findings in one class print three rows and a count.

        The class line already carries the true total, so the elision is not
        a loss of information -- it is the difference between a banner and a
        listing, and `pending` is the listing.
        """
        for name in ("alpha", "beta", "gamma", "delta"):
            self.item(f"2026-08-01-{name}", status="in_progress")
        banner = self.report().split("\npending\n")[0].splitlines()
        start = next(i for i, line in enumerate(banner)
                     if line.startswith("  in-progress-without-branch"))
        under = list(itertools.takewhile(
            lambda line: line.startswith("    "), banner[start + 1:]))
        self.assertEqual("4 findings", banner[start].split()[-2] + " findings")
        self.assertEqual(status.BANNER_LIMIT + 1, len(under))
        self.assertEqual("... 1 more, ranked in `pending`", under[-1].strip())

    def test_a_class_at_the_cap_elides_nothing(self) -> None:
        for name in ("alpha", "beta", "gamma"):
            self.item(f"2026-08-01-{name}", status="in_progress")
        self.assertNotIn("more, ranked in", self.report().split("\npending\n")[0])

    # -- one row, three renderings ------------------------------------------

    def test_next_names_the_first_row_of_pending_and_not_a_fourth_judgement(
        self,
    ) -> None:
        """C-3, rendered. The id in `next` is an id in `pending`.

        Three independent producers would give one fact three ids; one
        producer with three views gives it one, and this is the assertion
        that says the views did not drift apart.
        """
        # Three rows, not one. With a single row every candidate for "the
        # row `next` names" is the same row, so a renderer reaching for the
        # second would still pass -- which is exactly what this test did
        # until the breakage that was supposed to fail it did not.
        self.item("2026-08-01-alpha", status="in_progress")
        self.item("2026-08-02-beta", status="in_progress")
        self.item("2026-08-03-gamma", status="in_progress")
        rows = self.inventory().rows
        self.assertGreater(len(rows), 1)
        text = self.report()
        pending = text.split("\npending\n")[1].split("\nnext\n")[0]
        following = text.split("\nnext\n")[1].split("\nopen threads\n")[0]
        self.assertEqual(rows[0]["id"], pending.splitlines()[1].split()[0])
        self.assertEqual(rows[0]["id"], following.split()[0])
        self.assertIn(rows[0]["suggest"], following)
        for other in rows[1:]:
            self.assertNotIn(other["id"], following)

    def test_pending_states_the_denominator_it_capped_against(self) -> None:
        """A list that elides in silence is worse than no list."""
        for index in range(status.PENDING_LIMIT + 3):
            self.item(f"2026-08-{index + 1:02d}-item", status="in_progress")
        pending = self.report().split("\npending\n")[1].split("\nnext\n")[0]
        self.assertIn(f"{status.PENDING_LIMIT} of 13, by rank", pending)
        self.assertEqual(status.PENDING_LIMIT, len(pending.strip().splitlines()) - 1)

    def test_open_threads_counts_every_row_the_inventory_carries(self) -> None:
        """The per-source counts are a partition, not a sample.

        If they summed to less than the inventory, `pending`'s cap would have
        a denominator that understated what was elided.
        """
        self.item("2026-08-01-alpha", status="in_progress")
        self.item("2026-08-02-beta", status="planning")
        rows = self.inventory().rows
        threads = self.report().split("\nopen threads\n")[1].split("\nwork items\n")[0]
        counted = sum(
            int(line.rsplit(" ", 1)[1])
            for line in threads.splitlines()
            if line.startswith("  ") and line.rsplit(" ", 1)[-1].isdigit()
        )
        self.assertEqual(len(rows), counted)

    # -- widths are measured, never typed -----------------------------------

    def test_the_check_column_is_wide_enough_for_the_longest_check(self) -> None:
        """A hardcoded width lets one long name break every other line.

        `in-progress-without-branch` is 26 characters and the first draft of
        this renderer padded to 24, so that one row overflowed and every
        aligned line below it read as ragged.
        """
        self.assertEqual(
            max(len(kind.check) for kind in status.CLASSES), status.CHECK_WIDTH
        )
        banner = self.report().split("\npending\n")[0].splitlines()
        # The class rows start two lines below the heading: the summary
        # sentence sits between them and also ends in the word.
        start = banner.index("abnormalities") + 2
        labels = [line.index("clear") for line in banner[start:]
                  if line.startswith("  ") and line.rstrip().endswith("clear")]
        abnormal = sum(1 for kind in status.CLASSES if kind.abnormal)
        self.assertEqual(abnormal, len(labels))
        self.assertEqual(1, len(set(labels)))

class ActionsFlagTests(InventoryFixture):
    """`--actions`, and the two `--json` keys the report now carries.

    The flag exists because `pending` caps at ten and a caller that wants row
    eleven should not have to re-derive the list. So the thing under test is
    mostly that this surface is *not* the capped one.
    """

    def result(self, **overrides: Any) -> dict[str, Any]:
        inventory = self.inventory(**overrides)
        return {
            "actions": inventory.rows,
            "next": status.next_action(inventory.rows),
        }

    def actions_text(self, rows: list[dict[str, Any]]) -> str:
        stream = io.StringIO()
        status.render_actions(rows, stream)
        return stream.getvalue()

    def pending_text(self, rows: list[dict[str, Any]]) -> str:
        stream = io.StringIO()
        status._render_pending(rows, stream.write)
        return stream.getvalue()

    def test_the_count_on_the_first_line_equals_the_rows_below_it(self) -> None:
        """The acceptance criterion, in process rather than through a shell."""
        for index in range(6):
            self.item(f"2026-08-{index + 1:02d}-item", status="in_progress")
        rows = self.inventory().rows
        text = self.actions_text(rows)
        head = text.splitlines()[0]
        self.assertEqual(f"{len(rows)} actionable", head)
        self.assertEqual(
            len(rows),
            sum(1 for line in text.splitlines()
                if re.match(r"^[a-z][0-9a-f]{4,} ", line)),
        )

    def test_the_id_pattern_admits_a_widened_id(self) -> None:
        """`{4,}` and not `{4}`, which is what the criterion said.

        A collided id widens to eight hex digits by this design's own rule.
        The fixed-width form counted 120 of 122 in this repository and could
        never have passed here, so the criterion was wrong rather than the
        ids.
        """
        # `sd08e3f70` verbatim, one of the two this checkout actually widened,
        # and not a shortened stand-in: an id carrying seven hex digits passes
        # both assertions below while contradicting the docstring above them,
        # so the fixture has to carry the real width to be pinning anything.
        rows = [{"id": "sd08e3f70", "check": "open-step", "title": "t",
                 "suggest": "do the thing"}]
        line = self.actions_text(rows).splitlines()[1]
        self.assertTrue(re.match(r"^[a-z][0-9a-f]{4,} ", line))
        self.assertFalse(re.match(r"^[a-z][0-9a-f]{4} ", line))

    def test_a_widened_id_is_named_rather_than_changed_in_silence(self) -> None:
        """The mitigation `design.md:540` accepts the collision risk on.

        `_widen_collisions` has set `widened` since step 2 and no renderer read
        it, so a colliding id changed between runs with nothing in the text
        report saying why -- only `--json` carried the flag. The risk the
        design accepts is that "the survivor reverts to four, so its id
        changed"; the note is the whole reason that was acceptable.

        Two rows are forced to collide by giving them the same `(check, key)`
        under different data, which is what `_widen_collisions` keys on. One
        row would prove nothing: widening only happens to a pair.
        """
        rows = [
            {"id": "s0000", "check": "open-step", "title": "a",
             "suggest": "do a", "key": "same", "widened": True},
            {"id": "s0000", "check": "open-step", "title": "b",
             "suggest": "do b", "key": "same", "widened": True},
        ]
        for text in (self.actions_text(rows), self.pending_text(rows)):
            self.assertIn("widened to eight digits", text)
            self.assertIn("s0000", text)

    def test_no_note_is_printed_when_nothing_widened(self) -> None:
        """A line that always prints is not a signal."""
        rows = [{"id": "s0001", "check": "open-step", "title": "a",
                 "suggest": "do a", "key": "k", "widened": False}]
        self.assertNotIn("widened", self.actions_text(rows))

    def test_actions_is_not_capped_the_way_pending_is(self) -> None:
        """The whole point of the flag: `pending` elides, this does not."""
        for index in range(status.PENDING_LIMIT + 4):
            self.item(f"2026-08-{index + 1:02d}-item", status="in_progress")
        rows = self.inventory().rows
        self.assertGreater(len(rows), status.PENDING_LIMIT)
        listed = [line for line in self.actions_text(rows).splitlines()
                  if re.match(r"^[a-z][0-9a-f]{4,} ", line)]
        self.assertEqual(len(rows), len(listed))

    # -- the two keys -------------------------------------------------------

    def test_next_carries_the_id_it_belongs_to(self) -> None:
        """An object, not a string.

        A caller that acts on the suggestion needs the row it came from in
        the same breath; a bare sentence would make it look the id up again
        and could pick a different row than the one the report named.
        """
        self.item("2026-08-01-alpha", status="in_progress")
        self.item("2026-08-02-beta", status="in_progress")
        result = self.result()
        top = result["actions"][0]
        self.assertEqual(
            {"id": top["id"], "check": top["check"], "suggest": top["suggest"]},
            result["next"],
        )

    def test_next_is_none_rather_than_an_empty_object_when_nothing_is_open(
        self,
    ) -> None:
        """`null` says "no row"; `{}` would say "a row with no fields"."""
        self.assertEqual([], self.result()["actions"])
        self.assertIsNone(self.result()["next"])

    def test_actions_is_the_whole_inventory_and_not_a_second_producer(
        self,
    ) -> None:
        """C-3 again, at the `--json` boundary."""
        self.item("2026-08-01-alpha", status="in_progress")
        self.assertEqual(self.inventory().rows, self.result()["actions"])


class ActionsCliTests(StatusFixture):
    """The flag as a caller invokes it, including what wins against `--json`."""

    def test_json_wins_when_both_flags_are_given(self) -> None:
        """One output per run, and the machine-readable one is the wider.

        `--json` carries `actions` in full, so a caller passing both loses
        nothing by getting the object; the reverse would drop every other key.
        """
        self.item("2026-08-01-alpha", status="in_progress")
        completed = self.run_tool(SD_STATUS, "--json", "--actions")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(3, payload["schema"])
        self.assertTrue(payload["actions"])

    def test_the_actions_key_is_the_whole_inventory_not_the_pending_slice(
        self,
    ) -> None:
        """Through `collect()`, and with more rows than `pending` will show.

        `ActionsFlagTests` builds this key by hand to exercise the renderer,
        so nothing there can see a slice applied inside `collect()`: a
        deliberate `rows[:PENDING_LIMIT]` in the producer passed that whole
        class. It is the fixture defect the C-3 test had on step 4 wearing a
        different hat -- a fixture holding one row cannot tell an uncapped
        list from a capped one -- and the fix is the same, which is to hand
        the assertion more rows than the cap.
        """
        for index in range(status.PENDING_LIMIT + 4):
            self.item(f"2026-08-{index + 1:02d}-item", status="in_progress")
        payload = self.report()
        rows = payload["inventory"]["rows"]
        self.assertGreater(len(rows), status.PENDING_LIMIT)
        self.assertEqual(rows, payload["actions"])

    def test_the_flag_prints_the_list_and_nothing_else(self) -> None:
        self.item("2026-08-01-alpha", status="in_progress")
        completed = self.run_tool(SD_STATUS, "--actions")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(completed.stdout.startswith("1 actionable\n"))
        for absent in ("abnormalities", "pending", "work items"):
            self.assertNotIn(f"\n{absent}\n", completed.stdout)


if __name__ == "__main__":
    unittest.main()
