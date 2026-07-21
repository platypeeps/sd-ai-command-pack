# Implementation plan: journal validation consistency

1. Add section-aware contradiction detection to the template preflight and
   focused positive/negative tests.
2. Update the template `sd-review-pr` Step 8 to resolve and execute
   `sd-finish-work`; adjust lifecycle contract tests and documentation.
3. Bump the patch version and changelog, then run `make sync` so installed
   mirrors, generated adapters, provenance, and the Obsidian KB match sources.
4. Run focused tests first:
   - `.venv/bin/python -m unittest tests.test_review_preflight`
   - `.venv/bin/python -m unittest tests.test_sdlc_commands`
   - `.venv/bin/python -m unittest tests.test_record_session`
   - `.venv/bin/python -m unittest tests.test_generated_parity`
5. Generate the all-consumer fleet candidate ledger for the exact final
   payload.
6. Run `make check`, inspect the final diff for template/root parity, and
   confirm the working tree contains only task-scoped changes.

## Rollback Points

- If validation-claim matching is noisy, narrow the vocabulary rather than
  broadening exceptions around consumers.
- If routing creates recursion, stop: `sd-review-pr` may invoke
  `sd-finish-work`, but `sd-finish-work` must continue to invoke only
  `trellis-finish-work`.
- Do not hand-edit generated platform adapters; correct the template and rerun
  synchronization.
