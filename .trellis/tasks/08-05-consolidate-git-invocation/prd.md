# Consolidate git invocation into the shared library (A-076)

## Goal

Route every script's git invocation through the shared library so no script
builds a git environment of its own (AC4 of the parent task
`07-28-consolidate-shared-script-helpers`).

This is the fourth of four clusters from that parent task. Clusters A-085
(atomic write) and A-080 (cache-env key set) shipped in release 0.64.16. This
cluster was split out because migrating the true bypasses onto the library's
`run_git` is **not mechanical** — the library's git path has two properties the
bypasses must not inherit blindly.

## Confirmed evidence (re-derived 2026-08-05)

### The library git path forces cache setup and disables no prompt

`sd_ai_command_pack_lib.run_git` → `run_command` →
`build_tool_execution_plan` → `build_tool_environment`. So any call through the
library **requires a writable cache root** and raises `CacheSetupError` when
none is available. The library also does **not** set `GIT_TERMINAL_PROMPT=0`.

The two true bypasses currently avoid both: they run git with a minimal
environment and no cache dependency.

- `sd-ai-command-pack-review-local.py:541` `_git(repo, *args, binary=False)` —
  `env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}`, `text=not binary` (str/bytes
  overloads), raises `ReviewInputError` on timeout. `grep -c run_git_command`
  returns 0.
- `sd-ai-command-pack-surface-check.py:125`
  `_run_git(root, args, *, optional=False) -> bytes | None` — bytes return.
  `grep -c run_git_command` returns 0.

Naively repointing these onto `run_git` would (a) add a cache-setup failure mode
to review/surface-check git calls and (b) lose `GIT_TERMINAL_PROMPT=0` (hang
risk). Both changes are behavior-altering and must be handled deliberately.

### work-loop keeps its adapter (do NOT repoint its call sites)

`sd-ai-command-pack-work-loop.py:237` `run_git(repo, *args) -> str | None` never
raises: `OSError`, `UnicodeError`, `TimeoutExpired`, and any non-zero exit all
become `None`, and it uses `errors="strict"`. About ten call sites
(`resolve_repository:237`, `:1315`, `:2525`, `:2847`, and others) read `None` as
"unavailable". The library's `run_git` raises and defaults to `errors="replace"`
(non-UTF-8 → mojibake instead of a raise). Keep work-loop's swallowing adapter
as a thin wrapper over the library call; preserve `errors="strict"`. Rewriting
its ~10 call sites' error handling is out of scope.

### The three delegating adapters already use the library

`record-session.py` `run_git`, `pr-body-scope.py` `_run_git`, and
`review-learnings.py` `_run_git` already import `run_git as run_git_command` and
delegate to the library — they are signature adapters, not bypasses, and do not
violate AC4. `pr-body-scope`'s `CommandError` → `(124, "", str(exc))` flattening
is error shaping the library does not do and must be kept. Collapsing these to
shared shapes is optional cleanup, not AC4-required.

## Requirements

- R1: Add a library git path that runs git with a minimal, prompt-disabled
  (`GIT_TERMINAL_PROMPT=0`) environment **without** forcing cache setup, and can
  return bytes as well as text. Decide whether this is a new helper (e.g.
  `run_git_minimal`) or a flag on `run_git` / `run_command` that skips
  `build_tool_environment`. Setting `GIT_TERMINAL_PROMPT=0` in the shared git
  environment is a safe global improvement to consider.
- R2: Migrate `review-local.py:_git` (preserve str/bytes overloads and
  `ReviewInputError`-on-timeout) and `surface-check.py:_run_git` (preserve bytes
  return and the `optional` semantics) onto that library path.
- R3: Keep work-loop's `-> str | None` swallowing adapter and its
  `errors="strict"`; do not touch its ~10 call sites.
- R4: Preserve `pr-body-scope`'s `CommandError` → `(124, "", str(exc))`
  flattening. Adapter collapse (R5) is optional and must not change observable
  behavior.
- R5 (optional): collapse the three delegating adapters onto shared shapes with
  a per-script error adapter via `context=`.

## Acceptance criteria

- AC4: `grep -rnE 'subprocess\.(run|Popen)\(' scripts/*.py` shows git
  invocations only in `sd_ai_command_pack_lib.py` and work-loop's adapter. No
  other script builds a git environment.
- AC-regression: review-local and surface-check git behavior (str/bytes,
  timeout handling, prompt disabled, no new hard cache-setup dependency in
  contexts that previously worked) is preserved. Full test suite and template
  parity green.

## Boundaries

Complex task — needs `design.md` and `implement.md` before start. The library
git-path design (R1) is the crux; resolve it before migrating callers.
