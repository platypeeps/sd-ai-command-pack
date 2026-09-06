---
title: implement — five pull requests that need no database, then three that do
status: planning
created: 2026-09-05
---

# Implement

Eight pull requests. Five of them touch no row and can land before item B
exists at all; three are B's slice 2 and wait on the library. The `prd.md`'s
landing order names only the second group, because that is the part whose
order is contested. The first group is where most of this item's work
actually is, and putting it first is not a scheduling preference: it means
the pack gets smaller before it gets a database, rather than carrying every
cut across the migration.

Only the last slice's merge delivers the item, `Delivers:` on its message.
Every other carries `Item:` and leaves the row open.

## PR 1 — `WORKFLOW.md`, and the review table in exactly two places

**Touches:** `WORKFLOW.md` (new), `skills/sd-help/`, `bin/sd_install.py`,
`.claude/rules/`.

The policy page at the repository root: the two flows and the spine they
share, what runs by default, what is opt-in, what is advisory, what never
touches a shared repository, the review table with its caps, the path for a
change at each size, and the modes and how they resolve. `sd-help` names
it. The `CLAUDE.local.md` block the installer writes links to it, and
carries the keys the pack already reads and no others — `mode:` plus the
`CHECK_NAMES` entrypoints at `bin/sd_lib.py:36`, consumed at `:391-412`.

**Why no opt-in key goes in that block.** A key that turns a lane on
permanently is a default in disguise: it converts a decision about one
change into a decision about the repository, taken once and never
recorded. Every opt-in lane is asked for by name in the moment.

The four files stating the planning review rule collapse to one under
`.claude/rules/`, and that one states the review table. The table then
appears in exactly two places, `WORKFLOW.md` and that rule — which is
criterion 5, and is the reason this PR touches the rule file rather than
leaving it to PR 4.

**Verification.** Criteria 1, 4, 5, 6, 8, 11 and 20. Criterion 4 is the
sharp one: exactly one second-model lane named anywhere in the payload,
which is a grep over the governed tree and not a reading of the page.

## PR 2 — requirement 13's confirmed cuts and bugs

**Touches:** `skills/sd-plan/`, `skills/sd-status/`, `skills/sd-ship/`,
`skills/sd-plan/templates/work-README.md`, `contrib/` (new), and the rest
of the line-by-line list.

Every finding three read-only reviewers confirmed by source reading on
2026-09-05, seven of them re-checked by hand. `sd-plan`'s step 6 with
`sd-status --parked` and the sweep sentence at line 11 of the work-item
README template;
the flags table for a `bin/sd-plan` that does not exist; the
`--from-suggestion` and `--from-proposal` flags; one work-item threshold
rather than two, with `skills/sd-ship/SKILL.md:54` citing the page instead
of naming 800; `sd-grill` moving to `contrib/` where a trial decides
whether it stays.

**One path in the `prd.md` is a shorthand.** It cites
`templates/work-README.md:11`; there is no top-level `templates/`
directory, and the file is `skills/sd-plan/templates/work-README.md`. Line
11 there is the sweep sentence the cut names, checked, so the citation is
right about the content and short about the path. **Corrected in the
`prd.md` on 2026-09-05**, and spelled out here so nobody greps for a
directory that does not exist.

**Nothing in this PR adds a mechanism.** That is the requirement's own
framing and it is the property that makes the PR reviewable: every line is
a cut or a fix, and a plausible finding that would need a fixture first is
in the log rather than here.

**Verification.** Criterion 31, which closes requirement 13 line by line:
one test lists the symbols, flags and files the cuts remove and asserts a
grep of the governed tree returns nothing for each — `sd_sweep`, `parked`,
`archived`, `record_load` and the rest.

## PR 3 — the checks that cannot fail

**Touches:** `Makefile`, `.github/workflows/`,
`tests/test_selector_contract_drift.py`, `generated/registry-snapshot.json`,
`plugins/sd`.

`sd-docs-lint` rules 1 through 4 move into `make check`, conditional on
`docs/work/` existing — it runs in no Makefile target and no workflow
today, which is a check that cannot fail. The 100% coverage floor stays for
`bin/sd_install.py`, which writes under the operator's home, and is dropped
everywhere else. The four line-count ceilings warn and stop failing: they
were re-derived five times in five days and cost more in bookkeeping than
the headroom they defend. `make check` gains a changed-files fast path with
the full suite once before a push. The `bash32` job is cut, the `security`
job folds into `lint`, and the three residue files are deleted.

