# Design — a second tracker with no rows

## What changed since the PRD, and why this document exists

The PRD closed on one question the repository could not answer: does the
operator intend to work Jira tickets. Note #1244 on sd:361 answers it, dated
2026-09-12: **yes, build.** The PRD's "if yes" branch then applies, in its
stated order — configuration first, one proving collect against the existing
loop, sd:603 taken, and only then the port planned with the item's "what to
build" list rewritten as a migration. This document is that plan. It does not
rebuild `refresh_issues` (`dashboard/collect.py:151`); it moves the shape of
that function into the library the nightly job already runs, and it says
which reader shows the first Jira row and how.

Three of the PRD's preconditions have moved since it was measured, and the
plan below is written against today's state rather than the PRD's:

| | PRD, at `cc93ea85` | Today, at `a593db65` |
|---|---|---|
| sd:603 | open, "a hard precondition" | **done**, `platypeeps/system` PR #305, squash `940c045a` |
| Library pin in `.github/workflows/tests.yml:90` | `3c4c723a`, pre-603 | `758dfb48`, which carries `008_shadow_tracker_key.sql` |
| Live `sd.db` schema | version 7 | **version 8**, index `shadow_by_tracker_url` (measured below) |

So the migration hazard the PRD called fact two is closed on every layer this
plan touches: the schema, the writer, the two migration sources, and the pin.
What remains is exactly the port.

## Measurement, 2026-09-12

The counts note #1149 ran, re-run today against the live database
`sd_db.default_path()` opened read-only, and the legacy index at the path
`index_path` (`dashboard/store.py:66`) builds — derived, not spelled, because
that function honours `XDG_CACHE_HOME` (unset on this machine when this ran):

```
python - <<'EOF'
import sd_db, sqlite3
from dashboard import store
c = sqlite3.connect(f"file:{sd_db.default_path()}?mode=ro", uri=True)
print(c.execute("pragma user_version").fetchone()[0])
print([r[0] for r in c.execute("select name from sqlite_master where type='index' and tbl_name='shadow'")])
print(list(c.execute("select tracker, count(*) from shadow group by tracker")))
print(list(c.execute("select key, count(*), max(timestamp) from state where kind='watermark' group by key")))
print(c.execute("select body from state where kind='watermark' and resolved_at is not null order by timestamp desc, id desc limit 1").fetchone()[0])
l = sqlite3.connect(f"file:{store.index_path()}?mode=ro", uri=True)
print(list(l.execute("select tracker, count(*) from issue group by tracker")), list(l.execute("select * from tracker_watermark")))
EOF
```

