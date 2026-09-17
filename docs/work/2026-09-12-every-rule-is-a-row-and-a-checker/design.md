# Design — every rule is a row and a checker

## The first decision is to rescope, and it comes before the approach

The backbone item proposes three prose rules. Measured, one is unimplementable
as written and one now contradicts sd:568, which merged as `730d4541` after
this item was filed. Recording that first, because the approach below assumes
the narrowed form.

### Prose rule 3, as written, fires 681 times

> no enforcement verb (refuses, never, always, cannot) without a rule id
> citation

Measured on `e6c2cb20`: 4,711 lines of tracked markdown carry one of those four
verbs. Narrowed to lines that also name a pack tool or a test — the population
the rule is actually about — it is 681 outside `docs/work/archive`, of which
264 are in `skills/`. Exactly 1 cites a rule id.

A check that reddens 681 lines on its first run is not adopted; it is disabled.
And the verbs are not a reliable signal on their own: *"never write into a
shared checkout"* is an instruction to a reader, not a claim about machinery,
and it cites nothing because there is nothing to cite.

**Narrowed form.** The rule applies to a claim that asserts a *tool behaviour*:
an enforcement verb whose grammatical subject is a pack tool or a test. It
carries a frozen baseline — of the uncited claims in `skills/`, which is
leg b's scope, not of the whole live-prose population. A baseline counts
violations, never a population; on the population, a new and correctly cited
claim would redden it. The baseline may fall and may not rise, which makes the
rule bite on every new uncited claim while costing nothing on the existing
corpus. This is the same device `tests/test_loc_caps.py`
already uses for line counts, and the same rule applies to it: a baseline is
never raised in the pull request that busts it.

#### Correction, 2026-09-12 (sd:622) — 263 had no predicate behind it

Every figure in the paragraph above, and in requirement 6 of `prd.md`, was
produced by a predicate that was never written down. Steps 1 to 3 could not
reproduce 263 and offered three readings of the same corpus instead. A second
independent reconstruction of those same three readings produced a third set of
figures again, for the plainest possible reason: each reconstruction had to
invent the counting rule the original never recorded, and each invented a
different one.

So no number here is safe to act on, including the ones the delivery note
offered as replacements. The correction is not a better number. It is that the
predicate now exists as code, in one place —
`source:tests/test_rule_registry.py::claims_in` — and the only figure recorded
anywhere is `UNCITED_SKILL_CLAIMS`, which is a PROJECTION of that predicate and
not its return value. `claims_in` returns every matching
`(first line, run, rule ids)` tuple; `uncited_skill_claims()` then filters to
the tuples whose ids are empty and counts them per document, and that per-
document mapping is what is recorded. The distinction is load-bearing: reading
the dictionary as "what `claims_in` returns" sends the next baseline update to
the wrong value.

Three properties of the predicate were load-bearing and unstated, and each is
now pinned by a test rather than remembered:

1. **The scope is one line.** A verb and a tool name in the same paragraph are
   not a claim about that tool. The paragraph and whole-document readings are
   kept as runnable code beside the shipped one, so a rejected reading can be
   re-measured instead of re-argued.
2. **The verbs are matched as written, in lower case.** A bullet opening
   *"**Never accept a repo path**"* — this pack's commonest way of writing a
   rule — is invisible to leg b. Measured on `239ff624`, reading the verbs
   case-insensitively finds 12 claims where the shipped predicate finds 8.
   Left standing deliberately: widening the predicate is a change to the rule,
   which this correction is not, and the risk section below accepted false
   negatives in writing.
3. **The subject is enumerated from `bin/` and `tests/`, never listed**, so a
   tool built next month is covered the day it is written.

Counts do not even order across the three readings, which is the mechanical
reason three people measuring "the same thing" each thought the others had
miscounted: a document read whole is one span, so the widest reading yields the
*fewest* spans while reaching the *most* documents. The test asserts
containment of the documents reached, not a count.

### Prose rule 1 is half-delivered, and now conflicts with sd:568

> no `file.py:NNN` citation — use `source:<file>::<symbol>`, because bin/ moves
> constantly and every line-number citation is a future lie

