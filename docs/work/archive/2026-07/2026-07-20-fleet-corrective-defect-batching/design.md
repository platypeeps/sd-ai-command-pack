# Batch Source Defect Sweeps Before Corrective Fleet Releases Design

## Overview

Turn the first verified pack-owned rollout blocker into one bounded corrective
campaign. The campaign sweeps the complete affected contract surface, iterates
with focused tests and optional partial candidate diagnostics, then creates one
corrective version and one canonical full-fleet candidate ledger after the
payload is stable.

This task changes the operator contract, not the candidate validator's storage
format or the Trellis task schema.

## Proposal

Add a `Corrective Campaign` contract to the fleet guide and the canonical
`sd-fleet-refresh` skill:

1. Pause consumer mutation on the first verified pack-owned blocker.
2. Reuse or create one source-owned Trellis corrective task and retain the
   original fleet task for later resume.
3. Record a finding ledger in that corrective task with identifier, affected
   contract family, evidence, severity, disposition, fix, and regression.
4. Sweep equivalent paths before selecting a version: producers and consumers,
   mutation paths, persisted and dynamically loaded data, normalization and
   nullability, CLI exposure, human and JSON output, failure behavior, and
   generated/template mirrors where applicable.
5. Iterate with focused source tests and `--consumer` candidate diagnostics.
   Partial runs remain diagnostic and cannot replace the canonical ledger.
6. Freeze the payload only after the sweep and regressions converge, select one
   corrective version, update every release surface once, and run the canonical
   seven-consumer candidate validation once for that final payload.
7. Merge and tag through the source lifecycle, then resume the original fleet
   task from live preflight state.

An independently urgent security defect may ship immediately. Its task must
record why waiting for the broader campaign would increase risk; the remaining
campaign stays open rather than being silently discarded.

## Boundaries And Non-Goals

- Preserve the existing blocker classes until the separate interruption-
  severity task implements richer classification.
- Do not create a new executable campaign database or duplicate Trellis state.
- Do not change the rule that partial candidate runs leave the ledger intact.
- Do not combine consumer product work with a source pack correction.
- Do not roll consumers from an untagged source candidate.

## Affected Files

- `templates/.agents/skills/sd-fleet-refresh/SKILL.md` is the shipped source of
  truth; `.agents/skills/sd-fleet-refresh/SKILL.md` remains its byte-identical
  installed mirror.
- `docs/FLEET_ROLLOUT.md` owns the detailed operator procedure.
- `tests/test_sdlc_commands.py` pins the campaign ordering and safety contract.
- `manifest.json`, `CHANGELOG.md`, and the candidate ledger carry the required
  patch release evidence for a shipped skill change.
- The five sibling planning tasks created from the same retrospective remain
  independent backlog records and ship with this first planning PR.

## Data And Command Contracts

The finding ledger is Markdown in the source corrective task and uses these
columns:

`ID | Contract family | Evidence | Severity | Disposition | Fix | Regression`

Every verified blocker gets one row. Exact duplicates reuse the owning row.
The campaign may run:

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-fleet-candidate-check.py --consumer <name>
```

Only the no-filter canonical command may update
`docs/fleet/candidate-validation.json`.

## Risks And Edge Cases

- A campaign can become an excuse for unbounded analysis. Bound the sweep to
  contract families adjacent to the verified failure and record excluded areas.
- A second unrelated blocker may arrive while paused. Give it a distinct row;
  include it only when the same corrective PR remains coherent.
- Review feedback after version selection reopens the campaign when it changes
  shipped behavior; do not stack another version bump inside an unmerged PR.
- Urgent security handling must remain explicit and exceptional.

## Validation

- Focused command-contract tests assert pause-before-version, finding-ledger,
  sweep, partial-diagnostic, single canonical run, urgent exception, and resume
  language.
- Generated parity verifies the template and installed skill remain identical.
- The canonical pack gate validates release metadata and the final candidate
  ledger.
