BREW_PYTHON ?= /opt/homebrew/bin/python3.13
PYTHON ?= $(shell if [ -x "$(BREW_PYTHON)" ]; then printf '%s' "$(BREW_PYTHON)"; elif [ -x /usr/local/bin/python3.13 ]; then printf '%s' /usr/local/bin/python3.13; elif [ -x /opt/homebrew/bin/python3 ]; then printf '%s' /opt/homebrew/bin/python3; elif [ -x /usr/local/bin/python3 ]; then printf '%s' /usr/local/bin/python3; else command -v python3; fi)
VENV ?= .venv
VENV_PYTHON = $(VENV)/bin/python
VENV_BIN = $(VENV)/bin

.PHONY: setup hooks generate sync test lint audit full-check check

setup:
	"$(PYTHON)" -m venv "$(VENV)"
	"$(VENV_PYTHON)" -m pip install -r requirements-dev.txt -r requirements-security.txt
	git config core.hooksPath .githooks

hooks:
	git config core.hooksPath .githooks

generate:
	@if [ -x "$(VENV_PYTHON)" ]; then \
		"$(VENV_PYTHON)" .github/scripts/generate-command-surfaces.py; \
	else \
		"$(PYTHON)" .github/scripts/generate-command-surfaces.py; \
	fi

# Self-sync after payload or doc/spec/task edits: refresh the dogfood
# install from templates/, then regenerate the spec knowledge base.
sync:
	"$(VENV_PYTHON)" install.py . --force
	"$(VENV_PYTHON)" scripts/sd-ai-command-pack-update-spec-kb.py

test:
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/run-tests.sh
	@if grep -Eq 'skipped=[1-9][0-9]*' unittest-output.log; then printf '%s\n' "Tests skipped locally; install required tools or make the skip explicit."; exit 1; fi
	"$(VENV_PYTHON)" -m coverage combine
	"$(VENV_PYTHON)" -m coverage report --include="install.py,installer/*" --fail-under=100
	PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/check-shipped-script-coverage.sh

# Pass STRICT=1 to turn missing-tool skips below into hard errors (CI
# parity: the CI lint/security jobs always run the Node and ShellCheck
# lanes). Mypy covers installer/, the install.py facade, and shipped
# scripts/*.py; templates/scripts/ twins are byte-identical mirrors kept
# out of the run so duplicate script names cannot collide.
lint:
	"$(VENV_PYTHON)" -m ruff check install.py installer scripts templates/scripts tests
	"$(VENV_PYTHON)" -m mypy installer install.py scripts
	@if command -v node >/dev/null 2>&1; then \
		node --check scripts/sd-ai-command-pack-review-preflight.mjs; \
		node --check templates/scripts/sd-ai-command-pack-review-preflight.mjs; \
		bash .github/scripts/check-opencode-js.sh; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: node not found and STRICT=1; JavaScript syntax checks are required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: node not found; skipping JavaScript syntax checks."; \
	fi
	@if command -v shellcheck >/dev/null 2>&1; then \
		git ls-files -z '*.sh' | xargs -0 shellcheck -S warning .githooks/pre-push; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: shellcheck not found and STRICT=1; shell lint is required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: shellcheck not found; skipping shell lint."; \
	fi

audit:
	@if [ -x "$(VENV_BIN)/bandit" ]; then \
		"$(VENV_BIN)/bandit" -q -r --severity-level medium install.py installer scripts templates/scripts; \
	elif command -v bandit >/dev/null 2>&1; then \
		bandit -q -r --severity-level medium install.py installer scripts templates/scripts; \
	else \
		printf '%s\n' "warning: bandit not found; skipping Python security audit."; \
	fi
	@if [ -x "$(VENV_BIN)/zizmor" ]; then \
		"$(VENV_BIN)/zizmor" --offline .github/workflows/; \
	elif command -v zizmor >/dev/null 2>&1; then \
		zizmor --offline .github/workflows/; \
	else \
		printf '%s\n' "warning: zizmor not found; skipping workflow security audit."; \
	fi

full-check:
	SD_AI_COMMAND_PACK_FULL_CHECK_PRISM=0 SD_AI_COMMAND_PACK_FULL_CHECK_GITO=0 bash scripts/sd-ai-command-pack-full-check.sh

check: test lint audit full-check
