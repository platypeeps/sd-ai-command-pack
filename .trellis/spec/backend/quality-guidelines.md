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
- Documentation scans intentionally inspect regular files only; symlinked docs
  are skipped so local or generated links do not expand outside the repo.

### 4. Validation & Error Matrix

- Node below 16.9 -> exit nonzero with a concise `requires Node >= 16.9.0`
  message.
- Symlinked script invocation -> run the same checks and print the normal
  summary.
- Untracked copied pack/Trellis surface -> report the copied/generated scope
  warning just like a staged or branch diff would.
- Malformed `.sd-ai-command-pack/review-preflight.json` -> fail the preflight
  without wiping the failure during result-buffer reset.

### 5. Good/Base/Bad Cases

- Good: `node scripts/check-review-preflight-link.mjs` points at the pack
  preflight and still runs the checks.
- Base: a clean repo with no changed paths reports a no-current-diff pass.
- Bad: a symlinked invocation exits `0` with no output, or an untracked copied
  adapter is invisible to the copied/generated disclosure check.

### 6. Tests Required

- Script invocation through a symlink.
- Node-version helper coverage for below, at, and above the declared floor.
- Untracked copied-surface detection in a real Git fixture.
- Workspace index parsing with trailing whitespace.
- Template twin byte identity.

### 7. Wrong vs Correct

```text
Wrong: import.meta.url === pathToFileURL(process.argv[1]).href
Correct: realpath(import.meta.url path) === realpath(process.argv[1])

Wrong: currentChangedPaths returns the first non-empty diff source
Correct: currentChangedPaths unions staged, branch, working-tree, and untracked paths
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
- Template twin byte identity.

### 7. Wrong vs Correct

```text
Wrong: rerun add_session.py whenever the previous wrapper command exits nonzero
Correct: detect a modified latest same-title journal session and patch it

Wrong: search for "(see git log)" or "(Add test results)" before patching
Correct: replace hash-keyed commit rows and section bodies by structural anchors
```

## Required Patterns

- Use `pathlib.Path` for filesystem work.
- Keep pack files declared in `manifest.json`.
- The pack-source full-check env-var documentation gate must scan both shipped
  scripts and shipped skill templates. A `SD_AI_COMMAND_PACK_*` variable that
  appears only in `templates/.agents/skills/**/SKILL.md` is still user-facing
  and must be documented in `docs/SD_AI_COMMAND_PACK.md`.
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
