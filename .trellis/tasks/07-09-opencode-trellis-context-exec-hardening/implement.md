# Harden Vendored Trellis-Context JS Shell Invocation Implementation Plan

## Execution Order

1. Locate the template and root `trellis-context.js` copies.
2. Replace shell-string execution with `execFileSync` and array args.
3. Preserve timeout/stdout handling and fail-soft behavior.
4. Sync template/root copies and run syntax checks.
5. Add the upstream Trellis handoff text or issue link to this task.

## Validation Plan

Run `node --check templates/.opencode/lib/trellis-context.js` and the root copy.
Run pack drift/parity tests. If possible, create a temp checkout path with
quote/`$` characters and verify the command no longer breaks.

## Documentation And Spec Updates

No consumer docs are expected. The upstream handoff is the important durable
documentation.

## Review Notes

Reviewers should ensure no shell option behavior was implicitly relied on.

## Follow-Ups

If upstream Trellis accepts the fix later, the parked upstream-cleanup task can
decide whether the pack workaround can shrink.
