# Resolve audit roadmap cleanup

## Goal

Resolve the remaining local sd-audit-repo roadmap findings from the audit
ledger, reconcile the ledger, and document any upstream-only Trellis follow-up
without modifying Trellis-owned runtime files.

## Background

The follow-up audit at `2026-07-16 @ 7d0172e` left seven P3 findings open in
`.trellis/audit/ledger.md`:

- A-020: generated installer files use `MANIFEST_PATH` as a fake
  `PackFile.source`.
- A-025: old `CHANGELOG.md` release dates disagree with tag dates and ordering.
- A-026: deprecated `REVIEW_PREFLIGHT_PR_BODY` has no removal window.
- A-027: Trellis lifecycle hooks use config-sourced `shell=True`; this is
  upstream Trellis-owned runtime. Parked follow-up:
  `.trellis/tasks/07-16-upstream-trellis-hook-shell-semantics/`.
- A-031: default install does preflight and apply file reads separately.
- A-032: provenance hashing re-reads sources the apply pass already read.
- A-033: shipped shell/GitHub automation coverage is unmeasured or undocumented.

Upstream Trellis pull requests require explicit user consent. This task may
record a handoff for A-027 but must not edit `.trellis/scripts/**` runtime files
as a pack-owned fix.

## Requirements

- R1: Resolve A-020 by representing generated files without a false source path
  and preserving existing receipt/provenance behavior.
- R2: Resolve A-031 and A-032 by reusing source bytes/digests already collected
  during install planning/apply, without weakening the no-mutate-before-success
  preflight contract.
- R3: Resolve A-025 by correcting the affected changelog dates to match tag
  creation dates.
- R4: Resolve A-026 by documenting an explicit removal target for
  `REVIEW_PREFLIGHT_PR_BODY` everywhere the fallback is documented or warned.
- R5: Resolve A-033 by documenting the shell/GitHub automation coverage policy
  or adding a targeted gate; choose the lower-maintenance path if measurement
  tooling would add more noise than value.
- R6: Reconcile `.trellis/audit/ledger.md` so fixed local items are marked fixed
  and A-027 clearly records the upstream handoff state.
- R7: Do not modify Trellis-owned runtime files for A-027.

## Acceptance Criteria

- [x] Generated pack files no longer carry `MANIFEST_PATH` as their source.
- [x] Provenance continues to omit generated/managed files and still vouches
      normal installed files.
- [x] Default install reuses planned file content for apply when the conflict
      preflight has already succeeded.
- [x] Provenance can use the install result's source digest without re-reading
      the source file.
- [x] Changelog dates for `v0.7.1` through `v0.7.4` match tag creation dates.
- [x] `REVIEW_PREFLIGHT_PR_BODY` documentation/warnings include an explicit
      removal target.
- [x] Shell/GitHub automation coverage is explicitly documented as exempt with
      the compensating targeted tests/gates, or an equivalent gate is added.
- [x] A-020, A-025, A-026, A-031, A-032, and A-033 are marked fixed in the
      audit ledger after verification.
- [x] A-027 remains upstream-owned with a paste-ready handoff and no
      `.trellis/scripts/**` runtime edits.
- [x] A-027 is captured as a parked child Trellis task.
- [x] Focused tests pass for installer/provenance/review-scope behavior.

## Notes

- Tag dates checked with:
  `git for-each-ref --format='%(refname:short) %(creatordate:short)' refs/tags/v0.7.1 refs/tags/v0.7.2 refs/tags/v0.7.3 refs/tags/v0.7.4`.
- Validation:
  - `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_install_core tests.test_install_audit tests.test_review_scope`
  - `make lint`
  - `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_install_core tests.test_install_audit tests.test_review_scope tests.test_remove`
  - `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh`
