# Canonical release-prep implementation plan

1. Add `.github/scripts/prepare-release.py` with small, testable helpers for
   command execution, surface-report validation, release-prerequisite
   validation, and ordered preparation orchestration.
2. Add `release-prep` to the Makefile as a source-maintainer target that runs
   the orchestrator with `.venv/bin/python`, then invokes `$(MAKE) check` only
   after preparation succeeds.
3. Add focused unit tests for exact command ordering, fail-fast behavior,
   malformed or extra surface findings, version/changelog prerequisites,
   candidate reuse versus refresh, and final `make check` execution.
4. Update `CONTRIBUTING.md`, `README.md`, `docs/FLEET_ROLLOUT.md`, and
   `.trellis/spec/backend/manifest-and-filesystem.md` so maintainers use the
   canonical command and understand its fail-closed ordering.
5. Run focused tests, `make release-prep` where current evidence permits, and
   `make check`; inspect the resulting diff and repository status.

## Review convergence

- The command remains source-only and does not alter installed consumer
  interfaces.
- The expensive operation is behind both structural closure and versioning
  prerequisites.
- Existing strict validators remain authoritative; the orchestrator only
  recognizes the one transitional stale-ledger state needed to refresh their
  evidence.
- The final normal gate remains `make check`, so the new path cannot define a
  weaker meaning of release readiness.
