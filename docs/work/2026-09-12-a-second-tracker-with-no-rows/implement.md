# Implement — a second tracker with no rows

## Budget and shape

The port crosses the boundary sd:392 names: the collector and the dispatch
land in `platypeeps/system` (`local-sd-db`), the verb and the reader land
here, and the pin between them moves in its own pull request because
`.github/sd-review.json` lists `.github/workflows/**` as sensitive. That is
the sequence #888 followed for sd:360 and it is followed again here, step
for step. Nothing in the pack half depends on the newer library until the
pin moves: the verb reads `TRACKERS` and `configured` through `getattr` with
today's behaviour as the default, and that is asserted by running the verb's
tests with the pinned build, not assumed.

`dashboard/` is not touched. `DASHBOARD_CAP` (`tests/test_loc_caps.py:223`)
and `DASHBOARD_CODE_CAP` (`tests/test_loc_caps.py:231`) do not move;
`dashboard/jira.py` stays until the `index.sqlite` retirement deletes it. The
pack's `bin/` has no ceiling since R11-D48. The pack half is on the order of
forty lines in `bin/sd_shadow.py`, thirty in `bin/sd-status`, and their
tests.

## Step checklist

- [ ] **1. Configure, before any code.** Export `JIRA_BASE_URL` and
      `JIRA_EMAIL` in `~/.config/shell/env.sh`, beside the `JIRA_API_TOKEN`
      that is already there, because that file is what
      `local-cron-jobs/cron-jobs.sh` sources before the nightly job and what
      a login shell reads. This is the operator's step; the PRD's "if yes"
      branch puts it first and this checklist does not reorder it.
      Verify: in a fresh login shell, a presence check over the three names
      prints `set` three times and prints no value —
      `python3 -c 'import os; print([n for n in ("JIRA_BASE_URL","JIRA_EMAIL","JIRA_API_TOKEN") if not os.environ.get(n)])'`
      prints `[]`. Today it prints `['JIRA_BASE_URL', 'JIRA_EMAIL']`.

- [ ] **2. One proving collect against the loop that exists.** Run
      `sd-dashboard index` — the verb at `bin/sd-dashboard:250` — with the
      three variables exported. This is the PRD's "one successful collect
      against the existing `dashboard/collect.py:168` loop proving a row can
      be produced at all", and it costs no code.
      Verify: the run prints `issues[jira]: N new, 0 updated, M open` rather
      than `issues[jira]: not collected (...)`, and
      `sqlite3 ~/.cache/sd-ai-command-pack/index.sqlite "select tracker, count(*) from issue group by tracker"`
      returns a `jira` row where today it returns `github|1175` alone. Then
      `select url, state from issue where tracker='jira' and url like '%/browse/LOG-23818'`
      returns one row. **If it returns none while the run succeeded**, stop:
      check the `accountId` `myself` returned against the operator's own
      (design, last risk), because a token minted for another account
      collects that account's involvement and reports success. If the run
      prints `Jira rejected the credentials`, stop: the port does not start
      on credentials that do not reach Jira.

- [ ] **3. The library module: `sd_db/shadow_jira.py`.** In
      `platypeeps/system`, lift `dashboard/jira.py` whole — module docstring
      with both lists, `settings`, `missing`, `window_start`,
      `window_minutes`, `_request`, `account_id`, `search`, `state_of`,
      `normalize`, `collect` — with three changes and no others: `collect`
      returns `Collected` rather than the pack's dict; `window_start` calls
      the library's `parse_iso` at `sd_db/shadow_sync.py:119` instead of
      importing the pack's `github` module; and `fetch_issue`
      (`dashboard/jira.py:330`) does not move, because it belongs to
      `sd-trackers ref`, which the item says needs no change. `TRACKER =
      "jira"`, `OVERLAP` and `FIRST_RUN_WINDOW` are declared in the module,
      not shared, for the reason `window_start` (`dashboard/jira.py:114`)
      gives. Port `JiraTests` (`tests/test_sd_dashboard_index.py:465`) with
      its `jira_issue` and `jira_transport` fixtures to
      `local-sd-db/tests/test_shadow_jira.py`, asserting on `Collected`
      fields.
      Verify: the ported suite passes; the three named rules each have a
      test that reddens under mutation — swap `account_id` for a search
      (the empty-200 case), compare by email when both ids are present,
      and format the JQL with an absolute timestamp — and `diff -q` reports
      the tree identical after each is reverted. Control: a transport
      returning one `To Do` issue yields exactly one `Collected.issues` row
      with `tracker == "jira"`, `number is None`, `state == "open"`.

