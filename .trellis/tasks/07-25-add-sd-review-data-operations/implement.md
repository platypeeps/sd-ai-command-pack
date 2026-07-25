# sd-review Data Operations Implementation Plan

1. Freeze capability, retention-status, purge, deletion-receipt, and error
   fixtures from `sd-github-review`.
2. Add source-template command parsing and exact repository confirmation.
3. Implement read-only status delegation and bounded deterministic rendering.
4. Implement actor/reason-bound idempotent purge delegation and live/backup
   progress rendering.
5. Add GitHub-native exclusions, hold visibility, coverage gaps, and failure
   guidance.
6. Synchronize generated adapters, root mirrors, manifest, help, installed
   guide, tests, changelog, and release ledger.

Validate no-mutation status, purge confirmation/cancellation/replay,
capability incompatibility, outage behavior, redaction, template parity,
installer lifecycle, focused tests, and `make check`.
