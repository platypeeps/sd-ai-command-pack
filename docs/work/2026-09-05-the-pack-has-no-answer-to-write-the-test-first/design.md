# Design — the pack has no answer to write the test first

## Approach

One new folded skill, `skills/sd-tdd/SKILL.md`, and a `## Lineage` section
added to `skills/sd-typed-holes/SKILL.md`. No Python, no `bin/` tool, no test
changes beyond what the frontmatter suite already enumerates from disk, and no
edit to any other skill.

The skill follows the pack's section skeleton — When to use / Arguments /
The gate / Workflow / Red flags / Safety rules / Final report / Lineage — the
same shape `sd-debug` and `sd-receive-review` shipped in, so a reader moving
between the three finds the same furniture.

**This is the third scope for this item.** The first attempted three further
things: a route by which a test written late could still satisfy the gate, a
seam settling the apparent contradiction with `sd-typed-holes`, and a
carve-out permitting the scaffolding a test needs before the code exists.
Three review rounds produced twenty-three findings and fourteen of them
belonged to those three additions. D7 records why they were cut rather than
fixed a fourth time. The second scope kept a counted three-state close, which
round 6 cut in turn; D4 records that.

## Decisions

**D1 — the gate is stated on the observed failure, not on authorship order.**

Upstream's iron law is `NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST`. Order
of authorship is the natural way to state it and the wrong thing to gate on,
for the same reason the `sd-grill` question-form rule gates on authorship
rather than expectation: pick the property that is *observable at the moment it
matters*. Who typed what first is not recoverable from the tree an hour later.
Whether a test was ever seen to fail is: it is an event with output, and the
output can be quoted.

So the gate is **"no production code without a test that was seen to fail
against a tree lacking the behaviour"**, and the failure — not the authorship —
is what the final report carries.

This is a change of *evidence*, not of practice. Writing the test first remains
the only route the skill offers, because a test derived from an implementation
inherits its blind spots: it verifies the cases the code already handles rather
than the cases asking "what should this do?" would have surfaced. Upstream
states the mechanism directly — "tests written after are biased by the code you
already wrote — you verify the cases you remembered, not the ones you'd have
discovered."

**D2 — the expected-failure requirement is separate from the failure itself.**

