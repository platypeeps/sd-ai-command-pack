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
carries a frozen baseline — of the 263 uncited claims in `skills/`, which is
leg b's scope, not of the 681 live-prose population. A baseline counts
violations, never a population; on the population, a new and correctly cited
claim would redden it. The baseline may fall and may not rise, which makes the
rule bite on every new uncited claim while costing nothing on the existing
corpus. This is the same device `tests/test_loc_caps.py`
already uses for line counts, and the same rule applies to it: a baseline is
never raised in the pull request that busts it.

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
Each row records id, subject, checker, scope, and teaching section.

**The rejected alternative: a YAML or JSON registry file.** It reads better and
it is the obvious choice, which is why it needs the explicit rejection. A data
file cannot name a callable; it names a string, and something must resolve that
string to a function. That resolver is a second source of truth about which
checkers exist, and it fails at run time rather than at import time. A code
table holds the function object itself, so a row naming a checker that does not
exist is an `ImportError` on the first import, before any test runs. The whole
point of this item is to stop rules and machinery drifting; choosing a format
that reintroduces a gap between them would be the same defect one layer down.

**The meta-check is the deliverable, not the rules.** Legs a, b and c are what
make the system self-maintaining. The initial rules are a payload; a registry
with the meta-check and two rules is worth more than fifteen rules with no
meta-check, because the second one starts drifting the day it lands.

**The three tiers are three call sites of one registry, not three
implementations.**

| Tier | Scope | What runs |
|---|---|---|
| authoring | the file being written | the skill consults the registry and names the rule ids in scope |
| pre-commit | whole, except the one slow checker | the code checkers whole; `bin/sd-docs-lint` diff-scoped |
| CI | the repository | full run with baselines, the backstop |

### The item has diff-scoping backwards, and the clock says so

The backbone item justifies diff-scoping like this:

> Full-repo complexity and duplication over 781 functions is too slow to run
> per commit, and a slow hook gets bypassed.

The premise is false. Timed on `e6c2cb20`, on this machine:

| Whole-repository pass | Wall time |
|---|---|
| `tests/test_code_health.py` — complexity, length, depth, clones | 1.71 s |
| `tests/test_doc_citations.py` — the whole citation corpus | 0.84 s |
| `bin/sd-docs-lint` — rules 1 to 7 over the corpus | 19.87 s |

The code pass the item calls too slow finishes in under two seconds over the
whole tree. The tool the item proposes to *extend* — because it "already walks
the corpus" — is the one that takes twenty.

The function count is also stale: `bin/` carries 768 `def` lines today, not
781. That figure is a literal count restating something enumerable, which is
the exact defect prose rule 2 forbids, committed inside the item that proposes
prose rule 2. It is quoted here only to be retired.

**So the tiering inverts.** The code checkers run whole, in both tiers, and
there is no second scope to disagree with the first. Only `bin/sd-docs-lint`
earns diff-scoping, and earning it is a prerequisite: its 19.87 s must be
attributed to a stage before anyone scopes around it, because a tool that is
slow for a reason nobody measured will be slow again after the workaround.

A hook that is slow does get bypassed, and a bypassed hook is worse than none —
it is an advisory rule wearing the costume of an enforced one, which is the
exact failure this item exists to end. That argument is sound. It just does not
apply to the checkers the item aims it at.

## Decisions

- **2026-09-12 — the registry is a code table, not a data file.** Reversed if a
  consumer outside Python needs to read the registry; at that point the table
  gains a serializer, and the table stays the source.
- **2026-09-12 — prose rule 3 is narrowed to tool-behaviour claims and carries
  a frozen baseline of 263**, the uncited claims in `skills/`. Reversed if the
  corpus is deliberately swept and the baseline reaches a number small enough
  to fix outright.
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
- **2026-09-12 — the meta-check lands before any rule.** A registry with zero
  rows must pass its own tests. This makes step 1 independently landable and
  independently green.

## Risks

**Accepted: the baseline can be gamed.** Anyone may add a machinery claim if
they delete another. The baseline catches drift in aggregate, not per line.
Accepted because the alternative — fixing 263 claims before the check can land
— means the check never lands.

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

**Not accepted, and it needs an answer during implementation: what a rule id
means when its rule is repealed.** A repealed rule's id must not become
reusable, and live prose citing it must not silently start resolving to a
different rule. The registry needs a tombstone state before the first repeal,
not after.
