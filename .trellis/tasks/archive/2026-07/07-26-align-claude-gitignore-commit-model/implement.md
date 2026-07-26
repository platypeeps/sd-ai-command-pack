# Implementation plan: reverse claude gitignore to commit-by-default

## 0. Discovery / inventory (close the scope gap)

- `git status --ignored .claude` in the source and a representative consumer to
  enumerate the exact set that becomes tracked (Trellis runtime, agents,
  settings.json, authored/vendored skills). This set is a deliverable, not just
  a verification.
- Grep the blast radius: `_LEGACY_CLAUDE_GITIGNORE_SEQUENCE`, `is_gitignored`,
  `preserved_receipt_targets`, `gitignored`, `trellis_local_only`, `settings.json`,
  and `claude` across `installer/`, `scripts/`, `templates/scripts/`, `tests/`,
  `docs/`, `templates/docs/`, and `.trellis/spec/`. Produce the concrete edit
  list before changing code.

## 1. Generator change (R1, R2, R4)

- Edit `installer/registry.py`: replace the claude `local_gitignore_patterns`
  with exactly the R1 seven-pattern deny-list; remove `.claude/**` and all `!`
  negations; commit `.claude/settings.json` (no deny line). No additional denies
  (R2 is settled).
- Keep `_LOCAL_GITIGNORE_GROUP_ORDER` and byte-stable ordering intact.

## 2. Dependent registries + classifiers (R9)

- Add `.claude/agents/trellis-*.md` and `.claude/settings.json` to claude
  `trellis_local_only` (`installer/registry.py:80`); confirm the derived
  `LOCAL_ONLY_TRELLIS_EXCLUDES` / `LOCAL_ONLY_TRACKED_CHECK_PATHS` update.
- Teach `scripts/sd-ai-command-pack-review-scope.sh` + `templates/scripts/sd-ai-command-pack-review-scope.sh` and
  `scripts/sd-ai-command-pack-review-preflight.mjs` + `templates/scripts/sd-ai-command-pack-review-preflight.mjs`
  to recognize `.claude/settings.json` as copied adapter surface; keep the twins
  byte-consistent. Add classifier regression tests.

## 3. Accommodation subsystem (R3)

- Update `installer/provenance.py` (`is_gitignored_path`,
  `preserved_receipt_targets` claude docstring/comment) and BOTH audit twins
  (`scripts/sd-ai-command-pack-install-audit.py`, `templates/scripts/sd-ai-command-pack-install-audit.py`, the
  "e.g. repos ignoring .claude/" comments) so claude-in-normal is no longer the
  example while `--local-only` behavior is preserved.
- Re-point the `tests/test_install_audit.py` cases
  (`…downgrades_gitignored_missing_targets`,
  `…keeps_receipt_entries_for_gitignored_absent_anchor`,
  `…warns_for_unlisted_gitignored_pack_files`, `…batches_*_gitignore_candidates`,
  `test_refresh_detects_new_target_skipped_with_inactive_claude`) to a
  `--local-only`/still-gitignored fixture.

## 4. Block generation + migration tests (R6)

- Update the golden claude block, `assert_trellis_gitignore_block`
  (`tests/install_test_support.py`), and the block/migration tests in
  `tests/test_install_core.py` (`…adds…`, `…replaces_managed…`,
  `…migrates_legacy_claude_gitignore_sequence`, `…replaces_blanket…`,
  `…blanket_removal_preserves_blank_only_content`). Keep legacy blanket-stripping
  working in `installer/fileops.py`.

## 5. Regression invariants (R5)

- Add the isolated real-`git check-ignore` test with explicit expected-tracked
  and expected-ignored sets (per design), plus the cross-platform "declared
  markers not ignored" invariant **also via real `git check-ignore`** against
  each platform's generated block. Capture that both FAIL pre-change and PASS
  after; note in the PR.

## 6. Retire dogfood patch (R4) + track the source's newly-exposed files

- Remove `.gitignore:188-195` dogfood negation.
- Run the installer/`make sync` so the source block regenerates, then **`git add`
  and commit** the newly-tracked source `.claude/` runtime, agents,
  `settings.json`, and skills — being un-ignored is not sufficient; the source
  repo must itself be reproducible. Verify with `git check-ignore` + `git ls-files`.

## 7. Specs + docs in the shipped sources (R7, C-4)

- Edit `templates/docs/SD_AI_COMMAND_PACK.md` (block description ~1941-2010),
  `README.md` (~567), `CONTRIBUTING.md` (Trellis-owned platform files),
  `.trellis/spec/backend/manifest-and-filesystem.md` (receipt-stability +
  ignore-matrix), and `.trellis/spec/frontend/adapter-guidelines.md` if it
  references claude gitignore behavior. Edit the `templates/` source, not the
  installed mirror.

## 8. Sync + validate (before release closure)

- `make sync` (self-sync dogfood install + regenerate spec KB) so templates,
  dogfood mirrors, and `docs/SD_AI_COMMAND_PACK.md` are in final parity.
- `git check-ignore` acceptance assertions (markers + full Trellis surface +
  settings.json + arbitrary authored skill un-ignored; local/caches/logs/tmp
  ignored). Diff every non-claude platform's generated block → byte-identical.
- `make check` (installer 100% coverage, surface-drift, generated parity,
  shipped-script coverage, shellcheck). Adjust shipped-helper per-file coverage
  floors if the audit/classifier edits move them.

## 9. Release closure (R8, C-5) — last, after sync is final

- Choose a **minor** version; bump `manifest.json`; add the matching
  `## <version> - YYYY-MM-DD` `CHANGELOG.md` heading.
- Only after payload/template sync is final, regenerate the full-fleet ledger:
  `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-fleet-candidate-check.py`
  (all-pass, exact new payload digest). A partial `--consumer` run does not
  replace the full ledger.

## Review gates / rollback

- Review gate: planning stops for user approval before `task.py start`.
- Rollback (this task): revert registry patterns + `trellis_local_only` +
  classifiers, restore the source `.gitignore` (incl. dogfood negation) and
  newly-committed `.claude/` files (`git rm --cached` + re-ignore), tests,
  specs/docs, and version. No consumer is touched.
- Rollback (rollout, owned by I3): once a consumer commits newly-exposed files,
  reverting needs `git rm --cached` + re-ignore, not a block revert. The I3
  refresh gates on a pre-commit inventory + secret scan of newly-unignored files.
