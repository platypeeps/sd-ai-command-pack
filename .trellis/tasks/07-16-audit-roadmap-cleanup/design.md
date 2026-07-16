# Design

## Boundaries

- Pack-owned code/docs/tests may change.
- Trellis-owned runtime under `.trellis/scripts/**` must not change for A-027.
- The audit ledger is the durable reconciliation surface for this task.

## Installer Data Flow

- Keep `PackFile` as the manifest record type, but allow `source: Path | None`.
- Manifest-loaded entries still require a real source and are validated exactly
  as before.
- Installer-generated entries use `source=None`, making their template-less
  status explicit instead of pretending `manifest.json` is their content source.
- `InstallResult` carries optional `source_content`, `source_digest`, and
  `source_executable` for normal source-backed files.
- The no-force default preflight still runs before writes. When it succeeds,
  the apply pass receives the preflight results and can reuse the planned source
  bytes for created/unchanged/preserved outcomes instead of re-reading.
- Provenance prefers `InstallResult.source_digest`; it falls back to hashing
  `file.source` only when an older result does not carry a digest.

## Docs And Ledger

- Changelog dates are corrected to tag creation dates.
- `REVIEW_PREFLIGHT_PR_BODY` remains a deprecated fallback for now, but every
  documented/warned surface names a concrete removal target.
- Shell and GitHub automation coverage stays test-driven rather than
  coverage-tool-driven unless a later task proves bash coverage tooling is worth
  the dependency/noise. This task documents the exemption and compensating gates.
- A-027 records a paste-ready upstream handoff in the ledger; its status remains
  open because the risk still exists upstream and is not pack-owned.

## Compatibility

- Public install status strings do not change.
- Provenance JSON format does not change.
- Existing manifest JSON remains valid.
- Consumers that still set `REVIEW_PREFLIGHT_PR_BODY` keep working until the
  documented removal version.

## Rollback

- Revert the branch to restore prior installer behavior and audit ledger state.
- If install provenance changes unexpectedly, rerun install-audit fixtures
  before retrying.
