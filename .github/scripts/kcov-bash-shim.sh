#!/bin/bash
# Absolute interpreter path on purpose: this shim stands in for _bash_path, and
# some tests invoke it under a restricted PATH that omits bash. A
# `#!/usr/bin/env bash` shebang would need bash on that PATH before the shim even
# starts and fail with exit 127, which the real bash binary it replaces never
# does.
#
# kcov wrapper that stands in for `bash` while the Python test suite exercises
# the shipped shell surface, so kcov records which lines of
# scripts/sd-ai-command-pack-*.sh the subprocess tests actually reach.
#
# The test harness resolves its bash through SD_AI_COMMAND_PACK_TEST_BASH
# (tests/install_test_support.py). Point that variable at this shim in CI and
# every `bash ...` the tests spawn runs under kcov instead.
#
# Coverage scope note: full-check.sh runs a Python program on stdin via
# `python3 - <<'HEREDOC'`. bash never executes those heredoc lines — they are a
# single command's input — so kcov's bash collector never records them. The
# inline Python region is therefore excluded from this lane automatically; its
# extraction and measurement are deferred to a separate task.
#
# Fallback: when kcov is absent or no output directory is configured (local
# developer runs), exec the real bash unchanged so behaviour and exit codes are
# identical to invoking bash directly.
set -u

real_bash="${SD_AI_COMMAND_PACK_REAL_BASH:-/bin/bash}"
if [ ! -x "$real_bash" ]; then
  real_bash="$(command -v bash 2>/dev/null || printf '/bin/bash')"
fi

kcov_dir="${SD_AI_COMMAND_PACK_KCOV_DIR:-}"
if [ -z "$kcov_dir" ] || ! command -v kcov >/dev/null 2>&1; then
  exec "$real_bash" "$@"
fi

# Restrict measurement to the shipped shell scripts by name. kcov matches this
# as a plain substring against the source path, so use the basename marker
# rather than a path prefix: the tempdir copies the tests run are then also
# recorded, and summarize_shell_coverage.py re-collapses copies by basename and
# filters to .sh.
include_pattern="${SD_AI_COMMAND_PACK_KCOV_INCLUDE:-sd-ai-command-pack-}"

# Each invocation writes to a unique subdirectory; a later `kcov --merge` step
# combines them. $$ plus SRANDOM/epoch keeps names distinct across the many
# subprocesses a single test run spawns.
run_dir="$kcov_dir/run-$$-${RANDOM:-0}-${SRANDOM:-0}"

exec kcov \
  --include-pattern="$include_pattern" \
  --bash-dont-parse-binary-dir \
  "$run_dir" \
  "$real_bash" "$@"
