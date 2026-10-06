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
Unattended merging requires `runner_merge: auto` on the repository row and a fresh sole-operator check before each merge.
This runner rule is separate from active task permission under **Standing authorization**.
Without either applicable authority, stop at pull-request-ready.

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
  Under `repo.ci = local`, each round adds `--gate-check main` after an `sd gate check --base main` pass at that head (sd:2603).
- CI runs on the pull request.
  Wait for required checks on the exact head; preserve review, ownership, protection, and authorization gates.
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
  After each confirmed in-scope merge, the agent follows the ship skill's post-merge closeout procedure.
  It dispositions remaining findings and inventories refs, branches, stashes, and worktrees.
  It removes the merged PR's local and remote branches, stashes, refs and stale worktrees when they are safe, without asking.
  It records each removed target's object ID or path first, and keeps anything that fails a safety condition.
- Expected branch protection requires pull requests, current CI, and up-to-date branches, with no required approvals.
  Configure it deliberately in GitHub; installation does not grant a protection exception.
  `sd-status` reports gaps; executable merge stops when required protection is absent.
  Protection is read from both of GitHub's mechanisms: the classic object first, and when that is absent, the branch's active rulesets.
  A ruleset with a `pull_request` or `required_status_checks` rule is the protection, held to the same guards; one that only forbids deletion or force-push is not.
  One accepted gap changes that gate: an `unprotected` entry in `.github/sd-status.json` at the reviewed commit.
  Under it, `sd-ship merge` requires every check run, every status, and a `pull_request` run of every workflow at the head to pass.
  The receipt records `declared_gap: unprotected`. Any other gap, and a declaration only in the working tree, do not change the gate.
- `make check` and the pack's `lint` CI job run `sd-docs-lint` against the
  checkout's own `docs/work/`, `docs/spec/` and `docs/decisions/`.
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
  The dashboard's weekly missing-trailer count reads `Authored-with:`, not
  `Needed-by:`; nothing counts a missing `Needed-by:` after the warning.

## Opt-in

These run only when asked by name.

- A work item under `docs/work/<date>-<slug>/prd.md`. Create one when the
  work spans more than one session or more than about 300 changed lines.
  `design.md` and `implement.md` exist only when you ask for them. Where
  status lives is what `docs/work/.status-source` says. A checkout whose
  marker says `row` reads it from the item's row and nowhere in the file: an
  active `prd.md` there carries no `status:` line, and `sd-docs-lint` fails
  one that does. A checkout with no marker reads the prd's `status:` line,
  because its lines were never retired -- `file` is the unmarked default, and
  deliberately so (`source:bin/sd_lib.py::status_marker` answers `file` for an
  absent marker: the path every reader took before rows existed, not a new
  one that happens to agree with it). Under `row`, a checkout or CI runner
  with no database asks git whether the item is delivered, by the merge
  trailers, and nothing else. `ready_to_send` marks a finished artifact
  waiting on you.
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
When the cap is spent no further pass starts on its own. The artifact moves on,
to the send box, to implementation, to merge, once every blocking finding is
addressed or rebutted with evidence on the item. A blocking finding still open
past the cap marks the item `blocked`; non-blocking findings hold nothing.

| Flow | Point | What it checks | Cap |
|---|---|---|---|
| Research | After the brief and decisions | Claims against sources, gaps, wrong calls | 2 |
| Research | Final product, before the send box | The piece, page or ticket as a reader sees it | 1 |
| Development | prd and design | Scope, missing requirements, wrong assumptions | 5 |
| Development | Code, before merge | Defects a second reader finds | 5 rounds |

