---
title: A satellite relieves a busy hub lane
created: 2026-10-10
item: sd:3174
---

# Design: a satellite relieves a busy hub lane (sd:3174)

## Status

Draft for review. Three operator decisions are open (D0 to D2 below).
D0 comes first: the proposed flow builds on parts that merged away on 2026-10-10.

## Problem

The hub hosts most lanes. When its gates pile up, or one long gate holds a lane,
queued items wait while the satellite's CPUs sit idle.
The operator's plan (sd:3174 note, 2026-10-09): a satellite adopts a queued hub entry, gates it, and the hub merges it in seconds.

## What changed since the plan

The plan's steps 5 and 6 reuse sd:2704: the `lane request` row and `sd-ship merge --satellite-gate`.
Both are gone:

- sd:3003 (2026-10-08 ruling) gave each repository one lane on a movable host (`repo.lane_host`).
  Its design names the cost it removed: "The cost is in the hand-off, not in the gate or the merge."
- sd:3214 deleted lane requests, intake and `--satellite-only` (pack, 2026-10-10).
- sd:3216 deleted offload receipts; a gate receipt binds `machine` and no machine reuses another's (sd:2796).
- sd:3217 dropped `repo.satellite_gate` (system, 2026-10-10). The plan's "satellite-gate=accept" no longer exists.

What still exists and helps:

- `repo.lane_host` and its two setters: `sd-db.sh repo lane-host PATH HOST|hub` and the dashboard's Move lane.
- `lane run --hosted` on every machine, every 5 minutes, which reads the host again before each claim.
- `sd-ship prepare` runs off the lane host, lock-free, with revision-checked saves (sd:2679).
- The ship lock and the delivery rows live in the hub's database.

So the hub cannot merge on a satellite's gate without a new cross-machine trust rule.
That is the rule the 2026-10-08 ruling retired.

## Approach

Three shapes meet the need; D0 picks one.

**Shape A: move the lane, and its queue follows (Recommended).**
The operator moves a repository's lane to the satellite with the existing control.
The pending entries move with it, so no one cancels and enqueues them again by hand.
The satellite gates and merges them, one order per repository, as sd:3003 does.
New: portable entries (below) and a carry-over in `lane run --hosted`. No trust rule. No new command.

**Shape B: adopt one entry, as planned.**
The satellite marks one hub entry adopted, gates it, and records a pass; the hub merges on that pass.
New: portable entries, an entry state `adopted` with a lease, one lane verb or flag to adopt,
a pass row the hub's merge gate trusts at the exact head and tree, and an ordering rule.
It brings back a narrow form of what sd:3216 deleted.

**Shape C: build nothing.**
Move the lane with sd:3003's "Moving a lane" steps: cancel the pending entries on the old host,
make worktrees on the new host and enqueue them there. Each step is by hand.

Why A: it reuses sd:3003, keeps one host per lane, and adds no trust rule.
It meets both cases in the plan: an overloaded hub moves a lane;
a lane held by one long gate moves, and the next entries run on the satellite.
What A gives up: merges for a moved repository run on the satellite, and the unit is a repository, not one entry.
One order per repository still holds, because one machine hosts it.
Shape A is one pack PR, one commit per part: portable entries in `enqueue`, hand-over, take-in,
and a line on Move lane saying pending entries follow. No system change and no schema change. Run it on Opus.

## Non-goals

- Cross-repository merge order; each repository keeps its own lane.
- A merge while the hub is down (see "Hub down").
- An automatic trigger unless D1 picks it.
- Bringing back gate receipts that cross machines, in shape A or C.

## Shared part: a portable entry

Today an entry names a worktree and a body file on the host's disk.
Another machine can read neither.

- `lane enqueue` pushes the branch at the expected head before it writes the queue
  (`git push origin <branch>`, no force). A push refusal refuses the enqueue; nothing is queued.
- The entry keeps `branch` beside `worktree`.
- The body and acceptance texts go to the database only when an entry leaves its host (shape A) or is adopted (shape B).
  They go in the existing `state` table, the store the ship rows use, under one key per entry:
  `lane-carry:v1:<owner/repo>:<item>`. No new table.

## Shape A in steps

1. **Move.** The operator runs Move lane (dashboard) or `sd-db.sh repo lane-host <path> <satellite>`. Unchanged.
2. **Old host hands over.** `lane run --hosted` also visits a local queue whose repository it no longer hosts.
   For each pending entry, in queue order:
   1. Check the worktree is still at `expected_head`; else mark the entry `failed` with `head_moved`, as `run` does.
   2. Push the branch if the remote is behind; refuse a remote that is ahead or diverged.
   3. Write the `lane-carry` row: item, branch, head, title, body text, claim, authority, acceptance text, position, `from` host.
   4. Mark the local entry `moved`, a terminal status beside `cancelled`.
   A running entry finishes first; the runner already stops at the next item.
3. **New host takes in.** Before it claims, `lane run --hosted` reads `lane-carry` rows for each repository it hosts, by position:
   1. Fetch the branch; refuse a fetched head other than the row's.
   2. Make a worktree at `~/worktrees/<repo>-lane-<item>`, or reuse one at that head.
   3. Write the body to the lane root and `enqueue` with the row's fields.
   4. Delete the row with its revision.
4. **Run.** The new host gates and merges as any host does.
5. **Move back.** The same steps in the other direction.

A move costs one extra gate per carried entry, as sd:3003 accepted:
the new host's `prepare --catch-up` gates again. Same-machine receipt reuse then applies.

## Shape B in steps (if D0 picks it)

