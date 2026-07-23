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

    @staticmethod
    def trellis_task_record(
        name: str,
        *,
        status: str = "planning",
        branch: str | None = None,
        base_branch: str = "main",
        completed_at: str | None = None,
        parent: str | None = None,
        children: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "id": name,
            "name": name,
            "status": status,
            "completedAt": completed_at,
            "branch": branch,
            "base_branch": base_branch,
            "parent": parent,
            "children": children or [],
        }

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
  findContradictoryJournalValidationFallbacks,
  findHistoricalTrellisJournalSessionEdits,
  findMissingTrellisChildReferences,
  findTrellisTaskContextIssues,
  findTrellisTaskContextSeedRows,
  isBoundaryRiskReviewPath,
  isSourceReviewPath,
  isTrellisTaskContextReference,
  maskGeneratedDocumentationPathProvenance,
  parseNumstat,
  parseJournalSessionsFromText,
  parseTrellisTaskArtifactPath,
  parseWorkspaceIndexSessionsFromText,
  reviewRiskCategories,
  reviewRiskMatrix,
  shouldCheckDocumentationPathReference,
  trellisTaskDirectory,
  thrownValueMessage,
  unsupportedNodeVersionMessage,
  validateTrellisTaskMetadata,
  validateTrellisPlanningBaseInheritance,
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
assert.equal(isBoundaryRiskReviewPath('tests/test_project_check.py'), false);
assert.equal(isBoundaryRiskReviewPath('test/helpers/runner.sh'), false);
assert.equal(isBoundaryRiskReviewPath('src/__tests__/runner.ts'), false);
assert.equal(isBoundaryRiskReviewPath('src\\\\tests\\\\runner.ts'), false);
assert.equal(isBoundaryRiskReviewPath('scripts/test_runner.py'), false);
assert.equal(isBoundaryRiskReviewPath('scripts/runner_test.py'), false);
assert.equal(isBoundaryRiskReviewPath('scripts/runner.test.mjs'), false);
assert.equal(isBoundaryRiskReviewPath('scripts/runner.spec.ts'), false);
assert.equal(isBoundaryRiskReviewPath('scripts/test-runner.sh'), true);
assert.equal(isBoundaryRiskReviewPath('scripts/runtime.py'), true);
assert.equal(isBoundaryRiskReviewPath('scripts/sd-ai-command-pack-status.py'), false);
assert.equal(isBoundaryRiskReviewPath('fixtures/runtime.py'), false);
assert.equal(isBoundaryRiskReviewPath('vendor/runtime.js'), false);
assert.equal(isBoundaryRiskReviewPath('generated/runtime.ts'), false);
assert.equal(isBoundaryRiskReviewPath('.github/workflows/checks.yml'), true);
assert.equal(isBoundaryRiskReviewPath('.github/workflows/nested/checks.yml'), false);
assert.equal(isBoundaryRiskReviewPath('.github/dependabot.yml'), false);
assert.equal(isBoundaryRiskReviewPath('package.json'), false);
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
    'structured-input-types',
    'subprocess-command',
    'environment-global-state',
    'path-filesystem',
    'normalization-evidence',
  ],
);
const fullRiskMatrix = reviewRiskMatrix([
  'const parsed = JSON.parse(text);',
  'spawnSync(command);',
  'const token = process.env.TOKEN;',
  'const target = resolve(root, name);',
  'const normalized = createHash("sha256").digest();',
  'const detail = redact_error(str(error));',
].join('\\n'));
assert.deepEqual(fullRiskMatrix.map((entry) => entry.id), [
  'structured-input-types',
  'subprocess-command',
  'environment-global-state',
  'path-filesystem',
  'normalization-evidence',
  'diagnostic-redaction',
]);
assert.deepEqual(Object.keys(fullRiskMatrix[0].variants), ['good', 'base', 'failure']);
assert.deepEqual(
  reviewRiskCategories('customDiagnosticBoundary();', {
    'diagnostic-redaction': ['customDiagnosticBoundary'],
  }),
  ['diagnostic-redaction'],
);
assert.deepEqual(reviewRiskCategories("const words = label.split(' ');"), []);
assert.deepEqual(reviewRiskCategories("words = read_text(value).split(' ')"), []);
assert.deepEqual(
  reviewRiskCategories("const values = process.argv[2].split(',');"),
  ['structured-input-types'],
);
assert.deepEqual(
  reviewRiskCategories("const values = process.env.VALUES?.split(',');"),
  ['structured-input-types', 'environment-global-state'],
);
assert.deepEqual(
  reviewRiskCategories("values = os.getenv('VALUES', default_values()).split(',')"),
  ['structured-input-types', 'environment-global-state'],
);
assert.deepEqual(
  reviewRiskCategories("values = os.environ.get('VALUES', default_values()).split(',')"),
  ['structured-input-types', 'environment-global-state'],
);
assert.deepEqual(
  reviewRiskCategories("const values = readFileSync(path, 'utf8').split('\\n');"),
  ['structured-input-types', 'path-filesystem'],
);
assert.deepEqual(
  reviewRiskCategories("const values = readFileSync(resolve(root, name), 'utf8').split('\\n');"),
  ['structured-input-types', 'path-filesystem'],
);
assert.deepEqual(
  reviewRiskCategories("const values = fs.readFileSync(resolve(root, name), 'utf8').split('\\n');"),
  ['structured-input-types', 'path-filesystem'],
);
assert.deepEqual(
  reviewRiskCategories("values = Path(resolve(root, name)).read_text(encoding='utf8').split('\\n')"),
  ['structured-input-types', 'path-filesystem'],
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
assert.deepEqual(parseTrellisTaskArtifactPath('.trellis/tasks/archive/2026-06/00-bootstrap-guidelines/task.json'), {
  taskDir: '.trellis/tasks/archive/2026-06/00-bootstrap-guidelines',
  artifact: 'task.json',
  archived: true,
});
assert.equal(parseTrellisTaskArtifactPath('.trellis/tasks/archive/task.json'), null);
assert.equal(parseTrellisTaskArtifactPath('.trellis/tasks/archive/not-a-month/07-17-demo/task.json'), null);
assert.equal(parseTrellisTaskArtifactPath('.trellis/tasks/not-dated/check.jsonl'), null);
assert.deepEqual(parseTrellisTaskArtifactPath('.trellis/tasks/archive/2026-07/not-dated/check.jsonl'), {
  taskDir: '.trellis/tasks/archive/2026-07/not-dated',
  artifact: 'check.jsonl',
  archived: true,
});
assert.equal(parseTrellisTaskArtifactPath('.trellis/tasks/archive/2026-07/07-17-demo/prd.md'), null);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: 'codex/demo',
  base_branch: 'codex/parent',
}, '.trellis/tasks/07-17-demo', false), []);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'review',
  completedAt: null,
  branch: 'codex/demo',
  base_branch: 'main',
}, '.trellis/tasks/07-17-demo', false), []);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: null,
  base_branch: 'main',
  priority: 'P2',
  meta: {
    priorityProvenance: {
      sourcePriority: 'P3',
      rationale: 'Promoted because this task owns the broader safety policy.',
      evidence: 'source roadmap',
    },
  },
}, '.trellis/tasks/07-17-demo', false), []);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: null,
  base_branch: 'main',
  priority: 'P2',
  meta: { priorityProvenance: null },
}, '.trellis/tasks/07-17-demo', false), [
  'meta.priorityProvenance must be an object',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: null,
  base_branch: 'main',
  priority: 'P4',
  meta: { priorityProvenance: { sourcePriority: 'P5', rationale: ' ' } },
}, '.trellis/tasks/07-17-demo', false), [
  'priority must be one of P0, P1, P2, P3 when meta.priorityProvenance is declared',
  'meta.priorityProvenance.sourcePriority must be one of P0, P1, P2, P3',
  'meta.priorityProvenance.rationale must be a non-empty string',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: null,
  base_branch: 'main',
  priority: 'P2',
  meta: { priorityProvenance: {} },
}, '.trellis/tasks/07-17-demo', false), [
  'meta.priorityProvenance.sourcePriority must be one of P0, P1, P2, P3',
  'meta.priorityProvenance.rationale must be a non-empty string',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: null,
  base_branch: 'main',
  priority: 'P2',
  meta: { priorityProvenance: { sourcePriority: 'P2', rationale: 'No change.' } },
}, '.trellis/tasks/07-17-demo', false), [
  'meta.priorityProvenance.sourcePriority must differ from priority; remove provenance when priority is unchanged',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: null,
  base_branch: 'main',
  priority: 'P1',
  meta: { priorityProvenance: { sourcePriority: 'P3', rationale: 'x'.repeat(1001) } },
}, '.trellis/tasks/07-17-demo', false), [
  'meta.priorityProvenance.rationale must be at most 1000 characters',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: '00-bootstrap-guidelines',
  name: '00-bootstrap-guidelines',
  status: 'completed',
  completedAt: '2026-06-25',
  branch: null,
  base_branch: 'main',
}, '.trellis/tasks/archive/2026-06/00-bootstrap-guidelines', true), []);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  completedAt: null,
  branch: 'codex/demo',
  base_branch: 'main',
}, '.trellis/tasks/07-17-demo', false), [
  'status must be one of planning, in_progress, review, completed',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'in-progress',
  completedAt: null,
  branch: 'codex/demo',
  base_branch: 'main',
}, '.trellis/tasks/07-17-demo', false), [
  'status must be one of planning, in_progress, review, completed',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'wrong',
  name: 'demo',
  status: 'completed',
  completedAt: null,
  branch: 'main',
  base_branch: 'main',
}, '.trellis/tasks/07-17-demo', false), [
  'id must equal name',
  'completedAt must be a non-empty completion timestamp when status is completed',
  'status completed requires the task record to be under .trellis/tasks/archive/',
  'branch must differ from base_branch',
]);
assert.deepEqual(validateTrellisTaskMetadata({
  id: 'demo',
  name: 'demo',
  status: 'planning',
  completedAt: null,
  branch: ' ',
  base_branch: '',
}, '.trellis/tasks/07-17-demo', false), [
  'base_branch must be a non-empty string',
  'branch must be null or a non-empty string',
]);
assert.deepEqual(validateTrellisPlanningBaseInheritance({
  status: 'planning',
  branch: null,
  base_branch: 'codex/current-feature',
  parent: '07-17-parent',
}, {
  status: 'planning',
  branch: null,
  base_branch: 'main',
}), [
  'base_branch "codex/current-feature" must equal parent base_branch or active branch ("main")',
]);
assert.deepEqual(validateTrellisPlanningBaseInheritance({
  status: 'planning',
  branch: null,
  base_branch: 'main',
  parent: '07-17-parent',
}, {
  status: 'in_progress',
  branch: 'codex/parent',
  base_branch: 'main',
}), []);
assert.deepEqual(validateTrellisPlanningBaseInheritance({
  status: 'planning',
  branch: null,
  base_branch: ' main ',
  parent: '07-17-parent',
}, {
  status: 'in_progress',
  branch: 'codex/parent',
  base_branch: 'main',
}), []);
assert.deepEqual(validateTrellisPlanningBaseInheritance({
  status: 'planning',
  branch: null,
  base_branch: 'codex/parent',
  parent: '07-17-parent',
}, {
  status: 'in_progress',
  branch: 'codex/parent',
  base_branch: 'main',
}), []);
assert.deepEqual(validateTrellisPlanningBaseInheritance({
  status: 'planning',
  branch: 'codex/child',
  base_branch: 'codex/current-feature',
  parent: '07-17-parent',
}, {
  status: 'planning',
  branch: null,
  base_branch: 'main',
}), []);
assert.deepEqual(findMissingTrellisChildReferences(
  'Dependencies: [`07-17-child-extra`](./extra/prd.md) and `07-17-linked`.',
  ['07-17-child', '07-17-linked'],
), ['07-17-child']);
assert.deepEqual(findMissingTrellisChildReferences(
  '| Child |\\n| --- |\\n| `07-17-child` |',
  ['07-17-child'],
), []);
assert.deepEqual(findMissingTrellisChildReferences(
  '# Parent without declared children',
  ['07-17-z-child', '07-17-a-child', '07-17-z-child'],
), ['07-17-a-child', '07-17-z-child']);
assert.deepEqual(findTrellisTaskContextSeedRows('check.jsonl', [
  '{"file":".trellis/spec/backend/index.md","reason":"real"}',
  '{"_example":"remove me","file":"src/example.py"}',
  '{"nested":{"_example":"not a seed row"}}',
  'malformed',
].join('\\n')), [{ file: 'check.jsonl', line: 2 }]);
assert.equal(isTrellisTaskContextReference('.trellis/spec'), true);
assert.equal(isTrellisTaskContextReference('.trellis/spec/'), true);
assert.equal(isTrellisTaskContextReference('.trellis/spec/backend/index.md'), true);
assert.equal(isTrellisTaskContextReference('.trellis/spec/backend/'), true);
assert.equal(isTrellisTaskContextReference('./.trellis/spec/frontend/index.md'), true);
assert.equal(isTrellisTaskContextReference('.trellis/tasks/07-22-demo/research'), true);
assert.equal(isTrellisTaskContextReference('.trellis/tasks/07-22-demo/research/'), true);
assert.equal(isTrellisTaskContextReference('.trellis/tasks/07-22-demo/research/notes.md'), true);
assert.equal(isTrellisTaskContextReference('./.trellis/tasks/07-22-demo/research/notes.md'), true);
assert.equal(isTrellisTaskContextReference('.trellis/tasks/archive/2026-07/07-22-demo/research/'), true);
assert.equal(isTrellisTaskContextReference('.trellis/tasks/archive/2026-07/07-22-demo/research/notes.md'), true);
assert.equal(isTrellisTaskContextReference('src/index.ts'), false);
assert.equal(isTrellisTaskContextReference('../.trellis/spec/backend/index.md'), false);
assert.equal(isTrellisTaskContextReference('.trellis/spec//backend/index.md'), false);
assert.equal(isTrellisTaskContextReference('https://example.com/spec.md'), false);
assert.deepEqual(findTrellisTaskContextIssues('implement.jsonl', [
  '{"file":".trellis/spec/backend/index.md","reason":"real"}',
  '{"file":"tests/test_app.py","reason":"wrong boundary"}',
  '{"_example":"remove me","file":"src/example.py"}',
  'malformed',
].join('\\n')), [
  { file: 'implement.jsonl', line: 2, kind: 'reference' },
  { file: 'implement.jsonl', line: 3, kind: 'seed' },
  { file: 'implement.jsonl', line: 4, kind: 'malformed' },
]);
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
const managedReviewLearnings = [
  '# Review Learnings',
  '<!-- sd-review-learnings:start -->',
  '- PR #1 `remote/missing.py`: mentions `docs/also-missing.md`.',
  '<!-- sd-review-learnings:end -->',
  'Human reference: `docs/human-missing.md`.',
].join('\\n');
const maskedReviewLearnings = maskGeneratedDocumentationPathProvenance(
  'docs/review-learnings.md',
  managedReviewLearnings,
);
assert.equal(maskedReviewLearnings.split('\\n').length, managedReviewLearnings.split('\\n').length);
assert.deepEqual(
  extractDocumentationPathReferences('docs/review-learnings.md', maskedReviewLearnings),
  [{ file: 'docs/review-learnings.md', kind: 'code-span', line: 5, target: 'docs/human-missing.md' }],
);
const incompleteReviewLearnings = '<!-- sd-review-learnings:start -->\\n`docs/still-checked.md`';
assert.equal(
  maskGeneratedDocumentationPathProvenance('docs/review-learnings.md', incompleteReviewLearnings),
  incompleteReviewLearnings,
);
assert.equal(
  maskGeneratedDocumentationPathProvenance('docs/guide.md', managedReviewLearnings),
  managedReviewLearnings,
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
const contradictoryJournal = parseJournalSessionsFromText('.trellis/workspace/dev/journal-2.md', [
  '## Session 2: Contradictory',
  '### Summary',
  '- Full quality gate passed with no failures.',
  '### Status',
  '- [OK] **Completed**',
  '### Main Changes',
  '- Preserved concrete implementation details.',
  '### Testing',
  '- Validation was not recorded for this session.',
  '### Git Commits',
  '- abcdef2',
].join('\\n'))[0];
assert.deepEqual(
  findContradictoryJournalValidationFallbacks(contradictoryJournal),
  [{ line: 9, text: 'Validation was not recorded for this session.' }],
);
assert.deepEqual(
  validateTrellisJournalSessions({
    baselineJournalSessions: [contradictoryJournal],
    developerRelative: '.trellis/workspace/dev',
    indexFile: '.trellis/workspace/dev/index.md',
    indexSessions: null,
    journalSessions: [contradictoryJournal],
  }).failures,
  [],
);
for (const lines of [
  [
    '## Session 3: Incomplete',
    '### Summary',
    '- Tests passed.',
    '### Status',
    '- **In Progress**',
    '### Testing',
    '- Validation not recorded for this session.',
  ],
  [
    '## Session 4: Planning only',
    '### Summary',
    '- Completed planning; no validation was run.',
    '### Status',
    '- [OK] **Completed**',
    '### Testing',
    '- Validation not recorded for this session.',
  ],
  [
    '## Session 5: Explicit failure',
    '### Main Changes',
    '- Full check failed and tests were skipped.',
    '### Status',
    '- [OK] **Completed**',
    '### Testing',
    '- Validation was not recorded for this session.',
  ],
  [
    '## Session 6: Concrete testing',
    '### Summary',
    '- CI passed.',
    '### Status',
    '- [OK] **Completed**',
    '### Testing',
    '- [OK] make check',
  ],
]) {
  const candidate = parseJournalSessionsFromText(
    '.trellis/workspace/dev/journal-boundary.md',
    lines.join('\\n'),
  )[0];
  assert.deepEqual(findContradictoryJournalValidationFallbacks(candidate), []);
}
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
                    "    detail = redact_error(str(error))",
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
                json.dumps(
                    self.trellis_task_record(task_name.removeprefix("07-18-"))
                )
                + "\n",
                encoding="utf-8",
            )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("WARN changed code adds boundary-risk categories", result.stdout)
        for category in (
            "structured-input-types",
            "subprocess-command",
            "environment-global-state",
            "path-filesystem",
            "normalization-evidence",
            "diagnostic-redaction",
        ):
            self.assertIn(category, result.stdout)
        self.assertIn("good=", result.stdout)
        self.assertIn("base=", result.stdout)
        self.assertIn("failure=", result.stdout)
        self.assertIn("cover or disposition this regression matrix", result.stdout)
        matrix_warning = next(
            line
            for line in result.stdout.splitlines()
            if line.startswith("WARN changed code adds boundary-risk categories")
        )
        self.assertLess(len(matrix_warning), 2200)
        self.assertRegex(
            result.stdout,
            r"WARN .* changes \d+ authored source line\(s\) across \d+ file\(s\)",
        )
        self.assertIn("changes 2 Trellis task directories", result.stdout)

    def test_review_preflight_ignores_routine_string_split(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        source = root / "templates/scripts/split_fixture.mjs"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "export const words = (label) => label.split(' ');\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("structured-input-types", result.stdout)
        self.assertRegex(
            result.stdout,
            r"PASS checked \d+ changed code path\(s\); no boundary-risk trigger was added",
        )

    def test_review_preflight_uses_configured_literal_category_signals(self) -> None:
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
                    "reviewRiskCategorySignals": {
                        "diagnostic-redaction": ["  customDiagnosticBoundary  "]
                    }
                }
            ),
            encoding="utf-8",
        )
        source = root / "src/runtime.py"
        source.parent.mkdir(parents=True)
        source.write_text("customDiagnosticBoundary(detail)\n", encoding="utf-8")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "boundary-risk categories diagnostic-redaction", result.stdout
        )
        self.assertNotIn("structured-input-types", result.stdout)

    def test_review_preflight_scans_workflow_run_and_environment_boundaries(
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

        workflow = root / ".github/workflows/checks.yml"
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            "jobs:\n  checks:\n    env:\n      TOKEN: value\n    steps:\n"
            "      - run: python scripts/check.py\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("subprocess-command", result.stdout)
        self.assertIn("environment-global-state", result.stdout)

    def test_review_preflight_ignores_boundary_tokens_added_only_in_tests(
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

        test_source = root / "tests/test_runtime_boundary.py"
        test_source.parent.mkdir(parents=True)
        test_source.write_text(
            "import os\n"
            "import subprocess\n"
            "from pathlib import Path\n"
            "subprocess.run(['tool'])\n"
            "target = Path(os.environ.get('TARGET', '.'))\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("changed code adds", result.stdout)
        self.assertIn(
            "PASS no changed code paths require a first-review boundary-risk sweep",
            result.stdout,
        )

    def test_review_preflight_mixed_diff_scans_only_production_source(
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

        production_source = root / "scripts/runtime_boundary.py"
        production_source.write_text(
            "import subprocess\nsubprocess.run(['tool'])\n",
            encoding="utf-8",
        )
        test_source = root / "tests/test_runtime_boundary.py"
        test_source.parent.mkdir(parents=True)
        test_source.write_text(
            "import hashlib\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "parsed = json.loads(os.environ.get('VALUE', '{}'))\n"
            "digest = hashlib.sha256(str(Path(parsed['path'])).encode()).hexdigest()\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "WARN changed code adds boundary-risk categories subprocess-command",
            result.stdout,
        )
        self.assertNotIn("structured-input-types", result.stdout)
        self.assertNotIn("path-filesystem", result.stdout)
        self.assertNotIn("environment-global-state", result.stdout)
        self.assertNotIn("normalization-evidence", result.stdout)

    def test_review_preflight_ignores_upstream_only_changes_behind_base(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        upstream = root / "scripts/upstream.py"
        upstream.write_text(
            "import subprocess\n"
            + "\n".join(f"UPSTREAM_{index} = {index}" for index in range(12))
            + "\n",
            encoding="utf-8",
        )
        feature = root / "scripts/feature.py"
        feature.write_text("FEATURE = 1\n", encoding="utf-8")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        self.run_git(root, "branch", "-M", "main")
        self.run_git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

        self.run_git(root, "switch", "-c", "feature")
        feature.write_text("FEATURE = 2\n", encoding="utf-8")
        self.run_git(root, "add", "scripts/feature.py")
        self.run_git(root, "commit", "-m", "feature change")

        self.run_git(root, "switch", "main")
        upstream.write_text("SAFE = True\n", encoding="utf-8")
        self.run_git(root, "add", "scripts/upstream.py")
        self.run_git(root, "commit", "-m", "advance base")
        self.run_git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        self.run_git(root, "switch", "feature")

        config = root / ".sd-ai-command-pack/review-preflight.json"
        config.write_text(
            json.dumps({"sourceReviewWarningLines": 5}), encoding="utf-8"
        )
        env = os.environ.copy()
        env["SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF"] = "origin/main"
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
        self.assertNotRegex(result.stdout, r"WARN .* authored source line\(s\)")
        self.assertNotIn("boundary-risk categories subprocess-command", result.stdout)
        self.assertRegex(
            result.stdout,
            r"PASS checked \d+ changed code path\(s\); no boundary-risk trigger was added",
        )

    def test_review_preflight_warns_and_falls_back_without_merge_base(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        empty_tree = subprocess.run(
            ["git", "mktree"],
            cwd=root,
            input="",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(empty_tree.returncode, 0, empty_tree.stdout)
        unrelated = self.git_output(
            root,
            "commit-tree",
            empty_tree.stdout.strip(),
            "-m",
            "unrelated base",
        )
        self.run_git(root, "update-ref", "refs/remotes/origin/main", unrelated)

        env = os.environ.copy()
        env["SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF"] = "origin/main"
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
        self.assertIn(
            "WARN could not resolve the merge base of origin/main and HEAD; "
            "falling back to origin/main.",
            result.stdout,
        )

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
        self.assertNotIn("boundary-risk categories subprocess-command", result.stdout)
        self.assertNotIn("no boundary-risk trigger was added", result.stdout)
        self.assertIn(
            "includes a large file diff (4 lines): scripts/large-untracked.py",
            result.stdout,
        )

    def test_review_preflight_bounds_skipped_risk_path_details(self) -> None:
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
            json.dumps({"untrackedFileReadLimitBytes": 8}), encoding="utf-8"
        )
        for index in range(7):
            (root / f"scripts/risk-{index}.py").write_text(
                "import subprocess\nsubprocess.run(['tool'])\n",
                encoding="utf-8",
            )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        skipped_warning = next(
            line
            for line in result.stdout.splitlines()
            if "boundary-risk content scan skipped 7 oversized" in line
        )
        self.assertIn("(+2 more)", skipped_warning)
        self.assertEqual(skipped_warning.count("scripts/risk-"), 5)

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

    def test_review_preflight_accepts_valid_changed_task_metadata(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        parent_name = "07-21-parent"
        child_name = "07-21-child"
        parent = root / ".trellis/tasks" / parent_name
        child = root / ".trellis/tasks" / child_name
        archived = root / ".trellis/tasks/archive/2026-07/07-20-archived"
        for task in (parent, child, archived):
            task.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "parent",
                    branch="codex/parent",
                    children=[child_name],
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            f"# Parent\n\nDependency: `{child_name}`.\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "child",
                    branch="codex/child",
                    base_branch="codex/parent",
                    parent=parent_name,
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (archived / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "archived",
                    status="completed",
                    branch="codex/archived",
                    completed_at="2026-07-20",
                )
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 3 changed Trellis task metadata record(s)",
            result.stdout,
        )

    def test_review_preflight_accepts_declared_task_priority_provenance(
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
        task = root / ".trellis/tasks/07-23-promoted"
        task.mkdir(parents=True)
        record = self.trellis_task_record("promoted")
        record["priority"] = "P1"
        record["meta"] = {
            "priorityProvenance": {
                "sourcePriority": "P3",
                "rationale": "Implements an approved shared dependency.",
            }
        }
        (task / "task.json").write_text(
            json.dumps(record) + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 1 changed Trellis task metadata record(s)",
            result.stdout,
        )

    def test_review_preflight_rejects_invalid_task_priority_provenance(
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
        task = root / ".trellis/tasks/07-23-contradictory"
        task.mkdir(parents=True)
        record = self.trellis_task_record("contradictory")
        record["priority"] = "P2"
        record["meta"] = {
            "priorityProvenance": {
                "sourcePriority": "P2",
                "rationale": "SECRET_RATIONALE " + ("x" * 1000),
            }
        }
        (task / "task.json").write_text(
            json.dumps(record) + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "task.json field meta.priorityProvenance.sourcePriority must "
            "differ from priority",
            result.stdout,
        )
        self.assertIn(
            "task.json field meta.priorityProvenance.rationale must be at most "
            "1000 characters",
            result.stdout,
        )
        self.assertNotIn("SECRET_RATIONALE", result.stdout)

    def test_review_preflight_rejects_unrelated_deferred_planning_base(
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

        parent_name = "07-22-parent"
        child_name = "07-22-child"
        parent = root / ".trellis/tasks" / parent_name
        child = root / ".trellis/tasks" / child_name
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("parent", children=[child_name])
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            f"# Parent\n\n- `{child_name}`\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "child",
                    base_branch="codex/current-feature",
                    parent=parent_name,
                )
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            f'{child_name}/task.json field base_branch "codex/current-feature" '
            'must equal parent base_branch or active branch ("main")',
            result.stdout,
        )

    def test_review_preflight_accepts_parent_grounded_deferred_planning_bases(
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

        parent_name = "07-22-parent"
        base_child_name = "07-22-base-child"
        stacked_child_name = "07-22-stacked-child"
        parent = root / ".trellis/tasks" / parent_name
        parent.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "parent",
                    status="in_progress",
                    branch="codex/parent",
                    children=[base_child_name, stacked_child_name],
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            "# Parent\n\n"
            f"Dependencies: `{base_child_name}` and [{stacked_child_name}]"
            f"(../{stacked_child_name}/prd.md).\n",
            encoding="utf-8",
        )
        for child_name, base_branch in (
            (base_child_name, "main"),
            (stacked_child_name, "codex/parent"),
        ):
            child = root / ".trellis/tasks" / child_name
            child.mkdir(parents=True)
            (child / "task.json").write_text(
                json.dumps(
                    self.trellis_task_record(
                        child_name.removeprefix("07-22-"),
                        base_branch=base_branch,
                        parent=parent_name,
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            (child / "prd.md").write_text(
                f"# {child_name}\n",
                encoding="utf-8",
            )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 2 deferred planning child base(s) and 1 active parent PRD child map(s)",
            result.stdout,
        )

    def test_review_preflight_rejects_changed_parent_prd_child_drift(
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

        parent_name = "07-22-parent"
        child_name = "07-22-child"
        parent = root / ".trellis/tasks" / parent_name
        child = root / ".trellis/tasks" / child_name
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("parent", children=[child_name])
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            f"# Parent\n\nDependency: `{child_name}-extension`.\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("child", parent=parent_name)
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            f"{parent_name}/prd.md does not reference declared child {child_name}",
            result.stdout,
        )

    def test_review_preflight_checks_prd_only_child_map_changes(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        parent_name = "07-22-parent"
        child_name = "07-22-child"
        parent = root / ".trellis/tasks" / parent_name
        child = root / ".trellis/tasks" / child_name
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("parent", children=[child_name])
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            f"# Parent\n\n- `{child_name}`\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("child", parent=parent_name)
            )
            + "\n",
            encoding="utf-8",
        )
        (child / "prd.md").write_text(
            "# Child\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline topology")

        (parent / "prd.md").write_text(
            "# Parent\n\nThe child reference was removed.\n",
            encoding="utf-8",
        )
        missing = self.run_review_preflight(node, root)
        self.assertEqual(missing.returncode, 1, missing.stdout)
        self.assertIn(
            f"{parent_name}/prd.md does not reference declared child {child_name}",
            missing.stdout,
        )

        (parent / "prd.md").write_text(
            f"# Parent\n\nDependency: [{child_name}](../{child_name}/prd.md).\n",
            encoding="utf-8",
        )
        restored = self.run_review_preflight(node, root)
        self.assertEqual(restored.returncode, 0, restored.stdout)
        self.assertIn(
            "checked 0 deferred planning child base(s) and 1 active parent PRD child map(s)",
            restored.stdout,
        )

    def test_review_preflight_fails_closed_for_unsafe_parent_prds(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        parent_kinds = ("missing", "symlinked", "directory", "oversized")
        for kind in parent_kinds:
            parent_name = f"07-22-{kind}-parent"
            child_name = f"07-22-{kind}-child"
            parent = root / ".trellis/tasks" / parent_name
            child = root / ".trellis/tasks" / child_name
            parent.mkdir(parents=True)
            child.mkdir(parents=True)
            (parent / "task.json").write_text(
                json.dumps(
                    self.trellis_task_record(
                        f"{kind}-parent", children=[child_name]
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            (child / "task.json").write_text(
                json.dumps(
                    self.trellis_task_record(
                        f"{kind}-child", parent=parent_name
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            if kind == "directory":
                (parent / "prd.md").mkdir()
            elif kind == "oversized":
                (parent / "prd.md").write_text(
                    "x" * (1024 * 1024 + 1),
                    encoding="utf-8",
                )

        outside = root / "outside-prd.txt"
        outside.write_text("# Outside\n", encoding="utf-8")
        try:
            (
                root
                / ".trellis/tasks/07-22-symlinked-parent/prd.md"
            ).symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "07-22-missing-parent/prd.md is missing",
            result.stdout,
        )
        self.assertIn(
            "07-22-symlinked-parent/prd.md is a symlink; task PRD must be a regular file",
            result.stdout,
        )
        self.assertIn(
            "07-22-directory-parent/prd.md is not a regular file; task PRD must be a regular file",
            result.stdout,
        )
        self.assertIn(
            "07-22-oversized-parent/prd.md exceeds the bounded task PRD read limit",
            result.stdout,
        )

    def test_review_preflight_grandfathers_unchanged_parent_prd_drift(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        parent_name = "07-18-legacy-parent"
        child_name = "07-18-legacy-child"
        parent = root / ".trellis/tasks" / parent_name
        child = root / ".trellis/tasks" / child_name
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "legacy-parent", children=[child_name]
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            "# Legacy parent\n\nThe historical map is incomplete.\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "legacy-child", parent=parent_name
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline legacy topology")
        (root / ".trellis/config.yaml").write_text(
            "# unrelated change\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "no changed Trellis task topology requires semantic validation",
            result.stdout,
        )
        self.assertNotIn("legacy-child", result.stdout)

    def test_review_preflight_ignores_changed_archived_parent_prd_drift(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        parent_name = "07-18-archived-parent"
        child_name = "07-18-archived-child"
        archive = root / ".trellis/tasks/archive/2026-07"
        parent = archive / parent_name
        child = archive / child_name
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "archived-parent",
                    status="completed",
                    completed_at="2026-07-18T12:00:00Z",
                    children=[child_name],
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            f"# Archived parent\n\n- `{child_name}`\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "archived-child",
                    status="completed",
                    completed_at="2026-07-18T12:00:00Z",
                    parent=parent_name,
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline archived topology")

        (parent / "prd.md").write_text(
            "# Archived parent\n\nHistorical child prose was removed.\n",
            encoding="utf-8",
        )
        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "no changed Trellis task topology requires semantic validation",
            result.stdout,
        )
        self.assertNotIn("archived-child", result.stdout)

    def test_review_preflight_grandfathers_unchanged_task_metadata(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        legacy = root / ".trellis/tasks/07-17-legacy"
        legacy.mkdir(parents=True)
        legacy_record = self.trellis_task_record("legacy", branch="main")
        legacy_record["id"] = "historical-mismatch"
        (legacy / "task.json").write_text(
            json.dumps(legacy_record) + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline with legacy metadata")
        (root / ".trellis/config.yaml").write_text("# changed\n", encoding="utf-8")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "no changed Trellis task metadata records require integrity checks",
            result.stdout,
        )
        self.assertNotIn("historical-mismatch", result.stdout)

    def test_review_preflight_rejects_invalid_changed_task_metadata_fields(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        task = root / ".trellis/tasks/07-21-path-name"
        task.mkdir(parents=True)
        record = self.trellis_task_record(
            "record-name",
            status="in_progress",
            branch="main",
            base_branch="main",
            completed_at="2026-07-21",
        )
        record["id"] = "different-id"
        (task / "task.json").write_text(
            json.dumps(record) + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("task.json field id must equal name", result.stdout)
        self.assertIn(
            "task.json field name must match the dated task directory suffix \"path-name\"",
            result.stdout,
        )
        self.assertIn(
            "task.json field completedAt must be null when status is in_progress",
            result.stdout,
        )
        self.assertIn(
            "task.json field branch must differ from base_branch",
            result.stdout,
        )

    def test_review_preflight_rejects_nonreciprocal_task_links(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        parent_name = "07-21-parent"
        child_name = "07-21-child"
        parent = root / ".trellis/tasks" / parent_name
        child = root / ".trellis/tasks" / child_name
        parent.mkdir(parents=True)
        child.mkdir(parents=True)
        (parent / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "parent", children=["07-21-missing"]
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (parent / "prd.md").write_text(
            "# Parent\n\n- `07-21-missing`\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("child", parent=parent_name)
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            f'task.json field parent references {parent_name}, but its children field does not include {child_name}',
            result.stdout,
        )
        self.assertIn(
            "task.json field children references missing task 07-21-missing",
            result.stdout,
        )

    def test_review_preflight_rejects_unverifiable_changed_task_metadata(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        malformed = root / ".trellis/tasks/archive/2026-07/07-20-malformed"
        malformed.mkdir(parents=True)
        (malformed / "task.json").write_text("{malformed\n", encoding="utf-8")
        misplaced = root / ".trellis/tasks/archive/07-20-misplaced"
        misplaced.mkdir(parents=True)
        (misplaced / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "misplaced", status="completed", completed_at="2026-07-20"
                )
            )
            + "\n",
            encoding="utf-8",
        )
        wrong_bucket = root / ".trellis/tasks/archive/not-a-month/07-20-wrong-bucket"
        wrong_bucket.mkdir(parents=True)
        (wrong_bucket / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "wrong-bucket", status="completed", completed_at="2026-07-20"
                )
            )
            + "\n",
            encoding="utf-8",
        )
        symlinked = root / ".trellis/tasks/07-21-symlinked"
        symlinked.mkdir(parents=True)
        outside = root / "outside-task.json"
        outside.write_text(
            json.dumps(self.trellis_task_record("symlinked")) + "\n",
            encoding="utf-8",
        )
        try:
            (symlinked / "task.json").symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "07-20-malformed/task.json could not be parsed as JSON while checking task metadata integrity",
            result.stdout,
        )
        self.assertIn(
            "07-21-symlinked/task.json is a symlink; task metadata must be a regular file",
            result.stdout,
        )
        self.assertIn(
            "archive/07-20-misplaced/task.json is not in a supported Trellis task layout",
            result.stdout,
        )
        self.assertIn(
            "archive/not-a-month/07-20-wrong-bucket/task.json is not in a supported Trellis task layout",
            result.stdout,
        )

    def test_review_preflight_rejects_present_misplaced_task_context_only(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        deleted = root / ".trellis/tasks/archive/not-a-month/07-20-deleted"
        deleted.mkdir(parents=True)
        (deleted / "check.jsonl").write_text("", encoding="utf-8")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline with misplaced context")
        (deleted / "check.jsonl").unlink()
        present = root / ".trellis/tasks/archive/not-a-month/07-21-present"
        present.mkdir(parents=True)
        (present / "implement.jsonl").write_text("", encoding="utf-8")
        undated = root / ".trellis/tasks/archive/2026-07/not-dated"
        undated.mkdir(parents=True)
        (undated / "check.jsonl").write_text("", encoding="utf-8")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "archive/not-a-month/07-21-present/implement.jsonl is not in a supported Trellis task layout",
            result.stdout,
        )
        self.assertNotIn("archive/2026-07/not-dated/check.jsonl is not in", result.stdout)
        self.assertNotIn("07-20-deleted/check.jsonl is not in", result.stdout)

    def test_review_preflight_rejects_broken_symlink_misplaced_task_context(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        misplaced = root / ".trellis/tasks/archive/not-a-month/07-21-broken"
        misplaced.mkdir(parents=True)
        try:
            (misplaced / "check.jsonl").symlink_to(root / "missing-context.jsonl")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "archive/not-a-month/07-21-broken/check.jsonl is not in a supported Trellis task layout",
            result.stdout,
        )

    def test_review_preflight_rejects_unstatable_misplaced_task_context(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")
        if os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() == 0:
            self.skipTest("POSIX non-root permissions are required")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")
        archive_bucket = root / ".trellis/tasks/archive/not-a-month"
        misplaced = archive_bucket / "07-21-unstatable/check.jsonl"
        misplaced.parent.mkdir(parents=True)
        misplaced.write_text("", encoding="utf-8")
        self.run_git(
            root,
            "add",
            ".trellis/tasks/archive/not-a-month/07-21-unstatable/check.jsonl",
        )

        archive_bucket.chmod(0)
        try:
            result = self.run_review_preflight(node, root)
        finally:
            archive_bucket.chmod(0o755)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "archive/not-a-month/07-21-unstatable/check.jsonl is not in a supported Trellis task layout",
            result.stdout,
        )

    def test_review_preflight_checks_changed_context_in_every_task_phase(self) -> None:
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
        task_json.write_text(
            json.dumps(self.trellis_task_record("demo")) + "\n",
            encoding="utf-8",
        )
        seed = '{"_example":"replace me"}\n'
        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")

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

        context = '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n'
        (task / "implement.jsonl").write_text(context, encoding="utf-8")
        (task / "check.jsonl").write_text("", encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 2 changed Trellis task context file(s)",
            result.stdout,
        )

        (task / "implement.jsonl").write_text(
            context + "malformed non-empty row\n", encoding="utf-8"
        )
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-17-demo/implement.jsonl:2 is not valid JSONL",
            result.stdout,
        )

        task_json.write_text(
            json.dumps(self.trellis_task_record("demo", status="in_progress"))
            + "\n",
            encoding="utf-8",
        )
        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-17-demo/check.jsonl:1 still contains",
            result.stdout,
        )
        self.assertIn(
            ".trellis/tasks/07-17-demo/implement.jsonl:1 still contains",
            result.stdout,
        )

        self.assertIn(
            'replace it with grounded {"file": "<path>", "reason": "<why>"} context or leave the file empty',
            result.stdout,
        )

        task_json.write_text(
            json.dumps(
                self.trellis_task_record(
                    "demo", status="completed", completed_at="2026-07-17"
                )
            )
            + "\n",
            encoding="utf-8",
        )
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
        task_json.write_text(
            json.dumps(self.trellis_task_record("demo", status="in_progress"))
            + "\n",
            encoding="utf-8",
        )
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 2 changed Trellis task context file(s)",
            result.stdout,
        )

    def test_review_preflight_rejects_changed_non_spec_context_paths(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline")

        task = root / ".trellis/tasks/07-22-context-boundary"
        task.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps(self.trellis_task_record("context-boundary")) + "\n",
            encoding="utf-8",
        )
        (task / "implement.jsonl").write_text(
            '{"file":"src/app.py","reason":"implementation"}\n',
            encoding="utf-8",
        )
        (task / "check.jsonl").write_text(
            '{"file":"tests/test_app.py","reason":"tests"}\n',
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-22-context-boundary/implement.jsonl:1 contains a task context reference outside",
            result.stdout,
        )
        self.assertIn(
            ".trellis/tasks/07-22-context-boundary/check.jsonl:1 contains a task context reference outside",
            result.stdout,
        )
        self.assertIn(".trellis/spec/** or .trellis/tasks/**/research/** only", result.stdout)

        (task / "implement.jsonl").write_text(
            '{"file":".trellis/spec/backend/index.md","reason":"implementation contract"}\n',
            encoding="utf-8",
        )
        (task / "check.jsonl").write_text(
            '{"file":".trellis/tasks/07-22-context-boundary/research/cases.md","reason":"research evidence"}\n',
            encoding="utf-8",
        )
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_review_preflight_ignores_unchanged_planning_context(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        task = root / ".trellis/tasks/07-17-legacy-planning"
        task.mkdir(parents=True)
        task_json = task / "task.json"
        planning_record = self.trellis_task_record("legacy-planning")
        task_json.write_text(
            json.dumps(planning_record) + "\n",
            encoding="utf-8",
        )
        seed = '{"_example":"legacy planning"}\n'
        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline with planning task")

        planning_record["description"] = "metadata only"
        task_json.write_text(json.dumps(planning_record) + "\n", encoding="utf-8")
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "no changed Trellis task context manifests require validation",
            result.stdout,
        )
        self.assertNotIn("legacy-planning/implement.jsonl:1", result.stdout)
        self.assertNotIn("legacy-planning/check.jsonl:1", result.stdout)

    def test_review_preflight_checks_sibling_context_for_changed_active_task(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        task = root / ".trellis/tasks/07-17-active"
        task.mkdir(parents=True)
        task_json = task / "task.json"
        task_json.write_text(
            json.dumps(self.trellis_task_record("active")) + "\n",
            encoding="utf-8",
        )
        seed = '{"_example":"unchanged scaffold"}\n'
        (task / "implement.jsonl").write_text(seed, encoding="utf-8")
        (task / "check.jsonl").write_text(seed, encoding="utf-8")
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline with active task")

        task_json.write_text(
            json.dumps(self.trellis_task_record("active", status="in_progress"))
            + "\n",
            encoding="utf-8",
        )
        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-17-active/implement.jsonl:1 still contains",
            result.stdout,
        )
        self.assertIn(
            ".trellis/tasks/07-17-active/check.jsonl:1 still contains",
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
        legacy = root / ".trellis/tasks/archive/2026-07/07-17-legacy"
        legacy.mkdir(parents=True)
        (legacy / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "legacy", status="completed", completed_at="2026-07-17"
                )
            )
            + "\n",
            encoding="utf-8",
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

        current = root / ".trellis/tasks/archive/2026-07/07-17-current"
        current.mkdir(parents=True)
        (current / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "current", status="completed", completed_at="2026-07-17"
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (current / "implement.jsonl").write_text(
            '{"_example":"current"}\n', encoding="utf-8"
        )
        (current / "check.jsonl").write_text(
            '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
            encoding="utf-8",
        )
        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/archive/2026-07/07-17-current/implement.jsonl:1 still contains",
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
        task = root / ".trellis/tasks/archive/2026-07/07-17-symlinked"
        task.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "symlinked", status="completed", completed_at="2026-07-17"
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (task / "check.jsonl").write_text(
            '{"file":".trellis/spec/backend/index.md","reason":"grounded"}\n',
            encoding="utf-8",
        )
        try:
            (task / "implement.jsonl").symlink_to(outside)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_review_preflight(node, root)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 1 changed Trellis task context file(s)",
            result.stdout,
        )

    def test_review_preflight_rejects_completed_task_outside_archive(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        self.run_git(root, "config", "user.email", "test@example.com")
        self.run_git(root, "config", "user.name", "Test User")
        task = root / ".trellis/tasks/07-19-stranded"
        child_name = "07-19-child"
        child = root / ".trellis/tasks" / child_name
        task.mkdir(parents=True)
        child.mkdir(parents=True)
        (task / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "stranded",
                    status="completed",
                    completed_at="2026-07-19",
                    children=[child_name],
                )
            )
            + "\n",
            encoding="utf-8",
        )
        (task / "prd.md").write_text(
            f"# Stranded\n\n- `{child_name}`\n",
            encoding="utf-8",
        )
        (child / "task.json").write_text(
            json.dumps(
                self.trellis_task_record("child", parent="07-19-stranded")
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_git(root, "add", "-A")
        self.run_git(root, "commit", "-m", "baseline completed parent")

        (task / "prd.md").write_text(
            "# Stranded\n\nThe stale child prose changed.\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "FAIL .trellis/tasks/07-19-stranded/task.json has status completed outside",
            result.stdout,
        )
        self.assertIn(
            "task.py archive 07-19-stranded",
            result.stdout,
        )
        self.assertNotIn(
            "07-19-stranded/prd.md does not reference declared child",
            result.stdout,
        )

    def test_review_preflight_allows_archived_noncompleted_and_symlinked_tasks(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        for name, status in (("07-19-planned", "planning"), ("07-19-active", "in_progress")):
            task = root / ".trellis/tasks" / name
            task.mkdir(parents=True)
            (task / "task.json").write_text(
                json.dumps(
                    self.trellis_task_record(
                        name.removeprefix("07-19-"), status=status
                    )
                )
                + "\n",
                encoding="utf-8",
            )
        archived = root / ".trellis/tasks/archive/2026-07/07-19-complete"
        archived.mkdir(parents=True)
        (archived / "task.json").write_text(
            json.dumps(
                self.trellis_task_record(
                    "complete", status="completed", completed_at="2026-07-19"
                )
            )
            + "\n",
            encoding="utf-8",
        )
        outside = root / "outside-completed-task"
        outside.mkdir()
        (outside / "task.json").write_text(
            '{"id":"symlinked","status":"completed"}\n', encoding="utf-8"
        )
        try:
            (root / ".trellis/tasks/07-19-symlinked").symlink_to(
                outside, target_is_directory=True
            )
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlinks are not available: {exc}")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "checked 2 active-root Trellis task record(s); none is completed outside archive",
            result.stdout,
        )

    def test_review_preflight_rejects_malformed_active_root_task_record(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        self.assertEqual(self.run_install(root).returncode, 0)
        task = root / ".trellis/tasks/07-19-malformed"
        task.mkdir(parents=True)
        (task / "task.json").write_text("{malformed\n", encoding="utf-8")

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/tasks/07-19-malformed/task.json could not be parsed as JSON while checking completed-task location",
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

    def test_review_preflight_rejects_contradictory_journal_validation(self) -> None:
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
                    "## Session 1: Contradictory fixture",
                    "### Summary",
                    "- Full quality gate passed.",
                    "### Status",
                    "- [OK] **Completed**",
                    "### Main Changes",
                    "- Added the implementation.",
                    "### Testing",
                    "- Validation not recorded for this session.",
                    "### Git Commits",
                    "- abcdef1",
                ]
            ),
            encoding="utf-8",
        )
        (workspace / "index.md").write_text(
            "| Session | Title | Status | Commits | Notes |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| 1 | Contradictory fixture | Completed | abcdef1 | done |\n",
            encoding="utf-8",
        )

        result = self.run_review_preflight(node, root)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            ".trellis/workspace/dev/journal-1.md:9 completed Session 1 claims successful validation",
            result.stdout,
        )
        self.assertIn(
            'Testing still says "Validation not recorded for this session."',
            result.stdout,
        )
        self.assertIn("record concrete validation evidence", result.stdout)

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

    def test_review_preflight_preserves_archived_deleted_path_references(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        for archived in (True, False):
            with self.subTest(archived=archived):
                root = self.make_repo()
                self.assertEqual(self.run_install(root).returncode, 0)
                self.run_git(root, "config", "user.email", "test@example.com")
                self.run_git(root, "config", "user.name", "Test User")
                retired = root / "docs/retired-roadmap.md"
                retired.write_text("# Retired roadmap\n", encoding="utf-8")
                if archived:
                    task = (
                        root
                        / ".trellis/tasks/archive/2026-07/07-20-historical-path"
                    )
                    record = self.trellis_task_record(
                        "historical-path",
                        status="completed",
                        completed_at="2026-07-20",
                    )
                else:
                    task = root / ".trellis/tasks/07-23-live-path"
                    record = self.trellis_task_record("live-path")
                task.mkdir(parents=True)
                (task / "task.json").write_text(
                    json.dumps(record) + "\n",
                    encoding="utf-8",
                )
                (task / "prd.md").write_text(
                    "Historical source: `docs/retired-roadmap.md`.\n",
                    encoding="utf-8",
                )
                self.run_git(root, "add", "-A")
                self.run_git(root, "commit", "-m", "baseline with roadmap")
                retired.unlink()

                result = self.run_review_preflight(node, root)

                if archived:
                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertNotIn("retired-roadmap.md", result.stdout)
                else:
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn(
                        ".trellis/tasks/07-23-live-path/prd.md:1 references "
                        "missing path docs/retired-roadmap.md",
                        result.stdout,
                    )

    def test_review_preflight_ignores_only_managed_review_provenance_paths(
        self,
    ) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available on PATH")

        root = self.make_repo()
        result = self.run_install(root)
        self.assertEqual(result.returncode, 0, result.stdout)

        target = root / "docs/review-learnings.md"
        target.write_text(
            "# Review Learnings\n\n"
            "<!-- sd-review-learnings:start -->\n"
            "- PR #7 `remote/deleted.py`: mentions `docs/remote-missing.md`.\n"
            "<!-- sd-review-learnings:end -->\n\n"
            "Human reference: `docs/SD_AI_COMMAND_PACK.md`.\n",
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
        self.assertNotIn("remote/deleted.py", result.stdout)
        self.assertNotIn("docs/remote-missing.md", result.stdout)

        with target.open("a", encoding="utf-8") as stream:
            stream.write("Human broken reference: `docs/human-missing.md`.\n")

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
            "docs/review-learnings.md:8 references missing path "
            "docs/human-missing.md",
            result.stdout,
        )
        self.assertNotIn("remote/deleted.py", result.stdout)
        self.assertNotIn("docs/remote-missing.md", result.stdout)

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

    def test_review_preflight_rejects_unknown_boundary_category_config(
        self,
    ) -> None:
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
        config_dir = root / ".sd-ai-command-pack"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "review-preflight.json").write_text(
            json.dumps(
                {
                    "reviewRiskCategorySignals": {
                        "unknown-category": ["customBoundary"]
                    }
                }
            ),
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
            "reviewRiskCategorySignals contains unknown category unknown-category",
            result.stdout,
        )

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
