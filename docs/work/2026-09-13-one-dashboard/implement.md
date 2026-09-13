# Implement — one dashboard

## Budget and shape

Ten steps, numbered 0 to 9. Step 0 is a dependency, steps 1 to 7 are the
migration and most of them are a pair of pull requests across two repositories,
and steps 8 and 9 are the citation sweep and the closing notes. The boundary is
sd:392's: views and collectors land in `platypeeps/system`, verbs and
caps land here, and nothing in the pack half depends on the newer system side
until the step that says so.

Every step 2 to 6 is **two commits, system first**. The view appears on :8767,
then the pack loses it. A single commit that does both is the one shape this plan
refuses, because it is the only one with a window where a view exists nowhere.

`.github/workflows/**` is sensitive under `.github/sd-review.json`, so any pin
move is its own pull request, in the shape #888 and sd:361 step 5 both follow.
Only step 4 needs one.

**`DASHBOARD_CODE_CAP` comes down in every pack commit from step 3 onward, one
appended history value at a time; `DASHBOARD_CAP` does not move until it retires
at step 7.** The two ceilings behave differently and an earlier draft of this
paragraph flattened them into one sentence. The code cap is the one with slack of
29 against a live gap of 2, so a commit deleting more than 27 code lines must
lower it in the same commit to keep `test_the_code_ceiling_is_paid_for_in_kind`
(`tests/test_loc_caps.py:522`) green — and every deletion here is larger than
that. The total cap is 4,600 over a directory that only shrinks, so it is never
crossed on the way down.

Step 1 is outside all of this: it deletes lines from `bin/sd-dashboard`, which has
had no ceiling since R11-D48, and nothing under `dashboard/`. Step 2 deletes
nothing. **The first lowering is step 3's, it is where the history test goes red,
and it needs a preparatory commit of its own:** read step 7's first paragraph
before starting step 2.

## Step checklist

- [ ] **0. sd:361, to completion.** Its own `implement.md` is the plan and this
      item does not restate it. State on `main` at `e80153ee`: steps 1 and 2 are
      `[x]`; step 3 is `[ ]` in the file but **has landed** as system pull
      request #312, squash `b05d684a`, which added
      `local-sd-db/sd_db/shadow_jira.py` (343 lines) and
      `local-sd-db/tests/test_shadow_jira.py` (187). Steps 4 to 9 remain.
      Verify: `git ls-tree origin/main -r --name-only | grep shadow_jira` in
      `/Users/sven/repos/system` returns both paths — it does today — and
      `python -c "import sd_db; print(sd_db.TRACKERS)"` in the pack's venv prints
      `('github', 'jira')`, which is step 4's own verification. **Today it raises
      `AttributeError: module 'sd_db' has no attribute 'TRACKERS'`** — measured
      against the installed library, which reports `SCHEMA_VERSION` 8 — because
      `TRACKERS` appears nowhere in the system repository on `origin/main`. The
      raise is the expected pre-condition, not a failure of the check, and it is
      written out because "prints nothing" is what an empty tuple would do and
      would read as a pass. **Do not mark step 3 done in sd:361's file from this lane**;
      that item's owner holds the file, and editing it here is the cross-lane
      write sd:525 objects to. Record the landing as a note on sd:361 instead.

