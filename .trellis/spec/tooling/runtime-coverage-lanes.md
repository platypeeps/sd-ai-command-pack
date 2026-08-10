# Runtime Coverage Lanes

> How the shipped runtime surface (Python, Node, shell) is measured in CI, and
> the non-obvious gotchas that cost real debugging time. Read before touching
> `.github/scripts/kcov-bash-shim.sh`, `summarize_shell_coverage.py`,
> `report-shell-coverage.sh`, or the `shell-coverage` job in
> `.github/workflows/tests.yml`.

## Scope

Three lanes measure the runtime that ships in the pack. Each publishes a number
and gates only on a broken-plumbing signal (a zero-line measurement), never on a
coverage floor — floors are a deliberate follow-up (R4: measure before gating).

| Lane | Surface | Tool | Report step |
|------|---------|------|-------------|
| 1 | `.github/scripts/*.py` | `coverage.py` (`.coveragerc` include) | CI-scope job |
| 2 | `scripts/sd-ai-command-pack-review-preflight.mjs` | `c8` | "Report review preflight JavaScript coverage" |
| 3 | `scripts/sd-ai-command-pack-*.sh` | `kcov` v43 (built from pinned source) | `shell-coverage` job |

## Scenario: shell coverage via the kcov shim (Lane 3)

### 1. Scope / Trigger
Infra integration: a CI job wires kcov into the test suite by replacing the
bash the subprocess tests spawn. Touching the shim, the summarizer, the report
script, or the job is a code-spec trigger.

### 2. Signatures
- `SD_AI_COMMAND_PACK_TEST_BASH` — path the test harness resolves as its bash
  (`tests/install_test_support.py::setUpClass`). Set to the shim in CI; unset
  locally falls back to PATH bash. **Validated early**: a non-executable value
  raises `RuntimeError` in `setUpClass`, not a late `FileNotFoundError`.
- `kcov-bash-shim.sh` — invoked as `bash`; dispatches to kcov or real bash.
- `summarize_shell_coverage.py <cobertura.xml>` → prints `<covered> <total> <pct>`.
- `report-shell-coverage.sh` — merges kcov runs, calls the summarizer, publishes.

### 3. Contracts (env keys)
- `SD_AI_COMMAND_PACK_REAL_BASH` (default `/bin/bash`) — the bash kcov wraps.
- `SD_AI_COMMAND_PACK_KCOV_DIR` — per-run output root; unset ⇒ shim is a no-op
  passthrough to real bash (identical exit codes).
- `SD_AI_COMMAND_PACK_KCOV_INCLUDE` (default `sd-ai-command-pack-`) — kcov
  `--include-pattern`. **Basename marker, not a path prefix** (see gotcha).

### 4. Validation & Error Matrix
- `summarize`: `total == 0` → exit 2 (broken plumbing; a kcov run that
  instrumented nothing exits 0 and looks like success). `covered == 0` with
  `total > 0` → exit 0, prints `0.0%` (measured-but-unexercised is data, not a
  failure — failing here would be a hidden >0% floor). Missing/unparseable →
  exit 1.
- `report-shell-coverage.sh`: captures the summarizer in a command substitution
  (`if ! summary="$(...)"`) so its exit propagates — a process substitution
  would swallow it and defeat the zero-line guard.

### 5. Good/Base/Bad Cases
- Good: `bash scripts/sd-ai-command-pack-full-check.sh` → shim runs
  `kcov OUT scripts/...full-check.sh` → lines attributed.
- Base: `bash -c 'source ...; func'` → not script-targetable → real bash, no
  coverage (kcov cannot attribute a `-c` command string to a file).
- Bad: `bash -n script.sh` (syntax check, nothing executes) → real bash.

### 6. Tests Required
- `tests/test_summarize_shell_coverage.py` — every exit branch (0 real, 0
  unexercised, 2 zero-line, 1 unreadable) + basename union + marker/.sh filter.
- The live kcov number is CI-only (kcov is Linux/ptrace; not runnable on macOS).

### 7. Wrong vs Correct

#### Wrong — target the bash binary
```bash
exec kcov "$run_dir" "$real_bash" "$@"   # kcov's target is /usr/bin/bash
```
kcov treats bash as a compiled program, hunts for DWARF line info a stripped
bash does not carry, and records `total_lines=0`. Its shell-source collector
never engages. This looks like success (exit 0, a full report skeleton, empty
`coverage.json`) and silently measures nothing.

#### Correct — target the script
```bash
first="${1:-}"
if [ -n "$first" ] && [ "${first#-}" = "$first" ] && [ -f "$first" ]; then
  exec kcov "$run_dir" "$@"   # target is the script; kcov reads its shebang
fi
exec "$real_bash" "$@"        # option forms (-c/-n): no coverage, real bash
```

> **Warning: never `chmod` the target.** kcov reads a `0644` script through its
> shebang; it does not need the exec bit. Granting `+x` mutates the mode of the
> tracked shipped script, dirtying the working tree — which the
> surface-closure check observes and fails on.

> **Warning: `--include-pattern` is a plain substring, not a regex or path
> prefix.** Use the basename marker `sd-ai-command-pack-`. A `$PWD/scripts/...`
> prefix never matches the ephemeral tempdir copies (`/tmp/.../scripts/...`) the
> subprocess tests execute, so it measures zero and hard-fails.
> `summarize_shell_coverage.py` re-collapses the many tempdir copies by basename
> and unions covered/executable line numbers, so a line reached in any copy
> counts once.
