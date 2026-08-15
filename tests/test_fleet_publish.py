from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import install

SCRIPT_PATH = install.ROOT / "scripts/sd-ai-command-pack-fleet-publish.py"
SPEC = importlib.util.spec_from_file_location("sd_ai_command_pack_fleet_publish", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT_PATH}")
publish = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publish
SPEC.loader.exec_module(publish)


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class FleetPublishFailureSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="sd-fleet-publish-")
        self.addCleanup(self.tempdir.cleanup)
        self.repo = Path(self.tempdir.name).resolve()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@t.test")
        git(self.repo, "config", "user.name", "Test")
        # An active task and one committed source file.
        self.slug = "01-01-demo"
        task = self.repo / publish.TASK_ROOT / self.slug
        task.mkdir(parents=True)
        (task / "prd.md").write_text("# demo\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "app.py").write_text("print(1)\n", encoding="utf-8")
        # scripts/ and docs/ must be tracked: git status collapses a wholly-
        # untracked directory to one "scripts/" entry, which no per-file
        # allowlist can match. A real consumer has both under version control.
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "keep.py").write_text("print(0)\n", encoding="utf-8")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "keep.md").write_text("# keep\n", encoding="utf-8")
        # Every flow through publish() derives its allowlist from this file.
        (self.repo / ".sd-ai-command-pack").mkdir()
        (self.repo / ".sd-ai-command-pack" / "manifest.json").write_text(
            json.dumps({"files": [{"target": ".claude/skills/x/SKILL.md"}]}),
            encoding="utf-8",
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "seed")

    def _make_repomix(self, body: str) -> None:
        """Install an update_repomix stub and the map so the tree is indexed."""

        scripts = self.repo / "scripts"
        scripts.mkdir(exist_ok=True)
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs" / "repomix-map.md").write_text("# map\n", encoding="utf-8")
        stub = scripts / "update_repomix"
        stub.write_text("#!/usr/bin/env bash\nset -e\n" + body, encoding="utf-8")
        stub.chmod(0o755)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "add repomix")

    def _write_manifest(self, targets: object, *, raw: str | None = None) -> None:
        """Write the consumer manifest the allowlist is derived from.

        Each test states the payload shape it depends on instead of inheriting
        whatever this repository happens to ship.
        """

        directory = self.repo / ".sd-ai-command-pack"
        directory.mkdir(exist_ok=True)
        path = directory / "manifest.json"
        if raw is not None:
            path.write_text(raw, encoding="utf-8")
            return
        entries = [
            target if isinstance(target, dict) else {"target": target}
            for target in targets  # type: ignore[union-attr]
        ]
        path.write_text(json.dumps({"files": entries}), encoding="utf-8")

    def _gate(self, targets: object = (".claude/skills/x/SKILL.md",)) -> None:
        """Resolve the allowlist from a fixture manifest and run the gate."""

        self._write_manifest(targets)
        prefixes, exact = publish.derive_allowed_paths(self.repo)
        publish.check_preconditions(self.repo, self.slug, prefixes, exact)

    # ------------------------------------------------------------------ preconditions

    def test_refuses_when_tree_is_dirty_outside_allowlist(self) -> None:
        (self.repo / "src" / "app.py").write_text("print(2)\n", encoding="utf-8")
        with self.assertRaises(publish.PublishError) as ctx:
            self._gate()
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("src/app.py", str(ctx.exception))
        # No commit was created.
        self.assertEqual(
            subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=str(self.repo),
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "1",
        )

    def test_allows_dirty_paths_inside_the_allowlist(self) -> None:
        # A dirty task artifact and a dirty managed surface are tolerated.
        (self.repo / publish.TASK_ROOT / self.slug / "prd.md").write_text(
            "# demo edited\n", encoding="utf-8"
        )
        (self.repo / ".claude").mkdir(exist_ok=True)
        (self.repo / ".claude" / "x").write_text("y\n", encoding="utf-8")
        self._gate()

    # ------------------------------------------------- manifest-derived allowlist

    def test_new_payload_target_passes_without_a_code_edit(self) -> None:
        # The defect this task fixes: a payload target the old literal tuple
        # never named (scripts/) had to be hand-added before any lane on the
        # affected consumer could publish.
        target = "scripts/sd-ai-command-pack-check.py"
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / target).write_text("print(1)\n", encoding="utf-8")
        self.assertNotIn("scripts/", publish.DEFAULT_ALLOWED_PREFIXES)
        self._gate([target])

    def test_path_outside_derived_set_and_residue_still_refuses(self) -> None:
        (self.repo / "src" / "app.py").write_text("print(3)\n", encoding="utf-8")
        with self.assertRaises(publish.PublishError) as ctx:
            self._gate(["scripts/sd-ai-command-pack-check.py"])
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("src/app.py", str(ctx.exception))

    def test_missing_manifest_refuses_with_a_named_reason(self) -> None:
        (self.repo / publish.PACK_MANIFEST_RELATIVE).unlink()
        with self.assertRaises(publish.PublishError) as ctx:
            publish.derive_allowed_paths(self.repo)
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("manifest_missing", str(ctx.exception))

    def test_unreadable_manifest_refuses_with_a_named_reason(self) -> None:
        self._write_manifest(None, raw="{not json")
        with self.assertRaises(publish.PublishError) as ctx:
            publish.derive_allowed_paths(self.repo)
        self.assertIn("manifest_unreadable", str(ctx.exception))

    def test_malformed_manifest_refuses_with_a_named_reason(self) -> None:
        self._write_manifest(None, raw=json.dumps({"files": "not-a-list"}))
        with self.assertRaises(publish.PublishError) as ctx:
            publish.derive_allowed_paths(self.repo)
        self.assertIn("manifest_malformed", str(ctx.exception))

    def test_all_entries_skipped_refuses_and_reports_the_skip_count(self) -> None:
        self._write_manifest(
            [
                {"target": "/etc/passwd"},
                {"target": "../outside/x"},
                {"nope": 1},
                "",
            ]
        )
        with self.assertRaises(publish.PublishError) as ctx:
            publish.derive_allowed_paths(self.repo)
        message = str(ctx.exception)
        self.assertIn("manifest_targets_empty", message)
        self.assertIn("4 entries skipped", message)

    def test_dotted_root_collapses_to_a_directory_prefix(self) -> None:
        # The installer writes byproducts the manifest does not name; a dotted
        # platform root is trusted at directory level.
        (self.repo / ".claude" / "skills" / "x").mkdir(parents=True)
        (self.repo / ".claude" / "skills" / "x" / "other.md").write_text(
            "y\n", encoding="utf-8"
        )
        self._gate([".claude/skills/x/SKILL.md"])

    def test_non_dotted_target_does_not_allow_a_sibling(self) -> None:
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts" / "b.py").write_text("print(1)\n", encoding="utf-8")
        with self.assertRaises(publish.PublishError) as ctx:
            self._gate(["scripts/a.py"])
        self.assertIn("scripts/b.py", str(ctx.exception))

    def test_non_dotted_target_is_exact_not_a_string_prefix(self) -> None:
        # The hole a naive implementation leaves: prefix-matching "scripts/a.py"
        # also sanctions an editor backup beside it, which would ride into the
        # publication commit. The sibling test above passes either way.
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts" / "a.py.orig").write_text("print(1)\n", encoding="utf-8")
        with self.assertRaises(publish.PublishError) as ctx:
            self._gate(["scripts/a.py"])
        self.assertIn("scripts/a.py.orig", str(ctx.exception))

    def test_allow_path_prefix_keeps_prefix_semantics(self) -> None:
        # Derived non-dotted targets became exact; the operator override did not.
        (self.repo / "docs").mkdir(exist_ok=True)
        (self.repo / "docs" / "repomix-map.md").write_text("# map\n", encoding="utf-8")
        self._write_manifest([".claude/skills/x/SKILL.md"])
        prefixes, exact = publish.derive_allowed_paths(self.repo)
        publish.check_preconditions(
            self.repo, self.slug, prefixes + ("docs/rep",), exact
        )

    def test_residue_survives_derivation(self) -> None:
        (self.repo / publish.TASK_ROOT / self.slug / "prd.md").write_text(
            "# edited\n", encoding="utf-8"
        )
        (self.repo / ".gitignore").write_text("/.obsidian-kb\n", encoding="utf-8")
        self._gate([".claude/skills/x/SKILL.md"])

    def test_refuses_missing_task_directory(self) -> None:
        with self.assertRaises(publish.PublishError) as ctx:
            publish.resolve_task_dir(self.repo, "99-99-nope")
        self.assertEqual(ctx.exception.code, 3)

    def test_refuses_task_slug_escaping_task_root(self) -> None:
        with self.assertRaises(publish.PublishError) as ctx:
            publish.resolve_task_dir(self.repo, "../../etc")
        self.assertEqual(ctx.exception.code, 3)

    # ---------------------------------------------------------- self-publish guard

    def _make_pack_bookkeeping_gate(self) -> None:
        """Install the completion-mode bookkeeping gate fingerprint + commit it."""

        gate = self.repo / ".github" / "scripts"
        gate.mkdir(parents=True, exist_ok=True)
        (gate / "bookkeeping_ci_scope.py").write_text("# gate\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "add bookkeeping gate")

    def test_refuses_pack_repo_with_bookkeeping_gate(self) -> None:
        self._make_pack_bookkeeping_gate()
        with self.assertRaises(publish.PublishError) as ctx:
            self._gate()
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("sd-finish-work", str(ctx.exception))
        self.assertIn("consumer-only", str(ctx.exception))

    def test_consumer_repo_passes_self_publish_guard(self) -> None:
        # Default fixture carries no bookkeeping gate → the guard is a no-op and
        # a clean consumer tree passes preconditions.
        self._gate()

    def test_main_propagates_self_publish_guard_code(self) -> None:
        self._make_pack_bookkeeping_gate()
        rc = publish.main(
            [
                str(self.repo),
                self.slug,
                "--branch", "pub",
                "--title", "t",
                "--summary", "s",
                "--change", "c",
                "--test", "t",
                "--work-message-file", str(self.repo / "msg.txt"),
                "--receipt-out", str(self.repo / "receipt.json"),
                "--no-push",
            ]
        )
        self.assertEqual(rc, 3)

    # ------------------------------------------------------ archive loud abort (B-fleet)

    def test_archive_failure_raises_with_recovery_and_no_rollback(self) -> None:
        # Stub task.py archive: move the task on disk (staged) then FAIL before the
        # commit — exactly the stranded state a transient index.lock yields on a
        # consumer. fleet-publish must raise with recovery guidance and NOT roll back.
        trellis_scripts = self.repo / ".trellis" / "scripts"
        trellis_scripts.mkdir(parents=True, exist_ok=True)
        (trellis_scripts / "task.py").write_text(
            "import pathlib, subprocess, sys\n"
            "slug = sys.argv[2]\n"
            "src = pathlib.Path('.trellis/tasks') / slug\n"
            "dst = pathlib.Path('.trellis/tasks/archive') / slug\n"
            "dst.parent.mkdir(parents=True, exist_ok=True)\n"
            "subprocess.run(['git', 'mv', str(src), str(dst)], check=True)\n"
            "print('fatal: Unable to create .git/index.lock: File exists')\n"
            "sys.exit(1)\n",
            encoding="utf-8",
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "install failing archive stub")

        live = self.repo / publish.TASK_ROOT / self.slug
        archived = self.repo / publish.TASK_ROOT / "archive" / self.slug

        with self.assertRaises(publish.PublishError) as ctx:
            publish.archive_and_journal(
                self.repo,
                self.slug,
                python_bin=sys.executable,
                record_session=self.repo / "scripts" / "unused.py",
                title="t",
                summary="s",
                commit="deadbeef",
                changes=["c"],
                tests=["t"],
            )
        msg = str(ctx.exception)
        self.assertIn("git status", msg)              # recovery guidance
        self.assertIn("no rollback", msg.lower())     # states it will not roll back
        # NO rollback mutation: the tree is left exactly as the stub left it —
        # task moved to archive/, live dir gone, nothing restored by fleet-publish.
        self.assertTrue(archived.exists())
        self.assertFalse(live.exists())

    # ------------------------------------------------------------ transactional restore

    def test_task_restored_when_repomix_fails_mid_move(self) -> None:
        self._make_repomix("exit 7\n")  # update_repomix crashes while task is aside
        task = self.repo / publish.TASK_ROOT / self.slug
        with self.assertRaises(publish.PublishError):
            publish.regenerate_repomix_post_archive(
                self.repo, self.slug, "scripts/update_repomix", "docs/repomix-map.md", "2026-01"
            )
        # The task is back at its original path and never stranded in archive/.
        self.assertTrue((task / "prd.md").is_file())
        self.assertFalse((self.repo / publish.TASK_ROOT / "archive").exists())

    def test_task_restored_when_repomix_writes_outside_allowlist(self) -> None:
        self._make_repomix(
            'printf "# map\\n" > docs/repomix-map.md\n'
            'printf "stray\\n" > docs/other.md\n'
        )
        task = self.repo / publish.TASK_ROOT / self.slug
        with self.assertRaises(publish.PublishError) as ctx:
            publish.regenerate_repomix_post_archive(
                self.repo, self.slug, "scripts/update_repomix", "docs/repomix-map.md", "2026-01"
            )
        self.assertEqual(ctx.exception.code, 6)
        self.assertIn("docs/other.md", str(ctx.exception))
        # Even on the allowlist violation, the task is restored.
        self.assertTrue((task / "prd.md").is_file())
        self.assertFalse((self.repo / publish.TASK_ROOT / "archive").exists())

    def test_repomix_regen_succeeds_and_restores_task_when_only_map_changes(self) -> None:
        self._make_repomix('printf "# regenerated\\n" > docs/repomix-map.md\n')
        task = self.repo / publish.TASK_ROOT / self.slug
        publish.regenerate_repomix_post_archive(
            self.repo, self.slug, "scripts/update_repomix", "docs/repomix-map.md", "2026-01"
        )
        self.assertTrue((task / "prd.md").is_file())
        self.assertFalse((self.repo / publish.TASK_ROOT / "archive").exists())
        self.assertIn(
            "regenerated",
            (self.repo / "docs" / "repomix-map.md").read_text(encoding="utf-8"),
        )

    # ------------------------------------------------------------------ delta guard

    def test_trellis_only_delta_guard_rejects_non_trellis_change(self) -> None:
        base = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)
        (self.repo / "src" / "app.py").write_text("print(3)\n", encoding="utf-8")
        git(self.repo, "commit", "-aqm", "code change")
        head = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)
        with self.assertRaises(publish.PublishError) as ctx:
            publish.assert_trellis_only_delta(self.repo, base, head)
        self.assertEqual(ctx.exception.code, 5)
        self.assertIn("src/app.py", str(ctx.exception))

    def test_trellis_only_delta_guard_accepts_trellis_change(self) -> None:
        base = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)
        (self.repo / publish.TASK_ROOT / self.slug / "prd.md").write_text(
            "# demo v2\n", encoding="utf-8"
        )
        git(self.repo, "commit", "-aqm", "task change")
        head = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)
        publish.assert_trellis_only_delta(self.repo, base, head)

    # ---------------------------------------------------------- end-to-end publish

    def _install_publish_fakes(self) -> None:
        """Commit fakes for the three shell-outs publish() makes.

        Real ``task.py archive``, ``record-session``, and the node completion
        bundle need a full Trellis + review-preflight environment; the helper's
        orchestration is otherwise validated on a live disposable clone. These
        stand-ins keep every commit ``.trellis``-only and emit a ``valid``
        receipt so the in-process happy path is exercised hermetically.
        """

        trellis_scripts = self.repo / ".trellis" / "scripts"
        trellis_scripts.mkdir(parents=True, exist_ok=True)
        (trellis_scripts / "task.py").write_text(
            "import pathlib, subprocess, sys\n"
            "slug = sys.argv[2]\n"
            "src = pathlib.Path('.trellis/tasks') / slug\n"
            "dst = pathlib.Path('.trellis/tasks/archive') / slug\n"
            "dst.parent.mkdir(parents=True, exist_ok=True)\n"
            "subprocess.run(['git', 'mv', str(src), str(dst)], check=True)\n"
            "subprocess.run(['git', 'commit', '-q', '-m', 'chore(task): archive ' + slug], check=True)\n",
            encoding="utf-8",
        )
        record_session = self.repo / "scripts" / "fake-record-session.py"
        record_session.parent.mkdir(exist_ok=True)
        record_session.write_text(
            "import pathlib, subprocess\n"
            "workspace = pathlib.Path('.trellis/workspace')\n"
            "workspace.mkdir(parents=True, exist_ok=True)\n"
            "(workspace / 'journal.md').write_text('session\\n', encoding='utf-8')\n"
            "subprocess.run(['git', 'add', '-A'], check=True)\n"
            "subprocess.run(['git', 'commit', '-q', '-m', 'chore: record journal'], check=True)\n",
            encoding="utf-8",
        )
        # completion_receipt shells to `node scripts/sd-ai-command-pack-review-preflight.mjs`.
        preflight = self.repo / "scripts" / "sd-ai-command-pack-review-preflight.mjs"
        preflight.write_text(
            "process.stdout.write(JSON.stringify({status: 'valid'}));\n",
            encoding="utf-8",
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "install publish fakes")

    @unittest.skipUnless(shutil.which("node"), "node required for completion receipt")
    def test_publish_folds_finish_work_into_the_head_and_writes_a_valid_receipt(
        self,
    ) -> None:
        self._make_repomix('printf "# regenerated\\n" > docs/repomix-map.md\n')
        self._install_publish_fakes()
        base = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)

        # Pending finish-work: an allowlisted .trellis change the work commit folds in.
        workspace = self.repo / ".trellis" / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "note.md").write_text("finish work\n", encoding="utf-8")

        aux = tempfile.TemporaryDirectory(prefix="sd-fleet-publish-aux-")
        self.addCleanup(aux.cleanup)
        work_message = Path(aux.name) / "work.txt"
        work_message.write_text("chore: fold finish-work into head\n", encoding="utf-8")
        receipt = Path(aux.name) / "receipt.json"

        rc = publish.main(
            [
                str(self.repo),
                self.slug,
                "--branch",
                "main",
                "--title",
                "Demo publish",
                "--summary",
                "Fold finish-work.",
                "--change",
                "folded finish-work",
                "--test",
                "unit: fleet-publish happy path",
                "--work-message-file",
                str(work_message),
                "--receipt-out",
                str(receipt),
                "--record-session",
                str(self.repo / "scripts" / "fake-record-session.py"),
                "--python",
                sys.executable,
                "--archive-month",
                "2026-01",
                "--no-push",
            ]
        )

        self.assertEqual(rc, 0)
        # Receipt is valid and persisted.
        self.assertIn('"valid"', receipt.read_text(encoding="utf-8"))
        # The task was archived and the journal recorded, both in the published head.
        head = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)
        self.assertNotEqual(head, base)
        self.assertTrue(
            (self.repo / ".trellis/tasks/archive" / self.slug).is_dir(),
            "task should be archived into the published head",
        )
        self.assertTrue(
            (self.repo / ".trellis/workspace/journal.md").is_file(),
            "journal should be recorded into the published head",
        )
        # publish() internally asserts the H1..H3 delta is .trellis-only; a valid
        # rc of 0 means that held. Under --no-push no branch was pushed.
        branches = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
        ).stdout.split()
        self.assertEqual(branches, ["main"], "no push/new branch under --no-push")

    def test_archive_ctx_tidies_scaffolding_when_rename_fails(self) -> None:
        # The archive rename lives inside the try/finally, so a rename that itself
        # raises (here: a slug with no task dir) still runs the finally: the freshly
        # created archive scaffolding is removed and the tree is left untouched.
        archive_root = self.repo / publish.TASK_ROOT / "archive"
        self.assertFalse(archive_root.exists())
        with self.assertRaises(OSError):
            with publish.task_moved_to_archive(self.repo, "99-99-nonexistent", "2026-01"):
                self.fail("context body must not run when the rename fails")
        self.assertFalse(
            archive_root.exists(), "archive scaffolding leaked after a failed rename"
        )
        self.assertTrue(
            (self.repo / publish.TASK_ROOT / self.slug).is_dir(),
            "the real active task must be untouched by an unrelated failed archive",
        )

    # ------------------------------------------------- managed ignore block ordering

    def _make_kb_helper(self, body: str) -> Path:
        """Install a stub spec-KB updater at the path the consumer would ship."""

        scripts = self.repo / "scripts"
        scripts.mkdir(exist_ok=True)
        helper = scripts / "sd-ai-command-pack-update-spec-kb.py"
        helper.write_text("import sys\n" + body, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "add kb helper")
        return helper

    def test_gitignore_is_in_the_default_allowlist(self) -> None:
        # An operator who already ran housekeeping arrives with .gitignore dirty.
        # .gitignore is residue: housekeeping owns it, no payload target names
        # it, so it must survive derivation from the manifest.
        self.assertIn(".gitignore", publish.DEFAULT_ALLOWED_EXACT)
        (self.repo / ".gitignore").write_text("/.obsidian-kb\n", encoding="utf-8")
        self._gate()

    def test_residue_file_entries_are_exact_not_string_prefixes(self) -> None:
        # The same hole the derived set closes, applied to the residue: a
        # residue *file* left in the prefix tuple would sanction an editor
        # backup beside it, which is what this gate exists to stop.
        (self.repo / ".gitignore.bak").write_text("/.obsidian-kb\n", encoding="utf-8")
        with self.assertRaises(publish.PublishError) as ctx:
            self._gate()
        self.assertIn(".gitignore.bak", str(ctx.exception))

    def test_ignore_block_refresh_rewrites_the_managed_block(self) -> None:
        # Helper contract only. This says nothing about *when* publish() calls it;
        # test_publish_captures_a_stale_ignore_block_in_the_work_commit owns that.
        self._make_kb_helper(
            "from pathlib import Path\n"
            "Path('.gitignore').write_text('# sd-ai-command-pack obsidian-kb start\\n')\n"
        )
        state = publish.refresh_managed_ignore_block(self.repo, sys.executable)
        self.assertEqual(state, "refreshed")
        self.assertIn(
            "obsidian-kb start",
            (self.repo / ".gitignore").read_text(encoding="utf-8"),
        )

    @unittest.skipUnless(shutil.which("node"), "node required for completion receipt")
    def test_publish_captures_a_stale_ignore_block_in_the_work_commit(self) -> None:
        """The ordering regression, pinned where it actually bites.

        Moving ``refresh_managed_ignore_block()`` after ``work_commit()`` leaves
        ``.gitignore`` dirty for the merge gate, and by then the completion
        bundle cannot absorb it: the span is ``bundle_scope_invalid`` and a
        second bundle is ``completion_archive_move_missing``. Only an assertion
        about H1's contents catches that -- calling the helper directly passes
        either way.
        """

        # A consumer whose managed block predates the release that rewrites it.
        (self.repo / ".gitignore").write_text(
            "# Generated by scripts/sd-ai-command-pack-update-spec-kb.py."
            " DO NOT EDIT MANUALLY.\n/.obsidian-kb\n",
            encoding="utf-8",
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "stale managed ignore block")

        self._make_repomix('printf "# regenerated\\n" > docs/repomix-map.md\n')
        self._make_kb_helper(
            "from pathlib import Path\n"
            "Path('.gitignore').write_text("
            "'# Generated by sd-ai-command-pack. DO NOT EDIT MANUALLY.\\n"
            "/.obsidian-kb\\n')\n"
        )
        self._install_publish_fakes()
        base = publish.git_out(["rev-parse", "HEAD"], cwd=self.repo)

        aux = tempfile.TemporaryDirectory(prefix="sd-fleet-publish-aux-")
        self.addCleanup(aux.cleanup)
        work_message = Path(aux.name) / "work.txt"
        work_message.write_text("chore: refresh pack\n", encoding="utf-8")
        receipt = Path(aux.name) / "receipt.json"

        rc = publish.main(
            [
                str(self.repo),
                self.slug,
                "--branch",
                "main",
                "--title",
                "Demo publish",
                "--summary",
                "Refresh with a stale ignore block.",
                "--change",
                "regenerated the managed ignore block",
                "--test",
                "unit: stale ignore block folds into H1",
                "--work-message-file",
                str(work_message),
                "--receipt-out",
                str(receipt),
                "--record-session",
                str(self.repo / "scripts" / "fake-record-session.py"),
                "--python",
                sys.executable,
                "--archive-month",
                "2026-01",
                "--no-push",
            ]
        )
        self.assertEqual(rc, 0)

        # H1 is the first commit after the base: the work commit.
        revs = publish.git_out(
            ["rev-list", "--reverse", f"{base}..HEAD"], cwd=self.repo
        ).split()
        h1 = revs[0]
        h1_files = publish.git_out(
            ["show", "--name-only", "--format=", h1], cwd=self.repo
        ).split()
        self.assertIn(
            ".gitignore",
            h1_files,
            "the regenerated ignore block must land in the work commit, not at the merge gate",
        )
        self.assertIn(
            "# Generated by sd-ai-command-pack.",
            publish.git_out(["show", f"{h1}:.gitignore"], cwd=self.repo),
        )
        # Nothing left for housekeeping to rewrite.
        self.assertEqual(
            publish.git_out(["status", "--porcelain"], cwd=self.repo).strip(), ""
        )

    def test_ignore_block_refresh_is_invoked_with_the_consumer_as_cwd(self) -> None:
        # The real helper resolves its own root from the working directory, so a
        # wrong cwd would rewrite the source checkout's .gitignore instead.
        self._make_kb_helper(
            "import os\n"
            "from pathlib import Path\n"
            "Path('cwd.txt').write_text(os.getcwd())\n"
        )
        publish.refresh_managed_ignore_block(self.repo, sys.executable)
        self.assertEqual(
            Path((self.repo / "cwd.txt").read_text(encoding="utf-8")).resolve(),
            self.repo,
        )

    def test_ignore_block_refresh_passes_no_if_present(self) -> None:
        # Housekeeping omits --if-present; matching it is what keeps the two
        # writers producing identical .gitignore content.
        self._make_kb_helper(
            "from pathlib import Path\n"
            "Path('argv.txt').write_text(repr(sys.argv[1:]))\n"
        )
        publish.refresh_managed_ignore_block(self.repo, sys.executable)
        self.assertEqual((self.repo / "argv.txt").read_text(encoding="utf-8"), "[]")

    def test_ignore_block_refresh_reports_absent_helper_without_failing(self) -> None:
        self.assertEqual(
            publish.refresh_managed_ignore_block(self.repo, sys.executable), "absent"
        )

    def test_ignore_block_refresh_failure_is_advisory(self) -> None:
        # The KB folder is regenerable and ignored, so a failing refresh must not
        # abort a pack refresh that is otherwise sound.
        self._make_kb_helper("sys.stderr.write('read-only target\\n')\nsys.exit(2)\n")
        self.assertEqual(
            publish.refresh_managed_ignore_block(self.repo, sys.executable), "failed"
        )

    def test_ignore_block_refresh_reports_refreshed_when_a_failing_helper_still_wrote_it(
        self,
    ) -> None:
        # The real helper writes .gitignore before it copies anything, then exits
        # 3 when only the KB copies conflict. Keying the state off the exit code
        # would report a stale block that is in fact refreshed and inside H1.
        self._make_kb_helper(
            "from pathlib import Path\n"
            "Path('.gitignore').write_text('# Generated by sd-ai-command-pack.\\n')\n"
            "sys.stderr.write('kb copy conflict\\n')\n"
            "sys.exit(3)\n"
        )
        self.assertEqual(
            publish.refresh_managed_ignore_block(self.repo, sys.executable),
            "refreshed",
        )


if __name__ == "__main__":
    unittest.main()