- [x] **1. `serve` and `install` are removed; `index` stays.** Every
      `bin/sd-dashboard` line number in this step's plan is as of `e80153ee`,
      where it was measured, except the two live citations for `cmd_index` and
      `issue_lines`. In `bin/sd-dashboard`: delete `cmd_serve` (line 37),
      `cmd_install` (line 139), `launchctl` (line 126), `PLIST_BODY` (line 81),
      `LABEL` (line 52), `PLIST` (line 53) and the two `add_parser`
      registrations for them, and delete the stale comment at lines 48-51 with
      the constant it described rather than fixing its wording. **Then drop four
      imports, not one.** Each was grepped for its uses rather than read off the
      diff, which is the only way any of them shows up, and each is a `ruff`
      failure if it stays:

      | Import | Line at `e80153ee` | Every use, and why it goes |
      |---|---|---|
      | `server` | 34 | six uses, at lines 39, 43, 159, 172, 242 and 246 — each inside a deleted verb or its parser registration. |
      | `sd_ledger` | 32 | one use, `record=sd_ledger.append, acked=sd_ledger.acked` at line 44, inside `cmd_serve`. |
      | `subprocess` | 21 | one use, `subprocess.run` at line 134, inside `launchctl` — which this step deletes. |
      | `os` | 20 | one use, `os.getuid()` at line 149, inside `cmd_install`. |

      `collect` and `store` **stay** in the `dashboard` import: `cmd_index`
      (`bin/sd-dashboard:32`) and `issue_lines` (`bin/sd-dashboard:56`) still
      use them, and steps 4 and 5 still read the cache the `index` verb fills.

      **The module docstring is part of this step, because `--help` prints it.**
      At `e80153ee` it opened "Three verbs now, not the five the design lists"
      and spent a sentence on when `install` arrived; it is passed as
      `ArgumentParser(description=__doc__)`, so leaving it makes
      `sd-dashboard --help` advertise two verbs that no longer exist and a
      launchd workflow that has been deleted. One verb remains and the
      docstring says so.

      `InstallTests` (line 331 of `tests/test_sd_dashboard.py` at `e80153ee`)
      is deleted with the verb it covers, and the two cases in it that pin the
      port baked into the plist go with it.

      This step subsumes sd:705's destructive half and answers its port and label
      questions by deletion. It is first because it is the only step that makes
      the machine safer rather than tidier.

      Verify, and the important half is a negative:
      `launchctl list | grep com.sven.sd-dashboard` prints the same PID after
      the change as before it (37095 when this plan was measured, 76442 when
      step 1 landed), and
      `plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/com.sven.sd-dashboard.plist`
      still prints the system `dashboard.sh` as element 0 — asserted **after**
      the change and before it, so the pair is evidence rather than a hope. Then
      `grep -rn "com.sven.sd-dashboard" bin/ dashboard/ tests/` prints nothing:
      the pack no longer names a label it does not own. Then
      `grep -rn "sd-dashboard serve\|sd-dashboard install" . --include='*.md'
      --include='*.py' --include='*.sh'` outside `docs/work/archive/` prints
      nothing but this paragraph, which #898 already measured as true for
      `skills/` and `.claude/` and which this step re-runs over the whole tree
      rather than inheriting. `python -m unittest tests.test_sd_dashboard
      tests.test_loc_caps tests.test_code_health` passes; the caps do not move,
      because nothing under `dashboard/` changed.

      Mutation, to prove the negative is load-bearing rather than vacuous:
      register an `install` parser again, alone, and
      `test_index_is_the_only_verb` in `tests/test_sd_dashboard.py` reddens;
      revert and the tree is identical to the commit. An earlier draft said the
      `com.sven.sd-dashboard` grep would redden instead. It cannot: the parser
      registration never named the label, so that grep stays silent under this
      mutation, which is why the verb set is asserted by a test.

      **Done on `fix/sd-719-step1-pack-dashboard-stops-serving`, branched from
      `359a2bc9`, and the plan above had drifted by then.** #898 and #901
      (sd:705) landed after `e80153ee`, so everything was re-derived by `ast`
      before deleting. #901 had added `foreign_owner`, `LOGS` and
      `LAUNCHD_PATH`, all reachable only from `cmd_install`, and a fifth import,
      `plistlib`, used only by `foreign_owner`. All of them went with the verb,
      as did the second `sys.path` insert, which existed only so
      `import sd_ledger` resolved.

- [ ] **2. `queues` becomes a native system view.** System repository only;
      nothing in the pack changes. `queues` is the one of the six legacy views
      with no system-side path — the other five already render, four through the
      `collect` at
      /Users/sven/repos/system/local-project-dashboard/sd_dashboard/reports_screen.py:44
      and `ports` in-process through the `_collect` at
      /Users/sven/repos/system/local-project-dashboard/sd_dashboard/ports_screen.py:12.
      `queues` reads module state in `collectors.py` rather than a `collect_*`
      function, so it is not a fifth entry in `VIEWS` by construction; the
      decision of whether it joins that tuple or takes its own screen belongs to
      the system repository and this document does not make it.

      Verify: the system suite runs `Ran 307 tests` or more — it prints
      `Ran 306 tests ... OK` today — and one new case asserts the `queues` view
      renders rows from a fixture and that a collector failure surfaces on the
      screen rather than as an empty table. The pack is untouched, so
      `git status` in the pack is clean, which is the control that this step did
      not leak across the boundary.

