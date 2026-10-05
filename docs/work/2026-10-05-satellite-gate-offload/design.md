# Design — satellite gate offload

## The shape

The satellite gates; the hub merges. The merge still runs under the hub's
`repository_lock`, in the hub's lane, as the sd:1335 Decision requires. Two
things change. The merge gate reads a receipt from the satellite in place of a
run on the hub. And the satellite asks for the merge with a row in the hub's
database, which the hub's lane takes in.

| Step | Machine | Command | What it does |
|---|---|---|---|
| 1 | satellite | `git merge origin/main` on the branch, or `sd-ship prepare --catch-up` | The head contains the current base before any gate |
| 2 | satellite | `sd gate check --base main` | Runs `sd-check`; writes the satellite's own receipt and the offload receipt over the wire |
| 3 | satellite | `sd-ship prepare --item N --title T --body-file F` | Reviews (its gate reuses step 2), pushes, binds the PR, writes `ship:`, posts `sd/local-gate` from the offload receipt |
| 4 | satellite | `sd-ship lane request --item N --manual` | Writes the lane request row for this repository and item over the wire |
| 5 | hub | the scheduled job: `sd-ship -C <hub checkout> lane run --satellite-only`, every 5 minutes | Starts the lane runner for satellite entries only; exits at once when a runner already holds the lock |
| 6 | hub | `lane run` intake, before each claim | Validates each new request, adds a queue entry marked `gate: satellite`, writes `queued` to the row |
| 7 | hub | `lane run` processing the entry | Fetches the branch; head and base checks; no prepare, no catch-up, no speculation; then `sd-ship merge --item N --branch B --expected-head H --manual --satellite-gate` |
| 8 | hub | `sd-ship merge --satellite-gate` | Accepts the offload receipt under the trust rule; posts no status; merges |
| 9 | hub | `lane run` landing | Deletes `origin/B` with a lease on the merged head; writes the outcome to the row; notes the item |

Step 3 alone also gates when step 2 was skipped: `sd-review --gate-check`
runs the same `check_in_worktree` and writes the same rows.

## Decisions

Ruled by the operator on 2026-10-05, through the team lead. Each ruling took
the recommendation the first draft of this page gave, except Q2.

- **Q1 — the opt-in lives in a `repo` column.** `repo.satellite_gate`,
  `off|accept`, default `off`, set by
  `sd-db.sh repo satellite-gate <path> off|accept`, like `runner_merge`. A
  library older than the column reads `off`. The grant is the operator's, per
  repository, outside the tree.
- **Q2 — the handoff is a request row that `lane run` polls.** The first
  draft recommended SSH enqueue; the operator chose the row. "Handoff" below
  is the design for it.
- **Q3 — an offload receipt stands for 6 hours.** `OFFLOAD_WINDOW_SECONDS`
  equals `TREE_REUSE_WINDOW_SECONDS`, for either key.
- **Q4 — the scheduled run is for satellite requests only.** Ruled about
  04:25 MDT on 2026-10-05. The scheduled `lane run` takes in and merges
  satellite entries only. Hub entries still wait for an integrator's
  `lane run`. This replaces the first review's rebuttal of C-11.

## Overlap with sd:2724 and sd:2722

**sd:2724, folded in.** It was filed at 08:14 MDT on 2026-10-05: "Hub merge
reuses the satellite's gate receipt: portable receipt binding, reuse-first
merge". It has the same goal as this item and adds measured evidence:

- A satellite `sd gate check` passed, and its receipt (revision 29982)
  landed on the hub over the wire. The hub could not reuse it.
- The satellite runs as another local login than the hub. Its python and
  `make` digests matched the hub's. Its `environment_sha256` did not:
  `gate_environment` keeps `HOME`, `USER` and the whole `PATH`.
- The hub alone produced 8 distinct `environment_sha256` values for
  `make check` repositories that day, so same-machine reuse breaks too.

Its three work points map onto this record:

| sd:2724 point | Here |
|---|---|
| 1. Portable binding: bind tools, python and a named allow-list of variables, not `HOME`, `USER` or the whole `PATH` | Narrowed (C-17). Step 2a builds a portable view for the hub's offload comparison only. Local reuse keeps the whole environment, so same-machine reuse across hub sessions stays open under sd:2724 |
| 2. Hub reuses first and runs the gate only on a real miss | "Plain merge reuses first" under the trust rule, implement step 4 |
| 3. Docs: a "who does the work" table and one rule line in the system repository | Implement step 8 |

