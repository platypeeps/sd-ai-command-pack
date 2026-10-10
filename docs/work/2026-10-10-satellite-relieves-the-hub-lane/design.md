---
title: A satellite relieves a busy hub lane
created: 2026-10-10
item: sd:3174
---

# Design: a satellite relieves a busy hub lane (sd:3174)

## Status

The operator decided D0 to D2 on 2026-10-10 (see Decisions): shape A, a manual trigger, no merge while the hub is down.
The planned flow built on parts that merged away on 2026-10-10; shape A replaces it.

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

Three shapes met the need; D0 chose A.

**Shape A, chosen: move the lane, and its queue follows.**
The operator moves a repository's lane to the satellite with the existing control.
The pending entries move with it, so no one cancels and enqueues them again by hand.
The satellite gates and merges them, one order per repository, as sd:3003 does.
New: portable entries (below) and a carry-over in `lane run --hosted`. No trust rule. No new command.

**Shape B, rejected: adopt one entry, as planned.**
The satellite marks one hub entry adopted, gates it, and records a pass; the hub merges on that pass.
New: portable entries, an entry state `adopted` with a lease, one lane verb or flag to adopt,
a pass row the hub's merge gate trusts at the exact head and tree, and an ordering rule.
It brings back a narrow form of what sd:3216 deleted. A merge on the hub needs the branch up to date with the base,
so any merge between the satellite's gate and the hub's merge voids the pass; under load that is the common case.

**Shape C, rejected: build nothing.**
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
- An automatic trigger (D1).
- Adopting one entry while the hub keeps the lane (shape B).
- Bringing back gate receipts that cross machines, in shape A or C.

## Shared part: a portable entry

Today an entry names a worktree and a body file on the host's disk.
Another machine can read neither.

- `lane enqueue` pushes the branch at the expected head before it writes the queue
  (`git push origin <branch>`, no force). A push refusal refuses the enqueue; nothing is queued.
- The entry keeps `branch` beside `worktree`.
- The body and acceptance texts go to the database only when an entry leaves its host.
  They go in the existing `state` table, the store the ship rows use, under one key per transfer:
  `lane-carry:v1:<owner/repo>:<item>:<carry id>`. No new table.
- The carry id is a random id the sender makes once per transfer and writes on its local entry before the row.
  Every lookup in the carry steps matches on the carry id, never on the item alone: an item can move many times, and a row or entry from an earlier move must not count as this one.

## Shape A in steps

1. **Move.** The operator runs Move lane (dashboard) or `sd-db.sh repo lane-host <path> <satellite>`. Unchanged.
2. **Old host hands over.** `lane run --hosted` also visits a local queue whose repository it no longer hosts.
   For each pending entry, in queue order:
   1. Check the worktree is still at `expected_head`; else mark the entry `failed` with `head_moved`, as `run` does.
   2. Push the branch if the remote is behind; refuse a remote that is ahead or diverged.
   3. Make a carry id and write it on the local entry, unless the entry already has one.
   4. Write the `lane-carry` row under that id: item, branch, head, title, body text, claim, authority, acceptance text, position, `from` host.
   5. Mark the local entry `moved`, a terminal status beside `cancelled`.
   6. For each local `moved` entry, delete its own row once that row reads `taken`, with its revision. Only the sender deletes a row.
   Recovery, before step 1: a pending local entry with a carry id goes to step 4 if no row has that id, and to step 5 if one does, in any state.
   A running entry finishes first; the runner already stops at the next item.
3. **New host takes in.** Before it claims, `lane run --hosted` reads `lane-carry` rows for each repository it hosts, by position:
   1. Fetch the branch; refuse a fetched head other than the row's.
   2. Make a worktree at `~/worktrees/<repo>-lane-<item>`, or reuse one at that head.
   3. Write the body to the lane root and `enqueue` with the row's fields, with `carried_from` set to the row's carry id.
   4. Set the row's state from `carried` to `taken`, with its revision. The row stays as the sender's acknowledgement.
   Take-in reads only `carried` rows. Recovery, before step 1: a local entry in any status whose `carried_from` equals the row's carry id means step 3 ran; it goes straight to step 4.
   A row this host sent, whose carry id is on one of its own pending entries, means the lane came back before the hand-over finished: take-in sets it `taken` and enqueues nothing, and the local entry keeps its place.
4. **Run.** The new host gates and merges as any host does.
5. **Move back.** The same steps in the other direction.