The symbolic form already exists, and it is *not* `bin/sd-docs-lint` that
implements it. `source:bin/sd-docs-lint::resolve_citation` says so in its own
docstring: only `docs/work` markdown resolves there, and a citation into code
is the adjacency rule's business. The symbolic form is implemented in
`source:tests/test_doc_citations.py::source_declaration_error`, against the
`STABLE_SOURCE` pattern. 8 tracked files carry the form — 7 documents using it
in earnest, plus `tests/test_doc_citations.py`, whose fixtures include a
deliberately unresolvable one. So the alternative the rule demands is built,
but any plan that extends the wrong tool to enforce it would have extended a
resolver that refuses code citations by design.

But the flat prohibition cannot be adopted, for two reasons measured after the
item was filed:

1. The line-anchored form carries the pack's only *verified* citations — but
   far fewer than the raw count suggests, and the first draft of this document
   got that badly wrong. It claimed 325 line-anchored citations "each one
   enforced". `source:tests/test_doc_citations.py::anchored_citations` returns
   only the rows whose reason is `compared`, and the census over the corpus is:

   | Bucket | Rows | Staleness-checked |
   |---|---|---|
   | `no-adjacent-anchor` | 2,732 | no |
   | `elided-path` | 2,356 | no |
   | `archived-stale` | 277 | no |
   | `anchor-not-a-symbol` | 144 | no |
   | `separator-not-adjacent` | 134 | no |
   | `compared` | 54 | **yes** |
   | `declared-absent` | 1 | n/a |
   | `quoted` | 1 | by its own reason |
   | total classified | 5,699 | 54 |

   **54 of 5,699.** So prose rule 1's complaint is stronger than this document
   first allowed, not weaker: the overwhelming majority of line-anchored
   citations are counted, not checked. What survives is narrower — the
   `compared` and `quoted` rows are genuinely verified, and those are the ones a
   prohibition would have destroyed.
2. sd:568, in flight on pull request #870, introduces the marker
   `[quoted: path:line]`, whose whole purpose is to point at a line and prove
   the quoted text is on it. A line number is load-bearing there by
   construction. A rule forbidding line numbers would forbid the pack's newest
   evidence mechanism.

**Narrowed form.** Prefer the symbolic form *where a symbol exists*. A citation
naming a line inside a function should name the function. A citation naming a
line that is not inside any symbol — a module-level constant's comment, a
`quoted` reason, a line of prose in another document — keeps its line anchor,
because the symbolic form cannot express it. The checker is therefore "a
`path:line` citation resolving inside a named symbol should cite the symbol",
not "no `path:line` citations".

sd:525 already carries the broader complaint that line anchors shape code
layout. This item should not try to settle sd:525; it should stop asserting a
rule that contradicts it.

### Prose rule 2 survives, but it needs an exemption it was not filed with

> no literal count restating something enumerable — derive it

No conflict with other machinery. But as filed it would fail on *this document*,
which is nothing but literal counts: 768, 681, 264, 54, 5,699. Every one is a
measurement of an enumerable property, written down.

The distinction the rule needs: a count is a **claim** when prose asserts it as
the current state of the repository and a reader would act on it being current.
It is a **measurement** when it is reported against a named commit, as a
finding. `bin/` carrying 768 `def` lines is a measurement of `e6c2cb20`;
"the pack ships 16 tools" in a skill is a claim that rots.

So the rule applies to prose that states a count as present-tense fact, and
exempts a count carrying its own commit or date. That exemption must be written
into the rule before the rule lands, because the first document it would redden
is the one proposing it — and a rule whose own design document violates it gets
an exception carved out under pressure later, which is how rules stop meaning
anything.

## Approach

**The registry is a table in code, in the shape of `CLASSES` in `bin/sd-status`.**
A tuple of rows; every consumer iterates it; nothing carries a second list.
Each row records id, subject, checker, proof, scope, and teaching section.

**`checker` is a source location and `proof` is the mutation that reddens it.**
The checker is written `path::symbol` — a string — and the proof states, in one
sentence a reader can execute, what has to be broken for that checker to fail. A
row with a checker and no proof fails the meta-check, and leg d executes the
mutation rather than trusting the sentence. This is a correction, made on
2026-09-13: the field held the function object until then, and holding a
callable made the registry import every checker's module at load time and left
it unable to name the two places enforcement actually lives — an extensionless
entrypoint such as `bin/sd-review`, and a test over the tree.

