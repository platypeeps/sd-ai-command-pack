---
title: the pack runs a team process for a repository with one person in it
status: planning
created: 2026-09-05
---

# PRD — the process outgrew the person it serves

## Problem

The pack's contracts were written one gate at a time, each one answering a real
defect. Nothing ever asked what they cost together, and the answer turned out to
be most of the working day.

Measured across the last eight days, three repositories, sixty-nine sessions and
17,821 tool calls:

| Where the time went | Calls | Wall time |
|---|---|---|
| Hand-rolled polling loops waiting on GitHub | 417 | 770 min |
| All `gh` invocations | 3,172 | 1,100 min |
| Test runs (`make check` 599, `unittest` 786, `pytest` 331) | 1,876 | 898 min |
| Local review lane | 377 | 61 min |
| Status reporting | 228 | 23 min |

Ninety-eight pull requests opened and 102 merged in eight days, by one person.

The pack's own history is the sharpest example. One 291-line skill file drew
eight adversarial review rounds and 45 findings across a single evening,
producing an 855-line `prd.md`. Roughly a third of those findings were genuine
behavioural improvements; roughly a third were the same value stated in three
artifacts and drifting between them; roughly a quarter were defects introduced
by the previous round's own fix.

Four signals say the process serves nobody:

- **The framework gets the work, not the work.** In the same eight days the
  operator's own commits split 327 to 62: pack 244, system 48, writing pack 35,
  against 55 in `mezmo-world-simulator` and about seven in `mcp-research`. Those
  two repositories are the stated priority. Five commits on the tool for every
  one on the thing the tool is for.
- **Nobody reads the artifacts.** `docs/work/archive/` holds 487 items. A full
  enumeration of the git history, replacing an earlier sample of fifteen, shows
  386 arrived already `done` in one import commit (`46ec7fb85`) and were never
  active here; the other 100 were bulk-parked in one commit (`5278b0d28`). Five
  items in the whole history were ever touched by more than two commits, and
  four of those are open today. The archive is an import, not a record.
- **Skill usage cannot be measured, in either direction.** Three counts over
  identical eight-day data give six skills, thirteen, and eighty-one. No surface
  records "this skill's instructions governed this turn". Every "unused" claim
  in the audit that opened this item was unfalsifiable, and the twelve-of-82
  figure it carried is withdrawn. What the count did show is a second surface:
  270 Codex sessions against 2,487 Claude Code transcripts, with `sd-red-team`
  and the six `sd-rust-*` skills living almost entirely on Codex.
- **Finished work does not leave.** Four blog pieces at `ready` since
  mid-August, zero published. Six `mcp-research` handoff drafts written on
  2026-09-03, none filed. The operator's own account of the stall: not perfect
  yet, another pass first. A framework that can always run one more pass has no
  end state.

The rules that fail are the ones written as prose. The global "never `cd`,
always absolute paths" rule is contradicted by 9,455 of 16,033 Bash calls in the
sample window, by the same agents that read it every session.

## Why the obvious fix is wrong

**Not "delete the skills".** Skills cost nothing at rest; they render once at
install and sit in a catalog until named. What costs is the *mandatory path*:
the gates that run whether or not the change needs them. Cutting sixty skills
would remove capability the owner might want next month and would not save a
single one of the 770 polling minutes. And the usage evidence for any cut does
not exist. The skills stay; what changes is which of them install, and how that
is decided.

**Not "remove the gates".** The adversarial review lane is the single measured
win in the pack's history: it took one branch from fifteen remote review rounds
down to three, and seven passes on `mezmo-world-simulator` found real defects
each time. What is wrong is not that reviews exist; it is that they have no
cap, so a finished artifact can always be reviewed once more instead of sent.

**Not a new abstraction.** The pack already carries three review lanes, three
repository modes, a routing policy, a plugin registry and a fleet dashboard.
Another layer to decide when the other layers apply is the disease, not the
cure. What is missing is one page saying which defaults hold, one place that
holds state, and the existing knobs wired to both.

**Not "make everything opt-in".** A default nobody sets is a gate nobody runs.
The distinction that matters is *who sees the output*: a gate that runs on the
owner's machine and prints to the owner's screen is cheap and stays on by
default; a gate that writes to a shared repository, posts to a pull request, or
blocks a merge is expensive and turns off unless the work earns it.

**Not a bigger command line.** The operator is visual and forgets commands and
their options. Every prior fix added a command. The 82 skill names are a memory
load, which is one reason they go unused. The front door has to be a screen that
shows what is possible; the command line is the agent's surface, not the
operator's.

## What this changes

One page, `WORKFLOW.md`, states the pack's policy for a repository with one
person in it, and the pack's surfaces are brought into line with it. The policy
in one sentence: **anything the pack does should help the person running it,
without exposing or imposing that person's process on anyone else.**

The page describes two flows on one spine. The **research flow** runs sources,
understanding, brief, decisions, handoff or publish; the operator sits at the
end, and external publish is the only gate. The **development flow** runs prd,
design, implement, test, review, push, merge; in a repository the operator owns
it runs without a gate and the operator reviews the result after it lands. The
spine both flows share is the **item**: one row in a local database, one screen
on a dashboard, and the artifacts in git that the row points at.

That spine is not built here. This item was opened as one piece of work and,
after a second interview on 2026-09-05, became three:

- **A — this item, the pack.** Policy, the tiered ship path, review points and
  caps, the vendor rule and the provider registry, which skills install and how
  they are promoted, the filing skill, the handoff skill. Everything that
  describes behaviour or ships in the payload.
