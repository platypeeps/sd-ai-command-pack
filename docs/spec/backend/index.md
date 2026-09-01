# Installer CLI Guidelines

> [!important]
> **Stale as of 2026-09-01, and reduced on 2026-09-02.**
> Every subject the original Scope and Pre-Development Checklist named is gone.
> `install.py`, the `installer/` package, `manifest.json`, `templates/` and
> `tests/install_test_support.py` were deleted on 2026-08-30 by step 3e of the
> artifacts-as-product rollout (`43170716`, #610 -- 365 files, 183,433
> deletions). What replaced them is one file, `bin/sd_install.py`, plus
> `tests/test_sd_install.py`; `manifest.json` has no successor, because there is
> no payload left to manifest.
>
> **This page is now an index and nothing else.** Its Scope, Pre-Development
> Checklist and Quality Check sections were deleted with the pages they pointed
> at, rather than left standing as instructions for a tree that cannot follow
> them. It survives because `sd-docs-lint` rule 4 requires an `index.md` in
> every spec directory and three pages here are staying; the alternative was
> deleting the directory whole, which those three pages rule out.
>
> The three guides below are unedited and each carries its own dated notice.
> They are the record of what the machinery specified, not guidance for the
> repository as it stands. The triage that reached this verdict is recorded
> under step 7 in `docs/work/2026-08-29-artifacts-as-product/implement.md`;
> the pass that executed it is recorded in the same file.

## Guides

| Guide | What it records |
|-------|-----------------|
| [Manifest And Filesystem](./manifest-and-filesystem.md) | The manifest/installer/plugin-generation/payload-gate/fleet-campaign model. Partly stale: its Trellis-gitignore section still specifies the vestigial `SD-AI-COMMAND-PACK` markers that `CONTRIBUTING.md` keeps `.gitignore` for, and its Machine-Scope Installer section is a design record for files that no longer exist |
| [Error Handling](./error-handling.md) | The deleted `install.py` exit-code contract, plus three diagnostic lessons that outlive their subject |
| [Quality Guidelines](./quality-guidelines.md) | 18 contracts for deleted shipped scripts, the **live** bash 3.2 gate, and "Silent Paths Must Say Why" |

## What was deleted from this directory

Three pages went on 2026-09-02, each a `delete` verdict from the 2026-09-01
triage: `directory-structure.md` (the `install.py` + `installer/` + `templates/`
+ `scripts/` layout), `fleet-consumer-conversion.md` (running
`install.py <consumer>` across a fleet that no longer exists), and
`logging-guidelines.md` (installer status lines and a `_SECRET_SHAPES` constant
in a deleted file). All three are reachable in git history; the triage table
records what each specified.
