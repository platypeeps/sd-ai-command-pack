---
title: A satellite-owned lane keeps merging while the hub is down or on another build
created: 2026-10-14
item: sd:4188
---

# Design — satellite-lane

Status: agreed 2026-10-14 (three open questions answered); build starts after sd:4046 and sd:4184 land and a day shows which stalls remain (operator, 2026-10-14).
Builds on sd:3003 (`repo.lane_host`), sd:3282 (the queue in the hub database), sd:3340 (held review on disk), sd:4044 (fence) and sd:4012 (promote).

## Problem

A lane run touches the hub database at every step, so a satellite lane stalls when the hub is down or refuses its build (sd:4046 note: a 15-minute stall).
The hub accesses a run makes:

- **Queue:** every lane verb is one `BEGIN IMMEDIATE` on `state` rows keyed `lane:v1:<repo>:<id>`; the runner writes claim, renew, advance, finish, put-back, requeue and reclaim; `host_check` and `ship._owner` read `repo.lane_host`.
- **Receipts:** `ship.save` writes `ship:<sha>` receipts (review history, Copilot requests, closing owed and paid); gate pass receipts (`bin/sd_gate_receipts.py`) go to the hub too and are bound to the machine.
- **Item close and notes:** `progress.deliver_work`, `workflow.change_status`, `ship.note_merge`, the demotion note and the land and followup notes (`bin/sd task note`).
- **Reads:** `ship.identity`, item state, the claim check, acceptance and waive rows (sd:3704), `refuse_unclosable`, `manual_merge_guard`, `repo.runner_merge`, `repo.ci`, the fleet settings `copilot_review` and `fleet_owners`, `check_item` at enqueue.
- **No hub access:** gate slots (machine-local flocks), logs, held reviews and the runner lock.

The dashboard Queue page runs `sd-ship lane list` on the hub and edits through `lane move|hold|release|cancel|retry`.
Gap: `repos.set_lane_host` is hub-only and refuses while the lane runs elsewhere (`lib/sd_db/repos.py`, sd:3003 part 2), so a lane cannot move off a satellite today, alive or dead.

## Approach

1. **Owner.** A migration adds `repo.lane_local` (0 or 1) and `repo.lane_epoch`. `lane_local=1` with `lane_host=<satellite>` is the single-owner claim; refused while `lane_host` is the hub. Every move bumps the epoch by compare-and-set on host and epoch. The hub refuses a lane run, a ship lock or a replayed queue op from another host or epoch.
2. **Local lane database.** The owner keeps `$XDG_STATE_HOME/sd/lane.db`, an ordinary `sd_db` file at its own build, selected by one environment override in `database.default_path`; prepare and merge code stays as is. It holds the queue of owned repos, ship and gate receipts, and a seed: the repo rows, the fleet settings, the item, note and assignment rows of each queued item and each item it closes, and every repository-wide ownership witness `manual_merge_guard` reads: assignments across the repo's clones, unreleased `runner_run` and `runner_lease` rows. While a repo is local-mode the hub refuses new assignments and runner leases for it, so no competing owner appears offline. The seed refreshes at enqueue and at each run start that reaches a hub on the same build.
3. **Outbox**, written inside the local transaction. In local mode each write site inserts its op into an `outbox` table of `lane.db` in the same transaction as the write, so a rollback drops both. The replay reads committed ops from that table; no file journal, so there is no export step to interrupt. Each op is `{host, epoch, seq, op, args}`; six ops: `state_append` (only `lane:v1:<owned>`, `ship:` and `lane-heartbeat:v1:` keys), `note`, `deliver`, `status`, `note_merge` (one composite op: marker note, `verified` row under `code-delivery:<item>:<commit>`, written in one transaction; its nested note hook is suppressed), `lane_move`. Gate receipts stay local.
4. **Replay.** A new `serve` frame `apply_ops` with handshake `{protocol, ops_version}`, not the build digest. The hub runs each op through its own library functions, so a build mismatch does not matter for an `ops_version` it knows. It refuses when the fence `role()` refuses. A `lane-applied:v1:<host>` high-water row, written in the op's transaction, makes replay idempotent. The mark means "durably handled": an op the hub refuses (a cancelled item, an assignment guard) records a terminal refusal with its alert and note in the same transaction and the mark advances, so one refusal never blocks later ops. `lane_move` replays through a refactor of `set_lane_host` that takes the replay transaction and holds the ship flock until ownership and mark commit together. The reply carries the mark, pending dashboard edits for owned repos and the time of the hub's newest verified backup. The runner replays before each claim and after each entry.
5. **Edits from other machines.** For a local-mode repo the hub's lane verbs write `lane-edit:v1:<repo>:<ulid>` requests with the revision the caller read; the owner applies them at the next item boundary under its revision check and reports the result as `state_append`.
6. **Offline lease and merge deadline.** Each contact sets `lease_until = now + OFFLINE_MAX` locally and in the hub heartbeat. Past the lease the owner claims nothing new and starts no GitHub merge; a merge call already sent gets `MERGE_DEADLINE` (10 minutes) and the runner checks the lease again just before it. Hub-side epochs cannot fence an offline host's GitHub merge, so ownership moves only once the old owner is confirmed stopped, or after `lease_until + MERGE_DEADLINE` has passed.

