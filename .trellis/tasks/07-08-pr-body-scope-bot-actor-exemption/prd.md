# Exempt automated PR authors from the pr-body-scope check

## Goal

`scripts/sd-ai-command-pack-pr-body-scope.py` fails (exit `1`) whenever a
supplied PR body omits a required scope heading for a changed pack surface.
That is correct for human PRs, but it makes the checker unsafe to wire into a
required CI gate: Dependabot and Renovate open PRs whose bodies never carry the
human scope headings (`Tooling/generated scope:`, `CI/review scope:`, …), so
every bot PR would fail the gate and its auto-merge would be blocked
indefinitely.

This is the one genuinely pack-owned slice of review item 7 (PR-body scope
enforcement) surfaced in the anomaly-metric-creator deep review: the bot-skip
belongs in the shared script so **every** consuming repo benefits the moment it
wires the check in. The enforce-decision and the per-repo `ci.yml` wiring stay
repo-side and are out of scope here.

## Requirements

- R1: `check()` gains an `actor` parameter. When the resolved actor is an
  automated author, the check reports the skip and returns `0` even when a body
  is supplied and would otherwise fail.
- R2: Actor resolution precedence is `--actor` flag →
  `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_ACTOR` env var → empty (values are trimmed;
  empty/whitespace falls through).
- R3: The exemption predicate keys off the universal GitHub bot convention —
  a login ending in `[bot]` (`dependabot[bot]`, `github-actions[bot]`,
  `renovate[bot]`, …). No per-repo actor allowlist the pack would have to
  maintain; a non-`[bot]` service account is handled caller-side (skip the
  step for that actor).
- R4: Default behavior is unchanged when no actor is supplied — an empty actor
  is never exempt, so existing callers and human PRs keep the strict path.
- R5: Changes land byte-identically in both `scripts/` and
  `templates/scripts/`; the module docstring exit-code table,
  `docs/SD_AI_COMMAND_PACK.md` (+ template twin), the README env-var
  quick-reference table, and `manifest.json` version are all updated in the
  same change.

## Acceptance Criteria

- [ ] Bot author (`dependabot[bot]`) with a body missing the required section
  → exit `0` with a "skipped for automated actor" message (verified by test,
  via both `--actor` and the env var).
- [ ] Human author (or no actor) with the same missing section → exit `1`
  (strict path preserved; verified by test).
- [ ] `_actor_is_exempt` / `_resolve_actor` unit-covered: `[bot]` suffix True;
  human, empty, and `bot-fan` (non-suffix) False; flag-beats-env + trim.
- [ ] Full pack battery green; `scripts/` ↔ `templates/scripts/` and the docs
  twins stay byte-identical (existing sync tests pass).

## Notes

- Origin: 2026-07-06 anomaly-metric-creator deep review, item 7. Ownership
  boundary confirmed against `.sd-ai-command-pack/installed-targets.txt`
  (pack owns the `sd-ai-command-pack-*` scripts; the repo owns `ci.yml` and the
  `.sd-ai-command-pack/pr-body-scope.json` config).
- New test file `tests/test_pr_body_scope.py` also backfills the first
  behavioral coverage of this script (previously only exercised indirectly by
  the template-sync tests).
- Follow-up (repo-side, not this task): wire the check into
  anomaly-metric-creator `ci.yml`, passing the PR author via `--actor` /
  `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_ACTOR`.
