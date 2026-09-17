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
(in `tests/test_loc_caps.py`, retired at sd:719 step 7) green — and every deletion here is larger than
that. The total cap is 4,600 over a directory that only shrinks, so it is never
crossed on the way down.

Step 1 is outside all of this: it deletes lines from `bin/sd-dashboard`, which has
had no ceiling since R11-D48, and nothing under `dashboard/`. Step 2 deletes
nothing. **The first lowering is step 3's, it is where the history test goes red,
and it needs a preparatory commit of its own:** read step 7's first paragraph
before starting step 2.

## Step checklist

- [x] **0. sd:361, to completion.** Its own `implement.md` is the plan and this
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

      **Done: sd:361 closed on 2026-09-16, and its closing commit is pack pull
      request #988, squash `2eafa78b`, which ticked its steps 8 and 9.** All
      ten lines of its checklist are `[x]` at that commit. The verification
      above, re-run at that commit from the pack's venv:
      `python -c "import sd_db; print(sd_db.TRACKERS)"` prints
      `('github', 'jira')`, and the installed library reports `SCHEMA_VERSION`
      9 where the paragraph above measured 8. `git ls-tree a5347185 -r
      --name-only | grep shadow_jira` in `/Users/sven/repos/system` still
      returns both paths. The measurement behind steps 8 and 9 is sd:361's
      note 2522; the owner's check of the issues tab, LOG-23929 in the jira
      section, is its note 2542. Both are recorded on that item and not
      restated here.

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

      `collect` and `store` **stayed** in the `dashboard` import at this step:
      `cmd_index` and `issue_lines` (both in `bin/sd-dashboard`, retired at
      sd:719 step 4) still used them, and step 4 still read the cache the
      `index` verb filled until its own pack commit.

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
      `launchctl list | grep com.sven.sd-dashboard` still lists the label
      after the change; the PID it prints beside the label is the PID
      `lsof -nP -iTCP:8767 -sTCP:LISTEN` prints for the listener, the two read
      at one moment, which is what ties the port to the LaunchAgent; and
      `plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/com.sven.sd-dashboard.plist`
      still prints the system `dashboard.sh` as element 0 — asserted **after**
      the change and before it, so the pair is evidence rather than a hope. The
      PID is never compared across runs: it was 37095 when this plan was
      measured and 76442 when step 1 landed, and every owner-approved restart
      changes it (review-909 N3). Then
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

- [x] **2. `queues` becomes a native system view.** System repository only;
      nothing in the pack changes. When this step was planned, `queues` was the
      one of the six legacy views with no system-side path — the other five
      already rendered, four through the `collect` at
      /Users/sven/repos/system/local-project-dashboard/sd_dashboard/reports_screen.py:83
      and `ports` in-process through the `_collect` at
      /Users/sven/repos/system/local-project-dashboard/sd_dashboard/ports_screen.py:32.
      The plan left open whether `queues` would join `VIEWS` or take its own
      screen, because it reads module state in `collectors.py` rather than a
      `collect_*` function; the system repository decided, and the landed
      state below is that it joined `VIEWS` as the fifth entry.

      Verify: the system suite runs `Ran 307 tests` or more — it prints
      `Ran 306 tests ... OK` today — and one new case asserts the `queues` view
      renders rows from a fixture and that a collector failure surfaces on the
      screen rather than as an empty table. The pack is untouched, so
      `git status` in the pack is clean, which is the control that this step did
      not leak across the boundary.

      **Landed as system pull request #335, squash `0b5394ae`.** `queues`
      joined `VIEWS` in `reports_screen.py` with a 5-second view budget, and two
      new cases in `tests/test_resource_reports.py` cover the fixture rows and
      the on-screen failure. The dashboard suite ran `Ran 336 tests ... OK` on
      that head.

