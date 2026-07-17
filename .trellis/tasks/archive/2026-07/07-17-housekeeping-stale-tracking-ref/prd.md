# Fix housekeeping stale tracking ref on auto-delete-head-branch

## Problem

`scripts/sd-ai-command-pack-housekeeping.sh` flags a false anomaly and exits
nonzero after a clean merge when the remote has GitHub's
auto-delete-head-branch enabled.

Ordering gap: the initial `fetch_and_prune` fetches the source branch's
tracking ref while the branch still exists. The merge then triggers
server-side auto-delete. In cleanup, `ls-remote` returns 2 (absent), so the
"already absent" path runs — but unlike the explicit-delete path it does NOT
`fetch --prune`. The stale local `refs/remotes/<remote>/<branch>` survives,
and the final verification reports `remote source branch still tracked`,
producing an anomaly and rc=1.

## Requirements

- R1. In the already-absent branch, prune the stale tracking ref when it
  exists locally (a guarded second `fetch --prune`), so the final
  remote-branch-absent check passes on auto-delete-head-branch remotes.
  Preserve existing actions/anomalies; no behavior change when no stale ref
  exists.
- R2. Apply identically to both twins (scripts/ + templates/scripts/); keep
  them byte-identical (drift gate).
- R3. Add a regression test: an already-absent remote branch with a lingering
  local tracking ref ends with the ref pruned and no
  "remote source branch still tracked" anomaly.
- R4. Shipped-payload change: manifest version bump + matching CHANGELOG
  heading.

## Acceptance Criteria

- [ ] Simulated auto-delete-head-branch cleanup ends clean (ref pruned, no
  stale-tracking anomaly, rc=0).
- [ ] Twins byte-identical; `bash -n` clean; shellcheck clean.
- [ ] make test + make full-check green; version bumped with CHANGELOG entry.
