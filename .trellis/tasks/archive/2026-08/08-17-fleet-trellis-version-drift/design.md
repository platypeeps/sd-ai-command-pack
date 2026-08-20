# Design: fleet Trellis version drift

## Measurement, re-taken 2026-08-18

The PRD's table is from 2026-08-17 and its dirty column is stale. Re-measured
from `scripts/sd-ai-command-pack-status.py fleet --json`, reading
`repositories[].report.versions.trellis` and `.git.workingTree.state`:

| Consumer | Trellis | Pin | Branch | Tree | Sync |
|---|---|---|---|---|---|
| rwbp-coordinator | 0.6.7 | 0.71.22 | main | clean | synchronized |
| loadsmith | 0.6.7 | 0.71.22 | main | clean | synchronized |
| hoa-manager | 0.6.7 | 0.71.22 | main | clean | synchronized |
| rwbp-website | 0.6.7 | 0.71.22 | main | clean | synchronized |
| mezmo_benchmark | 0.6.7 | 0.71.22 | main | clean | synchronized |
| se-ai-command-pack | 0.6.7 | 0.71.22 | main | clean | synchronized |
| sd-github-review | 0.6.7 | 0.71.26 | main | clean | synchronized |
| anomaly-metric-creator | 0.6.7 | 0.71.22 | main | clean | synchronized |

Two changes from the PRD snapshot, both material:

**The dirty set is empty.** loadsmith, hoa-manager, and mezmo_benchmark are
clean. PRD requirement 1 anticipated a ledger with skip rows for three owned
checkouts; as measured there are none. This does not license carrying the
measurement forward — `08-08-fleet-one-path`'s `design.md` records the set
changing three times in four hours, and the same rule applies here: re-check
each consumer at the moment its lane starts, never from this table.

**The target is 0.6.14, and it is the newest.** `.trellis/.version` here reads
`0.6.14`; `git -C ~/repos/ai/Trellis describe --tags --abbrev=0` reads `v0.6.14`.
So the upgrade target is not merely "what this repository happens to vendor" — it
is also the current upstream release, which removes the risk that the fleet is
being moved to an intermediate version that is itself about to be superseded.

## The two defects are independent, and only one is a code change

The PRD frames one problem with two faces. They separate cleanly:

- **The drift** is uptake work in eight external repositories. No code in this
  repository changes.
- **The invisibility** is one function in this repository. No consumer is
  touched.

They are sequenced deliberately: the collector change lands **first**, because
the ledger requirement wants the after-value quoted from the report an operator
actually reads, and because a collector that stays silent makes each lane's
verification a JSON-only affair that nobody will repeat later.

## Where the silence is

`versions.trellis` is collected for every consumer at
`scripts/sd-ai-command-pack-status.py:652`:

```python
"trellis": read_version(repo / ".trellis/.version"),
```

It reaches the JSON. It never reaches the human row. `render_fleet` builds each
row at `:4141-4147` from working-tree state, branch, sync, a pack label, stash
count, PR count, and task counts. The pack label is the mode split, at `:4130-4139`:

```python
if item.get("installMode") == "thin":
    pin = item.get("pin") or {}
    pin_state = pin.get("state") or "unreadable"
    pack_label = (
        f"pin {pin.get('version')}" if pin_state == "present" else f"pin {pin_state}"
    )
else:
    pack_label = f"pack {versions.get('sdAiCommandPack') or 'none'}"
```

The PRD's diagnosis — that Trellis "inherited" the thin row's silence — is not
quite right, and the correction matters for the fix. A **fat** consumer's row is
equally silent about Trellis; it prints `pack <version>` and no Trellis version
either. The silence is not a consequence of the thin/fat split at all. Trellis
was simply never added to the row in either mode. That makes the fix smaller and
mode-independent: one field, appended for every consumer, no branch.

## Chosen shape for requirement 3

The PRD offers an either/or — change the collector, or record where the version
is observable instead. Take the collector change, and take it in **two** places,
because the row alone is not enough.

**1. The row states the fact.** Append `trellis <version>` to every consumer row,
both modes, using the value already collected. Absent or unreadable renders
`trellis unknown`, matching the `pack … or 'none'` convention beside it rather
than omitting the field — a missing field is the defect being fixed.

