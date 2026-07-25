# Add agent kind and subagent capability gate to installer

Parent: `.trellis/tasks/07-25-agent-artifacts` (Tier 2 plumbing). Settled inputs: parent
`design.md` section 1 and `research/cross-platform-agent-support.md` (binding, incl. the
17-platform support matrix).

## Goal

Make `agent` a first-class SD artifact kind gated by a per-platform capability flag:
canonical neutral MD agent sources in `templates/`, rendered per platform (MD dialects,
Codex TOML, Kiro JSON), fanned through the manifest, and installed only where the platform
natively supports agent files (~10 of 17).

## Requirements

- R1: `PlatformInfo` gains a subagent-support capability field (modeled on the existing
  `structured_question_tool` gate) with values covering: MD-dialect native file, TOML
  (codex), JSON (kiro), none (devin, trae, qoder, zcode, pi, reasonix, shared).
- R2: Manifest schema gains kind `agent`; rows carry existing provenance/removal/drift
  semantics; gitignore-tuple and byte-stability invariants extended; platforms with
  capability `none` get zero agent rows (test-asserted).
- R3: Generator renders canonical agents per platform; bounded insertion mechanisms are
  generalized per-capability rather than per-platform-name where feasible.
- R4: Wrinkle dispositions recorded and implemented:
  - Cursor auto-loads `.claude/agents/` and `.codex/agents/`: agent names are
    collision-safe (`sd-` prefix) and the design records whether cursor gets its own rows.
  - Copilot `.agent.md` 30,000-char body cap: charters are runtime-read, never inlined.
  - Gemini subagents run without per-tool confirmation: tools scoped tightly in that
    renderer.
  - Codex project-scope agents require project trust: documented in install/status output.
- R5: `sd-check` typed contract and `--audit`/`--status` inspection account for agent rows.
- R6: Wave-1 platform set decided in design (claude+codex pilot vs all supporters) and
  recorded; adding later platforms must be additive registry rows.

## Acceptance Criteria

- [ ] Installer round-trip (install, status, check, audit, remove) works for agent rows;
      capability-`none` platforms receive none; invariant tests pass.
- [ ] Renderer outputs validated per dialect; partition-regenerate and byte-stability
      checks cover agents.
- [ ] Wrinkle dispositions (R4) each have a recorded decision + test where applicable.
- [ ] Version bump + changelog; maintainer docs updated.

## Dependencies / order

- Independent of Tier 1 tasks. BLOCKS 07-25-worker-agents.

## Notes

- Complex task: needs `design.md` + `implement.md` before start.

## Cross-program coordination (2026-07-25 review)

- Registry contract consumer: the SE pack's shipped `skill_review.py` AST-parses
  `installer/registry.py` structures of BOTH pack checkouts (SE audit ledger A-002).
  Reshaping this repo's registry (new `agent` kind, subagent-capability field) changes
  what installed copies parse. Coordinate with se-ai-command-pack
  `07-25-audit-registry-snapshot-contract` (versioned registry snapshot) — land it first
  or in the same rollout window, and bump the snapshot schema with the new shapes.
