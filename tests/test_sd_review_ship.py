"""Bounded fix review keeps original blockers, authors, and exact endpoints."""

from __future__ import annotations

import json
import os
import pwd
import subprocess

from tests.test_sd_review import FakeRunner, ReviewFixture, namespace, sd_review


class FixReviewTests(ReviewFixture):
    def commit(self, root, path, text, message="change\n\nAuthored-with: human"):
        (root / path).write_text(text)
        subprocess.run(["git", "add", "--", path], cwd=root, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=root, capture_output=True, check=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    def branch(self):
        root = self.make_repo()
        subprocess.run(["git", "checkout", "-b", "topic"], cwd=root, capture_output=True, check=True)
        first = self.commit(root, "src.py", "the_original_defect = True\n")
        return root, first

    def test_exact_ancestor_is_the_whole_fix_subject(self):
        root, first = self.branch()
        second = self.commit(root, "other.py", "only_the_fix = 1\n")
        subject = sd_review.resolve_subject(root, "branch", base=first)
        self.assertEqual((subject.base, subject.head, subject.paths), (first, second, ("other.py",)))
        for scope, base in (("worktree", first), ("pr", first), ("branch", first[:12]), ("branch", "f" * 40)):
            with self.subTest(scope=scope, base=base), self.assertRaises(sd_review.UsageError):
                sd_review.resolve_subject(root, scope, base=base)

    def test_fix_commit_with_no_author_trailer_is_refused(self):
        root, first = self.branch()
        self.commit(root, "fix.py", "fix = 1\n", "unknown author")
        with self.assertRaises(sd_review.Refusal):
            sd_review.review(root, namespace(scope="branch", base=first), FakeRunner(), self.environment(), self.chatgpt_home())

    def test_unchanged_blocker_and_source_reach_the_fix_reviewer(self):
        root, first = self.branch()
        blocking = json.dumps({"findings": [{"path": "src.py", "line": 1, "summary": "original unresolved defect",
                                            "family": "correctness", "severity": "high"}]})
        prior = sd_review.review(root, namespace(scope="branch"), FakeRunner({"codex": sd_review.Completed(0, blocking, "")}),
                                 self.environment(), self.chatgpt_home())
        report = self.tmp / "prior.json"
        report.write_text(json.dumps(prior))
        self.commit(root, "other.py", "unrelated_fix = True\n")
        runner = FakeRunner({"codex": sd_review.Completed(0, blocking, "")})
        result = sd_review.review(root, namespace(scope="branch", base=first, verify_report=str(report)), runner,
                                  self.environment(), self.chatgpt_home())
        self.assertEqual(result["status"], "blocking")
        self.assertEqual(result["subject"]["paths"], ["other.py"])
        handed = json.dumps(runner.calls, default=str)
        self.assertIn("original unresolved defect", handed)
        self.assertIn("the_original_defect = True", handed)
        self.assertTrue(result["verification_report_digest"])

    def test_mismatched_or_malformed_previous_report_cannot_verify(self):
        root, first = self.branch()
        self.commit(root, "fix.py", "fix = True\n")
        report = self.tmp / "prior.json"
        for prior in ({}, {"scope": "branch", "subject": {"head": "0" * 40}, "status": "clean", "findings": [], "authored_with": []},
                      {"scope": "branch", "subject": {"head": first}, "status": "clean", "findings": ["forged"], "authored_with": []}):
            report.write_text(json.dumps(prior))
            runner = FakeRunner()
            with self.assertRaises(sd_review.UsageError):
                sd_review.review(root, namespace(scope="branch", base=first, verify_report=str(report)), runner,
                                 self.environment(), self.chatgpt_home())
            self.assertEqual(runner.calls, [])

    def test_every_actual_squash_author_vendor_is_excluded(self):
        root, first = self.branch()
        self.commit(root, "combined.py", "combined = 1\n", "multi author\n\nAuthored-with: codex/openai\nAuthored-with: claude/anthropic")
        vendors = sd_review.sd_lib.author_vendors(root, first, "HEAD")
        self.assertEqual(set(vendors), {"openai", "anthropic"})

    def test_refreshed_default_code_is_reviewed_without_requiring_item_authorship(self):
        root, first = self.branch()
        subprocess.run(["git", "checkout", "main"], cwd=root, check=True, capture_output=True)
        target = self.commit(root, "upstream.py", "fresh_target = True\n", "upstream change without local attribution")
        subprocess.run(["git", "checkout", "topic"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "merge", "--no-edit", "main"], cwd=root, check=True, capture_output=True)
        result = sd_review.review(root, namespace(scope="branch", base=first), FakeRunner(), self.environment(), self.chatgpt_home())
        self.assertEqual(result["status"], "clean")
        self.assertIn("upstream.py", result["subject"]["paths"])
        self.assertEqual(result["subject"]["base"], first)
        self.assertEqual(result["authorship_base"], target)

    def test_provider_user_is_actual_uid_and_unrelated_keys_stay_absent(self):
        provider = sd_review.sd_registry.Provider(name="fixture", vendor="fixture", bill="first", env=("OWN_KEY",))
        result = sd_review.sd_registry.provider_environment(provider, {"USER": "spoofed", "OWN_KEY": "mine", "OTHER_KEY": "secret"})
        self.assertEqual(result["USER"], pwd.getpwuid(os.getuid()).pw_name)
        self.assertEqual(result["OWN_KEY"], "mine")
        self.assertNotIn("OTHER_KEY", result)

    def test_native_auth_error_is_reported_while_structured_blocker_survives(self):
        findings = {"findings": [{"path": "src.py", "line": 1, "summary": "blocker", "family": "correctness", "severity": "high"}]}
        result, parsed = sd_review.claude_answer(sd_review.Completed(0, json.dumps({"type": "result", "subtype": "error",
                                 "is_error": True, "result": "Not logged in", "structured_output": findings}), ""))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.stderr, "Not logged in")
        self.assertTrue(parsed)