- **B — the system repository.** The database at `~/.local/share/sd/sd.db`,
  the one library that owns its schema and every write, the runner that turns
  an assignment into a session, the dashboard as the operator's front door with
  five sections, the migrations that fill it, the vault crons stopped, and the
  terminal-multiplexer wrapper. Everything that runs on the machine.
- **C — the writing repository.** A stub: ideas and pieces move into the
  database after B's library exists. Nothing else until one piece publishes.

B's library lands first, because requirements 5, 10, 11 and 12 below write to
it. Requirements 1 through 4 and 6 through 9 need nothing from B and land in any
order.

Decisions taken in the two interviews are the requirements below.

### Requirement 1 — the policy page exists and is discoverable

`WORKFLOW.md` at the repository root states, for a consuming repository: the two
flows and the spine they share; what runs by default, what is opt-in, what is
advisory, what never touches a shared repository; the review table with its
caps; the path for a change at each size; and the modes and how they resolve.
`sd-help` names it. The `CLAUDE.local.md` block the installer writes links to it.

The block carries the keys the pack already reads and no others: `mode:`, plus
the entrypoint names `check:`, `test:` and `lint:` from `CHECK_NAMES`
(`bin/sd_lib.py:36`, consumed at `:391-412`). Every opt-in lane is asked for by
name in the moment. A key that turns a lane on permanently is a default in
disguise: it converts a decision about one change into a decision about the
repository, taken once and unrecorded.

### Requirement 2 — the ship path is tiered, and it can run unattended

Today `sd-ship` applies eleven steps to a one-line fix. After this item the
default path is: commit enumerated paths, local review, push, open the pull
request, wait for CI once, merge, `git fetch -p`.

- `sd-spec` leaves the default path. It runs when a change alters behaviour that
  `docs/spec/` documents, and the operator asks for it.
- Step 11's remote-branch deletion is replaced by the repository setting
  `delete_branch_on_merge`. The step shrinks to the local report.
- The settle loop is one background wait on CI, not a shell loop. The 417
  hand-rolled polling loops in the measurement window, forty of which hit a tool
  timeout and were reissued, are the thing being removed.
- The 70 lines of pull-request history in the skill file (the `#718` and `#720`
  narratives) collapse to one paragraph stating the resulting rule.
- The path merges on its own when tests, review and CI pass, and reports, only
  in a repository whose row in the database carries `merge: auto`. The operator
  sets that once per repository from the dashboard; the default is off, and no
  detection sets it. Everywhere else the path stops at pull-request-ready. Mode
  decides where artifacts go; the merge policy decides whether the loop merges,
  and the two are separate because remote ownership can suggest the first and
  cannot authorize the second.
- Nothing on the path asks a question mid-run. Where a skill would ask today, it
  decides, records the choice on the item as a proposal, and continues. The
  operator vetoes after, not before. A test failure, a blocking review finding
  left open once the review cap is spent, or a write outside the repository
  stops the run and marks the item `blocked` with the reason.
- Every commit to the pack, the system repository or the writing repository
  names what needed it: a `Needed-by:` trailer carrying an item id or one of the
  three lanes `cost`, `efficiency`, `visibility`. `sd-ship` warns when it is
  missing and ships anyway. The weekly count of missing trailers is a number the
  dashboard shows. This is the guard against the 327-to-62 split, chosen soft
  because the operator asked for framework work to continue in those lanes.

### Requirement 3 — review points, caps, and the vendor rule

Three lanes review the same planning artifacts today: a host lane in the
contract, `sd-review --scope planning`, and a hand-launched background task
named in `AGENTS.md`. Two of them are the same external model reading the same
files. None of them has a cap.

After this item, adversarial review happens at four named points, each with a
cap, and nowhere else unless the operator asks by name:

| Flow | Point | What it checks | Cap |
|---|---|---|---|
| Research | After the brief and decisions | Claims against sources, gaps, wrong calls | 2 |
| Research | Final product, before the send box | The piece, page or ticket as a reader sees it | 1 |
| Development | prd and design | Scope, missing requirements, wrong assumptions | 1 |
| Development | Code, before merge | Defects a second reader finds | 1 |

The cap bounds automatic passes, not the disposition of what they find. When a
point's passes are spent, no further pass starts on its own; the artifact moves
on only once every blocking finding is dispositioned, addressed or rebutted with
evidence recorded on the item. A blocking finding still open past the cap marks
the item `blocked`, and the operator decides. Non-blocking findings never hold
an artifact. A further pass needs the operator to ask for it by name, and the
item records that it was asked for. This is the fix for "not perfect yet,
another pass first": the review ends; the findings do not vanish.

**The reviewer is a different vendor from the author, by policy.** Today Claude
writes and Codex reviews. If the primary moves to OpenCode or a local model, the
pair changes and the rule holds. The pack's skills name *roles*, `author` and
`reviewer`, never vendors. A **provider registry**, one config file read by B's
library, maps each role to a provider: name, how to start it, which roles it
may fill, cost basis. Adding exo, another commercial API, or a second local
model is an entry, not code. The registry's format and the role vocabulary are
defined in this item; the file lives with the database.

The registry is static and the author is not. `author` is a list too,
`[claude, codex]`, read in order when an assignment starts and never switched
mid-item: a Claude outage sends the next assignment to Codex, not the one in
flight. Whichever provider authored, a single-name `reviewer` line would
resolve to the vendor that wrote the code. So resolution takes the author into
account: the reviewer is the first entry on the `reviewer` list whose vendor
is not the author's, and the library refuses by name when none differs. The
assignment row names the author, so the runner and `sd-review` both know.