While the hub is down: enqueue from another machine, enqueue of an unseeded item, dashboard edits (they wait as requests), seed refresh and any claim past the lease all block. A merge closes the item locally; the hub's `deliver_work` re-checks at replay, and a refusal becomes a lane alert and a note while the merge stands.
The hub's `lane list` shows mirror rows plus one line per owned repo: owner, last contact, outbox depth, oldest unsent op, lease end. Staleness is shown, never enforced.

Rejected:
- **Fix only build churn** (sd:4046, sd:4184): cheaper, removes most stalls, does nothing for a hub that is down.
- **Replicate SQL rows:** schema-bound, so it breaks across the build mismatch it must survive, and it skips the hub's own checks.
- **Hub authoritative, owner a mirror, merge on reconnect:** during a mismatch both sides would edit the queue; one writer plus edit requests needs no merge logic.

## Non-goals

- Two satellites owning one lane, or failing a lane over automatically.
- Lanes on the hub: they keep today's path.
- Replacing sd:4046 or sd:4184; build churn still needs its own fix.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| claim offline | local queue row | lease passed, no contact | claim nothing; a running merge finishes | lease clock in the past: no claim |
| merge offline | GitHub merge; local close; `deliver` op | hub down | replay on contact; `deliver_work` is idempotent | hub killed mid-run; replay closes the item once |
| replay | op N applied, reply lost | connection drop | resend from the hub mark; op N skipped | reply dropped after commit: one note |
| replay | none | hub `ops_version` unknown | hold the outbox; report "hub too old for outbox v" | older `ops_version` refuses; outbox kept |
| replay | none | fence `elsewhere` | hold; retry against the new hub | `role()` stub `elsewhere`: nothing applied |
| replay | none | op epoch differs from the hub's | facts apply; queue ops go to `lane-orphan:v1`; runner stops | old owner after `--owner-dead` |
| replay after restore | hub mark below the owner's acked seq | hub restored from backup | rewind; replay retained ops | older database restored; ops reapplied once |
| restore past retention | acked ops lost on the hub | op pruned before the restore | gap hold; operator re-delivers from GitHub per item | prune then restore: `outbox_gap` |
| promote (sd:4012) | hub role moves | promoted hub is behind | as restore; if it is the owner, drain into local first | promote the owner host fixture |
| dashboard edit | `lane-edit` row | owner unreachable | waits; applied at the next boundary under its revision | stale revision refused and mirrored |
| hand-over | `lane_host`, `lane_epoch` | outbox will not drain | refuse; the lane stays put | hub down: hand-over refuses |
| write in local mode | local row and outbox op | transaction rolls back | both vanish; nothing replays | rollback after the op insert: outbox empty |
| replay | none on the hub | hub refuses the op | terminal refusal, alert and note recorded; mark advances | cancelled item: refusal row, next op applies |
| dead-owner move | `lane_host`, `lane_epoch` | old owner offline, mid-merge | move waits for lease plus `MERGE_DEADLINE` unless the stop is confirmed | old owner merging at lease end: move refused until the deadline |
| seed | ownership witnesses | another owner granted offline | hub refuses new assignments and leases for a local-mode repo | assignment on the hub for a local-mode repo: refused |
| seed | local item rows | item edited on the hub during a mismatch | merge uses the old seed; the hub's `deliver` refusal becomes an alert | cancel on the hub, merge offline: alert |

