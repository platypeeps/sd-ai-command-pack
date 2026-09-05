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

Three separate signals say the process serves nobody:

- **Nobody reads the artifacts.** 494 archived work items, sampled fifteen
  deep, have exactly one commit after creation: the archive move itself. Zero
  subsequent edits. The archive is a write-only log.
- **Nobody runs most of the payload.** Of 82 skills, twelve show any invocation
  evidence in the machine's history. Two of them carry nearly all real use.
- **The rules that fail are the ones written as prose.** The global "never `cd`,
  always absolute paths" rule is contradicted by 9,455 of 16,033 Bash calls in
  the sample window — by the same agents that read it every session.

Meanwhile the writing pack, running its own eleven-stage pipeline, has published
zero pieces. Four have been sitting at `ready` since mid-August. Its own skill
file says so: "Nothing has been pushed through this path yet."

## Why the obvious fix is wrong

**Not "delete the skills".** The unused-skill count looks like the headline and
is not. Skills cost nothing at rest — they render once at install and sit in a
catalog until named. What costs is the *mandatory path*: the gates that run
whether or not the change needs them. Cutting sixty skills would remove
capability the owner might want next month and would not save a single one of
the 770 polling minutes. The skills stay.

**Not "remove the gates".** The local adversarial review lane before the first
push is the single measured win in the pack's history: it took one branch from
fifteen remote review rounds down to three. Deleting gates indiscriminately
would delete that one too. What is wrong is not that gates exist; it is that
every gate applies at every size, to a one-line fix and a new subsystem alike.

**Not a new abstraction.** The pack already carries three review lanes, three
repository modes, a routing policy, a plugin registry and a fleet dashboard.
Another layer to decide when the other layers apply is the disease, not the
cure. What is missing is one page saying which defaults hold, and a set of
existing knobs wired to it.

**Not "make everything opt-in".** A default nobody sets is a gate nobody runs. The
distinction that matters is *who sees the output*: a gate that runs on the
owner's machine and prints to the owner's terminal is cheap and stays on by
default; a gate that writes to a shared repository, posts to a pull request, or
blocks a merge is expensive and turns off unless the work earns it.

## What this changes

One page, `WORKFLOW.md`, states the pack's policy for a repository with one
person in it, and the pack's surfaces are brought into line with it. The policy
in one sentence: **anything the pack does should help the person running it,
without exposing or imposing that person's process on anyone else.**

Twenty decisions were taken in a structured interview on 2026-09-05. They are
recorded here as the requirements below, grouped by what they touch.

### Requirement 1 — the policy page exists and is discoverable

`WORKFLOW.md` at the repository root states, for a consuming repository: what
runs by default, what is opt-in, what is advisory, what never touches a shared
repository, the path for a change at each size, the three modes, and the
override keys. `sd-help` names it. The `CLAUDE.local.md` block the installer
writes links to it.

### Requirement 2 — the ship path is tiered, not uniform

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

### Requirement 3 — one second-model lane, one round

Three lanes review the same planning artifacts today: a host lane in the
contract, `sd-review --scope planning`, and a hand-launched background task
named in `AGENTS.md`. Two of them are the same external model reading the same
files.

After this item there is one lane, `sd-review --scope planning`, and it is
opt-in per work item. One round by default. The concern ledger, the pre-edit
hash baselines and the per-round cross-artifact sweep apply only to paths listed
under `sensitive` in `.github/sd-review.json`. Rounds are counted per work item
and a scope cut does not reset the count; three rounds is the cap. The codex
appendix under `docs/` and the `AGENTS.md` bullet that mandates the second lane
are deleted.

### Requirement 4 — Copilot advises, CI decides

Merge blockers are the local review lane and CI. Copilot review is advisory:
GitHub requests it automatically when a pull request opens, its findings are
read and dispositioned, and it never blocks a merge. The pack never requests a
second round. The user-global `PostToolUse` hook that asks for a Copilot review
after every push is deleted; it is not installed by the pack, and it duplicates
what GitHub already does.

### Requirement 5 — a work item exists only when it earns one

A work item is created when the work spans more than one session or roughly 300
changed lines. `design.md` and `implement.md` are written when asked for, not by
default. `sd-plan` asks three to five questions before it writes anything.

A merged item is marked `done` and its directory is deleted at the next sweep;
git history holds it. The 45-day park stays for unmerged items. `docs/work/archive/`
and its 494 files are removed in one commit.

### Requirement 6 — nothing personal reaches a shared repository

A shared repository is one where somebody else also merges.

- The `Work:` line appears in a pull request body only when the pull request
  resolves a work item that lives in that repository. The `Work: none - <reason>`
  form is deleted, and rule 5 of the documentation lint becomes conditional on a
  work item existing.
- Planning artifacts for a shared repository live in an untracked local path
  covered by the global git excludes, the same mechanism `CLAUDE.local.md` uses.
  Nothing lands in the team's history.
- A repository the operator does not own defaults to `mode: guest`. The three
  modes are named in `README.md`, which does not mention two of them today.
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
  `.claude/rules/`.
- The pull-request template points contributors at `docs/SD_AI_COMMAND_PACK.md`,
  which does not exist. Fixed or removed.

### Requirement 9 — one terse-style mechanism

The output style already enforces short sentences everywhere. The caveman plugin
enforces a second, overlapping style through a session hook, and the writing
repository carries an override forbidding it. The plugin is uninstalled and the
override deleted, leaving the output style as the single mechanism.

### Requirement 10 — the writing pipeline proves itself before it grows

Zero pieces published, four at `ready` for three weeks, and process commits
running level with content commits (75 to 76). Before any further pipeline work:
publish one piece end to end, then delete every step that run did not need.

