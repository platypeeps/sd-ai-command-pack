---
name: sd-suggest
description: File a framework improvement to the configured tracker, deduplicating against what is already open.
disable-model-invocation: true
---

# sd-suggest

`sd-suggest` turns friction you just hit into a filed issue on the pack's own
tracker. Invocation is explicit approval to create that issue.

## When to use

The moment a framework limitation costs you a turn: a missing flag, a refusal
that was wrong, a gate that fired on the wrong thing. Suggestions filed later
from memory are vaguer and mostly do not get filed.

Not for: a bug in the *consuming* repo (that is a work item there), or a
preference with no incident behind it.

## The flow

1. Draft the suggestion locally: what happened, what you expected, and the
   smallest change that would have avoided it.
2. **Deduplicate first** — list the tracker's open issues through its list API
   and compare before creating anything. A duplicate issue is worse than no
   issue: it splits the discussion.
3. File to the configured tracker (GitHub issues on the pack repo by default;
   Jira where the repo's config maps to it).
4. **Delete the local draft on successful filing.** The tracker is the
   writable home; a leftover local copy is a second, staler one. On a failed
   filing the draft stays, and says why.

## Never

- **Never file without the dedup read.** Not "I searched my memory" — the list
  API call, actually made.
- **Never file a suggestion with no incident behind it.** Standing rule 1: a
  new gate, ledger, hook or rule needs a linked incident *and* a deletion
  criterion. A suggestion that proposes machinery states both.
- **Never keep a local ledger of filed suggestions.** The tracker is the
  system of record; anything local is a draft awaiting filing or nothing.
- **Never file into the consuming repo's tracker** unless its config maps
  there, and never into an upstream repo in `mode: guest` — the framework does
  not post in other people's trees.
- **Never accept a repo path** (R10-D6).

## State of the tooling

There is no `bin/sd-suggest` yet. Today: draft, dedup with
`mcp__github__list_issues` or `search_issues` against the pack repo, file with
`issue_write`, then delete the draft.
