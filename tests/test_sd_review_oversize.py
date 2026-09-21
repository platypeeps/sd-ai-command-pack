"""Input limits yield complete, nonexecuting split-branch advice."""

from __future__ import annotations

import json
import os
import subprocess
from unittest import mock

from tests.test_sd_review import (
    FakeClient,
    FakeRunner,
    ReviewFixture,
    codex_sessions,
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
                self.assertEqual(result["input_manifest"]["status"], "within_limit")
                self.assertIn("input_changed", [row["code"] for row in result["readiness"]["blockers"]])
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
        # The gate, the skill probe, the review. The probe is a codex call and
        # is counted here so a fourth call cannot arrive unnoticed.
        self.assertEqual(len(runner.calls), 3, [call["argv"][:3] for call in runner.calls])
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["input_manifest"]["status"], "within_limit")

    def test_oversize_is_advisory_without_gate_provider_or_meter(self):
        root = self.make_repo()
        registry = self.registry_home / ".local/share/sd/providers.yaml"
        registry.write_text(registry.read_text().replace("reader: codex-json", "reader: claude-json"))
        (root / "large.py").write_text("x" * sd_review.MAX_OUTPUT_BYTES)
        for explain in (False, True):
            runner, client = FakeRunner(), FakeClient()
            with read_only_connections():
                result = sd_review.review(root, namespace(explain=explain), runner, self.environment(),
                                          self.chatgpt_home(), client=client, meter=lambda *args: self.fail("meter"))
            inventory = result["input_manifest"]
            self.assertEqual(inventory["status"], "oversized")
            self.assertEqual(inventory["limit_bytes"], 2_000_000)
            self.assertEqual(inventory["next_action"], "split_input_for_oversized_providers")
            self.assertFalse(inventory["review_complete"])
            self.assertFalse(inventory["advisory_only"])
            self.assertTrue(inventory["split_plan_advisory_only"])
            self.assertEqual(inventory["oversized_paths"], ["large.py"])
            self.assertEqual(runner.calls, [])
            self.assertEqual(client.sent, [])
            self.assertEqual(result["completed_reviews"], 0)

    def test_native_codex_counts_only_actual_prompt_with_oversized_fallback(self):
        root = self.make_repo()
        (root / "large.py").write_text("x" * (sd_review.MAX_OUTPUT_BYTES + 100))
        registry = self.registry_home / ".local/share/sd/providers.yaml"
        registry.write_text(registry.read_text().replace("roles: [author, reviewer], reader: codex-json",
                                                       "roles: [author, reviewer], reader: claude-json"))
        for provider in ("codex", None):
            for failed in (False, True):
                runner = FakeRunner({"codex": sd_review.Completed(1, "", "synthetic failure")} if failed else {})
                with self.subTest(provider=provider, failed=failed):
                    result = sd_review.review(root, namespace(provider=provider), runner, self.environment(), self.chatgpt_home())
                    calls = codex_sessions(runner)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(len(runner.calls), 3, "oversized fallback must never dispatch")
                    self.assertEqual(result["readiness"]["status"], "ready")
                    self.assertEqual(result["input_manifest"]["transport_bytes"]["codex"], len(calls[0]["stdin"].encode()))
                    self.assertLess(len(calls[0]["stdin"].encode()), sd_review.MAX_OUTPUT_BYTES)
                    self.assertEqual(result["status"], ("unavailable" if provider else "refused") if failed else "clean")
                    if provider is None:
                        self.assertEqual([row["provider"] for row in result["readiness"]["warnings"]], ["second"])

    def test_each_dispatch_enforces_complete_transmitted_prompt(self):
        root = self.make_repo()
        subject = sd_review.resolve_subject(root, "worktree")
        for transport in ({"reader": "codex-json", "start": "codex exec"},
                          {"reader": "claude-json", "start": "claude"},
                          {"url": "https://api.example.invalid/v1", "model": "fixture"}):
            runner, client = FakeRunner(), FakeClient()
            provider = sd_review.sd_registry.Provider(name="fixture", vendor="fixture", bill="fixture", **transport)
            with self.subTest(transport=transport):
                outcome = sd_review.run_provider(provider, root, subject, "x" * (sd_review.MAX_OUTPUT_BYTES + 1),
                    runner, self.environment(), 10, self.chatgpt_home(), client)
                self.assertEqual(outcome.status, sd_review.REFUSED)
                self.assertEqual(runner.calls, [])
                self.assertEqual(client.sent, [])

    def test_attached_transports_measure_and_bound_the_complete_payload(self):
        root = self.make_repo()
        (root / "src.py").write_text("attached material " * 100)
        subject = sd_review.resolve_subject(root, "worktree")
        material, inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        prompt = "fixture prompt " * 100
        for remote in (False, True):
            transport = {"url": "https://api.example.invalid/v1"} if remote else {"reader": "claude-json", "start": "claude"}
            provider = sd_review.sd_registry.Provider(name="fixture", vendor="fixture", bill="fixture", **transport)
            captured = []

            def reply(argv, env, cwd, timeout, captured=captured):
                captured.append((sd_review.pathlib.Path(argv[argv.index("--add-dir") + 1]) / "review-subject.md").read_text())
                return sd_review.Completed(0, json.dumps({"type": "result", "subtype": "success", "structured_output": {"findings": []}}), "")

            client = FakeClient()
            with self.subTest(remote=remote):
                outcome = sd_review.run_provider(provider, root, subject, prompt, reply, self.environment(), 10, client=client)
                self.assertEqual(outcome.status, sd_review.CLEAN)
                sent = client.sent[0]["prompt"] if remote else captured[0]
                overhead = (f"\nSchema: {json.dumps(sd_review.CODEX_OUTPUT_SCHEMA)}\n\nReview input:\n{sd_review.URL_OUTPUT_CONTRACT}"
                            if remote else "\n\nReview input:\n")
                manifest = sd_review.sd_review_material.input_manifest(inventory, prompt, {"fixture": overhead}, sd_review.MAX_OUTPUT_BYTES)
                self.assertEqual(manifest["transport_bytes"]["fixture"], len(sent.encode()))
                limit = len(sent.encode()) - 1
                self.assertLess(len(prompt.encode()), limit)
                self.assertLess(len(material.encode()), limit)
                runner, client = FakeRunner(), FakeClient()
                with mock.patch.object(sd_review, "MAX_OUTPUT_BYTES", limit):
                    refused = sd_review.run_provider(provider, root, subject, prompt, runner, self.environment(), 10, client=client)
                self.assertEqual(refused.status, sd_review.REFUSED)
                self.assertEqual(runner.calls, [])
                self.assertEqual(client.sent, [])

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
