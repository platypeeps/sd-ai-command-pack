---
title: One dashboard, and the pack's is the one that gives up surface
created: 2026-09-13
---

# PRD — one dashboard

## Problem

Two programs call themselves the dashboard. One of them answers the front door
and the other one cannot.

The decision is made and this document does not re-open it. **On 2026-09-13 the
operator decided: one dashboard, and the system repository's workflow server in
`local-project-dashboard/sd_dashboard/` is the one that survives.** The pack's
`dashboard/` is the one that gives up surface. What follows is the plan for
getting there and the four questions the item left open, answered.

### The direction is settled by a ceiling, not by a preference

Measured in this worktree at `a8295266`, through the repository's own measure
rather than by arithmetic — `code_line_count` (`tests/test_loc_caps.py:403`)
over `tracked("dashboard")`:

| Measure | Value | Cap | Headroom |
|---|---|---|---|
| `dashboard/` total lines | 4,510 | 4,600 | 90 |
| `dashboard/` code lines | **2,326** | **2,328** | **2** |

Two lines. And `DASHBOARD_CODE_CAP` (`tests/test_loc_caps.py:231`) rises only
payable in kind: a raise must remove or factor at least as many code lines as it
claims, which `test_the_code_ceiling_is_paid_for_in_kind`
(`tests/test_loc_caps.py:522`) enforces against `DASHBOARD_CODE_SLACK`
(`tests/test_loc_caps.py:239`). The system package measures **4,431 lines of
Python across 20 modules, plus 1,077 lines of static CSS and JavaScript**, with
**306 tests** behind it — the suite prints `Ran 306 tests`, where
`grep -c "def test"` returns 293, because a shared mixin in
`tests/test_direct_access.py` is inherited by two `TestCase` subclasses.
Absorbing that into the pack would mean paying more than four thousand lines out
of a directory with two to spare. That is not a direction, it is a wall. The
reverse direction has no ceiling at all, because the system package has none.

### Neither dashboard is a superset, so this is a port and not a merge

They share exactly two facts on disk. One is `collect_ports`, which the system's
Ports area and the pack's `sys.ports` plugin tab both reach. The other is one
`sd_db` write: `deliver` (`dashboard/work.py:232`), which resolves a row by
external id and calls `deliver_work`. Four tab names match — now/today,
work/backlog, skills/skills, ports — and three of the four read different
sources, so the names overstate the overlap rather than evidencing it.

**Only in the pack:** Repos, PRs, Issues, Sessions and the Now ranking — about
1,500 lines of collectors and 250 of UI — plus the plugin loader, 719 lines of
it, whose `load` (`dashboard/plugins.py:652`) renders the six legacy collector
tabs.

**Only in the system:** its sections, which a reader should enumerate from
`SECTIONS` at
/Users/sven/repos/system/local-project-dashboard/sd_dashboard/pages.py:40 rather
than from a list in prose. Eight entries today, seven of them in the nav and
`item` deliberately not. Its Operations areas are a second declaration, `AREAS`
at
/Users/sven/repos/system/local-project-dashboard/sd_dashboard/operations_screen.py:14,
eight of them. **The runner and the palette are not sections and this document
does not call them that:** the runner renders as panels inside other screens and
the palette is a dialog plus two API endpoints, whose read-only history is one of
the eight areas. Ports is an area, not a section, which is why it is one of the
two facts the two programs already share.

### The store boundary is the one hard constraint on the port

`connect` (`dashboard/store.py:81`) opens `sqlite3.connect`
(`dashboard/store.py:89`) for reads and `sqlite3.connect`
(`dashboard/store.py:94`) for writes, against a cache at
`~/.cache/sd-ai-command-pack/index.sqlite`. The system package opens none, by a
stated contract in its own package docstring, at
/Users/sven/repos/system/local-project-dashboard/sd_dashboard/\_\_init\_\_.py:4-6:

> Nothing in this package opens a database of its own; the only `sqlite3`
> connection opened anywhere is `sd_db.database`'s, which is requirement 2 and
> criterion 2's grep.

That contract is enforced and not merely stated: the grep runs as
`test_no_sqlite3_connect_in_the_dashboard` at
/Users/sven/repos/system/local-project-dashboard/tests/test_markup.py:188, whose
docstring reads "Criterion 2: the library is the only thing that opens the
database." Run today over the whole directory it returns one hit, and the hit is
the name of the test itself.