One list of providers on the machine. `bin/sd-review` carries its own table,
`BACKENDS` at `bin/sd-review:195`, and `.github/sd-review.json` names providers
again under `challenge_providers` and `planning_providers`. Both go. The
registry entry holds what the table held: the start line, and the reader for
the provider's output. `sd-review.json` keeps what is repository policy and
nothing about vendors: tiers, categories, paths, `sensitive`, the severity
floor. Tier lists keep naming providers by registry name; the names are
validated against the registry where one exists, and pass as strings in CI.

**Fallback is the reviewer list, read in order, and the order follows the
bill.** Every entry names a `bill:`, and the registry's `bills:` section says
whose money it is: `subscription` for Codex and Claude, `prepaid` for the
Moonshot and MiniMax balances the operator has already paid, `company` for
Baseten, `local` for exo. The `reviewer` line runs subscription first, prepaid
next, company last: `[codex, kimi, minimax, prism, gito, exo]`, with `prism`
and `gito` re-pointed from OpenRouter to Baseten. The first entry that is
enabled, carries the role, is not the author's vendor, has budget left on its
bill, and passes its preflight reviews. A rate limit, a missing binary,
failed authentication, a non-zero exit and a timeout each fall through to the
next, and the run records which provider reviewed and why the earlier ones
did not, on the assignment row and in the JSON it emits. Fallthrough happens
on its own, onto prepaid and company bills included; every pass writes a cost
row and Today shows it.

One bill has a cap from day one. `baseten` is company money, and its bill
carries `cap_usd_month: 50`. The library sums cost rows per bill per calendar
month; at the cap, fallthrough skips every provider on that bill, direct
choice refuses by name with the month's total, and Today shows spend against
cap. The dashboard raises the cap in one action, and it enables, disables and
reorders providers the same way: the registry file holds identity and seeds
B's `provider` and `bill` tables, the rows hold what the page changes, and
the library merges the two on every read, so the file is never edited from a
page. No other bill has a cap. An API entry carries `price:` per million
tokens in and out, so a cost row is tokens times price without a billing API;
a subscription entry logs tokens alone.

An entry carries `vendor:`, the maker of the model behind it, and the
different-vendor rule compares vendors, not names or bills. `prism` and `gito`
are tools, not vendors: their vendor is whatever model Baseten serves them,
pinned on the entry. `kimi` is Moonshot, `minimax` is MiniMax, `exo` is
whatever model it serves. Entries carrying a `url:` run through one
OpenAI-compatible client in the library, with `model:` and `max_tokens:` from
the entry and one reader for all of them that takes the answer from
`content`, strips a `<think>` block, and ignores `reasoning_content`. That
client is what makes the prepaid balances usable: `prism` hardcodes 8,192
output tokens and a 120-second deadline, which is why `~/.prism/.env` records
Kimi and MiniMax as disabled there. The `kimi` CLI and `gito` ship disabled
until each has a verified start line and a reader; the Moonshot balance is
reached through the `url:` entry meanwhile. An entry also carries `enabled:`,
with `reason:` when false. Enabling one is a verified start line and a reader,
and the entry flips.

Choosing directly is one flag and one picker. `sd-review --provider <name>`
runs one named provider for one run, validated against the registry, and the
item records the choice. The dashboard's item screen offers the same picker
over the registry table, with vendor, cost, enabled and reason beside each
name. Switching the default is the `reviewer` line. GitHub-side reviewers,
Copilot and Greptile, are not registry entries: they post on the pull request,
which the local lane never does, and they stay advisory under requirement 4.
The local lane runs before every push regardless, so a Copilot outage costs
nothing; the local list is its fallback by construction.

**Code review is an experiment, not yet a rule.** The seven passes already run
on `mezmo-world-simulator` are scored first: findings accepted against findings
rejected, per pass. Then the other vendor reviews the next ten code pull
requests, and cost is logged per pass. Below thirty percent accepted, the code
point leaves the table.

The one lane is `sd-review --scope planning`. The concern ledger, the pre-edit
hash baselines and the per-round cross-artifact sweep apply only to paths listed
under `sensitive` in `.github/sd-review.json`. The codex appendix under `docs/`
and the `AGENTS.md` bullet that mandates the second lane are deleted.

### Requirement 4 — Copilot advises, on the repositories where the organisation pays

Merge blockers are the local review lane and CI. Copilot review is advisory:
GitHub requests it automatically when a pull request opens in an organisation or
shared repository, its findings are read and dispositioned, and it never blocks
a merge. The pack never requests a second round. On repositories the operator
pays for personally it is off. GitHub spend is the one cost line the operator
named as a worry, and this is the part of it the pack controls. The user-global
`PostToolUse` hook that asks for a Copilot review after every push is deleted;
it is not installed by the pack, and it duplicates what GitHub already does.

### Requirement 5 — a work item exists only when it earns one, and its state lives in the database

A work item is created when the work spans more than one session or roughly 300
changed lines. `design.md` and `implement.md` are written when asked for, not by
default. `sd-plan` asks three to five questions before it writes anything, and
in an unattended run it asks none and records its assumptions.

