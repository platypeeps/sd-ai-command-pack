# Add Codex adversarial planning review implementation plan

## 1. Add the canonical planning-review contract

- [x] Add one Claude-scoped rule reference defining the
      artifact baseline, material-change trigger, host adversarial pass, native
      Codex peer lane, concern dispositions, blocker gate, and bounded rerun.
- [x] Use direct `codex exec` with a read-only sandbox and ephemeral session;
      make plugin independence and missing-CLI fallback explicit.
- [x] Keep path handling quoted and constrain review to the active task's
      `prd.md`, `design.md`, and `implement.md` plus minimal evidence.

## 2. Add the Claude integration point

- [x] Add a concise `.claude/rules/` template that applies the canonical
      contract after a planning artifact edit batch and before implementation
      approval/start.
- [x] Register the rule and reference in `manifest.json` with Claude-only
      platform targeting.
- [x] Sync template sources to root dogfood mirrors without editing upstream
      Trellis skills or plugin-managed paths.

## 3. Test and document behavior

- [x] Add installer/manifest coverage for the new rule and scoped reference.
- [x] Add contract tests for trigger scope, formatting/unchanged exclusions,
      native CLI capability fallback, read-only execution, parallel collection,
      concern dispositions, blocking semantics, and the one-rerun limit.
- [x] Assert non-Claude installed targets do not receive the rule and shipped
      content does not depend on `/codex:adversarial-review`, plugin cache
      paths, or companion scripts.
- [x] Update README, shipped guide, frontend adapter spec, command inventory if
      affected, and release notes/version.

## 4. Validate and finish

- [x] Regenerate and synchronize all derived surfaces.
- [x] Run focused tests and `git diff --check`.
- [x] Refresh the final-payload fleet candidate ledger across all consumers.
- [x] Run `make check` and review the complete diff for upstream coupling,
      unintended non-Claude behavior, repeated paid calls, unsafe shell
      interpolation, and unresolved concern escape paths.
- [x] Run the normal Trellis spec, commit, and finish-work lifecycle.

## Rollback

Remove the pack-owned Claude rule and scoped reference plus their manifest,
test, documentation, and release entries. No upstream Trellis or Claude plugin
rollback is required.
