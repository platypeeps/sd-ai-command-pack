# Design — Consolidate git invocation (A-076, full scope)

## Scope / trigger

Parent AC4 (`07-28-consolidate-shared-script-helpers`): no script builds a
git-specific subprocess environment of its own. A planning adversarial review
(host + Codex, 2026-08-05) found the original "two bypasses" framing incomplete
and its AC4 grep gate invalid. The user chose **full scope**. This document
replaces that framing.

## What AC4 actually means (resolves review C-2 and C-6)

Neither a raw `subprocess.(run|Popen)` grep nor a git-argv-**presence** grep is
a valid gate. The subprocess grep matches deliberate non-git subprocesses
(`taskkill` review-local:1465, provider `Popen` review-local:1695,
`sys.executable` surface-check:616/674). The git-argv-presence grep is worse: it
false-positives on every file that **correctly** routes git through the library
by passing `["git", ...]` to `lib.run_command` — `audit-inventory.py:111`,
`check.py:249/273` (`_git_bytes`/`_git_optional_bytes`), `review.py:557`
(`_worktree_digest`), `record-session.py:470`, plus the generic runners. Those
are the *intended* consolidated end state, not violations.

The distinction AC4 actually draws is **direct-subprocess-git**: a
`subprocess.run(...)` / `subprocess.Popen(...)` whose command argument is a git
command literal (`["git", ...]`, `["git", *args]`, `["git", "-C", ...]`). Only
the shared library may do that. Three code shapes exist:

1. **Direct-subprocess-git — VIOLATION** — the migration targets: they call
   `subprocess.run(["git", ...])` themselves, hand-building env/flags. Route
   through the library helpers.
2. **Generic shared-env runner — ALLOWLISTED** — `pr-eligibility.run_command`,
   `status.run_command`, `fleet-candidate-check.run_command` call
   `subprocess.run(command, ...)` where `command` is a **variable** argv (git
   incidental) after `build_tool_environment`. Their `subprocess.run` first arg
   is not a git literal, so the AST gate passes them naturally; they are named
   in the allowlist only for documentation.
3. **Library-delegating git caller — NOT A VIOLATION, no change** —
   audit-inventory, check.py, review.py, record-session pass a `["git", ...]`
   literal to `lib.run_command` (never to `subprocess.run`). Already consolidated.

### AC4 gate (rewritten — AST, not grep)

`tests/test_git_invocation_boundary.py` runs two AST checks (resolves C-6, C-9;
supersedes the unsound C-17 runner-sink rule — see C-18). A runner-sink rule
that demands every git literal be a *direct* argument to an allowed runner is
**unsound**: it red-flags legitimate code that assigns a command to a variable
before `run_command` (fleet-candidate-check.py:157/183/208) or threads it
through a row helper (check.py:1038/1044 → `command_row`). Statically telling
"assigned → run_command" (fine) from "assigned → subprocess.run" (bad) needs
taint analysis, not a lint. The two sound checks:

1. **Check 1 — direct-subprocess-git (repo-wide).** Over every `scripts/*.py`,
   walk each `Call` to `subprocess.run`/`subprocess.Popen`; flag one whose first
   positional arg is a git-argv literal (an `ast.List`/`ast.Tuple` with
   `Constant "git"` first, or `["git"] + …`). Assert flagged calls exist **only**
   in `sd_ai_command_pack_lib.py`. Verified against the current tree: this flags
   exactly the six migration-target files and has **zero** false positives on
   the seven library-delegating / generic-runner files (whose `subprocess.run`
   first arg is a variable). Post-migration it is green everywhere but the lib.
2. **Check 2 — no git literal in the six migrated files (targeted).** For
   `review-local`, `surface-check`, `install-audit`, `work-loop`,
   `fleet-controller`, `fleet-publish`, assert no `["git", …]` literal appears at
   all. Post-migration these reach git only through the helpers, so any residual
   literal — including one handed to a local wrapper like fleet-publish's old
   `run(["git", …])`, which Check 1 alone misses because that `run`'s own
   `subprocess.run(list(argv))` takes a variable — fails. This is the sound way
   to close the fleet-publish indirection that motivated C-9.

