---
name: sd-help
description: Catalog the sd-* surfaces actually installed on this machine and the plugins registered with the pack.
---

# sd-help

`sd-help` answers "what is available here". It is the one surface in this set
that is a **skill, not a command** — the design's stated exception, because a
catalog pre-authorizes nothing and loading it has no side effect. That is why
this file carries no `disable-model-invocation` key, and why adding one would
be wrong.

## What it reports

- Every installed `sd-*` skill and command, **enumerated from disk at run
  time** — the rendered surfaces under the platform homes the installer owns
  (`~/.claude`, `~/.codex/skills`, `~/.config/opencode/commands`, and the
  Antigravity root once probe P1 passes).
- The plugins registered with the pack (`sd plugin`), with their declared
  prefix and interface version.
- The pack banner: checkout, commit, branch, and whether that checkout is
  dirty.

## The one rule that keeps it honest

**Enumerate; never recite.** A hardcoded list of the twelve commands is a list
that drifts the first time one is added or retired, and it drifts silently
because nothing reads it. If you are answering "what commands exist", read the
`skills/` tree or the installed renders — do not answer from this file, from
memory, or from the design's table.

Correspondingly: **when a surface is added or removed, no list here needs
editing** — which is the property that makes the enumeration worth having.

## When to use

- The user asks what sd-* can do, or which command fits a situation.
- You are about to guess at a command name or a flag. Look instead.
- Something referenced a surface you cannot find; the catalog says whether it
  is installed, missing, or renamed.

## Never

- **Never invent a command, subcommand, or flag** that the enumeration did not
  return. A plausible-sounding `sd-*` verb that does not exist wastes a turn
  and teaches the user a name that will fail again.
- **Never present a legacy `se-*` name as current.** Merged surfaces renamed to
  `sd-*` at the fold; retired ones (`se-help`, `se-brand-voice`,
  `se-humanizer`) keep their old names in historical records only.
- **Never run anything on the user's behalf from the catalog.** Listing a
  command is not invoking it — the commands are the surfaces that
  pre-authorize side effects, and each is invoked deliberately.
- **Never claim a plugin is registered because it exists on disk.**
  Registration happens only through `sd plugin add`; there is no disk scanning.

## State of the tooling

There is no `bin/sd-help` yet. Today: read `skills/` in the pack checkout for
the authored surfaces, and the installer's `installed.json` `owned[]` for what
is actually rendered on this machine.
