# Implementation plan: command surface drift lint

## 1. Normalize Registry Data

- Inventory current command definitions, generated target maps, help/catalog
  lists, configuration names, and retired-target registries.
- Choose one canonical model and add schema validation.

## 2. Implement The Linter

- Add structured and token-aware live-root scans.
- Add bounded allowlist entries with file pattern and reason.
- Emit JSON and concise human findings.

## 3. Seed Current Drift And Fixtures

- Add the stale `sd-review-local-all` spec case as a regression fixture.
- Correct live spec content and register intentional historical mentions.
- Add rename/removal/missing-target/stale-config fixtures.

## 4. Integrate Clean Cutovers

- Provide documented registry update steps to the routed-review and backlog
  retirement tasks.
- Add the linter to `make check` and release/fleet candidate validation.

## 5. Validate

- Run focused scanner/registry/allowlist tests, generated parity, `make sync`,
  `make check`, install audit, and a clean command-surface inventory.

## Stop Points

- Stop if a proposed exclusion would hide an entire live documentation root.
- Stop if two registries remain authoritative; consolidate before enforcing
  drift against them.