The code pass reads a head. Under `repo.ci = local` a gate pass at that head
comes first; see [Parallel work](#parallel-work). A fix that changes the head
gets a further verification pass over the diff since the reviewed head, up
to the cap above; `sd-ship` pushes only the reviewed head or a verified fix
of it, and merges naming that head with
`gh pr merge --squash --match-head-commit <the reviewed sha>` —
equivalently `PUT /repos/{owner}/{repo}/pulls/{n}/merge`
with `sha=` — so a head that moved after the review is refused at GitHub with
a 405. The flag is what does the refusing: a merge that carries only a title
and a body refuses nothing, whatever head moved under it.

The reviewer is a different vendor from the author, always. Skills name the
roles `author` and `reviewer`; the provider registry below maps them.

The post-merge ten-pass experiment, `sd:777`, is cancelled.
Its historical records remain evidence, not instructions to resume external reviews.
Restart requires a new explicit user decision.

## Advisory

- Copilot is an optional second review after local review.
  Repository policy can select automatic review for the high-value `deep` tier.
  Other requests require explicit task direction.
  Automatic review applies once per pull request, not after each push.
  Task-scoped suppression persists until a later explicit request replaces it.
  The shipping adapter caps total Copilot requests at three per pull request.
  Shared repositories receive no pack reviewer requests.
  Read and disposition independently posted findings.
  Policy selection remains advisory until a review is requested.
  After that request, completion and finding disposition become merge gates.
  Existing repository merge rules still apply.

After every confirmed in-scope merge, follow `skills/sd-ship/references/post-merge-closeout.md` in the sd-ai-command-pack checkout.
Inspect all paginated threads and review bodies, including late findings.
Local acknowledgement and remote thread resolution are separate operations.
Authorized shipping closeout replies with evidence or a verified follow-up before resolving eligible threads.
Uncertain findings remain open; no automatic Copilot request follows.

## Never in a shared repository

A shared repository resolves to `guest` mode. Detection never produces
`minimal`; only an operator writes it, and the refusals below that name
`guest` do not apply to it.
`full` requires administration, a non-fork remote, and exclusive push access.
In a shared repository:

- No `Work:` line in a pull request body unless the pull request resolves a
  work item that lives in that repository.
- No `docs/work/`, `docs/spec/`, or `docs/decisions/` commits. `mode: guest`
  already carries this: planning artifacts go to the fork's integration branch.
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
- No merge without task-specific or standing operator permission. Shared contributors
  do not revoke that permission. The assistant reads the permission, not
  `sd-ship`, which never consults `sd.assistant_merge`. `controlled` is standing
  permission to merge through `sd-ship prepare` then `sd-ship merge` without asking.
  No permission covers a merge that skips the review lane. Existing ownership and
  protection gates still decide whether the pack can execute it; a refusal remains a stop.
- No issue filed. `sd-suggest` writes a row everywhere; `sd suggest publish`
  files it as an sd item when you run it, in the checkout you name with
  `--belongs-to`. No pack surface files a GitHub issue.

## The path for a change

Small change: branch, commit, local review, push, pull request, CI, merge.
Use the ship workflow without inventing a planning artifact.
After review, take a newer default branch with `git merge origin/<base>`, never a rebase:
a rebase rewrites the reviewed commits, and the next push no longer fast-forwards
the branch `sd-ship` pushed. `sd-ship prepare --catch-up` makes that merge.

Change that earns a work item: `sd-plan` writes `prd.md` using the requirements
already available and asks only for missing decisions. Then the small-change
path runs with the applicable review points. An item can span several pull
requests. `Item: <item>` associates a merge without closing the item;
`Delivers: <item>` declares the delivering merge. Changes without an associated
item omit those trailers and create no placeholder record. The trailers are the
last paragraph of the squash message, contiguous, with the attribution
paragraph above them and nothing below: a squash merge concatenates the body
into the commit message, git reads trailers only out of the final paragraph,
and GitHub's appended `Co-authored-by:` joins a trailer block that ends the
message but opens a new paragraph after anything else.
`.github/PULL_REQUEST_TEMPLATE.md` ends in that order, with `Refs:` only.

A criterion only the operator can observe, such as a command running unprompted
on their machine, is not a checklist box. Record it in the item's `## Log` with
its date when it is observed; the delivering pull request never ticks it in
advance (operator ruling 2026-09-30, sd:1933).

`sd-ship` owns the lines `sd_lib.OWNED_TRAILERS` names: `Item:`, `Work:`,
`Delivers:`, `Closes:`, `Authored-with:` and `Attributes:`. `prepare` appends
`Work:` to the body it publishes, and `merge` appends `Item:`, `Delivers:`, any
owed `Closes:` (sd:1600) and the authorship lines to the squash message, so a
body written for `sd-ship` carries none of them. The one exception is
`Closes: sd:N[, sd:M]`: the body keeps it, and the merge adds `Delivers:` for
each item it names and closes them with the claimed item (sd:1481). Only a
column-zero line outside fenced code and HTML comments counts; `prepare`
refuses a quoted one, which an indent keeps as an example. `Refs:` is
not owned; its items stay open. A supplied line that says what `sd-ship` would write is
stripped and listed in the result's `normalized`; any other owned line is
refused by line number, with the expected value. So the body `sd-ship`
published, fed back as `--body-file`, prepares again. Without `--body-file`,
`prepare` reads an open pull request's live body, so an edit made on GitHub
survives; with no receipt, the pull request open for the branch is the one
read, so a pull request opened by hand keeps its body. The result's
`body_source` says `file`, `live_pr`, `state` or `default`.
`sd-ship body --item <item> [--body-file <file>] [--pr <n>]` prints
the body `prepare` would publish and runs the body lint on it. Its `scope`
names each scope line the diff demands, such as `CI/review scope:` for a
`.github/**` path, and whether the body carries it. The diff is the checkout's
HEAD against `origin/HEAD`; with `--pr` it is that pull request's files, and
without `--body-file` its live body is read. It reads no sd state, calls the
GitHub API only for `--pr`, and exits non-zero on a refusal or a lint failure. A merge
made without `sd-ship` writes the trailers by hand, in the order above.

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
writes no receipt, so the row reads as finished work. A finding that
`sd-review-ack` carried to a cancelled row reads `carry-dropped` and holds
again. The guard refuses a recurring task and a row with an active assignment.
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

- **A writer runs alone in its checkout.** One checkout holds one writer. An
  agent or session that changes files works in its own git worktree or clone.
  Prefer a patch-only worker: it returns a diff, and one integrator applies
  it. Never start a second writer in a checkout that already has one.
- **Readers fan out.** Investigation, review, planning and audits run in
  parallel across read-only workers. A read-only worker needs no isolation.
- **One integrator lands the work.** Several workers may produce patches or
  pull requests. One lane merges them, one at a time. Metadata that orders
  the landings — a session number, a journal or ledger entry, a changelog
  position — is allocated when the work lands, never when the branch is cut,
  because two branches cut in parallel would claim the same slot. An item id
  is not that kind of metadata: `sd work register` allocates it at plan time,
  before review and before any branch exists, and `sd runner prepare` and
  `sd run` both require it to already exist.
- **No worker fails silently.** Every worker gets a budget, in wall clock or
  tokens. It runs in the background and reports when it finishes. No report
  by the deadline is a failure. Do not poll, and do not assume success.
  A missing report does not mean the worker stopped: cancel it and confirm
  it is gone before starting a replacement, or two attempts run at once and
  the second writer lands in a checkout the first still holds. When the
  cancellation cannot be confirmed, escalate instead of respawning. Only a
  read-only worker may be replaced on the deadline alone.
- **Fan out only when three things hold.** The targets are independent, no
  mutable state is shared, and the results are cheap to verify. Work on the
  same files or the same metadata store stays in one lane, in sequence.
- **Group rows that change the same files.** Every open row on one file or
  folder goes to one worker, one branch and one pull request, so one review
  covers them all. Keep a group near 300 changed lines, and split a larger one
  by file. Do not group rows across unrelated folders: a wider diff draws more
  review rounds, not fewer. Name every grouped row in the pull request, and
  close each one when it merges.
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
  `CARGO_BUILD_JOBS` and `RUST_TEST_THREADS` in its checks to the cores over
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
  (unset: 45). The slot count is the one limit (sd:2607): macOS counts threads
  waiting on the disk in the load average, which read 124 on 2026-10-03 while
  most cores idled. So do not wait on the load average or wrap a gate in
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
  then `merge` for an entry queued with `--manual`. An entry with no claim is
  refused at enqueue, as prepare refuses it. A
  failed entry is marked and the next one runs. A second runner exits at once
  rather than wait. Each prepare and merge keeps its whole output under
  `<lane>/logs/`. `list` and `cancel` read and edit the queue; `watch` prints
  each gate end a log under `sd.lane_root` records, once. While an entry
  queued with `--manual` ships, the runner gates the next entry on its
  predicted landing in the background, and waits for that gate after the
  merge, so the next prepare reuses its receipt (sd:2586). That needs the
  tree key above; the next entry's `speculation` field says what ran.
- **Reorder a lane queue between items (sd:2584).** `sd-ship lane move <item>
  up|down|top|<position>` reorders the pending entries; `hold <item>` keeps an
  entry in place but skips it, and its speculative gate, until `release
  <item>`. These verbs edit the queue under its lock and refuse a running
  entry. The runner reads the queue's top before each item, so a change takes
  effect at the next item, never mid-merge.
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
- **A satellite gates; the hub's lane merges (sd:2704).** In a repository
  with `repo.ci = local` and `repo.satellite_gate = accept`, a satellite runs
  the gate and the prepare, and asks the hub's lane to merge with `sd-ship
  lane request`. The hub runs no gate for that item: its merge compares the
  satellite's offload receipt under the trust rule and refuses with a
  `satellite_*` or `base_moved` code. A refusal, or a branch or base that
  moved, hands the item back to the satellite with the next action on the
  request row and the item. Opting in also cuts the environment of every gate
  in the repository, on the hub too, to the variables the hub compares plus
  `HOME`, `USER` and `PATH` (sd:2782): a check that needs a credential or
  another variable off that list fails, so leave such a repository off. The
  table below is who does what. On a satellite, `sd-ship merge` and the queue
  verbs (`lane enqueue`, `list`, `cancel`, `move`, `hold`, `release`) refuse
  with `hub_only` before they read a row (sd:2795).
- **Test one version per language, the latest stable (Python 3.14, Node
  26), in CI and locally; no version matrices.**

| Step | Machine | Command | What it does |
|---|---|---|---|
| 1 | satellite | `git merge origin/main` on the branch, or `sd-ship prepare --catch-up` | The head contains the current base before any gate |
| 2 | satellite | `sd gate check --base main` | Runs `sd-check`; writes the satellite's receipt and the offload receipt to the hub |
| 3 | satellite | `sd-ship prepare --item N --title T --body-file F` | Reviews (its gate reuses step 2), pushes, binds the pull request, posts `sd/local-gate` from the offload receipt |
| 4 | satellite | `sd-ship lane request --item N --manual` | Writes `lane-request:v1:<slug>:<item>` to the hub |
| 5 | hub | `sd-ship -C <checkout> lane run --satellite-only`, from a scheduled job | Takes requests in and runs satellite entries only; exits when none is pending or another runner holds the lane |
| 6 | hub | intake, before each claim | Refuses a request the repository did not opt into, a malformed one, or one not prepared at its head; else queues a `gate: satellite` entry and writes `queued` |
| 7 | hub | the entry | Fetches the branch and the base; hands back on `head_moved` or `base_moved`; no prepare, no catch-up, no speculative gate; then `sd-ship merge --satellite-gate` |
| 8 | hub | `sd-ship merge --satellite-gate` | Accepts the offload receipt under the trust rule, posts no status, merges |
| 9 | hub | landing | Deletes `origin/<branch>` with a lease on the merged head; writes the outcome to the request row; notes the item |

Without `--manual` in step 4, step 7 stops before the merge as `prepared`,
as a hub entry queued without it does.

The pack has two write lanes, and each holds one writer. A session writes on
its own branch in its own worktree: `sd runner prepare <item> --branch <name>`
prepares the item branch in the current repository, and `sd-plan --worktree`
puts a new branch in a worktree of its own. The runner writes in a clone it
makes for each run of an assignment, under its work root. It holds a lease on
the repository branch for the run, so a second run on that branch waits until
the first ends. `sd worktree resume <assignment>` resumes a run whose checkout
the runner kept. `sd worktree restore <assignment> --destination <path>`
copies a retained clone to a new absolute path that does not exist yet.
Neither verb makes a worktree for a session; `git worktree add` does that.
Merging is one lane: `sd-ship` merges one pull request per run, and the
runner's unattended merge stays under **Development** above.

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
| `guest` | the fork's integration branch | the small-change path to pull-request-ready; no posts, no labels |

`minimal` holds no work items by agreement, not by a check.
`sd_lib.guest_artifact_refusal` and `sd-ship`'s push check refuse
`docs/work/`, `docs/spec/` and `docs/decisions/` in `guest` only, so a
`minimal` repository can commit and push them unrefused. `sd-ship` also adds
the `Work: sd:<id>` line in `minimal`, as it does in `full`. Only `guest`
refuses the review routing lane (R10-D5): `minimal` is written by hand and
never detected, so it names the operator's own quiet repository, and may
install the lane (operator ruling 2026-09-30, sd:1292).

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
next merge. The push check is of the destination: your fork's integration
branch is your own remote, and the guest push there proceeds while the
same branch offered upstream is refused. A lowered run leaves a note on the
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
sentence. Without that, the third question refused every co-authored
repository permanently and the lane ended at `ready_to_send` for a human to
finish by hand.

## Providers

The provider registry maps roles to providers.
Reusable skill procedures name roles; operator policy owns preferred entries.

Cheap, standard, and deep changes require one completed independent local review.
Skip requires none; planning and challenged reviews retain their minimum of one.
Tier selection still follows repository policy, without adding automatic local reviewers.
Complete local review before any Copilot request.
The machine's `sd.copilot_review` selects remote review during shipping: `deep` (unset reads `deep`), `always` or `never`.
A repository's `copilot_review.automatic_deep` overrides `deep` and `always` when the file names the key; a file that does not name it inherits.
A machine `never` wins over the file (sd:1444).
Shipping reads that override once, from the latest retained review report that names it, and applies it to the tiers every retained pass recorded.
`sd-review --explain` names the effective policy and whether the repository, the machine config, or the machine default answered.
Automatic review runs once per pull request after the local review and acknowledgement step.
Later pushes still require exact-head local review and CI.
A completed Copilot review must cover the merge head, or an ancestor of it.
An ancestor clears only when the diff from it to the merge head touches nothing outside `docs/`.
Each such path must also be one the repository's policy lets skip: in `docs_skip` and not in `never_skip`.
`tests/` is inside that surface: a green suite does not say a test still asserts what the reviewer approved.
The merge receipt carries a warning naming the ancestor whenever one clears the gate.
Request an explicit later-head review only when the automatic review is stale.
If that request cannot be recorded, a manual merge can abandon the latest request basis.
An exact-head receipt replaces the latest prior receipt as that basis.
Only submitted, non-pending reviews mark matching request heads complete.
`false` keeps Copilot explicit-only.

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
bill is refused when the file is read. That is why `baseten` is one `url`
entry and the `prism` and `gito` CLIs are gone: they pointed at the same
endpoint and added limits of their own.

Each entry also carries `env`, the list of variables the entry's process
receives beside `PATH`, `HOME`, `LANG`, `TERM` and `TMPDIR`, `env:
[OPENAI_API_KEY]` for `codex`; left out of the example above for width. A
session inherits the variables its own entry names and no other entry's.
That is inheritance, not isolation: the session runs as you, in your
`HOME`, and can read the file the keys live in.

Pins as of 2026-09-05, each read from the vendor's model list on that day:
`kimi-k3` is Moonshot's current flagship with a one-million-token window;
`MiniMax-M3` is MiniMax's newest, and it runs on the Token Plan the
operator has already paid, so the entry's price is zero and the bill
carries a meter instead: the plan grants use in a five-hour window and a
weekly window, and `GET /v1/token_plan/remains` on `www.minimax.io`, with
the same key, answers with `current_interval_remaining_percent` and
`current_weekly_remaining_percent` for `model_name: general`, probed
2026-09-05. The bill carries that meter as a URL and the variable holding
its key as `meter_env`. A review reads it only for an eligible selected or fallback provider: one `GET` to
that URL, and to no other -- the scheme, host, port and path are pinned in
`bin/sd_registry.py` and any other value is refused naming the value and
the four, with nothing sent -- then the two percents written as `meter`
rows for every enabled entry on the bill, then the newest row per window
read back. A window at zero, no row at all, or a newest row older than
five hours puts the bill beside the capped ones, so fallthrough passes it
over and `--provider` refuses it by name; a `GET` that fails writes nothing,
names itself in the result's `meter_faults`, and the rows already there
decide; `--explain` and `--dry-run` send nothing and read the rows alone. A
`meter:` without a `meter_env:` reads, and caps the bill at that step naming
the missing field, because a reinstall never rewrites this file in your
home. The Baseten registry entry pins `deepseek-ai/DeepSeek-V4-Pro-0813`.
`max_tokens` bounds generated reasoning and the final answer together;
exhausting it does not establish that the review subject was too large.
The shipped entries give each reviewer 65536, well under each model's
documented output ceiling. At 16384, `kimi-k3` spent the whole budget
reasoning on a 35k-token prompt and sent no answer (sd:1805); K3 always
thinks, and its effort can only drop to `low`. A stop at the ceiling reads
`<name> hit max_tokens (N) and it sent no answer`, with the completion
tokens and reasoning bytes, and `sd-ship` repeats that detail in its
refusal. A `length` stop below the ceiling says the context window may be
full and names shortening the review input first. The installer never rewrites the registry in your home, so a
home copy still at 16384 keeps the old ceiling until you edit it.
URL entries can declare one optional control: `thinking: disabled|adaptive`
or `reasoning_effort: none|low|high|max`. The client sends `thinking` as
`{"type": "disabled"}` or `{"type": "adaptive"}`, and effort as a top-level
string. Both registry readers validate and preserve these fields; omission
retains the endpoint default. These values require support from the selected
model: MiniMax-M3 supports disabled thinking, and Baseten's DeepSeek-V4-Pro-0813
supports effort `none`. Lower reasoning can change finding quality; full
subject coverage and the required reviewer count remain mandatory.
A URL entry can also declare `response_format: json_schema`. `sd-review`
then sends the findings schema as a strict `response_format`, in the copy
Moonshot's strict mode takes: every property typed, `line` as `anyOf`
integer or null, and no `minLength` or `maxItems`. The answer is still parsed
against the full schema. Only an entry that declares the field sends it; an
endpoint that accepts it may ignore it, as MiniMax-M3 does (sd:1827).
Incomplete output still fails the review. A pin is changed by editing the
registry file, never by a page.
A `url` answer that fails the findings schema is retried once on the same
entry only when its `price` names both `in` and `out` as zero, so a retry
never doubles a bill; the failed attempt stays in the outcomes with any
blocker it recovered. A priced entry falls through to the next reviewer as
before. Temperature is not a registry field: `kimi-k3` refuses any value but
1, and MiniMax-M3 at 0.2 broke the schema as often as at its default (sd:1821).

Adding a provider is an entry; adding money is a bill. Both role lines are
read in order. `author` is picked when an assignment starts and never switched
mid-item; outside the runner, `--author` names it to
`sd-ship`, which stamps it on each commit it makes as `Authored-with:
<name>/<vendor>`, the vendor as the registry gave it at commit time.
`SD_AUTHOR=<name>` names it to the pack's `commit-msg` hook, which writes the
same line on a commit whose message states none (sd:1295); a name nothing
resolves refuses the commit, and `sd attribute` never amends. `make hooks`
arms the pack's own clone, and `sd commit-hook` arms any other (sd:2546). Its own
repair commit says `SD_AUTHOR`'s entry too, else `claude` under `CLAUDECODE=1`
while the registry gives `claude` the vendor `anthropic` (another vendor
refuses and asks for `SD_AUTHOR`), else `human` (sd:2009, sd:2689). Both
places take `<name>/<vendor>` as well when the registry gives `<name>` that
vendor. `human` is a
commit a person wrote; `script` is one a deterministic job wrote, with no
model and no person in the loop (sd:1637). Both are reserved and carry no
vendor, so any provider may review them. The
review reads no declaration: every commit in the reviewed range is attributed
by its own trailer, or by an `Attributes: <sha> <name>/<vendor>` trailer on a
later commit in the range that `sd attribute` makes, and a commit with neither
refuses the review by name rather than being guessed. A Dependabot commit is
the one exception: its author `dependabot[bot]` with that account's noreply
address, and its committer `GitHub <noreply@github.com>`, read as
`dependabot/github`, a reserved value like `human` and no registry entry.
The pair is a claim, as a trailer is, and a local rewrite names another
committer, so the commit says nothing again until `sd attribute <sha>
dependabot` records it. `sd-ship merge` carries
into the squash each `Attributes:` line that names a commit the base already
holds, so a repair of landed history survives the merge. `reviewer` is the first entry that is enabled, is of no vendor the
range's trailers carry, is on no bill at its cap this month, and answers
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
The reserved `sd` namespace declares four settings:

- `sd.external_reviews`: `configured` permits private code and scoped review context to eligible configured providers.
  It includes future registry entries; registry configuration chooses capability, while this explicit operator grant authorizes transmission.
  `deny` vetoes all local allowances. Absence supplies no standing grant.
- `sd.assistant_merge`: `controlled` means merge without asking the operator, for active, in-scope PR work in repositories the user controls.
  The merge goes only through `sd-ship prepare` then `sd-ship merge`; the review lane and required CI are part of those gates.
  `controlled` never permits a merge that skips the review lane, such as a raw `gh pr merge` or a web squash.
  A refusal from `sd-ship` is a stop, not a reason to merge another way.
  When the value is `controlled` and the gates pass, merge; asking the operator "may I merge?" is wrong.
  An explicit instruction to wait wins. `ask`, or absence, means ask the operator first.
  `sd config` validates and stores the value; the assistant reads it, and `sd-ship` does not.
  It was `sd.merge_authorization` until 1.1.0, which still reads that name; 1.2.0 stops.
  It is the assistant's grant, where `repo.runner_merge` in the one database is the runner's.
  Shared contributors do not revoke permission, but the current sole-operator ownership gate may still refuse execution.
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
  Absence reads the deprecated `fleet.owners` list in the machine config, then the pack's default pair. It grants nothing.
- `sd.gate_cache_gb`: the most gigabytes the local gate's warm Rust build folders may hold; `0` is no bound.
  Absence reads 40. `SD_GATE_CACHE_GB` overrides it for one run. It grants nothing.
- `sd.lane_root`: the folder that holds each repository's `sd-ship lane` queue, as `<root>/<repository>/lane/queue/`.
  Absence reads `$XDG_STATE_HOME/sd/lanes`. `SD_LANE_ROOT` overrides it. It grants nothing.

Installation supplies neither grant. A new operator must state their own policy; never copy another user's personal permission.
These settings start no background work, enable no runner policy, and bypass no ownership, review, CI, or protection gate.
Review depth, author exclusions, spending limits, and the review table's automatic pass caps remain unchanged.
The additional-review request still needs its separate explicit authorization when the automatic cap is spent.
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