**The rejected alternative: a YAML or JSON registry file.** It reads better and
it is the obvious choice, which is why it needs the explicit rejection. The
argument this rejection first rested on has expired: it was that a data file
cannot name a callable, so something would have to resolve a string back to a
function, and that resolver would be a second source of truth failing at run
time rather than at import time. `checker` *is* a string now. The rejection
stands on two other grounds. The string is resolved by
`source:tests/test_doc_citations.py::source_declaration_error`, the resolver
this pack already uses for its documentation citations, so there is still one
resolver and the registry did not bring a second. And what a data file would
cost is the rest of a row: `subject` and `proof` are paragraphs whose value is
that a reader meets them beside the row, they are reviewed as code is reviewed,
and their shape is checked by the tuple's own type rather than by a schema file
somebody has to keep honest. What the import used to buy is bought better by leg
d, which proves the checker enforces rather than only that its name resolves.

**The meta-check is the deliverable, not the rules.** Legs a to d are what
make the system self-maintaining. The initial rules are a payload; a registry
with the meta-check and two rules is worth more than fifteen rules with no
meta-check, because the second one starts drifting the day it lands.

**Leg d is what makes legs a to c worth anything.** Each of the first three
asserts a *link* — a row is taught, a claim cites a row, a citation resolves to
a row — and none of them looks at what the checker does. A row naming
`sd_lib.repo_root`, the resolver by which its own rule would be violated, passed
all three; the only thing that stopped it was a human reviewer reading the diff.
Leg d is that reader made mechanical.

**The three tiers are three call sites of one registry, not three
implementations.**

| Tier | Scope | What runs |
|---|---|---|
| authoring | the file being written | the skill consults the registry and names the rule ids in scope |
| pre-commit | the staged files for Ruff; whole for the two test passes | `hooks/pre-commit`: Ruff over the staged Python, then `tests.test_code_health` and `tests.test_doc_citations` whole; `bin/sd-docs-lint` not run (step 7, 2026-09-16) |
| CI | the repository | full run with baselines, the backstop |

### The item has diff-scoping backwards, and the clock says so

The backbone item justifies diff-scoping like this:

> Full-repo complexity and duplication over 781 functions is too slow to run
> per commit, and a slow hook gets bypassed.

The premise is false. Timed on `e6c2cb20`, on the machine of the day:

**Superseded 2026-09-16 by step 7's readings**, recorded under the decision
"the code checkers are not diff-scoped" below; the table stays as the record.

| Whole-repository pass | Wall time, `e6c2cb20` — **expired, see below** |
|---|---|
| `tests/test_code_health.py` — complexity, length, depth, clones | 1.71 s |
| `tests/test_doc_citations.py` — the whole citation corpus | 0.84 s |
| `bin/sd-docs-lint` — rules 1 to 7 over the corpus | 19.87 s |

On those numbers the code pass the item calls too slow finished in under two
seconds over the whole tree, and the tool the item proposes to *extend* —
because it "already walks the corpus" — was the one that took twenty.

#### Retired 2026-09-14: none of those three numbers reproduces

The table above is kept as the record of what was measured on `e6c2cb20` and
is no longer a description of this repository. Two independent re-measurements
have been taken since, and they disagree with the record and with each other:

| Whole-repository pass | `e6c2cb20`, recorded | `fea53e96`, clone, one run each | `075eecf2`, this checkout, 2026-09-14 |
|---|---|---|---|
| `tests/test_code_health.py` | 1.71 s | 2.12 s | 2.18 s – 6.24 s over four runs; 1.66 s user + 0.35 s sys |
| `tests/test_doc_citations.py` | 0.84 s | 2.26 s | 2.44 s – 5.69 s over four runs; 1.67 s user + 0.67 s sys |
| `bin/sd-docs-lint` | 19.87 s | 2.85 s | 32.6 s – 35.9 s over three runs; 2.0 s – 2.2 s user + 1.7 s – 2.3 s sys |

**No row of the right-hand column is offered as a replacement record.** The
`075eecf2` figures were taken on a machine running many concurrent agents, and
the gap between wall time and CPU time says so plainly: `bin/sd-docs-lint`
spends about four seconds of CPU and about thirty-three seconds of wall clock,
and it starts no subprocess and opens no socket, so the difference is
contention and not work. A wall-clock number taken under that load measures the
machine, not the checker.