**The ceilings warn rather than vanish.** They are a signal that stopped
being worth a gate, not a signal that stopped being true — and this item
has its own evidence for the distinction, since an earlier item in this
repository spent a whole pull request re-deriving one.

**Verification.** Criteria 14, 15, 16, 17 and 30.

## PR 4 — the instruction layers stop contradicting each other

**Touches:** the routing block, `.claude/rules/`, the global settings,
`CONTRIBUTING.md`, the system repository's guide, the pull-request
template.

Every mention of Trellis leaves the routing block and the planning
contract, and the two `.trellis` allow rules leave the global settings; no
such directory exists here. The fourteen `Read()` deny globs and the global
"never `cd`" rule are dropped **together**, because the globs guard build
artifacts rather than secrets and their presence is what forces the
path-resolution prompts the rule exists to dodge. Four MCP pull-request
tools join the allowlist — nine merges in the measurement window were
blocked because the guidance says "MCP before `gh`" while only the `gh`
form was allowed. Dated narrative leaves the governing documents:
`CONTRIBUTING.md` is about 45% history and the system guide about 36%
incident write-ups, and each keeps its present-tense rules plus one
sentence where a rule needs its reason. The pull-request template stops
linking to `docs/SD_AI_COMMAND_PACK.md`, which does not exist. The caveman
plugin is uninstalled and the writing repository's override deleted.

**The deny globs and the `cd` rule are one change and must not be split.**
Dropping the rule while the globs stand leaves every resolvable-path
command prompting; dropping the globs while the rule stands leaves a rule
with no failure left to prevent, contradicted by 59% of Bash calls. Either
half alone is worse than neither.

**Verification.** Criteria 9, 18, 19, 22 and 23, plus criterion 12
(`README.md`'s writes-nothing claim naming the installer as its subject).

## PR 5 — skills install because a path names them

**Touches:** `skills/paths.json` (new), `contrib/`, `bin/sd`.

`skills/paths.json` naming three paths, with every directory under them
accounted for, and `sd skill try <name>` installing from `contrib/`. The
row this writes is PR 8's; the installation mechanism is this PR's, and
they are separate because one needs no database.

**Verification.** Criterion 24 whole; criterion 25's install half, its
trial-row half deferred to PR 8 and said so here.

## Slice 2, PR 6 — the registry reader, the tiered path, the protection

**Touches:** `bin/sd_lib.py`, `skills/sd-ship/`, the provider registry
reader.

The default path becomes: commit enumerated paths, local review, push, open
the pull request, wait for CI once, merge, close the item on the default
branch, `git fetch -p`. `sd-spec` leaves it and runs when the operator asks.
Step 11's remote-branch deletion becomes the repository's
`delete_branch_on_merge`, the step shrinking to the local report. The settle
loop becomes one background wait on CI, replacing the 417 hand-rolled
polling loops in the measurement window, forty of which hit a tool timeout
and were reissued. The 70 lines of pull-request history in the skill file
collapse to one paragraph stating the rule.

The reader reads the line or the row as the repository's `status_source`
says, which is what lets every intermediate state of the migration work.
`Needed-by:` trailers on every commit to the pack, the system repository or
the writing repository, `sd-ship` warning when one is missing and shipping
anyway — soft on purpose, because the operator asked for framework work to
continue in the `cost`, `efficiency` and `visibility` lanes.

**`merge: auto` is necessary and never sufficient.** Consent goes stale: a
row set once does not know a collaborator arrived since. So at the moment
of the merge the path asks the remote requirement 6's three questions again
— can the operator administer it, is it not a fork, can anyone else push —
through one predicate in the library that the artifact gate and this gate
both call and neither restates. Any no, or no answer, and the item ends
`ready_to_send` with the changed answer named, the row keeping `merge:
auto` and the dashboard showing it suspended.

**Verification.** Criteria 2, 3, 10, 11 and 32. Criterion 32 is the one
that has to hold in both worlds: before B's library is installed, the
file-only reader and, once it exists, the library resolver must return the
same reviewer order from the same `providers.yaml`.

## Slice 2, PR 7 — the `docs/work` retire step

**Touches:** the migration's retire step (B's command), and every
`prd.md` under `docs/work/` outside the archive.

B's one sitting for `docs/work`: freeze, import once more, verify, snapshot,
then remove every item's `status:` line outside the archive in one commit.
The command is B's; the pull request is this item's slice, and it lands
**after** PR 6, from A's rounds thirty-six and thirty-seven, so that the
pack installed at every point between reads every item as it is.

