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

## Trellis-Owned Platform Files

- Keep Trellis-owned platform files in their Trellis-managed state so
  `trellis update --dry-run --migrate` does not report avoidable local
  overrides.
- In particular, keep `.opencode/package.json` byte-identical to Trellis'
  canonical dependency range. Track `.opencode/bun.lock` in this repo to pin
  the exact resolved dependency graph, and refresh it from `.opencode/` with:

  ```bash
  bun install --lockfile-only
  ```

- Put machine-specific Claude permissions in the ignored
  `.claude/settings.local.json`, not Trellis-owned `.claude/settings.json`.

## Specs To Read First

- [Adapter guidelines](.trellis/spec/frontend/adapter-guidelines.md) for adding
  or changing platform adapters.
- [Manifest and filesystem](.trellis/spec/backend/manifest-and-filesystem.md)
  for installer, manifest, provenance, local-only, and audit behavior.
