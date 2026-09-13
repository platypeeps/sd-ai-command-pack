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

`dashboard/` changes by one expression, step 7b, so the page shows a Jira
row's key instead of its project. `DASHBOARD_CAP`
(`tests/test_loc_caps.py:223`) and `DASHBOARD_CODE_CAP`
(`tests/test_loc_caps.py:231`) do not move; `dashboard/jira.py` stays until
the `index.sqlite` retirement deletes it. The pack's `bin/` has no ceiling
since R11-D48. The pack half is on the order of forty lines in
`bin/sd_shadow.py`, thirty in `bin/sd-status`, and their tests.

## Step checklist

- [ ] **1. Configure, before any code.** Export `JIRA_BASE_URL` and
      `JIRA_EMAIL` in `~/.config/shell/env.sh`, beside the `JIRA_API_TOKEN`
      that is already there, because that file is what
      `local-cron-jobs/cron-jobs.sh` sources before the nightly job and what
      a login shell reads. This is the operator's step; the PRD's "if yes"
      branch puts it first and this checklist does not reorder it.
      Verify: in a fresh login shell, a presence check that prints the
      *missing* names and never a value —
      `python3 -c 'import os; print([n for n in ("JIRA_BASE_URL","JIRA_EMAIL","JIRA_API_TOKEN") if not os.environ.get(n, "").strip()])'`
      — prints `[]`. Today it prints `['JIRA_BASE_URL', 'JIRA_EMAIL']`. The
      `.strip()` matches `settings` (`dashboard/jira.py:89-96`), which strips
      before `missing` (`dashboard/jira.py:100`) looks; a value of spaces
      would otherwise pass this check and fail step 2.

- [ ] **2. One proving collect against the loop that exists.** Run
      `bin/sd-dashboard index` from the checkout — the verb at
      `bin/sd-dashboard:250`; the pack links no executable anywhere
      (`AGENTS.md:57-69`) — with the three variables exported. This is the PRD's "one successful collect
      against the existing `dashboard/collect.py:168` loop proving a row can
      be produced at all", and it costs no code.
      Verify: the run prints `issues[jira]: N new, 0 updated, M open` rather
      than `issues[jira]: not collected (...)`, and
      `sqlite3 "$(python3 -c 'from dashboard import store; print(store.index_path())')" "select tracker, count(*) from issue group by tracker"`
      — the path derived, because `index_path` honours `XDG_CACHE_HOME` —
      returns a `jira` row where today it returns `github|1175` alone. Then
      `sqlite3 "$(python3 -c 'from dashboard import store; print(store.index_path())')" "select url, state from issue where tracker='jira' and url like '%/browse/LOG-23818'"`
      — its own invocation; the first one has exited — returns one row. **If it returns none while the run succeeded**, stop:
      check the `accountId` `myself` returned against the operator's own
      (design, last risk), because a token minted for another account
      collects that account's involvement and reports success. If the run
      prints `Jira rejected the credentials`, stop: the port does not start
      on credentials that do not reach Jira.

