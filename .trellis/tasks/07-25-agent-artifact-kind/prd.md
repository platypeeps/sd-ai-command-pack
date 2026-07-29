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

- Complex task. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **The 17-platform support matrix is not settled — three sources contradict each other on
  11 of 17 platforms.** Verified 2026-07-28:

  | source | supporters |
  |---|---|
  | parent `design.md` §1.2 | claude, gemini, github, opencode, cursor, kiro, droid, codebuddy, antigravity, codex (TOML) |
  | registry `trellis_local_only` agent globs | claude, codebuddy, codex, cursor, gemini, kiro, pi, qoder, trae, zcode |
  | files on disk in this checkout | claude, codex, gemini, opencode, github |

  R1 lists `none (devin, trae, qoder, zcode, pi, reasonix, shared)` while the registry
  reserves agent paths for trae, qoder, zcode, and pi (`installer/registry.py:405`, `:357`,
  `:431`, `:331`); the parent design lists github/opencode/droid/antigravity as supporters
  while none has a registry agent glob — yet `.github/agents/` and `.opencode/agents/` each
  hold three real files. Only **claude, codex, gemini** appear in all three columns, which
  is what the design adopts as wave 1 (R6). The registry column is a Trellis-side path
  reservation, not a capability claim.
- **The registry field should be modeled on `command_kind` + `command_target_pattern`
  (`registry.py:25-26`), not on `structured_question_tool` as R1 states.** The latter is a
  runtime tool name set on 2 of 18 rows carrying no target path, so a second field would be
  needed anyway; the former already expresses dialect + target and already gates on None in
  both consumers (`registry.py:448`, `.github/scripts/generate-command-surfaces.py:713`).
- **R2's manifest work is smaller than it reads, and its gitignore clause is a non-event.**
  Kind branching exists at exactly two sites in `installer/` — the validation gate
  (`manifest.py:113`) and a `MANAGED_BLOCK_KIND` special case (`provenance.py:101`) — so
  install/status/remove/audit/check are kind-agnostic. But the kind is hardcoded in **three**
  places, one a byte-identical shipped mirror: `installer/manifest.py:31`,
  `scripts/sd-ai-command-pack-surface-check.py:253`, and
  `templates/scripts/sd-ai-command-pack-surface-check.py:253`. Separately, the
  gitignore/local-only order-tuple invariant (`tests/test_install_core.py:2016-2027`) only
  fires for platforms carrying `local_gitignore_patterns` or `trellis_local_only`; a
  capability field touches neither, and agent paths must **not** be added to
  `trellis_local_only` (every entry must appear verbatim in `review-scope.sh`,
  `tests/test_install_core.py:2111`) or pack agents stop being pack-managed.
- **R4's `sd-` prefix is mechanical, not cosmetic.** Every platform's Trellis agent glob is
  name-scoped (`.claude/agents/trellis-*.md`, `.codex/agents/trellis-*.toml`). A pack agent
  named `trellis-*` enters the Trellis-local carve-out and survives removal. The generator
  should reject non-`sd-` names. R4 also omits a wrinkle: **zcode has two agent
  directories** (`registry.py:431-432`), which a single target-pattern string cannot express.
- **R5 rests on a name collision.** `sd-check`'s `kind` is `builtin | prerequisite | check`
  (`scripts/sd-ai-command-pack-check.py:880`, `:1004`, `:1022`) — the check-*result* kind,
  unrelated to `KNOWN_MANIFEST_KINDS`. There is no typed artifact-kind contract in sd-check
  to extend; R5 is satisfied by confirming `--audit`/`--status` enumerate rows generically.
- **`SKILL_FANOUT_PLATFORMS` (`registry.py:456`) is not a capability list** and must not be
  reused as one — it is the skills-only complement of the bespoke-adapter set and contains
  none of claude/codex/gemini.
- Shipping with zero agent sources and zero rows is a valid end state; the capability gate
  is testable before any agent exists. Commits 1 and 2 are inert by construction.

## Cross-program coordination (2026-07-25 review)

- Registry contract consumer: the SE pack's shipped `skill_review.py` AST-parses
  `installer/registry.py` structures of BOTH pack checkouts (SE audit ledger A-002).
  Reshaping this repo's registry (new `agent` kind, subagent-capability field) changes
  what installed copies parse. Coordinate with se-ai-command-pack
  `07-25-audit-registry-snapshot-contract` (versioned registry snapshot) — land it first
  or in the same rollout window, and bump the snapshot schema with the new shapes.
