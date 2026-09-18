# Current architecture

This page owns the current repository topology.
Git history preserves the retired designs and completed work records.

## Repository model

The repository owns one payload copy under `skills/`.
Nothing renders into this checkout.
`skills/paths.json` defines the installed skill set.
The installer enforces the skill set and enumerates commands from `bin/` at runtime.

The executable entrypoints live under `bin/`.
Each installed command links back to the serving checkout.
The installation receipt records owned command links and digest-vouched rendered files.
Run `bin/sd_install.py --status` to inspect the current installation.

The installer does not edit shell configuration.
Bare command names resolve only when the selected installation directory is on `PATH`.

## Governing references

The [work-item guide](work/README.md) owns planning layout, status, registration, and archive rules.
The [contributor guide](../CONTRIBUTING.md) owns documentation, validation, and delivery rules.
The [archive index](work/archive/README.md) records cleanup boundaries and recovery instructions.

The pre-commit hook has an 8-second wall-time budget for a one-file diff.

## Historical design

The artifacts-as-product design created the current machine-scope model.
Its documents remain in the historical snapshot:

- [Design record](https://github.com/platypeeps/sd-ai-command-pack/blob/8ba8fa7a15fcd4783b42cbe580a04e89149be08d/docs/work/archive/2026-09/2026-08-29-artifacts-as-product/design.md)
- [Implementation record](https://github.com/platypeeps/sd-ai-command-pack/blob/8ba8fa7a15fcd4783b42cbe580a04e89149be08d/docs/work/archive/2026-09/2026-08-29-artifacts-as-product/implement.md)

Treat those files as historical evidence.
This page and current code define present behaviour.
