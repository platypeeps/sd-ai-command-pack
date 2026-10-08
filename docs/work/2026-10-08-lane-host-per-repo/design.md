# Lane host per repository (sd:3003)

## Status

Draft, 2026-10-08. Design only; no code. The operator ruling of 2026-10-08 on sd:3003 is the requirement.

## Problem

A satellite can gate an item, but only the hub can merge it (sd:2704).
The path between the two machines has many parts:
`lane request` rows, hub intake, `lane run --satellite-only` from a per-repository hub cron job,
`sd-ship merge --satellite-gate`, offload receipts under a trust rule, and a published pack digest.
Each part can refuse, and each refusal hands the item back to the other machine.

Evidence from the night of 2026-10-08, one pull request in a work repository gated on a satellite:

- The lane did not merge it. A person ran the merge line that `hand_merge` prints, on the hub.
- The hub's pack checkout had to stay at the satellite's pack revision, so the digests matched.
  That needed a lane hold for the pack repository while the item waited.
- Two sessions on two machines exchanged messages to sequence the gate, the request and the merge.

The cost is in the hand-off, not in the gate or the merge.
A machine that gates and merges its own repositories needs no hand-off.

## Decision

**The setting.** A new column `repo.lane_host` in the workflow database, beside `ci` and `runner_merge`.
Its value is a host name, written as `hostname -s` lower-cased (the `local-cron-jobs` per-host folder rule).
`NULL` means the hub; every existing row starts at `NULL`, so nothing changes at migration.

**The one verb.** `sd-db.sh repo lane-host PATH HOST|hub` sets it; `hub` writes `NULL`.
It refuses an unregistered path and a name that does not match `[a-z0-9-]+`, as `set_runner_merge` refuses.
It prints the value before and after. `repo list` shows the column.
It runs on any machine, since it is a row write over the wire.

**This machine hosts a repository** when `lane_host` equals this machine's name,
or when `lane_host` is `NULL` and this machine is the hub (`served_hub(...)` is `None`).
One pack function, `sd_lib.hosts_lane(connection, root)`, answers that; every check below calls it.
A read fault, or an `sd_db` without the column, reads as `NULL` (fail closed: only the hub hosts).

**The repository lock lives on the lane host.**
On the hub, `sd_db.ship.repository_lock` keeps its file beside the database.
Off the hub, it takes the same lock under `$XDG_STATE_HOME/sd/ship-locks/` instead of raising `HubOnly`.
Only the lane host ever takes a given repository's lock, so one machine-local lock is enough.

**What `sd-ship` refuses.** Every writing verb that takes the repository lock
(`merge`, `reconcile`, `review`, `verify-review`, `adjudicate`) refuses on a machine that does not host the repository.
It checks before the lock and again under it. The refusal:

    sd-ship merge: the lane for <owner>/<repo> runs on build-2, not on this machine (repo.lane_host).
    Run it on build-2, or move the lane: sd-db.sh repo lane-host <path> <this host>.

Code `lane_elsewhere`, boundary `policy`, state `operator_decision`.
`prepare` on a non-host, the hub included, runs lock-free with revision-checked saves, as a satellite prepare runs today (sd:2679).
`lane enqueue|cancel|move|hold|release|run` refuse the same way, since the queue file is local to the lane host.

**What each machine's lane job does.** One job per machine, the same file everywhere:
`sd-ship lane run --hosted`. It lists the `repo` rows this machine hosts and runs `lane run` for each, one after another.
Each repository keeps its own runner lock; a held lock skips that repository, never waits.
The runner reads `lane_host` again before each claim. A moved lane stops at the next item boundary, never mid-merge.

**The lane host gates and merges.** A lane host's `lane run` is today's hub `lane run`:
`prepare --catch-up`, its own `sd-check` (or its own receipt reuse), then `merge --manual`.
No receipt crosses a machine, so no trust rule, no offload view and no pack digest compare.

## What retires

Each mechanism, with its files. Enumerate again with a repo-wide grep before each deletion.

| # | Mechanism | Pack files | System files |
| --- | --- | --- | --- |
| 1 | Lane requests and intake | `bin/sd_lane.py`: `request`, `requests`, `intake`, `take_in`, `malformed`, `claimable`, `acknowledges`, `write_outcome`, `REQUEST_PREFIX`, `REFUSAL_ACTIONS`; the `lane request` parser; `tests/test_sd_lane_requests.py` | none |
| 2 | Satellite-only runs and satellite entries | `bin/sd_lane.py`: `--satellite-only`, `SATELLITE`, `process_satellite`, `satellite_merge_argv`, `handed_back`, `hand_merge`, `note_hand_back`, `LOCK_RETRIES`, `refuse_on_satellite` (replaced by `hosts_lane`) | `local-cron-jobs/examples/satellite-lane-run.job`; each `satellite-lane-<repo>.job` in the config folder |
| 3 | `merge --satellite-gate` and the trust rule | `bin/sd-ship`: the flag, the offload mode read, `satellite_status`; `bin/sd_local_gate.py`: `HAND_BACK`, `SATELLITE_REFUSALS`, `satellite_refusal`, `offload_status_inputs`; `tests/test_sd_satellite_merge.py` | none |
| 4 | Offload receipts and the offload environment | `bin/sd_gate_receipts.py`: `sd-gate-offload:v1:` rows, `offload_view`, `offload_differences`, `offload_miss`, `offload_environment`, `offload_run`, `offload_pins`, `satellite_identity`; `tests/test_sd_gate_offload_rows.py` | none |
| 5 | Pack-digest publish and compare | `bin/sd_lane.py`: `publish_pack` and its two calls; `bin/sd_gate_receipts.py`: `PACK_PREFIX` and the satellite's early warning | none |
| 6 | The opt-in column | `bin/sd_lib.py`: `repo_satellite_gate`, `SATELLITE_GATE_MODES` | `sd_db/repos.py`: `set_satellite_gate`, `repo_satellite_gate`; `sd_db/writes.py` parameter; `sd-db.sh repo satellite-gate`; a migration that drops `repo.satellite_gate` |
| 7 | Prose | `WORKFLOW.md` satellite steps; `docs/coding-to-release.md`; `docs/work/2026-10-05-satellite-gate-offload/` to `archive/`, status superseded | `local-sd-db/README.md` "Satellite gate offload" |

