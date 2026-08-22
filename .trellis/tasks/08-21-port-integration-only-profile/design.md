# Design — Port the fleet integration-only review profile into sd-review

## Boundaries

`sd-review` today is a 190-line public skill whose entire input surface is
optional `key=value` tokens (`SKILL.md:42-50`). `sd-review-pr` is 865 lines and
carries, in addition to the public surface, a trusted-caller contract that only
`sd-fleet-refresh` uses. This design moves that contract, and nothing else,
into `sd-review`.

The contract has four separable parts. They are listed here because
`implement.md` sequences them and each is independently testable:

1. **Trusted context intake and validation** — `sd-review-pr/SKILL.md:69-77`
   (field list) and `:81` (per-profile validation).
2. **Exact-head reclassification** — the `classified-head` / `LOCAL_HEAD` /
   `HEAD_SHA` identity requirement, stated at `:81` and re-required inside the
   recheck at `:209`.
3. **Classifier invocation** — the Fleet Integration-Only Recheck block at
   `:206-232`, which shells `sd-ai-command-pack-fleet-review-classify.py`.
4. **Deferral semantics and return shape** — `defer-finish-work` handling at
   `:244`, and `return-after: review-result`.

## Contracts

### Trusted context is not an argument

R1 forbids the public `key=value` surface from gaining these keys. The context
therefore enters the same way it does today: as a fenced `text` block supplied
by a caller skill that is already executing, validated against the caller
identity, never parsed from argv. `sd-review`'s `Arguments` section keeps its
current closed enum set and its existing rejection rule for unknown keys —
which means a user-supplied `caller=sd-fleet-refresh` token is rejected by the
existing validation, with no new code path. That is the security property worth
preserving, and a test should pin it explicitly rather than leaving it implied.

### Placement

A new `## Trusted caller context` section sits between `## Arguments` and
`## Safety and authority`. Rationale: the reader must know the context exists
before reading the safety rules that branch on it, and the section must not
appear to be part of the public argument surface.

### The finish-work tension — resolve before implementing

This is the one genuine incompatibility, and it is why this task is not a
copy-paste.

- `sd-review/SKILL.md:73` states: *"Do not merge, archive Trellis work, or run
  housekeeping from this skill."*
- `sd-review-pr/SKILL.md:244` does the opposite under authorized deferral: it
  cancels the deferral and *runs the SD finish-work procedure* when the PR was
  merged externally, because "the deferred merge tail cannot own finish-work
  after an external merge has already ended the normal chain."

Porting part 4 verbatim would put `sd-review` in direct contradiction with its
own line 73. Three candidate resolutions, to be settled in implementation and
recorded as a decision:

| Option | Shape | Cost |
| --- | --- | --- |
| A | Narrow line 73 to "except when authorized `defer-finish-work` context is active" | Weakens a blanket safety rule; smallest diff |
| B | Return a typed `deferral-cancelled` result and let `sd-fleet-refresh` own the finish-work call | Keeps line 73 absolute; moves behavior to the caller; changes the return shape R1 says must match |
| C | Leave deferral cancellation in `sd-fleet-refresh` entirely | Cleanest boundary; largest behavioral change to prove equivalent |

**Recommendation: B**, because line 73 is a safety invariant that other callers
rely on, and the `review-result` return shape is already the contract's
extension point. B does change the return shape, so R1's "same return shape"
must be read as *same for the review outcome*, with deferral disposition added
rather than substituted. If B proves to change observable fleet behavior, fall
back to A and record why.

### Recheck relocation

The `:206-232` block moves verbatim into
`templates/.agents/skills/sd-fleet-refresh/SKILL.md`. It is safe to move rather
than copy: `install-audit.py:121` lists `fleet-review-classify.py` as
source-only, and `sd-fleet-refresh` has **0 manifest entries** (verified
2026-08-21) — it exists only at `.agents/skills/sd-fleet-refresh` and
`templates/.agents/skills/sd-fleet-refresh`. So the block is already
unreachable in every shipped copy, and relocating it creates no new
plugin-closure exception. `sd-review` references the procedure by name; it does
not inline it, because `sd-review` *does* ship and inlining would pull
`fleet-review-classify.py` into its closure and require a new allowlist entry —
exactly the entry child 2 is trying to delete.

## Data flow

```
sd-fleet-refresh  (review action, SKILL.md:310)
      │  trusted context block: caller, review-profile, source-root,
      │  consumer, base-commit, release-remote, classified-head,
      │  return-after, defer-finish-work
      ▼
sd-review  ── validates caller identity + every field (profile-dependent)
      │    ── requires classified-head == LOCAL_HEAD == HEAD_SHA
      ▼
Fleet Integration-Only Recheck   (now owned by sd-fleet-refresh)
      │  fleet-review-classify.py --consumer --repo --base-commit --remote --json
      ▼
accept only when: exit 0, one valid schema-v1 object, eligible: true,
consumer/repo/base/head all match trusted context and live repo
      ▼
review-result  ──► back to sd-fleet-refresh
```

## Compatibility and rollback

`sd-review-pr` is untouched and still functional at the end of this task, so
rollback is reverting this task's commits — no release-level rollback needed.
The two skills implement the profile concurrently and must not disagree; the
fleet caller points at exactly one of them at a time (`sd-fleet-refresh`
switches to `sd-review` in this task).

## Validation strategy

Behavior, not prose, per R2. The suite must fail if the port is cosmetic:

1. Malformed / incomplete trusted context is rejected with the same strictness
   as `sd-review-pr/SKILL.md:81`.
2. `classified-head != LOCAL_HEAD != HEAD_SHA` is refused.
3. A user-supplied `caller=` argv token is rejected by the existing unknown-key
   rule.
4. Non-eligible / unavailable / malformed classifier output fails closed.
5. An end-to-end `sd-fleet-refresh` review against a real PR head returns a
   `review-result` and consults the classifier.

Tests 1-4 are offline. Test 5 needs a live consumer PR and is the only one that
cannot run in CI; it must be executed once by hand and its output recorded in
the task before the acceptance criterion is ticked.
