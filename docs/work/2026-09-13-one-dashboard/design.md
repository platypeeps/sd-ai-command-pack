# Design — one dashboard

## What this document decides

The PRD answers the hinge — `dashboard/` goes entirely — and states the six
questions. This document prices each of them, and it is written against a tree
that is further along than either item body says.

Measured 2026-09-13. Pack: this worktree at `a8295266`. System: `origin/main` at
`b05d684a`, and **not** the working checkout at `/Users/sven/repos/system`, which
lags it — a probe against the working tree reported `sd_db/shadow_jira.py` absent
while `git ls-tree origin/main` lists it. A plan measured against a stale
checkout plans for a world that no longer exists, so the provenance is stated
rather than assumed.

| Fact | Value | Where |
|---|---|---|
| `dashboard/` total / code | 4,510 / **2,326** | `line_count` and `code_line_count` over `tracked("dashboard")` |
| `DASHBOARD_CAP` / `DASHBOARD_CODE_CAP` | 4,600 / **2,328** | `DASHBOARD_CAP` (in `tests/test_loc_caps.py`, retired at sd:719 step 7), `DASHBOARD_CODE_CAP` (in `tests/test_loc_caps.py`, retired at sd:719 step 7); the code cap read 1,183 after step 4 and 0 after step 6, and both retired with the directory at step 7 |
| `DASHBOARD_CODE_SLACK` | 29, against a live gap of **2** | `DASHBOARD_CODE_SLACK` (in `tests/test_loc_caps.py`, retired at sd:719 step 7) |
| `ceiling_moves()` | `(29, 26, 0)` — 29 values, 26 up, **0 down** | `ceiling_moves` (`source:tests/test_loc_caps.py::ceiling_moves`); four falls recorded since, at steps 3 to 6, and `(33, 26, 4)` at step 7 with every ceiling closed |
| System package | 4,431 lines of Python, 20 modules; 1,077 of static | `sd_dashboard/**/*.py`, `sd_dashboard/static/` |
| System suite | **306** tests, `OK` | `grep -c "def test"` returns 293; a mixin in `tests/test_direct_access.py` is inherited twice |
| `sd_db/shadow_jira.py` | **343 lines, on system `main`** | system pull request #312, squash `b05d684a` |
| `TRACKERS` in the system repo | **absent**; `TRACKER = "github"` singular | `shadow_sync` |
| Live :8767 | PID 37095, label `com.sven.sd-dashboard`, `ProgramArguments[0]` = the system `dashboard.sh` | sd:705 note #1331; re-measured on pull request #898 at `d0ad6542` |

## Question 1 — does the pack keep a read-only dashboard?

**No. `dashboard/` goes entirely.** The recommendation and both costs.

**Cost of keeping one.** A read-only pack dashboard is not a subset of the
current program, it is a different one. `dashboard/server.py`'s docstring makes
the write path a decision rather than an accident: "6b-7 gave the handler a POST,
because the queue tabs exist to be decided in and a read-only port of them is a
list of questions nobody can answer." So the read-only variant deletes
`RUN_ALLOWLIST` (in `dashboard/actions.py`, retired at sd:719 step 6), `run`
(in `dashboard/actions.py`, retired at sd:719 step 6), the ack store, and `deliver`
(in `dashboard/work.py`, retired at sd:719 step 6) — which is one of only two facts the two dashboards
share on disk. What is left is 4,510 lines under a ceiling with two lines of code
headroom, needing a second port and a second LaunchAgent, showing views the
surviving dashboard also shows. The recurring cost is the more interesting half:
with 2 lines of headroom and a payable-in-kind rule, **the pack can never again
add a line of dashboard code without a decision record**, so every future edit to
a dashboard nobody visits costs a preparatory pull request.

**Cost of deleting it.** 4,510 lines, 2,326 of them code, and a ceiling rewrite
(question 4) that is the largest single piece of unplanned work in the port. Plus
three things that are *not* in `dashboard/` and have to be dealt with: the
`index` verb, the plugin registry's `tabs` and `tile` keys, and every anchored
citation in live prose that points into `dashboard/`.