An acked op is pruned only when the hub reports a verified backup taken after its ack.

## Slices

- **S1 (M) ownership:** migration, compare-and-set `set_lane_host` with epoch that also runs inside a caller's transaction, `sd-ship lane hand-over --to HOST`, `sd-db repo lane-host PATH HOST --owner-dead`, epoch checks in `ship._owner` and `host_check`. Leaves: lanes movable, live or dead owner; no local mode yet.
- **S2 (L) local lane database:** `default_path` override, seed and refresh, local queue, runner switch; only when `lane_local=1`.
- **S3 (M) outbox:** the `outbox` table and hooks in the write transaction at `ship.save`, lane store, `add_note`, `change_status`, `deliver_work`, `note_merge`; absorbs sd:4184's local fault record.
- **S4 (M/L) replay:** `apply_ops`, version-tolerant handshake, fence and epoch checks, high-water row, backup time, edits in the reply.
- **S5 (M) hub surfaces:** `lane-edit` requests, the staleness line, the Queue page badge (system repo).
- **S6 (S) restore and failover:** rewind to the hub mark, gap hold, pruning, "drain the outbox first" in the promote runbook.

Hand-over: the live owner takes the runner lock and ship flock, drains the outbox (the hub must answer), then sends `lane_move`; the new owner seeds from the hub mirror and pending entries keep their order.
A dead owner: the hub moves the lane only after `lease_until + MERGE_DEADLINE` from the last heartbeat; `--owner-dead` shortens that only when the operator confirms the old host is stopped (powered off or its runner unloaded), never on a guess. Running entries go back to pending in prepare and fail in merge (the reclaim rule). A returning old owner sees the epoch mismatch at first contact and stops; its `deliver` and `note` ops still apply, its queue ops land in `lane-orphan:v1` for the operator.

## Acceptance criteria

- [ ] With the hub's `serve` stopped, a local-mode satellite lane merges a queued item; on restart one replay closes the item on the hub once and `lane list` on the hub shows outbox depth 0.
- [ ] With the hub one build ahead, the same replay applies (handshake on `ops_version` only).
- [ ] A dead-owner move waits for the lease plus `MERGE_DEADLINE` (or a confirmed stop); the old owner's next contact stops its runner and files its queue ops under `lane-orphan:v1`.
- [ ] Every failure-table row has its test, each failing before its code.

## Risks

- Decided (operator, 2026-10-14): the owner may merge an item whose seed is up to 24 h old; past that it prepares and reviews but merges nothing.
- Decided: `OFFLINE_MAX` is 12 h, plus `MERGE_DEADLINE` of 10 minutes for a dead-owner move without a confirmed stop.
- Decided: dashboard edits while the owner is unreachable are stored as pending requests, shown "pending at owner", and applied or refused at reconnect.
- Accepted: the hub's view of an owned lane lags by the outbox depth; it is shown, not enforced.
- Accepted: a merge the hub would have refused (cancelled during a mismatch) stands; GitHub is the fact, the alert asks the operator.
- Gate pass receipts stay bound to the owner's machine and head; they never replay.
