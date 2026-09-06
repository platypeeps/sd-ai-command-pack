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
`skills/sd-research-repo/references/conventions.md` and
`tests/test_doc_citations.py`, which breaks when the page goes. Plus **`skills/sd-plan/SKILL.md`**, whose step 3 at `:38-41` "routes them to
the codex second-model lane" — the payload's own statement of the thing
criterion 4 greps for, which two earlier drafts scoped from the *filename*
`planning-adversarial-review-codex.md` instead. Criterion 4 is a grep for the
lane as a concept, and `git grep -niE 'second-model lane|codex (review
)?lane'` over the governed tree returns three files: `AGENTS.md:14`,
`skills/sd-plan/SKILL.md:40` and `skills/sd-receive-review/SKILL.md:3`. The
first and third were already here; the second was in PR 2's and PR 4's
Touches, neither of which claims criterion 4.

For criterion 5's vendor grep, the enumeration is the criterion's own
four-name list run over the whole `skills/` tree, not a subset. `git grep
-liE 'codex|openai|anthropic|claude' -- skills` returns **twelve** files:
`_shared/references/subagent-dispatch.md`, `sd-check/SKILL.md`,
`sd-handoff/SKILL.md`, `sd-help/SKILL.md`, `sd-plan/SKILL.md`,
`sd-propose-skills/SKILL.md`, `sd-research-repo/SKILL.md`,
`sd-research-repo/references/conventions.md`,
`sd-research-repo/templates/CLAUDE.md`, `sd-review/SKILL.md`,
`sd-ship/SKILL.md` and `sd-skill-adopt/SKILL.md`. All twelve are in scope
here. An earlier draft named three of them as "files the grep returns that
run no review" and stopped, having enumerated from the sentence that reported
the gap rather than re-running the criterion's grep. The two that matter most
are `sd-research-repo/SKILL.md:84` and the rendered
`sd-research-repo/templates/CLAUDE.md:82,87`, which carry more `codex`
invocations than the reference file beside them that was named.

**Why the Touches list reaches across `skills/`.** Criterion 5 asks that
*every* skill that runs a review name its point in the table and read the
cap from it, and that a grep of the payload for a vendor name inside a
skill's instructions return only the registry documentation. Criterion 4
asks that a grep of the governed tree for the deleted second-model lane
return nothing outside `CHANGELOG.md`. An earlier draft said this "means
deleting that lane's skill and agent files". It has neither: `ls agents/`
returns the five `sd-*` agents and none is this lane, and no `skills/`
directory implements it. The lane is `docs/planning-adversarial-review-codex.md`,
referenced from `AGENTS.md` at `:11-18`, from
`docs/spec/backend/manifest-and-filesystem.md:1519` and from
`skills/sd-research-repo/references/conventions.md:176` — and `AGENTS.md`
is a file criterion 4 names outright (`prd.md:1217-1218`). The same three
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
documents (`prd.md:1205-1209`). An earlier draft said "the keys the pack
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

**Verification.** Criteria 1, 5, 8 and 20, and criterion 4 whole. Criterion
4 is the sharp one: exactly one second-model lane named anywhere in the
payload, which is a grep over the governed tree and not a reading of the
page.

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
(`prd.md:1112-1160`), which gives a file and a line range for every cut, and
then widened by `git grep -l` over criterion 31's symbol list
(`prd.md:1604-1608`) to catch the readers requirement 13 does not name. An
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
`bin/sd-docs-lint:87-91`, `dashboard/work.py`, `dashboard/app.js`,
`tests/test_dashboard_work.py`, `tests/test_sd_lib.py`,
`tests/test_sd_docs_lint.py`, `skills/sd-receive-review/SKILL.md`,
`.claude/sd-ai-command-pack/planning-adversarial-review.md`,
`docs/spec/backend/quality-guidelines.md` and `docs/spec/guides/index.md`;
`--stash-ref` at `bin/sd-handoff:374` with `skills/sd-handoff/SKILL.md` and
`tests/test_sd_handoff.py`; `--park` and `--push` in
`skills/sd-handoff/SKILL.md`, `skills/sd-plan/SKILL.md`,
`skills/sd-status/SKILL.md` and `tests/test_skill_frontmatter.py`; the
`authors` **policy key** at `bin/sd-review:287`, `:1092`,
`bin/sd_setup_github.py:230,267`, `.github/sd-review.schema.json` and
`.github/sd-review.json:28`; and `Standing rule` in `bin/sd`,
`skills/sd-plan/templates/decision.md`, `skills/sd-suggest/SKILL.md` and
`tests/test_sd_plugin.py`.

**`authors` is two different things and criterion 31's grep cannot tell them
apart.** Requirement 13 removes the `authors` *policy key* at the five sites
above. Criterion 6 **introduces** `authors` as a row field —
`prd.md:1277`, "the row's `authors` naming both" — and PR 6 lands it in
`bin/sd_lib.py`, inside the governed tree, after this pull request. A bare
governed-tree grep for `authors` therefore passes here and fails again at
PR 6's merge, breaking criterion 30, which this page calls a precondition of
every merge. The criterion is scoped to the policy key in this item's ledger;
this pull request removes the key and not the word.

