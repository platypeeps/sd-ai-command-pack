# Workflow

How the pack expects to be used. One person does most of the work. Other
people see pull requests and merged commits, and nothing else the pack makes.
Every default below serves that person. Anything that would show a personal
process to someone else is off unless this file says otherwise.

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

**Development.** Pick the item. The loop writes the prd and design when the
change earns them, implements, tests, reviews, pushes, and merges where you
have allowed it. A repository merges unattended only when you set `merge: auto`
on its row, once, from the dashboard, and only while the remote still answers
that the repository is yours alone, asked again at every merge; there you
review the result on the item
screen after it lands, and revert is one action. This unattended runner rule
is separate from the assistant's active task permission under **Standing authorization**.
Without either applicable authority, stop at pull-request-ready.

The loop asks no questions while it runs. Where it would have asked, it decides,
records the choice on the item as a proposal, and continues. You veto after. It
stops, and marks the item `blocked` with the reason, on a failing test, a
blocking review finding still open once the review cap is spent, or a write
outside the repository.

## Defaults

These run without being asked.

- `sd-status` reports. It never writes.
- `sd-review --scope branch --challenge` runs on the machine before a push.
  Blocking findings are fixed or recorded before the branch leaves.
- CI runs on the pull request. The merge waits for CI and nothing else.
- `sd-ship` commits enumerated paths, pushes, opens the pull request, waits
  for CI once in the background, merges with an explicit title and body
  whose trailer names the item, and runs `git fetch -p`. The repository
  setting `delete_branch_on_merge` removes
  the remote branch.
- The default branch is protected: pull requests only, CI required, branches
  up to date before they merge, no required approvals. `sd-status` reports
  it, the dashboard sets it in one
  action on a repository you own, and an unattended merge into a branch
  that is not refuses naming the setting.
- `make check` runs `sd-docs-lint` rules 1 to 4 whenever `docs/work/` exists.
- A commit to the pack, the system repository or the writing repository names
  what needed it: `Needed-by: <item id>` or `Needed-by: cost | efficiency |
  visibility`. `sd-ship` warns when the trailer is missing and ships anyway.
  The weekly count of missing trailers is on the dashboard.

## Opt-in

These run only when asked by name.

- A work item under `docs/work/<date>-<slug>/prd.md`. Create one when the
  work spans more than one session or more than about 300 changed lines.
  `design.md` and `implement.md` exist only when you ask for them. Status lives
  on the item's row and nowhere in the file; a checkout or CI runner with no
  database asks git whether the item is delivered, by the merge trailers, and
  nothing else once the line has retired. `ready_to_send` marks a finished
  artifact waiting on you.
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
| Development | Code, before merge | Defects a second reader finds | 1, plus one verification of the fix |

The code pass reads a head. A fix that changes it gets one verification pass
over the diff since the reviewed head, the last automatic pass on that pull
request; `sd-ship` pushes only the reviewed head or a verified fix of it,
and merges naming that head with `gh pr merge --squash --match-head-commit <the
reviewed sha>` — equivalently `PUT /repos/{owner}/{repo}/pulls/{n}/merge`
with `sha=` — so a head that moved after the review is refused at GitHub with
a 405. The flag is what does the refusing: a merge that carries only a title
and a body refuses nothing, whatever head moved under it.

The reviewer is a different vendor from the author, always. Skills name the
roles `author` and `reviewer`; the provider registry below maps them.

The code point is an experiment: over ten pull requests, findings accepted
against findings rejected with each accepted finding's severity, and cost
logged per pass. The experiment ends in a report on the item, and you
decide whether the point stays; no ratio decides for you.

## Advisory

- Copilot review. In an organisation or shared repository GitHub requests it on
  its own when the pull request opens. Its findings are read and dispositioned.
  They never block a merge and the pack never requests a second round. On a
  repository you pay for personally it is off.

## Never in a shared repository

A shared repository is one where someone else also merges. In it:

- No `Work:` line in a pull request body unless the pull request resolves a
  work item that lives in that repository.
- No `docs/work/`, `docs/spec/`, or `docs/decisions/` commits. `mode: guest`
  already carries this: planning artifacts go to the fork's integration branch,
  and every writing skill refuses the upstream tree.
- No labels, review comments, reviewer requests, or bot posts from any pack
  surface. `sd-review` and `sd-receive-review` never post.
- No workflow files or repository settings unless the owner of that
  repository asked for them.
- No merge without task-specific or standing operator permission. Shared contributors
  do not revoke that permission. Existing ownership and protection gates still
  decide whether the pack can execute it; a refusal remains a stop.
- No issue filed. `sd-suggest` writes a row everywhere; `sd suggest publish`
  files one when you run it, to the destination you name with `--to`.

## The path for a change

Small change: branch, commit, `sd-review`, push, pull request, CI, merge.
Eight commands, one local review, no artifacts.

