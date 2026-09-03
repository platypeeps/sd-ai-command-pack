---
title: the dashboard's three open gaps — an ack that sticks, a mutation the index can count, and a bind that admits it failed
status: planning
created: 2026-09-02
---

# PRD — the dashboard's three open gaps

## Problem

The `artifacts-as-product` item closed on 2026-09-02 with the dashboard built and serving:
`dashboard/server.py` has a `do_POST` behind three guards, `bin/sd-dashboard` has `serve`,
`install` and `index`, and the system dashboard it replaced is gone (`platypeeps/system#190`
deleted the server half). It closed with two things it had named as belonging to a later item
rather than to itself; a third was found on 2026-09-02 by looking at the running service rather
than at the code. All three are open, all three were verified against the working tree or the live
process on 2026-09-02, and between them they make a deletion criterion both unevaluable and
untrustworthy on a date that is now fixed.

**1. A dismissed alert comes back.** `dashboard/now.py:15` states the contract — "**An id is an
ack key** (R11-D20), so it identifies one alert and not one row" — and nothing stores an ack.
`RUN_ALLOWLIST` (`dashboard/actions.py:52`) holds exactly one entry, `index`. There is no ack
producer and no ack consumer, so Now re-renders every row it ranked on the previous poll. The
prior item recorded this at `docs/work/2026-08-29-artifacts-as-product/implement.md:2062-2068` as "a tab-scoped version of the
dead-destination failure R11-D19 was written about," and assigned it to "whichever step builds
the ack store." No step did.

**2. R11-D10's deletion criterion has no counter.** The criterion (`docs/work/2026-08-29-artifacts-as-product/design.md:1528-1532`) is:
sixty days after the 6b swap, if the index shows fewer than ten mutating requests from a tailnet
Host, the write path and its three guards are deleted and the dashboard returns to GET-only.
`do_POST` (`dashboard/server.py:445`) writes no record of having run — it validates, dispatches to
`actions.run`, and returns a body. The index has no table for it. The criterion therefore
evaluates to "no evidence" rather than to a number, which is not the same answer and cannot be
read as one.

**3. The tailnet bind fails silently, and the failure latches.** `bound_addrs`
(`dashboard/server.py:125`) probes `tailscale ip` once and caches the answer in `_ADDRS`
(`dashboard/server.py:122`) for the life of the process. The cache has a good reason, written in
its own docstring: asked twice, the tailnet could come up between the allow-list and the bind, and
the server would bind an address it then answers 403 on. The cost was never written down beside
the reason — the *first* answer is also the *only* answer. `tailnet_addrs`
(`dashboard/server.py:89`) returns an empty list for three different failures (no `tailscale` on
`PATH`, a non-zero exit, output that does not parse as an address), and `serve`
(`dashboard/server.py:532`) treats an empty list as an ordinary start, because loopback bound and
its only fatal case is nothing binding at all. `KeepAlive` (`bin/sd-dashboard:58`) restarts on
exit, and nothing exits. So a probe that comes up empty at startup — launchd racing `tailscaled` at
boot is the ordinary way — leaves the dashboard reachable only from the machine it runs on, for as
long as it runs, with no crash, no error line, and a startup message that reads as success.

The install is what makes this a broken promise rather than a preference: `TAILNET_BIND`
(`bin/sd-dashboard:125`) turns the bind **on** for the installed service and leaves it off for a
hand-run `serve`, on the stated grounds that "installing is asking for the service the system
dashboard provided." The service can then decline to provide it without saying so.

The prior item found this failure *class* and fixed one instance of it. The plist's `PATH` comment
at `bin/sd-dashboard:77-80` says launchd's own `PATH` holds no `tailscale`, so "the tailnet bind
silently does nothing, both of them looking like a quiet dashboard rather than a broken one" — and
sets `PATH` to remove that cause. The empty-probe cause has the identical symptom and was left.

**This gap does not merely sit alongside gap 2; it corrupts it.** R11-D10's criterion counts
mutating requests *from a tailnet Host*. Every period in which the server is silently loopback-only
is a period in which no such request can be made. A counter that ships while the bind can fail this
way measures the bind and reports the result as demand — toward the zero that deletes the write
path. Gap 2's counter is not trustworthy until gap 3 is either fixed or recorded alongside it.

