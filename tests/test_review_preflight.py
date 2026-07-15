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


class ReviewPreflightTests(InstallTestCase):
    """Tests for review preflight, archived-task, and branch push guards."""

    def test_review_preflight_exports_reusable_helpers(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        result = subprocess.run(
            [
                node,
                "--input-type=module",
                "-e",
                """
import assert from 'node:assert/strict';
import {
  copiedTemplateKind,
  extractDocumentationPathReferences,
  parseNumstat,
  parseJournalSessionsFromText,
  parseWorkspaceIndexSessionsFromText,
  shouldCheckDocumentationPathReference,
  unsupportedNodeVersionMessage,
  validateTrellisJournalSessions,
} from './scripts/sd-ai-command-pack-review-preflight.mjs';

assert.equal(copiedTemplateKind('.trellis/scripts/get_context.py'), 'trellis');
assert.equal(copiedTemplateKind('.zcode/agents/trellis-check.md'), 'trellis');
assert.equal(copiedTemplateKind('.agents/skills/sd-review-pr/SKILL.md'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('.qoder/commands/sd-review-pr.md'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('scripts/sd-ai-command-pack-review-scope.sh'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('.sd-ai-command-pack/manifest.json'), 'sd-ai-command-pack');
assert.deepEqual(parseNumstat('1\\t2\\tsrc/file\\tname.js\\0'), [
  { added: 1, deleted: 2, path: 'src/file\\tname.js' },
]);
assert.deepEqual(parseNumstat('3\\t4\\t\\0old\\tname.js\\0new\\tname.js\\0'), [
  { added: 3, deleted: 4, path: 'new\\tname.js' },
]);
assert.deepEqual(
  extractDocumentationPathReferences('docs/guide.md', 'See `docs/current.md` and [missing](../missing.md).').map((item) => item.target),
  ['../missing.md', 'docs/current.md'],
);
assert.equal(shouldCheckDocumentationPathReference('docs/guide:section.md'), true);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/installed-targets.txt'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/local-only.txt'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/manifest.json'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/pr-body-scope.json'), false);
assert.equal(shouldCheckDocumentationPathReference('.sd-ai-command-pack/review-preflight.json'), false);
assert.equal(shouldCheckDocumentationPathReference('.trellis/.developer'), false);
assert.equal(shouldCheckDocumentationPathReference('.trellis/.template-hashes.json'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/TRELLIS_REVIEW_PR_PACK.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/repomix-map.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/review-learnings.md'), false);
assert.equal(shouldCheckDocumentationPathReference('package.json'), false);
assert.equal(shouldCheckDocumentationPathReference('https://example.com/docs.md'), false);
assert.equal(shouldCheckDocumentationPathReference('obsidian://open?vault=Repo'), false);
const journal = parseJournalSessionsFromText('.trellis/workspace/dev/journal-1.md', [
  '## Session 1: Done',
  '### Status',
  '- [OK] **Completed**',
  '### Main Changes',
  '(Add details)',
  '### Git Commits',
  '- abcdef1',
].join('\\n'));
assert.equal(unsupportedNodeVersionMessage('v16.9.0'), '');
assert.equal(unsupportedNodeVersionMessage('v20.0.0'), '');
assert.match(unsupportedNodeVersionMessage('v16.8.0'), /requires Node >= 16\\.9\\.0/);
assert.match(unsupportedNodeVersionMessage('not-a-version'), /could not parse/);
const index = parseWorkspaceIndexSessionsFromText('.trellis/workspace/dev/index.md', '| 1 | Done | Completed | 1234567 | note |  \\n');
const validation = validateTrellisJournalSessions({
  developerRelative: '.trellis/workspace/dev',
  indexFile: '.trellis/workspace/dev/index.md',
  indexSessions: index,
  journalSessions: journal,
});
assert.equal(validation.completedSessions, 1);
assert.ok(validation.failures.some((failure) => failure.includes('(Add details)')));
assert.ok(validation.failures.some((failure) => failure.includes('commits `1234567` do not match')));
""",
            ],
            cwd=PACK_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_review_preflight_script_runs_via_symlink(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        link = root / "scripts/check-review-preflight-link.mjs"
        try:
            link.symlink_to("sd-ai-command-pack-review-preflight.mjs")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = subprocess.run(
            [node, "scripts/check-review-preflight-link.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Review preflight:", result.stdout)
        self.assertNotEqual(result.stdout.strip(), "")

    def test_review_preflight_reports_untracked_copied_surfaces(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            scripts_dir / "sd-ai-command-pack-review-preflight.mjs",
        )
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "scripts/sd-ai-command-pack-review-preflight.mjs")
        self.run_git(root, "commit", "-m", "baseline")

        copied_surface = root / ".agents/skills/sd-review-pr/SKILL.md"
        copied_surface.parent.mkdir(parents=True, exist_ok=True)
        copied_surface.write_text("# Review PR\n", encoding="utf-8")

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN untracked files changes copied", result.stdout)
        self.assertIn(".agents/skills/sd-review-pr/SKILL.md", result.stdout)

    def test_archived_prd_backed_tasks_have_descriptions(self) -> None:
        missing_descriptions = self.archived_task_description_failures(
            PACK_ROOT / ".trellis/tasks/archive",
            base_root=PACK_ROOT,
        )

        self.assertEqual([], missing_descriptions)

    def test_archived_description_guard_skips_symlinked_task_files(self) -> None:
        tempdir = tempfile.TemporaryDirectory(
            prefix="sd-archive-description-symlink-"
        )
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        archive = root / ".trellis/tasks/archive/2026-07"

        missing = archive / "missing"
        missing.mkdir(parents=True)
        (missing / "prd.md").write_text("# Missing\n", encoding="utf-8")
        (missing / "task.json").write_text(
            json.dumps({"status": "completed", "description": ""}),
            encoding="utf-8",
        )

        outside_task = root / "outside-task.json"
        outside_task.write_text(
            json.dumps({"status": "completed", "description": ""}),
            encoding="utf-8",
        )
        symlinked_task = archive / "symlinked-task"
        symlinked_task.mkdir()
        (symlinked_task / "prd.md").write_text("# Symlinked task\n", encoding="utf-8")

        symlinked_prd = archive / "symlinked-prd"
        symlinked_prd.mkdir()
        (symlinked_prd / "task.json").write_text(
            json.dumps({"status": "completed", "description": ""}),
            encoding="utf-8",
        )
        outside_prd = root / "outside-prd.md"
        outside_prd.write_text("# Outside PRD\n", encoding="utf-8")

        try:
            (symlinked_task / "task.json").symlink_to(outside_task)
            (symlinked_prd / "prd.md").symlink_to(outside_prd)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        self.assertEqual(
            [".trellis/tasks/archive/2026-07/missing/task.json"],
            self.archived_task_description_failures(
                root / ".trellis/tasks/archive",
                base_root=root,
            ),
        )

    def test_review_preflight_script_detects_trellis_journal_drift(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        workspace = root / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        (workspace / "journal-1.md").write_text(
            "\n".join(
                [
                    "## Session 1: Guard fixture",
                    "### Status",
                    "**Completed**",
                    "### Main Changes",
                    "(Add details)",
                    "### Testing",
                    "(Add test results)",
                    "### Git Commits",
                    "- abcdef1",
                ]
            ),
            encoding="utf-8",
        )
        (workspace / "index.md").write_text(
            "| Session | Title | Status | Commits | Notes |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Guard fixture | Completed | 1234567 | done |\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("completed Session 1 still contains placeholder (Add details)", result.stdout)
        self.assertIn("completed Session 1 still contains placeholder (Add test results)", result.stdout)
        self.assertIn("commits `1234567` do not match", result.stdout)

    def test_review_preflight_allows_configured_linux_service_users(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        (root / "docs/service.md").write_text(
            "Use `/home/service-user/app` for the service account.\n",
            encoding="utf-8",
        )
        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.write_text(
            '{"allowedLinuxHomeUsers":["service-user"]}\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("personal absolute paths", result.stdout)

    def test_chore_scope_pre_push_hook_gates_direct_main_pushes(self) -> None:
        if self._bash_path is None:
            self.skipTest("bash is not available on PATH")

        tempdir = tempfile.TemporaryDirectory(prefix="sd-pack-hook-test-")
        self.addCleanup(tempdir.cleanup)
        base = Path(tempdir.name)
        origin = base / "origin.git"
        subprocess.run(
            ["git", "init", "--bare", "-q", str(origin)],
            check=True,
        )
        clone = base / "clone"
        subprocess.run(
            ["git", "clone", "-q", str(origin), str(clone)],
            check=True,
            stderr=subprocess.DEVNULL,
        )

        def run(*args: str, env: dict[str, str] | None = None):
            return subprocess.run(
                args,
                cwd=clone,
                env={**os.environ, **(env or {})},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        run("git", "config", "user.email", "test@example.com")
        run("git", "config", "user.name", "Test User")
        run("git", "checkout", "-q", "-b", "main")
        hooks_dir = clone / ".githooks"
        hooks_dir.mkdir()
        shutil.copy2(PACK_ROOT / ".githooks/pre-push", hooks_dir / "pre-push")
        run("git", "config", "core.hooksPath", ".githooks")

        chore = clone / ".trellis/tasks/07-01-demo/prd.md"
        chore.parent.mkdir(parents=True)
        chore.write_text("# demo\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore(task): demo")

        # Creating remote main directly fails closed (no chore baseline).
        result = run("git", "push", "-q", "origin", "main")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("creating remote main", result.stdout)
        result = run(
            "git",
            "push",
            "-q",
            "origin",
            "main",
            env={"SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)

        # With a baseline, chore-only pushes flow.
        chore.write_text("# demo v2\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore(task): demo v2")
        result = run("git", "push", "-q", "origin", "main")
        self.assertEqual(result.returncode, 0, result.stdout)

        (clone / "code.py").write_text("print('hi')\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "feat: code")
        result = run("git", "push", "-q", "origin", "main")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("chore-scope only", result.stdout)
        self.assertIn("code.py", result.stdout)

        result = run(
            "git",
            "push",
            "-q",
            "origin",
            "main",
            env={"SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("bypassed", result.stdout)

        # Rename detection must not hide a deletion outside chore scope.
        (clone / ".trellis/workspace").mkdir(parents=True, exist_ok=True)
        result = run("git", "mv", "code.py", ".trellis/workspace/code.py")
        self.assertEqual(result.returncode, 0, result.stdout)
        run("git", "commit", "-q", "-m", "chore: move code into workspace")
        result = run("git", "push", "-q", "origin", "main")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("code.py", result.stdout)
        result = run(
            "git",
            "push",
            "-q",
            "origin",
            "main",
            env={"SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)

        # NUL-delimited parsing allows unusual chore paths without ambiguity.
        unusual_chore = clone / ".trellis/tasks/07-01-demo/line\nbreak.md"
        unusual_chore.write_text("# unusual chore path\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "chore: unusual task path")
        result = run("git", "push", "-q", "origin", "main")
        self.assertEqual(result.returncode, 0, result.stdout)

        unusual_code = clone / "line\nbreak.py"
        unusual_code.write_text("print('blocked')\n", encoding="utf-8")
        run("git", "add", "-A")
        run("git", "commit", "-q", "-m", "test: unusual code path")
        result = run("git", "push", "-q", "origin", "main")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("line", result.stdout)
        self.assertIn("break.py", result.stdout)

    def test_review_preflight_accepts_line_suffixed_doc_references(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        (root / "docs/cite.md").write_text(
            "See [the gate](../scripts/sd-ai-command-pack-full-check.sh:12) and\n"
            "`scripts/sd-ai-command-pack-housekeeping.sh:34-56` for details.\n"
            "Also `scripts/sd-ai-command-pack-install-audit.py:7:3` and\n"
            "`scripts/sd-ai-command-pack-review-local.sh:10-20:4`.\n"
            "Broken: `docs/definitely-missing.md:5`.\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "references missing path docs/definitely-missing.md:5",
            result.stdout,
        )
        self.assertNotIn("full-check.sh:12", result.stdout)
        self.assertNotIn("housekeeping.sh:34-56", result.stdout)
        self.assertNotIn("install-audit.py:7:3", result.stdout)
        self.assertNotIn("review-local.sh:10-20:4", result.stdout)

    def test_review_preflight_reports_malformed_config_as_failure(self) -> None:
        # Regression: a malformed review-preflight.json must FAIL, not be wiped
        # by the failure-buffer reset and pass on defaults.
        if shutil.which("node") is None:
            self.skipTest("node is not available on PATH")
        root = self.make_repo()
        # The script resolves its repo root to its own parent dir, so it must be
        # run from inside the target repo's scripts/ as it is when installed.
        scripts_dir = root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            scripts_dir / "sd-ai-command-pack-review-preflight.mjs",
        )
        config_dir = root / ".sd-ai-command-pack"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "review-preflight.json").write_text(
            "{ not valid json", encoding="utf-8"
        )

        result = subprocess.run(
            ["node", "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("could not be parsed as JSON", result.stdout)

    def test_review_preflight_resolves_pytest_node_ids_to_files(self) -> None:
        # Regression: docs referencing pytest node ids (tests/x.py::test_y) must
        # resolve the file part only — present file passes, missing file fails.
        if shutil.which("node") is None:
            self.skipTest("node is not available on PATH")
        root = self.make_repo()
        scripts_dir = root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            install.ROOT / "scripts/sd-ai-command-pack-review-preflight.mjs",
            scripts_dir / "sd-ai-command-pack-review-preflight.mjs",
        )
        (root / "tests").mkdir()
        (root / "tests/test_real.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
        docs = root / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "Run `tests/test_real.py::test_ok` before merging.\n",
            encoding="utf-8",
        )

        def run_preflight() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["node", "scripts/sd-ai-command-pack-review-preflight.mjs"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )

        result = run_preflight()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("test_real.py", result.stdout.replace("PASS", ""))

        (docs / "guide.md").write_text(
            "Run `tests/test_missing.py::test_gone` before merging.\n",
            encoding="utf-8",
        )
        result = run_preflight()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("tests/test_missing.py", result.stdout)

    def test_main_push_scope_allows_only_trellis_chore_paths(self) -> None:
        script = PACK_ROOT / ".github/scripts/check-main-push-scope.sh"
        root = self.make_git_repo_without_trellis()
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")

        (root / "README.md").write_text("baseline\n", encoding="utf-8")
        self.run_git(root, "add", "README.md")
        self.run_git(root, "commit", "-m", "baseline")
        baseline = self.git_output(root, "rev-parse", "HEAD")

        task = root / ".trellis/tasks/example/task.json"
        task.parent.mkdir(parents=True)
        task.write_text('{"status": "planning"}\n', encoding="utf-8")
        self.run_git(root, "add", str(task.relative_to(root)))
        self.run_git(root, "commit", "-m", "record task")
        chore_head = self.git_output(root, "rev-parse", "HEAD")
        allowed = subprocess.run(
            ["bash", str(script), baseline, chore_head],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertIn("chore-only diff accepted", allowed.stdout)

        (root / "code.py").write_text("print('changed')\n", encoding="utf-8")
        self.run_git(root, "add", "code.py")
        self.run_git(root, "commit", "-m", "add source")
        source_head = self.git_output(root, "rev-parse", "HEAD")
        rejected = subprocess.run(
            ["bash", str(script), chore_head, source_head],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(rejected.returncode, 1, rejected.stdout)
        self.assertIn("code.py", rejected.stderr)

        workspace = root / ".trellis/workspace"
        workspace.mkdir(parents=True)
        self.run_git(root, "mv", "code.py", ".trellis/workspace/code.py")
        self.run_git(root, "commit", "-m", "move source into chore path")
        rename_head = self.git_output(root, "rev-parse", "HEAD")
        disguised_rename = subprocess.run(
            ["bash", str(script), source_head, rename_head],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(disguised_rename.returncode, 1, disguised_rename.stdout)
        self.assertIn("code.py", disguised_rename.stderr)

        # A pull-request merge commit (two parents) lands reviewed non-chore
        # content on main through the sanctioned path and is accepted, even
        # though its diff spans non-chore files.
        current_branch = self.git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
        self.run_git(root, "checkout", "-b", "feature-branch", baseline)
        (root / "feature.py").write_text("print('feature')\n", encoding="utf-8")
        self.run_git(root, "add", "feature.py")
        self.run_git(root, "commit", "-m", "feature work")
        self.run_git(root, "checkout", current_branch)
        merge_before = self.git_output(root, "rev-parse", "HEAD")
        self.run_git(
            root, "merge", "--no-ff", "-m", "Merge pull request #1", "feature-branch"
        )
        merge_head = self.git_output(root, "rev-parse", "HEAD")
        merged = subprocess.run(
            ["bash", str(script), merge_before, merge_head],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertIn("pull-request merge commit accepted", merged.stdout)

        missing_before = subprocess.run(
            ["bash", str(script), "0" * 40, rename_head],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(missing_before.returncode, 1, missing_before.stdout)
        self.assertIn("failing closed", missing_before.stderr)


if __name__ == "__main__":
    unittest.main()
