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

## Scope correction — 2026-08-05 (adversarial review → full scope re-plan)

The "two true bypasses" evidence below is **incomplete**. A planning adversarial
review (host + Codex) found git-subprocess sites across multiple files and five
blocking concerns (C-1..C-5). The user selected **full scope**: migrate every
git-**specific** invocation site.

`design.md` and `implement.md` have been rewritten to full scope. The resolved
inventory is **6 git-specific files / 13 git-argv call sites** to migrate:
`review-local._git` + `_artifact_root` (×2), `surface-check._run_git` (×1),
`install-audit.gitignored_paths` (×1), `work-loop.run_git` (×1),
`fleet-controller` (×3), `fleet-publish` (×5 argv sites via its `run` wrapper),
plus **3 generic shared-env runners** that are allowlisted rather than migrated
(`pr-eligibility.run_command`, `status.run_command`,
`fleet-candidate-check.run_command`). C-1..C-5 dispositions are recorded in
`design.md` → "Concern ledger disposition". Re-run the planning adversarial
review before `task.py start`.

The requirements below (R1–R5) are superseded by `design.md`'s R1–R4 and the
`design.md` AC4 definition; they are retained only for provenance.

## Acceptance criteria

- AC4: a committed **AST** boundary test
  (`tests/test_git_invocation_boundary.py`) — not a raw or git-argv-presence
  grep — proves that only `sd_ai_command_pack_lib.py` calls
  `subprocess.run`/`subprocess.Popen` with a git command **literal**. The three
  generic shared-env runners (`pr-eligibility.py`, `status.py`,
  `fleet-candidate-check.py`) pass naturally (variable argv) and are documented
  in an allowlist; library-delegating callers that pass `["git", ...]` to
  `lib.run_command` (audit-inventory, check.py, review.py, record-session) are
  the intended consolidated pattern, not violations. All git-specific
  direct-subprocess sites route through the library helpers (`run_git_minimal` /
  `run_git_cached`). See `design.md` → "AC4 gate".
- AC-regression: each migrated caller's exact error/return semantics are
  preserved — review-local's str/bytes overloads, `TimeoutExpired.stderr`, and
  escaping spawn `OSError`; surface-check's bytes/`optional`; install-audit's
  `set()`-on-failure + rc∈{0,1} + NUL stdin; work-loop's `->str|None` swallowing
  + `errors="strict"` + `CacheSetupError→WorkLoopError` (call sites untouched);
  fleet-controller's failure-value; fleet-publish's `PublishError`. No new hard
  cache-setup dependency on the minimal-env paths. Full test suite and template
  parity green.

## Boundaries

Complex task — needs `design.md` and `implement.md` before start. The library
git-path design (R1) is the crux; resolve it before migrating callers.
