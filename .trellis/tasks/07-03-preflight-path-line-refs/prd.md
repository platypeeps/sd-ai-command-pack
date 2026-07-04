# Accept path:line references in the preflight doc-path checker

## Goal

The review-preflight documentation path checker rejects markdown link/code-span targets carrying :line suffixes (path.md:42), which are the natural citation format agents produce. Hit three times in one week: AMC task PRD (ci.yml:267) broke AMC's local gate on main, the pack's own task design.md, and rwbp-website's 07-03-review-guard-doc-path-coverage task documents the systemic version incl. the docs-only-lane blind spot.

## Requirements

- R1: A documentation reference whose target carries a trailing line suffix
  (`path:12`, `path:12-34`, `path:12:5`) resolves against the base path: the
  reference is missing only when both the literal target and the suffix-
  stripped base path are absent. Literal files whose names contain `:digits`
  therefore keep resolving.
- R2: The behavior lives in the shared template
  `templates/scripts/sd-ai-command-pack-review-preflight.mjs` and its
  installed twin, so every consumer inherits it on the next refresh.
- R3: Behavioral test coverage runs the real script under node against a
  temp repo (skip gracefully when node is unavailable), asserting both the
  accepted `existing-path:line` case and the still-failing `missing-path:line`
  case.

## Non-goals

- No line-number bounds validation (files move; a stale line number is not a
  broken reference).
- No changed-files-scoped checking mode — that is rwbp-website's repo-local
  guard concern (their task 07-03-review-guard-doc-path-coverage).

## Acceptance Criteria

- [ ] A doc referencing `scripts/<existing>.sh:12` passes the preflight; a
      doc referencing `docs/<missing>.md:5` still fails.
- [ ] Twin gate passes (template and installed copy identical).
- [ ] Test suite green; node-gated test skips cleanly where node is absent.