Change that earns a work item: `sd-plan` writes `prd.md` using the requirements
already available and asks only for missing decisions. Then the small-change
path runs with the applicable review points. An item can span several pull
requests. `Item: <item>` associates a merge without closing the item;
`Delivers: <item>` declares the delivering merge. Changes without an associated
item omit those trailers and create no placeholder record.

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

## Modes

`CLAUDE.local.md` carries one `mode:` line per repository. The installer writes
the block; the file is untracked by construction.

| Mode | Where planning artifacts go | What ships |
|---|---|---|
| `full` | `docs/work/` in the repository | everything above; merge only with `merge: auto` on the row |
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
same branch offered upstream is refused. Mode never decides merging.
`merge: auto` is a per-repository policy you set once on the dashboard, off by
default, and nothing derives it. It is necessary, not sufficient: every merge
asks the same three questions again, one function for both gates, and a no
suspends it with the reason shown.

## Providers

One file, read by the library, maps roles to providers. Skills name roles and
never vendors.

Standard and deep changes require two completed reviews. Cheap changes require
one; skip requires none. Planning and challenged reviews retain their existing
minimum of one review. Tier selection still follows repository policy.

    bills:
      anthropic: { cost: subscription }
      openai:    { cost: subscription }
      moonshot:  { cost: prepaid }
      minimax:   { cost: plan, meter: "https://www.minimax.io/v1/token_plan/remains" }
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
      exo:     { url: "http://localhost:52415/v1", model: "<pinned>", vendor: local, bill: local,
                 roles: [author, reviewer], enabled: false, reason: "model not pinned" }
      # Shipped disabled: the local model is not pinned. A disabled entry
      # never resolves.
    roles:
      author:   [claude, codex]
      reviewer: [codex, claude, minimax, kimi, baseten, exo]

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
2026-09-05. The meter writes those two percents as `meter` rows, Today
shows them beside the bill, a `plan` bill reserves no dollars, and
fallthrough skips it while either window reads zero; the two Baseten tools
pin
DeepSeek V4 Pro, whose 0813 build is the cheapest of Baseten's frontier
reviewers. `max_tokens` bounds generated reasoning and the final answer together;
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
range's trailers carry, has budget left on its bill, and answers its preflight. A rate limit,
a missing binary, a failed run or a timeout falls through to the next, and the
run says which one reviewed and why the earlier ones did not. With none left,
the review refuses by name rather than reading its own work.
MiniMax and Kimi can replace each other in either configured order when an
attempt fails to complete. The chain continues until the required count completes
or eligible entries run out. Neither provider has a reserved slot. A completed
review with findings counts; it does not trigger a replacement. Consent, author
exclusions and spending limits apply to every fallback, and earlier findings remain.
`vendor` is the
maker of the model, not the tool; `bill` is whose money. A bill with
`cap_usd_month` is enforced per call: the library reserves each call's bound,
prompt plus `max_tokens` at the entry's price, against the month's settled and
reserved rows in one transaction, refuses the call when the bound would pass
the cap, and skips that bill in fallthrough for the rest of the month; a
direct pick of it refuses with the month's total. Entries with
`url` share one OpenAI-compatible client and one reader. This file is
identity and seed; enabled, order and caps are rows the dashboard edits, and
the library merges file and rows on every read.

`sd-review --provider <name>` picks one entry for one run. The dashboard's
item screen offers the same list, with vendor, cost and reason beside each
name. Copilot and Greptile are not entries: they post on the pull request, and
this lane never posts.

This file is the only list of providers. `sd-review` reads it through the
library. `.github/sd-review.json` carries repository policy, paths and severity;
it names no provider chain. Effective authorization restricts the registry's
reviewer chain before vendor, transport, availability and spending gates run.

## Standing authorization

Core settings use `sd config get|set|unset|list` and the existing atomic machine configuration writer.
The file is `~/.config/sd-ai-command-pack/config.json`, honoring `XDG_CONFIG_HOME`.
The reserved `sd` namespace declares two settings:

- `sd.external_reviews`: `configured` permits private code and scoped review context to eligible configured providers.
  It includes future registry entries; registry configuration chooses capability, while this explicit operator grant authorizes transmission.
  `deny` vetoes all local allowances. Absence supplies no standing grant.
- `sd.merge_authorization`: `controlled` permits assistant merges for active, in-scope PR work in repositories the user controls.
  An explicit instruction to wait wins. `ask`, or absence, requires task-specific permission.
  Shared contributors do not revoke permission, but the current sole-operator ownership gate may still refuse execution.

Installation supplies neither grant. A new operator must state their own policy; never copy another user's personal permission.
These settings start no background work, enable no runner policy, and bypass no ownership, review, CI, or protection gate.
Review depth, author exclusions, spending limits, and the review table's automatic pass caps remain unchanged.
The additional-review request still needs its separate explicit authorization when the automatic cap is spent.
The upstream Trellis PR exception still requires permission for that specific PR.

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
