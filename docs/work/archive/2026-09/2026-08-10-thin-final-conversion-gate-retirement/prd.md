---
title: Convert anomaly-metric-creator and retire the vendoring gates
status: planning
parked: 2026-09-01 bulk-park (D2)
created: 2026-08-10
---
# Convert anomaly-metric-creator and retire the vendoring gates

Child 5 of `08-09-thin-migration`, contract C-E.

**BLOCKED — requires explicit user authorization** for the final cohort,
and requires child 4 shipped. This task mutates
`platypeeps/anomaly-metric-creator`, then changes this repo's gates.

## Deliverable

The last fat consumer converted, then the consumer-facing vendoring
gates retired and every spec/doc surface that still describes consumer
vendoring as current behavior corrected.

## Requirements

1. Convert `anomaly-metric-creator` by the same sequence as children 3
   and 4. It carries two extras no other consumer has, and both must be
   deleted in the conversion PR:
   - the advisory `pr-body-scope.py` CI call (parent decision D2: it is
     a no-op — no PR body is supplied, so it always exits 0); and
   - `sd-ai-command-pack-sync.yml`, the consumer-side sync automation
     that would otherwise recreate the vendored state after conversion.
   Leaving the sync workflow in place would silently undo the
   conversion; it is the highest-consequence deletion in this task.
1a. **Machine provisioning precedes this conversion too** (parent
   contract C-C2), verified for the final cohort in its own right.
   "Same sequence as children 3 and 4" does not inherit their separately
   stated provisioning requirement, so it is stated here.
2. Retire, only after that conversion lands, **by enumerating the exact
   functions and tests removed or rescoped** — not by naming gates in
   prose. What retires is consumer fat installation and audit, which
   lives in `validate_consumer` in
   `scripts/sd-ai-command-pack-fleet-candidate-check.py`.
3. Keep `scripts/sd-ai-command-pack-surface-check.py`, which `make
   check` reaches through
   `scripts/sd-ai-command-pack-full-check.sh:612` and which validates
   template registration and root mirror bytes inside this repository —
   the source-of-truth gate `AGENTS.md:29` requires. "Shipped-surface
   closure" and "the pack-internal mirror gate" name overlapping
   machinery in that one checker, so retiring by gate name is exactly
   how the mirror gate gets removed by accident.
4. Correct spec and doc surfaces by enumeration — a grep of the
   install/fleet spec surfaces and `docs/` — not from memory. Text that
   is explicitly historical may stay and must read as history.

## Status of requirement 1 as of 2026-08-16

Requirement 1's conversion half is done and its deletion half is in flight.
Requirement 2's retirement — the half this task is actually still open for —
has not started.

`anomaly-metric-creator` was converted with the rest of the fleet:
`sd-status fleet --json` reports it `installMode: "thin"`,
`pin.state: "present"`, `pin.version: 0.71.22`, matching
`machineScope.packVersion` with `machineScope.state: "installed"` and
`machineScope.comparison: "current"`. All eight consumers now read that way.