- [ ] **3. The plugin loader retires, and the manifest loses two keys.** System
      commit first, and it is not nothing: **remove the `tabs` and `tile` keys
      from `/Users/sven/repos/system/sd-plugin.json`.** They are the system half
      of this step because they advertise a discovery contract to the registry,
      so they must stop advertising it before the loader that honours them is
      deleted — the same system-first order every other step follows, and an
      earlier draft had this step alone running backwards. The `actions` key
      stays: `sd plugin list --json` still reports it and the four queue-open
      actions are not tabs.

      Pack commit: delete `dashboard/plugins.py` (719 lines, 357 code), the
      `plugin-tabs` span and the `plugin-panels` div in `PAGE`
      (`dashboard/server.py:238`), and the loader's rows from the Now merge in
      `dashboard/now.py`.

      **The plugin half of `app.js` is `drawPlugins` and `panelId`. It is not
      `enhance`, and deleting `enhance` here breaks the page on load.** The
      disposition table in `design.md` had this wrong and the import graph
      corrects it:

      | Function | Step | Why |
      |---|---|---|
      | `drawPlugins` (`dashboard/app.js:690`) | **3** | It polls `/api/plugins`, which this step's `server.py` edit removes. Delete it *with all three of its call sites* — `drawPlugins()` at `dashboard/app.js:780`, `setInterval(drawPlugins, 10000)` at `:784`, and its entry in the redraw list at `:828` — or the page polls a deleted endpoint every ten seconds. |
      | `panelId` (`dashboard/app.js:526`) | **3** | Plugin-only, and its single caller is `drawPlugins` (`dashboard/app.js:690`). |
      | `enhance` (`dashboard/app.js:517`) | **6**, with `app.js` | **Not plugin-only.** `for (const [, panel] of STATIC) enhance(...)` at `dashboard/app.js:426` runs it over all seven static panels at startup. `drawPlugins` calling it at `:745` is the *second* caller, not the only one. Deleting it in step 3 is an uncaught `ReferenceError` at load, and it silently takes the skills-table filter with it. Step 3 removes the call at `:745` and nothing else. |
      | `addFilter` (`:463`), `addSort` (`:480`) | **6**, with `app.js` | Reached only through `enhance`. Their dispositions are in `design.md`: both dropped, the filter because the system page has one, the sort because no shipped table asks for it. |

      **`dashboard/actions.py` depends on the module this step deletes, and it
      survives to step 6.** `from .plugins import Bounded, bounded_run`
      (`dashboard/actions.py:37`) is a hard import, and the surviving server calls
      `plugins.catalog()` from the `/api/actions` path at `dashboard/server.py:501`
      and again at `:588`. So this step must, in its pack commit: move `Bounded`
      and `bounded_run` into `dashboard/actions.py`, which is their only remaining
      consumer, and reduce `actions.catalog` to the backbone's own actions —
      dropping the `plugins.catalog()` halves at `:501` and `:588` with the
      docstring sentence at `dashboard/actions.py:96` that promises "the
      backbone's, then the plugins'". Removing only the `/api/plugins` endpoint
      (`dashboard/server.py:506`) leaves an `ImportError` at startup, which no
      test in this step's list would catch before step 6.

      **`dashboard/markup.py` goes in this step and not a later one, and
      `server.py` has to be edited in it.** Both facts come from the import graph
      rather than from the file names: `markup` is imported at
      `dashboard/plugins.py:58` and **nowhere else** under `dashboard/`, so it is
      the loader's and dies with it. And `server.py` imports `plugins` at
      `dashboard/server.py:43` while surviving until step 6, so this step must
      drop `plugins` from that import line and the endpoint behind it, or step 3
      lands a module that fails to import. `tests/test_dashboard_markup.py` goes
      with `markup.py`. This is the step's real hazard and it is invisible in a
      plan that groups files by what they are for.

      **Two things this step gives up, and both are recorded rather than
      silently spent** (design, "Pricing the two options"): a third party
      declaring a dashboard tab, which has no instance — the registry holds two
      plugins and only `sys` declares tabs — and the rank-0 alert row a dark
      collector used to raise, which step 6 rebuilds on the system side. That
      second one is a gap **between step 3 and step 6, and not after it**: in the
      window a dark collector shows as the system side's per-screen `ValueError`
      and nothing more. `design.md` records the same boundary, because an
      indefinitely accepted gap there and a required row here would be two
      documents asking one commit for opposite things.

      Verify: `bin/sd plugin list --json` still reports the `sys` plugin with its
      four actions and no `tabs` key; `python -m unittest tests.test_loc_caps`
      passes with `DASHBOARD_CODE_CAP` lowered.

      **Lowered by what this commit removes in total, which is not 357.** That
      figure is `dashboard/plugins.py` alone, and
      `code_line_count(tracked("dashboard"))` charges every file in the commit:
      `plugins.py` at 357 code lines, `markup.py` at 121, plus the `app.js` and
      `server.py` lines above — 478 before the JavaScript, all measured with
      `code_line_count` rather than `wc -l`. Lowering by `357 - 27` leaves the gap
      above 29 and fails the same test the lowering was for. **Do not take any
      number from this document: re-measure `code_line_count(tracked("dashboard"))`
      in the finished commit and set the cap to that plus at most 27.** See step 7
      before choosing it, because the first lowering is where the history test goes
      red.

      **`tests/test_code_health.py` is part of this step's cleanup, not only the
      cap check.** It carries persistent baseline entries naming the files this
      commit deletes: `dashboard/plugins.py::bounded_run` in both `COMPLEX`
      (`tests/test_code_health.py:618`) and `LONG` (`tests/test_code_health.py:651`)
      — the entries themselves are at `:647` and `:665` — and the four
      `dashboard/markup.py::Filter.handle_*` methods in `DYNAMIC`
      (`tests/test_code_health.py:675`), entries `:676` to `:679`.
      `test_every_baseline_entry_still_earns_its_place` fails on a baseline whose
      subject is gone. The `markup.py` four are deleted. The `bounded_run` two are
      **repointed, not deleted** — the function moves to `dashboard/actions.py`
      above, so it is still there to be complex and long, under a new name.

      `tests/test_dashboard_plugins.py` is deleted with its subject.
      `python -m unittest tests.test_doc_citations` passes, which will require
      re-anchoring: every anchored citation into `dashboard/plugins.py` in live
      prose becomes `target-missing`, which is red, and the enumeration is
      `grep -rn 'dashboard/plugins.py:' --include='*.md' .` outside
      `docs/work/archive/`.

