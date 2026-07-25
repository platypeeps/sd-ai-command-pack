# Implement the unified routed sd-review command Implementation Plan

## Execution Order

1. Pin the released router v1 descriptor/request/receipt contract in focused
   fixtures and add a strict configuration/parser boundary for
   `remoteIntegration` without weakening the completed local-stage parser.
2. Add the review coordinator's pure scope, state, request, receipt, capability,
   and report functions. Cover identity, bounds, idempotency, state transitions,
   and atomic persistence before enabling any command execution.
3. Compose the typed `sd-check` and exact-scope local-stage subprocesses.
   Preserve their typed statuses and enforce the approved provider-failure and
   optional-absence matrix.
4. Add read-only GitHub capability/PR/head discovery, durable workflow dispatch,
   receipt query/reconciliation, declared-channel observation, paginated thread
   reads, and typed CI collection. Persist dispatch intent first and fail closed
   on ambiguous outcomes.
5. Add the canonical `sd-review` skill and neutral source, register it once,
   generate all platform adapters, and keep structured decisions limited to
   higher-risk fixes, true scope expansion, and explicit round extension.
6. Add focused lifecycle fixtures for changes, branch, codebase, and PR scopes;
   exact receipt reuse/invalidation; concurrent first-head local review;
   low-risk and bookkeeping successors; provider failures; optional/required
   router absence; malformed/incompatible/unavailable routing; delayed feedback;
   multi-page threads; changed correlation IDs; repeated families; and new
   exact heads.
7. Update README, installed guide, help/examples as generated, adapter spec,
   changelog, manifest version/provenance, and fleet candidate evidence. Do not
   remove or redirect legacy public surfaces; their retirement task owns that
   separate graph.

## Validation Plan

- Focused: controller/protocol/configuration/state-machine tests plus
  `tests/test_review_stage.py`, `tests/test_surface_generation.py`, installer
  manifest/audit tests, and shipped-script per-file coverage.
- Generation: `make generate`, `make sync`, template/root byte checks, command
  surface closure, and install `--check --json`.
- Broad: typed `sd-check`, full fleet candidate validation, and `make check`.
- Shipping: review the exact pushed head, remediate all actionable threads, and
  re-run the final gate after any review or bookkeeping successor commit.

## Documentation And Spec Updates

- Add the executable unified-review scenario to
  `.trellis/spec/frontend/adapter-guidelines.md` and replace statements that
  describe `sd-review-pr` as the future owner without prematurely documenting
  legacy removal as complete.
- Document the v1 router setup descriptor, optional local-only behavior,
  explicit/required failures, one report contract, and no direct fallback.
- Record the new public command and payload version in `CHANGELOG.md`,
  `README.md`, `docs/SD_AI_COMMAND_PACK.md`, manifest, provenance, and fleet
  candidate ledger.

## Review Notes

- Inspect every side-effect boundary for intent-before-dispatch persistence,
  exact-head validation, duplicate billing, hostile receipt data, symlink/path
  escape, bounded payloads, and secret leakage.
- Verify provider unavailability never becomes positive confidence or an
  implicit more-expensive local fallback.
- Verify router `absent` is not used for declared-invalid, incompatible,
  unreadable, or post-dispatch uncertain state.
- Verify the new skill never invokes `sd-review-local`, `sd-review-pr`, or a
  direct Copilot request.

## Rollback Points

- Before registry generation: revert the isolated controller/config/test work.
- Before remote dispatch support: keep pure request/receipt/capability code but
  do not expose the command if reconciliation is not fail-closed.
- After publication: pin the last pack release; do not add a legacy alias or
  direct reviewer fallback.

## Follow-Ups

- `remove-retired-review-surfaces` deletes old commands and configuration.
- `simplify-review-shipping-composition` migrates `sd-create-pr`, `sd-ship`, and
  internal wait ownership to the successor command.
- `validate-sd-workflow-program-integration` owns the final cross-child matrix
  and release/pilot proof.
