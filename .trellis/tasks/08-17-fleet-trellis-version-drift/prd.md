# Fleet Trellis version drift: 8 consumers seven patch releases behind

## Goal

Bring every fleet consumer to the Trellis version this repository vendors, one
reviewable PR per consumer, and make the drift visible in the status report that
operators actually read.

## Origin

Split out of `08-08-fleet-one-path` on 2026-08-17. That task's canonical-path
design names four legs — Trellis version, pack pin, review lane, CI shape — and
owns the pin leg's rollout. The Trellis leg turned out to be the widest measured
drift and has no owner, so it is filed here rather than carried as a footnote to
a pack-refresh task.

## Problem

Measured 2026-08-17 from
`scripts/sd-ai-command-pack-status.py fleet --json`, reading
`repositories[].report.versions.trellis`:

| Consumer | Trellis | Pack pin | Tree |
|---|---|---|---|
| rwbp-coordinator | 0.6.7 | 0.71.22 | clean |
| loadsmith | 0.6.7 | 0.71.22 | **dirty** |
| hoa-manager | 0.6.7 | 0.71.22 | **dirty** |
| rwbp-website | 0.6.7 | 0.71.22 | clean |
| mezmo_benchmark | 0.6.7 | 0.71.22 | **dirty** |
| se-ai-command-pack | 0.6.7 | 0.71.22 | clean |
| sd-github-review | 0.6.7 | 0.71.26 | clean |
| anomaly-metric-creator | 0.6.7 | 0.71.22 | clean |

This repository vendors **0.6.14**. All eight consumers are on **0.6.7**.

Two distinct defects:

**The drift itself.** Seven patch releases of Trellis changes are missing from
every consumer, including the scripts the pack's own skills call into. The
vendored compatibility spec exists
(`.trellis/spec/tooling/vendored-trellis-compatibility.md`) precisely because
pack behavior depends on the vendored version; eight consumers running a
version this repository stopped testing against is a standing compatibility
risk, not a cosmetic lag.

**The drift is invisible where operators look.** A thin consumer's fleet row
reports its pin instead of an installed-versus-target pair, by design — a thin
consumer has no vendored pack tree to compare. Trellis is not the pack, but it
inherited that silence: the human `sd-status fleet` report prints
`pin 0.71.22` and no Trellis version at all, while the JSON carries it. An
operator reading the human report concludes the fleet is consistent. The report
is not wrong about the pin; it is silent about a second version that also drifts.

## Requirements

1. Every consumer reaches this repository's vendored Trellis version, or carries
   a recorded reason it did not. The ledger is one row per consumer and is the
   deliverable; a uniform fleet is not, because three checkouts are dirty and
   owned by other people.
2. One PR per consumer, **separate** from that consumer's pack-refresh PR. A
   `trellis update` diff touches `.trellis/scripts/**` and can move behavior;
   the refresh PR's diff is a pin plus provider config that the candidate
   validator already exercised in a disposable clone. A combined PR cannot be
   reverted along one leg.
3. The human `sd-status fleet` row surfaces the consumer's Trellis version, or
   this task records the explicit decision not to change it and says where an
   operator is supposed to see it instead. Silence by default is the defect;
   either fix it or document the substitute.
4. Upgrade order follows the existing `rolloutPolicy` cohorts in
   `docs/fleet/consumers.json` — canary sequential, post-canary bounded, final
   sequential. Do not invent a second ordering; a Trellis bump is at least as
   risky as a pin bump.
5. Nothing in this task writes into a dirty or externally owned checkout, cleans
   one, or commits on another repository's behalf. A dirty consumer is a ledger
   row with a reason.

## Acceptance criteria

- [ ] A per-consumer ledger exists with 8 rows: version before, version after or
      the reason it was skipped, and the PR link where one was opened.
- [ ] Each upgrade PR contains only the `trellis update` diff — no pin change, no
      provider config, no unrelated bookkeeping.
- [ ] After each merge, `sd-status fleet --json` reports that consumer's
      `report.versions.trellis` at the target, quoted in the ledger.
- [ ] Requirement 3 is closed either by a status-collector change with a test, or
      by a recorded decision naming where the version is observable.
- [ ] `make check` passes in this repository for any collector change.
- [ ] No consumer checkout is left dirtier than this task found it, and the three
      already-dirty consumers are untouched unless their owners clear them.

## Out of scope

- Upgrading Trellis in *this* repository, or choosing the target version. The
  target is whatever this repository vendors when the pass runs.
- The pack pin leg, the review lane, and the CI shape — `08-08-fleet-one-path`,
  `08-08-copilot-request-policy`, `08-08-ci-lane-cost`.
- Defining a version-compatibility contract for incompatibilities that surface
  during the upgrade; that is `07-09-trellis-version-compatibility`. If an
  upgrade breaks a consumer, this task records it and stops for that consumer.
- Any upstream Trellis change. This is uptake of a released version, nothing more.

## Ownership and sequencing

The upgrade runs in consumer repositories, which are externally owned working
copies; each PR is reviewed and merged under that repository's own gates. Run
after or independently of the pack-pin campaign — the two legs are deliberately
decoupled, and neither blocks the other.

`design.md` and `implement.md` are not written yet: requirement 3 needs a look at
the status collector's thin-row rendering before a plan is worth writing, and
requirement 1 needs a fresh measurement because the dirty set changes without
notice. Both are planning work, not implementation.
