# Add KB freshness verification to local gates

## Goal

Add a full-check or spec-update verification path that detects stale generated Obsidian KB output before review or release.

## Problem

The architectural review found that `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh` passed while `python3 scripts/sd-ai-command-pack-update-spec-kb.py --check` failed because generated KB content was stale.

That means the normal expensive local readiness gate can miss a stale or incorrectly generated `.obsidian-kb` package.

## Requirements

- Decide where KB freshness belongs in the pack verification flow:
  - default `sd-full-check`,
  - opt-in full-check mode,
  - `sd-update-spec` post-refresh verification,
  - or a combination with clear documentation.
- Add a deterministic check path for `scripts/sd-ai-command-pack-update-spec-kb.py --check`.
- Avoid surprising consumer repos that have not generated `.obsidian-kb` yet. The check should either skip cleanly with a clear message or run only when the KB package exists/configuration says it is expected.
- Make the behavior configurable with an environment variable if strict mode would be too noisy for some repos.
- Document the new behavior in `README.md`, `docs/SD_AI_COMMAND_PACK.md`, and relevant skill/prompt surfaces if they mention full-check or update-spec verification.
- Add tests for the full-check or wrapper behavior so stale KB output is surfaced intentionally.

## Acceptance Criteria

- [x] A stale generated KB package is detected by the selected verification path (full-check lane, mode auto; test asserts the failure).
- [x] A repo without `.obsidian-kb` does not fail unexpectedly unless strict KB verification is explicitly enabled (auto skips with a warning; `required` fails).
- [x] The check emits an actionable message that tells the user which command to run to refresh or verify the KB.
- [x] Full-check documentation and installed docs describe the KB verification behavior and any opt-in/opt-out environment variable (README table, installed guide, sd-full-check skill).
- [x] Existing full-check behavior for Prism, Gito, CI classifier, install audit, and pack drift remains unchanged.
- [x] Focused tests cover pass, skip, stale, and disabled KB states.
- [x] `python3 -m unittest discover -s tests` passes (305 tests).
- [x] `git diff --check` passes.

## Implementation Notes

- Inspect the bottom of `scripts/sd-ai-command-pack-full-check.sh` where preflight, install audit, pack drift, scope, PR body, and CI checks are orchestrated.
- Consider a variable such as `SD_AI_COMMAND_PACK_FULL_CHECK_KB` with explicit values for `auto`, `required`, or `0`, but keep the final interface consistent with existing full-check environment variable conventions.
- This task should be easier after `07-06-kb-runtime-exclusion-hardening` is complete, because the KB check should not fail due to local Trellis backup artifacts.

## Notes

- This task tracks the tooling coverage gap, not the KB source-discovery bug itself.
