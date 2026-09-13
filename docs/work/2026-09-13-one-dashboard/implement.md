# Implement — one dashboard

## Budget and shape

Eight steps, most of them a pair of pull requests across two repositories. The
boundary is sd:392's: views and collectors land in `platypeeps/system`, verbs and
caps land here, and nothing in the pack half depends on the newer system side
until the step that says so.

Every step 2 to 6 is **two commits, system first**. The view appears on :8767,
then the pack loses it. A single commit that does both is the one shape this plan
refuses, because it is the only one with a window where a view exists nowhere.

`.github/workflows/**` is sensitive under `.github/sd-review.json`, so any pin
move is its own pull request, in the shape #888 and sd:361 step 5 both follow.
Only step 4 needs one.

The ceilings do not move until step 7, and then they move once. Steps 1 to 6
delete no tracked file under `dashboard/` — step 1 deletes lines from
`bin/sd-dashboard`, which has had no ceiling since R11-D48, and steps 2 to 6
delete `dashboard/` files only in their pack-side commit, each of which must lower
`DASHBOARD_CODE_CAP` to keep `test_the_code_ceiling_is_paid_for_in_kind`
(`tests/test_loc_caps.py:522`) green. **That is the trap in this plan and step 7
is written to absorb it:** see step 7's first paragraph before starting step 2.

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
      `('github', 'jira')`, which is step 4's own verification and prints nothing
      today because `TRACKERS` appears nowhere in the system repository on
      `origin/main`. **Do not mark step 3 done in sd:361's file from this lane**;
      that item's owner holds the file, and editing it here is the cross-lane
      write sd:525 objects to. Record the landing as a note on sd:361 instead.

- [ ] **1. `serve` and `install` are removed; `index` stays.** In
      `bin/sd-dashboard`: delete `cmd_serve` (`bin/sd-dashboard:37`),
      `cmd_install` (`bin/sd-dashboard:139`), `launchctl`
      (`bin/sd-dashboard:126`), `PLIST_BODY` (`bin/sd-dashboard:81`), `LABEL`
      (`bin/sd-dashboard:52`), `PLIST` (`bin/sd-dashboard:53`) and the two
      `add_parser` registrations for them, and delete the stale comment at
      `bin/sd-dashboard:48-51` with the constant it described rather than fixing
      its wording. **Then drop `server` from the import at
      `bin/sd-dashboard:34`**: every one of its six uses — at
      `bin/sd-dashboard:39`, `:43`, `:159`, `:172`, `:242` and `:246` — belongs to
      one of the two deleted verbs, so the import is unused afterwards and `ruff`
      fails on it. Found by grepping the uses rather than by reading the diff,
      which is the only way it shows up. `cmd_index` (`bin/sd-dashboard:176`) and
      the `index` verb stay, because steps 4 and 5 still read the cache it fills,
      and `collect` and `store` stay in that import for it. `InstallTests`
      (`tests/test_sd_dashboard.py:331`) is deleted with the verb it covers, and
      the two cases in `tests/test_sd_dashboard.py` that pin the port baked into
      the plist go with it.

      This step subsumes sd:705's destructive half and answers its port and label
      questions by deletion. It is first because it is the only step that makes
      the machine safer rather than tidier.

      Verify, and the important half is a negative:
      `launchctl list | grep com.sven.sd-dashboard` still prints PID 37095, and
      `plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/com.sven.sd-dashboard.plist`
      still prints the system `dashboard.sh` as element 0 — asserted **after**
      the change and before it, so the pair is evidence rather than a hope. Then
      `grep -rn "com.sven.sd-dashboard" bin/ dashboard/ tests/` prints nothing:
      the pack no longer names a label it does not own. Then
      `grep -rn "sd-dashboard serve\|sd-dashboard install" . --include='*.md'
      --include='*.py' --include='*.sh'` outside `docs/work/archive/` prints
      nothing, which #898 already measured as true for `skills/` and `.claude/`
      and which this step re-runs over the whole tree rather than inheriting.
      `python -m unittest tests.test_sd_dashboard tests.test_loc_caps
      tests.test_code_health` passes; the caps do not move, because nothing under
      `dashboard/` changed.

      Mutation, to prove the negative is load-bearing rather than vacuous: restore
      the `install` parser alone and the `com.sven.sd-dashboard` grep reddens;
      revert and `diff -q` reports the tree identical.

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
      commit first: nothing, because step 2 already put the sixth view there.
      Pack commit: delete `dashboard/plugins.py` (719 lines, 357 code), the
      plugin half of `dashboard/app.js` — `enhance`
      (`dashboard/app.js:517`) and `panelId` (`dashboard/app.js:526`) — the
      `plugin-tabs` span and the `plugin-panels` div in `PAGE`
      (`dashboard/server.py:238`), and the loader's rows from the Now merge in
      `dashboard/now.py`.

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

      Then, in the system repository, remove the `tabs` and
      `tile` keys from `/Users/sven/repos/system/sd-plugin.json`; the `actions`
      key stays, because `sd plugin list --json` still reports it and the four
      queue-open actions are not tabs.

      **Two things this step gives up, and both are recorded rather than
      silently spent** (design, "Pricing the two options"): a third party
      declaring a dashboard tab, which has no instance — the registry holds two
      plugins and only `sys` declares tabs — and the rank-0 alert row a dark
      collector used to raise, which moves to step 6 and is an accepted gap until
      then.

      Verify: `bin/sd plugin list --json` still reports the `sys` plugin with its
      four actions and no `tabs` key; `python -m unittest tests.test_loc_caps`
      passes with `DASHBOARD_CODE_CAP` lowered by the 357 code lines this removes
      **minus the 27 of headroom the slack rule allows** — see step 7 before
      choosing the number, because the first lowering is where the history test
      goes red. `tests/test_dashboard_plugins.py` is deleted with its subject.
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
      `dashboard/jira.py`, `dashboard/collect.py`, `cmd_index`
      (`bin/sd-dashboard:176`) and the `index` verb. This is the step that closes
      the criterion 2 problem outright, because `sqlite3.connect`
      (`dashboard/store.py:89`) and `sqlite3.connect`
      (`dashboard/store.py:94`) are the two connections the port could not
      carry.

      Pin commit, its own pull request: `.github/workflows/tests.yml` moves to the
      squash SHA of the system commit. **And the pin is not only CI's.** The
      running dashboard's own `/health` reports its `library` as
      `/Users/sven/repos/platypeeps/sd-ai-command-pack/.venv/lib/python3.13/site-packages/sd_db/__init__.py`
      — measured on pull request #898 at `d0ad6542`. The surviving dashboard
      imports `sd_db` from *the pack's* virtualenv, so a system-side view that
      needs a newer library is gated on the pack's venv being reinstalled, not
      just on CI going green. Sequence accordingly: library merge, pin, venv
      reinstall, restart PID 37095, and only then the view.

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
      `dashboard/sessions.py`, `dashboard/skills.py` and the repository collector.
      Cheapest of the ports and deliberately **not** first: these collectors open
      no database, so criterion 2 is not in play, and doing them early would have
      burned the ceiling headroom that steps 3 and 4 need. `collect.py`'s
      docstring is the authority for the claim that nothing here is stored —
      "Nothing here is stored as an input to anything" — and step 4 has already
      deleted that file, so this step's pack commit reads it from the history
      rather than the tree.
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

      `deliver` (`dashboard/work.py:232`) is one of the two facts the two
      dashboards share on disk, and it is a **write**. It does not simply
      disappear: either the system page grows the equivalent control or the
      operator uses `sd work deliver` from the CLI. Decide, and record which — a
      write path deleted without a successor is a capability lost by accident.
      Verify: `band` (`dashboard/app.js:547`)'s severity mapping is reproduced on
      the system page, asserted against the same rank numbers; a fixture
      collector that exits non-zero produces a visible row in the merged view;
      and `sd work deliver` or its successor still records a `status_change` note
      naming `DELIVERED_BY` (`dashboard/work.py:229`), whichever side owns it.

