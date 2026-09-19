---
title: implement — four pull requests that need no database, then four that do
created: 2026-09-05
---

# Implement

## Current status — 2026-09-18

The item remains `in_progress`.

Two deferred acceptance dependencies are blocked:

- `sd:777` has no qualifying pass because external provider reviews are cancelled.
- `sd:788` waits for the owner's live MiniMax check and `general` plan confirmation.

Other open criteria remain listed below.

Eight pull requests. **Four** of them touch no row and can land before item
B exists at all; four wait on the library or on B's fixture harness. The
`prd.md`'s landing order names only the second group, because that is the
part whose order is contested. The first group is where most of this item's
work actually is, and putting it first is not a scheduling preference: it
means the pack gets smaller before it gets a database, rather than carrying
every cut across the migration.

An earlier draft of this page said five pull requests needed no database and
was wrong four times over. Criterion 6 is a hundred and thirty lines of
provider-registry runtime, not a policy page. Criterion 11 needs rows and
six fixture-remote cases. Criterion 24 reads active trial rows. Criterion
25's printed date *is* the row's expiry, so there is no install half
observable without the row. Each is corrected below, and PR 5 is the one
that changes character: it now lands with the rows, not before them.

Only the last slice's merge delivers the item, `Delivers:` on its message.
Every other carries `Item:` and leaves the row open.

## PR 1 — `WORKFLOW.md`, and the review table in exactly two places

**Touches:** `WORKFLOW.md` (new), `skills/sd-help/`, `bin/sd_install.py`,
`.claude/rules/`, `.claude/sd-ai-command-pack/planning-adversarial-review.md`,
`skills/sd-receive-review/SKILL.md`, every skill that runs a review,
`README.md`; and — for criteria 4 and 20, which an earlier draft scoped from
a wrong model of where the deleted lane lives —
`docs/planning-adversarial-review-codex.md` (the lane page itself),
`AGENTS.md`, `docs/spec/backend/manifest-and-filesystem.md`,
`skills/sd-research-repo/references/conventions.md`. **Nothing gates the
reference.** An earlier draft named "the link checker whose
`documentationRoots` cover the page", citing
`docs/spec/backend/manifest-and-filesystem.md:1517-1519`. That passage is a
recommendation from an archived August item, not a description of a running
check: `documentationRoots` appears in five files repository-wide, all of
them prose — that spec page, an archived item's `design.md` and
`implement.md`, and this item's own two pages — and no workflow, `Makefile`
target or script in `.github/`, `bin/` or `tests/` invokes any link checker.
So deleting the lane page breaks its four referrers silently, and this pull
request updates all four by enumeration rather than relying on a gate to
catch a miss. **Not `tests/test_doc_citations.py`** either, which an earlier
draft listed as "the file that breaks when the page goes": it does not break,
on two counts run on 2026-09-05. Its `anchored_citations()` globs
`docs/**/*.md` only, so `AGENTS.md` and
`skills/sd-research-repo/references/conventions.md` are never read; and a
citation whose target no longer exists is skipped rather than failed —
`is_inside_repo()` returns `False` and the loop continues, which the test's
own docstring calls deliberate. `Ran 4 tests` / `OK` with the page deleted. Plus **`skills/sd-plan/SKILL.md`**, whose step 3 at `:38-41` "routes them to
the codex second-model lane" — the payload's own statement of the thing
criterion 4 greps for, which two earlier drafts scoped from the *filename*
`planning-adversarial-review-codex.md` instead. Criterion 4 is a grep for the
lane as a concept, and `git grep -niE 'second-model lane|codex (review
)?lane'` over the governed tree returns three files: `AGENTS.md:14`,
`skills/sd-plan/SKILL.md:40` and `skills/sd-receive-review/SKILL.md:3`. The
first and third were already here; the second was in PR 2's and PR 4's
Touches, neither of which claims criterion 4.

For criterion 5's vendor grep, the enumeration is the criterion's bare-token
shape run over the whole `skills/` tree, not a subset, and **not** the
case-insensitive four-name grep an earlier draft ran. That grep returns
**twelve** files:
`_shared/references/subagent-dispatch.md`, `sd-check/SKILL.md`,
`sd-handoff/SKILL.md`, `sd-help/SKILL.md`, `sd-plan/SKILL.md`,
`sd-propose-skills/SKILL.md`, `sd-research-repo/SKILL.md`,
`sd-research-repo/references/conventions.md`,
`sd-research-repo/templates/CLAUDE.md`, `sd-review/SKILL.md`,
`sd-ship/SKILL.md` and `sd-skill-adopt/SKILL.md`. Seven of
those twelve carry the strings only inside a path, a filename, an
environment variable, an MCP tool identifier, a URL or the product name
`Claude Code`, and none of those ever leaves; the criterion as first written
asked for a residue of "only the provider-registry documentation", which is
in `WORKFLOW.md` and so is in no skill at all, and could not pass. The
bare-token grep returns **thirty-two** hits across **eight** files, and all
eight are **PR 6's**, not this pull request's. What replaces a bare vendor
token is a role name, and nothing resolves a role until PR 6 lands the
registry reader; converting here would leave the research flow naming a
`reviewer` it cannot start, which is the stale-document failure inverted
again. So criterion 5's vendor clause closes in PR 6 whole.

What this pull request removes from those files instead is criterion 4's
deleted lane, a narrower grep — `second-model lane|codex (review )?lane` —
that returns `skills/sd-plan/SKILL.md:40`, plus the two references to the
lane page: `skills/sd-research-repo/SKILL.md:84` and
`skills/sd-research-repo/references/conventions.md:167,175-177`. The `codex
doctor` and `codex exec -s read-only` invocations beside them are how the
research pass is started today and stay until PR 6 can answer for them. An
earlier draft named three of the twelve files as "files the grep returns that
run no review" and stopped, having enumerated from the sentence that reported
the gap rather than re-running the criterion's grep.

**Why the Touches list reaches across `skills/`.** Criterion 5 asks that
*every* skill that runs a review name its point in the table and read the
cap from it, and that no skill's instructions carry a bare vendor token.
Criterion 4
asks that a grep of the governed tree for the deleted second-model lane
return nothing outside `CHANGELOG.md`. An earlier draft said this "means
deleting that lane's skill and agent files". It has neither: `ls agents/`
returns the five `sd-*` agents and none is this lane, and no `skills/`
directory implements it. The lane is `docs/planning-adversarial-review-codex.md`,
referenced from `AGENTS.md` at `:11-18`, from
`docs/spec/backend/manifest-and-filesystem.md:1519` and from
`skills/sd-research-repo/references/conventions.md:176` — and `AGENTS.md`
is a file criterion 4 names outright (`prd.md:1220-1221`). The same three
files carry criterion 20's fourth statement of the planning review rule.
The grep this criterion turns on would have come back dirty. Criterion 8 asks that the concern-ledger and
cross-artifact-sweep obligations become conditional on a `sensitive` path
"in every place they appear", and a governed-tree grep finds exactly two:
`.claude/sd-ai-command-pack/planning-adversarial-review.md` and
`skills/sd-receive-review/SKILL.md` — neither of which is the `.claude/rules/`
file. Criterion 11's closing sentence puts all three modes in `README.md`.
None of these is a documentation edit, and an earlier draft scoped this pull
request to `skills/sd-help/` alone.

The policy page at the repository root: the two flows and the spine they
share, what runs by default, what is opt-in, what is advisory, what never
touches a shared repository, the review table with its caps, the path for a
change at each size, and the modes and how they resolve. `sd-help` names
it. The `CLAUDE.local.md` block the installer writes links to it, and
carries five keys: `mode`, `check`, `test`, `lint` and `reviewers`, which
is the set criterion 1's test compares against what `WORKFLOW.md`
documents (`prd.md:1208-1212`). An earlier draft said "the keys the pack
already reads and no others — `mode:` plus the `CHECK_NAMES` entrypoints",
a four-key block: `grep -n reviewers bin/sd_lib.py` returns nothing, so
"already reads" excludes the consent key by construction and criterion 1's
test could not pass. The entrypoints are at `bin/sd_lib.py:36`, consumed at
`:391-414` — `_local_block_entrypoints` returns at `:409-414`, and both
this page and `design.md` cited `:391-412`. The `reviewers` line's value is
written by the installer's consent prompt, which is criterion 6's and so
PR 6's; PR 1 writes the key, PR 6 fills it, and criterion 1's test reads
the key set and not the value.

**Why no opt-in key goes in that block.** A key that turns a lane on
permanently is a default in disguise: it converts a decision about one
change into a decision about the repository, taken once and never
recorded. Every opt-in lane is asked for by name in the moment.

