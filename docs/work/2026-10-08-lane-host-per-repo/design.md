# Design — lane host per repository (sd:3003)

## Status

Accepted 2026-10-08. The operator ruling of 2026-10-08 on sd:3003 is the requirement; "Decisions taken" lists the rest.

## Problem

A satellite can gate an item, but only the hub can merge it (sd:2704).
The hand-off needs `lane request` rows, hub intake, a per-repository hub cron job (`lane run --satellite-only`),
`sd-ship merge --satellite-gate`, offload receipts under a trust rule, and a published pack digest.
Each part can refuse, and each refusal hands the item back to the other machine.

On 2026-10-08 one pull request in a work repository, gated on a satellite, needed three manual steps:

- A person ran the merge line that `hand_merge` prints, on the hub.
- A lane hold kept the hub's pack checkout at the satellite's pack revision, so the digests matched.
- Two sessions on two machines exchanged messages to sequence the gate, the request and the merge.

The cost is in the hand-off, not in the gate or the merge.

## Decision

**The setting.** A new column `repo.lane_host`, beside `ci` and `runner_merge`.
Its value is `hostname -s` lower-cased, the `local-cron-jobs` per-host folder rule.
`NULL` means the hub; every existing row starts at `NULL`, so nothing changes at migration.

**One setter, two surfaces.** `sd_db.repos.set_lane_host(connection, path, value)` is the only writer.
- Dashboard: the Management page shows `lane host` on each repository row, with a "Move lane" control.
  It posts to `/api/repos/lane-host`, which calls the setter through `management_screen.set_repo`,
  as `runner-merge` and `managed` do. It refuses a stale `before` and offers Undo.
  It offers `hub`, each host name a row already holds, and a typed name.
- Verb: `sd-db.sh repo lane-host PATH HOST|hub`, with no other flag. `hub` writes `NULL`.
  It prints the value before and after; `repo list` shows the column.
- Both refuse an unregistered path and a name that does not match `[a-z0-9-]+`.

**This machine hosts a repository** when `lane_host` equals this machine's name,
or when `lane_host` is `NULL` and this machine is the hub (`served_by(...)` is `None`).
`sd_db.ship.hosts_lane(connection, database, repository)` answers that. It matches `repository`,
the `owner/name` the lock takes, to the row whose `remote` gives it (`protection.github_slug`).
No row, a read fault, or an `sd_db` without the column reads as `NULL`: only the hub hosts.
The pack's `sd_lib.hosts_lane` wraps it and fails closed the same way on an older library.

**The repository lock refuses on a non-host, and lives on the host.**
`sd_db.ship.repository_lock` calls `hosts_lane` first, so every caller is covered:
the `sd-ship` writing verbs, the no-item verbs in `sd_ship_no_item`, and the runner's merge.
- On a non-host it raises `LaneElsewhere` (code `lane_elsewhere`) and takes no lock:

      The lane for <owner>/<repo> runs on build-2, not on this machine.
      Run it there, or move the lane: dashboard, Management, <repo>, Move lane;
      or sd-db.sh repo lane-host <path> <this host>.

- On the hub that hosts it, the lock file stays beside the database.
- On a satellite that hosts it, the lock file is under `$XDG_STATE_HOME/sd/ship-locks/`, not `HubOnly`.
  Only the host takes a given repository's lock, so one machine-local lock is enough.

**`sd-ship` on a non-host.** `merge`, `reconcile`, `review`, `verify-review` and `adjudicate` refuse with that text.
`prepare` runs lock-free with revision-checked saves, as a satellite prepare does today (sd:2679).
That includes the hub for a repository hosted elsewhere: `dispatch` tests `hosts_lane`, not `hub_serving`.
`lane enqueue|cancel|move|hold|release|run` refuse the same way: the queue file is local to the host.

**Each machine's lane job.** The same job file on every machine: `sd-ship lane run --hosted`.
`--hosted` replaces `--satellite-only`, so the flag count does not grow.
It runs `lane run` for each repository this machine hosts, one after another.
A held runner lock skips that repository and never waits.
The runner reads `lane_host` again before each claim, so a move stops it at the next item, never mid-merge.
A host's `lane run` is today's hub `lane run`: `prepare --catch-up`, its own `sd-check`, then `merge --manual`.
No receipt crosses a machine, so no trust rule, offload view or pack digest compare is needed.

## What retires

Grep the whole repository again before each deletion.

| # | Mechanism | Pack | System |
| --- | --- | --- | --- |
| 1 | Lane requests and intake | `bin/sd_lane.py`: `request`, `requests`, `intake`, `take_in`, `malformed`, `claimable`, `acknowledges`, `write_outcome`, `REQUEST_PREFIX`, `REFUSAL_ACTIONS`, the `lane request` parser; `tests/test_sd_lane_requests.py` | none |
| 2 | Satellite-only runs | `bin/sd_lane.py`: `--satellite-only`, `SATELLITE`, `process_satellite`, `satellite_merge_argv`, `handed_back`, `hand_merge`, `note_hand_back`, `LOCK_RETRIES`, `refuse_on_satellite` | `local-cron-jobs/examples/satellite-lane-run.job`; each `satellite-lane-<repo>.job` in the config folder |
| 3 | `merge --satellite-gate`, trust rule | `bin/sd-ship`: the flag, the offload mode read, `satellite_status`; `bin/sd_local_gate.py`: `HAND_BACK`, `SATELLITE_REFUSALS`, `satellite_refusal`, `offload_status_inputs`; `tests/test_sd_satellite_merge.py` | none |
| 4 | Offload receipts, offload environment | `bin/sd_gate_receipts.py`: `sd-gate-offload:v1:` rows, `offload_view`, `offload_differences`, `offload_miss`, `offload_environment`, `offload_run`, `offload_pins`, `satellite_identity`; `tests/test_sd_gate_offload_rows.py` | none |
| 5 | Pack digest | `bin/sd_lane.py`: `publish_pack` and its two calls; `bin/sd_gate_receipts.py`: `PACK_PREFIX` | none |
| 6 | The opt-in column | `bin/sd_lib.py`: `repo_satellite_gate`, `SATELLITE_GATE_MODES` | `sd_db/repos.py`: `set_satellite_gate`, `repo_satellite_gate`; `sd_db/writes.py`; `sd-db.sh repo satellite-gate`; a migration that drops the column |
| 7 | Prose | `WORKFLOW.md` satellite steps; `docs/coding-to-release.md`; the offload item to `docs/work/archive/2026-10/2026-10-05-satellite-gate-offload/` | `local-sd-db/README.md` "Satellite gate offload" |

