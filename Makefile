BREW_PYTHON ?= /opt/homebrew/bin/python3.13
PYTHON ?= $(shell if [ -x "$(BREW_PYTHON)" ]; then printf '%s' "$(BREW_PYTHON)"; elif [ -x /usr/local/bin/python3.13 ]; then printf '%s' /usr/local/bin/python3.13; elif [ -x /opt/homebrew/bin/python3 ]; then printf '%s' /opt/homebrew/bin/python3; elif [ -x /usr/local/bin/python3 ]; then printf '%s' /usr/local/bin/python3; else command -v python3; fi)
# `make setup` provisions one virtualenv, into the checkout it ran in, so a
# linked worktree has none and every recipe below died on `.venv/bin/python:
# No such file or directory`. `--git-common-dir` names the shared git
# directory, whose parent is the main checkout from any worktree -- so a
# worktree borrows the virtualenv that was actually provisioned, and a
# checkout with its own still uses its own. Overriding VENV skips all of it.
MAIN_CHECKOUT = $(shell git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | xargs -I{} dirname {})
VENV ?= $(shell if [ -x .venv/bin/python ] || [ -z "$(MAIN_CHECKOUT)" ] || [ ! -x "$(MAIN_CHECKOUT)/.venv/bin/python" ]; then printf '%s' .venv; else printf '%s' "$(MAIN_CHECKOUT)/.venv"; fi)
VENV_PYTHON = $(VENV)/bin/python
VENV_BIN = $(VENV)/bin

.PHONY: setup hooks fonts test lint audit docs-lint check

setup:
	"$(PYTHON)" -m venv "$(VENV)"
	"$(VENV_PYTHON)" -m pip install --require-hashes -r requirements-dev.txt -r requirements-security.txt
	"$(VENV_PYTHON)" bin/sd_install.py --provision-library

# The pre-commit tier of sd:431. `hooks/pre-commit` runs Ruff over the staged
# Python and the two whole-tree test passes that walk the tree, with a
# wall-time budget in its header. The install is one relative symlink,
# <common .git>/hooks/pre-commit -> ../../hooks/pre-commit, in the clone's
# common git directory: one hook per clone, read from the main checkout's
# tracked file, shared by every linked worktree, whichever worktree ran
# `make hooks` (a worktree's own copy is never linked, so no worktree's
# branch becomes every other worktree's policy). Not
# `.githooks/` and not `core.hooksPath`: those are the retired gate stack's
# signatures, and bin/sd-status reports each as residue with a removal
# command, so the pack's own hook must not wear them. A clone that still
# carries `core.hooksPath` is refused first, since `git rev-parse --git-path
# hooks` would honour it and place the link under the retired directory. A
# file already at the path that is not this link is refused by name and left
# alone. This is a
# setting of the clone, not a render: the installer does not make it, and
# folding it into `--user` is the owner's call. `SD_SKIP_HOOKS=1 git commit`
# skips the hook with a notice.
hooks:
	@if set="$$(git config --get core.hooksPath)"; then \
		printf '%s\n' "error: core.hooksPath is set to $$set; the pack's hook lives in .git/hooks -- run 'git config --unset core.hooksPath' (bin/sd-status names it as residue) and retry" >&2; \
		exit 1; \
	fi; \
	dir="$$(git rev-parse --path-format=absolute --git-common-dir)/hooks"; link="$$dir/pre-commit"; target=../../hooks/pre-commit; \
	if { [ -e "$$link" ] || [ -L "$$link" ]; } && [ "$$(readlink "$$link")" != "$$target" ]; then \
		printf '%s\n' "error: $$link exists and is not the link to hooks/pre-commit; move it aside first" >&2; \
		exit 1; \
	fi; \
	mkdir -p "$$dir" && ln -sfn "$$target" "$$link" && printf '%s\n' "git hooks: $$link -> $$(readlink "$$link")"

# `generate` and `surface-check` are gone with step 3e. They regenerated the
# committed per-platform copies under templates/ from .github/command-sources/,
# and there are no committed copies any more: bin/sd_install.py renders from skills/
# at install time, so there is nothing to keep in sync and nothing to check for
# closure against a generator.

