# Contributor experience baseline: CONTRIBUTING, Makefile, hook arming

## Goal

A contributor doing the full documented local verification needs ~10
commands across 4 concerns (venv+coverage battery, security tools that
must be reverse-engineered from tests.yml, full-check.sh, hook arming)
with no Makefile or single entry point. Two sharper edges from the
2026-07-06 review:

- **The pre-push chore-scope guard is unarmed by default**: activation
  is a manual `git config core.hooksPath .githooks` documented in
  README:751-757, and it was unset even in the maintainer's own clone
  during the review. The hook is the stated compensating control for
  `enforce_admins=off` branch protection (README:743-761), so an
  unarmed hook means the bypass is unguarded — and nothing warns.
- **No CONTRIBUTING.md / development docs**: the
  manifest-version-bump rule that the consumer provenance audit
  depends on (README:656-659) is written nowhere; the excellent
  internal guides (`.trellis/spec/frontend/adapter-guidelines.md` for
  "how to add a platform adapter",
  `.trellis/spec/backend/manifest-and-filesystem.md` for
  manifest/provenance mechanics) are unlinked from README/AGENTS.md.
- Minor hygiene: `.ruff_cache/` ignored only by ruff's self-written
  gitignore, not repo policy; `.opencode/package.json` has a caret
  dependency with no lockfile; local full-check does not mirror CI's
  test/security lanes.

## Requirements

- R1: Add a `Makefile` (or equivalent single entry point) with at
  least: `setup` (venv + deps + `git config core.hooksPath .githooks`),
  `test` (coverage battery), `lint` (ruff + shellcheck when on PATH),
  `audit` (bandit/zizmor when on PATH), `check` (full local battery
  mirroring CI).
- R2: `sd-ai-command-pack-full-check.sh` emits a warning when
  `git config core.hooksPath` is not `.githooks` in the pack source
  repo, so every full-check nags until the guard is armed.
- R3: Add CONTRIBUTING.md (or a README Development section) covering:
  setup/test/lint commands, the manifest-version-bump rule, the
  templates-are-source-of-truth + resync procedure
  (`python3 install.py . --force` as the documented self-sync), and
  links to the two `.trellis/spec` guides.
- R4: Add `.ruff_cache/` to the root `.gitignore`; pin or lock the
  `.opencode/package.json` dependency.

## Acceptance Criteria

- [x] `make setup && make check` (or equivalent) is the complete
  documented local flow; README Verify section updated to reference it.
- [x] Full-check warns on an unarmed hook (test with a scratch clone).
- [x] CONTRIBUTING content present and linked; hygiene items done.
- [x] Full battery green.

## Implementation Notes

- Added `Makefile` targets for `setup`, `hooks`, `test`, `lint`, `audit`,
  `full-check`, and `check`; `setup` prefers Homebrew Python 3.13 and arms the
  `.githooks` pre-push guard.
- Added `CONTRIBUTING.md` with setup/check commands, the manifest-version-bump
  rule, template source-of-truth guidance, self-sync instructions, and links to
  adapter plus manifest/filesystem specs.
- Updated `sd-ai-command-pack-full-check.sh` and its shipped template twin to
  warn in the pack source checkout when `core.hooksPath` is not `.githooks`.
- Pinned `.opencode/package.json` to `@opencode-ai/plugin` `1.14.39` and
  relied on the already-landed root `.ruff_cache/` ignore from the CI hardening
  task.
- Bumped the manifest version to `0.7.3` and added the changelog entry because
  the shipped full-check template changed.
- Validation: focused contributor/full-check tests, `make setup`, `make lint`,
  `make audit`, and `make test` using a disposable Python 3.13 venv, plus
  `git diff --check` and SD full-check with Prism/Gito disabled all passed.

## Notes

- Origin: 2026-07-06 deep review (Tooling findings 2/6/1/3b; Docs
  finding 4). Coordinates with 07-06-ci-skip-backstop-lint-lane
  (shares ruff pin/config) — land that first or together.
