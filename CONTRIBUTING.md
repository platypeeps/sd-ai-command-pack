# Contributing

Use Homebrew Python 3.13 on macOS for the local virtualenv; Apple/Xcode Python
often misses dev dependencies or writes caches into protected locations, and
some security scanners can lag newer Python AST changes.

## Setup

```bash
make setup
bash scripts/sd-ai-command-pack-toolchain.sh doctor
```

`make setup` creates `.venv` and installs `requirements-dev.txt` and
`requirements-security.txt`.

Both requirements files are hash-pinned compiled resolutions, installed with
`--require-hashes` locally and in CI so the transitive closure cannot drift
between runs. To bump a dependency, edit its `==` pin and rerun the compile
command recorded in the file's header
(`uv pip compile --universal --generate-hashes --python-version 3.10 <file> -o <file>`);
if the bump conflicts with a stale transitive pin, delete that transitive's
block and recompile. Do not hand-edit hashes. Dependabot updates these files
with matching hashes on its own.

## Local Checks

```bash
make test
make lint
make audit
make full-check
make check
```

`make check` runs the full local maintainer battery: coverage-gated tests,
Ruff, mypy over `installer/`, `install.py`, and shipped `scripts/`,
pack JavaScript syntax checks when Node is available, optional ShellCheck,
optional Bandit/Zizmor, and the SD full-check gate with Prism/Gito disabled.
Missing optional tools print warnings instead of blocking Python-only
contributor setups. Run `STRICT=1 make lint` to turn those missing-tool
skips into hard errors for parity with CI, which always runs the Node and
ShellCheck lanes.

`make lint` also parses every tracked shell script with bash 3.2 — the
interpreter macOS keeps at `/bin/bash` — through
`.github/scripts/check-bash32-syntax.sh`, so syntax that only bash 3.2 rejects
fails before the push instead of on the macOS CI leg minutes later. The script
list is enumerated from `git ls-files` at run time, never maintained inside the
gate. A platform with no bash 3.2 (any Linux) prints
`warning: no bash 3.2 interpreter found` and passes; `STRICT=1` turns that
missing interpreter into a failure, and `SD_AI_COMMAND_PACK_BASH32` overrides
the interpreter search with a space-separated candidate list.

`make generate` and the pack-source portion of `make full-check` also run
`scripts/sd-ai-command-pack-surface-check.py`. The versioned validator derives
the complete affected graph from `installer/registry.py` and `manifest.json`,
including explicitly source-only references, generated mirrors, caller
registrations, and release evidence. Its internal command lint rejects stale
names or missing targets across live surfaces. Historical mentions require a
bounded `CommandSurfaceAllowance` with a reason; do not add broad
documentation-root or source-only directory exclusions.

The shipped-script coverage lane has two thresholds: the aggregate
`scripts/sd-ai-command-pack-*.py` floor remains 76%, and
`.github/scripts/check-shipped-script-coverage.sh` lists an explicit per-file
floor for each shipped Python helper. Set per-file floors at or just below the
current measured coverage and ratchet them upward when focused tests improve a
script; do not let a single helper regress behind a healthy aggregate total.
`.github/scripts/*.py` automation is coverage-measured (no floor yet; floors
arrive in a follow-up at or below measured values). Shipped shell
(`scripts/sd-ai-command-pack-*.sh`) is coverage-measured in the `shell-coverage`
CI job with kcov, which routes the bash the subprocess tests spawn through
`.github/scripts/kcov-bash-shim.sh` and publishes a measured baseline (no floor
yet; floors arrive in a follow-up at or below measured values). `full-check.sh`'s
inline `python3 - <<HEREDOC` region is not bash-executed, so kcov cannot
attribute it; its extraction and measurement are tracked separately. GitHub
workflow YAML remains coverage-exempt. Continue covering shell behavior with
focused subprocess tests, syntax checks, and ShellCheck as well — the kcov lane
measures reach, it does not replace behavioral assertions.

To reproduce the shell-coverage measurement locally, install kcov and run the
suite with the shim as the tests' bash:

```bash
export SD_AI_COMMAND_PACK_TEST_BASH="$PWD/.github/scripts/kcov-bash-shim.sh"
export SD_AI_COMMAND_PACK_REAL_BASH="$(command -v bash)"
export SD_AI_COMMAND_PACK_KCOV_DIR="$(mktemp -d)"
export SD_AI_COMMAND_PACK_KCOV_INCLUDE="sd-ai-command-pack-"
python3 -m unittest discover -s tests -p 'test_*.py'
bash .github/scripts/report-shell-coverage.sh
```

