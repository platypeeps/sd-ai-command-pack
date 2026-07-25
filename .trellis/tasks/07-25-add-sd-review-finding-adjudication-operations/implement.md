# sd-review Finding Adjudication Operations Implementation Plan

1. Pin compatible setup, finding-query, adjudication-event, authorization,
   workflow-result, and receipt fixtures.
2. Add nested `findings list|adjudicate|status` argument parsing and shared
   capability/response validation to the authoritative review controller.
3. Implement read-only list/status output with coverage, freshness, dispute,
   truncation, and limitations.
4. Implement preview and explicit structured adjudication decisions for
   individual and bounded batch requests.
5. Invoke only the trusted workflow, preserve idempotency/reconciliation, and
   reject pack-local trust upgrades.
6. Update canonical skill, command source, generated adapters, installed guide,
   help/catalog, manifest, changelog/version, release ledger, and tests.
7. Run focused controller/interaction/contract tests, generated parity,
   install lifecycle, `make check`, and fleet candidate validation.
