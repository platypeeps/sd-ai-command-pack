from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

contextlib = _support.contextlib
hashlib = _support.hashlib
importlib = _support.importlib
io = _support.io
json = _support.json
os = _support.os
re = _support.re
shutil = _support.shutil
subprocess = _support.subprocess
sys = _support.sys
tempfile = _support.tempfile
unittest = _support.unittest
mock = _support.mock
Path = _support.Path
yaml = _support.yaml
install = _support.install
PACK_ROOT = _support.PACK_ROOT
INSTALLER = _support.INSTALLER
SECRET_MARKER_PATTERNS = _support.SECRET_MARKER_PATTERNS
InstallTestCase = _support.InstallTestCase


class RecordSessionTests(InstallTestCase):
    """Tests for session recorder wrapper behavior."""

    def test_recorder_journal_detection_handles_failures_and_renames(self) -> None:
        recorder = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-record-session.py",
            "sd_record_session_journals",
        )
        non_git = Path(tempfile.mkdtemp(prefix="sd-non-git-recorder-"))
        self.addCleanup(shutil.rmtree, non_git, True)
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(non_git)
        with self.assertRaisesRegex(SystemExit, "git status failed"):
            recorder.modified_workspace_journals()

        root = self.make_repo()
        os.chdir(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        journal = root / ".trellis/workspace/dev/journal-1.md"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text("# journal\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "seed journal")
        self.run_git(
            root,
            "mv",
            ".trellis/workspace/dev/journal-1.md",
            ".trellis/workspace/dev/journal-2.md",
        )
        spaced = root / ".trellis/workspace/dev two/journal-1.md"
        spaced.parent.mkdir(parents=True, exist_ok=True)
        spaced.write_text("# spaced journal\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/workspace")
        journals = recorder.modified_workspace_journals()
        self.assertEqual(
            journals,
            [
                Path(".trellis/workspace/dev two/journal-1.md"),
                Path(".trellis/workspace/dev/journal-2.md"),
            ],
        )
        # git status --porcelain -z emits "XY to\0from\0" for renames: the
        # first token is the CURRENT path; the skipped companion is the old
        # name and must never surface.
        self.assertNotIn(Path(".trellis/workspace/dev/journal-1.md"), journals)

    def test_record_session_wrapper_writes_complete_entry(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        (root / "feature.txt").write_text("hi\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "feat: add feature file")
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        # Dirty the bootstrap journal AND plant a second modified journal:
        # the before/after delta is then empty and two candidates remain,
        # so detection must disambiguate via the new entry's title.
        pre_journal = next((root / ".trellis/workspace").glob("*/journal-*.md"))
        pre_journal.write_text(
            pre_journal.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        # journal-0 sorts below the active part, so Trellis keeps writing
        # to journal-1 while the wrapper sees two modified candidates.
        decoy = pre_journal.parent / "journal-0.md"
        decoy.write_text("# Journal - tester (Part 0)\n", encoding="utf-8")

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Demo session",
            "--summary",
            "Did the demo work.",
            "--commit",
            commit_hash,
            "--change",
            "added the feature file",
            "--change",
            "- kept the docs current",
            "--test",
            "unit suite green",
            "--test",
            "  [WARN] flaky case quarantined",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        entry = pre_journal.read_text(encoding="utf-8")
        self.assertNotIn("Demo session", decoy.read_text(encoding="utf-8"))
        self.assertIn("feat: add feature file", entry)
        self.assertIn("- added the feature file", entry)
        self.assertIn("- kept the docs current", entry)
        self.assertIn("- [OK] unit suite green", entry)
        self.assertIn("- [WARN] flaky case quarantined", entry)
        self.assertNotIn("-  [WARN]", entry)
        self.assertNotIn("[OK] [WARN]", entry)
        self.assertNotIn("(Add details)", entry)
        self.assertNotIn("(Add test results)", entry)
        self.assertNotIn("(see git log)", entry)
        last_message = run("git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(last_message, "chore: record journal")
        committed = run("git", "show", "--name-only", "--format=", "HEAD").stdout
        self.assertIn("journal-1.md", committed)
        self.assertNotIn("journal-0.md", committed)

    def test_record_session_wrapper_prefers_current_branch_over_task_metadata(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "branch", "-m", "feature/current")

        task_dir = root / ".trellis/tasks/07-05-demo"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(
            json.dumps(
                {
                    "title": "Demo task",
                    "status": "in_progress",
                    "package": None,
                    "branch": "task/stale",
                    "base_branch": "main",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        sessions_dir = root / ".trellis/.runtime/sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "session.json").write_text(
            json.dumps(
                {
                    "current_task": ".trellis/tasks/07-05-demo",
                    "platform": "test",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed task")

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Branch session",
            "--summary",
            "Recorded with current branch.",
            "--change",
            "captured branch context",
            "--test",
            "branch assertion green",
            "--no-commit",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        journals = sorted(
            (root / ".trellis/workspace").glob("*/journal-*.md")
        )
        self.assertEqual(len(journals), 1)
        entry = journals[0].read_text(encoding="utf-8")
        index = journals[0].with_name("index.md").read_text(encoding="utf-8")
        self.assertIn("**Branch**: `feature/current`", entry)
        self.assertNotIn("task/stale", entry)
        self.assertIn("`feature/current` |", index)
        self.assertNotIn("`task/stale`", index)

    def test_record_session_wrapper_fails_fast_on_unknown_hash(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/sd-ai-command-pack-record-session.py",
                "--title",
                "Demo",
                "--summary",
                "S",
                "--commit",
                "deadbeef",
                "--change",
                "c",
                "--test",
                "t",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("unknown commit hash: deadbeef", result.stdout)
        # Fail-fast means add_session never ran: the bootstrap journal
        # skeleton exists but carries no session entry.
        for journal in (root / ".trellis/workspace").glob("*/journal-*.md"):
            self.assertNotIn(
                "## Session", journal.read_text(encoding="utf-8")
            )

    def test_record_session_wrapper_rejects_bad_commit_arguments(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def record(commit_arg: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [
                    sys.executable,
                    "scripts/sd-ai-command-pack-record-session.py",
                    "--title",
                    "Demo",
                    "--summary",
                    "S",
                    f"--commit={commit_arg}",
                    "--change",
                    "c",
                    "--test",
                    "t",
                ],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        result = record("--all")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("invalid commit hash: --all", result.stdout)

        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        ).stdout.strip()
        result = record(f"{head},{head}")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(f"duplicate commit hash: {head}", result.stdout)

    def test_record_session_wrapper_accepts_empty_commit_subject(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")
        run(
            "git", "commit", "-q", "--allow-empty",
            "--allow-empty-message", "-m", "",
        )
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Empty subject session",
            "--summary",
            "S",
            "--commit",
            commit_hash,
            "--change",
            "c",
            "--test",
            "t",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        journals = sorted(
            (root / ".trellis/workspace").glob("*/journal-*.md")
        )
        self.assertEqual(len(journals), 1)
        entry = journals[0].read_text(encoding="utf-8")
        self.assertIn(f"| `{commit_hash}` | (empty subject) |", entry)

    def test_record_session_wrapper_tolerates_prefilled_trellis_variant(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        # Emulate the Trellis variant that resolves commit subjects itself
        # and seeds a different Testing default (loadsmith's add_session).
        variant = root / ".trellis/scripts/add_session.py"
        source = variant.read_text(encoding="utf-8")
        self.assertIn("(see git log)", source)
        self.assertIn("- [OK] (Add test results)", source)
        source = source.replace("(see git log)", "prefilled subject")
        source = source.replace(
            "- [OK] (Add test results)",
            "- Validation not recorded for this session.",
        )
        variant.write_text(source, encoding="utf-8")

        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        # Track the seeded workspace so the wrapper's status scan sees the
        # journal add_session modifies rather than one untracked directory.
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")

        (root / "feature.txt").write_text("feature\n", encoding="utf-8")
        run("git", "add", "feature.txt")
        run("git", "commit", "-q", "-m", "feat: add feature file")
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Variant session",
            "--summary",
            "Recorded against a subject-resolving Trellis.",
            "--commit",
            commit_hash,
            "--change",
            "added the feature file",
            "--test",
            "unit suite green",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        journals = sorted(
            (root / ".trellis/workspace").glob("*/journal-*.md")
        )
        self.assertEqual(len(journals), 1)
        entry = journals[0].read_text(encoding="utf-8")
        self.assertIn("feat: add feature file", entry)
        self.assertNotIn("prefilled subject", entry)
        self.assertIn("- [OK] unit suite green", entry)
        self.assertNotIn("Validation not recorded", entry)
        last_message = run("git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(last_message, "chore: record journal")


if __name__ == "__main__":
    unittest.main()
