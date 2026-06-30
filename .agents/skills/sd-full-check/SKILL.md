---
name: sd-full-check
description: Use when the user asks to run the expensive local verification gate, prepare a PR for readiness, or perform a local-review-first check before requesting remote review.
---

# SD Full Check

Run this project-local skill for `sd-full-check` and `/sd:full-check` style
work. It is an optional but strongly recommended PR-readiness gate, not an
every-edit requirement.

The canonical implementation is:

```bash
bash scripts/sd-ai-command-pack-full-check.sh
```

## What It Does

The script runs:

1. `git diff --check` for unstaged changes.
2. `git diff --cached --check` for staged changes.
3. Repo-local review preflight through
   `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND` when configured, or
   through `scripts/check-review-preflight.mjs` when that Node.js script exists.
4. Copied/generated tooling scope checks for Trellis/SD AI command pack, known
   repository-map files when present, and Trellis workspace journal/index
   changes.
5. Structural post-install audit through
   `scripts/sd-ai-command-pack-install-audit.py`, verifying that copied pack
   targets match `.sd-ai-command-pack/installed-targets.txt`.
6. Configurable PR-body scope checks for generated/tooling, automation, and
   CI/review diffs, plus any repo-added categories in
   `.sd-ai-command-pack/pr-body-scope.json`.
7. Current-diff CI classification reporting through
   `scripts/classify-ci-changes.sh` when that script exists.
8. Optional package-script checks when `package.json`, Node.js, and the
   selected package runner are available. The default script-name probe looks
   for common entries: `typecheck`, `lint`, `test:unit`, `test:integration`,
   `build`, and `test:e2e`.
9. Prism local review when `prism` is on `PATH` and Prism is not disabled.
10. Gito review only when explicitly enabled.

## Safety Rules

- Do not stage, commit, push, or edit files as part of this skill unless the
  user separately asks for fixes.
- Treat failures as evidence to report and fix in the normal Trellis
  implementation flow.
- Prism is optional by default because some environments lack provider
  credentials or valid provider/model configuration. Set
  `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=required` when missing Prism, authentication
  failure, or provider/model configuration failure should fail the command.
- Gito is opt-in because it may invoke `uvx`, use a cache outside the repo, and
  require LLM credentials or network access. Set `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1` to
  run it. Reports are written to `.build/review/gito` by default.
- If the script reports skipped checks, include those skips in the final report.

## Useful Environment Variables

- `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`: base ref for branch review. Defaults to
  `origin/main`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT=0`: skip
  repo-local review preflight.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT=required`: fail if no configured
  review preflight command can run and the optional
  `scripts/check-review-preflight.mjs` fallback is unavailable.
- `SD_AI_COMMAND_PACK_FULL_CHECK_REVIEW_PREFLIGHT_COMMAND`: repo-specific review
  preflight command to run with `bash -lc`.
- `SD_AI_COMMAND_PACK_INSTALL_AUDIT=0`: skip the structural post-install audit.
- `SD_AI_COMMAND_PACK_INSTALL_AUDIT=required`: fail if the audit helper or
  `python3` is unavailable. By default those availability problems warn and
  continue.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_SCRIPTS`: space-separated package scripts
  to run when `package.json` and the selected package runner are available.
  The older `SD_AI_COMMAND_PACK_FULL_CHECK_NPM_SCRIPTS` name is still accepted for
  compatibility.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PACKAGE_RUNNER`: package runner. Defaults to `npm`
  when package-script checks apply.
- `SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_PACKAGE_SCRIPTS=1`: skip package-script
  checks. The older `SD_AI_COMMAND_PACK_FULL_CHECK_SKIP_NPM=1` name is still
  accepted for compatibility.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0`: skip Prism.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=required`: fail if Prism is missing,
  unauthenticated, or has provider/model configuration failures.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_RULES`: explicit Prism rules file.
- `SD_AI_COMMAND_PACK_FULL_CHECK_PRISM_FAIL_ON`: Prism fail threshold. Defaults to `high`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO=1`: run Gito review after Prism.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_BASE_REF`: base ref for Gito review. Defaults to
  `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`, then `origin/main`.
- `SD_AI_COMMAND_PACK_FULL_CHECK_GITO_OUT_DIR`: Gito report output directory. Defaults to
  `.build/review/gito`.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CHECK=0`: skip configurable PR-body scope
  checks.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_CONFIG`: explicit JSON config path for
  additional PR-body scope rules. Defaults to
  `.sd-ai-command-pack/pr-body-scope.json` when present.
- `SD_AI_COMMAND_PACK_PR_BODY_SCOPE_PR_BODY`: explicit PR body text for
  configurable PR-body scope checks.
- `SD_AI_COMMAND_PACK_SCOPE_PR_BODY`: explicit PR body text for tooling/generated
  and PR-body scope checks in local or CI contexts where `gh pr view` should
  not be used.

## Expected Report

Report:

- Whether deterministic checks passed.
- Whether repo-local review preflight ran, skipped, or failed.
- Whether the post-install audit ran, skipped, or failed.
- Which package-script checks ran or were skipped.
- Whether Prism ran, skipped, found findings, lacked credentials, or had
  provider/model configuration failures.
- Whether Gito ran or was intentionally skipped, and where reports were written.
- Any command that failed and the smallest next fix.
