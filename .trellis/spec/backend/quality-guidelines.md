# Quality Guidelines

> Code quality standards for backend and CLI development.

---

## Overview

Prefer small, explicit stdlib Python over framework code. The installer should
remain easy to audit because it writes files into other repositories.

## Forbidden Patterns

- Do not overwrite user files unless `--force` is set.
- Do not overwrite an existing `.prism/rules.json` or report it as a conflict;
  preserve repo-specific review rules during pack refreshes.
- Do not stage, commit, or modify the target repo beyond the manifest-listed
  files.
- Do not duplicate platform install rules in several places; update
  `manifest.json` and let `selected_files()` apply the rules.
- Do not replace structured parsing with ad hoc string parsing for JSON.
- Do not reintroduce install-time legacy or obsolete cleanup in `install.py`;
  legacy artifacts are advisory-only, reported by the install audit's
  `LEGACY_PACK_PATHS` / `LEGACY_PACK_REFERENCES` scans (see
  manifest-and-filesystem.md, Legacy And Obsolete Artifact Advisories).

## Silent Paths Must Say Why

Adopted 2026-07-06. Any code path that intentionally does nothing must print a
one-line reason: a skipped platform install, a no-op refresh, an empty scan,
a disabled or short-circuited gate. Silence is indistinguishable from success
and from breakage. The 2026-07-06 deep review found four independent defects
of this shape (silent marker-miss adapter skips, a review gate exiting 0 via
symlink without running, a learnings scan reporting OK after scanning
nothing, CI staying green over skipped tests).

- Good: `warn "No changed files remain after standard review-scan exclusions; skipping Gito review."`
- Bad: `return 0` out of a gate because a tool or input was missing, with no
  output.

## Review Preflight Runtime Contract

### 1. Scope / Trigger

Use this contract when changing
`scripts/sd-ai-command-pack-review-preflight.mjs`, its template twin, or tests
that exercise the generic JavaScript review preflight.

### 2. Signatures

- Command: `node scripts/sd-ai-command-pack-review-preflight.mjs`
- Reusable API: exported helpers such as `runReviewPreflight()` and parser
  helpers may be imported by Node-based tests.

### 3. Contracts

- The executable entry check must work when the script is invoked through a
  symlink. Compare resolved real paths before deciding whether to run.
- The script requires Node 16.9 or newer and must print a clear version error
  before running checks when invoked with an older supported-parser runtime.
- Changed-path detection for copied/generated disclosure must include staged,
  branch, working-tree, and untracked files instead of letting one source hide
  another.
- Diff-size review advisories compare the review base with the complete working
  tree and add untracked regular files. The authored-source threshold excludes
  installed pack/Trellis mirrors, task/workspace records, and known generated
  reports; canonical `templates/**` sources remain included.
- Changed code that adds parser/structured-input, subprocess, path/filesystem,
  environment/global-state, or digest/integrity behavior emits one advisory
  naming the boundary-test matrix for author disposition. This sweep is
  deterministic and must never invoke a review provider.
- More than one changed Trellis task directory emits a soft scope warning so
  unrelated outcomes can be split before remote review.
- Trellis journal sessions present at the review base and older than the newest
  current session are append-only. Compare normalized session blocks against
  the base and fail when an older block changes, disappears, or is renumbered;
  newly appended/current sessions remain editable.
- Documentation scans intentionally inspect regular files only; symlinked docs
  are skipped so local or generated links do not expand outside the repo.
- Diff-scoped Trellis task checks inspect changed `implement.jsonl` and
  `check.jsonl` files after their task leaves planning: `in_progress`,
  `completed`, or archived. A changed qualifying `task.json` checks both
  sibling context files. Parsed records with an own `_example` key fail;
  planning scaffolds, untouched historical archives, and symlinked context
  files remain outside the check.

### 4. Validation & Error Matrix

- Node below 16.9 -> exit nonzero with a concise `requires Node >= 16.9.0`
  message.
- Symlinked script invocation -> run the same checks and print the normal
  summary.
- Untracked copied pack/Trellis surface -> report the copied/generated scope
  warning just like a staged or branch diff would.
- Malformed `.sd-ai-command-pack/review-preflight.json` -> fail the preflight
  without wiping the failure during result-buffer reset.
- Older Trellis journal session differs from the review base -> fail with the
  session number and direct the author to restore history and edit the intended
  current session by heading.
- Review-base Trellis journal session is deleted or renumbered -> fail as a
  historical-session removal, including when its journal file or the entire
  current workspace disappears.
