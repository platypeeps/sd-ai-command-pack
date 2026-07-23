# Implementation plan: untrusted checkout preflight

## 1. Inventory Capabilities

- Enumerate every canonical command and all paths by which it can execute
  checkout-owned content or mutate state.
- Mark true non-executing exemptions with evidence.

## 2. Add Canonical Policy

- Extend the command registry/schema with capability metadata and conservative
  defaults.
- Implement a read-only trust classifier with structured output and reason
  codes.

## 3. Generate Adapter Guards

- Replace the four-command allowlist with capability-driven generation.
- Add host-specific safe-mode/stop text without changing canonical skill
  semantics.
- Ensure the guard precedes any repository script, config-command, package,
  hook, or provider execution.

## 4. Verify Security Boundaries

- Test malicious fork modifications to every representative execution path.
- Test same-repository, trusted local, detached, missing-origin, and API-failure
  cases.
- Add a registry completeness test that fails future unclassified commands.

## 5. Validate

- Run focused generator/security tests, `make sync`, `make check`, install
  audit, and generated diff review across all supported platforms.

## Stop Points

- Stop if a proposed safe mode needs to execute any untrusted checkout path.
- Stop if host adapters cannot enforce equivalent pre-execution ordering;
  document the unsupported capability and fail closed on that platform.