Two things survive the noise, because CPU time is not load-sensitive the way
wall time is:

1. **The code pass is over two seconds.** Every reading since `e6c2cb20` puts
   it there, on two machines and two commits. That is exactly the condition the
   decision below names as its own reversal trigger, so the trigger has fired
   and the diff-scoping decision is reopened rather than inherited.
2. **`bin/sd-docs-lint` is no longer twenty seconds of work.** Its CPU cost is
   of the same order as the other two passes. The sole justification recorded
   below for diff-scoping it — that it is an order of magnitude slower than
   everything else — is not supported by any reading taken since.

Where the replacement numbers come from: step 7's own pull request, which
re-runs all three passes and times the assembled hook on a one-file diff, on a
machine whose load is stated, and records them beside their commit.
`implement.md` step 7 carries that instruction, and the owner confirmed it on
2026-09-14 (note 1989) rather than dropping the pre-commit tier for CI alone.

The function count is also stale: `bin/` carries 768 `def` lines today, not
781. That figure is a literal count restating something enumerable, which is
the exact defect prose rule 2 forbids, committed inside the item that proposes
prose rule 2. It is quoted here only to be retired.

**So the tiering inverted**, on those numbers: the code checkers run whole in
both tiers, there is no second scope to disagree with the first, and only
`bin/sd-docs-lint` earns diff-scoping — with earning it as a prerequisite,
since its cost had to be attributed to a stage before anyone scoped around it,
because a tool that is slow for a reason nobody measured will be slow again
after the workaround.

**That conclusion is now unsupported in both halves, and step 7 re-makes it.**
The code pass is over two seconds, so "run it whole, it is free" no longer
follows; and `bin/sd-docs-lint` is no longer the outlier, so the one pass
singled out for diff-scoping may not need it. The prerequisite stands whatever
the timing says — nobody scopes around a cost that has not been attributed —
and so does the argument in the paragraph below, which never depended on a
number.

A hook that is slow does get bypassed, and a bypassed hook is worse than none —
it is an advisory rule wearing the costume of an enforced one, which is the
exact failure this item exists to end. That argument is sound. It just does not
apply to the checkers the item aims it at.

## Decisions

- **2026-09-12 — the registry is a code table, not a data file.** Reversed if a
  consumer outside Python needs to read the registry; at that point the table
  gains a serializer, and the table stays the source.
- **2026-09-13 — `checker` is a `path::symbol` location, not a callable, and
  every checker carries a `proof`.** The callable form cost an import edge from
  the registry to every enforcement in the pack, and it could not name a
  suffixless entrypoint or a test, which was the recorded obstacle on three of
  the four best-taught stranded ids. Reversed only by a reason stronger than
  either, since the resolution the import performed is now performed by the
  resolver the documentation citations already use.
