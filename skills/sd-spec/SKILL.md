---
name: sd-spec
description: Refresh docs/spec on the PR branch so the repository's knowledge artifacts match what shipped.
disable-model-invocation: true
---

# sd-spec

`sd-spec` updates `docs/spec/**` on the current PR branch, in the same commit
range as the change that made it stale. Invocation is explicit approval to
write under `docs/spec/` (and, with `--retro`, to append review learnings).

## When to use

- As the second stage of `sd-ship`, before docs-lint and the commit.
- Whenever a merged change made a spec page wrong. A spec page that describes
  last month's behaviour is worse than no page.

## What it does

- Rewrites the spec pages the change invalidated — in place, on the branch, so
  the correction and the change land together.
- Maintains `index.md` in every spec directory: it links each of its siblings,
  so no page can be reached only by guessing. `sd-docs-lint` rule 4 fails
  otherwise.
- In a repo that already has an `ARCHITECTURE.md` or equivalent, `docs/spec/`
  is a link index to it rather than a second copy.
- `--retro` appends review learnings — the patterns that came back repeatedly
  in review — to the spec's own learnings page.

## Never

- **Never generate a spec page from the diff alone.** A page nobody would read
  is footprint, not knowledge; the five gates count spec pages, not words.
- **Never commit derived state.** Anything that can be recomputed at run time
  is recomputed at run time — committed derived state is permanent staleness.
- **Never write outside `docs/spec/`** (plus the learnings page under
  `--retro`).
- **Never accept a repo path** (R10-D6); the repository is the one enclosing
  cwd.
- **Never touch the upstream tree in `mode: guest`.**

## State of the tooling

There is no `bin/sd-spec` yet. Today the agent performs the refresh and
`bin/sd-docs-lint` verifies rule 4 (`--spec-dir`, default `docs/spec`).
