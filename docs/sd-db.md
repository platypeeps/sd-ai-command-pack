# The workflow database: hub, lane host and judgments

`bin/sd-db` runs the workflow database's verbs from this checkout's `lib/`.
This page covers the hub and its satellites, the refusals, the lane host, `judgments`, the review queue, the item kinds, and renaming a repository by hand.
The module docstrings under `lib/sd_db/` hold the detail.

## One hub, many satellites: `serve` and `hub.json`

The hub is the one machine that holds `~/.local/share/sd/sd.db`.
A satellite holds no database.
It sends every open of the default database to the hub, one TCP session per connection.

### `serve` on the hub

    bin/sd-db serve              # the tailnet listener, port 8769
    bin/sd-db serve --loopback   # 127.0.0.1 behind a token: the suite over the wire

- `serve` opens the database on the hub's own disk, never through `hub.json`.
- It never creates a database. A missing file exits 1 and names the path it looked for.
- One server per file: it takes `<database>.serve.lock` beside the file.
  A second server exits non-zero and names the lock.
- It loads its build at start. After the pack's `lib/` changes, restart it.
  Until then it refuses each session with `HubRestartNeeded`.
- The first frame carries the client's protocol, package version, schema and build digest.
  The hub refuses any difference with `BuildMismatch`, which names the side to upgrade, and opens nothing.
- A launchd job on the hub runs the tailnet listener; the system repository's `local-machine-setup` installs it.

| | `--loopback` | Tailnet (no flag) |
| --- | --- | --- |
| Binds | `127.0.0.1` | this node's Tailscale IPv4 address |
| Admits | a session that sends the token from `<database>.serve.token` (mode 0600) | an untagged node of this node's owner |
| Token | fresh at each start, removed at exit | none |
| Opens | the file the session names, or the served one | the served database only |
| Used by | `python -m sd_db.testing.wire HOST:PORT TOKEN_FILE` | satellites |

Loopback is not a user boundary: every local account reaches `127.0.0.1`, so the token checks the account.

### Peer identity on the tailnet

The listener takes the peer from the TCP socket, never from a frame.
`sd_db.tailnet` asks `tailscale whois --json --proto=tcp` for the node and its owner.
The dashboard's direct listener reads the same rules.
Before anything opens, the listener refuses:

- a tagged node, an expired node, or a node that does not own the address;
- a login other than this node's owner;
- this node's own Tailscale addresses;
- a session that names a database path.

Each refusal goes to the log before any SQL runs.
`serve` does not start on a tagged node or while Tailscale is not running.

`whois` names a node's owner, not the local account that dialed.
So every process on an admitted satellite is trusted, service accounts included.
The refusal of the hub's own addresses keeps a second account on the hub out.

### `hub.json` on a satellite

`~/.config/sd/hub.json` makes a machine a satellite:

    {"hub": "hub.example.test", "port": 8769}

`python -I -m sd_db.satellite --hub HOST --apply` writes it; the system repository's machine setup runs that stage.

- No file: `connect` opens the local database.
- The file and no answer from the hub: `HubUnreachable`, which names the hub. Nothing is created.
- The file beside a local `sd.db`: `HubConflict`. A machine is a hub or a satellite, not both.
- A file that names no usable hub: `HubConfigError`, never a fall back to a local file.
- An explicit path equal to the default is the default.
  `sd-review --database ~/.local/share/sd/sd.db` opens the hub, though no file exists.
- An explicit path other than the default opens locally, such as a backup target.
- `init` and `migrate` refuse with `HubOnly`.
- `token_file` is for a loopback hub only; a satellite's file names none.

### A satellite on another build

The hub refuses a satellite whose `sd_db` build differs, with `BuildMismatch`.
Nothing installs a build: the pack's `lib/` is the one copy (sd:3280).
The satellite stage reports the build as `DIFFERS`, with both sides' values.
It names the `repo-sync.sh follow` verb that moves the pack to the hub's commit.

### A lost `COMMIT`: `request_outcome`

A write transaction over the wire carries a request id R.
R is a ULID the client makes at `BEGIN IMMEDIATE`.
The session owns R before any statement runs, and the hub refuses an R it has seen.
At `COMMIT` the hub inserts the `request_outcome` row on the same connection, then commits.
The row and the writes land together or not at all.
A transaction that wrote nothing gets no row.

