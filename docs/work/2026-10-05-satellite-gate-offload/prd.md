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
02:33 MDT on 2026-10-05 the hub's load5 read 41.75 with several lanes active. The operator
wants the gates to run on the satellite. The merge stays on the hub's lane.

sd:1335 made the hub's database reachable from a satellite. sd:2679 let a
satellite `sd-ship prepare` bind the pull request and write the `ship:` row
over the wire. The merge is hub-only: it runs under `repository_lock`, a file
on the hub. That decision stays (system repository,
`docs/work/2026-09-22-run-the-framework-from-a-second-machine/design.md`,
section Decision).

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

## Goal

A merge of a satellite-gated item on the hub runs no `sd-check`. The hub
accepts a receipt that the satellite wrote, at the exact head, under a trust
rule that this item states.

## Requirements

R1. A satellite gate pass writes a second receipt, the offload receipt, to the
    hub's database. Its key names the repository by its GitHub slug and the
    head (or the declared tree). It names the satellite.

R2. The offload receipt binds the head, the pack `bin/` digest and the
    `CLAUDE.local.md` digest. It also binds the tree-derived binding fields
    and the satellite's tools, interpreter and environment digest.

R3. The hub's merge gate accepts an offload receipt in place of `sd-check`
    only when every trust-rule clause holds (design.md, "The trust rule"). Any clause that fails refuses the merge. The hub never
    falls back to a run of its own for an entry that the satellite gates.

R4. Acceptance needs an opt-in per repository, default off. A repository that
    did not opt in behaves exactly as today.

R5. The satellite catches up with the base branch before its gate. When the
    base moved after the gate, the hub hands the entry back with a refusal
    whose `next_action` names the satellite's steps. The hub does not catch
    up and gate the entry itself.

R6. The hub refuses an offload receipt from a pack whose `bin/` differs from
    the hub's, and the refusal names both digests.

R7. The satellite posts `sd/local-gate` at the head from the authenticated
    account. The hub requires that status and posts none of its own for an
    accepted offload receipt.

R8. Every refusal names its cause and a `next_action` for the machine that
    must act.

## Acceptance criteria

1. A test drives `sd-ship merge --satellite-gate` on a fixture hub with a
   valid offload receipt and a matching status. No `sd-check` child starts,
   and the merge `PUT` is sent.
2. One test per trust-rule clause: with that clause broken, the merge refuses
   with its own code, and no `sd-check` child starts.
3. With `repo.satellite_gate` unset, `--satellite-gate` refuses as not opted
   in. Without the flag the merge path is byte-for-byte today's: the existing
   suites pass unchanged.
4. A lane entry enqueued with `--satellite` whose base moved ends
   `handed_back`. The lane runs no prepare, no catch-up and no speculative gate
   for it.
5. End to end on a fixture: a satellite home with `hub.json` names a scratch
   `sd_db.serve --loopback`. `sd gate check --offload` writes both rows and
   posts the status to the suite's GitHub double. A hub-side
   `sd-ship merge --satellite-gate` then merges with no gate run.

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
- **Multi-operator access.** One login on both machines.

## Not verified

- Whether a hub `sd-ship prepare` at a head that a satellite already
  prepared runs `sd-review`'s gate again. The design avoids the question: a
  satellite entry skips the hub's prepare. Implement step 1 measures it.
- The load reduction itself. It depends on the share of items built on the
  satellite. Implement step 7 measures the hub's gate count per merged item.
