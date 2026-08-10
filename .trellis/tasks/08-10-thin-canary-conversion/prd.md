# Convert the canary cohort to thin mode and prove revert

Child 3 of `08-09-thin-migration`.

**BLOCKED — requires explicit user authorization.** This task mutates
repositories outside `sd-ai-command-pack`: `platypeeps/rwbp-coordinator`,
`platypeeps/loadsmith`, `platypeeps/hoa-manager`. The autonomous
work-loop's run-level authority does not extend to them. Authorization
is per cohort; authorizing this cohort does not authorize post-canary.

Also requires children 1 and 2 shipped.

## Deliverable

The three canary consumers converted to thin mode in the registry's
`sequential` cohort order (rwbp-coordinator, loadsmith, hoa-manager),
each by one consumer PR plus the pack-side `mode` flip, and one executed
revert-and-restore proof.

## Requirements

1. Per consumer, in order: run the resweep against that consumer's
   exact HEAD **and clean worktree**, act on a `clear` verdict only,
   convert, open the consumer PR, land it green, then flip `mode: thin`
   in `docs/fleet/consumers.json`.
2. A `blocked` verdict stops that consumer's conversion and is reported
   with its reasons. It is not worked around. **It stops the whole
   canary cohort**, matching the existing rollout contract: the wave
   planner halts starts and holds merges on any unsettled terminal
   canary (`scripts/sd-ai-command-pack-fleet-wave-plan.py:200`) and
   `.trellis/spec/backend/manifest-and-filesystem.md:1778` permits
   progression only through successful canaries absent an explicit
   parked-canary override. Continuing past a blocked canary would need
   that override, invoked deliberately — not assumed.
3. Each conversion deletes the set enumerated **from that consumer's
   own installed-targets receipt** and classified through the partition
   (parent contract C-B) — measured today at 166 machine files plus 13
   retired files plus the four special cases, per consumer — and deletes
   that consumer's pack CI steps. It keeps the `repo-native` +
   `consumer-config` slices. The counts are recomputed per consumer, not
   assumed from this line.
4. The revert proof executes `install.py TARGET --revert-thin` on one
   converted canary, confirms CI stays green in the reverted state,
   then re-converts. Reading the revert code is not the proof.
5. `sd-status fleet` is the acceptance instrument, not a summary
   written by hand.
6. **Machine provisioning precedes conversion** (parent contract C-C2).
   Conversion removes a repository's agent surfaces on the assumption
   the machine supplies them; for anyone without the plugin installed
   and the machine installer run, it is indistinguishable from
   deletion. Before the first canary mutation, confirm through
   `sd-status`'s machine scope that the plugin and machine receipt are
   present, and state the prerequisite to whoever works in those
   repositories.

## Acceptance criteria

- [ ] Explicit user authorization for this cohort recorded in this file
      with its date before any consumer mutation.
- [ ] All three canaries satisfy `installMode == "thin"`, `pin.state == "present"`, and
      `pin.version == machineScope.packVersion` in
      `sd-status fleet --json`; plus `machineScope.state == "installed"`
      and `machineScope.comparison == "current"`. "No skew row" is not
      used: fleet mode exits zero on skew and its follow-up rows are
      untyped prose, so it cannot fail when it should.
- [ ] Each canary's CI is green post-conversion with zero pack CI steps,
      verified by grepping that consumer's `.github/workflows/` at its
      post-merge HEAD.
- [ ] No vendored payload remains in any canary beyond the
      `repo-native` + `consumer-config` slices, verified per consumer by
      comparing its post-conversion tree against **its own
      pre-conversion installed-targets receipt** — a comparison against
      the current partition alone would pass while orphan files from an
      older pin survive.
- [ ] Machine scope verified present (plugin + machine receipt) before
      the first canary mutation, with the `sd-status` output recorded.
- [ ] The revert proof was executed on a named canary at a named
      commit, CI stayed green, and the only residue was the
      `enabledPlugins` disable marker. The consumer was re-converted
      afterward.
- [ ] `make release-prep` passes on this repo after the registry flips
      — not `make check` alone. Each `mode` flip changes the
      fleet-manifest digest pinned into
      `docs/fleet/candidate-validation.json`
      (`scripts/sd_ai_command_pack_fleet_lib.py:766`), so `make check`
      cannot pass until release-prep refreshes the ledger.
