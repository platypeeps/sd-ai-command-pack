# Implementation plan: bookkeeping-only CI fast lane

## 1. Lock the behavioral contract in tests

- Add focused tests for event classification, exact SHA validation, linear
  ancestry, NUL-safe allowed paths, archive delete/add pairs, modes, symlinks,
  submodules, executable bits, mixed deltas, and missing objects.
- Add prior-run evidence fixtures for same-PR success, chained bookkeeping
  success, wrong PR/ref, missing/cancelled/failing runs, and API failure.
- Add workflow-structure tests that protect the `CI Result` name,
  mode-dependent `needs` logic, full-lane conditions, permissions, and
  auto-tag behavior.

## 2. Implement the deterministic scope helper

- Add the `.github/scripts/` classifier with a versioned JSON contract and
  stable reason codes.
- Default to full mode before inspecting optional evidence.
- Run the classifier materialized from the exact before SHA; an absent or
  invalid prior-head helper leaves the bootstrap default at full.
- Keep Git path/history inspection local and NUL-safe; keep API payload parsing
  separately testable and read-only.
- Consume the canonical finish-work bookkeeping validator for metadata and
  journal invariants; keep only history, prior-run, and tree-mode classification
  in this task.

## 3. Integrate the GitHub Actions fast lane

- Add the leading `ci-scope` job and fetch only the history/evidence it needs.
- Gate unit, lint, security, and release-payload jobs on full mode.
- Update `CI Result` to validate every legal full/bookkeeping result matrix and
  fail impossible combinations.
- Route direct main bookkeeping through the bounded lane while keeping real
  merges/releases full and preserving the main-push scope guard.
- Keep permissions read-only and avoid `pull_request_target` or secrets.

## 4. Preserve the one-push finish-work boundary

- Verify standalone review and housekeeping defer their push until archive and
  journal work is complete.
- Add a focused contract test or minimal wording correction only if a path can
  push intermediate bookkeeping state.
- Do not combine local archive/journal commits unless an actual extra push is
  demonstrated.

## 5. Validate and dogfood

- Run the focused classifier and workflow tests.
- Run workflow/YAML security validation and the existing main-push-scope tests.
- Run `git diff --check` and `make check`.
- On the implementation PR, confirm the code-bearing head runs full CI and the
  final finish-work-only successor reports current-head `CI Result` through the
  bookkeeping lane. Record run IDs and observed runner reduction in the task.
- If the fast path is ambiguous or produces an inconsistent aggregate, revert
  the workflow conditions to unconditional full CI before merge.
