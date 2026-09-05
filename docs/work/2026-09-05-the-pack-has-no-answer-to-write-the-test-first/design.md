# Design — the pack has no answer to write the test first

## Approach

One new folded skill, `skills/sd-tdd/SKILL.md`, plus reciprocal passages in
two skills that already exist — seven added lines in `sd-debug` and
fifty-four in `sd-typed-holes`, the latter carrying a `## Lineage` section as
well as the seam. No Python, no `bin/` tool, no test changes beyond what the
frontmatter suite already enumerates from disk.

The skill follows the pack's section skeleton — When to use / Arguments /
The gate / Workflow / Red flags / Safety rules / Final report / Lineage — the
same shape `sd-debug` and `sd-receive-review` shipped in yesterday, so the
anchored-heading criterion is the same check and a reader moving between the
three finds the same furniture.

## Decisions

**D1 — the gate is "seen to fail", not "written first".**

Upstream's iron law is `NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST`. Order
of authorship is the natural way to state it and the wrong thing to gate on,
for the same reason the `sd-grill` question-form rule gates on authorship rather
than expectation: pick the property that is *observable at the moment it
matters*. Who typed what first is not recoverable from the tree an hour later.
Whether a test was ever seen to fail is: it is an event with output, and the
output can be quoted.

So the gate is **"no production code without a test that was seen to fail
against a tree lacking the behaviour"**, and the failure — not the authorship —
is what the final report carries. The phrase names the tree deliberately: "seen
to fail first" would have re-imported the ordering the decision exists to
remove, and would have contradicted the revert-and-restore path in the very
next paragraph. That is the C-1 defect of the prior item — a rule contradicting
the sentence it is layered onto — and it was caught here by the host lane
rather than by a reader.

This also makes the rule reachable for a test written slightly late: revert the
code, watch the test fail, restore. Upstream forbids that path; this pack
allows it because a rule that cannot be satisfied without deleting work will be
skipped rather than followed.

**But the two routes are not equivalent, and an earlier draft of this decision
said they were.** It claimed "the evidence it produces is identical". It is not.
Reverting proves the test is *sensitive* to the behaviour — remove the code and
the test notices. It says nothing about *which cases the test covers*, and that
is the half upstream is defending: a test derived from an implementation
verifies the cases the implementation already handles, not the ones asking
"what should this do?" would have surfaced. Upstream states the mechanism
directly — "tests written after are biased by the code you already wrote — you
verify the cases you remembered, not the ones you'd have discovered".

Concretely: implement only the case you remembered, derive a test from that
implementation, revert, watch it fail. The gate is satisfied and the blind spot
is intact.

So the route stays open and it closes differently: test-before-code closes
`disciplined`, a recovered late test closes `partial` with the recovered
behaviours named (D6). This keeps the rule satisfiable without deleting work —
the reason D1 exists — while refusing to launder late evidence into the word
that means complete.

**D2 — the expected-failure requirement is separate from the failure itself.**

A test that fails is not a test that failed *correctly*. An import error, a typo
in a fixture, a collapsed factory — all produce red, and all of them mean the
test proves nothing about the behaviour. Upstream states this well
("Test errors? Fix error, re-run until it fails correctly") and it is the half
that gets dropped when the discipline is summarised, so it is requirement 2 on
its own rather than a clause inside requirement 1.

**D3 — the regression proof has two routes, and it is the seam with
`sd-debug`.**

Write the test, see it pass with the fix in place, **revert the fix**, see it
fail, restore. This proves a regression test guards the bug rather than merely
coexisting with it.

It is not the *only* construction that does so — an ordinary red-green cycle on
the bug, where the test is written before the fix and observed failing against
the unfixed tree, has already produced exactly this evidence and needs no
revert. The procedure is for the common case where the fix landed first. An
earlier draft of this decision called it "the only construction", which was
wrong.

**Reverting is a destructive act and the skill bounds it.** It removes working
code from a tree, and `sd-tdd` can neither commit nor branch, so it holds no
recovery mechanism of its own. The skill therefore requires the change be
already committed or explicitly saved (`git stash`, or a patch plus a copy for
untracked files) before any revert, and refuses to revert where unrelated dirty
edits mean the change cannot be isolated — reporting the proof as not run
instead. Restoration is a verified step, not an intention.

`sd-debug` today requires rerunning the reproduction after a fix, which proves
the symptom is gone and proves nothing about the test that is supposed to keep
it gone. Rather than duplicate the procedure into `sd-debug`, `sd-debug` gains
a short passage handing the regression test to `sd-tdd`, and `sd-tdd` owns the
proof. One procedure, one owner, two skills that agree — the same choice made
when `sd-receive-review` reused the planning contract's four dispositions
instead of coining new ones.

**D4 — the `sd-typed-holes` contradiction is resolved by scope, not by
precedence.**

The two skills look opposed and are not, once the question is asked precisely.
The exempt thing is the **type surface**: signatures, types, module boundaries,
and the `todo!()` bodies standing in for behaviour not yet written. That is a
design artifact the compiler reviews and there is no behaviour in it to test.
`sd-tdd` governs **behaviour**.