- [ ] **4. The library dispatch, the export, and the docstring.** In
      `sd_db/shadow_sync.py`: `sync` keeps its signature; `tracker="github"`
      runs the path at `sd_db/shadow_sync.py:595-661` unchanged;
      `tracker="jira"` runs a new `_sync_jira` — `read_watermark`, `collect`,
      then under `transaction` `store`, re-read the cursor, `write_watermark`
      only when `result.ok` and the cursor has not moved past `moment`, then
      the `tracker-sync:jira` heartbeat with the same body keys GitHub's
      writes at `sd_db/shadow_sync.py:638-646`, with `queued` 0 and
      `incomplete` empty; any other `tracker` raises `ValueError` naming
      `TRACKERS`. `Synced` gains `configured: bool = True`, last, after
      `incomplete`, so positional construction anywhere is unaffected;
      `_sync_jira` sets it `False` when `missing` is non-empty, writes the
      heartbeat with `ok False` and the reason, and returns before any
      request. The budget arguments `max_requests` and `max_seconds` are
      validated and otherwise unused on this path — Jira's ceiling is
      `MAX_PAGES` — and the docstring says so rather than accepting them
      silently. `sd_db/__init__.py` exports `TRACKERS =
      ("github", "jira")`. The paragraph at `sd_db/shadow_sync.py:25-29`
      is rewritten to name the second module, the caller's iteration, and
      the 2026-09-12 decision on sd:361.
      Verify, each as a test in `local-sd-db/tests/test_shadow_sync.py` or
      beside it: (a) `sync(connection, tracker="jira", ...)` with a
      transport fixture writes `jira` rows, writes a `watermark` row with
      `key = 'jira'`, and leaves `read_watermark(connection, "github")`
      `None` — the per-tracker rule, as a fact about the `state` table; (b)
      the same call with `JIRA_BASE_URL` absent from the environment writes
      no row, writes no watermark, makes no request, writes one
      `tracker-sync:jira` heartbeat whose body carries the reason, and
      returns `ok False, configured False`; (c) a transport that returns `isLast: false` with
      no token returns `truncated == ["jql"]` and the watermark is not
      written — mutation: drop the `result.ok` guard and (c) reddens; (d)
      `sync(connection, tracker="nope")` raises `ValueError`; (e) the
      GitHub path's existing tests are unchanged and green, which is the
      control that the dispatch did not touch them. Then
      `grep -n "retires with no successor" sd_db/shadow_sync.py` prints
      nothing — the item's last acceptance line, as a grep. Suites under
      the CI-shaped venv as sd:603 recorded them: `local-sd-db`, dashboard,
      runner, all OK.

- [ ] **5. The pin.** `.github/workflows/tests.yml:90` moves from `758dfb48`
      to the squash SHA of step 4's merge. Its own pull request, because the
      file is sensitive; nothing else in it.
      Verify: CI on that pull request is green with the new pin, and
      `python -c "import sd_db; print(sd_db.TRACKERS)"` in the CI venv prints
      `('github', 'jira')`.

- [ ] **6. The verb iterates.** `shadow_sync` (`bin/sd_shadow.py:126`) reads
      `names = getattr(sd_db, "TRACKERS", ("github",))`; when `--since` or
      `--until` is given, `names` is `("github",)` and every other tracker
      prints `shadow sync[<name>]: skipped (recovery window is GitHub's)`.
      For each name it calls `sd_db.sync_shadow(connection, tracker=name,
      **options)` and `report_sync` (`bin/sd_shadow.py:73`), which gains the
      name and prefixes every line it prints with `shadow sync[<name>]:`.
      When `getattr(result, "configured", True)` is false, `report_sync`
      prints the single line `shadow sync[<name>]: not collected (<reason>)`
      and returns 0 regardless of `--strict`. The exit code is the maximum
      over trackers. `docs/workflow-controls.md:197-205` gains two
      sentences: the flags are GitHub's, and an unconfigured tracker is a
      line.
      Verify: in `tests/test_sd_suggest.py`, beside `TheShadowSync`
      (`tests/test_sd_suggest.py:412`): (a) with the pinned library, the
      four existing tests pass unchanged — the substring assertions such as
      `wrote 2 shadow row(s)` still hold under the prefix, which is the
      control that the pin can lag; (b) with a fake `sd_db` whose `TRACKERS`
      is `("github", "jira")` and whose `sync_shadow` returns a `Synced`
      with `configured=False` for `jira`, `--strict` exits 0 and the output
      carries `shadow sync[jira]: not collected (JIRA_BASE_URL and
      JIRA_EMAIL not set)` — the item's second acceptance line; (c) same
      fake, `jira` returning `ok=False, configured=True, reason="Jira
      rejected the credentials (401 Unauthorized); check JIRA_EMAIL and
      JIRA_API_TOKEN"`, `--strict` exits 1 and the reason is printed — the
      fourth line; (d) `--since` given, `sync_shadow` is called once, with
      `tracker="github"`, and the skipped line is printed for `jira`.
      Mutation: make the unconfigured branch fall through to `cursor held`
      and (b) reddens on the exit code.

