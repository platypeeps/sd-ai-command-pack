"""Input limits yield complete, nonexecuting split-branch advice."""

from __future__ import annotations

import hashlib
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

    def test_folder_rename_is_sent_as_rename_records_with_both_paths(self):
        """sd:2400: a moved file costs a rename record, not a full delete and a full add."""
        for scope in ("worktree", "branch"):
            with self.subTest(scope=scope):
                root = self.make_repo(scope)
                (root / "old").mkdir()
                moved = [f"file-{index}.html" for index in range(40)]
                for index, name in enumerate(moved):
                    (root / "old" / name).write_text(f"<p>page {index}</p>\n" * 5000)
                subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "commit", "--quiet", "-m", "pages"], cwd=root, check=True, capture_output=True)
                if scope == "branch":
                    subprocess.run(["git", "checkout", "--quiet", "-b", "move"], cwd=root, check=True, capture_output=True)
                subprocess.run(["git", "mv", "old", "new"], cwd=root, check=True, capture_output=True)
                (root / "new" / "file-0.html").write_text("<p>edited</p>\n" + "<p>page 0</p>\n" * 4999)
                if scope == "branch":
                    subprocess.run(["git", "commit", "--quiet", "-am", "move"], cwd=root, check=True, capture_output=True)
                subject = sd_review.resolve_subject(root, scope)
                material, entries = sd_review.sd_review_material.collect_review_material(root, subject)
                expected = {f"{side}/{name}" for side in ("old", "new") for name in moved}
                self.assertEqual(set(subject.paths), expected)
                self.assertEqual({entry["path"] for entry in entries}, expected)
                self.assertEqual(sum(entry["bytes"] for entry in entries), len(material.encode()))
                moved_bytes = sum(len(f"<p>page {index}</p>\n".encode()) * 5000 for index in range(40))
                self.assertLess(len(material.encode()), moved_bytes // 20)
                for name in moved:
                    self.assertIn(f"rename from old/{name}\n", material)
                    self.assertIn(f"rename to new/{name}\n", material)
                    self.assertIn(f'[renamed] "old/{name}" -> "new/{name}"', material)
                self.assertIn("+<p>edited</p>\n", material)
                # The unchanged lines are not sent, so both sides are summarized and coverage is partial (sd:2181).
                self.assertEqual({entry["path"] for entry in entries if entry.get("summarized")}, expected)
                self.assertEqual(set(sd_review.sd_review_material.coverage(entries, {"r": "x"})["omitted_paths"]), expected)

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


class BinaryMaterialTests(ReviewFixture):
    """sd:2181: a binary path contributes a short summary, never its bytes."""

    SHOT = b"\x89PNG\r\n\x1a\n" + os.urandom(2_100_000)

    def git(self, root, *args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout

    def screenshot_branch(self):
        root = self.make_repo()
        (root / "src.py").write_text("".join(f"line = {index}\n" for index in range(200)))
        self.git(root, "add", "-A")
        self.git(root, "commit", "--quiet", "-m", "text")
        base = self.git(root, "rev-parse", "HEAD").strip()
        self.git(root, "checkout", "--quiet", "-b", "retake")
        (root / "shot.png").write_bytes(self.SHOT)
        (root / "src.py").write_text("".join(f"value = {index}\n" for index in range(200)))
        self.git(root, "add", "-A")
        self.git(root, "commit", "--quiet", "-m", "retake")
        return root, base

    def test_branch_adding_a_large_png_fits_the_review_limit(self):
        root, base = self.screenshot_branch()
        subject = sd_review.resolve_subject(root, "branch", base=base)
        material, inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        manifest = sd_review.sd_review_material.input_manifest(inventory, "prompt", {"fixture": "overhead"},
                                                               sd_review.MAX_OUTPUT_BYTES)
        self.assertEqual(manifest["status"], "within_limit", manifest["measured_bytes"])
        self.assertEqual([row["path"] for row in inventory], ["shot.png", "src.py"])
        self.assertEqual(sum(row["bytes"] for row in inventory), len(material.encode()))
        blob = self.git(root, "rev-parse", "HEAD:shot.png").strip()
        shot = material[material.index('diff --git a/shot.png'):material.index('diff --git a/src.py')]
        self.assertNotIn("GIT binary patch", shot)
        self.assertIn("[binary, not sent] added; old absent; new 2100008 bytes, blob " + blob, shot)
        self.assertLess(len(shot.encode()), 400)

    def test_text_change_beside_a_binary_is_sent_in_full(self):
        root, base = self.screenshot_branch()
        subject = sd_review.resolve_subject(root, "branch", base=base)
        material, _inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        expected = self.git(root, "diff", "--no-color", base, "HEAD", "--", "src.py")
        self.assertTrue(material.endswith(expected))
        self.assertEqual(expected.count("\n+value = "), 200)

    def test_worktree_binaries_report_old_blob_and_new_content_hash(self):
        root, _base = self.screenshot_branch()
        changed = b"\x89PNG\r\n\x1a\n\x00changed"
        old_blob = self.git(root, "rev-parse", "HEAD:shot.png").strip()
        (root / "shot.png").write_bytes(changed)
        (root / "new.png").write_bytes(self.SHOT)
        subject = sd_review.resolve_subject(root, "worktree")
        material, inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        self.assertEqual({row["path"] for row in inventory}, {"shot.png", "new.png"})
        self.assertEqual(sum(row["bytes"] for row in inventory), len(material.encode()))
        self.assertIn(f"[binary, not sent] modified; old 2100008 bytes, blob {old_blob}; "
                      f"new {len(changed)} bytes, sha256 {hashlib.sha256(changed).hexdigest()}", material)
        self.assertIn(f"[binary, not sent] added (untracked); 2100008 bytes, sha256 {hashlib.sha256(self.SHOT).hexdigest()}",
                      material)
        self.assertLess(len(material.encode()), 1000)

    def test_git_binary_text_is_sent_readable_and_unknown_bytes_are_not_summarized(self):
        # sd:2181 review: git also calls UTF-16 and `-diff` files binary; only media is summarized.
        root, base = self.screenshot_branch()
        self.git(root, "checkout", "--quiet", "-b", "configs")
        (root / ".gitattributes").write_text("notes.txt -diff\n")
        (root / "notes.txt").write_text("readable note behind -diff\n")
        (root / "config.ini").write_bytes("[core]\nsetting = utf16-value\n".encode("utf-16"))
        (root / "blob.dat").write_bytes(b"\x00\x01" + os.urandom(300))
        self.git(root, "add", "-A")
        self.git(root, "commit", "--quiet", "-m", "configs")
        subject = sd_review.resolve_subject(root, "branch", base=base)
        material, inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        self.assertEqual(sum(row["bytes"] for row in inventory), len(material.encode()))
        pieces = {name: material[material.index(f"diff --git a/{name}"):] for name in ("notes.txt", "config.ini", "blob.dat")}
        for name, expected in (("notes.txt", "+readable note behind -diff\n"), ("config.ini", "+setting = utf16-value\n"),
                               ("blob.dat", "GIT binary patch")):
            with self.subTest(name=name):
                self.assertIn(expected, pieces[name][:400])
        self.assertNotIn("[binary, not sent]", pieces["blob.dat"].split("diff --git a/config.ini")[0])
        self.assertIn("[binary, not sent] added; old absent; new 2100008 bytes, blob", material)

    def test_whole_file_material_follows_the_same_rule(self):
        root = self.make_repo()
        (root / "wide.ini").write_bytes("setting = utf16-untracked\n".encode("utf-16"))
        (root / "raw.dat").write_bytes(b"\x00\xff" + os.urandom(64))
        (root / "new.png").write_bytes(self.SHOT)
        subject = sd_review.resolve_subject(root, "worktree")
        material, _inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        self.assertIn("setting = utf16-untracked", material)
        self.assertIn('--- "raw.dat" ---\n[binary, base64]\n', material)
        self.assertIn("[binary, not sent] added (untracked); 2100008 bytes", material)

    def test_ico_magic_is_not_a_media_pass(self):
        # sd:2181 review: 00 00 01 00 is too weak a signature to let a file escape review.
        root, base = self.screenshot_branch()
        disguised = b"\x00\x00\x01\x00" + os.urandom(64)
        (root / "favicon.ico").write_bytes(disguised)
        self.git(root, "add", "-A")
        self.git(root, "commit", "--quiet", "-m", "icon")
        (root / "loose.ico").write_bytes(disguised)
        subject = sd_review.resolve_subject(root, "branch", base=base)
        material, _inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        piece = material[material.index("diff --git a/favicon.ico"):material.index("diff --git a/shot.png")]
        self.assertIn("GIT binary patch", piece)
        self.assertNotIn("[binary, not sent]", piece)
        self.assertIn('--- "loose.ico" ---\n[binary, base64]\n',
                      sd_review.sd_review_material.file_material(root, "loose.ico", "added (untracked)"))

    def test_a_summarized_path_leaves_a_material_only_review_partial(self):
        # sd:2181 review pass 2: a hash line is not a review. A `-diff` script that starts
        # like a GIF is summarized, so a reviewer that reads only material has partial coverage.
        root = self.make_repo()
        (root / ".gitattributes").write_text("build.sh -diff\n")
        self.git(root, "add", "-A")
        self.git(root, "commit", "--quiet", "-m", "attributes")
        (root / "build.sh").write_text("GIF89a\nrm -rf \"$HOME\"\n")
        registry = self.registry_home / ".local/share/sd/providers.yaml"
        registry.write_text(registry.read_text().replace("reader: codex-json", "reader: claude-json"))
        answer = sd_review.Completed(0, json.dumps({"type": "result", "subtype": "success",
                                                   "structured_output": {"findings": []}}), "")
        result = sd_review.review(root, namespace(), FakeRunner({"codex": answer, "second": answer}),
                                  self.environment(), self.chatgpt_home())
        self.assertEqual(result["completed_reviews"], 0, [(row["backend"], row["status"]) for row in result["outcomes"]])
        self.assertEqual(result["input_manifest"]["omitted_paths"], ["build.sh"])
        self.assertNotEqual(result["status"], "clean")
        partial = [row for row in result["outcomes"] if (row["diagnostic"] or {}).get("coverage") == "partial"]
        self.assertTrue(partial, result["outcomes"])
        self.assertTrue(all(row["diagnostic"]["omitted_paths"] == ["build.sh"] and "build.sh" in row["detail"]
                            for row in partial))

    def test_an_encoding_change_is_visible(self):
        root = self.make_repo()
        (root / "same.txt").write_text("unchanged words\n")
        (root / "moved.txt").write_text("old words\n")
        self.git(root, "add", "-A")
        self.git(root, "commit", "--quiet", "-m", "utf-8")
        (root / "same.txt").write_bytes("unchanged words\n".encode("utf-16"))
        (root / "moved.txt").write_bytes("new words\n".encode("utf-16"))
        subject = sd_review.resolve_subject(root, "worktree")
        material, _inventory = sd_review.sd_review_material.collect_review_material(root, subject)
        same = material[material.index("diff --git a/same.txt"):]
        moved = material[material.index("diff --git a/moved.txt"):material.index("diff --git a/same.txt")]
        self.assertIn("GIT binary patch", same)
        self.assertIn("[encoding] old utf-8; new utf-16-le, BOM\n", moved)
        self.assertIn("+new words\n", moved)

    def test_a_native_reader_completes_a_screenshot_review(self):
        root = self.make_repo()
        (root / "shot.png").write_bytes(self.SHOT)
        result = sd_review.review(root, namespace(), FakeRunner(), self.environment(), self.chatgpt_home())
        self.assertEqual(result["input_manifest"]["omitted_paths"], ["shot.png"])
        self.assertEqual(result["input_manifest"]["partial_providers"], [])
        self.assertEqual((result["status"], result["completed_reviews"]), ("clean", 1))
