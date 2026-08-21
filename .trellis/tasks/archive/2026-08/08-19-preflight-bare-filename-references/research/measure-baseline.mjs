import { readFileSync, existsSync, statSync, readdirSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// Repo root is four levels up from research/ ; override with argv[2].
const root = process.argv[2]
  || resolve(dirname(fileURLToPath(import.meta.url)), '../../../..');
const { shouldCheckDocumentationPathReference, isAbsentPathMarked } =
  await import(`${root}/scripts/sd-ai-command-pack-review-preflight.mjs`);

const roots = ['AGENTS.md','README.md','CLAUDE.md','docs','.github/instructions','.github/prompts','.trellis/spec','.trellis/tasks'];
const exts = ['.md','.mdx','.prompt.md','.toml','.jsonl'];

function walk(dir, out) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out); else out.push(p);
  }
  return out;
}

const files = [];
for (const r of roots) {
  const abs = join(root, r);
  if (!existsSync(abs)) continue;
  const cands = statSync(abs).isDirectory() ? walk(abs, []) : [abs];
  for (const c of cands) if (exts.some((x) => c.endsWith(x))) files.push(c.slice(root.length + 1));
}

const guard = [...new Set(files)].sort().filter((file) => {
  const base = file.split('/').pop();
  return !(file === 'docs/SD_AI_COMMAND_PACK.md' || file === 'docs/repomix-map.md'
    || file.startsWith('.trellis/tasks/archive/')
    || ((base === 'design.md' || base === 'implement.md') && file.startsWith('.trellis/tasks/')));
});

const tracked = execSync('git ls-files', { cwd: root, encoding: 'utf8', maxBuffer: 1 << 28 }).split('\n').filter(Boolean);
const byBasename = new Map();
for (const t of tracked) {
  const b = t.split('/').pop();
  if (!byBasename.has(b)) byBasename.set(b, []);
  byBasename.get(b).push(t);
}
const optionalPaths = new Set(['.sd-ai-command-pack/installed-targets.txt','.sd-ai-command-pack/local-only.txt','.sd-ai-command-pack/manifest.json','.sd-ai-command-pack/pr-body-scope.json','.sd-ai-command-pack/provenance.json','.sd-ai-command-pack/review-preflight.json','.trellis/.developer','.trellis/.template-hashes.json','.trellis/audit/ledger.md','ARCHITECTURE.md','ARCHITECTURE_OVERVIEW.md','docs/ARCHITECTURE.md','docs/ARCHITECTURE_OVERVIEW.md','docs/TRELLIS_REVIEW_PR_PACK.md','docs/repomix-map.md','docs/review-learnings.md','package.json','scripts/check-review-preflight.mjs','scripts/classify-ci-changes.sh','scripts/classify_ci_changes.sh']);
const prefixes = ['.agent/','.agents/','.claude/','.codebuddy/','.codex/','.cursor/','.devin/','.factory/','.gemini/','.gito/','.github/','.kiro/','.kilocode/','.opencode/','.pi/','.prism/','.qoder/','.reasonix/','.sd-ai-command-pack/','.trellis/','.trae/','.zcode/','apps/','docs/','scripts/','tests/'];

function stripLines(t) {
  return t.replace(/(?::~?\d+(?:-\d+)?(?:,~?\d+(?:-\d+)?)*)+$/, '');
}
function normalizeRef(raw) {
  const trimmed = raw.trim().replace(/^<|>$/g, '').replace(/[.,;:]+$/g, '');
  if (!trimmed) return '';
  return trimmed.split('#')[0].split('::')[0];
}
// The disqualifier half of shouldCheck..., minus the prefix/top-level gate.
function passesDisqualifiers(target) {
  if (!target || target.startsWith('#') || target.startsWith('/') || target.startsWith('~')
    || target.startsWith('$') || target.startsWith('@') || target.endsWith('/')
    || target.includes('://') || /[<>{}\[\]*]/.test(target) || /[\s|]/.test(target)) return false;
  if (/^\.env(?:\.|$)/.test(target)) return false;
  if (/^[A-Z_][A-Z0-9_]*$/.test(target) || target.startsWith('--')) return false;
  return true;
}