**Why deletion wins.** Not the line count — the front door. The pack's dashboard
cannot bind `DEFAULT_PORT` (in `dashboard/server.py`, retired at sd:719 step 6) while PID 37095 holds 8767,
neither README tells anyone to start it, and the pack's own README says at lines
198 to 200 that the current dashboard lives in `system/local-project-dashboard`. A
program that is documented as historical, cannot start on its default, and costs
a decision record per edit is not a dashboard the pack is keeping. It is one the
pack has already stopped keeping and has not deleted.

## Question 2 — plugin contract, or native system views?

**Native. The contract's transport survives; its discovery does not.**

The first draft of the PRD said the opposite, and one measurement reversed it.

### The premise that failed

The item says `dashboard/plugins.py` is "the only thing that renders the six
legacy collector tabs". It is not, for five of the six, and the two paths that
already exist are in the *surviving* package:

| Tab | System-side path at `a5347185` | Boundary | Budget |
|---|---|---|---|
| `toolbox`, `briefs`, `vault`, `research`, and `queues` since step 2 | `VIEWS` at .../sd_dashboard/reports_screen.py:24, spawned by the `collect` at .../reports_screen.py:83 | subprocess, `sys.executable -I sd_tile.py <area>` | `VIEW_SECONDS`, 5 s per view, and a shared 64 KB read (sd:758); 18 s and 65,537 bytes when this table was written |
| `ports` | the `_collect` at .../sd_dashboard/ports_screen.py:32 | **in-process**, `importlib` load of `collectors.py` | `timeout=12` |

When this table was written `queues` had no row: no system-side path, no
boundary, no budget. Step 2 gave it the first row's.

Full paths, so the anchors resolve for a reader: the two files are
/Users/sven/repos/system/local-project-dashboard/sd_dashboard/reports_screen.py
and
/Users/sven/repos/system/local-project-dashboard/sd_dashboard/ports_screen.py.

So the plugin loader was the only renderer of **one** tab, `queues`, until
step 2, and the system page had already gone native for the other five without
anybody writing it down. It went native in two different ways, with three
different budgets, and neither of them is the contract's. Since step 2 the
loader renders nothing the system page lacks, and step 3 deleted it.

A second thing falls out of that, and it belongs in the system repository rather
than here: `collectors.py`'s docstring says "`sd_tile.py` is the only caller",
and `ports_screen.py` is a second caller that bypasses the subprocess boundary
entirely. That is a stale claim in the same family as the two sd:705 is fixing.
It is **not this item's to fix** and is recorded here so it is filed rather than
absorbed.

### Pricing the two options

**Option A — keep the contract, build the loader in `sd_dashboard/`.** 357 code
lines of loader, and a shell-out: the loader does not read manifests, it runs
`sd plugin list --json`, because "the registry is asked, never scanned" and "the
CLI is the plugin service surface by design". That shell-out is a dependency
running from the surviving dashboard *into* the repository this item is emptying,
which is the wrong direction on the one axis the item is about. It also has to be
built rather than moved: the system package has no loader, no manifest reader, and
no tab enumeration — the only near-misses are a local HTML helper named `tile()`
and the string `"sd_tile.py"` inside a fingerprint file list.

**Option B — native, and keep `sd_tile.py` as the transport.** `queues` joins
`VIEWS` (or its own screen, since it reads module state rather than a `collect_*`
function), and `sd-plugin.json`'s `tabs` and `tile` keys retire. No new
cross-repository dependency, and the four views that already work do not move.

**Recommendation: B.** And what B gives up, stated rather than waved past,
because three of the loader's four documented properties are real:

