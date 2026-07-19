# Validate sd-status work-loop snapshot contracts

## Context

`sd-ai-command-pack-status.py` dynamically loads the paired work-loop helper and
already classifies import errors, exceptions, and non-dict results as invalid.
The helper validates persisted loop state before producing a snapshot, and the
installer plus provenance audit keep the two scripts on the same release.

AMC PR #256 identified one remaining defensive gap: a drifted or substituted
helper can return a dict whose `status` is missing or unsupported, or whose
active-loop fields are incomplete. The renderer currently treats that mapping
as a normal active loop and can print `None` values instead of a clear anomaly.

This is low-risk upstream hardening, not a consumer-local rollout blocker.

## Requirements

- Define the accepted work-loop snapshot shapes owned by `sd-status`:
  `none`, `invalid`, `unavailable`, and the supported active/paused states.
- Validate a helper-returned mapping before returning it from
  `collect_work_loop()`.
- Convert missing or unsupported status values and incomplete active-loop
  snapshots to `{"status": "invalid", "error": ...}` with a bounded,
  non-sensitive diagnostic.
- Preserve valid snapshots and existing rendering exactly.
- Update the canonical template first and keep the root script twin identical.
- Do not weaken installer provenance or audit checks.

## Acceptance Criteria

- [x] Missing `status` is reported as an invalid work-loop snapshot.
- [x] An unsupported `status` value is reported as invalid.
- [x] Active or paused snapshots missing required renderer fields are reported
      as invalid instead of printing `None` values.
- [x] Valid `none`, `invalid`, `unavailable`, active, and paused snapshots keep
      their current behavior.
- [x] Focused status tests, twin checks, and the canonical pack check pass.
- [x] A shipped payload change follows the normal version, changelog, release,
      and fleet-refresh process.

## Evidence

- Consumer review: https://github.com/platypeeps/anomaly-metric-creator/pull/256#discussion_r3610813075
- Upstream helper validation: `templates/scripts/sd-ai-command-pack-work-loop.py`
- Upstream status adapter: `templates/scripts/sd-ai-command-pack-status.py`

## Results

- `collect_work_loop()` now validates dynamically loaded helper mappings before
  they reach JSON or human rendering.
- Terminal states plus complete active, paused, stopped, and completed run
  snapshots preserve their prior behavior; malformed mappings become bounded
  structural `invalid` anomalies without echoing helper-controlled values.
- The focused status suite passes all 29 tests and the status script retains
  86% combined line/branch coverage.
- Release `0.21.6` passed the canonical pack check and disposable candidate
  validation for all seven configured consumers.
