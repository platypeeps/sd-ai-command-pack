"""Advisory routing reports unknown attribution without authorizing a review."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import Mock, patch

from sd_db import connect, create_item, initialise, upsert_repo

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review
from tests.test_sd_ship import ship


class AdvisoryAuthorshipTests(ReviewFixture):
    def branch(self, message="Bump fixture from1 to2"):
        root = self.make_repo()
        subprocess.run(["git", "checkout", "-qb", "dependabot/fixture"], cwd=root, check=True)
        (root / "requirements.txt").write_text("fixture==2\n")
        subprocess.run(["git", "add", "requirements.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
        return root

    def explained(self, root, **kwargs):
        runner, client = FakeRunner(), Mock(side_effect=AssertionError("URL provider must not run"))
        result = sd_review.review(root, namespace(scope="pr", explain=True, **kwargs), runner,
                                  self.environment(), self.chatgpt_home(), client=client)
        self.assertEqual(runner.calls, [])
        client.assert_not_called()
        return result

    def assert_unknown(self, result):
        self.assertEqual(result["status"], "explained")
        self.assertTrue(result["authorship_refusal"])
        self.assertIn("unknown", result["authored_with_report"])
        self.assertNotIn("human (every commit says so)", result["authored_with_report"])
        self.assertEqual(result["providers"], [])
        self.assertEqual(result["fallback_candidates"], [])
        self.assertEqual(result["completed_reviews"], 0)
        self.assertTrue(result["chain"])
        self.assertTrue(all(not row["eligible"] for row in result["chain"]))
        self.assertTrue(all(result["authorship_refusal"] in row["reason"] for row in result["chain"]))

    def test_untrailered_consumer_explain_marks_all_reviewers_ineligible(self):
        result = self.explained(self.branch())
        self.assert_unknown(result)
        self.assertIn("carry no Authored-with:", result["authorship_refusal"])
        output = io.StringIO()
        sd_review.render(result, output)
        self.assertIn(result["authorship_refusal"], output.getvalue())
        self.assertIn("explain only, nothing ran", output.getvalue())

    def test_invalid_trailer_is_unknown_not_a_human_claim(self):
        self.assert_unknown(self.explained(self.branch("change\n\nAuthored-with: openai")))

    def test_explicit_provider_does_not_bypass_unknown_authorship(self):
        result = self.explained(self.branch(), provider="second")
        self.assert_unknown(result)
        self.assertEqual(result["requested_reviews"], 1)

    def test_real_and_dry_run_refuse_before_checks_or_either_provider_transport(self):
        root = self.branch()
        for scope in ("branch", "pr"):
            for dry_run in (False, True):
                with self.subTest(scope=scope, dry_run=dry_run):
                    runner, client = FakeRunner(), Mock()
                    with self.assertRaises(sd_review.Refusal):
                        sd_review.review(root, namespace(scope=scope, dry_run=dry_run), runner,
                                         self.environment(), self.chatgpt_home(), client=client)
                    self.assertEqual(runner.calls, [])
                    client.assert_not_called()

    def test_known_author_vendor_still_excludes_its_own_reviewer(self):
        result = self.explained(self.branch("change\n\nAuthored-with: codex/openai"))
        self.assertFalse(result["authorship_refusal"])
        self.assertEqual(result["authored_with"], ["openai"])
        self.assertFalse(next(row for row in result["chain"] if row["provider"] == "codex")["eligible"])
        self.assertTrue(next(row for row in result["chain"] if row["provider"] == "second")["eligible"])

    def test_unknown_advisory_plan_preserves_zero_shipping_reservations(self):
        root = self.branch()
        remote = "https://github.com/fixture/repo.git"
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=root, check=True)
        database = self.tmp / "isolated-shipping/sd.db"
        initialise(database)
        connection = connect(database)
        self.addCleanup(connection.close)
        upsert_repo(connection, str(root), remote=remote)
        item = create_item(connection, kind="task", title="unknown authorship fixture", status="in_progress",
                           repo=str(root), branch="dependabot/fixture")
        runner, client = FakeRunner(), Mock(side_effect=AssertionError("URL provider must not run"))
        plan = sd_review.review(root, namespace(scope="branch", explain=True, database=database, challenge=True),
                                runner, self.environment(), self.chatgpt_home(), client=client)
        self.assert_unknown(plan)
        completed = subprocess.CompletedProcess([], 0, json.dumps(plan), "")
        with self.assertRaisesRegex(ship.Refusal, "no provider pass was reserved"):
            ship.timing_plan(completed)
        args = ship.parser().parse_args(["prepare", "--item", str(item), "--database", str(database), "--json"])
        operation = ship.Ship(root, connection, database, args)
        self.assertFalse(operation.state.get("passes"))

        def explain_only(_root, argv, *, timeout):
            self.assertIn("--explain", argv, "shipping must stop before review execution")
            return completed

        with patch.object(ship, "review_process", side_effect=explain_only) as process:
            with self.assertRaisesRegex(ship.Refusal, "no valid timing plan"):
                operation.review(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip())
        self.assertEqual(process.call_count, 1)
        saved = ship.Ship(root, connection, database, args).state
        self.assertFalse(saved.get("passes"))
        self.assertIsNone(saved.get("reviewed_head"))
        diagnostic = saved["review_preflight_error"]
        self.assertEqual((diagnostic["kind"], diagnostic["stage"], diagnostic["exit_code"]),
                         ("invalid_timing_plan", "planning", 0))
        self.assertEqual(diagnostic["stdout"]["sha256"], hashlib.sha256(completed.stdout.encode()).hexdigest())
        self.assertEqual(runner.calls, [])
        client.assert_not_called()

    def test_actual_advisory_action_succeeds_and_reports_missing_authorship(self):
        root = self.branch()
        remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "main"], cwd=root, check=True)
        subprocess.run(["git", "checkout", "--detach", "-q"], cwd=root, check=True)
        pack = Path(sd_review.__file__).resolve().parents[1]
        script = textwrap.dedent((pack / "actions/review-route/action.yml").read_text().split("      run: |\n", 1)[1])
        summary = self.tmp / "step-summary.md"
        home = self.tmp / "empty-action-home"
        home.mkdir()
        environment = {"HOME": str(home), "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
                       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "PYTHONDONTWRITEBYTECODE": "1",
                       "GITHUB_ACTION_PATH": str(pack / "actions/review-route"), "GITHUB_STEP_SUMMARY": str(summary),
                       "GITHUB_BASE_REF": "main", "SD_REVIEW_SCOPE": "pr"}
        before = subprocess.check_output(["git", "status", "--porcelain"], cwd=root)
        result = subprocess.run(["/bin/bash", "-c", script], cwd=root, env=environment,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unknown", summary.read_text())
        self.assertIn("Authored-with:", summary.read_text())
        self.assertEqual(subprocess.check_output(["git", "status", "--porcelain"], cwd=root), before)
        explained = subprocess.run([sys.executable, str(pack / "bin/sd-review"), "--scope", "pr", "--explain", "--json"],
                                   cwd=root, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(explained.returncode, 0, explained.stderr)
        self.assertTrue(json.loads(explained.stdout)["authorship_refusal"])