Gap 2 is the second time the same failure has been found in this codebase. R10-D3's 60-day
criterion had the identical shape and was fixed on 2026-09-02 by making `sd-handoff-restore`
append one line per restore to `handoff/loads.jsonl`; its evaluation is now answerable on
2026-11-01. `docs/work/2026-08-29-artifacts-as-product/implement.md:2069-2076` names the repeat in as many words: "a deletion criterion
nobody can evaluate is the failure mode standing rule 1 exists to prevent... It happened twice.
The rule catches a mechanism arriving without a criterion; it does not catch a criterion arriving
without a counter."

All three have one shape: a mechanism that fails by producing nothing, inside a system that reads
nothing as a number. An unacked alert is indistinguishable from a new one, an uncounted request
from an absent one, and an unbound address from an unwanted one.

## Measured state

| Fact | Number | Source |
|---|---|---|
| `dashboard/` total lines | **4,190 against a 4,300 cap — 110 headroom** | `wc -l dashboard/*.py dashboard/*.js` |
| `dashboard/` code lines | **2,206 against a 2,300 cap — 94 headroom** | the tokeniser in `tests/test_loc_caps.py:115-134` |
| `RUN_ALLOWLIST` entries | 1 (`index`) | `dashboard/actions.py:52-58` |
| Mutating requests recorded | 0 — no write site exists | `dashboard/server.py:445-481` |
| `bin/sd-dashboard` verbs | 3 of the design's 5 (`serve`, `install`, `index`) | `bin/sd-dashboard:207-216` |
| 6b swap closed | 2026-09-01 (6b-9) | `docs/work/2026-08-29-artifacts-as-product/implement.md:1504` |
| R11-D10 evaluation date, read literally | **2026-10-31**, against a count of zero | `docs/work/2026-08-29-artifacts-as-product/design.md:1529` + the above |
| Closest precedent's cost | `record_load` + `load_age_seconds` = **59 code lines** | the tokeniser, over `bin/sd-handoff-restore:157-313` |
| Recorded dashboard starts that published loopback alone | **1 of 5** | `~/Library/Logs/com.sven.sd-dashboard.log`, lines 2-10 |
| Tailnet address across those starts | changed, `100.82.165.108` → `100.73.1.43` | the same log, lines 6 and 10 |
| `bin/` lines | 11,147 against a 14,000 cap — **2,853 headroom** | the same tokeniser, over `tracked("bin")` |

`DASHBOARD_CODE_CAP` (`tests/test_loc_caps.py:66`) moves **downward only**, so 94 lines is a
budget this item cannot raise by writing prose or by re-deriving the cap. It is the binding
constraint on gaps 1 and 2, which have to live under `dashboard/`, and any solution for them that
does not fit inside it is not a solution. Gap 3 has an exit the other two do not: `bin/sd-dashboard`
is the CLI in front of the server and charges the `bin/` cap instead
(`tests/test_loc_caps.py:190-201`), where 2,853 lines are free — so where its fix lands is a budget
decision, not only a design one.

The log rows are machine-local evidence from this Mac, not something CI can reproduce. They are
cited for what they establish — that the failure has happened, and more than the address changed —
and the acceptance criteria below ask for a fixture rather than for the log.

## The clock is already running, and that is the urgent half

6b-9 closed on 2026-09-01 (`docs/work/2026-08-29-artifacts-as-product/implement.md:1504`), so a literal reading of R11-D10 makes its
criterion answerable on **2026-10-31** — against a count of zero, because nothing counts. "Fewer
than ten mutating requests" would be satisfied, and the rule would delete a write path the phone
uses daily, on the strength of evidence that was never collected. A criterion that cannot be
evaluated does not fail safe: it fails toward whichever branch a zero happens to select, and here
that branch is deletion.

R10-D3 hit this wall a week ago, and it was resolved on the record by Sven's direction — the sixty
days run **from the counter, not from the item**
(`docs/work/2026-08-29-artifacts-as-product/prd.md`, the R10-D3 close). The same resolution is proposed
here, and it needs saying out loud rather than being inherited quietly, because it moves a date.
Either the criterion is re-dated in this item's `design.md` to sixty days after the counter lands,
or it is evaluated on 2026-10-31 with a documented "no evidence" and the write path survives on
that basis. The first is better; both beat discovering it on the day. What this item may not do is
move the date by silence.

## The tension this item exists to resolve

An ack names one alert. Naming a thing is a parameter, and **R11-D25 decided against parameters**
(`docs/work/2026-08-29-artifacts-as-product/design.md:2255-2280`): an action is a command and not a form, it takes no arguments from the
page, and the write path's load-bearing property is that "nothing a caller sends is interpolated."
R11-D25 rejected ~100 lines of parameter validator against the 159 lines then remaining, for one
tab, before a second caller existed to say what the shape should be.