**Git owns the artifacts; the database owns the state.** `prd.md`, `design.md`
and `implement.md` stay in the repository as the decision trail. The item row in
`sd.db` holds status, dates, links and notes, and points at the files by path.
The `status:` line in `prd.md` stays, as a derived mirror the library writes
and nothing else writes: a fresh checkout and a CI runner have no database, and
`make check` runs the documentation lint there. The row carries the item's
branch, and that branch is the mirror's revision identity. Git checks a branch
out in one worktree at a time, so exactly one checkout on this machine holds
the mirror the row describes. The library writes the mirror only in that
checkout; `sd_lib.py` and `sd-docs-lint` compare row and mirror only there,
and fail by name when they disagree. In any other checkout, on `main` after the
merge or in a linked worktree on another branch, and in CI, they read the
mirror alone. A `done` row compares with nothing, and `done` is never written
into a mirror: the transition to `done` deletes the directory, below, so a
mirror carries only the states its branch passed through. `sd-ship` refreshes
the mirror before it commits. Until B's library exists the frontmatter is the
only copy, and the switch is one migration.

The status vocabulary gains one state, `ready_to_send`, for a finished artifact
waiting on the operator's external action, and keeps `blocked`. Nothing else
changes.

No sweep, no park, no archive. A merged item is `done` in the row and its
directory is deleted at the next `sd-plan` run, only when every file in it is
tracked and committed: `git status --porcelain --ignored -- <dir>` empty, so
that ignored files count alongside untracked and modified ones, and every path
under the directory listed by `git ls-files -- <dir>` and present at `HEAD`.
When that holds, the deletion is `git rm -r` of those tracked paths and
nothing else. When it does not, the directory stays and `sd-plan` reports the
untracked, ignored or modified files by name. Git history holds what is
deleted.
`docs/work/archive/` and its 941 files are removed in one commit that names
`46ec7fb85` as the commit that recovers any of them. The 100 parked items go
with the 386 imported ones: a backlog nobody opened in four months is not a
backlog, and B names one surface for later work.

### Requirement 6 — nothing personal reaches a shared repository, and ownership decides

A shared repository is one where somebody else also merges. Ownership decides
the mode; the organisation name does not. `mezmo-world-simulator` sits in the
`answerbook` organisation, has one author, and runs `full` with its triad
pushed and Notion mirrors for its audience. That is intended and stays.

- The `Work:` line appears in a pull request body only when the pull request
  resolves a work item that lives in that repository. The `Work: none - <reason>`
  form is deleted, and rule 5 of the documentation lint becomes conditional on a
  work item existing.
- Planning artifacts stay out of the shared tree through `mode: guest`, which
  already carries this rule across six skills: the triad goes to the fork's
  integration branch (`sd-plan/SKILL.md:105`), `sd-spec` never touches the
  upstream tree (`:41`), `sd-review` refuses outright (`:106`), `sd-ship` posts
  no reviews or labels (`:206`), `sd-deps` does not merge (`:49`), and
  `sd-suggest` files nothing upstream (`:44`). No new mechanism is built.
- A repository the operator does not own resolves to `mode: guest` without an
  explicit line. Today `sd_lib.mode()` reads the local block and falls back to
  `full`, so an unconfigured shared repository gets the most invasive mode by
  default. This is the one piece of requirement 6 that is new code: the fallback
  asks three questions of the remote before returning `full`: the owner is the
  operator, the repository is not a fork, and the operator is its only
  collaborator. Any other answer, and any failure to answer, returns `guest`
  for the artifact question while leaving the merge question to the policy
  above, which is off unless set. A personal fork of a shared upstream and a
  personally owned repository with collaborators both resolve to `guest`. The
  three modes are named in `README.md`, which mentions none of them today.
- `README.md`'s claim that the pack writes "nothing, ever" in a repository is
  rescoped to the installer, which is where it is true. The skills that write
  tracked files by design are named.

### Requirement 7 — the checks that cannot fail are removed or wired up

- `sd-docs-lint` runs in no Makefile target and no workflow. Rules 1 through 4
  move into `make check`, conditional on `docs/work/` existing.
- The 100% coverage floor stays for `bin/sd_install.py`, which writes files under
  the operator's home directory. It is dropped elsewhere.
- The four line-count ceilings print a warning and stop failing the suite. They
  were re-derived five times in five days and cost more in bookkeeping than the
  headroom they defend.
- `make check` gains a fast path over changed files. The full suite runs once
  before a push.
- The `bash32` job builds bash from source to lint the repository's own scripts,
  guarding a premise that stopped being true when shipped shell was deleted. It
  is cut. The `security` job folds into `lint`.
- `tests/test_selector_contract_drift.py` tests a contract its own docstring
  calls retired. `generated/registry-snapshot.json` and the `plugins/sd` stub are
  residue from a deleted architecture. All three are deleted.

### Requirement 8 — the instruction layers stop contradicting each other

- Every mention of Trellis leaves the routing block and the planning contract;
  no such directory exists in this repository. The two `.trellis` allow rules
  leave the global settings.
- The fourteen `Read()` deny globs and the global "never `cd`" rule are dropped
  together. The globs guard build artifacts rather than secrets, and their
  presence is what forces the path-resolution prompts the rule exists to dodge.
  The rule is contradicted by 59% of Bash calls, which is the definition of a
  rule that does not work.
- Four MCP pull-request tools join the permission allowlist. Nine merges in the
  measurement window were blocked by the classifier because the guidance says
  "MCP before `gh`" while only the `gh` form is allowed.
- Dated narrative leaves the governing documents. `CONTRIBUTING.md` is about 45%
  history and the system repository's guide about 36% incident write-ups. Each
  keeps its present-tense rules, plus one sentence where a rule needs its reason.
- The four files stating the planning review rule collapse to one under
  `.claude/rules/`, and that one states the review table from requirement 3.
- The pull-request template points contributors at `docs/SD_AI_COMMAND_PACK.md`,
  which does not exist. Fixed or removed.

