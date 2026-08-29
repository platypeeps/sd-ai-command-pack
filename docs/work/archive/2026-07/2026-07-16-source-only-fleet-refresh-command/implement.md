# Source-Only Fleet Refresh Command Implementation Plan

## Execution Order

1. Add source-only command metadata beside `COMMAND_NAMES` and validate that
   every source-only name exists in the complete catalog.
2. Update command-surface generation so adapters still cover all commands,
   stale command-shaped manifest rows are removed, and final manifest fanout
   excludes source-only commands.
3. Add the former fleet-refresh platform footprint as a dedicated source-only
   retirement target group. Skip that group only for the resolved pack root.
4. Regenerate `manifest.json`, then update installer/generated-parity tests:
   - source/template surfaces still exist;
   - consumer installs omit fleet-refresh surfaces;
   - old vouched consumer surfaces retire cleanly;
   - pack-root dogfood copies survive sync.
5. Correct the distributed guide and relevant specs; remove fleet-refresh from
   installed command inventories while retaining source-operator docs.
6. Bump both manifests to `0.15.1`, add the changelog entry, run `make generate`,
   `make sync`, focused suites, and `make check`.
7. Ship the prerequisite through PR review/housekeeping and confirm tag
   `v0.15.1` before resuming the parent rollout.

## Review Focus

- Registry remains the single command-policy source of truth.
- Manifest regeneration removes rather than preserves old source-only entries.
- Retirement safety remains vouch-gated in consumers.
- Source-root exception cannot leak to arbitrary repositories.
- Root/template source files remain byte-identical where mirrored.
