# Workflow controls and local rollout

The installed-state details below record earlier rollouts on 2026-09-08.
They do not establish the currently loaded build or complete the coordinated closeout.
Verify installation, process identity and live acceptance after delivering matching commits across all three repositories.

The workflow dashboard is installed at **http://127.0.0.1:8767** and privately at
**https://sol.tail6dbb92.ts.net:8443**. Remote access requires the Tailscale login
`sven@ignoranceisbliss.com`. The command pack, system repository and writing pack
share the installed `sd_db` library and `~/.local/share/sd/sd.db`. Ordinary work
progress belongs to the database.

## Daily use

| Need | Control |
| --- | --- |
| Capture work without a repository or PRD | Today, or `sd task add "Title"` |
| Prioritize, schedule, add details | Item screen, or `sd task edit ID` |
| Change task status | Item screen, or `sd task status ID STATUS` |
| Record and resolve a followup | Item notes, or `sd task note ID --kind followup --body TEXT` / `sd task resolve NOTE_ID` |
| See the same inventory as the dashboard | `sd today --json`, `sd store items --json` |
| Relink a moved work artifact | Item screen, or `sd work relink ID PATH` |
| Cancel repository work | Item screen, or `sd work cancel ID --reason TEXT` |
| Record verified code delivery | `sd work deliver ID FULL_COMMIT_SHA` |
| Move a writing piece through its stages | Writing screen, or `sd writing stage --piece YEAR/slug --stage STAGE` |
| Inspect current writing evidence | Item screen, or `sd writing readiness --piece YEAR/slug` |
| Park or revive a piece | Item screen, or `sd writing park --piece YEAR/slug [--revive]` |
| Observe jobs and assignments | Operations → Jobs, `sd jobs list`, `sd assignments list` |
| Inspect launchd services | Operations → Services, or `sd services list` |
| Start, stop or restart an eligible user service | Operations → Services, or `sd services start/stop/restart LABEL` |
| Inspect configured ports and observed TCP listeners | Operations → Ports |
| Find items by age in status | Operations → Progress; a bar opens matching Backlog items |
| See weekly numbers, cost and providers | Operations → Usage |
| Request a supported retry or stop | Operations, `sd jobs retry NAME`, `sd jobs cancel NAME` |
| Cancel a queued assignment | Operations, or `sd assignments cancel ID` |

Capture defaults to Task. Followup, Comment, Question, Decision and Proposal
require a Related item; the short inline CLI hint follows that selection.
`sd task note` defaults to Comment and accepts all five note kinds through
`--kind`. Use `--kind followup` for an action that should appear in Today.
The `sd` launcher is installed at `~/bin/common/sd` and is also managed by the
system repository's bin-links installer.

Run writing commands from the writing checkout. Existing `scripts/pack.py`
commands delegate to the same operations. JSON item responses carry a revision;
`--if-revision` requires the state you inspected. Browser forms always carry it.
Parked pieces and their followups stay out of Today, Backlog and resumed-session
followups. The Writing view can show parked pieces explicitly and revive them.

## Authority and review

Task completion requires no commit, pull request or GitHub issue. Repository
work has separate cancellation and delivery operations. Delivery checks the
full commit, delivery trailer and current default branch before recording its
receipt and shipment time together. An outdated external issue or branch name
cannot authorize completion or hold ordinary tasks open.

Suggestions default to local database rows. Publishing one as a GitHub issue
is an explicit action. External tracker snapshots carry their sync freshness
and remain context; they do not become the local progress authority.

Planning artifacts remain optional for small changes. Local code review stays
bounded by the existing review policy; status-only commits and bookkeeping
pull requests are not required to finish ordinary work. A stale review or a
blocking finding still requires evidence or a recorded disposition.

Writing readiness binds research and review evidence to the current draft and
review generation. Corrections invalidate prior readiness. An unstamped report
requires the digest actually reviewed; recording a verdict cannot silently
bless a changed draft. Publication is not a generic dashboard action.

## Installed state and recovery

The schema 2-to-3 migration preserved all 10 existing items exactly. The live
writing cutover imported 22 indexes, including 7 parked pieces, and verified
22 rows with zero differences. It removed only frontmatter status/publication
bookkeeping. Draft text, research, reports, article moves, concurrent commits
and Git history were preserved. Routine writing progress now changes rows,
not tracked content files.

Recovery material remains at:

- `/private/tmp/sd-workflow-implementation-kl1o4lht/backups`: original source
  patches/files, consistent database snapshots, and previous installed library.
- `~/.local/share/sd/writing-cutover-pmpw73si`: the original 22 writing indexes.
- `~/.local/share/sd/runtime-backups/`: prior LaunchAgents and exact installation
  plans. Each replacement keeps its own directory.