**2. A skew record states the obligation.** A version printed in a row is still
something an operator has to compare by eye across eight lines. `fleet_step_records`
(`:3722`) is the existing mechanism for "this needs doing", and `fleet_follow_ups`
(`:3914`) deliberately derives `F-*` rows from the complete, untruncated record
set precisely so a skew row cannot be crowded out. Add one record, ranked
`FLEET_STEP_RANK_SKEW`, naming every consumer whose Trellis version differs from
this repository's vendored version.

The comparison target is `pack_root / ".trellis/.version"`, read with the same
`read_version` helper in `collect_fleet`, which already holds `pack_root`. It is
carried in the report as a new top-level `targetTrellisVersion`, mirroring the
existing `targetPackVersion`, so the JSON consumer and the human renderer score
against one value rather than each re-deriving it.

### What is deliberately *not* changed: the `attention` counter

`render_fleet:4070-4090` carries an explicit invariant, at `:4082`:

> Version attention follows the mode split, so the human counter and the JSON
> skew rows cannot disagree.

Trellis drift is left out of `attention`. Two reasons, and the second is the
real one:

- `attention` is scored per consumer against the pack target, and its whole
  point is "is this consumer ready for a pack refresh". Trellis uptake is a
  different leg with its own PRs; conflating them would make every consumer read
  `needs attention` for the entire duration of a campaign that is not the pack
  campaign.
- More concretely, it would break `08-08-fleet-one-path`. That task's Step 6
  reads the fleet report to decide which consumers are eligible for a pin lane.
  If Trellis drift inflates `attention`, the pin campaign's own gating starts
  reacting to a version it has no business reacting to — and `fleet-one-path`'s
  Step 7 explicitly forbids the two legs mixing.

So: the row reports it, the `F-*` follow-up makes it actionable, the counter
stays scoped to the pack leg. If a later task wants Trellis in `attention`, it
must add the matching JSON skew field in the same change to keep the invariant
above true.

## Upgrade mechanics per consumer

Requirement 2 wants a PR containing only the `trellis update` diff. The
constraint that makes this non-trivial is that a Trellis update touches
`.trellis/scripts/**` — executable code the pack's own skills call into — so the
diff is not reviewable by pin-diff inspection the way a pack refresh is.

Three things bound the risk:

- **The compatibility spec already exists.** `.trellis/spec/tooling/vendored-trellis-compatibility.md`
  is the written contract for what pack behavior depends on the vendored
  version. It is the review checklist for each lane, not a document to write.
- **The target is one hop from the source of truth.** Both this repository and
  upstream are at 0.6.14, so the diff each consumer takes is exactly the diff
  this repository has already been running against.
- **Failure is per-consumer and recorded, not repaired.** The PRD's out-of-scope
  section is explicit: if an upgrade breaks a consumer, this task records it and
  stops for that consumer. `07-09-trellis-version-compatibility` owns any
  contract change that emerges.

Ordering follows `docs/fleet/consumers.json`'s existing `rolloutPolicy` cohorts
(PRD requirement 4). No second ordering is invented, and the cohorts are read at
run time rather than transcribed here, because transcribing them is how the two
legs drift apart.

## Interaction with the pack-pin campaign

`08-08-fleet-one-path` Step 7 forbids a rollout PR carrying a `trellis update`
diff, and this task's requirement 2 forbids the reverse. Both hold if each lane
commits from a branch cut off the consumer's default branch with exactly one
kind of change. The failure mode to watch is a consumer whose pack-refresh PR is
open when its Trellis lane starts: the Trellis branch must be cut from the
default branch, not from the refresh branch, or the merged diff carries both.

The two campaigns are otherwise decoupled and neither blocks the other, as the
PRD's ownership section states. In particular this task does **not** depend on
the machine install being at the pack target — that is a pack-leg gate.

## Rollback

- The collector change is one function plus its tests; revert the commit.
- Each consumer upgrade is one PR in that consumer's repository, reverted there
  by its owner. That per-leg independence is the reason requirement 2 forbids a
  combined PR, and it is the whole design constraint on the PR shape.

## Findings recorded, not fixed here

- `fleet_step_records:3826` emits the plugin/receipt reconcile row only when
  `machine_scope["comparison"] == "skew"`. A machine with the plugin registered
  at two conflicting install paths reports `comparison: "unknown"` and
  `pluginVersion: null`, which that branch does not cover, so the report is
  silent about a genuinely unresolvable machine scope. Observed on this machine
  on 2026-08-18. It belongs to the pack leg, not this one.
