# Resolve bookkeeping evidenceRunId through the GitHub API

## Goal

Stop the `ci-scope` publish gate from accepting any positive integer as
`evidenceRunId`, and make the accepted value provably describe a real, successful
`Tests` run on the prior head.

## Requirements

- `evidenceRunId` values accepted by the jq validation at
  `.github/workflows/tests.yml:105-106` must be resolved against the GitHub API in
  a trusted step, not accepted as a positive integer. The two clauses there are
  distinct: `:105` requires a non-null ID for a `bookkeeping` result, `:106` is the
  numeric shape check.
- The lookup must be conditional on a non-null ID. A `full`-mode result
  legitimately carries `evidenceRunId: null` (`tests.yml:82`) and the step runs
  under `set -euo pipefail` (`tests.yml:55`), so an unconditional lookup fails
  every full-mode run.
- Lookup failure, run-not-found, or a validation mismatch must route through the
  existing `select_full` idiom (`tests.yml:121-125`) with a new reason code
  matching `test("^[a-z0-9_]{1,80}$")` (`tests.yml:100`). Never `exit 1` — an
  unreachable API must make CI slow, not broken.
- No change may weaken the fail-closed reasons in
  `.github/scripts/bookkeeping_ci_scope.py`.

## Open decision — widen or narrow. Settle before design.

`head_sha == BEFORE_SHA` alone is **not** sufficient and must not be shipped as
the whole check. It accepts a failed run, and a run of an unrelated workflow, on
that SHA. Two facts bound the choice:

1. The spec contract already demands more.
   `.trellis/spec/backend/quality-guidelines.md:1623-1626` requires the prior head
   to have "a completed successful `Tests` workflow plus GitHub Actions
   `CI Result` for the same" head.
2. The existing Python classifier already enforces that.
   `.github/scripts/bookkeeping_ci_scope.py:290-292` requires
   `name == "Tests"`, `path == ".github/workflows/tests.yml"`, and `head_sha`;
   `:318-320` requires `name == "CI Result"` and `head_sha`.

So a `head_sha`-only inline check would be **weaker than what the trusted
classifier already performs** — a hardening change that lowers the bar. The two
honest resolutions:

- **Widen** — validate the full evidence shape inside the workflow block, and
  build a harness that can execute that block. Larger, and duplicates logic the
  classifier already has.
- **Narrow** — scope the inline check to what the block can honestly guarantee,
  and leave full evidence validation in the classifier where it lives. Then the
  acceptance criterion must be written against that narrower guarantee.

Whichever is chosen, the test placement problem below must be solved first,
because it decides whether "widen" is even testable.

## Test-layer constraint

`BookkeepingCiScopeTests.classify` calls `bookkeeping_ci_scope.classify` directly
(`tests/test_bookkeeping_ci_scope.py:158`) — the Python classifier, not the
workflow's inline `gh api` block. A behavioral case for this requirement placed in
that class exercises the wrong layer and would pass while the workflow block is
broken. Either a workflow-block execution harness is built, or the acceptance
criterion is written against something the existing layers can actually observe.

`tests/test_bookkeeping_ci_scope.py:544` asserts the current jq text and must be
updated with any change to the publish gate.

## Acceptance Criteria

- [ ] The `evidenceRunId` path rejects a fabricated run ID, demonstrated by a test
      at a layer that actually executes the validation being changed.
- [ ] A `full`-mode run with `evidenceRunId: null` still succeeds — no regression
      on the common path.
- [ ] Every rejection path selects `mode: full` with a valid reason code; none
      exits nonzero.
- [ ] `make check` passes.

## Notes

- Split from `07-28-pin-bookkeeping-ci-classifier-trust` on 2026-07-29 by
  maintainer decision, recorded in that task's planning adversarial review as
  concern C-14. The parent task's P0 (requirements 1 and 2, the blob-identity
  guard) does not depend on this work and ships without it.
- This is **not** on A-038's attack path. Once the parent's identity guard lands,
  the classifier is trusted code and its evidence fields derive from the trusted
  `gh api` calls at `tests.yml:156` and `:163`. This task closes a shape-check
  gap, not a bypass.
- Nothing reads `needs.ci-scope.outputs.evidence_run_id` today, so nothing gates
  on the value. It is a published `ci-scope` job output (`tests.yml:31`), passed as
  `EVIDENCE_RUN_ID` at `:236` and printed to the step summary at `:249`, so a
  future consumer could gate on it. That is the reason to fix it, and the reason
  it is P2 rather than P0.
- `make sync` is required before full-check after task edits
  (`CONTRIBUTING.md:108-111`).
- `make check` may write outside the repository: full-check auto-refreshes the
  Obsidian KB (`scripts/sd-ai-command-pack-full-check.sh:557-561`) and
  `.obsidian-kb` is a symlink to
  `~/Documents/<obsidian-vault>/raw/sd-ai-command-pack`. Accepted by the
  maintainer 2026-07-29 as expected behavior in this checkout.
