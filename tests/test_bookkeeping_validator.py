from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
os = _support.os
shutil = _support.shutil
subprocess = _support.subprocess
Path = _support.Path
PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase


class BookkeepingValidatorTests(InstallTestCase):
    def setUp(self) -> None:
        self.node = shutil.which("node")
        if self.node is None:
            self.skipTest("node is not available on PATH")

    def make_validator_repo(self) -> Path:
        root = self.make_repo()
        self.run_git(root, "config", "user.email", "bookkeeping@example.com")
        self.run_git(root, "config", "user.name", "Bookkeeping Test")
        scripts = root / "scripts"
        scripts.mkdir()
        shutil.copy2(
            PACK_ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            scripts / "sd-ai-command-pack-review-preflight.mjs",
        )
        self.run_git(root, "add", ".")
        self.run_git(root, "commit", "-m", "seed validator")
        self.run_git(root, "branch", "-M", "main")
        return root

    @staticmethod
    def task_record(
        name: str,
        *,
        status: str,
        branch: str | None,
        completed_at: str | None,
        description: str = "A bounded fixture task.",
    ) -> dict[str, object]:
        return {
            "id": name,
            "name": name,
            "title": "Bookkeeping fixture",
            "description": description,
            "status": status,
            "createdAt": "2026-07-25",
            "completedAt": completed_at,
            "branch": branch,
            "base_branch": "main",
            "parent": None,
            "children": [],
        }

    def write_task(
        self,
        root: Path,
        task_dir: str,
        record: dict[str, object],
    ) -> Path:
        task = root / task_dir
        task.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        (task / "prd.md").write_text("# Fixture\n\nValidated task.\n", encoding="utf-8")
        (task / "implement.jsonl").write_text("", encoding="utf-8")
        (task / "check.jsonl").write_text("", encoding="utf-8")
        return task

    def write_session(
        self,
        root: Path,
        commit: str,
        *,
        commit_in_journal: str | None = None,
        commits_in_journal: list[str] | None = None,
    ) -> None:
        commits = commits_in_journal or [commit_in_journal or commit]
        self.write_sessions(root, [commits])

    def write_sessions(self, root: Path, sessions: list[list[str]]) -> None:
        workspace = root / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        journal_lines = ["# Development Journal", ""]
        index_lines = [
            "# Sessions",
            "",
            "| # | Date | Title | Commits | Branch |",
            "|---|------|-------|---------|--------|",
        ]
        for number, commits in enumerate(sessions, start=1):
            title = "Validate bookkeeping" if number == 1 else f"Validate bookkeeping {number}"
            journal_lines.extend(
                [
                    f"## Session {number}: {title}",
                    "",
                    "### Summary",
                    "",
                    "Validated the final bookkeeping bundle.",
                    "",
                    "### Main Changes",
                    "",
                    "- Added canonical task and journal validation.",
                    "",
                    "### Git Commits",
                    "",
                    "| Hash | Message |",
                    "|------|---------|",
                ]
            )
            journal_lines.extend(
                f"| `{commit[:12]}` | fixture work |" for commit in commits
            )
            journal_lines.extend(
                [
                    "",
                    "### Testing",
                    "",
                    "- [OK] bookkeeping validator fixture",
                    "",
                    "### Status",
                    "",
                    "[OK] **Completed**",
                    "",
                    "### Next Steps",
                    "",
                    "- None",
                    "",
                ]
            )
            index_commits = ", ".join(f"`{commit[:12]}`" for commit in commits)
            index_lines.append(
                f"| {number} | 2026-07-25 | {title} | {index_commits} | `fixture` |"
            )
        index_lines.append("")
        (workspace / "journal-1.md").write_text(
            "\n".join(journal_lines), encoding="utf-8"
        )
        (workspace / "index.md").write_text(
            "\n".join(index_lines), encoding="utf-8"
        )

    def run_validator(
        self,
        root: Path,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.node,
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                *args,
                "--json",
            ],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_pre_archive_rejects_blank_description_without_mutation(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-blank-description"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "blank-description",
                status="in_progress",
                branch="codex/blank-description",
                completed_at=None,
                description=" ",
            ),
        )
        before = self.git_output(root, "status", "--porcelain")

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("task_metadata_invalid", payload["reasonCodes"])
        self.assertIn("description must be a non-empty string", result.stdout)
        self.assertEqual(self.git_output(root, "status", "--porcelain"), before)
        self.assertTrue((root / task_dir).is_dir())
        self.assertFalse((root / ".trellis/workspace").exists())

    def test_cli_usage_documents_repository_override(self) -> None:
        root = self.make_validator_repo()

        result = subprocess.run(
            [
                self.node,
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                "pre-archive",
                "--unknown",
            ],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(
            "node scripts/sd-ai-command-pack-review-preflight.mjs\n",
            result.stdout,
        )
        self.assertIn("[--repo <repo-root>]", result.stdout)

    def test_validator_honors_configured_artifact_limit(self) -> None:
        root = self.make_validator_repo()
        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.parent.mkdir(parents=True)
        config.write_text(
            json.dumps({"untrackedFileReadLimitBytes": 16}) + "\n",
            encoding="utf-8",
        )
        task_dir = ".trellis/tasks/07-25-configured-limit"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "configured-limit",
                status="in_progress",
                branch="codex/configured-limit",
                completed_at=None,
            ),
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("16 bytes", result.stdout)

    def test_cli_defaults_to_script_repository_outside_working_directory(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-outside-cwd"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "outside-cwd",
                status="in_progress",
                branch="codex/outside-cwd",
                completed_at=None,
            ),
        )

        result = subprocess.run(
            [
                self.node,
                str(root / "scripts/sd-ai-command-pack-review-preflight.mjs"),
                "pre-archive",
                "--task-dir",
                task_dir,
                "--json",
            ],
            cwd=root.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "valid")

    def test_diagnostics_redact_repository_path(self) -> None:
        root = self.make_validator_repo()

        result = self.run_validator(
            root,
            "pre-archive",
            "--task-dir",
            ".trellis/tasks/07-25-missing-fixture",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("<repo>", result.stdout)
        self.assertNotIn(str(root), result.stdout)

    def test_pre_archive_reuses_lifecycle_topology_and_context_rules(self) -> None:
        root = self.make_validator_repo()
        parent_name = "07-25-parent-fixture"
        parent = self.write_task(
            root,
            f".trellis/tasks/{parent_name}",
            self.task_record(
                "parent-fixture",
                status="in_progress",
                branch="codex/parent-fixture",
                completed_at=None,
            ),
        )
        task_dir = ".trellis/tasks/07-25-child-fixture"
        child_record = self.task_record(
            "child-fixture",
            status="planning",
            branch=None,
            completed_at=None,
        )
        child_record["parent"] = parent_name
        child = self.write_task(root, task_dir, child_record)
        (child / "implement.jsonl").write_text(
            '{"_example":{"file":"src/example.py"}}\n', encoding="utf-8"
        )
        parent_record = json.loads((parent / "task.json").read_text(encoding="utf-8"))
        parent_record["children"] = []
        (parent / "task.json").write_text(
            json.dumps(parent_record, indent=2) + "\n", encoding="utf-8"
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn("task_lifecycle_not_completion_ready", payload["reasonCodes"])
        self.assertIn("task_topology_not_reciprocal", payload["reasonCodes"])

        child_record["status"] = "in_progress"
        child_record["branch"] = "codex/child-fixture"
        (child / "task.json").write_text(
            json.dumps(child_record, indent=2) + "\n", encoding="utf-8"
        )
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        payload = json.loads(result.stdout)
        self.assertIn("task_context_seed", payload["reasonCodes"])

    def test_pre_archive_rejects_unsafe_unbounded_and_invalid_utf8_artifacts(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-artifact-fixture"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                "artifact-fixture",
                status="in_progress",
                branch="codex/artifact-fixture",
                completed_at=None,
            ),
        )

        (task / "prd.md").write_bytes(b"\xff\xfe")
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        self.assertIn("task_prd_invalid", json.loads(result.stdout)["reasonCodes"])

        (task / "prd.md").write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        self.assertIn("task_prd_invalid", json.loads(result.stdout)["reasonCodes"])

        (task / "prd.md").unlink()
        (task / "prd.md").symlink_to("task.json")
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        self.assertIn("task_prd_invalid", json.loads(result.stdout)["reasonCodes"])

    def test_valid_completion_archive_and_journal_bundle(self) -> None:
        root = self.make_validator_repo()
        name = "completion-fixture"
        active_dir = f".trellis/tasks/07-25-{name}"
        active = self.write_task(
            root,
            active_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/completion-fixture",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        base = self.git_output(root, "rev-parse", "HEAD")

        archive = root / f".trellis/tasks/archive/2026-07/07-25-{name}"
        archive.parent.mkdir(parents=True)
        active.rename(archive)
        record = json.loads((archive / "task.json").read_text(encoding="utf-8"))
        record["status"] = "completed"
        record["completedAt"] = "2026-07-25"
        (archive / "task.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "archive fixture")
        self.write_session(root, base)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])
        self.assertNotIn(str(root), result.stdout)

    def make_post_archive_successor_repo(
        self, *, prehistory_commits: int = 0, corrupt_archive: bool = False
    ) -> tuple[Path, str, str]:
        root = self.make_validator_repo()
        for index in range(prehistory_commits):
            self.run_git(
                root,
                "commit",
                "--allow-empty",
                "-m",
                f"historical commit {index + 1}",
            )
        name = "completion-successor"
        active_dir = f".trellis/tasks/07-25-{name}"
        active = self.write_task(
            root,
            active_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/completion-successor",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        work_commit = self.git_output(root, "rev-parse", "HEAD")

        archive_dir = f".trellis/tasks/archive/2026-07/07-25-{name}"
        archive = root / archive_dir
        archive.parent.mkdir(parents=True)
        active.rename(archive)
        record = json.loads((archive / "task.json").read_text(encoding="utf-8"))
        record["status"] = "completed"
        record["completedAt"] = None if corrupt_archive else "2026-07-25"
        (archive / "task.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "archive fixture")
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        bookkeeping_head = self.git_output(root, "rev-parse", "HEAD")
        return root, archive_dir, bookkeeping_head

    def test_completion_successor_recovers_post_archive_review_fixes(self) -> None:
        root, archive_dir, bookkeeping_head = self.make_post_archive_successor_repo()
        (root / "src").mkdir()
        (root / "src/app.py").write_text("value = 1\n", encoding="utf-8")
        self.run_git(root, "add", "src/app.py")
        self.run_git(root, "commit", "-m", "fix review finding")
        (root / "src/app.py").write_text("value = 2\n", encoding="utf-8")
        self.run_git(root, "add", "src/app.py")
        self.run_git(root, "commit", "-m", "fix follow-up finding")
        head = self.git_output(root, "rev-parse", "HEAD")
        before = self.git_output(root, "status", "--porcelain")

        first = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )
        second = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertEqual(first.stdout, second.stdout)
        payload = json.loads(first.stdout)
        evidence = payload["evidence"]
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])
        self.assertEqual(
            evidence["completionSubtype"], "post-archive-review-successor"
        )
        self.assertEqual(
            evidence["completionAnchor"]["bookkeepingHeadOid"], bookkeeping_head
        )
        self.assertEqual(evidence["taskDirectories"], [archive_dir])
        self.assertEqual(
            [item["oid"] for item in evidence["successor"]["commits"]],
            self.git_output(
                root,
                "rev-list",
                "--first-parent",
                "--reverse",
                f"{bookkeeping_head}..{head}",
            ).splitlines(),
        )
        self.assertEqual(evidence["successor"]["changedPaths"], ["src/app.py"])
        self.assertRegex(evidence["repository"]["rootDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(self.git_output(root, "status", "--porcelain"), before)

    def test_completion_successor_finds_recent_anchor_in_long_history(self) -> None:
        root, _, bookkeeping_head = self.make_post_archive_successor_repo(
            prehistory_commits=101
        )
        (root / "review-fix.txt").write_text("reviewed\n", encoding="utf-8")
        self.run_git(root, "add", "review-fix.txt")
        self.run_git(root, "commit", "-m", "fix review finding")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        evidence = json.loads(result.stdout)["evidence"]
        self.assertEqual(
            evidence["completionAnchor"]["bookkeepingHeadOid"], bookkeeping_head
        )

    def test_completion_successor_rejects_invalid_nearest_anchor(self) -> None:
        root, _, _ = self.make_post_archive_successor_repo(corrupt_archive=True)
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"],
            ["completion_successor_anchor_invalid"],
        )

    def test_completion_successor_enforces_commit_bound(self) -> None:
        root, _, _ = self.make_post_archive_successor_repo()
        for index in range(51):
            self.run_git(
                root,
                "commit",
                "--allow-empty",
                "-m",
                f"review remediation {index + 1}",
            )
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_history_oversized",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_completion_successor_rejects_runtime_evidence_changes(self) -> None:
        root, _, _ = self.make_post_archive_successor_repo()
        runtime = root / ".trellis/.runtime"
        runtime.mkdir(parents=True)
        (runtime / "finish-work.json").write_text("{}\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/.runtime/finish-work.json")
        self.run_git(root, "commit", "-m", "persist forbidden finish-work state")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_scope_invalid",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_completion_successor_rejects_bookkeeping_changes_after_archive(
        self,
    ) -> None:
        root, archive_dir, _ = self.make_post_archive_successor_repo()
        task_file = root / archive_dir / "task.json"
        record = json.loads(task_file.read_text(encoding="utf-8"))
        record["notes"] = "changed after completion"
        task_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        self.run_git(root, "add", archive_dir)
        self.run_git(root, "commit", "-m", "mutate archived bookkeeping")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_scope_invalid",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_completion_successor_rejects_merge_commit(self) -> None:
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        self.run_git(root, "switch", "-c", "review-side")
        (root / "side.txt").write_text("side\n", encoding="utf-8")
        self.run_git(root, "add", "side.txt")
        self.run_git(root, "commit", "-m", "side review fix")
        self.run_git(root, "switch", "main")
        self.run_git(root, "merge", "--no-ff", "review-side", "-m", "merge review fix")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn("completion_successor_history_non_linear", payload["reasonCodes"])
        self.assertEqual(
            payload["evidence"]["headOid"],
            head,
        )
        self.assertNotEqual(bookkeeping_head, head)

    def test_completion_successor_requires_a_canonical_anchor(self) -> None:
        root = self.make_validator_repo()
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"],
            ["completion_successor_anchor_missing"],
        )

    def test_valid_planning_task_and_journal_bundle(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "planning-fixture"
        task_dir = f".trellis/tasks/07-25-{name}"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "plan fixture work")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record planning journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["mode"], "planning")
        self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])

    def test_valid_journal_only_planning_recovery(self) -> None:
        root = self.make_validator_repo()
        name = "journal-only-planning"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "create planning fixture")
        create_commit = self.git_output(root, "rev-parse", "HEAD")
        (task / "prd.md").write_text(
            "# Fixture\n\nValidated journal-only planning recovery.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "refine planning fixture")
        refine_commit = self.git_output(root, "rev-parse", "HEAD")
        base = refine_commit
        self.write_session(
            root,
            refine_commit,
            commits_in_journal=[create_commit, refine_commit],
        )
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record recovered planning journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])
        self.assertEqual(
            payload["evidence"]["planningSubtype"], "journal-only-recovery"
        )
        self.assertEqual(payload["evidence"]["taskDirectories"], [task_dir])

    def test_journal_only_recovery_batches_regular_path_inspection(self) -> None:
        source = (
            PACK_ROOT / "templates/scripts/sd-ai-command-pack-review-preflight.mjs"
        ).read_text(encoding="utf-8")

        batched_call = "bookkeepingRegularPathsAtCommit(commit.oid, commitPaths)"
        entry_loop = "for (const entry of commitEntries)"
        self.assertIn(batched_call, source)
        batched_call_offset = source.index(batched_call)
        self.assertLess(
            batched_call_offset,
            source.index(entry_loop, batched_call_offset),
        )
        self.assertIn(
            "runGit(['ls-tree', '-z', commitOid, '--', ...batch])",
            source,
        )
        self.assertIn("chunkBookkeepingGitPathspecs(paths)", source)
        self.assertIn(
            "if (pathBytes > MAX_BOOKKEEPING_GIT_PATHSPEC_BYTES) return [];",
            source,
        )
        self.assertNotIn("bookkeepingPathIsRegularAtCommit", source)

    def test_journal_only_recovery_chunks_large_pathspec_batches(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-large-pathspec-fixture"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                "large-pathspec-fixture",
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        for number in range(60):
            filename = f"artifact-{number:03d}-{'x' * 180}.md"
            (task / filename).write_text("bounded pathspec fixture\n", encoding="utf-8")
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "add large pathspec planning fixture")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record large pathspec recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        shim_dir = root / ".test-bin"
        shim_dir.mkdir()
        log_path = root / ".test-git.log"
        git_shim = shim_dir / "git"
        git_shim.write_text(
            "#!/usr/bin/env python3\n"
            "import subprocess\n"
            "import sys\n"
            f"real_git = {real_git!r}\n"
            f"log_path = {str(log_path)!r}\n"
            f"tracked_commit = {work_commit!r}\n"
            "args = sys.argv[1:]\n"
            "if len(args) > 2 and args[:2] == ['ls-tree', '-z'] and args[2] == tracked_commit:\n"
            "    with open(log_path, 'a', encoding='utf-8') as log:\n"
            "        log.write(str(len(args[4:])) + '\\n')\n"
            "raise SystemExit(subprocess.run([real_git, *args]).returncode)\n",
            encoding="utf-8",
        )
        git_shim.chmod(0o755)

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
            env={**os.environ, "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "valid")
        batches = [
            int(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(batches), 64)

    def test_journal_only_recovery_does_not_reaudit_published_content(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-published-content-debt"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                "published-content-debt",
                status="planning",
                branch=None,
                completed_at=None,
                description=" ",
            ),
        )
        seed = '{"_example":{"file":"src/example.py"}}\n'
        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "publish planning content debt")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record content-debt recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["evidence"]["planningSubtype"], "journal-only-recovery"
        )
        self.assertNotIn("task_context_seed", payload["reasonCodes"])
        self.assertNotIn("task_metadata_invalid", payload["reasonCodes"])

    def test_journal_only_recovery_labels_historical_task_json_failures(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-invalid-historical-json"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                "invalid-historical-json",
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        task_file = task / "task.json"
        valid_task = task_file.read_text(encoding="utf-8")
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "create historical-json fixture")
        task_file.write_text("{\n", encoding="utf-8")
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "corrupt historical task metadata")
        invalid_commit = self.git_output(root, "rev-parse", "HEAD")
        task_file.write_text(valid_task, encoding="utf-8")
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "restore historical task metadata")
        restored_commit = self.git_output(root, "rev-parse", "HEAD")
        base = restored_commit
        self.write_session(
            root,
            restored_commit,
            commits_in_journal=[invalid_commit, restored_commit],
        )
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record historical-json recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn(
            "planning_recovery_commit_task_json_invalid",
            payload["reasonCodes"],
        )
        self.assertIn(
            "planning_recovery_commit_parent_task_json_invalid",
            payload["reasonCodes"],
        )
        current_finding = next(
            item
            for item in payload["findings"]
            if item["reasonCode"]
            == "planning_recovery_commit_task_json_invalid"
        )
        parent_finding = next(
            item
            for item in payload["findings"]
            if item["reasonCode"]
            == "planning_recovery_commit_parent_task_json_invalid"
        )
        self.assertIn("the recovered work commit", current_finding["message"])
        self.assertIn(
            "the recovered work commit parent",
            parent_finding["message"],
        )
        self.assertNotIn("bundle base", current_finding["message"])
        self.assertNotIn("bundle base", parent_finding["message"])

    def test_journal_only_recovery_rejects_non_task_commit_scopes(self) -> None:
        fixtures = (
            ("src/app.py", "production code"),
            (".trellis/spec/backend/example.md", "specification"),
            (".sd-ai-command-pack/review.json", "configuration"),
            (".trellis/workspace/other/note.md", "workspace history"),
        )
        for path, content in fixtures:
            with self.subTest(path=path):
                root = self.make_validator_repo()
                artifact = root / path
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(content + "\n", encoding="utf-8")
                self.run_git(root, "add", path)
                self.run_git(root, "commit", "-m", "record non-task fixture")
                work_commit = self.git_output(root, "rev-parse", "HEAD")
                base = work_commit
                self.write_session(root, work_commit)
                self.run_git(root, "add", ".trellis/workspace/dev")
                self.run_git(root, "commit", "-m", "record recovery journal")
                head = self.git_output(root, "rev-parse", "HEAD")

                result = self.run_validator(
                    root,
                    "final-bundle",
                    "--mode",
                    "planning",
                    "--base",
                    base,
                    "--head",
                    head,
                )

                self.assertEqual(result.returncode, 1, result.stdout)
                reason_codes = json.loads(result.stdout)["reasonCodes"]
                self.assertIn("planning_recovery_commit_scope_invalid", reason_codes)
                self.assertIn("planning_recovery_task_change_missing", reason_codes)

    def test_journal_only_recovery_rejects_merge_commit(self) -> None:
        root = self.make_validator_repo()
        self.run_git(root, "switch", "-c", "fixture-side")
        task_dir = ".trellis/tasks/07-25-merge-fixture"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "merge-fixture", status="planning", branch=None, completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add merge-side planning fixture")
        self.run_git(root, "switch", "main")
        self.run_git(root, "merge", "--no-ff", "fixture-side", "-m", "merge fixture")
        merge_commit = self.git_output(root, "rev-parse", "HEAD")
        base = merge_commit
        self.write_session(root, merge_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record merge recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "planning_recovery_commit_non_linear",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_journal_only_recovery_rejects_root_commit(self) -> None:
        root = self.make_validator_repo()
        root_commit = self.git_output(root, "rev-list", "--max-parents=0", "HEAD")
        base = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, root_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record root recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "planning_recovery_commit_non_linear",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_journal_only_recovery_rejects_non_regular_task_artifact(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-symlink-fixture"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                "symlink-fixture", status="planning", branch=None, completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "seed regular planning fixture")
        (task / "linked-design.md").symlink_to("design.md")
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "add unsafe task symlink")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record symlink recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "planning_recovery_commit_scope_invalid",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_journal_only_recovery_rejects_non_ancestor_commit(self) -> None:
        root = self.make_validator_repo()
        self.run_git(root, "switch", "-c", "unpublished-side")
        task_dir = ".trellis/tasks/07-25-unpublished-fixture"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "unpublished-fixture",
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add unpublished planning fixture")
        unpublished = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(root, "switch", "main")
        base = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, unpublished)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record invalid recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        reason_codes = json.loads(result.stdout)["reasonCodes"]
        self.assertIn("journal_commit_unreachable", reason_codes)
        self.assertIn("planning_recovery_commit_not_published", reason_codes)

    def test_journal_only_recovery_rejects_duplicate_resolved_commit(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-duplicate-fixture"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "duplicate-fixture", status="planning", branch=None, completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add duplicate planning fixture")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        self.write_session(
            root,
            work_commit,
            commits_in_journal=[work_commit, work_commit[:12]],
        )
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record duplicate recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "planning_recovery_commit_duplicate",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_journal_only_recovery_rejects_invalid_planning_lifecycle(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-started-fixture"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "started-fixture",
                status="in_progress",
                branch="codex/started-fixture",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "start planning fixture")
        invalid_commit = self.git_output(root, "rev-parse", "HEAD")
        task_record = json.loads(
            (root / task_dir / "task.json").read_text(encoding="utf-8")
        )
        task_record["status"] = "planning"
        task_record["branch"] = None
        (root / task_dir / "task.json").write_text(
            json.dumps(task_record, indent=2) + "\n", encoding="utf-8"
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "restore planning lifecycle")
        restored_commit = self.git_output(root, "rev-parse", "HEAD")
        base = restored_commit
        self.write_session(
            root,
            restored_commit,
            commits_in_journal=[invalid_commit, restored_commit],
        )
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record lifecycle recovery journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "planning_lifecycle_mutation",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_journal_only_recovery_rejects_multiple_new_sessions(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-session-count-fixture"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                "session-count-fixture",
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add session-count fixture")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        self.write_sessions(root, [[work_commit], [work_commit]])
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record multiple recovery sessions")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn(
            "planning_recovery_session_count_invalid",
            payload["reasonCodes"],
        )
        self.assertNotIn("planningSubtype", payload["evidence"])
        self.assertEqual(payload["evidence"]["taskDirectories"], [])

    def test_journal_only_recovery_rejects_unknown_commit(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, base, commit_in_journal="deadbee")
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record unknown recovery commit")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        reason_codes = json.loads(result.stdout)["reasonCodes"]
        self.assertIn("journal_commit_unknown", reason_codes)
        self.assertIn("planning_recovery_task_change_missing", reason_codes)

    def test_journal_only_recovery_rejects_task_deletion_and_rename(self) -> None:
        for operation in ("delete", "rename"):
            with self.subTest(operation=operation):
                root = self.make_validator_repo()
                task_dir = ".trellis/tasks/07-25-history-fixture"
                task = self.write_task(
                    root,
                    task_dir,
                    self.task_record(
                        "history-fixture",
                        status="planning",
                        branch=None,
                        completed_at=None,
                    ),
                )
                (task / "design.md").write_text(
                    "# Design\n\nHistorical fixture.\n", encoding="utf-8"
                )
                self.run_git(root, "add", ".trellis/tasks")
                self.run_git(root, "commit", "-m", "seed task history fixture")
                if operation == "delete":
                    (task / "design.md").unlink()
                else:
                    (task / "design.md").rename(task / "implement.md")
                self.run_git(root, "add", "-A", ".trellis/tasks")
                self.run_git(root, "commit", "-m", f"{operation} task artifact")
                work_commit = self.git_output(root, "rev-parse", "HEAD")
                base = work_commit
                self.write_session(root, work_commit)
                self.run_git(root, "add", ".trellis/workspace")
                self.run_git(root, "commit", "-m", "record history recovery journal")
                head = self.git_output(root, "rev-parse", "HEAD")

                result = self.run_validator(
                    root,
                    "final-bundle",
                    "--mode",
                    "planning",
                    "--base",
                    base,
                    "--head",
                    head,
                )

                self.assertEqual(result.returncode, 1, result.stdout)
                reason_codes = json.loads(result.stdout)["reasonCodes"]
                self.assertIn("planning_recovery_commit_scope_invalid", reason_codes)
                self.assertIn("planning_task_deletion", reason_codes)

    def test_final_bundle_rejects_unknown_journal_commit_and_whitespace(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "invalid-planning"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        (task / "prd.md").write_text("# Invalid fixture  \n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "invalid planning fixture")
        self.write_session(root, base, commit_in_journal="deadbee")
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "invalid fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn("bookkeeping_whitespace_invalid", payload["reasonCodes"])
        self.assertIn("journal_commit_unknown", payload["reasonCodes"])