- Changed in-progress/completed/archived context owns `_example` -> fail with
  the exact file and line plus replacement/removal guidance.
- Planning context, untouched archived context, or symlinked context -> skip
  without reading outside the repository.
- Added boundary-sensitive code -> warn with stable risk categories and the
  malformed input, command failure/timeout, path, environment, symlink/global
  state, and multiline/extension matrix; do not fail the gate.
- Installed mirrors or known generated reports dominate a large diff -> retain
  the total-size warning but exclude them from the authored-source threshold.
- Two changed task directories -> warn to confirm one reviewable outcome or
  split the work.

### 5. Good/Base/Bad Cases

- Good: `node scripts/check-review-preflight-link.mjs` points at the pack
  preflight and still runs the checks.
- Good: a new session is appended while all base sessions remain byte-equivalent
  after line-ending and trailing-whitespace normalization.
- Base: a clean repo with no changed paths reports a no-current-diff pass.
- Bad: a broad replacement updates a repeated fallback line in an older journal
  session while adding the intended current session.

### 6. Tests Required

- Script invocation through a symlink.
- Node-version helper coverage for below, at, and above the declared floor.
- Untracked copied-surface detection in a real Git fixture.
- Workspace index parsing with trailing whitespace.
- Historical-session comparison in a real Git fixture, including an appended
  session that leaves prior history unchanged, per-line trailing whitespace,
  renumbering, and deletion of a baseline journal file.
- Completed-status sibling checks, newly archived seed rejection, untouched
  archive grandfathering, planning scaffold allowance, and symlink skipping.
- Stable first-review risk categorization, authored-source exclusions, and
  multi-task directory extraction, plus a real Git fixture covering all three
  advisory types.
- Template twin byte identity.

### 7. Wrong vs Correct

```text
Wrong: import.meta.url === pathToFileURL(process.argv[1]).href
Correct: realpath(import.meta.url path) === realpath(process.argv[1])

Wrong: currentChangedPaths returns the first non-empty diff source
Correct: currentChangedPaths unions staged, branch, working-tree, and untracked paths

Wrong: replace the first repeated fallback sentence in a whole journal file
Correct: edit content inside the explicit current `## Session <n>:` block
```

## Session Recorder Retry Contract

### 1. Scope / Trigger

Use this contract when changing `scripts/sd-ai-command-pack-record-session.py`,
its template twin, or the `sd-finish-work` flow that calls it.

### 2. Signatures

- Command:
  `python3 scripts/sd-ai-command-pack-record-session.py --title ... --summary ... --change ... --test ...`
- Trellis dependency: `.trellis/scripts/add_session.py --no-commit`
- Commit behavior: the pack wrapper, not Trellis, stages
  `.trellis/workspace/<developer>/journal-*.md` plus sibling `index.md` and
  commits them as `chore: record journal` unless `--no-commit` is passed.

### 3. Contracts

- The wrapper may call Trellis `add_session.py` only when no modified
  workspace journal already has the requested title as its latest session
  heading.
- If a previous run appended the session but failed during the pack-owned
  staging or commit step, a retry must patch and commit that pending latest
  session instead of appending another one.
- Journal discovery must enumerate untracked files inside `.trellis/workspace/`
  (for example with `git status --untracked-files=all`) because local-only and
  fresh workspaces can otherwise collapse to `?? .trellis/workspace/` and hide
  the actual `journal-*.md` file.
- If more than one modified journal has the requested title as its latest
  session heading, fail closed with a clear error rather than guessing.
- The patcher anchors on session headings, commit hashes, and section headings;
  it must not depend on Trellis placeholder wording.

### 4. Validation & Error Matrix

- Unknown or duplicate commit hash -> exit `2` before touching the journal.
- Trellis append succeeds, later `git add` fails -> exit `1`, leave one
  pending session, and surface git output.
- Retry after the pending-session failure -> exit `0`, reuse the pending
  session, and keep a single journal entry.
- Retry after the pending-session failure with an untracked workspace -> same
  result: exit `0`, reuse the pending session, and keep a single journal entry.
- Multiple matching pending journals -> exit `1` and do not append.

### 5. Good/Base/Bad Cases

- Good: a sandbox or index-lock failure after append can be rerun safely.
- Base: a clean run appends, patches, verifies placeholders are absent, stages,
  and commits one journal/index pair.
- Bad: retrying a post-append failure calls `add_session.py` again and creates
  duplicate consecutive sessions.

### 6. Tests Required

- End-to-end happy path against a Trellis-bootstrapped scratch repo.
- Fail-fast validation for unknown, duplicate, and option-like commit hashes.
- Retry after synthetic `git add` failure proves no duplicate session is
  appended.
- Retry coverage must include both tracked and untracked `.trellis/workspace/`
  states.
- Template twin byte identity.

### 7. Wrong vs Correct

```text
Wrong: rerun add_session.py whenever the previous wrapper command exits nonzero
Correct: detect a modified latest same-title journal session and patch it

