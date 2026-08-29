# Design: Upgrade vendored Trellis 0.6.7 to 0.6.14

## Mechanism decision: official `trellis update`, not a manual file swap

Two candidate mechanisms were evaluated:

1. **Manual swap** — `git archive v0.6.14 packages/cli/src/templates/trellis/scripts`
   from the fork, untar over `.trellis/scripts/`.
2. **Official updater** — install `@mindfoldhq/trellis@0.6.14` globally, run
   `trellis update` in the repo. npm `latest` is 0.6.14 (verified
   `npm view @mindfoldhq/trellis version`); byte-agreement between the fork's
   v0.6.14 tag and the published package is asserted by the post-apply
   byte-identity check, not assumed — the authoritative comparison target for
   acceptance is the installed 0.6.14 package's templates, with the fork tag
   as a cross-check.

**Chosen: (2), the official updater.** Facts driving the decision (all
verified 2026-08-08 in this repo and the fork at `~/repos/ai/Trellis`):

- The pack is a genuine Trellis-initialized project: `.trellis/.version` =
  0.6.7 and a schema-v2 `.trellis/.template-hashes.json` (gitignored, local)
  tracking **114 template files** across `.claude/` (skills, agents, hooks,
  commands, settings.json), `.agents/`, `.opencode/`, `.github/` (skills +
  copilot instructions), `.codex/hooks`, `.gemini/hooks`, `AGENTS.md`, and
  `.trellis/workflow.md`. A scripts-only swap would create version skew:
  0.6.14 scripts driven by 0.6.7 skills/hooks on five platforms.
- `update.ts` (read at tag v0.6.14) is the purpose-built repo-template
  updater. `upgrade.ts` only does the global `npm install -g`; `update` does
  the repo files. Classification per file: byte-equal to new template →
  unchanged; stored hash == current hash → auto-update; hash missing or
  mismatched and content differs → conflict requiring confirmation
  (`overwrite`/`skip`/`create-new`).
- Platform scope is derived **from the hash file** (`getConfiguredPlatforms`
  reads tracked paths per platform configDir), so `update` cannot drag in
  new platform surfaces (no codebuddy/). The opt-in statusline hook is
  unconditionally excluded from `update` regardless of platform tracking
  (`configurators/claude.ts:101-107`) and is not installed here.
- Protected paths are hard-excluded: `.trellis/tasks/`, `.trellis/spec/`,
  `.trellis/workspace/`, `.trellis/.developer`, `.trellis/.current-task`.
- `update` finishes by writing `.trellis/.version` = CLI version (0.6.14) and
  refreshing the hash manifest — exactly the acceptance criteria.

## Conflict-safety gate (the one real risk)

Only 8 of 28 `.trellis/scripts` source files are hash-tracked (28 excludes
generated `__pycache__` bytecode), so ~20 script files will classify as
**conflicts** (content differs from 0.6.14 template, no stored hash) even
though the tree is byte-identical to the *0.6.7* templates. Blanket
`--force` is only safe if every conflict file is pristine 0.6.7.

Gate (two parts — a dry run alone cannot prove managed-block safety because
`--dry-run` prints classifications and stops without materializing proposed
content, `update.ts:1088/2518`):

1. **Dry-run classification check**: `trellis update --dry-run`; verify every
   conflict file is byte-equal to its v0.6.7 counterpart
   (`git show v0.6.7:packages/cli/src/templates/<mapped path>` from the fork
   — tag verified present; the installed 0.6.7 npm package is NOT a usable
   baseline because the global upgrade replaces it), except the two expected
   managed-block files below.
2. **Sandbox apply**: `git clone` the repo into scratch, copy the gitignored
   `.trellis/.template-hashes.json` (and `.trellis/.developer`) into the
   clone so classification matches, run `trellis update --force` there, and
   inspect the clone's full diff. `AGENTS.md` and
   `.github/copilot-instructions.md` must differ from the working tree only
   inside their `TRELLIS`/`COPILOT` managed blocks. The clone result is the
   exact expected post-apply surface; the real-tree apply must reproduce it
   byte-for-byte.

- All conflicts explained and clone diff clean → apply on the real tree.
- Any unexplained locally-modified file or outside-block delta → stop, list
  it, decide individually.

