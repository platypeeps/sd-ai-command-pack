# Implement — Decouple sd:fleet-refresh command from installed-skill resolution

> Reworked 2026-08-03 for the expanded scope (generator anchor change +
> mandatory version bump). Supersedes the one-file plan.

## Preconditions

- Branch off `main` (e.g. `feat/decouple-fleet-refresh-command`).
- Capture pre-edit hashes of prd/design/implement for the planning
  adversarial-review contract before `task.py start`.

## Ordered steps

1. **Generator — per-command injection anchor**
   (`.github/scripts/generate-command-surfaces.py` +
   `installer/registry.py`):
   - Add `injection_anchor: <compiled-regex> | None = None` to `CommandInfo`
     (`registry.py` L723 block).
   - In the checkout-trust injection function (generator L534-568), resolve the
     anchor as `command.injection_anchor or SKILL_RESOLUTION_ANCHOR`; keep the
     exactly-one-match guard and the insert-before-anchor behavior.
   - Define a fleet-refresh anchor regex matching the reworded step 1
     (`^1\. Load the fleet-refresh procedure by reading ` + backtick + `[^` +
     backtick + `]+` + backtick) and set it on the `sd-fleet-refresh`
     `COMMAND_REGISTRY` row (L831 area).
   - If `validate_command_registry` needs to accept the new field, extend it
     minimally.

2. **Command body** — edit **`.github/command-sources/sd-fleet-refresh.md`**
   (NOT `templates/.commands/…`, which is generated):
   - Reword line 7 self-reference (no installed-skill-resolver claim).
   - Rewrite step 1 to read `.agents/skills/sd-fleet-refresh/SKILL.md` from the
     pack checkout; note the skill is source-only / not resolvable by name. The
     wording must match the fleet-refresh anchor from step 1.
   - Rewrite step 2 stop-and-report, re-anchored to the file.
   - Rewrite step 3 to "use that file's contents"; steps 4-6 verbatim.

3. **Regenerate**: `make generate` then `make sync`; then the inline
   surface-check. Confirm the four generated fleet-refresh adapters
   (`templates/.commands/…`, `templates/.claude/…`, `templates/.gemini/…toml`,
   `templates/.github/prompts/…`) regenerated with the checkout-trust block
   still injected before step 1 (`.opencode`/`.cursor` are neutral-adapter
   routings, not generated templates), and that the **other 21** commands'
   surfaces are unchanged (`git diff --name-only` lists only fleet-refresh
   adapters + the generator/registry files).

4. **Version + release evidence (mandatory — C-3)**:
   - Bump `manifest.json` `version` 0.64.1 → **0.64.2**.
   - Add the top `CHANGELOG.md` 0.64.2 heading + entry.
   - `make sync` refreshes provenance + `.sd-ai-command-pack/manifest.json`.
   - Regenerate `docs/fleet/candidate-validation.json` via
     `python3 scripts/sd-ai-command-pack-fleet-candidate-check.py`.

5. **Verify guardrails**:
   - The regenerated fleet-refresh adapters contain the full checkout-trust
     policy block (grep the `Checkout trust policy — complete before step 1:`
     marker), byte-identical to the block on the other commands.
   - `sd-fleet-refresh` still absent from `manifest.json` and `.claude/skills/`;
     still in `SOURCE_ONLY_COMMAND_NAMES`. `Skill("sd-fleet-refresh")` still
     errors `Unknown skill`.

6. **Tests + full gate**:
   - Add/adjust a `test_surface_generation.py` case asserting the fleet-refresh
     injection works under the custom anchor (policy present, correct position,
     exactly-one-anchor honored). Confirm `test_generated_parity.py`,
     `test_command_surface_drift.py`, `test_pack_drift.py`, `test_surface_closure.py`
     stay green after regeneration.
   - `make release-prep` (prepare-release version+changelog gate + `make check`)
     exits 0.

## Validation commands

- `make generate && make sync` — regenerate, no drift.
- `git diff --name-only` — only: `.github/command-sources/sd-fleet-refresh.md`,
  the generator + registry, the 4 generated fleet-refresh `templates/**`
  adapters, `manifest.json`, `CHANGELOG.md`, regenerated
  `.sd-ai-command-pack/manifest.json` + `docs/fleet/candidate-validation.json`
  (+ any version-bearing surface like command-catalog.md), and the added test.
- `grep -rn "Resolve .sd-fleet-refresh. skill by name" .github/command-sources templates`
  → 0 hits (old instruction gone from source + generated adapters).
- `grep -c "Checkout trust policy — complete before step 1:" templates/.commands/sd-fleet-refresh.md`
  → 1 (policy still injected).
- `python3 -c 'import json; d=json.load(open("manifest.json")); print(sum("fleet-refresh" in str(f) for f in d["files"]))'`
  → 0 (still source-only).
- `make release-prep` → exit 0.

## Review gates

- Planning adversarial review already run this planning batch (host + Codex);
  rerun if these artifacts change again before `task.py start`.
- Copilot review on the PR; converge before merge.

## Rollback points

- After step 1-2 (pre-regen): revert the generator/registry + neutral source.
- After merge: single feature-branch revert + regenerate.

## Manual acceptance (not unit-testable)

- AC1: dry-run walkthrough from the pack checkout reaches the procedure via the
  file read (no `Unknown skill`).
- AC4: in a scratch copy with `.agents/skills/sd-fleet-refresh/SKILL.md`
  removed, the command halts at step 2 with a file-not-found blocker.
- AC6 (corrected): assert non-installation — neither command nor skill appears
  in `manifest.json` / a consumer install; there is no consumer-side run path.
