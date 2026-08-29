---
title: Shrink machine plugin closure by splitting fileops
status: planning
created: 2026-08-09
---
# PRD: Shrink machine plugin closure by splitting fileops

## Goal
Reduce the generated plugin's bundled `installer/**` import closure (~100KB driven by `installer/fileops.py` pulling broad module dependencies) so the machine bootstrap ships only what the machine engine needs.

## Requirements
- Split `installer/fileops.py` so machine-scope code imports only the symlink/traversal/atomic-write primitives it uses.
- Regenerated `plugins/sd/installer/**` closure shrinks measurably; `generate-plugin.py --check` and determinism tests stay green.
- No behavior change for `install.py` repo-scope installs.

## Acceptance criteria
- Bundled installer closure byte size reduced and asserted in `tests/test_generate_plugin.py` inventory expectations.
- `make test` and `make generate` clean.