**The exemption is narrower than "the skeleton commit", and an earlier draft of
this decision drew it at the commit.** `sd-typed-holes` step 2 lands real
derives, `From`/`Into` impls, and trivial accessors *implemented rather than
held open* — each has a real body and real runtime semantics. A getter
returning the wrong same-typed field compiles, passes clippy, and would have
been exempt. That skill's own safety rules already concede the point: a green
skeleton "shows the design composes, not that behavior is correct — derives and
runtime semantics still need inspection and tests."

So the seam divides the *contents* of the work, not its commits: type surface
and `todo!()` bodies are outside test-first; every real body — whether it lands
in the skeleton commit or a later fill — is inside it. Neither skill wins. Stated in both files, because a Rust author
may arrive at either one first, and a seam readable from only one side is the
defect `sd-feedback` had before requirement 11 of the prior item fixed it.

The alternative — declaring one skill to govern Rust — was rejected: it would
make the pack's answer to "write the test first" depend on the language, which
is exactly the kind of hidden exception this pack keeps finding in its own
rules.

**D5 — this skill never deletes, and that is a deliberate departure.**

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
consent. D1 also removes most of the occasions for it: the
revert-and-watch-it-fail path reaches a watched failure without a rewrite, and
closes `partial` rather than `disciplined` — which is the honest price of
having written the code first, and a far smaller one than deleting it.

Two claims that stood in this paragraph are gone, both wrong for reasons the
review found elsewhere. It said the revert path reaches "the same evidence",
which C-3 refuted: reverting proves sensitivity, not case coverage. And it said
"without deleting anything", which C-6 refuted: a revert *does* remove working
code from the tree, which is why D3 now requires a recoverable copy first.

**D6 — closing states mirror `sd-debug`'s three, with different words.**

`disciplined` (every production change was preceded by its test, and each was
seen to fail against a tree lacking the behaviour), `partial`, `abandoned` (the
discipline was not followed; the report says so rather than implying
otherwise). Three states, exactly one chosen, and the middle one exists so that
an honest partial result has a word — without it, partial work gets reported as
`disciplined`, which is the failure mode the state set is for.

`partial` carries **two** groups, named separately in the report: changes with
no failing-test evidence at all, and changes whose test was recovered late by
reverting. The second satisfies the gate and still lands here, per D1.

A fourth state was considered and rejected for the case where the first test
*passes* — the behaviour already existed. That is not a closing state, because
no production code is written for such a behaviour: it is a report line
(**Behaviours already present**) that requires no quoted failure and counts
neither for nor against the state. Without that line the workflow told an agent
to stop and left it no truthful way to say so.

## Risks

**One skill, three files touched.** `sd-tdd` is new; `sd-debug` and
`sd-typed-holes` each gain a passage — not the "one line" an earlier draft of
this document claimed, and not four surfaces either. The prior item's risk
section warned about three deliverables in one work item; this is one
deliverable with two reciprocal pointers, which is the shape that item's
requirement 11 established as correct rather than a repeat of its risk.

**The skill is reader-verified, like the three before it.** Nothing here tests
conduct. This is the fourth skill in that condition and the PRD says so; it
does not resolve C-11 and does not claim to.

**Upstream's rationalization table is its strongest mechanic and the easiest to
copy badly.** A table of excuses is only worth shipping if each reply is an
argument rather than a scolding. The ones adopted are the ones that name a
mechanism — tests-after answer "what does this do?", tests-first answer "what
should this do?" — and the purely admonitory rows are left upstream, because a
skill that lectures gets skimmed. The example of such a row is
`"I'm tired" / "Exhaustion ≠ excuse"`, which an earlier draft of this document
attributed to upstream's TDD skill; it is not there. It is at
`superpowers/skills/verification-before-completion/SKILL.md:70`, a different
skill, and the point about admonitory rows survives the correction.

**`sd-typed-holes` had no lineage; this item writes one.** D4 wrote a seam into
a file whose own provenance was unrecorded — it arrived from
`se-ai-command-pack` in `56ba92eb` as an addition, not a rename, so its history
lived in another repository. That history was recovered and the file now
carries a `## Lineage` section, so both sides of the seam are documented.

Recovering it changed D4 rather than merely annotating it. Upstream
(`Shearerbeard/claude-skills`, `plugins/rust/skills/typed-holes`) is a
**two-layer** practice: layer 1 is the type-checked skeleton this pack kept,
and layer 2 is whole-frame golden tests written from the spec "so they fail on
arrival" — test-first under another name, which this pack did not carry over.
The apparent contradiction requirement 4 exists to settle is therefore an
artifact of a dropped half, not a genuine disagreement between two practices,
and `sd-tdd` restores that half pack-wide rather than Rust-only.

One thing the lineage cannot say: that repository ships **no licence file**
(`LICENSE`, `LICENSE.md`, `LICENSE.txt` and `COPYING` all absent at revision
`c79fe3a`). Its terms are unstated rather than permissive, so the section says
that plainly instead of naming a licence, and records that the ideas were
re-authored rather than copied.
