---
title: A satellite runs a busy lane from one shared queue
created: 2026-10-10
item: sd:3174
---

# Design: a satellite runs a busy lane from one shared queue (sd:3174)

## Problem

The hub hosts most lanes. When its gates pile up, queued items wait while the satellite's CPUs sit idle.
sd:3003 lets the operator move a repository's lane to a satellite (`repo.lane_host`), but the queue stays behind.
Each lane's queue is a file on its host's disk (`<lane root>/<repo>/lane/queue/queue.json`),
and each entry names a worktree and a body file on that disk.
So a move today means: cancel each pending entry on the old host, make worktrees on the new host, enqueue again (sd:3003, "Moving a lane").

The first answer carried entries between hosts. Review blocked it three rounds running on that carry:
transfer identity, an interrupted move back, lost work. The operator ruled on 2026-10-10: one shared queue, no carry.

## Approach

The queue moves into the hub database. Whichever host `repo.lane_host` names runs the lane.
Nothing is copied between hosts: a move changes who claims the next entry, and every host reads the same rows.

- **Store.** The `state` table, kind `checkpoint`, one key per entry: `lane:v1:<owner/repo>:<entry id>`.
  The latest row of a key is the entry; older rows are its history. This is the store and the append-only pattern of
  the `ship:` receipts, and of the retired `lane-request:` rows. No new table and no schema change.
- **Lock.** Every queue write is one hub database transaction (`BEGIN IMMEDIATE`), local on the hub and over the
  tailnet session on a satellite. It replaces the queue file's flock. The read, the check and the write sit in one
  transaction, so `--expected-revision` and `--expected-head` keep their meaning.
- **Runner.** The machine-local runner lock stays: one runner per repository per machine.
  Across machines, a claim refuses while another entry of the repository runs: one running entry per repository.

Rejected:

- **Carry entries between hosts** (the previous shape A). Its transfer protocol is what failed review.
- **Adopt one entry and merge on the hub** (shape B). It needs the hub to trust a satellite's gate, the rule the
  2026-10-08 ruling retired, and any merge between the gate and the hub's merge voids the pass.
- **Build nothing** (shape C). Moves stay three manual steps per entry.

## Decisions

Operator, 2026-10-10. D0 to D2 stand from the first round; the shared queue replaces D0's carry.

- D0. Move the whole lane with the existing control: the dashboard's Move lane or `sd-db.sh repo lane-host`.
  Merges follow the host. Pending entries follow because they live in the shared queue.
- D1. The trigger is manual: that same control.
- D2. No merge while the hub is down; the database lives there.
- Shared queue: the queue lives in the hub database; nothing is copied between hosts.
- D3. The operator can release a stuck running entry at once, without waiting for its lease (below, "Operator release").

## The entry

Fields another machine needs to run it:

- `id`: made once at enqueue, `<UTC stamp>-<8 hex>`; the key's last part.
- `repository` (`owner/name`, lower-cased), `item`, `branch`, `expected_head`, `title`.
- `body` and `acceptance`: the texts, not file paths. The runner writes each to a private temporary file for
  `prepare`. This retires `keep_body` and `drop_body`, and new entries write nothing to `bodies/` (the import empties it of what it read): rows are history, so `retry` copies the
  last entry's texts and no copy rule is needed.
- `claim` (`deliver` or `associate-only`) and `authority`, unchanged.
- `position`: the queue order. Enqueue takes the largest position plus one; `move` renumbers the pending entries.
- `enqueued_on` (host) and `worktree`: a hint, valid only on that host.
- `status`, `held` and the outcome fields, as today. Each log path gets the `host` that wrote it; logs stay on that disk.

`lane enqueue` publishes the expected head first, by the rule in "Publishing a head".
A refused or failed publish refuses the enqueue; nothing is queued.
`lane list` prints `body_bytes`, not the body, and keeps its `queue` key, now the local lane folder, for the dashboard.
A checkout whose origin names no GitHub repository has no lane: prepare could not open its pull request either.

## Publishing a head

