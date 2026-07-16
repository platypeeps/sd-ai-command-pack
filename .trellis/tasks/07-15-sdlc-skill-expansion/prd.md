# SDLC skill expansion: six new distributed commands (0.12.0)

## Problem

The pack covers the middle of the delivery lifecycle (plan, implement,
review, gate, merge, cleanup) but leaves recurring edge chores manual:
watching a PR settle, triaging red CI, batching dependency PRs, rolling
the pack across the consumer fleet, closing coverage gaps, and capturing
debug retrospectives. Each was performed by hand repeatedly in the
2026-07-15 session (five hand-rolled PR/tag watchers; four manually
triaged dependabot PRs; a pending 0.10.5+0.11.0 fleet rollout).

## Goal

Ship six new distributed commands in one release (0.12.0), following the
established per-command pattern (shared skill + neutral command + bespoke
Claude/Gemini/GitHub adapters + manifest wiring + format tests + docs):
sd-watch-pr, sd-fix-ci, sd-update-deps, sd-fleet-refresh, sd-test-gaps,
sd-retro.

## Requirements

- R1. Each command ships the full adapter surface that sd-audit-repo
  shipped (minus charters): ~25 manifest entries per command.
- R2. Every skill defines mandatory final-report sections (housekeeping
  precedent) and follows the scannable-format rules (bullets, no blobs).
- R3. Zero new environment variables: tuning is via command arguments, so
  the env-var documentation gate surface does not grow.
- R4. No new runtime scripts: skills orchestrate existing shipped scripts
  (housekeeping, fleet-preflight, full-check) and gh/git.
- R5. Merge-affecting behavior is delegated to the existing housekeeping
  gate semantics — no skill introduces a second merge path with weaker
  criteria.
- R6. Per-skill contracts are defined in design.md and pinned by tests.
- R7. Docs: usage-guide Commands prose + command lists, README sections,
  Codex name list — all six commands.
- R8. Single release: manifest 0.11.0 -> 0.12.0 with one CHANGELOG entry.

## Acceptance Criteria

- [ ] A1. install.py installs all six commands' adapters + skills;
  install-audit passes with the grown target count.
- [ ] A2. Format tests pin each skill's mandatory sections, arguments, and
  safety rules; parity/core tests cover the six fan-outs.
- [ ] A3. Guide + README document all six with argument tables and
  positioning; command lists updated everywhere.
- [ ] A4. make test and make full-check green; 0.12.0 + CHANGELOG.
- [ ] A5. Each child task's acceptance criteria met (child PRDs).

## Out of scope

- Fleet rollout execution (sd-fleet-refresh ships the capability; running
  it is a separate stream).
- New scripts, env vars, or CI jobs.
