---
title: Offload gates to an sd satellite; the hub's lane merges on a satellite receipt
created: 2026-10-05
branch: sd2704-satellite-gate-design
item: sd:2704
---
# PRD — satellite gate offload

## Problem

The hub runs the workflow database, the runner, the dashboard and every merge
lane. Under `repo.ci = local` it also runs `make check` for each merge. At
02:33 MDT on 2026-10-05 the hub's load5 read 41.75 with several lanes active.
The operator wants the gates to run on the satellite. The merge stays on the
hub's lane.

sd:1335 made the hub's database reachable from a satellite. sd:2679 let a
satellite `sd-ship prepare` bind the pull request and write the `ship:` row
over the wire. The merge is hub-only: it runs under `repository_lock`, a file
on the hub. That decision stays: see the Decision section of sd:1335's design page,
in the system repository's work item "run the framework from a second machine".

A satellite gate does not help the hub today. The code shows two reasons:

1. **The key is per machine.** `receipt_key` in `bin/sd_gate_receipts.py`
   hashes the absolute git common directory. A satellite `sd gate check`
   already writes its receipt into the hub's database, because the
   satellite's `default_path` is a `HubPath`. The row lands under a key that
   no hub reader computes.
2. **The binding is per machine.** `gate_binding` binds tool paths and bytes,
   the interpreter, and a digest of the whole gate environment. The hub's
   binding never equals the satellite's, so `examine` answers `binding` and
   the merge gate runs the check again.

A third gap is in the handoff. The lane queue is a file on the hub, and
`lane run` drains it and exits. Nothing on a satellite can add an entry to it.

## Goal

A merge of a satellite-gated item on the hub runs no `sd-check`. The hub
accepts a receipt that the satellite wrote, at the exact head, under a trust
rule that this item states. The satellite asks for the merge with a row in the
hub's database, and the hub's lane picks the row up.

## Decisions

Ruled by the operator on 2026-10-05, through the team lead:

- **Q1, the opt-in: a `repo` column.** `repo.satellite_gate`, `off` or
  `accept`, default `off`, set by `sd-db.sh repo satellite-gate`.
- **Q2, the handoff: a request row.** The satellite writes a lane request row
  over the wire, and the hub's `lane run` polls for it. SSH enqueue is not
  used.
- **Q3, the window: 6 hours.** An offload receipt stands for 6 hours under
  either key.

## Requirements

R1. A satellite gate pass writes a second receipt, the offload receipt, to the
    hub's database. Its key names the repository by its GitHub slug and the
    head (or the declared tree). It names the satellite.

R2. The offload receipt binds the head, the pack `bin/` digest and the
    `CLAUDE.local.md` digest. It also binds the tree-derived binding fields
    and the satellite's tools, interpreter and environment digest.

R3. The hub's merge gate accepts an offload receipt in place of `sd-check`
    only when every trust-rule clause holds (design.md, "The trust rule").
    Any clause that fails refuses the merge. The hub never falls back to a run
    of its own for an entry that the satellite gates.

R4. Acceptance needs `repo.satellite_gate = accept` (Decision Q1). A
    repository that did not opt in behaves exactly as today.

R5. The satellite catches up with the base branch before its gate. When the
    base moved after the gate, the hub hands the entry back. The refusal's
    `next_action` names the satellite's steps. The hub does not catch up and
    gate the entry itself.

R6. The hub refuses an offload receipt from a pack whose `bin/` differs from
    the hub's, and the refusal names both digests.

R7. The satellite posts `sd/local-gate` at the head from the authenticated
    account. The hub requires that status and posts none of its own for an
    accepted offload receipt.

R8. Every refusal names its cause and a `next_action` for the machine that
    must act.

R9. A satellite asks for a merge with `sd-ship lane request`, which writes a
    lane request row to the hub's database (Decision Q2). The hub's
    `lane run` takes each valid request for its repository into its queue
    before it claims the next entry. It writes the outcome back to the row and
    notes the item.

R10. Some hub process must run `lane run` for a request to move. A scheduled
     hub job runs it for each opted-in repository; overlapping starts exit at
     once on the runner lock.

## Acceptance criteria

1. A test drives `sd-ship merge --satellite-gate` on a fixture hub with a
   valid offload receipt and a matching status. No `sd-check` child starts,
   and the merge `PUT` is sent.
2. One test per trust-rule clause: with that clause broken, the merge refuses
   with its own code, and no `sd-check` child starts.
3. With `repo.satellite_gate` unset, `--satellite-gate` refuses as not opted
   in. Without the flag the merge path is today's: the existing suites pass
   unchanged.
4. A lane request whose base moved ends `handed_back`, on the queue entry and
   on the request row. The lane runs no prepare, no catch-up and no
   speculative gate for it.
5. Intake: a test per refusal (not opted in, not prepared, head moved, bad
   branch name) leaves no queue entry and writes the reason to the row. A
   second request for a pending item supersedes the first. A request already
   taken in is not taken in twice after a crash between the queue write and
   the row write.
6. End to end on a fixture: a satellite home with `hub.json` names a scratch
   `sd_db.serve --loopback`. `sd gate check` writes both receipt rows,
   `sd-ship prepare` posts the status to the suite's GitHub double, and
   `sd-ship lane request` writes the request row. A hub-side `sd-ship lane run`
   takes it in and merges with no gate run.

## Out of scope

- **Satellite-side merge.** The merge stays under the hub's
  `repository_lock`, as sd:1335 decided.
- **Hub speculation for satellite entries.** The lane's predicted-landing gate
  (sd:2586) runs on the hub, so a satellite entry gets none.
- **Accepting a satellite receipt for the hub's own catch-up head.** A
  tree-keyed receipt could cover it if the satellite gated the predicted
  landing. That is a later row.
- **A hub-attested satellite identity.** `sd_db.serve` admits a peer by
  `tailscale whois`, but it does not stamp rows. design.md says why a
  self-reported name is enough under the sd:1335 Q3 ruling.
- **A long-running lane daemon.** The scheduled job starts `lane run`; the
  runner stays a drain-and-exit process.
- **Multi-operator access.** One login on both machines.

## Not verified

- Whether a hub `sd-ship prepare` at a head that a satellite already
  prepared runs `sd-review`'s gate again. The design avoids the question: a
  satellite entry skips the hub's prepare. Implement step 1 measures it.
- The load reduction itself. It depends on the share of items built on the
  satellite. Implement step 8 measures the hub's gate count per merged item.
