# Design — lane host per repository

## Status

Accepted 2026-10-08. The operator ruling of 2026-10-08 on sd:3003 is the requirement.
The operator accepted the five recommendations of the first draft; "Decisions taken" lists them.

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

## Decision

**The setting.** A new column `repo.lane_host` in the workflow database, beside `ci` and `runner_merge`.
Its value is a host name, `hostname -s` lower-cased (the `local-cron-jobs` per-host folder rule).
`NULL` means the hub; every existing row starts at `NULL`, so nothing changes at migration.

**One setter, two surfaces.** `sd_db.repos.set_lane_host(connection, path, value)` is the only writer.
- The dashboard's Management page shows a `lane host` field on each repository row, and a "Move lane" control.
  The control posts to `/api/repos/lane-host`, which calls the setter through `management_screen.set_repo`,
  as `runner-merge` and `managed` do. It refuses a stale `before`, and it offers Undo.
  It offers `hub`, each host name a row already holds, and a typed name.
- The verb: `sd-db.sh repo lane-host PATH HOST|hub`, with no other flag. `hub` writes `NULL`.
  It prints the value before and after. `repo list` shows the column.
- Both refuse an unregistered path and a name that does not match `[a-z0-9-]+`, as `set_runner_merge` refuses.

**This machine hosts a repository** when `lane_host` equals this machine's name,
or when `lane_host` is `NULL` and this machine is the hub (`served_by(...)` is `None`).
One `sd_db` function, `ship.hosts_lane(connection, database, repository)`, answers that.
It matches `repository`, the `owner/name` the lock takes, to the row whose `remote` gives it (`protection.github_slug`).
No row, a read fault, or an `sd_db` without the column reads as `NULL`: only the hub hosts.
The pack's `sd_lib.hosts_lane` calls it, and fails closed the same way on an older library.

**The repository lock refuses on a non-host, and lives on the host.**
`sd_db.ship.repository_lock` calls `hosts_lane` first. Every caller routes through it:
the `sd-ship` writing verbs, the no-item verbs in `sd_ship_no_item`, and the runner's merge.
- On a non-host it raises `LaneElsewhere` (code `lane_elsewhere`) and takes no lock. Its text:

      The lane for <owner>/<repo> runs on build-2, not on this machine.
      Run it there, or move the lane: dashboard, Management, <repo>, Move lane;
      or sd-db.sh repo lane-host <path> <this host>.

- On the hub that hosts it, the lock file stays beside the database.
- On a satellite that hosts it, the lock file is under `$XDG_STATE_HOME/sd/ship-locks/`, not `HubOnly`.
  Only the host takes a given repository's lock, so one machine-local lock is enough.

**`sd-ship` on a non-host.** `merge`, `reconcile`, `review`, `verify-review` and `adjudicate` refuse with that text.
`prepare` runs lock-free with revision-checked saves, as a satellite prepare runs today (sd:2679).
That now includes the hub for a repository hosted elsewhere: `dispatch` tests `hosts_lane`, not `hub_serving`.
`lane enqueue|cancel|move|hold|release|run` refuse with the same text: the queue file is local to the host.

**Each machine's lane job.** One job file, the same on every machine: `sd-ship lane run --hosted`.
`--hosted` replaces `--satellite-only`, so the flag count does not grow.
It lists the `repo` rows this machine hosts and runs `lane run` for each, one after another.
Each repository keeps its own runner lock; a held lock skips that repository and never waits.
The runner reads `lane_host` again before each claim. A move stops it at the next item, never mid-merge.

**The host gates and merges.** A host's `lane run` is today's hub `lane run`:
`prepare --catch-up`, its own `sd-check` or receipt reuse, then `merge --manual`.
No receipt crosses a machine, so no trust rule, no offload view and no pack digest compare.

## What retires

Enumerate again with a repo-wide grep before each deletion. `implement.md` gives the order.

