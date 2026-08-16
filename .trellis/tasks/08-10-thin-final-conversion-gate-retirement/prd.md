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

**This task stays in planning.** Requirement 2 (retiring `validate_consumer` in
`scripts/sd-ai-command-pack-fleet-candidate-check.py`) and requirement 4 (the
spec/doc correction sweep) are untouched real work, and requirement 3's warning
about `scripts/sd-ai-command-pack-surface-check.py` still applies to them.

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
