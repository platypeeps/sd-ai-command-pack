---
title: Shadowing Jira is a migration question with no demand behind it, not the construction sd:361 describes
created: 2026-09-12
---

# PRD — a-second-tracker-with-no-rows

## Problem

sd:361 asks for a second tracker module beside the library's GitHub collector,
`sd shadow sync` iterating trackers with per-tracker watermarks, env-only
configuration with no default host, and an unconfigured Jira reported as a
not-collected line rather than a failure.

**Every one of those four things already exists in this pack, and all four
work.** Measured at 730d4541:

- **The iteration.** `TRACKERS` (`dashboard/collect.py:24`) is
  `(github, jira)`. The loop over it begins at `dashboard/collect.py:168`.
- **Per-tracker watermarks.** Inside that loop, `dashboard/collect.py:170`
  reads `store.watermark(connection, name)` for that tracker, and
  `dashboard/collect.py:173-174` writes it back *only* when that tracker's own
  collect succeeded. The rationale is written out at
  `dashboard/collect.py:160-162`: "Watermarks are per tracker, so Jira being
  unconfigured neither blocks GitHub from collecting nor lets GitHub's success
  step Jira's window forward over a gap it never read."
- **Env-only configuration with no default host.** `settings`
  (`dashboard/jira.py:89`) reads `JIRA_BASE_URL`, `JIRA_EMAIL`,
  `JIRA_API_TOKEN` and optional `JIRA_JQL`, and the module docstring at
  `dashboard/jira.py:26-30` states the no-default-host rule and why.
- **Graceful degradation.** `bin/sd-dashboard:220-221` already prints
  `issues[<tracker>]: not collected (<reason>)` and continues.

So sd:361 is not a construction task. **The real question is a migration**: the
pack has a working two-tracker collector writing to its own `index.sqlite`, the
library has a one-tracker collector writing to the shared `shadow` table, and
the library's retirement of `index.sqlite` was gated on a sync after the import.
sd:361 describes building what exists rather than moving what exists, and its
own framing hides the two facts that actually decide it.

### Fact one: the collector has never produced a Jira row, and still has not

The retirement sd:361 proposes to reverse was not a judgement that Jira does not
matter. It was the observation that the collector had never collected anything.
The system commit that recorded it, `b5e28bb` of 2026-09-06, says so:

> `dashboard/jira.py` is wired into TRACKERS but has never produced a row: the
> index holds github|1175 and no Jira row, tracker_watermark holds only
> GitHub's line, and two of the three variables `jira.settings` needs are unset
> in both the shell and the dashboard agent's plist. It retires with the
> package and nothing is lost.

Re-measured 2026-09-12, six days later, the rationale holds unchanged and the
gap has widened:

| | 2026-09-06 | 2026-09-12 |
|---|---|---|
| GitHub rows collected | 1,175 (`index.sqlite`) | **3,668** (`shadow`) |
| Jira rows collected | 0 | **0** |
| Watermark keys present | GitHub only | **GitHub only**, 10 rows, latest `2026-09-12T17:14:56Z` |
| `jira.settings` variables set | 1 of 3 | **1 of 3** |

`select distinct tracker from shadow` returns exactly one value, `github`. Of
the three variables, only the API token is present in the shell; the base URL
and the email are unset. (Presence was checked, never values.)

The commit's own numbers are still directly re-checkable, because the legacy
index was never deleted. Read on 2026-09-12 from
`~/.cache/sd-ai-command-pack/index.sqlite`, the path
`dashboard/store.py:78` builds: grouping its `issue` rows by tracker prefix
still returns `github|1175` and nothing else, and its `tracker_watermark`
table still holds one row, GitHub's, last moved 2026-09-01T05:23:37Z. So the
two-tracker loop at `dashboard/collect.py:168` ran against this store, with
Jira in `TRACKERS` the whole time, and produced zero Jira rows before it
stopped running. The mechanism is not untested. It is tested and empty.

The operator's Jira credentials *do* exist on this machine — they are set in
the `jira` MCP server's own environment block, not exported to the shell — so
this is not "Jira is unreachable". It is that the path `dashboard/jira.py` and
any library port would read is not configured, and has not been for at least
six days. sd:361's acceptance criterion "`sd-status` and the dashboard show
`LOG-23818`" therefore cannot be met by writing code: it needs a configuration
step the item does not name.

### Fact two: the migration would move rows into a weaker store

This is the part neither sd:361 nor the retirement commit noticed, and it runs
the wrong way.

- The pack's store keys a row on **tracker plus URL**. `row_id`
  (`dashboard/store.py:108`) returns `f"{tracker}:{url}"`, and its docstring at
  `dashboard/store.py:111-114` says the prefix exists precisely so that "a
  future tracker cannot silently adopt another's rows."
- The library's store keys on **URL alone**. The schema declares
  `CREATE UNIQUE INDEX shadow_by_url ON shadow (url);` at
  `sd_db/schema/001_initial.sql:99`, and the upsert at `sd_db/writes.py:460`
  resolves a collision with `ON CONFLICT(url) DO UPDATE SET tracker =
  excluded.tracker` — it rewrites the row's owner, with no error and no
  constraint violation.

