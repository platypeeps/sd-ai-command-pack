# Bound the Obsidian KB refresh against a stalled filesystem target

## Goal

The Obsidian KB refresh must not be able to hang a housekeeping run indefinitely. When
`.obsidian-kb` resolves to a filesystem that stalls, the refresh blocks with no timeout and no
diagnostic, and the merge that housekeeping owns never happens.

## Background

`scripts/sd-ai-command-pack-update-spec-kb.py` writes through the `.obsidian-kb` symlink. The
symlink may point anywhere; on this machine it pointed into `~/Documents/...`, which macOS
syncs to iCloud when Desktop & Documents sync is enabled. Writes to an unmaterialized
cloud-backed directory block in the kernel rather than failing.

`sd-ai-command-pack-housekeeping.sh` runs the refresh as its `kb_refreshed` step, before
eligibility and merge. The step has no timeout, so a stalled target stops the whole gate. The
operator sees the run's last output line, `==> Refresh Obsidian KB`, and nothing further —
there is no indication that the KB target is the problem, or which path it resolves to.

## Evidence

Observed on 2026-08-28 while merging PR #574. Two housekeeping runs stalled at the refresh
step; `ps` showed `sd-ai-command-pack-update-spec-kb.py` at 0.0% CPU for over 1.5 minutes, and the first run was
killed at a 10-minute ceiling with no output beyond the step banner. The PR was green,
eligible, and exact-head current the whole time; only the KB step blocked the merge.

Repointing `.obsidian-kb` to a local APFS path and re-running the same command completed in
**0.705s writing 1210 files**. Ten repositories on this machine had `.obsidian-kb` symlinks;
eight pointed into the cloud-synced path and have since been moved to local storage.

## Requirements

- The KB refresh is bounded. Exceeding the bound ends the step rather than the run.
- A refresh that cannot complete is reported as its own condition, naming the resolved
  `.obsidian-kb` target path, so the cause is legible without attaching a debugger or reading
  `ps`.
- Decide explicitly whether a failed or timed-out KB refresh should block housekeeping or
  degrade to an anomaly and let the merge proceed. The KB is a derived artifact and the merge
  does not depend on it, which argues for degrading — but the finish-work contract names the KB
  refresh as housekeeping's responsibility, so the decision needs to be recorded rather than
  assumed. Whichever is chosen, the run must not stall.
- Consider a cheap preflight — a bounded write probe against the resolved target before the
  full refresh — so the common case fails fast and the timeout is a backstop rather than the
  normal detection path.
- The bound is configurable, with a default suited to the observed cost: a healthy refresh of
  this repository's KB takes well under a second.

## Non-goals

- Preventing a user from pointing `.obsidian-kb` at a cloud-synced path. That is the user's
  choice; this task makes the consequence survivable and legible.
- Migrating existing KB content between locations.

## Acceptance Criteria

- [ ] A KB refresh whose target does not respond ends within the configured bound instead of
      blocking indefinitely.
- [ ] The resulting report names the resolved `.obsidian-kb` target and states that the refresh
      did not complete.
- [ ] A healthy refresh is unaffected in behaviour and cost.
- [ ] The block-versus-degrade decision for housekeeping is documented with its reasoning, and
      the chosen behaviour is covered by a test.

## Related

- Merge of PR #574, where this was the last blocker after review and checks were green.
