# Implement — Consolidate git invocation (A-076, full scope)

Execution by cluster. Edit `templates/scripts/` (source) first for synced files,
then `make sync` regenerates twins. Source-only files (`fleet-controller.py`,
`fleet-publish.py`) edit in place under `scripts/`. Validate after each cluster.
Do not run `task.py start` until the planning adversarial review passes (see
Review gates).

## Cluster 1 — library git paths (`sd_ai_command_pack_lib.py`)

File: `templates/scripts/sd_ai_command_pack_lib.py`.

1. Add `_run_git_process(args, *, environment, cwd, timeout, binary, input,
   stderr, encoding, errors)` per `design.md` R1: `subprocess.run(["git",
   *args], ...)`, `check=False`, `stdout=PIPE`, `stderr=stderr`, `text=not
   binary`, `encoding=None if binary else encoding`, `errors=None if binary else
   errors`, `timeout=timeout`. It does **not** catch anything —
   `OSError`/`TimeoutExpired` propagate.
2. Add `run_git_minimal(args, *, cwd=None, timeout=None, binary=False,
   input=None, stderr=subprocess.PIPE, encoding=None, errors=None)` with two
   `@overload`s (str for `binary=False`, bytes for `binary=True`). Env =
   `{**os.environ, "GIT_TERMINAL_PROMPT": "0"}`. No `build_tool_environment`.
3. Add `run_git_cached(args, *, repo, cwd=None, timeout=None, binary=False,
   input=None, stderr=subprocess.PIPE, encoding=None, errors=None)`: `env, _, _ =
   build_tool_environment(repo=repo)` (propagates `CacheSetupError`), then
   `env.setdefault("GIT_TERMINAL_PROMPT", "0")`, then `_run_git_process(...,
   cwd=cwd, ...)`. **`repo` (cache namespace) and `cwd` (child dir) are separate
   params** (C-14): install-audit/work-loop pass `repo=<root>, cwd=None`.
   **Defaults matter** (design C-4/C-5/C-11/C-12): `timeout=None` = no timeout;
   `encoding=None`/`errors=None` = platform locale + strict. Do **not** hardcode
   a 60s default or force UTF-8.
4. In `build_tool_environment`, right before `return environment, cache_paths,
   namespace` (~375), add `environment.setdefault("GIT_TERMINAL_PROMPT", "0")`
   so it lands on the returned dict without overriding an explicit caller value.
5. Confirm `Sequence`, `Mapping`, `overload`, `Path`, `subprocess`, `os` are
   already imported; add only what is genuinely missing.

Validation:

```bash
grep -n "def run_git_minimal\|def run_git_cached\|def _run_git_process" templates/scripts/sd_ai_command_pack_lib.py
grep -c "GIT_TERMINAL_PROMPT" templates/scripts/sd_ai_command_pack_lib.py   # >=3
grep -c "DEFAULT_GIT_TIMEOUT\|encoding=.utf-8., errors=.strict." templates/scripts/sd_ai_command_pack_lib.py   # expect 0 (no forced default)
.venv/bin/python -c "import ast; ast.parse(open('templates/scripts/sd_ai_command_pack_lib.py').read())"
```

## Cluster 2 — minimal-env callers (synced)

### 2a `review-local.py:_git` (tmpl 549)

- Replace the `subprocess.run(...)` body with `run_git_minimal(args, cwd=repo,
  timeout=GIT_TIMEOUT_SECONDS, binary=binary)`.
- Keep `except subprocess.TimeoutExpired` → `ReviewInputError` using
  `TimeoutExpired.stderr` (the helper re-raises it unchanged). Let spawn
  `OSError` continue to escape (helper does not catch it; do not add a catch).
- Keep both `@overload`s; keep `returncode != 0 → ReviewInputError`.

### 2b `review-local.py:_artifact_root` check-ignore (tmpl 1334)

- Replace the bare `subprocess.run(["git", "check-ignore", "-q", "--", ...])`
  with `run_git_minimal(["check-ignore", "-q", "--", rel], cwd=repo,
  timeout=None, binary=True)` — **`timeout=None`** (current has none; a default
  would add an unhandled `TimeoutExpired`, C-11) and **`binary=True`** (current
  is bytes/no-decode; avoids a new decode path, C-15).
- Logic uses only `result.returncode`. Keep `returncode != 0 → ReviewInputError(
  "review artifact root must be ignored by Git")`. Note: raw git stderr no longer
  echoes to the terminal on error (behavior-neutral to the code).

### 2c `surface-check.py:_run_git` (tmpl 127)

- Replace the body with `run_git_minimal(args, cwd=root, timeout=60,
  binary=True)`; return `result.stdout` (bytes).
- Keep `except (OSError, subprocess.TimeoutExpired)` → `None` when `optional`
  else `SurfaceInputError`; keep `returncode != 0` → same.