When the answer to `COMMIT` is lost, the client asks the hub `outcome(R)`:

| Answer | Meaning | The client |
| --- | --- | --- |
| `recorded` | the transaction committed | returns, and runs nothing again |
| `in_flight` | a session still owns R | asks again, with a backoff |
| `absent` | the transaction did not commit | raises `TransactionLost(R)`; run the verb again, under a new id |

When the outcome is still unknown after 60 seconds (`OUTCOME_BOUND`), the client raises `UnknownOutcome(R)`.
Do not run the verb again until the hub answers for R.

- A plain `BEGIN` opens a read transaction under `query_only`: no R and no row.
- A session silent for 4 seconds inside an open transaction is closed, which rolls it back.
  That is below the 5-second `BUSY_TIMEOUT`, so a hub writer behind an abandoned satellite gets the lock.
- No `request_outcome` row is ever deleted.
- A local connection ignores R.

## Refusals

### What a session may not run

SQLite's authorizer on each session's connection refuses these statements:

- `ATTACH`, and every `VACUUM`, which SQLite authorizes as an `ATTACH`;
- `load_extension`;
- a `PRAGMA` not in `PRAGMAS` of `sd_db/serve.py`, and one that sets a value not in `PRAGMAS_WITH_ARGUMENT`;
- `BEGIN`, `COMMIT` and `ROLLBACK` that the hub does not route, whatever the text;
- a `query_only` setting inside a transaction the hub holds.

The client gets `StatementRefused`, which is also a `sqlite3.DatabaseError`.
The refused statement does not run, and the session continues.

### Hub-only verbs

A file lock or a directory beside the database exists on the hub only.
So off the hub, each verb that needs one raises `HubOnly` before it locks or writes.
The message names the verb and the hub.
`sd_db.database.refuse_hub_only` is the one guard; its callers are the list:

- the control gate of service controls and restore;
- `backup`, `restore`, `init` and `migrate`;
- runner controls and the runner's executions directory;
- `repo remove` and `item remove`;
- the retention and executions prunes;
- the publication journal and the `sd writing` cutover;
- shadow sync;
- `repo lane-host`, which holds the hub's ship lock while it moves a lane (sd:3075);
- `records render`, the vault mirror of base rows (next section).
- `sd reports brief render`, the vault copies of routine briefs.

`ledger.reserve` raises `LedgerRefused` with scope `hub`: provider calls are charged on the hub.
`ledger.release_orphans` sweeps nothing off the hub, because it asks the local kernel about owner pids.
The `sd-ship` repository lock follows the lane host instead; see the next section.

## Lane host

`repo.lane_host` names the machine that runs a repository's merge lane (sd:3075, sd:3003).
The value is that machine's `hostname -s`, lower-cased.
NULL, shown as `hub`, means the hub; every row starts there.

    bin/sd-db repo lane-host PATH build-2   # move the lane; prints before and after
    bin/sd-db repo lane-host PATH hub       # NULL again; refused while another machine hosts it

The dashboard does the same: Management, the repository's page, `lane_host`, Move lane.
Both refuse an unregistered path and a name outside `[a-z0-9-]+`.
A move sets every clone row of the remote, so clones never disagree.
The queue lives in the hub database, so pending entries follow a move and nothing is copied.
The dashboard Queue page lists each managed lane with its host; Release there ends a stuck claim.

A move holds the ship lock of the machine that hosts the lane, from before its read to after its commit.
Every ship takes that lock, so a held lock proves no ship runs.
A busy lock refuses the move and names its holder.
A ship that waited through the move reads the new host once it gets the lock, and refuses.
A move runs only on the hub, and only while the hub hosts the lane.
A lane on another machine refuses with "run the move on <host> (sd:3003 part 2)".

`sd_db.ship.hosts_lane` answers whether this machine hosts a repository.
`repository_lock` asks it before the flock and again once it holds it, so a move during a wait refuses.
On any other machine it raises `LaneElsewhere` (`lane_elsewhere`) and locks nothing.
A read fault, a database that cannot be opened, or clones that disagree raise `LaneUnknown` (`lane_unknown`).
Uncertain ownership never grants the hub.
A missing row reads as the hub.
The hub's lock file sits beside the database; a satellite host's sits under `$XDG_STATE_HOME/sd/ship-locks/`.

