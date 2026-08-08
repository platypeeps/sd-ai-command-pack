# PARKED: Revisit platform registry after upstream active-platform state lands

## Goal

Capture the conditional task for simplifying pack platform detection if upstream
Trellis exposes machine-readable per-repo active-platform state. Today the pack
maintains marker tables and registry-derived scanners because Trellis does not
publish that state in a stable machine-readable form.

## Trigger

Waiting for external trigger: upstream
[mindfold-ai/Trellis#396](https://github.com/mindfold-ai/Trellis/issues/396)
lands or otherwise provides a documented machine-readable active-platform
contract.

Source:
`.trellis/tasks/archive/2026-07/07-06-introduce-platform-registry/prd.md`.

## Requirements

- Verify the upstream contract is available in the Trellis versions used by the
  fleet.
- Compare the upstream active-platform state to the pack's existing platform
  registry and marker tables.
- Replace or shrink pack-owned marker inference only where the upstream
  contract is stable enough.
- Preserve all-platform audit and review-scope coverage.

## Acceptance Criteria

- [ ] Upstream active-platform state is available and linked.
- [ ] The pack consumes the upstream state or explicitly documents why it is not
  yet sufficient.
- [ ] Platform registry, install audit, review-scope, and PR-body scope tests
  remain consistent across all supported platforms.
- [ ] Consumer install/update behavior remains unchanged unless the upstream
  contract enables a deliberate simplification.

## Notes

- Do not start this task until the upstream trigger exists.
- This is a parked task, not currently actionable backlog.
- Live check on 2026-07-20: [mindfold-ai/Trellis#396](https://github.com/mindfold-ai/Trellis/issues/396)
  closed as completed through [PR #448](https://github.com/mindfold-ai/Trellis/pull/448),
  whose migration manifest targets Trellis 0.6.8. This checkout still uses
  Trellis 0.6.7. Continue using the tested pack-owned marker inference until
  0.6.8 is available in the fleet, then evaluate the released contract.
