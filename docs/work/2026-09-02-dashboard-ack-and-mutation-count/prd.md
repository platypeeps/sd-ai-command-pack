---
title: the dashboard's two open gaps — an ack that sticks, and a mutation the index can count
status: planning
created: 2026-09-02
---

# PRD — the dashboard's two open gaps

## Problem

The `artifacts-as-product` item closed on 2026-09-02 with the dashboard built and serving:
`dashboard/server.py` has a `do_POST` behind three guards, `bin/sd-dashboard` has `serve`,
`install` and `index`, and the system dashboard it replaced is gone (`platypeeps/system#190`
deleted the server half). It closed with two things it had named as belonging to a later item
rather than to itself. Both are still open, both were verified against the working tree on
2026-09-02, and one of them makes a deletion criterion unevaluable on a date that is now fixed.

**1. A dismissed alert comes back.** `dashboard/now.py:15` states the contract — "**An id is an
ack key** (R11-D20), so it identifies one alert and not one row" — and nothing stores an ack.
`RUN_ALLOWLIST` in `dashboard/actions.py:52-58` holds exactly one entry, `index`. There is no ack
producer and no ack consumer, so Now re-renders every row it ranked on the previous poll. The
prior item recorded this at `implement.md:2062-2068` as "a tab-scoped version of the
dead-destination failure R11-D19 was written about," and assigned it to "whichever step builds
the ack store." No step did.

**2. R11-D10's deletion criterion has no counter.** The criterion (`design.md:1528-1532`) is:
sixty days after the 6b swap, if the index shows fewer than ten mutating requests from a tailnet
Host, the write path and its three guards are deleted and the dashboard returns to GET-only.
`do_POST` (`server.py:443-479`) writes no record of having run — it validates, dispatches to
`actions.run`, and returns a body. The index has no table for it. The criterion therefore
evaluates to "no evidence" rather than to a number, which is not the same answer and cannot be
read as one.

This is the second time the same failure has been found in this codebase. R10-D3's 60-day
criterion had the identical shape and was fixed on 2026-09-02 by making `sd-handoff-restore`
append one line per restore to `handoff/loads.jsonl`; its evaluation is now answerable on
2026-11-01. `implement.md:2069-2076` names the repeat in as many words: "a deletion criterion
nobody can evaluate is the failure mode standing rule 1 exists to prevent... It happened twice.
The rule catches a mechanism arriving without a criterion; it does not catch a criterion arriving
without a counter."

## Measured state

| Fact | Number | Source |
|---|---|---|
| `dashboard/` total lines | **4,128 against a 4,300 cap — 172 headroom** | `wc -l dashboard/*.py dashboard/*.js` |
| `dashboard/` code lines | **2,190 against a 2,300 cap — 110 headroom** | the tokeniser in `tests/test_loc_caps.py:115-134` |
| `RUN_ALLOWLIST` entries | 1 (`index`) | `dashboard/actions.py:52-58` |
| Mutating requests recorded | 0 — no write site exists | `dashboard/server.py:443-479` |
| `bin/sd-dashboard` verbs | 3 of the design's 5 (`serve`, `install`, `index`) | `bin/sd-dashboard:207-216` |
| 6b swap closed | 2026-09-01 (6b-9) | `implement.md:1504` |
| R11-D10 evaluation date, read literally | **2026-10-31**, against a count of zero | `design.md:1529` + the above |
| Closest precedent's cost | `record_load` + `load_age_seconds` = **59 code lines** | the tokeniser, over `bin/sd-handoff-restore:157-313` |

`DASHBOARD_CODE_CAP` moves **downward only** (`tests/test_loc_caps.py:20`), so 110 lines is a
budget this item cannot raise by writing prose or by re-deriving the cap. It is the binding
constraint on everything below, and any solution that does not fit inside it is not a solution.

## The clock is already running, and that is the urgent half

6b-9 closed on 2026-09-01 (`implement.md:1504`), so a literal reading of R11-D10 makes its
criterion answerable on **2026-10-31** — against a count of zero, because nothing counts. "Fewer
than ten mutating requests" would be satisfied, and the rule would delete a write path the phone
uses daily, on the strength of evidence that was never collected. A criterion that cannot be
evaluated does not fail safe: it fails toward whichever branch a zero happens to select, and here
that branch is deletion.

R10-D3 hit this wall a week ago, and it was resolved on the record by Sven's direction — the sixty
days run **from the counter, not from the item**
(`../2026-08-29-artifacts-as-product/prd.md`, the R10-D3 close). The same resolution is proposed
here, and it needs saying out loud rather than being inherited quietly, because it moves a date.
Either the criterion is re-dated in this item's `design.md` to sixty days after the counter lands,
or it is evaluated on 2026-10-31 with a documented "no evidence" and the write path survives on
that basis. The first is better; both beat discovering it on the day. What this item may not do is
move the date by silence.