Review rounds 1 and 2 found one class: what a step publishes, and when. Another host runs an entry only from a commit
on `origin`, so each step that names a head for another host publishes exactly that head, or names one already there.

One rule for every publish: push `<head>:refs/heads/<branch>`, never the branch tip and never with force.
A builder can move its branch after enqueue, and `--expected-head` takes any local commit; the explicit refspec still
publishes the head the entry names. The steps, from the repository's checkout, whose worktrees share one object store:

1. Read the tip of `branch` on `origin` (`git ls-remote`), and fetch it when this checkout lacks it.
   A failed read or fetch is an unknown answer, not "no branch".
2. The tip is `head` or contains it: published, push nothing. The runner's head rule decides the rest, as today:
   a catch-up merge runs, any other move skips with `head_moved`.
3. This checkout has no `head` commit: `head_gone`. The tip and `head` each lack the other: `branch_diverged`.
   Both answers are definite: the same push can never succeed.
4. Else push; with no branch, or a tip that `head` contains, it is a fast-forward. A failed or refused push is
   unknown: `origin` may have moved between the read and the push.

Every step that publishes, or depends on a published head:

- `lane enqueue` publishes `expected_head`. Any answer but published refuses the enqueue; nothing is queued.
- `lane retry` of a blocked entry, imported or not, publishes at retry time. Its head is the catch-up merge in the
  worktree when that is on this host, else `expected_head`. `head_gone` refuses with "sd:N's head <sha> is not on
  `origin` or in this checkout; run the retry on <enqueued_on>, or enqueue again from a worktree that has it".
  `branch_diverged` and unknown refuse with git's answer. A refusal queues nothing, and the old entry stays blocked.
- The import publishes pending entries only (see "Migration"). An unknown answer stops the import for the repository
  and keeps the file. `head_gone` or `branch_diverged` imports that entry `skipped` with the reason, so one dead branch
  cannot hold the live queue; `lane retry` publishes it once the operator fixes the branch.
- The import publishes no blocked (`failed`, `skipped`, `prepared`) or terminal entry: those rows are history.
  Their worktrees or branches may be gone. `lane retry` is the one way back to pending, and it publishes then.
- `prepare`, unchanged, pushes its reviewed head, catch-up merge included, by the same refspec.
- A put-back (move, reclaim, operator release, hub-fault requeue) publishes nothing. It reads `origin/<branch>` only
  to move `expected_head` to a catch-up merge that prepare pushed (see "Claim and lease").
- A claim and the worktree step publish nothing. On another host the worktree step fetches `origin/<branch>`.
  A failed fetch is unknown, not a skip: the runner puts the entry back pending at its place and stops this run.

## Claim and lease

A running entry carries `holder` (`host`, `pid`, a random `token` made per claim), `step` (`prepare` or `merge`)
and `lease_until`. The existing locks cannot do this: the ship flock and the runner lock are files on one machine,
and `runner_lease` belongs to the framework runner's `runner_run` rows.

1. **Claim**, one transaction: read `repo.lane_host`; stop unless this host runs the lane.
   Stop if another entry of the repository is `running` with a live holder.
   Take the first pending entry not held, by position; write it `running` with a new holder, `step: prepare` and
   `lease_until` = now + 2 × `PREPARE_SECONDS` (prepare and its one review retry).
   The host read and the claim sit in one transaction, and `set_lane_host` writes in its own, so a move is either
   before the claim or after it.
2. **Before merge**, one transaction: check the holder token and the lane host. On this host, write `step: merge` and
   `lease_until` = now + `MERGE_SECONDS` + 30 minutes for the landing. Off it, put the entry back (below).
3. **Finish**, one transaction: write the outcome only if the entry is still `running` under this token.
   A token that no longer matches writes nothing: the runner reports `claim_lost` and stops.
   A second try that finds its own outcome under its token is done, so a retried write is idempotent.

Every runner write checks the token. That includes the hub-fault requeue (sd:3239) and the step write.
A runner write that meets a hub fault is tried again every 30 seconds for up to 10 minutes, then the runner stops.