The files stating the planning review rule collapse to one under
`.claude/rules/`, and that one states the review table. **Enumerated, because
criterion 20 closes on the count and an earlier draft gave a number and no
list.** The rule is stated in six places today:
`.claude/rules/sd-planning-adversarial-review.md` (the one that survives),
`.claude/sd-ai-command-pack/planning-adversarial-review.md` (the contract it
points at, which also survives and is one of criterion 8's two places),
`docs/planning-adversarial-review-codex.md` (the lane page, deleted),
`AGENTS.md:11-18`, `docs/spec/backend/manifest-and-filesystem.md:1519` and
`skills/sd-research-repo/references/conventions.md:176`. A seventh statement
is `skills/sd-plan/SKILL.md:38-41`, which states it as a numbered step rather
than as a rule; it is in this pull request for criterion 4 and its wording is
brought into line here. The earlier "four" counted the deletions and the
survivor inconsistently, and its neighbouring sentence about "the same three
files" double-counted `AGENTS.md`. The table then
appears in exactly two places, `WORKFLOW.md` and that rule — which is
criterion 5, and is the reason this PR touches the rule file rather than
leaving it to PR 4.

**Verification.** Criteria 1, 8 and 20, criterion 4 whole, and criterion 5's
two table clauses — the table in exactly two identical copies, and every
skill that runs a review naming its point and reading its cap from it.
Criterion 5's vendor clause is PR 6's whole, since a converted token names a
role and nothing resolves a role until PR 6's registry reader. Criterion 4 is
the sharp one: exactly one second-model lane named anywhere in the payload,
which is a grep over the governed tree and not a reading of the page.

**Criteria 6 and 11 are not here**, though an earlier draft's closure table
put them here. Criterion 6 is requirement 3's whole runtime — `sd attribute`
and its two forms, `Authored-with:` and `Attributes:` trailer writing and
reading, `SD_AUTHOR` handling and its refusal at commit, `bin/sd-review`
losing its provider table, `sd-review.json` losing `_providers` and `tiers`,
a `--provider` flag refusing an unknown name and a disabled one by its
reason, bill caps and `meter` rows, fallthrough over disabled, failing and
capped entries, installer consent writing a `reviewers` line, and
url/executable/fingerprint/env refusals against a recording fixture. Only
`bin/sd_install.py` overlaps this pull request at all. Criterion 11 needs a
`full` repository whose row lacks `merge: auto`, six mode-detection cases
against fixture remotes, and a collaborator added and removed. Both are
PR 6's, where the registry reader and the fixture harness are.

## PR 2 — requirement 13's confirmed cuts and bugs

**Touches:** enumerated from **requirement 13's own removal list**
(`prd.md:1114-1162`), which gives a file and a line range for every cut, and
then widened by `git grep -l` over criterion 31's symbol list
(`prd.md:1664-1668`) to catch the readers requirement 13 does not name. An
earlier draft claimed the second derivation alone and did not run it: seven
of the nineteen symbols — `parked`, `archived`, `--stash-ref`, `--push`,
`--park`, `authors` and `Standing rule` — had no enumeration at all, and
twenty-two governed-tree files carrying them sat outside this pull request
while it claimed the criterion whose test greps for them. `bin/sd_sweep.py`,
`bin/sd`, `tests/test_sd_sweep.py` (`sd_sweep`); `bin/sd-handoff-restore`,
`tests/test_sd_handoff_restore.py` (`record_load`); `bin/sd-status`,
`tests/test_sd_status.py` (`carrier_branches`, `_protection_gaps`,
`load_acknowledgements`); the fifty-six `skills/*/SKILL.md` files carrying
`argument-vocabulary`; the thirty-nine files across `bin/`, `skills/`, `tests/`,
`dashboard/`, `.github/` and `docs/spec/` carrying `R10-D`;
`skills/sd-spec/SKILL.md` (`five gates`); `skills/sd-handoff/SKILL.md`
(`cron-jobs.sh`); the five `agents/*.md` and seven `skills/*/SKILL.md`
carrying `Active item:`; `agents/sd-rust-fill.md`,
`agents/sd-rust-reviewer.md`, `agents/sd-rust-write.md`,
`skills/sd-typed-holes/SKILL.md`; `README.md`, `bin/sd-skill-adopt`,
`skills/sd-deps/SKILL.md`, `tests/test_loc_caps.py`,
`tests/test_permission_allowlist.py`, `tests/test_skill_frontmatter.py`
(`sd-deps`).

For the seven symbols an earlier list left unenumerated, from requirement
13's own line references and then the readers: the `archived` and `parked`
fields at `bin/sd_lib.py:355-368`, `:271-282`, `:302-303`, `:350` and every
reader — `bin/sd-status:183,190,1122-1129,1234-1242,1254-1287`,
`dashboard/work.py`, `dashboard/app.js`,
`tests/test_dashboard_work.py`, `tests/test_sd_lib.py`,
`tests/test_sd_docs_lint.py`, `skills/sd-receive-review/SKILL.md`,
`.claude/sd-ai-command-pack/planning-adversarial-review.md`,
`docs/spec/backend/quality-guidelines.md` and `docs/spec/guides/index.md`;
`--stash-ref` at `bin/sd-handoff:374` with `skills/sd-handoff/SKILL.md` and
`tests/test_sd_handoff.py`; `--park` and `--push` in
`skills/sd-handoff/SKILL.md`, `skills/sd-plan/SKILL.md`,
`skills/sd-status/SKILL.md` and `tests/test_skill_frontmatter.py`; the
`authors` **policy key** at `bin/sd-review:276`, `:283` and `:1098` — `:283`
is the shared `_STRING_LIST_KEYS` tuple, so that one is an edit and not a
line deletion; an earlier draft cited `:287` and `:1092`, which are a
`raise PolicyError` and `"scope": args.scope` —
`bin/sd_setup_github.py:230,267`, `.github/sd-review.schema.json` and
`.github/sd-review.json`; and `Standing rule` in `bin/sd`,
`skills/sd-plan/templates/decision.md`, `skills/sd-suggest/SKILL.md` and
`tests/test_sd_plugin.py`.

And, for criterion 21's deletion-verb grep, two sites no other clause of this
pull request reaches: `bin/sd-status`'s `RESIDUE` tuple at `:960-996` — the
file is already above for the `sd_lib` field readers, named again because the
grep lands on a different block of it — and `bin/sd_install.py:820`, `:827`
and `:961`. Neither is a deletion here. Both are enumerate-and-freeze sites,
for the reason Verification gives below.

**`authors` is two different things and criterion 31's grep cannot tell them
apart.** Requirement 13 removes the `authors` *policy key* at the five sites
above. Criterion 6 **introduces** `authors` as a row field —
`prd.md:1289`, "the row's `authors` naming both" — and PR 6 lands it in
`bin/sd_lib.py`, inside the governed tree, after this pull request. A bare
governed-tree grep for `authors` therefore passes here and fails again at
PR 6's merge, breaking criterion 30, which this page calls a precondition of
every merge. The criterion is scoped to the policy key in this item's ledger;
this pull request removes the key and not the word.

For the named bug fixes: `bin/sd_research_review.py`, `bin/sd-research-kit`,
`agents/sd-claim-verifier.md`, `skills/sd-fact-check/SKILL.md`, the
`adversarial-gate` surface, and **`bin/sd-docs-lint`**, which criterion 31's
regression-test clause reaches through requirement 13's second bug:
`bin/sd-docs-lint:244` tests `value.startswith("none")` where it must compare
the whole token with `none`, so any `Work:` value beginning with those four
letters — `nonexistent-item`, `nonesuch` — fails as a missing reason rather
than as an unresolved path. The fix is `if value == "none":`. An earlier
draft had this backwards, citing `:242`, which is a `report.note` call, and
prescribing `startswith` — which is the bug — as the cure; a reader following
it would have changed nothing. Executed against `check_pr_link` on
2026-09-05: `'nonexistent-item'` returns "Work: none needs a reason", while
a value naming an item directory that is not there returns "does not resolve
to a work item", so the two outcomes are distinguishable and only the first
is wrong. The regression test
asserts `Work: nonexistent-item` produces the **unresolved path** failure. No Touches list held that file for this pull
request, which claims the criterion that mandates its test. Plus
`skills/sd-plan/`, `skills/sd-status/`, `skills/sd-ship/`,
`skills/sd-plan/templates/work-README.md`, `tests/test_sd_docs_lint.py`, for the
`bin/sd-docs-lint:244` regression test above and **not** for the `none - `
form, which is criterion 10's and PR 6's — an earlier draft moved the file
here saying "the `none - ` form this cut removes", and requirement 13 names
no such cut; and `contrib/`, created in PR 5, which therefore lands before
this pull request, as the ordering section states.

An earlier draft ended this list with "and the rest of the line-by-line
list", which is a pointer back to the requirement the list is meant to
bound, not a file set — and then named `bin/sd_sweep.py` in its prose, a
file the declared scope excluded. This is the item's largest deletion and
its boundary has to be readable from this line alone.

Every finding three read-only reviewers confirmed by source reading on
2026-09-05, seven of them re-checked by hand. `sd-plan`'s step 6 with
`sd-status --parked` and the sweep sentence at line 11 of the work-item
README template;
the flags table for a `bin/sd-plan` that does not exist; the
`--from-suggestion` and `--from-proposal` flags; one work-item threshold
rather than two, which makes `skills/sd-ship/SKILL.md:54` cite the page
instead of naming 800 — that line names 800 literally today, so this is the
work and not a description of what the file already says; `sd-grill` moving to `contrib/` where a trial decides
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
`archived`, `record_load` and the rest. Plus **criterion 21's code-path
half**, whose grep this pull request must also make true, and an earlier
draft assumed deleting `bin/sd_sweep.py` would do it. It does not. Run on
2026-09-05, `git grep -nE 'git rm|rmtree|rmdir' -- bin skills` returns eight
lines and `bin/sd_sweep.py` is in none of them: five are removal-suggestion
**strings** in `bin/sd-status`'s `RESIDUE` tuple at `:965-995`, telling an
operator how to uninstall a Trellis or legacy footprint; `bin/sd_install.py:820`
and `:827` are the installer pruning its own empty parents, which the
criterion's own words allow; and `bin/sd_install.py:961` is an error message
reading "Untrack it (git rm --cached) and re-run", which is neither a code
path nor a temporary path. So deleting `sd_sweep.py` and the `parked`
handling clears **zero** of the eight, and a criterion phrased "names
nothing" cannot go green — while this page's own ordering makes a green suite
a precondition of all eight merges.

**The cut that would clear five of them is in requirement 13 and in no pull
request.** `prd.md`'s removal list carries "the residue detectors
(`bin/sd-status:960-1018`) after one clean run across the fleet", which is
the `RESIDUE` tuple and `residue_section` together. That range holds five of
the eight grep hits. Three things follow. The cut is **gated** on a clean
fleet run that nothing in this item schedules, so it cannot be assumed. It
appears in **no pull request** on this page, so requirement 13's own list has
an entry with no landing site — which criterion 31, closing that requirement
line by line, does not catch, because `residue` is not among the symbols it
greps. And a criterion 21 written against the post-cut tree would be red from
PR 2's merge until a fleet run that may never come.

So the grep becomes an enumerate-and-freeze over both states: the eight lines
today, the three that remain if the detectors go, and an assertion that the
set has not grown and that no hit is a sweep or park code path. Even at three
the grep is not empty — `bin/sd_install.py:961` is an error message, not a
temporary path — so "names nothing" is unreachable in either state.
`bin/sd-status`'s `RESIDUE` tuple and `bin/sd_install.py` join this pull
request's Touches for that reason, and the residue detectors are carried here
as a **deferred cut**: named, gated, and not performed by this pull request,
so requirement 13's list has an entry that a reader can find. Criterion 31's grep covers
the symbols but not the deletion verbs, and PR 7 — which was given criterion
21 alone — touches no code and cannot remove a code path.

## PR 3 — the checks that cannot fail

**Touches:** `Makefile`, `.github/workflows/`, `.github/scripts/` — which
is not `.github/workflows/` and holds `check-installer-coverage.sh`, the
gate `make test` actually runs at `Makefile:23`, and
`check-bash32-syntax.sh`, invoked at `Makefile:74` and by the `bash32` job
whose header is `.github/workflows/tests.yml:101`; `.coveragerc`, which has
**two** `include` keys and the edit is to the first: `[run] include` at
`:11-13` carries `bin/sd_install.py` **and** `.github/scripts/*.py`, while
`[report] include` at `:21-22` carries `bin/sd_install.py` alone and
`fail_under = 100` sits beside it at `:24`. Criterion 15 asks that the
coverage floor apply to `bin/sd_install.py` and no other file; `[report]`
already satisfies it, so the file that changes is `[run]`'s `:13`. An earlier
draft cited `:11-24`, one range spanning both sections, and put `fail_under`
inside the `[run]` list — which would point an implementer at the wrong one
of two identically-named keys. Also `tests/test_loc_caps.py`, which holds the
four ceilings at `:61`, `:62`, `:101`, `:109` and `assert_cap` at `:193-203`,
whose `assertLessEqual` at `:195-202` is the fail-the-suite line, so it and
not the `Makefile` is what turns a failing cap into a warning; and the three residue paths,
`tests/test_selector_contract_drift.py`, `generated/registry-snapshot.json`
and the `plugins/sd` directory.

`sd-docs-lint`'s no-database rules move into `make check`, conditional on
`docs/work/` existing — it runs in no Makefile target and no workflow
today, which is a check that cannot fail. The `Makefile` asks the lint which
rules those are rather than naming a range, and a test asserts the two sets
are equal. An earlier draft wrote "rules 1 through 4", which would have left
criterion 33's rule 7 — added in PR 7, after this pull request — present in
the lint and run by nothing, which is the same defect this pull request
exists to remove. The 100% coverage floor stays for
`bin/sd_install.py`, which writes under the operator's home, and is dropped
everywhere else. `MIGRATE_CAP` remains enforced for temporary migration tools.
The retired `BIN_CAP` and dashboard ceilings remain in `CEILING_HISTORY`.
`make check` gains a changed-files fast path with
the full suite once before a push. The `bash32` job is cut, the `security`
job folds into `lint`, and the three residue files are deleted.

**Retired ceilings remain evidence.** Their histories stay in
`CEILING_HISTORY`. `MIGRATE_CAP` remains a live gate.

**Verification.** Criteria 14, 15, 16, 17 and 30.

## PR 4 — the instruction layers stop contradicting each other

**This numbered unit is one pull request plus three landings that cannot be
one.** Criterion 19's subject is `~/.claude/settings.json`, which is under
the operator's home and in no git repository; criterion 23 deletes the
writing repository's `.claude/settings.local.json`; and the system
repository's guide is `system`'s. (2026-09-14: the override criterion 23's
second half closed on is not `.claude/settings.local.json`. It is the `## Style`
section of that repository's tracked `CLAUDE.md` and its tracked
`.caveman/config.json`, both deleted by `sd-writing-pack` #41 at `be76962e` and
read through GitHub. On that `main`, `.claude/settings.json` has no `caveman`
and no `settings.local.json` is tracked. An untracked local
`.claude/settings.local.json` was not read; the operator can run `grep -c
caveman` on it if it exists.) The page's framing — each numbered unit is
one pull request whose merge carries `Item:` — does not hold for those three,
and an earlier draft added them to this list without reconciling it. So: the
governed-tree files, `CONTRIBUTING.md` and `WORKFLOW.md` are **this
repository's pull request**, which carries the trailer; the writing
repository's override is its own one-line pull request there; the system
repository's guide is its own pull request there; and the global settings
file is an operator edit recorded on the item, because it is in no
repository and no pull request can carry it. Criteria 19 and 23 are recorded
against those landings and not against this repository's diff. PR 8 carries a
smaller version of the same shape for the writing repository's manifest.

**Touches:** the nineteen governed-tree files that carry the forbidden
strings, enumerated below; the global settings; `CONTRIBUTING.md`; the
system repository's guide; `WORKFLOW.md`; `README.md`, for criterion 12,
which C-95 said was addressed and was not; `skills/sd-ship/SKILL.md`,
`skills/sd-handoff/SKILL.md`, `bin/sd-review`, `bin/sd-status` and
`skills/sd-review/SKILL.md:80`, whose "github-kind backends `copilot` and
`greptile`" sentence the grep also returns and which an earlier
four-surface enumeration missed; and the writing repository's style override,
which criterion 23 deletes and which no Touches list named.

**`bin/sd-review`'s copilot rows are inside the table PR 6 deletes**, at
`bin/sd-review:238-243` within `BACKENDS` (`:193-248`), with `greptile` at
`:244-247` and `:248` closing the tuple. The two pull requests
were unordered and edit the same lines in opposite directions. PR 6 lands
first, so criterion 9's edit lands on the registry and the skill page rather
than on rows that no longer exist; the ordering section states it.

**The Trellis removal is nineteen files, not three.** Criterion 18 demands a
governed-tree grep for `Trellis`, `.trellis` and `task.py` return nothing.
The governed tree is `bin/`, `skills/`, `templates/`, `dashboard/`,
`tests/`, `.claude/`, `.github/`, `CLAUDE.md`, `AGENTS.md`, `README.md` and
`docs/spec/`. Grepping exactly that set on 2026-09-05 returns:

```
.claude/sd-ai-command-pack/planning-adversarial-review.md
.github/PULL_REQUEST_TEMPLATE.md
.github/copilot-instructions.md
AGENTS.md
bin/sd
bin/sd-status
bin/sd_setup_github.py
dashboard/sessions.py
dashboard/work.py
docs/spec/backend/error-handling.md
docs/spec/backend/index.md
docs/spec/backend/manifest-and-filesystem.md
docs/spec/backend/quality-guidelines.md
docs/spec/guides/code-reuse-thinking-guide.md
docs/spec/guides/cross-layer-thinking-guide.md
docs/spec/guides/index.md
skills/sd-plan/SKILL.md
tests/test_sd_agents.py
tests/test_sd_status.py
```

Two of them are test files and seven are `docs/spec/` pages. An earlier
draft named "the routing block" and `.claude/rules/`, and **neither carries
a hit**: `bin/sd_route.py` is clean, while `bin/sd`, `bin/sd-status` and
`bin/sd_setup_github.py` are not, and the `.claude/` file with hits is
`.claude/sd-ai-command-pack/planning-adversarial-review.md`. So the old
scope covered one of nineteen.

**The governed tree names a directory that does not exist.** Criterion 4's
definition lists `templates/`; there is no top-level `templates/` here, and
the templates live under `skills/*/templates/`. The grep above skips it
without error, so the criterion passes today for the wrong reason. Recorded
in the `prd.md` log; the definition is a criteria-list edit.

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

**Verification.** Criteria 9, 18, 19, 22 and 23, plus criterion 12.
Criterion 9 needs `WORKFLOW.md` to state that Copilot review is off on
repositories the operator pays for personally, so `WORKFLOW.md` is in the
Touches list above; criterion 12 needs `README.md`, which is now in this pull request's Touches
above. Two corrections to an earlier draft. The writes-nothing claim is the
repository `README.md`'s "**What it writes in a repository:**" paragraph —
quoted at `prd.md:871` — and not the rendered-copies paragraph above it; an
implementer following the old citation would have edited the wrong paragraph
and left the claim unscoped. Named by its heading rather than by a line: the
line number this sentence used to carry was both stale and mis-resolved,
because a bare filename with no directory component was read against the work
root, where a different seven-line `README.md` lives. Rule 6 now fails that
shape by name. And criterion 12 has a
second half that appeared in no pull request at all: `README.md` must also
**list the skills that write tracked files** (`prd.md:1405-1406`). Both
halves land here. C-95 recorded this criterion as addressed; it was not,
and the rewrite documented the split instead of closing it.

## Slice 2, PR 5 — skills install because a path names them

**Touches:** `skills/paths.json` (new), `contrib/`, `bin/sd`,
**`bin/sd_install.py`** and `tests/`.

**The installer is the operative verb of both criteria this pull request
claims, and two earlier Touches lists held none of its code.** Criterion 24
is "**the installer renders** exactly the union of the paths plus active
trials, asserted by a test that adds an unlisted skill directory and sees
`make check` fail", and "`contrib/` exists and **the installer never renders
from it** without a trial row". Criterion 25 is "**the next install run**
after expiry with no `skill_use` rows removes the skill and says so". The
installer is `bin/sd_install.py`, whose `:224-229` enumerates
`skills/sd-*/SKILL.md` from disk today — the exact behaviour the paths file
replaces. The three-file list covered the data file, the trial directory and
the `sd skill try` subcommand, and none of the code whose behaviour the
criteria assert. Recorded as C-121 and marked addressed in the round-three
ledger; the prose beneath was rewritten to answer a different half of that
finding and the list it named was left alone.

`skills/paths.json` naming three paths, with every directory under them
accounted for, and `sd skill try <name>` installing from `contrib/`,
writing a trial row with an expiry and printing the date.

**This pull request needs rows, and an earlier draft said it did not.**
Criterion 24 requires the installer to render "exactly the union of the
paths plus **active trials**", and that `contrib/` exists and the installer
"never renders from it **without a trial row**" — both are row reads.
Criterion 25 requires `sd skill try` to write the trial row and print the
expiry, "both asserted by tests against a temporary database", and the
printed date *is* the row's expiry, so the install half is not observable
without the row. The earlier split into a PR 5 install half and a PR 8
trial-row half would have landed `paths.json` rendering three static paths
with no trials concept, and criterion 24's test would then have had to be
rewritten in PR 8, a pull request that did not claim it.

**Verification.** Criteria 24 and 25 whole, against a temporary database.

### What landed

`skills/paths.json` names three paths — research, "sources to brief to
handoff"; development, "plan to build to ship"; act, "brief to draft to
send" — covering thirty-two skills. The other forty-nine moved to `contrib/`,
in git and not installed, `sd skill try` away. The tight reading, on the
operator's word: C-180 carries the choice and the warrant.

`bin/sd_install.py` renders the union of what the paths name and what has an
active trial row, falling back from `skills/<name>` to `contrib/<name>` for a
trial. A directory on no path, or a path naming a directory that is gone,
refuses the install and says which. `bin/sd_skill.py` is the `sd skill`
verb group: `try` writes a thirty-day trial row and prints the date, `list`
shows what is on the paths and what is not.

Four things this pull request found rather than built, each with a ledger
entry: the library had no trial readers (C-178); its `record_skill_use`
stamped `now()` and could not be told when a use happened (C-179); retiring
a skill became two edits and three tests were written for one (C-181); and
the `sd_db` installer step had to move here from PR 7 because criteria 24
and 25 cannot be verified without it (C-177).

**Two defects the suite found in this pull request's own code, both from
making one thing of two.** `cmd_user` called `provision_library`, so every
render shelled out to `pip` — which in a parallel test run replaced `sd_db`
in site-packages underneath a shard importing it, and surfaced as
`ModuleNotFoundError: No module named 'sd_db.testing.home'` in a file that
touches neither. Rendering skills must not rebuild the virtualenv it renders
from; `--provision-library` is the only door, and `make setup` is its one
caller. Then `--provision-library`'s exit code read its own prose —
`"installed" in report` — and `"sd_db not installed, trials unavailable"`
contains it, so the one machine the exit code exists for returned zero. The
function returns a flag and a line now, and the line is only prose.

Three tests changed their premise rather than their expectation.
`test_sd_restore.WithoutTheLibrary` held by stripping `local-sd-db` from
`sys.path`, which stopped meaning anything once the installer put a built
copy in site-packages; it blocks the import by name now, with a test that
the block itself works, because both refusals it asserts can be raised for
other reasons. `test_skill_frontmatter` and `test_sd_skill_adopt` read both
roots: `paths.json` decides what installs and decides nothing about what is
well formed, and a `contrib/` skill is one command from a reader's machine.
`test_selector_contract_drift` scans `contrib/` for the same reason.

**Verified.** `make check`, exit 0: 1267 tests, installer coverage
`687 statements, 0 missed, 256 branches, 0 partial, 100%`, ruff and mypy
clean, `sd-docs-lint: clean`.

## Slice 2, PR 6 — the registry reader, the tiered path, the protection

**Touches:** `bin/sd_lib.py`, `skills/sd-ship/`, the provider registry
reader, and the four files criterion 6 and the installer step require that
an earlier draft omitted when C-90 moved the criterion here without its
scope: **`WORKFLOW.md`**, because criterion 6's *first* clause is that the provider
registry format "is documented in `WORKFLOW.md` with the role vocabulary
`author` and `reviewer`" (`prd.md:1235-1237`) — a documentation obligation an
earlier rebuild skipped while deriving this list from the criterion's runtime
clauses, and the reason PR 1 lands first; `bin/sd-review`, whose `BACKENDS`
table is at **`:193-248`** with `DEFAULT_POLICY` at `:260` and its `tiers`
dict at **`:262`** — an earlier draft said `:200-266` with `tiers` at `:265`,
a range that begins inside the *second* entry and so omits the `codex` row
criterion 6 names most often, and ends eighteen lines past the table inside
`DEFAULT_POLICY`, so deleting it would leave the provider table's head and
remove the tier lists instead; `.github/sd-review.json`, carrying `tiers` at `:4`,
`challenge_providers` at `:30` and `planning_providers` at `:31`;
`bin/sd_install.py`, where `DEFAULT_BLOCK_BODY` at `:766-772` writes the
block and where the `reviewers` consent line lands — the `sd_db` installer
step is criterion 13's and is PR 7's, not this one's; and `bin/sd`, for `sd attribute`. For criterion 10, also
`bin/sd-docs-lint`, which holds rule 5 and is the only file besides
`skills/sd-ship/SKILL.md` and `tests/test_sd_docs_lint.py` carrying the
`none - ` form, and `bin/sd_setup_github.py`, the other file naming rule 5.
And `README.md`, for criterion 11's closing sentence — see below. And
`skills/sd-review/SKILL.md`, which stood in no pull request's Touches while
documenting exactly what criterion 6 deletes: `codex_preflight` at `:66-72`,
the `BACKENDS` table at `:74-80` — naming `prism` and `gito` as shipped,
which requirement 3 removes — and the tier policy at `:82-88`.

**Criterion 5's vendor clause is here, whole.** All thirty-two bare vendor
tokens across eight files convert to the role vocabulary in this pull
request, because a role only resolves once this pull request's registry
reader exists: `skills/sd-handoff/SKILL.md:73,84`,
`skills/sd-plan/SKILL.md:40`, `skills/sd-propose-skills/SKILL.md:100`,
`skills/sd-research-repo/SKILL.md:84`,
`skills/sd-research-repo/references/conventions.md` (eleven),
`skills/sd-research-repo/templates/CLAUDE.md` (seven),
`skills/sd-review/SKILL.md` (five) and `skills/sd-ship/SKILL.md`'s `--agent
claude|codex` at `:141,150-151,212` (five). PR 1 lands the review table
those files read their caps from and removes criterion 4's lane; it converts
no vendor token.

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

**Verification.** Criteria 2, 3, 6, 10, 11 and 32. **Not the `sd_db`
installer step**, which is criterion 13's clause and PR 7's; an earlier draft
claimed it here and in PR 7 both, and called it "item B's criterion 13", which
is a dashboard criterion in B's slice 4. Criterion 6 is the largest of them — requirement 3's
whole runtime, listed under PR 1 above where it used to be filed — and
criterion 11's six mode-detection cases run against the fixture remotes B's
harness provides. Criterion 32 is the one that has to hold in both worlds: before B's library is installed, the
file-only reader and, once it exists, the library resolver must return the
same reviewer order from the same `providers.yaml`.

**This pull request needs `BIN_CAP` moved, and cannot move it.** No Touches
list above noticed that `bin/` is capped. It stood at 13,307 on `main` against
14,000, and this pull request's first half — `bin/sd_registry.py` and the
installer's registry seed — measures +559, which leaves 134 lines for the
reviewer chain, `sd attribute`, criterion 11's predicate, the `url` client and
the consent prompt. `tests/test_loc_caps.py:11-12` forbids raising a cap in the
pull request that busts it, so the re-derivation is its own change, landing
first and touching nothing under `bin/`: R11-D31, 14,700, itemised in
`prd.md`'s log. That change is a precondition of this one in exactly the way
B's fixture harness is, and belongs in the ordering section below rather than
being discovered again by whoever runs `make check` next.

## Slice 2, PR 7 — the `docs/work` retire step

**Touches:** the migration's retire step (B's command), every `prd.md`
under `docs/work/` outside the archive, and — for criterion 13, which the
closure table filed here while this list reached none of it —
`bin/sd_lib.py`, `bin/sd-status` and `bin/sd-docs-lint`, which derive an
item's status from its row (`prd.md:1407-1408`) — and, in `bin/sd-docs-lint`
alone, `item_directories`, `check_shape` and **`check_ready`**, for rule 1's
archive predicate below and for rule 2, which stops matching anything when
the `status:` lines go — `check_ready` returns early on
`if status not in WORKABLE_STATUSES: continue` (`bin/sd-docs-lint:141-143`),
so the retire commit switches off three checks for every active item in every
registered repository unless rule 2 reads the row; B's criterion 7 carries the
clause and B's round fifty-five carries the fixture. Plus **rule 7 and its two
tests**, criterion 33's dangling-reference
scan, which lands here because this pull request creates
`docs/work/.status-source` and that marker is one of the three references in
the tree that does not resolve until it does; `skills/sd-ship/` and
`dashboard/`, for `sd-ship --deliver`, the hand-merge reconciliation, the
notes on the squash commit and `deliver` on the item screen
(`prd.md:1450-1464`) and the three kill-and-reconcile tests
(`prd.md:1485-1494`); and `bin/sd_install.py`, for the `sd_db` step
(`prd.md:1541-1547`).

B's one sitting for `docs/work`: freeze, import once more, verify, snapshot,
then remove every item's `status:` line outside the archive in one commit.

**Three things land in that commit and in this pull request that an earlier
draft of this page named nowhere.** All three come from item B's criterion 7,
enumerated clause by clause in B's round five, and each is a pack file no
`system` pull request can reach.

*The tracked marker.* `prd.md:582` and `prd.md:2632` both say the retire
commit adds `docs/work/.status-source`, one line, `row`. This page named
`status_source` — the column — and never the file. It is what a checkout
without a database reads, so it lands in the same commit as the removal, not
after it.

*The lint's sign changes outside the archive, and rule 1 gains a signature to
tell the two apart.* `bin/sd-docs-lint` rule 1 fails today when a `status:`
line is **missing** (`bin/sd-docs-lint:121-123`,
`if status not in ITEM_STATUSES`). `B/prd.md:1251-1252` requires it to fail
when one is **present** in a `prd.md` under `docs/work/` outside the archive,
asserted with one seeded. **Both signs must hold at once**, and an earlier
draft of this paragraph said they could not: rule 1 iterates
`item_directories`, whose own docstring is "Every work item, active or
archived", and archived items keep their `status:` line because they are
records of what was. `git grep -l '^status:' -- 'docs/work/archive/*/*/prd.md'`
returns **487** on 2026-09-05, every one of which a naive inversion would
fail on the retire commit. So this is not a sign flip. `item_directories`
returns a flat list with no marker, so `check_shape` must be given the
distinction — either two enumerations or `(path, archived)` pairs — and then
keeps `if status not in ITEM_STATUSES` for items under `docs/work/archive/`
and gains a failure for a `status` key present outside it. That signature
change is `bin/sd-docs-lint` work in its own right. The Touches entry above
names that file only for deriving an item's status from its row; rule 1's
archive predicate and the `item_directories` signature are a second reason,
recorded here so the implementer does not read the entry as covered. It
still lands in the commit that removes the lines, since the window between
two merges is what the ordering exists to avoid.

*`sd-ship` writes `shipped_at` and a `Closes:` trailer on a merge.*
`B/prd.md:910-912` names three writers of `shipped_at` and gives the merge to
`sd-ship`; B's clause 7.18 asserts a cancel writes `done` with a `cancelled`
note and that the next `sd-ship` merge carries `Closes:` with no `Delivers:`
and no extra pull request; clause 7.21 asserts a merge confirmed through the
fixture remote writes `done` with `shipped_at` and one `status_change` note;
and B's clause 15.25 asserts the field does not move on a second merge.
Neither string appeared anywhere in this item before B's round five.
`skills/sd-ship/` is already in this pull request's Touches for
`--deliver`.
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

**Verification.** Criteria 13 and 21, and **item B's criterion 7 clauses
this pull request builds**: the retire itself (7.1, 7.3), the seeded-line
lint failure (7.2), `sd_lib.delivered` refusing under a pack that lacks it
(7.4), the marker and `status_source` read by a checkout with no database
(7.6), the retained worktree's line ignored (7.7), the sitting's two
kill-and-rerun points (7.8), and `sd-ship`'s `Closes:` and `shipped_at` on a
merge (7.18, 7.21, and B's clause 15.25's `shipped_at` half). B records these
as hand-offs 11 and 12 with the note that this plan did not schedule them;
it does now. Criterion 13 is recorded as waiting
**before the second slice**, not before this one: `prd.md:1197-1198` says
"Before the second slice, criteria 13 and 32 are recorded as waiting" — and
"before the second slice" means before slice 2 opens, not before every pull
request inside it. This pull request is **in** slice 2, as its heading says:
this item's landing order defers to B's (`prd.md:1181-1185`), and B's slice 2
at `B/prd.md:1144-1147` is where "`docs/work` and the register retire … in
the run that lands their writers". An earlier draft moved the boundary a
slice later and said the landing order said so "in those words"; a later one
argued the point by calling this the third slice, which contradicted the
heading above it and B's numbering both. Criterion 32 is covered by
the same sentence, and neither this pull request nor PR 6 noted it.

## Slice 2, PRs 8a to 8d — rows for uses, suggestions, promotion and handoff

**PR 8 is four pull requests, not one, from R11-D42 on 2026-09-07.** Priced
whole against built analogues it came to 2,592 lines of `bin/`, a 16.5% raise
in one step for scope a month out, which is what R11-D15's clause exists to
refuse. The four criteria are near-independent and the split costs nothing —
2,593 across four against 2,592 together, because no seam is crossed twice.
Each slice is preceded by its own `BIN_CAP` re-derivation, and only the slice
about to be written is funded. The earlier single-PR heading, its combined
Touches list and its "Verification: criteria 26, 27, 28 and 29" are superseded
by the four below; what that draft got right is preserved in each.

**Order: 8a (26), 8b (29), 8c (27), 8d (28).** Forced once and only once: the
installer's move from one hook event to five is +55 shared by all four new
hooks, and 8a pays it so 8b rides free. 8d is last because two of its clauses
answer to files outside this repository.

### PR 8a — criterion 26, the two hooks and the Codex nightly

**Touches:** `bin/sd-skill-use` (new), `bin/sd_codex.py` (new),
`bin/sd_install.py`, `bin/sd` for the `sd skill scan` entry, and the scheduler
that runs the nightly, which is in neither `bin/` nor this repository —
`.github/workflows/` holds two files and neither is scheduled.

**Funded: 976, `BIN_CAP` 15,750 to 16,750 (R11-D42). Body delivered: 650
against 663 reserved, measured across the merge at `6b36e3ec`.**
`bin/sd-skill-use` came in at 243 against 240; the installer's move to a
plural hook table at +39 against +55; `bin/sd_codex.py` at 349 plus 19 for
the verb, against 368. `bin/` went 15,749 to 16,399. Neither reserve was
touched: 238 of seam and 75 of post-report went unspent, which is what
R11-D43 re-derives from. What is left of the criterion is the scheduler,
which this repository cannot hold, and the OpenCode plugin, which waits on that surface being in
use.

`skill_use` is not new. The table is declared at `sd_db/schema/001_initial.sql:126-133`
with exactly the columns the criterion names — `timestamp`, `skill`, `surface`,
`mode` under a `CHECK (mode IN ('direct','path'))`, `cwd` — and the writer is
`sd_db/writes.py:530` `record_skill_use`, whose own docstring at `:541-545`
already names both producers this criterion asks for. Nothing in the pack calls
it: the only callers are `tests/test_sd_skill.py:171` and `:184`, and both pass
`skill` and `timestamp` alone. **What is built here is the two producers, not
the row.**

**One hook file and not two.** `PreToolUse` and `UserPromptSubmit` differ only
in how the skill name comes off the payload. Two files would duplicate the
header, the library open, `resolve_root` and `main` — 132 of the body — to save
an eight-line branch. The hook must exit 0 silently on every internal error,
which is why its library open takes the `return None` form of
`bin/sd_registry.py:161-167` and not `bin/sd_restore.py:54-67`, whose refusal
prose a hook may not print.

**There is no recorded-session fixture anywhere.** `tests/fixtures/` holds two
provider files. The closest built thing is `tests/test_sd_handoff_restore.py:123`,
which constructs a hook payload inline rather than replaying one. Both fixtures
this criterion needs are new, and `tests/` answers to no line cap.

### PR 8b — criterion 29, continuity that survives a kill

**Touches:** `bin/sd-handoff-restore`, `bin/sd_handoff_rows.py` (new),
`bin/sd-note` (new). **No `bin/sd_install.py`, no `bin/sd-handoff-prompt`, no
new hook registration** — see the cut below. Nothing under `sensitive` in
`.github/sd-review.json` is touched.

**Priced 573 and funded by R11-D43, which raised `BIN_CAP` to 17,000 off a
measured 16,399 base.** 422 of body, 119 of seam for the `PreCompact` and
`SessionEnd` payload contract, 32 of post-report at 7.6%. Down from R11-D42's
836: glue is 2.10 lines per boundary at this module size rather than a flat
2.9, the note rows are priced as a caller of built writes rather than as a
seam, and `bin/sd_install.py` costs +2 because 8a made the hook table plural.

**This is a rewrite of where continuity comes from, not a wiring job.** Today
`bin/sd-handoff-restore` injects a JSON packet that exists only if someone ran
`bin/sd-handoff` by hand, and nothing calls that automatically. The criterion's
test writes three followups *through the library*, ends the session without
calling `sd-handoff`, and asserts all three arrive — so the row has to become a
source the hook reads, beside the packet. `run` returns 0 at `if not
path.is_file()`, which is the line the test hits first.

`add_note` with `kind='followup'` already exists (`sd_db/writes.py:335`; the
vocabulary is the SQL `CHECK` at `001_initial.sql:66-69`) and **has no caller
anywhere in this pack.**

**A suffixless file cannot be imported.** `bin/sd-handoff-restore` and a
followup writer cannot share code directly, so the item resolver and the row
reader go in `bin/sd_handoff_rows.py`, which both import — one header paid once
instead of a reimplementation. `tests/test_sd_handoff.py:334-339` bans
`sd_lib`, `import requests` and `from installer` from `bin/sd-handoff` **only**;
there is no equivalent assertion on the restore hook, which may therefore
import both `sd_lib` and the new module.

**`bin/sd-handoff-prompt` is cut, and its 119-line seam with it, for two
independent reasons found while building.**

1. **A shipped skill rule already forbids it.** `skills/sd-handoff/SKILL.md:102`
   reads "Never write a packet automatically. **No SessionEnd hook, no
   PreCompact hook**, no 'I'll snapshot this just in case'. Writing stays an
   explicit act, because auto-writing every session is exactly how the journals
   started." The plan above was written without reading it.
2. **Neither event can inject context, so the prompt could not arrive.**
   Measured against Claude Code 2.1.263: the `hookSpecificOutput` union carries
   `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`,
   `SubagentStart`, `SubagentStop` and fourteen more, and `PreCompact` and
   `SessionEnd` are in **none** of them. `PreCompact`'s only lever is refusal
   ("compaction blocked by PreCompact hook; continuing uncompacted") and
   `SessionEnd` carries a `reason` and no output path at all. A hook printing
   `additionalContext` on either would be silently discarded — which is the
   failure mode the 119 was reserved against, arriving before a line was
   written.

**The criterion does not need it.** Clause 29 says the session "ends without
calling `sd-handoff`" and asserts the followups arrive. Rows are the source;
the packet is not involved. `bin/sd-handoff-restore` is already registered on
`SessionStart`, so the read needs no new registration — which is why
`bin/sd_install.py` drops out of the Touches list and this slice touches no
sensitive path.

**What replaces the automatic write is an explicit one.** `bin/sd-note add`
writes a followup row as it is named, which is an explicit act and so is not
what SKILL.md:102 forbids. A row survives a kill because it was never in the
session.

**Delivered: 324 against 573 funded**, `bin/` 16,399 to 16,723 at `BIN_CAP`
17,000, all three figures counted from git. `bin/sd_handoff_rows.py` 170
against 120, `bin/sd-note` 116 against 106, the `sd-handoff-restore` delta +38
against +32; `bin/sd-handoff-prompt` 162 and the 119 seam unspent. The three
body spans overran by 66 together and the cut returned 281.

**One defect found and fixed in the delta itself.** Reading the rows before the
packet's `if not path.is_file(): return 0` was not enough: six further refusal
paths in `run` returned straight out, so a corrupt packet, or one written for a
different project, silently dropped followups that had nothing to do with it.
The packet half is now `packet_section`, which returns its context or its
refusal as a string, and `run` emits once with the rows appended. Asserted by
`test_a_bad_packet_does_not_take_the_rows_with_it`.

### PR 8c — criterion 27, promotion and demotion

**Touches:** `skills/paths.json`, `contrib/`, `skills/`, `bin/sd_skill.py`,
`bin/sd` for the two subparsers, and `dashboard/` only in that the dashboard
must **not** be where the pull request is opened. R11-D44 removes
`bin/sd_lib.py` from this list: the git runner the openers need is
`sd_lib.git_output`, and it is already public at `bin/sd_lib.py:143`. Nothing
under `.github/sd-review.json`'s `sensitive` list is crossed.

**Priced 288 and funded by R11-D44, which raised `BIN_CAP` to 17,050 off a
base of 16,723 measured on `main` after PR 8b merged at `05adec9e`.** 204 of
body, 8 of glue, 40 of seam, 24 of body variance, 12 of post-report at 5.7%.
Down from R11-D42's 417, and the difference is two corrections.

`skills/paths.json` exists and has readers only — `bin/sd_install.py:253` and
`bin/sd_skill.py`. **Nothing writes it programmatically.**

**R11-D42 priced promotion and demotion as two functions on the
`install_hook` / `remove_hook` precedent, and R11-D44 does not.** That pair at
`bin/sd_install.py:536` and `:608` is 72 and 76 lines, and reading it shows the
cost is not the two directions. It is that `~/.claude/settings.json` is
somebody else's file: idempotence against a second `--user` run, interleaving
against another installer, refusing rather than overwriting a file that will
not parse. `skills/paths.json` is this repository's own tracked file with a
validating reader already at `bin/sd_install.py:265`, so none of the three
transfer. What differs between the directions is the move and the edit; the
branch, the commit, the push and the pull request are identical.

**The seam is 40, not the flat 119 R11-D42 charged for `git push`.** Write-side
git is already built — `git commit` at `bin/sd_lib.py:1227` — and so is
network git, `git fetch` at `bin/sd_lib.py:1343` and `:1349`, both through
`sd_lib.git_output` at `:143`, which takes arbitrary argv behind a timeout, no
shell and a failure-is-None contract across 30 call sites. What is genuinely
uncrossed is narrower and is not the push: **no `gh` call in `bin/` has ever
sent a non-GET method or a request body.** `gh_api` at `bin/sd_lib.py:269` is
read-only and every `gh_json` caller at `bin/sd-pr-state:117` reads. Opening a
pull request is the pack's first write to GitHub from `bin/`, and needs a
refusal vocabulary a read does not have — a rejected push, a pull request that
already exists, an unauthorised `gh`, the last already written at
`bin/sd-pr-state:166`.

**Built in `bin/sd_skill.py`, not a new module**, because `sd skill promote`
and `sd skill demote` join `try`, `list` and the nightly under one verb group
and reuse `SkillRefusal`, `checkout()`, `available()`, `CONTRIB_DIR` and
`SKILLS_DIR`.

| span | priced |
|---|---|
| `paths_edit`, both directions | 34 |
| `branch_and_open`, the shared half | 66 |
| `promote` | 36 |
| `demote` | 34 |
| `bin/sd`, two subparsers | 22 |
| docstring and banner | 12 |
| glue, four boundaries at 2.10 | 8 |
| seam, the first `gh` write | 40 |
| body variance at 12% | 24 |
| post-report at 5.7% | 12 |

`branch_and_open` carries a dirty-tree refusal, so the commit sweeps in no
unrelated work. `demote` carries a real branch for a skill on two paths, which
`skills/paths.json`'s own `$comment` says is allowed. `paths_edit` loads the
whole document rather than `read_paths`'s `data["paths"]`, or the `$comment`
block is destroyed on write.

**Delivered 172 against 288 funded**, `bin/` 16,723 to 16,895 at `BIN_CAP`
17,050, all counted from git. `bin/sd_skill.py` goes 151 to 306 with ten
top-level definitions, and `bin/sd` gains 17 lines of subparser.

| span | priced | delivered |
|---|---|---|
| `paths_edit` | 34 | 36 |
| the shared opener, `move_in_a_pull_request` | 66 | 68 |
| `skill_promote` | 36 | 9 |
| `skill_demote` | 34 | 8 |
| `_sibling`, unpriced | — | 18 |
| `bin/sd` | 22 | 17 |
| docstring and banner | 12 | 4 |

**The two ends came in at 9 and 8 against 36 and 34, because the split moved.**
The derivation put validation in the ends and the rest in the middle, which was
right, and then left the move and the clean check in the ends where each would
have been written twice. Passing `promoting` as a parameter pulled both into
the shared half, which grew by 2 to absorb them. What is left in each end is
the three questions that differ: does the source exist, does the target already
exist, and which path names it.

**`_sibling` at 18 is what the 40 of seam actually bought.** The write is ten
lines, because `gh api --method POST` goes through `gh_json` unchanged exactly
as R11-D44 predicted. Reaching `gh_json` costs a loader, because
`bin/sd-pr-state` has no `.py` suffix. `bin/sd-status:97` carries the same
eighteen lines for the same reason; a third copy is the argument for moving it
into `sd_lib`, and two copies is not.

**Verification.** `make test` exit 0, 55 `OK` blocks. `make check` exit 0, `No
findings to report`. Nineteen tests in `tests/test_sd_skill_promotion.py`, and
seven mutations all caught under `PYTHONDONTWRITEBYTECODE=1`.

### PR 8d — criterion 28, suggestions that file nothing

**Touches:** `skills/sd-suggest/`, `contrib/sd-propose-skills/`, `bin/sd`,
`bin/sd_suggest.py` (new), `bin/sd_shadow.py` (new), and the writing
repository's manifest, which is not in this checkout.

**Priced 330 and funded by R11-D45, which raised `BIN_CAP` to 17,250 off a
base of 16,895 measured on `main` after PR 8c merged at `17d80480`.** 244 of
body, 12 of glue, 0 of seam, 63 of variance, 11 of post-report at 4.5%. Last,
because two clauses answer elsewhere.

R11-D42's 364 and this 330 are close, which hides that almost nothing in them
agrees: it carried 327 of body and 37 of post-report at R11-D38's rate, and
this carries 244 of body, a variance reserve it had no line for, and a
post-report rate a fifth of the size.

**The seam stays 0, and PR 8c is why.** Every boundary here now has a built
crossing on the other side: `gh api --method POST` at `bin/sd_skill.py`,
the `gh_json` transport at `bin/sd-pr-state:117`, the suffixless import at
`bin/sd_skill.py`, and `sd_db.sync_shadow`.

| span | lines |
|---|---|
| `bin/sd_suggest.py` — header 45, `sd_db` frame 18, the row 30, `publish` 35 | 128 |
| `bin/sd_shadow.py` — header 32, `sd_db` frame 18, the wrapper 34 | 84 |
| `bin/sd`, two new groups and three verbs | 28 |
| `_sibling` into `sd_lib`, the third copy | 4 |
| glue, five boundaries | 12 |
| variance reserve at 26% | 63 |
| post-report at 4.5% | 11 |

**The variance reserve is sized to the worst overrun, not to the mean.** Three
observations now — 8a −2%, 8b +26%, 8c −19% — mean +1.7%, and a reserve at the
mean of a symmetric spread is too small half the time. The costs are not
symmetric: an underrun leaves budget unspent, an overrun busts the cap and the
clause forbids raising it in the pull request that busts it. So 26%.

**A correction to every earlier Touches list: the skill is at
`contrib/sd-propose-skills/`, not `skills/sd-propose-skills/`.** That directory
does not exist; PR 2 moved the skill into `contrib/`, and the lists were written
against the old path. The work is real — `contrib/sd-propose-skills/SKILL.md:94`
still carries `content-type: skill-proposal` and `:126` still names the retired
`skill-proposal-accept` routine — only its location was wrong.

**A correction to how `sd shadow sync` was scoped: only the verb is new.**
Earlier text called the whole command greenfield. `sd_db/shadow_sync.py:391`
`sync(connection, *, now, runner, tracker)` is complete and installed, exported
as `sd_db.sync_shadow`, and its module docstring settles the split in as many
words — "This module is the collector, not the command. `sd shadow sync` is a
verb and verbs live in the pack." The pack builds a wrapper, priced at 155 for
the group and the module together. `sync` calls only `collect`, `store` and
`write_watermark`, so the criterion's "the fixture saw no close call" is
**structurally satisfiable** rather than something the slice must enforce.

`sd suggest` is a verb group under `bin/sd` and not a `bin/sd-suggest`
executable, which the criterion decides for us: it must be no palette entry,
and a verb under `sd` is not an installed entrypoint while a standalone binary
is. The `sd-suggest` skill files suggestions through this verb group.
This slice extends that group. "Every mode" is `bin/sd_lib.py:33`
`MODES = ("full", "minimal", "guest")`: the row is
written in all three, and only `publish` is gated.

**Two clauses cannot close from this checkout, and this slice does not claim
them.** `commands.yaml` does not exist here — it is item B's, written by B's
dashboard — so the "no palette entry" assertion sits behind B's slice 4, as an
earlier draft already flagged. The writing manifest is another repository's, so
the `skill-proposal` removal reaches only the `contrib/sd-propose-skills/` half
from here. Flagged rather than quietly dropped, and the second of the two was
not flagged before.

**Delivered 228 against 330 funded**, `bin/` 16,895 to 17,123 at `BIN_CAP`
17,250, all three counted from git. 127 of headroom left standing.

| span | priced | delivered |
|---|---|---|
| `bin/sd_suggest.py` | 128 | 133 |
| `bin/sd_shadow.py` | 84 | 53 |
| `bin/sd`, two groups and three verbs | 28 | 37 |
| `sibling` into `sd_lib`, the third copy | 4 | +25 −20 = 5 |
| glue, five boundaries | 12 | — |
| variance reserve at 26% | 63 | — |
| post-report at 4.5% | 11 | 0 |

**`bin/sd_shadow.py` came in at 53 against 84 because the header priced a
module and the module is a wrapper.** The derivation charged 32 of header and
18 of `sd_db` frame on the analogues, and both were right for a module that
owns something. This one owns nothing: `_rows()` is five lines because
`bin/sd_handoff_rows.py` already carries the import refusal and the connect,
and `shadow_sync` is 22 because `sd_db.sync_shadow` returns a `Synced` whose
six fields are the report. What is left is a header of 24 that says which of
the two halves is which, and the rendering of one dataclass.

**`bin/sd` at 37 against 28 is the one overrun, and it is the `RowsRefusal`
handler.** Two groups and three subparsers were priced; what the price omitted
is that `sd_suggest` and `sd_shadow` raise a refusal class `bin/sd` had never
caught, because `sd_handoff_rows` was until now only read by a hook that
swallows everything. Nine lines, and they are the reason a bad `--item` prints
one sentence rather than a traceback.

**The variance reserve went unspent for the third time in four.** 8a −2%,
8b +26%, 8c −19%, 8d −31%. The mean over four is −6.5%, and the 26% reserve
sized to 8b's overrun is now the only observation of its kind. The next
re-derivation should say plainly that three of four slices have come in under
and consider whether the body prices, not the reserve, are what is high.

**`tests/test_sd_suggest.py` carries 25 tests in seven classes, and six
mutations were run against them.** `TheCriterion`
holds the four clauses as four assertions: the row written in each of
`sd_lib.MODES` with `gh` never asked about an issue, the refusal with no
`--to`, one list call then exactly one POST, and two open issues in with two
`shadow` rows out and no argv carrying `--method` or `close`. The fifth test
in that class is the `skill-proposal` removal, checked across the whole
`contrib/sd-propose-skills/` directory rather than `SKILL.md` alone — a
template moved to a sibling file would pass a one-file check and would still
be the writing path the row replaced.

**The `gh` here is a recorder on `PATH`, not `sd_db.testing`'s
`GitHubDouble`.** The double routes `/repos`, `/branches`, `/collaborators`
and `/pulls`; this criterion is about issues, which it does not serve. The
recorder logs one argv per line, which is what makes "it filed exactly one"
and "the fixture saw no close call" assertions about a list rather than about
a mock's call count.

**The `full` case needs no remote and no credential.**
`sd_lib.remote_permits_full` answers yes for a repository with no origin —
there is nobody to expose anything to — so the `full` third of the every-mode
test asks `gh` nothing at all, which is what lets the same test assert both
the row and the silence.

**Six mutations, all caught**: the `--to` guard removed, the dedup comparison
forced false, the mode hardcoded to `full`, the failed dedup read falling
through to a file instead of refusing, `--strict` ignored on a held cursor,
and the `RowsRefusal` handler deleted from `bin/sd`.

**One defect found by the code review point, and fixed in the delta.** The
nine lines of `RowsRefusal` handler this entry named as the overrun had no
test that would have noticed them going away. Every other reader of that
class is `bin/sd-handoff-restore`, a hook that swallows everything by design,
so nothing in the suite exercised the CLI path. `TheRefusalReachesTheOperator`
now runs `bin/sd` as a subprocess and asserts what an operator sees: exit 1, a
line beginning `sd: `, and no traceback -- plus one end-to-end write, so the
group is not a parser with no verb behind it. Deleting the handler fails two
of the three.

**Verification.** `make lint` exit 0 after one fix — ruff `I001` on the new
`import sd_shadow` / `import sd_suggest` block in `bin/sd`. `make test` exit
0, 56 `OK` blocks. `tests/test_loc_caps.py` passes with `bin/` at 17,123
against 17,250.

## Two things about the criteria list itself

**Criteria 31 and 32 are out of order in the `prd.md`.** 30 is at line
`1595`, 32 at `1596` and 31 at `1606`. Nothing depends on
it and no test reads the order, but a reader working down the list will hit
32 where they expect 31 and wonder what they missed. It is a `prd.md` edit,
noted here rather than made silently. **This paragraph got the numbers wrong
twice.** A first draft cited 1580 and 1590, which fall mid-body of criteria
29 and 32. The correction of that draft cited 1591, 1592 and 1602 — all
three off by four, and 1592 and 1602 again land mid-body of criteria 29 and
32, the identical failure at a smaller offset. The numbers above were read
from `grep -n '^3[012]\. ' prd.md` on 2026-09-05 rather than counted from a
previous sentence, which is the only method that has produced a right answer
here.

**Criterion 30 is `make check` passes.** It is closed by PR 3 in the sense
that PR 3 is where the suite changes shape, but every pull request in this
item has to leave it true. It is listed once, against PR 3, and that is a
simplification worth naming: a green suite is a precondition of all eight
merges, not an achievement of one.

## Order and dependency

**This section is re-derived from the rebuilt Touches lists, and it was not
before.** Round two rebuilt every Touches list from the criteria and left the
ordering below it as the round-one grouping, which said "PRs 1 through 4 in
any order". Three of the files round two *added* to those lists are files
another pull request creates, and one is a file two pull requests rewrite in
opposite directions. Each constraint below names the file that forces it.

- **PR 1 before PR 4** — `WORKFLOW.md`. It does not exist; PR 1's Touches
  marks it "(new)" and PR 4 was given it in round two for criterion 9's
  personally-paid-repository sentence. PR 4 merging first either edits a
  missing file or creates a second one, and criterion 5's "exactly two
  places" test then passes against a page PR 1 overwrites.
- **PR 1 before PR 6** — `WORKFLOW.md` again, and criterion 11's closing
  sentence: all three modes in `README.md` are PR 1's while the criterion
  closes on PR 6. Criterion 6's own first clause is that the provider
  registry format is documented in `WORKFLOW.md`, which is why PR 6 now
  carries it too.
- **PR 5 before PR 8** — `skills/paths.json`. PR 5 creates it; PR 8 edits it
  for criterion 27's promotion and demotion. Both were constrained only to be
  after B's slice 1, so PR 8 could merge first onto a branch without the file
  and criterion 27's "asserts the branch content" test would have nothing to
  assert against.
- **PR 5 before PR 2** — `contrib/`. It does not exist. PR 2 moves `sd-grill`
  into it and says in its own parenthetical that PR 5 creates it, while PR 2
  sat in the unordered group. The alternative — PR 2 creating the directory —
  would make that parenthetical false, so the ordering is the half that gives.
- **PR 6 before PR 4** — `bin/sd-review`'s `BACKENDS` table. Criterion 6
  requires `bin/sd-review` to contain no provider table, and criterion 9's
  copilot rows that PR 4 edits are `bin/sd-review:238-243`, inside that table.
  PR 6 deletes the table; PR 4 then edits the registry and the skill page
  instead. Landed the other way, PR 4's edit has no target after PR 6.
  Criterion 9's grep also reaches a fifth payload surface,
  `skills/sd-review/SKILL.md:80`, which is in PR 4's Touches for that reason.
- **`bin/sd_install.py` is written by four pull requests**, and only three of
  them were transitively ordered by the constraints above. PR 1 writes the
  `test` and `lint` keys into `DEFAULT_BLOCK_BODY` (`:766-772`), where `mode`
  and `check` already stand — an earlier draft named the two that are already
  there, which would have made PR 1's block edit a no-op and left criterion
  1's five-key set two keys short; PR 5
  replaces the disk enumeration at `:224-229` with the paths file; PR 6 adds
  the `reviewers` consent line to the same block PR 1 writes; PR 7 adds the
  `sd_db` step. PR 1 → PR 6 → PR 7 already follows from `WORKFLOW.md` and
  from PR 7's slice, and **PR 5 before PR 6** is added here, since PR 5's
  renderer edit and PR 6's block edit both land in this file and the block is
  rendered by the enumeration PR 5 replaces. An earlier ordering rebuild
  derived its constraints from the files it had just changed rather than from
  the union of every Touches list, which is how the item's second-most
  contended file ended up with no constraint at all.
- **PR 1 and PR 6 both list `README.md`, and the clause is PR 1's.** The
  closure table puts criterion 11's `README.md` clause in PR 1; PR 6 keeps
  the file in its Touches only for the criterion's closing sentence, which it
  asserts rather than writes. Four pull requests edit `README.md` and this is
  the only contended clause among them.

- **R11-D31 before PR 6** — `tests/test_loc_caps.py`. `bin/` is capped, no
  Touches list above said so, and PR 6 is the first pull request in this item
  large enough to reach the ceiling. The cap may not be raised in the pull
  request that busts it, so the re-derivation lands first, on its own branch,
  touching nothing under `bin/`. This is the one constraint here that binds a
  change that is not in the eight.

Otherwise PR 2 and PR 3 need no database and no other item. **PR 5 needs a
database** — criteria 24 and 25 both read trial rows — so it lands with B's
slice 1 library, not before it. PR 6 after B's slice 1 lands the library and
B's harness. PR 7 after PR 6. PR 8 after PR 6 and after PR 5, and its
criterion 28 `commands.yaml` clause after B's slice 4.

The one hard ordering that reaches outside this item: B's fixture harness
merges before any pull request in any item that claims a criterion naming
it, which B's criterion 23 asserts from the log. Criterion 6 needs a fixture
remote and a fixture system checkout; criterion 11 needs six fixture-remote
cases plus a collaborator added and removed. So PRs 5 through 8 sit behind
that harness whatever else is true.

**The `sd_db` installer step is this item's criterion 13, and it rides with
PR 7.** B's settled open question 3 (`B/prd.md:1665-1670`) puts the pack's
installer provisioning `sd_db` into the pack's virtualenv from B's checkout,
as a built copy at a tag and never editable, and says "Item A's criterion 13
carries it". Without it B's library lands and nothing installs it, and the
first `sd today` after B's PR 2 fails on import.

**Two earlier drafts got this wrong in two different ways at once.** They
called it "item B's criterion 13", which is a dashboard criterion in B's
slice 4 (`B/prd.md:1419-1429`: "Status change, assign, promote, demote and
`merge_policy` each round-trip from the dashboard to a row") and has nothing
to do with an installer. And they filed the step on two pull requests: this
section and PR 6's Verification put it on PR 6, while PR 7's Touches and the
closure table put it on PR 7. The clause is A's own criterion 13, at
`prd.md:1541-1547`, whose files (`bin/sd_install.py`) are in PR 7's Touches,
so PR 7 carries it and PR 6 does not. B's dependency is on the merge, not on
which of the two pull requests holds it, and PR 7 lands after PR 6.

## Closing the item

PR 7 or PR 8, whichever merges last, carries `Delivers:`. Then `prd.md`
goes to `status: done` and drops its `branch:` field in the same edit.

**That instruction is wrong, and PR 8d merging last is what showed it.** All
eight pull requests have merged — PR 7 at `b0873ec1`, PR 8d at `fe0712ae` —
and the item still cannot go `done`, because two criteria were open and
neither is a pull request in this list. One has since been cut by the
operator; one remains. (2026-09-13: that one, criterion 28, is closed by
reading, and a third this count missed, criterion 23's second half, is what
is left. See the dated paragraphs at the end of this section.) (2026-09-13,
later: criterion 23's second half has closed as well, and this count also
missed criterion 7's forward experiment, which the owner has moved to
followup sd:777. See "The closure state today" at the end of this
section.) (2026-09-14: the first claim is wrong. PRs 2, 3 and 4 never
merged. Only PRs 1 and 5 to 8 did. The criteria PRs 2, 3 and 4 were to close
still fail their own checks on `main` at `ef9d3499`, so "two criteria were
open" undercounted by far more than one. See "The closure state today".)

*Criterion 7 was unscored, and its scoring clause is now cut.* The seven
`mezmo-world-simulator` passes had no scores anywhere on this item; `git grep`
over `prd.md` and this file returned the sentences that *described* the
criterion and no table of accepted against rejected. The criterion's wording
was stronger than "unscored": the scores were due **"before the code review
point runs on any new pull request"**, and the point ran on every pull request
from `#758` to `#777` regardless — a gate that had already been passed through
twenty times without anyone stopping. On 2026-09-07 the operator removed the
back-scoring rather than the review point, because the benchmark is not being
worked in parallel right now. Criterion 7 keeps the half that was load-bearing
— no percentage removes the code review point, and the point stays or goes by
a recorded decision — which is where C-39 and C-42 resolve. The scoring is
parked with the operator, triggered by `mezmo-world-simulator` Phase 1 reaching
`done`; `prd.md`'s log carries the reasoning. (2026-09-13: this paragraph
is incomplete. It names the scoring and the grep and leaves out the third
part of criterion 7: the other vendor reviews the next ten code pull
requests, a report goes on this item, and the review point stays or goes by
a decision. The 2026-09-07 cut kept that forward experiment on purpose. It
was never closed. The owner deferred it to followup sd:777 on 2026-09-13, in decision
note 1920;
see "The closure state today".)

