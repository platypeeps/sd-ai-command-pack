# Contributing

Use Homebrew Python 3.13 on macOS for the local virtualenv; Apple/Xcode Python
often misses dev dependencies or writes caches into protected locations, and
some security scanners can lag newer Python AST changes.

## Setup

```bash
make setup
bash scripts/sd-ai-command-pack-toolchain.sh doctor
```

`make setup` creates `.venv`, installs `requirements-dev.txt` and
`requirements-security.txt`, and arms the direct-to-main safety hook with
`git config core.hooksPath .githooks`.

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

`make generate` and the pack-source portion of `make full-check` also run
`.github/scripts/check-command-surface-drift.py`. The linter derives live and
retired command footprints from `installer/registry.py`, rejects stale names or
missing targets across live surfaces, and emits exact-path JSON with `--json`.
Historical mentions require a bounded `CommandSurfaceAllowance` with a reason;
do not add broad documentation-root exclusions.

The shipped-script coverage lane has two thresholds: the aggregate
`scripts/sd-ai-command-pack-*.py` floor remains 76%, and
`.github/scripts/check-shipped-script-coverage.sh` lists an explicit per-file
floor for each shipped Python helper. Set per-file floors at or just below the
current measured coverage and ratchet them upward when focused tests improve a
script; do not let a single helper regress behind a healthy aggregate total.
Shell scripts, GitHub workflow YAML, and `.github/scripts/*` automation are
coverage.py-exempt by design. Cover behavior with focused subprocess tests,
syntax checks, ShellCheck, workflow assertions, and the live CI gate instead
of introducing a second shell-coverage tool unless a concrete defect shows the
current controls are insufficient.

Ruff covers pack-owned Python in `install.py`, `installer/`, `scripts/`,
`templates/scripts/`, and `tests/`. Trellis-owned platform runtime is excluded;
tracked OpenCode JavaScript receives syntax-only validation with `node --check`.

## Main Branch Policy

Only task and workspace bookkeeping under `.trellis/tasks/**` and
`.trellis/workspace/**` may be pushed directly to `main`. The tracked pre-push
hook prevents other paths locally, and the `Main push scope` CI job detects the
same violation after any accepted push. Use a pull request for every non-chore
change; CI cannot undo an accidental direct push.

CI intentionally tests the supported Python floor (3.10) and current project
runtime (3.13), plus macOS on 3.13. Intermediate 3.11/3.12 jobs would duplicate
the same compatibility interval while increasing Actions cost; add one only
when a version-specific defect provides evidence that endpoint coverage is
insufficient.

## Release And Payload Rules

- Bump `manifest.json` whenever shipped payload changes: `templates/**`,
  `docs/SD_AI_COMMAND_PACK.md`, or the manifest itself.
- Pull request CI runs a `Release payload gate` job against the PR base and
  includes it in `CI Result`, so payload changes without the manifest bump and
  matching top `CHANGELOG.md` heading are blocked before merge. A version bump
  also requires an all-pass `docs/fleet/candidate-validation.json` matching the
  exact payload and fleet manifest; generate it with
  `scripts/sd-ai-command-pack-fleet-candidate-check.py` before the final gate.
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

- Run the fleet candidate validator only after payload/template sync is final.
  It uses disposable origin clones and does not mutate active consumer trees.
  A partial `--consumer` diagnostic run never replaces the full-fleet ledger.

## Versioning

The pack is still in `0.x`, so use the minor number for meaningful consumer
behavior changes and the patch number for compatible fixes or documentation.

- Bump the minor version for new distributed commands, new shipped files,
  changed command semantics, new required installer behavior, or additions to
  the stable public surface.
- Bump the patch version for compatible bug fixes, performance improvements,
  test-only improvements, doc corrections, provenance/hash refreshes, or
  internal refactors that keep installed behavior stable.
- Treat command names, command arguments, shipped script paths and CLIs,
  documented `SD_AI_COMMAND_PACK_*` environment variables, managed-block names,
  manifest target paths, and generated state file names as stable public
  surface.
- Treat private Python helper functions, shell helper internals, test fixtures,
  local implementation structure, and undocumented temporary files as internal
  unless a consumer-facing doc names them.
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