This record does not edit sd:2724. The operator ruled at 08:40 MDT that it
stays open as the item for step 2a.

**sd:2722, separate.** "Gate receipts: for a repository other than the pack,
hash only sd-check's import closure, not every pack bin/ file." It shrinks
what `gate_inputs` hashes. Clause 6 compares whatever `gate_inputs` hashes,
so `pack_bin` follows sd:2722 with no change here. sd:2722 makes
`satellite_pack_mismatch` rarer, and helps hub-only reuse too. It needs no
part of this item, and this item needs no part of it.

## The offload receipt

### Why a second row

The satellite's own receipt keeps working as today: its key and binding serve
the satellite's next prepare. The offload receipt is a second row with a key
that both machines compute alike. Two rows, each written in its own
transaction, keep the two readers apart. With one shared key, a satellite
write would append a newer revision over the hub's own receipt. `ship.save`
would then refuse the next writer as a concurrent change.

### Key

    sd-gate-offload:v1:<sha256 of [slug, head]>          head key
    sd-gate-offload:v1:<sha256 of [slug, "tree", tree]>  tree key

`slug` is `owner/name` from `remote.origin.url`, lower case, as `sd-ship`
derives `self.repository`. The `ship:` key already names a repository this
way, and that is why a hub lane finds a satellite's `ship:` row today. The
tree key follows `tree_key` in `bin/sd_gate_receipts.py` unchanged.

### Row

Written through `sd_db.ship.save`, so the store, the revision check and the
request-id protocol of sd:1335 step 5 apply as for every `ship:` row.

| Field | Value |
|---|---|
| `writer` | `sd-satellite-gate` |
| `satellite` | `{"login", "address", "hostname"}`: `sd_db.tailnet.this_node()` gives the owner login and the Tailscale IPv4 address; `socket.gethostname()` is for display only |
| `hub` | `served_by(database)`, the `host:port` the row went to |
| `binding` | the satellite's whole `gate_binding` output, unchanged |
| `offload_view` | the portable view of the run's environment (step 2a; "The offload view" below), taken before the run; the satellite's own receipt keeps it, a reuse writes the kept one, and a view that moves during the run writes no row |
| `pack_bin` | sha256 of the pack `bin/` files that `gate_inputs` hashes, or `"tree"` when the run gated its own tree (`gates_itself`) |
| `pack_rev` | `git rev-parse HEAD` of the pack checkout, for the refusal text only |
| `local_block` | sha256 of the copied `CLAUDE.local.md`, or `"absent"` |
| `reading` | the passing reading, as `record_pass` stores it |
| `head` | the commit that passed |
| `recorded_at` | the run's time on the satellite's clock; a reuse keeps the original run's time |

### What the hub compares, and what it only records

The hub checks the head out into a temporary worktree, as the merge gate does
now before `examine`. That needs a checkout, not a run. It then computes the
tree-derived part of the binding. That part does not resolve a single tool:
`gate_binding` returns `None` whenever `tool_identity` cannot find a tool on
the hub's `PATH`, and a hub without `cargo` must still compare a Rust
repository's receipt. So implement step 4 splits `gate_binding` into a
tree part and a machine part, and `gate_binding` returns their union as today.
The hub never compares the machine part. It compares `offload_view`
once step 2a lands.

| Binding field | Hub compares | Why |
|---|---|---|
| `schema`, `reuse`, `head`, `tree`, `fork` | yes | The commit, or the tree and the merge base's tree, that passed |
| `inputs` | yes | Hashes the head or tree, `CLAUDE.local.md` and the pack `bin/`. Equal inputs mean the same pack and the same local block. `pack_bin` and `local_block` name which part differs |
| `scope`, `detection` | yes | Pack code over the tree, the local block and the base. A difference means another command ran |
| `tools` | through `offload_view`, after step 2a | Paths may differ between logins; bytes must not. A tool the hub cannot resolve is recorded, not compared, and named in the merge's provenance |
| `python` | through `offload_view`, after step 2a: `python3` is in `OFFLOAD_TOOLS` | sd:2724 measured equal digests on both machines |
| `environment` | no; `offload_view` stands in for it, after step 2a | The digest holds `HOME`, `USER` and absolute `PATH` entries, so it never matches across logins |
| `satellite` | no, recorded | `serve` admitted only the operator's untagged node (sd:1335 step 7). A second check reads the same claim |

