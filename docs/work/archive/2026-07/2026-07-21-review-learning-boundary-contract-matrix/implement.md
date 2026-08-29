# Implementation plan: boundary contract regression matrix

1. Add failing tests for the six category families and for excluded test,
   copied, generated, and vendored paths.
2. Introduce the declarative category table and changed-line classifier in the
   template review-preflight source.
3. Render stable, deduplicated, bounded matrix output while preserving current
   advisory exit behavior.
4. Synchronize the root preflight copy and update `sd-review-pr` plus adapter
   guidance if category disposition wording changes.
5. Add mixed-language and unreadable-diff regressions and verify no existing
   boundary-warning test regresses.
6. Run focused preflight tests, adapter/template parity, install audit, and the
   repository full-check.

Do not start this task until the user reviews the planning artifacts.
