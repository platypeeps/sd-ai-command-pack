# Optimize audit charter routing

## Goal

Reduce routine formal-audit cost and context while preserving an explicit
exhaustive mode and transparent coverage. Route optional charters from
deterministic repository fingerprints and user-selected dimensions, never from
an opaque claim that a risk area is irrelevant.

## Evidence

- `templates/.agents/skills/sd-audit-repo/SKILL.md:28-38`, 70-104, and 128-143
  define a broad base charter set plus conditional dimensions.
- The charter corpus is intentionally comprehensive, but loading and running
  every dimension on every repository can spend review capacity on absent
  stacks or surfaces.
- Follow-up task creation is already consent-gated; structured multi-selection
  can improve that final decision without interrupting the audit itself.

## Dependencies

- Consume `07-22-add-portable-structured-questions` only for choosing proposed
  follow-up tasks.
- No dependency on routed review or fleet orchestration.

## Requirements

- R1: Add explicit `depth=standard|exhaustive` and optional dimension controls.
  Exhaustive mode runs the full charter contract and remains the reference for
  high-assurance audits.
- R2: Define a mandatory standard core that cannot be skipped, including at
  least correctness, security/trust boundaries, tests, build/release, and
  operational failure handling as applicable to the repository type.
- R3: Route additional charters through deterministic fingerprints from files,
  manifests, dependencies, languages, infrastructure, data stores, public APIs,
  UI, and deployment surfaces. Record each fingerprint and routing reason.
- R4: Allow an explicit dimension selector to add charters regardless of
  fingerprints. It cannot silently remove mandatory charters.
- R5: Report every charter as `run|not-applicable|not-selected|failed`, with a
  reason and evidence. Omission must remain visible.
- R6: Keep charter-specific findings independent and preserve the current
  severity/evidence/report normalization.
- R7: Add a calibration suite comparing standard and exhaustive modes across
  representative repositories. Standard mode cannot miss seeded material
  findings in charters its fingerprints should select.
- R8: Do not claim standard mode is equivalent to exhaustive mode. Reports must
  disclose coverage and recommend exhaustive mode for release/security or other
  policy-required contexts.
- R9: Use structured multi-select only when the user chooses which proposed
  prevention tasks to create after findings are complete.

## Acceptance Criteria

- [ ] Exhaustive mode selects every canonical charter and matches existing
  formal coverage expectations.
- [ ] Standard mode always selects the mandatory core and deterministically
  selects optional charters from fixture fingerprints.
- [ ] Fingerprint absence, unknown stack, conflicting evidence, and classifier
  failure are visible and conservative; unknown state does not silently skip a
  risk dimension.
- [ ] Seeded UI, database, API, infrastructure, dependency, and release findings
  are caught by the expected standard routing fixtures.
- [ ] Reports enumerate run and omitted charters with evidence and do not claim
  exhaustive assurance in standard mode.
- [ ] Follow-up task selection uses the portable structured-question contract
  without prompting before or during the requested audit.
- [ ] Focused routing/report tests, representative calibration, generated
  parity, and `make check` pass.

## Out Of Scope

- Weakening exhaustive audit coverage.
- Using an LLM-only applicability decision without deterministic evidence.
- Automatically creating follow-up tasks without consent.