- [ ] **4. PRs and Issues are served from `sd_db.shadow`; the legacy index
      retires.** System commit: the tracker views read `tracker_items` and
      `tracker_freshness` from `sd_db`, which already take a tracker argument, and
      derive a Jira row's key as `url.rpartition("/")[2]` — the rule sd:361 step
      7b writes into `where` (`dashboard/app.js:115`), carried across rather than
      reinvented. No new column: the key is the last path segment of the URL, and
      a `key` column would be a second copy of a stored fact, which is the ruling
      sd:603 already recorded.

      Pack commit: delete `dashboard/store.py`, `dashboard/github.py`,
      `dashboard/jira.py`, `cmd_index` (`bin/sd-dashboard:32`) and the `index`
      verb. This is the step that closes the criterion 2 problem outright, because
      `sqlite3.connect` (`dashboard/store.py:89`) and `sqlite3.connect`
      (`dashboard/store.py:94`) are the two connections the port could not carry.

      **Four live callers import those modules, and three of them are not the
      dashboard.** Each was found by grepping importers rather than by reading the
      deletion list, and each is edited in this same pack commit or the tree does
      not import:

      | Caller | Line | What it needs |
      |---|---|---|
      | `dashboard/server.py` | `:43` | imports `collect` and `store`; survives to step 6, so this commit drops both from the import line and the endpoints behind them. |
      | `bin/sd-dashboard` | `:29` | `from dashboard import collect, store` (step 1 removed `server`) — `store` goes with `issue_lines` (`bin/sd-dashboard:56`) and the `index` verb this step deletes. |
      | `bin/sd` | `:2728` | `from dashboard.collect import discover_checkouts, repo_root`, inside `sd plugin list --fleet`. **This one is not a dashboard file and nothing in this plan would otherwise touch it.** |
      | `bin/sd-trackers` | `:42` | `from dashboard import github, jira`. The whole tool is built on the two modules this step deletes, so it retires in the same commit or it is a broken entry point. |

      **`dashboard/collect.py` is not deleted here. It moves to step 5**, which is
      where the repository collector it holds is ported. An earlier draft listed it
      in both steps; deleting it here would take `discover_checkouts` and
      `repo_root` out from under `bin/sd` and leave step 5 with a Repos view and no
      collector to compare against.

      Pin commit, its own pull request, **and it lands before the pack commit
      above, not after it.** The order in this step is: system commit, library
      merge, pin, venv reinstall, restart PID 37095, verify the new view on :8767,
      *then* the pack deletion. A merged system commit is not a running view while
      PID 37095 serves the old library, so deleting the pack's tracker path first
      would leave the operator with neither. `.github/workflows/tests.yml` moves to
      the squash SHA of the system commit. **And the pin is not only CI's.** The
      running dashboard's own `/health` reports its `library` as
      `/Users/sven/repos/platypeeps/sd-ai-command-pack/.venv/lib/python3.13/site-packages/sd_db/__init__.py`
      — measured on pull request #898 at `d0ad6542`. The surviving dashboard
      imports `sd_db` from *the pack's* virtualenv, so a system-side view that
      needs a newer library is gated on the pack's venv being reinstalled, not
      just on CI going green. That is the sequence stated above, and the pack
      deletion is the last thing in it.

      Verify: on :8767, a Jira row shows `LOG-23818` and not `LOG`, and a GitHub
      row shows its number — the same assertion sd:361 step 7b makes about the
      page it replaces. `select tracker, count(*) from shadow group by tracker`
      returns both trackers. Then the criterion 2 grep over
      `/Users/sven/repos/system/local-project-dashboard/` still returns exactly
      one hit and that hit is still the name of
      `test_no_sqlite3_connect_in_the_dashboard` at
      /Users/sven/repos/system/local-project-dashboard/tests/test_markup.py:188 —
      asserted **after** the views arrive, because the whole risk of this step is
      that a ported view brings a connection with it. Then
      `~/.cache/sd-ai-command-pack/index.sqlite` is deleted by hand and both
      dashboards still work, which is what "the index is a cache" has always
      claimed and what nothing has ever checked.

