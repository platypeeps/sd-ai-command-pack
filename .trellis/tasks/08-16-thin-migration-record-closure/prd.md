# PRD: Close the thin-migration records and clear the stale AMC blocker

Child of `08-09-thin-migration`, itself a child of
`08-09-deployment-thin-consumers`.

## Goal

The thin conversion is finished in the fleet but not in the record. Answering
"is the migration done?" currently requires re-measuring the fleet, reading two
parent PRDs, and knowing which of their statements have expired. Bring the
records into agreement with the measured state so the answer is readable
instead of reconstructed.

This task delivers record correction only. It changes no installer, status, or
gate behaviour, and it does not resolve the one genuinely open engineering
question (`08-10-thin-final-conversion-gate-retirement`, requirement 2).

## What is stale

### 1. `08-09-deployment-thin-consumers` still declares AMC blocked

Lines 3-10 of that task's `prd.md` carry a `Known blocker (recorded
2026-08-14)` stating that `anomaly-metric-creator` is
`blocked: 175 consumer-authored reference(s) to removed paths` and that those
references must be dispositioned "before AMC's conversion child can start".

AMC has since been converted. `docs/fleet/candidate-validation.json` now
reports `passed` for all eight consumers, AMC included. The blocker notice is
the first thing a reader sees on the program's top-level task and it is false.

### 2. `08-09-thin-migration` has five unticked acceptance criteria

Measured against the tree and the fleet, three are satisfied, one is unproven,
and one is half satisfied. For the satisfied three the evidence exists — spread
across archived children, merged PRs,
and this repository — but none of it is recorded against the criteria it
settles.

| # | Criterion (abbreviated) | Assessment |
| --- | --- | --- |
| 1 | First canary converted, CI green, zero pack CI steps | satisfied by archived child `08-10-thin-canary-conversion` |
| 2 | Revert restores fat, CI stays green | **unproven** — asserted from a `loadsmith` rehearsal recalled in session, with no citation located in this checkout; see `design.md` D2 |
| 3 | AMC conversion removes the advisory CI call and `sd-ai-command-pack-sync.yml` | satisfied; both deletions merged |
| 4 | Retired gates removed/rescoped; grep finds zero present-tense vendoring descriptions | **half** — the grep half is satisfied and recorded; the gate half is not |
| 5 | Rescoped candidate loop runs in release-prep and blocks on failure | satisfied; `.github/scripts/prepare-release.py` defines the candidate check and raises on failure |

Criterion 4 is the reason the parent cannot simply be ticked and archived.

## Requirements

1. Replace the stale blocker header on `08-09-deployment-thin-consumers` with
   the resolved state. Historical text may stay if it reads as history; a
   present-tense blocker that no longer blocks may not.
2. Tick each criterion that re-measurement actually settles, with the evidence
   that settles it. Any `path:line` citation must resolve in this checkout —
   the CI scope preflight resolves against the local tree. Evidence that lives
   outside this repository, such as criterion 3's merged consumer change, is
   recorded as a repository plus PR or commit reference instead; that is the
   correct form for it, not an exception to the rule. Do not
   tick criterion 4. A criterion whose evidence cannot be located stays
   unticked and records what was searched — ticking on recollection is the
   failure mode this task exists to remove, so reproducing it here would be
   self-defeating.
3. Record against criterion 4 what remains and where it lives, so the parent's
   one open dependency is named rather than implied.
4. Re-measure every assessment in the table above rather than copying it. This
   record is a starting point for the sweep, not a substitute for it. In
   particular, criteria 1, 2, and 5 are asserted here from archived children and
   a script reading, and each should be confirmed against the tree.
5. Decide and record whether the parent stays in `planning`. Its own PRD states
   it stays `planning` for the length of the program and documents that starting
   it once (`6e66f38a`) made its whole subtree unfinalizable. Ticking criteria
   is not starting it; this requirement exists so the decision is deliberate
   rather than incidental.

## Known risk to resolve in design

This task's deliverable is edits to **other active tasks'** `prd.md` files —
its parent's and its grandparent's — not to its own directory. The finalization
validator applies per-path lifecycle rules to active-task directories, and a
work commit touching a sibling or ancestor task's artifacts may not pass the
same way an ordinary repository path does.

Design must establish which finalization mode this batch is shipped under
before implementation, not discover it at the merge gate. The parent's PRD
already records one instance of this family of failure: a linked task in the
wrong status left the whole subtree unshippable.

## Acceptance criteria

- [ ] `08-09-deployment-thin-consumers` contains no present-tense claim that
      `anomaly-metric-creator` is blocked, and the candidate ledger's
      all-`passed` state is cited as what replaced it.
- [ ] Criteria 1, 3, and 5 on `08-09-thin-migration` are ticked, each with
      evidence re-measured in this session rather than carried from this PRD.
- [ ] Criterion 2 is resolved either way: ticked if a durable record of the
      revert rehearsal is located, or left unticked with the search recorded.
      Both outcomes satisfy this criterion; ticking it unevidenced does not.
- [ ] Criterion 4 remains unticked and names
      `08-10-thin-final-conversion-gate-retirement` requirement 2 as the
      specific outstanding work, along with the unresolved premise that blocks
      it.
- [ ] Every `path:line` citation added by this task resolves in this checkout,
      confirmed by the CI scope preflight rather than by inspection.
- [ ] The finalization mode this batch ships under is recorded in `design.md`
      before implementation begins, and the batch ships under that mode.
- [ ] `make check` passes.
