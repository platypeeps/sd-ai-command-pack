# Enforce Untrusted Checkout Preflight Implementation Plan

## Execution Order

1. Extend `CommandInfo` with conservative capability fields, classify the
   current command set, and add validation for contradictory metadata.
2. Relocate hand-authored neutral bodies to `.github/command-sources/` and make
   `templates/.commands/` a generated guarded payload.
3. Replace the GitHub-only four-command allowlist with one capability-driven
   trust block inserted before skill resolution for every execution-capable
   command and all generated adapter formats.
4. Update manifest generation and drift tests so every neutral platform uses
   guarded generated sources and no platform can opt out locally.
5. Add behavioral tests for conservative defaults, exemption constraints,
   adapter completeness, pre-execution ordering, stable reason codes, and
   untrusted/indeterminate stop behavior.
6. Update the release ledger and installed documentation, run generation and
   dogfood sync, then refresh exact-payload fleet candidate evidence.

## Validation Plan

- Focused: `python3 -m unittest tests.test_help_command tests.test_generated_parity tests.test_pack_drift`.
- Generation: `make generate` followed by `make sync` and generator `--check`.
- Installer: source install audit and affected installer/parity tests.
- Release: full disposable fleet candidate validation after payload bytes are
  final.
- Broad: `make check` and `git diff --check`.

## Documentation And Spec Updates

- Document capability-driven checkout trust and the fail-closed reason codes
  in the installed guide.
- Update adapter and manifest specs for the authored-source/generated-neutral
  boundary.
- Bump the pack minor version because every execution-capable installed command
  gains a required preflight, and add the matching changelog entry.

## Review Notes

- Verify no checkout-owned helper runs before the trust decision.
- Verify `sd-help` is the only initial exemption and remains strictly
  non-executing.
- Verify a missing GitHub API result is `indeterminate`, not trusted local.
- Verify generated neutral, Claude, Gemini, GitHub, and installed dogfood
  copies all contain the same gate before skill resolution.

## Rollback Points

- Capability metadata and generator changes can be reverted before release
  generation without consumer impact.
- After release generation, roll back the whole pack version; do not restore
  the partial GitHub allowlist alongside the new metadata.

## Follow-Ups

- Sandboxing third-party provider execution remains outside this task.
- Any host that cannot preserve pre-skill guard ordering must be reported as
  unsupported and fail closed rather than receiving a platform-specific
  exemption.

## Completion Evidence

- `make generate` and generator `--check` produced 89 matching guarded
  surfaces; the hand-authored Claude start override passed the same marker and
  pre-step ordering validation.
- Focused registry, generation, parity, drift, and installer coverage passed
  201 tests, including conservative defaults, fail-closed source/anchor
  validation, every command capability, every generated adapter format, all
  trust reason codes, and the no-checkout-execution-before-resolution order.
- The disposable fleet candidate gate passed all eight configured consumers
  for exact payload version `0.34.0` and refreshed
  `docs/fleet/candidate-validation.json`.
- `make check` passed with 100% installer-package coverage, Ruff, mypy, zizmor,
  install audit, generated/dogfood parity, release and candidate ledgers,
  Obsidian KB freshness, and the full pack gate.
- Review preflight's path/filesystem advisory is covered by generator failures
  for missing/duplicate anchors and authored trust markers, fixed in-repository
  source paths, manifest-source drift gates, and installer path-boundary tests.
  The large authored-file count is generated adapter fanout from one canonical
  policy and one source body per command, verified by parity tests.