- `/private/tmp/sd-workflow-implementation-kl1o4lht/acceptance`: rehearsal
  results, apply manifests, CLI/HTTP acceptance tests and verification reports.

`sd writing recover` reconciles an interrupted cutover journal. It restores
only files still matching this operation's output and preserves concurrent
edits for explicit reconciliation. Database restore stages and validates the
snapshot before replacing a live database; it does not unlink live WAL files.
An older backup can lack post-cutover progress. `sd restore reimport REPOSITORY`
now previews recovery from verified historical source evidence. Applying that
preview requires its `--if-fingerprint` value. Missing or unproven sources
refuse recovery; the command cannot invent progress absent from the surviving
evidence. Retain backups and reconcile authority before resuming dispatch.

`sd shadow sync --strict` fails when any requested tracker interval remains
incomplete. It retains collected rows and holds the cursor for a later retry.
Bound recovery with `--since` and `--until`, using timezone-aware ISO timestamps
such as `2026-09-06T10:00:00Z`. Bounds are inclusive UTC seconds; fractional
seconds round down. The end cannot exceed the current time. Equal bounds
request one second. Complete historical intervals retain a later cursor.
Complete intervals separated from the cursor also retain it, preserving the
uncovered gap. Both cases report successful coverage and cursor retention.

`--max-requests` accepts a positive integer. `--max-seconds` accepts a positive
finite number. Omitted controls use the library defaults. Invalid controls
refuse before database access. If coverage exceeds these limits, retry a
smaller interval or increase the limits; strict mode continues to report
failure until coverage is complete.

The dashboard launcher uses the command pack's installed library in an isolated
interpreter. Health verifies schema, loaded process identity and hashes of the
running build; changing installed code requires a restart. Provisioning refuses
to replace a newer schema library with an older committed system version.
Deliver matching committed versions of all three repositories and verify a
fresh installation before activating the coordinated rollout. A source commit
or merged pull request alone does not establish the installed runtime.

## Verification on 2026-09-08

- `bin/sd-check --json`: `"status": "pass"`, 1,893 tests, 100% installer
  coverage, clean Ruff and mypy, and no security findings (4 existing workflow
  suppressions). The parked-followup query initially failed the security scan;
  static queries fixed it, and the complete check passed on the final source.
- Shared database suite: `Ran 445 tests in 83.292s`, `OK`. Final dashboard
  suite: `Ran 207 tests in 31.849s`, `OK`. Writing CLI/HTTP acceptance:
  9 tests passed.
- Operations acceptance: 5 tests passed using a controlled launchd fixture.
  No live job was retried or stopped. Daily workflow CLI/HTTP acceptance:
  8 tests passed.
- Live health: `ok=true`, `code_changed=false`, schema 3. Database integrity:
  `ok`; inventory: 32 items, 22 writing pieces, 7 parked.
- Live Today returns the same 16 item IDs in the same order through CLI and
  HTTP, with zero parked items. Browser inspection covered the 820px tablet
  layout; the temporary viewport was reset afterward.
- `git diff --check` passed in all three repositories. Source commits remain
  unchanged by this rollout; the user's concurrent writing commits were kept.

The final pack report and full unittest log are in the acceptance directory as
`operations-tabs-pack-check.json` and `operations-tabs-pack-unittest.log`.
The dashboard output is `operations-tabs-dashboard-tests.log`. The temporary
launchd lifecycle acceptance is `live-service-controls.json`: start observed
running, restart observed a new PID, stale stop refused, and final stop observed
unloaded. The fixture was cleaned up; no existing user service was controlled. Live CLI/HTTP
comparison and build identity are in `live-final-verification.json`.

## Private access rollout

Private access was explicitly approved and enabled on 2026-09-08. The new
`~/.config/sd/dashboard-private.json` is mode 0600 and names the exact HTTPS
origin and operator above. The LaunchAgent passes this configuration explicitly;
the previous local-only `dashboard.json` remains unchanged for rollback.
The installation backup is
`~/.local/share/sd/runtime-backups/dashboard-1guqtxwl`.

Every remote request revalidates the node, operator and private Serve route.
Sessions bind the origin and operator; HTTPS cookies are Secure, HttpOnly and
SameSite=Strict, and write requests also require the exact origin and CSRF token.
The authentication/runtime security scan passed. Live HTTPS checks returned 200
for Today, Writing, Operations and health; invalid identities and forwarded
local-host requests returned 403. Serve replaced a client-supplied false identity
with the authenticated identity. A valid remote session passed the POST security
checks and reached action validation; the deliberately empty action returned 400
before opening a database writer. No live job was invoked.

