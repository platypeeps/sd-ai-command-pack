# Implementation plan: sd-audit-repo

Ordered checklist. Validation commands use the repo venv
(`.venv/bin/python`) and `make` targets. Rollback point: every step lands on
the task branch only; full rollback = delete branch.

## Step 0 — Wiring research (read-only)

- [ ] Study the commit that added sd-work-designs (0.8.0) to enumerate every
  file a new command touches: `git log --oneline --diff-filter=A -- 'templates/.commands/sd-work-designs.md'`
  then `git show --stat <sha>`.
- [ ] Confirm whether manifest.json command entries are hand-authored or
  generated from installer/registry.py; identify any registry constant that
  lists command names (e.g., for parity tests).
- [ ] Confirm shared-platform (`.agents/`) is installed unconditionally
  (registry semantics for `platform: shared, install: always`). If not,
  switch charters to full fan-out (design fallback) before proceeding.

## Step 1 — Skill + charters

- [ ] Write `templates/.agents/skills/sd-audit-repo/SKILL.md` per design
  contract (mandatory sections, pipeline, rubric, report + ledger formats,
  dispatch, safety rules).
- [ ] Write the 15 charters from the common skeleton; each self-contained;
  `improvements.md` carries the evidence-citation requirement; the 3
  conditional charters state their fingerprint trigger.
- [ ] Cross-check: Out-of-scope sections mutually consistent (no dimension
  gaps or double-ownership).

## Step 2 — Command surfaces

- [ ] `templates/.commands/sd-audit-repo.md` (neutral body: resolve skill,
  verify charters dir exists, run per skill, blocker reporting — match the
  established neutral-command voice).
- [ ] Bespoke adapters: `templates/.claude/commands/sd/audit-repo.md`,
  `templates/.gemini/commands/sd/audit-repo.toml`,
  `templates/.github/prompts/sd-audit-repo.prompt.md` (mirror sibling
  command adapters).
- [ ] Manifest entries (~25 command/skill/prompt/workflow + 15 shared charter
  entries), matching sd-work-designs' shape.

## Step 3 — Docs

- [ ] Usage-guide section in `templates/docs/SD_AI_COMMAND_PACK.md`: command,
  arguments, pipeline summary, report skeleton, ledger path + rules,
  positioning vs sd-review-* and sd-full-check.
- [ ] README command list mention if the README enumerates commands
  (verify; README was slimmed in 0.10.2 — likely guide-only).

## Step 4 — Tests

- [ ] `tests/test_audit_repo.py`: mandatory report sections, rubric strings,
  ledger path, charter roster ↔ files completeness, charter skeleton
  headings, argument names; guide-section sync assertions.
- [ ] Extend registry/parity tests for the new command fan-out + multi-file
  skill (charter parity template↔installed).
- [ ] Run: `PYTHONPATH="$PWD:$PWD/tests" .venv/bin/python -m unittest tests.test_audit_repo tests.test_generated_parity tests.test_install_core -v`

## Step 5 — Fan-out + release bookkeeping

- [ ] `python3 install.py . --force` (dogfood twins); verify
  `git status --porcelain` shows only expected paths.
- [ ] Bump manifest.json + snapshot to 0.11.0; CHANGELOG heading.
- [ ] Regenerate Obsidian KB if the freshness lane trips:
  `.venv/bin/python scripts/sd-ai-command-pack-update-spec-kb.py`.

## Step 6 — Gates

- [ ] `make test` (coverage floors hold).
- [ ] `make full-check` green (release gate sees 0.11.0 + CHANGELOG).

## Step 7 — Dogfood validation (manual gate, pre-merge)

- [ ] Run `/sd:audit-repo` with `depth=quick` on this repo; confirm the
  report contains every mandatory section and `.trellis/audit/ledger.md` is
  created well-formed. Commit the initial ledger with the task branch.
- [ ] Fix any instruction ambiguities the dogfood run exposes; re-run gates.

## Step 8 — Ship

- [ ] Commit on task branch, push, PR (scope: Automation/skill payload +
  tests + docs + release bookkeeping), Copilot review, gated housekeeping
  merge, confirm v0.11.0 auto-tag.

## Review gates

- After Step 1: charter roster + SKILL.md read-through (self-review against
  design contract) before wiring surfaces.
- After Step 7: user sees the dogfood report before merge (A7).

## Rollback points

- Steps 0–7 are branch-local; abandon branch to roll back.
- Post-merge: revert PR; consumer ledgers (none yet — pre-rollout) unaffected.
