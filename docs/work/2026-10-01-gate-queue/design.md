# Design — gate queue

## Build on the slots, add a queue in front

The sd:1996 slots stay as they are. A slot is a kernel `flock` on
`<dir>/slot.N.lock`, and the kernel frees it when its holder dies. This item
adds three files in the same directory:

| Path | Holds |
|---|---|
| `queue.lock` | the admission lock: one short `flock` around every queue read and change |
| `queue/<seq>.ticket` | one waiter: its sequence number, pid, label, working directory and start time |
| `queue.state` | the next sequence number, the last admission time, and the load record |

A ticket is created and locked by its waiter while the waiter holds
`queue.lock`. The waiter keeps a `flock` on its own ticket while it waits. The
kernel drops that lock when the waiter dies.

## Admission is one step under one lock

A waiter polls. Each poll takes `queue.lock`, then does all of this before it
lets go:

1. Read `queue.state`.
2. Remove each ticket whose `flock` this process can take: its waiter is dead.
3. Stop here unless this waiter holds the lowest live sequence number.
4. Sample the load (`os.getloadavg`) under this waiter's own rule.
5. Stop here unless the load condition holds (below).
6. Try each slot lock. On a taken slot, write the admission time, remove the
   own ticket, and return the slot.

Every admission runs under `queue.lock`, so two waiters never see the same
free slot or the same load reading as theirs. That closes the
check-then-start race of the hand rule.

Removing a dead ticket is safe, and this is why. The sd:1195 review rejected two
earlier designs because a waiter judged a holder dead and deleted its file.
Here a ticket is created and locked under `queue.lock`, and it is removed only
under `queue.lock` by a process that holds its `flock`. A live waiter holds
that `flock`, so no other process can take it. A dead waiter's ticket cannot
come back to life. Tickets are opened without inheritance, so no child keeps
one alive.

## Load condition

Two settings, each read from a variable first, then from the machine setting,
then from a default:

| Setting | Variable | Default | `0` |
|---|---|---|---|
| `sd.gate_load_max` | `SD_GATE_LOAD_MAX` | 2.5 times the cores | no load condition |
| `sd.gate_settle_seconds` | `SD_GATE_SETTLE_SECONDS` | 45 | no settle time |

The head is admitted when all of these hold:

- load1 is below the limit;
- load5 is below the limit, or load1 stayed below it for the settle time;
- the last admission on the machine was at least the settle time ago.

"Stayed below" uses `queue.state`. Only the head's poll records a sample, and
the record names the limit and settle time it was kept under. Callers can run
different rules (a variable overrides the setting for one run), so a waiter
behind the head must not clear or keep the head's record; the review of
2026-10-01 found both cases. A sample under another rule starts the record
again. A sample at or above the limit clears it. A gap between samples longer
than the settle time, or 15 s, starts it again, so an old sample counts for
nothing.

Why load5: load1 is a one-minute average that falls fast. On 2026-10-01 load1
fell to 31 while the machine was still busy. Load5 was well above 40 then, so
the head had to see 45 s of low load1 first. On an idle machine load5 is low,
and the head starts at once.

Why a least time between admissions: load1 lags a new gate by tens of seconds.
Without spacing, the next waiter reads the old, low value and starts too.

## Release on a crash or a signal

`sd gate run` holds the slot lock in its own process and starts the command
in a new process group. It does not pass the lock to the command, as sd:1996
already decided: a daemon that the command starts must not hold a slot for
ever. SIGINT, SIGTERM and SIGHUP go to the command's whole group, and the
runner then waits for the command. When the runner itself dies, the kernel
frees the slot. A command that outlives a SIGKILLed runner keeps running
without a slot; that is the accepted cost.

A waiter that gets a signal before admission dies. Its ticket is unlocked and
the next poll removes it.

## Visibility

A holder writes its pid into `slot.N.lock`, as before, and its label, working
directory and start time into `slot.N.info`. `sd gate status` takes
`queue.lock`, probes each slot, and reads the tickets. It shows an info file
only when its pid matches the pid in the lock file, so a holder that wrote no
info file (the shell helper) never shows an older holder's label.

## Callers

| Caller | How it queues |
|---|---|
| `sd-check` (and `sd-ship` through it) | `sd_gate_slots.acquire`, now through the queue |
| `.github/scripts/run-tests.sh` | the `wait` helper, now through the queue |
| a hand-written waiter, any repository | `sd gate run -- make check` |

The shell helper reads the same rule as `sd-check`: `machine_rule` reads
`sd.gate_load_max` and `sd.gate_settle_seconds` from the machine config with
stdlib only, at the path `sd_lib.machine_config_path` names. A config it cannot
read gives the defaults with a warning, since load control never fails a gate.

## Decisions (operator, 2026-10-01)

- The default slot count stays a quarter of the cores. The load rule spaces
  heavy gates; one gate at a time is `sd.gate_slots=1`.
- The queue has one class. A ticket's order is its sequence number alone.
  A class would order by class first and by sequence second; add one only if
  the queue shows merge gates waiting behind long ones.
- A checkout that pins an older pack takes slots without queueing until its
  pin moves. That window is accepted; the pin bump follows this item.

## Rejected

- **A second, parallel mechanism** (a queue daemon, a socket). It would need a
  supervisor and would not free a crashed holder's place by itself.
- **Blocking `flock` as the queue.** The kernel does not promise first-in,
  first-out to `flock` waiters, and a blocked waiter cannot read the load.
- **The pid in a file as liveness.** A pid can be reused; the `flock` cannot.
