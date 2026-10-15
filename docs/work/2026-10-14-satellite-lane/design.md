---
title: A satellite-owned lane keeps merging while the hub is down or on another build
created: 2026-10-14
item: sd:4188
---

# Design — satellite-lane

Status: agreed 2026-10-14 (three open questions answered); revised the same day after lane review: the lane moves only once the old owner is confirmed stopped, never on a timeout (lead's ruling on sd:4188). Build starts after sd:4046 and sd:4184 land and a day shows which stalls remain (operator, 2026-10-14).
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
4. **Replay.** A new `serve` frame `apply_ops` with handshake `{protocol, ops_version}`, not the build digest. The hub runs each op through its own library functions, so a build mismatch does not matter for an `ops_version` it knows. It refuses when the fence `role()` refuses; a `holder` answer does not prove that no promoted hub took over, so the owner keeps acks per hub and compares marks at its next contact (failure table). A `lane-applied:v1:<host>` high-water row, read and written inside each op's transaction, makes replay idempotent: a timed-out request that is still applying and its resend cannot both apply an op. The mark means "durably handled": an op the hub refuses (a cancelled item, an assignment guard) records a terminal refusal with its alert and note in the same transaction and the mark advances, so one refusal never blocks later ops. `lane_move` replays through a refactor of `set_lane_host` that takes the replay transaction and holds the ship flock until ownership and mark commit together. The reply carries the mark, pending dashboard edits for owned repos and the time of the hub's newest verified backup. The runner replays before each claim and after each entry.
5. **Edits from other machines.** For a local-mode repo the hub's lane verbs write `lane-edit:v1:<repo>:<ulid>` requests with the revision the caller read; the owner applies them at the next item boundary under its revision check and reports the result as `state_append`. The hub never applies a request itself because the owner is silent; requests are keyed by repo, so after a move the new owner applies them.
6. **Offline lease, a self-limit only.** Each hub contact sets `lease_until = now + OFFLINE_MAX` locally, bound to the boot token (`operations._boot_token`), and copies it into the hub heartbeat. Past the lease, or after a reboot since the last contact, the owner claims nothing and starts no GitHub merge until a hub contact. `MERGE_DEADLINE` (10 minutes) is the merge call's client timeout; the runner checks the lease just before the call. The lease limits only the owner's own work: a suspended owner can pass its last check and merge later, and a timed-out call can still land on GitHub. So no party reads an elapsed lease, a missed heartbeat or a timeout as proof that the owner stopped; the hub shows them and acts on none.
7. **The lane moves only on a confirmed stop.** Hub epochs fence hub writes, not an offline host's GitHub merge, so ownership moves only once the old owner's runner is proven stopped: (a) its relinquish record reached the hub (hand-over, below); (b) the old machine's session confirms that hand-over wrote its relinquish record there although the hub did not answer; or (c) the operator confirms the old host is shut down, not asleep or unreachable, and the reboot rule in point 6 keeps it from merging when it returns. No timeout transfers a lane.

While the hub is down: enqueue from another machine, enqueue of an unseeded item, dashboard edits (they wait as requests), seed refresh and any claim past the lease or after a reboot all block. A merge closes the item locally; the hub's `deliver_work` re-checks at replay, and a refusal becomes a lane alert and a note while the merge stands.
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
| claim offline | local queue row | lease passed, or a reboot since the last contact | claim nothing and start no merge until a hub contact; a merge already sent finishes | lease clock in the past: no claim; boot token changed with the hub down: no claim |
| merge offline | GitHub merge; local close; `deliver` op | hub down | replay on contact; `deliver_work` is idempotent | hub killed mid-run; replay closes the item once |
| merge call | GitHub merge | client timeout (`MERGE_DEADLINE`) | result unknown, never re-sent: read the PR; merged closes it, open or unreadable fails the entry (the reclaim rule) | timed-out stub that lands: item closes once, one merge call |
| merge after the lease | GitHub merge | owner suspended after its last lease check | the merge stands as the owner's; no move happened, since none happens without a confirmed stop | owner silent past lease plus 10 minutes: hand-over and `--owner-dead` without proof refuse |
| replay | op N applied, reply lost | connection drop | resend from the hub mark; op N skipped | reply dropped after commit: one note |
| replay | op N applied | owner's request timed out while the hub still applies it; the owner resends | mark read and written inside each op's transaction; each op applies once | two concurrent replays of one outbox: one note per op |
| replay | ops acked on a hub | that hub was demoted, but its fence still answered `holder` | acks count per hub; the promoted hub's lower mark rewinds the replay, or holds on a gap if pruned | ack on a demoted hub, then contact the promoted one: ops reapplied once |
| replay | none | hub `ops_version` unknown | hold the outbox; report "hub too old for outbox v" | older `ops_version` refuses; outbox kept |
| replay | none | fence `elsewhere` | hold; retry against the new hub | `role()` stub `elsewhere`: nothing applied |
| replay | none | op epoch differs from the hub's | facts apply; queue ops go to `lane-orphan:v1`; runner stops | old owner after `--owner-dead` |
| replay after restore | hub mark below the owner's acked seq | hub restored from backup | rewind; replay retained ops | older database restored; ops reapplied once |
| restore past retention | acked ops lost on the hub | op pruned before the restore | gap hold; operator re-delivers from GitHub per item | prune then restore: `outbox_gap` |
| promote (sd:4012) | hub role moves | promoted hub is behind | as restore; if it is the owner, drain into local first | promote the owner host fixture |
| dashboard edit | `lane-edit` row | owner unreachable for hours | waits; the hub never applies it on a timeout; applied at the next boundary under its revision, by the new owner after a move | stale revision refused and mirrored; owner silent a day: request still pending |
| hand-over | relinquish record | hub does not answer, so the outbox will not drain | record kept, old runner stays stopped; the move finishes at the next contact, or by `--owner-dead` with proof (b) | hub down: record kept, no claim, `lane_host` unchanged |
| hand-over | relinquish record | process killed between the record and the drain | the record blocks the runner; the next run resumes the drain, then the move | kill after the record: next run drains and moves |
| hand-over | `lane_host`, `lane_epoch` | reply to `lane_move` lost after the hub commits | the record stays; the next contact reads the epoch: moved drops ownership, unchanged resends the compare-and-set | reply dropped after commit: old owner claims nothing, then drops ownership |
| write in local mode | local row and outbox op | transaction rolls back | both vanish; nothing replays | rollback after the op insert: outbox empty |
| replay | none on the hub | hub refuses the op | terminal refusal, alert and note recorded; mark advances | cancelled item: refusal row, next op applies |
| dead-owner move | `lane_host`, `lane_epoch` | old owner offline, maybe mid-merge or asleep | refuse until a stop is confirmed (proof b or c); no elapsed time moves it; the note names who confirmed what | heartbeat a day old, no proof: refused; proof given: moved |
| owner returns after shutdown | none on the hub | it boots while the hub is unreachable | the reboot voided its lease: it claims and merges nothing until contact, then stops on the epoch | boot token changed, hub down: no claim; contact: runner stops |
| reclaim | running entry | old owner's claim `lease_until` passed | no reclaim on claim age in local mode: the same-machine rule (lock free, pid gone) or a confirmed-stop move; the hub never reclaims a mirror row | stale `lease_until` from another host, no move: entry stays running |
| seed | ownership witnesses | another owner granted offline | hub refuses new assignments and leases for a local-mode repo | assignment on the hub for a local-mode repo: refused |
| seed | local item rows | item edited on the hub during a mismatch | merge uses the old seed; the hub's `deliver` refusal becomes an alert | cancel on the hub, merge offline: alert |

An acked op is pruned only when the hub reports a verified backup taken after its ack.

## Slices

- **S1 (M) ownership:** migration, compare-and-set `set_lane_host` with epoch that also runs inside a caller's transaction, `sd-ship lane hand-over --to HOST` with its relinquish record, `sd-db repo lane-host PATH HOST --owner-dead` that requires and records a confirmed stop, epoch checks in `ship._owner` and `host_check`. Leaves: lanes movable, live or dead owner; no local mode yet.
- **S2 (L) local lane database:** `default_path` override, seed and refresh, local queue, the boot-bound lease, runner switch; only when `lane_local=1`.
- **S3 (M) outbox:** the `outbox` table and hooks in the write transaction at `ship.save`, lane store, `add_note`, `change_status`, `deliver_work`, `note_merge`; absorbs sd:4184's local fault record.
- **S4 (M/L) replay:** `apply_ops`, version-tolerant handshake, fence and epoch checks, high-water row, backup time, edits in the reply.
- **S5 (M) hub surfaces:** `lane-edit` requests, the staleness line, the Queue page badge (system repo).
- **S6 (S) restore and failover:** rewind to the hub mark, gap hold, pruning, "drain the outbox first" in the promote runbook.

Hand-over moves state in three steps, each resumed by the next run: (1) the live owner takes the runner lock and ship flock and commits a relinquish record at its epoch to `lane.db`; from then its runner claims and merges nothing, whatever the clocks say. (2) It drains the outbox, the relinquish record last (the hub must answer). (3) It sends `lane_move`, a compare-and-set on host and epoch. Only a hub answer clears the record: the epoch moved (drop ownership) or the move was refused with the epoch still its own (run on). The new owner seeds from the hub mirror and pending entries keep their order.
A dead owner: `sd-db repo lane-host PATH HOST --owner-dead` moves the lane only with proof (b) or (c) of Approach point 7, and records who confirmed what in a lane note; its refusal lists the accepted proofs. No time since the last heartbeat replaces that proof. The old owner's running entries go back to pending in prepare and fail in merge (the reclaim rule) because the stop is confirmed, not because a claim's `lease_until` passed. A returning old owner (a wrong confirmation) sees the epoch mismatch at first contact and stops; its `deliver` and `note` ops still apply, its queue ops land in `lane-orphan:v1` for the operator.

## Acceptance criteria

- [ ] With the hub's `serve` stopped, a local-mode satellite lane merges a queued item; on restart one replay closes the item on the hub once and `lane list` on the hub shows outbox depth 0.
- [ ] With the hub one build ahead, the same replay applies (handshake on `ops_version` only).
- [ ] A dead-owner move refuses without a confirmed stop, however old the last heartbeat; with one it moves, and the old owner's next contact stops its runner and files its queue ops under `lane-orphan:v1`.
- [ ] After a reboot, a local-mode owner claims and merges nothing until a hub contact.
- [ ] Every failure-table row has its test, each failing before its code.

## Risks

- Decided (operator, 2026-10-14): the owner may merge an item whose seed is up to 24 h old; past that it prepares and reviews but merges nothing.
- Decided: `OFFLINE_MAX` is 12 h, plus `MERGE_DEADLINE` of 10 minutes. Ruled after lane review (lead, sd:4188): neither moves a lane; the lease limits the owner's own work and the deadline is the merge call's client timeout.
- Accepted: a dead owner's lane stays put until someone confirms the stop, so it stalls meanwhile; GitHub offers no fence, and a timeout is not one.
- Accepted: a wrong confirmation (a host reported shut down that was only asleep) can let two owners merge until the old one's next contact; the move's note names who confirmed it.
- Decided: dashboard edits while the owner is unreachable are stored as pending requests, shown "pending at owner", and applied or refused at reconnect.
- Accepted: the hub's view of an owned lane lags by the outbox depth; it is shown, not enforced.
- Accepted: a merge the hub would have refused (cancelled during a mismatch) stands; GitHub is the fact, the alert asks the operator.
- Gate pass receipts stay bound to the owner's machine and head; they never replay.