### Requirement 9 — one terse-style mechanism

The output style already enforces short sentences everywhere. The caveman plugin
enforces a second, overlapping style through a session hook, and the writing
repository carries an override forbidding it. The plugin is uninstalled and the
override deleted, leaving the output style as the single mechanism.

### Requirement 10 — a skill installs because a path names it, or because it was used

Usage counts cannot decide what stays, because none exist. Cohesion can.

- `skills/paths.json` names three paths and the skills on each: research
  (sources to brief to handoff), development (plan to build to ship), and act
  (brief to draft to send). The installer renders only what a path names. A
  directory under `skills/` that no path names fails `make check`. The list is
  enumerated at install, never recited.
- `contrib/` holds every skill no path names. In git, not installed. Every
  adoption from outside lands in `contrib/` first; adopting is cheap, promotion
  costs a trial.
- `sd skill try <name>` installs a `contrib/` skill on this machine for thirty
  days and writes a trial row. Direct use during the trial lands in the
  `skill_use` table B's library owns: a `PreToolUse` hook on the `Skill` tool
  and on reads of `skills/*/SKILL.md`, a `UserPromptSubmit` hook for typed
  `/sd-*` commands (marked `direct`), a nightly parse of `~/.codex/sessions`
  for the same, and an OpenCode plugin when that surface is in use.
- Promotion is a pull request that moves `contrib/<name>` to `skills/<name>` and
  adds it to a path; direct use counts as a path of length one. Demotion is the
  reverse. A trial that expires with zero rows is removed at the next install
  run, which says so. A path skill with no use in ninety days is proposed for
  demotion. No demotion on counts happens before ninety days of data exist.
- The dashboard's skills section (B) is a catalog: what each skill does, when to
  use it, use per surface, trials and their expiry, and two buttons, promote and
  demote, that call the library to open the pull request. The operator merges.
  The dashboard never writes to git.

### Requirement 11 — filing an improvement is one skill and one row

Internal GitHub issues stop. Two are open across repositories the operator owns
(`sd-ai-command-pack` 1, `mezmo_benchmark` 1); they import to the database and
close on GitHub with a pointer.

`sd-suggest` is the one way to file, for the operator and for the agent. It
captures a fixed small set: repository, what happened, what it cost, what was
expected, and the session it came from. In a repository the operator owns it
writes a row. In a repository someone else merges it files a GitHub issue there,
as it does today. Issues other people file on GitHub arrive as read-only shadow
rows through B's sync, with the operator's notes beside them.

The vault `skill-proposal` database, its kind in the writing manifest, and
`sd-propose-skills`'s vault write all go; they were the previous answer to this
requirement, and the routine they depended on, `skill-proposal-accept`, never
existed.

### Requirement 12 — handoff loses nothing, because nothing lives only in context

`sd-handoff` exists and has been used once. It is manual by design: a hook
cannot write `summary`, `next` and `dont`, only the model can, and a model that
has to be asked is not asked.

After this item the packet is the last resort, not the mechanism. Followups,
decisions, proposals and open questions are written to the item's rows as the
session produces them, through the library; nothing that matters lives only in
the conversation. A `PreCompact` hook and a `SessionEnd` hook prompt the model
to write the packet for whatever is left. The `SessionStart` hook loads the
item's open rows, the packet if one exists, and the `claude-mem` context it
loads today. The test of this requirement is a session killed mid-task and
restarted: every followup it had named is on the item, and the new session
begins from them without being told.

## What leaves this item

Two requirements of the first draft are gone, recorded here so the trail holds.

- **The writing pipeline** (was requirement 10) moves to C. Blog writing is
  third in priority behind `mezmo-world-simulator` and `mcp-research`, and its
  ideas and pieces belong in the database, which does not exist yet. The four
  cuts it named (`sdw-review-push`, `sdw-review-pull`, `sdw-help`,
  `sdw-blog-research` folding into `sdw-research`) go with it.
- **One surface per question** (was requirement 11) is superseded. It merged
  three vault databases into one vault backlog. Obsidian is now a knowledge
  base, not a process surface: no ladders, no tasks, no crons, no state the pack
  reads. The backlog is a table in `sd.db`. The two defects that requirement
  found stand as evidence: nine of ten pieces disagree with the vault note they
  name, and the `skill-proposal-accept` routine does not exist.

## Acceptance criteria

1. `WORKFLOW.md` exists at the repository root, states the two flows and the
   spine, the default, opt-in, advisory and never-in-a-shared-repository sets,
   the review table with its caps, and the modes with their resolution rule. It
   is reachable from both `sd-help` and the `CLAUDE.local.md` block the
   installer writes. A test asserts the installer's block names it. A test
   asserts the set of keys `WORKFLOW.md` documents equals the set `sd_lib.py`
   reads, enumerated from `MODES` and `CHECK_NAMES` in the source rather than
   from a list written down beside it. The set today is `mode`, `check`, `test`,
   `lint`; the test must fail if a fifth key is added to either side alone.
2. `sd-ship` invoked on a change with no work item performs no `sd-spec` run, no
   `Work:` line, and no remote-branch deletion command, and its settle step
   issues no shell polling loop. Asserted against the skill text, not inferred.
3. `sd-ship` warns on a commit to the pack, system or writing repository whose
   message lacks a `Needed-by:` trailer, and ships. A test covers the warning
   path and the pass path. The count of missing trailers per week is readable
   from the database once B exists, and from the git log before that.
