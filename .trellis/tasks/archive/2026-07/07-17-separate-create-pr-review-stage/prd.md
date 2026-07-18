# Separate sd-create-pr publish and review stages for sd-ship

## Goal

Give sd-ship a supported Stage 1 publish-only delegation so sd-create-pr does not enter standalone review before Stage 2 can apply merge-through finish-work deferral.

## Requirements

- Add an internal composite-only delegation mode that lets `sd-ship` run the
  publish/reuse portion of `sd-create-pr` without entering its standalone
  `sd-review-pr` handoff.
- Represent that mode as explicit orchestration context supplied by the active
  `sd-ship` Stage 1 call, not as an environment variable or public
  `sd-create-pr` argument.
- Keep standalone `sd-create-pr` behavior unchanged: after publishing, it must
  still enter the normal non-deferred review loop.
- Accept the internal mode only from the active `sd-ship` chain and reject it
  as a public user argument.
- Make Stage 1 and Stage 2 ownership explicit in both shared skills so
  `until=pr`, `until=review`, and `until=merge` each invoke review exactly when
  intended.
- Preserve every update-spec, staging, push, PR creation/reuse, review, CI, and
  finish-work gate.
- Update templates, installed mirrors, usage docs, adapter specs, focused
  lifecycle tests, release metadata, and fleet candidate validation.

## Acceptance Criteria

- [x] `sd-ship until=pr` publishes or reuses the PR and stops without running
  review.
- [x] `sd-ship until=review` publishes in Stage 1, then runs one non-deferred
  review loop in Stage 2.
- [x] `sd-ship until=merge` publishes in Stage 1, then runs one deferred review
  loop in Stage 2 so Stage 4 remains the finish-work owner.
- [x] Standalone `sd-create-pr` still publishes and enters standalone review.
- [x] User-supplied attempts to select the internal mode are rejected before
  update-spec, commit, push, or PR side effects begin.
- [x] Focused lifecycle tests and canonical pack/fleet validation pass.

## Validation

**Focused tests:** 132 lifecycle and installer tests passed.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_sdlc_commands tests.test_install_core
```

**Fleet candidate:** all seven configured consumers passed and the 0.17.0
candidate ledger was written.

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py
```

**Canonical check:** `make check` passed the full unit suite, 100 percent
installer line and branch coverage, shipped-script coverage floors, Ruff,
mypy, JavaScript and shell checks, Bandit, Zizmor, install audit, KB freshness,
release gates, and the deterministic full-check with Prism and Gito disabled.

## Notes

- Discovered while resuming PR #145 through `sd-ship`: creating the operational
  shipping task made Stage 1 necessary, exposing the duplicate review handoff.
- The current PR #145 run should preserve `sd-ship`'s explicit stage boundary
  and leave this implementation for a dedicated follow-up stream.