A `{filename: rationale}` note for the three generic runners is printed on
failure. Stated residual limitation (deferred to human review, not hidden): a
brand-new seventh script that both defines its own subprocess wrapper *and*
feeds it git through a variable evades both static checks; a fully dynamic argv
(`["gi"+"t", …]`) likewise. Catching those requires taint analysis beyond a
lint-style boundary test. This pair replaces the invalid raw/presence greps and
the unsound runner-sink rule in every artifact.

## R1 — library git paths (crux)

Add a shared low-level core plus two public wrappers. The wrappers **do not
convert exceptions** — they centralize environment construction and the
`subprocess.run` call, and let `OSError`/`TimeoutExpired`/`CacheSetupError`
propagate so each caller keeps its own error policy verbatim (resolves C-3).

```python
def _run_git_process(
    args, *, environment, cwd, timeout, binary, input, stderr, encoding, errors,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=dict(environment), check=False,
        stdout=subprocess.PIPE, stderr=stderr,
        input=input, text=not binary,
        encoding=None if binary else encoding,   # None => platform locale
        errors=None if binary else errors,        # None => Python default "strict"
        timeout=timeout,                          # None => no timeout
    )

@overload  # binary=False -> CompletedProcess[str]; binary=True -> [bytes]
def run_git_minimal(args, *, cwd=None, timeout=None, binary=False, input=None,
                    stderr=subprocess.PIPE, encoding=None, errors=None): ...
def run_git_minimal(args, *, cwd=None, timeout=None, binary=False, input=None,
                    stderr=subprocess.PIPE, encoding=None, errors=None):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return _run_git_process(args, environment=env, cwd=cwd, timeout=timeout,
                            binary=binary, input=input, stderr=stderr,
                            encoding=encoding, errors=errors)

def run_git_cached(args, *, repo, cwd=None, timeout=None, binary=False,
                   input=None, stderr=subprocess.PIPE, encoding=None, errors=None):
    env, _, _ = build_tool_environment(repo=repo)  # may raise CacheSetupError
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return _run_git_process(args, environment=env, cwd=cwd, timeout=timeout,
                            binary=binary, input=input, stderr=stderr,
                            encoding=encoding, errors=errors)
```

`run_git_cached` separates `repo` (the repository whose cache namespace
`build_tool_environment` prepares) from `cwd` (the child process working
directory), because install-audit and work-loop build cache for the repo but
launch git with `git -C <repo>` and **no** child `cwd` (resolves C-14). They
pass `repo=<root>, cwd=None` and keep their `-C` argv unchanged; `run_git_minimal`
keeps a single `cwd` (its callers already pass one or use `-C`).

Parameter defaults are chosen so an unspecified call reproduces bare
`subprocess.run(["git", ...], text=True)` behavior — **no** timeout, locale
decoding, `strict` errors, captured `PIPE` stderr. Every migrated caller passes
its *exact* current values rather than relying on a helper-imposed default
(resolves C-4/C-5/C-11/C-12):

- `timeout` — `None` default means no timeout is imposed. Sites that had one pass
  it (review-local `_git`=60, surface-check=60, install-audit=`GIT_TIMEOUT_SECONDS`,
  work-loop=20, fleet-controller=10); sites that had none (`_artifact_root`,
  fleet-publish) pass `None`, so migration adds no new `TimeoutExpired` path.
- `encoding`/`errors` — default `None` = platform locale + strict, matching the
  bare `text=True` callers (review-local, fleet-controller, fleet-publish,
  `_artifact_root`). Only work-loop overrides (`encoding="utf-8"`,
  `errors="strict"`) because it set those explicitly today. No caller gains a
  forced-UTF-8 decode that could raise on non-UTF-8 output.
- `stderr` — default `PIPE` (review-local/surface-check keep captured detail);
  install-audit and work-loop pass `DEVNULL`; fleet-publish passes
  `subprocess.STDOUT` to preserve its merged-stream `PublishError` message.
  `subprocess.run` drains a `PIPE` fully, so no choice can deadlock.

- `run_git_minimal`: cache-free, `GIT_TERMINAL_PROMPT=0`. For sites that today
  run git with a minimal/no env. Propagates `OSError`/`TimeoutExpired`.
- `run_git_cached`: cache-backed (`build_tool_environment`), for sites that today
  use it. Propagates `CacheSetupError`/`OSError`/`TimeoutExpired`.