**Reclaim.** A holder is dead when its host is this machine, this machine's runner lock for the repository is free,
and its pid is gone. That check runs for every repository with a checkout here, hosted or not, at each
`lane run --hosted`. A holder on another machine is dead only once its `lease_until` has passed; the lane host checks
that at claim. A dead holder's entry:

- at `step: prepare` goes back to pending at its place, with `reclaims` plus one. Prepare saves under revision
  checks and runs again safely. At the third reclaim the entry fails instead, so a crash loop stops.
- at `step: merge` fails with today's reclaim text: a merge may have landed, so read its logs and pull request.

**Operator release.** The lease is the backstop, not the only way out. `lane cancel` on a running entry, no new verb or flag,
applies the reclaim rule above at once: at `step: prepare` the entry goes back to pending at its place; at `step: merge` it fails
with the reclaim text. It refuses when the holder is on this machine and its pid is alive. A holder on another machine counts as
stuck on the operator's word: the dashboard Queue row shows the holder host, step and claim age, and a Release control that
confirms first. The released claim's token is void, so a holder that comes back has every queue write refused.
A merge the old holder already started can still land; branch protection's up-to-date rule stops a second one (sd:3003).

A put-back (move, reclaim, release, hub-fault requeue) moves `expected_head` to prepare's catch-up merge, as
`caught_up` does today, only when `origin/<branch>` is that merge: prepare pushed it. A catch-up that exists only in
the worktree, or a failed read of `origin`, leaves `expected_head` as it was, still published; the worktree rules
below accept the catch-up on the host that made it. So `expected_head` always names a published commit.

## When the lane moves

The operator moves the lane with the existing control. Nothing else happens at the move.

- The old host's runner finishes the step in flight. At the before-merge write it finds the move and puts the entry
  back: `pending`, same position, holder removed, `moved_off` set to its host and time. It then stops.
- `sd-ship merge` keeps its own check: under the ship lock it reads the host again and refuses `lane_elsewhere`.
  The runner treats that answer as a move and puts the entry back too.
- The new host's next `lane run --hosted`, within 5 minutes, waits while the old entry runs, then claims in position
  order. The moved entry is first again.
- A move during a merge is refused as today: `set_lane_host` holds the host's ship flock.
- A moved entry costs one extra gate: gate receipts stay bound to their machine (sd:2796), so the new host gates again.

The new host waits for the old host's step in flight, up to one prepare. That keeps one order per repository and one
gate at a time per lane.

## Worktrees on the new host

The runner needs a checkout at the entry's head on its own disk. In order:

1. The entry's `worktree`, when `enqueued_on` is this host and that worktree's HEAD is `expected_head` or its
   catch-up merge.
2. Any worktree on this host with `branch` checked out at `expected_head` or its catch-up merge.
3. Else fetch `origin/<branch>` and require `expected_head` there, or its catch-up merge.
   No `origin/<branch>` skips the entry with `head_gone`; `lane retry` publishes it again from a checkout that has it.
   With no local branch of that name, make a lane worktree at `<lane folder>/worktrees/<item>` on a new local branch
   at that head, tracking `origin/<branch>`.
   A local branch at another commit, or one checked out elsewhere at another head, skips the entry with `branch_busy`.

The runner removes a lane worktree it made once the entry ends: no builder writes there.
Builder worktrees keep today's rule: the runner never removes them, and the landing note gives the removal command,
naming the host they are on.
An entry with no worktree on this host gets no speculative gate; its speculation records why.

## Migration of the file queues

Each host imports its own queue files. `lane run --hosted` does it for every repository with a checkout on this disk,
and any lane verb does it for its repository, whenever a `queue.json` exists.

1. Take the repository's runner lock without waiting, then the old queue flock. A busy runner lock skips the import
   until the next run, so an older runner mid-entry keeps its file.
2. Publish each pending file entry's `expected_head` by the rule in "Publishing a head". Older `sd-ship` never
   pushed, so these heads may exist only here. An unknown answer stops the import for this repository: nothing is
   written, the file stays, and the pass reports the entry. The next pass tries again.
   `head_gone` or `branch_diverged` is definite: that entry imports `skipped` with the reason, and the rest import.
   Blocked (`failed`, `skipped`, `prepared`) and terminal entries are not published: they import as history, and
   `lane retry` publishes one when it makes it runnable.