A move costs one extra gate per carried entry, as sd:3003 accepted:
the new host's `prepare --catch-up` gates again. Same-machine receipt reuse then applies.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| enqueue | branch pushed | push refused or fails | enqueue refuses; nothing queued | new: a push double that fails leaves the queue unchanged |
| enqueue | queue entry written | killed after push, before the queue write | nothing to undo: a pushed branch alone is harmless | covered by the test above |
| 2.1 hand-over | none | worktree head moved | entry `failed` with `head_moved`; no row written | new: hand-over with a moved worktree writes no row |
| 2.3 hand-over | carry id on the local entry | killed before the row write | next pass finds the id and no row, and writes the row under the same id | new: kill between id and row; rerun gives one row |
| 2.4 hand-over | `lane-carry` row written | killed before the local mark | next pass finds the row with its carry id, `carried` or `taken`, and only marks the entry `moved` | new: kill between row and mark; rerun gives one row, one `moved` entry |
| 2.4 hand-over | row written; destination takes, runs and finishes it | sender stopped between row and mark | the row stays `taken` until the sender deletes it, so the sender's next pass finds it and marks `moved`; it never writes a second row | new: kill the sender after the row; destination takes in and finishes the entry; rerun the sender; one gate, one `moved` entry |
| 2.4 hand-over | row write | database unreachable or refuses | unknown result: the entry stays pending and the pass stops; next pass finds the row by carry id if the write landed, else writes it | new: a write that lands but reports failure; rerun gives one row |
| 2.6 hand-over | `taken` row deleted | killed mid-delete, or revision conflict | the next pass deletes the rest; a row already gone is done | new: concurrent delete double |
| 3.1 take-in | none | fetched head differs from the row | row kept, refused with `carry_head_moved`; a note on the item; the operator re-enqueues by hand | new: take-in with a moved remote leaves the row and notes it |
| 3.3 take-in | local entry written | killed before the row reads `taken` | next pass finds a local entry whose `carried_from` is the row's carry id, in any status, and only sets `taken` | new: kill between enqueue and mark; let the entry finish; rerun gives one entry and no second gate |
| 3.4 take-in | row `taken` | revision conflict | reread; a row already `taken` is done | new: concurrent mark double |
| sender gone | `taken` rows left | the old host never runs again | the rows are inert: take-in reads only `carried` rows; `status` lists `taken` rows older than a day | new: status lists an old `taken` row |
| move back mid-hand-over | a row written, the local entry still pending | the lane returns before the mark | take-in finds the carry id on its own pending entry, sets the row `taken`, enqueues nothing; the entry runs here once | new: move, write the row, move back; one entry, one gate |
| repeated moves | `moved` entries and `taken` rows from earlier transfers | the same item moves hub, satellite, hub, satellite | each transfer has its own carry id, so an old `moved` entry or an undeleted `taken` row matches no new row; the item ends with one pending entry | new: four moves of one pending item, once with acknowledgements deleted between moves and once with them left |
| run | merge on the new host | old host still merging its running entry | branch protection's up-to-date rule stops the stale merge (sd:3003) | existing sd:3003 tests |
| older state | queue files without `branch` | entry from before this change | hand-over reads the branch from the worktree; with no worktree, entry `failed` with `no_branch` | new: hand-over of an old-format entry |

## Hub down

The database, the ship lock and the delivery rows are on the hub.
With the hub down, no `sd-ship` verb that writes can run on any machine, so no merge happens (D2).
A satellite merge with the hub down would need an offline merge path that writes no database row and is reconciled later.
That is a new mechanism; this design does not draw it.

## Decisions

Operator, 2026-10-10.

- D0. Shape A: move the whole lane with the existing control; its pending entries carry over; merges follow the host.
- D1. The trigger is manual: the dashboard's Move lane or `sd-db.sh repo lane-host`.
- D2. No merge while the hub is down; the database lives there.

## Acceptance criteria


1. With two pending entries on the hub, Move lane to the satellite. Within two lane-job runs both are pending on the satellite, in the same order, and `moved` on the hub.
2. The satellite merges both. Each item gets the landing note from the satellite.
3. Move the lane back. New entries queue on the hub again.
4. Every row of the shape A failure table has its test, run fail-first.

## Risks

- The carry-over is a hand-off between machines, the class sd:3003 removed. It runs once per move, not once per entry; its failure rows each need a test.
- A carried entry gates once more on the new host. Moving a lane with many pending entries costs that many extra gates.
