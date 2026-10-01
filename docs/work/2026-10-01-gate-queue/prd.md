---
title: One machine-wide queue for local gates
created: 2026-10-01
branch: feat/gate-queue-2262
item: sd:2262
---
# PRD — gate queue

## Problem

On 2026-10-01 about 14 gates from three sessions waited at once. Each session
ran its own copy of one load rule: start `make check` only when load1 is below
40 and no other `make check` runs, checked twice 45 s apart. When load fell to
31, several waiters saw the same quiet moment. Five gates of one repository
and one of another started within 3 minutes, and load went back to about 125.
Under that load, runner timing tests failed (sd:2333), and one merge needed a
retry.

Two faults caused this:

- **A check-then-start race.** Each waiter read the load, then started. Nothing
  made the read and the start one step, so many waiters passed one read.
- **No order.** A waiter that started to wait first had no better chance to
  start first.

The sd:1996 gate slots (`bin/sd_gate_slots.py`) cap how many gates run. They
do not order the waiters, and they read no load. The hand rule exists because
of these two gaps.

## Requirements

1. One waiting order on the machine. The first waiter to queue is the first to
   start.
2. Admission is atomic. Two waiters can never both take the last free place,
   and two waiters can never both pass one load reading.
3. Admission reads a load condition. The condition is configurable, and its
   default matches the hand rule.
4. A small command waits for a place, runs a command, and releases the place
   when the command ends. It releases on a crash or a signal too.
5. A place that a dead process holds is free again without operator action.
6. A command shows the queue: who holds a place, who waits, and since when.
7. A slot count of 1 is possible, so that heavy gates run one at a time.
8. `sd-check`, `sd-ship` (through `sd-check`) and the pack's own
   `run-tests.sh` use the same queue. There is one mechanism, not two.

## Acceptance criteria

- [x] N waiters that start at once never run more than the slot count at the
      same time; a test with 5 waiters on 2 slots and on 1 slot shows this.
- [x] Waiters start in the order they queued; a test queues waiters one by one
      on 1 slot and reads the start order.
- [x] With load1 at or above the limit, no waiter starts; with load1 below the
      limit but load5 at or above it, the head starts only after load1 stays
      below the limit for the settle time.
- [x] Two admissions are at least the settle time apart.
- [x] `sd gate run -- CMD` exits with CMD's code and frees its place; a holder
      killed with SIGKILL frees its place, and a dead waiter's ticket goes away.
- [x] `sd gate status` names each holder and each waiter, with its place and
      the time it started to hold or wait; `--json` gives the same data.
- [x] `SD_GATE_SLOTS=1` runs one gate at a time.

## Settled here

- **Default load limit: 2.5 times the cores.** That is 40 on a 16-core machine,
  the hand rule's number. `sd.gate_load_max` sets another limit; `0` turns the
  condition off. `SD_GATE_LOAD_MAX` overrides it for one run.
- **Default settle time: 45 s.** `sd.gate_settle_seconds` and
  `SD_GATE_SETTLE_SECONDS` set it; `0` turns it off. It has two uses: the
  least time between two admissions, and how long load1 must stay low when
  load5 is not yet low. An idle machine, where load5 is low too, starts the
  head at once.
- **Plain first-in, first-out.** A smaller cap on the head of the queue holds
  back the waiters behind it. That is the cost of a strict order.
- **The command is `sd gate run`, with `sd gate status`.** The same verbs run
  stdlib-only as `python3 bin/sd_gate_slots.py run|status`, which reads only
  the variables and the defaults.
- **Exit codes of `sd gate run`:** the command's own code; 128 plus the signal
  number when a signal ended it; 124 when `--timeout` passed before a place
  came free; 125 when no place was taken for another reason.
- **A gate inside a gate does not queue.** A holder runs its command with
  `SD_GATE_SLOTS=0`, as sd:1996 does.

## Log

- 2026-10-01: three questions went to the operator; the rulings follow.
  - **Default slot count stays a quarter of the cores (4).** The load limit
    and the settle time throttle heavy gates; `sd.gate_slots=1` stays
    available for one gate at a time.
  - **One class, plain first-in, first-out.** Priority classes come only if
    the queue later shows merge gates waiting behind long ones.
  - **The window for older pack copies is accepted.** A checkout that pins an
    older pack (for example through `.sd-pack-rev`) takes slots without
    queueing until its pin moves; the pin bump in system follows this item.

The mechanism and its reasons are in [design.md](design.md). The steps are in
[implement.md](implement.md).