4. Exactly one second-model lane is named anywhere in the payload, the
   contract, or `AGENTS.md`. A repository-wide grep for the deleted lane returns
   nothing outside `CHANGELOG.md`.
5. The review table appears in exactly two places, `WORKFLOW.md` and the one
   rule file under `.claude/rules/`, and a test asserts the two copies are
   identical. Every skill that runs a review names its point in the table and
   reads the cap from it. A grep of the payload for a vendor name (`codex`,
   `claude`, `openai`, `anthropic`) inside a skill's instructions returns only
   the provider-registry documentation.
6. The provider registry format is documented in `WORKFLOW.md` with the role
   vocabulary `author` and `reviewer`, and a test asserts the registry the
   library ships resolves both roles to different providers. Adding a provider
   entry named `exo` with an OpenAI-compatible URL needs no code change,
   asserted by a test that adds one and resolves it. Resolving `reviewer` for
   a change authored by the registry's reviewer provider returns a different
   provider, and fails by name when no other provider carries the role; a test
   asserts both. `bin/sd-review` contains no provider table, `sd-review.json`
   contains no key ending in `_providers`, and every provider name in its
   tiers resolves against the registry on a machine that has one. The
   reviewer list falls through: a test disables the first entry, then makes
   it fail preflight, and asserts the second reviews and the output names the
   fallthrough. `sd-review --provider <name>` refuses a name not in the
   registry, and refuses a disabled one by its reason. Every entry carries
   `vendor:`, and a test asserts an entry whose vendor matches the author's
   is skipped. Fallthrough skips every provider on a bill at its cap: a test
   writes cost rows to `cap_usd_month` and asserts resolution passes over the
   bill, and that `--provider` on it refuses with the month's total. A `url:`
   entry whose response carries a `<think>` block and `reasoning_content`
   yields a clean finding list, asserted against a fixture response.
7. The seven `mezmo-world-simulator` passes are scored, accepted against
   rejected per pass, and the scores are recorded on this item before the code
   review point runs on any new pull request.
8. The concern-ledger and cross-artifact-sweep obligations are stated as
   conditional on a `sensitive` path in every place they appear.
9. No pack surface requests a Copilot review. The global settings contain no
   Copilot-requesting hook. Both asserted by grep over the rendered payload and
   the settings file. `WORKFLOW.md` states that Copilot review is off on
   repositories the operator pays for personally.
10. A pull request body carries a `Work:` line only when the item exists; the
    `none - <reason>` form appears in no skill, tool, or lint rule. The lint's
    rule 5 passes on a body with no `Work:` line when no work item is present,
    and still fails a body naming an item that does not resolve.
11. Without an explicit `mode:` line, `full` is the resolved mode only when the
    remote owner is the operator, the repository is not a fork, and the operator
    is its sole collaborator; every other answer resolves to `guest`. A test
    covers five cases: owned sole-collaborator remote, unowned remote, a
    personal fork of a shared upstream, an owned remote with a second
    collaborator, and a root with no remote or no git at all. The last resolves
    to `full` for artifacts, since a local scratch repository has no one to
    expose anything to, and is named and asserted as its own case rather than
    left to whichever branch an exception reaches. An explicit `mode:` line
    still wins over detection. Unattended merge is never derived from mode: a
    test asserts the loop stops at pull-request-ready in a `full` repository
    whose row lacks `merge: auto`. All three modes appear in `README.md`.
12. `README.md`'s writes-nothing claim names the installer as its subject and
    lists the skills that write tracked files.
13. Once B's library exists: on a machine with the database, in a checkout on
    the item's branch, `sd_lib.py` and `sd-docs-lint` derive an item's status
    from its row, and a `prd.md` whose `status:` mirror disagrees with the row
    fails the lint by name. In a checkout on any other branch, and without the
    database as in CI, both read the mirror and pass. Tests cover all three:
    the item's branch with a disagreeing mirror fails; a linked worktree on
    another branch with the same mirror passes; no database passes. `sd-ship`
    refreshes the mirror before committing, asserted by a test that changes a
    row and ships. Before B exists, this criterion is recorded as waiting, not
    as met.
14. `make check` runs documentation-lint rules 1 through 4 when `docs/work/`
    exists, and skips them cleanly when it does not.
15. The coverage floor applies to `bin/sd_install.py` and to no other file. The
    four line-count ceilings emit a warning and exit zero when exceeded. A test
    asserts the warning path, not only the passing one.
16. `make check` accepts a changed-files fast path, and the full suite remains
    the default when no such argument is given.
17. The `bash32` job, `tests/test_selector_contract_drift.py`,
    `generated/registry-snapshot.json` and the `plugins/sd` stub are absent, and
    the `security` job's steps run inside `lint`.
18. A repository-wide grep for `Trellis`, `.trellis` and `task.py` returns
    nothing outside `CHANGELOG.md`.
19. The global settings contain no `Read()` deny rule and no `.trellis` allow
    rule, and do contain the four MCP pull-request tools. The global guide
    contains no `cd` prohibition.
20. Exactly one file states the planning adversarial review rule.
21. `docs/work/archive/` does not exist. All 487 items in it are deleted, the
    386 `done` and the 100 `planning` alike, and the deletion commit names
    `46ec7fb85` as the commit that recovers them. `sd-plan` deletes a `done`
    item's directory rather than moving it, and only when the directory is
    clean and fully tracked; no sweep or park code path remains. Tests cover
    the deletion path, an untracked file that blocks it, an ignored file that
    blocks it, and an uncommitted edit that blocks it, and assert the report
    names the file; the deletion test asserts `git rm` removed only tracked
    paths.