3. In one transaction, write one row per file entry, in file order, under a fixed id:
   `import-<16 hex of sha256(host, queue path, item, enqueued_at)>`. An id already present is skipped.
   Each row records the body file it read.
4. Rename the file to `queue.json.imported-<UTC stamp>`, then delete only the body files the committed rows name.
   `bodies/` itself and any other file in it stay: an older `sd-ship` copies a body before it takes the queue flock,
   so a body there may belong to an enqueue whose queue write has not happened yet. That entry lands in a new
   `queue.json`, and the next pass imports it with its body.

What the import does with older rows:

- `running`: no live runner holds the lock, so its runner died; imported `failed` with today's reclaim text.
- No `branch`: read from the worktree; with no worktree, a pending entry imports `failed` with `no_branch`,
  and a blocked one keeps its status. `lane retry` refuses either and names `lane enqueue`.
- A pending entry whose body file is gone: `failed` with `no_body`. A blocked one keeps its status with no body;
  `lane retry` refuses it, as today, and names `lane enqueue --body-file`.
- A status this version does not know, such as the retired `handed_back`: kept as history, terminal.
- An item already pending or running in the shared queue: imported `cancelled` with `duplicate_on_import`.

Pending entries an sd:3003 move left on an old host import too, so the new host runs them.
The retired `lane-request:`, `sd-lane-pack:` and `sd-gate-offload:` rows stay inert: nothing here reads them.

## Hub down

The queue, the lane host rows and the delivery rows are on the hub. With the hub down, every lane verb on
every machine refuses with `hub_unavailable` and writes nothing. A runner stops at its next queue write, after the
10-minute retry. No merge happens (D2). When the hub returns, reclaim settles any entry whose holder died meanwhile.
Today a satellite already refuses `lane enqueue` with `lane_unknown` while the hub is down, so this loses nothing.

## Non-goals

