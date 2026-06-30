# Directory Structure

> How backend and CLI code is organized in this project.

---

## Overview

This repository is a small Python extension-pack installer, not a service app.
Keep the root layout flat unless a new feature clearly needs more structure.
The backend surface is the installer CLI plus its manifest-driven file-copy
logic.

## Directory Layout

```text
.
├── install.py                  # Python CLI and installer implementation
├── manifest.json               # Pack metadata and installable file manifest
├── scripts/                     # Dogfooded pack-owned helper scripts
├── templates/                  # Files copied into target Trellis repos
│   ├── .agents/skills/...
│   ├── .cursor/commands/...
│   ├── .gemini/commands/...
│   ├── .github/prompts/...
│   ├── .opencode/commands/...
│   └── scripts/...              # Helper scripts installed into target repos
├── tests/
│   └── test_install.py         # unittest coverage for installer behavior
└── README.md                   # User-facing install and verify docs
```

## Module Organization

- Keep installer behavior in `install.py` while the project stays this small.
- Keep installable payloads under `templates/` and describe them in
  `manifest.json`; do not hard-code new template paths only in Python.
- Keep platform adapters thin. The shared workflow belongs in
  the matching `templates/.agents/skills/<command>/SKILL.md` file.
- Keep tests in `tests/test_install.py` unless test volume grows enough to
  justify splitting by behavior.

## Naming Conventions

- Use lowercase, underscore-separated Python names, as in `load_manifest`,
  `selected_files`, and `run_diff_check`.
- Use `Path` objects for filesystem paths, matching `ROOT`, `MANIFEST_PATH`,
  and `PackFile.source` / `PackFile.target`.
- Use `sd-ai-command-pack` as the canonical pack slug for repository names,
  script filenames, generated state folders, managed-block names, and docs that
  refer to the pack. Use `SD_AI_COMMAND_PACK_*` for pack-owned environment
  variables and `sd_ai_command_pack_*` for pack-owned Python helpers. Treat
  older `sd-command-pack`, `SD_COMMAND_PACK_*`, and `sd_command_pack_*` forms as
  legacy installer cleanup aliases only.
- Platform identifiers in manifests and CLI arguments are lowercase strings:
  `shared`, `claude`, `cursor`, `gemini`, `github`, and `opencode`.

## Examples

- `install.py` owns CLI parsing, manifest loading, target validation, file
  selection, file installation, and final diff checking.
- `manifest.json` is the source of truth for source and target paths.
- `tests/test_install.py` exercises the CLI through subprocess calls against
  temporary Trellis repos instead of mocking the installer internals.
