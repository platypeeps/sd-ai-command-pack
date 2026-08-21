# Adopt configure_git_identity across the test suite

## Goal

Route the test suite's git-identity setup through the shared
`configure_git_identity` helper, so the fixture that needs a committer
identity gets one from a single place instead of 109 hand-copied pairs.

## Context

0.71.38 added `configure_git_identity` to `tests/install_test_support.py`
after CI runners — which have no ambient `~/.gitconfig` — died with
"Author identity unknown" on fixtures that ran `git init` and stopped there.
It fixed the failures at hand and is used by 5 call sites.

It did not touch the duplication that motivated it. 114 `user.email` lines
remain across 27 test files; 5 go through the helper, 109 do not. Two of
those copies carry comments explaining the exact CI failure, in prose, twice.

`make_repo` (`tests/install_test_support.py`) is where this belongs: it runs
`git init` and nothing else, is called from hundreds of tests, and is the
reason each caller has to remember the two lines at all. Its sibling
`make_git_repo_without_trellis` has the same gap.

Verified safe to change: no test asserts on git config contents, on the
absence of config, or on an author identity string anywhere in the suite. The
one test that reads `.git/config` hashes whatever is on disk at fixture time
rather than pinning bytes, so a longer config file still matches. Every
tree-snapshot helper already excludes `.git/`.

## Requirements

- Prefer seeding the identity in `make_repo` and `make_git_repo_without_trellis`
  over rewriting 109 call sites. A caller that cannot forget the two lines is
  better than 109 callers that remember them; the per-site replacement is the
  fallback if seeding turns out to break a fixture that deliberately wants an
  identity-less repository.
- Roughly 15 sites use a distinctive identity rather than the default
  `test@example.com` / `Test User` — `work-loop@example.com`, `candidate@invalid`,
  `scope@example.invalid` and others. Nothing asserts on them, but they make it
  obvious which fixture authored a commit when a failure is being read.
  Preserve that: give the helper optional name and email rather than
  flattening every fixture to one identity.
- Do not set the identity through `GIT_AUTHOR_*` / `GIT_COMMITTER_*` env vars.
  `.github/scripts/run-tests.sh` already injects config via
  `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_*`, and `tests/test_generated_parity.py`
  asserts on the literal `GIT_CONFIG_COUNT=3` and the three key names, so an
  env-based fix drags that parity test along for no benefit. Repo-local config
  keeps the change inside the fixture.

## Acceptance Criteria

- [ ] A fixture created by `make_repo` can commit without its caller setting an identity.
- [ ] No test file outside the shared support module sets `user.email` or `user.name` directly.
- [ ] Fixtures that used a distinctive identity still commit under it.
- [ ] The full suite passes on a runner with no ambient git identity, which is the condition that motivated the helper.