**Why the retire cannot ride along with the reader.** A pack that removed
the lines before shipping a reader that can read rows would leave every
item unreadable in the window between the two merges. The whole point of
`status_source` is that the window is safe; landing both in one pull
request would waste it.

**`docs/work/archive/` is untouched**, asserted by criterion 21 as a diff
of the branch against its base — the retire step's scope is items outside
the archive, and an archive rewritten by a migration would be a record
altered after the fact.

**Verification.** Criteria 13 and 21. Criterion 13 is recorded as waiting
before this slice, which the landing order says in those words.

## Slice 2, PR 8 — rows for trials, uses, suggestions and handoff

**Touches:** `bin/sd`, the `PreToolUse` and `UserPromptSubmit` hooks,
`skills/sd-suggest/`, the handoff path.

`sd skill try` writing a trial row; the two hooks writing `skill_use` rows;
promotion and demotion each producing one pull request that moves the
skill; `sd-suggest` writing a row in every mode and filing nothing; and
handoff losing nothing because nothing lives only in context — a session
killed mid-task and restarted in the same directory begins from the row and
not from a re-read.

**Verification.** Criteria 25's trial-row half, 26, 27, 28 and 29.

## Two things about the criteria list itself

**Criteria 31 and 32 are out of order in the `prd.md`.** 32 appears at line
1580 and 31 at line 1590. Nothing depends on it and no test reads the
order, but a reader working down the list will hit 32 where they expect 31
and wonder what they missed. It is a `prd.md` edit, noted here rather than
made silently.

**Criterion 30 is `make check` passes.** It is closed by PR 3 in the sense
that PR 3 is where the suite changes shape, but every pull request in this
item has to leave it true. It is listed once, against PR 3, and that is a
simplification worth naming: a green suite is a precondition of all eight
merges, not an achievement of one.

## Order and dependency

PRs 1 through 5 in any order and at any time; they need no database and no
other item. PR 6 after B's slice 1 lands the library. PR 7 after PR 6. PR 8
after PR 6.

The one hard ordering that reaches outside this item: B's fixture harness
merges before any pull request in any item that claims a criterion naming
it, which B's criterion 23 asserts from the log. Several criteria here name
a fixture repository, so PRs 6, 7 and 8 sit behind that harness whatever
else is true.

## Closing the item

PR 7 or PR 8, whichever merges last, carries `Delivers:`. Then `prd.md`
goes to `status: done` and drops its `branch:` field in the same edit.

That field was missing when this file was first written, and adding it was
the fix. This repository's items carry `branch:` by convention — 237
`prd.md` files under `docs/work/` have the line, and the sibling item
`2026-09-04-the-plan-interview-is-one-sentence` reads `branch:
skill/sd-grill` — while this item's front matter had `title`, `status` and
`created` and stopped there, with the item sitting on
`feat/solo-first-workflow-policy`.

The consequence ran the opposite way from the usual one.
`bin/sd_sweep.py:91` skips an item when `item.status != SWEEPABLE_STATUS or
item.branch`. A stale field left behind excludes an item that should be
swept; a **missing** field includes an item that should not be. This item
was `planning` with no branch recorded, so at 45 days the sweep would have
offered it as long-idle while it was being actively worked. `branch:
feat/solo-first-workflow-policy` is now in the front matter, `sd sweep`
reports "nothing over 45 days: 8 active", and `sd-docs-lint` is clean over
495 items.

## What closes the criteria

| Criterion | Closed by |
|---|---|
| 1, 4, 5, 6, 8, 11, 20 — the policy page and the review table | PR 1 |
| 31 — requirement 13 line by line | PR 2 |
| 14, 15, 16, 17, 30 — the checks | PR 3 |
| 9, 12, 18, 19, 22, 23 — the instruction layers | PR 4 |
| 24 — `skills/paths.json` and its three paths | PR 5 |
| 25 — `sd skill try` installs, and writes a trial row | PR 5 (install), PR 8 (row) |
| 2, 3, 10, 32 — the tiered path, trailers, reviewed head | PR 6 |
| 13, 21 — status from the row, archive untouched | PR 7 |
| 26, 27, 28, 29 — use rows, promotion, suggestions, handoff | PR 8 |
| 7 — the seven `mezmo-world-simulator` passes scored | see below |

Criterion 7 is scored against another repository's passes and is the one
row in this table with no pull request beside it. It is evidence the item
collects, not code the item ships, and it closes when the passes are scored
and accepted rather than when something merges here. Naming a PR for it
would be a false entry in a table whose whole value is that its entries are
checkable.
