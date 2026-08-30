BREW_PYTHON ?= /opt/homebrew/bin/python3.13
PYTHON ?= $(shell if [ -x "$(BREW_PYTHON)" ]; then printf '%s' "$(BREW_PYTHON)"; elif [ -x /usr/local/bin/python3.13 ]; then printf '%s' /usr/local/bin/python3.13; elif [ -x /opt/homebrew/bin/python3 ]; then printf '%s' /opt/homebrew/bin/python3; elif [ -x /usr/local/bin/python3 ]; then printf '%s' /usr/local/bin/python3; else command -v python3; fi)
VENV ?= .venv
VENV_PYTHON = $(VENV)/bin/python
VENV_BIN = $(VENV)/bin

.PHONY: setup generate surface-check test lint audit full-check check

setup:
	"$(PYTHON)" -m venv "$(VENV)"
	"$(VENV_PYTHON)" -m pip install --require-hashes -r requirements-dev.txt -r requirements-security.txt

# Regenerates the authored command surfaces under templates/ from
# .github/command-sources/ and installer/registry.py, then re-checks closure.
generate:
	@if [ -x "$(VENV_PYTHON)" ]; then \
		"$(VENV_PYTHON)" .github/scripts/generate-command-surfaces.py; \
		"$(VENV_PYTHON)" templates/scripts/sd-ai-command-pack-surface-check.py; \
	else \
		"$(PYTHON)" .github/scripts/generate-command-surfaces.py; \
		"$(PYTHON)" templates/scripts/sd-ai-command-pack-surface-check.py; \
	fi

surface-check:
	"$(PYTHON)" templates/scripts/sd-ai-command-pack-surface-check.py

test:
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/run-tests.sh
	@if grep -Eq 'skipped=[1-9][0-9]*' unittest-output.log; then printf '%s\n' "Tests skipped locally; install required tools or make the skip explicit."; exit 1; fi
	"$(VENV_PYTHON)" -m coverage combine
	"$(VENV_PYTHON)" -m coverage report --include="install.py,installer/*" --fail-under=100
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/check-shipped-script-coverage.sh
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/check-shipped-script-docs.sh
	"$(VENV_PYTHON)" .github/scripts/check-helper-resolution.py
	"$(VENV_PYTHON)" .github/scripts/check-shipped-script-modes.py

# The one definition of what the Python linters cover. CI reads these through
# the lint-ruff-paths / lint-mypy-paths targets rather than restating them:
# the workflow carried its own hand-copied list until 2026-08-29 and had
# silently omitted every bin/ file, so each tool added since sd_route.py was
# lint-clean locally and unlinted in CI. Derive it, do not duplicate it.
LINT_RUFF_PATHS := install.py installer bin/migrate-trellis bin/sd_route.py bin/sd-docs-lint bin/sd_lib.py bin/sd-check bin/sd-handoff bin/sd-handoff-restore bin/sd-pr-state bin/sd-review bin/sd-status templates/scripts tests .github/scripts/check-command-surface-drift.py .github/scripts/check-helper-resolution.py .github/scripts/check-shipped-script-modes.py .github/scripts/summarize_shell_coverage.py
LINT_MYPY_PATHS := installer install.py bin/sd_route.py bin/sd-docs-lint bin/sd_lib.py bin/sd-check bin/sd-handoff bin/sd-handoff-restore bin/sd-pr-state bin/sd-review bin/sd-status templates/scripts .github/scripts/check-command-surface-drift.py .github/scripts/check-helper-resolution.py .github/scripts/check-shipped-script-modes.py .github/scripts/summarize_shell_coverage.py

.PHONY: lint-ruff-paths lint-mypy-paths
lint-ruff-paths:
	@printf '%s\n' "$(LINT_RUFF_PATHS)"
lint-mypy-paths:
	@printf '%s\n' "$(LINT_MYPY_PATHS)"

# Pass STRICT=1 to turn missing-tool skips below into hard errors (CI
# parity: the CI lint/security jobs always run the Node and ShellCheck
# lanes). Ruff and mypy cover the paths named in LINT_RUFF_PATHS and
# LINT_MYPY_PATHS above -- installer/, the install.py facade, the single copy
# of the payload under templates/scripts/, and the bin/ tools. The bash 3.2 lane
# parses tracked shell with the interpreter macOS keeps at /bin/bash, so syntax
# that only bash 3.2 rejects fails before the push. The bash32 CI job enforces
# the same lane on a bash 3.2 it builds itself, so this is a fast local echo of
# a real gate rather than the only place it runs. A platform without bash 3.2
# prints a skip line; STRICT=1 makes it fatal.
lint:
	"$(VENV_PYTHON)" -m ruff check $(LINT_RUFF_PATHS)
	"$(VENV_PYTHON)" -m mypy $(LINT_MYPY_PATHS)
	@if command -v node >/dev/null 2>&1; then \
		node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs; \
		bash .github/scripts/check-opencode-js.sh; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: node not found and STRICT=1; JavaScript syntax checks are required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: node not found; skipping JavaScript syntax checks."; \
	fi
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
		"$(VENV_BIN)/bandit" -q -r --severity-level medium install.py installer templates/scripts; \
	elif command -v bandit >/dev/null 2>&1; then \
		printf '%s\n' "warning: $(VENV_BIN)/bandit is missing; using an UNPINNED bandit from PATH ($$(bandit --version 2>&1 | head -1 | tr -d '\r')). CI uses the requirements-security.txt pin; run 'make setup' to match it."; \
		bandit -q -r --severity-level medium install.py installer templates/scripts; \
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

full-check:
	SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash templates/scripts/sd-ai-command-pack-full-check.sh

check: test lint audit full-check