What stays: the hub and its served database, the lock-free `prepare`, same-machine gate receipts and reuse (sd:2586),
`sd-ship hold`, and the staleness alarm (sd:2918).

## Moving a lane

1. Dashboard, Management, the repository's row: Move lane, then pick `build-2`.
   Or from any machine: `sd-db.sh repo lane-host <path> build-2`. Both show `before: hub, after: build-2`.
2. The old host finishes its running entry, if any, and claims no next entry for that repository.
3. On the old host, `sd-ship lane list` shows the pending entries; cancel each one there.
4. On the new host, make a worktree on each item's pushed branch and run `sd-ship lane enqueue`.

An in-flight pull request loses nothing: its `ship:` row is in the hub database, and the PR is on GitHub.
The new host's `prepare --catch-up` gates again, so a move costs one extra gate run.
If the old host still merges while the new host prepares, branch protection's up-to-date rule stops a stale merge.

## Acceptance

Each line is a test that fails before its change.

1. The verb sets `repo.lane_host`, prints before and after, writes `NULL` for `hub`, and takes no other flag.
2. The verb and the dashboard route refuse an unregistered path and the name `Build_2`.
3. The Management page shows each repository's lane host; Move lane changes it, refuses a stale `before`, and Undo restores it.
4. A migrated database reads `NULL` on every row.
5. `hosts_lane`: `NULL` on the hub is true, `NULL` on a satellite is false, a match on a satellite is true;
   a column-less `sd_db` and an unmatched remote read `NULL`.
6. `repository_lock` on a non-host raises `lane_elsewhere` and takes no lock; the text names host, dashboard control, verb, in that order.
7. `repository_lock` on a satellite host takes the local lock; today it raises `HubOnly`.
8. On a non-host, `sd-ship merge` and a no-item verb refuse before any row changes.
9. On a satellite host, `sd-ship merge` merges (fake GitHub).
10. On the hub, `prepare` for a repository hosted elsewhere runs lock-free and saves under the revision check.
11. On a non-host, `lane enqueue` and `lane run` refuse `lane_elsewhere`.
12. `lane run --hosted` runs only hosted repositories, in order, and skips one whose runner lock is held.
13. After a move, the runner finishes its running entry and claims no next entry for that repository.
14. After the retirements, `lane request` and `merge --satellite-gate` are unknown arguments, and `repo satellite-gate` is gone.

## PR split

Each PR leaves the hub and every satellite working.

1. **System: setting, dashboard, lock.** Migration `024_repo_lane_host.sql`; `set_lane_host` and the verb;
   `hosts_lane`, `LaneElsewhere` and the lock change in `sd_db/ship.py`; the Management field and Move lane
   (invoke `hallmark` first); a README "Lane host" section. Acceptance 1 to 7. All rows stay `NULL`, so nothing moves.
2. **Pack: host check and hosted job.** `sd_lib.hosts_lane`; `dispatch` in `bin/sd-ship`; the lane verbs and
   `lane run --hosted` in `bin/sd_lane.py`. Acceptance 8 to 13.
3. **System: pin and job.** `.sd-pack-rev` to PR 2's revision; `local-cron-jobs/examples/lane-run.job`.
   Then, with no PR: install the job on every machine, remove each hub `satellite-lane-<repo>.job`,
   confirm no `lane-request:v1:` row is `requested` or `queued`, and move each satellite repository from the dashboard.
4. **Pack: retire the hand-off.** Rows 1, 2, 3 and 5, then row 4 after a grep for other `sd_gate_tools` callers;
   archive the offload item. Acceptance 14 for the pack verbs.
5. **System: retire the column.** Row 6's system part and its README section; delete the example job. Acceptance 14.

## Decisions taken

The operator accepted these on 2026-10-08:

1. The host name is `hostname -s` lower-cased; it needs no Tailscale.
2. The setting limits every verb that takes the repository lock, not only `merge`.
3. A move transfers no queue entries; the operator cancels on the old host and enqueues on the new one.
4. The offload environment filter retires; the sd:2936 pinned tools stay only if a grep finds another caller.
5. The setting, verb, dashboard control and lock change land in system first; sd:2997 moves `sd_db` later.
6. The dashboard is the primary surface: the refusal names its control before the command.
7. One document per work item: this file. The pack lint asks for a `prd.md` until sd:3000 accepts a single `design.md`.

Not in scope: a dashboard view of a satellite host's queue file.
