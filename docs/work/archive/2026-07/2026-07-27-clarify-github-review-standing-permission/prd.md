---
title: Clarify standing permission for GitHub commits and code review
status: done
created: 2026-07-27
branch: codex/rollout-sd-ai-command-pack-0-55-1
---
# Clarify standing permission for GitHub commits and code review

## Goal

Make normal GitHub publication and code-review dispatch feel like a seamless
part of every review-capable SD workflow. Once the user invokes such a
workflow, creating and pushing its in-scope commits to the current pull-request
branch, and sending that pull-request diff or code through its configured
GitHub review path, must not trigger another approval question.
For a merge-capable fleet campaign, the same standing authority extends through
each eligible controller-issued consumer merge so an end-to-end rollout does
not pause again after its review findings are addressed. Repository
documentation refreshes should also consistently prefer Archify for generated
technical visuals when that skill is available, without making it a required
dependency.

## Background

- `sd-review-pr` already says not to ask before each configured remote-review
  request, but higher-level workflows and the unified `sd-review` contract do
  not state the same standing authority as explicitly.
- Skill frontmatter descriptions are available during skill discovery in a new
  session, while detailed skill bodies are loaded only after selection. The
  authority therefore needs to be visible in the applicable descriptions as
  well as the workflow bodies.
- The pack's structured-question contract already says routine actions
  authorized by an invocation should not gain extra confirmations.
- The durable behavior must live in shipped templates so new installs,
  upgrades, and future sessions inherit it.

## Requirements

- Define one explicit authority rule: invoking a publication/review-capable
  workflow grants standing permission to create and push its in-scope commits
  to the current GitHub pull-request branch, send the resulting diff/code
  through the configured GitHub review request path, and re-request review
  after an in-scope pushed fix.
- Put the authority in the applicable skill frontmatter descriptions so newly
  created sessions can discover it without first loading a skill body; repeat
  or reference it in the body where execution guidance requires it.
- Apply the rule consistently to the canonical review workflows and their
  publication/lifecycle orchestrators: `sd-review`, `sd-review-pr`,
  `sd-create-pr`, `sd-ship`, `sd-work-backlog`, `sd-fleet-refresh`,
  `sd-fix-ci`, `sd-finish-work`, and `sd-housekeeping` where they own or
  delegate in-scope Git commits, PR-branch pushes, or configured review.
- State that pack guidance must not add an `AskUserQuestion`, plain-text
  confirmation, or other approval prompt solely because an in-scope commit will
  be created/pushed to the PR branch or a configured GitHub reviewer will
  receive the diff/code.
- For `sd-fleet-refresh`, state that invoking a merge-capable campaign grants
  standing approval for every eligible controller-issued consumer
  `sd-housekeeping` merge, including after in-scope review-finding remediation;
  `no-merge` remains the explicit opt-out.
- Preserve questions for genuine decision boundaries such as scope expansion,
  higher-risk fixes, and attempts beyond the configured review-round limit.
- Preserve all independent safety and authority boundaries, including checkout
  trust, exact-head validation, deterministic checks, merge/destructive gates,
  ambiguous file ownership, credentials, and explicit approval for each
  upstream Trellis pull request.
- Keep provider selection generic: the permission follows the configured
  GitHub review path and must not hard-code Copilot as the only allowed backend.
- Update `templates/**` first, synchronize installed root mirrors, and add a
  focused contract test that prevents future workflow drift.
- Route workflow, architecture, sequence, data-flow, lifecycle/state, and
  similar technical visuals created or materially updated in repository
  documentation through `archify` when that skill is available.
- Keep the visual route optional and scoped: fall back gracefully to documented
  repo-native tooling or the existing manual format when Archify is absent, do
  not create unsolicited visuals, and report the route and validation used.

## Acceptance Criteria

- [x] Applicable skill frontmatter descriptions explicitly say that creating
      and pushing in-scope GitHub PR-branch commits, configured GitHub code/diff
      review requests, and post-fix re-requests need no extra user approval once
      a publication/review-capable workflow is invoked.
- [x] Every listed publication/lifecycle skill states the rule or delegates to
      an authoritative skill that states it without contradictory prompting
      language.
- [x] The guidance remains backend-neutral and does not bypass review-round,
      safety, destructive-action, merge, or upstream-Trellis-PR approval gates.
- [x] `sd-fleet-refresh` discovers and executes eligible serialized consumer
      merges without another approval prompt in merge-capable mode, while
      retaining `no-merge` and every controller/lifecycle gate.
- [x] Template and installed skill copies remain synchronized.
- [x] Focused tests assert the standing-permission contract, and the relevant
      generated-parity/pack checks pass.
- [x] `sd-update-spec` prefers Archify for in-scope repository documentation
      visuals, reports the selected route, and retains a tested graceful
      fallback when Archify is unavailable.

## Out of Scope

- Changing GitHub authentication, repository visibility, reviewer routing, or
  configured review providers.
- Removing confirmations required for higher-risk, destructive, ambiguous, or
  out-of-scope operations.
- Authorizing force pushes, pushes to the default branch, or commits that do
  not clearly belong to the active task or pull request.
- Changing upstream Trellis.
- Changing fleet merge eligibility, serialization order, or housekeeping
  validation.
- Requiring Archify, installing it automatically, or changing a repository's
  documentation format solely to accommodate it.