- [ ] **3. The library module: `sd_db/shadow_jira.py`.** In
      `platypeeps/system`, lift `dashboard/jira.py` whole — module docstring
      with both lists, `settings`, `missing`, `window_start`,
      `window_minutes`, `_request`, `account_id`, `search`, `state_of`,
      `normalize`, `collect` — with four changes and no others. (i) `collect`
      returns `Collected` rather than the pack's dict. (ii) Every use of the
      pack's `github` module goes: `window_start` calls the library's
      `parse_iso` at `sd_db/shadow_sync.py:119`, and the three `github.iso`
      calls in `collect` (`dashboard/jira.py:285`, on its missing-variable,
      failed-`myself` and normal returns) call the library's `iso` at
      `sd_db/shadow_sync.py:114`; `from . import github` appears nowhere in
      the new module, and an import of it is the first thing the ported test
      module would fail on. (iii) `ok` folds truncation in: the pack's
      `collect` sets `ok` from `not error` alone at `dashboard/jira.py:322`
      and reports `truncated` beside it, because `refresh_issues` reads only
      `ok` and the pack never advanced a cursor over a truncated page only
      because `truncated` was reported, not because it was guarded. The
      library's `Collected` is `ok=not errors and not truncated`
      (`sd_db/shadow_sync.py:466`), and the port returns
      `ok=not error and not cut`, so the watermark guard on `ok` in step 4
      is sound. (iv) `fetch_issue` (`dashboard/jira.py:330`) does not move,
      because it belongs to `sd-trackers ref`, which the item says needs no
      change. `TRACKER =
      "jira"`, `OVERLAP` and `FIRST_RUN_WINDOW` are declared in the module,
      not shared, for the reason `window_start` (`dashboard/jira.py:114`)
      gives. Port `JiraTests` (`tests/test_sd_dashboard_index.py:465`) with
      its `jira_issue` and `jira_transport` fixtures to
      `local-sd-db/tests/test_shadow_jira.py`, asserting on `Collected`
      fields. The suite is not free of the pack:
      `test_the_window_is_relative_minutes_not_a_timestamp` calls
      `github.iso(...)` at `tests/test_sd_dashboard_index.py:493` through
      the module's `dashboard.github` import, so the port replaces that call
      with the library's `iso` at `sd_db/shadow_sync.py:114` and drops the
      import; a copy that keeps it fails on collection in `local-sd-db`,
      where there is no `dashboard` package.
      Verify: the ported suite passes, and each of the three carried-over
      rules is guarded by a test that goes red under the mutation that
      breaks it. The rules, as `dashboard/jira.py:254-258` implements them:
      `myself` is the availability check; account ids are compared when both
      sides have one and email only as the fallback; the JQL window is
      relative minutes. The mutations, each of which must redden its test
      and be reverted with `diff -q` reporting the tree identical: replace
      the `myself` call with the search itself (the empty-200 case passes
      as "no issues"); compare by email even when both ids are present;
      format the JQL with an absolute timestamp. A fourth, for (iii): set
      `ok` from `not error` alone and the truncation test in step 4 (c)
      reddens. Control: a transport returning one `To Do` issue yields
      exactly one `Collected.issues` row with `tracker == "jira"`,
      `number is None`, `state == "open"`.

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
      transport fixture, on a database seeded with
      `write_watermark(connection, "github", <known stamp>)`, writes `jira`
      rows, writes a `watermark` row with `key = 'jira'`, and leaves
      `read_watermark(connection, "github")` equal to the seeded stamp —
      exactly, not merely non-`None`, because an empty database would let a
      cross-tracker overwrite pass; and the mirror, a GitHub sync on a
      database seeded with a `jira` watermark leaves the `jira` stamp
      exactly as seeded — the per-tracker rule, as a fact about the `state`
      table; (b)
      the same call with `JIRA_BASE_URL` absent from the environment writes
      no row, writes no watermark, makes no request, writes one
      `tracker-sync:jira` heartbeat whose body carries the reason, and
      returns `ok False, configured False`; (c) a transport that returns `isLast: false` with
      no token returns `ok False, truncated == ["jql"]`, the rows it did
      return are stored, and the watermark is not written — two mutations,
      each of which reddens (c): drop the `result.ok` guard in `_sync_jira`,
      and set `ok` from `not error` alone in `shadow_jira.collect`; (d)
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
      The lines `_library_lines` (`bin/sd_shadow.py:106`) forwards already
      begin `shadow sync: ` — `Synced.report` at `sd_db/shadow_sync.py:547`
      writes that head on each, and the test double at
      `tests/test_sd_suggest.py:606-607` reproduces it — so the verb strips
      that head before adding its own, and never prints
      `shadow sync[jira]: shadow sync: ...`. A forwarded line that does not
      carry the head is prefixed as it is.
      When `getattr(result, "configured", True)` is false, `report_sync`
      prints the single line `shadow sync[<name>]: not collected (<reason>)`
      and returns 0 regardless of `--strict`. The exit code is the maximum
      over trackers. `docs/workflow-controls.md:197-205` is rewritten, not
      appended to: its first sentence, "`sd shadow sync --strict` fails when
      any requested tracker interval remains incomplete", becomes "fails
      when any *configured* tracker's interval remains incomplete; a tracker
      whose variables are unset is reported as not collected and does not
      fail the run", and a sentence follows saying the recovery flags bound
      GitHub only. Left as it stands, the paragraph would tell the operator
      that an unconfigured Jira fails the nightly.
      Verify: in `tests/test_sd_suggest.py`, beside `TheShadowSync`
      (`tests/test_sd_suggest.py:412`): (a) with the pinned library, the
      four existing tests pass unchanged — the substring assertions such as
      `wrote 2 shadow row(s)` still hold under the prefix, which is the
      control that the pin can lag; (b) with a fake `sd_db` whose `TRACKERS`
      is `("github", "jira")` and whose `sync_shadow` returns a `Synced`
      with `configured=False` for `jira`, `--strict` exits 0 and the output
      carries `shadow sync[jira]: not collected (JIRA_BASE_URL and
      JIRA_EMAIL not set)` — the item's second acceptance line — and, with
      the fake's `report()` returning a `shadow sync: contribution detail
      backlog: 3 queued` line for `github`, the output carries exactly
      `shadow sync[github]: contribution detail backlog: 3 queued` and no
      line containing `shadow sync[github]: shadow sync:`; (c) same
      fake, `jira` returning `ok=False, configured=True, reason="Jira
      rejected the credentials (401 Unauthorized); check JIRA_EMAIL and
      JIRA_API_TOKEN"`, `--strict` exits 1 and the reason is printed — the
      fourth line; (d) `--since` given, `sync_shadow` is called once, with
      `tracker="github"`, and the skipped line is printed for `jira`.
      Mutation: make the unconfigured branch fall through to `cursor held`
      and (b) reddens on the exit code.

