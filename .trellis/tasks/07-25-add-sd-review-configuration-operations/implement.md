# sd-review Configuration Operations Implementation Plan

1. Pin setup-discovery and configuration contract majors plus good, malformed,
   incompatible, and unavailable fixtures.
2. Extend the authoritative review controller/template with nested config
   argument parsing, capability resolution, bounded invocation, and structured
   result validation.
3. Implement read-only validate, render, explain, semantic diff, explicit
   merge-policy, and branch-protection readiness paths.
4. Implement init and one-time migration with preview, observed-identity
   conflict checks, atomic writes, recovery guarantees, and post-write
   validation.
5. Update canonical `sd-review` skill and command-source guidance; regenerate
   all supported adapters and synchronize root/template script twins.
6. Update installed docs, help/catalog, manifest/provenance,
   changelog/version, release ledger, and installer lifecycle expectations.
7. Add focused controller/contract and mutation-safety tests, then run
   generated parity, install/update/check/uninstall, `make check`, and fleet
   candidate validation.

Stop if router contracts cannot provide canonical output and bounded safe
diagnostics without the pack reproducing compiler logic.
