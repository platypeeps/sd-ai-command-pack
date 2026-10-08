---
title: One lane per repository; the machine that runs it is a per-repository setting
created: 2026-10-08
branch: design/lane-host
item: sd:3003
---
# PRD — lane host per repository

## Problem

A satellite gates an item, but only the hub merges it (sd:2704).
The hand-off between the two machines needs request rows, a hub cron job per repository,
`merge --satellite-gate`, offload receipts and a pack digest that must match.
On 2026-10-08 one pull request needed a merge line run by hand, a lane hold to pin the pack, and messages between two sessions.
[design.md](design.md), "Problem", has the evidence.

## Goals

1. Each repository has one lane, and one machine runs it.
2. The operator moves a lane with one action: the dashboard control, or one `sd-db.sh` verb.
3. The lane host gates and merges its own repositories, and writes only to the hub's database.
4. The satellite hand-off retires: lane requests, `--satellite-gate` merges, offload receipts and pack-digest matching.
5. No leases and no hand-off protocol: the setting and the repository lock are the whole mechanism.

## Non-goals

- Moving queue entries between machines on a move.
- A dashboard view of a satellite host's queue file.
- Moving `sd_db` into the pack; sd:2997 does that.

## Acceptance criteria

Each line is a test that fails before the change.

1. `sd-db.sh repo lane-host PATH HOST|hub` sets `repo.lane_host`, prints before and after, and takes no other flag.
2. The verb and the dashboard control refuse an unregistered path and a host name outside `[a-z0-9-]+`.
3. The dashboard's Management page shows each repository's lane host, and its Move lane control changes it through the same setter.
4. The control refuses a stale `before`, and Undo restores the earlier value.
5. A new row and every migrated row read `NULL`, and `NULL` means the hub.
6. On a machine that does not host the repository, `repository_lock` refuses with `lane_elsewhere` and takes no lock.
7. That refusal names the host, then the dashboard control, then the verb.
8. On a satellite that hosts the repository, `sd-ship merge` takes a local lock and merges.
9. On a non-host, `prepare` runs lock-free; `merge`, `reconcile`, `review`, `verify-review`, `adjudicate` and the `lane` queue verbs refuse.
10. `sd-ship lane run --hosted` runs only the repositories this machine hosts, and never waits on a held lock.
11. After a move, the old host finishes its running entry and claims no other entry for that repository.
12. After the retirements, `sd-ship lane request` and `sd-ship merge --satellite-gate` are unknown arguments.
13. After the retirements, `sd-db.sh repo satellite-gate` is gone, and `repo.satellite_gate` is dropped.