- [ ] **7. `sd-status` shows the row.** `_database_issues`
      (`bin/sd-status:1134`) keeps its GitHub call as it is. A new
      `_jira_issues(connection)` calls `tracker_items(connection,
      tracker="jira", state="open")` — no `repo` — and
      `tracker_freshness(connection, "jira")`, and `_render_issues`
      (`bin/sd-status:3378`) gains a block after the GitHub rows: the
      freshness line for `jira`, then one row per issue as
      `KEY  state  title[:60]` with `KEY` = `row["url"].rpartition("/")[2]`,
      through a renderer that never formats `number`. When
      `last_success_at` is `None` the block is the one line
      `jira: never collected`, with ` (<reason>)` appended when the latest
      heartbeat carries one; it is keyed on `last_success_at` and not on the
      state word because `tracker_freshness` says `degraded`, not `never`,
      once a failed heartbeat exists (design, "Readers"). `skills/sd-status/SKILL.md:41` gains the
      block's description.
      Verify, in `tests/test_sd_status.py`: (a) a fixture database holding
      one `jira` row with `number NULL` and `url .../browse/LOG-23818`
      renders `LOG-23818  open  Benchmark harness` and raises nothing — the
      regression for the `:<6` format at `bin/sd-status:3394`, which raises
      `TypeError` on `None` today; (b) the same database with no `jira`
      rows and no heartbeat renders `jira: never collected`; (c) a
      `tracker-sync:jira` heartbeat with `ok False` and a reason, and no
      watermark, renders `jira: never collected (<reason>)` even though
      `tracker_freshness` reports `degraded`; (d) the GitHub block's existing assertions are unchanged —
      the control. Mutation: route the Jira row through the GitHub renderer
      and (a) reddens with the `TypeError`.

- [ ] **8. The first real sync, and the measurement.** With steps 1 to 7
      landed and the venv reinstalled at the new pin, run
      `sd shadow sync --strict` once by hand, then re-run the measurement
      block in `design.md` and record the numbers on sd:361 as a note.
      Verify: the run prints `shadow sync[jira]: wrote N shadow row(s)` and
      `shadow sync[jira]: cursor moved to cover from <stamp>`; `select
      tracker, count(*) from shadow group by tracker` returns two rows where
      today it returns one; `select key from state where kind='watermark'
      group by key` returns `github` and `jira`; `select url, state from
      shadow where tracker='jira' and url like '%/browse/LOG-23818'` returns
      one row; `sd-status` in any checkout prints `LOG-23818` in the issues
      section. The nightly's next run, read from its log the following
      morning, carries both prefixes.

- [ ] **9. Correct the item.** The PRD's last acceptance line: sd:361's body
      still says it builds an iteration and per-tracker watermarks that
      exist. Add a note to the item, and edit issue #805's "What to build"
      into the migration this document describes, citing `design.md`.
      Verify: `sd store item 361` shows the note; the issue body no longer
      contains the sentence "The caller iterates trackers" as a thing to
      build.

Steps 1 and 2 are the operator's and gate everything after them. Steps 3 and
4 are one pull request in `platypeeps/system`; step 5 is one here; steps 6
and 7 may share a pull request here; steps 8 and 9 follow the merge.

## Verification

**Named before the work starts.**

- The per-tracker watermark rule is proved as a fact about the `state`
  table, not about a return value: after a Jira sync, `github`'s cursor row
  count is unchanged and `jira`'s is one; after a GitHub sync on the same
  database, `jira`'s is unchanged. Step 4 (a) and its mirror.
- Every guard is proved by mutation, restored, and `diff -q` reports the
  tree identical. A mutation script asserts its own edit applied
  (`assert text.count(old) == 1`) before running the test, because a pattern
  that matches nothing reports a false pass.
- The pack half is run twice: once at the pinned library, once at the new
  one. Both green is the claim; one green is not.
- No value of any `JIRA_*` variable appears in any log, test output, note, or
  pull request body. Presence only. `grep -rn "JIRA_API_TOKEN=" .` over the
  pack and the system checkout prints nothing; today it prints nothing, and
  the fixture at `tests/test_sd_dashboard_index.py:426` is the shape a test
  value takes — a dict literal with a placeholder, never an assignment.
- The acceptance lines on the item map to steps: line 1 to step 8, line 2
  to step 6 (b), line 3 to a second sync after a ticket closes — not
  provable on demand; recorded on the item when it first happens — line 4
  to step 6 (c), line 5 to steps 2 and 7, line 6 to step 4's grep.

**What cannot be verified from the repository, stated rather than invented:**
that the token authenticates the operator's own account (step 2 stops on
it); that `LOG-23818` is still open (either answer is correct and the row
says which); and that the nightly job's environment carries the variables,
which only the morning-after log shows.