## The tension this item exists to resolve

An ack names one alert. Naming a thing is a parameter, and **R11-D25 decided against parameters**
(`design.md:2255-2280`): an action is a command and not a form, it takes no arguments from the
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

The `artifacts-as-product` requirements carry unchanged; requirement 6 is the one this item is
mostly about. Specific to this item:

1. Every mutating request that passes the three guards is recorded durably enough to survive a
   restart, with what R11-D10's criterion actually needs: a timestamp and whether the Host was a
   tailnet name. A count that cannot distinguish a tailnet Host from loopback does not answer the
   criterion as written.
2. The record is a byproduct of serving, never a precondition: a failure to write it degrades to a
   missing row, never to a refused or 500'd request. The write path is a security boundary, and a
   counter is not a reason to add a failure mode to it.
3. An acknowledged alert stays acknowledged across polls and across a server restart, keyed by the
   R11-D20 alert id.
4. The write path keeps the property R11-D25 bought: nothing a caller sends reaches an argv.
   An ack id is stored and compared, never interpolated into a command.
5. Both mechanisms are new, so standing rule 1 applies to each: a linked incident and a deletion
   criterion that a command can evaluate — and, this time, the counter that makes the criterion
   evaluable ships with the mechanism rather than after it.
6. The whole item fits in 110 lines of code under `dashboard/`, or it explicitly proposes what to
   delete to make room. Raising `DASHBOARD_CODE_CAP` is not available.

   The yardstick for whether 110 is enough, rather than a guess: `record_load` and
   `load_age_seconds` in `bin/sd-handoff-restore:157-313` are **59 code lines** by the same
   tokeniser — one durable append-only counter, hardened over eight review rounds for concurrent
   writers, torn records and an unparseable timestamp. That is the honest cost of the *first* of
   this item's two mechanisms, leaving ~51 for an ack store and its control. `dashboard/app.js`
   charges the same cap, so the dismiss control is inside that number, not beside it. This is
   feasible and it is thin; `design.md` should treat "what do we delete" as a live branch rather
   than a fallback, and the counter may be cheaper here than it was there — a POST handler has no
   second writer racing it the way a SessionStart hook does.

## Acceptance criteria

- [ ] A mutating request that passes Host, token and `RUN_ALLOWLIST` leaves exactly one durable
      record; a request refused at any guard leaves none. Verified by pressing the real button on
      the real machine and by a test for each of the four paths.
- [ ] A forced failure of the record write (unwritable store) still returns the action's own
      status to the caller. Verified by a fixture, not by inspection.
- [ ] R11-D10's criterion is answerable by a command that runs against the store and prints a
      number, written in this item's `design.md` the way R10-D3's `wc -l` and `jq` median are
      written in `../2026-08-29-artifacts-as-product/prd.md`.
- [ ] An alert acknowledged once does not reappear on the next poll or after a server restart;
      an alert whose underlying condition returns after being acked is a decision this item
      records rather than discovers.
- [ ] `grep` over `dashboard/` shows no caller-supplied value reaching an argv.
- [ ] `dashboard/` stays under both caps, with the PR reporting its own line count against the
      110-line code headroom (R11-D24's convention at `design.md:1330`).
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
3. Where does an ack live so that a `dashboard/` line budget of 110 is enough for both mechanisms?

## Planning adversarial review — 2026-09-02

Host lane only; this repository defines no additional lane. Trigger: `prd.md` is new. Every claim
above was checked against the working tree or the prior item's artifacts, not against memory.

- **C-1 — the criterion's clock was left implicit. Blocking. `addressed`.** The draft said the
  criterion "has no counter" without saying when it comes due. 6b-9 closed 2026-09-01, so the
  literal date is 2026-10-31 and the literal answer is a zero that deletes a live write path.
  Evidence: `implement.md:1504`, `design.md:1529`. Owning artifact: this file, new section *The
  clock is already running*.
- **C-2 — the 110-line budget was asserted, never sized. Material. `addressed`.** Evidence:
  the closest precedent is 59 code lines by the same tokeniser
  (`bin/sd-handoff-restore:157-313`), which leaves ~51 for the second mechanism *including* its
  `app.js` control. Owning artifact: this file, requirement 6.
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

Implementation is **not** unblocked, and deliberately so: this is a PRD with three open questions
that `design.md` owns. No blocking concern is unresolved.

## Log

- 2026-09-02 created. Both gaps verified against the working tree rather than carried over from
  the prior item's prose: `RUN_ALLOWLIST` holds one entry, `do_POST` has no write site.
- 2026-09-02 host adversarial review run; C-1 and C-2 changed this file, C-3 rebutted with
  evidence, C-4 addressed by construction.
