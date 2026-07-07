# Harden the review-preflight mjs entry and inputs

## Goal

Three MEDIUM defects in `scripts/sd-ai-command-pack-review-preflight.mjs`
from the 2026-07-06 deep review:

1. **Symlink invocation silently no-ops with exit 0** (:190):
   `import.meta.url === pathToFileURL(process.argv[1] || '').href` —
   Node realpaths the ESM main entry but `argv[1]` keeps the symlink
   path, so `node /path/symlink-to-preflight.mjs` fails the
   comparison, runs zero checks, prints nothing, and exits 0. A review
   gate that silently passes is the worst failure mode available to
   it. Fix: compare `realpathSync(process.argv[1])` (with a safe
   fallback when realpath fails).
2. **Undeclared Node floor, no version guard** (:229 `Object.hasOwn`
   → Node ≥16.9; :919 `||=` → ≥15): no engines field, no runtime
   check, no documented minimum. Node 14 dies with a bare parse-time
   `SyntaxError`; full-check aborts with that opaque error under
   `set -e`. Fix: early `process.version` check with a clear message
   plus "Node ≥ 16.9" in `docs/SD_AI_COMMAND_PACK.md`.
3. **Changed-path collection omits untracked files** (:839-864):
   `currentChangedPaths` uses staged → branch → working-tree git diff
   only, while the shell siblings (full-check.sh:317-341,
   review-local.sh:114-132) also include
   `git ls-files --others --exclude-standard`. A freshly installed
   (untracked) pack surface is invisible to
   `checkCopiedTemplateDiffDisclosure` while the shell-side scope
   checks in the same full-check run DO see it — inconsistent verdicts
   from one pipeline. Also reconsider first-match-wins ordering (one
   staged file hides the entire branch diff).

Also fold in the LOW nits: workspace-index row regex is
trailing-whitespace-sensitive (:1013, add `[ \t]*$`), and the doc scan
silently skips symlinked docs (:1105-1132 — document or follow
symlinks deliberately).

## Requirements

- R1: symlink-invoked entry runs checks (realpath comparison), with a
  node-gated behavioral test invoking via symlink.
- R2: version guard with actionable message; documented Node floor.
- R3: untracked files included in changed-path collection (union or
  documented ordering), matching the shell siblings; test with an
  untracked copied-template file.
- R4: L9/L10 nits fixed; existing behavioral tests stay green.
- R5: changes land in both `scripts/` and `templates/scripts/`.

## Acceptance Criteria

- [ ] Symlink invocation runs the full check suite (verified by test).
- [ ] Old-Node failure mode is a clear versioned error message.
- [ ] .mjs and shell scripts agree on untracked-file visibility within
  one full-check run.
- [ ] Full battery green; template twins byte-identical.

## Notes

- Origin: 2026-07-06 deep review (Shell agent M3/M4/M5, L9/L10).
  Builds on 07-03-preflight-path-line-refs test infrastructure.
