# Design: Align sd-ship finish-work ownership

## Problem

`sd-review-pr` currently runs finish-work as part of its clean-loop exit. When
`sd-ship` continues past that stage to `sd-watch-pr` and `sd-housekeeping`, the
active task is archived before the PR has settled or merged. In addition,
standalone `sd-watch-pr` can invoke housekeeping itself even though `sd-ship`
models housekeeping as a separate fourth stage.

## Ownership model

| Invocation | Review exit | Watch exit | Finish-work and merge owner |
| --- | --- | --- | --- |
| Standalone `sd-review-pr` | Finish work | N/A | `sd-review-pr` |
| `sd-ship until=review` | Finish work | N/A | `sd-review-pr` |
| Standalone `sd-watch-pr` | N/A | Existing automatic handoff | `sd-housekeeping` |
| `sd-ship until=merge` | Defer finish-work | Watch with `no-merge` | Stage 4 `sd-housekeeping` |

## Contract changes

The canonical `sd-review-pr` skill gains a composite-only
`defer-finish-work` invocation mode. It is not a public user argument: the
skill accepts it only when `sd-ship` is continuing through `until=merge`.
Without that authorized context, Step 8 remains unchanged.

The canonical `sd-ship` skill owns the internal handoff:

1. For `until=review`, run Stage 2 normally.
2. For `until=merge`, run Stage 2 with `defer-finish-work` and require its
   report to identify the Stage 4 handoff.
3. Run Stage 3 with the already-supported `no-merge` option, plus any user
   `timeout-minutes=` value.
4. Run Stage 4 housekeeping once. Housekeeping performs finish-work, pushes
   any task/journal commits, rechecks CI, and then applies its merge gate.

## Failure behavior

Deferral does not mark a blocked review as complete. If review fails, the
chain stops under the existing Stage 2 rules. If Stage 3 blocks or times out,
the chain stops without running Stage 4, leaving the active task in place for
a later resume. No merge or cleanup runs from a blocked stage.

If the PR is observed as already merged, existing post-merge handoff rules
remain authoritative; this change does not invent a second cleanup path.

## Compatibility

Standalone command behavior remains compatible. The internal mode is defined
in the shared skills, so thin platform adapters do not need independent
workflow logic. Existing user arguments and environment variables are
unchanged.

## Verification

Static contract tests assert all ownership branches and protect against a
future reintroduction of duplicate finish-work or housekeeping calls.
Generated-parity tests continue to verify installed mirrors. Full repository
checks and fleet candidate installs validate the shipped payload.

## Rollback

Revert the shared-skill, documentation, spec, test, and release-metadata
commit together. No persistent data migration or consumer configuration
change is involved.
