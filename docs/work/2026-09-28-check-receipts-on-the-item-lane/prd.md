---
title: One passing local check per head, reused by prepare's gate
created: 2026-09-28
---
# PRD — check receipts on the item lane

## Problem

Shipping sd:1910 ran the pack's `make check` on the same commit more than
once: the operator's session ran it before the first push and after the first
fix, and `sd-ship prepare`'s deterministic gate ran it again on each of the
four reviewed heads before Codex saw them. Six full runs of a gate that takes
about four minutes, on four commits, plus the GitHub `unittest` check on each
head, which is required and stays.

The pack already has the mechanism: `sd-check --record-receipt` stores a
passing full check bound to the clean head and its declared inputs, and
`sd-ship prepare --reuse-check` accepts it instead of running the gate again
(`bin/sd_ship_review.py`, the `--reuse-check` forwarding). It needs a tracked
`.github/sd-check-reuse.json` in the checkout, and the pack has none. The
receipt contract, `skills/sd-check/references/check-receipts.md`, says "Do not
enable it for this pack's network-dependent full gate", and
`docs/coding-to-release.md` repeats it, without either saying which part of
`make check` needs the network. `Makefile` names one network target, the font
re-vendoring, and keeps it out of `check`. Whether the sentence is still true
is the first thing to find out.

## Requirements

1. Name what in `make check` (`lint`, `audit`, `docs-lint`, `test`) reads the
   network, in this PRD's Log, with the command or test that does it. If
   nothing does, correct the two sentences that say it does. If something
   does, say whether it can leave the gate or be declared, and if neither,
   the pack stays ineligible and the two sentences gain the reason.
2. If the gate is eligible, track `.github/sd-check-reuse.json` in the pack
   with an audited dependency inventory (every root `make check` reads, every
   tool it invokes, every environment variable it honours). `complete: true`
   is asserted only after that audit, per the contract.
3. `skills/sd-ship/SKILL.md` says, in one line, when to record a receipt: after
   the session's own passing full run on the clean head it is about to push,
   and that `prepare --reuse-check` is what reads it.
4. Measure once: one item lane through prepare with a receipt, wall time of the
   gate step against sd:1910's four-minute runs, in the Log.
5. Measure the other managed repositories with a real test gate:
   mezmo-world-simulator, mezmo_benchmark, anomaly-metric-creator,
   people-profiles, rwbp-coordinator, rwbp-website, rwbp-songs. `sd-check
   --json` wall time in each, in the Log. File one item per repository whose
   gate takes longer than the threshold the operator sets; suggested 60 s.
   ui-design's gate is seconds and needs nothing; system, sd-writing-pack and
   trace-classifier have no check entrypoint.
6. An Unreleased entry in `CHANGELOG.md`.

Out of scope: the GitHub `unittest` required check on the PR head. It runs
on every head whatever the local receipt says, and the merge gate reads it.
Out of scope: reusing a check across different heads. A receipt binds one
commit and its inputs; a fix commit is a new head and a new run, by design.

## Acceptance criteria

- [ ] The Log names the network reader in `make check`, or says there is none
      and the two doc sentences are corrected.
- [ ] If eligible: `git ls-files .github/sd-check-reuse.json` lists it, and
      `sd-check --record-receipt --json` on a clean head reports a reusable
      pass.
- [ ] If eligible: `sd-ship prepare --item <id> --reuse-check --json` on that
      head reports the gate as reused, not run.
- [ ] `skills/sd-ship/SKILL.md` has the one line from requirement 3.
- [ ] The Log has seven `sd-check --json` durations, one per repository in
      requirement 5, and the operator's threshold.
- [ ] `CHANGELOG.md` Unreleased names the change.

## References

- `skills/sd-check/references/check-receipts.md`, the contract.
- `docs/coding-to-release.md`, "the pack's network-dependent full gate
  remains ineligible".
- `bin/sd_ship_review.py`, where `--reuse-check` is forwarded to `sd-check`.
- sd:1910, `docs/work/2026-09-28-a-directory-option-on-the-lane-commands/`,
  the lane whose four passes are the measured cost.

## Log

- 2026-09-28 created, from the operator's question during sd:1910: "we seem
  to run make check multiple times on the same code".
- 2026-10-03 rulings D1-D3 (operator, via the lead): drop harness session
  variables from the gate child (yes), widen the 30-minute window (no), make
  builders use `sd gate check` (no, optional). Prepare's gate now reads a
  same-head receipt; requirements 1-6 above (the pack's declared contract and
  the measurements) remain open.
