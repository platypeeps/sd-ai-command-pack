---
name: sd-deps
description: Batch-triage the open dependabot and renovate pull requests, merging only the safe class sequentially.
disable-model-invocation: true
---

# sd-deps

`sd-deps` classifies every open dependency-bot PR in this repository, merges
the safe class one at a time through the same gate criteria a human PR faces,
and parks the rest with a one-line recommendation each. Invocation is explicit
approval for those merges — and only for the class that qualifies.

## When to use

When the dependency-bot queue has grown past the point of reading PR by PR.
Not as a scheduled job: **the backbone ships no scheduler and schedules
nothing.**

## Classification

Each open PR lands in exactly one class, and the class decides the action:

- **Safe** — patch or minor bump, lockfile-only or manifest+lock, CI green,
  no source diff outside the dependency files. Merged.
- **Needs review** — major bump, a changed API surface, a source diff, or a
  transitive change the PR body does not explain. Parked with the reason.
- **Blocked** — CI red, conflicts, or a repo whose protection state means the
  merge would not be gated. Parked with the reason.

## The merge lane is serial

One PR merges at a time, each rebased and re-checked against the base it will
actually land on. Batching classification is the point; batching merges is how
a queue of independently-green PRs lands as a collectively-red main.

## Never

- **Never merge a red PR, and never rerun CI until it goes green.** A flake is
  a bounded rerun with the count reported, not a retry loop.
- **Never merge a major version bump** because CI passed. CI passing is not the
  same as the API being unchanged.
- **Never edit the dependency PR's branch** to make it mergeable. Close it and
  let the bot regenerate.
- **Never touch the repo's own automation** — the framework never registers,
  edits, or removes repo CI or cron.
- **Never accept a repo path** (R10-D6); the repository is the one enclosing
  cwd. Do not loop this across checkouts.
- **In `mode: minimal` or `guest`, do not merge at all** — report the
  classification and stop.

## State of the tooling

There is no `bin/sd-deps` yet. Today the agent lists the PRs (`gh` or the
GitHub MCP tools), classifies them by the rules above, and merges the safe
class one at a time with `sd-status` consulted for the repo's protection state
first.
