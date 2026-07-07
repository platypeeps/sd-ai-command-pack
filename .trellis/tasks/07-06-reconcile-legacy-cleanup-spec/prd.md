# Reconcile legacy/obsolete cleanup spec against 0.4.0 code removal

## Goal

Resolve a HIGH spec-vs-code divergence:
`.trellis/spec/backend/manifest-and-filesystem.md:369-398` ("Legacy
Adapter Cleanup", "Obsolete Adapter Cleanup") and
`.trellis/spec/backend/quality-guidelines.md:22-24` still mandate an
install-time cleanup pipeline (remove old `/trellis:*` adapter files
matching known template variants, report `legacy-conflict` /
`obsolete-conflict` otherwise; clean up the OpenCode nested→flat move,
`docs/TRELLIS_REVIEW_PR_PACK.md` → `docs/SD_AI_COMMAND_PACK.md`, and
`sd-command-pack-*` → `sd-ai-command-pack-*` script renames). That
machinery was deleted from `install.py` in commit a820182 ("Prepare
sd-ai-command-pack 0.4.0", ~536 lines removed); `grep legacy|obsolete
install.py` returns zero hits and the spec was never updated. The only
surviving mechanism is advisory (`LEGACY_PACK_PATHS` /
`LEGACY_PACK_REFERENCES` warnings in
`scripts/sd-ai-command-pack-install-audit.py:50-73`), and its list
omits `docs/TRELLIS_REVIEW_PR_PACK.md`, nested
`.opencode/commands/sd/*.md`, and `scripts/sd-command-pack-*`.
Consumers upgrading from the old pack identity keep orphaned files
forever, and the spec — the declared review baseline — describes
install statuses reviewers and agents will never see.

## Requirements

- R1: Make an explicit decision: (a) the 0.4.0 removal was deliberate
  and cleanup responsibility lives in audit advisories, or (b) restore
  a manifest-driven cleanup (e.g. an `obsoleteTargets` list of old
  path → known-template hashes consumed by the install pipeline).
- R2 (if a): rewrite/delete spec sections
  `manifest-and-filesystem.md:369-398` and
  `quality-guidelines.md:22-24` to describe the advisory-only model.
- R3 (either path): complete the audit's `LEGACY_PACK_PATHS` with the
  three rename-era families the spec names
  (`docs/TRELLIS_REVIEW_PR_PACK.md`, nested `.opencode/commands/sd/*`,
  `scripts/sd-command-pack-*`), with tests.
- R4: Record the decision and rationale in the PRD/design so the next
  reviewer does not re-open the divergence.

## Acceptance Criteria

- [ ] Spec and code agree on the cleanup model; no spec section
  describes statuses install.py cannot emit.
- [ ] Audit warns on all rename-era legacy families in a consumer repo
  fixture; tests cover the new advisory entries.
- [ ] Full battery green: unittest suite, 100% coverage on install.py,
  full-check, shellcheck; template twin byte-identical.

## Notes

- Origin: 2026-07-06 deep review (Architecture finding 1, HIGH).