- Neither raises on a non-zero return code; callers inspect `returncode`.
- `input`/`binary` support the NUL-stdin bytes contract (install-audit).
- **Global hardening:** `build_tool_environment` gets
  `environment.setdefault("GIT_TERMINAL_PROMPT", "0")` so every shared-env caller
  (the generic runners too) inherits prompt suppression without overriding an
  explicit value.
- The existing `run_git` (str, via `run_command`, no prompt flag before this
  change) stays for the delegating adapters (record-session, pr-body-scope,
  review-learnings) that already use it — unchanged except it now inherits
  `GIT_TERMINAL_PROMPT=0` from `build_tool_environment`.

## R2 — per-site migrations (exact semantics preserved)

| Site (file) | New call | Preserved behavior |
|---|---|---|
| `review-local._git` (tmpl 549) | `run_git_minimal(args, cwd=repo, timeout=GIT_TIMEOUT_SECONDS, binary=binary)` | str/bytes overloads; `except TimeoutExpired`→`ReviewInputError` (keeps `TimeoutExpired.stderr`); spawn `OSError` still escapes (helper does not catch it); non-zero → `ReviewInputError`; locale decode (encoding default `None`) |
| `review-local._artifact_root` (tmpl 1334) | `run_git_minimal([...], cwd=repo, timeout=None, binary=True)` | **no timeout** + **`binary=True`** (current is bytes with no decoding — `binary=True` preserves that and removes any decode-failure path, C-15); logic reads only `returncode`; `returncode != 0 → ReviewInputError("must be ignored by Git")`; keep `check-ignore -q --` argv. Minor: raw git stderr no longer echoes to the terminal on the rare error path (returncode-only logic and the exception message are unchanged) |
| `surface-check._run_git` (tmpl 127) | `run_git_minimal(args, cwd=root, timeout=60, binary=True)` | `except (OSError, TimeoutExpired)`→None/`SurfaceInputError`; bytes; `optional`; adds `GIT_TERMINAL_PROMPT=0` (safe; read-only) |
| `install-audit.gitignored_paths` (tmpl 590) | `run_git_cached([...], repo=root, cwd=None, binary=True, input=payload, stderr=DEVNULL, timeout=GIT_TIMEOUT_SECONDS)` | **`repo=root, cwd=None`** — keep `git -C root` argv, add no child cwd (C-14); `except (CacheSetupError, OSError, TimeoutExpired)`→`set()`; rc∈{0,1}; NUL stdin; bytes split |
| `work-loop.run_git` (tmpl 237) | `run_git_cached([...], repo=repo, cwd=None, timeout=20, stderr=DEVNULL, encoding="utf-8", errors="strict")` | **`repo=repo, cwd=None`** — keep `git -C repo` argv, add no child cwd (C-14); `->str|None`; explicit utf-8/strict (matches current); `except CacheSetupError → WorkLoopError` (keep message shaping); `(OSError, UnicodeError, TimeoutExpired)`→None; **do not touch ~10 call sites** |
| `fleet-controller` ×3 (src 1670/1677/1684) | `run_git_minimal([...], cwd=None, timeout=10)` | keep `git -C path` argv, add no child cwd (C-14); locale decode; replace `check=True`+`except (OSError, SubprocessError)` with the same `except` **plus** `if returncode != 0: return result` (identical observable "failure → unchanged result"; `TimeoutExpired` is a `SubprocessError`, still caught) |
| `fleet-publish` git via `run` (src 118/124/233/234/379) | new `git_run(argv, *, cwd)` → `run_git_minimal(list(argv), cwd=cwd, timeout=None, stderr=subprocess.STDOUT)` | **`cwd` threaded from each caller** (`git_out`/`porcelain`=`cwd`, `work_commit`/push=`repo`) — C-16; **no timeout**; `stderr=STDOUT` preserves merged-output ordering; locale decode; on `returncode != 0` raise `PublishError(f"command failed (git {' '.join(argv)}): {detail}", code=2)` — **note the literal `git ` prefix** so the message matches today's full-argv form (C-16); **push/commit now prompt-disabled** |

`work-loop`'s adapter migration resolves review C-4 by **choosing migration**:
the adapter becomes a thin wrapper over `run_git_cached`, so all git env
construction lives in the library while the `->str|None` swallowing contract and
its ~10 call sites are untouched.