The first brief asked for the pack `bin/` digest as the one compared field.
Comparing `inputs` covers it and adds the `CLAUDE.local.md` digest. That file
can spell the repository's check, so a different copy means a different
command. Under the pack's own tree key with `"tool": "tree"`, `inputs` leaves
out `bin/` (sd:2613). There the running pack does not decide what ran, and
`pack_bin` reads `"tree"` on both sides.

### The offload view

Local reuse does not change. `gate_binding` keeps `environment_sha256` over
the whole `gate_environment`, and every local receipt binds it as today.
The ship review of 884d31a3 showed why (C-17). Equal `make` bytes can run
another python or compiler through another `PATH` order. `HOME` selects
tool configuration.

The satellite writes `offload_view` from the run's own environment. Only the
hub reads it, only on the offload path, and only when `repo.satellite_gate`
is `accept`. It has four parts:

| Part | Content | What it covers |
|---|---|---|
| `path` | the gate's `PATH` entries in order, each `$HOME` prefix written as `~` | Equal order: a name resolves through the same directory on both sides |
| `tools` | sha256 of each name in `OFFLOAD_TOOLS`, resolved on that `PATH`, and of each tool `gate_binding` resolves | A name the check reaches through `make` or a script has equal bytes |
| `home_files` | sha256 of each file in `OFFLOAD_HOME_FILES` under `HOME`, or `"absent"` | Named tool configuration under `HOME` is equal |
| `variables` | sha256 of the value of every other variable `gate_environment` keeps, with the `$HOME` prefix written as `~` first, so a row holds no credential | A variable that steers the check is equal. A variable present on one side only misses |

`OFFLOAD_TOOLS` is one pack constant: `sh`, `bash`, `make`, `python3`,
`git`, `cc`, `c++`, `clang`, `cargo`, `rustc`, `node`, `npm`, `uv`.
`OFFLOAD_HOME_FILES` is another: `.gitconfig`, `.config/git/config`,
`.cargo/config.toml`, `.npmrc`, `.config/pip/pip.conf`, `.config/uv/uv.toml`.
A name the hub cannot resolve is recorded, not compared, and named in the
merge's provenance. A name the hub resolves and the satellite does not
misses with `satellite_binding`.

The variables part compares by exclusion, not by an allow-list. An unknown
variable that differs misses, which costs one hub run. An allow-list would
let it pass unseen.

Residual risk on the offload path:

- an executable reached by a name outside `OFFLOAD_TOOLS`, whose bytes
  differ between the machines;
- tool configuration under `HOME` outside `OFFLOAD_HOME_FILES`, and outside
  `HOME`, such as `/etc` or the package manager's prefix;
- shared libraries that the compared tools load.

A repository whose check depends on one of these leaves `repo.satellite_gate`
off.

## The trust rule

`sd-ship merge --satellite-gate` accepts an offload receipt in place of
`sd-check` only when every clause holds. The clauses run in this order, and
the first that fails refuses with its code. No clause failure starts a run.

| # | Clause | Refusal code |
|---|---|---|
| 1 | `repo.ci` is `local` and `repo.satellite_gate` is `accept` for this repository | `satellite_gate_off` |
| 2 | The pull request is not BEHIND its base (`refuse_behind`, unchanged) | `base_moved` |
| 3 | An offload row exists at the key for this slug and the exact `--expected-head` (or its tree) | `satellite_receipt_missing` |
| 4 | `writer` is `sd-satellite-gate`, `reading.status` is `success`, and `satellite` is present | `satellite_receipt_invalid` |
| 5 | The compared binding fields equal the hub's (table above); the refusal names each differing field | `satellite_binding` |
| 6 | Within that, `pack_bin` equals the hub's; the refusal names both digests and both `pack_rev` values | `satellite_pack_mismatch` |
| 7 | Age on the hub's clock is at most `OFFLOAD_WINDOW_SECONDS`, and `recorded_at` is at most 300 s in the hub's future | `satellite_receipt_expired` |
| 8 | The newest `sd/local-gate` status at the head is `success`, posted by `viewer_login()`, and its description starts with `head[:12] inputs <digest>`, where the digest is the hub's own `gate_inputs(root, head)` | `satellite_status_missing` or `local_gate_foreign` |