- [ ] **5. Repos and Sessions.** System commit, then pack commit deleting
      `dashboard/sessions.py`, `dashboard/skills.py` and `dashboard/collect.py` —
      which is the repository collector, named as a path here because step 4's
      draft also claimed it and two steps cannot delete one file. Cheapest of the
      ports and deliberately **not** first: these collectors open no database, so
      criterion 2 is not in play, and doing them early would have burned the
      ceiling headroom that steps 3 and 4 need. `collect.py`'s docstring is the
      authority for the claim that nothing here is stored — "Nothing here is
      stored as an input to anything" — and it is still in the tree to be read at
      this point.

      **`dashboard/server.py` imports all three and survives to step 6, so this
      commit edits it too.** `sessions` and `skills` arrive on the import line at
      `dashboard/server.py:43`; the calls are `sessions.fleet_worktrees` at
      `dashboard/server.py:472`, `sessions.collect_sessions` at `:478` and
      `skills.collect_skills` at `:485`. The `/api/sessions` and `/api/skills`
      endpoints go with their modules, and `/api/now` loses the session rows it
      merges at `:472`. `bin/sd`'s `from dashboard.collect import ...`
      (`bin/sd:2728`) is the other caller and `sd plugin list --fleet` loses its
      fleet walk in this commit. Deleting the three modules and leaving the server
      is a pack that does not import, and the next step is the one that would have
      noticed.
      Verify: the system page lists the same repositories and worktrees the pack
      page listed, compared row for row on one capture taken **before** step 5's
      system commit — a comparison nobody can make afterwards, which is why the
      capture is part of the step and not of its verification.