So the tracker cache cannot travel with the views. It has to land in `sd_db`.
**That is criterion 2, and citing criterion 12 for it is a mis-citation** — an
earlier probe attributed the store boundary to `test_criterion_12`, which is
about escaped markup. The substance is unchanged; the citation is not, and the
wrong one sends a reader to the wrong test.

sd:361 is that move, for Jira, as `sd_db/shadow_jira.py`. GitHub follows the
same shape. sd:361 is therefore step zero of this item and not a side quest.

### The pack's dashboard has not been the front door since #221, and that is what makes the port safe

The fear this plan has to answer is a broken front door mid-port. It does not
arise, and the reason is worth stating before the ordering section leans on it.

`DEFAULT_PORT` (`dashboard/server.py:57`) is 8767. The process listening on 8767
is PID 37095, which `launchctl` runs under the label `com.sven.sd-dashboard`,
and whose `ProgramArguments[0]` is the system repository's
`local-project-dashboard/dashboard.sh`. Measured by sd:705's followup note #1331,
and independently re-measured on pull request #898 at `d0ad6542`. So the pack
dashboard cannot bind its own default while the system server holds it:
starting it either fails or wins a race nobody wants it to win. **It is not a
fallback. There is no window in which the machine depends on it.** The invariant
the ordering has to protect is therefore not "the pack keeps serving until the
system catches up" — it is that the *system* page never loses a section the
operator was reading.

### And the pack's installer would stop the surviving dashboard

`LABEL` (`bin/sd-dashboard:52`) declares `com.sven.sd-dashboard` as the one
LaunchAgent the pack owns, and `PLIST` (`bin/sd-dashboard:53`) renders to that
name. `cmd_install` (`bin/sd-dashboard:139`) writes that file and then boots the
label out and bootstraps its own, at `bin/sd-dashboard:163-164`. Run today it
stops PID 37095, overwrites the system's plist body with the pack's, and
repoints the name at the pack. The live file's mode is 600 where the pack's
`write_text` would leave 644, which is evidence independent of either
repository's claims that the pack did not write it.

Nothing in the pack warns about this and no test covers it: `InstallTests`
(`tests/test_sd_dashboard.py:331`) patches the plist path to a scratch HOME, so
every case starts from a path that is absent or pack-written and none of them
puts a foreign plist there first.

This is sd:705's territory, and the requirement below says how the two items
divide.

## Requirements