Clause 6 is a named case of clause 5, so a pack mismatch gets its own
remedy. Clause 8 reuses `local_gate_passed` and adds the description test.
The digest is the one `local_gate` would post on the hub for this head, so a
status from a run with another pack or local block does not count.

On a pass the merge saves `local_gate` with `satellite` provenance: the
row's revision, the satellite's login, address and hostname, and the age. It
posts no status, because the satellite's status already stands at the head.
Then `settled_ready` runs as today. `ready` still calls `local_gate_passed`,
and still refuses a head behind the base.

The lane passes `--satellite-gate` for an entry marked `gate: satellite`; a
person may pass it by hand.

### Plain merge reuses first (sd:2724)

A plain `sd-ship merge`, without the flag, in a repository with
`repo.satellite_gate = accept`, looks for an offload receipt after its own
receipt misses. When clauses 3 to 8 hold, it merges with no run, as the flag
does. On any miss it runs the gate as today, and `reuse_miss` names the
clause and field. In a repository that did not opt in, a plain merge is
today's merge.

The two differ only on a miss. A plain merge falls back to a hub run; a
`--satellite-gate` merge refuses and hands back. The fallback is right for a
person merging by hand. The refusal is right for the lane, because the
operator's goal is that the hub runs no check for a satellite item.

### What the hub no longer guarantees

Under an accepted offload receipt the hub does not run the check. It no longer
guarantees that the check passes on the hub's own image:

- system libraries, and tools reached by a name outside `OFFLOAD_TOOLS`;
- a tool the hub cannot resolve, which is recorded but not compared;
- tool configuration outside `OFFLOAD_HOME_FILES`;
- before step 2a, the whole environment;
- inputs outside the repository on the satellite: an external makefile, a
  tool's own files, machine state, a network answer.

`sd_gate_receipts` already names the last as its trust boundary for a local
receipt. This item widens that boundary from one machine to two. A head can
pass on the satellite and fail on the hub. That is the accepted residual risk.
A repository that cannot accept it leaves `repo.satellite_gate` off.

### A forged receipt or request

One operator runs both machines under one GitHub account. sd:1335 Q3 ruled
that the whole satellite machine is the trust boundary. Any process there
passes `whois`, and the wire accepts any statement it sends. The same process
can post `sd/local-gate` with the operator's `gh` token. So any process on
the satellite can write an offload row and a matching status for a head that
never ran. No clause here can tell that apart from a real pass. The same holds
for a request row that asks for a merge with `manual` authority.

This is the same trust that a local receipt has today: any hub process can
write a row at the hub's key, and any hub session can run
`lane enqueue --manual`. The trust rule defends against accidents: a stale
head, another pack, a moved base, a half-written handoff, a status from
another account. It does not defend against the operator's own processes. A
process the operator does not trust must not run on the satellite (sd:1335 Q3).

A hub-attested name was considered and rejected for now. `serve` could
register a SQL function returning the admitted peer, and the write could
stamp it. It would prove only that the row came over the wire from an
admitted node. That boundary already admits every satellite process.

## Freshness

The strict up-to-date rule already forces the satellite to catch up first.
Three reads refuse a head that lacks the current base, whatever the gate
said:

- `refuse_behind` on GitHub's `mergeable_state == "behind"`, before the gate;
- `ready`, which refuses when `commits_behind(base, head) != 0`, on every
  merge, protection object or declared gap;
- `still_gated`, which reads `commits_behind` again before the `PUT` under a
  declared gap or an accepted `strict` gap.

So an offload receipt for a head behind the base can never merge. What the
hub must stop doing is its own catch-up. The lane runs
`sd-ship prepare --catch-up` for each entry, and a catch-up makes a new head,
which needs a gate at that head. For a satellite entry the lane runs no
prepare at all. Instead, after it fetches the branch and the base:

1. The fetched `origin/B` must equal the entry's head. Otherwise the entry is
   `handed_back` with `head_moved`: the satellite pushed again and must
   request again.
2. `git merge-base --is-ancestor origin/<base> <head>` must hold. Otherwise
   the entry is `handed_back` with `base_moved`, and merge never starts.
