# Workflow

How the pack expects to be used. One person does most of the work. Other
people see pull requests and merged commits, and nothing else the pack makes.
Every default below serves that person. Anything that would show a personal
process to someone else is off unless this file says otherwise.

For this maintainer's reviewer and report preferences, read the
sd-ai-command-pack checkout's [.claude/rules/sd-operator-defaults.md](.claude/rules/sd-operator-defaults.md).
Those instructions do not change executable gates or another operator's permissions.

## Available controls

`sd task` and the dashboard create and update ordinary tasks directly in the
database, without a Git checkout, PRD or GitHub issue. `sd today` and `sd store
items` use the same queries as Today and Backlog. Completion of an ordinary
task is independent of code delivery. `sd work deliver` verifies delivery
evidence; `sd work cancel --reason` records a cancellation without waiting for
another merge, and `sd task cancel --reason` does the same for a task or
followup. Artifact relinking preserves the item's identity and history.

Writing uses shared stage and review-evidence checks through `sd writing` and
the Writing screen. After the verified one-time cutover, stages, parking and
publication metadata belong to the database; drafts and research stay in Git.
The supported operational controls inspect existing launchd jobs and database
assignments. Running an arbitrary agent command or terminating an unowned
process is not a dashboard action.

The automation policies below describe the intended development loop. They do
not mean an autonomous queue runner, send box, one-click revert, or repository
settings editor is installed. Consult the current command help and dashboard
controls for executable operations.

## Two flows, one spine

The spine is the **item**: one row in the local database and one screen on the
dashboard, with optional files in Git. A small code change can proceed without
creating an item or placeholder planning artifact.

**Research.** Sources, understanding, brief, decisions, handoff or publish. The
research kit lays out the repository; the item tracks what is open. You sit at
the end: external publish or filing is the one gate, and it is yours.

**Development.** Plan when warranted, then implement, test, review, push, and merge when authorized.
Merging needs `runner_merge: auto` on the repository row, for the runner and the assistant alike, and a fresh sole-operator check before each merge.
Without it, or an operator request for that merge, stop at pull-request-ready.

The loop proceeds within the approved scope and existing permissions.
Missing authority, unresolved scope, failed checks, or exhausted review allowance stops the affected operation.
Record the blocker and next supported action.
Do not replace required approval with a proposal that the user can veto afterward.

## Defaults

These run without being asked.

- No pack command runs in a checkout whose `repo.managed` is no (sd:1620, sd:2566).
  `sd-ship`, `sd-review`, `sd-check`, `sd-status` and `sd-ship lane enqueue` refuse there, dry runs included.
  The refusal names the remedy: `sd-db.sh repo managed <path> yes`.
  A checkout with no row proceeds; only a row marked unmanaged refuses.
