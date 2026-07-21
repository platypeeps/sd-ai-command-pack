# Fix terminal reconciliation status diagnostic

## Goal

Make invalid work-loop snapshot diagnostics identify the field whose presence is inconsistent with the top-level run state, so operators are not told that a valid nested reconciliation status is malformed.

## Background

In `scripts/sd-ai-command-pack-status.py`, a snapshot with `terminalReconciliation.status == "verified"` and a non-terminal top-level `status` is correctly rejected, but the error currently identifies `terminalReconciliation.status`. RWBP consumer review [comment 3618461807](https://github.com/platypeeps/rwbp-website/pull/149#discussion_r3618461807) confirmed that the invalid condition is the presence of `terminalReconciliation` on an active or paused run, not the nested verified value. The shipped script and its template twin must remain identical.

## Requirements

- Preserve rejection of `terminalReconciliation` records unless the top-level run status is `stopped` or `completed`.
- Report the cross-field invariant failure against `terminalReconciliation`, while continuing to report an actually invalid nested status against `terminalReconciliation.status`.
- Add focused regression coverage for both diagnostic paths.
- Keep `scripts/sd-ai-command-pack-status.py` and `templates/scripts/sd-ai-command-pack-status.py` in byte-for-byte parity.
- Release the shipped payload as `0.24.8`, including the required changelog entry and generated version surfaces.
- Do not change the work-loop snapshot schema or relax validation.

## Acceptance Criteria

- [x] An active or paused snapshot with an otherwise valid verified terminal reconciliation is rejected with a diagnostic ending in `terminalReconciliation`, not `terminalReconciliation.status`.
- [x] A terminal reconciliation whose nested `status` is not `verified` is still rejected as `terminalReconciliation.status`.
- [x] Focused status tests, generated parity checks, and the canonical upstream full check pass.
- [x] Manifest and generated command surfaces report `0.24.8`, with a matching top changelog heading.
- [x] Fleet candidate validation passes for the exact release payload before the PR is opened.

## Out of Scope

- Changing reconciliation state semantics, accepted run statuses, or snapshot fields.
- Patching consumer repositories before the upstream release is merged and tagged.

## Notes

- This is a lightweight, PRD-only task. The minimal implementation changes one validator label, its template twin, focused tests, and release metadata.
- Focused regression: `python -m unittest tests.test_status.StatusTests.test_collect_work_loop_validates_helper_snapshot_shapes` (1 test passed).
- Generated parity: root/template status scripts are byte-identical and `generate-command-surfaces.py --check` reports 67 matching surfaces.
- Canonical verification: `make check` passed tests, coverage floors, Ruff, mypy, zizmor, review preflight, install audit, KB freshness, release drift, and full-check.
- Fleet candidate validation passed P10 through P90 across all seven configured disposable consumers for pack version `0.24.8`.
- The status snapshot code-spec now records the cross-field diagnostic contract and its focused assertion points.
