from __future__ import annotations

import importlib.util
import sys

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

_ELIGIBILITY_SCRIPT = PACK_ROOT / "scripts/sd-ai-command-pack-pr-eligibility.py"
_eligibility_module = None


def eligibility_module():
    """Load the eligibility script once so receipt-consumption tests can call it."""
    global _eligibility_module
    if _eligibility_module is None:
        spec = importlib.util.spec_from_file_location(
            "sd_ai_command_pack_pr_eligibility_for_bookkeeping_tests",
            _ELIGIBILITY_SCRIPT,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {_ELIGIBILITY_SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        sys.path.insert(0, str(_ELIGIBILITY_SCRIPT.parent))
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        _eligibility_module = module
    return _eligibility_module


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
        # exist_ok: a fixture that records two separate journal-writing
        # commits (e.g. AC3's two-touch case) calls this helper twice against
        # the same repo; the second call must overwrite, not fail.
        workspace.mkdir(parents=True, exist_ok=True)
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
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
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
            env={**os.environ, **(extra_env or {})},
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
        self.assertNotIn("task_context_seed", payload["reasonCodes"])

        (child / "implement.jsonl").write_text(
            '{"_example":{"file":"src/example.py"}}\n'
            '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
            encoding="utf-8",
        )
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        payload = json.loads(result.stdout)
        self.assertIn("task_context_seed", payload["reasonCodes"])

        # A lone _example scaffold is advisory in any lifecycle phase now
        # (finding #5): moving to in_progress with a still-lone scaffold no
        # longer raises task_context_seed.
        (child / "implement.jsonl").write_text(
            '{"_example":{"file":"src/example.py"}}\n', encoding="utf-8"
        )
        child_record["status"] = "in_progress"
        child_record["branch"] = "codex/child-fixture"
        (child / "task.json").write_text(
            json.dumps(child_record, indent=2) + "\n", encoding="utf-8"
        )
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        payload = json.loads(result.stdout)
        self.assertNotIn("task_context_seed", payload["reasonCodes"])

        # A seed row MIXED with a real row still raises it while in_progress.
        (child / "implement.jsonl").write_text(
            '{"_example":{"file":"src/example.py"}}\n'
            '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
            encoding="utf-8",
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

    def write_completion_ready_task(
        self, root: Path, task_dir: str, prd: str, *, name: str | None = None
    ) -> Path:
        slug = task_dir.rsplit("/", 1)[-1]
        derived = name or slug[6:] if slug[:6].count("-") == 2 else slug
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                derived,
                status="in_progress",
                branch=f"codex/{slug}",
                completed_at=None,
            ),
        )
        (task / "prd.md").write_text(prd, encoding="utf-8")
        return task

    def test_pre_archive_passes_when_every_acceptance_criterion_checked(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-acceptance-complete"
        self.write_completion_ready_task(
            root,
            task_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [x] The parser rejects malformed input with a typed error.\n"
            "- [x] Focused tests cover the valid, empty, and malformed cases.\n\n"
            "## Post-archive handoff\n\n"
            "- Merge the reviewed head through `sd-housekeeping`, then delete "
            "the branch and synchronize the default branch.\n",
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["reasonCodes"], ["pre_archive_valid"])

    def test_pre_archive_rejects_unchecked_acceptance_without_mutation(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-acceptance-incomplete"
        task = self.write_completion_ready_task(
            root,
            task_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [x] Implementation and focused tests are complete.\n"
            "- [ ] The changelog entry is written.\n",
        )
        prd_before = (task / "prd.md").read_text(encoding="utf-8")
        before = self.git_output(root, "status", "--porcelain")

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("pre_archive_acceptance_incomplete", payload["reasonCodes"])
        self.assertIn("unchecked required item", result.stdout)
        # Read-only: the PRD, task, journal, and Git state are untouched.
        self.assertEqual((task / "prd.md").read_text(encoding="utf-8"), prd_before)
        self.assertEqual(self.git_output(root, "status", "--porcelain"), before)
        self.assertTrue((root / task_dir).is_dir())
        self.assertFalse((root / ".trellis/workspace").exists())

    def test_pre_archive_accepts_post_archive_handoff_prose(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-handoff-prose"
        self.write_completion_ready_task(
            root,
            task_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [x] The stabilized release candidate builds with current ledger "
            "evidence.\n\n"
            "## Post-archive handoff\n\n"
            "- Merge through `sd-housekeeping`, publish the successor release, "
            "then run the bounded fleet refresh once.\n"
            "- Close the superseded release-candidate PRs after the successor "
            "merges.\n",
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reasonCodes"], ["pre_archive_valid"])

    def test_pre_archive_rejects_checkbox_in_post_archive_handoff(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-handoff-checkbox"
        self.write_completion_ready_task(
            root,
            task_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [x] Implementation is complete.\n\n"
            "## Post-archive handoff\n\n"
            "- [ ] Merge the branch through `sd-housekeeping`.\n",
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn("pre_archive_acceptance_malformed", payload["reasonCodes"])
        self.assertNotIn("pre_archive_acceptance_incomplete", payload["reasonCodes"])
        self.assertIn("must be prose bullets", result.stdout)

    def test_pre_archive_fails_closed_on_malformed_and_duplicate_sections(self) -> None:
        root = self.make_validator_repo()
        malformed_dir = ".trellis/tasks/07-25-acceptance-malformed"
        self.write_completion_ready_task(
            root,
            malformed_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [y] A criterion with an invalid checkbox marker.\n"
            "- [] A criterion with an empty checkbox.\n",
        )
        result = self.run_validator(root, "pre-archive", "--task-dir", malformed_dir)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "pre_archive_acceptance_malformed",
            json.loads(result.stdout)["reasonCodes"],
        )

        duplicate_dir = ".trellis/tasks/07-25-acceptance-duplicate"
        self.write_completion_ready_task(
            root,
            duplicate_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n- [x] First list.\n\n"
            "## Acceptance Criteria\n\n- [x] Second list.\n",
        )
        result = self.run_validator(root, "pre-archive", "--task-dir", duplicate_dir)
        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertIn("pre_archive_acceptance_malformed", payload["reasonCodes"])
        self.assertIn("allows exactly one", result.stdout)

    def test_pre_archive_ignores_unchecked_boxes_outside_canonical_section(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-noncanonical-boxes"
        self.write_completion_ready_task(
            root,
            task_dir,
            "# Fixture\n\n## Notes\n\n- [ ] A stray idea, not a completion "
            "criterion.\n\n"
            "## Acceptance Criteria\n\n- [x] The only required criterion.\n\n"
            "## Examples\n\nAuthoring format:\n\n```\n- [ ] example criterion\n"
            "```\n",
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"], ["pre_archive_valid"]
        )

    def test_pre_archive_regression_pr187_merge_criterion(self) -> None:
        root = self.make_validator_repo()
        task_dir = ".trellis/tasks/07-25-pr187-regression"
        task = self.write_completion_ready_task(
            root,
            task_dir,
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [x] The coordinator refresh lands with green CI.\n"
            "- [ ] Merge the reviewed exact head through sd-housekeeping and "
            "delete the branch.\n",
        )

        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "pre_archive_acceptance_incomplete",
            json.loads(result.stdout)["reasonCodes"],
        )

        # Reconciling the merge obligation into the prose handoff clears the
        # contradiction Copilot flagged on rwbp-coordinator PR #187.
        (task / "prd.md").write_text(
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [x] The coordinator refresh lands with green CI.\n\n"
            "## Post-archive handoff\n\n"
            "- Merge the reviewed exact head through `sd-housekeeping`, then "
            "delete the branch.\n",
            encoding="utf-8",
        )
        result = self.run_validator(root, "pre-archive", "--task-dir", task_dir)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"], ["pre_archive_valid"]
        )

    def test_planning_finalization_ignores_acceptance_readiness(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "planning-acceptance"
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
        # A planning task legitimately carries unchecked acceptance criteria; the
        # completion-scoped gate must not evaluate them during planning finalization.
        (task / "prd.md").write_text(
            "# Fixture\n\n## Acceptance Criteria\n\n"
            "- [ ] `prd.md`, `design.md`, and `implement.md` capture the contract.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "plan fixture work")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record planning journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "planning", "--base", base, "--head", head
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])

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

    def run_completion_branch_bundle(
        self,
        *,
        source_branch: str | None,
        drop_source_branch: bool = False,
        archived_updates: dict[str, object] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Archive one task and validate the completion bundle.

        The move changes ``status`` and ``completedAt``; ``archived_updates``
        adds whatever else the caller wants inside the archive commit.
        """
        root = self.make_validator_repo()
        name = "branch-transition"
        record = self.task_record(
            name,
            status="in_progress",
            branch=source_branch,
            completed_at=None,
        )
        if drop_source_branch:
            del record["branch"]
        active = self.write_task(root, f".trellis/tasks/07-25-{name}", record)
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        base = self.git_output(root, "rev-parse", "HEAD")

        archive = root / f".trellis/tasks/archive/2026-07/07-25-{name}"
        archive.parent.mkdir(parents=True)
        active.rename(archive)
        archived = json.loads((archive / "task.json").read_text(encoding="utf-8"))
        archived["status"] = "completed"
        archived["completedAt"] = "2026-07-25"
        archived.update(archived_updates or {})
        (archive / "task.json").write_text(
            json.dumps(archived, indent=2) + "\n", encoding="utf-8"
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "archive fixture")
        self.write_session(root, base)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        return self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            base,
            "--head",
            head,
        )

    def assert_archive_identity_rejected(
        self, result: subprocess.CompletedProcess[str]
    ) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid", result.stdout)
        self.assertIn(
            "completion_archive_identity_changed",
            payload["reasonCodes"],
            result.stdout,
        )

    def test_completion_bundle_allows_branch_recorded_during_archive(self) -> None:
        # The pre-archive gate demands a non-empty branch, so an operator who
        # satisfies it after the finalization base is captured lands the write
        # inside the archive commit. That must not read as smuggled content.
        result = self.run_completion_branch_bundle(
            source_branch=None,
            archived_updates={"branch": "codex/completion-fixture"},
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid", result.stdout)
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])

    def test_completion_bundle_rejects_branch_rewritten_during_archive(self) -> None:
        self.assert_archive_identity_rejected(
            self.run_completion_branch_bundle(
                source_branch="codex/a",
                archived_updates={"branch": "codex/b"},
            )
        )

    def test_completion_bundle_rejects_branch_erased_during_archive(self) -> None:
        self.assert_archive_identity_rejected(
            self.run_completion_branch_bundle(
                source_branch="codex/a",
                archived_updates={"branch": None},
            )
        )

    def test_completion_bundle_rejects_unrelated_field_change_during_archive(
        self,
    ) -> None:
        self.assert_archive_identity_rejected(
            self.run_completion_branch_bundle(
                source_branch="codex/a",
                archived_updates={"title": "Rewritten during the archive move"},
            )
        )

    def test_completion_bundle_rejects_branch_added_to_keyless_record(self) -> None:
        # An absent key is a distinct state from an explicit null, and only the
        # latter is the deadlock this tolerance exists for. Pins `=== null`
        # against a later simplification to `== null`, which also matches
        # `undefined`.
        self.assert_archive_identity_rejected(
            self.run_completion_branch_bundle(
                source_branch=None,
                drop_source_branch=True,
                archived_updates={"branch": "codex/a"},
            )
        )

    def test_completion_bundle_allows_null_branch_through_archive(self) -> None:
        result = self.run_completion_branch_bundle(source_branch=None)

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid", result.stdout)
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])

    IN_PLACE_TASK_DIR = ".trellis/tasks/07-25-in-place-completion"

    def run_in_place_bundle(
        self,
        *,
        branch_before: str | None,
        status_after: str,
        branch_after: str | None,
    ) -> subprocess.CompletedProcess[str]:
        """Touch an in_progress task's own directory with no archive move.

        ``branch_before``/``status_after``/``branch_after`` let callers pin the
        Decision 4 invariant: status and branch must stay byte-identical
        between base and head for this bundle shape (no transition tolerance,
        unlike the archive-move shape).
        """
        root = self.make_validator_repo()
        name = "in-place-completion"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="in_progress",
                branch=branch_before,
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        base = self.git_output(root, "rev-parse", "HEAD")

        record = json.loads((task / "task.json").read_text(encoding="utf-8"))
        record["status"] = status_after
        record["branch"] = branch_after
        (task / "task.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        # Always touch prd.md too, so the identity-preserving success fixture
        # (status/branch unchanged) still produces a real bookkeeping commit
        # instead of an empty diff.
        (task / "prd.md").write_text(
            "# Fixture\n\nValidated task.\n\n- [x] Bookkeeping touch recorded.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record bookkeeping touch")

        self.write_session(root, base)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        return self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            base,
            "--head",
            head,
        )

    def test_completion_bundle_validates_in_place_task_touch(self) -> None:
        # AC1: an in_progress task's own bookkeeping touch (no archive move)
        # validates directly through the widened normal path.
        result = self.run_in_place_bundle(
            branch_before="codex/in-place-completion",
            status_after="in_progress",
            branch_after="codex/in-place-completion",
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid", result.stdout)
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])
        self.assertNotIn("completionSubtype", payload["evidence"])
        self.assertEqual(
            payload["evidence"]["taskDirectories"], [self.IN_PLACE_TASK_DIR]
        )

    def test_completion_bundle_rejects_status_transition_in_place(self) -> None:
        # AC10 / Decision 4: unlike the archive-move shape, this shape
        # tolerates no in_progress -> review transition.
        result = self.run_in_place_bundle(
            branch_before="codex/in-place-completion",
            status_after="review",
            branch_after="codex/in-place-completion",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid", result.stdout)
        self.assertIn("completion_source_lifecycle_invalid", payload["reasonCodes"])

    def test_completion_bundle_rejects_branch_newly_recorded_in_place(self) -> None:
        # AC10 / Decision 4: unlike the archive-move shape, this shape has no
        # "newly recorded branch" exception.
        result = self.run_in_place_bundle(
            branch_before=None,
            status_after="in_progress",
            branch_after="codex/newly-recorded",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid", result.stdout)
        self.assertIn("completion_task_identity_changed", payload["reasonCodes"])

    def make_post_archive_successor_repo(
        self,
        *,
        prehistory_commits: int = 0,
        corrupt_archive: bool = False,
        unarchive_after: bool = False,
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
        if unarchive_after:
            # Reproduce the PR #301 shape: rename the task directory back from
            # archive/ to its active location AND restore the original active
            # task.json content, so task.json is a *modified* rename (R09x), not
            # an identical-content R100. This is the direction the fix must detect.
            (root / archive_dir).rename(root / active_dir)
            restored = root / active_dir / "task.json"
            record = json.loads(restored.read_text(encoding="utf-8"))
            record["status"] = "in_progress"
            record["completedAt"] = None
            restored.write_text(
                json.dumps(record, indent=2) + "\n", encoding="utf-8"
            )
            self.run_git(root, "add", ".trellis/tasks")
            self.run_git(root, "commit", "-m", 'Revert "archive fixture"')
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
        self.assertRegex(
            evidence["repository"]["lineageDigest"], r"^sha256:[0-9a-f]{64}$"
        )
        self.assertEqual(self.git_output(root, "status", "--porcelain"), before)

        relocated = root / "relocated-checkout"
        clone = subprocess.run(
            ["git", "clone", "--quiet", str(root), str(relocated)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(clone.returncode, 0, clone.stdout)
        replay = self.run_validator(
            relocated,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
        )
        self.assertEqual(replay.returncode, 0, replay.stdout)
        replay_payload = json.loads(replay.stdout)
        self.assertEqual(replay_payload["evidence"]["repository"], evidence["repository"])

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

    def test_completion_successor_reports_unavailable_candidate_diff(self) -> None:
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        (root / "review-fix.txt").write_text("reviewed\n", encoding="utf-8")
        self.run_git(root, "add", "review-fix.txt")
        self.run_git(root, "commit", "-m", "fix review finding")
        head = self.git_output(root, "rev-parse", "HEAD")
        archive_oid = self.git_output(root, "rev-parse", f"{bookkeeping_head}^")
        archive_tree = self.git_output(root, "rev-parse", f"{archive_oid}^{{tree}}")
        (root / ".git/objects" / archive_tree[:2] / archive_tree[2:]).unlink()

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
        self.assertEqual(
            payload["reasonCodes"], ["completion_successor_history_unavailable"]
        )
        self.assertEqual(payload["status"], "indeterminate")

    def test_completion_successor_reports_unavailable_commit_subject(self) -> None:
        root, _, _ = self.make_post_archive_successor_repo()
        (root / "review-fix.txt").write_text("reviewed\n", encoding="utf-8")
        self.run_git(root, "add", "review-fix.txt")
        self.run_git(root, "commit", "-m", "fix review finding")
        head = self.git_output(root, "rev-parse", "HEAD")
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / ".test-bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "log" ] && [ "$2" = "-1" ] '
            '&& [ "$3" = "--format=%s" ]; then\n'
            '  echo "fatal: injected subject failure" >&2\n'
            "  exit 73\n"
            "fi\n"
            f"exec {json.dumps(real_git)} \"$@\"\n",
            encoding="utf-8",
        )
        git_stub.chmod(0o755)

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
            extra_env={"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["reasonCodes"], ["completion_successor_history_unavailable"]
        )
        self.assertEqual(payload["status"], "indeterminate")
        subject_findings = [
            finding
            for finding in payload["findings"]
            if "subject for successor commit" in finding["message"]
        ]
        self.assertEqual(len(subject_findings), 1, payload["findings"])
        self.assertIn("exited 73", subject_findings[0]["message"])
        self.assertIn("fatal: injected subject failure", subject_findings[0]["message"])
        self.assert_failure_receipt_shape(payload)

    def test_completion_successor_reports_unavailable_successor_diff(self) -> None:
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        (root / "review-fix.txt").write_text("reviewed\n", encoding="utf-8")
        self.run_git(root, "add", "review-fix.txt")
        self.run_git(root, "commit", "-m", "fix review finding")
        head = self.git_output(root, "rev-parse", "HEAD")
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / ".test-diff-bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n"
            f"if [ \"$1\" = diff ] && [ \"$5\" = {bookkeeping_head} ] "
            f"&& [ \"$6\" = {head} ]; then\n"
            "  exit 73\n"
            "fi\n"
            f"exec {json.dumps(real_git)} \"$@\"\n",
            encoding="utf-8",
        )
        git_stub.chmod(0o755)

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
            extra_env={"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["reasonCodes"], ["completion_successor_history_unavailable"]
        )
        self.assertEqual(payload["status"], "indeterminate")

    RECEIPT_KEYS = {
        "schemaVersion",
        "kind",
        "status",
        "command",
        "mode",
        "reasonCodes",
        "evidence",
        "findings",
        "advisories",
    }

    def assert_failure_receipt_shape(self, payload: dict) -> None:
        # The git-failure enrichment must never change the receipt contract:
        # same schema version, same top-level keys, and only known
        # dispositions -- detail lands inside existing message strings.
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(set(payload), self.RECEIPT_KEYS)
        for finding in payload["findings"]:
            self.assertIn(
                finding["disposition"], {"invalid", "indeterminate"}, finding
            )

    def write_git_stub(self, root: Path, name: str, body: str) -> Path:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / name
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n" + body + f"exec {json.dumps(real_git)} \"$@\"\n",
            encoding="utf-8",
        )
        git_stub.chmod(0o755)
        return stub_bin

    def stub_path_env(self, stub_bin: Path) -> dict[str, str]:
        return {"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"}

    def test_completion_recovery_names_git_failure_for_archive_delta(self) -> None:
        # Fingerprint 1 of the kcov-lane flake: the candidate ARCHIVE delta
        # diff fails mid-scan and the old finding said only "could not
        # inspect". The stub fails exactly the anchor window's
        # baseOid..archiveOid pair: the direct final-bundle diff uses
        # identical oids and the scan's journal-delta diff (archiveOid..
        # bookkeepingHeadOid) runs first, so any broader stub would fire at
        # the wrong site.
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        (root / "review-fix.txt").write_text("reviewed\n", encoding="utf-8")
        self.run_git(root, "add", "review-fix.txt")
        self.run_git(root, "commit", "-m", "fix review finding")
        head = self.git_output(root, "rev-parse", "HEAD")
        archive_commit = self.git_output(root, "rev-parse", f"{bookkeeping_head}^")
        work_commit = self.git_output(root, "rev-parse", f"{bookkeeping_head}~2")
        stub_bin = self.write_git_stub(
            root,
            ".test-archive-delta-bin",
            f"if [ \"$1\" = diff ] && [ \"$5\" = {work_commit} ] "
            f"&& [ \"$6\" = {archive_commit} ]; then\n"
            '  echo "fatal: injected diff failure" >&2\n'
            "  exit 128\n"
            "fi\n",
        )

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
            extra_env=self.stub_path_env(stub_bin),
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["reasonCodes"], ["completion_successor_history_unavailable"]
        )
        self.assertEqual(payload["status"], "indeterminate")
        [finding] = payload["findings"]
        self.assertIn("candidate archive delta", finding["message"])
        self.assertIn("exited 128", finding["message"])
        self.assertIn("fatal: injected diff failure", finding["message"])
        self.assert_failure_receipt_shape(payload)

    def test_final_bundle_names_git_failure_for_direct_diff(self) -> None:
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        base = self.git_output(root, "rev-parse", f"{bookkeeping_head}^")
        stub_bin = self.write_git_stub(
            root,
            ".test-direct-diff-bin",
            'if [ "$1" = diff ] && [ "$2" = --raw ]; then\n'
            '  echo "fatal: injected direct diff failure" >&2\n'
            "  exit 128\n"
            "fi\n",
        )

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            base,
            "--head",
            bookkeeping_head,
            extra_env=self.stub_path_env(stub_bin),
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reasonCodes"], ["bundle_diff_unavailable"])
        [finding] = payload["findings"]
        self.assertIn("finalization delta", finding["message"])
        self.assertIn("exited 128", finding["message"])
        self.assertIn("fatal: injected direct diff failure", finding["message"])
        self.assert_failure_receipt_shape(payload)

    def test_git_failure_stderr_is_bounded_in_findings(self) -> None:
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        base = self.git_output(root, "rev-parse", f"{bookkeeping_head}^")
        long_line = "A" * 300
        stub_bin = self.write_git_stub(
            root,
            ".test-bounded-bin",
            'if [ "$1" = diff ] && [ "$2" = --raw ]; then\n'
            f'  echo "{long_line}" >&2\n'
            '  echo "second stderr line" >&2\n'
            "  exit 128\n"
            "fi\n",
        )

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            base,
            "--head",
            bookkeeping_head,
            extra_env=self.stub_path_env(stub_bin),
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        [finding] = payload["findings"]
        self.assertIn("A" * 200 + "...", finding["message"])
        self.assertNotIn("A" * 201, finding["message"])
        self.assertNotIn("second stderr line", finding["message"])
        self.assert_failure_receipt_shape(payload)

    def test_git_failure_detail_is_not_stale_across_invocations(self) -> None:
        # Two runBookkeepingValidator calls in ONE process: the first fails
        # its diff with a known stderr (positive control: pre-change code
        # embedded no stderr anywhere, so this half fails against the old
        # script), the second returns status-0 MALFORMED diff output. The
        # malformed null must not inherit the first call's failure detail.
        root, _, bookkeeping_head = self.make_post_archive_successor_repo()
        base = self.git_output(root, "rev-parse", f"{bookkeeping_head}^")
        marker = root / ".stale-slot-marker"
        stub_bin = self.write_git_stub(
            root,
            ".test-stale-slot-bin",
            'if [ "$1" = diff ] && [ "$2" = --raw ]; then\n'
            f"  if [ -f {json.dumps(str(marker))} ]; then\n"
            "    printf 'not-a-raw-record'\n"
            "    exit 0\n"
            "  fi\n"
            '  echo "fatal: injected stale stderr" >&2\n'
            "  exit 128\n"
            "fi\n",
        )
        runner = root / "stale-slot-runner.mjs"
        runner.write_text(
            "import { runBookkeepingValidator } from"
            " './scripts/sd-ai-command-pack-review-preflight.mjs';\n"
            "import { writeFileSync } from 'node:fs';\n"
            "const [base, head, marker] = process.argv.slice(2);\n"
            "const first = runBookkeepingValidator("
            "{ command: 'final-bundle', mode: 'completion', base, head });\n"
            "writeFileSync(marker, 'switch\\n');\n"
            "const second = runBookkeepingValidator("
            "{ command: 'final-bundle', mode: 'completion', base, head });\n"
            "console.log(JSON.stringify({ first, second }));\n",
            encoding="utf-8",
        )

        env = dict(os.environ)
        env.update(self.stub_path_env(stub_bin))
        completed = subprocess.run(
            [self.node, str(runner), base, bookkeeping_head, str(marker)],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        first_messages = [f["message"] for f in payload["first"]["findings"]]
        self.assertTrue(
            any("fatal: injected stale stderr" in message for message in first_messages),
            first_messages,
        )
        self.assertIn("bundle_diff_malformed", payload["second"]["reasonCodes"])
        for finding in payload["second"]["findings"]:
            self.assertNotIn("fatal: injected stale stderr", finding["message"])

    def test_completion_successor_names_git_failure_for_range(self) -> None:
        root, _, _ = self.make_post_archive_successor_repo()
        (root / "review-fix.txt").write_text("reviewed\n", encoding="utf-8")
        self.run_git(root, "add", "review-fix.txt")
        self.run_git(root, "commit", "-m", "fix review finding")
        head = self.git_output(root, "rev-parse", "HEAD")
        stub_bin = self.write_git_stub(
            root,
            ".test-range-bin",
            'if [ "$1" = rev-list ] && [ "$2" = --first-parent ] '
            '&& [ "$3" = --reverse ]; then\n'
            '  echo "fatal: injected rev-list failure" >&2\n'
            "  exit 73\n"
            "fi\n",
        )

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
            extra_env=self.stub_path_env(stub_bin),
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["reasonCodes"], ["completion_successor_history_unavailable"]
        )
        range_findings = [
            finding
            for finding in payload["findings"]
            if "completion-successor commit range" in finding["message"]
        ]
        self.assertEqual(len(range_findings), 1, payload["findings"])
        self.assertIn("exited 73", range_findings[0]["message"])
        self.assertIn("fatal: injected rev-list failure", range_findings[0]["message"])
        self.assert_failure_receipt_shape(payload)

    def test_run_git_failure_includes_repo_state_context(self) -> None:
        root = self.make_validator_repo()
        (root / ".git/HEAD").write_text("garbage\n", encoding="utf-8")

        with self.assertRaises(AssertionError) as caught:
            self.run_git(root, "commit", "--allow-empty", "-m", "context probe")

        message = str(caught.exception)
        self.assertIn("git repo-state context", message)
        self.assertIn("HEAD bytes", message)
        self.assertIn("garbage", message)

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
        # A one-commit repo with no task and no archive ever created:
        # shapedTailCount is structurally always 0 here (definitively, no Git
        # errors), so the active-task-ambiguous fallback correctly supersedes
        # the old generic anchor-missing diagnostic. Intentional, documented
        # behavior change (design.md's Control Flow "Round 3 note"), not a
        # regression.
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
            ["completion_successor_active_task_ambiguous"],
        )

    def test_completion_successor_flags_reverted_anchor(self) -> None:
        # PR #301 witness: the successor range un-archives the exact task the
        # candidate anchor archived. Direction-aware detection must name the
        # revert AND keep reporting the scope violation for the same paths.
        root, _, _ = self.make_post_archive_successor_repo(unarchive_after=True)
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        codes = json.loads(result.stdout)["reasonCodes"]
        self.assertIn("completion_successor_anchor_reverted", codes)
        self.assertIn("completion_successor_scope_invalid", codes)
        # The revert diagnosis is prepended so the actionable cause reads first.
        self.assertEqual(codes[0], "completion_successor_anchor_reverted")

    def test_completion_successor_rejects_pure_unarchive_as_anchor(self) -> None:
        # A commit that only moves a task out of archive/ is not an archive
        # commit (C1/R1). With the direction-aware predicate the pure un-archive
        # is no longer a shaped archive tail, so recovery falls through to the
        # active-task path, which diagnoses the now-active task rather than
        # dressing the un-archive up as a reverted archive anchor.
        root = self.make_validator_repo()
        name = "completion-successor"
        active_dir = f".trellis/tasks/07-25-{name}"
        archive_dir = f".trellis/tasks/archive/2026-07/07-25-{name}"
        self.write_task(
            root,
            archive_dir,
            self.task_record(
                name,
                status="completed",
                branch="codex/completion-successor",
                completed_at="2026-07-25",
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "seed archived task")

        (root / archive_dir).rename(root / active_dir)
        restored = root / active_dir / "task.json"
        record = json.loads(restored.read_text(encoding="utf-8"))
        record["status"] = "in_progress"
        record["completedAt"] = None
        restored.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", 'Revert "archive"')

        work_commit = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        codes = json.loads(result.stdout)["reasonCodes"]
        self.assertNotIn("completion_successor_anchor_reverted", codes)
        self.assertEqual(codes, ["completion_successor_active_task_anchor_missing"])

    def test_completion_successor_indeterminate_range_is_not_a_revert(self) -> None:
        # An un-archive whose successor range cannot be inspected must fail closed
        # as history_unavailable and must never be dressed up as a revert.
        root, _, bookkeeping_head = self.make_post_archive_successor_repo(
            unarchive_after=True
        )
        head = self.git_output(root, "rev-parse", "HEAD")
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        stub_bin = root / ".test-diff-bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text(
            "#!/bin/sh\n"
            f"if [ \"$1\" = diff ] && [ \"$5\" = {bookkeeping_head} ] "
            f"&& [ \"$6\" = {head} ]; then\n"
            "  exit 73\n"
            "fi\n"
            f"exec {json.dumps(real_git)} \"$@\"\n",
            encoding="utf-8",
        )
        git_stub.chmod(0o755)

        result = self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "completion",
            "--base",
            head,
            "--head",
            head,
            extra_env={"PATH": f"{stub_bin}{os.pathsep}{os.environ['PATH']}"},
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["reasonCodes"], ["completion_successor_history_unavailable"]
        )
        self.assertEqual(payload["status"], "indeterminate")
        self.assertNotIn(
            "completion_successor_anchor_reverted", payload["reasonCodes"]
        )

    def test_completion_successor_delete_only_is_not_a_revert(self) -> None:
        # Half an un-archive: the archived task.json leaves but no active copy
        # arrives. Cleanup, not a revert — scope_invalid without the revert code.
        root, archive_dir, _ = self.make_post_archive_successor_repo()
        (root / archive_dir / "task.json").unlink()
        self.run_git(root, "add", "-A", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "delete archived task json")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        codes = json.loads(result.stdout)["reasonCodes"]
        self.assertIn("completion_successor_scope_invalid", codes)
        self.assertNotIn("completion_successor_anchor_reverted", codes)

    def test_completion_successor_added_active_copy_is_not_a_revert(self) -> None:
        # Half an un-archive: an active task.json is added (A) while the archive
        # path stays untouched. A duplicate, not a revert.
        root, _, _ = self.make_post_archive_successor_repo()
        active_dir = ".trellis/tasks/07-25-completion-successor"
        self.write_task(
            root,
            active_dir,
            self.task_record(
                "completion-successor",
                status="in_progress",
                branch="codex/completion-successor",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add active copy while archive remains")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        codes = json.loads(result.stdout)["reasonCodes"]
        self.assertIn("completion_successor_scope_invalid", codes)
        self.assertNotIn("completion_successor_anchor_reverted", codes)

    def test_completion_successor_revert_does_not_mask_runtime_write(self) -> None:
        # A revert that also persists forbidden .runtime/ state must report both
        # the revert AND the independent scope violation — the new code cannot
        # absorb an unrelated failure.
        root, _, _ = self.make_post_archive_successor_repo(unarchive_after=True)
        runtime = root / ".trellis/.runtime"
        runtime.mkdir(parents=True)
        (runtime / "finish-work.json").write_text("{}\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/.runtime/finish-work.json")
        self.run_git(root, "commit", "-m", "persist forbidden finish-work state")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        codes = json.loads(result.stdout)["reasonCodes"]
        self.assertIn("completion_successor_anchor_reverted", codes)
        self.assertIn("completion_successor_scope_invalid", codes)
        self.assertIn(".trellis/.runtime/finish-work.json", result.stdout)

    def test_active_task_successor_recovers_single_touch(self) -> None:
        # AC2: a single touch+journal pair recovers via the new subtype;
        # historicalBase resolves to the commit before the prd.md touch.
        root = self.make_validator_repo()
        name = "active-task-successor"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/active-task-successor",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        fixture_work = self.git_output(root, "rev-parse", "HEAD")

        (task / "prd.md").write_text(
            "# Fixture\n\nValidated task.\n\n- [x] Bookkeeping touch recorded.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record bookkeeping touch")

        self.write_session(root, fixture_work)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])
        evidence = payload["evidence"]
        self.assertEqual(evidence["completionSubtype"], "active-task-review-successor")
        self.assertEqual(evidence["taskDirectories"], [task_dir])
        self.assertEqual(
            evidence["completionAnchor"],
            {
                "source": "active-task-range",
                "taskDir": task_dir,
                "historicalBase": fixture_work,
                "headOid": head,
            },
        )

    def test_active_task_successor_recovers_oldest_of_two_touches(self) -> None:
        # AC3: two touches inside one range; historicalBase resolves to
        # before the OLDER touch (the oldest qualifying one within the
        # bound, not the nearest), and both journal sessions are confirmed.
        root = self.make_validator_repo()
        name = "active-task-two-touches"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/active-task-two-touches",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        fixture_work = self.git_output(root, "rev-parse", "HEAD")

        (task / "prd.md").write_text(
            "# Fixture\n\nValidated task.\n\n- [x] First touch recorded.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record first bookkeeping touch")

        self.write_session(root, fixture_work)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record first fixture journal")

        (root / "ordinary.txt").write_text("ordinary work\n", encoding="utf-8")
        self.run_git(root, "add", "ordinary.txt")
        self.run_git(root, "commit", "-m", "ordinary repo work")

        (task / "prd.md").write_text(
            "# Fixture\n\nValidated task.\n\n"
            "- [x] First touch recorded.\n- [x] Second touch recorded.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record second bookkeeping touch")
        touch2 = self.git_output(root, "rev-parse", "HEAD")

        self.write_sessions(root, [[fixture_work], [touch2]])
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record second fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])
        evidence = payload["evidence"]
        self.assertEqual(evidence["completionSubtype"], "active-task-review-successor")
        # historicalBase resolving to before touch1 (not touch2) proves the
        # range spans both touches and both journal-recording commits without
        # rejecting on the second journal write; evidence.journalSessions is
        # not part of this subtype's shape (design.md's explicit evidence
        # list), unlike the archive-successor subtype's separate anchor.
        self.assertEqual(evidence["completionAnchor"]["historicalBase"], fixture_work)

    def test_active_task_successor_recovers_when_task_created_and_started_in_window(
        self,
    ) -> None:
        # AC3b / AC11, the most serious round-2 finding: task.py create
        # (status planning) and task.py start (-> in_progress) both touch the
        # task's own directory too. historicalBase must resolve to after
        # start, never to the creation or start commit itself -- this is the
        # ordinary shape for any task young enough to fit in the search
        # window, not an edge case.
        root = self.make_validator_repo()
        name = "active-task-created-started"
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
        self.run_git(root, "commit", "-m", "create task")

        record = json.loads((task / "task.json").read_text(encoding="utf-8"))
        record["status"] = "in_progress"
        (task / "task.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "start task")
        start_commit = self.git_output(root, "rev-parse", "HEAD")

        (task / "prd.md").write_text(
            "# Fixture\n\nValidated task.\n\n- [x] Bookkeeping touch recorded.\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record bookkeeping touch")

        self.write_session(root, start_commit)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["reasonCodes"], ["completion_bundle_valid"])
        evidence = payload["evidence"]
        self.assertEqual(evidence["completionSubtype"], "active-task-review-successor")
        self.assertEqual(evidence["completionAnchor"]["historicalBase"], start_commit)

    def test_active_task_successor_rejects_second_active_task_touch(self) -> None:
        # AC4(a): a range touching a second, unrelated task directory blocks.
        # The sibling is `planning` (not in_progress/review) so discovery
        # itself still resolves to exactly one candidate; the violation is
        # caught by the per-commit scope check, not discovery ambiguity.
        root = self.make_validator_repo()
        name = "active-task-scope"
        task_dir = f".trellis/tasks/07-25-{name}"
        other_dir = ".trellis/tasks/07-26-active-task-scope-other"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                name, status="in_progress", branch="codex/active-task-scope", completed_at=None
            ),
        )
        self.write_task(
            root,
            other_dir,
            self.task_record(
                "active-task-scope-other", status="planning", branch=None, completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        fixture_work = self.git_output(root, "rev-parse", "HEAD")

        (root / task_dir / "prd.md").write_text(
            "# Fixture\n\n- [x] Touch.\n", encoding="utf-8"
        )
        (root / other_dir / "prd.md").write_text(
            "# Fixture\n\n- [x] Unrelated touch.\n", encoding="utf-8"
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "touch both tasks")

        self.write_session(root, fixture_work)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_scope_invalid",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_active_task_successor_rejects_archive_touch_in_range(self) -> None:
        # AC4(b): a range touching the archive blocks.
        root = self.make_validator_repo()
        name = "active-task-archive-scope"
        task_dir = f".trellis/tasks/07-25-{name}"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/active-task-archive-scope",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        fixture_work = self.git_output(root, "rev-parse", "HEAD")

        archive_dir = root / ".trellis/tasks/archive/2026-06/06-01-already-done"
        archive_dir.mkdir(parents=True)
        archived_record = self.task_record(
            "already-done",
            status="completed",
            branch="codex/already-done",
            completed_at="2026-06-01",
        )
        (archive_dir / "task.json").write_text(
            json.dumps(archived_record, indent=2) + "\n", encoding="utf-8"
        )
        (archive_dir / "prd.md").write_text("# Archived\n\nDone.\n", encoding="utf-8")
        (archive_dir / "implement.jsonl").write_text("", encoding="utf-8")
        (archive_dir / "check.jsonl").write_text("", encoding="utf-8")
        self.run_git(root, "add", ".trellis/tasks/archive")
        self.run_git(root, "commit", "-m", "seed pre-existing archive")

        (root / task_dir / "prd.md").write_text(
            "# Fixture\n\n- [x] Touch.\n", encoding="utf-8"
        )
        (archive_dir / "task.json").write_text(
            json.dumps({**archived_record, "notes": "mutated"}, indent=2) + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", task_dir, ".trellis/tasks/archive")
        self.run_git(root, "commit", "-m", "touch task and mutate archive")

        self.write_session(root, fixture_work)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_scope_invalid",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_active_task_successor_rejects_merge_commit_in_range(self) -> None:
        # AC4(c): a merge commit anywhere in the range blocks.
        root = self.make_validator_repo()
        name = "active-task-merge-scope"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/active-task-merge-scope",
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        fixture_work = self.git_output(root, "rev-parse", "HEAD")

        (task / "prd.md").write_text(
            "# Fixture\n\n- [x] Touch.\n", encoding="utf-8"
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record bookkeeping touch")

        self.run_git(root, "switch", "-c", "side-branch")
        (root / "side.txt").write_text("side\n", encoding="utf-8")
        self.run_git(root, "add", "side.txt")
        self.run_git(root, "commit", "-m", "side work")
        self.run_git(root, "switch", "main")
        self.run_git(root, "merge", "--no-ff", "side-branch", "-m", "merge side work")

        self.write_session(root, fixture_work)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_history_non_linear",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_active_task_successor_rejects_mutate_then_revert_in_range(self) -> None:
        # AC4(d): a forbidden-path mutation later reverted by another commit
        # in the same range still blocks -- proves the scope check is
        # per-commit, not a net diff a revert could evade.
        root = self.make_validator_repo()
        name = "active-task-revert-scope"
        task_dir = f".trellis/tasks/07-25-{name}"
        other_dir = ".trellis/tasks/07-26-active-task-revert-scope-other"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="in_progress",
                branch="codex/active-task-revert-scope",
                completed_at=None,
            ),
        )
        self.write_task(
            root,
            other_dir,
            self.task_record(
                "active-task-revert-scope-other",
                status="planning",
                branch=None,
                completed_at=None,
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        fixture_work = self.git_output(root, "rev-parse", "HEAD")

        (task / "prd.md").write_text(
            "# Fixture\n\n- [x] Touch.\n", encoding="utf-8"
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "record bookkeeping touch")

        original_other_prd = (root / other_dir / "prd.md").read_text(encoding="utf-8")
        (root / other_dir / "prd.md").write_text("mutated\n", encoding="utf-8")
        self.run_git(root, "add", other_dir)
        self.run_git(root, "commit", "-m", "forbidden mutation of unrelated task")

        (root / other_dir / "prd.md").write_text(original_other_prd, encoding="utf-8")
        self.run_git(root, "add", other_dir)
        self.run_git(root, "commit", "-m", "revert forbidden mutation")

        self.write_session(root, fixture_work)
        self.run_git(root, "add", ".trellis/workspace")
        self.run_git(root, "commit", "-m", "record fixture journal")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "completion_successor_scope_invalid",
            json.loads(result.stdout)["reasonCodes"],
        )

    def test_active_task_successor_ambiguous_when_no_qualifying_task(self) -> None:
        # AC5, "zero" variant: one task exists but is not in_progress/review.
        root = self.make_validator_repo()
        name = "active-task-planning-only"
        task_dir = f".trellis/tasks/07-25-{name}"
        self.write_task(
            root,
            task_dir,
            self.task_record(name, status="planning", branch=None, completed_at=None),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"],
            ["completion_successor_active_task_ambiguous"],
        )

    def test_active_task_successor_ambiguous_when_multiple_qualifying_tasks(
        self,
    ) -> None:
        # AC5, "multiple" variant: two in_progress/review tasks exist.
        root = self.make_validator_repo()
        self.write_task(
            root,
            ".trellis/tasks/07-25-active-task-multi-a",
            self.task_record(
                "active-task-multi-a", status="in_progress", branch="codex/a", completed_at=None
            ),
        )
        self.write_task(
            root,
            ".trellis/tasks/07-26-active-task-multi-b",
            self.task_record(
                "active-task-multi-b", status="review", branch="codex/b", completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"],
            ["completion_successor_active_task_ambiguous"],
        )

    def test_active_task_successor_ambiguous_when_sibling_task_json_corrupt(
        self,
    ) -> None:
        # AC5, "unreadable sibling" variant: one valid in_progress task plus
        # one sibling whose task.json is corrupt/unparseable -- the corrupt
        # sibling must not be silently treated as "not a candidate," since
        # that could hide a genuine second in_progress task.
        root = self.make_validator_repo()
        self.write_task(
            root,
            ".trellis/tasks/07-25-active-task-corrupt-sibling",
            self.task_record(
                "active-task-corrupt-sibling",
                status="in_progress",
                branch="codex/valid",
                completed_at=None,
            ),
        )
        corrupt_dir = root / ".trellis/tasks/07-26-active-task-corrupt-other"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / "task.json").write_text("{not valid json", encoding="utf-8")
        (corrupt_dir / "prd.md").write_text(
            "# Fixture\n\nCorrupt sibling.\n", encoding="utf-8"
        )
        (corrupt_dir / "implement.jsonl").write_text("", encoding="utf-8")
        (corrupt_dir / "check.jsonl").write_text("", encoding="utf-8")
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"],
            ["completion_successor_active_task_ambiguous"],
        )

    def test_active_task_successor_reports_no_anchor_within_bound(self) -> None:
        # AC6: exactly one active task, but no commit touching its directory
        # within the bounded search window resolves to a qualifying starting
        # point (the only touch is the task's own creation, whose parent
        # never had the file) -- a direct diagnostic, not old archive-search
        # noise from unrelated history.
        root = self.make_validator_repo()
        name = "active-task-no-anchor"
        task_dir = f".trellis/tasks/07-25-{name}"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                name, status="in_progress", branch="codex/active-task-no-anchor", completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "fixture work")
        for index in range(5):
            self.run_git(
                root, "commit", "--allow-empty", "-m", f"unrelated commit {index + 1}"
            )
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_validator(
            root, "final-bundle", "--mode", "completion", "--base", head, "--head", head
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["reasonCodes"],
            ["completion_successor_active_task_anchor_missing"],
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
            extra_env={"PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}"},
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

    def test_planning_bundle_rejects_executable_file_mode(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "exec-mode"
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
        tool = task / "tool.sh"
        tool.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        tool.chmod(0o755)
        self.run_git(root, "add", ".trellis/tasks")
        # Force the executable bit into the committed tree even when the runner
        # has core.fileMode disabled, so the raw-diff mode is 100755.
        self.run_git(root, "update-index", "--chmod=+x", f"{task_dir}/tool.sh")
        self.run_git(root, "commit", "-m", "plan fixture with executable")
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

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("bundle_unsupported_file_mode", payload["reasonCodes"])

    def test_planning_bundle_rejects_symlink_file_mode(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "symlink-mode"
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
        os.symlink("prd.md", str(task / "link.md"))
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "plan fixture with symlink")
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

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("bundle_unsupported_file_mode", payload["reasonCodes"])

    def test_planning_bundle_rejects_submodule_gitlink(self) -> None:
        # Isolated, auto-cleaned source repository for the gitlink. A real
        # submodule (not a bare cacheinfo entry) keeps the worktree clean so the
        # mode check runs instead of tripping the dirty-worktree precondition.
        inner = self.make_repo()
        self.run_git(inner, "config", "user.email", "submodule@example.com")
        self.run_git(inner, "config", "user.name", "Submodule Source")
        (inner / "readme.txt").write_text("vendored\n", encoding="utf-8")
        self.run_git(inner, "add", ".")
        self.run_git(inner, "commit", "-m", "seed submodule source")

        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "gitlink-mode"
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
        self.run_git(
            root,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(inner),
            f"{task_dir}/vendored",
        )
        self.run_git(root, "add", ".trellis/tasks", ".gitmodules")
        self.run_git(root, "commit", "-m", "plan fixture with submodule")
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

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("bundle_unsupported_file_mode", payload["reasonCodes"])

    def test_planning_bundle_rejects_archived_task_mutation(self) -> None:
        root = self.make_validator_repo()
        base = self.git_output(root, "rev-parse", "HEAD")
        name = "archive-guard"
        task_dir = f".trellis/tasks/07-25-{name}"
        # A valid active planning change accompanies the offending archive edit so
        # the salient rejection is the archive mutation, not a missing task change.
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
        archived = root / ".trellis/tasks/archive/2026-07/07-20-old-work"
        archived.mkdir(parents=True, exist_ok=True)
        (archived / "task.json").write_text(
            json.dumps(
                self.task_record(
                    "old-work",
                    status="completed",
                    branch=None,
                    completed_at="2026-07-20T00:00:00Z",
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "plan fixture touching archive")
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

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("planning_archive_mutation", payload["reasonCodes"])

    def test_planning_bundle_blocks_active_task_outside_closure(self) -> None:
        root = self.make_validator_repo()
        parent_name = "ac2-parent"
        child_name = "ac2-child"
        parent_dir = f".trellis/tasks/07-25-{parent_name}"
        child_dir = f".trellis/tasks/07-25-{child_name}"
        parent = self.task_record(
            parent_name,
            status="in_progress",
            branch="codex/ac2-parent-work",
            completed_at=None,
        )
        parent["children"] = [f"07-25-{child_name}"]
        self.write_task(root, parent_dir, parent)
        self.run_git(root, "add", ".trellis/tasks")
        # The active parent is committed at/below base, so it stays outside the
        # changed planning closure.
        self.run_git(root, "commit", "-m", "seed active in-progress parent")
        base = self.git_output(root, "rev-parse", "HEAD")

        child = self.task_record(
            child_name,
            status="planning",
            branch=None,
            completed_at=None,
        )
        child["parent"] = f"07-25-{parent_name}"
        self.write_task(root, child_dir, child)
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add planning child")
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

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn(
            "planning_active_task_outside_closure", payload["reasonCodes"]
        )

    def test_planning_bundle_allows_planning_neighbor_closure(self) -> None:
        root = self.make_validator_repo()
        parent_name = "ac2-plan-parent"
        child_name = "ac2-plan-child"
        parent_dir = f".trellis/tasks/07-25-{parent_name}"
        child_dir = f".trellis/tasks/07-25-{child_name}"
        parent = self.task_record(
            parent_name,
            status="planning",
            branch=None,
            completed_at=None,
        )
        parent["children"] = [f"07-25-{child_name}"]
        self.write_task(root, parent_dir, parent)
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "seed planning parent")
        base = self.git_output(root, "rev-parse", "HEAD")

        child = self.task_record(
            child_name,
            status="planning",
            branch=None,
            completed_at=None,
        )
        child["parent"] = f"07-25-{parent_name}"
        self.write_task(root, child_dir, child)
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "add planning child")
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
        self.assertNotIn(
            "planning_active_task_outside_closure", payload["reasonCodes"]
        )

    def commit_planning_journal(self, root: Path, work_commit: str) -> str:
        self.write_session(root, work_commit)
        self.run_git(root, "add", ".trellis/workspace/dev")
        self.run_git(root, "commit", "-m", "record planning journal")
        return self.git_output(root, "rev-parse", "HEAD")

    def run_planning_bundle(
        self, root: Path, base: str, head: str
    ) -> subprocess.CompletedProcess[str]:
        return self.run_validator(
            root,
            "final-bundle",
            "--mode",
            "planning",
            "--base",
            base,
            "--head",
            head,
        )

    def test_planning_bundle_scopes_untouched_sibling_defects_to_advisories(
        self,
    ) -> None:
        root = self.make_validator_repo()
        name = "advisory-fixture"
        task_dir = f".trellis/tasks/07-25-{name}"
        task = self.write_task(
            root,
            task_dir,
            self.task_record(
                name,
                status="planning",
                branch=None,
                completed_at=None,
                description=" ",
            ),
        )
        (task / "check.jsonl").write_text(
            '{"_example":{"file":"src/example.py"}}\n'
            '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
            encoding="utf-8",
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "seed defective sibling artifacts")
        base = self.git_output(root, "rev-parse", "HEAD")

        (task / "prd.md").write_text(
            "# Fixture\n\nDelta-scoped planning refinement.\n", encoding="utf-8"
        )
        self.run_git(root, "add", task_dir)
        self.run_git(root, "commit", "-m", "refine prd only")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        head = self.commit_planning_journal(root, work_commit)

        result = self.run_planning_bundle(root, base, head)

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])
        self.assertEqual(payload["findings"], [])
        advisory_codes = {item["reasonCode"] for item in payload["advisories"]}
        self.assertIn("task_metadata_invalid", advisory_codes)
        self.assertIn("task_context_seed", advisory_codes)
        receipt_path = root / "receipt.json"
        receipt_path.write_text(result.stdout, encoding="utf-8")
        loaded = eligibility_module().load_finish_work_receipt(receipt_path)
        self.assertEqual(loaded["mode"], "planning")

    def test_planning_bundle_broken_sibling_task_json_keeps_delta_checks_blocking(
        self,
    ) -> None:
        cases = (
            ("malformed-json", '{"broken": \n', "task_json_invalid"),
            ("missing-file", None, "task_artifact_invalid"),
        )
        for label, task_json_content, advisory_code in cases:
            with self.subTest(label=label):
                root = self.make_validator_repo()
                name = f"broken-sibling-{label}"
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
                if task_json_content is None:
                    (task / "task.json").unlink()
                else:
                    (task / "task.json").write_text(
                        task_json_content, encoding="utf-8"
                    )
                self.run_git(root, "add", ".trellis/tasks")
                self.run_git(root, "commit", "-m", "seed broken sibling task.json")
                base = self.git_output(root, "rev-parse", "HEAD")

                (task / "prd.md").write_text(
                    "# Fixture\n\ntrailing \n", encoding="utf-8"
                )
                self.run_git(root, "add", task_dir)
                self.run_git(root, "commit", "-m", "refine prd only")
                work_commit = self.git_output(root, "rev-parse", "HEAD")
                head = self.commit_planning_journal(root, work_commit)

                result = self.run_planning_bundle(root, base, head)

                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "invalid", result.stdout)
                finding_codes = {
                    item["reasonCode"] for item in payload["findings"]
                }
                self.assertIn(
                    "bookkeeping_whitespace_invalid", finding_codes, result.stdout
                )
                advisory_codes = {
                    item["reasonCode"] for item in payload["advisories"]
                }
                self.assertIn(advisory_code, advisory_codes, result.stdout)

    def test_planning_bundle_group_one_producers_delta_scope(self) -> None:
        grounded_row = '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n'
        cases = (
            ("task_prd_empty", "prd.md", "", "check.jsonl", grounded_row),
            (
                "task_context_malformed",
                "implement.jsonl",
                '{"file":\n',
                "prd.md",
                "# Fixture\n\nDelta refinement.\n",
            ),
            (
                "bookkeeping_whitespace_invalid",
                "prd.md",
                "# Fixture\n\ntrailing \n",
                "check.jsonl",
                grounded_row,
            ),
        )
        for reason_code, seed_name, seed_content, delta_name, delta_content in cases:
            with self.subTest(reason_code=reason_code):
                root = self.make_validator_repo()
                name = f"scope-{reason_code.replace('_', '-')}"
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
                (task / seed_name).write_text(seed_content, encoding="utf-8")
                self.run_git(root, "add", ".trellis/tasks")
                self.run_git(root, "commit", "-m", "seed sibling defect")
                base = self.git_output(root, "rev-parse", "HEAD")

                (task / delta_name).write_text(delta_content, encoding="utf-8")
                self.run_git(root, "add", task_dir)
                self.run_git(root, "commit", "-m", "touch unrelated artifact")
                work_commit = self.git_output(root, "rev-parse", "HEAD")
                head = self.commit_planning_journal(root, work_commit)

                result = self.run_planning_bundle(root, base, head)

                self.assertEqual(result.returncode, 0, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "valid")
                self.assertEqual(
                    payload["reasonCodes"], ["planning_bundle_valid"]
                )
                advisory_codes = {
                    item["reasonCode"] for item in payload["advisories"]
                }
                self.assertIn(reason_code, advisory_codes)

    def test_planning_bundle_blocks_delta_contained_defects(self) -> None:
        cases = (
            (
                "task_metadata_invalid",
                "task.json",
                None,
            ),
            (
                "task_context_seed",
                "check.jsonl",
                '{"_example":{"file":"src/example.py"}}\n'
                '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
            ),
        )
        for reason_code, delta_name, delta_content in cases:
            with self.subTest(reason_code=reason_code):
                root = self.make_validator_repo()
                name = f"block-{reason_code.replace('_', '-')}"
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
                self.run_git(root, "commit", "-m", "seed clean planning task")
                base = self.git_output(root, "rev-parse", "HEAD")

                if delta_name == "task.json":
                    record = self.task_record(
                        name,
                        status="planning",
                        branch=None,
                        completed_at=None,
                        description=" ",
                    )
                    (task / "task.json").write_text(
                        json.dumps(record, indent=2) + "\n", encoding="utf-8"
                    )
                else:
                    (task / delta_name).write_text(
                        delta_content, encoding="utf-8"
                    )
                self.run_git(root, "add", task_dir)
                self.run_git(root, "commit", "-m", "introduce delta defect")
                work_commit = self.git_output(root, "rev-parse", "HEAD")
                head = self.commit_planning_journal(root, work_commit)

                result = self.run_planning_bundle(root, base, head)

                self.assertEqual(result.returncode, 1, result.stdout)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "invalid")
                self.assertIn(reason_code, payload["reasonCodes"])

    def test_planning_bundle_topology_findings_follow_anchor(self) -> None:
        parent_name = "topology-parent"
        child_name = "topology-child"
        parent_dir = f".trellis/tasks/07-25-{parent_name}"
        child_dir = f".trellis/tasks/07-25-{child_name}"

        with self.subTest(scenario="anchor-in-delta-blocks"):
            root = self.make_validator_repo()
            self.write_task(
                root,
                parent_dir,
                self.task_record(
                    parent_name, status="planning", branch=None, completed_at=None
                ),
            )
            self.write_task(
                root,
                child_dir,
                self.task_record(
                    child_name, status="planning", branch=None, completed_at=None
                ),
            )
            self.run_git(root, "add", ".trellis/tasks")
            self.run_git(root, "commit", "-m", "seed unlinked tasks")
            base = self.git_output(root, "rev-parse", "HEAD")

            child = self.task_record(
                child_name, status="planning", branch=None, completed_at=None
            )
            child["parent"] = f"07-25-{parent_name}"
            (root / child_dir / "task.json").write_text(
                json.dumps(child, indent=2) + "\n", encoding="utf-8"
            )
            self.run_git(root, "add", child_dir)
            self.run_git(root, "commit", "-m", "link child without reciprocity")
            work_commit = self.git_output(root, "rev-parse", "HEAD")
            head = self.commit_planning_journal(root, work_commit)

            result = self.run_planning_bundle(root, base, head)

            self.assertEqual(result.returncode, 1, result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "invalid")
            self.assertIn("task_topology_not_reciprocal", payload["reasonCodes"])
            self.assertEqual(payload.get("advisories"), [])

        with self.subTest(scenario="anchor-outside-delta-advises"):
            root = self.make_validator_repo()
            self.write_task(
                root,
                parent_dir,
                self.task_record(
                    parent_name, status="planning", branch=None, completed_at=None
                ),
            )
            broken_child = self.task_record(
                child_name, status="planning", branch=None, completed_at=None
            )
            broken_child["parent"] = f"07-25-{parent_name}"
            self.write_task(root, child_dir, broken_child)
            self.run_git(root, "add", ".trellis/tasks")
            self.run_git(root, "commit", "-m", "seed broken link")
            base = self.git_output(root, "rev-parse", "HEAD")

            (root / child_dir / "prd.md").write_text(
                "# Fixture\n\nDelta-scoped prd refinement.\n", encoding="utf-8"
            )
            self.run_git(root, "add", child_dir)
            self.run_git(root, "commit", "-m", "refine child prd only")
            work_commit = self.git_output(root, "rev-parse", "HEAD")
            head = self.commit_planning_journal(root, work_commit)

            result = self.run_planning_bundle(root, base, head)

            self.assertEqual(result.returncode, 0, result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "valid")
            self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])
            advisory_codes = {
                item["reasonCode"] for item in payload["advisories"]
            }
            self.assertIn("task_topology_not_reciprocal", advisory_codes)

        with self.subTest(scenario="neighbor-path-anchor-in-delta-blocks"):
            root = self.make_validator_repo()
            neighbor_name = "topology-neighbor"
            neighbor_dir = f".trellis/tasks/07-25-{neighbor_name}"
            neighbor = self.write_task(
                root,
                neighbor_dir,
                self.task_record(
                    neighbor_name, status="planning", branch=None, completed_at=None
                ),
            )
            (neighbor / "task.json").write_text("not json\n", encoding="utf-8")
            seeded_child = self.task_record(
                child_name, status="planning", branch=None, completed_at=None
            )
            seeded_child["parent"] = f"07-25-{neighbor_name}"
            self.write_task(root, child_dir, seeded_child)
            self.run_git(root, "add", ".trellis/tasks")
            self.run_git(root, "commit", "-m", "seed unparseable neighbor")
            base = self.git_output(root, "rev-parse", "HEAD")

            tweaked = self.task_record(
                child_name,
                status="planning",
                branch=None,
                completed_at=None,
                description="A refined bounded fixture task.",
            )
            tweaked["parent"] = f"07-25-{neighbor_name}"
            (root / child_dir / "task.json").write_text(
                json.dumps(tweaked, indent=2) + "\n", encoding="utf-8"
            )
            self.run_git(root, "add", child_dir)
            self.run_git(root, "commit", "-m", "tweak child metadata")
            work_commit = self.git_output(root, "rev-parse", "HEAD")
            head = self.commit_planning_journal(root, work_commit)

            result = self.run_planning_bundle(root, base, head)

            self.assertEqual(result.returncode, 1, result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "invalid")
            self.assertIn("task_topology_unverifiable", payload["reasonCodes"])
            unverifiable = next(
                item
                for item in payload["findings"]
                if item["reasonCode"] == "task_topology_unverifiable"
            )
            self.assertEqual(unverifiable["path"], f"{neighbor_dir}/task.json")
            self.assertEqual(payload.get("advisories"), [])

    def test_journal_only_recovery_accepts_repo_maintenance_commits(self) -> None:
        root = self.make_validator_repo()
        scripts = root / "scripts"
        (scripts / "tool.sh").write_text("echo tool\n", encoding="utf-8")
        (scripts / "legacy.sh").write_text("echo legacy\n", encoding="utf-8")
        (scripts / "dead.sh").write_text("echo dead\n", encoding="utf-8")
        self.run_git(root, "add", "scripts")
        self.run_git(root, "commit", "-m", "seed maintenance fixtures")

        (scripts / "tool.sh").write_text("echo tool v2\n", encoding="utf-8")
        self.run_git(root, "mv", "scripts/legacy.sh", "scripts/renamed.sh")
        (scripts / "dead.sh").unlink()
        self.run_git(root, "add", "-A", "scripts")
        self.run_git(root, "commit", "-m", "maintain repo scripts")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        head = self.commit_planning_journal(root, work_commit)

        result = self.run_planning_bundle(root, base, head)

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])
        self.assertEqual(
            payload["evidence"]["planningSubtype"], "journal-only-recovery"
        )
        self.assertEqual(payload["evidence"]["taskDirectories"], [])
        self.assertEqual(payload.get("advisories"), [])
        receipt_path = root / "receipt.json"
        receipt_path.write_text(result.stdout, encoding="utf-8")
        loaded = eligibility_module().load_finish_work_receipt(receipt_path)
        self.assertEqual(loaded["mode"], "planning")

    def test_journal_only_recovery_still_rejects_workspace_cited_commit(
        self,
    ) -> None:
        root = self.make_validator_repo()
        note = root / ".trellis/workspace/other/note.md"
        note.parent.mkdir(parents=True)
        note.write_text("workspace history\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/workspace/other")
        self.run_git(root, "commit", "-m", "record workspace fixture")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        base = work_commit
        head = self.commit_planning_journal(root, work_commit)

        result = self.run_planning_bundle(root, base, head)

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn(
            "planning_recovery_commit_scope_invalid", payload["reasonCodes"]
        )

    def test_journal_only_recovery_rejects_archive_and_malformed_namespace_paths(
        self,
    ) -> None:
        fixtures = (
            ".trellis/tasks/archive/2026-07/07-25-old-fixture/notes.md",
            ".trellis/tasks/not-a-task/file.md",
        )
        for path in fixtures:
            with self.subTest(path=path):
                root = self.make_validator_repo()
                artifact = root / path
                artifact.parent.mkdir(parents=True)
                artifact.write_text("fixture content\n", encoding="utf-8")
                self.run_git(root, "add", path)
                self.run_git(root, "commit", "-m", "record namespace fixture")
                work_commit = self.git_output(root, "rev-parse", "HEAD")
                base = work_commit
                head = self.commit_planning_journal(root, work_commit)

                result = self.run_planning_bundle(root, base, head)

                self.assertEqual(result.returncode, 1, result.stdout)
                reason_codes = json.loads(result.stdout)["reasonCodes"]
                self.assertIn(
                    "planning_recovery_commit_scope_invalid", reason_codes
                )
                self.assertIn(
                    "planning_recovery_task_change_missing", reason_codes
                )

    def test_planning_bundle_rejects_audit_path_in_delta(self) -> None:
        root = self.make_validator_repo()
        name = "audit-scope-fixture"
        task_dir = f".trellis/tasks/07-25-{name}"
        self.write_task(
            root,
            task_dir,
            self.task_record(
                name, status="planning", branch=None, completed_at=None
            ),
        )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "plan fixture work")
        base_parent = self.git_output(root, "rev-parse", "HEAD~1")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        self.write_session(root, work_commit)
        ledger = root / ".trellis/audit/ledger.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("# Audit\n", encoding="utf-8")
        self.run_git(root, "add", ".trellis/workspace/dev", ".trellis/audit")
        self.run_git(root, "commit", "-m", "record journal with audit ledger")
        head = self.git_output(root, "rev-parse", "HEAD")

        result = self.run_planning_bundle(root, base_parent, head)

        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("bundle_scope_invalid", payload["reasonCodes"])

    def test_planning_bundle_caps_advisories_and_reports_dropped(self) -> None:
        root = self.make_validator_repo()
        tasks = []
        for index in range(14):
            name = f"cap-fixture-{index:02d}"
            task_dir = f".trellis/tasks/07-25-{name}"
            task = self.write_task(
                root,
                task_dir,
                self.task_record(
                    name,
                    status="planning",
                    branch=None,
                    completed_at=None,
                    description=" ",
                ),
            )
            (task / "check.jsonl").write_text(
                '{"_example":{"file":"src/example.py"}}\n'
                '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
                encoding="utf-8",
            )
            tasks.append(task)
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "seed advisory overflow fixtures")
        base = self.git_output(root, "rev-parse", "HEAD")

        for task in tasks:
            (task / "prd.md").write_text(
                "# Fixture\n\nDelta-scoped prd refresh.\n", encoding="utf-8"
            )
        self.run_git(root, "add", ".trellis/tasks")
        self.run_git(root, "commit", "-m", "refresh every prd")
        work_commit = self.git_output(root, "rev-parse", "HEAD")
        head = self.commit_planning_journal(root, work_commit)

        result = self.run_planning_bundle(root, base, head)

        self.assertEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["reasonCodes"], ["planning_bundle_valid"])
        self.assertEqual(len(payload["advisories"]), 25)
        self.assertEqual(payload["evidence"]["advisoriesDropped"], 3)
        self.assertLess(len(result.stdout.encode("utf-8")), 64 * 1024)
        receipt_path = root / "receipt.json"
        receipt_path.write_text(result.stdout, encoding="utf-8")
        module = eligibility_module()
        validated = module.validate_finish_work_receipt(
            module.load_request(receipt_path)
        )
        self.assertEqual(validated["mode"], "planning")