For the named bug fixes: `bin/sd_research_review.py`, `bin/sd-research-kit`,
`agents/sd-claim-verifier.md`, `skills/sd-fact-check/SKILL.md`, the
`adversarial-gate` surface, and **`bin/sd-docs-lint`**, which criterion 31's
regression-test clause reaches through requirement 13's second bug:
`bin/sd-docs-lint:242` compares the token before ` - ` with `none` instead of
`startswith`, so `Work: nonexistent-item` fails as a missing reason rather
than an unresolved path. No Touches list held that file for this pull
request, which claims the criterion that mandates its test. Plus
`skills/sd-plan/`, `skills/sd-status/`, `skills/sd-ship/`,
`skills/sd-plan/templates/work-README.md`, `tests/test_sd_docs_lint.py`, for the
`bin/sd-docs-lint:242` regression test above and **not** for the `none - `
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
`archived`, `record_load` and the rest. Plus **criterion 21's code-path
half**: "no sweep or park code path remains, and a grep of `bin/` and
`skills/` for `git rm`, `rmtree` and `rmdir` names nothing outside the
installer's own temporary paths." Deleting `bin/sd_sweep.py` and the
`parked` handling is this pull request's work; criterion 31's grep covers
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
quoted at `prd.md:870` — and not line 21, which is a claim about rendered
copies; an implementer following the old citation would have edited the
wrong paragraph and left "nothing, ever" unscoped. And criterion 12 has a
second half that appeared in no pull request at all: `README.md` must also
**list the skills that write tracked files** (`prd.md:1394-1395`). Both
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

## Slice 2, PR 6 — the registry reader, the tiered path, the protection

**Touches:** `bin/sd_lib.py`, `skills/sd-ship/`, the provider registry
reader, and the four files criterion 6 and the installer step require that
an earlier draft omitted when C-90 moved the criterion here without its
scope: **`WORKFLOW.md`**, because criterion 6's *first* clause is that the provider
registry format "is documented in `WORKFLOW.md` with the role vocabulary
`author` and `reviewer`" (`prd.md:1232-1234`) — a documentation obligation an
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
And `README.md`, for criterion 11's closing sentence — see below.

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

## Slice 2, PR 7 — the `docs/work` retire step

**Touches:** the migration's retire step (B's command), every `prd.md`
under `docs/work/` outside the archive, and — for criterion 13, which the
closure table filed here while this list reached none of it —
`bin/sd_lib.py`, `bin/sd-status` and `bin/sd-docs-lint`, which derive an
item's status from its row (`prd.md:1396-1397`); `skills/sd-ship/` and
`dashboard/`, for `sd-ship --deliver`, the hand-merge reconciliation, the
notes on the squash commit and `deliver` on the item screen
(`prd.md:1435-1449`) and the three kill-and-reconcile tests
(`prd.md:1470-1479`); and `bin/sd_install.py`, for the `sd_db` step
(`prd.md:1523-1529`).

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
**before the second slice**, not before this one: `prd.md:1194-1195` says
"Before the second slice, criteria 13 and 32 are recorded as waiting" — and
"before the second slice" means before slice 2 opens, not before every pull
request inside it. This pull request is **in** slice 2, as its heading says:
this item's landing order defers to B's (`prd.md:1178-1182`), and B's slice 2
at `B/prd.md:1145-1148` is where "`docs/work` and the register retire … in
the run that lands their writers". An earlier draft moved the boundary a
slice later and said the landing order said so "in those words"; a later one
argued the point by calling this the third slice, which contradicted the
heading above it and B's numbering both. Criterion 32 is covered by
the same sentence, and neither this pull request nor PR 6 noted it.

## Slice 2, PR 8 — rows for trials, uses, suggestions and handoff

**Touches:** `bin/sd`, the `PreToolUse`, `UserPromptSubmit`, `PreCompact`,
`SessionEnd` and `SessionStart` hooks — **five hooks from two criteria, not
five from one requirement**. Requirement 12 (`prd.md:984-998`) names three:
`PreCompact` and `SessionEnd` prompt the packet, `SessionStart` loads the
item's open rows. The other two come from criterion 26 (`prd.md:1571-1573`),
"The `PreToolUse` and `UserPromptSubmit` hooks write `skill_use` rows". Both
criteria are this pull request's, so the file set was right and the
justification was not: an earlier draft called all five "requirement 12
names" and cited `prd.md:993-995`, three lines carrying three of them; the nightly parse of
`~/.codex/sessions`; `skills/sd-suggest/`; `skills/sd-propose-skills/`;
`skills/paths.json`; `dashboard/`; `bin/sd-handoff` and
`bin/sd-handoff-restore`, which are the handoff path named as files; and
the writing repository's manifest, from which criterion 28 removes the
`skill-proposal` kind, plus **`sd shadow sync` (new)**, the surface
criterion 28's shadow rows are asserted against — neither of which any
Touches list named. `sd shadow sync` does not exist: `prd.md:955` introduces
it ("They are shadowed, not imported: `sd shadow sync` keeps their state"),
criterion 28 says only "appear as `shadow` rows after a sync", and no `shadow
sync` string appears anywhere in the pack. An earlier draft listed it as an
existing surface; it is built here, and marked new like `WORKFLOW.md` and
`skills/paths.json` are.

