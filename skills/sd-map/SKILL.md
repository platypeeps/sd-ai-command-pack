---
name: sd-map
description: Build supporting repository artifacts (repomix, index, kb) out of tree, on demand, as a convenience only.
disable-model-invocation: true
---

# sd-map

`sd-map` builds the supporting artifacts a large repository makes useful —
a repomix bundle, a file index, a knowledge base — and writes them **outside
the repository**:

```
~/.local/share/sd-ai-command-pack/<repo-id>/artifacts/
```

Out of tree by construction. The consuming repo's tracked footprint does not
grow by one byte, and `git status` after a run is unchanged.

## When to use

When you are about to read broadly in an unfamiliar repository and a bundle or
index would genuinely save turns. That is the whole case for it.

## How it behaves

- **Flock'd.** Two sessions in the same repo do not both build; the second
  waits or reports that a build is in progress.
- **Rebuildable cache, never an input.** Everything under `artifacts/` can be
  deleted at any moment; `rm -rf` costs time and nothing else. No command reads
  it as a source of truth, and no gate consults it.
- Repo identity comes from the current directory (R10-D6). There is no
  repo-path argument.

## Never

- **sd-map is never a gate.** No command fails because the map is missing,
  stale, or absent. If you find yourself wanting to require it, that is a
  decision record with an incident and a deletion criterion, not a patch.
- **sd-map is never scheduled.** The backbone ships no scheduler and schedules
  nothing — no cron, no launchd, no post-commit hook, no "refresh it while I
  wait". It runs when a human or an agent asks for it, once.
- **Never write into the repository.** Not a dotfile, not a gitignore entry,
  not a cache directory. Out of tree means out of tree.
- **Never treat a stale artifact as current.** It records when it was built;
  if the repo has moved since, rebuild or read the source, and never cite the
  bundle as evidence of present-tense state.
- **Never let the artifacts become the only copy of anything.** Every fact has
  exactly one writable home, and this directory is not a home.

## State of the tooling

There is no `bin/sd-map` yet. Until it lands, read the source directly; do not
substitute an ad-hoc bundle written into the repo.
