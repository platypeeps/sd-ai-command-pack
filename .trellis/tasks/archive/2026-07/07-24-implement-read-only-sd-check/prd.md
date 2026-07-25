# Implement the read-only sd-check command

## Goal

Implement `sd-check` as the one deterministic, side-effect-free verification
primitive and the complete successor to `sd-full-check` behavior that belongs in
a check command.

## Confirmed Evidence

- Review finding `1.4.6.1` confirms that `sd-full-check` says it will not edit
  files without separate authority but refreshes stale ignored `.obsidian-kb`
  output in its default `auto` mode.
- The old full-check path also contains local AI review, optional networked Gito
  review, shell-string configuration, package command discovery, and PR-readiness
  behavior that overlaps review and publishing.
- Parent requirements R2, R22, and R26 define the clean successor boundary.

## Dependencies And Boundaries

- Parent: `07-22-integrate-routed-review-backends`.
- The completed exact-head eligibility evaluator remains the readiness source of
  truth; `sd-check` may consume it read-only but never merge or publish.
- This task creates the successor. `07-24-remove-retired-review-surfaces` owns
  deletion of the old command and compatibility artifacts after all consumers
  use the successor.
- Contains `07-24-validate-shipped-surface-closure`, whose registry-driven
  graph becomes the authoritative shipped-surface check.
- Depends on `07-24-standardize-sandbox-safe-tool-cache-routing` for the shared
  external cache environment; this task must not implement a check-only cache
  policy.

## Requirements

- R1: Expose one `sd-check` command/skill across every supported platform with a
  versioned deterministic JSON result and concise human rendering.
- R2: Run repository verification, scope/readiness checks, install/provenance
  audit, and explicitly configured project checks only. Never invoke an AI
  reviewer, remote router, GitHub review dispatch, finding remediation, commit,
  push, merge, or branch mutation.
- R3: Be side-effect-free across tracked repository state, Git, GitHub,
  generated knowledge, and repository-owned caches. Stale `.obsidian-kb`, repo
  maps, generated adapters, manifests, or provenance are reported with their
  owning refresh command; they are not rewritten.
- R4: Replace shell-string and environment-command execution with one versioned
  pack-owned check configuration using validated argument arrays/adapters,
  bounded paths, explicit timeouts, and normalized outcomes.
- R5: Distinguish `passed`, `failed`, `skipped`, `unavailable`, `invalid`, and
  `indeterminate`; absence or tool failure must not be reported as success.
- R6: Route caches and temporary tool state outside tracked repository paths in
  sandboxed environments. A check that cannot remain non-mutating stops with an
  actionable diagnostic.
- R7: Publish the typed result contract consumed by `sd-review`, `sd-create-pr`,
  `sd-ship`, `sd-work-backlog`, CI/preflight, and the final integration gate.
- R8: Keep neutral source and generated adapters portable; platform-specific
  command syntax remains generator-owned.

## Acceptance Criteria

- [ ] A clean install exposes `sd-check` on every supported platform with one
  shared behavior contract.
- [ ] Tests instrument filesystem, Git, GitHub, provider, and generated-state
  calls and prove zero mutation/provider dispatch for pass, failure, stale, and
  unavailable scenarios.
- [ ] Stale KB/map/generated fixtures fail or report cleanly without changing a
  byte in the repository.
- [ ] Configuration rejects shell strings, unknown schema majors, escaped paths,
  malformed argument arrays, and unbounded timeouts before execution.
- [ ] Every caller consumes the typed result rather than reconstructing check or
  readiness rules in prompt prose.
- [ ] The child-owned shipped-surface graph catches missing source/manifest/
  generated/platform/check edges locally and is consumed identically by CI.
- [ ] Cache-writing checks use the shared sandbox-safe environment without
  redirecting authentication configuration or writing into the repository.
- [ ] Focused behavioral tests, generated parity, install audit, `make sync`, and
  `make check` pass.

## Out Of Scope

- AI review, finding fixes, PR publication, waiting, merging, or generated-file
  refresh.
- Keeping `sd-full-check` as an alias, wrapper, fallback, or configuration mode.

## Notes

- Complete removal of the predecessor is a hard dependency of program closure,
  not optional follow-up cleanup.
