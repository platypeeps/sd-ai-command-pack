# Add sd-review data operations

## Goal

Add portable `sd-review data status` and explicitly confirmed `sd-review data
purge` operations over the router-owned retention contracts.

## Background

`sd-github-review` owns the immutable `standard-v1` policy, data classes,
durations, lifecycle, legal-hold, purge, backup, deletion-receipt, and coverage
semantics. This task renders and safely orchestrates those contracts; it is not
a second retention authority.

## Requirements

- Add `sd-review data status [--repo <owner/repo>]` as a read-only operation.
  Show policy ID/version/digest, record counts and next deletion by class,
  active holds, retained coverage window/gaps, last deletion, live-purge state,
  backup purge deadline, and excluded GitHub-native artifacts.
- Add `sd-review data purge --repo <owner/repo>` as an explicitly destructive
  operation requiring authenticated tenant/repository scope, actor, reason,
  exact repository confirmation, and idempotency identity.
- Present live deletion and backup expiry as separate phases. Never claim full
  purge before the contract reports both, and preserve the bounded deletion
  receipt.
- Consume setup-discovery and versioned status/purge contracts only. Reject
  absent, incompatible, malformed, stale, or unauthorized integrations with
  actionable guidance and no state change.
- In standalone mode, report that no private service data exists under this
  contract and that status/purge are unsupported. Do not imply that GitHub-
  native artifacts were inspected or deleted.
- State that uninstall is not purge and that private purge does not remove
  GitHub checks, comments, reviews, Actions logs, or other GitHub-native state.
- Keep legal-hold mutation and retention-profile definition out of this MVP;
  status reports active holds but the private administrative boundary owns
  hold creation/release.
- Implement source-template/generated parity, help, docs, manifest, installer,
  lifecycle, and adapter tests required by the command pack.

## Acceptance Criteria

- [ ] Status is deterministic, bounded, read-only, coverage-aware, and redacts
      prohibited/private content.
- [ ] Purge requires exact repository confirmation, actor/reason, and compatible
      capability; cancellation or validation failure performs no mutation.
- [ ] Replay returns the same purge/deletion identity and never duplicates the
      destructive operation.
- [ ] Output distinguishes pending live deletion, live deleted, backup pending,
      and backup expired, plus GitHub-native exclusions.
- [ ] Absent/incompatible/unavailable control planes fail closed without ledger,
      repository, GitHub, or provider mutation.
- [ ] Standalone status/purge return actionable unsupported output and perform
      no mutation, while managed outage remains unavailable rather than
      changing mode.
- [ ] Every supported adapter, template/generated mirror, help/catalog,
      install/update/check/uninstall, focused test, and `make check` gate passes.

## Dependencies

- Parent `07-25-add-routed-review-operator-ux`.
- `platypeeps/sd-github-review:07-25-define-review-data-retention-policy` and
  stable setup-discovery/status/purge conformance fixtures.

## Out of Scope

- Retention policy authority, legal-hold mutation, provider-side deletion, or
  deletion of GitHub-native artifacts.
