# Installer CLI Guidelines

> Project-specific guidance for the Python installer and pack metadata.

---

## Scope

Use these specs when changing:

- `install.py`
- `manifest.json`
- installer behavior documented in `README.md`
- tests that exercise installer behavior under `tests/`

This repo is a small Python CLI package, not a backend service. "Backend" in
this Trellis layer means installer logic, local filesystem writes, subprocess
checks, and manifest handling.

## Guides

| Guide | Use When |
|-------|----------|
| [Directory Structure](./directory-structure.md) | Adding, moving, or organizing installer, manifest, template, or test files |
| [Manifest And Filesystem](./manifest-and-filesystem.md) | Changing pack metadata, platform selection, target validation, conflict behavior, or file writes |
| [Error Handling](./error-handling.md) | Changing CLI validation, conflict reporting, subprocess handling, or exit codes |
| [Logging Guidelines](./logging-guidelines.md) | Changing command output, warnings, or status summaries |
| [Quality Guidelines](./quality-guidelines.md) | Changing installer behavior, tests, compatibility, or review expectations |

## Pre-Development Checklist

Before editing installer behavior:

1. Read `install.py`, especially `PackFile`, `load_manifest()`,
   `selected_files()`, `install_file()`, and `main()`.
2. Read `manifest.json` and confirm the behavior belongs in manifest data,
   Python logic, or both.
3. Read `tests/test_install.py` for the CLI-through-subprocess test style.
4. If template files are involved, also read the frontend/template specs.

## Quality Check

Run:

```bash
python3 -m unittest discover -s tests
git diff --check
```

For untracked spec or template files, also scan trailing whitespace directly:

```bash
rg -n "[ \t]+$" .trellis/spec templates tests install.py manifest.json README.md
```

Review that any new adapter or template path is listed in `manifest.json`,
documented in `README.md`, and covered by an installer test.