## R3 — generic runners (allowlisted; optional delegation)

`pr-eligibility.run_command`, `status.run_command`, and
`fleet-candidate-check.run_command` already build the shared env via
`build_tool_environment` and run arbitrary argv. They are **allowlisted**, not
migrated. Optional cleanup (separate, behavior-identical): have each delegate to
`lib.run_command` behind its local `CommandResult` adapter — deferred, and only
if observ­ably identical (return type, `errors="strict"`, DEVNULL stderr,
`PYTHONDONTWRITEBYTECODE`). Not required for AC4.

## R4 — untouched

`pr-body-scope._run_git` keeps its `CommandError → (124, "", str)` shaping;
record-session / review-learnings adapters keep delegating to `run_git`.

## Source model (resolves the "no templates twin" question)

- `templates/scripts/` → synced to `scripts/`: lib, review-local, surface-check,
  install-audit, work-loop, pr-eligibility, status. Edit the template; `make
  sync` regenerates the twin byte-identically.
- **Source-only in `scripts/`** (per `docs/SD_AI_COMMAND_PACK.md:1390`):
  `fleet-controller.py`, `fleet-publish.py`, `fleet-candidate-check.py`. Edit in
  place; `make sync` does not overwrite them.

## Sync / rollback (resolves review C-5, C-13)

The real sync mechanism is `make sync`, which is two steps (`Makefile:31`):
`install.py . --force` (regenerates the dogfood `scripts/` twins from
`templates/`) and `update-spec-kb.py`. There is **no**
`scripts/sd-ai-command-pack-sync.py`; the earlier design draft invented it. Use
`make sync`.

- The KB step writes through this checkout's `.obsidian-kb` symlink into an
  external vault. That write is idempotent and the KB path is **gitignored**, so
  it produces no tracked-worktree change and cannot corrupt the parity check.
  The earlier "avoid `make sync` / no external state" framing was wrong on both
  counts — name the side effect, don't fight it.
- Parity check after `make sync`: `git diff --stat -- scripts/ templates/scripts/`
  shows only the intended synced twins, and each `scripts/` twin is
  byte-identical to its `templates/scripts/` source. `fleet-controller.py` and
  `fleet-publish.py` are source-only (no template twin) — `install.py . --force`
  does not overwrite them; they are edited directly and appear as their own
  diffs.
- Rollback: `git checkout -- <edited templates + regenerated twins + the two
  source-only files + the boundary test>`. No data migration. The external KB is
  idempotent and needs no rollback.

## Compatibility / versioning

Behavior-preserving internal refactor; no CLI/JSON/payload contract change. If
`make test`'s shipped-surface gate reports a payload digest change, bump
`manifest.json` and restamp `docs/fleet/candidate-validation.json` via
`prepare-release.py`. Let the gate decide.

## Concern ledger disposition (round 1 → this revision)

- **C-1 addressed** — full inventory: 6 git-specific files / 13 git-argv call
  sites (review-local ×2, surface-check ×1, install-audit ×1, work-loop ×1,
  fleet-controller ×3, fleet-publish ×5) + `input=`/`binary` in the helpers.
- **C-2 addressed** — AC4 redefined semantically with a git-argv gate + named
  allowlist + a committed boundary test.
- **C-3 addressed** — wrappers propagate `OSError`/`TimeoutExpired` instead of
  collapsing them, so each caller's exact error policy (incl. review-local's
  `TimeoutExpired.stderr` and escaping spawn `OSError`) is preserved.
- **C-4 addressed** — work-loop adapter migrates to wrap `run_git_cached`;
  decision recorded; call sites untouched.
- **C-5 addressed** — targeted parity check replaces `make sync` reliance;
  external-KB side effect named; rollback corrected.
- **C-6 addressed (remediation round found by host review)** — the first-pass
  AC4 gate keyed on git-argv *presence*, which false-positives on the four
  library-delegating callers (audit-inventory, check.py ×2, review.py,
  record-session) that already route git through `lib.run_command`. Gate
  rewritten to an AST direct-subprocess-git check. Inventory re-verified against
  the full set of files that call `subprocess.run/Popen` directly (lib +
  install-audit, review-local, surface-check, work-loop, pr-eligibility, status,
  fleet-candidate-check, fleet-controller, fleet-publish); the 6 git-specific
  direct-subprocess files match the migration list exactly, with the 3 generic
  runners allowlisted — no further sites exist.