- **2026-09-13 — the meta-check has a fourth leg, and it executes the proof.**
  Legs a to c assert links between a row and the corpus; none of them asks what
  the checker does, and a row naming a non-enforcing symbol passed all three.
  Leg d applies each row's mutation in a private copy of the tree and requires
  the named test to go green-then-red. Reversed if the copy-and-run cost stops
  being affordable, at which point the leg is scoped rather than dropped — a
  registry whose checkers are unproven is the state this item exists to end.
  **Budgeted 2026-09-16 (owner decision Dec-6, note 1989): one tracked-file
  copy per run, shared by every row and both controls.** Measured with one
  command each: `LegD` took real 6.81 s for 8 tests at load average 39.25
  before the change and real 2.72 s for 9 tests at load average 32.26 after
  it, on the same machine under different load, so no ratio is claimed. The
  copy is 2.16 s for 1306 tracked files and is now paid once; what remains is
  two child `unittest` runs per row, so the cost is still linear in rows but
  with the copy out of the slope. Sharing is as strong as copying because the
  `diff -rq` restore proof runs after every row, and a control in `LegD`
  leaves a byte in the copy and requires that proof to fail.
  **Re-measured 2026-09-16, step 5.** The copy carries an index of its own
  since the code rules became rows: their checkers enumerate the corpus with
  `git ls-files`, and in an index-less copy the named test ran nothing. One
  copy per run still holds; `LegD` read real 3.69 s for 9 tests at load
  average 7.90 before the four rows and real 14.47 s at 15.85 after, on the
  same machine under different load, so no ratio is claimed. The slope is
  the code-health walk, about 1.2 s a child run, two runs a row.
  **Budgeted 2026-09-16 (sd:971): `LegD` is 21 s of wall time, and the
  controls run in one child.** The rule is twice the measured wall time,
  rounded up to the second, so a busier machine passes and a doubled leg
  does not. Measured with one command, `uptime; /usr/bin/time -p python -m
  unittest tests.test_rule_registry.LegD`, on the pack venv: real 14.71 s
  for 9 tests at load average 6.31 before the change and real 10.34 s at
  6.28 after it; the module real 31.87 s at 11.87 before and real 23.56 s
  at 6.09 after, so no ratio is claimed for the module. A code-health
  control child read 1.28 s and a child that walks nothing 0.10 s; one
  child running all four code-health nodes read 1.28 s, and all eight
  nodes 1.95 s, so the walk is per child, not per node, and the cut is
  one control child that runs every row's test (`source:tests/test_rule_registry.py::batched_controls`),
  then one mutated child per row. The shape is held by
  `source:tests/test_rule_registry.py::TheSharedCopy`: children at most
  `rows + 1 + 2 * controls`. When a row pushes `LegD` past 21 s the leg
  is scoped, never dropped: the row's control still runs in the shared
  child and its mutation in its own, and the budget is re-measured with
  the same command and restated here with the load average.
- **2026-09-13 — leg a counts a citation in a section's body, never in its
  heading.** `section_body` drops the heading line, so a row's id has to appear
  in the body text of the section its `teaches` names. `R10-D1` to `R10-D3`
  meet this next. Reversed only as a deliberate change to leg a's measurement,
  made in its own slice.
- **2026-09-12 — prose rule 3 is narrowed to tool-behaviour claims and carries
  a frozen baseline**, the uncited claims in `skills/`, held per document. Reversed if the
  corpus is deliberately swept and the baseline reaches a number small enough
  to fix outright. **Superseded 2026-09-12 by the correction above (sd:622):
  263 has no predicate behind it and neither do its proposed replacements. The
  baseline is whatever `claims_in` returns, recorded per document in
  `UNCITED_SKILL_CLAIMS`.**
- **2026-09-12 (sd:622) — leg b's predicate has one recorded definition, and
  the rejected readings are kept as code rather than as numbers.** The scope is
  the line, the verbs are matched as written, and the subject is enumerated;
  each is pinned by a test. Reversed only by a change that says which property
  it is changing and what that costs, measured.
- **2026-09-12 — the backfill lands in slices, and a slice records the reason
  for every id it did not take.** Registering a rule needs a checker reachable
  from `bin/` and a skill section that teaches it; most stranded ids fail one
  or the other, and rediscovering which is most of the cost. Reversed if the
  remaining ids turn out to share one obstacle that can be removed at once.
- **2026-09-12 — prose rule 2 gains an exemption for counts reported against a
  commit.** Without it the rule reddens its own design document. Reversed if a
  cheaper discriminator than "carries a commit or a date" is found.
- **2026-09-12 — prose rule 1 is narrowed from a prohibition to a preference
  conditioned on a symbol existing.** Reversed by sd:525 deciding the broader
  question against line anchors, which would then be that item's call to make,
  not this one's.
