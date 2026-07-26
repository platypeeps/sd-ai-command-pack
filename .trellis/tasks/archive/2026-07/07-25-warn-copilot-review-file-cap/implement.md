# Warn on Copilot review file cap Implementation Plan

1. Add and validate `copilotReviewFileLimit` in the preflight default/config
   loader.
2. Add the exact-boundary file-count result to `checkDiffSize()` without
   changing the existing advisories.
3. Add focused 300/301/override/invalid-config regression coverage.
4. Document the key and bump the compatible shipped-payload patch release.
5. Generate and synchronize root mirrors and provenance.
6. Run focused tests, `make check`, the release payload gate, and full fleet
   candidate validation.

## Rollback Gates

- Stop if the diff source omits files or requires a GitHub API call.
- Stop if template/root parity cannot be regenerated cleanly.
- Do not publish if the release ledger does not bind to the exact payload.
