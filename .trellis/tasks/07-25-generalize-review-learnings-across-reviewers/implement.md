# Reviewer-Neutral sd-review-learnings Implementation Plan

1. Add generic reviewer, shared-publisher, disposition, duplicate, trust,
   missing-source, and truncation fixtures.
2. Extract shared reviewer/adjudication parsing and replace Copilot-specific
   internal types without breaking valid CLI/JSON behavior.
3. Deduplicate underlying issues before clustering while preserving sources.
4. Gate historical promotion on trusted valid evidence and report coverage.
5. Update canonical skill/script templates, generated copies, docs, help,
   schema, tests, changelog/version, manifest, and installer audit.
6. Run focused learning tests, generated parity, install lifecycle,
   `make check`, and fleet validation.