1. *Registry asked, never scanned.* Kept, and arguably strengthened: `VIEWS` and
   `AREAS` are in-code tuples in the repository that owns the screen, so nothing
   can appear because a file landed in a directory. What is lost is a *third
   party* declaring a tab — and measured, there is no third party. The registry
   holds two plugins: `sdw`, which declares no tabs, and `sys`, which declares
   all six. **A contract with one tab-declaring consumer, and that consumer being
   the repository that owns the surviving dashboard, is not a contract.**
2. *Per-tab invocation with a 5s budget.* The loader's docstring argues this is
   forced rather than preferred: the five system collectors measure 3.78s, 2.84s,
   0.03s, 0.01s and 0.00s, which fits a 5s budget individually and totals 6.66s
   in sequence, so one command for five tabs is a tile killed on every load.
   **Native keeps per-view invocation** — `reports_screen` spawns one area per
   call — so the property survives; only the number changes, from 5s to 18s.
   That is a widening and it should be argued in the system repository, not
   inherited silently. Recorded as a decision that item owes.
3. *A plugin that goes dark says so.* Of the properties the loader's docstring
   names, this is the one genuinely lost. The loader turns every failure mode — absent, non-zero, timed out, oversized,
   unparseable, contract-violating — into a rank-0 row in the Now view, on the
   reasoning that "the failure that matters is not a plugin crashing, it is a
   plugin crashing quietly and leaving Now looking calm." The system side raises
   a `ValueError` on the screen instead. **Going native trades a fleet-wide alert
   for a per-screen error, and there is no mechanical check that the trade was
   made deliberately.**

   **The gap is bounded, not accepted for good, and the boundary is step 6.** It
   opens when step 3 deletes the loader and closes when step 6 ports the Now
   ranking: a collector that goes dark raises a visible row in the merged system
   view, which `implement.md`'s step 6 verifies with a fixture collector that
   exits non-zero. Between those two steps a dark collector shows as a per-screen
   `ValueError` and nothing else, and that window is the accepted part. Recording
   the whole thing as permanently accepted would have left this document and
   `implement.md` asking one commit for opposite behaviour.
4. *Bounded reads rather than checked-after reads.* Kept: `reports_screen` reads
   65,537 bytes and no more.

**One more loss, recorded on 2026-09-13 after step 3 landed** (review-928 N1,
owner decision): *a plugin's declared actions as dashboard buttons.* The four
`sys/queue-*` actions — `queue-blog`, `queue-tip`, `queue-topic` and
`queue-watch` — were buttons in the pack dashboard's run strip. Step 3 reduced
the catalog to the backbone's own actions, and no dashboard renders them now.
The pack dashboard is not served, and no module of the system dashboard reads
the manifest. They stay reachable as `dashboard.sh queue-open <q>` and in
`sd plugin list`. The loader's docstring did not list this among its
properties, which is why the list above missed it.

## Question 3 — the `PAGE` string and `app.js`

**Both are deleted. Neither is ported. Six behaviours are carried out of them by
name first.**

`PAGE` (in `dashboard/server.py`, retired at sd:719 step 6) is an HTML literal whose nav declared seven
tabs (lines 290-306 of `dashboard/server.py` at `a8295266`) and whose plugin
mount point was a div (line 371 at that commit; step 3 removed it, and step 4
removed the `prs` and `issues` tabs, so the nav declares five today). The
system package already has one page shell and a
`static/` of one stylesheet and one script, and its package docstring refuses an
asset pipeline outright: "There is no frontend build step and there will not be
one." Two shells cannot merge and the surviving one is not the pack's. So `PAGE`
is deleted with `serve`, and it is not a loss worth arguing about.

`app.js` is 855 lines, 569 of them code by `code_line_count`, which measures
JavaScript by the conservative rule — a non-blank line not opening with `//` — so
that error can only tighten the cap. What is in it that the system page may not
have, each named so it cannot be lost quietly:

| Behaviour | Pack location | Disposition |
|---|---|---|
| Severity band from a rank | `band` (in `dashboard/app.js`) | ports with the Now ranking, step 6. The rank is a server-side number and the band is the rendering choice; the system page needs the second half only. |
| Per-table filter | `addFilter` (in `dashboard/app.js`) | **dropped, measured rather than assumed.** The system page already filters its listings: the field is `[data-listing-filter]` (`/Users/sven/repos/system/local-project-dashboard/sd_dashboard/static/dashboard.js:385`) and `/` is bound to focus it (`:189`). |
| Per-table sort | `addSort` (in `dashboard/app.js`) | **dropped, and it costs nothing, because no shipped table asks for it.** `PAGE` declares `data-sd-search` on exactly one table (the skills table; line 356 of `dashboard/server.py` at `a8295266`, 347 at step 4's landing) and `data-sd-sort` on none; the only `data-sd-sort` in the repository was a fixture in `tests/test_dashboard_markup.py`, which step 3 deleted. The system side refuses a client sort on purpose and says why (`/Users/sven/repos/system/local-project-dashboard/sd_dashboard/screens.py:135`): `sd today` and the page must list the same ids in the same order. |
| Panel enhancement | `enhance` (in `dashboard/app.js`) | **not dropped, and not step 3's.** It is the dispatcher for the two rows above and it runs for every *static* panel at startup — `for (const [, panel] of STATIC) enhance(...)` (line 426 of `dashboard/app.js` at `a8295266`, 275 at step 4's landing), seven panels then and five since step 4, none of them a plugin. Deleting it in step 3 is a `ReferenceError` on page load. It dies with `app.js` at step 6. |
| Plugin panel id assignment | `panelId` (in `dashboard/app.js`) | **dropped at step 3.** This one *is* plugin-only: its single caller is `drawPlugins` (in `dashboard/app.js`), which goes in the same commit. |
| Tracker key for a null-number row | `where` (in `dashboard/app.js`) | **specification, not code.** sd:361 step 7b changes this one expression so a Jira row shows `LOG-23818` rather than `LOG`. The system page needs the same rule when it takes the tracker views over. |

**The `where` row is also an ordering decision.** sd:361 step 7b edits a file this
item deletes. The temptation is to block 7b as wasted work. **Do not.** It is one
expression, it lands before the tracker views move, and it is the only written
statement of the rule the system page will need. A blocked 7b buys nothing and
loses the specification. sd:361 is not gated on this item in either direction.

## Question 4 — how the LOC caps move

The PRD states the correction that decides this; the design states the sequence
and the numbers.

### A removal earns 27 code lines, and its size does not change that

`test_the_code_ceiling_is_paid_for_in_kind` (in `tests/test_loc_caps.py`, retired at sd:719 step 7)
computes `DASHBOARD_CODE_CAP - code_line_count(tracked("dashboard"))` and asserts
it is at most `DASHBOARD_CODE_SLACK`, 29. Remove *N* code lines and the highest
cap that still passes is `(2,326 − N) + 29`; headroom after the change is 29 for
every *N*. Today it is 2. **So the whole of what any removal earns is 27 lines,
and there is nowhere for a larger figure to go.**

Run against the repository's own functions rather than by arithmetic, which is
how it was checked:

| Removal | Gap if the cap does not move | Passes? | Highest legal cap | Headroom then |
|---|---|---|---|---|
| the loader, 357 code lines | 359 | **no** | 1,998 | 29 |
| `app.js`, 569 | 571 | **no** | 1,786 | 29 |
| all of `dashboard/`, 2,326 | 2,328 | **no** | **29** | 29 |

The last row is the argument against a tombstone on its own: a code ceiling of 29
over an empty directory is not a record of anything.

That is the mechanical refutation of pull request #898's option B, which reads:
"it *removes* `dashboard/` code, and `DASHBOARD_CODE_CAP` is payable in kind, so
removal earns budget rather than spending it." Removal does not earn budget. It
forces the ceiling down, and forcing the ceiling down is the expensive part.

### Lowering a ceiling costs a decision record, by design

