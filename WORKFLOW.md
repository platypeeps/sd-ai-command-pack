# Workflow

How the pack expects to be used. One person does most of the work. Other
people see pull requests and merged commits, and nothing else the pack makes.
Every default below serves that person. Anything that would show a personal
process to someone else is off unless this file says otherwise.

For this maintainer's reviewer, writing, and diagram preferences, read the
sd-ai-command-pack checkout's [.claude/rules/sd-operator-defaults.md](.claude/rules/sd-operator-defaults.md).
Those instructions do not change executable gates or another operator's permissions.

## Available controls

`sd task` and the dashboard create and update ordinary tasks directly in the
database, without a Git checkout, PRD or GitHub issue. `sd today` and `sd store
items` use the same queries as Today and Backlog. Completion of an ordinary
task is independent of code delivery. `sd work deliver` verifies delivery
evidence; `sd work cancel --reason` records a cancellation without waiting for
another merge. Artifact relinking preserves the item's identity and history.

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

- `sd-status` reports. It never writes.
- `sd-review --scope branch --challenge` runs on the machine before a push.
  Blocking findings are fixed or recorded before the branch leaves.
- CI runs on the pull request.
  Wait for required checks on the exact head; preserve review, ownership, protection, and authorization gates.
- `sd-ship` commits enumerated paths, pushes, opens the pull request, waits
  for CI once in the background, merges with an explicit title and body
  whose trailer names the item, and runs `git fetch -p`. The repository
  setting `delete_branch_on_merge` removes
  the remote branch.
  After each confirmed in-scope merge, the agent follows the ship skill's post-merge closeout procedure.
  It dispositions remaining findings and inventories refs, branches, stashes, and worktrees.
  Local deletion needs separate, consolidated approval for exact targets with verified recovery evidence.
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
  it read.
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

The code pass reads a head. A fix that changes it gets a further verification
pass over the diff since the reviewed head, up to the cap above; `sd-ship`
pushes only the reviewed head or a verified fix of it, and merges naming that
head with `gh pr merge --squash --match-head-commit <the reviewed sha>` —
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

A shared repository resolves to `guest` or `minimal` mode.
`full` requires administration, a non-fork remote, and exclusive push access.
In a shared repository:

- No `Work:` line in a pull request body unless the pull request resolves a
  work item that lives in that repository.
- No `docs/work/`, `docs/spec/`, or `docs/decisions/` commits. `mode: guest`
  already carries this: planning artifacts go to the fork's integration branch.
  Two machines enforce that refusal. `sd-review --scope planning` calls
  `sd_lib.guest_artifact_refusal`, which resolves the mode and names refused
  paths. `sd-plan` uses that review before promotion. `sd-ship` separately
  checks the same three path prefixes before a guest push.
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
  `sd-ship`, which never consults `sd.assistant_merge`. Existing ownership and protection gates still
  decide whether the pack can execute it; a refusal remains a stop.
- No issue filed. `sd-suggest` writes a row everywhere; `sd suggest publish`
  files one when you run it, to the destination you name with `--to`.

## The path for a change

Small change: branch, commit, local review, push, pull request, CI, merge.
Use the ship workflow without inventing a planning artifact.

Change that earns a work item: `sd-plan` writes `prd.md` using the requirements
already available and asks only for missing decisions. Then the small-change
path runs with the applicable review points. An item can span several pull
requests. `Item: <item>` associates a merge without closing the item;
`Delivers: <item>` declares the delivering merge. Changes without an associated
item omit those trailers and create no placeholder record. The trailers are the
last paragraph of the pull-request body, contiguous, with the attribution
paragraph above them and nothing below: a squash merge concatenates the body
into the commit message, git reads trailers only out of the final paragraph,
and GitHub's appended `Co-authored-by:` joins a trailer block that ends the
message but opens a new paragraph after anything else.
`.github/PULL_REQUEST_TEMPLATE.md` ends in that order.

After the remote confirms the delivering merge, `sd work deliver <row-id>
<full-commit-sha>` verifies the commit, default branch and delivery trailer. It
records completion and the shipment time together. Repeating that operation
preserves the original receipt. A missing trailer or unavailable remote leaves
the claim unverified and reports the missing evidence; a bare merged branch or
stale issue status cannot close the item.

`sd work cancel <row-id> --reason TEXT` records cancellation immediately,
without a status-file change or another pull request. It does not claim the
work shipped. A later associated merge may carry `Closes: <item>` for context;
that merge is not a prerequisite for database completion. Readers with no
database can use explicit `Delivers:` or `Closes:` evidence to see that work is
closed, while only `Delivers:` says it shipped. A shallow clone that cannot
establish the evidence reports uncertainty.

The item directory stays in place. Use `sd work relink <row-id> <path>` when an
artifact moves: it preserves the row, notes and original source identity. No
command automatically deletes or archives a completed item directory.

## Parallel work

The harness fans work out only when a `CLAUDE.md` or a skill asks for it.
These rules say when to ask. They hold wherever a pack skill runs. A skill
that dispatches workers cites this section and restates nothing.

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
| `minimal` | nowhere; no work items | the small-change path only |
| `guest` | the fork's integration branch | the small-change path to pull-request-ready; no posts, no labels |

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
`sd-db.sh repo runner-merge <path> auto`, off by default, and nothing derives it. It is necessary, not sufficient: every merge
asks the same three questions again, one function for both gates, and a no
suspends it with the reason shown.