- **2026-09-12 — the code checkers are not diff-scoped; only
  `bin/sd-docs-lint` is.** Measured, not assumed. Reversed if the whole-tree
  code pass passes two seconds, at which point the timing is re-run and the
  decision re-made on the new number rather than on this one.
  **Reversal clause triggered 2026-09-14, and the decision is reopened, not
  re-made here.** The code pass is over two seconds on every reading taken
  since `e6c2cb20`, and the numbers that singled out `bin/sd-docs-lint` have
  expired in the other direction too. The re-run and the re-decision belong to
  step 7's own pull request, per the owner decision of 2026-09-14 (note 1989);
  nothing in this document should be read as a live diff-scoping decision until
  that lands.
  **Re-made 2026-09-16 in step 7's pull request, on readings taken at
  `ef7c0c7b` with the one-minute load average stated, three runs each,
  `/usr/bin/time -p`, the pack's `.venv/bin/python`:**
  `tests.test_code_health` real 1.79 / 1.71 / 1.74 s at load 9.90 / 8.73 /
  7.39; `tests.test_doc_citations` real 3.41 / 3.38 / 3.33 s at load 9.91 /
  8.75 / 7.39; `bin/sd-docs-lint` real 20.34 / 21.85 / 21.65 s at load 9.91 /
  8.75 / 7.52, with 2.0 s of user+sys CPU on each run. The assembled hook on a
  one-file diff, a line appended to a skill page and staged, read real 5.26 /
  5.07 / 5.01 s at load 7.47 / 7.60 / 7.55. No ratio between runs at
  different loads is claimed. The decision, in three parts. (1) **The code
  checkers run whole in the hook, and so does the citation pass.** The 2 s
  reversal trigger above did not fire on these readings: the code pass is
  under it on all three. Neither pass has a diff-scoped form to choose:
  `.github/scripts/select-tests.py` puts both in `ALWAYS_RUN`, because they
  walk the tree rather than name a file, so the pack's own fast path runs
  them whole on every change, and the hook does the same. Together they read
  5.04 to 5.20 s. (2) **`bin/sd-docs-lint` is not in the hook, whole or
  scoped.** Its `--changed` flag needs `--pr-body` and scopes rule 8 only;
  rules 1 to 4, 6 and 7 read the whole corpus whatever is passed, so there is
  no file-scoped run to time. And its cost is now attributed: a `cProfile`
  run at the same commit puts 20.7 of 21.2 s inside `sd_lib.delivered`,
  called from rule 2's `check_ready`, which runs `git fetch` and
  `git ls-remote` seventy times in all. That is network, not work. A commit
  hook that reaches the network is slow when the link is slow and fails when
  it is absent, which is the bypassed-hook failure this section is about, so
  the tool stays in `make check` and CI, where the 2026-09-14 attribution
  prerequisite is now met for whoever scopes around it. (3) **Ruff runs on
  the staged Python only**, which is the one gate here that is file-scoped by
  nature. The hook is **budgeted at 8 s** wall on a one-file diff; the number
  is in its header and in `BUDGET_SECONDS`, `tests/test_pre_commit_hook.py`
  holds the three copies equal, and the hook prints its own wall time on
  every exit so a reading over the budget is seen by the person who paid it.
  Reversed if a hook reading on a one-file diff passes the budget at a stated
  load under 10, at which point the slower pass is dropped from the hook and
  left to CI, not diff-scoped, since neither has such a form. The hook is
  Python, not shell: `tests/test_no_shipped_shell.py` allows tracked shell
  under `.github/scripts/` only. **The layout dodges the pack's own residue
  detector.** `bin/sd-status` carries a `RESIDUE` row for a `.githooks`
  directory and a `hooks-path` row for any `core.hooksPath` set, each with a
  removal command (`git config --unset core.hooksPath; git rm -r
  --ignore-unmatch .githooks`), because those two were the retired gate
  stack's signatures in every consumer. A hook installed the conventional way
  would have matched both rows in this checkout, and the pack's status tool
  would have told the operator to delete the pack's hook. So the file is
  tracked as `hooks/pre-commit`, a visible directory the detector does not
  glob, and `make hooks` installs it as the link
  `.git/hooks/pre-commit -> <checkout>/hooks/pre-commit` in the directory
  git names, with an absolute target because from a worktree that directory
  is the main checkout's and the link must name the worktree's copy; it
  refuses by name to replace anything else at that path;
  `core.hooksPath` is never set. `tests/test_pre_commit_hook.py` runs
  `residue_section` from `bin/sd-status` over a checkout laid out this way,
  after `make hooks`, and requires neither row; the detector is not edited.
- **2026-09-12 — the meta-check lands before any rule.** A registry with zero
  rows must pass its own tests. This makes step 1 independently landable and
  independently green.

## Risks

**Accepted: the baseline can be gamed.** Anyone may add a machinery claim if
they delete another. The baseline catches drift in aggregate, not per line.
Accepted because the alternative — fixing every uncited claim before the check
can land — means the check never lands.