The Google Docs review loop (`sdw-review-push`, `sdw-review-pull`) is cut;
reviewers do not comment on the copies. `sdw-help` duplicates `sd-help` and is
cut. `sdw-blog-research` folds into `sdw-research` as a from-an-idea path. Dated
narrative leaves `pipeline.md` and `permissions.md`.

## Acceptance criteria

1. `WORKFLOW.md` exists at the repository root, states the default, opt-in,
   advisory and never-in-a-shared-repository sets, and is reachable from both
   `sd-help` and the `CLAUDE.local.md` block the installer writes. A test
   asserts the installer's block names it.
2. `sd-ship` invoked on a change with no work item performs no `sd-spec` run, no
   `Work:` line, and no remote-branch deletion command, and its settle step
   issues no shell polling loop. Asserted against the skill text, not inferred.
3. Exactly one second-model planning lane is named anywhere in the payload, the
   contract, or `AGENTS.md`. A repository-wide grep for the deleted lane returns
   nothing outside `CHANGELOG.md`.
4. The concern-ledger and cross-artifact-sweep obligations are stated as
   conditional on a `sensitive` path in every place they appear.
5. No pack surface requests a Copilot review. The global settings contain no
   Copilot-requesting hook. Both asserted by grep over the rendered payload and
   the settings file.
6. A pull request body carries a `Work:` line only when the item exists; the
   `none - <reason>` form appears in no skill, tool, or lint rule. The lint's
   rule 5 passes on a body with no `Work:` line when no work item is present,
   and still fails a body naming an item that does not resolve.
7. `mode: guest` is the resolved mode for a repository whose remote owner is not
   the operator, absent an explicit `mode:` line. All three modes appear in
   `README.md`.
8. `README.md`'s writes-nothing claim names the installer as its subject and
   lists the skills that write tracked files.
9. `make check` runs documentation-lint rules 1 through 4 when `docs/work/`
   exists, and skips them cleanly when it does not.
10. The coverage floor applies to `bin/sd_install.py` and to no other file. The
    four line-count ceilings emit a warning and exit zero when exceeded. A test
    asserts the warning path, not only the passing one.
11. `make check` accepts a changed-files fast path, and the full suite remains
    the default when no such argument is given.
12. The `bash32` job, `tests/test_selector_contract_drift.py`,
    `generated/registry-snapshot.json` and the `plugins/sd` stub are absent, and
    the `security` job's steps run inside `lint`.
13. A repository-wide grep for `Trellis`, `.trellis` and `task.py` returns
    nothing outside `CHANGELOG.md` and archived items.
14. The global settings contain no `Read()` deny rule and no `.trellis` allow
    rule, and do contain the four MCP pull-request tools. The global guide
    contains no `cd` prohibition.
15. Exactly one file states the planning adversarial review rule.
16. `docs/work/archive/` does not exist, and the sweep deletes a `done` item
    rather than moving it. A test asserts the deletion path and asserts that an
    unmerged item still parks at 45 days.
17. The pull-request template links only to files that exist. A test walks its
    links.
18. The caveman plugin is absent from the global settings, and the writing
    repository's style override is deleted.
19. In the writing repository: one piece reaches `published` with a live URL
    recorded, before any further pipeline change lands. `sdw-review-push`,
    `sdw-review-pull` and `sdw-help` are absent, and `sdw-blog-research` is
    reachable as a path within `sdw-research`.
20. `make check` passes, and the acceptance-criteria count it reports does not
    fall below its current 40 without each removal being named in this item's
    log.

## Open questions

1. The three override keys the policy page names (`spec:`, `codex:`,
   `copilot:`) do not exist. `sd_lib.py` reads `mode:` and `check:` only.
   Adding three keys to satisfy a document is exactly the kind of machinery this
   item exists to remove — but leaving the page describing knobs that do nothing
   is worse. Either implement the three, or rewrite the page to say "ask for it
   by name" and carry no keys at all. The second is cheaper and matches how the
   opt-in lanes are actually invoked.
2. Requirement 6's untracked-local-path mechanism for shared repositories is
   stated but not designed. `CLAUDE.local.md` works because the installer puts
   one line in the global excludes. A `docs/work.local/` would need the same,
   and the sweep and the lint would both need to find it. Guest mode already
   routes artifacts to a fork branch; whether that is sufficient, and this
   mechanism unnecessary, should be settled before either is built.
3. Deleting `docs/work/archive/` is irreversible in the working tree and
   reversible only through git history. 494 items, none ever re-read in the
   sample. The sample was fifteen. Whether to sample deeper before deleting, or
   accept git history as the archive, is the owner's call.
4. Requirement 10 orders the writing-pack work behind a publish that has not
   happened. If the publish surfaces pipeline defects, those become work of
   their own and this item's writing-pack scope is superseded. That is the
   intended outcome, but it means requirement 10 may close by being replaced
   rather than by being met.
5. The measurement window was eight days and covered Claude Code transcripts
   only. Codex sessions and OpenCode invocations are not in the data, so the
   skill-usage figures undercount by an unknown amount. Nothing in this item cuts
   a skill, so the exposure is limited to the framing — but the twelve-of-82
   figure should not be quoted as settled.

## Log

- **2026-09-05** — Item opened on `feat/solo-first-workflow-policy`, from a
  five-round interview covering the pack, the writing pack, the system
  repository and the global instruction layer. Six read-only audit agents
  supplied the evidence: the mandatory process path, teammate-visible surfaces,
  skill usage against machine history, cross-layer rule consistency, tooling
  weight, and writing-pipeline throughput. Twenty decisions recorded as
  requirements 1 through 10 above. The policy page draft exists and lands with
  the first implementation commit.