What stays: the hub and its served database, the satellite's lock-free `prepare`,
same-machine gate receipts and their reuse (sd:2586 speculation), `sd-ship hold`, and the staleness alarm (sd:2918).

Deletion order. Each step leaves both machines working.

1. Add `repo.lane_host`, the verb and `hosts_lane`; the `sd-ship` and `lane` refusals; the local repository lock off the hub. All rows are `NULL`, so behaviour is unchanged.
2. Add `lane run --hosted`; install its job on every machine; remove the hub's `satellite-lane-<repo>.job` files.
3. Check that no `lane-request:v1:` row is `requested` or `queued`. Then move each satellite repository: `repo lane-host <path> <satellite>`.
4. Delete rows 1, 2, 3 and 5 of the table in one pack change. Nothing calls them after step 3.
5. Delete row 4. It is separate because the environment filter changes what an opted-in repository's gate sees.
6. Drop `repo.satellite_gate` (row 6): the pack reads it fail-closed, so an older pack still reads `off`.
7. Prose (row 7) moves with the step that removes its subject.

## Moving a lane

From any machine:

1. `sd-db.sh repo lane-host <path> build-2`. The verb prints `before: hub, after: build-2`.
2. The old host's running entry, if any, finishes. Its runner reads the setting before the next claim and stops there.
3. On the old host, `sd-ship lane list` shows the entries still pending; cancel each one there.
4. On the new host, create a worktree on each item's pushed branch and run `sd-ship lane enqueue` for it.
   The next `lane run --hosted` on the new host gates it there and merges it.

An in-flight pull request loses nothing. Its `ship:` row is in the hub database, and its pull request is on GitHub.
The new host's `prepare --catch-up` gates again on its own machine and posts `sd/local-gate` at the same or a newer head.
The cost is one extra gate run.

Two hosts can overlap for one entry: the old host still merges while the new host prepares.
Branch protection's up-to-date rule stops a stale merge, and the new host's prepare catches up again.
No lease covers that window; the cost is time, not a wrong merge.

## Tests (fail first)

Each test fails on `main` before the change, and passes after it.

- `repo lane-host` sets, prints before and after, writes `NULL` for `hub`, refuses an unregistered path and `Build_2`.
- `hosts_lane`: `NULL` on the hub is true; `NULL` on a satellite is false; a matching name on a satellite is true; a column-less `sd_db` reads `NULL`.
- `sd-ship merge` on a non-host refuses `lane_elsewhere` and names the host, before the lock; no row changes.
- The same refusal under the lock, when the setting moves between the first check and the lock.
- `sd-ship merge` on a satellite that hosts the repository takes a local lock and merges (fake GitHub); today it raises `hub_only`.
- `prepare` on a non-host stays lock-free and saves under the revision check.
- `lane enqueue` and `lane run` on a non-host refuse `lane_elsewhere`.
- `lane run --hosted` runs only the hosted repositories, in order, and skips one whose runner lock is held.
- A moved lane: the runner finishes its running entry and claims no next entry for that repository.
- The runner's automatic merge (`runner_merge = auto`) on the hub, for a repository hosted elsewhere, refuses `lane_elsewhere`.
- After step 4: `sd-ship lane request` and `merge --satellite-gate` are unknown arguments (parser test).

## Open questions

1. **The host name format.** Recommend `hostname -s` lower-cased: the cron-jobs folder already uses it, and it is local.
   The tailnet node name is the alternative; it needs Tailscale up to answer.
2. **Which verbs the setting limits.** Recommend every verb that takes the repository lock, not only `merge`:
   the lock lives on the lane host, so a lock-taking verb elsewhere would take a second, unrelated lock.
3. **Queue entries on a move.** Recommend no automatic transfer: the operator cancels on the old host and re-enqueues on the new one.
   A transfer needs the two machines to talk, which is the hand-off this design removes.
4. **The offload environment filter (row 4).** Recommend retiring it.
   It exists so two machines run the same check; with one gate machine per repository it only drops variables.
   The pinned tools of sd:2936 stay only if a caller other than `offload_pins` reads them; decide at step 5 by grep.
5. **Order against sd:2997** (`sd_db` moves into the pack). Recommend steps 1 to 3 in system's `local-sd-db` now,
   as one migration and one verb; sd:2997 then moves them with the rest. Waiting for sd:2997 keeps the hand-run merges in place.
