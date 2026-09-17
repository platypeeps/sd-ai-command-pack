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
- Where the policy is written: `WORKFLOW.md` in the pack checkout, which
  states the two flows, what runs by default, what is opt-in, what is
  advisory, what never touches a shared repository, the review table with its
  caps, the path for a change at each size, and the modes with their
  resolution rule. `sd-help` names that page and does not restate it.

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
  `se-humanizer`, `se-review-skills`) keep their old names in historical
  records only.
- **Never run anything on the user's behalf from the catalog.** Listing a
  command is not invoking it — the commands are the surfaces that
  pre-authorize side effects, and each is invoked deliberately.
- **Never claim a plugin is registered because it exists on disk.**
  Registration happens only through `sd plugin add`; there is no disk scanning.

## The store and plugin contract

`sd plugin add` and `sd store` are the two verbs a plugin author meets, and
the registry holds three rules about what they accept and what they read.
Write a kind with the eight keys `KIND_KEYS` in `bin/sd` holds and no other; a
ninth key is a decision record before it is a commit, and `validate_kind`
turns a manifest carrying one away by name (R11-D14). Change a field with
`sd store add` or `sd store set` and expect the note back byte-identical
apart from the one line `edit_field` writes; do not parse a note and render it
back (R11-D27). Read with `sd store list` or `sd store get` knowing that every
query lists the vault directory at the moment of asking, in `store_list`, so a
note written by hand or by Obsidian is visible to the next query with no sync
step (R5-D1). The rows in `bin/sd_rules.py` state each rule; none is restated
here. `bin/sd-rules --for <path>` prints the rows in scope for the file being
written.

## State of the tooling

`sd-help` has no `bin/` half, and is not waiting for one — this file already
says why in its opening paragraph: it is the one surface in this set that is a
skill rather than a command, because a catalog pre-authorizes nothing. Three
reads answer it: a directory listing (`skills/` in the pack checkout, for the
authored surfaces), a file (the installer's `installed.json` `owned[]`, for what
is actually rendered on this machine), and one command (`sd plugin list`, for
the registered plugins).