- `sd-status` reports. It never writes.
- `sd-review --scope branch --challenge` runs on the machine before a push.
  Blocking findings are fixed or recorded before the branch leaves.
  Under `repo.ci = local`, see **Gate first, then review the same head** under [Parallel work](#parallel-work).
- The required check runs on the exact head: `sd/local-gate` under `repo.ci = local`, CI otherwise.
  Preserve review, ownership, protection, and authorization gates.
- `sd-ship` commits enumerated paths, pushes, opens the pull request, waits
  for CI once in the background, merges with an explicit title and body
  whose trailer names the item, and runs `git fetch -p`. The repository
  setting `delete_branch_on_merge` removes
  the remote branch.
  A merge into the system checkout that changes `local-sd-db` also installs
  `sd_db` at the merge commit into the pack's virtualenv, so the dashboard's
  next restart finds the library it expects (sd:2108). An installed copy that
  is not an ancestor of the merge commit is kept. Every install holds one
  machine-wide lock across that check and pip, so concurrent reconciles
  cannot interleave. The receipt's `library`
  says whether the install worked, or why it was skipped.
  After each confirmed in-scope merge, follow `skills/sd-ship/references/post-merge-closeout.md`.
- Expected branch protection requires pull requests, current CI, and up-to-date branches, with no required approvals.
  Configure it deliberately in GitHub; installation does not grant a protection exception.
  `sd-status` reports gaps; executable merge stops when required protection is absent.
  Protection is read from both of GitHub's mechanisms: the classic object first, and when that is absent, the branch's active rulesets.
  A ruleset with a `pull_request` or `required_status_checks` rule is the protection, held to the same guards; one that only forbids deletion or force-push is not.
  One accepted gap changes that gate: an `unprotected` entry in `.github/sd-status.json` at the reviewed commit.
  Under it, `sd-ship merge` requires every check run, every status, and a `pull_request` run of every workflow at the head to pass.
  The receipt records `declared_gap: unprotected`. Any other gap, and a declaration only in the working tree, do not change the gate.
- `make check` runs `sd-docs-lint` against the checkout's own `docs/work/`, `docs/spec/` and `docs/decisions/`.
  `sd-ship` runs it again at delivery time. A consumer that wants the gate
  checks the pack out in its own workflow and runs `<pack>/bin/sd-docs-lint`
  from there; the machine-scope installer puts no `bin/` in a consumer,
  and nothing runs the lint there otherwise. A runner has no database, so
  rule 2 reads statuses from git there, with full history, and checks
  fewer items than the machine with the rows; each run prints which source
  it read. `make check` passes `--no-history`: rule 2 then fetches nothing
  and reads no `git log`, and an item only git could answer reads `unknown`.
  The delivery question stays with the lint `sd-ship` runs.
- A commit to the pack, the system repository or the writing repository names
  what needed it: `Needed-by: <item id>` or `Needed-by: cost | efficiency |
  visibility`. `sd-ship` warns when the trailer is missing and ships anyway.

## Opt-in

These run only when asked by name.

- A work item is a row: `sd task add`. Its status, notes and progress live on the row.
  Write `docs/work/<date>-<slug>/design.md` only when the shape needs agreement before the work starts.
  The design names its row with `item: sd:<n>`; there is no `prd.md` or `implement.md` to write.
  An older item keeps its `prd.md`; an active one carries no `status:` line,
  and `sd-docs-lint` fails one that does. Every checkout reads status from the
  item's row. A checkout or CI runner with no database asks git whether the
  item is delivered, by the merge trailers, and nothing else.
  `ready_to_send` marks a finished artifact waiting on you.
- `sd-spec`. Run it when a change alters behaviour that `docs/spec/` documents.
- A review pass beyond the table below. Ask for it by name; the item records
  that you did.
- `sd-handoff`. Write a packet when you stop mid-task. Followups, decisions and
  open questions are already on the item; the packet carries only what is not.

## No-CI mode

A repository whose `repo.ci` row says `local` runs no GitHub Actions (sd:1843).
`github` is the default. Every reader treats a missing column, row or library as `github`.

Switch a repository with `sd ci local`, run from its checkout (sd:1914).
It is a dry run; `--apply` makes the changes, and a second run finds none.
It refuses a repository the sd database does not mark managed (`repo.managed = no`, sd:1620).
It needs `admin` on the repository and makes three changes, each only where it does not hold yet:

- It sets `repo.ci` to `local`, as `sd-db.sh repo ci <path> local` does.
- It makes `sd/local-gate` the one required status check, `strict` on, in whichever mechanism the default branch uses.
  Classic protection has its required checks replaced.
  A repository ruleset keeps every other rule; only its status-check rule changes, or is added.
  The dropped contexts are named: their workflows no longer run, and a required context that never reports blocks every merge.
  A branch protected classically with no required checks refuses; add the check in the branch settings.
  A required check it cannot rewrite stops the run before any write: an organization ruleset's, or another protected branch's.
- A private repository has Actions disabled outright.
  A public one keeps Actions on for its dynamic workflows (CodeQL, Dependabot, Copilot).
  Each workflow its files declare is disabled.

After the switch:

- `sd-ship merge` checks the reviewed head out into a clean, detached `git worktree`.
  It runs `sd-check` there, not in your checkout, and removes the worktree after.
- The child drops `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `CONDA_PREFIX` and `PATH` entries inside your checkout.
  It also drops any `PATH` entry whose parent holds `pyvenv.cfg`: a virtualenv's `bin`, wherever it lives.
- A Rust repository (any tracked `Cargo.toml`) builds into a warm folder the gate owns, not the worktree's `target/` (sd:2493).
  Each repository keeps two under `${XDG_CACHE_HOME:-~/.cache}/sd/gate/`, one gate at a time in each; `CARGO_TARGET_DIR` names it.
  A warm run gets `CARGO_INCREMENTAL=0`. When both are held, the run builds cold in its worktree.
  Your own `CARGO_TARGET_DIR` never reaches the check.
  `SD_GATE_CARGO_TARGETS` sets the count, `0` switches the cache off, and `SD_GATE_CACHE_DIR` moves it.
  Cargo prunes nothing there, so the gate bounds the cache at `sd.gate_cache_gb` (sd:2598).
  Past it, the gate removes the least recently used free folders, its own last, and names each on stderr.
- This is a self-hosted runner, not a hermetic build.
  The gate guarantees a clean tree at the exact head, a scrubbed Python environment and no virtualenv on `PATH`.
  The rest of `PATH` and the system tools are this machine's image.
  The repository's own `check` entrypoint owns a hermetic environment if it needs one.
- It posts the result to that exact commit as the `sd/local-gate` status, `success` or `failure`.
  It refuses to post for any commit other than the one the worktree held.
- The description carries `inputs <digest>` as provenance: the head, the copied `CLAUDE.local.md` and the pack's `bin/` files.
  A tree whose `.github/sd-gate-reuse.json` adds `"pack": "sd-check"` declares that its check runs no other pack command.
  Its inputs then hash only what `sd-check` and the gate's `sd_gate_run` import, so a pack landing elsewhere voids no receipt (sd:2722).
- Every merge attempt posts a fresh status. `sd-ship prepare` runs this same gate, through `sd-review --gate-check`.
  Prepare's pass leaves a receipt; the merge gate at the same head and binding, within 30 minutes, reads it instead of running `sd-check` again.
  The status then says `(reused)`. The merge gate never writes a receipt.
  Prepare reads one too: a pass that `sd gate check` or an earlier prepare left at the same head and binding (sd:1912).
  A repository that tracks `.github/sd-gate-reuse.json` keys receipts by tree and merge base instead of head, for 6 hours (sd:1912).
  The merge base binds by its tree, not its commit (sd:2586).
  The pack's own declaration adds `"tool": "tree"`: its gate runs the gated tree's own `bin/sd-check` and binds that tree, not the checkout's `bin/` (sd:2613).
  A pack landing between a builder's gate and the lane's prepare then keeps the pack item's receipt.
  The field counts only when the running pack belongs to the gated repository; any other repository's gate keeps the checkout binding.
  A pass whose binding moved during the run leaves no receipt, and the result's `receipt_skipped` names what moved (sd:2612).
  Inputs outside the repository are not bound; `bin/sd_gate_receipts.py` names the binding and this trust boundary.
- Given the base branch, the gate passes `sd-check --base`: a repository's declared docs-only scope applies (sd:2072).
- `sd-ship merge --watch` starts no remote watch: no remote check is coming, and the gate runs to completion in the merge (sd:1875).
- The merge then requires that status as `success` at the head, posted by the authenticated account.
  Missing, failed, pending, naming another commit, or from another account: each refuses.
- Under a declared gap, the status replaces the `pull_request` workflow runs `every_check` asks for.
  Under protection, the status is required beside the protection's own contexts.
- Protection for such a repository should require `sd/local-gate`; `sd ci local` sets that.
  A merge path of the repository's own (a Dependabot merge, a script that merges) gets no status from `sd-ship merge`.
  Have it run `sd gate post --head SHA` first, or its required check never reports (sd:1989).
  After a switch, grep the repository for such automation, such as a script that polls check runs.
  `sd-status` reports it as the one produced context, so a required workflow context shows as not produced.
- Under a declared gap, a head that already carries a failed check run still refuses: a workflow that ran before the switch, or a billing-blocked one.
  GitHub reports the pull request `unstable`, not `clean`, and `every_check` requires every check run to pass.
  Under protection, `unstable` merges: only the required checks and the local gate are read (sd:2075).
  Push a fresh commit to the branch; an empty one will do. Nothing runs on it but the local gate.
- `sd fleet stamp` and `sd-review setup-github` lay no workflow and say why.
  Absence is not drift: `setup-github --check` prints `absent` and exits 0.
  A tracked route workflow never runs; `--check` names it `REMOVE`, and the stamp names it too.
  Remove it with `sd-review setup-github --remove`, which also lifts its Dependabot guard; `--dry-run` previews.
- Routing needs no workflow. `sd-ship prepare` routes in its local review pass and records the plan in the receipt.
  The route workflow only printed that plan to a job summary; nothing reads it.

## Reviews

Adversarial review runs at four points, each with a cap on automatic passes.
The points, the caps and the stop rule are in
[.claude/rules/sd-planning-adversarial-review.md](.claude/rules/sd-planning-adversarial-review.md); this page does not copy them.

The code pass reads a head. Under `repo.ci = local` a gate pass at that head
comes first; see [Parallel work](#parallel-work). A fix that changes the head
gets a further verification pass over the diff since the reviewed head, up
to the cap; `sd-ship` pushes only the reviewed head or a verified fix
of it, and merges naming that head with
`gh pr merge --squash --match-head-commit <the reviewed sha>` —
equivalently `PUT /repos/{owner}/{repo}/pulls/{n}/merge`
with `sha=` — so a head that moved after the review is refused at GitHub with
a 405. The flag is what does the refusing: a merge that carries only a title
and a body refuses nothing, whatever head moved under it.

The reviewer order gives independence: Codex reviews first by config, and
commits carry no attribution trailer (sd:3014). When Codex is down, a Claude
reviewer may review Claude's code. Skills name the roles `author` and
`reviewer`; the provider registry below maps them.

No post-merge external review runs (sd:777).

## Advisory

- Copilot is an optional second review after local review; `sd.copilot_review` under
  [Standing authorization](#standing-authorization) decides when `sd-ship` requests one.
  `sd-ship` requests at most three per pull request. Read and disposition every posted finding.

## Never in a shared repository

A shared repository resolves to `guest` mode. Detection never produces
`minimal`; only an operator writes it, and the refusals below that name
`guest` do not apply to it.
`full` requires administration, a non-fork remote, and exclusive push access.
In a shared repository:

- No `Work:` line in a pull request body unless the pull request resolves a
  work item that lives in that repository.
- No `docs/work/`, `docs/spec/`, or `docs/decisions/` commits. `mode: guest`
  already carries this: planning artifacts stay out of the repository, on
  every branch and every remote, a fork's included; no integration branch
  holds them.
  Two machines enforce that refusal. `sd-review --scope planning` calls
  `sd_lib.guest_artifact_refusal`, which resolves the mode and names refused
  paths. `sd-plan` uses that review before promotion. `sd-ship` checks the
  same list, `sd_lib.guest_refused_dirs`, before a guest push.
  A `guest_allow: docs/decisions` line in the local block takes decision
  records out of both checks for that repository (sd:2168).
  `docs/work/` and `docs/spec/` stay refused; naming either is an error.
  Nothing yet refuses a `docs/spec/` or
  `docs/decisions/` write at the moment it happens — `sd-spec` and `sd-plan
  --decision` are still prose there, and the push gate is where those are
  caught.
- No labels, review comments, reviewer requests, or bot posts from any pack
  surface. `sd-review` and `sd-receive-review` never post.
- No workflow files or repository settings unless the owner of that
  repository asked for them.
- No merge without `runner_merge: auto` on the row or an operator request for that merge;
  see [Standing authorization](#standing-authorization). No permission covers a merge that skips
  the review lane. Ownership and protection gates still decide whether `sd-ship` can execute it;
  a refusal is a stop.
- No issue filed. `sd suggest add` writes a row everywhere; `sd suggest publish`
  files it as an sd item when you run it, in the checkout you name with
  `--belongs-to`. No pack surface files a GitHub issue.

## The path for a change

Small change: branch, commit, local review, push, pull request, CI, merge.
Use the ship workflow without inventing a planning artifact.
After review, take a newer default branch with `git merge origin/<base>`, never a rebase:
a rebase rewrites the reviewed commits, and the next push no longer fast-forwards
the branch `sd-ship` pushed. `sd-ship prepare --catch-up` makes that merge.

Change that earns a work item: `sd-plan` adds the row, and writes `design.md`
only when the shape needs agreement; it asks only for missing decisions. Then the small-change
path runs with the applicable review points. An item can span several pull
requests. `Item: <item>` associates a merge without closing the item;
`Delivers: <item>` declares the delivering merge. Changes without an associated
item omit those trailers and create no placeholder record. `sd-ship` writes the
trailers as the last paragraph of the squash message, since git reads trailers
only from the final paragraph.

A criterion only the operator can observe, such as a command running unprompted
on their machine, is not a checklist box. Record it in the item's `## Log` with
its date when it is observed; the delivering pull request never ticks it in
advance (sd:1933).

`sd-ship` owns the lines `sd_lib.OWNED_TRAILERS` names: `Item:`, `Work:`, `Delivers:` and `Closes:`.
`prepare` writes `Work:` into the body it publishes; `merge` writes `Item:`, `Delivers:` and any owed
`Closes:` (sd:1600) into the squash message. A body keeps `Closes: sd:N[, sd:M]` to co-deliver those
items; the merge adds `Delivers:` for each (sd:1481). Each `sd:N` the pull request title names closes
the same way (sd:3014). `prepare` strips any other owned line from the
supplied body and lists it in the result's `normalized`. `Refs:` is not owned; its items stay open.
Without `--body-file`, `prepare` reads the open pull request's live body; `body_source` names the source.
`sd-ship body --item <item> [--body-file <file>] [--pr <n>]` prints the body `prepare` would publish
and runs the body lint on it. A merge made without `sd-ship` writes `Item:` or `Delivers:` by hand.

After the remote confirms the delivering merge, `sd work deliver <row-id>
<full-commit-sha>` verifies the commit, default branch and delivery trailer. It
records completion and the shipment time together. Repeating that operation
preserves the original receipt. A missing trailer or unavailable remote leaves
the claim unverified and reports the missing evidence; a bare merged branch or
stale issue status cannot close the item.

A whole-item merge prepared without `--deliver` carries `Item:` and no
`Delivers:`, so `sd work deliver` refuses it. `sd work deliver <row-id>
<full-commit-sha> --associated --reason TEXT` closes that row. It runs the same
reachability check, accepts the `Item:` trailer for the row instead, and records
the trailer and the reason on the receipt. A task or followup has no receipt:
its move to done records the delivery sentence and the reason. It refuses a
missing reason, and `sd-ship prepare --deliver` on such a record names it.

A `--deliver` squash GitHub lands on a base its review did not cover is held:
reconcile records the merge and not the delivery, and no git reader takes its
`Delivers:`. Once the combined tree passes and the operator closes the row by
hand, reconcile clears the hold and records `closing_owed` on the receipt. The
next `sd-ship merge` in the same repository then writes `Closes: <item>` into
its squash's trailer block, at most 10 per squash, and its result names each
in `carried_closes`. Its reconcile marks them paid only if that squash is not
held itself. Accepted gap (sd:1600): until that merge lands, a reader with no
database still sees the item open; `closes_left` names debts past the cap.

`sd work cancel <row-id> --reason TEXT` records cancellation immediately,
without a status-file change or another pull request. It does not claim the
work shipped. A later associated merge may carry `Closes: <item>` for context;
that merge is not a prerequisite for database completion. Readers with no
database can use explicit `Delivers:` or `Closes:` evidence to see that work is
closed, while only `Delivers:` says it shipped. A shallow clone that cannot
establish the evidence reports uncertainty.

`sd task cancel <row-id> --reason TEXT` closes a task or followup nobody will
do. It writes the same `done` status and `cancelled` receipt, through the same
library call with the task guard (sd:1005). `sd task status <row-id> done`
writes no receipt, so the row reads as finished work.
The guard refuses a recurring task and a row with an active assignment.
An `sd_db` older than the guard refuses the verb by name.

The item directory stays in place. Use `sd work relink <row-id> <path>` when an
artifact moves: it preserves the row, notes and original source identity. No
command automatically deletes or archives a completed item directory.

## Mutation checks

A mutation check edits the code a test covers, runs the test, and restores the
edit; a test that passes on the mutation has not earned its place.
Run a Python mutation check with `PYTHONDONTWRITEBYTECODE=1`, and delete the
`__pycache__` folders first (sd:1790). Python reuses a `.pyc` whose recorded
source size and whole-second mtime still match, so a same-size edit restored
within a second runs stale bytecode: a mutation reads as killed or survived by
timing, and a restored file can fail its own test. The variable stops writes,
not reads, so a cache left from an earlier run still answers.

## Parallel work

The harness fans work out only when a `CLAUDE.md` or a skill asks for it.
These rules say when to ask. They hold wherever a pack skill runs. A skill
that dispatches workers cites this section and restates nothing.
The pack ships a writer for multi-file code: the `sd-slice-builder` agent,
which the installer places in `~/.claude/agents`.

Four roles share the work:

- **The lead plans and lands.** One lead session per machine plans, starts
  builders, runs the merge lane and records state in `sd task note`; a
  repository's lane runs on one machine (sd:3003), so a second lead races it.
- **A builder writes code in its own worktree.** It runs only the suites its
  change touches, never `make check`, and ends with commits, a pull-request
  body file and a report; the lead's `sd-ship prepare` runs the one full gate.
- **A reader is read-only and unlimited.** Investigation, review, planning
  and audits fan out across readers; a reader changes no file, so it needs no
  worktree.
- **An integrator is a builder that merges several builders' work.** It
  applies their commits or patches on one branch, so the lane lands one pull
  request instead of several that conflict.

The rules for them:

- **Run at most 6 code-writing builders per machine.** More starve the gates
  and reviews they all wait on.
- **Start no builder while load5 is above 40.** A machine that busy already
  stretches every running builder past its deadline.
- **A writer runs alone in its checkout.** One checkout holds one writer. An
  agent or session that changes files works in its own git worktree or clone.
  Prefer a patch-only worker: it returns a diff, and one integrator applies
  it. Never start a second writer in a checkout that already has one.
- **One lane lands the work.** Several workers may produce patches or
  pull requests. One lane merges them, one at a time. Metadata that orders
  the landings — a session number, a journal or ledger entry, a changelog
  position — is allocated when the work lands, never when the branch is cut,
  because two branches cut in parallel would claim the same slot. An item id
  is not that kind of metadata: `sd work register` allocates it at plan time,
  before review and before any branch exists. Run `sd-ship prepare` and
  `merge` back to back for one item; do not hold a prepared item while
  another merges ahead of it, or its merge needs a catch-up and a new review
  (sd:2339).
- **No worker fails silently.** Every worker gets a budget, in wall clock or
  tokens. It runs in the background and reports the moment its last step
  ends, pass or fail. No report by the deadline is a failure, and so is a
  worker gone idle without one. Do not poll, and do not assume success.
  A missing report does not mean the worker stopped: cancel it and confirm
  it is gone before starting a replacement, or two attempts run at once and
  the second writer lands in a checkout the first still holds. When the
  cancellation cannot be confirmed, escalate instead of respawning. Only a
  read-only worker may be replaced on the deadline alone.
- **Fan out only when three things hold.** The targets are independent, no
  mutable state is shared, and the results are cheap to verify. Work on the
  same files or the same metadata store stays in one lane, in sequence.
- **Batch a repository's small items into one pull request.** Its small rows
  (follow-ups, P3 and P4 fixes, same-area tasks) go to one worker, one branch
  and one pull request, one commit per row, across folders too; rows that
  change the same files always group. Each pull request costs a review, a
  catch-up and a serial gate, and overlapping ones conflict. Keep a group near
  300 changed lines. Name every grouped row in the pull request, and close
  each one when it merges.
- **Iterate on the fast path; gate once before the push.** While fixing, run
  `make check CHANGED="<paths>"`, which runs only the tests those paths need
  plus an always-run set. Before the push, run the full gate once: under
  `repo.ci = local` that is `sd gate check --base main`, below; elsewhere
  `make check`. Only the full gate counts as evidence; a narrowed run exits 2
  to say so.
- **Gate first, then review the same head (sd:2603).** `sd gate check --base
  main` runs the full check in a clean worktree, takes a gate slot, and
  records a pass for the head. Then review with
  `sd-review --scope branch --gate-check main` within 30 minutes: that form reads the pass and runs no second check. Run both with
  the same environment, since the receipt binds it; a one-off prefix such as
  `TEST_WORKERS=6` on one of them makes the review run the full check again.
  A fix commit moves the head, so the next round needs a new gate pass first.
  Never run plain `sd-review --scope branch` there: it runs a second full
  check in the checkout and reuses no pass.
- **A change that moves state in steps carries a failure table before review
  round 1.** Its `design.md` or pull-request body lists each step, the state
  it moved, the failure, the recovery and the test, so round 1 reviews the
  recovery paths and not only the success path.
- **A repeating finding starts a class pass.** The trigger is two findings of
  one class in different rounds, or three blocking rounds in a row; one more
  single-finding fix lets the class come back next round. Name the class,
  list every instance from the code rather than from the findings, add each
  to the failure table, and fix each row that lacks a recovery or a test,
  fail-first. The integrator names the class in the next round's brief and
  records the trigger in `sd task note`. Split the pull request when the
  table shows it does too much.
- **Gates share the machine through slots.** Every `sd-check` run, and so
  every gate `sd-ship prepare` or `merge` runs in any repository, first takes
  one of `sd.gate_slots` machine-wide slots (unset: a quarter of the cores,
  4 on 16). `SD_GATE_SLOTS` overrides it for one run, `0` lifts the cap, and
  CI takes none. A queued gate prints `waiting for a gate slot` on stderr and
  again each minute, naming each holder's label, pid, directory and start
  time. The wait counts against `sd-check --timeout`, and each check gets the
  rest; with `--slot-timeout`, the wait has its own bound and each check gets
  the whole `--timeout`. `sd gate check`, the gate `sd-review` runs for
  `sd-ship prepare`, and the merge gate queue that way for up to 4 hours
  (sd:2607, sd:2611); the review plan counts that bound as its own phase. A holder runs its checks with `SD_GATE_SLOTS=0`, and names its cap
  in `SD_GATE_POOL_SIZE`, so the pack's own `make test` inside a gate takes no
  second slot and sizes its workers to the pool; run directly, `make test`
  takes one of the same slots. Slots are kernel locks under
  `$XDG_STATE_HOME/sd/gate-slots`, so a dead holder's slot is free at once.
- **Each gate gets its share of the cores (sd:2726).** The slot count bounds
  how many gates run, not the CPU each uses. Under a cap, a holder sets
  `CARGO_BUILD_JOBS`, `RUST_TEST_THREADS` and `NEXTEST_TEST_THREADS` (sd:2872) in its checks to the cores over
  `sd.gate_slots`, at least 1: 8 for 2 slots on 16 cores. A positive value the
  caller set wins when it is lower; a higher one is lowered. The
  `sd gate check` receipt binds these values, because a suite can pass on
  one test thread and fail on eight. So a slot count that
  changes the share misses reuse once and runs the check again. `MAKEFLAGS`
  gets no `-j`, since it would run a Makefile's prerequisites at once; a
  repository caps its own `make` pool, as the system repository's
  `make check` does (sd:2719).
- **A precheck runs before the slot wait (sd:2604).** When the repository's
  Makefile defines `precheck`, `sd-check` runs `make precheck` first, outside
  the pool. A failure stops the run there: no slot, no `check`, and the report
  names the failing check. The pack's `precheck` is `lint` plus the always-run
  test modules, about a minute. `--only` and a docs-only scope skip it, and
  the checks get what the precheck left of `--timeout`.
- **Wrap every other gate in the pool (sd:2522).** The pool is one per
  machine, not one per repository. A plain `make check` in a repository whose
  Makefile takes no slot runs as `sd gate run -- make check`, so it queues with
  every `sd-check` and `sd-ship` gate. A per-repository `lockf` around a lane's
  gate is then unnecessary: the pool already orders gates across every
  repository, and a `lockf` only orders the gates of one.
- **Gates wait in one queue (sd:2262).** Every waiter takes a place in one
  machine-wide queue, and only the head starts: first to wait, first to
  start, when a slot is free. Two starts are `sd.gate_settle_seconds` apart
  (unset: 45). The slot count is the one limit (sd:2607): macOS counts disk
  waits in the load average, so it misreads CPU pressure. So do not wait on the load average or wrap a gate in
  `lockf`; the queue already orders every gate. `sd.gate_load_max` still adds
  a load1 condition where a machine sets it (unset: none). While load5 is
  above it, load1 must then stay below it for the settle time.
  `SD_GATE_LOAD_MAX` and `SD_GATE_SETTLE_SECONDS` override them for one run;
  `0` turns either off. To gate any other command, such as
  another repository's `make check`, run `sd gate run -- make check`; it waits,
  runs the command, and frees the slot when the command ends.
  `sd gate status` shows who holds a slot and who waits, and since when.
- **Reviews share the machine through their own slots (sd:2523).** Every
  review takes one of `sd.review_slots` machine-wide review slots (unset: 2)
  before its first reviewer starts, and frees it after the last, before the
  gate.
  `SD_REVIEW_SLOTS` overrides it for one run, and `0` lifts the cap. A waiting
  review prints one `waiting for a review slot` line on stderr, naming each
  holder. The wait spends what is left of the setup bound, counted from
  the review's start; when that runs out, the review refuses with
  `review_slot_busy`. Slots are kernel locks
  under `$XDG_STATE_HOME/sd/review-slots`, so a dead holder's slot is free.
- **Ship a run of items through one lane queue (sd:2524).** `sd-ship lane
  enqueue --item N --title T --body-file F --deliver|--associate-only
  [--acceptance-file A] [--manual]` adds a worktree's item
  to its repository's queue file, which outlives the session. `sd-ship lane
  run` drains it in order under one lock per repository: head check,
  `prepare --catch-up` with the entry's delivery claim and acceptance file,
  then `merge` when `repo.runner_merge` is `auto` or the entry was queued
  with `--manual` (sd:3132); otherwise, or when the setting cannot be read,
  the entry stops `prepared` and its `code` says why. An entry with no claim is
  refused at enqueue, as prepare refuses it. A
  failed entry is marked and the next one runs. A second runner exits at once
  rather than wait. Each prepare and merge keeps its whole output under
  `<lane>/logs/`. `list` and `cancel` read and edit the queue; `watch` prints
  each gate end a log under `sd.lane_root` records, once. While an entry
  the runner may merge ships, the runner gates the next entry on its
  predicted landing in the background, and waits for that gate after the
  merge, so the next prepare reuses its receipt (sd:2586). That needs the
  tree key above; the next entry's `speculation` field says what ran.
- **Reorder a lane queue between items (sd:2584).** `sd-ship lane move <item>
  up|down|top|<position>` reorders the pending entries; `hold <item>` keeps an
  entry in place but skips it, and its speculative gate, until `release
  <item>`. These verbs edit the queue under its lock and refuse a running
  entry. The runner reads the queue's top before each item, so a change takes
  effect at the next item, never mid-merge.
- **The lead ships only through the lane.** It enqueues with `sd-ship lane
  enqueue` and drains with `sd-ship lane run`; a hand-run prepare-and-merge
  chain jumps the queue's order and leaves no log under `<lane>/logs/`.
- **Stop an item's queued ship before its builder merges main.** Run
  `sd-ship lane cancel <item>` first: the ship merges in the same worktree,
  and its abort can discard the builder's merge.
- **Stop a running ship chain by its process group** (`kill -- -<pgid>`).
  A killed shell alone leaves its children holding a gate slot.
- **After a lane merge, the runner lands the entry (sd:2568).** It deletes
  the remote branch with `--force-with-lease` while the worktree's tip is
  the merged head. It never removes the worktree or its local branch: no
  lock excludes the builder, and a write through a file handle opened before
  removal reaches an unlinked file and is lost. The entry's `remove` holds
  the command to run once the builder stops: `git -C <main> worktree remove
  <worktree> && git -C <main> update-ref -d refs/heads/<branch> <tip>`.
  `git worktree remove` refuses uncommitted or untracked files, and
  `update-ref -d` refuses a branch that moved. The runner then notes the
  item: `Landed: merged at <merge> (head <head>). Cleanup: …. Recover: git
  branch <branch> <tip>. Remove: <command>` Last, it fast-forwards the main
  checkout when it is on the default branch. When that checkout holds the
  running `sd-ship`, it first tries every other lane's runner lock once and
  skips if one is held; the next landing retries.
- **Each lane runs on its lane host (sd:3003).** `repo.lane_host` names the
  machine that runs a repository's lane; NULL means the hub. Off that host,
  `sd-ship merge`, `reconcile`, `review`, `adjudicate --accept-dispositions`
  and `lane enqueue`, `move`, `hold`, `release` and `run` refuse with
  `lane_elsewhere` before they read a row (sd:2795); the text names the host,
  the dashboard's Move lane control, and the verb. A host that cannot be read
  refuses with `lane_unknown` and never counts as the hub. `prepare` runs
  everywhere without the ship lock (sd:1938), and `lane list` and `cancel` still answer, so
  an old host's pending entries can be cancelled after a move. Every machine
  runs the same scheduled `sd-ship lane run --hosted`: each lane it hosts, in
  path order, skipping one whose runner is busy. The runner reads the host
  again before each claim, so a move stops it at the next item. A satellite
  that hosts a lane gates and merges there; no item passes between machines.
- **Large uncommitted data goes under the bulk root (sd:1792).** When
  `sd.bulk_storage_root` names a folder, put run outputs, logs, captures,
  agent scratch evidence and large downloaded fixtures under
  `<root>/<repository>/`, not in the checkout. Keep build output, such as
  Cargo's `target/` or `node_modules/`, and data whose mode or owner matters
  on the system disk: a bulk volume may be ejected mid-build, and a volume
  mounted `noowners` reports every file as yours. Unset, nothing moves.
- **Test one version per language, the latest stable (Python 3.14, Node 26); no version matrices.**

A session writes on its own branch in its own worktree, one writer per
worktree: `sd-plan --worktree` puts a new branch in a worktree of its own, and
`git worktree add` makes one for any other session. Merging is one lane:
`sd-ship` merges one pull request per run.

Before writing a fix, look on the remote for a branch or pull request that
already claims it, by the item id or by the changed path. Two sessions that
land one defect waste one session's work; sd:1151 records the case.

## Modes

`CLAUDE.local.md` carries one `mode:` line per repository. The installer writes
the block; the file is untracked by construction.

| Mode | Where planning artifacts go | What ships |
|---|---|---|
| `full` | `docs/work/` in the repository | everything above; merge only with `runner_merge: auto` on the row |
| `minimal` | nowhere, by convention only; nothing enforces it | the small-change path only |
| `guest` | nowhere in the repository; both checks below refuse them | the small-change path to pull-request-ready; no posts, no labels |

`minimal` holds no work items by agreement, not by a check.
`sd-docs-lint` skips its `docs/work` rules there: a local folder and the pages that name it are not linted.
`sd_lib.guest_artifact_refusal` and `sd-ship`'s push check refuse
`docs/work/`, `docs/spec/` and `docs/decisions/` in `guest` only, so a
`minimal` repository can commit and push them unrefused. `sd-ship` also adds
the `Work: sd:<id>` line in `minimal`, as it does in `full`. Only `guest`
refuses the review routing lane (R10-D5): `minimal` is written by hand and
never detected, so it names the operator's own quiet repository, and may
install the lane (sd:1292).

Access decides where artifacts go, whichever namespace holds the
repository. Without a `mode:` line, the pack asks three questions of the
remote: can you administer it, is it not a fork, can anyone else push. Admin,
not a fork, nobody else: `full`, in your namespace or an organisation's.
Anything else, including no answer: `guest`. A root with no remote, **or
no git at all**, is `full`; there is no one to expose anything to. The
no-git case is decided on its own rather than falling into whichever
exception branch the remote lookup raises. The questions are asked
again before every artifact write and every push, and a `no` makes the
run `guest` whatever the line says: a `mode: full` you wrote is a ceiling,
never a floor: detection lowers it and never raises it, so a repository
that gains a collaborator stops
receiving your planning artifacts before the next push, not after the
next merge. The push check reads what the push adds over `origin/<base>`
and refuses a guest push that carries planning paths, to an upstream or to
your own fork alike; no fork integration branch exists. A lowered run leaves a note on the
item saying which answer lowered it, once per item and remote however many
runs it takes, and `sd-status` names the planning artifacts the shared tree
was already carrying, which are yours to move. Mode never decides merging.
`runner_merge: auto` is a per-repository policy you set once with
`sd-db.sh repo runner-merge <path> auto`, off by default, and nothing derives it.
Every merge asks the same three questions again, one function for both gates.
Two of the three answers are final: a repository you do not administer, and a
fork, are refusals no setting reaches, and so is a question the remote could
not answer at all. The third -- "nobody else may push" -- is the one the row
speaks for, because co-ownership is exactly what you decided about when you
set the row. `auto` answers it and a merge proceeds; `manual`, no row, or a
database that cannot be read suspends it with the reason shown. A merge the
row let through says so on its receipt, naming the repository, the setting and
who else may push, so an ownership merge and a row-authorized one are not one
sentence.

## Providers

The provider registry maps roles to providers.
Reusable skill procedures name roles; operator policy owns preferred entries.

Cheap, standard, and deep changes require one completed independent local review.
Skip requires none; planning and challenged reviews retain their minimum of one.
Tier selection still follows repository policy, without adding automatic local reviewers.
Complete local review before any Copilot request; [Standing authorization](#standing-authorization) holds the policy.
A completed Copilot review must cover the merge head, or an ancestor whose diff to it touches only skippable `docs/` paths.

    bills:
      anthropic: { cost: subscription }
      openai:    { cost: subscription }
      moonshot:  { cost: prepaid }
      minimax:   { cost: plan, meter: "https://www.minimax.io/v1/token_plan/remains", meter_env: MINIMAX_API_KEY }
      baseten:   { cost: company, cap_usd_month: 50 }
      local:     { cost: local }
    providers:
      claude:  { start: "claude -p",  vendor: anthropic, bill: anthropic, roles: [author, reviewer], reader: claude-json }
      codex:   { start: "codex exec", vendor: openai,    bill: openai,    roles: [author, reviewer], reader: codex-json }
      opencode: { start: "opencode run", model: openai/gpt-5.5, vendor: openai, bill: openai,
                  roles: [reviewer], reader: opencode-json }
      kimi:    { url: "https://api.moonshot.ai/v1", model: kimi-k3, vendor: moonshot, bill: moonshot,
                 roles: [reviewer], max_tokens: 65536, price: { in: 3.00, out: 15.00 } }
      minimax: { url: "https://api.minimax.io/v1", model: MiniMax-M3, vendor: minimax, bill: minimax,
                 roles: [reviewer], max_tokens: 65536, price: { in: 0, out: 0 } }
      baseten: { url: "https://inference.baseten.co/v1", model: deepseek-ai/DeepSeek-V4-Pro-0813, vendor: deepseek,
                 bill: baseten, roles: [reviewer], max_tokens: 65536, price: { in: 1.32, out: 3.96 } }
    roles:
      author:   [claude, codex]
      reviewer: [codex, claude, opencode]

A capped bill takes `url` entries only, because the library makes those
calls and can refuse one before it is sent; a `start` entry on a capped
bill is refused when the file is read.

Each entry also carries `env`, the list of variables the entry's process
receives beside `PATH`, `HOME`, `LANG`, `TERM` and `TMPDIR`, `env:
[OPENAI_API_KEY]` for `codex`; left out of the example above for width. A
session inherits the variables its own entry names and no other entry's.
That is inheritance, not isolation: the session runs as you, in your
`HOME`, and can read the file the keys live in.

Model pins, meters, token ceilings, reasoning controls and `response_format`: [docs/providers.md](docs/providers.md).
Change a pin by editing the registry file, never by a page.
A `url` answer that fails the findings schema retries once on the same entry only when its `price` is zero in and out;
a priced entry falls through to the next reviewer.

Adding a provider is an entry; adding money is a bill. Both role lines are
read in order. `author` is picked when an assignment starts and never switched
mid-item. `reviewer` is the first entry that is enabled, is of no vendor that
authored the change, is on no bill at its cap this month, and answers
its preflight (the cap check is below). A rate limit,
a missing binary, a failed run or a timeout falls through to the next, and the
run says which one reviewed and why the earlier ones did not. With none left,
the review refuses by name rather than reading its own work.
Only entries on the reviewer order participate in automatic fallback.
Enabled reviewer-capable entries outside that order require an explicit `--provider` selection.
With a database, the order in force is its rows: `sd providers configure` sets it, `sd providers list` shows it, and `sd-review --explain` names it on its `order from` line; the file's `roles:` lists only seed those rows. The shipped seed contains Codex, then Claude, then opencode; other providers remain explicit-only until an order names them.
Existing provider files and database orders remain unchanged until the operator migrates them.
The chain continues until the required count completes or eligible entries run out. A completed
review with findings counts; it does not trigger a replacement. Consent, author
exclusions and spending limits apply to every fallback, and earlier findings remain.
`vendor` is the
maker of the model, not the tool; `bill` is whose money. A bill with
`cap_usd_month` is held per call, and a `url` entry on a capped bill is
held to it before its request is sent. Every `url` call `sd-review` makes
goes through the library's `sd_db.calls.call` (`source:bin/sd-review::charged_call`):
the call's bound, the prompt's estimated tokens at `price.in` plus
`max_tokens` at `price.out`, is reserved against the bill's month; the
request is claimed, sent once, and the row is settled at the usage the
answer carries or bound at the reservation when it cannot be costed. A
bound that would pass the cap is refused by the ledger and the fallthrough
passes the entry over. Before the chain is built, `review` sweeps
reservations whose process is gone and asks the ledger which capped bills
are at their cap this month (`source:bin/sd-review::capped_bills`); those
reach `reviewer_chain` and `pick` in `bin/sd_registry.py` as bill name to
the month's total, so the fallthrough skips every entry on such a bill and
`--provider` refuses one by name, saying what the month spent or holds.
Once the registry read succeeds, a fault at the ledger -- no library to
reach with no state file beside the registry, a library older than
`sd_db.calls`, or a reservation the database will not take -- refuses an
entry on a capped bill naming the fault and dispatches an entry on an
uncapped bill as before: unknown is not uncapped. A state file that exists
but cannot be read, or exists while the library cannot be imported, is
refused at registry read (`source:bin/sd_registry.py::read_runtime`), and
nothing is dispatched. A `url` entry on a capped bill without a usable
`price.in`, `price.out` and `max_tokens` is refused at registry read, on
the file and on the merged rows, since a cap the ledger cannot reserve
against is not a cap. Entries with `url` share one OpenAI-compatible client
and one reader. This file is identity and seed; enabled, order and caps
are rows the dashboard edits, and the library merges file and rows on
every read.

`sd-review --provider <name>` picks one entry for one run. The dashboard's
item screen offers the same list, with vendor, cost and reason beside each
name. Copilot and Greptile are not entries: they post on the pull request, and
this lane never posts.

This file is the only list of provider identities. `sd-review` reads it through the
library. `.github/sd-review.json` carries repository policy, paths and severity;
it names no provider chain. Effective authorization restricts the registry's
reviewer chain before vendor, transport, availability and spending gates run.

## Standing authorization

Core settings use `sd config get|set|unset|list` and the existing atomic machine configuration writer.
The file is `~/.config/sd-ai-command-pack/config.json`, honoring `XDG_CONFIG_HOME`.
Merge permission is one setting, `repo.runner_merge`: a column on the repository row in the workflow database, not an `sd` key.
Set it with `sd-db.sh repo runner-merge <path> auto|manual`; `sd-db.sh repo list` shows it as each row's last field.
`auto` lets the runner and the assistant merge active, in-scope work without asking, only through `sd-ship prepare` then `sd-ship merge`.
No value permits a merge that skips the review lane, such as a raw `gh pr merge` or a web squash; a refusal from `sd-ship` is a stop.
`manual`, no row, or an unreadable database means ask the operator first. An explicit instruction to wait wins.
`sd.assistant_merge` is retired: `repo.runner_merge` is the assistant's setting too.

The reserved `sd` namespace declares these settings:

- `sd.external_reviews`: `configured` permits private code and scoped review context to eligible configured providers.
  It includes future registry entries; registry configuration chooses capability, while this explicit operator grant authorizes transmission.
  `deny` vetoes all local allowances. Absence supplies no standing grant.
- `sd.copilot_review`: when `sd-ship` requests a Copilot review by itself. `deep` requests one on deep-tier changes only,
  `always` on every reviewing tier, `never` on none. Absence reads `deep`, so a repository with no
  `.github/sd-review.json` gets Copilot on deep changes and on nothing else.
  A repository file that names `copilot_review.automatic_deep` overrides `deep` and `always`; one that does not inherits.
  `never` wins over the file.
  `sd-review` reports the effective policy, its source and the repository's say under `remote_reviews.copilot`.
  `sd-ship` resolves the decision again at dispatch, from the setting as it stands then and the tiers the
  retained passes recorded, so a setting changed after the review takes effect without another review.
- `sd.gate_slots`: how many gates (`sd-check` runs, `sd gate run`, the pack's `make test`) may run at once on
  this machine; `0` is no cap. Absence reads a quarter of the cores. `SD_GATE_SLOTS` overrides it
  for one run. It grants nothing;
  see [Parallel work](#parallel-work).
- `sd.review_slots`: how many reviews may run their reviewers at once on this machine; `0` is no cap.
  Absence reads 2. `SD_REVIEW_SLOTS` overrides it for one run. It grants nothing.
- `sd.gate_load_max`: the gate queue starts a gate only while load1 is below this; `0` is no load condition.
  Absence is no load condition (sd:2607). `SD_GATE_LOAD_MAX` overrides it for one run. It grants nothing.
- `sd.gate_settle_seconds`: seconds between two gate starts, and of low load1 while load5 is high; `0` is none.
  Absence reads 45. `SD_GATE_SETTLE_SECONDS` overrides it for one run. It grants nothing.
- `sd.fleet_owners`: comma-separated GitHub logins whose repositories `sd fleet stamp` treats as the operator's own.
  Absence reads the deprecated `fleet.owners` list in the machine config, then the pack's default, `platypeeps`. It grants nothing.
- `sd.gate_cache_gb`: the most gigabytes the local gate's warm Rust build folders may hold; `0` is no bound.
  Absence reads 40. `SD_GATE_CACHE_GB` overrides it for one run. It grants nothing.
- `sd.lane_root`: the folder that holds each repository's `sd-ship lane` queue, as `<root>/<repository>/lane/queue/`.
  Absence reads `$XDG_STATE_HOME/sd/lanes`. `SD_LANE_ROOT` overrides it. It grants nothing.
- `sd.bulk_storage_root`: the folder for large uncommitted data, as `<root>/<repository>/`; see
  [Parallel work](#parallel-work). Absence is no bulk root. It grants nothing.
- `sd.privacy_patterns`: the privacy-pattern file `sd-docs-lint --pr-body` checks a pull request body against, one
  extended regular expression per line. Absence reads `privacy-patterns` in `$SYSTEM_TOOLS_CONFIG`, else in
  `${XDG_CONFIG_HOME:-~/.config}/system`. No file skips the check with a note. It grants nothing.

Installation supplies no grant. A new operator must state their own policy; never copy another user's personal permission.
These settings start no background work, enable no runner policy, and bypass no ownership, review, CI, or protection gate.
Review depth, author exclusions, spending limits, and the review table's automatic pass caps remain unchanged.
The upstream pull-request exception in `AGENTS.md` still requires permission for that specific PR.

Review resolution is ordered: machine deny; present local restriction; configured standing policy; otherwise refusal.
A local named list restricts recipients. An explicit empty list denies all; malformed local consent refuses.
An absent local key inherits standing policy. `--explain` and review receipts identify the authorization source.
Linked worktrees share the main checkout's local block; installer output and review receipts name that canonical path.
Unreadable existing configuration paths refuse, including directories and dangling links.
Ship receipts bind the external-review policy source and value; changing it invalidates the recorded review.
Unrelated machine settings do not invalidate reviews.

## Overrides

The `CLAUDE.local.md` block carries these keys, and the pack reads no others.

    mode: full | minimal | guest
    check: <the command that verifies this repo>
    test: <optional, when the repo spells its tests separately>
    lint: <optional, same>
    reviewers: <entry@recipient pairs that may receive this repository's diff, e.g. claude@claude+3f9a1c2e, baseten@inference.baseten.co>
    guest_allow: docs/decisions   (optional; the only tree a guest repository can take out of the refusal)

`check`, `test` and `lint` run in that order and are optional; one combined command can use `check` alone.
`reviewers` restricts the effective authorization described above. Each local entry binds its destination:
a URL host, or an executable with a fingerprint of its command and declared environment names.
A changed destination or fingerprint needs a changed local allowance. Standing `configured` policy follows the current registry instead.
Transport restrictions and the operator's responsibility for tool configuration remain unchanged.

The installer preserves an existing answer, including empty denial. Malformed existing blocks and unknown answers refuse without rewriting consent.
Without local consent it inherits an explicit machine policy, or offers enabled recipients with no default grant.
An explicit empty answer writes a durable empty restriction. Earlier installers erased some empty answers;
missing historical keys cannot distinguish those answers from repositories never configured. Inspect them before granting standing policy.

Everything under **Opt-in** above is asked for by name, in the moment, rather
than switched on in a file. Naming it is already the whole cost, and a key that
turns a lane on permanently is a default in disguise: it stops being a decision
you make about this change and becomes one you made about this repository,
months ago, for reasons the file does not record.
