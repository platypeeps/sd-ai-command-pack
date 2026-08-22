# Port the fleet integration-only review profile into sd-review

> Child 1 of 3 under `08-09-retire-review-pr-surface`. Ordering is a
> requirement of this task, not an implication of tree position: this task
> **must land before** `08-21-delete-review-pr-surface`, because that task
> deletes the only existing implementation of the profile ported here.
> Nothing is deleted by this task.

## Goal

Give `sd-review` the fleet integration-only review profile that only
`sd-review-pr` implements today, repoint `sd-fleet-refresh` at it, and preserve
the Fleet Integration-Only Recheck procedure in a surviving, reachable home.
On completion the fleet review action runs end to end through `sd-review` while
`sd-review-pr` still exists and still works.

## Why this is separate

The profile is a trusted nested contract with a live production caller. Porting
it is a behavioral migration that must be provable on its own, with its own
review and its own green run, before any deletion makes the old implementation
unavailable as a reference or a fallback. Deleting first would remove the fleet
integration-only mechanism outright.

## Current state (verified 2026-08-21)

- `templates/.agents/skills/sd-fleet-refresh/SKILL.md:310` invokes
  `sd-review-pr` with trusted `caller: sd-fleet-refresh`.
- `templates/.agents/skills/sd-review-pr/SKILL.md` implements the contract:
  trusted context block and field list at `:69-77`, per-profile field
  validation at `:81`, the Fleet Integration-Only Recheck at `:206-232`
  (including the `classified-head`/`LOCAL_HEAD`/`HEAD_SHA` identity
  requirement at `:209`), and deferral cancellation at `:244`.
- `templates/.agents/skills/sd-review/SKILL.md:42` accepts only public
  `key=value` tokens and implements none of the trusted-context contract.
- The recheck block invokes
  `scripts/sd-ai-command-pack-fleet-review-classify.py`, which
  `scripts/sd-ai-command-pack-install-audit.py:121` marks source-only. The
  block is therefore already unreachable in every shipped copy, and the
  `sd-review-pr` skill text is its only written record.
- `sd-fleet-refresh` ships in neither `plugins/sd/skills/` nor the machine
  payload, so relocating the procedure there creates no new plugin-closure
  exception.

## Requirements

- R1: `sd-review` accepts the integration-only profile with the same trusted
  context fields, the same validation strictness, and the same `review-result`
  return shape `sd-review-pr` implements today. The public `key=value` argument
  surface gains none of these keys.
- R2: `sd-review` implements `classified-head` validation, classifier
  invocation, and `defer-finish-work` semantics — behavior, not restated prose.
- R3: `sd-fleet-refresh`'s `review` action invokes `sd-review`, and its
  integration-only path is exercised rather than merely re-worded.
- R4: The Fleet Integration-Only Recheck procedure lives in the source-only
  `sd-fleet-refresh` skill and its script reference resolves before any
  deletion task starts.
- R5: `sd-review-pr` remains present and functional at the end of this task.
  Removing it is child 2's work.

## Acceptance Criteria

- [ ] `sd-fleet-refresh` completes an integration-only review through
      `sd-review` against a real PR head, with the classifier consulted and the
      `review-result` return honored.
- [ ] `sd-review` rejects a malformed or incomplete trusted context with the
      same strictness `sd-review-pr` applies at `SKILL.md:81`, proven by test.
- [ ] `sd-review` refuses integration-only when `classified-head`,
      `LOCAL_HEAD`, and `HEAD_SHA` are not identical.
- [ ] The recheck procedure is reachable from `sd-fleet-refresh` and its
      `fleet-review-classify.py` reference resolves from `source-root`.
- [ ] No public `sd-review` argument accepts a trusted-context key.
- [ ] `sd-review-pr` still runs its own integration-only path unchanged.
- [ ] `make check` is green.

## Out Of Scope

- Deleting or disabling any `sd-review-pr` file, row, or identifier.
- Any full-check script, `Makefile`, or CI gate change.
