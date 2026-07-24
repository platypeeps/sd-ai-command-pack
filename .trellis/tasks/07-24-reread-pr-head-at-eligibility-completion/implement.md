# Implementation plan: final PR-head eligibility proof

## 1. Lock focused fixtures

- Extend the eligibility fixture runner so the final `headRefOid` query can
  return a stable OID, a changed OID, provider failure, timeout-equivalent
  failure, malformed JSON, missing field, invalid type, and invalid OID.
- Assert local mode queries the retained numeric PR identity exactly once at
  completion and never substitutes the branch name.
- Preserve mutation-spy assertions for Git pushes and GitHub merge commands.

## 2. Extend the canonical evaluator

- Edit `templates/scripts/sd-ai-command-pack-pr-eligibility.py` first.
- Retain the initial PR number and OID in local mode, then make its common
  completion path perform the existing bounded `query_pr_head` call.
- Record the result as additive `pullRequest.finalHeadOid`; populate the same
  field from dependency mode's existing final read without another call.
- Collect both final local and PR observations and apply the documented stable
  precedence before emitting the result.
- Keep the shell adapter and every mutation boundary unchanged.

## 3. Update the contract and synchronized surface

- Document initial/final PR evidence, nullable unavailable evidence, reason
  precedence, and schema-major-1 compatibility in
  `.trellis/spec/backend/quality-guidelines.md`.
- Run `make sync` so the root evaluator remains a byte-identical generated
  mirror; refresh any manifest/provenance data owned by synchronization.
- Do not add a compatibility alias, alternate command, or caller-owned head
  check.

## 4. Prove all completion paths

- Verify stable local and PR heads retain eligible, blocked, and indeterminate
  candidate outcomes as appropriate.
- Verify a moved PR with a stable local branch becomes retryable
  `indeterminate:head_changed`.
- Verify every unavailable/malformed final PR response becomes retryable
  `indeterminate:head_unavailable` without traceback.
- Verify local-head changes and dependency-mode double reads retain their
  existing behavior and now expose normalized final PR evidence.
- Run focused eligibility and housekeeping tests, template/root parity,
  `make sync`, `git diff --check`, and `make check`.

## Dependency Handoff

After this task lands, `07-24-support-planning-only-pr-finalization` may change
the finalization evidence schema while reusing this exact final PR-head read.
Reconcile that later cutover against these fixtures instead of replacing the
completion check or introducing a second provider query.

This task is also the approved bootstrap implementation on PR #244. Before
remote review, replace that PR's planning-only scope statement with the exact
mixed scope, run the complete review gate on the resulting head, and finish
this task through the normal archive/evidence path.
