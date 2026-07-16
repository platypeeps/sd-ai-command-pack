# Add sd-audit-repo formal multi-agent repo audit command

## Problem

Deep repo reviews are currently ad-hoc. Each one improvises its dimension set,
report format, severity language, and follow-up mechanism. Findings evaporate
between sessions ("what's still open from the review?" requires transcript
archaeology), false positives reach reports unverified, and findings are not
systematically reconciled against the Trellis backlog. The pack has no
distributed command for a formal, repeatable, whole-repo audit.

## Goal

Ship a distributed `sd-audit-repo` command + skill that runs a standardized,
multi-dimension, sub-agent-driven audit of the current repository and produces
a canonical report plus a persistent, committed findings ledger with follow-up
support.

## Users

Developers on any pack-consuming Trellis repo, and the pack repo itself
(dogfooded).

## Requirements

### Functional

- R1. New distributed command `sd-audit-repo` on all supported platforms:
  neutral command template + bespoke Claude/Gemini/GitHub adapters + shared
  skill fan-out, following the existing per-command wiring pattern
  (sd-work-designs is the blueprint).
- R2. The skill bundles an orchestrator `SKILL.md` plus 15 per-dimension
  charter files in a `charters/` directory. Charters install once under the
  shared `.agents/skills/sd-audit-repo/charters/` path; all platform SKILL.md
  copies reference that canonical path.
- R3. Charter roster — always-on (12): architecture, design, correctness
  (incl. error handling/resilience), security, testing, documentation, bloat,
  performance, dependencies, tooling (CI/CD & DX), release-hygiene,
  improvements. Conditional (3, fingerprint-selected): consumer-impact,
  observability, accessibility-i18n.
- R4. Fixed pipeline, mandatory and ordered: fingerprint → dimension reviews →
  adversarial verification → synthesis/dedupe → Trellis reconciliation →
  report + ledger update.
- R5. Fixed scoring rubric defined in the skill: severity P0–P3, effort S/M/L,
  confidence Verified/Plausible, with written definitions so results are
  comparable across repos and over time.
- R6. Canonical report with mandatory sections — Verdict, Findings by
  dimension, Trellis reconciliation, Prioritized actions, Ledger delta,
  Coverage & limits — never omitted (housekeeping-report precedent). Coverage
  & limits must state what was not reviewed and why (no silent caps).
- R7. Committed ledger at `.trellis/audit/ledger.md`: stable monotonically
  assigned finding IDs (never reused), status lifecycle
  new/still-open/fixed/regressed, first-seen/last-seen date + commit,
  severity/effort/dimension/evidence per entry.
- R8. Arguments: dimension filter (e.g. `security,testing`), depth
  `quick|standard|deep`, and `follow-up` mode (re-verify open ledger items +
  regression sweep instead of a full audit).
- R9. Platform degradation: parallel read-only sub-agents on sub-agent
  dispatch platforms; sequential per-charter execution on inline platforms
  with guidance to prefer quick/filtered runs.
- R10. Sub-agents are read-only reviewers (no file modifications) and follow
  the pack's sub-agent dispatch protocol (Active task prefix when a task is
  active).
- R11. Untracked P0–P2 findings yield prd-ready Trellis task proposals
  presented for user consent; the skill never auto-creates tasks.
- R12. Documentation positions the command relative to existing surfaces: it
  complements sd-review-local-all (provider loop), sd-review-pr (PR loop), and
  sd-full-check (gate); it is the periodic formal audit.

### Constraints

- C1. Shipped-payload change: manifest version bump + matching CHANGELOG
  heading (release gate).
- C2. Byte-identical template↔installed twins for every shipped file
  (parity gate).
- C3. First multi-file skill in the pack: registry/parity tests must be
  extended to cover charter files without weakening existing coverage floors.
- C4. Instructions-only feature: no new shell/Python runtime scripts.
- C5. Ledger and report writes are the only repo mutations the skill performs;
  everything else is read-only.

## Acceptance Criteria

- [ ] A1. `install.py` on a consumer repo installs the command adapters for
  active platforms, the skill fan-out, and the charters; `install-audit`
  passes with the new targets counted.
- [ ] A2. All 15 charters exist, follow one common template (mission / scope /
  out-of-scope / method hints / severity calibration / output schema), and are
  individually consumable by a sub-agent without the orchestrator context.
- [ ] A3. Tests pin the report's mandatory section names, the rubric strings,
  and the ledger path in SKILL.md and the usage guide (format-drift
  protection).
- [ ] A4. Parity tests confirm twins for every new shipped file, including
  charters.
- [ ] A5. The installed usage guide documents command, arguments, pipeline,
  report format, ledger, and positioning.
- [ ] A6. `make full-check` green; version bumped with matching CHANGELOG
  entry.
- [ ] A7. A dogfood run on the pack repo (depth=quick) produces a well-formed
  report and initial ledger (manual verification gate before merge).

## Out of scope

- Consumer fleet rollout (separate refresh stream after release).
- Scripts/automation for ledger parsing or CI-scheduled audits.
- Changes to existing review commands.
