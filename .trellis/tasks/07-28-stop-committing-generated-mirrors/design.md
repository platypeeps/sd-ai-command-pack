# Design — stop committing the generated installed mirrors

## Scope boundary

`.gitignore`, CI workflow, and the four parity/drift modules. `templates/` stays
authoritative and untouched. Consumer install behavior must not change.

## Confirmed measurements

```
manifest.json  vs  .sd-ai-command-pack/manifest.json   IDENTICAL, 163,553 bytes
```

Tracked mirror files by root: `.github` 113, `.agents` 99, `.opencode` 77,
`.claude` 77, `.gemini` 31, `.sd-ai-command-pack` 2.

Machinery actually measured — **173,615 bytes, not the ~210 KB the PRD states**:

| file | bytes |
|---|---|
| `tests/test_generated_parity.py` | 94,825 |
| `tests/test_pack_drift.py` | 25,841 |
| `scripts/sd-ai-command-pack-surface-check.py` | 29,730 |
| `.github/scripts/check-command-surface-drift.py` | 23,219 |

The regeneration path exists (`Makefile:31`):

```make
sync:
	"$(VENV_PYTHON)" install.py . --force
	"$(VENV_PYTHON)" scripts/sd-ai-command-pack-update-spec-kb.py
```

## The consequence the finding does not name

**The mirrors are not dead duplicates — they are this repo's own dogfood
install.** `.claude/`, `.agents/`, `.gemini/`, `.opencode/` in the dev tree are
the live agent surface that this repository uses to operate on itself. Gitignoring
them means a fresh clone has no skills, no commands, and no agent context until
someone runs `install.py`.

That lands on: every new contributor, every CI job that assumes the surface
exists, and every agent session opened against a clean checkout. It is not a
blocker, but it converts a zero-step setup into a one-step setup, and that step
must be discovered — the failure mode is an agent silently operating with no pack
skills rather than an error.

Mitigation options, in preference order:

- **A — bootstrap in CI and document the local step.** Add `install.py . --force`
  as an early CI step; add it to the contributor quickstart. Cheap, obvious.
- **B — keep `.claude/` and `.agents/` tracked, ignore the rest.** Preserves
  zero-step agent operation, still removes the bulk. Concedes the duplication
  argument for the two largest agent surfaces.
- **C — ignore everything, no bootstrap.** Rejected: silent degradation.

## Hard interaction with `07-28-regenerate-fleet-refresh-adapters`

The four source-only fleet-refresh adapters live in the dev tree and have **no
manifest entry** — `generate-command-surfaces.py:881` excludes source-only
commands from `derived`, and `installer/removal.py:272-275` skips them in source
checkouts. Therefore `install.py . --force` does **not** regenerate them.

Gitignoring the mirror roots would delete the only copy of:

- `.claude/commands/sd/fleet-refresh.md`
- `.gemini/commands/sd/fleet-refresh.toml`
- `.github/prompts/sd-fleet-refresh.prompt.md`
- `.opencode/commands/sd-fleet-refresh.md`

**Sequencing constraint: land `07-28-regenerate-fleet-refresh-adapters` first.**
Once the generator emits source-only adapters into the dev tree, regeneration
covers them and this task is safe. Before that, this task destroys them.

## Staged scope

The PRD offers a reduced scope, and it is the right first step:

1. **Stage 1 — drop the duplicate `.sd-ai-command-pack/manifest.json`.** 163,553
   bytes, byte-identical, no agent surface involved, no bootstrap question. Land
   alone and verify consumer installs are unaffected.
2. **Stage 2 — mirrors, with the chosen bootstrap option.**
3. **Stage 3 — retire or collapse the machinery** once the parity suites have
   been reframed as "regeneration is clean" checks rather than byte comparisons
   of committed duplicates.

Do not collapse the machinery before stage 2 has run green for a release cycle —
those suites are the only thing currently proving the mirrors match.

## Compatibility

Consumers must be unaffected: mirrors must still exist in a consumer checkout
after `install.py`. This is testable directly and is the single most important
check in the task. Coordinate with A-058 (orphan manifest targets) before dropping
any manifest entry — an orphaned target is a hard consumer-audit failure.

## Rollback

Stage 1 and stage 2 are each a plain revert plus `git add` of the restored files.
Stage 3 is not cheaply reversible — deleted test modules are the safety net for
stages 1 and 2, so it goes last and only after evidence.