22. The pull-request template links only to files that exist. A test walks its
    links.
23. The caveman plugin is absent from the global settings, and the writing
    repository's style override is deleted.
24. `skills/paths.json` exists, names three paths, and every directory under
    `skills/` appears on at least one. The installer renders exactly the union
    of the paths plus active trials, asserted by a test that adds an unlisted
    skill directory and sees `make check` fail. `contrib/` exists and the
    installer never renders from it without a trial row.
25. `sd skill try <name>` installs from `contrib/`, writes a trial row with an
    expiry, and prints the date. The next install run after expiry with no
    `skill_use` rows removes the skill and says so. Both asserted by tests
    against a temporary database.
26. The `PreToolUse` and `UserPromptSubmit` hooks write `skill_use` rows with
    `surface`, `mode` and `cwd`, and the Codex nightly parse writes the same
    shape. A test feeds one recorded session of each kind and asserts the rows.
27. Promotion and demotion each produce one pull request that moves the
    directory and edits `paths.json`, opened by the library and never by the
    dashboard directly. A test asserts the branch content.
28. `sd-suggest` writes a row in an owned repository and files a GitHub issue in
    a repository someone else merges, asserted by a test for each mode. The two
    open internal issues are closed on GitHub with a pointer to their rows. The
    `skill-proposal` kind is absent from the writing manifest and
    `sd-propose-skills` writes no vault note.
29. A session killed mid-task and restarted in the same directory begins from
    the followups it had named, with none lost. The test writes three followups
    through the library, ends the session without calling `sd-handoff`, starts a
    new one, and asserts all three are in the injected context.
30. `make check` passes.

## Open questions

All five questions the first draft carried are settled and recorded in the log
under their dates. None are open. New questions raised during implementation
are filed as rows on this item once B's library exists, and in the log before.

## Log

- **2026-09-05** — Item opened on `feat/solo-first-workflow-policy`, from a
  five-round interview covering the pack, the writing pack, the system
  repository and the global instruction layer. Six read-only audit agents
  supplied the evidence: the mandatory process path, teammate-visible surfaces,
  skill usage against machine history, cross-layer rule consistency, tooling
  weight, and writing-pipeline throughput. Twenty decisions recorded as
  requirements 1 through 10. The policy page draft exists and lands with the
  first implementation commit.
- **2026-09-05** — Open question 1 settled: the drafted `spec:`, `codex:` and
  `copilot:` keys are cut, and opt-in lanes are asked for by name. Requirement 1
  and acceptance criterion 1 now bound the key set to what `sd_lib.py` already
  reads, checked by enumeration rather than by a list.

  Writing that criterion found a defect in the same edit that introduced it: the
  first draft said the block carries `mode:` and `check:`. It carries four keys,
  `mode:` plus the three `CHECK_NAMES` entrypoints, so the page was wrong by two
  before it was ever written down as policy. Enumerating from `sd_lib.py` caught
  it; reading the draft would not have.
- **2026-09-05** — Open question 2 settled: guest mode covers the shared-repository
  case and the drafted untracked local path is cut. Requirement 6 keeps one piece
  of new code, the mode fallback, and its criterion names three cases including
  the detection-failure path.
- **2026-09-05** — Tracking surfaces consolidated into a requirement 11 that no
  longer exists; see "What leaves this item". Verifying it found two live
  defects that stand as evidence: `skill-proposal-accept`, which
  `sd-propose-skills/SKILL.md:126` relies on, is not in the vault's scheduled
  tasks, which is why `accepted` holds zero notes; and nine of ten pieces
  disagree with the vault note their `obsidian_source` line names, two of them
  active against notes marked `declined`.
- **2026-09-05** — Open questions 3, 4 and 5 settled. Three: delete both
  archive groups, git is the archive; the full enumeration replaced the sample
  and is now in the problem statement. Four: the writing publish closes its
  requirement and defects open their own item; moot an hour later when the
  requirement left this item. Five: the skill-usage undercount is real, uneven,
  and unfixable by counting; the twelve-of-82 figure is withdrawn and no figure
  replaces it, and requirement 10 now installs by path rather than by count.
- **2026-09-05** — Second interview, on the operator's goals rather than the
  pack's defects. Priorities: `mezmo-world-simulator` and `mcp-research` first,
  blog writing third. The operator is visual, forgets commands, tinkers, and
  wants tools perfect before use; the framework has been the rabbit hole, at
  327 commits to 62. Twenty-three decisions taken, and the item split into
  three. What moved into this item: the two-flow policy page, the unattended
  ship path with a soft `Needed-by:` guard, the review table with caps and the
  different-vendor rule, the provider registry, Copilot scoped to where the
  organisation pays, ownership deciding mode, state leaving frontmatter for the
  database, path-based skill installation with `contrib/` and trials, one
  filing skill, and handoff on rows. What moved out: the writing pipeline to C;
  the vault consolidation, superseded by Obsidian's exit from process. What
  moved to B: the database, the library, the runner, the five-section
  dashboard, migrations, the vault crons stopping, and the multiplexer wrapper.

  This week's deliverables, outside this item: the six `mcp-research` drafts
  filed, and `mezmo-world-simulator` Phase 1 to `done`. The seven
  `mezmo-world-simulator` passes are scored before any new code review runs.

  One decision from the interview is corrected here. The 104 Codex sessions
  that run from the Obsidian vault are not scheduled jobs: no launchd job or
  cron script spawns Codex. They are the writing pipeline's hostile-read
  fan-out, `pack.py review adversarial` through `adversarial-gate.sh`, one
  `codex exec` per piece, in bursts of up to eighteen when the pipeline runs.
  There is nothing to unload. The cap in requirement 3 is what governs them.
