"""Input limits yield complete, nonexecuting split-branch advice."""

from __future__ import annotations

import os
import subprocess
from unittest import mock

from tests.test_sd_review import (
    FakeClient,
    FakeRunner,
    ReviewFixture,
    namespace,
    sd_review,
)
from tests.test_sd_review_readiness import read_only_connections


class OversizeTests(ReviewFixture):
    def test_gate_mutation_cannot_dispatch_an_unmeasured_subject(self):
        for target in ("introduced.py", "change.py"):
            with self.subTest(target=target):
                root = self.make_repo(target)
                (root / "change.py").write_text("small change")

                def change_during_gate(*args, root=root, target=target):
                    (root / target).write_text("x" * sd_review.MAX_OUTPUT_BYTES)
                    return sd_review.Completed(0, "{}", "")

                runner = FakeRunner({"sd-check": change_during_gate})
                result = sd_review.review(root, namespace(), runner, self.environment(), self.chatgpt_home())
                self.assertEqual(len(runner.calls), 1, "a changed subject must stop before provider dispatch")
                self.assertEqual(result["status"], "refused")
                self.assertEqual(result["input_manifest"]["status"], "oversized")
                self.assertIn(target, [row["path"] for row in result["input_manifest"]["paths"]])

    def test_same_size_material_and_prompt_changes_also_stop_dispatch(self):
        for change in ("material", "prompt"):
            with self.subTest(change=change):
                root = self.make_repo(change)
                (root / "change.py").write_text("before")

                def change_during_gate(*args, root=root, change=change):
                    if change == "material":
                        (root / "change.py").write_text("after!")
                    else:
                        self.local_block(root, "convention: changed")
                    return sd_review.Completed(0, "{}", "")

                runner = FakeRunner({"sd-check": change_during_gate})
                result = sd_review.review(root, namespace(), runner, self.environment(), self.chatgpt_home())
                self.assertEqual(len(runner.calls), 1)
                self.assertEqual(result["status"], "refused")
                self.assertIn("input_changed", [row["code"] for row in result["readiness"]["blockers"]])

    def test_unchanged_gate_inputs_still_dispatch_normally(self):
        root = self.make_repo()
        (root / "change.py").write_text("small change")
        runner = FakeRunner()
        result = sd_review.review(root, namespace(), runner, self.environment(), self.chatgpt_home())
        self.assertEqual(len(runner.calls), 2)
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["input_manifest"]["status"], "within_limit")

    def test_oversize_is_advisory_without_gate_provider_or_meter(self):
        root = self.make_repo()
        (root / "large.py").write_text("x" * sd_review.MAX_OUTPUT_BYTES)
        for explain in (False, True):
            runner, client = FakeRunner(), FakeClient()
            with read_only_connections():
                result = sd_review.review(root, namespace(explain=explain), runner, self.environment(),
                                          self.chatgpt_home(), client=client, meter=lambda *args: self.fail("meter"))
            inventory = result["input_manifest"]
            self.assertEqual(inventory["status"], "oversized")
            self.assertEqual(inventory["limit_bytes"], 2_000_000)
            self.assertEqual(inventory["next_action"], "split_branch_required")
            self.assertFalse(inventory["review_complete"])
            self.assertEqual(inventory["oversized_paths"], ["large.py"])
            self.assertEqual(runner.calls, [])
            self.assertEqual(client.sent, [])
            self.assertEqual(result["completed_reviews"], 0)

    def test_inventory_preserves_rename_binary_symlink_and_unusual_paths(self):
        root = self.make_repo()
        subprocess.run(["git", "mv", "README.md", "renamed.md"], cwd=root, check=True, capture_output=True)
        names = [" leading.py", "tabs\tand\nlines.py", "binary.bin", "link"]
        for name in names[:2]:
            (root / name).write_text("some text\n")
        (root / "binary.bin").write_bytes(b"\xff\x00\x01")
        os.symlink("../outside-secret", root / "link")
        subject = sd_review.resolve_subject(root, "worktree")
        material, entries = sd_review.sd_review_material.collect_review_material(root, subject)
        expected = {"README.md", "renamed.md", *names}
        self.assertEqual(set(subject.paths), expected)
        self.assertEqual({entry["path"] for entry in entries}, expected)
        self.assertEqual(sum(entry["bytes"] for entry in entries), len(material.encode()))
        self.assertIn("[binary, base64]", material)
        self.assertIn("symlink -> ../outside-secret", material)
        plan = sd_review.sd_review_material.input_manifest(entries, "prompt", {"test": "overhead"}, 200)
        grouped = [path for group in plan["suggested_groups"] for path in group["paths"]]
        self.assertEqual(len(grouped), len(set(grouped)))
        self.assertEqual(set(grouped), expected)
        self.assertEqual(plan["measured_bytes"], len(("prompt" + material + "overhead").encode()))

    def test_prompt_overhead_is_counted_even_when_material_fits(self):
        root = self.make_repo()
        (root / "small.py").write_text("x = 1")
        with mock.patch.object(sd_review, "MAX_OUTPUT_BYTES", 1000):
            result = sd_review.review(root, namespace(explain=True), FakeRunner(), self.environment(), self.chatgpt_home())
        self.assertLess(result["input_manifest"]["material_bytes"], 1000)
        self.assertGreater(result["input_manifest"]["measured_bytes"], 1000)
        self.assertEqual(result["readiness"]["status"], "blocked")

    def test_material_collection_uses_constant_git_calls(self):
        root = self.make_repo()
        for index in range(20):
            (root / f"file-{index}.py").write_text("initial\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "tracked files"], cwd=root, check=True, capture_output=True)
        for index in range(20):
            (root / f"file-{index}.py").write_text("changed\n")
        subject = sd_review.resolve_subject(root, "worktree")
        helper = sd_review.sd_review_material
        with mock.patch.object(helper, "read_git_material", wraps=helper.read_git_material) as git_calls:
            material, inventory = helper.collect_review_material(root, subject)
        self.assertEqual(git_calls.call_count, 3)
        self.assertEqual(len(inventory), 20)
        self.assertEqual(sum(row["bytes"] for row in inventory), len(material.encode()))
