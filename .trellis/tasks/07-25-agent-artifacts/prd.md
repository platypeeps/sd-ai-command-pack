# Ship SD commands as cross-platform sub-agents

Status: ACCEPTED as parent task (user, 2026-07-25). Requirements R1-R7 are binding.
Delivery is decomposed into child tasks (see Task map); the parent owns the source
requirement set, cross-child acceptance criteria, and final integration review. The parent
has no direct implementation work and must not be started; start children instead.

## Goal

Let SD commands delegate bounded units of work (per audit charter, per failing CI job, per
coverage-gap file, per dependency-PR classification, per fleet repo) to sub-agents on
platforms that support them, and ship the agent definitions through the existing SD
installer - preserving the one-body-fans-to-17-platforms invariant and the checkout-trust
model.

## Requirements

- R1 (cross-platform, settled): The design MUST incorporate the findings and recommendation
  in `research/cross-platform-agent-support.md`: canonical agents authored once as neutral
  MD + frontmatter; per-platform renderers; capability-gated so only supporting platforms
  (~10 of 17) receive agent artifacts.
- R2 (no new layer): Agent shipping extends registry -> generator -> manifest -> installer
  (new manifest kind `agent`, new `PlatformInfo` capability field modeled on
  `structured_question_tool`); no separate install mechanism.
- R3 (graceful degradation): Every dispatching command keeps the capability-first inline
  fallback (sd-audit-repo pattern) so non-dispatch platforms produce the same outcome
  sequentially.
- R4 (trust model): Sub-agents inherit the checkout-trust preflight classification; dispatch
  prompts restate it; structured answers cannot override safety gates.
- R5 (deliberate serializations preserved): sd-update-deps merges, sd-work-backlog task
  loop, and sd-housekeeping final-state collection remain sequential by design.
- R6 (enforced restriction where it pays): First named agents are read-only/limited roles
  (audit reviewer, audit refuter, CI triager), not general-purpose workers.
- R7 (pilot scope): Wave 1 limits dispatch protocols to a pilot set (proposed: sd-audit-repo
  formalization, sd-fix-ci per-job triage) before broader rollout.

## Acceptance Criteria

- [ ] Manifest schema accepts kind `agent`; installer round-trip (install, status, check,
      remove, provenance) works for agent rows; unsupported platforms receive none and
      gitignore-tuple invariants still pass.
- [ ] Generator renders canonical agent sources per platform; byte-stability and
      partition-regenerate checks cover them.
- [ ] Pilot commands carry dispatch sections with inline fallback and trust restatement.
- [ ] Cursor duplicate-discovery wrinkle addressed (naming or exclusion decision recorded).
- [ ] Copilot 30k body cap respected (charters referenced at runtime, not inlined).
- [ ] Tests cover the new kind, capability gating, and renderer outputs; sd-check contract
      updated if affected.

## Task map (parent-owned)

Recommended order below; dependencies are restated inside each child's `prd.md` (tree
position is not a dependency system).

1. `07-25-fix-ci-dispatch` (Tier 1 pilot) - per-job triage dispatch in sd-fix-ci.
   No dependencies; do first.
2. `07-25-dispatch-rollout` (Tier 1) - sd-test-gaps per-file, sd-update-deps
   classification-only, sd-fleet-refresh per-repo waves. Blocked by 1.
3. `07-25-agent-artifact-kind` (Tier 2) - manifest kind `agent`, PlatformInfo capability
   gate, per-platform renderers, wrinkle dispositions. Blocks 4.
4. `07-25-worker-agents` (Tier 2) - sd-audit-reviewer, sd-audit-refuter, sd-ci-triager.
   Blocked by 3; aligns with 1.

Cross-child acceptance (parent integration review, run when all children archive):

- [ ] `make generate` byte-stable and full sd-check green with all child changes merged.
- [ ] One sd-audit-repo run using named agents on a dispatch platform and one inline run
      produce contract-identical ledgers (execution strategy differs, outcome does not).
- [ ] Fleet consumers unaffected until the version rollout that ships agents.

## Open questions (delegated)

- Wave-1 platform set and install scope (incl. Codex trust gate) ->
  `07-25-agent-artifact-kind`.
- Fleet worker agents -> RESOLVED (2026-07-25): sd-fleet-refresh gets Tier 1 dispatch
  prose only; the controller stays deterministic and no fleet named agent ships in wave 1.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Complex task: `design.md` and `implement.md` required before `task.py start`.

## Cross-program coordination (2026-07-25 review; additive — does not alter R1-R7)

- Twin-pack consistency: before the parent integration review closes, compare with
  se-ai-command-pack `.trellis/tasks/07-25-agent-artifacts/` for drift in the shared
  settled design (renderer sets and platform gating intentionally differ; the canonical
  source format and governance must not).
- Registry consumer: see `07-25-agent-artifact-kind`'s coordination note (SE skill_review
  AST-parse, snapshot-first sequencing).
- Clarification for cross-child acceptance: "contract-identical ledgers/reports" means
  identical section structure, field vocabulary, and evidence rules — not identical
  content.