> **Re-examined 2026-09-12 (sd:622), because the correction above dissolves the
> reason this risk was accepted.** The acceptance rested on 263 being too many
> to fix outright. It is not 263, and whatever the true figure is it is small
> enough that "fix them all" is no longer obviously unreachable. The
> *conclusion* survives, but on different ground and only partly: the baseline
> is held per document, so a new uncited claim in one skill cannot be netted
> off against a cleanup in another, and the aggregate game the risk describes
> is closed. What remains open is the within-document trade, which is the
> narrower risk this paragraph should have described. Sweeping the corpus to
> zero is now a real option and is left to its own item rather than smuggled in
> here.

**Accepted: leg b needs a parser for "the subject of this verb is a tool", and
English does not oblige.** The narrowed rule will have false negatives. It is a
ratchet on new claims, not an audit of old ones, and a ratchet with false
negatives still only moves one way.

**Accepted: the R-id backfill is judgement work, not mechanical.** 33 of the 50
definitions sit inside archived planning documents, and deciding which are
still live rules rather than historical decisions cannot be automated. Step 2
is the expensive step and it is sized accordingly.

**Accepted: "a skill cites the rule and does not restate it" is half
unenforceable.** Citation is checkable; non-restatement is not, short of
judging whether two English sentences say the same thing. The requirement was
narrowed to the checkable half rather than left standing as an enforcement
claim with no enforcer — which would have reproduced, in this item's own
requirements list, the `WORKFLOW.md` defect that motivates the item.

**Accepted, recorded 2026-09-14: `MUTATIONS` is a second copy of `proof`, and
it is the one second list this item keeps.** A row states its mutation twice.
`Rule.proof` states it in a sentence a reader can execute, in `bin/sd_rules.py`
beside the row. `MUTATIONS`, in `tests/test_rule_registry.py`, states it as
`(path, old, new, test)`, and that tuple is what leg d actually applies. This
is the shape the whole item exists to end, committed inside the item's own
machinery, so it is recorded here as an accepted gap rather than left for the
next reader to discover and file as a defect.

It is accepted because the two copies cannot be collapsed. Prose does not run,
so the sentence cannot be the mutation; and a tuple of `old` and `new` strings
is not a sentence a reviewer can follow to a rule's meaning, so the mutation
cannot be the sentence. Deleting either one loses something the row needs.

What holds them together, and how far it reaches:
`source:tests/test_rule_registry.py::LegD` carries
`test_every_proof_names_the_file_and_the_test_its_mutation_uses`, which
requires the proof sentence to contain the file the mutation edits and the leaf
name of the test that reddens. That is string containment over two of the four
fields. **The edit itself — `old` and `new` — is held by nothing.** A proof
sentence describing a different change to the same file, reddening the same
test, passes. The gap is narrow and it is real, and it is the reason a row's
proof is reviewed as prose rather than trusted as a specification.

Reconsidered if a row is ever found whose proof and mutation disagree, or if a
form is found that is both executable and readable — at which point the field
becomes one thing and this paragraph goes.

**Accepted, and answered in two steps: what a rule id means when its rule is
repealed.** A repealed rule's id must not become reusable, and live prose
citing it must not silently start resolving to a different rule. The
tombstone state came first, on 2026-09-13 with step 4's second slice:
`source:bin/sd_rules.py::STATES` allows exactly two values, `live` and
`repealed`, and a `repealed` row holds `None` in both `checker` and `proof`
(`test_every_live_rule_names_a_checker_that_exists`, which reports a value
in either field as "repealed, but still holds"). Leg a skips the row; leg c
resolves it, because `source:tests/test_rule_registry.py::registered_rule_ids`
returns live and repealed ids alike; and the id-uniqueness check is what
keeps it from ever being handed out again. The first repeal came second, on
2026-09-16, under the owner decision of 2026-09-14 (note 1989, Dec-4):
`R10-D2` is a `repealed` row, because the section that teaches it, whose
heading at `skills/sd-handoff/SKILL.md:118` reads "Lane B (`--push`,
`--park`) is not implemented", says in that heading that the behaviour the
rule names does not exist. A live row would have asserted an enforcement nothing performs;
the repealed row answers the citation and asserts nothing. The row's
`teaches` still names that section, so a reader following it lands on the
sentence that says why there is nothing to run.