Migrating from the composite-keyed store into the URL-keyed one is a regression
on exactly the property the pack wrote a comment to protect, and it is a silent
one. Two fields are also lost at the boundary: the pack's table declares
`updated_at TEXT NOT NULL` and `why TEXT NOT NULL`
(`dashboard/store.py:48-49`), and the `shadow` table has no `why` column at
all. This is filed separately as **sd:603**, and it is a hard precondition:
adding a second writer to a store that can silently reassign ownership is worse
than having one writer that cannot.

## Requirements

This item asks for a decision, not an implementation. The requirement is that
the decision be made on the two facts above rather than on sd:361's framing.

1. **Correct the item's framing before anything else.** sd:361's "what to
   build" list describes work that is already done. Whoever picks it up next
   must read the four line references in the Problem section first, or they
   will rebuild `dashboard/collect.py:168-186` in the library and call it
   progress.
2. **Do not treat this as reversing a decision.** The docstring the item quotes
   said: "When there is a second tracker there will be a second module, and the
   caller will iterate them; building the iteration now would be building it
   against one example." That is a stated precondition, not a prohibition. The
   precondition is *there being a second tracker* — meaning one that collects.
   With zero rows in six days, it is **not yet met**. sd:361 satisfies a
   precondition that has not arrived; it reverses nothing.
3. **sd:603 lands before any migration.** No Jira row may be written into
   `shadow` while a URL collision can silently reassign a row's tracker.
4. **Answer `why` and `updated_at` explicitly.** Either add the columns, or
   record in the migration that the fields are dropped and what stops depending
   on them. Dropping a `NOT NULL` field by not mentioning it is not an answer.
5. **The decision itself is the operator's and is not resolved here.** The one
   question that settles it is whether the operator intends to work Jira
   tickets at all. **The repository cannot answer that**, and this document
   does not guess. What the repository can say is on both sides below.

## The decision, laid out

**Cost: lower than sd:361 implies.** The library side is genuinely small,
because the plumbing is already generic:

- The `shadow` table already carries a `tracker` column
  (`sd_db/schema/001_initial.sql:87`).
- The watermark is already per-tracker: the read binds `(WATERMARK, tracker)`
  at `sd_db/shadow_sync.py:151-155` and the write records `key=tracker` at
  `sd_db/shadow_sync.py:176-183`.
- The store already honours a row that names its own tracker —
  `tracker=issue.get("tracker") or TRACKER` at `sd_db/shadow_sync.py:482`.
- The heartbeat key is already per-tracker,
  `f"tracker-sync:{tracker}"` at `sd_db/shadow_sync.py:631`.
- There is exactly **one** hard GitHub binding in the row shape: `normalize`
  writes a literal `"tracker": TRACKER` at `sd_db/shadow_sync.py:393`.

So the real work is a Jira collector module — most of which can be lifted from
`dashboard/jira.py`, 363 lines that already carry the three hard-won Jira rules
its docstring lists — plus a caller that iterates, which can be lifted from
`dashboard/collect.py:168-186`. Plus sd:603 first.

**Value: zero so far, and measurably so.** 3,668 shadow rows, none from Jira,
ever. Two of three variables unset for at least six days. One seed ticket named
in the item, in a tracker that has never been collected from. Building a
collector for a tracker nobody has configured produces a not-collected line and
nothing else.

**Retiring pays something back, too.** `dashboard/` is under a line-count
cap that `tests/test_loc_caps.py` measures against and that the file's own
header discusses at length; `dashboard/jira.py` is 363 lines of it.

## Acceptance criteria

- [ ] The operator answers one question: do they intend to work Jira tickets
      such that a shadow row would be acted on? **Not answerable from the
      repository** — recorded here as the gate, not as a task.
- [ ] If **no**: sd:361 is closed as not-to-be-built, `dashboard/jira.py` and
      its entry in `TRACKERS` (`dashboard/collect.py:24`) retire with the
      legacy collector, and `bin/sd-trackers ref jira:KEY` is decided
      separately — it is a different feature that resolves a reference without
      collecting anything, and it costs nothing to keep.
- [ ] If **yes**: the first step is configuration, not code —
      `JIRA_BASE_URL` and `JIRA_EMAIL` exported where `sd shadow sync` runs,
      and one successful collect against the existing
      `dashboard/collect.py:168` loop proving a row can be produced at all.
      Only then is sd:603 taken, and only then is the port planned, with
      sd:361's "what to build" list rewritten to describe the migration rather
      than the construction.
- [ ] Either way, sd:361's body is corrected so it no longer claims to be
      building an iteration and per-tracker watermarks that exist.

## References

- GitHub issue: <https://github.com/platypeeps/sd-ai-command-pack/issues/805>
- `platypeeps/system@b5e28bb`, 2026-09-06, "docs(work): B: Jira is not
  collected, and sd-trackers is not a collector", ledger C-159 — the rationale
  the `shadow_sync` docstring does not carry.
- sd:603 — the silent tracker-reassignment hazard. Precondition.
- sd:392 — the cross-repository boundary any port would cross.
- Not verifiable from here: `LOG-23818`'s current status. The item records it
  as the one live ticket on 2026-09-10 ("Gathering Requirements"). The `jira`
  MCP server timed out for this session and a direct API probe was refused by
  policy, so this document carries **no re-measurement of it**. It should not
  be treated as confirmed. Its state does not change the analysis: one ticket in
  a tracker with zero collected rows is not the fact that decides this.

## Log

- 2026-09-12 created. Pack facts measured at 730d4541; library facts against
  `platypeeps/system@754204d`; database counts from the live `sd.db`.
