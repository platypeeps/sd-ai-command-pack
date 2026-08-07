# Thinking Guides

> **Purpose**: Expand your thinking to catch things you might not have considered.

---

## Why Thinking Guides?

**Most bugs and tech debt come from "didn't think of that"**, not from lack of skill:

- Didn't think about what happens at layer boundaries → cross-layer bugs
- Didn't think about code patterns repeating → duplicated code everywhere
- Didn't think about edge cases → runtime errors
- Didn't think about future maintainers → unreadable code

These guides help you **ask the right questions before coding**.

---

## Available Guides

| Guide | Purpose | When to Use |
|-------|---------|-------------|
| [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md) | Identify patterns and reduce duplication | When you notice repeated patterns |
| [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md) | Think through data flow across layers | Features spanning multiple layers |

---

## Quick Reference: Thinking Triggers

### When to Think About Cross-Layer Issues

- [ ] Feature touches 3+ layers (API, Service, Component, Database)
- [ ] Data format changes between layers
- [ ] Multiple consumers need the same data
- [ ] You're not sure where to put some logic
- [ ] You are adding an event kind, JSONL record, RPC payload, or config field
- [ ] UI / command code starts casting raw payload fields directly

→ Read [Cross-Layer Thinking Guide](./cross-layer-thinking-guide.md)

### When to Think About Code Reuse

- [ ] You're writing similar code to something that exists
- [ ] You see the same pattern repeated 3+ times
- [ ] You're adding a new field to multiple places
- [ ] **You're modifying any constant or config**
- [ ] **You're creating a new utility/helper function** ← Search first!
- [ ] Two files read the same untyped payload field with local casts
- [ ] Multiple branches update the same derived state from `kind` / `action`

→ Read [Code Reuse Thinking Guide](./code-reuse-thinking-guide.md)

### When Verifying AI Cross-Review Results

- [ ] Reviewer claims "user input can be malicious" → Check the actual data source (internal manifest? user config? external API?)
- [ ] Reviewer flags "missing validation" → Is the data from a trusted internal source?
- [ ] Reviewer says "behavior change" → Read the code comments — is it intentional design?
- [ ] Reviewer identifies a "bug" in test → Mentally delete the feature being tested — does the test still pass? If yes → tautological test

**Common AI reviewer false-positive patterns**:
1. **Trust boundary confusion**: Treating internal data (bundled JSON manifests) as untrusted external input
2. **Ignoring design comments**: Flagging intentional behavior documented in code comments as bugs
3. **Variable misreading**: Not tracing a variable to its actual definition (e.g., Map keyed by path vs name)

### When a Design Changes Control Flow That Existing Tests Already Pin

Adopted 2026-08-01, from `.trellis/tasks/archive/2026-08/07-31-completion-recovery-no-archive-anchor`.
That task's design went through two full rounds of host+Codex adversarial
review — read-only, line-by-line against real source — before any code was
written, and both rounds found and fixed real, confirmed defects. Despite
that, implementing the design and running the *existing* test suite against
it immediately surfaced three further genuine defects neither review round
caught, all three specifically about control-flow discriminators: an
orchestration choice that silently replaced 9 of 11 existing tests' specific
reason codes with a generic one; a follow-up gap in that same discriminator
missed by the first fix; an anchor-search that would select the wrong commit
for the single most common real-world case. Static, evidence-checking review
is a different check from running the real suite against a real
implementation — it is not a stronger version of the same check, and it
catches a different class of bug.

- [ ] Design changes an existing function's control flow (a new branch, a
      changed discriminator, a new early return) → find every existing test
      that already exercises that function and confirm someone has actually
      run them against a literal implementation of the new logic, not just
      reasoned about it against the code.
- [ ] Review reasoning says "this preserves existing behavior" → that is a
      claim to test, not a conclusion reasoning alone can certify. Prefer
      "confirmed: N/N existing tests pass, byte-identical" over "should be
      behavior-preserving."
- [ ] A design review's stated confidence is entirely text/reasoning-based
      (no test run mentioned) → treat control-flow claims in it as
      unverified until an implementation actually exercises them, regardless
      of how many review rounds or how rigorous the citations were.

**Verification rule**: Every CRITICAL/WARNING finding must be verified against the actual code before prioritizing. Budget ~35% false-positive rate for AI reviews.

### When a Reviewer Reports Nothing

Over-claiming is the well-known failure. Under-claiming is the one that ends a review loop early:

