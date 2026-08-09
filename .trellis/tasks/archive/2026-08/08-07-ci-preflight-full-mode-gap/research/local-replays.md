# Local pre-publication replays (2026-08-08, implement.md step 3)

Named check: four replays, expected exit codes 1/0/1/1. All matched.

## Replay 1 — PR-base simulation, defective record → FAIL (exit 1)

Working tree carried `base_branch: "chore/demo-bad-base"` injected into
this task's own `task.json`; command
`SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF=origin/main node
scripts/sd-ai-command-pack-review-preflight.mjs`. Decisive output:

```
FAIL .trellis/tasks/08-07-ci-preflight-full-mode-gap/task.json field root task base_branch "chore/demo-bad-base" must equal the repository default branch "main" or carry a meta.base_branch_exemption reason (...)
Review preflight: 1 failure(s), 1 warning(s).
```

Record restored byte-exact afterwards (verified: only the legitimate
`task.py start` status change remained in `git diff`).

## Replay 2 — same base, clean tree → PASS (exit 0)

Same command after restoration, with the workflow edit present in the
tree: `Review preflight: 0 failure(s), 1 warning(s).` (The warning is
the first-review boundary-risk advisory triggered by the workflow shell
changes — advisory by design, dispositioned in the PR body.)

## Replay 3 — fail-closed base guard → FAIL (exit 1)

The `Validate event head` guard body with
`EVENT_BASE_SHA=0000000000000000000000000000000000000000`:

```
error: event base 0000000000000000000000000000000000000000 does not resolve to a commit; failing closed rather than validating an empty or arbitrary diff window.
```

## Replay 4 — zero-line guard negative probe → FAIL (exit 1)

The report step's body run against an EMPTY c8 temp directory (fresh
`mktemp -d`), exactly as the step would see it if instrumentation
produced no data:

```
error: c8 measured zero lines for scripts/sd-ai-command-pack-review-preflight.mjs (total=0 covered=0). Coverage plumbing is broken, not merely unexercised code.
```

This is the AC evidence that the zero-line hard gate can still fire
(source inspection alone would not prove the negative path executes).
The positive half — non-zero measured lines in a real full-mode run —
is captured from the fix PR's own CI run in `evidence-fix-pr.md`.