3. Merge runs. A `base_moved` or `satellite_*` refusal there, from a base
   that moved in between, also ends `handed_back`.

Step 2 is needed, not only tidy. `ready`'s behind refusal carries no code
today (`Refusal("the reviewed branch is behind the current default branch")`),
so the lane could not tell it from any other failure. Implement step 4 gives
it `base_moved` for the race that check 2 above cannot close.

The hand-back `next_action`, on the queue entry, the request row and the item
note:

    On the satellite: git merge origin/<base> on the branch (or sd-ship prepare --catch-up),
    then sd gate check --base <base>, sd-ship prepare, and sd-ship lane request again.

**Cost.** Two satellite entries queued together cannot both merge without a
round trip. The first merge moves the base, so the second hands back. Each
extra entry costs one satellite gate and one request. The hub runs no check
for any of them. Out of scope in `prd.md` names the later row that removes the
round trip.

The 6-hour window (Q3) does not guard base freshness; the reads above do. It
bounds how long the hub trusts the satellite's machine state, which the hub
cannot observe at any age.

## Handoff: the lane request row

### Row

One row per repository and item, in the `state` table as a checkpoint,
written through `sd_db.ship.save`. No schema change is needed.

    lane-request:v1:<slug>:<item>

| Field | Written by | Value |
|---|---|---|
| `writer` | satellite | `sd-lane-request` |
| `repository`, `item`, `branch`, `head`, `base` | satellite | what to merge; `head` is the satellite's pushed head |
| `authority` | satellite | `manual` or none, as `lane enqueue --manual` |
| `satellite` | satellite | the same identity as the offload receipt |
| `requested_at` | satellite | satellite clock, for display |
| `status` | both | `requested` by the satellite; then `queued`, `refused`, `handed_back`, `merged` or `failed` by the hub |
| `reason`, `next_action`, `code` | hub | why the status, and who acts next |
| `entry` | hub | the queue's `enqueued_at` and the request revision it took in |

`sd-ship lane request` refuses on the hub, naming `lane enqueue`: a request
means "the satellite gated this", which a hub item is not. It also refuses
when the item's `ship:` row is not `ready_to_send` at the branch's pushed
head, so a request that intake would refuse is not written.

Every write is revision-checked. When the satellite writes a new request while
the hub writes an outcome, one of them meets "ship receipt changed
concurrently". The satellite reruns its verb; the hub retries at its next
intake.

### Intake

`run_lane` calls `intake` before each `claim_next`, under the runner lock.
It reads every `lane-request:v1:<own slug>:*` row whose newest status is
`requested`, oldest first. The slug is the lane's own, from its main
checkout's origin, so each repository's lane reads only its own requests. For
each request, in order:

1. **Opt-in.** `repo.ci = local` and `repo.satellite_gate = accept`.
   Otherwise `refused`, `satellite_gate_off`.
2. **Shape.** `branch` passes `git check-ref-format --branch` and does not
   start with `-`; `head` is 40 hex digits; `item` is an integer. Otherwise
   `refused`, `invalid_request`. The branch reaches `git fetch` and
   `git push` argv, so this is input validation at a trust boundary.
3. **Prepared.** The `ship:` row for the slug, branch and item is
   `ready_to_send` at `head`. Otherwise `refused`, `satellite_not_prepared`.
4. **Taken in already.** A queue entry that names this request's revision
   means a crash came between the queue write and the row write. Write
   `queued` and go on; add nothing.
5. **Pending entry for the item.** Cancel it, marked `superseded` by this
   revision. The row needs no extra write: its older revision stays in its
   history. A `running` entry for the item leaves the request `requested`
   for the next intake.
6. **Enqueue.** Add an entry: `worktree` is the lane's main checkout,
   `gate: satellite`, `branch`, `expected_head`, `authority`, and the
   request's revision. No title or body file: the `ship:` row holds both.
   Then write `queued`.

Queue first, row second, so a crash leaves a queue entry that step 4
recognises, never a `queued` row with no entry.

### Scheduling

`lane run` drains its queue and exits; it is not a poller. A request moves
only when something on the hub starts it. The hub runs one scheduled job per
opted-in repository:

    */5 * * * *  sd-ship -C <hub checkout> lane run --satellite-only

It is operator configuration in the system repository's `local-cron-jobs`
folder for the hub host, not code. A start that finds the runner lock held
exits at once ("another runner holds ..."), so overlapping starts cost
nothing.

