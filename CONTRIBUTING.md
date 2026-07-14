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
Ruff, review-preflight JavaScript syntax checks when Node is available,
optional ShellCheck, optional Bandit/Zizmor, and the SD full-check gate with
Prism/Gito disabled. Missing optional tools print warnings instead of blocking
Python-only contributor setups.

## Release And Payload Rules

- Bump `manifest.json` whenever shipped payload changes: `templates/**`,
  `docs/SD_AI_COMMAND_PACK.md`, or the manifest itself.
- Treat `templates/**` as the source of truth for shipped files. Root-level
  copies under `.agents/`, `.opencode/`, `scripts/`, and similar dogfood paths
  are mirrors.
- After changing shipped payload, self-sync the dogfood install when needed:

  ```bash
  bash scripts/sd-ai-command-pack-toolchain.sh run-python -- install.py . --force
  ```

- Refresh the generated KB before full-check after README, docs, spec, or task
  edits:

  ```bash
  bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
    scripts/sd-ai-command-pack-update-spec-kb.py
  ```

## Specs To Read First

- [Adapter guidelines](.trellis/spec/frontend/adapter-guidelines.md) for adding
  or changing platform adapters.
- [Manifest and filesystem](.trellis/spec/backend/manifest-and-filesystem.md)
  for installer, manifest, provenance, local-only, and audit behavior.
