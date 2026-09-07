---
title: implement — four pull requests that need no database, then four that do
status: planning
created: 2026-09-05
---

# Implement

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
is a file criterion 4 names outright (`prd.md:1222-1223`). The same three
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
documents (`prd.md:1210-1214`). An earlier draft said "the keys the pack
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
(`prd.md:1116-1164`), which gives a file and a line range for every cut, and
then widened by `git grep -l` over criterion 31's symbol list
(`prd.md:1633-1637`) to catch the readers requirement 13 does not name. An
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
`.github/sd-review.json:28`; and `Standing rule` in `bin/sd`,
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
`prd.md:1291`, "the row's `authors` naming both" — and PR 6 lands it in
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

**This numbered unit is one pull request plus three landings that cannot be
one.** Criterion 19's subject is `~/.claude/settings.json`, which is under
the operator's home and in no git repository; criterion 23 deletes the
writing repository's `.claude/settings.local.json`; and the system
repository's guide is `system`'s. The page's framing — each numbered unit is
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
above. Two corrections to an earlier draft. The writes-nothing claim is
`README.md:34`, "**What it writes in a repository:** nothing, ever." —
quoted at `prd.md:873` — and not line 21, which is a claim about rendered
copies; an implementer following the old citation would have edited the
wrong paragraph and left "nothing, ever" unscoped. And criterion 12 has a
second half that appeared in no pull request at all: `README.md` must also
**list the skills that write tracked files** (`prd.md:1408-1409`). Both
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
`author` and `reviewer`" (`prd.md:1237-1239`) — a documentation obligation an
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
item's status from its row (`prd.md:1410-1411`) — and, in `bin/sd-docs-lint`
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
(`prd.md:1449-1463`) and the three kill-and-reconcile tests
(`prd.md:1484-1493`); and `bin/sd_install.py`, for the `sd_db` step
(`prd.md:1537-1543`).

B's one sitting for `docs/work`: freeze, import once more, verify, snapshot,
then remove every item's `status:` line outside the archive in one commit.

**Three things land in that commit and in this pull request that an earlier
draft of this page named nowhere.** All three come from item B's criterion 7,
enumerated clause by clause in B's round five, and each is a pack file no
`system` pull request can reach.

*The tracked marker.* `prd.md:584` and `prd.md:2575` both say the retire
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
**before the second slice**, not before this one: `prd.md:1199-1200` says
"Before the second slice, criteria 13 and 32 are recorded as waiting" — and
"before the second slice" means before slice 2 opens, not before every pull
request inside it. This pull request is **in** slice 2, as its heading says:
this item's landing order defers to B's (`prd.md:1183-1187`), and B's slice 2
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
`bin/sd_skill.py:117`. **Nothing writes it programmatically.**

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

### PR 8d — criterion 28, suggestions that file nothing

**Touches:** `skills/sd-suggest/`, `contrib/sd-propose-skills/`, `bin/sd`,
`bin/sd_suggest.py` (new), `bin/sd_shadow.py` (new), and the writing
repository's manifest, which is not in this checkout.

**Priced 364. Not funded by R11-D42. Last, because two clauses answer elsewhere.**

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
is. `skills/sd-suggest/SKILL.md:50` states the gap — "There is no `bin/sd-suggest`
yet" — and `:28` still files to a tracker, which this slice reverses. "Every
mode" is `bin/sd_lib.py:33` `MODES = ("full", "minimal", "guest")`: the row is
written in all three, and only `publish` is gated.

**Two clauses cannot close from this checkout, and this slice does not claim
them.** `commands.yaml` does not exist here — it is item B's, written by B's
dashboard — so the "no palette entry" assertion sits behind B's slice 4, as an
earlier draft already flagged. The writing manifest is another repository's, so
the `skill-proposal` removal reaches only the `contrib/sd-propose-skills/` half
from here. Flagged rather than quietly dropped, and the second of the two was
not flagged before.

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
`prd.md:1537-1543`, whose files (`bin/sd_install.py`) are in PR 7's Touches,
so PR 7 carries it and PR 6 does not. B's dependency is on the merge, not on
which of the two pull requests holds it, and PR 7 lands after PR 6.

## Closing the item

PR 7 or PR 8, whichever merges last, carries `Delivers:`. Then `prd.md`
goes to `status: done` and drops its `branch:` field in the same edit.

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
| 5 — the review table in exactly two places, and no bare vendor token in a skill | PR 1 (the two table clauses), PR 6 (the vendor clause whole: a converted token names a role, and no role resolves before PR 6's registry reader) |
| 31 — requirement 13 line by line | PR 2 |
| 21 — the archive untouched, and no sweep or park code path remains | PR 2 (the code paths), PR 7 (the archive diff) |
| 14, 15, 16, 17, 30 — the checks | PR 3 |
| 33 — no document names a `docs/work/` path that does not resolve | PR 7, which adds the rule; wired by criterion 14's enumeration in PR 3, which lands first |
| 9, 12, 18, 19, 22, 23 — the instruction layers | PR 4 |
| 24, 25 — `paths.json`, the union with active trials, `sd skill try` and its row | PR 5 |
| 2, 3, 6, 10, 11, 32 — the registry runtime, the tiered path, trailers, the modes, reviewed head | PR 6, which also carries criterion 5's vendor clause; with criterion 11's closing sentence — all three modes in `README.md` — in PR 1, so PR 1 must land before PR 6 rather than in any order with it |
| 13 — status from the row | PR 6 (the reader, which PR 7 lands after), PR 7 (the retire step, the `prd.md` writes, `sd-ship --deliver`, the reconciliation and the `sd_db` installer step at `prd.md:1537-1543`, whose files are in its Touches and in no other pull request's claim) |
| 26, 27, 28, 29 — use rows, promotion, suggestions, handoff | PR 8; criterion 28's `commands.yaml` clause behind B's slice 4 |
| 7 — the seven `mezmo-world-simulator` passes scored | see below |

Criterion 7 is scored against another repository's passes and is the one
row in this table with no pull request beside it. It is evidence the item
collects, not code the item ships, and it closes when the passes are scored
and accepted rather than when something merges here. Naming a PR for it
would be a false entry in a table whose whole value is that its entries are
checkable.