`--satellite-only` (ruling Q4) filters the run:

- Intake runs as in a plain `lane run`.
- `claim_next` claims only a pending entry with `gate: satellite`. A hub
  entry stays `pending`, in its place, for an integrator's plain `lane run`.
- No speculative gate starts. A satellite follower never gets one, and a hub
  entry is not this run's to prepare.
- The run exits when no satellite entry is pending, even when hub entries
  wait.

A plain `lane run` is unchanged and also takes in and runs satellite entries.

Two consequences, accepted:

- A satellite entry can merge ahead of an older hub entry in the same queue.
  The hub entry was waiting for an integrator anyway.
- While the scheduled run holds the runner lock, an integrator's `lane run`
  exits at once as busy and must start again. The scheduled run holds the
  lock only while satellite entries remain; it runs no gate.

## Lane changes

- `process`, for `gate: satellite`: fetch `refs/heads/B` and the base, then
  the head and base checks of "Freshness", then merge with `--branch B` and
  `--satellite-gate`. No prepare. The hub needs no worktree of the branch:
  `merge_branch` and `merge_head` already let a lane merge from its own
  checkout while the branch stays open elsewhere (sd:2037).
- `speculate`: no predicted-landing gate for a following entry with
  `gate: satellite`. An entry ahead that is a satellite entry predicts as now:
  its head already contains the base, so its catch-up is a no-op.
- `clean_up`, for `gate: satellite`: the worktree is the main checkout, so the
  worktree branch is skipped. It deletes `origin/B` with
  `--force-with-lease=refs/heads/B:<merged head>` when the remote is still at
  that head. The satellite removes its own worktree.
- `finish`: a satellite entry also writes its outcome to its request row. A
  `handed_back` or `failed` entry notes the item with the reason and the
  `next_action`, as a merge already notes it.

## Satellite-side changes

- `check_in_worktree`, after `record_unless_moved` records a pass: when
  `served_by(database)` names a hub and `repo.satellite_gate` is `accept`,
  write the offload row. On a reuse of the satellite's own receipt with no
  offload row at the key, write it from the reused reading, keeping its
  `recorded_at`. A failed write sets `offload_error`; the pass stands. The
  repository resolves by origin (`registered_for`), as `repo_ci` does on a
  satellite.
- `sd gate check` keeps running when the hub does not answer. The check still
  tells the builder whether the code passes; the result carries
  `offload_error` instead of a row.
- `sd gate check` warns, before the run, when its `pack_bin` differs from the
  hub's last published digest. `lane run` writes that digest to
  `sd-lane-pack:v1:<slug>` at each start and after each fast-forward of the
  pack checkout. It is a warning: the hub's pack can still move after the
  gate, and clause 6 is the check.
- `sd-ship prepare` on a satellite, opted in, at `ready_to_send`: post
  `sd/local-gate` from the offload row through `post_gate_status`. That
  function refuses a head the run did not check. The description is
  `head[:12] inputs <gate_inputs(root, head)>: sat <hostname>: <summary>`,
  cut to 140 characters. No row, no post; prepare reports `offload_error`.
- `sd-ship lane request`: the new verb above.
- `sd_gate_run` keeps its contract that it posts nothing. Only `sd-ship`
  posts.

## Failure modes