Both enumerated deletions are in
[platypeeps/anomaly-metric-creator#380](https://github.com/platypeeps/anomaly-metric-creator/pull/380),
open at the time of writing. Retiring the sync workflow entirely — rather than
narrowing it — is the operator's standing decision: pack refreshes are
initiated by hand against the machine install and never by a consumer.

### The stated rationale for the sync deletion is stale

This requirement calls `sd-ai-command-pack-sync.yml` "the highest-consequence
deletion in this task" because leaving it "would silently undo the conversion."
That is no longer true, and the record should not carry a justification that
does not hold.

The workflow ran `install.py "$GITHUB_WORKSPACE" --force`. Against a thin
consumer that refreshes nothing: `_residual_files_for_thin` (`install.py:805`)
narrows the payload to the residual slice as soon as the provenance receipt
reads `mode: "thin"`, and `_selection_for_target` (`install.py:834`) takes the
pin's platforms rather than detecting fresh. Measured against the live
consumer:

```text
$ .venv/bin/python install.py ~/repos/platypeeps/anomaly-metric-creator --check --json
state: current
```

A `--force` run writes nothing, so the workflow could not have re-vendored.
Deleting it is still correct — it is a scheduled job, a scoped secret, and a
contract in `tools/check_ci_review_contract.py` all maintained for a no-op —
but it is ordinary cleanup, not the load-bearing safety deletion this
requirement describes. The same correction applies to the `pr-body-scope.py`
call, which parent decision D2 already classified as a no-op.

**This task stays in planning** for requirement 2, which is the only remaining
work. Requirement 4 is already satisfied; see below. Requirement 3's warning
about `scripts/sd-ai-command-pack-surface-check.py` still applies.

## Requirement 4 is already satisfied (measured 2026-08-16)

This requirement asks for the spec/doc correction sweep to be done "by
enumeration — a grep of the install/fleet spec surfaces and `docs/` — not from
memory". Run:

```text
$ grep -rnE 'consumers? (vendor|vendors|install a copy)|vendored (into|in) (each|the) consumer|consumer.{0,20}vendor' .trellis/spec/ docs/ \
    | grep -viE 'historical|used to|formerly|before the thin|no longer|until the thin|prior to'
docs/FLEET_ROLLOUT.md:15:consumer vendors no tree, so fleet status reports its pin — `present` with a
```

One hit, and it is not a stale claim: read in context it says "A `thin`
consumer vendors no tree", which is the new behaviour stated correctly. A
second, differently-worded sweep for `fat install`, `vendored tree`, and
`installed payload in the consumer` returns three hits
(`.trellis/spec/backend/manifest-and-filesystem.md:262`,
`.trellis/spec/backend/fleet-consumer-conversion.md:58`,
`docs/SD_AI_COMMAND_PACK.md:128`), all of which describe the fat/thin
*distinction* the installer still implements rather than asserting that
consumers vendor.

So the count of present-tense descriptions of consumer vendoring is **zero**,
which is what this requirement asks for. Nothing is left to correct. Re-run
both greps at implementation time rather than trusting this record; the point
of the requirement is that the answer comes from the tree, not from a note.

## Requirement 2 has an unresolved premise — resolve in design

Requirement 2 says what retires is "consumer fat installation and audit, which
lives in `validate_consumer`". Retiring it as written would remove the only
consumer validation the candidate check has, while the state that validation
exists for is still reachable and still recommended.

- `validate_consumer` is the sole validator in the file:
  `grep -n 'def validate_' scripts/sd-ai-command-pack-fleet-candidate-check.py`
  returns exactly one line, `:489`. It spans 368 lines, has one caller, and 24
  test references.
- `--revert-thin` is not deprecated. It is a live installer flag
  (`install.py:415`), and `docs/FLEET_ROLLOUT.md:257` prescribes it as *the*
  recovery route: "`--revert-thin` plus a reviewed reconversion, never a fleet
  sweep." `docs/SD_AI_COMMAND_PACK.md:2099` documents its `.gitignore`
  behaviour.

A consumer that follows the documented recovery path therefore ends up fat, and
after this retirement nothing in the candidate loop would validate it. The
retirement and the recovery path cannot both be right as currently written.

Design must pick one and record why:

1. **Retire and accept the gap** — fat is a transient state inside a supervised
   recovery, so candidate validation is not the control that protects it. Then
   name what does, because "nothing" is an answer that should be written down
   rather than arrived at silently.
2. **Retire the fleet-sweep path, keep a reachable validator** — the fat audit
   stops running across the fleet but stays callable for a reverted consumer.
   This is the smaller change and probably the honest one.
3. **Deprecate `--revert-thin` first** — only coherent if revert is genuinely
   being withdrawn, which contradicts `docs/FLEET_ROLLOUT.md:257` and would
   need its own decision.

Whichever is chosen, requirement 2's instruction to enumerate the exact
functions and tests removed or rescoped still governs, and the 24 test
references are part of that enumeration rather than collateral.

## Acceptance criteria

- [ ] Explicit user authorization for this cohort recorded in this file
      with its date before any consumer mutation.
- [ ] Machine scope verified present — `machineScope.state ==
      "installed"` and `machineScope.comparison == "current"` — and the
      output recorded **before** mutating anomaly-metric-creator, not
      only as part of the post-conversion fleet result.
- [ ] `anomaly-metric-creator` reports `installMode: "thin"` with
      `pin.state: "present"`; its workflows contain neither the
      `pr-body-scope.py` call nor `sd-ai-command-pack-sync.yml`,
      verified by grepping its `.github/workflows/` at its post-merge
      HEAD.
- [ ] `sd-status fleet --json` reports all 8 consumers with
      `installMode == "thin"`, `pin.state == "present"`, and
      `pin.version == machineScope.packVersion`, plus
      `machineScope.state == "installed"` and
      `machineScope.comparison == "current"`.
- [ ] The retirement lists every function and test it removed or
      rescoped, and that list is checked against what actually
      disappeared from the tree rather than accepted as written.
- [ ] `scripts/sd-ai-command-pack-surface-check.py` still runs through
      `scripts/sd-ai-command-pack-full-check.sh:612` **and still fails**
      on a deliberately introduced template/root mirror drift, proven by
      executing that break and reverting it.
- [ ] A grep of install/fleet spec surfaces and `docs/` finds zero
      present-tense descriptions of consumer vendoring; the grep command
      and its zero-count output are recorded.
- [ ] `anomaly-metric-creator`'s post-conversion tree matches its own
      pre-conversion installed-targets receipt minus the enumerated
      delete set.
- [ ] `make check` and `make release-prep` pass. Any `templates/**` or
      `docs/SD_AI_COMMAND_PACK.md` change in this task also carries a
      `manifest.json` bump and a matching top `CHANGELOG.md` heading —
      `make check` does not run the release payload gate
      (`.github/workflows/tests.yml:639`).
