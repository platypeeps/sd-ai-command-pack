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

import importlib.machinery
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
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
        self.assertIn("gates nothing", found[0]["gap"])


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

    def test_protection_degrades_with_no_github_remote(self) -> None:
        self.install_gh()
        completed = self.run_tool(SD_STATUS)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("no GitHub remote", completed.stdout)


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


if __name__ == "__main__":
    unittest.main()
