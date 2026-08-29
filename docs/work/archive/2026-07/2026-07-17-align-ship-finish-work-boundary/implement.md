# Implementation plan

1. Add focused lifecycle-contract tests for standalone review, review
   stop-point, merge continuation, watch-only Stage 3, and single-owner Stage
   4 behavior.
2. Update the canonical `sd-review-pr` template with the authorized composite
   deferral mode and explicit final-report state.
3. Update the canonical `sd-ship` template so `until=merge` passes the
   deferral context to Stage 2 and `no-merge` to Stage 3, while
   `until=review` keeps normal review behavior.
4. Update consumer documentation and the adapter-guideline spec with the
   lifecycle ownership matrix.
5. Bump the patch version and changelog because shared shipped skill behavior
   changes.
6. Run `make sync` to update installed mirrors, provenance, and the local KB.
7. Run focused tests, generated parity, the canonical repository check, and
   the fleet candidate validation.
8. Review the final diff for template/mirror parity and accidental Trellis
   runtime edits.
