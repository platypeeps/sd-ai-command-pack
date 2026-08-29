---
title: Align Claude gitignore with per-platform commit model
status: done
created: 2026-07-26
---
# Align Claude gitignore with per-platform commit model

## Goal

Reverse a deliberate, documented design: today the pack treats `.claude/` as
local Claude Code state and commits only its own SD files there, while every
other platform's adapter directory is committed. Change `.claude/` to the same
commit-by-default model as the other platforms so a Trellis-enabled repo's
committed tree reproduces its Claude runtime and repo-authored Claude content.

This is a design change, not a bug fix. The current behavior is intentional and
documented ([docs/SD_AI_COMMAND_PACK.md:2002], [CONTRIBUTING.md:141],
manifest-and-filesystem.md receipt-stability). The change is chosen (direction
"A — full reversal") because the current design makes Trellis-on-Claude
non-reproducible from a clone, silently drops repo-authored `.claude/skills/`,
and is inconsistent with the 15 other platforms.

## Confirmed Evidence

- `claude` is the only platform whose `local_gitignore_patterns` starts with a
  blanket `.claude/**` + an SD allow-list (`installer/registry.py:64`). Others
  ignore only runtime sub-paths (`**/*.local.*`, `.cache/`, `cache/`, `logs/`,
  `tmp/`, `*.log`) without a blanket.
- The blanket is documented as intentional: docs describe ".claude/ is handled
  differently … ignores `.claude/**` while negating tracked
  `.claude/commands/sd/*.md`" and "ignoring the rest of `.claude/` as local
  Claude Code state" (`docs/SD_AI_COMMAND_PACK.md:1947`, `:2002`).
- Supporting machinery exists specifically because claude markers are
  gitignored: `installer/provenance.py:247` `is_gitignored_path()` and `:266`
  `preserved_receipt_targets()` (docstring cites "the claude adapter"), the
  install-audit twin `templates/scripts/sd-ai-command-pack-install-audit.py`
  (`gitignored_paths`, "e.g. repos ignoring .claude/"), and its source twin.
  This machinery ALSO serves `--local-only` installs and rwbp-website's
  receipt-stripping policy, so it is not removed — only its claude-specific
  assumptions change.
- Fleet audit (8 consumers + source, 2026-07-26): consumers track 0/3 declared
  claude markers; source tracks 1/3 via a dogfood-only negation
  (`.gitignore:188-195`). loadsmith's ignored `.claude/` contents: 49 Trellis
  runtime files, 3 Trellis agents, `.claude/settings.json`, a repo-authored
  skill (`loadsmith-swift-app`), and a vendored skill (`security-best-practices`).
- `.claude/settings.json` is Trellis-generated shared config (hook wiring + an
  `env` object), not machine-specific state; machine-specific permissions belong
  in the ignored `.claude/settings.local.json` (`CONTRIBUTING.md:141`).

## Dependencies And Boundaries

- Pack-source-only change. It edits the generator, its tests, specs, the
  `templates/` doc twin, and release metadata. It does NOT mutate any consumer.
- The consumer rollout is the separate operator-triggered `sd-fleet-refresh`
  (audit finding I3). Because a normal refresh rewrites `.gitignore` and exposes
  files, that rollout MUST run a per-consumer inventory + secret scan of every
  newly-unignored `.claude/` path before committing.
- Do not touch Trellis-owned `.trellis/.gitignore`.
- The gitignored-accommodation code paths must keep working for `--local-only`
  installs; only their claude-in-normal-install assumptions change.
- Installer 100% coverage, surface-drift, generated parity, and shipped-script
  gates must stay green.

## Requirements

- R1: Replace the `claude` `local_gitignore_patterns` blanket+allow-list with a
  runtime deny-list mirroring the other platforms: `.claude/settings.local.json`,
  `.claude/**/*.local.*`, `.claude/**/.cache/`, `.claude/**/cache/`,
  `.claude/**/logs/`, `.claude/**/tmp/`, `.claude/**/*.log`. Everything else
  under `.claude/` is committed by default. Remove all `!.claude/...` negations
  (R4 below) — they exist only to punch through the blanket.
- R2: Fix the exact, settled shared-vs-local boundary now — no deferred
  discovery. The in-repo ignore set is precisely the R1 seven patterns and
  nothing more: Claude Code writes its personal/session state (projects, todos,
  history, shell-snapshots, statsig, sessions) under `~/.claude/`, not a repo's
  `.claude/`, so the only in-repo local files are `settings.local.json` and
  `*.local.*` plus the standard runtime buckets. `.claude/settings.json` is
  committed (shared Trellis config). If implementation discovers a genuinely
  in-repo Claude-local path not already caught by `*.local.*`, it is added with
  recorded evidence; absent that, the set is complete as stated.
- R3: Update the gitignored-accommodation subsystem so it stays correct once
  claude is tracked in normal installs: `installer/provenance.py`
  (`is_gitignored_path`, `preserved_receipt_targets` docstring/behavior), both
  install-audit twins (`scripts/sd-ai-command-pack-install-audit.py` and its
  `templates/scripts/` twin), and their claude
  examples. The accommodation must still apply to `--local-only` and
  receipt-stripping repos.
- R4: Retire the source dogfood-only negation (`.gitignore:188-195`) so the
  source `.claude` boundary equals the shipped block.