1. **`dashboard/` goes entirely. The pack keeps no HTTP dashboard, read-only or
   otherwise.** A read-only pack dashboard is not the cheap option it sounds
   like: `dashboard/server.py`'s own docstring says the POST path is deliberate
   ("6b-7 gave the handler a POST, because the queue tabs exist to be decided
   in"), so a read-only variant means deleting `RUN_ALLOWLIST`
   (`dashboard/actions.py:52`), `run` (`dashboard/actions.py:114`), the ack
   store and `deliver` (`dashboard/work.py:232`) — which is most of what
   distinguishes the program from a report. What would remain is 4,510 lines
   under a cap with two lines of code headroom, a second port, and a second
   LaunchAgent, serving views the surviving dashboard also serves.

2. **`serve` and `install` go first, and they answer sd:705 by deletion.** The
   port number and the LaunchAgent label are this item's to decide, and the
   decision is that neither gets a new value. `cmd_serve`
   (`bin/sd-dashboard:37`) and `cmd_install` (`bin/sd-dashboard:139`) are
   removed; `cmd_index` (`bin/sd-dashboard:176`) stays until the tracker views
   move. This is the only step that makes the machine safer rather than only
   tidier, and it is first for that reason.

3. **The six plugin tabs become native system views. The plugin contract's
   transport survives; its discovery does not.** The question is already half
   answered on the ground, and the answer is not the one the item assumed. Five
   of the six tabs *already* render inside the system package, and none of them
   goes through the contract:

   - The tuple `VIEWS`, declared at
     /Users/sven/repos/system/local-project-dashboard/sd_dashboard/reports_screen.py:19,
     is `(("toolbox", …), ("briefs", …), ("vault", …), ("research", …))` — four
     of the six — and the `collect` below it, at
     /Users/sven/repos/system/local-project-dashboard/sd_dashboard/reports_screen.py:44,
     spawns `sd_tile.py` by a fixed sibling path with an 18-second wait and a
     65,537-byte read.
   - The `_collect` at
     /Users/sven/repos/system/local-project-dashboard/sd_dashboard/ports_screen.py:12
     loads `collectors.py` by path through `importlib` and calls `collect_ports`
     **in-process**, with `timeout=12`.

   Only `queues` has no system-side path. So the premise that the pack's loader
   is "the only renderer of the six legacy collector tabs" is false for five of
   them, and requirement 3 is written against what is there rather than against
   that premise.

   The decisive cost of the other option: **the system package has no loader at
   all.** It never reads `sd-plugin.json`, never enumerates tabs, never discovers
   an external tile. Re-homing the contract therefore means *building* 357 lines
   of loader code in that package, plus a shell-out to the pack's `bin/sd` for
   `sd plugin list --json` — a new dependency running from the surviving
   dashboard back into the repository this item is emptying. `design.md` prices
   both options and records what going native gives up.

4. **The 7-tab page and `app.js` are deleted, not ported — and five behaviours
   are ported out of them by name before they go.** `PAGE`
   (`dashboard/server.py:238`) is an HTML literal and the system package already
   has its own page and `static/`; two page shells cannot merge. `app.js` is 855
   lines, 569 of them code. A plan that says "deleted" without naming what has
   to survive is a plan that loses it silently, so `design.md` names five
   behaviours and records each as ported or dropped.

5. **The LOC caps come down in one change with the deletion, and that change
   rewrites a test's premise rather than only its number.** This is the
   requirement most likely to be got wrong, because the obvious reading of
   "payable in kind" is backwards. See the next section.

6. **Every step moves a section onto the system page before the pack loses
   it — two commits, never one.** At no instant is a section absent from both
   dashboards. This is the ordering requirement, and it is enforced by review
   rather than mechanically: no test in either repository can see both pages at
   once, and this document does not claim one. Recorded as an accepted gap in
   `design.md`.

7. **sd:705 keeps the two stale comments and nothing else.** Pull request #898
   is documentation-only and should merge on its own, independent of this item.
   Its port option A (move the default to a free port) and label option L1 (take
   a distinct label) are work this item then deletes and **should not be done**.
   Its option L2, the guard that refuses a plist the pack did not write, is
   unnecessary once requirement 2 lands, because there is no verb left to guard.

## The correction that decides requirement 5

Pull request #898's body says, of retiring `serve` and `install`: *"it removes
`dashboard/` code, and `DASHBOARD_CODE_CAP` is payable in kind, so removal earns
budget rather than spending it."* **That is wrong in the direction that
matters, and this item cannot be planned around it.**

`test_the_code_ceiling_is_paid_for_in_kind` (`tests/test_loc_caps.py:522`)
asserts that `DASHBOARD_CODE_CAP` minus what `dashboard/` measures is at most
`DASHBOARD_CODE_SLACK` (`tests/test_loc_caps.py:239`), which is 29. Today that
gap is 2. **Removing code widens the gap and fails the test.** So a removal does
not earn budget; it forces the ceiling down.

How much a removal earns, exactly, and the number does not depend on the size of
the removal. Remove *N* code lines and the highest cap that still passes is
`(2,326 - N) + 29`, which leaves headroom of 29 whatever *N* is. Headroom goes
from 2 to 29. **A removal of any size earns 27 lines of code headroom and
nothing else.** There is nowhere for a larger budget to go, because the slack
test caps standing permission at 29 regardless.

And lowering the cap is not a one-line edit either.
`test_each_ceiling_is_the_last_value_its_history_records`
(`tests/test_loc_caps.py:552`) requires the new value to be appended to
`CEILING_HISTORY` (`tests/test_loc_caps.py:287`) in the same commit. That append
is the first downward move the history has ever recorded — `ceiling_moves`
(`tests/test_loc_caps.py:331`) returns `(29, 26, 0)` in this worktree — and
`test_the_recorded_history_is_raises_only` (`tests/test_loc_caps.py:577`)
asserts that the downward count is zero. It goes red.

That is by design and its docstring says so: it "fails the day a ceiling finally
comes down — at which point the paragraph in R11-D41 that reasons from *not one
downward move* needs rewriting, which is what a failure here is for." So the cap
step is a decision record with a new R-id, not a patch: it lowers both
ceilings, appends both values, rewrites the `downward == 0` assertion into one
that permits a recorded fall and names it, and rewrites the paragraph in the
module docstring that reasons from there being none.

One more mechanical detail nobody finds by reading prose.
`test_the_dashboard_stays_under_its_ceiling` (`tests/test_loc_caps.py:487`) and
`test_the_dashboard_code_stays_under_its_own_ceiling`
(`tests/test_loc_caps.py:500`) both assert the enumeration is non-empty
("dashboard/ enumeration matched no tracked files"). **The commit that deletes
the last file under `dashboard/` reddens both of them on the empty
enumeration.** They retire in that same commit, in the shape `BIN_CAP` retired
at R11-D48: the constants deleted, the `CEILING_HISTORY` entries kept, because a
decision whose evidence has been deleted cannot be reviewed later.

## Acceptance criteria

- [ ] `cmd_serve` and `cmd_install` are gone from `bin/sd-dashboard`, and after
      the change `launchctl list` still shows PID 37095 under
      `com.sven.sd-dashboard` with `ProgramArguments[0]` unchanged. The negative
      is the point: the pack can no longer stop the surviving dashboard.
- [ ] All six legacy views — `toolbox`, `briefs`, `vault`, `research`, `ports`,
      `queues` — are reachable on :8767, each failing on its own rather than
      taking a screen down with it, and the pack's loader is deleted only after
      the sixth arrives. Five are reachable today; `queues` is the one to add.
      The check enumerates from the system package's own declaration rather than
      from this list, because a list in prose drifts and a tuple does not.
- [ ] Every one of the five behaviours `design.md` names out of `app.js` is
      recorded as ported, with the system-side location, or as dropped, with the
      reason. A behaviour with neither is a blocking finding.
- [ ] `python -m unittest tests.test_loc_caps` passes at every step, including
      the step that lowers the ceilings and the step that deletes them.
- [ ] `bin/sd-docs-lint` exits 0 and `python -m unittest
      tests.test_doc_citations` passes at every step. Deleting `dashboard/`
      invalidates every live anchored citation into it; `design.md` enumerates
      them rather than discovering them on a red build.
- [ ] Not mechanically checkable, and stated rather than invented: that the
      operator reads no section on either page during the window in which it is
      moving. Requirement 6 is a review habit. No test can see both pages.

## References

- sd:361, `docs/work/2026-09-12-a-second-tracker-with-no-rows/`. Step zero, and
  further along than its own checklist says. On `main` at `e80153ee` — pull
  request #897, which rewrote step 2's verify after note #1327 found that its
  named canary could never have been inside the query's window — steps 1 and 2
  are `[x]` and steps 3 through 9 are `[ ]`. But step 3 **has landed**: system
  pull request #312 merged as `b05d684a` and added
  `local-sd-db/sd_db/shadow_jira.py`, 343 lines, with a 187-line test module.
  Step 4 has not: `TRACKERS` appears nowhere in the system repository on
  `origin/main`, and what exists is the singular `TRACKER = "github"` in
  `shadow_sync`. So the file lags the code by one step, and this item's ordering
  reads the code.
- sd:705 and pull request #898, head `d0ad6542`. The two stale comments, and the
  enumeration of port and label options this item answers by deletion.
- `docs/work/2026-09-12-every-rule-is-a-row-and-a-checker/`, for the shape of a
  requirement that admits what it does not enforce.
- Not verifiable from this checkout: whether the system repository's page can
  host the plugin contract without a new asset pipeline. Its package docstring
  refuses a build step outright, and `design.md` takes that as a constraint
  rather than re-deciding it.

## Log

- 2026-09-13 created. Pack facts measured in this worktree at `a8295266`;
  LaunchAgent and port facts taken from sd:705 note #1331 and pull request
  #898's re-measurement at `d0ad6542`, not re-run here. System facts read from
  `origin/main` at `b05d684a`, because the working checkout at
  `/Users/sven/repos/system` lags it and a probe against the working tree
  reported `shadow_jira.py` absent when it is on `main`.
- 2026-09-13 requirement 3 was written the other way round in the first draft —
  keep the contract, move the loader — and the measurement overturned it. Five
  of the six tabs already render in the system package outside the contract, and
  that package has no loader to move one next to. The premise has been rewritten
  where it stood rather than corrected underneath itself.
