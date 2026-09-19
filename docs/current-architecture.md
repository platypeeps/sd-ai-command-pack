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
Run `python3 bin/sd_install.py --status` to inspect the current installation.
Run `python3 bin/sd_install.py --verify --json` for strict, read-only verification.
The strict check rejects receipt, source, rendered-file, command-resolution, and help-probe failures.

Canonical payload and Claude output retain `disable-model-invocation`.
Codex skills translate only this field into `agents/openai.yaml` policy; their Markdown bodies remain byte-identical.
The generated companion records the inverse boolean as `policy.allow_implicit_invocation`.
Absent markers preserve the source invocation policy.
Source interface and dependency metadata remain unchanged.
The adapter accepts plain block-mapping keys and lowercase invocation booleans.
It refuses quoted keys, aliases, flow policy mappings, duplicates, and conflicting invocation controls before rendering.
This narrow exception does not adapt Claude agents or OpenCode commands.

The installer does not edit shell configuration.
Bare command names resolve only when the selected installation directory is on `PATH`.

## Governing references

The [work-item guide](work/README.md) owns planning layout, status, registration, and archive rules.
The [contributor guide](../CONTRIBUTING.md) owns documentation, validation, and delivery rules.
The [archive index](work/archive/README.md) records cleanup boundaries and recovery instructions.

The pre-commit hook has an 8-second wall-time budget for a one-file diff.
It takes its interpreter from this worktree's `.venv`, then from the clone's
main checkout, the way `make hooks` installs one hook per clone, and failing
both from `python3` on `PATH`, which on a machine that installed the dev
requirements globally runs the gates perfectly well. Only when the interpreter
it settled on cannot import them does it refuse the commit as `unchecked`,
which is `bin/sd-status`'s word for a check that could not run, rather than as
a lint verdict on the staged code. The clone's checkout is borrowed only where
`root` is a linked worktree of it, which its own `--git-dir` shows by sitting
under that `.git`'s `worktrees/`; a separated git directory, a submodule and a
bare clone fall back rather than reach into an unrelated tree. The name of the
common directory does not settle this on its own, because
`git init --separate-git-dir` can be pointed at a path named `.git`.

## Historical design

The artifacts-as-product design created the current machine-scope model.
Its documents remain in the historical snapshot:

- [Design record](https://github.com/platypeeps/sd-ai-command-pack/blob/8ba8fa7a15fcd4783b42cbe580a04e89149be08d/docs/work/archive/2026-09/2026-08-29-artifacts-as-product/design.md)
- [Implementation record](https://github.com/platypeeps/sd-ai-command-pack/blob/8ba8fa7a15fcd4783b42cbe580a04e89149be08d/docs/work/archive/2026-09/2026-08-29-artifacts-as-product/implement.md)

Treat those files as historical evidence.
This page and current code define present behaviour.