- [ ] **6. The Now ranking, last.** System commit, then pack commit deleting
      `dashboard/now.py`, `dashboard/actions.py`, `dashboard/work.py`,
      `dashboard/server.py` and `dashboard/app.js`. Last because Now is the merge
      of every source above and cannot be correct until each is in place, and
      because the rank-0 row step 3 gave up belongs here: a collector that goes
      dark has to raise a row in the merged view or the trade step 3 recorded was
      never honoured.

      **`deliver`'s successor is a prerequisite of this step, not a question left
      inside it.** `deliver` (`dashboard/work.py:232`) is one of the two facts the
      two dashboards share on disk, and it is a **write**; a write path deleted
      without a successor is a capability lost by accident. The earlier draft
      offered "or the operator uses `sd work deliver` from the CLI" as the fallback
      — **and there is no `work` verb in `bin/sd`.** Measured: `bin/sd` names
      `deliver` nowhere outside a docstring at `bin/sd:6`, so that fallback was a
      verb this plan invented. The successor is therefore the system page's own
      control, built in this step's **system** commit, and the pack commit does not
      start until it exists. Acceptance is mechanical and it is listed in the
      verification below: a delivery made through the successor writes a
      `status_change` note naming `DELIVERED_BY` (`dashboard/work.py:229`). If the
      decision is instead to build a CLI verb, that verb is a prerequisite item and
      this step waits on it; what it may not be is undecided at the moment
      `work.py` is deleted.
      Verify: `band` (`dashboard/app.js:547`)'s severity mapping is reproduced on
      the system page, asserted against the same rank numbers; a fixture
      collector that exits non-zero produces a visible row in the merged view;
      and `deliver`'s chosen successor — the system control this step's system
      commit builds, per the prerequisite above — still records a `status_change`
      note naming `DELIVERED_BY` (`dashboard/work.py:229`).

