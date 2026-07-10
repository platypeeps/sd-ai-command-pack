# Verify Remote Reviewer Requests Actually Materialize Design

## Overview

Keep `sd-review-pr` provider-neutral while giving its default Copilot adapter
the identities GitHub documents. Request execution and review completion are
separate contracts: command success records an attempt; author-matched GitHub
activity proves materialization.

## Configuration Contract

Retain the existing environment variables, but derive defaults conditionally:

- `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REVIEWER`: request identity. Default
  `@copilot`.
- `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_AUTHOR_MATCH`: review/comment author.
  Default `copilot-pull-request-reviewer[bot]` when the reviewer is `@copilot`;
  otherwise default to the configured reviewer.
- `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND`: custom trigger. When
  present, it remains authoritative and bypasses built-in reviewer requests.
- `SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_ROUND_LIMIT`: unchanged bounded-loop
  limit.

Do not overload one string as both Copilot's CLI alias and REST/bot login.

## Request Flow

1. Run the deterministic local full-check with Prism and Gito disabled.
2. Record the UTC trigger timestamp and current PR head SHA.
3. If a custom request command is configured, execute it.
4. Otherwise, if the reviewer is `@copilot`, run
   `gh pr edit "$PR_NUMBER" --add-reviewer @copilot` directly.
5. Otherwise, use the generic GitHub requested-reviewers REST endpoint with the
   configured reviewer, retaining `gh pr edit --add-reviewer` as its fallback.
6. Record the request path and command result, but do not record a completed
   remote-review round yet.

An explicit future Copilot REST mode may request
`copilot-pull-request-reviewer[bot]`; the default path should remain the
documented CLI command so it avoids the known-bad bare slug and collaborator
error.

## Materialization State Machine

- **Attempted:** request command returned success for the current head.
- **Pending:** reviewer remains requested, or activity may still be within the
  settle interval.
- **Materialized:** a review, review comment, or top-level PR comment from
  `REMOTE_REVIEW_AUTHOR_MATCH` appears after the trigger timestamp for the
  requested head.
- **Ambiguous/no materialization:** the request is absent or cleared after the
  bounded settle polls and one-time full fetch, with no author-matched activity.

`updatedAt` is only a hint that triggers a full fetch; it is not sufficient
evidence because unrelated PR events also update it. A cleared request without
author-matched activity must not increment the completed-round count.

## Error Reporting

Differentiate:

- command rejection, including Copilot policy or availability errors;
- accepted request that remains pending;
- accepted request with no observable materialization;
- completed review with no actionable findings; and
- completed review with actionable findings.

The ambiguous report includes reviewer/author identities, request path,
timestamp, head SHA, polling duration, and the
`SD_AI_COMMAND_PACK_REVIEW_PR_REMOTE_REQUEST_COMMAND` override.

## Compatibility And Migration

- Existing custom reviewer configurations continue to use their current
  generic request path.
- Existing repos that explicitly set the old bare Copilot slug receive a clear
  diagnostic recommending `@copilot`; do not silently reinterpret arbitrary
  custom reviewer values.
- Automatic Copilot reviews remain an external GitHub setting. The explicit
  request loop stays deterministic and runs only after the local gate.
- Trellis-owned files are not modified.

## Affected Files

- `templates/.agents/skills/sd-review-pr/SKILL.md` and installed mirror
- Platform review-pr adapters only when their summary becomes stale
- `templates/docs/SD_AI_COMMAND_PACK.md` and installed mirror
- `README.md`, environment-variable tables, and `CHANGELOG.md`
- `manifest.json` and installed provenance
- `tests/test_review_scope.py` and focused installer/parity tests

## Validation

- Static assertions for request and author identities across template/root/docs.
- Fixture cases for materialized, pending, and ambiguous states.
- Install self-sync and provenance audit.
- KB refresh and deterministic full-check with local AI providers disabled.
