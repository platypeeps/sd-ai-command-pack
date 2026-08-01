from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PACK_ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_PATH = PACK_ROOT / ".github/scripts/bookkeeping_ci_scope.py"
AGGREGATE_PATH = PACK_ROOT / ".github/scripts/check-ci-result.sh"
WORKFLOW_PATH = PACK_ROOT / ".github/workflows/tests.yml"

SPEC = importlib.util.spec_from_file_location("bookkeeping_ci_scope", CLASSIFIER_PATH)
assert SPEC and SPEC.loader
bookkeeping_ci_scope = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bookkeeping_ci_scope
SPEC.loader.exec_module(bookkeeping_ci_scope)


class BookkeepingCiScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.evidence_counter = 0
        self.git("init", "-b", "main")
        self.git("config", "user.email", "ci@example.com")
        self.git("config", "user.name", "CI Test")
        self.write("README.md", "baseline\n")
        self.commit("baseline")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def oid(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", ref).stdout.strip()

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-m", message)
        return self.oid()

    def evidence_files(
        self,
        before_sha: str,
        *,
        event_name: str = "pull_request",
        pr_number: int = 17,
        run_id: int = 101,
        check_run_id: int = 202,
        conclusion: str = "success",
        associated_pr: int | None = None,
        details_run_id: int | None = None,
        head_branch: str | None = None,
    ) -> tuple[Path, Path]:
        self.evidence_counter += 1
        pulls = []
        if event_name == "pull_request":
            pulls = [{"number": associated_pr if associated_pr is not None else pr_number}]
        runs = {
            "workflow_runs": [
                {
                    "id": run_id,
                    "name": "Tests",
                    "path": ".github/workflows/tests.yml",
                    "head_sha": before_sha,
                    "head_branch": head_branch
                    if head_branch is not None
                    else "main"
                    if event_name == "push"
                    else "feature",
                    "status": "completed",
                    "conclusion": conclusion,
                    "event": event_name,
                    "pull_requests": pulls,
                }
            ]
        }
        checks = {
            "check_runs": [
                {
                    "id": check_run_id,
                    "name": "CI Result",
                    "head_sha": before_sha,
                    "status": "completed",
                    "conclusion": conclusion,
                    "details_url": (
                        "https://github.com/example/repo/actions/runs/"
                        f"{details_run_id if details_run_id is not None else run_id}/job/1"
                    ),
                    "app": {"slug": "github-actions"},
                }
            ]
        }
        runs_path = self.write(
            f"runs-{self.evidence_counter}.json",
            json.dumps(runs),
        )
        checks_path = self.write(
            f"checks-{self.evidence_counter}.json",
            json.dumps(checks),
        )
        return runs_path, checks_path

    def args(
        self,
        before_sha: str,
        after_sha: str,
        *,
        event_name: str = "pull_request",
        event_action: str = "synchronize",
        pr_number: int | None = 17,
        evidence_available: bool = True,
        runs_path: Path | None = None,
        checks_path: Path | None = None,
    ) -> argparse.Namespace:
        if runs_path is None or checks_path is None:
            runs_path, checks_path = self.evidence_files(
                before_sha,
                event_name=event_name,
                pr_number=pr_number or 17,
            )
        return argparse.Namespace(
            repo=self.root,
            event_name=event_name,
            event_action=event_action,
            before_sha=before_sha,
            after_sha=after_sha,
            pr_number=pr_number,
            protected_ref="refs/heads/main",
            runs_json=runs_path,
            checks_json=checks_path,
            evidence_available=evidence_available,
        )

    def classify(self, *args: object, **kwargs: object) -> dict[str, object]:
        return bookkeeping_ci_scope.classify(self.args(*args, **kwargs))

    def test_journal_only_pr_successor_selects_bookkeeping(self) -> None:
        before = self.oid()
        self.write(".trellis/workspace/dev/journal-1.md", "## Session 1\n")
        self.write(".trellis/workspace/dev/index.md", "| 1 | Session |\n")
        after = self.commit("record journal")

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "bookkeeping")
        self.assertEqual(decision["reasonCode"], "verified_bookkeeping_successor")
        self.assertEqual(decision["validationMode"], "planning")
        self.assertEqual(decision["evidenceRunId"], 101)
        self.assertEqual(decision["evidenceCheckRunId"], 202)
        self.assertEqual(decision["evidenceScope"], "pull_request:17")

    def test_multiple_linear_bookkeeping_commits_are_one_successor(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{"status":"planning"}\n')
        self.commit("add task")
        self.write(".trellis/workspace/dev/journal-1.md", "## Session 1\n")
        self.write(".trellis/workspace/dev/index.md", "| 1 | Session |\n")
        after = self.commit("record journal")

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "bookkeeping")
        self.assertEqual(decision["commitCount"], 2)
        self.assertEqual(decision["validationMode"], "planning")

    def test_task_metadata_only_uses_generic_validation(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{"status":"planning"}\n')
        after = self.commit("add task")

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "bookkeeping")
        self.assertEqual(decision["validationMode"], "none")

    def test_archive_and_journal_delta_selects_completion_validation(self) -> None:
        self.write(".trellis/tasks/07-01-example/task.json", '{"status":"in_progress"}\n')
        self.write(".trellis/tasks/07-01-example/prd.md", "# Example\n")
        before = self.commit("add active task")
        archive = self.root / ".trellis/tasks/archive/2026-07/07-01-example"
        archive.parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", ".trellis/tasks/07-01-example", str(archive.relative_to(self.root)))
        self.write(".trellis/workspace/dev/journal-1.md", "## Session 1\n")
        self.write(".trellis/workspace/dev/index.md", "| 1 | Session |\n")
        after = self.commit("archive and journal")

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "bookkeeping")
        self.assertEqual(decision["validationMode"], "completion")
        self.assertIn(
            ".trellis/tasks/archive/2026-07/07-01-example/task.json",
            decision["changedPaths"],
        )

    def test_direct_main_bookkeeping_uses_same_ref_evidence(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{"status":"planning"}\n')
        after = self.commit("add task")
        runs, checks = self.evidence_files(before, event_name="push")

        decision = self.classify(
            before,
            after,
            event_name="push",
            event_action="",
            pr_number=None,
            runs_path=runs,
            checks_path=checks,
        )

        self.assertEqual(decision["mode"], "bookkeeping")
        self.assertEqual(decision["evidenceScope"], "ref:refs/heads/main")

    def test_direct_main_rejects_prior_success_from_another_ref(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{"status":"planning"}\n')
        after = self.commit("add task")
        runs, checks = self.evidence_files(
            before,
            event_name="push",
            head_branch="feature",
        )

        decision = self.classify(
            before,
            after,
            event_name="push",
            event_action="",
            pr_number=None,
            runs_path=runs,
            checks_path=checks,
        )

        self.assertEqual(decision["mode"], "full")
        self.assertEqual(decision["reasonCode"], "prior_success_missing")

    def test_non_bookkeeping_and_unsafe_tree_entries_select_full(self) -> None:
        scenarios = []

        before = self.oid()
        self.write("source.py", "print('changed')\n")
        after = self.commit("source")
        scenarios.append((before, after, "changed_path_not_bookkeeping"))

        self.git("reset", "--hard", before)
        executable = self.write(".trellis/tasks/tool.sh", "#!/bin/sh\n")
        executable.chmod(0o755)
        after = self.commit("executable")
        scenarios.append((before, after, "tree_entry_unsafe"))

        self.git("reset", "--hard", before)
        link = self.root / ".trellis/tasks/link"
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink("../../README.md", link)
        after = self.commit("symlink")
        scenarios.append((before, after, "tree_entry_unsafe"))

        for base, head, reason in scenarios:
            with self.subTest(reason=reason, head=head):
                self.git("reset", "--hard", head)
                decision = self.classify(base, head)
                self.assertEqual(decision["mode"], "full")
                self.assertEqual(decision["reasonCode"], reason)

    def test_control_character_path_selects_full(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/bad\nname/task.json", '{}\n')
        after = self.commit("unsafe path")

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "full")
        self.assertEqual(decision["reasonCode"], "changed_path_invalid")

    def test_oversized_path_set_selects_full(self) -> None:
        before = self.oid()
        for index in range(bookkeeping_ci_scope.MAX_CHANGED_PATHS + 1):
            self.write(f".trellis/tasks/bulk/{index}.json", '{}\n')
        after = self.commit("oversized bookkeeping delta")

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "full")
        self.assertEqual(decision["reasonCode"], "changed_path_set_oversized")

    def test_non_ancestor_and_checked_out_head_mismatch_select_full(self) -> None:
        before = self.oid()
        self.git("switch", "-c", "old-head")
        self.write(".trellis/tasks/old/task.json", '{}\n')
        old_head = self.commit("old task")
        self.git("switch", "main")
        self.write(".trellis/tasks/new/task.json", '{}\n')
        after = self.commit("new task")

        non_ancestor = self.classify(old_head, after)
        mismatch = self.classify(before, old_head)

        self.assertEqual(non_ancestor["mode"], "full")
        self.assertEqual(non_ancestor["reasonCode"], "history_not_ancestor")
        self.assertEqual(mismatch["mode"], "full")
        self.assertEqual(mismatch["reasonCode"], "after_head_mismatch")

    def test_gitlink_selects_full(self) -> None:
        before = self.oid()
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{before},.trellis/tasks/gitlink",
        )
        self.git("commit", "-m", "gitlink")
        after = self.oid()

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "full")
        self.assertEqual(decision["reasonCode"], "tree_entry_unsafe")

    def test_merge_commit_selects_full(self) -> None:
        before = self.oid()
        self.git("switch", "-c", "side")
        self.write(".trellis/tasks/side/task.json", '{}\n')
        self.commit("side task")
        self.git("switch", "main")
        self.write(".trellis/tasks/main/task.json", '{}\n')
        self.commit("main task")
        self.git("merge", "--no-ff", "side", "-m", "merge bookkeeping")
        after = self.oid()

        decision = self.classify(before, after)

        self.assertEqual(decision["mode"], "full")
        self.assertEqual(decision["reasonCode"], "history_contains_merge")

    def test_missing_wrong_pr_or_failed_prior_evidence_selects_full(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{}\n')
        after = self.commit("task")
        wrong_runs, wrong_checks = self.evidence_files(before, associated_pr=99)
        failed_runs, failed_checks = self.evidence_files(before, conclusion="failure")
        cancelled_runs, cancelled_checks = self.evidence_files(
            before,
            conclusion="cancelled",
        )
        other_run, other_check = self.evidence_files(before, details_run_id=999)

        cases = (
            (
                self.args(
                    before,
                    after,
                    runs_path=wrong_runs,
                    checks_path=wrong_checks,
                ),
                "prior_success_missing",
            ),
            (
                self.args(
                    before,
                    after,
                    runs_path=failed_runs,
                    checks_path=failed_checks,
                ),
                "prior_success_missing",
            ),
            (
                self.args(
                    before,
                    after,
                    runs_path=cancelled_runs,
                    checks_path=cancelled_checks,
                ),
                "prior_success_missing",
            ),
            (
                self.args(
                    before,
                    after,
                    runs_path=other_run,
                    checks_path=other_check,
                ),
                "prior_success_missing",
            ),
            (self.args(before, after, evidence_available=False), "prior_evidence_unavailable"),
        )
        for args, reason in cases:
            with self.subTest(reason=reason):
                decision = bookkeeping_ci_scope.classify(args)
                self.assertEqual(decision["mode"], "full")
                self.assertEqual(decision["reasonCode"], reason)

    def test_invalid_evidence_and_event_boundaries_select_full(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{}\n')
        after = self.commit("task")
        invalid_runs = self.write("invalid-runs.json", "not json\n")
        _, checks = self.evidence_files(before)

        invalid = bookkeeping_ci_scope.classify(
            self.args(before, after, runs_path=invalid_runs, checks_path=checks)
        )
        opened = bookkeeping_ci_scope.classify(
            self.args("", after, event_action="opened")
        )
        malformed = bookkeeping_ci_scope.classify(
            self.args("not-a-sha", after)
        )
        missing = bookkeeping_ci_scope.classify(
            self.args("f" * 40, after)
        )

        self.assertEqual(invalid["reasonCode"], "prior_evidence_invalid")
        self.assertEqual(opened["reasonCode"], "pull_request_action_not_synchronize")
        self.assertEqual(malformed["reasonCode"], "before_sha_invalid")
        self.assertEqual(missing["reasonCode"], "commit_object_unavailable")
        self.assertTrue(all(item["mode"] == "full" for item in (invalid, opened, malformed, missing)))

    def test_cli_emits_one_versioned_json_document(self) -> None:
        before = self.oid()
        self.write(".trellis/tasks/07-01-example/task.json", '{}\n')
        after = self.commit("task")
        runs, checks = self.evidence_files(before)

        result = subprocess.run(
            [
                sys.executable,
                str(CLASSIFIER_PATH),
                "--repo",
                str(self.root),
                "--event-name",
                "pull_request",
                "--event-action",
                "synchronize",
                "--before-sha",
                before,
                "--after-sha",
                after,
                "--pr-number",
                "17",
                "--runs-json",
                str(runs),
                "--checks-json",
                str(checks),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["kind"], "bookkeeping-ci-scope")
        self.assertEqual(result.stdout.count("\n"), 1)


class CiResultAggregateTests(unittest.TestCase):
    def run_aggregate(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(AGGREGATE_PATH), *args],
            cwd=PACK_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_accepts_only_legal_mode_specific_lane_combinations(self) -> None:
        passing = (
            ("pull_request", "success", "full", "success", "success", "success", "success", "skipped"),
            ("push", "success", "full", "success", "success", "success", "skipped", "success"),
            ("pull_request", "success", "bookkeeping", "skipped", "skipped", "skipped", "skipped", "skipped"),
            ("push", "success", "bookkeeping", "skipped", "skipped", "skipped", "skipped", "success"),
        )
        for args in passing:
            with self.subTest(args=args):
                result = self.run_aggregate(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"accepted the {args[2]} mode", result.stdout)

    def test_rejects_failures_skips_and_impossible_combinations(self) -> None:
        failing = (
            ("pull_request", "failure", "full", "skipped", "skipped", "skipped", "skipped", "skipped"),
            ("pull_request", "success", "full", "skipped", "success", "success", "success", "skipped"),
            ("push", "success", "full", "success", "success", "success", "skipped", "skipped"),
            ("pull_request", "success", "bookkeeping", "success", "skipped", "skipped", "skipped", "skipped"),
            ("push", "success", "bookkeeping", "skipped", "skipped", "skipped", "skipped", "skipped"),
            ("pull_request", "success", "unknown", "skipped", "skipped", "skipped", "skipped", "skipped"),
        )
        for args in failing:
            with self.subTest(args=args):
                result = self.run_aggregate(*args)
                self.assertEqual(result.returncode, 1, result.stdout)


class BookkeepingWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.workflow = yaml.load(self.text, Loader=yaml.BaseLoader)

    def scope_step(self, step_id: str) -> dict:
        steps = self.workflow["jobs"]["ci-scope"]["steps"]
        matches = [step for step in steps if step.get("id") == step_id]
        self.assertEqual(
            len(matches), 1, f"expected exactly one ci-scope step with id {step_id}"
        )
        return matches[0]

    def test_scope_job_is_read_only_prior_head_and_exact_event_head(self) -> None:
        scope = self.workflow["jobs"]["ci-scope"]
        self.assertEqual(scope["name"], "CI scope")
        self.assertEqual(
            scope["permissions"],
            {"actions": "read", "checks": "read", "contents": "read"},
        )
        checkout = scope["steps"][0]
        self.assertEqual(checkout["with"]["fetch-depth"], "0")
        self.assertEqual(
            checkout["with"]["ref"],
            "${{ github.event.pull_request.head.sha || github.sha }}",
        )
        classify = self.scope_step("classify")["run"]
        self.assertIn('git ls-tree "$BEFORE_SHA"', classify)
        self.assertIn('git show "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py"', classify)
        self.assertIn("actions/workflows/tests.yml/runs?head_sha=${BEFORE_SHA}", classify)
        self.assertIn("commits/${BEFORE_SHA}/check-runs", classify)
        self.assertIn(
            'if .mode == "bookkeeping" then .evidenceRunId != null and .evidenceCheckRunId != null else true end',
            classify,
        )
        self.assertIn('write_full_result "bootstrap_full"', classify)
        self.assertNotIn("pull_request_target", self.text)

    def test_prior_classifier_is_pinned_to_the_pull_request_base(self) -> None:
        classify_step = self.scope_step("classify")
        classify = classify_step["run"]

        # The base sha must be wired in. Without it the guard compares
        # $BEFORE_SHA's blob against the checked-out index -- "git rev-parse
        # ':path'" with an empty prefix resolves and exits 0 -- so the ordering
        # assertion below would still pass while nothing was actually pinned.
        self.assertEqual(
            classify_step["env"]["BASE_SHA"],
            "${{ github.event.pull_request.base.sha }}",
        )

        show_index = classify.index(
            'git show "$BEFORE_SHA:.github/scripts/bookkeeping_ci_scope.py"'
        )
        guard_start = classify.index(
            'if [ "$EVENT_NAME" = "pull_request" ]',
            classify.index('select_full "prior_classifier_unsafe"'),
        )
        self.assertLess(guard_start, show_index)
        guard = classify[guard_start:show_index]

        # Identity is established before the author-controlled blob is written
        # to disk and executed.
        self.assertLess(
            classify.index('git rev-parse "$BASE_SHA:'),
            show_index,
        )

        # An empty base sha is rejected explicitly, before the first rev-parse.
        # Either polarity is acceptable.
        emptiness = [
            guard.index(check)
            for check in ('[ -z "$BASE_SHA" ]', '[ -n "$BASE_SHA" ]')
            if check in guard
        ]
        self.assertTrue(emptiness, "guard must test BASE_SHA for emptiness")
        self.assertLess(min(emptiness), guard.index('git rev-parse "$BASE_SHA:'))

        # Every failure path falls back to full mode. Exact counts, not floors:
        # a floor of two would pass a guard that dropped the emptiness check.
        self.assertEqual(
            guard.count('select_full "prior_classifier_identity_unavailable"'), 3
        )
        self.assertEqual(
            guard.count('select_full "prior_classifier_not_base_identical"'), 1
        )

        # Neither lookup may be advisory: each must be the condition of a
        # branch, so a failure reaches one of the calls counted above.
        lookups = [
            line.strip()
            for line in guard.splitlines()
            if 'git rev-parse "' in line
        ]
        self.assertEqual(len(lookups), 2)
        for line in lookups:
            self.assertTrue(
                line.startswith("if ! ") and line.endswith("; then"),
                f"classifier rev-parse must gate a branch: {line}",
            )

    def test_expensive_lanes_run_only_in_full_mode(self) -> None:
        jobs = self.workflow["jobs"]
        for name in ("unittest", "lint", "security", "release-payload-gate"):
            with self.subTest(job=name):
                self.assertEqual(jobs[name]["needs"], "ci-scope")
                self.assertIn("needs.ci-scope.outputs.mode == 'full'", jobs[name]["if"])
        self.assertNotIn("needs", jobs["main-push-scope"])
        self.assertNotIn("paths-ignore", self.workflow["on"]["push"])

    def test_bookkeeping_lane_reuses_canonical_validators(self) -> None:
        validation = self.scope_step("bookkeeping-validation")
        self.assertIn("git diff --check", validation["run"])
        self.assertIn("SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF", validation["run"])
        self.assertIn("sd-ai-command-pack-review-preflight.mjs", validation["run"])
        self.assertIn("final-bundle --mode", validation["run"])
        self.assertIn('reasonCodes == [($mode + "_bundle_valid")]', validation["run"])

    def test_bookkeeping_lane_measures_review_preflight_coverage(self) -> None:
        install = self.scope_step("install-review-preflight-coverage-tooling")
        self.assertEqual(install["if"], "steps.classify.outputs.mode == 'bookkeeping'")
        self.assertIn("npm ci", install["run"])

        validation = self.scope_step("bookkeeping-validation")
        self.assertIn("--clean=false", validation["run"])
        self.assertIn("c8_run=(npm exec --no -- c8", validation["run"])
        self.assertEqual(
            validation["run"].count('"${c8_run[@]}"'),
            2,
            "both review-preflight.mjs invocations must reuse the shared c8_run wrapper",
        )

        report = self.scope_step("report-review-preflight-coverage")
        self.assertEqual(
            report["if"], "steps.classify.outputs.mode == 'bookkeeping' && !cancelled()"
        )
        self.assertIn(
            "jq -e '.total.lines.total > 0 and .total.lines.covered > 0'", report["run"]
        )

        validation_temp_dir = re.search(r'c8_temp_dir="([^"]+)"', validation["run"])
        report_temp_dir = re.search(r'c8_temp_dir="([^"]+)"', report["run"])
        self.assertIsNotNone(validation_temp_dir)
        self.assertIsNotNone(report_temp_dir)
        self.assertEqual(
            validation_temp_dir.group(1),
            report_temp_dir.group(1),
            "validation and report steps must accumulate coverage in the same --temp-directory",
        )

    def test_report_review_preflight_coverage_gate_fails_closed_on_zero_lines(self) -> None:
        report = self.scope_step("report-review-preflight-coverage")
        match = re.search(r"jq -e '([^']+)'", report["run"])
        self.assertIsNotNone(match, "expected a jq -e gate expression in the report step")
        gate_expression = match.group(1)

        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "coverage-summary.json"
            summary_path.write_text(
                json.dumps({"total": {"lines": {"total": 0, "covered": 0, "pct": 0}}}),
                encoding="utf-8",
            )
            result = subprocess.run(
                ["jq", "-e", gate_expression, str(summary_path)],
                capture_output=True,
                text=True,
            )

        self.assertNotEqual(
            result.returncode,
            0,
            "jq -e gate must fail closed (nonzero exit) when c8 measures zero lines",
        )

    def test_aggregate_and_auto_tag_are_mode_bound(self) -> None:
        jobs = self.workflow["jobs"]
        aggregate = jobs["ci-result"]
        self.assertIn("ci-scope", aggregate["needs"])
        self.assertEqual(aggregate["outputs"]["mode"], "${{ steps.evaluate.outputs.mode }}")
        checkout = aggregate["steps"][0]
        self.assertEqual(
            checkout["with"]["ref"],
            "${{ github.event.pull_request.head.sha || github.sha }}",
        )
        self.assertEqual(checkout["with"]["persist-credentials"], "false")
        self.assertIn(".github/scripts/check-ci-result.sh", aggregate["steps"][1]["run"])
        self.assertIn(
            "needs.ci-result.outputs.mode == 'full'",
            jobs["auto-tag-release"]["if"],
        )


if __name__ == "__main__":
    unittest.main()