Port 8443 proxies only to `127.0.0.1:8767` and has Funnel disabled. The complete
remaining Serve configuration, including public 443 to port 8766 and its Funnel
setting, matched the saved pre-install snapshot exactly. The HTTPS UI was opened
and inspected in Chrome. Physical iPad access has not been tested; connect
Tailscale on the iPad under the approved login, then open the private URL.

The acceptance directory contains `private-access-dashboard-tests.log`,
`private-access-preflight.json`, `private-access-install.json`,
`private-access-live.json`, and `private-access-serve-after.json`. Source and
configuration backups are under `backups/private-access-20260908`.

## Operations layout rollout

The Operations update is installed on the same local and private URLs. The
latest runtime backup is
`~/.local/share/sd/runtime-backups/dashboard-xuqj6_qm`. The 18 promoted source
files match the reviewed manifest; the installed library matches all 38 files
in the tested wheel. No schema change was needed.

Live acceptance returned `"ok": true`: all five Operations tabs returned 200,
Today and Backlog show the exact inline CLI hint with no separate CLI details,
Backlog no longer contains the age chart, and all three populated Progress
links opened the matching active-item scope. The HTTP Services inventory
matched all 32 scoped IDs from `sd services list --json`. Ports showed the
running dashboard process on `127.0.0.1:8767`. Browser inspection confirmed the
capture hint, Services controls, Ports, Progress and Usage layouts; a disposable
browser fixture exercised Start, Restart and Stop. Existing user services were
only inspected. Physical iPad access remains untested.

The complete Tailscale Serve configuration matched the pre-install snapshot.
Health returned `ok=true`, `code_changed=false`, schema 3, PID 78555. Evidence
is in `operations-tabs-live.json`, `operations-tabs-install.json`,
`operations-tabs-serve-after.json` and `operations-tabs-source-verification.json`
in the acceptance directory above.

## Capture types rollout

Installed on 2026-09-08. Capture distinguishes standalone tasks from attached
notes. Related choices carry the stable ID, repository and current status;
completed and parked parents remain available without being reopened. Selection
loads a revision through the authenticated context endpoint. Stale or missing
parents retain the draft and require a deliberate refresh. An uncertain save
outcome retains the draft and requires checking the result before retrying.

The 13 promoted system files and installed 38-file library match the reviewed
build. Pack checks passed; the shared database suite passed 445 tests, and the
dashboard suite passed 207 tests. Repository guard failures in the initial
scratch checkout were resolved by restoring its missing Git context, without
weakening the checks. Browser tests created a standalone task and attached a
followup to the intended item, and confirmed draft retention after stale
selection and type changes. JavaScript checks covered out-of-order responses
and interrupted-save retry handling. These writes used only a disposable DB.

Live read-only acceptance verified all six types, all 32 related items, the
context endpoint and healthy schema 3 with unchanged Serve configuration.
Evidence and source/library backups are under
`/private/tmp/sd-capture-types-fn5icxdj/acceptance` and `backups` respectively.
The runtime rollback snapshot is
`~/.local/share/sd/runtime-backups/dashboard-fumx279q`.

## Limits

Job actions apply only to recognized installed launchd jobs. Unknown runtime
output disables controls. An accepted request is not a completed job; the UI
shows the observed state separately. Repeated requests are suppressed until
the observation changes. Running assignments without an owned cancellation
backend cannot be stopped through the dashboard. The system now includes an
owned queue runner and finite command execution. Their implementation does not
activate the service: verify its configured work volume, installed build and
observed runtime before dispatch. The pack exposes these controls through
`sd runner`; `sd-ship` records reviewed delivery and verified remote merges.

The refreshed UI contains Today, Backlog, Writing, Operations and item details.
Operations has Jobs, Services, Ports, Progress and Usage subtabs. Services lists
user LaunchAgents and third-party system LaunchDaemons. Controls apply to owned,
recognized, long-running user services; system daemons, scheduled/startup jobs
and the dashboard/Tailscale access services show why they are read-only. Stop
unloads for this login without deleting the plist or changing persistent
enablement. Start/restart honor restore, revision and identity guards.

Ports merges configured Docker-candidate ports with the TCP listeners visible
to the dashboard user. It retains all observed owners and addresses, and does
not infer process ownership from a configured port number. Failed observations
remain unknown; no listener observed does not prove another interface or
privileged process is absent. Other legacy plugin views remain CLI-only.
Metered-cost redesign is deferred; existing figures moved to Usage.

See `system/local-project-dashboard/RUNTIME.md` for the fingerprinted installer,
health checks and rollback limits. The earlier rollout evidence above records
its own source and live operations; use the coordinated delivery receipts for
subsequent commits, merges, installation and acceptance.
