# Implementation plan: skill workflow remediation program

## 1. Review And Approve Planning

- Review this parent finding ledger and every child PRD/design/implementation
  plan.
- Confirm the task boundaries and dependency waves before starting any child.
- Start only the child that owns the next independently verifiable deliverable;
  do not start this parent unless it gains direct implementation scope.

## 2. Land Foundation Contracts

- Implement the shared PR eligibility gate.
- Implement generated checkout-trust policy.
- Implement the portable structured-question contract.
- Implement command-registry drift lint.
- Structure deterministic housekeeping output and optional update-spec
  references.

## 3. Simplify Workflow Owners

- Land the routed review/check cutover after its external router and local
  foundation dependencies are satisfied.
- Land the fleet controller, backlog/design simplification, review-learnings
  safety boundary, and adaptive audit routing as independently reviewed tasks.
- Preserve templates as source and regenerate after each child; do not defer
  generated parity to the final integration task.

## 4. Run Integration Review

- Map every F01-F17 finding to the landed task and tests.
- Run the cross-child scenario matrix from `design.md`.
- Run focused tests, `make sync`, `make check`, install `--check --json`, and
  applicable fleet candidate validation.
- Verify the live catalog, specs, docs, manifests, and installed receipts have
  no retired surface outside explicit history/migration fixtures.

## 5. Close The Program

- Record child PRs/commits and remaining accepted follow-ups.
- Archive completed children, then archive this parent only when the final
  integration acceptance criteria pass.

## Stop Points

- Stop before `task.py start` until the user reviews the planning artifacts.
- Stop a child if it needs to broaden another child's mutation authority.
- Stop if a cross-repository change requires an upstream Trellis PR; provide a
  paste-ready handoff and request explicit approval for that specific PR.
