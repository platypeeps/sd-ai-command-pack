# Design — satellite gate offload

## The shape

The satellite gates; the hub merges. Nothing else moves. The merge still runs
under the hub's `repository_lock`, in the hub's lane, as the sd:1335 Decision
requires. What changes is the evidence that the merge gate reads: a receipt
from the satellite in place of a run on the hub.

| Step | Machine | Command | What it does |
|---|---|---|---|
| 1 | satellite | `git merge origin/main` on the branch, or `sd-ship prepare --catch-up` | The head contains the current base before any gate |
| 2 | satellite | `sd gate check --base main` | Runs `sd-check`; writes the satellite's own receipt and the offload receipt over the wire |
| 3 | satellite | `sd-ship prepare --item N --title T --body-file F` | Reviews (its gate reuses step 2), pushes, binds the PR, writes `ship:`, posts `sd/local-gate` from the offload receipt |
| 4 | satellite → hub | `ssh <hub> sd-ship -C <hub checkout> lane enqueue --satellite --item N --branch B --manual` | Adds a hub worktree of `origin/B` and a lane entry marked `gate: satellite` |
| 5 | hub | `sd-ship lane run` (the lane's runner, unchanged) | Head check; no prepare, no catch-up, no speculation; then `sd-ship merge --satellite-gate` |
| 6 | hub | `sd-ship merge --item N --expected-head H --manual --satellite-gate` | Accepts the offload receipt under the trust rule; posts no status; merges |

Step 3 alone also gates when step 2 was skipped: `sd-review --gate-check`
runs the same `check_in_worktree` and writes the same rows.

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
way (`ship.receipt_key(self.repository, self.branch, args.item)`), and that
is why a hub lane finds a satellite's `ship:` row today. The tree key follows
`tree_key` in `bin/sd_gate_receipts.py` unchanged.

### Row

Written through `sd_db.ship.save`, so the store, the revision check and the
request-id protocol of sd:1335 step 5 apply as for every `ship:` row.

| Field | Value |
|---|---|
| `writer` | `sd-satellite-gate` |
| `satellite` | `{"login", "address", "hostname"}`: `sd_db.tailnet.this_node()` gives the owner login and the Tailscale IPv4 address; `socket.gethostname()` is for display only |
| `hub` | `served_by(database)`, the `host:port` the row went to |
| `binding` | the satellite's whole `gate_binding` output, unchanged |
| `pack_bin` | sha256 of the pack `bin/` files that `gate_inputs` hashes, or `"tree"` when the run gated its own tree (`gates_itself`) |
| `pack_rev` | `git rev-parse HEAD` of the pack checkout, for the refusal text only |
| `local_block` | sha256 of the copied `CLAUDE.local.md`, or `"absent"` |
| `posted_inputs` | `gate_inputs(root, head)`: the digest the status description carries |
| `reading` | the passing reading, as `record_pass` stores it |
| `head` | the commit that passed |
| `recorded_at` | the run's time on the satellite's clock; a reuse keeps the original run's time |

### What the hub compares, and what it only records

The hub builds its own binding for the head in its worktree, exactly as the
merge gate does now before `examine`. That needs a checkout, not a run. Then
it compares field by field:

| Binding field | Hub compares | Why |
|---|---|---|
| `schema`, `reuse`, `head`, `tree`, `fork` | yes | The commit, or the tree and the merge base's tree, that passed |
| `inputs` | yes | Hashes the head or tree, `CLAUDE.local.md` and the pack `bin/`. Equal inputs mean the same pack and the same local block. `pack_bin` and `local_block` name which part differs |
| `scope`, `detection` | yes | Pack code over the tree, the local block and the base. A difference means another command ran |
| `tools` | no, recorded | Paths and bytes of the satellite's `make`, `python3` and others. The hub's differ by construction |
| `python` | no, recorded | The satellite's interpreter |
| `environment_sha256` | no, recorded | The satellite's whole gate environment |
| `satellite` | no, recorded | `serve` admitted only the operator's untagged node (sd:1335 step 7). A second check reads the same claim |

The brief asked for the pack `bin/` digest as the one compared field.
Comparing `inputs` covers it and adds the `CLAUDE.local.md` digest. That file
can spell the repository's check, so a different copy means a different
command. Under the pack's own tree key with `"tool": "tree"`, `inputs` leaves
out `bin/` (sd:2613). There the running pack does not decide what ran, and
`pack_bin` reads `"tree"` on both sides.

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
| 8 | The newest `sd/local-gate` status at the head is `success`, posted by `viewer_login()`, and its description starts with `head[:12] inputs <posted_inputs>` | `satellite_status_missing` or `local_gate_foreign` |

Clause 6 is a named case of clause 5, so a pack mismatch gets its own
remedy. Clause 8 reuses `local_gate_passed` and adds the description test, so
a status from a run at another inputs digest does not count.

On a pass the merge saves `local_gate` with `satellite` provenance: the
row's revision, the satellite's login, address and hostname, and the age. It
posts no status, because the satellite's status already stands at the head.
Then `settled_ready` runs as today. `ready` still calls `local_gate_passed`,
and still refuses a head behind the base.

Without `--satellite-gate` the merge is today's merge. A hub-built item in an
opted-in repository runs its gate on the hub as before. The flag is what the
lane passes for an entry enqueued with `--satellite`; a person may pass it by
hand.

### What the hub no longer guarantees

Under an accepted offload receipt the hub does not run the check. It no longer
guarantees that the check passes on the hub's own image:

- the satellite's `make`, interpreter, compilers and system libraries;
- the satellite's environment, which is bound whole there but compared nowhere;
- inputs outside the repository on the satellite: an external makefile, a
  tool's own files, machine state, a network answer.

`sd_gate_receipts` already names the last as its trust boundary for a local
receipt. This item widens that boundary from one machine to two. A head can
pass on the satellite and fail on the hub. That is the accepted residual risk.
A repository that cannot accept it leaves `repo.satellite_gate` off.

### A forged receipt

One operator runs both machines under one GitHub account. sd:1335 Q3 ruled
that the whole satellite machine is the trust boundary. Any process there
passes `whois`, and the wire accepts any statement it sends. The same process
can post `sd/local-gate` with the operator's `gh` token. So any process on
the satellite can write an offload row and a matching status for a head that
never ran. No clause here can tell that apart from a real pass.

This is the same trust that a local receipt has today: any hub process can
write a row at the hub's key. The trust rule defends against accidents: a
stale head, another pack, a moved base, a half-written handoff, a status from
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
prepare at all:

- The satellite's prepare already reached `ready_to_send` at the head; the
  lane reads that from the `ship:` row and skips the entry if it does not hold.
- Merge refuses `base_moved` when the base moved. The lane marks the entry
  `handed_back` instead of `failed`, and notes the item.

The hand-back `next_action`, for both `base_moved` and every
`satellite_*` refusal under `--satellite-gate`:

    On the satellite: git merge origin/<base> on the branch (or sd-ship prepare --catch-up),
    then sd gate check --base <base> and sd-ship prepare, then enqueue on the hub again.

**Cost.** Two satellite entries queued together cannot both merge without a
round trip. The first merge moves the base, so the second hands back. Each
extra entry costs one satellite gate and one enqueue. The hub runs no check
for any of them. Out of scope above names the later row that removes the
round trip.

`OFFLOAD_WINDOW_SECONDS` is 6 hours, as `TREE_REUSE_WINDOW_SECONDS` (open
question 3). The window does not guard base freshness; the three reads above
do. It bounds how long the hub trusts the satellite's machine state, which the
hub cannot observe at any age.

## Lane changes

- `lane enqueue --satellite --branch B`: fetches `origin/B` into the main
  checkout, adds a worktree at `<lane dir>/worktrees/<item>-<B>` on a local
  branch `B` at `origin/B`, and refuses when a local `B` exists at another
  commit. The branch name must match, because the `ship:` key names it. Title
  and body come from the `ship:` row, so `--title` and `--body-file` are not
  needed. The entry records `gate: satellite`.
- `process`: for `gate: satellite`, head check, then the `ship:` phase check,
  then merge with `--satellite-gate`. No prepare.
- `speculate`: no predicted-landing gate for a following entry with
  `gate: satellite`. An entry ahead that is a satellite entry predicts as now:
  its head already contains the base, so its catch-up is a no-op.
- `land`: unchanged. The worktree is under the lane directory, outside
  `~/repos`, and the note carries its removal command as for any entry.

## Satellite-side changes

- `check_in_worktree`, after `record_unless_moved` records a pass: when
  `served_by(database)` names a hub and `repo.satellite_gate` is `accept`,
  write the offload row. On a reuse of the satellite's own receipt with no
  offload row at the key, write it from the reused reading, keeping its
  `recorded_at`. A failed write sets `offload_error`; the pass stands.
- `sd gate check` refuses before the run when the repository is opted in
  and the hub does not answer. The check then cannot leave the receipt it
  exists for.
- `sd-ship prepare` on a satellite, opted in, at `ready_to_send`: post
  `sd/local-gate` from the offload row through `post_gate_status`. That
  function refuses a head the run did not check. The description is
  `head[:12] inputs <posted_inputs>: sat <hostname>: <summary>`, cut to 140
  characters. No row, no post; prepare reports `offload_error`.
- `sd_gate_run` keeps its contract that it posts nothing. Only `sd-ship`
  posts.

## Failure modes

| Condition | Behaviour | Named by |
|---|---|---|
| Hub offline when the satellite gates | `sd gate check` refuses before the run for an opted-in repository: `HubUnreachable` names host and port. Nothing runs, nothing posts | sd:1335 R4 |
| Hub offline after the gate | Prepare cannot write `ship:` and posts nothing. Rerun prepare; the gate reuses the satellite's own receipt | sd:2679 |
| Satellite on another pack revision | Clause 6: `satellite_pack_mismatch` names both `bin/` digests and both revisions. Remedy: fast-forward the satellite's pack, then `sd gate check` again (inputs changed, so it runs) | R6 |
| Satellite on another `sd_db` build | The session refuses at the handshake with `BuildMismatch`, before any SQL. No row is written | sd:1335 design, A2 |
| Receipt for a moved head | No row at the new head's key: `satellite_receipt_missing`, handed back. The old row stays, under the old key, unread | Clause 3 |
| Base moved after the gate | `base_moved`, handed back; the lane does not catch up | Freshness |
| Forged receipt | Not detected; the operator's own process is inside the boundary (above) | sd:1335 Q3 |
| Status from another account | `local_gate_foreign`, as today | Clause 8 |
| Status at another inputs digest | `satellite_status_missing` | Clause 8 |
| Connection drops during the row write | One `ship.save` transaction with a request id. `recorded`: the row exists. `TransactionLost`: nothing was written; `offload_error` is set and no status posts. Rerun `sd gate check`: it reuses the satellite's own receipt and writes the offload row from it | sd:1335 step 5 |
| Connection drops between the row and the status | Row present, no status: clause 8 refuses. Rerun the satellite's prepare; it posts | Clause 8 |
| Satellite clock ahead | Up to 300 s accepted; beyond that `satellite_receipt_expired` names both clocks | Clause 7 |
| Opt-in turned off while an entry waits | Clause 1 refuses; the entry hands back; enqueue it without `--satellite` to gate on the hub | R4 |

## Alternatives rejected

- **Relax the binding until satellite and hub agree.** Dropping `tools`,
  `python` and the environment from every receipt weakens every local reuse
  to buy one remote case.
- **Key every receipt by slug.** Hub and satellite rows would share a key, and
  each write would append over the other's revision.
- **Hub falls back to its own run on a miss.** It defeats the goal, and a
  silent fallback hides a broken handoff. A hub-built item already takes the
  path without the flag.
- **Satellite enqueues by a request row the hub polls.** It needs a new row
  kind, a poller and its own lock. SSH runs today's verb where it already
  works (open question 2).

## Questions for the operator

**Q1 — where does the opt-in live?**

- A. A `repo` column, `satellite_gate` `off|accept`, set by
  `sd-db.sh repo satellite-gate <path> off|accept`, like `runner_merge`. A
  system-repository migration comes first. An older library reads `off`.
- B. A pack core key, `sd.satellite_gate`. It needs no migration, but it is
  per machine, not per repository.
- C. A field in `.github/sd-gate-reuse.json`. It is reviewed, but a branch
  could opt itself in under its own gate.

Recommendation: **A**. The grant is the operator's, per repository, outside
the tree, and it fails closed the way `repo_ci` does.

**Q2 — how does the entry reach the hub's lane?**

- A. SSH from the satellite runs `sd-ship lane enqueue --satellite` on the
  hub. sd:1335 kept SSH (option B) for hub-only verbs.
- B. A lane request row in the hub's database, which `lane run` picks up.

Recommendation: **A** now. It reuses the hub's verb and lock as they are. B
becomes worth building if satellite items arrive while no hub session runs
the lane.

**Q3 — how long does an offload receipt stand?**

- A. 6 hours for both keys, the tree-key window.
- B. 30 minutes for a head key, as the hub's own head receipts.

Recommendation: **A**. A lane wait often passes 30 minutes, and an expired
receipt costs a full satellite gate and a round trip. Base freshness is
guarded by the strict rule, not by the window.
