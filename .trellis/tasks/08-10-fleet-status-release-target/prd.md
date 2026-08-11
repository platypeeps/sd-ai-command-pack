# Fleet status: compare against the newest published release

Filed 2026-08-10 from `08-09-thin-fleet-status-pins` (PR #416), which recorded
it explicitly as out of scope.

## Problem

The fleet "target pack version" is the **resolved pack checkout's**
`manifest.json` version — `_pack_identity` returns `manifest_version`
(`scripts/sd_ai_command_pack_fleet_lib.py:192-200`) and every resolution sets
`target_version=version` (`:251, 268, 284`). There is no GitHub release lookup
anywhere in the fleet library.

That makes "stale" mean *behind the operator's local checkout*, which is not
the same as *behind the newest published release*. An operator on an old
checkout sees a healthy-looking fleet; an operator on an unreleased working
copy sees the whole fleet flagged stale against a version nobody can install.

## Requirements

1. Fleet mode can compare consumer versions against the newest published
   `sd-ai-command-pack` release, not only the resolved checkout's manifest.
2. Both targets stay distinguishable in the report; a reader must be able to
   tell which comparison produced a stale row.
3. An unavailable release lookup is labeled `unavailable`, never silently
   downgraded to the checkout target and never rendered as agreement.

## Constraint that makes this non-trivial

`sd-status` is strictly read-only *and* currently makes no network call for the
fleet target; `--no-network` must keep working. Adding a release lookup puts a
network dependency into a collector whose contract is "read-only, works
offline". Decide deliberately whether it is opt-in (a flag), cached, or
resolved outside status entirely — do not just add a call.

## Acceptance criteria

- [ ] The release target is available and clearly distinguished from the
      checkout target in both JSON and human output.
- [ ] `--no-network` still produces a complete report, with the release target
      explicitly `unavailable` rather than absent or silently substituted.
- [ ] Status remains read-only: no fetch, install, or write is added.
