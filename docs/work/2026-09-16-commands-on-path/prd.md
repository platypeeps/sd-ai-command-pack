---
title: The installer links the pack commands onto PATH, and --status counts them
created: 2026-09-16
---

# PRD — commands on PATH

## Problem

On 2026-09-16 a skill ran `sd-handoff` from `~/` and the shell did not find
it. The command lives in the pack checkout's `bin/`, and nothing the pack
ships puts it on PATH. The owner wants the pack commands usable from every
repository, on every machine. Measured at `c6879551` on sol:

- `bin/` holds 17 extensionless executables, all `#!/usr/bin/env python3`.
  Fourteen locate the checkout with `Path(__file__).resolve()`; `sd-handoff`,
  `sd-handoff-restore` and `sd-skill-use` import siblings bare through
  `sys.path[0]`, which CPython sets from the script's real path. A symlink
  from elsewhere reaches all 17 (probed: a link to `bin/sd-skill-use` in a
  scratch directory runs, rc 0).
- The `source:bin/sd_install.py::command_report` docstring says `--user`
  "links no executable anywhere"; `AGENTS.md` "Calling Convention" says the
  same and calls by-path "the only convention the repository supports".
- The hand loop put 17 links in `~/bin/common`, on PATH from `~/.zshrc`.
  `--status` still prints `commands: 17 in bin/, not on PATH -- invoke by
  path (bin/sd)`: `command_report` asks whether a PATH *directory* resolves
  to `bin/`, which per-command links never satisfy, while its shadow check
  already treats such a link as this checkout's command.
- `skills/sd-handoff/SKILL.md:18` names the command bare, and two prose
  skills name `bin/` commands bare too: `skills/sd-plan/SKILL.md:103`
  (`sd-trackers`) and `skills/sd-research-repo/SKILL.md:57`
  (`sd-research-kit`). The documented invocation presumes PATH.

## Requirements

The four rules of the item body, numbered as it numbers them.

1. `--user` links every executable in `bin/` into one configured link
   directory (`~/.local/bin` by default, `--bin-dir DIR` otherwise), warns
   when no PATH entry resolves to that directory, records each link in the
   receipt, refuses to overwrite a file at the target that is not a link to
   this checkout's copy, keeps a link that already points there rather than
   rewriting it, and `--uninstall` removes exactly the links the receipt
   records and nothing else in that directory. The installer does not edit
   the shell: PATH membership is the owner's setup, and `--status` reports it.
2. `--status` counts per-command links: all 17, or `N of 17` naming every
   missing one, and keeps the shadow warning for a name that resolves to
   another install.
3. The README install table, the `command_report` docstring and the
   `AGENTS.md` calling convention state the new rule; the "invoke by path"
   hint stays for a checkout that was never `--user` installed.
4. One test per rule, fail-first, with the installer's 100% line-and-branch
   coverage gate (`.github/scripts/check-installer-coverage.sh`) still green.

## Acceptance criteria

- [ ] After `--user` into a scratch home, `<home>/.local/bin/<name>` is a
      symlink to `<checkout>/bin/<name>` for every executable, and
      `installed.json` carries one `kind: link` row per name; a regular file
      at one target makes `--user` exit 1, name that path, and write no
      render, link or receipt; `--uninstall` then leaves no receipt-named
      link and leaves an unrecorded link in the same directory untouched.
- [ ] `command_report` over three commands with two linked prints
      `2 of 3 resolve on PATH from this checkout (missing: <name>)`; with all
      three linked, `3 in bin/, 3 resolve on PATH from this checkout`.
- [ ] The README install table, the docstring and `AGENTS.md` name the link rule.
- [ ] `make check VENV=...` exits 0 and the installer coverage gate stays 100%.

## Decisions for the owner

Decided 2026-09-16, note #2616: the four recommendations were accepted as
written.

- **Default link directory.** `~/.local/bin`, with `--bin-dir DIR` as the
  override. On sol `~/.zshrc` prepends it (`path=("$HOME/.local/bin" $path)`)
  and appends `~/bin/common`; `~/.local/bin` existed and held no `sd*`;
  `~/.config/shell/env.sh` sets neither. The second machine was not
  measurable from the planning lane; the item states `~/.local/bin` is on
  PATH there, and if it is not, `--bin-dir ~/bin/common` reuses the directory
  `~/.zshrc` already appends.
- **Link by default, or only under `--bin-dir`.** By default under `--user`.
  A flag remembered per machine is the hand loop under another name.
- **What `--pull` does to links.** Nothing new: `--pull` re-runs `--user`,
  which keeps a link that points here, adds one for a new command, and prunes
  a receipt-named link whose command `bin/` no longer has.
- **The 17 hand links in `~/bin/common`.** Left in place. The receipt does not
  name them, so the installer leaves them; `~/.local/bin` precedes them on
  PATH, so they are neither counted nor shadows. The owner deletes them by
  hand or not.

## References

sd:969 carries the measurement and the four rules. Code:
`source:bin/sd_install.py::cmd_user`, `source:bin/sd_install.py::cmd_uninstall`,
`source:bin/sd_install.py::prune_stale`, `source:bin/sd_install.py::command_report`.

## Log

- 2026-09-16 created