| Measure | 2026-09-12 (note #1149) | 2026-09-12 (this document) |
|---|---|---|
| `shadow` rows by tracker | `github` 3,668 | **`github` 3,668**, no other value |
| `state` watermark keys | GitHub only, 10 rows | **`github` only, 10 rows**, latest `2026-09-12T17:14:56+00:00` |
| Latest resolved watermark body | — | `collected_at 2026-09-12T17:06:52Z`, `window_start 2026-09-12T15:56:41Z` |
| `tracker-sync:*` heartbeats | — | `tracker-sync:github` only, 10 rows |
| `sd.db` `user_version` | 7 (note #1181, "until it runs") | **8**; the only index on `shadow` is `shadow_by_tracker_url` |
| Legacy `index.sqlite` `issue` by tracker | `github` 1,175 | **`github` 1,175**; watermark `2026-09-01T05:23:37Z`, unmoved |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` (required) and `JIRA_JQL` (optional) in this shell | 1 of 3 required set | **1 of 3 required set — the token; base URL and email unset; the optional JQL unset** (presence only) |
| Same four in the nightly and dashboard launch agents | — | none of the four named in either plist |

Nothing has moved since note #1149: same 3,668, same ten watermark rows, same
latest stamp. The one change is the schema, which is now at 8 on the live
database — note #1181 recorded it as 7 immediately after the merge and said
the migration would have to be run explicitly. It has been.

## Approach

**The port is the library's; the iteration is the verb's.** The library's own
docstring at `sd_db/shadow_sync.py:25-29` set the terms: "When there is a
second tracker there will be a second module, and the caller will iterate
them." Read literally, and the plan follows it literally:

- **A second module**, `sd_db/shadow_jira.py`, is `dashboard/jira.py` lifted
  into the library with its return shape changed from the pack's five-key
  dict to the library's `Collected` dataclass at `sd_db/shadow_sync.py:407`.
  The three carried-over rules in the pack module's docstring — `myself` is
  the availability check, match by account id, window in relative minutes —
  and the no-default-host rule at `dashboard/jira.py:25` move with it,
  verbatim. Nothing new is designed here; the module has tests in the pack
  (`JiraTests`, `tests/test_sd_dashboard_index.py:465`) that move with it.
- **The caller iterates.** `sync`, defined at `sd_db/shadow_sync.py:566`, already takes a
  `tracker` argument and already keys the watermark, the heartbeat and the
  row on it. It stays one-tracker-per-call. What changes is that `tracker`
  stops being a free string that selects only the *key* and starts selecting
  the *collector*: `"github"` runs today's path unchanged; `"jira"` runs
  collect, store, watermark-on-success, heartbeat, and nothing else; any other
  value is a `ValueError`. Today `sync(connection, tracker="jira")` would run
  GitHub's four buckets under Jira's watermark key and write the cursor there.
  Nobody calls it that way, and after this change nobody can.
- **The library exports the order.** `sd_db.TRACKERS = ("github", "jira")`,
  in report order, the same enumerated-not-discovered shape as
  `TRACKERS` (`dashboard/collect.py:24`) and for the same reason its comment
  gives. The verb `shadow_sync` (`bin/sd_shadow.py:126`) iterates it and calls
  `sync_shadow(connection, tracker=name, **options)` once per name, printing
  one block per tracker, each line prefixed `shadow sync[<tracker>]:`. A pin
  that predates the export yields `("github",)` through `getattr`, so the
  verb's tests keep passing at either pin.

**Why not iterate inside `sync`.** Because the GitHub path is not just a
collect: it plans contribution details, splits a budget between search and
details, runs the protection sweep, and dispatches notifications
(`sd_db/shadow_sync.py:600-648`). None of that is Jira's. A loop inside
`sync` would either run those stages per tracker, which is wrong, or branch
around them per tracker, which is the dispatch this design does anyway, with
a worse shape: one `Synced` for two trackers, and `--strict` unable to say
which one failed. The item asks for `--strict` judged per tracker. One
`Synced` per call is what makes that free.

### The watermark

Per tracker, already. `read_watermark` at `sd_db/shadow_sync.py:143` binds
`(WATERMARK, tracker)` and `write_watermark` at `sd_db/shadow_sync.py:164`
records `key=tracker`. Jira's cursor lives under key `jira` in the same
`state` kind, written only when Jira's own collect returned `ok` — no
errors, no truncation. **That is a change from the pack module**, whose
`collect` (`dashboard/jira.py:285`) sets `ok` from `not error` alone at
`dashboard/jira.py:322` and reports truncation beside it, leaving the
watermark decision to `refresh_issues`, which reads only `ok`. The library's
`Collected` convention folds truncation in — `ok=not errors and not
truncated` at `sd_db/shadow_sync.py:466` — and the port adopts it, so a
guard on `ok` alone is correct there and a truncated page holds the cursor.
Written under the same transaction shape GitHub uses at
`sd_db/shadow_sync.py:629-637`, including the re-read of the cursor under
the write lock. GitHub's success never moves Jira's cursor; Jira being
unconfigured never holds GitHub's. That is the rule `refresh_issues` states
at `dashboard/collect.py:160-162`, and it holds here because the keys were
never shared.

Jira's `moved` condition is simpler than GitHub's: there is no `detail["staged"]`
because there is no detail stage. It is `result.ok and (previous is None or
moment > previous)`. The `parse_iso(window_start) <= previous_time` clause
that guards GitHub's explicit `--since` recovery does not apply, because the
recovery flags do not reach Jira (below).

### Configuration: environment only, no default host

The three required names are the `ENV_*` constants `dashboard/jira.py:84-86`
declares; the optional fourth is read as a literal inside `settings`
(`dashboard/jira.py:89`) at `dashboard/jira.py:96`:

| Variable | Required | Read as |
|---|---|---|
| `JIRA_BASE_URL` | yes | trimmed, trailing `/` stripped; **no default, ever** |
| `JIRA_EMAIL` | yes | trimmed |
| `JIRA_API_TOKEN` | yes | trimmed; never printed, never logged |
| `JIRA_JQL` | no | replaces `DEFAULT_JQL` (`dashboard/jira.py:78`) when set |

They are read from the process environment and nowhere else — not a `.env`,
not a config file, not a plist the library knows about. **Where to set them
on this machine is a fact, not a design choice:** the nightly job
`local-cron-jobs/jobs/shadow-sync-nightly.job` runs
`sd shadow sync --strict`, and `local-cron-jobs/cron-jobs.sh` sources
`~/.config/shell/env.sh` before any job. That file is where `JIRA_API_TOKEN`
already is, and where `JIRA_BASE_URL` and `JIRA_EMAIL` go. The pack's part is
to say so in `skills/sd-status/SKILL.md` and in the verb's not-collected
line; the export itself is the operator's step and is the first step in
`implement.md`.

The GitHub collector has no equivalent because it has no configuration: it
reads `gh auth status` (`sd_db/shadow_sync.py:205`). Jira's `missing`
(`dashboard/jira.py:100`) is the analogue of `available`, and reports names
only.

### The "not collected" line, and which report prints it

Three surfaces read tracker state. Each prints an unconfigured Jira
differently, and the difference is deliberate:

| Surface | Line | Exit |
|---|---|---|
| `sd shadow sync` | `shadow sync[jira]: not collected (JIRA_BASE_URL and JIRA_EMAIL not set)` | 0, even with `--strict` |
| `sd-status`, `jira` section | `never collected (JIRA_BASE_URL and JIRA_EMAIL not set)`, then the stored rows if any | unchanged |
| `sd-dashboard index` | `issues[jira]: not collected (JIRA_BASE_URL and JIRA_EMAIL not set)` | 0 — already today, `bin/sd-dashboard:220-221` |

The verb's line is the new one. Its wording matches the dashboard's because
`issue_lines` (`bin/sd-dashboard:200`) settled it: "a tracker that cannot be
reached is a reported row, never an exit code." The reason text comes from the
collector's `missing` list, joined as "A, B and C", the same sentence
`collect` (`dashboard/jira.py:285`) already builds. With every variable set
and the credentials wrong, the line is instead `cursor held: Jira rejected the
credentials (401 Unauthorized); check JIRA_EMAIL and JIRA_API_TOKEN`, which
`--strict` does turn into exit 1 — that is a configured tracker failing, and
the item's fourth acceptance line asks for exactly that distinction.

**How the verb tells the two apart.** `Synced`, the dataclass at `sd_db/shadow_sync.py:528`,
gains one field, `configured: bool = True`. Jira's sync sets it `False` when
`missing` is non-empty and returns before any request is made — but after
writing the `tracker-sync:jira` heartbeat with `ok False` and the reason, so
that `sd-status` on the same machine can say *why* there is no Jira row
without re-reading the environment. The verb reads
`getattr(result, "configured", True)`, so a pin without the field reports as
it does today. `--strict` exits 1 when any tracker with `configured` true has
`ok` false; an unconfigured tracker is a line, never an exit code.

### Rows: keyed on (tracker, url), and what sd:603 changed so this is safe

A Jira row is `normalize` (`dashboard/jira.py:229`) as it stands: `tracker`
`jira`, `url` `{JIRA_BASE_URL}/browse/{KEY}`, `repo` the project key,
`number` `NULL`, `kind` `issue`, `state` `open`/`closed` from the status
*category* via `state_of` (`dashboard/jira.py:217`), `author` the reporter's
display name. `store` at `sd_db/shadow_sync.py:477` writes it through
`upsert_shadow` at `sd_db/writes.py:442`, whose conflict target is now
`(tracker, url)` (`sd_db/writes.py:468`). Before PR #305 it was `url` alone
with `SET tracker = excluded.tracker`, which meant the last writer took the
row. A Jira URL and a GitHub URL never coincide in practice, so the hazard was
never that Jira would adopt a GitHub row by accident; it was that the store
*permitted* it, and that the two import sources keyed by url alone would have
collapsed two rows into one on the way in (`sources/index_cache.py`,
`sources/issues.py`, both fixed in the same PR through `shadow_identity`). All
three are closed, the pin carries them, and the live database has run the
index swap. The row-keying question is therefore settled by measurement, not
by this design: `shadow_by_tracker_url` is the only index on the live table.

**No new column.** The item asks for "the issue key carried where the
projection can show it." The key is the last path segment of the URL and
nothing else; `url.rpartition("/")[2]` recovers `LOG-23818` from
`https://host/browse/LOG-23818`. A `key` column would be a second copy of a
stored fact, which is the ruling sd:603 recorded for `why` and `updated_at`
and the comment above the table now carries. The reader derives it.

### The seed row

After the first successful Jira collect, the row to check is:

| Column | Expected |
|---|---|
| `tracker` | `jira` |
| `url` | `${JIRA_BASE_URL}/browse/LOG-23818` |
| `repo` | `LOG` |
| `number` | `NULL` |
| `kind` | `issue` |
| `title` | `Benchmark harness` (as read 2026-09-10; may have been edited) |
| `state` | `open`, if its status category is still not Done |

The PRD records that `LOG-23818`'s state was not re-measured, and this
document does not re-measure it either. If it has closed since 2026-09-10 the
row's `state` is `closed`, which is the *correct* answer and is itself the
third acceptance line. The first window is 90 days
(`FIRST_RUN_WINDOW`, `dashboard/jira.py:64`), so the tail of Done tickets the
item lists (`LOG-21060`, `LOG-21118`, `LOG-21119`, `LOG-21338`, `RS-6`
through `RS-41`) lands as `closed` rows in the same run if their `updated`
falls inside it.

### Readers

**`sd-status`.** `_database_issues` (`bin/sd-status:1134`) reads
`tracker_items(connection, tracker="github", repo=slug, ...)` at
`bin/sd-status:1146` and `tracker_freshness(connection, "github")` at
`bin/sd-status:1147`. Both library functions already take the tracker
(`sd_db/progress.py:314`, `sd_db/progress.py:349`); only the caller is
hard-coded. Two things are wrong with widening it naively:

1. The section is "this repo": `repo=slug` scopes to the checkout's GitHub
   slug, and a Jira row's `repo` is a project key. No Jira row would ever
   match, and the section would silently keep saying `github` only.
2. `_render_issues` (`bin/sd-status:3378`) prints `#{row['number']:<6}` at
   `bin/sd-status:3394`. With `number` `NULL` that is
   `TypeError: unsupported format string passed to NoneType.__format__`,
   confirmed on this interpreter. The first Jira row the section tried to
   print would take `sd-status` down with a traceback.

And a third thing, which rules out a block *inside* the issues section:
`issues_section` (`bin/sd-status:1181`) returns at `bin/sd-status:1197-1199`
with `no GitHub remote` before any database is opened, and `_database_issues`
closes its only connection before `_render_issues` runs. There is no path
through that section that reaches a Jira row in every checkout, and its
heading is `issues (this repo, from the index)`, which a global row would
contradict.

So the design is: a **fourteenth section**, `jira (shared database, all
repositories)`, rendered after the issues section, with its own producer and
its own renderer. `jira_section()` opens its own read-only connection when
`sd_db.default_path()` exists — the same gate `_database_issues` uses — and
never depends on the checkout's slug. It calls `tracker_items(connection,
tracker="jira", state=None)` with no `repo`, because the operator's Jira
involvement is not a property of the checkout, and
`tracker_freshness(connection, "jira")`. The renderer prints:

1. A freshness line, keyed on `last_success_at` rather than on the state
   word: `tracker_freshness` at `sd_db/progress.py:314` answers `never` only
   when there is no success *and* no failed heartbeat, and `degraded` the
   moment a heartbeat with `ok False` exists — which an unconfigured Jira
   writes every night. When `last_success_at` is `None` the line is
   `never collected`, with ` (<reason>)` appended when the latest heartbeat
   carries one; otherwise it is the `external context: <state>; last
   successful sync <stamp>` pair the issues section already prints.
2. **Every stored row, whatever the freshness line says.** The library keeps
   rows from a partial collect on purpose — `store` runs before the cursor
   decision at `sd_db/shadow_sync.py:630` — and a first run that truncated
   has written rows the verb reported as written. Hiding them behind a
   `never collected` line would contradict the verb. Open rows print first
   as `KEY  open  title`; closed rows print after them, as
   `KEY  closed  title`, but only those whose `last_seen` is within seven
   days, because a Done ticket stops being re-seen once it leaves the JQL
   window and a permanent list of every ticket ever closed is not a
   worklist. The key is derived from the URL; nothing formats `number`.
3. `none` when there are no rows at all.

`state=None` rather than `"open"` because the item's fourth "what to build"
line and third acceptance line require a close to be *recorded*, and this
document allows `LOG-23818` to have closed before the first run. A reader
that filtered to open would store the close and hide it. The sixth
acceptance line — `sd-status` shows `LOG-23818` with its key and state — is
met by that section in either state, on the first run, because a seed row's
`last_seen` is that run.

The section is added to the heading order the skeleton test recites at
`tests/test_sd_status.py:3555-3560`, and the JSON output carries it under
the key `jira`.

**The dashboard.** `sd-dashboard` reads `index.sqlite` through `store.issues`
(`dashboard/server.py:638`), not `shadow`, and its collector is
`refresh_issues` with Jira already in `TRACKERS`. It shows `LOG-23818` the
moment the same three variables are exported and `sd-dashboard index` runs —
no code change, and the page already renders a row whose `number` is null by
its key (`dashboard/app.js:116-120`), which is the null-number case
`sd-status` gets wrong today. That is the PRD's proving step, and it is step 2 of
`implement.md`. Porting the dashboard onto `shadow` is the retirement of
`index.sqlite`, which is a separate item and not widened into this one.

**`sd-trackers ref jira:KEY`** — no change, as the item says.

### The docstring

The paragraph at `sd_db/shadow_sync.py:25-29` is replaced by one that names
the second module, says the caller iterates `TRACKERS`, and cites sd:361 and
the 2026-09-12 decision the way it cites the 2026-09-06 one now. The sixth
acceptance line is a grep.

## Decisions

- **2026-09-12 — the port lands in the library; the pack keeps
  `dashboard/jira.py` until `index.sqlite` retires.** Two copies of the Jira
  rules for a while, both under test. Reversed the day the dashboard reads
  `shadow`; that item deletes the pack copy and 363 lines of `DASHBOARD_CAP`
  (`tests/test_loc_caps.py:223`) with it.
- **2026-09-12 — the verb iterates; `sync` stays one tracker per call.**
  Reversed if a third tracker arrives with GitHub's shape (details, budget
  split, protection) rather than Jira's, at which point the per-tracker stage
  list becomes data and the loop moves down.
- **2026-09-12 — `--since` and `--until` are GitHub's.** They exist to re-walk
  a GitHub search-cap gap. Jira's window is relative minutes, so an absolute
  `--until` in the past cannot be expressed without the account's timezone,
  which is the defect the relative form was chosen to avoid. A Jira run that
  truncates or errors holds its cursor and re-reads the same window next
  night, which is all a recovery flag would do. When either flag is given,
  the verb runs GitHub only and prints `shadow sync[jira]: skipped (recovery
  window is GitHub's)`. Reversed if a Jira collect ever needs a wider window
  than a held cursor gives it.
- **2026-09-12 — no `key` column, no schema change.** The key is the URL's
  last segment. Same ruling as sd:603's for `why`.
- **2026-09-12 — `Synced.configured`, defaulting `True`.** One field, so the
  verb can tell "not configured" from "failed" without parsing a reason
  string. Reversed if the library grows a typed reason.
- **2026-09-12 — `sd-status` prints Jira as its own section, not inside the
  per-repo issues section.** The issues section is gated on a GitHub remote
  and closes its connection before rendering; a Jira row has no slug. Reversed
  if items gain a Jira `external_id` and a per-repo join becomes meaningful.
- **2026-09-12 — closed Jira rows print for seven days after they were last
  seen, then drop from the section; they stay in `shadow`.** Reversed if the
  operator wants a `--closed` switch, at which point the seven days become
  that switch's default.

## Rejected alternatives

**A `TRACKERS` tuple of modules inside `sync`, looping like
`refresh_issues`.** The obvious port, and the one the item's wording invites.
Rejected above: the GitHub path carries four stages that are not collects,
and a loop over modules would need each module to declare which stages apply
to it. That is a plugin interface for two members.

**Storing the Jira key in `number`.** `number` is declared
`INTEGER` at `sd_db/schema/001_initial.sql:114`, and `LOG-23818` is not one. SQLite
would store the text, `_render_issues` would print it, and the first reader
that does arithmetic on `number` would meet a string. No.

**Reading credentials from the `jira` MCP server's environment block.** The
PRD notes they exist there. The library reads the process environment and
nothing else; reading another tool's configuration is standing rule 1's
"does not touch repo files for its own purposes" one layer out.

**Failing `--strict` on an unconfigured Jira.** It would turn every machine
without Jira credentials red every night. The item's second acceptance line
forbids it, and the dashboard settled the same question in 2026-08.

## Risks

**The PRD's citation `sd_db/schema/001_initial.sql:99` no longer points at
`shadow_by_url`.** PR #305 added a 25-line comment above the table, so the
index line is `sd_db/schema/001_initial.sql:124` on the pinned library, and
it now carries the note "Migration 008 replaces this". The PRD was right at
`754204d`; it is stale at `758dfb48`. Not silently corrected here: the
PRD's fact two is historical and its numbers stand as measured.

**The PRD's table says the live database was at 7.** Measured 8 today. The
PRD's "sd:603 lands before any migration" is satisfied more completely than
it knew; nothing in the plan depends on 7.

**Two collectors, one set of credentials.** Exporting the three variables
configures both `dashboard/jira.py` (through `sd-dashboard index`) and the
library port. They write to different stores and neither reads the other's
watermark, so they cannot interfere; they can double the Jira API traffic on
a machine that runs both, which is bounded by `MAX_PAGES` at 50 per page and
is accepted.

**The first window is 90 days wide and paged to ten.** 500 issues is the
ceiling for one run. The item's seed data is twenty tickets. If the
operator's involvement exceeds 500 updates in 90 days, the first run reports
`truncated` and holds the cursor, and the next run re-reads the same window
— it never converges. Accepted because the seed measurement says twenty, and
named so that the symptom ("cursor held" every night with `truncated: jql`)
is recognised rather than debugged.

**`JIRA_API_TOKEN` is set in the shell but the other two are not.** The
token's presence was checked, not its validity. Step 1 of `implement.md`
exports the other two; step 2 is what proves the three together reach Jira.
If step 2 fails on credentials, the failure is the operator's and the port
does not start.

**The pack's tests for the verb stub `sync_shadow` at one pin.** After the
library change, `tests/test_sd_suggest.py` runs at the CI pin
(`.github/workflows/tests.yml:90`), which will not carry `TRACKERS` or
`configured` until the pin moves. The verb is written to work at both pins,
and the pin bump is its own PR against a sensitive file (`.github/sd-review.json`
lists `.github/workflows/**`) — the same sequence sd:360 followed in #888.

**Not accepted, and open: which Jira account the token belongs to.**
`myself` returns the account the token authenticates, and `DEFAULT_JQL`
selects by `currentUser()`. If the token was minted for a service account,
the first run succeeds and returns that account's involvement, which is not
the operator's. The seed row would be missing and nothing would say why. Step
2's check compares the `accountId` `myself` returns against the one the
operator's session shows; this cannot be verified from the repository.