| # | Mechanism | Pack files | System files |
| --- | --- | --- | --- |
| 1 | Lane requests and intake | `bin/sd_lane.py`: `request`, `requests`, `intake`, `take_in`, `malformed`, `claimable`, `acknowledges`, `write_outcome`, `REQUEST_PREFIX`, `REFUSAL_ACTIONS`; the `lane request` parser; `tests/test_sd_lane_requests.py` | none |
| 2 | Satellite-only runs and satellite entries | `bin/sd_lane.py`: `--satellite-only`, `SATELLITE`, `process_satellite`, `satellite_merge_argv`, `handed_back`, `hand_merge`, `note_hand_back`, `LOCK_RETRIES`, `refuse_on_satellite` | `local-cron-jobs/examples/satellite-lane-run.job`; each `satellite-lane-<repo>.job` in the config folder |
| 3 | `merge --satellite-gate` and the trust rule | `bin/sd-ship`: the flag, the offload mode read, `satellite_status`; `bin/sd_local_gate.py`: `HAND_BACK`, `SATELLITE_REFUSALS`, `satellite_refusal`, `offload_status_inputs`; `tests/test_sd_satellite_merge.py` | none |
| 4 | Offload receipts and the offload environment | `bin/sd_gate_receipts.py`: `sd-gate-offload:v1:` rows, `offload_view`, `offload_differences`, `offload_miss`, `offload_environment`, `offload_run`, `offload_pins`, `satellite_identity`; `tests/test_sd_gate_offload_rows.py` | none |
| 5 | Pack-digest publish and compare | `bin/sd_lane.py`: `publish_pack` and its two calls; `bin/sd_gate_receipts.py`: `PACK_PREFIX` and the satellite's early warning | none |
| 6 | The opt-in column | `bin/sd_lib.py`: `repo_satellite_gate`, `SATELLITE_GATE_MODES` | `sd_db/repos.py`: `set_satellite_gate`, `repo_satellite_gate`; `sd_db/writes.py` parameter; `sd-db.sh repo satellite-gate`; a migration that drops `repo.satellite_gate` |
| 7 | Prose | `WORKFLOW.md` satellite steps; `docs/coding-to-release.md`; `docs/work/2026-10-05-satellite-gate-offload/` to `archive/`, superseded | `local-sd-db/README.md` "Satellite gate offload" |

What stays: the hub and its served database, the lock-free `prepare`,
same-machine gate receipts and their reuse (sd:2586), `sd-ship hold`, and the staleness alarm (sd:2918).

## Moving a lane

1. On the dashboard, Management, the repository's row: Move lane, then pick `build-2`.
   Or from any machine: `sd-db.sh repo lane-host <path> build-2`. Both show `before: hub, after: build-2`.
2. The old host's running entry, if any, finishes. Its runner reads the setting before the next claim and stops.
3. On the old host, `sd-ship lane list` shows the entries still pending; cancel each one there.
4. On the new host, create a worktree on each item's pushed branch and run `sd-ship lane enqueue` for it.

An in-flight pull request loses nothing. Its `ship:` row is in the hub database, and its pull request is on GitHub.
The new host's `prepare --catch-up` gates again on its own machine. The cost is one extra gate run.
Two hosts can overlap for one entry: the old host still merges while the new host prepares.
Branch protection's up-to-date rule stops a stale merge. No lease covers that window; the cost is time.

## Tests (fail first)

- Setter: sets, returns before, writes `NULL` for `hub`, refuses an unregistered path and `Build_2`.
- Dashboard route: `/api/repos/lane-host` moves the row, refuses a stale `before`, and Undo restores it.
- `hosts_lane`: `NULL` on the hub is true; `NULL` on a satellite is false; a match on a satellite is true;
  a column-less `sd_db` and an unmatched remote read `NULL`.
- `repository_lock` on a non-host raises `lane_elsewhere`; the text names the dashboard control before the command.
- `repository_lock` on a satellite host takes the local lock; today it raises `HubOnly`.
- `sd-ship merge` on a non-host refuses before any row changes; a no-item verb refuses the same way.
- `sd-ship merge` on a satellite host merges (fake GitHub).
- `prepare` on the hub, for a repository hosted elsewhere, runs lock-free and saves under the revision check.
- `lane enqueue` and `lane run` on a non-host refuse `lane_elsewhere`.
- `lane run --hosted` runs only the hosted repositories, in order, and skips one whose runner lock is held.
- A moved lane: the runner finishes its running entry and claims no next entry for that repository.
- After the retirements: `lane request` and `merge --satellite-gate` are unknown arguments.

## Decisions taken

The operator accepted these on 2026-10-08:

1. The host name is `hostname -s` lower-cased. The cron-jobs folders use it, and it needs no Tailscale.
2. The setting limits every verb that takes the repository lock, not only `merge`: the lock lives on the host.
3. A move transfers no queue entries. The operator cancels on the old host and enqueues again on the new one.
4. The offload environment filter retires. The sd:2936 pinned tools stay only if a grep finds a caller other than `offload_pins`.
5. The column, setter, verb, dashboard control and lock change land in the system repository first; sd:2997 moves them later.
6. The dashboard is the primary surface: the refusal names its control first, the command second.

Not in scope: the dashboard shows each repository's host, not the queue file on a satellite host.