- [ ] Review body says "no new comments" → Search the body for a collapsed `<details>` block disclosing withheld entries, typically titled `Comments suppressed due to low confidence (N)`. Match the intent, not that exact string; the wording can change. Copilot hides observations there; they never become inline comments or threads, so a loop reading only thread state never sees them.
- [ ] Suppressed entry looks weak → Low confidence is the reviewer's confidence in **its own scoring**, not evidence the observation is wrong. Verify each one against the code like any inline comment. On PR #273, 3 of 4 suppressed entries were real defects.
- [ ] Review body claims full coverage ("reviewed N out of N changed files") → Compare the review event's `commit_id` to the recorded head. A review can be submitted against an earlier commit while a newer one is already head; N is counted against the commit it actually read, so the claim is true and the head is still unreviewed.
- [ ] Round looks clean → It is clean only when the body reports no new comments **and** no suppressed entry survives verification **and** `commit_id` equals the head.

Enforcement lives in `templates/.agents/skills/sd-review-pr/SKILL.md` steps 4 and 5.

### When Closing Out a Task Whose Work Already Landed

Adopted 2026-08-06, from `.trellis/tasks/archive/2026-08/07-28-consolidate-shared-script-helpers`.
That task sat `in_progress` with five unchecked acceptance criteria long after
the work was done — two of its four planned commits shipped under it, and the
other two were split mid-implementation into follow-up tasks that inherited two
of the criteria and were themselves completed. Nothing was outstanding; nobody
closed it, because no single task's history showed the whole picture.

Checking which commits had landed by grepping commit messages for the finding
IDs reported `A-046` as shipped by `dde46efd` — but that commit is a *different*
task's, and the only reason it matched is that its body says "Records the
sd-review coordinator defect found while shipping A-046". The conclusion
happened to be right; the evidence was not. A message-grep searches prose
written by whoever typed the commit, which includes cross-references to work
the commit does not contain.

- [ ] Deciding whether a change landed → verify against the tree (the symbol
      exists at the expected path, the old copies are gone), not against
      `git log --grep`. Commit bodies cite other tasks' IDs.
- [ ] Ticking an acceptance criterion → the check must be able to fail. Prefer
      an enumeration that would catch what you did not think of — a repo-wide
      grep for the *forbidden* pattern returning 0 beats confirming the
      intended pattern is present in the file you already opened.
- [ ] Criterion says "no X anywhere" → scope the grep to the whole repo, not to
      the directory the task touched. AC4 here was "no script constructs a git
      environment outside the lib"; only a sweep of every `*.py` in `scripts/`
      *and* `.github/scripts/` can establish that.
- [ ] Task looks done → confirm it has no children (`subtasks`, `children`, and
      nested task dirs all empty) before archiving. A parent archived over open
      children strands them outside the active root.
- [ ] About to write "this task delivered X" → read its own `implement.md` to
      the end first. Scope splits get recorded there, not in `task.json`: this
      task's `subtasks` and `children` were both empty while `implement.md:211`
      said two of its four commits had moved to separate tasks. An empty
      `children` array means "no Trellis parent/child link", not "no scope ever
      left this task".
- [ ] A criterion is satisfied by work that landed under a *different* task →
      say so, and name that task. "Verified against the tree" and "delivered
      here" are two different claims; an archived PRD that blurs them misleads
      the next reader about what this task actually did.

---

## Pre-Modification Rule (CRITICAL)

> **Before changing ANY value, ALWAYS search first!**

```bash
# Search for the value you're about to change
grep -r "value_to_change" .
```

This single habit prevents most "forgot to update X" bugs.

**This applies to prose artifacts, not just code.** A measurement, count, size, path, or identifier usually appears in more than one of `prd.md`, `design.md`, `implement.md`, and `task.json`, and one artifact often cites what another "states". Correcting the figure in one place leaves the others asserting the old value, and correcting a cited artifact can invalidate the citation itself. Grep the whole task directory; the stale copy is the one you did not think to open.

---

## How to Use This Directory

1. **Before coding**: Skim the relevant thinking guide
2. **During coding**: If something feels repetitive or complex, check the guides
3. **After bugs**: Add new insights to the relevant guide (learn from mistakes)

---

## Contributing

Found a new "didn't think of that" moment? Add it to the relevant guide.

---

**Core Principle**: 30 minutes of thinking saves 3 hours of debugging.
