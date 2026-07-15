# CI hardening tail: SHA-pin actions, deadlock, mypy, dependabot

## Goal

Close the residual CI/tooling hardening items from the 2026-07-09 review that
are real but low-severity, and that the shell/hook hardening task explicitly
punted. The workflow is already well-hardened (top-level read-only
permissions, `persist-credentials: false`, no `${{ }}` interpolation into run
bodies, macOS lane, timeouts, concurrency, a correct `CI Result` aggregate);
these are the remaining edges.

## Problem

- **Actions are tag-pinned, not SHA-pinned.** `.github/workflows/tests.yml`
  uses `actions/checkout@v4`, `actions/setup-python@v5`, etc. zizmor's default
  policy tolerates tag pins for official actions, so the security lane does not
  flag it, but a moved tag is an unpinned-supply-chain risk.
- **`paths-ignore` + required "CI Result" context can deadlock a PR.**
  tests.yml:4-11 (`paths-ignore`) vs 137-139 (required context): a PR touching
  only `.trellis/workspace/**` triggers no workflow, so the required
  `CI Result` context never reports and the PR is unmergeable. Semi-intentional
  for the maintainer's chore lane, but a fork contributor without main-push
  rights would be stuck.
- **No type checking.** ruff selects only `E4,E7,E9,F` (pyflakes-ish) with
  `F401/F403/F405/F811` ignored for `install.py` and `installer/*` (the F811
  piece is handled by `07-09-installer-import-write-hygiene`); there is no
  mypy/pyright anywhere for ~180KB of shipped Python.
- **No dependency-update automation.** No Dependabot configuration file, no
  renovate; requirements use strict `==` pins with no bot to bump them, so
  e.g. `coverage==7.6.0` ages silently.
- **ruff scope excludes vendored hook `.py`** (`.codex`/`.gemini`/`.github/copilot`)
  — consistent with the documented vendored-exemption stance; note it, decide
  whether to include the pack-owned ones.

## Requirements

- R1: SHA-pin all GitHub Actions with a trailing version comment
  (`uses: actions/checkout@<sha> # v4`); keep them updatable (see R4).
- R2: Resolve the `paths-ignore`/required-context deadlock so a PR that
  changes only ignored paths is still mergeable — e.g. a trivial always-green
  job that reports the `CI Result` context, or drop `.trellis/workspace/**`
  from `paths-ignore`.
- R3: Add a mypy (or pyright) lane over `installer/` at a pragmatic strictness,
  wired into CI and the Makefile `check` target; fix or baseline findings.
- R4: Add a minimal Dependabot configuration covering the `pip` and
  `github-actions` ecosystems (the latter keeps the R1 SHAs current).
- R5: Decide and document ruff's Python-file scope (whether pack-owned hook
  scripts under `.codex`/`.gemini`/`.github/copilot` are linted); apply the
  decision.

## Acceptance Criteria

- [x] All actions SHA-pinned with version comments; zizmor lane still green.
- [x] A PR touching only `paths-ignore` paths can reach a mergeable state
      (verified by reasoning or a test PR).
- [x] mypy lane runs in CI + `make check`; baseline committed if not clean.
- [x] `dependabot.yml` present for pip + github-actions.
- [x] ruff scope decision recorded (CONTRIBUTING or workflow comment) and
      applied.

## Non-goals

- actionlint — an explicit deferred roadmap item
  (`07-09-actionlint-workflow-linting`); do not duplicate it here.
- Adding Python 3.11/3.12 CI lanes (separate matrix-coverage decision).