- [ ] **7. `dashboard/` is deleted, and the ceilings retire in the same commit.**
      **Read this before starting step 2.** Three tests interlock and the
      interaction decides how steps 3 to 6 are written:

      (a) `test_the_code_ceiling_is_paid_for_in_kind`
      (`tests/test_loc_caps.py:522`) asserts
      `DASHBOARD_CODE_CAP - code_line_count(tracked("dashboard")) <=
      DASHBOARD_CODE_SLACK`, which is 29 against a live gap of 2. **Every pack
      commit here that deletes code must lower `DASHBOARD_CODE_CAP` in the same
      commit** or this test fails. A removal leaves headroom of 29 whatever its
      size, so it earns 27 lines and no more — but the *obligation* to lower
      begins at 28 removed lines, because a gap of `2 + N` stays legal while
      `2 + N <= 29`. Every deletion in this plan is far past that threshold, which
      is why the rule reads as unconditional here; `prd.md` states the threshold
      itself, for the reader who applies the rule to a smaller removal elsewhere.

      (b) `test_each_ceiling_is_the_last_value_its_history_records`
      (`tests/test_loc_caps.py:552`) requires each new value appended to
      `CEILING_HISTORY` (`tests/test_loc_caps.py:287`) in the same commit.

      (c) `test_the_recorded_history_is_raises_only`
      (`tests/test_loc_caps.py:577`) asserts the downward count is zero, at
      `tests/test_loc_caps.py:590`. `ceiling_moves` (`tests/test_loc_caps.py:331`)
      returns `(29, 26, 0)` today, and **the first append from (b) makes it red.**
      Its docstring says that is deliberate: it fails "the day a ceiling finally
      comes down", and the fix is to rewrite the paragraph in the module docstring
      at `tests/test_loc_caps.py:33-46` that reasons from there being none.

      **That test has a second assertion and it breaks too.**
      `tests/test_loc_caps.py:598` asserts `upward == values -
      len(CEILING_HISTORY)` — every recorded move is a raise, which is true only
      while nothing has ever come down. At `(30, 26, 1)` it reads `26 == 30 - 3`,
      and that is false: 27 moves, 26 up and 1 down. The invariant it is really
      protecting is that no ceiling repeats a value, so the repair is
      `upward + downward == values - len(CEILING_HISTORY)`, and its message — "a
      row that moves nothing is a raise nobody made" — widens the same way. A
      preparatory commit that rewrites only the `downward == 0` assertion lands red
      on this one, reporting a repeated ceiling value that never happened.

      So (c) goes red on **step 3**, not on step 7. The order that follows:
      step 3's pack commit is preceded by its own preparatory commit — a new
      R-id — that rewrites (c)'s assertion and the R11-D41 paragraph and makes a
      recorded fall legal; only then do steps 3 to 6 lower the cap as they go.
      The clause R11-D24 wrote, "a cap is never raised in the pull request that
      crossed it", applies unchanged in the mirror: **a ceiling is never lowered
      in the pull request that needed it.**

      Then this step: delete the remaining tracked files under `dashboard/` and
      `bin/sd-dashboard` itself, and in the same commit delete `DASHBOARD_CAP`
      (`tests/test_loc_caps.py:223`), `DASHBOARD_CODE_CAP`
      (`tests/test_loc_caps.py:231`), `DASHBOARD_CODE_SLACK`
      (`tests/test_loc_caps.py:239`) and the four tests that read them —
      `test_the_dashboard_stays_under_its_ceiling`
      (`tests/test_loc_caps.py:487`),
      `test_the_dashboard_code_stays_under_its_own_ceiling`
      (`tests/test_loc_caps.py:500`), (a) and (b) — **keeping both
      `CEILING_HISTORY` entries**, in the shape `BIN_CAP` retired at R11-D48 and
      for the reason that entry's own comment gives.

      **The empty directory breaks more than the caps, and all of it retires in
      this commit.** Enumerated from the tree rather than recalled:

      - `Makefile:45` passes `dashboard` to Ruff and `Makefile:46` passes it to
        mypy, so `make check` fails on a path that no longer exists.
      - `tests/test_code_health.py` still holds `dashboard/` baseline entries for
        whatever steps 3 to 6 have not already retired, and
        `test_every_baseline_entry_still_earns_its_place` fails on each one.
      - **Twenty-six test files name `dashboard`**, counted with
        `grep -ln dashboard tests/*.py`. Those whose whole subject is deleted go
        with it — `tests/test_sd_dashboard.py`, `tests/test_sd_dashboard_index.py`,
        `tests/test_dashboard_actions.py`, `tests/test_dashboard_deliver.py`,
        `tests/test_dashboard_now.py`, `tests/test_dashboard_sessions.py`,
        `tests/test_dashboard_skills.py`, `tests/test_dashboard_work.py`,
        `tests/test_sd_ledger.py` and `tests/test_sd_trackers.py`. The rest only
        mention the path and are edited instead. **Re-run the grep inside the
        commit rather than working from this list**, because steps 3 to 6 will have
        moved some of it.

      Verify from the enumeration and not the list: `make check` exits 0, and
      `grep -ln dashboard tests/*.py` returns only files that name it deliberately
      in prose.

      One commit, forced rather than chosen: both cap tests open with
      `self.assertTrue(paths, "dashboard/ enumeration matched no tracked files")`,
      so they fail on the empty enumeration whatever the constants say. A commit
      that deletes the directory and leaves the tests is red on a message about
      enumeration, which reads like a tooling fault and is not one.

      Verify: `python -m unittest tests.test_loc_caps` passes and
      `CEILING_HISTORY` still holds all three entries, `BIN_CAP` included;
      `git ls-files dashboard/ bin/sd-dashboard` prints nothing;
      `grep -rn "DASHBOARD_CAP\|DASHBOARD_CODE_CAP\|DASHBOARD_CODE_SLACK" tests/
      bin/` prints only the `CEILING_HISTORY` keys; `bin/sd-docs-lint` exits 0
      and `python -m unittest tests.test_doc_citations` passes, which requires the
      enumeration below to have been done rather than discovered.

      Mutation: delete the directory and keep the two cap tests; both redden on
      the enumeration assertion, which is the proof the one-commit rule is real
      and not a preference. Revert and `diff -q` reports the tree identical.