## Providers

The provider registry maps roles to providers.
Reusable skill procedures name roles; operator policy owns preferred entries.

Cheap, standard, and deep changes require one completed independent local review.
Skip requires none; planning and challenged reviews retain their minimum of one.
Tier selection still follows repository policy, without adding automatic local reviewers.
Complete local review before any Copilot request.
The machine's `sd.copilot_review` selects remote review during shipping: `deep` (unset reads `deep`), `always` or `never`.
A repository's `copilot_review.automatic_deep` overrides it when the file names the key; a file that does not name it inherits.
`sd-review --explain` names the effective policy and whether the repository, the machine config, or the machine default answered.
Automatic review runs once per pull request after the local review and acknowledgement step.
Later pushes still require exact-head local review and CI.
A completed Copilot review must cover the exact merge head.
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
      kimi:    { url: "https://api.moonshot.ai/v1", model: kimi-k3, vendor: moonshot, bill: moonshot,
                 roles: [reviewer], max_tokens: 16384, price: { in: 3.00, out: 15.00 } }
      minimax: { url: "https://api.minimax.io/v1", model: MiniMax-M3, vendor: minimax, bill: minimax,
                 roles: [reviewer], max_tokens: 16384, price: { in: 0, out: 0 } }
      baseten: { url: "https://inference.baseten.co/v1", model: deepseek-ai/DeepSeek-V4-Pro-0813, vendor: deepseek,
                 bill: baseten, roles: [reviewer], max_tokens: 16384, price: { in: 1.32, out: 3.96 } }
    roles:
      author:   [claude, codex]
      reviewer: [codex, claude]

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
URL entries can declare one optional control: `thinking: disabled|adaptive`
or `reasoning_effort: none|low|high|max`. The client sends `thinking` as
`{"type": "disabled"}` or `{"type": "adaptive"}`, and effort as a top-level
string. Both registry readers validate and preserve these fields; omission
retains the endpoint default. These values require support from the selected
model: MiniMax-M3 supports disabled thinking, and Baseten's DeepSeek-V4-Pro-0813
supports effort `none`. Lower reasoning can change finding quality; full
subject coverage and the required reviewer count remain mandatory.
Incomplete output still fails the review. A pin is changed by editing the
registry file, never by a page.

Adding a provider is an entry; adding money is a bill. Both role lines are
read in order. `author` is picked when an assignment starts and never switched
mid-item; outside the runner, `SD_AUTHOR` or `--author` names it to
`sd-ship`, which stamps it on each commit it makes as `Authored-with:
<name>/<vendor>`, the vendor as the registry gave it at commit time. The
review reads no declaration: every commit in the reviewed range is attributed
by its own trailer, or by an `Attributes: <sha> <name>/<vendor>` trailer on a
later commit in the range that `sd attribute` makes, and a commit with neither
refuses the review by name rather than being guessed. `reviewer` is the first entry that is enabled, is of no vendor the
range's trailers carry, is on no bill at its cap this month, and answers
its preflight (the cap check is below). A rate limit,
a missing binary, a failed run or a timeout falls through to the next, and the
run says which one reviewed and why the earlier ones did not. With none left,
the review refuses by name rather than reading its own work.
Only entries on the reviewer order participate in automatic fallback.
Enabled reviewer-capable entries outside that order require an explicit `--provider` selection.
The shipped order contains Codex, then Claude; other providers remain explicit-only.
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
The reserved `sd` namespace declares three settings:

- `sd.external_reviews`: `configured` permits private code and scoped review context to eligible configured providers.
  It includes future registry entries; registry configuration chooses capability, while this explicit operator grant authorizes transmission.
  `deny` vetoes all local allowances. Absence supplies no standing grant.
- `sd.assistant_merge`: `controlled` permits assistant merges for active, in-scope PR work in repositories the user controls.
  An explicit instruction to wait wins. `ask`, or absence, requires task-specific permission.
  `sd config` validates and stores the value; the assistant reads it, and `sd-ship` does not.
  It was `sd.merge_authorization` until 1.1.0, which still reads that name; 1.2.0 stops.
  It is the assistant's grant, where `repo.runner_merge` in the one database is the runner's.
  Shared contributors do not revoke permission, but the current sole-operator ownership gate may still refuse execution.
- `sd.copilot_review`: when `sd-ship` requests a Copilot review by itself. `deep` requests one on deep-tier changes only,
  `always` on every reviewing tier, `never` on none. Absence reads `deep`, so a repository with no
  `.github/sd-review.json` gets Copilot on deep changes and on nothing else.
  A repository file that names `copilot_review.automatic_deep` overrides it; one that does not inherits.
  `sd-review` reports the effective policy, its source and the repository's say under `remote_reviews.copilot`.
  `sd-ship` resolves the decision again at dispatch, from the setting as it stands then and the tiers the
  retained passes recorded, so a setting changed after the review takes effect without another review.

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