The machine that hosts a repository gates and merges it, and no request crosses a machine.
Schedule `sd-ship lane run --hosted` on every machine: it runs each lane the machine hosts.
[WORKFLOW.md § Parallel work](../WORKFLOW.md#parallel-work) covers the lane from the ship side.

## Channels

`repo.channels` names the publish channels a repository uses, and the folder each one writes to (sd:3462).
It is a JSON object; NULL, shown as `none`, means no setting, and every row starts there.
The design is `docs/work/2026-10-13-channels/design.md`.

    bin/sd-db repo channels PATH                                         # print: canonical JSON or none
    bin/sd-db repo channels PATH obsidian=Briefs/x notion=Example drive= # set; prints before -> after
    bin/sd-db repo channels PATH none                                    # clear

The keys are `obsidian`, `notion` and `drive`; `drive=` names the default folder, and a channel left out is off.
`feed=URL` adds the repo's one RSS/Atom subscription (sd:3980), an http or https URL with no credentials; `sd-watchlist` reads it.
The feed is inbound, not a channel: a setting naming only a feed publishes as no setting, and `channels.outbound` drops it for every publisher.
`jira=KEY` and `github=OWNER/NAME` name the repo's issue sources (sd:3461), inbound like the feed: the `repo` value that tracker's `shadow` rows carry, a Jira project key or a GitHub `owner/name`.
`repos.issue_sources` reads them for Today and Tasks; a managed repo refuses `github` and reads one set before as none, since managed repos use no GitHub issues.
`repos.mine_issues` reads each repo's open issues whose `shadow.reason` is `assigned` or `filed` (sd:4636); both collectors write the reason, `watched` rows stay synced and hidden, and a row synced before migration 34 reads unknown until a collect sees it again.
A set naming any channel replaces the channels; one naming none keeps them, so the dashboard form never drops a source. Each inbound key (feed, jira, github) is set on its own: a set that leaves one out keeps it. `none` clears all of it; to drop one source, clear and set the rest again. The verb prints `before -> after`, as stored.
A folder is a name, never an id or a URL: no leading `/`, no `.` or `..` segment, no control character.
A Notion folder is one page name, with no `/`.
`sd_db.channels.validate` checks every write; `repos.set_channels` is the one writer, `repos.repo_channels` the reader.
The verb refuses an unregistered path when it sets, and prints `none` with a note when it reads one.
A stored value the validator refuses, or a database not yet migrated, exits 1 and prints no value.
So does a read while a `restore` is unresolved, for every reader: the row may be older than the operator's last edit. A set still works; it is the restore's recovery.
A change takes effect at the next `sd-research-kit render` in the checkout, or the next commit.
The render reads the setting once; one it cannot read holds the vault copy and the queue, and a render by hand exits 1.
What each channel's folder replaces, and drain step 2's refusal: `skills/_shared/references/publication-contract.md`.

## Clone profiles and Dependabot

`repo.clone_profiles` names the machine kinds `repo-sync` clones a repository on: `personal`, `work` and `terra` (sd:4043).
NULL, shown as `none`, means none, and every row starts there.
A set has one spelling, its words in that order, so the column's CHECK is a closed list.
`repo.dependabot` is 1 for a repository outside the owner rule whose Dependabot pull requests the daily sweep may take.
The design is slice P2 of the system repository's config-to-DB design (sd:3983).

    bin/sd-db repo clones PATH personal,work    # set; prints before -> after
    bin/sd-db repo clones PATH +terra           # add one profile; -terra takes one away; none clears
    bin/sd-db repo dependabot PATH yes          # or no; prints before -> after
    bin/sd-db repo seed --clones personal       # add personal to each row repo-sync's lists give it
    bin/sd-db repo list --clones personal       # `<subdir> <owner/repo>`, the lines repo-sync reads

`repo clones` reads and writes in one transaction, so a `+P` beside a `-Q` on the same row loses neither.
`seed --clones P` reads `repos.common.conf` and `repos.P.conf` in the `repo-sync` config folder; terra reads its own list alone.
The profile is the argument, never `REPO_SYNC_PROFILE`.
A line with no row is registered as `repo seed` would, when its checkout is here.
A line with neither a checkout nor a row is named, and the run exits 1 after the other lines.
A line names a repository; its path only says where it sits.
The checkout's origin and the row's remote must each name the line's repository, or that line writes nothing, is named with what the path holds, and the run exits 1.
No origin counts as a mismatch here; plain `repo seed` refuses a differing origin too, and keeps the conf's slug for a checkout with none.
It only adds, one transaction per line, so a rerun finishes a stopped run.
`list --clones P` prints one line per row cloned on P, `.` for a checkout straight under `~/repos` (`SD_REPO_ROOT`).
A row that cannot be such a line exits 1, names every such row, and prints nothing on stdout.
Such a line needs a row one or two folders deep, a GitHub remote, and a folder named as the repository.
A database not yet migrated exits 1 too; neither case answers an empty list.

## `judgments`: what the judgment models cost, by stage

`bin/sd-db judgments` compares the stages that route a decision through a judgment model.
The system repository's `local-jev` writes a `judgment` row per call.
The mechanism each caller used before writes one too, under the same stage key and in the same table.
A fallback that cannot be counted against a judgment answers nothing.

    bin/sd-db judgments                 # every stage, both arms
    bin/sd-db judgments --since 2026-09 # a month; bounds are compared as text
    bin/sd-db judgments --json          # the same read, for a screen

### What a row holds

The table holds identifiers and counts, and nothing that was submitted.
No prompt, state, path, subject or body reaches it.
The two columns that could carry content are shaped, not only capped: a length cap lets anything short through.
`answer` is a number: a probability, a score, or a position into the caller's own criteria.
`ordering` is positions into the caller's own input.
`sd_db.judgment` refuses a row rather than truncate either.

The names are shaped too.
`caller`, `stage`, `primitive`, `question_id` and `pair` are identifiers: letters, digits and `.`, `_`, `:` or `-`.
They are caller-controlled, and a cap alone would accept a file path or a short subject line.
`provider` and `model` are exempt on purpose: they carry vendor names such as `anthropic/claude-opus-5`.

`location` is where the call came from; `caller` is who asked.
It is the git toplevel of the caller's working directory, else that directory.
`record` stores a path under `$HOME` as `~/` plus the relative path, and any other path absolute.
A bad `location` does not refuse the row.
A value over 255 characters, or one with a control character, is stored as NULL and the row is kept.

More columns record the conditions of a call.
A value that fails its shape is stored as NULL and the row is kept.

| Column | What it holds |
| --- | --- |
| `threshold` | the cut-off the caller applied (`--gate`, `--unsure-below`), from 0 to 1 |
| `run_id` | an identifier that groups the calls of one run, such as one review |
| `prompt_hash` | 16 lowercase hex digits hashing the question definition, never the state |
| `load_avg` | the one-minute load average when the call was made |
| `error_class` | an exception class name such as `ConnectionRefusedError` (sd:2973) |
| `error_detail` | an errno name or HTTP status such as `ECONNREFUSED` or `503`, never message text |

### Batches and gate events

A batched call asks several questions at once (sd:2966).
Its row is the call: tokens, latency, cost, `questions=N`, and no answer.
Given `answers`, one entry per question in order, `record` also writes one child row per question.
A child's `parent` names the batch row; its `question_id` is `<id>:<position>`.
A child carries the question's type as `primitive`, and its own answer and confidence.
It carries no tokens, latency or cost, so nothing is counted twice.
Every report counts calls from batch rows only; agreement and labels read the children.
A child whose field fails its shape is kept as `invalid` with that field NULL.

A gate event is not a decision.
A caller that declines at the gate, then records its own mechanism, writes two rows for one decision.
So the comparison leaves the gate row out of the calls and the declines, and counts it on its own line.

### Cost

A judgment row is not a `cost` row.
`cost` is money against a `bill`, and its `provider` is a foreign key into the registry; a judgment model is on neither.
A row's `usd` is the cost its caller reports.
Without one, `record` prices the tokens at the `price` (`in` and `out`, dollars per million) in `providers.yaml`.
An entry that names a `model` prices that model only.
With no usable price, `usd` stays NULL and the token counts are the record.
The report names those rows per arm as `unpriced`, with their providers.
`local-jev` rows name provider `typesafe`; its price is the operator's to enter.
An entry with `roles: []` is never chosen for a role.

A local model is priced by machine time instead (sd:2967).
An entry with `price: { hour: N }` prices a `jev`, `kev` or `haiku` row at N dollars per hour.
The time is `server_ms`, or `duration_ms` when the server reported none.
The rate is the machine's, so it applies whatever the entry's `model`.
A baseline row is not priced by time. With no `hour` price, a `local` row stays NULL, never 0.0.
A rate prices the rows written after it is entered; old rows are never repriced.

The operator measures the rate.
Take the machine's hourly cost, or measure its power under load and multiply by the electricity price:

    sudo powermetrics --samplers cpu_power,gpu_power -n 1   # watts, while the model answers
    # hour = watts / 1000 * dollars per kWh; 40 W at $0.15/kWh is 0.006

### Labels: whether a judgment was right

Reported confidence is not accuracy.
A row can carry a label: `override` is the answer an authoritative later source says it should have been.
It is a number in the shape of `answer`.
`override_source` names the rule that produced it, and `override_at` says when.
A row is right when the label equals the answer, compared exactly as decimals.
A row with no answer, such as a failed call or a batch row, cannot be labelled; a batch's child rows can.
The report counts labelled and right rows per arm, and per arm by reported confidence in tenths.
It prints each rule's known blind spot beside the stage it labelled.

`judgments label` is the one write path; a labeller uses these verbs and never opens the database itself.
The same label twice changes nothing.
A different label is refused unless `--replace` says to overwrite it.
A `kev` or `haiku` comparison row is refused: a pair's label lives on its Jev row.
A choice is labelled with a whole position from 1.

    bin/sd-db judgments unlabelled --stage JEV_SD_REVIEW --prefix sd-review-tier: --json
    bin/sd-db judgments label --row 42 --override 3 --source outcome.example

No labeller writes this table yet.
A label needs independent evidence of the right answer, never one derived from the prediction it scores (sd:2107).

### The comparison arms

`jev` can ask a local Kev and a Haiku model the same request beside each live call, once each arm is on (sd:2366).
Each answer is its own row, arm `kev` or `haiku`, with the Jev row's pair id.
It carries the latency the model reported in `server_ms`, and the distribution in `probabilities`.
The distribution is numbers in option order, never the keys.
The report above reads only `jev` and `baseline`; this one reads the three model arms:

    bin/sd-db judgments compare [--stage NAME] [--since STAMP] [--until STAMP] [--json]

It reports per stage, and per arm and provider:

- calls, and declines by cause;
- p50 and p95 latency, by nearest rank, so every printed number is one a call took;
- tokens and cost;
- agreement with the Jev row of the same pair;
- accuracy and Brier score on pairs whose Jev row carries a label.

A noul agrees when both sit on the same side of 0.5; the mean `|Δp|` is printed beside it.
A score agrees when the rounded scores are equal; its distribution feeds the Brier score only.
A batch is compared question by question: each child row against the Jev child with the same pair and `question_id`.
Its calls, latency, tokens and cost come from the batch row alone.

Each arm, Jev included, is also read against the old mechanism (sd:2761).
That is the baseline row a shadow call writes under the same pair id.
The line gives agreements over comparable pairs, the percent, and the five most common disagreements.
Each disagreement reads `old→arm`: 1 or 0 for a noul, a position for a choice, a rounded level for a score.
A pair whose old answer is not a number is counted and not compared.
Examples are a `--fallback` marker, or a noul asked under a `--gate` other than 0.5.
A stage with no such pair says `no paired samples with the old mechanism`.

## `review`: one queue of small questions

`bin/sd-db review` is the plumbing behind one review queue that any repository or experiment files into (sd:3635).
A producer writes one batch file and files it; the operator answers each question with one option; the producer exports the labels.
The design is the review-queue design in the system repository; `lib/sd_db/review.py` holds the note formats.

    bin/sd-db review file batch.json                      # file a batch; the same file again is a no-op
    bin/sd-db review export 4242 --out labels.jsonl       # labels with provenance, as JSONL
    bin/sd-db review export 4242 --key key.csv --out labels.jsonl  # sealed: closes the batch, then joins the key
    bin/sd-db review apply nightly                        # approvals to tasks; close or expire each batch

A batch is one task under the ref `review:<queue>:<batch>`, so a second filing finds the first.
Its first comment is the header; each question is a `question` note in the Decisions format, with one `Subject:` line.
A label is the Decisions ruling, `Ruling on note #N: <option>`; an undo is a `Withdrawn: ruling #M on note #N` decision.
A sealed export refuses a key whose SHA-256 is not the header's seal, and refuses while a question is open.
It commits the batch's close before it parses the key.
A batch once closed refuses every ruling and withdrawal.
Labels are read from the note history up to the first close, never from a question's resolution; a note written after the close by another path is exported as `late` and moves nothing.
The key is CSV; its first column names the subject.
`apply` acts only on questions that offer `Approve` and `Reject`; each approval files one task under `review-approved:<note>`.
It resolves a batch's open questions as `Expired, not ruled` after 7 days.

## The state kinds

`state.kind` has no CHECK since migration 031 (sd:3506): `writes.STATE_KINDS` is its one list, and `writes.record_state` refuses a kind outside it.
A list the library validates gets no CHECK: SQLite cannot alter one, so each new kind used to rebuild the whole table.

## The item kinds, and the two words called `followup`

`item.kind` is a closed list, guarded by a CHECK. Nine values:

| Kind | What it is |
|---|---|
| `work` | a change to a repository, planned under `docs/work/` |
| `task` | a scoped piece of work in a repository |
| `report` | a run report a scheduled job wrote |
| `skill-review` | a review of a skill, run by the catalogue |
| `idea` | **a writing piece on the article ladder, and nothing else** |
| `work-idea` | an idea about a repository or product, not yet planned work |
| `personal-idea` | an idea about life, which does not enter the writing pipeline |
| `personal` | a to-do, an errand, a chore; it belongs to no repository |
| `followup` | something to come back to, filed as an item of its own |

`idea` looks like the generic word and is not.
`writing.list_pieces` reads `kind = 'idea'` with a `piece`, and the dashboard renders writing controls on it.
So a personal or a work idea has its own kind, not a stage on `idea`.

`note.kind` is its own closed list of seven: `followup`, `decision`, `proposal`, `question`, `comment`, `exec` and `status_change`.
Only `followup` is in both lists. Migration 032 (sd:3510) dropped the `proposal` and `dep` item kinds: neither had a producer or a row.

- A `followup` note hangs off an item and is resolved against it (`sd task note <item> --kind followup`).
  A `followup` item stands on its own (`sd task add --kind followup`).
  If it makes no sense with the parent deleted, it is a note.
- A `proposal` is a note: `sd task note <item> --kind proposal` records one, and `reads.brief_notes` carries it into a brief.

`task`, `personal` and `followup` items (`workflow.TASK_STATUS_KINDS`) share the five `TASK_STATUSES`:
`planning`, `ready`, `in_progress`, `blocked` and `done`.
`work` keeps its delivery rules; `idea`, `work-idea`, `personal-idea` and `report` keep their own workflows.

`workflow.edit_item` is the verb a person uses to change a row's kind.
The target must be in the store's CHECK (`workflow.schema_kinds`) and in `workflow.HAND_KINDS`, the five `sd task add --kind` files.
A `work`, `report` or `skill-review` row keeps its kind, because its producer owns it.
So does an `idea` with a `piece`, and a row whose `fields` carry `contribution` or `skill_review` (`workflow.PRODUCED_FIELDS`).
The edit writes a `comment` note, `Changed kind <old> -> <new> by <who>`, in the same transaction.
`writes.upsert_item` also writes `kind` on every import, with no note: a vault-imported `idea` moved by hand goes back on the next import.

`work-idea`, `personal-idea` and `personal` (`workflow.REPO_LESS_KINDS`) are filed with no repository.
Read them as a group with `reads.backlog_items(connection, repo=reads.NO_REPO)` or the dashboard's `/tasks?repo=no%20repo`.
That is filing behaviour, not a constraint: `item.repo` has no per-kind CHECK, and `writes.create_item` takes a `repo` for any kind.

## `records render`: the vault mirror of base rows

Once a plugin's `store.driver` is `db`, its vault base rows live in `item` and `sd_db.records` writes them.
`records render [KIND ...]` writes them back into the vault as a read-only mirror; with no kind it takes every kind a `db` plugin declares.

- Each row's note sits at its `path`, with `status` from `stage`, the body verbatim and a `mirror-hash` of the rest of the file.
- One HTML page per base goes to `<vault>/docs/dashboard/base-<kind>.html`, for the dashboard's Documents tab.
- A file is overwritten only when its `mirror-hash` matches its content, or it has none and reads as its row. Any other file is a hand edit: it stays, and the render reports it.
- A note in the base folder that no row holds is reported and kept.
- It refuses off the hub, while a `restore` is unresolved, for a kind still on the `vault` driver, and when a base folder does not exist.

Each committed `records` write renders its kind, or every kind after a failed render. A write never fails for its render: it prints `mirror not updated: <reason>`.
Every render records the `heartbeat` state row `records-mirror`, body `{at, ok, kinds, written, refused, reason}`.
`records.mirror_state(connection)` reads the last one, `(timestamp, body)` or None; the dashboard's Health shows it.
The verb exits 1 on any refused file or a render that stopped.

## `sd reports brief`: routine briefs

A routine brief is one `item` row of kind `report`, source `brief`, keyed by its stem, `<YYYY-MM-DD> - <Series>` (sd:3459).
It is filed `done` and stays `done`: `sd reports list` skips it, and `acknowledge` and `reopen` refuse it.
`sd_db.routine_briefs` holds the rows; `sd_db.brief` is the session brief, a different thing.

- `add <file> --belongs-to <checkout>` files one brief. A file the rules refuse exits 2 before any write.
- The same stem with the same bytes prints `unchanged`. Other bytes are a conflict, exit 1, unless `--extend` (the row's text is a strict prefix of the file) or `--replace` (the operator's flag) allows the file.
- `list [--series S] [--since DAY] [--json]` and `show <stem>` read the rows.
- `import <folder> --belongs-to <checkout> [--replace <stem>]...` adds each missing stem and strips a `mirror-hash` line first. A row that differs is a conflict, never replaced unless its stem is named; the import prints `verified <n>` when every row it took reads back with the note's sha256.

The row is the source of truth: no counter or time decides a difference, because a restore rolls those back with the rows.

`render` writes each row's copy, `<vault>/<folder>/<stem>.md`, under the `records render` mirror rule (sd:4041).

- The folder is the owning repository's `channels` obsidian folder; no setting or `obsidian: {}` is `Briefs/<repo>`, and a setting without `obsidian` writes no copy.
- A setting it cannot read writes no copy and names the cause.
- A hand-edited copy and a brief-shaped note no row holds are kept and refused; the verb then exits 1.
- It refuses off the hub and while a `restore` is unresolved. A lock beside the database serializes renders, and each reads the rows only once it holds the lock.
- When the folder moves, it names the copies left in the previous folder and deletes none.
- Every render records the `heartbeat` state row `brief-copies`; `routine_briefs.copies_state` reads the last one.
- A hub `add` renders after its commit. A failed render prints `vault copy not written: <reason>`, and `add` still exits 0.

## Renaming a repository

There is no rename verb (sd:3172).
A rename by hand changes the keyed rows and the runner journal together.
Otherwise `bin/sd-db backup` stops with "runner row ... differs from the backup journal".

1. Stop the lanes, the dashboard and `sd-serve`, then run `bin/sd-db backup`.
2. In one transaction, change the old key (`~/repos/old`) to the new one in `repo.path` and every `repo` column:
   `item`, `cost`, `repo_protection`, `runner_lease`, `runner_run` (its `detached_from` too) and `shadow`.
   `SELECT m.name, p.name FROM sqlite_master m, pragma_table_info(m.name) p
   WHERE m.type = 'table' AND p.name LIKE '%repo%'` lists the columns.
3. Rewrite each file in `runner-journal/` beside `sd.db` whose `record.repo` names the old repository, by its key or its absolute path.
   Do not edit the text: `runner_journal.read` checks the envelope's sha256.
   Recompute it as `runner_journal.persist` writes it, with sorted keys and compact separators:

       import hashlib, json, pathlib
       path = pathlib.Path("~/.local/share/sd/runner-journal/<id>.json").expanduser()
       record = {**json.loads(path.read_text())["record"], "repo": "~/repos/new"}
       def compact(value):
           return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
       envelope = {"record": record, "sha256": hashlib.sha256(compact(record)).hexdigest()}
       path.write_bytes(compact(envelope) + b"\n")

4. Run `bin/sd-db backup` again; it passes when rows and journal agree.
