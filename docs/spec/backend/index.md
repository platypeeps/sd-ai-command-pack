# Installer CLI Guidelines

> [!important]
> **Stale as of 2026-09-01.**
> Every subject in the Scope and Pre-Development Checklist below is gone.
> `install.py`, the `installer/` package, `manifest.json`, `templates/` and
> `tests/install_test_support.py` were deleted on 2026-08-30 by step 3e of the
> artifacts-as-product rollout (`43170716`, #610 -- 365 files, 183,433
> deletions). What replaced them is one file, `bin/sd_install.py`, plus
> `tests/test_sd_install.py`; `manifest.json` has no successor, because there is
> no payload left to manifest. Every guide this index links describes that same
> deleted installer.
>
> The text below is unedited. It is the record of what that machinery
> specified, not guidance for the repository as it stands. The triage that
> produced this notice is recorded under step 7 in
> `docs/work/2026-08-29-artifacts-as-product/implement.md`.

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
| [Fleet Consumer Conversion](./fleet-consumer-conversion.md) | Running `install.py` against a registered fleet consumer rather than this repository. Documents that `--force` refreshes the whole payload rather than the cohort you named, the pre-install digest rule that protects locally owned files, the stash-and-branch ordering, and why the post-conversion fleet count reads incomplete |
| [Logging Guidelines](./logging-guidelines.md) | Changing command output, warnings, or status summaries |
| [Quality Guidelines](./quality-guidelines.md) | Changing installer behavior, tests, compatibility, or review expectations |

## Pre-Development Checklist

Before editing installer behavior:

1. Read `install.py`, especially `PackFile`, `load_manifest()`,
   `selected_files()`, `install_file()`, and `main()`.
2. Read `manifest.json` and confirm the behavior belongs in manifest data,
   Python logic, or both.
3. Read `tests/install_test_support.py` and the closest focused
   `tests/test_*.py` module for the CLI-through-subprocess test style.
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
