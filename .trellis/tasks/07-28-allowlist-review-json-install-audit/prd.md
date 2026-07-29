# Allowlist the shipped review.json in the install audit

## Goal

Make the documented `.sd-ai-command-pack/review.json` configuration file pass the shipped install audit, so a consumer that follows the shipped docs does not turn sd-full-check, sd-check, and sd-review red.

## Requirements

- `LOCAL_ALLOWED_PACK_FILES` in `scripts/sd-ai-command-pack-install-audit.py:78` must include `review.json`.
- A focused test must assert that a consumer fixture carrying `.sd-ai-command-pack/review.json` passes the install audit, and fails if the allowlist entry is removed.
- Mirror the change to `templates/` and run `make sync`.

## Acceptance Criteria

- [ ] A consumer fixture containing `.sd-ai-command-pack/review.json` passes `install-audit` with exit 0.
- [ ] The new test fails if `review.json` is removed from the allowlist.
- [ ] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-056 (P1 · S · Verified · consumer-impact).
- `templates/scripts/sd-ai-command-pack-review.py:30` declares the path; `templates/docs/SD_AI_COMMAND_PACK.md:865` documents it as supported.
- Collection walks the filesystem (install-audit.py:558), so an untracked file is still collected and becomes a hard failure at :668, exiting 1 at :1021.
- `installer/registry.py:1759` has no managed gitignore pattern covering it, and `templates/scripts/sd-ai-command-pack-check.py:917` registers `pack.install-audit` as an sd-check gate, so three gates break at once.
- The pack's own fixture already classifies review.json as tracked configuration (`tests/test_bookkeeping_validator.py:1386`).
- Tracked-stale against `07-22-integrate-routed-review-backends`: R23 mandates the stanza in this exact file but never mentions the audit allowlist.
- Ownership decided 2026-07-28: this task fixes the `review.json` **instance** only. The recurrence invariant — a registry of every shipped `.sd-ai-command-pack/` path constant with a declared tracked/ignored disposition, plus its test — is owned by `07-22-integrate-routed-review-backends` R36. A `CONFIG_PATH`-named-constant test was the original wording here and would not have closed the class anyway: `scripts/sd-ai-command-pack-pr-body-scope.py:69` uses `DEFAULT_CONFIG_PATH` and `:70` `INSTALLED_TARGETS_FILE`.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision.
- Lightweight task; PRD-only is appropriate. Classified 2026-07-28: one allowlist entry
  in a named constant, one fixture-backed test, and `make sync`. There is no contract,
  data-flow, or compatibility decision left open, and the requirements above are already
  an ordered checklist — a `design.md` would restate them and an `implement.md` would
  add a third copy. The recurrence invariant that *would* need design is explicitly not
  owned here (see the ownership note above; it belongs to
  `07-22-integrate-routed-review-backends` R36).