| Condition | Behaviour | Named by |
|---|---|---|
| Hub offline when the satellite gates | The check runs; no row is written; `offload_error` names `HubUnreachable`. Rerun `sd gate check` once the hub answers: it reuses nothing (the satellite's own receipt lives on the hub too) and runs again | sd:1335 R4 |
| Hub offline at prepare or request | Prepare cannot write `ship:`; the request verb cannot write its row. Both exit non-zero naming the hub. Rerun them | sd:2679 |
| No hub process runs `lane run` | The request stays `requested`. The scheduled job bounds the wait to its period plus the satellite entries ahead | R10 |
| Integrator starts `lane run` while the scheduled run holds the lock | It exits as busy; start it again once the scheduled run ends | Q4 ruling |
| Satellite on another pack revision | Warned before the gate; clause 6 refuses at merge with both digests and revisions. Remedy: fast-forward the satellite's pack, `sd gate check` again (inputs changed, so it runs), request again | R6 |
| Satellite on another `sd_db` build | The session refuses at the handshake with `BuildMismatch`, before any SQL. No row is written | sd:1335 design, A2 |
| Receipt for a moved head | Intake refuses `satellite_not_prepared`, or the lane hands back `head_moved`, or clause 3 refuses `satellite_receipt_missing`. The old row stays under the old key, unread | Intake 3; Freshness 1; clause 3 |
| Base moved after the gate | `base_moved`, handed back; the lane does not catch up | Freshness |
| Forged receipt or request | Not detected; the operator's own process is inside the boundary | sd:1335 Q3 |
| Status from another account | `local_gate_foreign`, as today | Clause 8 |
| Status at another inputs digest | `satellite_status_missing` | Clause 8 |
| Connection drops during a row write | One `ship.save` transaction with a request id. `recorded`: the row exists. `TransactionLost`: nothing was written. For the offload row, `offload_error` is set and no status posts; rerun `sd gate check`, which reuses the satellite's own receipt and writes the offload row from it. For the request row, rerun the verb | sd:1335 step 5 |
| Connection drops between the offload row and the status | Row present, no status: clause 8 refuses and the entry hands back. Rerun the satellite's prepare; it posts | Clause 8 |
| Hub crashes between the queue write and the row write | The next intake finds the entry by revision and writes `queued` | Intake 4 |
| Satellite clock ahead | Up to 300 s accepted; beyond that `satellite_receipt_expired` names both clocks | Clause 7 |
| Opt-in turned off while an entry waits | Clause 1 refuses; the entry hands back; new requests are refused at intake | R4 |
| A malicious branch name in a request | Intake refuses it before any git call | Intake 2 |

## Rollout and rollback

Rollout is per repository: set `repo.satellite_gate = accept`, add the hub's
scheduled job, and request from the satellite. Rollback is the reverse:
`sd-db.sh repo satellite-gate <path> off`. Intake then refuses new requests,
and clause 1 hands back any waiting entry. Hub-built items never took the new
path, so nothing else changes. Code rollback needs no data migration: the
offload, request and pack rows are checkpoints no older reader looks for.

## Alternatives rejected

- **Make every receipt portable.** sd:2724 asked for it, and the first
  step 2a did it. It weakens local reuse in repositories that never offload
  (C-17). Step 2a now builds a view that only the offload comparison reads.
- **Run the offload gate under a fixed `PATH` and `HOME`.** It is larger and
  less sound. A fixed `HOME` loses the login's credentials and caches, so
  checks that pass today fail. A fixed `PATH` must still equal the hub's,
  which the `path` part already checks.
- **Key every receipt by slug.** Hub and satellite rows would share a key, and
  each write would append over the other's revision.
- **The lane falls back to a hub run on a miss.** It defeats the goal, and
  a silent fallback hides a broken handoff. A plain merge by hand does fall
  back (sd:2724); the lane's `--satellite-gate` does not.
- **SSH enqueue from the satellite.** The first draft's recommendation;
  the operator chose the request row (Q2).
- **A lane-owned worktree per satellite branch.** Not needed: merge already
  merges a branch from the lane's own checkout (sd:2037), and a worktree would
  collide with any hub checkout of the same branch.

## Planning review, 2026-10-05

The pack's planning review contract
(`.claude/sd-ai-command-pack/planning-adversarial-review.md`) ran once on
this artifact set, as the host lane; the pack defines no other lane. No
artifact touches a path the pack's `sensitive` list names. The contract then
needs no stable-id ledger or cross-artifact sweep. Both are kept here
anyway, because the team lead asked for every finding to be answered in the
record.

| ID | Severity | Concern | Evidence | Disposition |
|---|---|---|---|---|
| C-1 | blocking | `lane run` drains and exits, so a request row is never read without a hub process | `run_lane` returns when `claim_next` finds nothing | addressed: R10, "Scheduling", implement steps 6 and 8 |
| C-2 | blocking | The hub cannot build a binding when a tool is missing on its `PATH`, so clause 5 could not compare | `tool_identity` raises `Unavailable`; `gate_binding` returns `None` | addressed: tree part and machine part split; implement step 4 |
| C-3 | blocking | The lane cannot classify `ready`'s behind refusal: it carries no code | `Refusal("the reviewed branch is behind the current default branch")` in `ready` | addressed: lane checks the base before merge; that refusal gets `base_moved` |
| C-4 | major | Clause 8 compared the status with a satellite-written digest, which proves nothing the hub knows | `post_gate_status` writes `head[:12] inputs <digest>` | addressed: clause 8 uses the hub's own `gate_inputs(root, head)`; `posted_inputs` dropped from the row |
| C-5 | major | A branch name from a request reaches git argv on the hub | intake's fetch and the lease delete | addressed: intake step 2 |
| C-6 | major | Frequent pack landings make `satellite_pack_mismatch` common, each costing a satellite gate | the lane fast-forwards the pack checkout after its merges | addressed: published hub digest and a pre-gate warning; clause 6 stays the check |
| C-7 | major | A pre-run refusal when the hub is down blocked a builder's plain check for every repository | the first draft's "refuses before the run" | addressed: the check runs and reports `offload_error` |
| C-8 | major | Queue file and request row are two stores; a crash between writes could double-enqueue | intake writes both | addressed: queue first, revision on the entry, intake step 4 |
| C-9 | minor | A per-branch hub worktree is needless and can collide with a hub checkout | `merge_branch`, `merge_head` (sd:2037) | addressed: merge from the main checkout with `--branch` |
| C-10 | minor | A request carries `manual` authority from a satellite process | `merge_authority` reads only `--manual` | rebutted: same grant as `lane enqueue --manual`, inside the sd:1335 Q3 boundary; `manual_merge_guard` still runs on the hub |
| C-11 | minor | The scheduled job also merges hub entries sooner than an integrator would | `run_lane` drains every pending entry | first rebutted; then ruled by the operator (Q4): addressed by `--satellite-only` |
| C-12 | minor | Satellite repository resolution: its checkout path is not the hub's registered path | `registered_for` falls back to the origin | rebutted: resolution by origin already works for `repo_ci` on a satellite |
| C-13 | minor | No rollback was stated | — | addressed: "Rollout and rollback" |
| C-14 | blocking | The environment digest keeps `HOME`, `USER` and `PATH`, so neither a satellite receipt nor many hub receipts ever match (sd:2724's evidence) | `gate_environment`; sd:2724: revision 29982, 8 hub digests in a day | addressed: step 2a, narrowed by C-17. The hub compares `offload_view` on the offload path only. Same-machine reuse stays with sd:2724 |
| C-15 | major | The satellite runs as another local login, and clause 8 needs its `gh` to be the hub's GitHub account | sd:2724 names two logins | parked: implement step 1 reads both; two accounts block step 5. Owner: the operator |
| C-16 | minor | sd:2722 changes what `gate_inputs` hashes | sd:2722's title | rebutted: clause 6 compares whatever `gate_inputs` hashes; the items are independent |
| C-17 | blocking | Step 2a dropped `HOME`, `USER` and `PATH` from every local binding, also where offload is off. Equal `make` bytes can run another python or compiler through another `PATH` order; `HOME` selects tool configuration | ship review of 884d31a3, HIGH, on implement step 2a | addressed: local reuse keeps the whole environment; `offload_view` compares `PATH` order, named tools, named `HOME` files and other variables, on the offload path only; residual risk under "The offload view" |

Round 2 swept the three artifacts for each value they share: the window,
the skew bound, step numbers, refusal codes, the request key and the
estimate. It found two references that named the wrong step, both fixed:
"step 2" in "Freshness" now reads "check 2 above", and C-1 now names
implement steps 6 and 8. It found no new concern. No finding is open.
Implementation is unblocked on the planning side; the item still needs its
move out of `planning`.

After ruling Q4 a third sweep read every `lane run` in the three artifacts.
Each scheduled run now names `--satellite-only`; each integrator run stays
plain. The estimate, the criterion numbers and C-11 moved with the ruling.
No new concern was found.

Round 4 folded in sd:2724 and swept the step numbers, the estimate, the PR
count and the criterion numbers. The sweep moved "criterion 7" to 9 in
implement step 8. C-15 is parked, not open: it blocks only step 5, and step 1
settles it.

Round 5 answered the ship review of 884d31a3 (C-17). It chose a compared
view over a normalized run, as "Alternatives rejected" says. It swept R2,
R12, criterion 7, the comparison table, the residual-risk list, the overlap
table, C-14, implement steps 2a, 3 and 4 and the PR list. No finding is
open.
