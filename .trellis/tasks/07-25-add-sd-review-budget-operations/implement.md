# sd-review Budget Operations Implementation Plan

1. Pin compatible setup, status, pending, explanation, recovery, and receipt
   contracts plus bounded good/failure fixtures.
2. Extend the authoritative review controller/template with nested budget
   parsing, read-only capability invocation, response validation, and stable
   human/structured output.
3. Implement status aggregation and freshness/unknown rendering without
   double-counting shared pools.
4. Implement pending and no-dispatch explanation views bound to exact head,
   independent review/assurance/gate outcomes, explicit merge policy, and
   compiled configuration/catalog digests.
5. Implement explicit retry with trusted-workflow validation, authorization,
   current-head checks, idempotent attempt/fingerprint handling, and receipt
   correlation.
6. Update canonical `sd-review` guidance, generated adapters, installed docs,
   help/catalog, manifest/provenance, changelog/version, release ledger, and
   install lifecycle expectations.
7. Add focused status/recovery and no-side-effect tests, then run generated
   parity, install/update/check/uninstall, `make check`, and fleet candidate
   validation.

Stop if the pack must access private ledger storage, carry provider
credentials, or invent selection/recovery policy to complete an operation.