- [ ] **7. `dashboard/` is deleted, and the ceilings retire in the same commit.**
      **Read this before starting step 2.** Three tests interlock and the
      interaction decides how steps 3 to 6 are written:

      (a) `test_the_code_ceiling_is_paid_for_in_kind`
      (`tests/test_loc_caps.py:522`) asserts
      `DASHBOARD_CODE_CAP - code_line_count(tracked("dashboard")) <=
      DASHBOARD_CODE_SLACK`, which is 29 against a live gap of 2. **Every pack
      commit that deletes code must lower `DASHBOARD_CODE_CAP` in the same
      commit** or this test fails. A removal of any size leaves headroom of 29,
      so it earns 27 lines and no more.

      (b) `test_each_ceiling_is_the_last_value_its_history_records`
      (`tests/test_loc_caps.py:552`) requires each new value appended to
      `CEILING_HISTORY` (`tests/test_loc_caps.py:287`) in the same commit.

      (c) `test_the_recorded_history_is_raises_only`
      (`tests/test_loc_caps.py:577`) asserts the downward count is zero.
      `ceiling_moves` (`tests/test_loc_caps.py:331`) returns `(29, 26, 0)` today,
      and **the first append from (b) makes it red.** Its docstring says that is
      deliberate: it fails "the day a ceiling finally comes down", and the fix is
      to rewrite the paragraph in the module docstring at
      `tests/test_loc_caps.py:33-46` that reasons from there being none.

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
      enumeration, run once before step 3 and re-run before step 7:
      `python -c "from tests.test_doc_citations import classify; [print(r.doc, r.path, r.start, r.reason) for r in classify() if r.reason == 'compared' and r.path.startswith('dashboard/')]"`.
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
  gone, `launchctl list | grep com.sven.sd-dashboard` still prints PID 37095 and
  the plist's `ProgramArguments[0]` is still the system `dashboard.sh`. Asserted
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