So the ack cannot be a `RUN_ALLOWLIST` action in the shape actions currently have, and it cannot
be one action per alert, because alert ids are generated per poll from live fleet state. The
three ways out — a typed ack endpoint beside `/api/run` that interpolates nothing because it
writes an opaque id to a store rather than into an argv; a general parameter mechanism; or
deciding that alerts are not dismissible and deleting the R11-D20 contract instead — are a
`design.md` question. This PRD's job is to say that the tension is real, that R11-D25 is the
constraint rather than an obstacle, and that a second caller now exists, which is precisely the
evidence R11-D25 said a parameter mechanism should arrive on.

## Requirements

The `artifacts-as-product` requirements carry unchanged; that item's requirement 6 is the one this
item is mostly about. Specific to this item:

1. Every mutating request that passes the three guards is recorded durably enough to survive a
   restart, with what R11-D10's criterion actually needs: a timestamp and whether the Host was a
   tailnet name. A count that cannot distinguish a tailnet Host from loopback does not answer the
   criterion as written, and — because of gap 3 — a count that cannot distinguish *no demand* from
   *no path* does not answer it either.
2. The record is a byproduct of serving, never a precondition: a failure to write it degrades to a
   missing row, never to a refused or 500'd request. The write path is a security boundary, and a
   counter is not a reason to add a failure mode to it.
3. An acknowledged alert stays acknowledged across polls and across a server restart, keyed by the
   R11-D20 alert id.
4. The write path keeps the property R11-D25 bought: nothing a caller sends reaches an argv.
   An ack id is stored and compared, never interpolated into a command.
5. Each mechanism this item *adds* is new, so standing rule 1 applies to it: a linked incident and
   a deletion criterion that a command can evaluate — and, this time, the counter that makes the
   criterion evaluable ships with the mechanism rather than after it. Gap 3's fix is a repair to an
   existing mechanism and does not attract rule 1 on its own; if `design.md` chooses a shape that is
   itself a new mechanism — a health check, a retry loop, a proxy — rule 1 attaches to that shape.
6. When the tailnet bind is asked for and not achieved, that is visible without reading a log
   file: a start that publishes fewer addresses than were requested is not a successful start. What
   the server does about it — retry, exit for `KeepAlive` to restart, or report and continue — is
   `design.md`'s to choose, but choosing "say nothing" is not available.
7. A tailnet address that changes while the server runs is either picked up or reported. The server
   must not go on publishing an address it no longer holds while refusing the one it does, which is
   what a cached `_ADDRS` produces today.
8. Everything that must live under `dashboard/` fits in its 94 lines of code, or the item
   explicitly proposes what to delete to make room. Raising `DASHBOARD_CODE_CAP` is not available.

   It was 110 when this item opened. The assigned-only change to the tracker views spent sixteen of
   them — a net spend, after deleting one table and its heading and adding a closed disclosure — and
   the number is restated here rather than left at the figure the budget below was first divided against.

   The yardstick for whether 110 is enough, rather than a guess: `record_load`
   (`bin/sd-handoff-restore:157`) and `load_age_seconds` (`bin/sd-handoff-restore:290`)
   are **59 code lines** by the same
   tokeniser — one durable append-only counter, hardened over eight review rounds for concurrent
   writers, torn records and an unparseable timestamp. That is the honest cost of the *first* of
   this item's first mechanism, leaving ~35 for an ack store and its control. `dashboard/app.js`
   charges the same cap, so the dismiss control is inside that number, not beside it. This is
   feasible and it is thin; `design.md` should treat "what do we delete" as a live branch rather
   than a fallback, and the counter may be cheaper here than it was there — a POST handler has no
   second writer racing it the way a SessionStart hook does.

   Gap 3 is deliberately outside that 51: its fix must either be small enough to fit what remains
   after the ack, or live in `bin/sd-dashboard`, which charges `bin/` and its 2,853 free lines. A
   `bound_addrs` re-probe charges the 110; a plist change does not. `design.md` should say which
   cap it is spending before it says what the code does.

## Acceptance criteria

- [ ] A mutating request that passes Host, token and `RUN_ALLOWLIST` leaves exactly one durable
      record; a request refused at any guard leaves none. Verified by pressing the real button on
      the real machine and by a test for each of the four paths.
- [ ] A forced failure of the record write (unwritable store) still returns the action's own
      status to the caller. Verified by a fixture, not by inspection.