- Two running entries in one repository, on one host or two.
- Cross-repository merge order; each repository keeps its own lane.
- A merge while the hub is down (D2), or an offline queue on a satellite.
- An automatic trigger (D1).
- Moving a satellite-hosted lane from the hub; `set_lane_host` still runs on the lane's host (sd:3003 part 2).
- Moving logs between hosts; an entry names the host that holds each log.
- Gate receipts that cross machines.
- Deleting the retired `lane-request:` and offload rows.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| enqueue | branch pushed | push refused or fails, or `branch_diverged` | enqueue refuses; nothing queued | new: a failing push double leaves no row; a diverged remote refuses |
| enqueue | branch pushed | the branch tip moved past `--expected-head` before enqueue | the explicit refspec publishes `expected_head`, not the tip | new: enqueue an older commit; `origin/<branch>` is that commit |
| enqueue | branch pushed, no row | killed or hub fault between the push and the row write | the rerun finds the head published, pushes nothing, and writes one row | new: kill after the push; rerun gives one entry and no second push |
| enqueue | entry row | hub fault; the write may have landed | verb says `hub_unavailable`; rerun queues it, or refuses `already queued` if it landed | new: a write that lands but reports failure; rerun gives one entry |
| claim | entry `running` | hub fault or unknown outcome | runner starts no step; a landed claim has a dead holder, and reclaim puts it back pending | new: claim lands, answer lost; next run gives one pending entry |
| claim | none | lane moved after the runner's last read | host read in the claim's transaction; no claim | new: move between read and claim claims nothing |
| claim | entry `running` | old and new host claim at once | one transaction wins; the other sees a running entry and stops | new: two hosts, one claim |
| prepare | entry at `step: prepare` | runner or host dies | same host: pid gone, back to pending; other host: after `lease_until`; third reclaim fails it | new: kill mid-prepare, rerun gives pending; three kills give failed |
| release | running entry reclaimed by the operator | the holder is alive on another machine and writes again | its token is void, so each queue write is refused and it stops; a merge it already started meets branch protection | new: release a running entry, then a write under the old token is refused; release with a live local pid refuses |
| prepare | entry at `step: prepare` | lease passes while the holder sleeps, lane not moved | only the lane host claims, it is the holder's host, and its pid is alive: no reclaim | new: expired lease, live pid, same host: entry stays running |
| before merge | entry back to pending | lane moved during prepare | put back at its place with `moved_off`; new host claims it first | new: move mid-prepare; one entry, old host stops |
| before merge | none | hub fault for 10 minutes | runner stops; reclaim later sees `step: prepare` and puts it back | new: step write fails; rerun gives pending |
| merge | none | merge refuses `lane_elsewhere` | put back pending, as a move | new: a merge double answering `lane_elsewhere` |
| merge | entry at `step: merge` | runner dies mid-merge | reclaim fails it with today's text | existing reclaim test, adapted |
| finish | outcome row | hub fault for 10 minutes after a merge | runner stops; reclaim fails it with "a merge may have landed" | new: finish write fails after a merge |
| finish | none | token reclaimed while the holder slept | nothing written; runner reports `claim_lost` and stops | new: reclaim, then a late finish writes nothing |
| finish | outcome row | unknown outcome; retried | the retry finds its own outcome under its token | new: double finish gives one outcome row |
| worktree | none | fetched head is neither `expected_head` nor its catch-up | entry `skipped`, `head_moved` | new: moved remote skips |
| worktree | none | `origin/<branch>` deleted after enqueue | entry `skipped`, `head_gone`; `lane retry` publishes it again from a checkout that has it | new: deleted remote branch skips `head_gone` |
| worktree | entry `running` | the fetch fails | unknown, not a skip: put back pending at its place; next run tries again | new: failing fetch double leaves the entry pending |
| put-back | `expected_head` | the catch-up merge exists only in the worktree, or the `origin` read fails | `expected_head` stays, still published; the same-host worktree rule accepts the catch-up | new: put-back with an unpushed catch-up keeps `expected_head`, and the same host runs it |
| worktree | none | local branch at another commit | entry `skipped`, `branch_busy` | new: conflicting local branch skips |
| worktree | lane worktree made | killed before claim or step | next run reuses it at the head, or removes and remakes a lane worktree it made | new: leftover lane worktree at another head |
| import | rows | killed mid-transaction | nothing written; next pass imports | new: fault inside the transaction leaves no row |
| import | rows written | killed before the rename | fixed ids exist and are skipped; the file is renamed | new: rerun gives one row per entry |
| import | file renamed | killed before the named body files go | next pass reads the committed rows and deletes the body files they name | new: leftover named bodies removed, an unnamed body kept |
| import | none | an older `sd-ship` copied a body, not yet its queue write | the body is not named by any row, so it stays; its entry lands in a new file and imports with it | new: a body written between import and the old enqueue's queue write survives and imports |
| import publish | pending branches pushed | a read, fetch or push fails or is refused | unknown: nothing written, file kept, entry reported; next pass retries | new: a failing push leaves the file and writes no row |
| import publish | some branches pushed | killed before the transaction | pushed branches are harmless; the rerun finds them published, pushes nothing, and imports | new: rerun after a kill between push and write gives one row per entry |
| import publish | branch pushed | the builder moved the branch after enqueue | the refspec publishes `expected_head`, not the tip; a remote tip that already contains it is left alone, and the runner skips `head_moved` as today | new: pending entry behind its branch tip; `origin/<branch>` gets `expected_head` |
| import publish | entry row | a pending entry's commit is gone, or its remote branch diverged | definite: that entry imports `skipped` with `head_gone` or `branch_diverged`; the rest import | new: one dead pending branch among live ones; live rows import, the file is renamed |
| import | rows | a blocked entry's worktree and branch were deleted | no publish: it imports as history with its status; the pending rows import | new: blocked entry with no branch or commit; no push attempted, every row written |
| retry | branch pushed | the retried entry's commit is in this checkout but not on `origin` | retry publishes `<head>:refs/heads/<branch>` at retry time, then queues | new: retry an imported blocked entry; `origin/<branch>` is its head |
| retry | none | the commit is gone here and on `origin`, or the remote diverged | refuses with `head_gone` naming `enqueued_on`, or with git's answer; nothing queued; the old entry stays blocked | new: retry after the branch and worktree were deleted refuses and writes no row |
| retry | branch pushed, no row | killed or hub fault between the push and the row write | the rerun finds the head published, pushes nothing, and queues one entry | new: kill after the retry push; rerun gives one entry |
| import | rows | an older `sd-ship` enqueues during the import | the old queue flock orders it; a later entry lands in a new file, imported next pass | new: append after rename imported once |
| import | rows | older rows: `running`, no branch, no body, `handed_back`, duplicate item | the rules in "Migration" | new: one fixture per older row |
| rollback | file renamed | the pack goes back to before slice 1 | the old code finds no queue file and runs nothing; rename the `imported` file back, or roll forward | new: the `imported` file holds the original bytes |
| mixed versions | entry row | slice 2 enqueues into a lane whose host still runs an older pack | the entry waits; that host's self-install runs it | covered by the slice 2 test that runs an entry another host enqueued |
| hub down | none | the hub is down | every lane verb refuses `hub_unavailable` and writes nothing | new: unreachable hub, each verb |

