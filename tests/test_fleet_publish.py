from __future__ import annotations

import importlib.util
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

    # ------------------------------------------------------------------ preconditions

    def test_refuses_when_tree_is_dirty_outside_allowlist(self) -> None:
        (self.repo / "src" / "app.py").write_text("print(2)\n", encoding="utf-8")
        with self.assertRaises(publish.PublishError) as ctx:
            publish.check_preconditions(
                self.repo, self.slug, publish.DEFAULT_ALLOWED_PREFIXES
            )
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
        publish.check_preconditions(
            self.repo, self.slug, publish.DEFAULT_ALLOWED_PREFIXES
        )

    def test_refuses_missing_task_directory(self) -> None:
        with self.assertRaises(publish.PublishError) as ctx:
            publish.resolve_task_dir(self.repo, "99-99-nope")
        self.assertEqual(ctx.exception.code, 3)

    def test_refuses_task_slug_escaping_task_root(self) -> None:
        with self.assertRaises(publish.PublishError) as ctx:
            publish.resolve_task_dir(self.repo, "../../etc")
        self.assertEqual(ctx.exception.code, 3)

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


if __name__ == "__main__":
    unittest.main()