Three tests interlock, and a change that moves one without the others is red:

1. `test_each_ceiling_is_the_last_value_its_history_records`
   (in `tests/test_loc_caps.py`, retired at sd:719 step 7) requires the new value appended to
   `CEILING_HISTORY` (`source:tests/test_loc_caps.py::CEILING_HISTORY`) in the same commit.
2. `test_the_recorded_history_is_raises_only`
   (`source:tests/test_loc_caps.py::test_the_recorded_history_is_raises_only`) asserts the downward count across every
   recorded ceiling is zero. `ceiling_moves` (`source:tests/test_loc_caps.py::ceiling_moves`)
   returns `(29, 26, 0)` today. The append in (1) makes it `(30, 26, 1)` and this
   test goes red.
3. Its docstring says that is the point: it "fails the day a ceiling finally
   comes down — at which point the paragraph in R11-D41 that reasons from *not
   one downward move* needs rewriting, which is what a failure here is for."

So the cap step is: rewrite the `downward == 0` assertion
(line 590 of `tests/test_loc_caps.py` at `a8295266`) into one that permits a recorded fall and names
which ceiling fell and why; rewrite the *second* assertion in the same test
(line 598 at that commit), which asserted `upward == values -
len(CEILING_HISTORY)` and was arithmetically false the moment one move is not a
raise; and rewrite the module docstring paragraph that reasoned from there being
none, lines 33-46 at that commit. R11-D49 did all three (pull request #922). That is a new R-id, not a patch, and it
is the first time this repository has argued a ceiling downward.

**One ceiling moves, not both.** `DASHBOARD_CODE_CAP` comes down in each pack
commit that deletes code, one appended value each time. `DASHBOARD_CAP` covers the
whole directory including its prose, stands at 4,600 over a directory that only
shrinks from here, and is therefore never crossed on the way down — it moves once,
to nothing, when it retires at step 7. That is why the figure the implementation
verifies is `(30, 26, 1)` and not `(31, 26, 2)`: one value appended to one
history, not one to each.

### And the last deletion reddens both dashboard cap tests

`test_the_dashboard_stays_under_its_ceiling` (in `tests/test_loc_caps.py`, retired at sd:719 step 7) and
`test_the_dashboard_code_stays_under_its_own_ceiling`
(in `tests/test_loc_caps.py`, retired at sd:719 step 7) each open with
`self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")`.
**The commit that removes the last tracked file under `dashboard/` fails both on
the empty enumeration**, whatever the caps say. Nobody finds that by reading the
ceilings; it is found by reading the two assertions above them.

Both tests and both constants therefore retire in that same commit, in the shape
`BIN_CAP` retired at R11-D48: the constants deleted, the `CEILING_HISTORY`
entries kept, on the stated reasoning that these rows "are the evidence the
retirement was argued from, and a decision whose evidence has been deleted cannot
be reviewed later."

`test_the_migration_tools_stay_under_their_own_ceiling`
(`source:tests/test_loc_caps.py::test_the_migration_tools_stay_under_their_own_ceiling`) is the precedent for the other shape — it asserts
the empty case rather than skipping it, "so the transition is visible in the test
output" — and it is available if the dashboard ceilings are wanted as tombstones
instead. **Recommendation: retire rather than tombstone.** `MIGRATE_CAP`'s
subject is deleted at a known future step of a rollout that is still running; a
directory that is gone for good is not the same thing, and a cap on nothing that
can never come back is a row that outlives its question.

### Where the earned budget goes

Nowhere, and that is the honest answer. 27 code lines of headroom on a directory
that is being emptied is not budget anyone spends. The pack does not want
dashboard capacity after this item; it wants the constants gone. Any plan that
proposes moving those 27 lines to another ceiling is proposing a transfer no test
in this repository supports.

## Question 5 — ordering

The invariant to protect is **not** "the pack keeps serving until the system
catches up". The pack's dashboard has not been the front door since system pull
request #221, cannot bind 8767 while PID 37095 holds it, and is documented as
historical in both repositories' READMEs. The invariant is: **the system page
never loses a view the operator was reading, and nothing the pack runs can stop
PID 37095.**

| Step | What lands | Where | Why here |
|---|---|---|---|
| 0 | sd:361 to completion | both | Given. Step 3 has landed as `b05d684a`; steps 4 to 9 have not. The tracker views cannot leave the pack before the shared store can hold both trackers. |
| 1 | `serve` and `install` are removed from `bin/sd-dashboard`; `index` stays | pack | The only step that makes the machine **safer**. It closes sd:705's destructive half and answers its port and label questions by deletion. Nothing under `dashboard/` is deleted, so no ceiling moves. |
| 2 | `queues` becomes a native system view | system | The one view with no system-side path. After it, the pack's loader renders nothing that is not also reachable on :8767. |
| 3 | `sd-plugin.json`'s `tabs` and `tile` keys retire; then `dashboard/plugins.py`, `markup.py` and the plugin half of `app.js` go | system, then pack | Two commits, the system side first, like every other step here. The manifest keys are the system half: they advertise a discovery contract to the registry, so they must stop advertising it *before* the loader that honours them is deleted, not after. |
| 4 | PRs and Issues are served from `sd_db.shadow`; `index`, `store.py`, `github.py`, `jira.py`, `collect.py` retire | system, then pack | The legacy `index.sqlite` retirement. GitHub rows are already in `sd_db` — 3,668 of them as of sd:361's measurement — so this needs no new store work beyond step 0. |
| 5 | Repos and Sessions | system, then pack | Cheapest of the ports and deliberately not first: these collectors open no database at all, so criterion 2 is not in play. `collect.py`'s docstring is the authority — "Nothing here is stored as an input to anything." |
| 6 | The Now ranking | system, then pack | **Last, and it must be last.** Now is the merge of every source above and cannot be correct until each one is in place. It is also where question 2's lost alert row belongs. |
| 7 | `dashboard/` and `bin/sd-dashboard` are deleted; both ceilings and both cap tests retire in the same commit | pack | Forced into one commit by the empty-enumeration assertions, not chosen. |

Steps 2 through 6 are each **two commits, system first**: the view appears on
:8767, then the pack loses it. That is requirement 6 and **no test enforces it**,
because no test in either repository can see both pages. It is a review habit and
this document does not dress it up as a gate.

## Question 6 — what sd:705 keeps

**sd:705 keeps the two stale comments and nothing else.**

- `DEFAULT_PORT` (in `dashboard/server.py`, retired at sd:719 step 6) carried a comment above it
  (lines 54-56 of `dashboard/server.py` at `a8295266`) saying the system dashboard "landed on 8768 at P3
  so the two could run side by side" and that taking the port "is what makes the
  swap a swap". The swap reversed.
- `LABEL` (line 52 of `bin/sd-dashboard` at `e80153ee`) carried one at lines 48-51 of that commit saying
  the name "cannot collide with the system dashboard's plist while both exist".
  It is the cause of the collision, not a guard against it, and it sits directly
  above a destructive verb.

Pull request #898 fixes both and changes no constant. **It should merge on its
own, now, and it is not gated on this item.** A false comment that has already
misdirected an audit — note #1124 on sd:452 quoted the first one as a reason to
build a screen that was already live elsewhere — is worth landing ahead of any
port.

**Everything else in sd:705 is answered by deletion, and this is the plain
statement the item asked for.** Its port option A (move the default to 8769+) and
its label option L1 (take a distinct label) are work this item then deletes and
**should not be done**. Its option L2, the guard that refuses a plist the pack did
not write, is the right guard for a verb that stays; step 1 removes the verb, so
the guard has nothing to protect. Option C, failing loudly on a bind conflict, is
likewise moot once nothing binds.

One thing #898 flags out of scope stays out of scope and is answered here rather
than fixed: line 14 of `dashboard/server.py` (at `a8295266`, and unmoved at step 4's landing) still says "the replacement dashboard takes
:8767 with the tailnet reach". As a record of R11-D10 it is historically true, and
step 1 deletes the module that carries it, so it needs no edit of its own.

And the one correction this item owes #898: its option B's reasoning about
`DASHBOARD_CODE_CAP` is wrong in the direction that matters. See question 4.

## The five review passes, and what each changed

The planning cap is five. All five were spent and each one changed the document,
which is recorded here because a planning artefact that survived no attack has
not been planned.

1. **The plugin premise.** A read of the surviving package found that five of the
   six legacy views already render there, and that the package has no loader to
   move one next to. Question 2's recommendation reversed, from "keep the contract,
   move the loader" to "go native". The premise was rewritten where it stood; no
   correction was appended under live text saying the opposite.
2. **Three measurements.** "About 4,400 lines" became 4,431 Python plus 1,077
   static; "293 tests" became 306, with the reason the two differ; and the runner
   and the palette stopped being called sections, because `SECTIONS` holds eight
   entries and neither is one. The section and area lists now point at the two
   tuples a reader can re-run instead of reciting them.
3. **The cap arithmetic, run rather than reasoned.** The 27-line figure was
   asserted before it was computed. Computing it against `code_line_count` and
   `DASHBOARD_CODE_SLACK` confirmed it and produced the table above, including
   the "highest legal cap = 29 over an empty directory" row, which is what turned
   "retire or tombstone" from a preference into an argument.
4. **The import graph, against the step grouping.** Two defects in
   `implement.md`, both invisible in a plan that groups files by purpose. Step 1
   left `server` as an unused import (line 34 of `bin/sd-dashboard` at `a8295266`) after deleting the
   only six uses of it, which `ruff` fails on. Step 3 deleted
   `dashboard/plugins.py` while `server.py` still imports it at
   line 43 of `dashboard/server.py` (at `a8295266`; the same line at step 4's landing, without `plugins` or `store`) and survives to step 6, which would land a module
   that cannot import. Both steps were rewritten. The same pass confirmed
   `markup` is the loader's alone — imported by `dashboard/plugins.py` and
   nowhere else — so its grouping was right.
5. **The pin is not only CI's.** The running dashboard's `/health` reports its
   `sd_db` as the **pack's** virtualenv copy, so a system-side view needing a
   newer library is gated on the pack's venv being reinstalled and PID 37095
   restarted, not on CI alone. Step 4 gained that sequence.

## Accepted gaps

Stated as gaps because there is no mechanical check, and asserting one there is
not is the defect this pack files items about.

1. **Requirement 6's two-commit ordering.** No test can see both pages. Review
   only.
2. **The per-view timeout widening from 5s to 18s.** The loader's 5s is argued
   from measured collector timings; the system side's 18s is not argued anywhere
   this document could find. Nothing checks either number against the other, and
   this item does not add a check. It owes the system repository a decision.
3. **The lost rank-0 alert row.** Going native trades a fleet-wide "a collector
   went dark" row for a per-screen `ValueError`. Nothing asserts the trade was
   deliberate. Belongs with step 6.
4. **Citation breakage across the deletion.** `tests.test_doc_citations` will
   catch anchored citations into `dashboard/` as `target-missing`, which is red —
   so this gap is *closed* for citations inside this repository. What it does not
   cover is prose in the system repository or in `~/repos` elsewhere citing
   `dashboard/` paths, because that corpus is a different repository's. Not
   checked, and not claimed to be.

## What could not be verified

- That the operator reads no moving view during a step's two-commit window.
  Requirement 6's whole content, and unobservable from any checkout.
- That the system page can host a sixth view without an asset pipeline. Its
  package docstring refuses one, and this document takes that as a constraint
  rather than testing it.
- The 5s-versus-18s question above: the loader's five collector timings are
  quoted from its docstring and were **not** re-measured here.