## Acceptance criteria

- [ ] With two pending entries on the hub, Move lane to the satellite. Within two lane-job runs the satellite runs
      both in order and merges them; the hub's queue view shows the same rows.
- [ ] A move during a prepare on the hub puts that entry back first; the satellite runs it, and it merges once.
- [ ] A builder on the satellite enqueues into a hub-hosted lane, and the hub runs it.
- [ ] Each host's file queue is imported once, and `lane list` on both machines prints the same entries.
- [ ] Every failure table row has its test, run fail-first.

## Risks

- One transaction per queue write puts the hub database in every lane step. A slow tailnet session holds the hub's
  write lock for its round trips. The writes are a few small rows per entry.
- A host that dies mid-merge and never returns holds its entry until the lease passes, up to `MERGE_SECONDS`
  plus 30 minutes. A dead holder mid-prepare on another host waits up to 2 × `PREPARE_SECONDS`.
  Operator release (D3) ends either wait at once.
- Reclaim to pending changes today's rule for a dead runner mid-prepare, which marks the entry failed. The cap of
  three reclaims bounds a crash loop.
- A database restored from a backup (sd:3256) brings back the queue as of the backup.
  An entry that merged after it reads pending, and its prepare then meets the merged pull request.
- Evidence ties: a claim's writes are tied to its token; a step to the repository's lane host read in the same
  transaction; an imported row to its host, queue path, item and enqueue time; a worktree to `expected_head` or its
  catch-up merge; a published branch to `expected_head` by the explicit refspec, never to the branch tip.

## Slices

Each slice leaves the hub and every satellite working.

1. **Pack: the queue in the database.** `bin/sd_lane.py`: the store, the entry shape with body texts and `branch`,
   the publish rule for enqueue, retry and the import of pending entries, claim with holder and lease, token checks, reclaim by step, the 10-minute write retry, and the
   import. Lane verbs still refuse off the lane host, and the runner still uses the entry's own worktree.
   Only the storage changes on one host. The module docstring and `WORKFLOW.md`'s queue file prose follow. Opus.
2. **Pack: any host runs any entry.** Worktrees on the new host, the before-merge host check and put-back that reads only a pushed catch-up,
   `lane_elsewhere` as a move, cross-host lease reclaim, and host names in the landing note. `enqueue`, `list`,
   `move`, `hold`, `release`, `retry` and `cancel` work from any host, so `HOST_VERBS` retires; only `run` stays
   host-bound. Starts once every machine runs slice 1. Opus.
3. **System: the dashboard and the docs.** The Queue page lists every managed repository's lane, not only those with
   a lane folder, and shows a running entry's host, `step` and claim age, which replaces its prepare-log probe.
   A running row carries a Release control that confirms, then runs `lane cancel` on that entry (D3).
   Move lane and the `local-sd-db/README.md` "Lane host" section say pending entries follow.
   Invoke `hallmark` first.