- R5: Add a real-`git check-ignore` regression test (isolated temp repo) that
  asserts, against the actual generated managed block: the 3 markers,
  `.claude/commands/trellis/*`, `.claude/hooks/*.py`, `.claude/agents/trellis-*.md`,
  `.claude/settings.json`, a `.claude/skills/trellis-*/**` path, and an arbitrary
  `.claude/skills/<authored>/SKILL.md` are NOT ignored, while
  `.claude/settings.local.json`, a `*.local.*`, and a `.cache/` path ARE ignored.
  Add the cross-platform invariant — also exercised through real
  `git check-ignore` against each platform's generated managed block, not
  pattern comparison: no platform's declared `markers` may be ignored. Both
  must fail on the pre-change config and pass after.
- R6: Update every test that assumes claude-is-gitignored in a normal install —
  the block goldens and `assert_trellis_gitignore_block`
  (`tests/install_test_support.py`), the migration tests
  (`test_install_migrates_legacy_claude_gitignore_sequence`,
  `test_install_replaces_blanket_trellis_gitignore_entry`,
  `test_trellis_gitignore_blanket_removal_preserves_blank_only_content`), and the
  audit tests in `tests/test_install_audit.py` (`…downgrades_gitignored_missing_targets`,
  `…keeps_receipt_entries_for_gitignored_absent_anchor`,
  `…warns_for_unlisted_gitignored_pack_files`, `…batches_*_gitignore_candidates`,
  `test_refresh_detects_new_target_skipped_with_inactive_claude`). Re-point
  gitignored fixtures to a still-valid case (`--local-only`), not claude-in-normal.
- R7: Update the specs and docs that describe the old behavior in their SHIPPED
  sources: `templates/docs/SD_AI_COMMAND_PACK.md` (block description at
  ~1941-2010; then `make sync` regenerates `docs/SD_AI_COMMAND_PACK.md`),
  `README.md` (the "tracked Claude SD commands … committed" line ~567),
  `CONTRIBUTING.md` (Trellis-owned platform files section),
  `.trellis/spec/backend/manifest-and-filesystem.md` (receipt-stability and
  ignore-matrix sections), and `.trellis/spec/frontend/adapter-guidelines.md`
  if it references claude gitignore behavior.
- R8: Release closure: bump `manifest.json` a **minor** version (consumer-visible
  installer behavior change per `CONTRIBUTING.md:105`), add the matching
  `CHANGELOG.md` heading, and regenerate `docs/fleet/candidate-validation.json`
  via `scripts/sd-ai-command-pack-fleet-candidate-check.py` so the release gate's
  exact-payload all-pass record is current.
- R9: Update the dependent registries and classifiers that encode the old
  boundary. Add `.claude/agents/trellis-*.md` and `.claude/settings.json` to the
  claude `trellis_local_only` set (`installer/registry.py:80`) so `--local-only`
  installs still exclude them (they drive `LOCAL_ONLY_TRELLIS_EXCLUDES` and
  `LOCAL_ONLY_TRACKED_CHECK_PATHS`). Teach both generated-file classifier twins
  to recognize `.claude/settings.json` as copied adapter surface —
  `scripts/sd-ai-command-pack-review-scope.sh` + `templates/scripts/sd-ai-command-pack-review-scope.sh` and
  `scripts/sd-ai-command-pack-review-preflight.mjs` + `templates/scripts/sd-ai-command-pack-review-preflight.mjs` —
  keeping template and dogfood twins byte-consistent, with regression tests.

## Acceptance Criteria

- [ ] `installer/registry.py` claude group has no `.claude/**` and no `!.claude/…`
  negations — only the R1 deny-list + R2 defensive denies.
- [ ] R5 real-`git check-ignore` test passes: markers, `commands/trellis`,
  `hooks/*.py`, `agents/trellis-*`, `settings.json`, a trellis skill, and an
  arbitrary authored skill are un-ignored; `settings.local.json`, `*.local.*`,
  and `.cache/` are ignored. The test fails on the pre-change config.
- [ ] The cross-platform "declared markers not self-ignored" invariant passes.
- [ ] All R6 tests updated and green; gitignored-accommodation paths still
  covered via `--local-only` fixtures.
- [ ] Source `.gitignore` no longer contains the dogfood negation, and the
  source's own claude runtime, agents, `settings.json`, and skills are **tracked**
  (git-added and committed in this task's change) — not merely un-ignored — so a
  fresh clone of the source reproduces Trellis-on-Claude.
- [ ] The claude `trellis_local_only` set excludes agents + `settings.json` under
  `--local-only`, and both classifier twins recognize `.claude/settings.json`;
  regression tests cover local-only exclusion and classifier scope.
- [ ] Specs and the `templates/` doc twin describe commit-by-default `.claude/`;
  `make sync` leaves `docs/SD_AI_COMMAND_PACK.md` in parity.
- [ ] `manifest.json` minor-bumped, `CHANGELOG.md` heading added,
  `docs/fleet/candidate-validation.json` regenerated all-pass for the new payload.
- [ ] `make check` (installer 100% coverage, surface-drift, generated parity,
  shipped-script coverage, shellcheck) passes; non-claude platform blocks are
  byte-identical.

## Out Of Scope

- Running the fleet refresh / mutating consumers (I3), including the per-consumer
  inventory + secret scan of newly-unignored files (that gate is designed here
  but executed at rollout).
- Reconciling fleet version drift / two block generations (I3).
- Changing Trellis-owned `.trellis/.gitignore` or de-duplicating the overlapping
  `.trellis/*` runtime ignores between the two files.
- Any change to non-claude platform ignore groups.