- [ ] **8. The citation sweep, enumerated rather than discovered.** Deleting
      `dashboard/` turns every live anchored citation into it from `compared` to
      `target-missing`, which `test_the_red_buckets_are_empty` fails on. The
      enumeration, run once before step 3 and re-run before step 7 — filtering on
      **both** deleted paths, because step 7 deletes `bin/sd-dashboard` as well and
      28 anchored `bin/sd-dashboard:` citations exist today, in live documents as
      well as archived ones (sd:361's three files carry them):
      `python -c "from tests.test_doc_citations import classify; [print(r.doc, r.path, r.start, r.reason) for r in classify() if r.reason == 'compared' and (r.path.startswith('dashboard/') or r.path == 'bin/sd-dashboard')]"`.
      A sweep filtered on `dashboard/` alone prints nothing, passes, and leaves
      `test_doc_citations` red on the bin path.
      Archived documents are not edited: an archive citing a deleted file is
      `archived-stale`, which is reported and fails nothing, and this step does
      not touch `docs/work/archive/`.
      Verify: the command above prints nothing after step 7, and
      `python -m unittest tests.test_doc_citations` prints its census with
      `target-missing=0`. Each live document rewritten cites the system-side
      location or says the behaviour was dropped, matching the dispositions
      `design.md` records for `app.js` — a citation repointed at a file that no
      longer carries the behaviour passes the gate and lies to the reader, which
      is the one failure this step cannot detect mechanically.

- [ ] **9. Close the items.** Note on sd:719 with the measurements re-run; sd:705
      closed as answered by deletion, naming step 1 as the answer to its port and
      label halves and #898 as the answer to its comment half. sd:452's note
      #1124 quoted the stale comment as a reason to build a screen elsewhere; a
      note saying so closes the loop that misdirection opened.
      Verify: `bin/sd store item 705` shows the closing note and a status of
      `done`; `bin/sd store item 719` shows the measurement note.

## Verification

**Named before the work starts.**

- **The negative that matters most is step 1's.** After `serve` and `install` are
  gone, `launchctl list | grep com.sven.sd-dashboard` still prints the PID it
  printed before (37095 at planning, 76442 when step 1 landed) and the plist's `ProgramArguments[0]` is still the system `dashboard.sh`. Asserted
  before and after, because "it still works" is only evidence if the before was
  recorded.
- **The ceiling claim is proved by a failure, not by a pass.** The step-3
  preparatory commit is correct only if `test_the_recorded_history_is_raises_only`
  is red *before* it and green *after*, with `ceiling_moves()` printing
  `(30, 26, 1)`. A plan that only shows the green half has not shown that the
  rewrite was necessary.
- **The two-commit ordering is a review habit and is not claimed as a gate.** No
  test in either repository can see both pages. Steps 2 to 6 each name the system
  commit first and the pack commit second, and a reviewer checks the order on the
  pull request pair. Recorded as accepted gap 1 in `design.md`.
- **Every deletion is proved by an enumeration, never by a search for what was
  typed.** `git ls-files dashboard/` for the directory,
  `classify()` for the citations, `sd plugin list --json` for the manifest keys,
  `grep -rn "com.sven.sd-dashboard"` for the label. Each asks the filesystem or
  the registry rather than confirming a string the author already knew.

**What cannot be verified from either repository, stated rather than invented:**

- That the operator reads no view during a step's two-commit window.
- That the system page's 18-second per-view wait is the right number where the
  loader argued 5. The loader's five collector timings are quoted from its
  docstring and were **not** re-measured for this plan.
- That a repointed citation names a file that actually carries the behaviour it
  claims. The gate checks the symbol is at the line; nothing checks that the
  symbol still does the thing.
- That `queues` can be rendered without an asset pipeline. The system package's
  docstring refuses one and this plan takes that as a constraint.