Import `run_git_minimal` in 2a/2c; remove now-unused `subprocess`/`os` imports
only after `grep` proves them unused in that file.

Validation:

```bash
for f in review-local surface-check; do
  grep -c "run_git_minimal" templates/scripts/sd-ai-command-pack-$f.py
  grep -nE "subprocess\.run\(\[.git" templates/scripts/sd-ai-command-pack-$f.py   # expect none
done
```

## Cluster 3 — cache-backed callers (synced)

### 3a `install-audit.py:gitignored_paths` (tmpl 590)

- Replace with `run_git_cached(["-C", str(root), "check-ignore", "--stdin",
  "-z"], repo=root, cwd=None, binary=True, input=input_payload,
  timeout=GIT_TIMEOUT_SECONDS, stderr=subprocess.DEVNULL)`. **`repo=root,
  cwd=None`** keeps the `git -C root` argv and adds no child cwd (C-14);
  preserves the current `stderr=DEVNULL`.
- Keep `except (CacheSetupError, OSError, subprocess.TimeoutExpired)` → `set()`;
  keep `returncode not in {0, 1}` → `set()`; keep NUL split of `result.stdout`.

### 3b `work-loop.py:run_git` (tmpl 237)

- Reimplement the adapter body as: `try: result = run_git_cached(["-C",
  str(repo), *args], repo=repo, cwd=None, timeout=20, stderr=subprocess.DEVNULL,
  encoding="utf-8", errors="strict")` — keep `->str|None`. **`repo=repo,
  cwd=None`** keeps `git -C repo` and adds no child cwd (C-14). The explicit
  `encoding`/`errors` reproduce the current call exactly (C-12); `stderr=DEVNULL`
  preserves suppression.
- Keep `except CacheSetupError` → `WorkLoopError` with the existing message
  shaping (`removeprefix`, `CACHE_ROOT_ENV` hint).
- Keep `except (OSError, UnicodeError, subprocess.TimeoutExpired)` → `None`.
- `return result.stdout.strip() if result.returncode == 0 else None`.
- **Do not touch the ~10 call sites.**

Import the helper + `CacheSetupError` where needed.

Validation:

```bash
grep -c "run_git_cached" templates/scripts/sd-ai-command-pack-install-audit.py templates/scripts/sd-ai-command-pack-work-loop.py
grep -nE "subprocess\.run\(\[.git" templates/scripts/sd-ai-command-pack-install-audit.py templates/scripts/sd-ai-command-pack-work-loop.py   # expect none
```

## Cluster 4 — source-only callers (edit `scripts/` in place)

### 4a `fleet-controller.py` ×3 (1670/1677/1684)

- Import `run_git_minimal` from the lib (fleet-controller already imports lib
  helpers; confirm the import path).
- Replace each `subprocess.run(["git", "-C", str(path), ...], check=True,
  capture_output=True, text=True, timeout=10)` with `run_git_minimal([...],
  cwd=None, timeout=10)`. **`cwd=None`** — the argv keeps `git -C path`; current
  calls pass no child cwd (C-14). Leave `encoding` at default `None` — current
  bare `text=True` (locale) is reproduced (C-12).
- Since `check=True` is gone, keep the existing `except (OSError,
  subprocess.SubprocessError)` block (still catches spawn errors and the
  propagated `TimeoutExpired`, which is a `SubprocessError`), and add `if
  result.returncode != 0: return result` before reading `.stdout` — reproducing
  today's "CalledProcessError → return unchanged `result`" behavior.

### 4b `fleet-publish.py` git argv (118/124/233/234/379 — 5 sites)

- `fleet-publish` has no lib env today; route only its **git** argv through
  `run_git_minimal`, keeping non-git `run` calls as-is.
- Add `git_run(argv, *, cwd)` calling `run_git_minimal(list(argv), cwd=cwd,
  timeout=None, stderr=subprocess.STDOUT)`. **`cwd` is an explicit param
  threaded from each caller** (C-16) — do not reference a module-level `repo`.
  **`timeout=None`** matches the current no-timeout `run` (avoids leaking
  `TimeoutExpired` on a slow push, C-10). **`stderr=subprocess.STDOUT`**
  preserves merged-output ordering. On `returncode != 0`:
  `detail = (result.stdout or "").strip().splitlines()[-1:] or [""]` then
  `raise PublishError(f"command failed (git {' '.join(argv)}): {detail[0]}",
  code=2)` — **the literal `git ` prefix is required** so the message matches
  today's full-argv `run(["git", *argv])` output (C-16).
- Repoint the call sites, threading `cwd`:
  - `git_out(argv, *, cwd)` → `return (git_run(argv, cwd=cwd).stdout or "").strip()`
  - `porcelain_paths(cwd)` → `git_run(["status", "--porcelain"], cwd=cwd)`
  - `work_commit(repo, ...)` → `git_run(["add", "-A"], cwd=repo)`,
    `git_run(["commit", "-q", "-F", str(message_file)], cwd=repo)`
  - push → `git_run(["push", "-u", args.remote, args.branch], cwd=repo)`