- [ ] R11-D10's criterion is answerable by a command that runs against the store and prints a
      number, written in this item's `design.md` the way R10-D3's `wc -l` and `jq` median are
      written in `docs/work/2026-08-29-artifacts-as-product/prd.md`.
- [ ] An alert acknowledged once does not reappear on the next poll or after a server restart;
      an alert whose underlying condition returns after being acked is a decision this item
      records rather than discovers.
- [ ] With the bind requested and `tailscale` unavailable — a stub on `PATH` that exits non-zero,
      and one that prints an unparseable line — the server does what this item chose, verified by
      fixture. "Starts quietly on loopback" is the current behaviour and is the thing being fixed.
- [ ] The command that answers R11-D10 can distinguish *no demand* from *no tailnet path*, or the
      criterion is recorded as not evaluated. A zero from a server nothing could reach is not
      evidence about the write path.
- [ ] `grep` over `dashboard/` shows no caller-supplied value reaching an argv.
- [ ] `dashboard/` stays under both caps, with the PR reporting its own line count against the
      110-line code headroom (R11-D24's convention at `docs/work/2026-08-29-artifacts-as-product/design.md:1330`).
- [ ] Each new mechanism carries an incident and an evaluable deletion criterion, with the
      evaluating command written down at the time the mechanism lands.

## Explicitly out of scope

- **`item set-status` and `export --obsidian`**, the two of five `bin/sd-dashboard` verbs still
  unbuilt. R11-D25 decided status-setting stays in Obsidian, so the intents lane behind
  `item set-status` has no remaining caller; it is not "not yet built," it is undecided again, and
  reopening it needs its own evidence. `export --obsidian` has never had a stated incident.
- **A Suggestions tab.** R11-D22 left it off the backbone tab list until something fills it, and
  `skills/sd-suggest/SKILL.md:50` still says "There is no `bin/sd-suggest` yet."
- **Parameterised actions as a general mechanism**, unless this item's `design.md` concludes the
  ack requires one — in which case it is that decision's subject and is argued there, against
  R11-D25's rejection, on the second-caller evidence R11-D25 named.

## Open questions for `design.md`

1. Does the mutation record share the SQLite index (`dashboard/store.py`) or take the
   `loads.jsonl` shape that R10-D3 already proved? The index is the thing R11-D10's criterion
   names — "the index shows fewer than ten" — but an append-only file is what survived review last
   week, and the criterion's wording is this repo's to correct if the other shape is better.
2. Is an ack permanent, or does it expire when the underlying condition clears and returns? The
   R11-D20 contract says an id identifies one alert; it does not say what happens on recurrence.
3. Where does an ack live so that a `dashboard/` line budget of 110 is enough for the mechanisms
   that have to live there?
4. How many failed probes before the server accepts loopback and says so? A retry that never gives
   up is the crashloop `ThrottleInterval` (`bin/sd-dashboard:69`) was added to bound; giving up on
   the first probe is today's behaviour and is the defect. The answer is a number and a place to
   put it, not a principle.
5. Which of the four shapes, and against which cap: re-probe inside `bound_addrs` on a miss; have
   the plist wait on a network condition before `RunAtLoad`; let `serve` exit non-zero when the bind
   was requested and only loopback bound, so `KeepAlive` plus a 30-second throttle does the
   retrying; or restore a `tailscale serve` proxy to loopback. The last one re-introduces the
   component `platypeeps/system#190` deleted and needs to argue that rather than assume it.

## Planning adversarial review — 2026-09-02

Host lane only; this repository defines no additional lane. Trigger: `prd.md` is new. Every claim
above was checked against the working tree or the prior item's artifacts, not against memory.

- **C-1 — the criterion's clock was left implicit. Blocking. `addressed`.** The draft said the
  criterion "has no counter" without saying when it comes due. 6b-9 closed 2026-09-01, so the
  literal date is 2026-10-31 and the literal answer is a zero that deletes a live write path.
  Evidence: `docs/work/2026-08-29-artifacts-as-product/implement.md:1504`, `docs/work/2026-08-29-artifacts-as-product/design.md:1529`. Owning artifact: this file, new section *The
  clock is already running*.
- **C-2 — the 110-line budget was asserted, never sized. Material. `addressed`.** Evidence:
  the closest precedent is 59 code lines by the same tokeniser
  (`bin/sd-handoff-restore:157-313`), which leaves ~51 for the second mechanism *including* its
  `app.js` control. Owning artifact: this file, requirement 8.
- **C-3 — "verified by pressing the real button" is not reproducible in CI. Minor. `rebutted`.**
  It is paired with per-path fixtures in the same criterion, and this repository's own record
  treats hand-verification as evidence alongside tests, not instead of them
  (`dashboard/actions.py:47`, "Found by pressing it").
- **C-4 — an ack id could be read as reaching an argv, which R11-D25 forbids. Material.
  `addressed` by construction.** Requirement 4 states the id is stored and compared, never
  interpolated, and the acceptance list carries a `grep` that fails if it ever is.
- **C-5 — cross-artifact sweep. `n/a this round`.** This item has one artifact; there is no
  second copy of any figure to drift. Every citation *out* of it was opened and confirmed to say
  what it is quoted as saying. The two figures that will need re-checking when `design.md` lands
  are 110 and 2026-10-31.

## Planning adversarial review, second pass — 2026-09-02, third gap added

Host lane only. Trigger: a third gap was added to a `prd.md` that had already converged once, which
moves counts, budget arithmetic and C-1's argument. C-1 through C-5 above stand; C-1 is
strengthened rather than reopened, because the 2026-10-31 zero can now arrive by two independent
routes — nothing counts, *and* nothing could have been counted.

- **C-6 — gap 3's evidence is machine-local, and "1 of 5" is not a rate. Material. `addressed`.**
  The log lives at `~/Library/Logs/com.sven.sd-dashboard.log`, outside the repository, carries no
  timestamps, and is whatever launchd has appended since the file last existed. It establishes that
  the failure has occurred and that the address has changed; it does not establish how often, and
  this item does not claim to know. The measured-state section now says so, and the acceptance
  criterion asks for a stubbed `tailscale` fixture rather than for the log.
- **C-7 — the observed loopback-only start's cause was inferred, not seen. Material. `addressed` by
  wording.** No timestamps means the boot-order race is a hypothesis about that start, not an
  observation of it. The claim the PRD actually makes is narrower and is provable from the code:
  `tailnet_addrs` (`dashboard/server.py:89`) collapses three distinct failures into one empty list,
  `bound_addrs` (`dashboard/server.py:125`) latches it, and `serve` (`dashboard/server.py:532`)
  reports success. Which of the three fired on that start does not change the defect or the fix.
- **C-8 — gap 3 could be its own item. Material. `rebutted`.** The usual reason to split is budget
  contention, and it does not apply: gap 3's fix can charge `bin/`, which gaps 1 and 2 cannot. The
  reason to keep it is coupling — gap 2 ships a counter whose zero is uninterpretable while gap 3
  stands, so shipping them apart means shipping the counter into a known measurement error.
- **C-9 — requirement 6 could forbid a deliberately Tailscale-less machine. Minor. `addressed` by
  construction.** Requirement 6 constrains *silence*, not the outcome: "report and continue" is
  listed as an allowed answer. Open question 4 owns where the retry stops.
- **C-10 — cross-artifact sweep. `addressed`.** Still one artifact, so the sweep is internal:
  title, heading and opening paragraph re-counted; the yardstick's "two mechanisms" corrected to
  "first mechanism" since 59 lines buys one of three, not one of two; open question 3's "both
  mechanisms" narrowed to the ones that must live under `dashboard/`; C-2's pointer followed
  requirement 6 to requirement 8. Every citation added this pass was opened and read, including the
  two that are prose rather than symbol anchors (`bin/sd-dashboard:77-80`, the log lines).

Implementation is **not** unblocked, and deliberately so: this is a PRD with five open questions
that `design.md` owns. No blocking concern is unresolved.

## Log

- 2026-09-02 created with the two gaps carried from the prior item, both verified against the
  working tree rather than against its prose: `RUN_ALLOWLIST` holds one entry, `do_POST` has no
  write site.
- 2026-09-02 host adversarial review run; C-1 and C-2 changed this file, C-3 rebutted with
  evidence, C-4 addressed by construction.
- 2026-09-02 third gap added: the tailnet bind is probed once and every way it can fail is silent.
  Found by looking at the running service rather than at the code — `lsof` showed one listening
  socket where the installed plist had asked for three. Cleared on the machine with
  `launchctl kickstart -k`, which is why the fix is still open: the defect was cleared, not fixed,
  and the next boot that wins the race brings it back.
- 2026-09-02 second host adversarial review run over the third gap; C-6 and C-7 tightened the
  evidence claims, C-8 rebutted the split, C-9 addressed by construction, C-10 swept the counts and
  the budget arithmetic this file states in more than one place.
- 2026-09-02 the directory keeps its `-ack-and-mutation-count` name. It is a handle, not an
  inventory, and renaming it would move every path this branch has already published.