- **2026-09-05** — Planning review, round one, `sd-review --scope planning
  --challenge` through Codex. Four blocking findings, all addressed.
  - C-1, `design.md` modes: remote ownership cannot establish that nobody else
    merges; a personal fork or an owned repository with collaborators would
    resolve `full` and merge unattended. Addressed: mode detection asks owner,
    not-a-fork, and sole-collaborator, and any other answer is `guest`;
    unattended merge is a separate per-repository policy, `merge: auto`, set
    once by the operator and never derived. Requirement 2, requirement 6,
    criterion 11.
  - C-2, requirement 5: status only in a machine-local database leaves CI's
    documentation lint with nothing to read. Addressed: the `status:` line
    stays as a derived mirror the library writes; the machine reads the row and
    fails on disagreement, CI reads the mirror, `sd-ship` refreshes it before
    committing. Criterion 13.
  - C-3, requirement 5: deleting a `done` directory on the row alone destroys
    untracked or uncommitted files. Addressed: deletion requires a clean, fully
    tracked directory, else the run keeps it and names the files. Criterion 21.
  - C-4, requirement 3: "moves on when the cap is spent" contradicted "blocked
    on an open blocking finding past the cap". Addressed: the cap bounds
    automatic passes; advancement needs every blocking finding dispositioned;
    an open one past the cap marks the item `blocked`. Requirement 2 and 3, and
    the page.
- **2026-09-05** — Planning review, round two, same lane. Three blocking
  findings: two addressed, one recorded on the item it belongs to. This is the
  last remediation round the contract allows.
  - C-5, requirement 5: `git status --porcelain` omits ignored files, so the
    deletion guard could pass over ignored notes or evidence and delete them
    beyond recovery. Addressed: the guard adds `--ignored`, the deletion is
    `git rm -r` of the paths `git ls-files` enumerates and nothing else, and a
    directory left non-empty stays. Criterion 21 gains the ignored-file case.
  - C-6, requirement 5: one machine-local row over a versioned mirror had no
    revision identity; with linked worktrees, a second checkout's committed
    mirror would fail lint, and refreshing it would commit `done` onto
    unfinished work. Addressed: the row carries the item's branch, git holds a
    branch in one worktree at a time, the library writes the mirror only in
    that checkout, comparison happens only there, a `done` row compares with
    nothing, and `done` is never written into a mirror because `done` deletes
    the directory. Every other checkout reads the mirror as CI does. Criterion
    13 gains the three cases; B's `item` table gains the `branch` column.
  - C-7, `2026-09-04-the-sweep-trusts-a-branch-field-it-never-resolves`,
    criterion 5: remote-tracking refs stay until pruned, so counting them does
    not establish that a branch is live. Valid, and not this item's: criterion
    21 removes the sweep, so that item is superseded when this one lands. The
    finding is recorded on that item's Log so it survives if the sweep outlives
    this item. Not addressed here.
- **2026-09-05** — Two gaps recorded from the operator's question on code
  review. First: the registry is static, so a Codex-authored change would
  have resolved `reviewer` to Codex. Resolution now takes the author into
  account and falls through to the next provider carrying the role.
  Second: `bin/sd-review` and `.github/sd-review.json` each carried their own
  provider list beside the registry. The registry owns providers; the other
  two keep policy only. Requirement 3 and criterion 6.
- **2026-09-05** — Fallbacks and direct choice, from the operator's question.
  The `reviewer` line becomes an ordered list; rate limit, missing binary,
  failed authentication, failed run and timeout fall through, and the run
  records which provider reviewed. `sd-review --provider <name>` and a
  dashboard picker choose one directly. Entries gain `vendor:`, `enabled:`,
  `reason:` and `reader:`. Checked while writing this: `prism` and `gito`
  both run `openai/gpt-5.6-sol` through OpenRouter, per `~/.prism/.env` and
  `~/.gito/.env`, so they are OpenAI-vendor reviewers on a metered bill, not
  a second vendor beside Codex; `local-prism/README.md` still says the active
  provider is Moonshot and is stale. `gito` and `kimi` stay disabled until
  each has a verified start line and a reader. Copilot has no local fallback
  to add: the local lane runs before every push, and Copilot only advises.
  Requirement 3 and criterion 6.
- **2026-09-05** — Four answers from the operator, and two corrections.
  Fallthrough runs on its own with the cost logged; `author` is a list picked
  at assignment start; the dashboard is this Mac only; the palette's
  execution model stays open on B. The corrections: the operator
  holds prepaid balances on Moonshot and MiniMax and prefers them over
  OpenRouter, so the reviewer order is subscription, then prepaid, then
  company; and `prism` and `gito` move from OpenRouter to Baseten, which is
  company money and gets the first cap, fifty dollars a month, on its bill.
  The registry gains `bills:`, and entries gain `bill:`, `price:`, `model:`
  and `max_tokens:`. The prepaid balances need the library's own
  OpenAI-compatible client, because `prism`'s fixed output cap is why both
  are recorded as disabled in `~/.prism/.env`. Requirement 3, criterion 6,
  and B's requirements 4, 5 and 6.
- **2026-09-05** — Correction to the entry above: the dashboard is not this
  Mac only. The operator works mostly from an iPad, so B serves it over
  Tailscale, bound to the tailnet address, identified by `tailscale whois`.
  Nothing in this item changes; recorded so the two ledgers agree.
