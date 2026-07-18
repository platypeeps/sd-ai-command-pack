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
  findHistoricalTrellisJournalSessionEdits,
  findTrellisTaskContextSeedRows,
  isSourceReviewPath,
  parseNumstat,
  parseJournalSessionsFromText,
  parseTrellisTaskArtifactPath,
  parseWorkspaceIndexSessionsFromText,
  reviewRiskCategories,
  shouldCheckDocumentationPathReference,
  trellisTaskDirectory,
  thrownValueMessage,
  unsupportedNodeVersionMessage,
  validateTrellisJournalSessions,
} from './scripts/sd-ai-command-pack-review-preflight.mjs';

assert.equal(copiedTemplateKind('.trellis/scripts/get_context.py'), 'trellis');
assert.equal(copiedTemplateKind('.zcode/agents/trellis-check.md'), 'trellis');
assert.equal(copiedTemplateKind('.agents/skills/sd-review-pr/SKILL.md'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('.qoder/commands/sd-review-pr.md'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('scripts/sd-ai-command-pack-review-scope.sh'), 'sd-ai-command-pack');
assert.equal(copiedTemplateKind('.sd-ai-command-pack/manifest.json'), 'sd-ai-command-pack');
assert.equal(isSourceReviewPath('templates/scripts/sd-ai-command-pack-review-preflight.mjs'), true);
assert.equal(isSourceReviewPath('scripts/sd-ai-command-pack-review-preflight.mjs'), false);
assert.equal(isSourceReviewPath('docs/repomix-map.md'), false);
assert.equal(isSourceReviewPath('.trellis/tasks/07-17-demo/prd.md'), false);
assert.equal(trellisTaskDirectory('.trellis/tasks/07-17-demo/prd.md'), '.trellis/tasks/07-17-demo');
assert.equal(
  trellisTaskDirectory('.trellis/tasks/archive/2026-07/07-17-demo/task.json'),
  '.trellis/tasks/archive/2026-07/07-17-demo',
);
assert.equal(trellisTaskDirectory('src/demo.py'), '');
assert.deepEqual(
  reviewRiskCategories([
    'const parsed = JSON.parse(text);',
    'spawnSync(command);',
    'const target = resolve(root, name);',
    'const token = process.env.TOKEN;',
    'createHash("sha256").digest();',
  ].join('\\n')),
  [
    'parser/structured input',
    'subprocess/external command',
    'path/filesystem boundary',
    'environment/global state',
    'digest/integrity framing',
  ],
);
assert.deepEqual(parseTrellisTaskArtifactPath('.trellis/tasks/07-17-demo/check.jsonl'), {
  taskDir: '.trellis/tasks/07-17-demo',
  artifact: 'check.jsonl',
  archived: false,
});
assert.deepEqual(parseTrellisTaskArtifactPath('.trellis/tasks/archive/2026-07/07-17-demo/implement.jsonl'), {
  taskDir: '.trellis/tasks/archive/2026-07/07-17-demo',
  artifact: 'implement.jsonl',
  archived: true,
});
assert.equal(parseTrellisTaskArtifactPath('.trellis/tasks/archive/task.json'), null);
assert.equal(parseTrellisTaskArtifactPath('.trellis/tasks/archive/2026-07/07-17-demo/prd.md'), null);
assert.deepEqual(findTrellisTaskContextSeedRows('check.jsonl', [
  '{"file":"spec.md","reason":"real"}',
  '{"_example":"remove me"}',
  '{"nested":{"_example":"not a seed row"}}',
  'malformed',
].join('\\n')), [{ file: 'check.jsonl', line: 2 }]);
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
assert.equal(shouldCheckDocumentationPathReference('.trellis/audit/ledger.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/TRELLIS_REVIEW_PR_PACK.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/repomix-map.md'), false);
assert.equal(shouldCheckDocumentationPathReference('docs/review-learnings.md'), false);
assert.equal(shouldCheckDocumentationPathReference('package.json'), false);
assert.equal(shouldCheckDocumentationPathReference('https://example.com/docs.md'), false);
assert.equal(shouldCheckDocumentationPathReference('obsidian://open?vault=Repo'), false);
assert.equal(thrownValueMessage(new Error('error detail')), 'error detail');
assert.equal(thrownValueMessage('string detail'), 'string detail');
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
const currentJournal = parseJournalSessionsFromText('.trellis/workspace/dev/journal-1.md', [
  '## Session 1: Done',
  '### Main Changes',
  '- Accidentally replaced history.',
  '## Session 2: Current',
  '### Main Changes',
  '- Intended current change.',
].join('\\n'));
assert.deepEqual(
  findHistoricalTrellisJournalSessionEdits(journal, currentJournal).map((issue) => [issue.kind, issue.session.number]),
  [['modified', 1]],
);
assert.deepEqual(
  findHistoricalTrellisJournalSessionEdits(
    journal,
    parseJournalSessionsFromText('.trellis/workspace/dev/journal-1.md', [
      '## Session 1: Current correction',
      '### Main Changes',
      '- Explicitly corrected current session.',
    ].join('\\n')),
  ),
  [],
);
assert.deepEqual(
  findHistoricalTrellisJournalSessionEdits(journal, currentJournal.slice(1))
    .map((issue) => [issue.kind, issue.session.number]),
  [['removed', 1]],
);
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

    def test_review_preflight_advises_scope_section_for_generated_files(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        # An untracked repository-map file requires a PR scope section; the
        # pre-PR preflight must surface the advisory (naming the section)
        # without any PR present.
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "repomix-map.md").write_text("# map\n", encoding="utf-8")

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("the PR body must include", result.stdout)
        self.assertIn("Tooling/generated scope:", result.stdout)

    def test_review_preflight_advises_first_review_risks_and_review_scope(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.write_text(
            json.dumps({"sourceReviewWarningLines": 5}), encoding="utf-8"
        )
        source = root / "templates/scripts/risk_fixture.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "\n".join(
                [
                    "import hashlib",
                    "import json",
                    "import os",
                    "import subprocess",
                    "from pathlib import Path",
                    "def inspect(raw):",
                    "    parsed = json.loads(raw)",
                    "    subprocess.run(['tool'], timeout=1)",
                    "    target = Path(parsed['path'])",
                    "    token = os.environ.get('TOKEN', '')",
                    "    return hashlib.sha256((str(target) + token).encode()).hexdigest()",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        for task_name in ("07-18-one", "07-18-two"):
            task = root / ".trellis/tasks" / task_name
            task.mkdir(parents=True)
            (task / "task.json").write_text(
                '{"status":"planning"}\n', encoding="utf-8"
            )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN changed code adds parser/structured input", result.stdout)
        self.assertIn("subprocess/external command", result.stdout)
        self.assertIn("path/filesystem boundary", result.stdout)
        self.assertIn("environment/global state", result.stdout)
        self.assertIn("digest/integrity framing", result.stdout)
        self.assertIn("cover the applicable boundary matrix", result.stdout)
        self.assertRegex(
            result.stdout,
            r"WARN .* changes \d+ authored source line\(s\) across \d+ file\(s\)",
        )
        self.assertIn("changes 2 Trellis task directories", result.stdout)

    def test_review_preflight_size_checks_large_untracked_file_without_reading_it(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.write_text(
            json.dumps(
                {
                    "largeFileWarningLines": 3,
                    "untrackedFileReadLimitBytes": 8,
                }
            ),
            encoding="utf-8",
        )
        (root / "docs/large-untracked.md").write_text(
            "this is one long line that should not be counted exactly",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "includes a large file diff (4 lines): docs/large-untracked.md",
            result.stdout,
        )

    def test_review_preflight_bounds_large_untracked_code_risk_scan(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.write_text(
            json.dumps(
                {
                    "largeFileWarningLines": 3,
                    "untrackedFileReadLimitBytes": 8,
                }
            ),
            encoding="utf-8",
        )
        source = root / "scripts/large-untracked.py"
        source.write_text(
            "import subprocess\nsubprocess.run(['tool'])\n",
            encoding="utf-8",
        )
        if os.name != "nt":
            source.chmod(0)
            self.addCleanup(source.chmod, 0o600)

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "boundary-risk content scan skipped 1 oversized untracked code "
            "file(s) above 8 bytes: scripts/large-untracked.py",
            result.stdout,
        )
        self.assertNotIn("changed code adds subprocess/external command", result.stdout)
        self.assertNotIn("no boundary-risk trigger was added", result.stdout)
        self.assertIn(
            "includes a large file diff (4 lines): scripts/large-untracked.py",
            result.stdout,
        )

    @unittest.skipIf(os.name == "nt", "POSIX file permissions required")
    def test_review_preflight_warns_when_untracked_code_is_unreadable(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        source = root / "scripts/unreadable.py"
        source.write_text("value = 1\n", encoding="utf-8")
        source.chmod(0)
        self.addCleanup(source.chmod, 0o600)

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "boundary-risk content scan skipped 1 unreadable untracked code "
            "file(s): scripts/unreadable.py",
            result.stdout,
        )
        self.assertNotIn("no boundary-risk trigger was added", result.stdout)

    def test_review_preflight_fails_hard_when_git_cannot_run(self) -> None:
        # Regression: a git spawn failure (missing binary, buffer overflow)
        # must FAIL the preflight naming the git command, not silently pass
        # the diff-driven checks against an empty diff.
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
        empty_bin = root / "empty-bin"
        empty_bin.mkdir()
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in (
                "SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF",
                "SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF",
            )
        }
        env["PATH"] = str(empty_bin)

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, r"FAIL .*: git .+ could not run: ")

    def test_review_preflight_fails_hard_when_git_is_killed(self) -> None:
        # Regression: a git child terminated by a signal returns
        # {signal, status: null} without result.error; that must FAIL the
        # preflight instead of degrading to an empty diff.
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
        shim_bin = root / "shim-bin"
        shim_bin.mkdir()
        git_shim = shim_bin / "git"
        git_shim.write_text("#!/bin/sh\nkill -9 $$\n", encoding="utf-8")
        git_shim.chmod(0o755)
        env = {
            key: value
            for key, value in os.environ.items()
            if key
            not in (
                "SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF",
                "SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF",
            )
        }
        env["PATH"] = str(shim_bin)

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(
            result.stdout,
            r"FAIL .*: git .+ did not complete: terminated by signal ",
        )

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

    def test_review_preflight_checks_context_after_task_leaves_planning(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        task = root / ".trellis/tasks/07-17-demo"
        task.mkdir(parents=True)
        task_json = task / "task.json"
        task_json.write_text('{"status":"planning"}\n', encoding="utf-8")
        seed = '{"_example":"replace me"}\n'
        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")

        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "no changed in-progress, completed, or archived Trellis task context files",
            result.stdout,
        )

        task_json.write_text('{"status":"in_progress"}\n', encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-17-demo/implement.jsonl:1 still contains",
            result.stdout,
        )
        self.assertIn(
            ".trellis/tasks/07-17-demo/check.jsonl:1 still contains",
            result.stdout,
        )

        context = '{"file":"spec.md","reason":"grounded"}\n'
        (task / "implement.jsonl").write_text(context, encoding="utf-8")
        (task / "check.jsonl").write_text("", encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 2 changed in-progress, completed, or archived Trellis task context file(s)",
            result.stdout,
        )

        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")
        task_json.write_text("{malformed\n", encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "task.json could not be parsed as JSON while checking task context state",
            result.stdout,
        )
        self.assertNotIn(
            "no changed in-progress, completed, or archived Trellis task context files",
            result.stdout,
        )

        task_json.write_text('{"status":"completed"}\n', encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-17-demo/implement.jsonl:1 still contains",
            result.stdout,
        )
        self.assertIn(
            ".trellis/tasks/07-17-demo/check.jsonl:1 still contains",
            result.stdout,
        )

        (task / "implement.jsonl").write_text(context, encoding="utf-8")
        (task / "check.jsonl").write_text(context, encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 2 changed in-progress, completed, or archived Trellis task context file(s)",
            result.stdout,
        )

    def test_review_preflight_checks_new_but_not_untouched_archived_seeds(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        legacy = root / ".trellis/tasks/archive/2026-07/legacy"
        legacy.mkdir(parents=True)
        (legacy / "task.json").write_text(
            '{"status":"completed"}\n', encoding="utf-8"
        )
        (legacy / "implement.jsonl").write_text(
            '{"_example":"legacy"}\n', encoding="utf-8"
        )
        (legacy / "check.jsonl").write_text(
            '{"_example":"legacy"}\n', encoding="utf-8"
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline with legacy archive")

        (root / ".trellis/config.yaml").write_text("# changed\n", encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("legacy/implement.jsonl:1", result.stdout)

        current = root / ".trellis/tasks/archive/2026-07/current"
        current.mkdir(parents=True)
        (current / "task.json").write_text(
            '{"status":"completed"}\n', encoding="utf-8"
        )
        (current / "implement.jsonl").write_text(
            '{"_example":"current"}\n', encoding="utf-8"
        )
        (current / "check.jsonl").write_text(
            '{"file":"spec.md","reason":"grounded"}\n', encoding="utf-8"
        )
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/archive/2026-07/current/implement.jsonl:1 still contains",
            result.stdout,
        )
        self.assertNotIn("legacy/implement.jsonl:1", result.stdout)

    def test_review_preflight_skips_symlinked_completed_task_context(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        outside = root / "outside.jsonl"
        outside.write_text('{"_example":"outside"}\n', encoding="utf-8")
        task = root / ".trellis/tasks/archive/2026-07/symlinked"
        task.mkdir(parents=True)
        (task / "task.json").write_text(
            '{"status":"completed"}\n', encoding="utf-8"
        )
        (task / "check.jsonl").write_text(
            '{"file":"spec.md","reason":"grounded"}\n', encoding="utf-8"
        )
        try:
            (task / "implement.jsonl").symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 1 changed in-progress, completed, or archived Trellis task context file(s)",
            result.stdout,
        )

    def run_review_preflight(
        self, node: str, root: Path
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
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

    def test_review_preflight_rejects_historical_trellis_journal_edits(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)
        workspace = root / ".trellis/workspace/dev"
        workspace.mkdir(parents=True)
        journal = workspace / "journal-1.md"
        index = workspace / "index.md"
        original_session = "\n".join(
            [
                "## Session 1: Historical fixture",
                "### Status",
                "- [OK] **Completed**",
                "### Main Changes",
                "- Original historical change.",
                "### Testing",
                "- Original historical validation.",
                "### Git Commits",
                "- abcdef1",
            ]
        )
        journal.write_text(f"{original_session}\n", encoding="utf-8")
        index.write_text(
            "| Session | Title | Status | Commits | Notes |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Historical fixture | Completed | abcdef1 | done |\n",
            encoding="utf-8",
        )
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        current_session = "\n".join(
            [
                "## Session 2: Current fixture",
                "### Status",
                "- [OK] **Completed**",
                "### Main Changes",
                "- Intended current change.",
                "### Testing",
                "- Current validation.",
                "### Git Commits",
                "- 1234567",
            ]
        )
        changed_history = original_session.replace(
            "- Original historical change.",
            "- Accidentally replaced history.",
        )
        journal.write_text(
            f"{changed_history}\n\n{current_session}\n",
            encoding="utf-8",
        )
        index.write_text(
            "| Session | Title | Status | Commits | Notes |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Historical fixture | Completed | abcdef1 | done |\n"
            "| 2 | Current fixture | Completed | 1234567 | done |\n",
            encoding="utf-8",
        )
        env = {
            **os.environ,
            "SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF": "HEAD",
        }

        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("modifies historical Session 1 from HEAD", result.stdout)
        self.assertIn("edit the intended current session by heading", result.stdout)

        journal.write_text(
            f"{original_session}\n\n{current_session}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1 baseline session(s) for historical edits", result.stdout)

        whitespace_only_history = original_session.replace(
            "- Original historical change.",
            "- Original historical change.   ",
        )
        journal.write_text(
            f"{whitespace_only_history}\n\n{current_session}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout)

        renumbered_history = original_session.replace(
            "## Session 1: Historical fixture",
            "## Session 3: Historical fixture",
        )
        journal.write_text(
            f"{renumbered_history}\n\n{current_session}\n",
            encoding="utf-8",
        )
        index.write_text(
            "| Session | Title | Status | Commits | Notes |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 2 | Current fixture | Completed | 1234567 | done |\n"
            "| 3 | Historical fixture | Completed | abcdef1 | done |\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("removes historical Session 1 from HEAD", result.stdout)

        journal.unlink()
        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("removes historical Session 1 from HEAD", result.stdout)

        shutil.rmtree(root / ".trellis/workspace")
        result = subprocess.run(
            [node, "scripts/sd-ai-command-pack-review-preflight.mjs"],
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("removes historical Session 1 from HEAD", result.stdout)

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

        (root / "docs/current.md").write_text("# Current\n", encoding="utf-8")

        (root / "docs/cite.md").write_text(
            "See [the current guide](./current.md:42) and\n"
            "[the gate](../scripts/sd-ai-command-pack-full-check.sh:12) and\n"
            "`docs/current.md:12:5` and\n"
            "`scripts/sd-ai-command-pack-housekeeping.sh:34-56` for details.\n"
            "Also `scripts/sd-ai-command-pack-install-audit.py:7:3` and\n"
            "`scripts/sd-ai-command-pack-review-local.sh:10-20:4`.\n"
            "Multi-range `scripts/sd-ai-command-pack-full-check.sh:1-2,3-4,5-6`.\n"
            "Approx `scripts/sd-ai-command-pack-install-audit.py:~145` and\n"
            "`scripts/sd-ai-command-pack-review-local.sh:~315-366`.\n"
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
        self.assertNotIn("current.md:42", result.stdout)
        self.assertNotIn("current.md:12:5", result.stdout)
        self.assertNotIn("housekeeping.sh:34-56", result.stdout)
        self.assertNotIn("install-audit.py:7:3", result.stdout)
        self.assertNotIn("review-local.sh:10-20:4", result.stdout)
        self.assertNotIn("full-check.sh:1-2,3-4,5-6", result.stdout)
        self.assertNotIn("install-audit.py:~145", result.stdout)
        self.assertNotIn("review-local.sh:~315-366", result.stdout)

    def test_review_preflight_exempts_design_implement_docs_from_path_check(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        task = root / ".trellis/tasks/07-17-demo"
        task.mkdir(parents=True, exist_ok=True)
        # design.md / implement.md are forward-looking: they name files the task
        # proposes to CREATE, so the path-existence check must skip them.
        (task / "design.md").write_text(
            "Introduce `apps/web/src/lib/designOnly.ts` for the new route.\n",
            encoding="utf-8",
        )
        (task / "implement.md").write_text(
            "Add `apps/web/src/lib/implementOnly.ts` in step 2.\n",
            encoding="utf-8",
        )
        # prd.md describes current state and keeps the existence check.
        (task / "prd.md").write_text(
            "Depends on `apps/web/src/lib/prdRequired.ts` existing today.\n",
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

        # prd.md is still checked, so its missing reference fails the gate.
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "references missing path apps/web/src/lib/prdRequired.ts",
            result.stdout,
        )
        # design.md / implement.md are exempt: their proposed files are not flagged.
        self.assertNotIn("designOnly.ts", result.stdout)
        self.assertNotIn("implementOnly.ts", result.stdout)

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

        squash_merged = subprocess.run(
            ["bash", str(script), baseline, source_head],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_MAIN_PUSH_PR_MERGE": "1",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(squash_merged.returncode, 0, squash_merged.stderr)
        self.assertIn(
            "GitHub-confirmed pull-request merge accepted", squash_merged.stdout
        )

        malformed_evidence = subprocess.run(
            ["bash", str(script), baseline, source_head],
            cwd=root,
            env={
                **os.environ,
                "SD_AI_COMMAND_PACK_MAIN_PUSH_PR_MERGE": "unexpected",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            malformed_evidence.returncode,
            1,
            f"stdout={malformed_evidence.stdout!r} "
            f"stderr={malformed_evidence.stderr!r}",
        )
        self.assertIn("failing closed", malformed_evidence.stderr)

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