1. **Choose.** `sd-ship lane adopt --item N` on the satellite (new verb), or a dashboard button on a pending entry.
2. **Claim.** `lane enqueue` on the hub writes each entry's portable row at enqueue time, not at a move.
   The adopt verb writes `adopted_by`, `lease_until` on that row with its revision.
   The hub runner reads the row before each claim and skips an adopted entry. A running entry refuses adoption.
3. **Code.** The satellite fetches the branch at the row's head and makes a worktree.
4. **Gate.** The satellite runs `sd-ship prepare` (review, then gate), as off-host prepare does today.
5. **Hand back.** It writes `gated_head`, `tree`, `pack_sha` and its host name on the row.
6. **Merge.** The hub runner takes gated entries first. Its merge gate accepts the row's pass when the head, the tree and the pack sha equal its own.
   That trust rule is new. It binds no tools, per the 2026-10-08 ruling.
7. **Lease.** The satellite renews `lease_until` while it works. An expired lease clears `adopted_by`; the entry returns to the hub queue.

A merge on the hub needs the branch up to date with the base.
If any entry merges between the satellite's gate and the hub's merge, the catch-up moves the head, the pass no longer applies,
and the hub gates again. Under load that is the common case, so shape B saves less than it seems.

## Failure table

Shape A:

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| enqueue | branch pushed | push refused or fails | enqueue refuses; nothing queued | new: a push double that fails leaves the queue unchanged |
| enqueue | queue entry written | killed after push, before the queue write | nothing to undo: a pushed branch alone is harmless | covered by the test above |
| 2.1 hand-over | none | worktree head moved | entry `failed` with `head_moved`; no row written | new: hand-over with a moved worktree writes no row |
| 2.3 hand-over | `lane-carry` row written | killed before the local mark | next pass finds the row at the same head and only marks the entry `moved` | new: kill between row and mark; rerun gives one row, one `moved` entry |
| 2.3 hand-over | row write | database unreachable or refuses | unknown result: the entry stays pending and the pass stops; next pass retries | new: failing write leaves the entry pending, not `moved` |
| 3.1 take-in | none | fetched head differs from the row | row kept, refused with `carry_head_moved`; a note on the item; the operator re-enqueues by hand | new: take-in with a moved remote leaves the row and notes it |
| 3.3 take-in | local entry pending | killed before the row delete | next pass finds a pending entry for that item and head; it deletes the row only | new: kill between enqueue and delete; rerun gives one entry |
| 3.4 take-in | row deleted | revision conflict | reread; a row already gone is done | new: concurrent delete double |
| move back mid-hand-over | rows exist for the old host | the old host now hosts again | take-in on the old host reads its own rows like any host | new: move, hand over, move back; entries return once each |
| run | merge on the new host | old host still merging its running entry | branch protection's up-to-date rule stops the stale merge (sd:3003) | existing sd:3003 tests |
| older state | queue files without `branch` | entry from before this change | hand-over reads the branch from the worktree; with no worktree, entry `failed` with `no_branch` | new: hand-over of an old-format entry |

Shape B adds these rows to the enqueue and take-in rows above:

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| 2 claim | `adopted_by` written | hub claimed the entry first | revision check refuses adoption | new: race double, hub claim first |
| 2 claim | hub runner | row unreadable | unknown: the runner skips the entry this pass, never claims it as unadopted | new: failing read skips, does not run |
| 4 gate | satellite prepare | gate or review fails | row records the failure; adoption ends; entry returns to the hub queue | new |
| 5 hand back | pass on the row | killed before the write | the lease expires; the entry returns; the satellite's receipt is not reused on the hub | new: expired lease returns the entry |
| 6 merge | hub catch-up | base moved after the gate | head changes; the pass no longer applies; the hub gates again | new: catch-up after a base move runs the gate |
| 6 merge | trust | pass from another head, tree or pack sha | refused; the hub gates | new: pass with each field changed is refused |
| 7 lease | satellite dies | no renewal | expiry returns the entry; a late pass write fails its revision check | new: late write after expiry refused |

## Hub down

The database, the ship lock and the delivery rows are on the hub.
With the hub down, no `sd-ship` verb that writes can run on any machine, so no merge happens in any shape.
A satellite merge with the hub down would need an offline merge path that writes no database row and is reconciled later.
That is a new mechanism; this design does not draw it.

## Open decisions

D0. The shape.
- Option: A, move the lane and carry its pending entries; merges follow the host (Recommended).
- Option: B, adopt one entry; the hub merges on a satellite pass (a new trust rule).
- Option: C, build nothing; move lanes by hand with the sd:3003 steps.

D1. The trigger.
- Option: manual, a dashboard control or one command (Recommended).
- Option: automatic, past a queue wait or load threshold. It needs a threshold setting, a cool-down and a way back, and can move lanes back and forth.

D2. Hub down.
- Option: no merge until the hub returns (Recommended; the database lives there).
- Option: a satellite merge with operator approval; a separate item would design the offline path.

## Acceptance criteria

For shape A:

1. With two pending entries on the hub, Move lane to the satellite. Within two lane-job runs both are pending on the satellite, in the same order, and `moved` on the hub.
2. The satellite merges both. Each item gets the landing note from the satellite.
3. Move the lane back. New entries queue on the hub again.
4. Every row of the shape A failure table has its test, run fail-first.

## Risks

- The carry-over is a hand-off between machines, the class sd:3003 removed. It runs once per move, not once per entry; its failure rows each need a test.
- A carried entry gates once more on the new host. Moving a lane with many pending entries costs that many extra gates.
- Under shape B, a base that moves between the satellite's gate and the hub's merge voids the pass; under load that is common.
