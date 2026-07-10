# Verify remote reviewer requests actually materialize

## Goal

PR #88 showed the direct Copilot review request API returning 422, while gh pr edit --add-reviewer returned success but no reviewRequests/latestReviews/comments appeared after polling. Harden sd-review-pr so a cleared request without review activity is reported or retried with repo-configured evidence instead of being treated as a completed remote review.

## Requirements

- R1: Reproduce or simulate the PR #88 behavior where the primary Copilot
  reviewer API returns HTTP 422, the `gh pr edit --add-reviewer` fallback
  exits successfully, but `reviewRequests`, `latestReviews`, pull comments, and
  issue comments show no remote-review activity after polling.
- R2: Update `sd-review-pr` guidance and/or helper scripts so this state is not
  silently treated as a completed remote-review round without evidence.
- R3: Preserve support for repos where the configured remote reviewer clears
  its request without publishing a formal review, but require some observable
  evidence such as a latest review, PR comment, issue comment, updated timestamp
  after the trigger, or a repo-configured custom request command result.
- R4: Document the fallback behavior and the recommended repo override
  (`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND`) when the standard
  GitHub reviewer request path is not reliable.

## Acceptance Criteria

- [ ] Review-loop instructions distinguish "request cleared with review
      evidence" from "request cleared with no observable activity".
- [ ] A deterministic test or scripted fixture covers the no-materialization
      state when practical.
- [ ] PR #88 evidence is referenced in the task or implementation notes.
- [ ] Full-check remains green after any skill/script changes.

## Notes

- Evidence from PR #88: direct
  `repos/platypeeps/sd-ai-command-pack/pulls/88/requested_reviewers` API call
  returned HTTP 422 for `copilot-pull-request-reviewer`; `gh pr edit
  --add-reviewer copilot-pull-request-reviewer` returned success; after roughly
  90 seconds, `reviewRequests`, `latestReviews`, PR review comments, and issue
  comments were all empty while CI was green.
