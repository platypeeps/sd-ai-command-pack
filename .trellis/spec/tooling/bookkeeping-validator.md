# Bookkeeping Validator Notes

> Non-obvious gotchas and conventions specific to
> `scripts/sd-ai-command-pack-review-preflight.mjs`, learned from
> `.trellis/tasks/07-31-completion-recovery-no-archive-anchor`.

---

## Gotcha: top-level `const` placement is not cosmetic

Adopted 2026-08-01. This file's CLI dispatch (`if (isMainModule()) { ... }`)
runs as literal top-level module code — it executes synchronously during
import, interleaved with every other top-level statement in file order, not
inside a function called later. A `const` declared *after* that dispatch
block is in its temporal dead zone at the exact moment the dispatch chain
calls into a function that references it, throwing
`ReferenceError: Cannot access '<name>' before initialization` on every real
invocation. `node --check` does not catch this — it only parses, it does not
execute, so a broken file can look clean right up until someone runs it.

This is why every top-level constant this file needs at dispatch time
already lives in one block near the top (`MAX_BOOKKEEPING_*`,
`ACTIVE_TRELLIS_TASK_STATUSES`, etc.). Any new top-level `const`/config
object — including one a design doc's illustrative pseudocode shows "near
its callers" for readability — must go in that existing top block instead.
Verify by actually running the code path (a targeted test, not just
`node --check`) before considering the change done.

- Bad: adding `const ARCHIVE_MOVE_IDENTITY_OPTIONS = {...}` physically next
  to the function that uses it, if that function is reachable from the
  top-level dispatch block above the declaration.
- Good: adding it to the existing top-of-file constants block, then
  confirming with a real test run (not just `node --check`) that it resolves.

## Design principle: a "historical proof" via a live-reading function is only sound for immutable content

Adopted 2026-08-01. The completion-mode auto-recovery mechanisms
(`post-archive-review-successor`, `active-task-review-successor`) need to
prove things about a historical point in git history. Several core
functions this file already has — `validateBookkeepingTaskDirectory`,
`loadTrellisTaskMetadataFile`, `safeJournalFiles`,
`loadBoundedTrellisTaskArtifact` — read the **live, currently-checked-out
worktree** via `readdirSync`/`lstatSync`, not git objects at a ref. Two
different helpers exist for genuinely historical reads:
`loadBookkeepingJsonAtRef` and `bookkeepingChangedEntries` (both backed by
`git cat-file`/`git diff`, not the filesystem).

The archive-successor mechanism gets away with calling the live-reading
functions inside what's conceptually a "historical" proof only because the
content in question — an already-archived task directory — is provably
immutable from that point forward (nothing can legally mutate
`.trellis/tasks/archive/**` again; other checks in this same family enforce
that). Live and historical reads coincide *because nothing changed in
between*, not because the mechanism is generically safe to reuse.

**Before reusing this pattern for any new recovery mechanism, ask: is the
content I'm "historically" proving guaranteed static from that point to
true head?** If the answer is no — as it is for an *active* task directory
that a design deliberately allows to be touched again later — do not call a
live-reading function against anything but genuinely-live true head. Prove
the historical side entirely through `loadBookkeepingJsonAtRef` /
`bookkeepingChangedEntries`, and run whatever full-content sweep is needed
exactly once, at live head, not once per historical checkpoint. This was
caught by adversarial review before any code was written for
`active-task-review-successor` (see that task's `design.md`, Change B, "Why
the first draft's mechanism doesn't work") — it is easy to reach for the
existing pattern by analogy and miss that its safety depends on a property
the new case doesn't have.

## Related

- [Code Reuse Thinking Guide](../guides/code-reuse-thinking-guide.md) — this
  file's primitives (`bookkeepingChangedEntries`, `loadBookkeepingJsonAtRef`,
  the `validateTaskLifecycleIdentity` shared helper) are reused across many
  call sites; search before adding a new one.
- [guides/index.md](../guides/index.md), "When Verifying AI Cross-Review
  Results" — the review-methodology lesson from the same task (static
  review vs. running the real test suite) lives there, since it applies
  beyond this one file.
