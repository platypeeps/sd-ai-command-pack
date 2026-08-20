// Measures the PROPOSED rules: exact-basename index + bounded pack-prefix
// expansion + mirror classification. Reports the residual that would newly FAIL.
import { readFileSync, existsSync, statSync, readdirSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { createHash } from 'node:crypto';
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
const PACK_PREFIXES = ['sd-ai-command-pack-', 'sd_ai_command_pack_'];
function lookup(name) {
  const exact = byBasename.get(name);
  if (exact && exact.length) return { via: 'exact', hits: exact };
  for (const p of PACK_PREFIXES) {
    if (name.startsWith(p)) continue;
    const hits = byBasename.get(p + name);
    if (hits && hits.length) return { via: `prefix:${p}`, hits };
  }
  return { via: 'none', hits: [] };
}
const hashCache = new Map();
function blobHash(p) {
  if (!hashCache.has(p)) {
    try { hashCache.set(p, createHash('sha256').update(readFileSync(join(root, p))).digest('hex')); }
    catch { hashCache.set(p, 'ERR'); }
  }
  return hashCache.get(p);
}
function allMirrors(hits) { return new Set(hits.map(blobHash)).size === 1; }

const optionalPaths = new Set(['.sd-ai-command-pack/installed-targets.txt','.sd-ai-command-pack/local-only.txt','.sd-ai-command-pack/manifest.json','.sd-ai-command-pack/pr-body-scope.json','.sd-ai-command-pack/provenance.json','.sd-ai-command-pack/review-preflight.json','.trellis/.developer','.trellis/.template-hashes.json','.trellis/audit/ledger.md','ARCHITECTURE.md','ARCHITECTURE_OVERVIEW.md','docs/ARCHITECTURE.md','docs/ARCHITECTURE_OVERVIEW.md','docs/TRELLIS_REVIEW_PR_PACK.md','docs/repomix-map.md','docs/review-learnings.md','package.json','scripts/check-review-preflight.mjs','scripts/classify-ci-changes.sh','scripts/classify_ci_changes.sh']);
const stripLines = (t) => t.replace(/(?::~?\d+(?:-\d+)?(?:,~?\d+(?:-\d+)?)*)+$/, '');
const normalizeRef = (raw) => {
  const t = raw.trim().replace(/^<|>$/g, '').replace(/[.,;:]+$/g, '');
  return t ? t.split('#')[0].split('::')[0] : '';
};
function passesDisqualifiers(target) {
  if (!target || /^[#/~$@]/.test(target) || target.endsWith('/') || target.includes('://')
    || /[<>{}\[\]*]/.test(target) || /[\s|]/.test(target)) return false;
  if (/^\.env(?:\.|$)/.test(target)) return false;
  if (/^[A-Z_][A-Z0-9_]*$/.test(target) || target.startsWith('--')) return false;
  return true;
}
const B = { resolved: [], ambiguousDistinct: [], residualLocator: [], residualNoun: [] };
const linkPattern = /!?\[[^\]\n]*\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g;
const spanPattern = /`([^`\n]+)`/g;
for (const file of guard) {
  const text = readFileSync(join(root, file), 'utf8');
  for (const [kind, pattern] of [['markdown-link', linkPattern], ['code-span', spanPattern]]) {
    for (const m of text.matchAll(new RegExp(pattern.source, 'g'))) {
      const target = normalizeRef(m[1]);
      if (!target) continue;
      if (shouldCheckDocumentationPathReference(target, kind)) continue;
      if (target.includes('/')) continue;
      if (!passesDisqualifiers(target)) continue;
      const base = stripLines(target);
      // BARE_REFERENCE_PATTERN exactly as published in design.md: optional leading
      // dot, a name segment, then an extension from bareReferenceExtensions.
      if (!/^\.?[A-Za-z0-9_](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?\.(?:md|mdx|py|mjs|js|ts|sh|json|jsonl|toml|ya?ml|txt|cfg|ini)$/.test(base)) continue;
      if (base.includes('..')) continue;   // separate guard: the charset above admits '..'
      const end = (m.index ?? 0) + m[0].length;
      if (isAbsentPathMarked(text, end)) continue;
      // The real checker compares the FULL normalized target at :5167, never the
      // basename. For a locator-form bare name ('CLAUDE.md:12') no entry can match,
      // so this never fires -- kept only to mirror the checker exactly.
      if (optionalPaths.has(target)) continue;
      const { via, hits } = lookup(base);
      const isLocator = base !== target;   // a line/range suffix was stripped
      const rec = { file, line: text.slice(0, m.index ?? 0).split('\n').length, target, base, via, n: hits.length, isLocator };
      if (via === 'none') (isLocator ? B.residualLocator : B.residualNoun).push(rec);
      else if (hits.length === 1 || allMirrors(hits)) B.resolved.push(rec);
      else B.ambiguousDistinct.push(rec);
    }
  }
}

const uniq = (a) => [...new Set(a.map((r) => r.base))].sort();
for (const k of ['resolved','ambiguousDistinct','residualLocator','residualNoun'])
  console.log(`${k.padEnd(18)} refs=${String(B[k].length).padStart(4)}  distinct=${uniq(B[k]).length}`);
console.log('\n=== TIER 1 RESIDUAL: locator form (line suffix), does NOT resolve => proposed FAIL ===');
for (const r of B.residualLocator) console.log(`  ${r.file}:${r.line}  ${r.target}`);
console.log('\n=== locator-form refs that DO resolve (proposed newly-checked, passing) ===');
const lr = B.resolved.filter(r=>r.isLocator);
console.log(lr.length, 'refs,', uniq(lr).length, 'names:', uniq(lr).join(', '));
console.log('\n=== TIER 2 residual (noun form, declined) ===', B.residualNoun.length, 'refs,', uniq(B.residualNoun).length, 'names');
console.log(uniq(B.residualNoun).join(', '));

const ambLoc = B.ambiguousDistinct.filter((r) => r.isLocator);
const resLoc = B.resolved.filter((r) => r.isLocator);
console.log('\n=== NEWLY PASSING under the final rule (>=1 candidate, locator form) ===');
console.log('  locator-form in resolved bucket        :', resLoc.length);
console.log('  locator-form in ambiguousDistinct      :', ambLoc.length,
            '=>', [...new Set(ambLoc.map(r=>r.base))].sort().join(', '));
console.log('  TOTAL newly passing                    :', resLoc.length + ambLoc.length);
console.log('  TOTAL newly failing                    :', B.residualLocator.length);
console.log('  declined (noun form or no suffix)      :',
            B.resolved.length + B.ambiguousDistinct.length + B.residualNoun.length
            - resLoc.length - ambLoc.length);

const mirrored = B.resolved.filter((r) => r.n > 1);
console.log('  of `resolved`: unique-candidate      :', B.resolved.length - mirrored.length);
console.log('  of `resolved`: mirror sets (n>1)     :', mirrored.length);
console.log('  genuinely-distinct multi-match       :', B.ambiguousDistinct.length,
            'across', [...new Set(B.ambiguousDistinct.map(r=>r.base))].length, 'names');
