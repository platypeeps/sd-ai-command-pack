# Verify Remote Reviewer Requests Actually Materialize

## Goal

Make `sd-review-pr` use GitHub's documented Copilot reviewer identifiers and
require observable review activity before counting a remote-review round as
complete.

## Background

- The shipped skill currently defaults to `copilot-pull-request-reviewer`.
  GitHub documents `@copilot` for `gh pr create` / `gh pr edit`, and
  `copilot-pull-request-reviewer[bot]` for REST reviewer requests and review
  author matching.
- PRs #88 and #90 used the undocumented bare slug. The REST request returned
  HTTP 422, while `gh pr edit --add-reviewer` exited successfully without
  producing `reviewRequests`, `latestReviews`, review comments, or issue
  comments. Those runs prove the current identifiers and completion check are
  unsafe; they do not prove that GitHub's documented Copilot path is unreliable.
- A successful trigger command is still only an attempted request. The review
  loop needs author-matched evidence for the current PR head after the trigger
  timestamp before it reports a completed round.

GitHub references:

- CLI: <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/use-code-review?tool=cli>
- REST reviewer identity: <https://docs.github.com/en/copilot/how-tos/copilot-on-github/use-copilot-agents/copilot-code-review>

## Requirements

- **R1: Correct default Copilot request.** Use
  `gh pr edit <pr> --add-reviewer @copilot` as the default explicit Copilot
  trigger after the deterministic local gate. Do not first issue the known-bad
  REST request with `copilot-pull-request-reviewer`.
- **R2: Correct author matching.** Default Copilot review-author matching to
  `copilot-pull-request-reviewer[bot]`. Preserve explicit overrides for other
  reviewers and custom request commands.
- **R3: Generic reviewer support.** Keep the normal GitHub reviewer API path
  for non-Copilot reviewer logins/slugs. If an implementation exposes an
  explicit Copilot REST mode, it must use
  `copilot-pull-request-reviewer[bot]`.
- **R4: Materialization evidence.** Distinguish `request attempted`,
  `request pending`, `review materialized`, and `ambiguous/no materialization`.
  A round completes only when author-matched review or comment activity exists
  for the requested head after the trigger timestamp.
- **R5: Bounded ambiguity handling.** After the configured settle polls and
  one-time full fetch, stop with a diagnostic when no materialization evidence
  exists. Report the request path, reviewer, author matcher, trigger timestamp,
  head SHA, and the custom-command override option.
- **R6: Re-review behavior.** Preserve the bounded loop and request a fresh
  Copilot review after each pushed review-fix commit. Do not count the final
  Trellis journal-only commit as a new review-fix round.
- **R7: Shipped consistency.** Update template sources first, synchronize root
  mirrors through the installer, update docs and environment-variable tables,
  bump the pack version for the shipped behavior change, and add deterministic
  regression coverage.

## Acceptance Criteria

- [ ] The default CLI trigger is exactly `gh pr edit <pr> --add-reviewer @copilot`.
- [ ] The bare `copilot-pull-request-reviewer` slug is absent from active
      defaults and request examples.
- [ ] Copilot author matching defaults to
      `copilot-pull-request-reviewer[bot]`.
- [ ] Tests cover default Copilot, generic reviewer, custom request command,
      and optional explicit REST Copilot behavior.
- [ ] Tests cover a successful request command with no review activity and
      prove that it is not counted as a completed round.
- [ ] Tests cover late-arriving inline comments within the settle window.
- [ ] User-facing diagnostics distinguish policy/availability failures from
      no-materialization after an accepted request.
- [ ] Root/template parity, install audit, KB freshness, and deterministic
      full-check pass.

## Out Of Scope

- Enabling or changing GitHub organization, enterprise, billing, or automatic
  Copilot-review settings.
- Running Prism or Gito from `sd-review-pr`.
- Modifying Trellis-owned runtime or skill files.