`SD_AI_COMMAND_PACK_TEST_BASH` overrides the bash the subprocess tests spawn
(default: the bash on `PATH`); the four `SD_AI_COMMAND_PACK_KCOV_*` variables
scope and collect the kcov data. Leaving all of them unset — the normal case —
runs the tests exactly as before with no coverage instrumentation. kcov is
Linux-only, so this reproduction does not run on macOS.

Ruff covers pack-owned Python in `install.py`, `installer/`, `scripts/`,
`templates/scripts/`, and `tests/`. Trellis-owned platform runtime is excluded;
tracked OpenCode JavaScript receives syntax-only validation with `node --check`.
`scripts/sd-ai-command-pack-review-preflight.mjs` keeps that `node --check`
syntax gate in the `lint` job; its behaviour is exercised by the Python test
suite's subprocess tests rather than by a JavaScript coverage number. The
`templates/scripts/` twin is a byte-identical mirror and is not separately
measured.

## Main Branch Policy

Every change to `main` goes through a pull request. Merge authority is GitHub
branch protection on the four CI checks; there is no local pre-push hook, no
server-side path policy, and no bookkeeping fast lane. A pull-request head and
a push to `main` run the same four unconditional jobs: the `unittest` matrix,
`shell-coverage`, `lint`, and `security`.

CI intentionally tests the supported Python floor (3.10) and current project
runtime (3.13), plus macOS on 3.13. Intermediate 3.11/3.12 jobs would duplicate
the same compatibility interval while increasing Actions cost; add one only
when a version-specific defect provides evidence that endpoint coverage is
insufficient.

## Release And Payload Rules

- 0.72.0 (tag `v0.72.0`) is the terminal release. There are no further
  releases: do not bump `manifest.json`, do not add a `CHANGELOG.md` heading,
  and do not create a tag. The release preparation command, the candidate
  ledger, the payload gate, and the auto-tag job were deleted with it.
  Shipped payload edits after 0.72.0 are reviewed and merged like any other
  change and are not versioned.
- Treat `templates/**` as the source of truth for shipped files. Root-level
  copies under `.agents/`, `.opencode/`, `scripts/`, and similar dogfood paths
  are mirrors.
- After changing shipped payload, and before full-check after README, docs,
  spec, or task edits, run `make sync`: it self-syncs the dogfood install
  (`install.py . --force`) and refreshes the generated spec KB
  (`scripts/sd-ai-command-pack-update-spec-kb.py`) in one step.
- Without make, the same two steps are:

  ```bash
  bash scripts/sd-ai-command-pack-toolchain.sh run-python -- install.py . --force
  bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
    scripts/sd-ai-command-pack-update-spec-kb.py
  ```

## Versioning

The pack is still in `0.x`, so use the minor number for meaningful consumer
behavior changes and the patch number for compatible fixes or documentation.

- Bump the minor version for new distributed commands, new shipped files,
  changed command semantics, new required installer behavior, or additions to
  the stable public surface.
- Bump the patch version for compatible bug fixes, performance improvements,
  test-only improvements, doc corrections, provenance/hash refreshes, or
  internal refactors that keep installed behavior stable.
- Treat command names, command arguments, the paths and CLIs of shipped scripts
  that carry an explicit entry bullet in the installed guide, documented
  `SD_AI_COMMAND_PACK_*` environment variables, managed-block names, manifest
  target paths, and generated state file names as stable public surface.
- Treat private Python helper functions, shell helper internals, test fixtures,
  local implementation structure, and undocumented temporary files as internal
  unless a consumer-facing doc names them. Shipped scripts on the doc-coverage
  gate's internal allowlist (`.github/scripts/check-shipped-script-docs.sh` —
  internal pipeline stages and library modules) stay internal even when the
  guide mentions them for context, such as the review-local name-collision
  note: their manifest paths are stable, but only an explicit guide entry
  bullet makes a script's CLI public surface.
- Keep deprecated public aliases documented until the removal release that
  intentionally drops them, and note the removal in `CHANGELOG.md`.

## Trellis-Owned Platform Files

- Keep Trellis-owned platform files in their Trellis-managed state so
  `trellis update --dry-run --migrate` does not report avoidable local
  overrides.
- Do not track `.opencode/package.json` or any `.opencode` Bun lockfile in this
  repo unless the checked-in OpenCode plugins or tools import external npm
  packages. If that changes, keep the manifest minimal, commit the lockfile,
  and refresh it from `.opencode/` with:

  ```bash
  cd .opencode
  bun install --lockfile-only
  ```

- Put machine-specific Claude permissions in the ignored
  `.claude/settings.local.json`, not Trellis-owned `.claude/settings.json`.

## Specs To Read First

- [Adapter guidelines](.trellis/spec/frontend/adapter-guidelines.md) for adding
  or changing platform adapters.
- [Manifest and filesystem](.trellis/spec/backend/manifest-and-filesystem.md)
  for installer, manifest, provenance, local-only, and audit behavior.