**Four surfaces the criteria name and an earlier Touches list did not.**
Criterion 26 requires "the Codex nightly parse writes the same shape", with
a test feeding one recorded session of each kind — so the parse is in scope,
and the OpenCode plugin is named by requirement 10 for when that surface is
in use. Criterion 27 requires the promotion and demotion pull request to
move the directory **and edit `paths.json`**, opened by the library and
never by the dashboard directly, which puts both `skills/paths.json` and
`dashboard/` in scope. Criterion 28 requires the `skill-proposal` kind to be
absent from the writing manifest and `sd-propose-skills` to write no vault
note.

`sd skill try` writing a trial row; the two hooks writing `skill_use` rows;
promotion and demotion each producing one pull request that moves the
skill; `sd-suggest` writing a row in every mode and filing nothing; and
handoff losing nothing because nothing lives only in context — a session
killed mid-task and restarted in the same directory begins from the row and
not from a re-read.

**Verification.** Criteria 26, 27, 28 and 29.

**Criterion 28 asserts against a file this repository does not have.** It
requires `sd suggest publish` to be no palette entry, "asserted by
enumerating `commands.yaml`"; `git ls-files` finds no `commands.yaml`
anywhere here, because it is item B's, written by B's dashboard. The
assertion is real but it runs against B's file, so this pull request sits
behind B's slice 4 for that clause alone. Flagged rather than quietly
dropped.

## Two things about the criteria list itself

**Criteria 31 and 32 are out of order in the `prd.md`.** 32 appears at line
1592 and 31 at line 1602, with 30 between them at 1591. Nothing depends on
it and no test reads the order, but a reader working down the list will hit
32 where they expect 31 and wonder what they missed. It is a `prd.md` edit,
noted here rather than made silently. An earlier draft of this paragraph
cited 1580 and 1590, which fall mid-body of criteria 29 and 32 — a reader
following the citation to fix the transposition would have landed inside a
different criterion.

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
  `mode` and `check` keys into `DEFAULT_BLOCK_BODY` (`:766-772`); PR 5
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
PR 7.** B's settled open question 3 (`B/prd.md:1666-1671`) puts the pack's
installer provisioning `sd_db` into the pack's virtualenv from B's checkout,
as a built copy at a tag and never editable, and says "Item A's criterion 13
carries it". Without it B's library lands and nothing installs it, and the
first `sd today` after B's PR 2 fails on import.

**Two earlier drafts got this wrong in two different ways at once.** They
called it "item B's criterion 13", which is a dashboard criterion in B's
slice 4 (`B/prd.md:1420-1430`: "Status change, assign, promote, demote and
`merge_policy` each round-trip from the dashboard to a row") and has nothing
to do with an installer. And they filed the step on two pull requests: this
section and PR 6's Verification put it on PR 6, while PR 7's Touches and the
closure table put it on PR 7. The clause is A's own criterion 13, at
`prd.md:1523-1529`, whose files (`bin/sd_install.py`) are in PR 7's Touches,
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
| 1, 4, 5, 8, 20 — the policy page, the lane, the review table, the conditional obligations | PR 1 |
| 31 — requirement 13 line by line | PR 2 |
| 21 — the archive untouched, and no sweep or park code path remains | PR 2 (the code paths), PR 7 (the archive diff) |
| 14, 15, 16, 17, 30 — the checks | PR 3 |
| 9, 12, 18, 19, 22, 23 — the instruction layers | PR 4 |
| 24, 25 — `paths.json`, the union with active trials, `sd skill try` and its row | PR 5 |
| 2, 3, 6, 10, 11, 32 — the registry runtime, the tiered path, trailers, the modes, reviewed head | PR 6, with criterion 11's closing sentence — all three modes in `README.md` — in PR 1, so PR 1 must land before PR 6 rather than in any order with it |
| 13 — status from the row | PR 6 (the reader, which PR 7 lands after), PR 7 (the retire step, the `prd.md` writes, `sd-ship --deliver`, the reconciliation and the `sd_db` installer step at `prd.md:1523-1529`, whose files are in its Touches and in no other pull request's claim) |
| 26, 27, 28, 29 — use rows, promotion, suggestions, handoff | PR 8; criterion 28's `commands.yaml` clause behind B's slice 4 |
| 7 — the seven `mezmo-world-simulator` passes scored | see below |

Criterion 7 is scored against another repository's passes and is the one
row in this table with no pull request beside it. It is evidence the item
collects, not code the item ships, and it closes when the passes are scored
and accepted rather than when something merges here. Naming a PR for it
would be a false entry in a table whose whole value is that its entries are
checkable.