# `make check CHANGED="<paths>"` is the changed-files fast path (sd:10
# criterion 16): the tests those paths need plus an always-run set, chosen by
# .github/scripts/select-tests.py. Only a CHANGED given on the command line
# counts; one inherited from the environment is ignored, so the full suite
# stays the default. A run the selector narrowed skips `coverage combine` and
# the installer gate, which only the full suite can meet; a run it widened to
# the full suite keeps both. CI calls run-tests.sh itself and never passes it.
#
# A narrowed run then exits 2, so that a zero from `test` means the full suite
# ran with both coverage gates and means nothing else. Until sd:840 it printed
# the notice below and exited 0, and a caller that reads the status rather than
# the transcript -- a script, a hook, the left half of an `&&` -- could not
# tell a partial run from a green one.
#
# 2 rather than 1 is for whoever reads this recipe: 1 is already the
# skipped-test gate below and a failing shard inside run-tests.sh. It buys
# nothing at the call site, and the number is not a signal a caller can read.
# `make` reports 2 for any failed recipe whatever the recipe exited -- a 1
# here would reach a caller of `make check` as 2 as well -- so the recipe's
# own number appears only on make's `*** [test] Error 2` line. The
# distinction this does deliver, and the one the item asked for, is 0 for the
# whole suite with both coverage gates and non-zero for anything less.
#
# The value is exported rather than written into the recipe as a quoted word:
# a path holding a quote would otherwise end the quoting and the rest would be
# read as shell. And with no CHANGED on the command line the runner is given a
# tree with TEST_CHANGED_FILES removed, so an operator who left one in their
# environment still gets the full suite from a plain `make check`.
ifeq ($(origin CHANGED),command line)
export TEST_CHANGED_FILES := $(CHANGED)
TEST_RUNNER_ENV =
else
TEST_RUNNER_ENV = env -u TEST_CHANGED_FILES
endif

test:
	PYTHON_BIN="$(VENV_PYTHON)" $(TEST_RUNNER_ENV) bash .github/scripts/run-tests.sh
	@if grep -Eq 'skipped=[1-9][0-9]*' unittest-output.log; then printf '%s\n' "Tests skipped locally; install required tools or make the skip explicit."; exit 1; fi
	@if head -n 1 unittest-output.log | grep -q '^test selection: changed files'; then \
		printf '%s\n' "Changed-files fast path: coverage combine and the installer gate were not run. Run make check without CHANGED before a push."; \
		exit 2; \
	else \
		"$(VENV_PYTHON)" -m coverage combine && \
		PYTHON_BIN="$(VENV_PYTHON)" bash .github/scripts/check-installer-coverage.sh; \
	fi

# The one definition of what the Python linters cover. CI reads these through
# the lint-ruff-paths / lint-mypy-paths targets rather than restating them:
# the workflow carried its own hand-copied list until 2026-08-29 and had
# silently omitted every bin/ file, so each tool added since sd_route.py was
# lint-clean locally and unlinted in CI. Derive it, do not duplicate it.
#
# `bin/` is enumerated from the index rather than listed, for the same reason
# tests/test_code_health.py enumerates: a hand-written list cannot see the file
# somebody adds next month, and that file is then lint-clean by never having
# been linted. The list here was that trap in miniature until 2026-08-31, and
# tests/test_loc_caps.py's docstring had already named it as one.
# Everything tracked under `bin/`
# is Python (tests/test_no_shipped_shell.py enforces it), so a non-Python file
# arriving there fails lint loudly, which is the right direction to fail.
# `--deduplicate`: an unmerged path is listed once per merge stage, so during
# a conflict ruff and mypy would each be handed the same file three times.
# Both dedupe internally, so this one is waste rather than a wrong answer --
# but every `ls-files` in this repository now says what it means (item 481).
# `:(exclude)bin/fonts`: that directory holds vendored woff2 files, and ruff
# reads every path it is handed as UTF-8 source -- a binary there fails the
# lane with E902 rather than being skipped. Excluded by directory and not by
# extension, so a second binary asset lands in the same place or not at all.
LINT_BIN := $(shell git ls-files --deduplicate -- bin ':(exclude)bin/fonts')
LINT_RUFF_PATHS := $(LINT_BIN) tests
LINT_MYPY_PATHS := $(LINT_BIN)

.PHONY: lint-ruff-paths lint-mypy-paths
lint-ruff-paths:
	@printf '%s\n' "$(LINT_RUFF_PATHS)"
lint-mypy-paths:
	@printf '%s\n' "$(LINT_MYPY_PATHS)"