- **C-7 addressed (host review)** — helpers take a `stderr` parameter (default
  `PIPE`); install-audit and work-loop pass `DEVNULL` to preserve their current
  stderr suppression exactly. `subprocess.run` drains `PIPE` fully, so no caller
  deadlocks on either choice.

### Remediation round 1 — Codex lane (C-8..C-13)

- **C-8 addressed** — the "7 sites" count conflated files with argv sites.
  Restated everywhere as 6 git-specific files / 13 git-argv call sites
  (fleet-publish is 5 argv sites, not 1).
- **C-9 addressed** — a first-arg-only AST scan misses indirection like
  fleet-publish's `subprocess.run(list(argv))`. Gate strengthened with a second
  check: the six migrated files must contain no `["git", ...]` literal at all
  (they reach git only through the helpers). See "AC4 gate".
- **C-10 addressed** — fleet-publish migration now passes `timeout=None`
  (current has none; avoids leaking `TimeoutExpired` on a slow push) and
  `stderr=subprocess.STDOUT` (preserves merged-output ordering in the
  `PublishError` message), raising `PublishError(<last non-empty stdout line>)`
  on non-zero — the current shape.
- **C-11 addressed** — helper `timeout` now defaults to `None`, so
  `_artifact_root` (and fleet-publish) migrate with no imposed timeout, matching
  their current no-timeout calls; timed sites pass their exact value.
- **C-12 addressed** — helper no longer forces UTF-8/strict. `encoding`/`errors`
  default `None` (platform locale + strict), matching the bare `text=True`
  callers (review-local, fleet-controller, fleet-publish, `_artifact_root`);
  only work-loop passes explicit `utf-8`/`strict`, as it does today. No new
  decode-failure path on non-UTF-8 output.
- **C-13 addressed** — the invented `scripts/sd-ai-command-pack-sync.py` is
  removed; the real sync is `make sync` (`install.py . --force` + KB). The KB
  write is idempotent and gitignored, so it does not affect the parity check;
  the earlier "avoid make sync" framing is corrected. See "Sync / rollback".

### Remediation round 2 — Codex lane (C-14..C-17)

- **C-14 addressed** — `run_git_cached` now takes separate `repo` (cache
  namespace) and `cwd` (child dir). install-audit and work-loop pass
  `repo=<root>, cwd=None` and keep their `git -C` argv, adding no child cwd;
  fleet-controller keeps `git -C` with `cwd=None`. Callers that already passed
  `cwd` (review-local ×2, surface-check, fleet-publish) keep it.
- **C-15 addressed** — `_artifact_root` migrates with `binary=True`, matching its
  current bytes/no-decode call and eliminating the text-decode path the prior
  draft introduced. Logic reads only `returncode`; the sole residual difference
  (raw git stderr no longer echoing to the terminal on error) is documented and
  behavior-neutral to the code.
- **C-16 addressed** — fleet-publish's `git_run` (a) takes an explicit `cwd`
  threaded from each caller (`git_out`/`porcelain`=`cwd`, `work_commit`/push
  =`repo`) instead of a bare `repo`, and (b) formats the `PublishError` with a
  literal `git ` prefix (`command failed (git {argv})`) so the message matches
  today's full-argv output.
- **C-17 superseded (was: runner-sink rule) — see C-18.** The round-2 attempt to
  make the gate repo-wide via a runner-sink rule was itself defective; it is
  withdrawn.

### Remediation round 3 — Codex lane (C-18)

- **C-18 addressed** — the C-17 runner-sink rule is **unsound**: it flags
  legitimate code that assigns a git command to a variable before `run_command`
  (fleet-candidate-check.py:157/183/208) or routes it through a row helper
  (check.py:1038/1044), so the boundary test would be red on the current, valid
  repository. Reverted to the sound two-check gate (Check 1 direct-subprocess-git
  repo-wide + Check 2 no-git-literal in the six migrated files). Proven against
  the current tree: Check 1 flags exactly the six migration targets with zero
  false positives on the seven delegating/generic-runner files. The
  deliberate-indirection residual (a new self-wrapping script, or fully dynamic
  argv) is documented and deferred to human review — a bound no static lint can
  close without taint analysis. See "AC4 gate".
