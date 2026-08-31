BREW_PYTHON ?= /opt/homebrew/bin/python3.13
PYTHON ?= $(shell if [ -x "$(BREW_PYTHON)" ]; then printf '%s' "$(BREW_PYTHON)"; elif [ -x /usr/local/bin/python3.13 ]; then printf '%s' /usr/local/bin/python3.13; elif [ -x /opt/homebrew/bin/python3 ]; then printf '%s' /opt/homebrew/bin/python3; elif [ -x /usr/local/bin/python3 ]; then printf '%s' /usr/local/bin/python3; else command -v python3; fi)
VENV ?= .venv
VENV_PYTHON = $(VENV)/bin/python
VENV_BIN = $(VENV)/bin

.PHONY: setup test lint audit check

setup:
	"$(PYTHON)" -m venv "$(VENV)"
	"$(VENV_PYTHON)" -m pip install --require-hashes -r requirements-dev.txt -r requirements-security.txt

# `generate` and `surface-check` are gone with step 3e. They regenerated the
# committed per-platform copies under templates/ from .github/command-sources/,
# and there are no committed copies any more: bin/sd_install.py renders from skills/
# at install time, so there is nothing to keep in sync and nothing to check for
# closure against a generator.

test:
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/run-tests.sh
	@if grep -Eq 'skipped=[1-9][0-9]*' unittest-output.log; then printf '%s\n' "Tests skipped locally; install required tools or make the skip explicit."; exit 1; fi
	"$(VENV_PYTHON)" -m coverage combine
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/check-installer-coverage.sh

# The one definition of what the Python linters cover. CI reads these through
# the lint-ruff-paths / lint-mypy-paths targets rather than restating them:
# the workflow carried its own hand-copied list until 2026-08-29 and had
# silently omitted every bin/ file, so each tool added since sd_route.py was
# lint-clean locally and unlinted in CI. Derive it, do not duplicate it.
#
# `bin/` is enumerated from the index rather than listed, for the same reason
# the LOC caps are: a hand-written list cannot see the file somebody adds next
# month, and that file is then lint-clean by never having been linted. The list
# here was that trap in miniature until 2026-08-31 -- it had already been named
# as one in tests/test_loc_caps.py's docstring. Everything tracked under `bin/`
# is Python (tests/test_no_shipped_shell.py enforces it), so a non-Python file
# arriving there fails lint loudly, which is the right direction to fail.
LINT_BIN := $(shell git ls-files -- bin)
LINT_RUFF_PATHS := dashboard $(LINT_BIN) tests
LINT_MYPY_PATHS := dashboard $(LINT_BIN)

.PHONY: lint-ruff-paths lint-mypy-paths
lint-ruff-paths:
	@printf '%s\n' "$(LINT_RUFF_PATHS)"
lint-mypy-paths:
	@printf '%s\n' "$(LINT_MYPY_PATHS)"

# Pass STRICT=1 to turn missing-tool skips below into hard errors (CI
# parity: the CI lint/security jobs always run the Node and ShellCheck
# lanes). Ruff and mypy cover the paths named in LINT_RUFF_PATHS and
# LINT_MYPY_PATHS above, which after step 3e is just the bin/ tools: the
# installer package and the shipped payload are gone.
#
# The bash 3.2 lane survives 3e on a narrower rationale than it had, and the
# narrowing is worth stating. It existed because the pack shipped shell scripts
# that ran on whatever bash a consumer's macOS had, which is 3.2. Nothing is
# shipped now. What it still protects is this repo's own three scripts under
# .github/scripts/, which `make check` runs through /bin/bash on the
# maintainer's machine -- a real subject, just a smaller one. The bash32 CI job
# enforces the same lane on a bash 3.2 it builds itself, so this is a fast local
# echo of a real gate rather than the only place it runs. A platform without
# bash 3.2 prints a skip line; STRICT=1 makes it fatal.
lint:
	"$(VENV_PYTHON)" -m ruff check $(LINT_RUFF_PATHS)
	"$(VENV_PYTHON)" -m mypy $(LINT_MYPY_PATHS)
	@if command -v shellcheck >/dev/null 2>&1; then \
		git ls-files -z '*.sh' | xargs -0 shellcheck -S warning; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: shellcheck not found and STRICT=1; shell lint is required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: shellcheck not found; skipping shell lint."; \
	fi
	@STRICT="$(STRICT)" bash .github/scripts/check-bash32-syntax.sh

# A scanner found on PATH is whatever version happens to be installed, while
# CI runs the requirements-security.txt pin under --require-hashes. When the
# two differ the gate is not reproducible: a newer scanner invents findings CI
# never sees, an older one misses findings CI would catch, and either way the
# local result says nothing about the pipeline. The fallback still runs -- it
# is better than no audit -- but it announces the skew instead of hiding it.
#
# A scanner that is missing entirely is a silent pass: the `if` exits 0 and
# `make audit` reports success having audited nothing. STRICT=1 makes that
# fatal, matching the node and shellcheck lanes above, so a CI lane or a
# release gate can demand the audit actually ran.
audit:
	@if [ -x "$(VENV_BIN)/bandit" ]; then \
		"$(VENV_BIN)/bandit" -q -r --severity-level medium bin; \
	elif command -v bandit >/dev/null 2>&1; then \
		printf '%s\n' "warning: $(VENV_BIN)/bandit is missing; using an UNPINNED bandit from PATH ($$(bandit --version 2>&1 | head -1 | tr -d '\r')). CI uses the requirements-security.txt pin; run 'make setup' to match it."; \
		bandit -q -r --severity-level medium bin; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: bandit not found and STRICT=1; the Python security audit is required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: bandit not found; skipping Python security audit."; \
	fi
	@if [ -x "$(VENV_BIN)/zizmor" ]; then \
		"$(VENV_BIN)/zizmor" --offline .github/workflows/; \
	elif command -v zizmor >/dev/null 2>&1; then \
		printf '%s\n' "warning: $(VENV_BIN)/zizmor is missing; using an UNPINNED zizmor from PATH ($$(zizmor --version 2>&1 | head -1 | tr -d '\r')). CI uses the requirements-security.txt pin; run 'make setup' to match it."; \
		zizmor --offline .github/workflows/; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: zizmor not found and STRICT=1; the workflow security audit is required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: zizmor not found; skipping workflow security audit."; \
	fi

# `full-check` is gone with step 3e: it ran a shipped script that no longer
# exists, and every lane it wrapped that still has a subject is already a target
# here. `check` is now exactly the three gates CI runs.
check: test lint audit