- [ ] **7. `sd-status` shows the row, in its own section.** The issues
      section cannot carry it: `issues_section` (`bin/sd-status:1181`)
      returns `no GitHub remote` at `bin/sd-status:1197-1199` before any
      database is opened, `_database_issues` (`bin/sd-status:1134`) closes
      its connection before `_render_issues` (`bin/sd-status:3378`) runs,
      and the heading says `this repo, from the index`. Neither function is
      touched. A new producer `jira_section()` opens its own read-only
      connection when `sd_db.default_path()` exists — the same gate
      `_database_issues` uses, and the same `available: False, reason`
      shape when it does not — and calls `tracker_items(connection,
      tracker="jira", state=None)` with no `repo`, and
      `tracker_freshness(connection, "jira")`, and drops every closed row
      whose `last_seen` is more than seven days old before it returns, so
      the cutoff is a property of the `rows` list and not of one renderer.
      It is added to the status dict beside `"issues"` at
      `bin/sd-status:3061` under the key `jira`, so `--json` carries it. A
      new `_render_jira` prints the heading `jira (shared database, all
      repositories)` after the issues section, and `render()`
      (`bin/sd-status:3305`) calls it — `_render_jira(result["jira"],
      write)` on the line after `_render_issues(result["issues"], write)`
      at `bin/sd-status:3328` — because a renderer that is defined and not
      called leaves the section in `--json` only:
      the freshness line, keyed on `last_success_at` and not on the state
      word because `tracker_freshness` says `degraded`, not `never`, once a
      failed heartbeat exists (design, "Readers") — `never collected`, with
      ` (<reason>)` when the latest heartbeat carries one, else the
      `external context` pair; then every open row as
      `KEY  open  <title>` with `KEY` = `row["url"].rpartition("/")[2]` and
      `<title>` = `json.dumps(row["title"], ensure_ascii=False)`, the rule
      `_render_contributions` applies to external text at
      `bin/sd-status:3365-3368`; then every closed row the producer kept as
      `KEY  closed  <title>`; then `none` if there were no rows. Nothing
      formats `number` and nothing slices a title. `ORDER`
      (`tests/test_sd_status.py:3555`) gains the heading after
      `issues (this repo, from the index)`, and the skeleton test's count
      moves from thirteen to fourteen. Every hand-built result the suite
      passes to `render()` gains a `jira` entry, starting with
      `report` (`tests/test_sd_status.py:3522`) on `ReportSectionTests`,
      which builds `issues` and `contributions` and no `jira` — without
      that edit the existing skeleton tests fail with `KeyError` before
      any new case runs. `skills/sd-status/SKILL.md` is rewritten in three
      places, not appended to: `:23` ("The thirteen sections") and `:29`
      ("the thirteen below") say fourteen; `:41`'s issues row keeps saying
      "for this repository", and a new row for the `jira` section says it
      is the operator's Jira involvement from the shared database, across
      every repository, and is not scoped to the checkout.
      Verify, in `tests/test_sd_status.py`: (a) a fixture database holding
      one `jira` row with `number NULL` and `url .../browse/LOG-23818`
      renders `LOG-23818  open  "Benchmark harness"` under the new heading in
      a checkout **with no GitHub remote**, and raises nothing — the
      regression for the `:<6` format at `bin/sd-status:3394`, which raises
      `TypeError` on `None` today, and the proof the section does not sit
      behind the slug gate; (b) the same database with no `jira` rows and
      no heartbeat renders `never collected` then `none`; (c) a
      `tracker-sync:jira` heartbeat with `ok False` and a reason, no
      watermark, and two stored rows — the partial-collect fixture —
      renders `never collected (<reason>)` **and** both rows, because a
      truncated first run stores what it saw; (d) a closed row with
      `last_seen` eight days old is absent from **both** the text and
      `jira_section()["rows"]`, and the same row at six days prints as
      `closed` and is in the list — the cutoff asserted on the producer, so
      `--json` cannot carry what the text hides; (e) a row whose title is
      `"a\x1b[2Jb\nprotection"` prints as one line under the `jira`
      heading, quoted, and the skeleton order test still counts fourteen
      headings — the control-character fixture, the same shape
      `_render_contributions` is tested against; (f) `--json` output carries
      a `jira` object with `available`, `reason`, `freshness` and `rows`,
      and each row carries `url`, `state`, `title` and `last_seen`, asserted
      on the parsed JSON and not on the text; (g) the issues section's
      existing assertions are unchanged, including `no GitHub remote` in a
      checkout without one — the control. Mutation: route the Jira row
      through `_render_issues` and (a) reddens with the `TypeError`; gate
      `jira_section` on the slug and (a) reddens on the missing heading;
      delete the `_render_jira` call from `render()` and (a) reddens on the
      missing heading while (f) stays green, which is why both exist; move
      the seven-day filter into `_render_jira` and (d) reddens on the
      `rows` assertion.

