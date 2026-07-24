# Implementation plan

## 1. Add Claude-only Codex CLI orchestration

- [ ] Add a narrowly keyed Claude platform insertion to
      `.github/scripts/generate-command-surfaces.py` for `sd-review-local`.
- [ ] Specify Codex CLI/flag capability detection, concurrent runner and Codex
      execution, unconditional task collection, and combined result handling.
- [ ] Map dirty state to `codex review --uncommitted` and branch state to
      `codex review --base <resolved-ref>`.
- [ ] Encode visible missing/incompatible CLI fallback, review failure
      reporting, and the full-codebase scope skip.
- [ ] Update the canonical `sd-review-local` skill with provider aggregation,
      verification, rerun, and reporting rules.
- [ ] Keep the neutral command source generic except where it must establish the
      shared aggregation contract.

## 2. Tests and contracts

- [ ] Add generator tests proving native Codex fan-out appears only in the
      Claude adapter and survives regeneration.
- [ ] Add parity/drift assertions for the bounded Claude-specific insertion.
- [ ] Add review-local contract tests for CLI capability fallback, execution
      failure, rerun, and full-codebase scope wording without changing the
      runner tool list.
- [ ] Assert generated/installable content contains no Claude plugin cache,
      companion-script, or plugin-install dependency.
- [ ] Update `.trellis/spec/frontend/adapter-guidelines.md` and
      `docs/SD_AI_COMMAND_PACK.md` with the CLI prerequisite and optional-plugin
      lifecycle.
- [ ] Run focused Python tests and the command-surface generation check.

## 3. Release and verification

- [ ] Regenerate surfaces and run `make sync` so template sources and dogfood
      mirrors match.
- [ ] Bump the manifest minor version because Claude command semantics change;
      add the matching top changelog entry.
- [ ] Run the full fleet candidate validator and refresh
      `docs/fleet/candidate-validation.json` at the final payload state.
- [ ] Run `make check`.
- [ ] Review the complete diff for non-Claude drift, plugin coupling, unsafe
      argument interpolation, and scope mismatch.
- [ ] Run the repository's normal PR/review/finish-work lifecycle after explicit
      publication authority.

## Rollback

Revert the Claude-only generator insertion and associated shared aggregation
wording. The existing runner remains the fallback and its public tool surface
is unchanged. No plugin or user-level Claude state needs restoration.
