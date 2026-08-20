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

    def test_derive_work_commits_picks_unrecorded_non_workspace_commits(self) -> None:
        """Omitting --commit must not produce a session the validator rejects.

        ``add_session.py`` writes "(No commits - planning session)" with no
        hash, and the pack's own final-bundle validator then fails that session
        with ``journal_commit_missing``. Derivation closes that gap: it stops at
        the first commit a journal already cites, and skips commits confined to
        the workspace so journal and index commits never nominate themselves.
        """
        recorder = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-record-session.py",
            "sd_record_session_derive",
        )
        root = self.make_repo()
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")

        def head() -> str:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()

        def commit(message: str, path: str, body: str) -> str:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            self.run_git(root, "add", "-A")
            self.run_git(root, "commit", "-m", message)
            return head()

        seed = commit("seed work", "work-1.txt", "one\n")
        journal = root / ".trellis/workspace/dev/journal-1.md"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(
            "| Hash | Message |\n|------|---------|\n"
            f"| `{seed[:7]}` | seed work |\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "chore: record journal")
        first = commit("real work one", "work-2.txt", "two\n")
        second = commit("real work two", "work-3.txt", "three\n")
        commit("chore: bookkeeping", ".trellis/workspace/dev/index.md", "note\n")

        self.assertEqual(recorder.recorded_commit_hashes(), {seed[:7]})
        # Oldest first, journal and workspace-only commits excluded, and the
        # walk stops at the already-recorded seed.
        self.assertEqual(recorder.derive_work_commits(), [first, second])

    def test_derive_work_commits_declines_when_the_answer_is_not_obvious(self) -> None:
        recorder = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-record-session.py",
            "sd_record_session_derive_edges",
        )
        root = self.make_repo()
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(root)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        (root / "work.txt").write_text("one\n", encoding="utf-8")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "seed work")

        # No journal cites anything, so there is no boundary to walk back to.
        self.assertEqual(recorder.derive_work_commits(), [])

        journal = root / ".trellis/workspace/dev/journal-1.md"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text("| `0123456` | unrelated |\n", encoding="utf-8")
        # A recorded hash absent from this history never terminates the walk,
        # so every commit would be a false candidate.
        self.assertEqual(recorder.derive_work_commits(), [])

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

    def test_record_session_patch_uses_atomic_write(self) -> None:
        recorder = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-record-session.py",
            "sd_record_session_atomic_write",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-recorder-atomic-")
        self.addCleanup(tempdir.cleanup)
        journal = Path(tempdir.name) / "journal-1.md"
        original = (
            "# Journal\n"
            "\n"
            "## Session 1: Atomic session\n"
            "\n"
            "### Summary\n"
            "Started.\n"
            "\n"
            "### Main Changes\n"
            "- recorded work\n"
            "\n"
            "### Commits\n"
            "| Commit | Subject |\n"
            "| `abc123` | feat: atomic journal |\n"
        )
        journal.write_text(original, encoding="utf-8")

        with mock.patch.object(recorder.os, "replace", side_effect=OSError("blocked")):
            error = recorder.patch_last_session(
                journal,
                "Atomic session",
                ["abc123"],
                ["- [OK] unit tests"],
                [],
            )

        self.assertEqual(error, f"cannot write {journal}: blocked")
        self.assertEqual(journal.read_text(encoding="utf-8"), original)
        self.assertEqual(list(journal.parent.glob(".*.tmp")), [])

    def test_record_session_patch_requires_a_real_commit_table_row(self) -> None:
        """Prose naming the OID must not stand in for the row itself.

        The assertion exists to catch the runtime failing to write a commit
        row. A `--change` bullet mentioning the same hash in a code span is
        the case where a bare substring search would report success for
        exactly the failure it is there to detect.
        """
        recorder = self.load_module_from_path(
            PACK_ROOT / "scripts/sd-ai-command-pack-record-session.py",
            "sd_record_session_row_anchor",
        )
        tempdir = tempfile.TemporaryDirectory(prefix="sd-recorder-row-")
        self.addCleanup(tempdir.cleanup)
        journal = Path(tempdir.name) / "journal-1.md"
        journal.write_text(
            "# Journal\n"
            "\n"
            "## Session 1: Anchored session\n"
            "\n"
            "### Summary\n"
            "Started.\n"
            "\n"
            "### Main Changes\n"
            "- reverted `abc123` after the build broke\n"
            "\n"
            "### Commits\n"
            "| Commit | Subject |\n",
            encoding="utf-8",
        )

        error = recorder.patch_last_session(
            journal,
            "Anchored session",
            ["abc123"],
            ["- [OK] unit tests"],
            [],
        )

        self.assertEqual(error, f"missing commit table row for abc123 in {journal}")

    def test_record_session_wrapper_reuses_uncommitted_retry_entry(self) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                **kwargs,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")
        (root / "feature.txt").write_text("hi\n", encoding="utf-8")
        run("git", "add", "feature.txt")
        run("git", "commit", "-q", "-m", "feat: add retry feature")
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / "stub-bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"add\" ]; then\n"
            "  echo synthetic git add failure >&2\n"
            "  exit 1\n"
            "fi\n"
            f"exec {real_git} \"$@\"\n",
            encoding="utf-8",
        )
        git_stub.chmod(0o755)
        path = os.environ.get("PATH", "")
        failing_env = {
            **os.environ,
            "PATH": f"{stub_bin}{os.pathsep}{path}" if path else str(stub_bin),
        }

        command = [
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Retry session",
            "--summary",
            "Recorded after retry.",
            "--commit",
            commit_hash,
            "--change",
            "added retry feature",
            "--test",
            "retry test green",
        ]
        failed = run(*command, env=failing_env)

        self.assertEqual(failed.returncode, 1, failed.stdout)
        self.assertIn("synthetic git add failure", failed.stdout)
        journal = next((root / ".trellis/workspace").glob("*/journal-*.md"))
        self.assertEqual(
            journal.read_text(encoding="utf-8").count("## Session"), 1
        )

        retried = run(*command)

        self.assertEqual(retried.returncode, 0, retried.stdout)
        entry = journal.read_text(encoding="utf-8")
        index = journal.with_name("index.md").read_text(encoding="utf-8")
        self.assertEqual(entry.count("## Session"), 1)
        self.assertEqual(entry.count("Retry session"), 2)
        self.assertEqual(index.count("Retry session"), 1)
        self.assertIn("feat: add retry feature", entry)
        self.assertIn("- [OK] retry test green", entry)

    def test_record_session_wrapper_emits_git_metadata_block_under_json(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                **kwargs,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / "stub-bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "add" ]; then\n'
            "  echo synthetic git add failure >&2\n"
            "  exit 1\n"
            "fi\n"
            f'exec {real_git} "$@"\n',
            encoding="utf-8",
        )
        git_stub.chmod(0o755)
        path = os.environ.get("PATH", "")
        failing_env = {
            **os.environ,
            "PATH": f"{stub_bin}{os.pathsep}{path}" if path else str(stub_bin),
        }

        command = [
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Blocked session",
            "--summary",
            "Recorded but blocked at commit.",
            "--change",
            "did the work",
            "--test",
            "green",
            "--json",
        ]
        blocked = run(*command, env=failing_env)

        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        # git's own output stays on the human channel.
        self.assertIn("synthetic git add failure", blocked.stderr)
        # The machine channel carries exactly the structured evidence, nothing
        # else, so a consumer can parse it without stripping human noise.
        envelope = json.loads(blocked.stdout.strip())
        self.assertEqual(envelope["outcome"], "blocked")
        fragment = envelope["environmentBlocked"]
        self.assertEqual(fragment["boundary"], "git-metadata")
        self.assertEqual(fragment["checkpoint"], "journal-recorded")
        self.assertEqual(fragment["mutationState"], "partial-recoverable")
        self.assertIs(fragment["retryable"], True)
        self.assertEqual(fragment["recoveryAction"]["kind"], "skill")

        # The journal entry exists exactly once despite the block.
        journal = next((root / ".trellis/workspace").glob("*/journal-*.md"))
        self.assertEqual(journal.read_text(encoding="utf-8").count("## Session"), 1)

        # Retrying with a working git commits the entry without appending a
        # second one, proving the partial-recoverable / retryable claim.
        retried = run(*[arg for arg in command if arg != "--json"])
        self.assertEqual(retried.returncode, 0, retried.stdout)
        self.assertEqual(
            journal.read_text(encoding="utf-8").count("## Session"), 1
        )

    def test_record_session_wrapper_reuses_untracked_workspace_retry_entry(
        self,
    ) -> None:
        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self._seed_trellis_session_tooling(root)

        def run(*args: str, **kwargs: object) -> subprocess.CompletedProcess:
            return subprocess.run(
                args,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                **kwargs,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        self.assertEqual(
            run(
                "git",
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--",
                ".trellis/workspace",
            ).stdout,
            "?? .trellis/workspace/\n",
        )
        (root / "feature.txt").write_text("hi\n", encoding="utf-8")
        run("git", "add", "feature.txt")
        run("git", "commit", "-q", "-m", "feat: add untracked retry feature")
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / "stub-bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"add\" ]; then\n"
            "  echo synthetic git add failure >&2\n"
            "  exit 1\n"
            "fi\n"
            f"exec {real_git} \"$@\"\n",
            encoding="utf-8",
        )
        git_stub.chmod(0o755)
        path = os.environ.get("PATH", "")
        failing_env = {
            **os.environ,
            "PATH": f"{stub_bin}{os.pathsep}{path}" if path else str(stub_bin),
        }

        command = [
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Untracked retry session",
            "--summary",
            "Recorded after retry in an untracked workspace.",
            "--commit",
            commit_hash,
            "--change",
            "added untracked retry feature",
            "--test",
            "untracked retry test green",
        ]
        failed = run(*command, env=failing_env)

        self.assertEqual(failed.returncode, 1, failed.stdout)
        self.assertIn("synthetic git add failure", failed.stdout)
        journal = next((root / ".trellis/workspace").glob("*/journal-*.md"))
        self.assertEqual(
            journal.read_text(encoding="utf-8").count("## Session"), 1
        )

        retried = run(*command)

        self.assertEqual(retried.returncode, 0, retried.stdout)
        entry = journal.read_text(encoding="utf-8")
        index = journal.with_name("index.md").read_text(encoding="utf-8")
        self.assertEqual(entry.count("## Session"), 1)
        self.assertEqual(entry.count("Untracked retry session"), 2)
        self.assertEqual(index.count("Untracked retry session"), 1)
        self.assertIn("feat: add untracked retry feature", entry)
        self.assertIn("- [OK] untracked retry test green", entry)

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

    def test_record_session_wrapper_delegates_commit_cell_escaping(
        self,
    ) -> None:
        """The runtime renders the commit cell; the wrapper must not redo it.

        The wrapper used to overwrite each row with
        ``subject.replace("|", "\\|")``, which escapes pipes but leaves
        backslashes raw and preserves whitespace runs that can break the row.
        ``escape_markdown_cell`` collapses whitespace and escapes both, so the
        subject below is the case the removal fixes.
        """
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
        # Track the seeded workspace so the wrapper's status scan sees the
        # journal add_session modifies rather than one untracked directory.
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: seed trellis tooling")

        subject = "fix: escape a | pipe and a C:\\tmp path   with   gaps"
        (root / "feature.txt").write_text("feature\n", encoding="utf-8")
        run("git", "add", "feature.txt")
        run("git", "commit", "-q", "-m", subject)
        commit_hash = run("git", "rev-parse", "--short", "HEAD").stdout.strip()

        result = run(
            sys.executable,
            "scripts/sd-ai-command-pack-record-session.py",
            "--title",
            "Escaping session",
            "--summary",
            "Recorded a subject needing cell escaping.",
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
        row = next(
            line for line in entry.splitlines() if commit_hash in line
        )
        # Both metacharacters escaped, whitespace collapsed, and the row still
        # has exactly the two cells the table declares.
        self.assertIn("\\|", row)
        self.assertIn("C:\\\\tmp", row)
        self.assertNotIn("   ", row)
        self.assertEqual(row.count("|") - row.count("\\|"), 3)
        self.assertIn("- [OK] unit suite green", entry)
        last_message = run("git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(last_message, "chore: record journal")


if __name__ == "__main__":
    unittest.main()