- [ ] **7b. The dashboard shows the key.** `where` (`dashboard/app.js:115-120`)
      returns `issue.url.split("/").pop()` when `number` is null and the
      row has a URL, and `issue.repo || issue.tracker` only when it does
      not; the comment above it, which says the identity is in the URL
      tail, is already the rationale. The page stays an open worklist
      (`dashboard/server.py:638`); nothing else in `dashboard/` changes.
      Verify: a test in `tests/test_dashboard_now.py`, source-reading like
      that file's `fillIssues` cases, asserts the null-number branch of
      `where` derives from `issue.url` and not from `issue.repo` first; and
      `python -m unittest tests.test_loc_caps` stays green with
      `DASHBOARD_CODE_CAP` (`tests/test_loc_caps.py:231`) unmoved. Mutation:
      restore `issue.repo || issue.tracker` as the first branch and the
      test reddens. Manual check after step 2 has run: the issues tab shows
      `LOG-23818`, linked, where before this step it showed `LOG`.

- [ ] **8. The first real sync, and the measurement.** With steps 1 to 7
      landed and the venv reinstalled at the new pin, run
      `bin/sd shadow sync --strict` once by hand — by path, as every verb
      here (`AGENTS.md:57-69`) — then re-run the measurement
      block in `design.md` and record the numbers on sd:361 as a note.
      Verify: the run prints `shadow sync[jira]: wrote N shadow row(s)` and
      `shadow sync[jira]: cursor moved to cover from <stamp>`; `select
      tracker, count(*) from shadow group by tracker` returns two rows where
      today it returns one; `select key from state where kind='watermark'
      group by key` returns `github` and `jira`; `select url, state from
      shadow where tracker='jira' and url like '%/browse/LOG-23818'` returns
      one row; `bin/sd-status` in any checkout, with or without a GitHub
      remote, prints `LOG-23818` under `jira (shared database, all
      repositories)`. The nightly's next run, read from its log the following
      morning, carries both prefixes.

- [ ] **9. Correct the item.** The PRD's last acceptance line: sd:361's body
      still says it builds an iteration and per-tracker watermarks that
      exist. Add a note to the item, and edit issue #805's "What to build"
      into the migration this document describes, citing `design.md`, and
      restate its fifth acceptance line the way design.md's "The dashboard"
      reads it: `sd-status` shows `LOG-23818` with its key and state; the
      dashboard shows the key and, as an open worklist, shows the ticket
      while it is open.
      Verify: `bin/sd store item 361` shows the note; the issue body no
      longer contains the sentence "The caller iterates trackers" as a thing
      to build, and its fifth acceptance line names the two readers
      separately.

Steps 1 and 2 are the operator's and gate everything after them. Steps 3 and
4 are one pull request in `platypeeps/system`; step 5 is one here; steps 6,
7 and 7b may share a pull request here; steps 8 and 9 follow the merge.

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
  pull request body. Presence only. `p=JIRA_API_TOKEN; grep -rn "${p}=" .`
  over the pack and the system checkout prints nothing — the pattern is
  assembled from a shell variable because a document that spelled it out
  would match itself; today it prints nothing, and
  the fixture at `tests/test_sd_dashboard_index.py:426` is the shape a test
  value takes — a dict literal with a placeholder, never an assignment.
- The acceptance lines on the item map to steps: line 1 to step 8, line 2
  to step 6 (b), line 3 to a second sync after a ticket closes — not
  provable on demand; recorded on the item when it first happens — line 4
  to step 6 (c), line 5 to steps 2, 7 and 7b — `sd-status` shows key and
  state; the dashboard shows the key and, being an open worklist, the
  state only as presence (design, "The dashboard"), which step 9 records
  on the item — line 6 to step 4's grep.

**What cannot be verified from the repository, stated rather than invented:**
that the token authenticates the operator's own account (step 2 stops on
it); that `LOG-23818` is still open (either answer is correct and the row
says which); and that the nightly job's environment carries the variables,
which only the morning-after log shows.