const buckets = { unique: [], ambiguous: [], unknown: [] };
const linkPattern = /!?\[[^\]\n]*\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g;
const spanPattern = /`([^`\n]+)`/g;

for (const file of guard) {
  const text = readFileSync(join(root, file), 'utf8');
  for (const [kind, pattern] of [['markdown-link', linkPattern], ['code-span', spanPattern]]) {
    for (const m of text.matchAll(new RegExp(pattern.source, 'g'))) {
      const target = normalizeRef(m[1]);
      if (!target) continue;
      if (shouldCheckDocumentationPathReference(target, kind)) continue; // already checked today
      if (target.includes('/')) continue;                                // not a bare filename
      if (!passesDisqualifiers(target)) continue;
      const base = stripLines(target);
      // Same BARE_REFERENCE_PATTERN as measure-proposed.mjs and design.md.
      if (!/^\.?[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?\.(?:md|mdx|py|mjs|js|ts|sh|json|jsonl|toml|ya?ml|txt|cfg|ini)$/.test(base)) continue;
      if (base.includes('..')) continue;
      const end = (m.index ?? 0) + m[0].length;
      if (isAbsentPathMarked(text, end)) continue;
      // Mirror the checker: it compares the FULL normalized target at :5167.
      if (optionalPaths.has(target)) continue;
      const hits = (byBasename.get(base) || []);
      const rec = { file, line: text.slice(0, m.index ?? 0).split('\n').length, target, base, hits: hits.length };
      if (hits.length === 1) buckets.unique.push(rec);
      else if (hits.length > 1) buckets.ambiguous.push(rec);
      else buckets.unknown.push(rec);
    }
  }
}

const uniq = (a) => [...new Set(a.map((r) => r.base))].sort();
console.log('guard files:', guard.length);
console.log('bare-filename refs currently skipped:',
  buckets.unique.length + buckets.ambiguous.length + buckets.unknown.length);
console.log('  unique tracked match (would newly PASS):', buckets.unique.length, uniq(buckets.unique).length, 'distinct');
console.log('  ambiguous (>1 tracked match; R2 says do not report):', buckets.ambiguous.length, uniq(buckets.ambiguous).length, 'distinct');
console.log('  NO tracked match (would newly FAIL under a naive rule):', buckets.unknown.length, uniq(buckets.unknown).length, 'distinct');
const filesHit = new Set(buckets.unknown.map((r) => r.file));
console.log('distinct guard FILES that would newly fail:', filesHit.size);
const mirror = buckets.ambiguous.filter((r) => {
  const h = byBasename.get(r.base) || [];
  return h.length === 2 && h.some((t) => t.startsWith('templates/')) && h.some((t) => !t.startsWith('templates/'));
});
console.log('ambiguous refs whose ambiguity is ONLY the templates/ mirror:', mirror.length, 'of', buckets.ambiguous.length);
console.log('\n--- no-match refs by file (top 20) ---');
const byFile = new Map();
for (const r of buckets.unknown) byFile.set(r.file, (byFile.get(r.file) || 0) + 1);
for (const [f, n] of [...byFile].sort((a,b)=>b[1]-a[1]).slice(0,20)) console.log(String(n).padStart(4), f);
console.log('\n--- distinct no-match names (top 60) ---');
console.log(uniq(buckets.unknown).slice(0, 60).join('\n'));
console.log('\n--- distinct ambiguous names (top 40) ---');
console.log(uniq(buckets.ambiguous).slice(0, 40).join('\n'));
console.log('\n--- sample unique-match refs (10) ---');
for (const r of buckets.unique.slice(0, 10)) console.log(`${r.file}:${r.line} ${r.target}`);