- [x] **3. The plugin loader retires, and the manifest loses two keys.** Every
      `dashboard/` and `tests/test_code_health.py` line number in this step's
      plan is as of `a8295266`, where it was measured. The step has landed, and
      at `2eafa78b` the lines it names are deleted or have moved, except two:
      `dashboard/server.py:43` is still the import line, now without
      `plugins`, and the `bounded_run` entries at `:647` and `:665` of
      `tests/test_code_health.py` still stand, repointed to
      `dashboard/actions.py` as the step said. System
      commit first, and it is not nothing: **remove the `tabs` and `tile` keys
      from `/Users/sven/repos/system/sd-plugin.json`.** They are the system half
      of this step because they advertise a discovery contract to the registry,
      so they must stop advertising it before the loader that honours them is
      deleted — the same system-first order every other step follows, and an
      earlier draft had this step alone running backwards. The `actions` key
      stays: `sd plugin list --json` still reports it and the four queue-open
      actions are not tabs. **They stay in the manifest and leave every
      dashboard**, which is the third give-up recorded below.

      Pack commit: delete `dashboard/plugins.py` (719 lines, 357 code), the
      `plugin-tabs` span and the `plugin-panels` div in `PAGE`
      (in `dashboard/server.py`, retired at sd:719 step 6), and the loader's rows from the Now merge in
      `dashboard/now.py`.

      **The plugin half of `app.js` is `drawPlugins` and `panelId`. It is not
      `enhance`, and deleting `enhance` here breaks the page on load.** The
      disposition table in `design.md` had this wrong and the import graph
      corrects it:

      | Function | Step | Why |
      |---|---|---|
      | `drawPlugins` (in `dashboard/app.js`) | **3** | It polls `/api/plugins`, which this step's `server.py` edit removes. Delete it *with all three of its call sites* — the `drawPlugins()` call, `setInterval(drawPlugins, 10000)`, and its entry in the redraw list — or the page polls a deleted endpoint every ten seconds. `drawPlugins` [absent: step 3 shipped and removed it from dashboard/app.js with all three call sites; nothing in the file names the symbol today]. |
      | `panelId` (in `dashboard/app.js`) | **3** | Plugin-only, and its single caller is `drawPlugins` (in `dashboard/app.js`). |
      | `enhance` (in `dashboard/app.js`) | **6**, with `app.js` | **Not plugin-only.** `for (const [, panel] of STATIC) enhance(...)` at `dashboard/app.js:426` runs it over all seven static panels at startup. `drawPlugins` calling it at `:745` is the *second* caller, not the only one. Deleting it in step 3 is an uncaught `ReferenceError` at load, and it silently takes the skills-table filter with it. Step 3 removes the call at `:745` and nothing else. |
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
      rather than from the file names: `markup` is imported by
      `dashboard/plugins.py` and **nowhere else** under `dashboard/`, so it is
      the loader's and dies with it. And `server.py` imports `plugins` at
      `dashboard/server.py:43` while surviving until step 6, so this step must
      drop `plugins` from that import line and the endpoint behind it, or step 3
      lands a module that fails to import. `tests/test_dashboard_markup.py` goes
      with `markup.py`. This is the step's real hazard and it is invisible in a
      plan that groups files by what they are for.

      **Three things this step gives up, all recorded rather than silently
      spent.** The first two were priced before it landed (design, "Pricing the
      two options"): a third party declaring a dashboard tab, which has no instance — the registry holds two
      plugins and only `sys` declares tabs — and the rank-0 alert row a dark
      collector used to raise, which step 6 rebuilds on the system side. That
      second one is a gap **between step 3 and step 6, and not after it**: in the
      window a dark collector shows as the system side's per-screen `ValueError`
      and nothing more. `design.md` records the same boundary, because an
      indefinitely accepted gap there and a required row here would be two
      documents asking one commit for opposite things.

      **A third, recorded on 2026-09-13 after the step landed** (review-928 N1,
      owner decision). The four `sys/queue-*` actions — `queue-blog`,
      `queue-tip`, `queue-topic` and `queue-watch` — were buttons in the pack
      dashboard's run strip. Step 1 had already stopped serving that page, so
      they were unseen from then; this step removed them from its catalog too,
      which leaves them reachable from no dashboard. The pack commit reduced
      `catalog` (in `dashboard/actions.py`, retired at sd:719 step 6) to `RUN_ALLOWLIST`, so
      `/api/actions` offers `index` alone and a POST naming `sys/queue-blog` is
      a 404. Nothing replaced them, for two reasons: the pack dashboard is not
      served, because step 1 removed `serve`, and no module of the system
      dashboard reads the manifest. They remain reachable as
      `dashboard.sh queue-open <q>` in the system repository and in
      `sd plugin list`. The plan said to reduce the catalog and did not list
      what that cost; this paragraph is the listing, and `design.md` carries the
      same entry.

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
      (`source:tests/test_code_health.py::COMPLEX`) and `LONG` (`source:tests/test_code_health.py::LONG`)
      — the entries themselves are at `:647` and `:665` — and the four
      `dashboard/markup.py::Filter.handle_*` methods in `DYNAMIC`
      (`source:tests/test_code_health.py::DYNAMIC`), entries `:676` to `:679`.
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

      **Landed as system pull request #342, squash `95568487`, then pack pull
      request #928, squash `68fa908c`.** The system manifest's `dashboard`
      block keeps `actions` only; its dashboard suite ran
      `Ran 346 tests ... OK`. The pack commit deleted `dashboard/plugins.py`,
      `dashboard/markup.py` and their tests, moved `bounded_run` into
      `dashboard/actions.py`, and lowered `DASHBOARD_CODE_CAP` from 2,328 to
      1,850 against 1,848 measured, the first fall `CEILING_HISTORY` records
      (R11-D49, pull request #922). `AMBIGUOUS_CEILING` fell from 154 to 145 and
      `STRANDED_RULE_IDS` from 23 to 20. CI was green on head `45752934`, and
      review-928 found nothing blocking. Its N1 is the third give-up above. Its
      N5, three line citations into files this step deleted, was fixed in the
      tick's fix round by dropping the line numbers, because step 8's sweep
      filters on `compared` citations under `dashboard/` and would not have
      found them; `prd.md`'s Log lists the three.

- [x] **4. PRs and Issues are served from `sd_db.shadow`; the legacy index
      retires.** System commit: the tracker views read `tracker_items` and
      `tracker_freshness` from `sd_db`, which already take a tracker argument, and
      derive a Jira row's key as `url.rpartition("/")[2]` — the rule sd:361 step
      7b writes into `where` (in `dashboard/app.js`), carried across rather than
      reinvented. No new column: the key is the last path segment of the URL, and
      a `key` column would be a second copy of a stored fact, which is the ruling
      sd:603 already recorded.

      Pack commit: delete `dashboard/store.py`, `dashboard/github.py`,
      `dashboard/jira.py`, `cmd_index` (in `bin/sd-dashboard`, retired at this
      step) and the `index` verb. This is the step that closes the criterion 2
      problem outright, because the read and the write `sqlite3.connect` in
      `connect` (in `dashboard/store.py`, retired at this step) are the two
      connections the port could not carry.

      **Four live callers import those modules, and three of them are not the
      dashboard.** Each was found by grepping importers rather than by reading the
      deletion list, and each is edited in this same pack commit or the tree does
      not import:

      | Caller | Line | What it needs |
      |---|---|---|
      | `dashboard/server.py` | `:43` | imports `collect` and `store`; survives to step 6, so this commit drops both from the import line and the endpoints behind them. |
      | `bin/sd-dashboard` | `:29` | `from dashboard import collect, store` (step 1 removed `server`) — `store` goes with `issue_lines` (in `bin/sd-dashboard`, retired at this step) and the `index` verb this step deletes. |
      | `bin/sd` | `:2729` | `from dashboard.collect import discover_checkouts, repo_root`, inside `sd plugin list --fleet`. **This one is not a dashboard file and nothing in this plan would otherwise touch it.** |
      | `bin/sd-trackers` | `:42` | `from dashboard import github, jira`. The whole tool is built on the two modules this step deletes, so it retires in the same commit or it is a broken entry point. |

      **`dashboard/collect.py` is not deleted here. It moves to step 5**, which is
      where the repository collector it holds is ported. An earlier draft listed it
      in both steps; deleting it here would take `discover_checkouts` and
      `repo_root` out from under `bin/sd` and leave step 5 with a Repos view and no
      collector to compare against.

      Pin commit, its own pull request, **and it lands before the pack commit
      above, not after it.** The order in this step is: system commit, library
      merge, pin, venv reinstall, an owner-run restart of the
      `com.sven.sd-dashboard` LaunchAgent, verify the new view on :8767,
      *then* the pack deletion. A merged system commit is not a running view while
      the process on :8767 serves the old library, so deleting the pack's tracker path first
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

      **Landed as system pull request #411, squash `fe556f4`, then the pin,
      pack pull request #999 (`c6879551`, `ref: 4b240d28`), then the pack
      deletion, this pull request.** Operations > Trackers on :8767 was
      verified by the owner before the deletion (sd:719 note 2579). The pack
      commit deleted `dashboard/store.py`, `dashboard/github.py`,
      `dashboard/jira.py`, `bin/sd-trackers` and their two test modules, and
      left `bin/sd-dashboard` with no verb at all: `sd-dashboard index` exits 2
      with the parser's usage, and the file itself goes at step 7. The four
      callers in the table above each went one way: `dashboard/server.py` lost
      `store` from its import, the `/api/prs` and `/api/issues` routes, the
      two tabs in `PAGE` and the `app.js` views that polled them; the
      `/api/now` payload no longer carries pull request rows, so `pr_rows`
      (in `dashboard/now.py`, retired at sd:719 step 6) has no caller until step 6 decides
      Now; `bin/sd` was not touched, because `collect.py` stays; and
      `dashboard/collect.py` lost `refresh_issues`, the one function that
      imported the three modules, which the brief's importer grep did not see
      because the import is relative. `bin/sd-status` lost the `store` import
      and the fallback in `issues_section` that read the index when no shared
      database existed; `_database_issues`
      (`source:bin/sd-status::_database_issues`) is the only reader, and with
      no database the section says `available: False` and names `sd_db`
      rather than `sd-dashboard index`. Its section heading and three labels
      still say "the index" and "dashboard index"; they sit inside a hunk
      fix-431-d holds, and are residue for that lane or the step 6 sweep.
      `DASHBOARD_CODE_CAP` fell from 1,850 to 1,183 against 1,183 measured,
      667 code lines gone under `dashboard/` (`github.py` 190, `jira.py` 202,
      `store.py` 128, `app.js` 92, `server.py` 30, `collect.py` 25), the
      second fall `CEILING_HISTORY` records; `DASHBOARD_CAP` did not move.
      `AMBIGUOUS_CEILING` fell from 142 to 124. `skills/sd-plan/SKILL.md`'s
      `--from gh:`/`jira:` now resolves against the shadow rows, and a
      reference the shadow does not hold is pasted by hand. Citations into
      the deleted files on this item's three pages and on sd:361's pages
      (still live, not archived) were rewritten in prose; `prd.md`'s Log
      lists the count.

- [x] **5. Repos and Sessions.** System commit, then pack commit deleting
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
      commit edits it too.** `sessions` and `skills` arrive on the import line of
      `dashboard/server.py` (a file retired at sd:719 step 6; the line numbers
      this passage carried were as of `a8295266`); the calls are
      `sessions.fleet_worktrees`, `sessions.collect_sessions` and
      `skills.collect_skills` in the same file. The `/api/sessions` and `/api/skills`
      endpoints go with their modules, and `/api/now` loses the session rows it
      merges at `:490`. `bin/sd`'s `from dashboard.collect import ...`
      (`bin/sd:2729`) is the other caller and `sd plugin list --fleet` loses its
      fleet walk in this commit. Deleting the three modules and leaving the server
      is a pack that does not import, and the next step is the one that would have
      noticed.
      Verify: the system page lists the same repositories and worktrees the pack
      page listed, compared row for row on one capture taken **before** step 5's
      system commit — a comparison nobody can make afterwards, which is why the
      capture is part of the step and not of its verification.

      **Landed as system pull request #427, squash `051d931a`, then the pack
      deletion, this pull request.** The capture was taken first: at
      2026-09-16T22:19:37Z, pack `b4211959`, the s5sys lane called
      `collect.build_state` and `sessions.collect_sessions` in-process — 81
      repos (3 dirty, 2 ahead), 14 worktrees across 4 checkouts — and compared
      the rows against `sd_dashboard/fleet.py` twelve minutes later: 81 rows
      against 81, 78 identical in all eleven fields and 7 cells on 3 rows
      changed by commits and fetches git's reflog dates to the gap; 13
      worktrees against 14, the one missing row a lane whose worktree was
      removed between the reads. Operations > Repos and Sessions on :8767 is
      that lane's commit, read as a budgeted child (12 s, 64 KB). The pack
      commit deleted `dashboard/collect.py`, `dashboard/sessions.py`,
      `dashboard/skills.py` and their two test modules, the `/api/state`,
      `/api/sessions` and `/api/skills` routes, the state cache in front of
      the first, the three tabs in `PAGE` and the three views in `app.js` that
      polled them. `discover_checkouts` did not go: `dashboard/work.py` imports
      it as `from .collect import discover_checkouts`, a fourth import shape
      the step's grep did not name and step 4's `ast` walk read as an import
      of the *symbol*, so the function moved into `work.py` (its one caller
      left, with `checkout_of`) and the walk in `tests/test_sd_dashboard.py`
      now reads `from .<module> import` as naming the module. `/api/now`
      still answers, with no fleet rows and no worktree rows: `backbone_rows`
      and `session_rows` (in `dashboard/now.py`, retired at sd:719 step 6) join
      `pr_rows` uncalled until step 6 decides Now on the system page, and the
      pack's Now shows the ack filter over an empty merge. `dashboard/actions.py`
      stays whole: its only mention of `/api/state?refresh=1` is the docstring
      contrasting this server with the one it replaced, and the `/api/actions`
      and `/api/run` routes it serves are step 6's. **Two sentences in the
      step text above were stale when this landed.** `bin/sd` has no
      `--fleet` and no `dashboard.collect` import — `grep -n
      'dashboard.collect\|--fleet' bin/sd` at `85c4fa1b` returns only a
      comment naming `local-project-dashboard/collectors.py` — so `sd plugin
      list --fleet` lost nothing here, and the four line numbers the step
      gives into `dashboard/server.py` (43, 490, 495, 502) had already moved
      by step 4's deletion: at the base the import line stood at line 43 and
      the three calls at lines 462, 467 and 474. `bin/sd-dashboard` had no verb and no
      import to lose. `DASHBOARD_CODE_CAP` fell from 1,183 to 866 against
      866 measured, 317 code lines gone under `dashboard/` (`collect.py` 86,
      `sessions.py` 66, `skills.py` 50, `app.js` 102, `server.py` 26, less
      the 13 of `discover_checkouts` that moved into `work.py`), the third fall
      `CEILING_HISTORY` records; `DASHBOARD_CAP` did not move.
      `AMBIGUOUS_CEILING` fell from 124 to 121. The one `path:line` into a
      deleted file in a live document, lines 45-74 of `dashboard/sessions.py`
      cited on
      `docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md`,
      was pinned at `85c4fa1b` in prose; `README.md` and
      `AGENTS.md` name none of the three views. The :8767 pages after
      `~/deploy-sd-db.sh` are the owner's to read and were not read by this
      commit.

- [x] **6. The Now ranking, last.** System commit, then pack commit deleting
      `dashboard/now.py`, `dashboard/actions.py`, `dashboard/work.py`,
      `dashboard/server.py` and `dashboard/app.js`. Last because Now is the merge
      of every source above and cannot be correct until each is in place, and
      because the rank-0 row step 3 gave up belongs here: a collector that goes
      dark has to raise a row in the merged view or the trade step 3 recorded was
      never honoured.

      **`deliver`'s successor is a prerequisite of this step, not a question left
      inside it.** `deliver` (in `dashboard/work.py`, retired at sd:719 step 6) is one of the two facts the
      two dashboards share on disk, and it is a **write**; a write path deleted
      without a successor is a capability lost by accident. The earlier draft
      offered "or the operator uses `sd work deliver` from the CLI" as the fallback
      — **and there is no `work` verb in `bin/sd`.** Measured: `bin/sd` names
      `deliver` nowhere outside a docstring at `bin/sd:6`, so that fallback was a
      verb this plan invented -- until #802 landed it (see the landing paragraph
      below). The successor is that CLI verb, `sd work deliver <item> <full-sha>`
      (`source:bin/sd_work.py`), and the pack commit does not start until it
      exists. Acceptance is mechanical and it is listed in the verification
      below: a delivery made through the successor writes a `status_change`
      note reading `delivered at <commit> on <ref>` through
      `sd_db.progress.deliver_work`, whose `who=` names the deliverer; the
      system commit builds no page control, and `DELIVERED_BY` (in
      `dashboard/work.py`, retired at sd:719 step 6) retires with the file.

      **6a. The capture form's followup path, in this step's system commit.**
      sd:730 closed on 2026-09-16 (its note 2527), and its owner decision (note
      1844) sent one piece of scope here: filing a standalone followup item
      from the dashboard. The capture form is a system file,
      `local-project-dashboard/sd_dashboard/static/dashboard.js`, whose
      `var noteKinds = ["followup", "comment", "question", "decision", "proposal"]`
      still owns the word `followup` as a note kind, and the form has no path
      to file a followup *item*, the kind `sd task add --kind followup`
      creates. The system commit adds that path; the sub-step has no other
      completion, and the word may not go on meaning one thing on the form and
      another in the store. Verify: a filing through the form produces an item
      of kind `followup`, and the note-kind path still produces a note.
      Verify: `band` (in `dashboard/app.js`)'s severity mapping is reproduced on
      the system page, asserted against the same rank numbers; a fixture
      collector that exits non-zero produces a visible row in the merged view;
      and `deliver`'s chosen successor -- the CLI verb `sd work deliver`, per the
      prerequisite above -- still records a `status_change` note reading
      `delivered at <commit> on <ref>`.

      **Landed as system pull request #428, squash `e43444f5`, then the pack
      deletion, this pull request.** The capture was taken
      first: at 2026-09-17T00:27:40Z, pack `85c4fa1b`, the s6sys lane called
      `dashboard.now` in-process over the live fleet and the live shadow
      table, read-only -- 5 rows (two `ahead` at rank 3, three `dirty` at
      rank 4), 0 pull request rows, 0 abandoned -- and compared them against
      `sd_dashboard/now_screen.py` at system `d3a0255` twenty minutes later:
      the same 5 ids at the same ranks, one `dirty` count moved by a commit
      the checkout's reflog dates to the gap. Today on :8767 opens with a Now
      section, rows from `/api/now` painted by the system's `dashboard.js`,
      `band` in Python and asserted over ranks 0..5, a rank-0 row per dark
      collector, and 6a's `Followup item` path on the capture form; that is
      the s6sys lane's commit and its report holds the comparison. The pack
      commit deleted `dashboard/now.py`, `dashboard/actions.py`,
      `dashboard/work.py`, `dashboard/server.py`, `dashboard/app.js` and
      their four test modules, `tests/test_dashboard_now.py`,
      `tests/test_dashboard_work.py`, `tests/test_dashboard_deliver.py` and
      `tests/test_dashboard_actions.py`; no test in them exercised a
      survivor, so nothing moved. `tests/test_sd_ledger.py` lost the four
      classes that drove `dashboard/server.py` -- an importer the step's grep
      did not name, because `git grep -E` on this platform has no `\b` and
      `dashboard.server` was matched by nothing. `dashboard/__init__.py`
      stays for step 7, and so does `bin/sd-dashboard`, which imports nothing
      from the package and still answers `--help` with the system dashboard's
      address. **Two sentences in the step text above were stale when this
      landed.** "There is no `work` verb in `bin/sd`" was measured before
      #802 landed one: `bin/sd_work.py` registers `deliver` under `work`
      (`working.add_parser("deliver", ...)`), and `sd work deliver <item>
      <full-sha>` writes the `status_change` note `delivered at <commit> on
      <ref>` through `sd_db.progress.deliver_work`, whose `who=` names the
      deliverer. So the successor is the CLI verb and not a page control; the
      system commit built none, and `DELIVERED_BY = "dashboard"` in
      `dashboard/work.py` retired with the file rather than being reproduced.
      The two `source:` locators into `dashboard/work.py` in the step text,
      and eighteen more across this item's three pages and the
      2026-09-05 prd, were rewritten as prose naming the file because the
      citation gate refuses a locator into a file that is gone; the plan
      text itself stands. `DASHBOARD_CODE_CAP` fell from 866 to 0 against 0
      measured, every code line under `dashboard/` gone (`now.py` 79,
      `actions.py` 138, `work.py` 127, `server.py` 213, `app.js` 309), the
      fourth fall `CEILING_HISTORY` records; `DASHBOARD_CAP` did not move.
      `AMBIGUOUS_CEILING` fell from 121 to 116. `R11-D20` lost its one live
      definition, the module docstring of `dashboard/now.py`, and is back in
      `STRANDED_RULE_IDS`; two ids cited by nothing live any more left it.
      `README.md`, `AGENTS.md` and the skills name none of the Now view,
      `/api/now`, `/api/ack` or `/api/deliver`. The :8767 Today page after
      `~/deploy-sd-db.sh` is the owner's to read and was not read by this
      commit.

- [x] **7. `dashboard/` is deleted, and the ceilings retire in the same commit.**
      **Read this before starting step 2.** Three tests interlock and the
      interaction decides how steps 3 to 6 are written:

      (a) `test_the_code_ceiling_is_paid_for_in_kind`
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7) asserts
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
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7) requires each new value appended to
      `CEILING_HISTORY` (`source:tests/test_loc_caps.py::CEILING_HISTORY`) in the same commit.

      (c) `test_the_recorded_history_is_raises_only`
      (`source:tests/test_loc_caps.py::test_the_recorded_history_is_raises_only`) asserts the downward count is zero, at
      `tests/test_loc_caps.py:590`. `ceiling_moves` (`source:tests/test_loc_caps.py::ceiling_moves`)
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

      **(c) has been done, as R11-D49 in pull request #922, before step 3's
      pack commit.** The line numbers in (c) are as of `a8295266`, where they
      were measured. At `2eafa78b` the test
      (`source:tests/test_loc_caps.py::test_the_recorded_history_is_raises_only`)
      permits a recorded fall on `DASHBOARD_CODE_CAP` alone, its second
      assertion reads `upward + downward == values - len(CEILING_HISTORY)`, and
      the module docstring carries an R11-D49 paragraph after R11-D41's.

      So (c) goes red on **step 3**, not on step 7. The order that follows:
      step 3's pack commit is preceded by its own preparatory commit — a new
      R-id — that rewrites (c)'s assertion and the R11-D41 paragraph and makes a
      recorded fall legal; only then do steps 3 to 6 lower the cap as they go.
      The clause R11-D24 wrote, "a cap is never raised in the pull request that
      crossed it", applies unchanged in the mirror: **a ceiling is never lowered
      in the pull request that needed it.**

      Then this step: delete the remaining tracked files under `dashboard/` and
      `bin/sd-dashboard` itself, and in the same commit delete `DASHBOARD_CAP`
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7), `DASHBOARD_CODE_CAP`
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7), `DASHBOARD_CODE_SLACK`
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7) and the four tests that read them —
      `test_the_dashboard_stays_under_its_ceiling`
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7),
      `test_the_dashboard_code_stays_under_its_own_ceiling`
      (in `tests/test_loc_caps.py`, retired at sd:719 step 7), (a) and (b) — **keeping both
      `CEILING_HISTORY` entries**, in the shape `BIN_CAP` retired at R11-D48 and
      for the reason that entry's own comment gives.

      **The empty directory breaks more than the caps, and all of it retires in
      this commit.** Enumerated from the tree rather than recalled:

      - `LINT_RUFF_PATHS := dashboard $(LINT_BIN) tests` and
        `LINT_MYPY_PATHS := dashboard $(LINT_BIN)` in the `Makefile` pass
        `dashboard` to Ruff and to mypy, so `make check` fails on a path that
        no longer exists.
      - `tests/test_code_health.py` still holds `dashboard/` baseline entries for
        whatever steps 3 to 6 have not already retired, and
        `test_every_baseline_entry_still_earns_its_place` fails on each one.
      - **Twenty-six test files name `dashboard`**, counted with
        `grep -ln dashboard tests/*.py`. Those whose whole subject is deleted go
        with it — `tests/test_sd_dashboard.py`, `tests/test_sd_dashboard_index.py`,
        `tests/test_dashboard_actions.py`, `tests/test_dashboard_deliver.py`,
        `tests/test_dashboard_now.py`, `tests/test_dashboard_sessions.py`,
        `tests/test_dashboard_skills.py`, `tests/test_dashboard_work.py`,
        `tests/test_sd_ledger.py` and `tests/test_sd_trackers.py` (the two
        index suites went at step 4). The rest only
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

      **Landed as the pack deletion, this pull request, 2026-09-16.** One
      commit deleted `dashboard/__init__.py` (the directory with it),
      `bin/sd-dashboard` and `tests/test_sd_dashboard.py`, and in the same
      commit `DASHBOARD_CAP`, `DASHBOARD_CODE_CAP`, `DASHBOARD_CODE_SLACK`,
      the derivation comments that stood over them (R11-D29, R11-D30,
      R11-D38, the raise of 2026-09-07 and the four falls) and five tests:
      the four named above plus
      `test_no_javascript_under_the_cap_hides_prose_in_a_block_comment`,
      which iterated `tracked("dashboard")` for `.js` files and had nothing
      left to iterate. `test_each_ceiling_is_the_last_value_its_history_records`
      was measured before it went: it read `DASHBOARD_CAP` and
      `DASHBOARD_CODE_CAP` only, never `BIN_CAP`, so there was nothing to
      narrow it to. All three `CEILING_HISTORY` entries stay, the two
      dashboard ones under a `Closed.` comment in the shape `BIN_CAP`'s
      carries from R11-D48, and the record of the retirement is a comment
      below `MIGRATE_CAP` in that shape too; `ceiling_moves()` reads
      `(33, 26, 4)` over three closed ceilings and
      `test_the_recorded_history_is_raises_only` still passes over them.
      The module docstring's live-rule paragraphs (downward-only, payable in
      kind, the report-not-gate consideration) are one dated past-tense
      paragraph now; the R11-D41 and R11-D49 paragraphs stand as the dated
      records they were. The `Makefile` lost `dashboard` from
      `LINT_RUFF_PATHS` and `LINT_MYPY_PATHS` and from the comment that
      restates them, so `LINT_MYPY_PATHS` is `$(LINT_BIN)` alone;
      `tests/test_code_health.py` reads `tracked("bin")` alone, its
      docstrings stop naming `dashboard/` as a corpus tree, it had no
      `dashboard/` baseline row left to drop (`DYNAMIC` emptied at step 3),
      and `AMBIGUOUS_CEILING` fell 116 to 114 for `bin/sd-dashboard`'s
      `build_parser` and `main`, the two shared names the CLI carried.
      **Twenty test files named `dashboard` at `2da4e973`, counted with
      `grep -ln dashboard tests/*.py`; seventeen do after this commit, and
      each names it deliberately.** Deleted: `tests/test_sd_dashboard.py`,
      whose subject was the verbless parser and the retired-import census;
      the census needed no new home, because mypy over `bin/` reports
      `import-not-found` for a package that is not there (measured: a probe
      importing `dashboard.store` from `bin/` failed the lint on this base
      with `Module "dashboard" has no attribute` and fails it with
      `import-not-found` once the package is gone) and a test module
      importing it fails at collection. Edited, dropping the tree from an
      enumeration: `tests/test_loc_caps.py` (above; the unmerged-index
      fixture's throwaway path is `bin/panel.py` now, and the
      registry-snapshot reader walk lost the pathspec),
      `tests/test_code_health.py` (above), `tests/test_cut_symbols.py`
      (`GOVERNED` and the `parked`/`archived` reader grep lost `dashboard`;
      the frozen reader set did not change, since its last `dashboard/` row
      left at step 6), `tests/test_no_trellis_residue.py` and
      `tests/test_workflow_policy.py` (`GOVERNED`), and
      `tests/test_rule_registry.py` (`consumer_sources` reads
      `read_corpus("bin")`, and the two docstrings that named the tree say
      when it went). Untouched, each for a reason:
      `tests/test_changed_files_fast_path.py` builds a throwaway `dashboard/`
      tree to exercise `.github/scripts/select-tests.py`, whose
      `IMPORTING_TREES` still names it; `tests/test_delivery_evidence.py`
      carries a captured review body naming `tests/test_dashboard_plugins.py`;
      `tests/test_doc_citations.py`, `tests/test_permission_allowlist.py`,
      `tests/test_sd_research_pins.py` and this file's own tests name the
      retired files in dated prose; `tests/test_sd_ledger.py` asserts the
      ledger's on-disk path,
      `~/.local/state/sd-ai-command-pack/dashboard/ledger.jsonl`, which is
      `bin/sd_ledger.py`'s state directory and not the tree;
      `tests/test_sd_plugin.py` exercises the `dashboard` key of
      `sd-plugin.json`, which `bin/sd plugin` still validates;
      `tests/test_sd_status.py` keeps the regression that `sd-dashboard index`
      is never printed and the copy-of-`bin/`-alone test; and
      `tests/test_sd_docs_lint.py`, `tests/test_sd_handoff_rows.py`,
      `tests/test_sd_registry.py`, `tests/test_sd_review.py` and
      `tests/test_sd_suggest.py` say "dashboard" of the system dashboard, a
      fixture sentence, or a `docs/work/` directory name. **Installer
      count:** `bin/sd_install.py --status` from this tree reports
      `commands: 16 in bin/`, down from 17; no test, `README.md` row or
      `AGENTS.md` line hard-codes either number, so nothing else moved, and
      the owner's `~/.local/bin/sd-dashboard` link stays until `--user` runs
      again and prunes a receipt-named link whose command `bin/` no longer
      has. **`select-tests.py` on a tree with no `dashboard/`:** measured by
      running it the way `.github/scripts/run-tests.sh` does, over this
      diff's paths and over the two deleted paths alone. Both exit 0; the
      diff resolves to `full` because the `Makefile` is a full-suite path,
      and the two deleted paths alone select 10 modules, since `importers`
      guards each tree of `IMPORTING_TREES` with `is_dir()`. No change to
      the selector is needed; its `dashboard` entry is inert. CI ignores
      `TEST_CHANGED_FILES` besides. `make check` exits 0 (the gate in the
      pull request body); `git ls-files dashboard/ bin/sd-dashboard` prints
      nothing; the `DASHBOARD_*` grep over `tests/` and `bin/` prints the
      two `CEILING_HISTORY` keys, this file's own test and prose, and one
      fixture heading in `tests/test_rule_registry.py`. Three tests were
      committed first and watched fail on `2da4e973`: `DashboardCut` in
      `tests/test_cut_symbols.py` (the `ls-files` enumeration), the
      three-keys-and-no-constants test in `tests/test_loc_caps.py`, and
      `LintPaths` in `tests/test_code_health.py`, which reads the two
      `Makefile` variables as text and asserts every literal token has a
      tracked file under it -- green on the base, where `dashboard/` still
      existed, and red on the mutation that puts the token back after the
      deletion.

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

      **Run with step 7, 2026-09-16, and not ticked: the mechanical half is
      done and the prose sweep has residue in files other lanes hold.** The
      enumeration command above printed nothing before step 7's commit and
      nothing after it, at `2da4e973` and on the finished tree: steps 3 to
      6 had already rewritten every anchored citation into the deleted
      files. `python -m unittest tests.test_doc_citations` prints
      `target-missing=0`, and `bin/sd-docs-lint` is clean. What the
      deletion did turn red was the `source:` form: 28 locators into the
      seven `tests/test_loc_caps.py` symbols step 7 deleted, in this item's
      three pages and in sd:361's `design.md` and `implement.md`, each
      rewritten as prose naming the file, retired at step 7, the shape step
      6 used for `dashboard/work.py`. The prose count,
      `grep -rn -E 'dashboard/[a-z_]+\.(py|js)|bin/sd-dashboard'` over live
      `.md` files, read 219 lines before and 217 after: `CONTRIBUTING.md`
      and `docs/lane-brief.md` used `dashboard/app.js` as their example of a
      file with no locator and name the `Makefile` now, and `README.md`'s
      `lint` row stopped listing `dashboard`. The 217 that stay are this
      item's three pages (132: the plan text of ticked steps, pinned at
      `a8295266` where it carries a line number, and their landing
      paragraphs), sd:361's three pages (62: all but eight pinned
      `at 2a2dbad6` or marked retired at step 4 by that step's sweep, and
      those eight name a file in the plan text of a closed item), the
      2026-09-05 prd and implement (19, PR 7's derivation, with three
      unanchored `path:line` tokens the gate reports as
      `no-adjacent-anchor`; those pages are sd:234's and its lanes hold
      them), the citation-gate design's two dated counts, one line in
      sd:431's implement, and the review anecdote in
      `skills/sd-review/SKILL.md`. Residue for the owner or a later sweep,
      outside what this lane may edit: `skills/sd-status/SKILL.md` and
      `bin/sd-status`'s `CLASSES` still say `dashboard index` as the source
      of the two `issue-*` rows (the verb went at step 4; the file is held
      by #1011 and fix-431-d); `bin/sd_rules.py`'s four `R12-D*` subjects,
      `bin/sd_lib.py`, `bin/sd_codex.py`, `bin/sd-status`'s two comments and
      `bin/sd_install.py`'s comment still say `dashboard/` or
      `sd-dashboard` in prose; and `.github/scripts/select-tests.py` keeps
      `dashboard` in `IMPORTING_TREES`, inert (step 7 measured it).

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
  gone, `launchctl list | grep com.sven.sd-dashboard` still lists the label,
  the PID beside it is the PID `lsof -nP -iTCP:8767 -sTCP:LISTEN` reports,
  the two read at one moment, and the plist's `ProgramArguments[0]` is still
  the system `dashboard.sh`. Asserted before and after, because "it still
  works" is only evidence if the before was recorded. The PID is compared
  within one reading and never across two: it is part of the record (37095 at
  planning, 76442 when step 1 landed), and an owner-approved restart changes
  it (review-909 N3).
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

## Log

- 2026-09-16 step 4 landed: system pull request #411 (`fe556f4`), pin #999
  (`c6879551`), then the pack deletion. Step 4 is ticked with the measurement
  above; `DASHBOARD_CODE_CAP` reads 1,183.
- 2026-09-16 step 5 landed: the capture at pack `b4211959`, system pull
  request #427 (`051d931a`), then the pack deletion. Step 5 is ticked with the
  measurement above; `DASHBOARD_CODE_CAP` reads 866.
- 2026-09-16 step 6 landed: the capture at pack `85c4fa1b`, system pull
  request #428 (`e43444f5`), then the pack deletion. Step 6 is ticked with the
  measurement above; `DASHBOARD_CODE_CAP` reads 0.
- 2026-09-16 step 7 landed: the pack deletion of `dashboard/`,
  `bin/sd-dashboard` and the three ceilings, in one commit. Step 7 is ticked
  with the measurement above; `CEILING_HISTORY` holds three closed records
  and `ceiling_moves()` reads `(33, 26, 4)`. Step 8's enumeration is 0 before
  and after; its prose residue is recorded on the step and it stays open.
