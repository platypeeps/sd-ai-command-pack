---
name: sd-suggest
description: Record framework friction as a local proposal; publish an issue only when explicitly requested.
disable-model-invocation: true
---

# sd-suggest

`sd-suggest` records friction as a local `proposal` note on an existing work
item. Invocation authorizes that local write. Publishing to a tracker is a
separate action requiring an explicit destination.

## When to use

The moment a framework limitation costs you a turn: a missing flag, a refusal
that was wrong, a gate that fired on the wrong thing. Suggestions filed later
from memory are vaguer and mostly do not get filed.

Not for: a bug in the *consuming* repo (that is a work item there), or a
preference with no incident behind it.

## The flow

1. Describe what happened, what you expected, and the smallest change that
   would have avoided it. Read the item's existing proposals before adding
   another account of the same incident.
2. Record it with `sd suggest add <body> --item <work-directory-name>`. This
   writes a proposal note through `sd_db` in every repository mode and prints
   its note ID. It makes no GitHub issue request and requires no progress
   commit.
3. Stop after reporting the local note. If the user explicitly asks to file
   it, use `sd suggest publish --note <id> --to <owner/repo>`. The command reads
   open issues before posting and refuses when that read fails. There is no
   default tracker or automatic publication after capture. Keep the local note
   after publication; the command prints the issue URL and does not delete it.

## Never

- **Never publish without an explicit request and destination**, or without
  the dedup read. The list API call must actually succeed.
- **Never file a suggestion with no incident behind it.** Standing rule 1: a
  new gate, ledger, hook or rule needs a linked incident *and* a deletion
  criterion. A suggestion that proposes machinery states both.
- **Never turn capture into a tracker dependency.** A local proposal is a
  durable record even if no issue is ever filed.
- **Never infer publication consent from repository mode** or a configured
  tracker. Follow the repository's explicit authorization rules for external
  writes.
- **Never accept a repo path** (R10-D6).

## State of the tooling

The implemented commands are `sd suggest add` and `sd suggest publish`, verbs
under `bin/sd`. Filing is deliberately not an entrypoint of its own, so there is
no standalone command to look for. Capture currently requires
both a directory under `docs/work/` and its imported database row. If either is
missing, report the prerequisite; do not create a GitHub issue or a PRD merely
to work around it. `sd-status` is read-only and cannot create the missing row.
General capture without a planning artifact is not implemented yet.
