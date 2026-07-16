# Implementation plan: SDLC skill expansion

## Step 1 — Skill content (3 parallel trellis-implement agents)
- [ ] Agent A: sd-watch-pr + sd-fix-ci SKILL.md per design contracts.
- [ ] Agent B: sd-update-deps + sd-fleet-refresh SKILL.md.
- [ ] Agent C: sd-test-gaps + sd-retro SKILL.md.

## Step 2 — Surfaces + wiring (1 agent, after/parallel)
- [ ] Agent D: 6 neutral commands + 18 bespoke adapters (claude md, gemini
  toml, github prompt each) + ~150 manifest entries mirroring the
  sd-audit-repo per-section pattern. JSON parse + no-missing-sources check.

## Step 3 — Docs (main session)
- [ ] Guide: 6 "What is installed" bullets, Codex list, /sd: and /sd-
  lists, Commands prose block per skill.
- [ ] README: 6 ### sections; extend the heading-pin tuple.

## Step 4 — Tests (main session)
- [ ] tests/test_sdlc_commands.py (parameterized format-drift suite).
- [ ] Parity/core sibling insertions for 6 commands + adapter tuples +
  dispatch branches + gemini descriptions + codex/source name lists.

## Step 5 — Release bookkeeping + gates
- [ ] install.py --force fan-out; KB regen; bump 0.12.0 + CHANGELOG.
- [ ] make test; make full-check.

## Step 6 — Ship
- [ ] Commit (feature), PR, Copilot, watch, gated merge, v0.12.0 tag,
  journal, archive parent+children.

## Rollback points
Branch-local until merge; revert PR post-merge.