*Criterion 28 has two clauses that cannot close from this checkout.* PR 8d
says so in its own text and the closure table says so in its own row, and this
section was written before either. It is now the only criterion between the
item and `done` (wrong: criterion 23's second half is open too, corrected
below; and, 2026-09-13, so is criterion 7's forward experiment, now deferred
to sd:777), but it is **two** pieces of work and not one:

1. **`commands.yaml`, item B's.** The "no palette entry" assertion enumerates
   a file that does not exist in this repository. B's slice 4 PR 7 writes it,
   as the dashboard's palette; that PR is behind B's slice 3 PRs 5 and 6.
   `tests/test_sd_suggest.py:17` records the omission deliberately.
2. **The writing manifest, another repository's.** `skill-proposal` has to be
   absent from it, and PR 8d could only reach the
   `contrib/sd-propose-skills/` half from here.

Neither is code this repository writes. Both are one assertion each once the
thing they assert against exists. (2026-09-13: wrong. Both things now exist,
and neither can be an assertion here, because pack CI reaches neither. Both
were checked by reading instead; see below.)

**So `Delivers:` is deliberately not on `fe0712ae`.** `git log --grep
'^Delivers:'` on `main` returns nothing, which is the state this paragraph
wants: a `Delivers:` here would mark the item shipped with two criteria open,
and `WORKFLOW.md:153` makes that commit the answer a database-free reader
gets. `WORKFLOW.md:149-152` already provides the remedy for a delivery that
happened without its trailer — the next `sd-ship` merge here, or one empty
commit on the branch — so nothing is lost by waiting, and the item stays
`in_progress` until the two close. (2026-09-13: they have, and the item is
still `in_progress`, now held by criterion 23's second half; see below.)
(2026-09-13, later: that half has closed too, and the pull request that
adds "The closure state at delivery" carries `Delivers:`.) (2026-09-14: it
does not. That pull request, #931, became a correction of the closure state
and carries no `Delivers:`, because criteria are still open; see "The
closure state today".)

**What is left, in the order it can be done.** Two things, and neither is this
repository's to write. Item B's slice 4 PR 7 lands `commands.yaml`, and the
palette clause becomes assertable here. The writing repository drops the
`skill-proposal` kind from its manifest, and the manifest clause becomes
assertable here. Then, and not before, the delivery commit. (2026-09-13:
superseded. Both things have happened, neither clause became assertable
here, and the delivery commit does not follow from them: it waits on
criterion 23's second half, as the dated paragraphs below record.)
(2026-09-13, later: that half is closed; see "The closure state
today".) (2026-09-14: and the delivery commit still does not follow, because
PRs 2, 3 and 4 never merged.)
Scoring the seven passes is no longer in this order at all: it is evidence
gathered from `answerbook/mezmo-world-simulator` rather than code written here
— its git history records at least the fourth and the seventh (`0c39c78`,
`426a405`) — and it now sits behind that repository's own Phase 1 rather than
in front of this item's delivery.

**2026-09-13: both of criterion 28's open clauses were checked by reading, and
criterion 28 is closed.** Neither check is a test, and neither can be one in
this repository: what each reads lives outside this checkout, where pack CI
cannot reach it. A regression in either place would not turn this repository
red. They are recorded here with enough to repeat them. Closing a criterion
by a dated one-time read instead of a test is the owner's call, not this
page's: the owner accepted the read as the evidence in decision note 1904 on
sd:10, recorded 2026-09-14 for the review of pack #926.

1. **`commands.yaml` exists and names no suggest or publish entry.** The file
   is at `~/.local/share/sd/commands.yaml`, the default path `sd_db`'s runner
   reads its command catalog from. Read on 2026-09-13 (sha256 `de63f1bf…`,
   last modified 2026-09-11), it holds three entries: `git-status`,
   `runner-provisioning-probe` and `plan-item`. The strings `suggest` and
   `publish` appear nowhere in the file, so `sd suggest publish` is not a
   palette entry. It is per-machine state outside git, which is why
   `tests/test_sd_suggest.py` still leaves this clause out on purpose.
2. **The writing manifest no longer declares `skill-proposal`.** On
   `platypeeps/sd-writing-pack` `main` at `3d0be2c3`, `sd-plugin.json`
   declares three kinds, `tip`, `blog-idea` and `topic`. The string
   `skill-proposal` appears nowhere in it, and `templates/skill-proposal.md`
   is gone. The kind was removed by `e79d75e5` (that repository's #34) on
   2026-09-08. At `3d0be2c3` the log entry is at line 2278 (at `e79d75e5`
   it is line 2279) of
   `sd-writing-pack/docs/work/2026-09-05-the-writing-pipeline-runs-on-the-row/prd.md`.
   The local checkout at `~/repos/platypeeps/sd-writing-pack` matches. Pack
   CI has no checkout of the writing pack, so this clause is recorded here
   and not tested. The clause's other half, that `sd-propose-skills` writes
   no vault note, was already covered by PR 8d's test across
   `contrib/sd-propose-skills/`.

**Closing criterion 28 does not make the item deliverable, and this section
was wrong to say it would.** "It is now the only criterion between the item
and `done`" overlooked criterion 23's second half, which the subsection below
still records as open. That is still true on 2026-09-13: `CLAUDE.md` on the
writing pack's `main` at `3d0be2c3` still has a `## Style` section (lines 20
to 22) that forbids "caveman mode", and criterion 23 deletes that override.
The first half of criterion 23 still holds, since `~/.claude/settings.json`
does not contain `caveman`. So `Delivers:` is still not written. One clause is
left, and it is the writing repository's one-line pull request that removes
that section. (2026-09-13, later: superseded. That pull request has merged;
see below. "One clause is left" was also wrong, because it missed criterion
7's forward experiment.)

**The closure state as of 2026-09-13, in one place.** Criterion 7's scoring
clause is cut. Criterion 28 is closed by reading, with the evidence above,
under decision note 1904.
Criterion 23's second half is open. The delivery commit waits on that one
clause and on nothing else this section names. Every earlier sentence in this
section that says otherwise carries a dated marker pointing here. (2026-09-13,
later: superseded by "The closure state today" below. Criterion 23's
second half has since closed. This paragraph also left out criterion 7's
forward experiment, which was open when it was written.)

**2026-09-13: criterion 23's second half is closed.** `platypeeps/sd-writing-pack`
#41 merged as `be76962e` ("docs(sd:10): remove the repository's caveman style
override", 2026-09-14T04:40Z, which is the evening of 2026-09-13 local time).
It deletes the `## Style` section of `CLAUDE.md`, which forbade caveman mode,
and `.caveman/config.json`, the same override in config form. Read through
GitHub on that repository's `main` at `be76962e`: `CLAUDE.md` contains neither
`## Style` nor `caveman`, and `.caveman/config.json` does not exist. The first
half still holds: `grep -c caveman ~/.claude/settings.json` prints `0`. Like
criterion 28, this is a dated read of another repository and of per-machine
state. It is not a test, because pack CI reaches neither.

**2026-09-13: the closure state above missed criterion 7.** Criterion 7 has
three parts. The first is the grep: no percentage in `bin/` or `skills/`
disables a review point. The second is back-scoring the seven old passes. The
third is the forward experiment: the other vendor reviews the next ten code
pull requests, a report goes on this item, and the code review point stays or
goes by a recorded decision. The 2026-09-07 cut removed only the second part,
and `prd.md`'s log entry for that date says it kept the forward experiment "so
the report the operator decides from still has to exist". No pass log, report
or decision was ever recorded on this item, and `WORKFLOW.md` still describes
the experiment. #926's closure state named only the cut, so it missed the
third part. On 2026-09-13 the owner decided to move the forward experiment,
with its report and decision, to followup sd:777 ("sd:10 criterion 7:
ten-pass forward experiment on the code review point, report and decision"),
in decision note 1920 on sd:10.
The delivery does not wait on it. The grep was re-run over `bin/` and
`skills/` for percentages, `percent` and `threshold` on 2026-09-13.
That review recorded no hit that disables a review point.
The matches covered age thresholds, line thresholds, size reports, and the
`sd-review` severity floor.

**The closure state today, 2026-09-14.** This replaces "The closure state at
delivery, 2026-09-13", which said every criterion was closed, cut or deferred
and put `Delivers: sd:10` on #931. That was wrong. It trusted the table under
"What closes the criteria" and the claim that all eight pull requests had
merged, and PRs 2, 3 and 4 never did. #931 now corrects the closure state and
does not deliver the item.

Each line below is that criterion's own check, run on `origin/main` at
`ef9d3499` on 2026-09-14, with the line that decides it. No line uses merge
history as evidence. "Tests pass" means the named module ran green with the
pack's `.venv` Python on this branch, whose code is `ef9d3499`'s.

**Open after the owner's decisions, 2026-09-14: criteria 5, 16, 18, 21, 22,
27 (the help text), 13 (the refusal test) and 31 (a, b and
c).** Decision note 1942 on sd:10, recorded in `prd.md`'s log entry of that
date, decides the rest of the open list below. Criterion 14 and criterion
15's ceilings clause are cut. Criterion 6's open parts are deferred to
followup sd:788 and criterion 11's to followup sd:789. Criterion 27 and
criterion 13's moved-default-branch clause are rewritten to #802's design.
Criterion 31 is rescoped, and criterion 18 gains two exemptions. Criterion 9
closed when #931 merged as `0aeb42a1`. The checks below ran before those
decisions, on `ef9d3499`, and each open line carries a dated marker for the
decision that changed it.

**Open after the merges of 2026-09-14: criteria 5 (the table-reads clause),
13 (the refusal test), 16, 18, 21 and 31 (a, b and c).** #935 (`48d1d58e`)
closed criterion 5's vendor clause and no more of criterion 5. Its review
found the clause at `prd.md:1235-1236`, that every skill which runs a review
names its point in the table and reads the cap from it, unasserted and
outside that pull request's scope, so criterion 5 is part-closed and that
clause stays open. #936 (`c3604594`) closed criterion 22. #939 (`0feecae9`)
fixed the help text at `bin/sd:3031-3046` and closed criterion 27. Criterion
16 is still open, in #938. #940 (`075eecf2`) is sd:787's and touches no
criterion of this item.

**The lane order, from decision note 1942.** Criteria 5, 16 and 22 are being
implemented now (2026-09-14: 5's vendor clause closed in #935, 22 in #936;
16 is still open, in #938, and 5's table-reads clause is still open.
2026-09-16: #938 merged as `a3baf6d9`, so 16 is closed). After
#932, which merged as `107016fc`, in series:

1. criterion 27's help text (2026-09-14: done, #939 merged as `0feecae9`);
2. criterion 21 with 31(a), once the system sweep job and its LaunchAgent
   are retired (2026-09-16: the sweep is cut, see the entry at the end of
   this page; 31(a)'s `parked` and `archived` field cut stays open);
3. criterion 18;
4. criterion 31(b);
5. criterion 31(c), which carries `Delivers: sd:10`.

**Two clauses this order did not schedule, now scheduled.** Criterion 13's
refusal test and criterion 5's table-reads clause were in the open list above
and in the `Delivers:` gate below, and in no step of this order. Decision
note 1942 is silent about both. Team-lead decision 2026-09-16, under the
standing authorization and reversible by the owner: the two land as their
own small pull request before 31(b), not in 31(c), and the tick of criterion
16 rides along because it is the same page. That pull request is the one
that carries this paragraph. `Delivers: sd:10` still waits on every open
criterion, so 31(c) carries the trailer only after that pull request has
merged.

**Open on `ef9d3499`, before those decisions: criteria 5, 6, 11, 13, 14,
15, 16, 18, 21, 22, 27 and 31, and criterion 9 until #931 merges.** The review of #931 named 9, 14,
15, 16, 18, 21 (the code-path half), 22 and 31. These checks confirm those and
add 5, 6 and 27. The verification of #931 adds 11 and 13.

- **5, open (vendor clause).** The table clauses hold:
  `ReviewTable.test_the_two_copies_are_identical` passes. A grep of
  `skills/` for a bare `codex`, `claude`, `openai` or `anthropic`, not
  `Claude Code`, finds 3 lines, all in `skills/sd-review/SKILL.md`: `:123`
  "`--scope branch --provider claude` review", `:137` "Codex also receives
  the exact" and `:142` "runs Claude in safe and restricted modes".
  (2026-09-14: the vendor clause closed in #935, `48d1d58e`. Criterion 5 is
  part-closed. The clause at `prd.md:1235-1236`, that every skill which runs
  a review names its point in the table and reads the cap from it, is
  unasserted and was outside #935's scope, so it stays open.) (2026-09-16:
  closed by the pull request that carries this line. `SkillsThatRunAReview`
  in `tests/test_workflow_policy.py` enumerates the skills whose `SKILL.md`
  invokes a reviewer, `sd-review` with its flags or `sd-research-kit review`,
  four on this base: `sd-plan`, `sd-research-repo`, `sd-review` and
  `sd-ship`. Each links `.claude/rules/sd-planning-adversarial-review.md`,
  names a Point cell read from that table, and carries no cap literal of its
  own. A mention of the lane is not a run of it: six other skills name
  `sd-review` as the holder of the verdict and run nothing. Four mutations
  killed: a `cap of 1 pass` in `sd-ship`, a `2 passes` in `sd-review`, the
  link dropped from `sd-plan`, the point renamed in `sd-research-repo`.)
- **6, open (the `minimax` meter clause).** `git grep -l token_plan -- bin
  tests` finds 0 files, so nothing reads `token_plan/remains` and no test
  asserts the two windows. Other clauses have passing tests, among them
  `tests/test_sd_registry.py:1261`
  `test_the_shipped_registry_still_resolves_exo_over_http`, `:1173`
  `test_a_think_block_and_reasoning_content_still_read_clean` and `:795`
  `test_a_bill_at_its_cap_is_passed_over`. No test was found for the two
  concurrent calls against room for one. (2026-09-14: deferred to followup
  sd:788 by decision note 1942. It covers the `minimax` meter, the spend
  cap, which no production caller wires, and an audit of the attribution
  clauses whose names `SD_AUTHOR` and `slice_base` have 0 hits. Caps on
  `url` entries stay unenforced until then, by the owner's acceptance.)
- **9, open on `main`, closed by #931.** The settings clause is
  removed by the owner's decision note 1921 (2026-09-14): the global
  Copilot-requesting hook stays. On 2026-09-14,
  `grep -c -i copilot ~/.claude/settings.json` counts 1 and
  `grep -c requested_reviewers` counts 1. The pack-surface clause holds: a
  case-insensitive grep of `bin/`, `skills/`, `agents/`, `dashboard/`,
  `.claude/`, `.github/`, `CLAUDE.md`, `AGENTS.md` and `README.md` for
  `copilot`, `requested_reviewers` and `request_copilot` finds 9 lines, and
  none requests a review. The nearest is `skills/sd-handoff/SKILL.md:123`
  "**suppress the Copilot re-request**". The `WORKFLOW.md` clause failed on
  `main`: `:148-149` said "On a repository you pay for personally it is off".
  #931 changed it to say Copilot review there comes from the
  operator's own global hook, at the operator's choice and cost, citing note
  1921. (2026-09-14: closed. #931 merged as `0aeb42a1`.)
- **11, open (the demotion-note clause).** No code writes the demotion note
  the criterion asks for when a collaborator joins a `mode: full`
  repository. `source:bin/sd_lib.py::remote_permits_full` has two callers,
  the mode resolver in `bin/sd_lib.py` and the ownership check in
  `bin/sd_ship_remote.py`, and neither writes a note. No test names demotion outside `tests/test_sd_skill_promotion.py`.
  The six detection cases pass, `test_case_1_…` to `test_case_6_…` in
  `tests/test_mode_detection.py:144-180`. (2026-09-14: deferred to followup
  sd:789 by decision note 1942, with the `merge: auto` clauses, which were
  never audited. The protective refusal is tested at
  `tests/test_guest_artifact_refusal.py:178`.)
- **13, open (the moved-default-branch clause).** The criterion asks for one
  integration update when the default branch moves after the review, and for
  a seeded conflict in it to end the item `blocked`. `grep -c -i integrat
  bin/sd-ship` counts 0, and no `tests/test_sd_ship*.py` test covers an
  integration update or its conflict. `tests.test_delivered` (15) and
  `tests.test_status_source` (43) pass. (2026-09-14: the clause is rewritten
  to #802's refusal in `bin/sd_ship_remote.py:119-127` by decision note 1942.
  No test asserts either refusal message yet, so criterion 13 stays open for
  that test.) (2026-09-16: closed by the pull request that carries this
  line. `ReadyCase` in `tests/test_sd_ship_remote.py` stubs the adapter's one
  outbound call and asserts `source:bin/sd_ship_remote.py::ready` by
  message: a moved head and a moved base each refuse "pull-request head or
  default base moved after local review" with no call made, and a `compare`
  answer whose `behind_by` is not 0 refuses "the reviewed branch is behind
  the current default branch" on the one `compare` call. A fourth test pins
  that `behind_by: 0` passes the guard. Four mutations killed: each message
  reworded, the `behind_by` guard weakened, the base-ref half of the moved
  guard dropped.)
- **14, open.** `Makefile:125-126` `docs-lint:` runs `bin/sd-docs-lint`
  whole. It wires no no-database rule set enumerated from the lint, and no
  test compares a wired set to the lint's set. (2026-09-14: cut by decision
  note 1942. #820 runs the whole lint in `make check`, and the lint needs no
  database.)
- **15, open (the ceilings).** The floor half holds: `.coveragerc` includes
  only `bin/sd_install.py`. The ceilings fail rather than warn:
  `tests/test_loc_caps.py:505`, `:554` and `:584` use `assertLessEqual`. There
  is no warning-path test. (2026-09-14: the ceilings clause is cut by
  decision note 1942, as superseded by #813, sd:430 and sd:719. The floor
  half holds, so nothing of criterion 15 is open.)
- **16, open.** `Makefile:20` `test:` and `:134` `check: test lint audit
  docs-lint` take no changed-files argument. (2026-09-16: closed. #938
  merged as `a3baf6d9`. Re-measured on this base: the `ifeq ($(origin
  CHANGED),command line)` block in `Makefile` exports `TEST_CHANGED_FILES`
  only for a `CHANGED` given on the command line and otherwise runs the
  suite under `env -u TEST_CHANGED_FILES`, so the full suite is the default;
  `.github/scripts/select-tests.py` picks the modules; `check:` is now at
  `Makefile:201` and `test:` at `:55`.)
- **18, swept 2026-09-16 in #998**, down to the exemptions and two words in
  files #995 held; see "Criterion 18 landed" at the end of this page, which
  names the remainder and the edit that closes it. (2026-09-16, 31(b1): both
  words are reworded, `HELD` in `tests/test_no_trellis_residue.py` is empty
  and `HELD_BOUND` keeps the two rows as its ceiling; the grep of the
  governed tree outside that test returns 12 lines, all in the exemption
  sets. See "Criterion 31(b1) landed" at the end of this page.) (Measured 2026-09-14: a grep of the
  governed tree found `Trellis` in 14 files, `.trellis` in 11 and `task.py`
  in 2, with two exemptions from decision note 1942. The upstream Trellis
  pull-request guard at `AGENTS.md:7-10,31` is exempt while sd:241, sd:242
  and sd:244 are open. The residue detectors are cut only after the gating
  fleet check passes, and until then the `.trellis` residue line is exempt.)
- **21, open (the code-path half).** `bin/sd_sweep.py` is tracked, and
  `bin/sd:2969` still defines `"sweep", help="report the planning items the
  45-day rule would park"`. No test asserts a frozen set for `git rm`,
  `rmtree` and `rmdir`. The archive half holds: `tests.test_archive_untouched`
  passes (5 tests). No test was found that puts a `planning` item under the
  archive and runs `sd-status`, `sd-plan` and `sd-review --scope planning`.
  (2026-09-14: still open. By decision note 1942 the system job
  `local-cron-jobs/jobs/sd-sweep-weekly.job` and its LaunchAgent retire
  first, with the operator running the `launchctl` step. Then the verb and
  `bin/sd_sweep.py` are cut, under this criterion and 31(a). The job's last
  log is from 2026-09-07.) (2026-09-16: the code-path half is closed. The
  system job retired as system `e029934`, #356, and `launchctl list` names
  no sweep agent; the verb and the module are cut and a frozen set of eight
  deletion-verb sites is asserted. See the entry at the end of this page.)
- **22, open (the test).** The template's one link,
  `.github/copilot-instructions.md`, exists. No test walks the links:
  `tests/test_delivery_evidence.py:148` reads the template for its trailer
  block only. (2026-09-14: closed. #936 merged as `c3604594`.)
- **27, open as written.** `tests/test_sd_skill_promotion.py:78`
  `test_promotion_and_demotion_queue_code_review_without_git_writes` asserts
  that promotion queues a review assignment and writes nothing to git.
  `:112` asserts `bin/sd_skill.py` contains no `pr create`. No pull request
  moves the directory, and no test asserts a branch's content. #802
  (`505431b8`, 2026-09-10) made that change, and no entry on this item
  records it. (2026-09-14: the criterion is rewritten to #802's queue design
  by decision note 1942, and `prd.md`'s log entry of that date records it.
  The help text at `bin/sd:3031-3046` still said both verbs open a pull
  request, so criterion 27 stayed open for that fix. Later that day #939
  merged as `0feecae9`, and the help text now says the verbs queue a code
  review task. Criterion 27 is closed. The rewritten criterion also records
  the half the help text does not carry: one pull request is still the
  deliverable, prepared later by the queued agent from the brief at
  `sd_db/skills_catalog.py:253-255`, and merged by the operator.)
- **31, open.** Governed-tree file counts: `sd_sweep` 6, `parked` 13,
  `archived` 19, `record_load` 2, `carrier_branches` 2, `_protection_gaps` 2,
  `load_acknowledgements` 2, `--stash-ref` 4, `--push` 2, `--park` 4,
  `argument-vocabulary` 21, `Standing rule` 4, `R10-D` 45, `five gates` 1,
  `Active item:` 8, `sd-rust-reviewer` 3, `sd-deps` 4. Only `cron-jobs.sh`
  finds 0. The `authors` policy key is still in `.github/sd-review.json:22`.
  (2026-09-14: rescoped by decision note 1942. `R10-D` is dropped, since
  those are sd:431's rule registry ids. `parked` and `archived` are scoped to
  the `sd_lib` item field and its readers. `sd-rust-reviewer` is removed, as
  a live agent. The cross-repository bug regression tests, for
  `adversarial-gate` in the system repository, move to followup sd:790. The
  rest lands in three pull requests: (a) `sd_sweep`, `parked` and `archived`,
  with criterion 21; (b) the prose symbols and flags; (c) the bug
  regressions and the one-definition greps.) (2026-09-16: `sd_sweep` finds
  0 governed-tree files, so 31(a) is closed for `sd_sweep`. The `parked`
  and `archived` field cut is deferred to a later lane, team-lead decision
  2026-09-16, reversible by the owner; the reader set is frozen meanwhile.
  See the entry at the end of this page.) (2026-09-16, 31(b1) landed: the
  prose symbols and flags. `record_load`, `carrier_branches`, `--stash-ref`,
  `--push`, `--park`, `argument-vocabulary`, `Standing rule`, `five gates`,
  `cron-jobs.sh`, `Active item:` and `sd-deps` each find 0 governed-tree
  files outside the gate that freezes them, `PROSE_SYMBOLS`
  (`source:tests/test_cut_symbols.py::PROSE_SYMBOLS`). BLOCKED-in-part:
  `_protection_gaps` and `load_acknowledgements` are the live protection
  section of `bin/sd-status`, which applies the accepted gaps in
  `.github/sd-status.json`, and the cut is requirement 13's rewrite to one
  `protected: yes/no` line, the owner's change; `HELD_SYMBOLS_BOUND`
  (`source:tests/test_cut_symbols.py::HELD_SYMBOLS_BOUND`) holds them in
  `bin/sd-status` and `tests/test_sd_status.py` and nowhere else. Left for
  (b2): the `authors` policy key. See "Criterion 31(b1) landed" at the end
  of this page.)

**Closed, by the criterion's own check:**

- **1.** `tests.test_workflow_policy` passes (19 tests), including
  `test_the_installer_block_names_the_page` and
  `test_a_sixth_key_on_one_side_alone_fails`.
- **2.** `tests.test_sd_ship_skill` passes (66 tests), including
  `test_no_step_runs_sd_spec`, `test_no_step_carries_a_branch_deletion_command`
  and `test_the_settle_step_issues_no_polling_loop`.
- **3.** `test_a_missing_trailer_warns`, `test_the_warning_does_not_hold_the_ship`
  and `test_the_carried_trailer_passes_quietly` pass. `bin/sd-ship:491` says
  "has no Needed-by trailer; delivery continues".
- **4.** `DeletedLane.test_no_governed_file_names_the_lane` passes.
- **7.** The grep of `bin/` and `skills/` for percentages, `percent` and
  `threshold` finds 33 lines. None disables a review point; the nearest is
  `source:bin/sd-review::dispose` `threshold = BLOCKING_ORDER[floor]`, a severity floor.
  The back-scoring is cut (2026-09-07). The forward experiment is deferred to
  followup sd:777 by the owner's decision note 1920.
- **8.** `ConditionalObligations.test_every_site_naming_the_ledger_names_the_gate`
  passes.
- **10.** `none - ` finds 0 files in `bin/` and `skills/`.
  `test_green_no_work_line_claims_no_item` and
  `test_red_a_bare_none_is_a_path_that_does_not_resolve` pass.
- **12.** The root README, line 50: "**What it writes in a repository:** nothing at
  machine-scope install." and line 72: "Two skills add paths of their own, both
  tracked".
- **17.** `tests/test_selector_contract_drift.py`,
  `generated/registry-snapshot.json` and `plugins/sd` are untracked (0 files),
  and `bash32` appears in no workflow.
- **19.** A dated read on 2026-09-14, counts only: `Read(` 0, `trellis` 0,
  and 1 each for `create_pull_request`, `pull_request_read`,
  `merge_pull_request`, `list_pull_requests` and `update_pull_request`. The
  global guide's `cd`-prohibition pattern counts 0.
- **20.** `test_exactly_one_file_states_the_planning_review_rule` passes.
- **23.** `grep -c caveman ~/.claude/settings.json` counts 0 on 2026-09-14,
  and `sd-writing-pack` `be76962e` deleted the override (above).
- **24.** `skills/paths.json` names `research`, `development` and `act`.
  `test_an_unlisted_skill_directory_refuses_the_install` and
  `test_contrib_is_not_rendered_without_a_trial_row` pass.
- **25.** `test_a_trial_writes_one_row_and_prints_its_expiry` and
  `test_an_expired_trial_with_no_use_is_removed_and_named` pass.
- **26.** `tests.test_sd_skill_use` (13 tests) reads `skill, surface, mode,
  cwd` rows from `PreToolUse` and `UserPromptSubmit` events and passes.
  `tests/test_sd_codex.py:117`
  `test_a_skill_opened_by_path_is_one_row_on_the_codex_surface` passes.
- **28.** `test_the_row_is_written_in_every_mode_and_reaches_no_tracker`,
  `test_publish_refuses_without_a_destination` and
  `test_shadow_sync_writes_the_open_issues_and_closes_nothing` pass. The two
  clauses closed by reading are under decision note 1904.
- **29.** `test_three_followups_survive_a_session_that_wrote_no_packet` passes.
- **32.** `test_the_push_refuses_a_head_the_local_review_has_not_cleared`,
  `test_a_moved_head_is_refused_by_the_merge_the_skill_prescribes` and
  `tests/test_sd_registry.py:156` `test_the_same_file_gives_the_same_reviewer_order`
  pass.
- **33.** `test_red_a_page_naming_an_item_directory_that_is_not_there` and
  `test_green_a_metavariable_is_a_pattern_and_not_a_path` pass, and
  `bin/sd-docs-lint` reports `clean`.

**Not settled by these checks:**

- **30.** `make check` is what CI runs, so it is the state of CI on the pull
  request that last changed `main`. It was not run locally.

The first instruction in this section, that `prd.md` goes to `status: done`
and drops `branch:`, predates criterion 13. `prd.md` now has no `status:`
line, since the row carries status, so no delivery edits it. The item is
not deliverable: `Delivers: sd:10` waits until every open criterion above is
closed, cut or deferred by a recorded owner decision: 5, 6, 9, 11, 13, 14,
15, 16, 18, 21, 22, 27 and 31. (2026-09-14: after decision note 1942 the
list is 5, 16, 18, 21, 22, 27 (the help text), 13 (the
refusal test) and 31 (a, b and c). `Delivers: sd:10` goes on 31(c), the last
pull request in the lane order above. After that day's merges the list is 5
(the table-reads clause), 13 (the refusal test), 16, 18, 21 and 31 (a, b and
c). Criterion 13 and criterion 5's remaining clause have no step in the lane
order, and this gate is what still holds them: 31(c) cannot carry the
trailer while either is open.) (2026-09-16: 16 closed when #938 merged as
`a3baf6d9`; 13 and 5 close with the pull request that carries this line,
by the team-lead decision recorded under "The lane order". The list is 18,
21 (the archive-test clauses, after #995 cut the sweep), 31(a)'s `parked`
and `archived` field cut, 31(b) and 31(c). Followups sd:789, criterion 11's demotion note, and
sd:790, criterion 31's cross-repository regressions, are both `done`, by
#957 `c43747e4` and system #396 `e2a38474`.)

### The three landings that are no pull request of this repository's

PR 4 said criteria 19 and 23 are recorded against their landings rather than
against this repository's diff, and left no place to record them. This is that
place, and two of the three have now happened. (2026-09-13: all three have.)

**Criterion 19 and criterion 23's first half — the global settings and the
global guide — landed on 2026-09-07 as an operator edit.** They are under
`~/.claude/` and in no git repository, so there is no commit to cite; what
follows is the measurement, taken before and after, with
`~/.claude/settings.json.bak-2026-09-07` and `CLAUDE.md.bak-2026-09-07` beside
the originals so the edit is reversible by hand.

| clause | before | after |
|---|---|---|
| no `Read()` deny rule | 14 | 0 |
| no `.trellis` allow rule | 2 | 0 |
| the four MCP pull-request tools | 1 of 5 | 5 |
| the guide's `cd` prohibition | 30 lines | absent |
| the caveman plugin | enabled | absent |

**The item never names which four MCP tools, so the four are chosen here and
recorded rather than left to the next reader.** `create_pull_request`,
`pull_request_read`, `merge_pull_request` and `list_pull_requests` — the
`mcp__github__` mirror of the `gh pr create`, `view`, `merge` and `list`
already on the allowlist, which is where requirement 8's nine blocked merges
came from. `update_pull_request` was already there and is the fifth.

**The `cd` prohibition and the deny globs were one change, not two, and the
guide said so itself.** Its own paragraph gave the deny rules as the reason
the rule existed — a `cd` makes the working directory statically
unresolvable, so the harness cannot prove the target matches no deny rule, so
an auto-approvable command escalates — and added that narrowing the globs does
not help, because the trigger is that *any* `Read()` deny rule exists.
Removing the globs removes the reason, which is why requirement 8 drops the
two together and why removing only one of them would have been worse than
removing neither.

**Criterion 23's second half is open.** The writing repository's style
override is that repository's one-line pull request and is not this
repository's or `system`'s. It was still present on 2026-09-13; see "Closing
the item". (2026-09-13, later: closed. `sd-writing-pack` #41 merged as
`be76962e` and deleted the override; see "Closing the item".)

**The system repository's guide landed as its own pull request there.**
`CLAUDE.md` 341 lines to 278, five narrative sections rewritten as
present-tense rules: the drift markers, TCC under launchd, the 02:xx wake, the
GitHub token facts and the Slack digest. Forty-one load-bearing tokens were
enumerated from the old text before the edit and all forty-one survive it.
Dates that fix a state change inside a present-tense rule are left alone.
What is left is the account of the night each rule was learned.

That field was missing when this file was first written, and adding it was
the fix. This repository's items carry `branch:` by convention — 238 `prd.md` files
under `docs/work/` have the line, and the sibling item
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

## Where the tests land, which no pull request said

Every pull request carries its own criterion's tests in `tests/`, and no
Touches list above said so as a rule — they named individual test files, one
per cut, as the cuts happened to break them. At least seventeen criteria
mandate a test in their own words.

The cuts break six existing files: `tests/test_sd_sweep.py`,
`tests/test_sd_status.py`, `tests/test_sd_handoff_restore.py`,
`tests/test_doc_citations.py`, `tests/test_loc_caps.py` and
`tests/test_sd_docs_lint.py`, all of which assert symbols or pages that PR 1,
PR 2 and PR 3 remove. Five are named in the Touches lists above. The sixth,
`tests/test_sd_docs_lint.py`, is named only in PR 6's prose, and PR 6 removes
none of those symbols — it is added to PR 2's Touches, the pull request whose
`none - ` cut breaks it. An earlier version of this section opened by saying
`tests/` "appeared in exactly one Touches list above — as a file to delete",
which its own next sentence refuted three times over. Criterion 30 makes `make check` passing a precondition of
every merge by this page's own argument, so a pull request that deletes a
symbol and leaves its test asserting it cannot merge. Each deletion pull
request updates or removes the tests its cut breaks, named in the Touches
lists above; each new behaviour ships its test in the pull request that
builds it.

## One count in the nineteen-file list depends on how the grep is written

The nineteen files enumerated for criterion 18 reproduce under
`git grep -lE "Trellis|.trellis|task\.py"` with the dot unescaped, or under
a case-insensitive grep. Under criterion 18's literal strings the count is
eighteen: `bin/sd_setup_github.py`'s only hit is the comment
"`bin/migrate-trellis` removed" at `:52`, lower-case and hyphen-preceded,
matching none of `Trellis`, `.trellis` or `task.py` literally. The file is
worth editing either way, and the subcounts hold — two test files, seven
`docs/spec/` pages — but an implementer running the criterion's own grep
sees eighteen and cannot reconcile it. Recorded rather than silently
recounted.

## What closes the criteria

| Criterion | Closed by |
|---|---|
| 1, 4, 8, 20 — the policy page, the lane, the conditional obligations | PR 1 |
| 5 — the review table in exactly two places, and no bare vendor token in a skill | PR 1 (the two table clauses), PR 6 (the vendor clause whole: a converted token names a role, and no role resolves before PR 6's registry reader) (2026-09-14: the vendor clause is open, see "The closure state today"; being implemented now, from decision note 1942). (2026-09-14, superseding that vendor clause only: #935 closed it, `48d1d58e`. Criterion 5 is part-closed. The clause at `prd.md:1235-1236`, that every skill which runs a review names its point in the table and reads the cap from it, is unasserted and was outside #935's scope, so it stays open and no step of the lane order schedules it). (2026-09-16: that clause is closed by the pull request that carries this row, `SkillsThatRunAReview` in `tests/test_workflow_policy.py`, under the team-lead decision recorded in "The lane order". Criterion 5 is closed) |
| 31 — requirement 13 line by line | PR 2 (2026-09-14: never merged; open, see "The closure state today"). (2026-09-14, superseding the scope this row's heading names, not the criterion's open state, decision note 1942: rescoped, with `R10-D` and `sd-rust-reviewer` dropped, `parked` and `archived` scoped to the `sd_lib` item field and its readers, and the cross-repository bug regression tests moved to followup sd:790. Three pull requests close it: 31(a) with criterion 21, then 31(b), then 31(c), which carries `Delivers: sd:10`). (2026-09-16: 31(a)'s `sd_sweep` symbol is closed by the sweep cut, asserted by `tests/test_cut_symbols.py`; its `parked` and `archived` field cut is deferred to a later lane (team-lead decision 2026-09-16, reversible by the owner) with the reader set frozen by `tests/test_cut_symbols.py::ParkedAndArchivedReaders`, see the 2026-09-16 entry at the end of this page). (2026-09-16: followup sd:790 is `done`: system #396 `e2a38474` adds the two cross-repository regression tests in `local-adversarial-gate/tests/test_run.py`, and its decision note files the pack-side gaps as their own followups, sd:947 among them, merged as `77a191df`) |
| 21 — the archive untouched, and no sweep or park code path remains | PR 2 (the code paths), PR 7 (the archive diff) (2026-09-14: PR 2 never merged; the code-path half is open, see "The closure state today"). (2026-09-14, superseding the PR 2 assignment only, not the code-path half's open state, decision note 1942: one pull request with 31(a), after #932, which merged as `107016fc`, and after the system sweep job and its LaunchAgent are retired). (2026-09-16: the code-path half is closed by the sweep cut, with the frozen deletion-verb set in `tests/test_archive_untouched.py`; see the 2026-09-16 entry at the end of this page) |
| 14, 15, 16, 17, 30 — the checks | PR 3 (2026-09-14: never merged; 14, 15 and 16 are open, 17 closed by #892 and 30 is CI's, see "The closure state today"). (2026-09-14, superseding that sentence's claim that 14 and 15 are open, and nothing else in it, decision note 1942: 14 is cut and 15's ceilings clause is cut, so 15 is closed on its floor clause; 16 is being implemented now, in #938, and is still open). (2026-09-16: 16 closed, #938 merged as `a3baf6d9`) |
| 33 — no document names a `docs/work/` path that does not resolve | PR 7, which adds the rule; wired by criterion 14's enumeration in PR 3, which lands first (2026-09-14: PR 3 never merged and criterion 14 is open, so nothing wires the rule into `make check`; see "The closure state today"). (2026-09-14, superseding the sentence before it: criterion 14 is cut by decision note 1942, and #820 runs the whole lint, rule 7 with it, in `make check`) |
| 9, 12, 18, 19, 22, 23 — the instruction layers | PR 4; criterion 19 and criterion 23's first half by the operator edit of 2026-09-07; criterion 23's second half, the writing repository's style override, by `sd-writing-pack` #41 (`be76962e`), read on 2026-09-13 and recorded under "Closing the item" (2026-09-14: PR 4 never merged; 18 and 22 are open, and criterion 9's settings clause is removed by decision note 1921, see "The closure state today"). (2026-09-14, superseding that sentence's claim about criterion 9 only, and leaving criteria 19 and 23's recorded landings and 18's open state standing: 9 closed when #931 merged as `0aeb42a1`. By decision note 1942, 22 is being implemented now, and 18 lands after 21 with 31(a), with the `AGENTS.md` upstream Trellis guard and the `.trellis` residue line exempt. Criterion 22 closed later that day: #936 merged as `c3604594`) |
| 24, 25 — `paths.json`, the union with active trials, `sd skill try` and its row | PR 5 |
| 2, 3, 6, 10, 11, 32 — the registry runtime, the tiered path, trailers, the modes, reviewed head | (2026-09-14: criterion 6's `minimax` meter clause and criterion 11's demotion-note clause are open, see "The closure state today"; decision note 1942 defers 6's open parts to followup sd:788 and 11's to followup sd:789) (2026-09-16: sd:789 is `done`, #957 merged as `c43747e4`: `sd-ship` writes the demotion note when the remote lowers the mode; sd:788 is still `planning`) PR 6, which also carries criterion 5's vendor clause; with criterion 11's closing sentence — all three modes in `README.md` — in PR 1, so PR 1 must land before PR 6 rather than in any order with it |
| 13 — status from the row | PR 6 (the reader, which PR 7 lands after), PR 7 (the retire step, the `prd.md` writes, `sd-ship --deliver`, the reconciliation and the `sd_db` installer step at `prd.md:1541-1547`, whose files are in its Touches and in no other pull request's claim) (2026-09-14: the moved-default-branch clause is open, see "The closure state today"; decision note 1942 rewrites it to #802's refusal, and the test for the refusal is still to add). (2026-09-14: no step of the lane order schedules that test, and the note is silent on which pull request carries it. `Delivers: sd:10` on 31(c) is what still holds it). (2026-09-16: the test is `ReadyCase` in `tests/test_sd_ship_remote.py`, in the pull request that carries this row, under the team-lead decision recorded in "The lane order". The moved-default-branch clause is closed) |
| 26, 27, 28, 29 — use rows, promotion, suggestions, handoff | PR 8; criterion 28's `commands.yaml` and writing-manifest clauses checked by reading on 2026-09-13 and recorded under "Closing the item", not tested (2026-09-14: criterion 27 fails its own words on `main`, see "The closure state today"; decision note 1942 rewrites it to #802's queue design, and its help text is the first fix after #932, which merged as `107016fc`). (2026-09-14: criterion 27 is closed. #939 merged as `0feecae9` and fixed the help text at `bin/sd:3031-3046`) |
| 7 — no percentage removes the code review point | the grep, which passes (re-run 2026-09-13); the back-scoring of the seven passes is cut (operator, 2026-09-07); the forward ten-pass experiment, its report and its decision are deferred to followup sd:777 (owner decision, 2026-09-13, decision note 1920) |

Criterion 7 is the one row in this table with no pull request beside it, and
it stays that way after the 2026-09-07 cut. Its assertable half is a grep of
`bin/` and `skills/` for a percentage that disables a review point, which
returns nothing and is checked from any checkout. Its remaining half is a
report the operator writes after ten forward passes and a decision recorded
here. (2026-09-13: that half is now followup sd:777's, by owner decision in
decision note 1920, and this item no longer carries it.) Neither is code this item ships, so naming a PR for it would be a false
entry in a table whose whole value is that its entries are checkable.

## 2026-09-16 — criterion 21's code-path half and 31(a)'s `sd_sweep`: the sweep is cut

The system side went first, as decision note 1942 ordered:
`local-cron-jobs/jobs/sd-sweep-weekly.job` retired in system `e029934`
(#356), and on 2026-09-16 `launchctl list` filtered for `sweep` returned no
line. Then the pack cut.

**What is gone.** `bin/sd_sweep.py` (365 lines) and `tests/test_sd_sweep.py`
(702 lines). In `bin/sd`, the `sweep` verb, `sweep_roots`, the parser
registration, and the `datetime` and `sd_research_pins` imports that only
the verb used; `sd-research-kit fleet-pins` is now the one surface for the
pin report, and `source:bin/sd_research_pins.py::fleet` keeps its `trees`
parameter for the reason its docstring gives. The four prose sites that told
a reader to run `sd sweep` (`skills/sd-plan/SKILL.md`, the work-item README
template, `bin/sd-research-kit`'s help, `bin/sd_research_pins.py`) now name
`sd-status` or nothing.

**What moved rather than died.** `sd-status`'s `idle-planning` read three
names off the sweep module: the threshold and two of the functions behind
the aging basis. They are `sd_lib`'s now — `source:bin/sd_lib.py::DEFAULT_DAYS`,
`source:bin/sd_lib.py::touched`, `source:bin/sd_lib.py::last_active` — and
`bin/sd-status` changed only where it named the module: `IDLE_DAYS =
sd_lib.DEFAULT_DAYS`, two call sites and three docstring mentions. The
sweep's own date parser, `source:bin/sd_lib.py::item_date`, moved with them
so the basis is whole in one place, but `sd-status` never read it: its local
`source:bin/sd-status::_item_date` reads the same two sources in the same
order off the entry dict, and it stayed local (Copilot's third pass caught
the entry saying four names where the measurement is three). Nothing else in
`sd-status` moved; sd:431's slice D rewrites its `R10-D1` strings later and
separately. The cases that covered
the moved functions moved with them into `tests/test_sd_lib.py` (`ItemDate`,
`LastActive`, `ItemDirectory`, `Touched`); the cases that covered the scan,
the render, the branch annotation and the fleet pins went with the code they
tested.

**The tests.** `tests/test_cut_symbols.py` is criterion 31's file: a
governed-tree `git grep` per symbol, 31(a)'s `sd_sweep` today, with a control
that the grep finds a name the tree does carry. It also asserts the module and
its suite are absent, that `build_parser()` registers no `sweep` group, and
that the four moved names exist in the library.
`tests/test_archive_untouched.py` gained `NoDeletionPath`, criterion 21's
code-path half: `git grep -nE 'git rm|rmtree|rmdir' -- bin skills` is
compared against a frozen set keyed by file and text, not line number, with a
subset assertion so the residue cut lowers the count without an edit here, a
control that the grep still finds the frozen sites, and a check that no site
is in a sweep or park file. Re-measured on 2026-09-16 the set is the same
eight of 2026-09-05 on moved lines: the five `RESIDUE` commands in
`bin/sd-status`, `prune_empty_dirs` in `bin/sd_install.py` twice (docstring
and call) and its untrack-and-re-run error string. `tests/test_sd_status.py`
asserts `IDLE_DAYS` is 45 and, by reading the source, that it is assigned
from `sd_lib.DEFAULT_DAYS` and not restated. Fail-first on `2eafa78b`:
`FAILED (failures=4, errors=2)`. Mutations: a re-registered `sweep` parser,
a `shutil.rmtree` added to `bin/sd_lib.py`, `DEFAULT_DAYS = 46`, and
`IDLE_DAYS = 45` restated in `sd-status` each redden exactly the test that
guards them. The dead-code check's shared-name blind spot fell from 145 to
142 with the module, and `AMBIGUOUS_CEILING` in `tests/test_code_health.py`
fell with it, as that test requires.

**Two things the `sd_sweep` grep leaves alone, by name.** `docs/work/` and
`CHANGELOG.md`, which the criterion's own definition of the governed tree
excludes as history. And `tests/fixtures/*-round.json`: captured review
rounds, read from the GitHub API as they stood, and one Copilot body in the
sd:543 capture summarises a change to `bin/sd_sweep.py`. Editing a capture
to satisfy a grep would falsify the record it is kept for, so the captures
are excluded the way history is, and the exclusion is stated in the test's
docstring rather than hidden in a pattern.

**What 31(a) still owes: the `parked` and `archived` field cut.** Decision
note 1942 scopes those two symbols to the `sd_lib` item field and its
readers. The readers are `bin/sd-status` — the `--parked` flag, the parked
section, and the `entry["archived"]` and `entry["parked"]` filters in three
producers — and `tests/test_sd_status.py`. This pull request was told to
leave `bin/sd-status` alone beyond the import, because sd:431's slice D edits
that file next, so the field and its readers stand. The team-lead's decision
of 2026-09-16, reversible by the owner: 31(a) is closed for `sd_sweep`, and
the field cut is deferred to a later lane after slice D. Until that lane,
`ParkedAndArchivedReaders` in `tests/test_cut_symbols.py` freezes the reader
set, every `.parked`, `.archived`, `["parked"]` and `["archived"]` read under
`bin` and `dashboard`, as fourteen `(path, text)` rows, and asserts the set
has not grown, the shape criterion 21 gives the deletion verbs. The later
lane removes rows as it cuts readers; nothing before it may add one. It is
one edit to `bin/sd_lib.py` plus its readers, and no note yet says which
pull request carries it.

**What criterion 21 still does not assert**, unchanged by this entry: no test
puts a `planning` item under `docs/work/archive/` and runs `sd-status`,
`sd-plan` and `sd-review --scope planning` against it, and no test ships a
`done` item and re-runs `sd-plan` and `sd-ship` over it. Both clauses were
recorded open on 2026-09-14 and are still open.

## Landed 2026-09-16: criteria 13 and 5 close by test, 16 by re-measure

Team-lead decision 2026-09-16, under the standing authorization and
reversible by the owner: criterion 13's refusal test and criterion 5's
table-reads clause land as one small pull request before 31(b), and criterion
16's tick rides along. `ReadyCase` in `tests/test_sd_ship_remote.py` asserts
the two refusals of `source:bin/sd_ship_remote.py::ready` by message.
`SkillsThatRunAReview` in `tests/test_workflow_policy.py` enumerates the
skills that invoke a reviewer and asserts the link, the point and the absence
of a cap literal. Criterion 16 closed when #938 merged as `a3baf6d9`. Open
after this and #995 (the entry above): 18, criterion 21's archive-test
clauses, 31(a)'s `parked` and `archived` field cut, 31(b) and 31(c).
Followups sd:789 and sd:790 are `done`; sd:788 is still `planning`.

## Criterion 18 landed

2026-09-16, by the criterion 18 lane. At base `2eafa78b` the criterion's own
grep of the governed tree, `Trellis`, `.trellis` and `task.py` as literals,
returned 123 lines in 19 files; the new test
`tests/test_no_trellis_residue.py`, run red before the sweep, counted 113 of
them outside the ten exempt lines. After the sweep the grep returns nothing
outside the fourteen rows the test names: the ten exempt lines, the two held
lines below, and the two `ALLOWED_IF_PRESENT` lines that arrive with #995.

What the sweep did, by kind:

- The five `docs/spec/` record pages keep their bodies and lose the name:
  where a path, identifier or heading carried it, `predecessor` stands in its
  place, and each page's stale notice says so. The one section removed
  outright is the gitignore-block section of
  `docs/spec/backend/manifest-and-filesystem.md`, which was the stated reason
  `.gitignore` kept its marker pair; the markers went in the same change, and
  `CONTRIBUTING.md` and `docs/spec/backend/index.md` say what happened.
- The planning contract under `.claude/` names a work item under `docs/work/`
  and the move to `in_progress` where it named the framework's task script.
- The routing block of `AGENTS.md` names git and GitHub workflows instead;
  the upstream pull-request guard above it is untouched, as the exemption
  says.
- The pull-request template's two checklist lines about copied files and
  journals are one line about `docs/work/` pages. `.github/copilot-instructions.md`,
  `dashboard/sessions.py`, `dashboard/work.py`, `bin/sd_setup_github.py`, the
  template-links test, `WORKFLOW.md`, `.prism/rules.json` and
  `.gito/config.toml` lose their mentions in prose. `tests/test_sd_agents.py`
  no longer spells the name itself; the residue test greps `agents/` for it.

The test holds the exemption set as `(path, line text)` rows, the whole
line stripped: the four guard lines of `AGENTS.md`, the three `RESIDUE` lines
of `bin/sd-status` and the three lines of `tests/test_sd_status.py` that
exercise them. Keyed by text, an edit above a row does not move it, and an
edit to the line itself, a second literal appended to an exempt one say, is
not covered. A second test fails when a row matches no line or more than
one, so the set cannot outlive its lines. The test is in the always-run set
of the changed-files fast path, with the other tree walkers.

A separate `HELD` set, disjoint from the exemptions by a third test, names
the two lines the sweep could not reach: one word each in `bin/sd` (a
docstring listing dot-directories) and `skills/sd-plan/SKILL.md` (a list of
paths the plan skill may not write). Both files were held by #995
(fix-10-sweep) when the sweep ran, so the lane left them, labelled "held by
#995; reword in the follow-up"; team-lead hands the two rewords to the
sd:10 31(b) lane. #995 merged as `486a223b` with both words in place: after
this branch's rebase onto it the grep of those two files returns
`bin/sd:1753` and `skills/sd-plan/SKILL.md:169`, and nothing else. The
reword removes the word and its row. The set is
bounded above by a frozen copy of the two rows, `HELD_BOUND`, so it may only
shrink, and the criterion is closed in full when it is empty. Until then the
tick above is the sweep's, with those two words as the named remainder.
(2026-09-16, 31(b1): both words are reworded and `HELD` is empty; see
"Criterion 31(b1) landed" below.)

A third set, `ALLOWED_IF_PRESENT`, carries the two lines #995 adds to
`tests/test_archive_untouched.py`: the `FROZEN_DELETION_SITES` row that
quotes `sd-status`'s `.trellis` removal command and the comment above it
that names the framework. Team-lead's ruling: a test that names the residue
commands must name them, so both are permanent exemptions of the same kind as
`bin/sd-status:1091-1093`. They are matched by file and content, not by line
number, and may match zero lines, so the test is green whether #995 merges
before this branch or after it; a fourth test fails a row that matches two
lines. Proof, 2026-09-16, on a scratch worktree at this branch with
`git merge --no-commit --no-ff origin/feat/sd-10-sweep-cut` (`5691b193`)
applied: the only conflicts were this page and its `.citations.tsv`, both
outside the governed tree; `governed_rows()` returned 14 rows, the two #995
  lines at `tests/test_archive_untouched.py:221` and `:231` among them; and
`python -m unittest tests.test_no_trellis_residue` ended `Ran 4 tests`, `OK`.
Without the merge the same command also ends `OK`. #995 then merged as
`486a223b`; on this branch rebased onto it, the two lines stand at
`tests/test_archive_untouched.py:221` and `:231` and the test is green.

Outside the governed tree, `docs/review-learnings.md` keeps its rows marked
**historical**, which quote review comments by the paths they named at the
time, and its one curated lesson about journal sessions.

## Criterion 31(b1) landed

2026-09-16, by the 31(b1) lane, at base `29de1970`. The criterion's grep of
the governed tree, with the test's own file and the captured review rounds
excluded, found the thirteen symbols of this slice on these line and file
counts: `record_load` 5 in 2, `carrier_branches` 4 in 1, `_protection_gaps`
11 in 2, `load_acknowledgements` 7 in 2, `--stash-ref` 3 in 3, `--push` 7 in
3, `--park` as a bare flag 3 in 2, `argument-vocabulary` 21 in 21, `Standing
rule` in either case 13 in 7, `five gates` 1 in 1, `cron-jobs.sh` 0,
`Active item:` 8 in 8, `sd-deps` 6 in 4. After the sweep every count but two
is 0. `_protection_gaps` finds 14 lines and `load_acknowledgements` 10, all
in `bin/sd-status` and `tests/test_sd_status.py`, and the gate holds them
there.

The gate is `ProseSymbolsAndFlags` in `tests/test_cut_symbols.py`, run red
before the sweep on ten of its eleven symbols, `cron-jobs.sh` already at 0,
and on the `R10-D2` teaching check below. `PROSE_SYMBOLS`
(`source:tests/test_cut_symbols.py::PROSE_SYMBOLS`) is the frozen tuple of
name and pattern; one test greps the governed tree for each and names the
file and line of every hit. `--park` is bounded so `--parked`, the
`sd-status` flag over the `parked` field whose cut 31(a) deferred, does not
match, and a control test proves the bound still finds the bare flag.
`Standing rule` is matched in either case, since `standing rule 2` in a
comment cites the same undefined rule as `Standing rule 2` in a docstring.
`HELD_SYMBOLS` (`source:tests/test_cut_symbols.py::HELD_SYMBOLS`) names the
two held symbols and the files that may carry them; a test fails a hit
outside those files, and `HELD_SYMBOLS_BOUND`
(`source:tests/test_cut_symbols.py::HELD_SYMBOLS_BOUND`) is the frozen
ceiling, so the held set may only shrink. `TheRepealedRowStillTeaches` reads
the `R10-D2` row of `RULES` (`source:bin/sd_rules.py::RULES`) and asserts
its `teaches` names one heading of `skills/sd-handoff/SKILL.md` whose body
cites the rule id; leg a of `tests/test_rule_registry.py` skips repealed
rows, so without this test the teaching sentence could go with nothing
noticing.

What the sweep did, by kind:

- Cut from code, each with no consumer outside its file and its own tests:
  `record_load` and `load_age_seconds` from `bin/sd-handoff-restore`, with
  the lock-retry constants and the consumed-packet load log, so the restore
  step now stamps `consumed` and moves on; 180 deleted lines of code and
  418 of tests, `LoadLogTests` and `TornRecordTests`. `carrier_branches` from
  `bin/sd-status`, with its renderer loop, the `carriers` key of the handoff
  section and the one test that derived carriers from origin refs.
  `--stash-ref` from `bin/sd-handoff`, with the packet field, the `--show`
  line and the test that recorded it.
- Reworded, the symbol gone and the sentence kept: `Standing rule 1` and
  `Standing rule 2` are inlined at their thirteen sites in `bin/sd`, the
  plan decision template, `sd-spec`, `sd-suggest` and `tests/test_sd_plugin.py`,
  each saying what the rule said. The `R10-D2` row of `RULES` and the Lane B
  section of `skills/sd-handoff/SKILL.md` lose `--push` and `--park`
  together: the section is now `## Lane B is not implemented`, the row's
  `teaches` points at it, and the section body still cites `R10-D2`. `five
  gates` in `tests/test_skill_frontmatter.py` is the count it stood for. The
  seven `Active item prefix` bullets in skills and `contrib/` are deleted,
  and the five agents' opening-context paragraphs say what the dispatch
  prompt carries today, since nothing in `bin/` or `skills/` emits an
  `Active item:` line.
- Deleted: `skills/_shared/references/argument-vocabulary.md` and the line
  citing it in 57 skill pages, 21 of them governed; `contrib/sd-deps/` and
  its README row, so `sd-deps` leaves the command roster of
  `tests/test_skill_frontmatter.py` and `bin/sd-skill-adopt`, and the eleven
  named surfaces are ten commands plus `sd-help`. `README.md` changed on
  four lines outside the two `sd-deps` lines the lane was given, because
  `tests/test_skill_frontmatter.py` reads the README's count sentence and
  asserts the table's row count against it; none of the four is in a hunk of
  #1006.
- Criterion 18's two held words are reworded: the dot-directory list in
  `bin/sd` and the paths list of `skills/sd-plan/SKILL.md` name the
  directories and tools without the framework's name. `HELD`
  (`source:tests/test_no_trellis_residue.py::HELD`) is empty, `HELD_BOUND`
  is unchanged, and the module docstring names all three sets. `named_by`,
  which nothing called, is gone.
- Residue from #994 and #998: `tests/test_workflow_policy.py` gains a floor
  on the set of skills that run a review, the `sd-research-kit review`
  invocation shape in one alternation with `sd-review`, a mention fixture
  that must not count as an invocation, and a check that the linking
  sentence says the cap is the one on the row, with three negative
  fixtures. `docs/spec/guides/cross-layer-thinking-guide.md` names the
  upstream package instead of its scoped name. The #998 note above now
  counts fourteen rows.
- `tests/test_rule_registry.py`, held by the sd:431 lane: one baseline row
  removed from `UNCITED_SKILL_CLAIMS`, since the cut `stash_ref` sentence
  was the `sd-handoff` page's only uncited claim. `prd.md`'s requirement 13
  list marks `record_load` and `carrier_branches` cut, because their
  `source:` locators no longer resolve.

Not cut, and why: `_protection_gaps` and `load_acknowledgements` are the
live protection section of `bin/sd-status`. It applies the accepted gaps
recorded in `.github/sd-status.json`, a sensitive path under
`.github/sd-review.json`, and `README.md`, `CONTRIBUTING.md` and the
`sd-status` skill describe it. Requirement 13's cut is a rewrite of that
section to one `protected: yes/no` line, which changes what the owner sees
and what the acceptance file means; that is the owner's change, and the
gate holds the two symbols to their two files until it lands. The `authors`
policy key is 31(b2). The two kept 31(a) deferrals, `parked` and `archived`,
are untouched.