- No `["git", ...]` literal remains in the file (the boundary gate enforces
  this). `push`/`commit` now run prompt-disabled — an intended safety gain.

Validation:

```bash
# no git literal or direct git subprocess remains in either source-only file
grep -nE '\[.git.' scripts/sd-ai-command-pack-fleet-controller.py scripts/sd-ai-command-pack-fleet-publish.py   # expect none
.venv/bin/python -c "import ast; [ast.parse(open(f).read()) for f in ['scripts/sd-ai-command-pack-fleet-controller.py','scripts/sd-ai-command-pack-fleet-publish.py']]"
```

## Cluster 5 — AC4 boundary test + allowlist

Add `tests/test_git_invocation_boundary.py`. Two sound AST checks (C-6/C-9;
supersedes the unsound runner-sink attempt, C-18). Do **not** require every git
literal to be a direct arg to an allowed runner — that red-flags legitimate
assign-before-`run_command` (fleet-candidate-check.py:157/183/208) and
`command_row` (check.py:1038/1044) code.

Helper — a **git-argv literal** is an `ast.List`/`ast.Tuple` with
`ast.Constant("git")` first, or an `ast.BinOp(Add)` whose `left` is such a list.

**Check 1 — direct-subprocess-git (repo-wide):**
1. For each `scripts/*.py`, walk every `Call` to `subprocess.run` /
   `subprocess.Popen`.
2. Flag it when its first positional arg is a git-argv literal.
3. Assert flagged calls exist **only** in `sd_ai_command_pack_lib.py`.

**Check 2 — no git literal in the six migrated files (targeted):**
4. For `review-local`, `surface-check`, `install-audit`, `work-loop`,
   `fleet-controller`, `fleet-publish`, assert no git-argv literal appears at
   all — closes fleet-publish's `run(["git", ...])` indirection that Check 1
   alone misses (its `run` calls `subprocess.run(list(argv))`, a variable).

5. Print a `{filename: rationale}` note for the three generic runners on failure.
6. Include a test comment documenting the residual limit (a new self-wrapping
   script feeding git via a variable, or fully dynamic argv, escapes a static
   lint — deferred to review).

Sanity-proven against the current tree before shipping: Check 1 flags exactly
the six migration targets, zero false positives on the seven
delegating/generic-runner files. The raw/presence greps and the runner-sink rule
are retired from every artifact.

## Cluster 6 — sync + gates

`make sync` = `install.py . --force` (regenerates `scripts/` twins from
`templates/`) + `update-spec-kb.py` (refreshes the gitignored external
`.obsidian-kb`; idempotent, produces no tracked diff — see design C-13):

```bash
make sync
git diff --stat -- scripts/ templates/scripts/   # only intended synced twins + the two source-only files
# spot-check a twin is byte-identical to its template:
diff templates/scripts/sd-ai-command-pack-review-local.py scripts/sd-ai-command-pack-review-local.py
```

Then:

```bash
make check
.venv/bin/python -m pytest tests/test_git_invocation_boundary.py -q
make test        # template parity + shipped-surface gate
```

Add/extend `run_git_minimal`/`run_git_cached` unit tests:

- `binary=False` → `str` stdout; `binary=True` → `bytes`.
- Non-zero git exit returns the `CompletedProcess` (no raise).
- `run_git_minimal` succeeds with **no** writable cache root (where
  `run_git_cached`/`run_git` would raise `CacheSetupError`).
- `TimeoutExpired`/`OSError` propagate (monkeypatch `subprocess.run`).
- `input=`/`binary=True` round-trips NUL-delimited stdin (install-audit path).
- `GIT_TERMINAL_PROMPT=0` present in the child env (capture via monkeypatch).

If the shipped-surface gate reports a payload digest change, bump
`manifest.json` and restamp `docs/fleet/candidate-validation.json` via
`prepare-release.py`, then re-run `make test`.

## Sync / rollback

- Parity is verified by the twin diff above. The KB refresh is a harmless
  gitignored side effect of `make sync`, not something to avoid (design C-13
  corrects the earlier framing).
- Rollback: `git checkout -- <edited templates + their regenerated twins +
  scripts/sd-ai-command-pack-fleet-controller.py +
  scripts/sd-ai-command-pack-fleet-publish.py +
  tests/test_git_invocation_boundary.py>`. No data migration; external KB is
  idempotent.

## Review gates

- Before `task.py start`: run the SD planning adversarial review contract
  (`.claude/rules/sd-planning-adversarial-review.md`) on this prd/design/implement
  batch; resolve every blocking concern first. This is remediation round ≥1 of
  the round that found C-1..C-5.
- Do not touch work-loop's ~10 call sites (Cluster 3b) or pr-body-scope's error
  shaping. The generic runners (Cluster 5 allowlist) are not migrated.
