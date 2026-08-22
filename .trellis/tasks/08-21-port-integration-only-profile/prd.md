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
- [x] `sd-review` rejects a malformed or incomplete trusted context with the
      same strictness `sd-review-pr` applies at `SKILL.md:81`, proven by test.
- [x] `sd-review` refuses integration-only when `classified-head`,
      `LOCAL_HEAD`, and `HEAD_SHA` are not identical.
- [x] The recheck procedure is reachable from `sd-fleet-refresh` and its
      `fleet-review-classify.py` reference resolves from `source-root`.
- [x] No public `sd-review` argument accepts a trusted-context key.
- [x] `sd-review-pr` still runs its own integration-only path unchanged. *(met with a recorded deviation — see Evidence.)*
- [x] `make check` is green.

## Out Of Scope

- Deleting or disabling any `sd-review-pr` file, row, or identifier.
- Any full-check script, `Makefile`, or CI gate change.

## Evidence (2026-08-22, PR #535, head `31e5950a`)

Criterion 1 is **not** ticked. It requires one real `sd-fleet-refresh`
integration-only review against a live consumer PR head, with the classifier
output and the returned `review-result` recorded in this directory. That cannot
run in CI and was not run. Do not tick it from a dry run or from inspection.

The rest:

| Criterion | Evidence |
| --- | --- |
| Strict rejection of a malformed/incomplete context | `tests/test_review_trusted_context.py::test_trusted_context_is_documented_with_every_field`, `::test_trusted_context_is_accepted_only_from_the_resolved_caller`, `::test_recheck_failure_modes_fail_closed` |
| Exact-head refusal | `::test_integration_only_requires_exact_head_identity`. `sd-review` states the requirement as `classified-head` identical to the live local head and the PR head; `LOCAL_HEAD` / `HEAD_SHA` are `sd-review-pr`'s Step 1 shell variable names for those same two values, and they still appear verbatim in the relocated recheck section. |
| Recheck reachable, classifier resolves from `source-root` | `::test_fleet_refresh_owns_the_recheck_procedure`; `sd-ai-command-pack-surface-check.py` clean |
| No public argument accepts a trusted key | `::test_trusted_context_is_not_an_argument`, mutation-checked: adding `caller` to the enum fails it |
| `make check` green | `rc=0` on head `31e5950a` |

### Deviation on "`sd-review-pr` ... unchanged"

`sd-review-pr` still runs its own integration-only path, and its behavior is
unchanged — but its **text** is not. `design.md` and `implement.md` step 1
authorized *moving* the recheck procedure into `sd-fleet-refresh` rather than
copying it, precisely so two live copies could not drift, and leaving
`sd-review-pr` a pointer. This PRD's criterion was written before that decision
and says "unchanged"; it was not rewritten to match after the fact. Read it as
*behaviorally* unchanged.

Verified by `::test_review_pr_no_longer_inlines_the_procedure`, which asserts
both that the pointer names `sd-fleet-refresh` and that the classifier
invocation is gone, and by
`test_sdlc_commands.py::test_fleet_integration_only_review_is_head_bound_and_fail_closed`,
which still pins `sd-review-pr`'s own profile, `0` remote rounds, and deferred
finish-work message.