**Expected conflict set** (host-verified 2026-08-08 by recomputing all 114
tracked hashes against current content — 111 match, 1 file deleted, 2
modified):

- Untracked-but-pristine files (~20 of 28 `.trellis/scripts` source files,
  plus any untracked platform templates): must be byte-equal to v0.6.7
  templates → safe to overwrite.
- `AGENTS.md` and `.github/copilot-instructions.md`: tracked, locally
  modified **outside** their managed blocks. Safe under `--force` by
  construction: for these two, `update` builds the proposed content by
  merging the *current* file with only the new `TRELLIS`/`COPILOT` block
  replaced, so user content outside the block survives an overwrite.
  Verified executably via the sandbox apply above, not via dry-run output.
- `.opencode/package.json`: tracked hash exists but the file was deleted
  locally; `update` classifies this as user-deleted and respects the
  deletion (no re-add).

New files in the 0.6.14 templates for already-tracked platforms are auto-
added; review the sandbox-clone new-file list and accept it as
release-following surface. Migration inventory 0.6.7→0.6.14 (read from the
fork's `packages/cli/src/migrations/manifests/`): a single **optional**
0.6.8 `.pi/skills` rename; later manifests are empty and there are no
safe-file-delete entries. Inapplicable here — this repo has no `.pi`
surface — and the plan does not pass `--migrate`.

## Wrapper `--json` adoption (PRD requirement 3)

Enumeration (repo-wide grep for `task.py` invocations that parse output):

- `scripts/sd-ai-command-pack-status.py:508` — runs `task.py current`, parses
  stdout as a path. **The only prose parser.** Adopt `current --json`
  (returns `{current_task: {dir,id,title,status,parent,children,branch,
  base_branch}, source, stale}`) **with fallback** to the prose path parse:
  status.py also runs against fleet consumer repos still on 0.6.7, where
  `--json` is `error: unrecognized arguments` (verified against the pack's
  own 0.6.7 task.py). Fallback on nonzero exit re-runs bare `current`.

  Change discipline (repo rules, `AGENTS.md:29` + `CONTRIBUTING.md`): the
  root file is a byte-verified generated mirror; the source of truth is
  `templates/scripts/sd-ai-command-pack-status.py` (`manifest.json` maps
  source→target with `install: always`). Edit the template first, sync the
  mirror, add focused tests (JSON success path; nonzero-exit 0.6.7 fallback
  path — the existing fixture emits prose regardless of `--json`, so new
  fixtures are needed), and carry the required shipped-payload bookkeeping:
  manifest version bump, changelog heading, release evidence.
- `scripts/sd-ai-command-pack-fleet-publish.py:284` — runs `task.py archive`,
  consumes exit code only (stdout used solely in the error message). No
  change; `archive` has no `--json` in 0.6.14 anyway (only `current` and
  `list` do).
- `scripts/sd-ai-command-pack-review-preflight.mjs` — mentions task.py in
  messages only. No change.

## Rollback

- Before applying, record: the pre-update `git status --porcelain`
  inventory, a copy of `.trellis/.template-hashes.json` (gitignored — a git
  revert cannot restore it), and the updater's own managed-surface backup
  path (`update` writes `.trellis/.backup-<timestamp>/` before writing;
  prior runs' backups exist in the repo).
- Pre-commit rollback: restore **only updater-owned paths** from the
  recorded inventory (`git checkout -- <paths>` per path, `git clean -fd`
  scoped to the new-file list — never a blanket `git checkout -- .`), and
  restore the saved `.template-hashes.json` copy.
- Post-commit rollback: revert the commit(s), restore the saved
  `.template-hashes.json`.
- Either way, downgrade the binary (`npm install -g
  @mindfoldhq/trellis@0.6.7`) and verify: `.trellis/.version` reads 0.6.7
  and a 0.6.7 `trellis update --dry-run` reports no unexplained changes.
- No consumer repo is affected until it runs its own update (global binary
  at 0.6.14 with a repo at 0.6.7 is the normal pre-update state).

## Out of scope

- Fleet consumer repos (separate rollout, tracked by existing tasks).
- Adopting `list --json` anywhere: no pack code parses `task.py list` today.
- Upstream 0.7.0-beta line (not a release).
