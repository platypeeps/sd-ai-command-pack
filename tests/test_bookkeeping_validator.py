from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

json = _support.json
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
    ) -> None:
        workspace = root / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        journal_commit = commit_in_journal or commit
        (workspace / "journal-1.md").write_text(
            "\n".join(
                [
                    "# Development Journal",
                    "",
                    "## Session 1: Validate bookkeeping",
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
                    f"| `{journal_commit[:12]}` | fixture work |",
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
            ),
            encoding="utf-8",
        )
        (workspace / "index.md").write_text(
            "\n".join(
                [
                    "# Sessions",
                    "",
                    "| # | Date | Title | Commits | Branch |",
                    "|---|------|-------|---------|--------|",
                    f"| 1 | 2026-07-25 | Validate bookkeeping | `{journal_commit[:12]}` | `fixture` |",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def run_validator(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                self.node,
                "scripts/sd-ai-command-pack-review-preflight.mjs",
                *args,
                "--json",
            ],
            cwd=root,
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
        self.assertIn("[--repo <repo-root>]", result.stdout)

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