A test that fails is not a test that failed *correctly*. An import error, a
typo in a fixture, a collapsed factory — all produce red, and all of them mean
the test proves nothing about the behaviour. Upstream states this well ("Test
errors? Fix error, re-run until it fails correctly") and it is the half that
gets dropped when the discipline is summarised, so it is requirement 2 on its
own rather than a clause inside requirement 1.

The skill asks the agent to quote the message and say why it is the behaviour
being absent. It deliberately does **not** offer a syntactic rule for telling
the two apart — see D7, where two such rules were tried and both failed.

**D3 — this skill never deletes, and that is a deliberate departure.**

Upstream: *"Write code before the test? Delete it. Start over. No exceptions:
don't keep it as 'reference', don't 'adapt' it... Delete means delete."*

Read by a human that is good discipline. Read by an agent with write access it
is an instruction to destroy work the user has not committed, on the authority
of a skill file. The pack's other skills bound outward action in exactly this
way — `sd-debug` never commits or branches, `sd-receive-review` posts no reply,
`sd-ship` refuses to delete any local branch or worktree because it cannot tell
which are disposable. A skill that deletes source code is further over that
line than any of them.

So `sd-tdd` **proposes** the rewrite, names what would be lost, and requires
consent.

**D4 — the close is a per-change record, and a counted grade was cut.**

Six drafts closed on one of three states — `disciplined`, `partial`,
`abandoned` — chosen by sorting each production change into proven or unproven,
counting rather than judging so that exactly one state always fit. The counting
itself worked; a review lane enumerated the state space and found no session
mapping to two states or to none.

It was cut anyway, because the classifier was exclusive over its inputs and the
inputs were what kept breaking. Producing them meant ruling on what a refactor
is, when step 7 says it needs no test of its own and so has no red; on what a
consented scaffold is, being production code that exists before any red; on
what a behaviour "already present" is, when the code was written earlier in the
same session; and on what a bound yields when it fires after the code is
written and before the rerun. Each needed its own rule, and the rules collided
with one another and with the report's categories — `Scaffolding` and
`Unproven changes` both claimed a consented scaffold, and between `Deferred`
and `Cycles` there was no place at all for a behaviour reached but not
implemented. Across six review rounds, nine of thirty-seven findings were this
machinery, and not one of them was a question about whether the code was
tested.

What replaced it asks the question the discipline actually cares about, per
change instead of per session: what did this change owe, and what was actually
observed? The obligation depends on what the change claims, so the skill states
one table with three exhaustive kinds. A **behaviour** change owes valid red
against a tree lacking it and a pass with the suite green. A **refactor** owes
the suite seen green before it and green after it — both runs, since "on green"
with an unobserved baseline is not on green — in place of the red it never had.
A **scaffold** owes recorded consent and nothing else, and the behaviour it
unblocks owes the behaviour row in full. One change is one kind; a change that
would be two is split, and one that cannot be split owes the behaviour row,
never the cheaper refactor one. The report is two lists — every behaviour once
in one, every production change once in the other, each naming its kind — and
the untested code is read off the second: any change missing any part of what
its row owed.

The table is stated once, in the skill, and this decision and requirement 4
restate it rather than paraphrasing it. An earlier draft left the obligation as
prose in four places and the four drifted apart within a single review round —
a refactor owing one green run here and two there, a scaffold owing "no red" in
one artifact and "neither half" in another.

The cost is that no single token grades a session, and that is the point. The
counted word was the part an agent under pressure would round up, and a reader
given one word cannot recover the list, while a reader given the list can form
whatever word they want.

**D5 — the suite's blast radius is bounded.**

"Prefer real code over mocks" is a statement about the code under test and not
a licence to reach production. Without a bound, a skill telling an agent to run
the surrounding suite says nothing about production credentials, live
endpoints, shared databases, or fixtures that send mail or move money. One
safety rule covers it, and anything needing a real external system is named and
consented to before the first run.

**D6 — the rationalization table keeps the rows that name a mechanism.**

Upstream's table is its strongest mechanic and the easiest to copy badly. A
table of excuses is only worth shipping if each reply is an argument rather
than a scolding. The ones adopted name a mechanism — tests-after answer "what
does this do?", tests-first answer "what should this do?" — and the purely
admonitory rows are left upstream, because a skill that lectures gets skimmed.
The example of such a row is `"I'm tired" / "Exhaustion ≠ excuse"`, which an
earlier draft of this document attributed to upstream's TDD skill; it is not
there, it is at `verification-before-completion/SKILL.md:70`, and the point
survives the correction.

**D7 — three additions were cut, and the skill says what it does not settle.**

The first scope tried to answer three further questions. Each was answered,
reviewed, found wrong, re-answered, and found wrong again:

- **A route for a test written late** — revert the change, watch the test fail,
  restore. Cut. It produced seven findings. The final one was fatal in a plain
  way: the procedure could not execute, because after writing the test the tree
  holds both the test and the fix, and the `git stash --include-untracked` the
  skill prescribed removes both, leaving nothing to run. Beyond mechanics it
  also weakened the discipline, since reverting proves a test is *sensitive* to
  a behaviour and not that it covers the right cases.
- **A seam with `sd-typed-holes`** — cut, four findings. The boundary is real
  but sits inside that skill's step 2, which lands derives, conversion impls
  and implemented accessors alongside the `todo!()` holes. Every attempt to
  draw it either exempted those real bodies or wrote a rule that skill's own
  workflow then walked past.
- **A bootstrap carve-out** — cut, three findings. Permitting the scaffolding a
  test needs before the code exists requires distinguishing "the behaviour is
  absent" from "the test is broken", and both rules tried for it sorted real
  cases backwards. A bare `NotImplementedError` carries no message naming the
  behaviour; a collapsed factory's `AttributeError: 'LegacyCart' object has no
  attribute 'calculate_total'` names it perfectly and is invalid red.

Cutting them is not pretending the questions do not exist. The skill carries a
`## What this skill does not settle` section naming the first and third, with
what was tried and why it failed, and `sd-typed-holes` names the second in its
own Lineage. A reader who hits one of these in a real session gets told it is
open, which is worth more than a rule that reads authoritative and misfires.

One constraint on how an open question may be written, learned the hard way:
it may not issue a positive instruction that contradicts a rule the skill still
enforces. The first draft told the reader to "write the least scaffolding that
lets the test speak" — production code before valid red, which the gate
prohibits absolutely — inside the section admitting the question was
unresolved. So the bootstrap question routes to the user rather than to the
reader's judgement, the same move D3 makes for a proposed rewrite.

## Risks

**The skill is reader-verified, like the three before it.** Nothing here tests
conduct. This is the fourth skill in that condition and the PRD says so; it
does not resolve C-11 on the `sd-grill` item and does not claim to.

**Two open questions ship inside a discipline skill.** A skill whose job is to
state a rule crisply now contains a section saying two adjacent rules are
unsettled. That is a legible cost. The alternative on offer was a fourth
attempt at boundaries that failed review three times, and a rule an agent
follows into the wrong behaviour is worse than a question it is told to think
about.

**`sd-typed-holes` gains a Lineage and nothing else.** Its provenance was
unrecorded; it is recorded now, including that its upstream ships no licence
file and that this pack dropped upstream's second layer. The seam that would
have used that finding was cut, so the Lineage carries the observation and the
open question without a rule depending on it.
