# Delete the sd-review-pr command surface

> Child 2 of 3 under `08-09-retire-review-pr-surface`. Ordering is a
> requirement of this task, not an implication of tree position.
>
> **Blocks on `08-21-port-integration-only-profile` (child 1).** Do not start
> until child 1 is archived. Child 1 moves the fleet integration-only profile
> into `sd-review`; deleting this surface first removes the fleet
> integration-only review mechanism outright.
>
> **Independent of `08-21-retire-full-check-family` (child 3).** The full-check
> scripts are not reachable from `sd-review-pr` — `SKILL.md:295-297` forbids
> falling back to either — so neither task waits on the other for correctness.
> Child 3 is ordered after this one only to keep `RETIRED_TARGETS` edits in one
> file from colliding.

## Goal

Remove every `sd-review-pr` identifier, adapter, prompt, manifest row, receipt,
and generated mirror from every platform, flip the `review-pr-command` registry
row from schedule-only to enforcing, and empty the plugin dependency-closure
allowlist that exists only for this skill.

## Current state (verified 2026-08-21)

Eleven source-tree paths carry the surface. Note the fan-out: the 24
manifest rows below install from only **three** sources —
`templates/.agents/skills/sd-review-pr/SKILL.md`,
`templates/.commands/sd-review-pr.md`, and
`templates/.github/prompts/sd-review-pr.prompt.md` — across 14 platforms
(`.agent`, `.claude`, `.codebuddy`, `.cursor`, `.devin`, `.factory`,
`.github`, `.kilocode`, `.kiro`, `.opencode`, `.pi`, `.qoder`,
`.reasonix`, `.trae`, `.zcode`). Deleting the eleven files is not the
work; removing the rows and covering the 24 consumer-side targets in
`RETIRED_TARGETS` is. Separately, 110 non-`.trellis/` tracked files still
reference the identifier and must be swept for R1.

The source-tree paths:

| Path | Kind |
| --- | --- |
| `.opencode/commands/sd-review-pr.md` | command |
| `.github/prompts/sd-review-pr.prompt.md` | prompt |
| `.github/command-sources/sd-review-pr.md` | source |
| `templates/.commands/sd-review-pr.md` | command |
| `templates/.github/prompts/sd-review-pr.prompt.md` | prompt |
| `plugins/sd/machine-payload/.opencode/commands/sd-review-pr.md` | command |
| `.agents/skills/sd-review-pr/` | skill (1 file) |
| `.claude/skills/sd-review-pr/` | skill (1 file) |
| `plugins/sd/skills/sd-review-pr/` | skill (1 file) |
| `templates/.agents/skills/sd-review-pr/` | skill (1 file, 865 lines) |
| `plugins/sd/machine-payload/.agents/skills/sd-review-pr/` | skill (1 file) |

- `installer/registry.py:1416` holds the `review-pr-command` row; `:1449` maps
  `"sd-review-pr" -> ("sd-review", "review-pr-command")`. The same two rows
  exist in the generated `plugins/sd/installer/registry.py`.
- `installer/references.py:320` (`PLUGIN_CLOSURE_ALLOWLIST`) and `:326`
  (`MACHINE_CLOSURE_ALLOWLIST`) each hold exactly one entry pointing at
  `fleet-review-classify.py`, but under **different** keys —
  `skills/sd-review-pr/SKILL.md` for the plugin and
  `.agents/skills/sd-review-pr/SKILL.md` for the machine payload. Both must be
  removed; matching on one key path alone leaves the other behind. A parity
  assertion in `tests/test_generate_plugin.py` covers them.
- `command_installed_targets()` returns `.agents/skills/<name>/SKILL.md` and
  per-platform command paths only — no `scripts/` path — confirming R3.
- The `SD_AI_COMMAND_PACK_REVIEW_PR_*` family is 7 keys with zero executable
  readers — a skill-text contract pinned by
  `tests/test_review_scope.py:1711-1720`.

## Requirements

- R1: No `sd-review-pr` identifier, adapter, prompt, manifest row, receipt, or
  provenance entry survives on any platform.
- R2: The `review-pr-command` registry row flips from schedule-only to
  enforcing, with `identifiers` populated, `source_paths_must_be_absent=True`,
  and `removed_version` unchanged.
- R3: `RETIRED_TARGETS` gains the `sd-review-pr` command family.
  `command_installed_targets()` returns command paths only, so a registry row
  alone would leave consumer copies undeletable forever.
- R4: Both closure allowlists are empty and `generate-plugin.py --check` passes
  on a regenerated tree, with `tests/test_generate_plugin.py` asserting the
  empty set.
- R5: The `SD_AI_COMMAND_PACK_REVIEW_PR_*` family (7 keys) and its pinning
  assertions in `tests/test_review_scope.py` are removed together.
- R6: A live-surface drift lint with a minimal, individually justified
  allowlist confirms the absence.

## Acceptance Criteria

- [ ] Fresh installs and help/catalog discovery expose no `sd-review-pr`
      identifier on any supported platform.
- [ ] Upgrade from the prior release removes every unchanged vouched
      `sd-review-pr` target; a locally modified copy is preserved and reported;
      the new receipt contains neither.
- [ ] `review-pr-command` is enforcing with `identifiers` populated and
      `source_paths_must_be_absent=True`.
- [ ] Both closure allowlists are empty; `generate-plugin.py --check` passes;
      `tests/test_generate_plugin.py` asserts the empty set.
- [ ] No `SD_AI_COMMAND_PACK_REVIEW_PR_*` key survives in any tree.
- [ ] Command-surface drift lint is green, every allowance carrying a reason
      naming why the reference is historical.
- [ ] `make check` is green.

## Dependencies

- **Blocks on child 1** (`08-21-port-integration-only-profile`) — must be
  archived first.
- **Subsumes `08-09-review-pr-fleet-classifier-ref`.** That task's entire
  subject is the closure-allowlist entry removed by R4. Close it as
  resolved-by-removal in this task's deletion commit; do not implement it
  separately.

## Out Of Scope

- Backward-compatible aliases, deprecation windows, or forwarding scripts.
  Rollback is installing the last pre-cut release.
- Any full-check script, `Makefile`, or CI gate change — child 3 owns those.