Wrong: rely on default git status output for a fully untracked .trellis/workspace/
Correct: enumerate untracked workspace files so journal-*.md remains visible

Wrong: search for "(see git log)" or "(Add test results)" before patching
Correct: replace hash-keyed commit rows and section bodies by structural anchors
```

## Toolchain Preflight Runtime Contract

### 1. Scope / Trigger

Use this contract when changing the distributed toolchain helper, SD workflow
instructions that select Python, or tests that execute dependency-sensitive
pack commands.

### 2. Signatures

- `bash scripts/sd-ai-command-pack-toolchain.sh doctor [--json]`
- `bash scripts/sd-ai-command-pack-toolchain.sh python [--require-module NAME]...`
- `bash scripts/sd-ai-command-pack-toolchain.sh run-python [--require-module NAME]... -- ARGS...`

### 3. Contracts

- Resolve Python once in documented precedence order; explicit overrides and
  an existing repo `.venv` are authoritative and never fall through after a
  failed probe.
- Require Python 3.10 or newer and probe requested modules before executing a
  workload. Resolution and `doctor` must not execute project workloads.
- `SD_AI_COMMAND_PACK_PROJECT_CHECK_COMMAND` is the only automatically selected
  project check. Make targets, package scripts, and executable conventional
  scripts are report-only candidates.
- Keep the helper compatible with macOS Bash 3.2, quote paths, avoid `eval`,
  and support both `.venv/bin/python` and `.venv/Scripts/python.exe`.
- Report project checks, the pack full-check, and optional AI review as
  separate verification lanes.

### 4. Validation & Error Matrix

- Invalid CLI or module name -> exit `2` without selecting a tool.
- No supported Python -> exit `3` with the Homebrew Python 3.13/setup remedy.
- Invalid selected interpreter, unsupported version, or missing module -> exit
  `4`, identify the selected source, and do not try another interpreter.
- Valid `run-python` request -> probe once, then execute the workload once with
  the selected interpreter.
- Recursive project-check candidate -> report it as recursive and never invoke
  it from the full-check lane.

### 5. Good / Base / Bad Cases

- Good: a repo `.venv` lacking `coverage` produces one actionable failure and
  no Apple/Xcode Python retry.
- Base: `doctor --json` reports a supported interpreter and zero or more
  project-check candidates without changing the repo.
- Bad: trying `python3`, Homebrew Python, and `uv run` in sequence after each
  fails, or executing an inferred `make check` that recursively calls the pack
  full-check.

### 6. Tests Required

- Explicit override, repo `.venv`, active virtualenv, Homebrew, PATH fallback,
  Windows-style virtualenv, unsupported version, and missing-module fixtures.
- Probe/workload invocation counts and authoritative-candidate stop behavior.
- Non-mutating Makefile, package-script, executable-script, ambiguity, and
  recursive-candidate discovery.
- Installer, removal, provenance, manifest, executable-mode, and root/template
  parity coverage.

### 7. Wrong vs Correct

```text
Wrong: python3 check.py || /opt/homebrew/bin/python3.13 check.py || uv run check.py
Correct: sd-ai-command-pack-toolchain.sh run-python --require-module coverage -- check.py

