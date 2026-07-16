# Make sd-fleet-refresh source-checkout-only

## Goal

Prevent the source-only fleet orchestrator from being installed into consumer repositories, remove existing consumer copies through installer retirement, add regression coverage, release 0.15.1, and unblock the active fleet rollout.

## Requirements

- Keep the `sd-fleet-refresh` skill and platform adapters available in the
  sd-ai-command-pack source checkout, where `install.py`, the fleet manifest,
  preflight helper, and rollout runbook exist.
- Mark `sd-fleet-refresh` as source-only in the command registry and exclude
  all of its derived targets from `manifest.json` without hand-editing generated
  adapter bodies or duplicating the command list.
- During consumer refresh, retire every previously installed
  `sd-fleet-refresh` skill/command/prompt target using the existing
  provenance-vouched retirement safety model. Preserve drifted consumer files
  unless `--force` is explicitly used.
- Dogfood install/sync in the pack source checkout must not retire the
  source-only command surfaces.
- Update distributed documentation so consumers are not told that
  `sd-fleet-refresh` is installed locally; clearly identify it as a pack-source
  operator command.
- Add focused tests for generated manifest exclusion, source surface presence,
  consumer absence, retirement cleanup, and source-checkout preservation.
- Bump the release to `0.15.1`, update the changelog/spec, and ship through the
  standard PR review and housekeeping flow before resuming fleet rollout.

## Acceptance Criteria

- [x] `manifest.json` contains no `sd-fleet-refresh` target while source and
  template skill/adapter surfaces remain present and generated consistently.
- [x] A fresh consumer install contains no `sd-fleet-refresh` skill or adapter.
- [x] Refreshing an older vouched consumer removes all previously installed
  `sd-fleet-refresh` targets and leaves install audit/full-check green.
- [x] A pack-source dogfood install preserves its root `sd-fleet-refresh`
  surfaces while excluding them from receipts/provenance.
- [x] Generated-parity, installer, retired-target, audit, and full-check suites
  pass with the release ledger at `0.15.1`.
- [x] The `0.15.1` PR passes the merge gate with the release ledger ready;
  post-merge tag confirmation and rollout resumption remain owned by the parent
  fleet-refresh task.

## Notes

- Root/template source surfaces remain byte-consistent; consumer install
  state is manifest-driven.
- Do not modify upstream Trellis-owned files.
- Validation evidence: `make check` passed on 2026-07-16 with 100% installer
  line/branch coverage, all shipped-script coverage floors, Ruff, mypy,
  zizmor, install audit, KB freshness, release ledger, and full-check green.
- PR #134 reached `CLEAN` with every executed CI check successful. GitHub
  accepted the Copilot review request, but no review activity materialized
  during the bounded settle window; there are no review comments or threads.