# Pass STRICT=1 to turn missing-tool skips below into hard errors. That is
# parity with the CI lint job, which always runs the ShellCheck lane and
# never skips it. Ruff and mypy cover the paths named in LINT_RUFF_PATHS and
# LINT_MYPY_PATHS above: Ruff over the tracked bin/ files and tests/, mypy
# over the tracked bin/ files. The installer
# package and the shipped payload that step 3e removed are not in either.
#
# The bash 3.2 lane survives 3e on a narrower rationale than it had, and the
# narrowing is worth stating. It existed because the pack shipped shell scripts
# that ran on whatever bash a consumer's macOS had, which is 3.2. Nothing is
# shipped now. What it still protects is this repo's own three scripts under
# .github/scripts/, which `make check` runs through /bin/bash on the
# maintainer's machine -- a real subject, just a smaller one. This is the only
# place the lane runs: the CI job that built bash 3.2 from source to run it on
# Linux was cut by sd:10 criterion 17, because a from-source interpreter build
# was guarding three scripts the local run already executes under the real
# thing. A platform without bash 3.2 prints a skip line; STRICT=1 makes it
# fatal, so do not pass STRICT=1 on Linux and expect this target to pass.
lint:
	"$(VENV_PYTHON)" -m ruff check $(LINT_RUFF_PATHS)
	"$(VENV_PYTHON)" -m mypy $(LINT_MYPY_PATHS)
	@if command -v shellcheck >/dev/null 2>&1; then \
		git ls-files -z --deduplicate '*.sh' | xargs -0 shellcheck -S warning; \
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
# The zizmor lane runs twice. The first is the gate, and it has been reporting
# "No findings to report. Good job! (3 suppressed)" for as long as anyone has
# looked; the second says what those three are. They are not suppressions
# anybody wrote -- there is no zizmor configuration file here and no
# `# zizmor: ignore` comment in any workflow -- they are findings carrying a
# persona the default gate drops, and until sd:876 the only enumeration of
# them was a sentence in a tracked-work note. The script asks zizmor for the
# set instead of reciting it, and fails when a workflow earns a fourth one or
# when a decision outlives its finding. The same binary is handed to both, so
# the enumeration can never be measured by a different zizmor than the gate.
# Neither run is chained behind the other: a workflow edit big enough to redden
# the gate is exactly the edit most likely to have moved the persona-gated set,
# so the run that would be skipped is the one worth having. Both statuses are
# kept and the recipe fails if either does.
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
		"$(VENV_BIN)/zizmor" --offline .github/workflows/; gate=$$?; \
		"$(VENV_PYTHON)" .github/scripts/check-zizmor-personas.py --zizmor "$(VENV_BIN)/zizmor"; names=$$?; \
		[ $$gate -eq 0 ] && [ $$names -eq 0 ]; \
	elif command -v zizmor >/dev/null 2>&1; then \
		printf '%s\n' "warning: $(VENV_BIN)/zizmor is missing; using an UNPINNED zizmor from PATH ($$(zizmor --version 2>&1 | head -1 | tr -d '\r')). CI uses the requirements-security.txt pin; run 'make setup' to match it."; \
		zizmor --offline .github/workflows/; gate=$$?; \
		"$(PYTHON)" .github/scripts/check-zizmor-personas.py --zizmor zizmor; names=$$?; \
		[ $$gate -eq 0 ] && [ $$names -eq 0 ]; \
	elif [ "$(STRICT)" = "1" ]; then \
		printf '%s\n' "error: zizmor not found and STRICT=1; the workflow security audit is required." >&2; \
		exit 1; \
	else \
		printf '%s\n' "warning: zizmor not found; skipping workflow security audit."; \
	fi

# WORKFLOW.md said `make check` ran `sd-docs-lint`, and nothing did:
# `test` lints temporary fixture repositories, `sd-ship` lints at delivery
# time, and CI ran neither against this checkout's own docs/work. The lint
# reads `sd_lib` and the working tree only, so it needs no database and no
# provisioned library. Item 370.
docs-lint:
	"$(VENV_PYTHON)" bin/sd-docs-lint

# Re-vendor the research renderer's Latin woff2 faces and rewrite
# bin/sd_research_fonts.py from them. Needs network; not part of `check`,
# because a check that reaches Google fails on a plane. Run it after
# changing FAMILIES in bin/sd_research_fonts_build.py, and commit both the
# files under bin/fonts/ and the regenerated module.
fonts:
	"$(VENV_PYTHON)" bin/sd_research_fonts_build.py

# `full-check` is gone with step 3e: it ran a shipped script that no longer
# exists, and every lane it wrapped that still has a subject is already a target
# here. `check` is the four gates CI runs, with one lane CI does not have: the
# bash 3.2 parse inside `lint` runs only where a bash 3.2 exists, which is
# this machine when it is a Mac and no runner (sd:10 criterion 17 cut the job
# that built one).
#
# `test` runs last, and the order is load-bearing twice over (sd:840). `make`
# stops at the first prerequisite that fails, and a narrowed `test` now fails
# by design, so anything listed after it would not run at all on the
# changed-files fast path: with `test` last, `make check CHANGED="<paths>"`
# still runs the three whole-tree lanes and still comes out non-zero. And on
# a full run the cheap gates now go first, so a Ruff error is seconds away
# rather than a whole suite away. tests/test_changed_files_fast_path.py pins
# the position; do not move `test` back to the front.
check: lint audit docs-lint test