Wrong: infer one project check and run it during doctor
Correct: report candidates; run only an explicitly configured or repo-documented check
```

## Shipped Script Coverage Gate Contract

### 1. Scope / Trigger

Use this contract when changing Python helper tests, `.coveragerc`,
`.github/scripts/run-tests.sh`,
`.github/scripts/check-shipped-script-coverage.sh`, `make test`, or the CI
unittest coverage lane.

### 2. Signatures

- `PYTHON_BIN=<python> bash .github/scripts/check-shipped-script-coverage.sh`
- CI command: `bash .github/scripts/check-shipped-script-coverage.sh`
- Local command: `make test`

### 3. Contracts

- The installer coverage gate remains a separate 100% line-and-branch floor for
  `install.py,installer/*`.
- The shipped-script gate runs both the aggregate
  `scripts/sd-ai-command-pack-*.py` floor and a per-file floor for every
  shipped Python helper.
- Every tracked `scripts/sd-ai-command-pack-*.py` helper must appear exactly
  once in `.github/scripts/check-shipped-script-coverage.sh` with an integer
  floor.
- The helper must resolve and `cd` to the repository root before choosing a
  Python interpreter or checking helper paths, matching other `.github/scripts`
  entry points.
- Floors should be set at or just below current measured coverage and ratcheted
  upward when focused tests improve a helper. Do not lower a floor to hide a
  real regression.
- The helper honors `PYTHON_BIN`, then `.venv/bin/python`, then `python3` so
  direct local runs avoid Apple/Xcode Python when the repo venv exists.

### 4. Validation & Error Matrix

- Missing helper listed in the coverage gate -> nonzero with the missing path.
- Helper coverage below its floor -> nonzero from `coverage report` for that
  helper.
- Aggregate shipped-script coverage below 76% -> nonzero before per-file
  reports.
- New shipped Python helper without a listed floor -> unit test failure.

### 5. Good/Base/Bad Cases

- Good: a fleet-preflight CLI test raises that script's measured coverage and
  the floor is ratcheted upward.
- Base: unrelated test changes leave all aggregate and per-file floors passing.
- Bad: one helper drops below its floor while the aggregate total remains above
  76% and CI still passes.

### 6. Tests Required

- CLI behavior tests for helper surfaces that automation invokes directly.
- A drift test proving every shipped Python helper has a per-file floor.
- A wiring test proving `make test` and CI call the shared coverage helper.

### 7. Wrong vs Correct

```text
Wrong: rely only on TOTAL coverage for scripts/sd-ai-command-pack-*.py
Correct: run aggregate coverage plus one fail-under report per shipped helper

Wrong: python3 -m coverage report ...
Correct: PYTHON_BIN=.venv/bin/python bash .github/scripts/check-shipped-script-coverage.sh
```

## Required Patterns

- Use `pathlib.Path` for filesystem work.
- Keep pack files declared in `manifest.json`.
- The pack-source full-check env-var documentation gate must scan both shipped
  scripts and shipped skill templates. A `SD_AI_COMMAND_PACK_*` variable that
  appears only in `templates/.agents/skills/**/SKILL.md` is still user-facing
  and must be documented in `docs/SD_AI_COMMAND_PACK.md`.
- Gate SD pack-source assumptions on the parsed manifest name, not generic
  installer paths. Other installer repositories must skip SD-only checks, while
  malformed manifests that assert the SD identity fail without a traceback.
- Validate manifest paths before deriving target destinations or anchors.
- Treat Windows drive/root anchors and backslash-separated parent traversal as
  unsafe manifest paths, even when tests run on POSIX.
- Validate resolved pack source paths so template symlinks cannot escape the
  pack root.
- Validate resolved write and backup paths so target-repo symlinks cannot
  redirect installer writes outside the target repo.
- Reject occupied non-file target paths with a controlled installer error.
- Keep platform selection behavior covered by tests when adding adapters or
  install modes.
- Run `git diff --check` against installed target paths after writes unless
  `--skip-diff-check` is requested.
- Keep force-overwrite behavior covered by tests, including backup behavior
  when `--backup` is used.

## Testing Requirements

Run the installer tests with:

```bash
python3 -m unittest discover -s tests
```

CI must fail when `unittest` reports skipped tests, even though local skipped
tests remain friendly for missing developer tools. The required CI aggregate
also includes Ruff, pinned in `requirements-dev.txt`, over `install.py`,
`installer/`, `scripts/`, `templates/scripts/`, and `tests/`; a macOS unittest
leg protects BSD-tool and bash-3.2 behavior that Ubuntu cannot exercise.

Add or update tests when changing:

- CLI flags or argument behavior
- conflict and force handling
- backup behavior
- platform selection and anchor rules
- manifest path validation
- template paths or manifest semantics

## Code Review Checklist

- Does the change preserve existing target files by default?
- Are manifest `source`, `target`, and `anchor` paths validated before any
  file writes?
- Are resolved pack source paths still inside the pack root?
- Are resolved destination and backup paths still inside the target repo?
- Do occupied directories, broken symlinks, and other non-file target paths
  fail without a traceback?
- Are new templates listed in `manifest.json` and documented in `README.md`?
- Do tests exercise the behavior through the CLI, not only helper functions?
- Does the installer still work with only Python 3.10+ stdlib dependencies?
- Is terminal output concise and stable enough for users to understand failures?
