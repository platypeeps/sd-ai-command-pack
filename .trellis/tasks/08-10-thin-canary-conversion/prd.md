# Convert the canary cohort to thin mode and prove revert

Child 3 of `08-09-thin-migration`.

**BLOCKED — requires explicit user authorization.** This task mutates
repositories outside `sd-ai-command-pack`: `platypeeps/rwbp-coordinator`,
`platypeeps/loadsmith`, `platypeeps/hoa-manager`. The autonomous
work-loop's run-level authority does not extend to them. Authorization
is per cohort; authorizing this cohort does not authorize post-canary.

Also requires children 1, 2, and 2b shipped. Child 2b is not optional
sequencing: until the pack's own surviving surfaces stop citing removed
paths, every consumer's resweep returns `packDefects` and `--thin`
refuses. Measured 2026-08-10: 16 such hits in 7 files in all three canary
consumers, which still carry the pack's own PR template.

## Deliverable

The three canary consumers converted to thin mode in the registry's
`sequential` cohort order (rwbp-coordinator, loadsmith, hoa-manager),
each by one consumer PR plus the pack-side `mode` flip, and one executed
revert-and-restore proof.

## Requirements

1. Per consumer, in order: run the resweep against that consumer's
   exact HEAD **and clean worktree**, act on a `clear` verdict only,
   run `--thin`, open the consumer PR, land it green, then land the pack
   PR carrying that consumer's `mode: thin` row in
   `docs/fleet/consumers.json`. **The registry row is written by `--thin`,
   not by hand afterwards**: one invocation writes both roots, which is
   why it refuses unless both are writable (child 1's `design.md`). The
   two edits then travel in two pull requests and land in that order. The
   window between them — tree thin, registry row still `fat` — is the
   pin-vs-mode skew the parent design accepts and `sd-status fleet`
   reports.
2. A `blocked` verdict stops that consumer's conversion and is reported
   with its reasons. It is not worked around. **It stops the whole
   canary cohort**, matching the existing rollout contract: the wave
   planner halts starts and holds merges on any unsettled terminal
   canary (`scripts/sd-ai-command-pack-fleet-wave-plan.py:200`) and
   `.trellis/spec/backend/manifest-and-filesystem.md:1778` permits
   progression only through successful canaries absent an explicit
   parked-canary override. Continuing past a blocked canary would need
   that override, invoked deliberately — not assumed.
3. One consumer-authored blocker is already measured and belongs to this
   task rather than to child 2b: `rwbp-coordinator/.prism/rules.json:55`
   is a live Prism **required** rule naming three removed paths. Its text
   is not in the pack's `templates/.prism/rules.json`, so it is
   rwbp-coordinator's own drift, and the partition keeps `.prism/` as
   `shared / consumer-config` — conversion leaves the broken rule
   behind unless the consumer PR fixes it. Repoint it in the same PR that
   converts rwbp-coordinator, before the resweep can return `clear`.
   `.prism/rules.json` is agent-executed, not inert data: round 10
   reclassified it from `advisories` to `blockers` for exactly that
   reason.
4. Each conversion deletes the set enumerated **from that consumer's
   own installed-targets receipt** and classified through the partition
   (parent contract C-B) — measured today at **179 removed targets per
   consumer**, being 166 machine files plus 13 retired files. The four
   special cases are not part of that number and must not be added to it:
   three generated bookkeeping files are **kept and rewritten**, and
   `.gitignore` **survives** with one exact marker block removed. Saying
   "plus the four special cases" described 183 deletions and overstated
   destructive scope by four files. It **keeps** the `repo-native` and
   `consumer-config` slices. The counts are recomputed per consumer, not
   assumed from this line.
5. The revert proof executes `install.py TARGET --revert-thin` on one
   converted canary, confirms CI stays green in the reverted state,
   then re-converts. Reading the revert code is not the proof.
6. `sd-status fleet` is the acceptance instrument, not a summary
   written by hand.
7. **Machine provisioning precedes conversion** (parent contract C-C2).
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
- [ ] `rwbp-coordinator/.prism/rules.json` names no removed path at the
      converted HEAD, verified by the resweep returning `clear` for that
      consumer rather than by reading the file — the rule text moved once
      already and a hand check would re-measure the old bytes.
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
