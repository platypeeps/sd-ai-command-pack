# Design: command infrastructure streamline

## 1. Surface generation

Source of truth: a `COMMAND_NAMES` tuple (name → short form) in
installer/registry.py next to PLATFORM_REGISTRY (dev-side authority, not
shipped). Generator: .github/scripts/generate-command-surfaces.py, invoked
by `make generate`.

Inputs per command: templates/.commands/sd-<name>.md (neutral, hand-authored)
+ registry patterns. Outputs (committed, regenerated in place):
- templates/.claude/commands/sd/<short>.md — neutral body minus frontmatter,
  with the alias-rewrite rules moved from the parity test's
  CLAUDE_COMMAND_ALIAS_REWRITES into generator config.
- templates/.gemini/commands/sd/<short>.toml — description = neutral
  frontmatter description; prompt block = body minus the SD-preamble line.
- templates/.github/prompts/sd-<name>.prompt.md — commented YAML frontmatter
  + description + mode: agent + full body.
- manifest.json — regenerated as: static base entries (scripts, configs,
  docs, gitignore blocks, charters, non-command skills) preserved from a
  base section, plus derived per-command entries (skill fan-out + command/
  prompt/workflow targets) expanded from COMMAND_NAMES × registry
  command_target_pattern/kind data. One-time canonical ordering accepted.

Overrides: OVERRIDE_BODIES set (the current BESPOKE_BODY_PARITY_EXEMPTIONS
files, e.g. the Claude start/continue/finish-work variants) — the generator
leaves them untouched and the parity tests keep their exemption pins.

Drift gate: tests/test_surface_generation.py runs the generator in check
mode (--check: regenerate to temp, byte-compare, list drifted paths) so CI
fails when a generated file is hand-edited or the list/manifest desyncs.
Full-check picks this up via make test; no new full-check lane.

## 2. review-local merge

- templates/.agents/skills/sd-review-local/SKILL.md gains the `all`
  argument: same provider fix loop with
  `bash scripts/sd-ai-command-pack-review-local.sh --full-codebase`,
  absorbing sd-review-local-all's skill content (retry/exclusion notes).
- Delete sd-review-local-all: skill, neutral body, generated adapters,
  COMMAND_NAMES entry (manifest entries disappear via generation).
- Consumer migration: add the removed installed target paths to the
  installer's legacy-removal mechanism (installer/removal.py's recognized
  removal targets — investigate exact structure during implementation) so
  a refresh deletes orphans; add a removal test (install old layout into a
  temp repo, refresh, assert files gone and audit clean).
- Docs: guide/README sections merged into sd-review-local (documenting
  `all`); command lists drop the -all entries; CHANGELOG states the removal
  and the replacement invocation.
- Tests: parity/core lists drop -all sibling lines; sdlc/format pins update;
  review-local skill test pins `all`.

## 3. sd-ship

New command (via the generator): skill + neutral only.
- Sections per house pattern (When to use · Arguments · Workflow · Safety
  rules · Final report).
- Arguments: `until=pr|review|merge` (default merge); pass-through args
  forwarded verbatim to stages (e.g. `timeout-minutes=` to watch).
- Workflow: preconditions (feature branch; changes exist or PR already
  open) → stage 1 sd-create-pr flow → stop if until=pr → stage 2
  sd-review-pr loop → stop if until=review → stage 3 sd-watch-pr →
  stage 4 housekeeping gate merge. Each stage's own preconditions, gates,
  and reports remain authoritative; sd-ship only sequences and reports.
- Safety: no new gate logic (pin "adds no new gate logic; every stage's own
  gates remain authoritative"); a failed stage stops the chain with that
  stage's report; never bypasses or weakens any stage behavior.
- Final report: stage table (stage · outcome), stop-point, PR/merge state,
  next step.

## Sequencing

Phase A generator (byte-reproduction proven against current tree, minus
the accepted manifest reorder) → Phase B review-local merge (list edit +
skill merge + removal wiring) → Phase C sd-ship (list entry + skill +
neutral) → docs/tests/bump/gates/PR.

## Tradeoffs decided

- Generator is dev-side (.github/scripts/), not shipped payload — consumers
  never run it; committed outputs remain the contract.
- One-time manifest reorder accepted over slavishly reproducing historical
  insertion order; semantic tests are the protection.
- sd-review-local-all removed outright (no alias shim) — single-org fleet,
  changelog-communicated, refresh cleans orphans.
