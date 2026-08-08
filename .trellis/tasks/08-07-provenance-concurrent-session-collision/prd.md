# Gitignored provenance.json collides between concurrent sessions

## Goal

Stop one session's installer run from blocking `sd-check` for every other
session sharing the same working copy, and stop the resulting failure from
being invisible to CI.

## Problem

`.sd-ai-command-pack/provenance.json` records the installed pack version. It is
gitignored (`.gitignore:26`), so it is per-working-copy state, not per-branch
state — but `sd-check`'s `pack.install-audit` reads it and compares it against
the checked-out tree.

Two sessions sharing one clone therefore fight over one file:

1. Session A works a release branch and runs `install.py .`, stamping `0.64.25`.
2. Session B, on an unrelated branch cut from `0.64.24`, runs `sd-check`.
3. `pack.install-audit` fails for B citing "pack 0.64.25" — a version B never
   installed, from a branch B never touched.

Observed on 2026-08-07 against PR #351. The audit failed on a branch whose
entire diff was a single Markdown file, and all three files the diagnostic
named were byte-identical to `origin/main`. Root-causing it cost roughly forty
minutes, most of it spent looking for a defect in the branch's own content.

The concurrent session was real and was later confirmed: it had cut
`fix/pack-helper-defaults-and-guards` from `main` and committed
`chore(release): bump to 0.64.25 for the helper-default fixes`.

### Why CI does not catch it

CI clones fresh, so the file is absent and regenerated consistently. The
failure exists only in shared local checkouts. Local `sd-check` and CI
`sd-check` therefore disagree about the same commit, and the local one is the
one that blocks a human.

### Why the recovery is not obvious

The remedy is to re-stamp by running `install.py .` from the current checkout —
an installer invocation, which reads as a mutating, potentially wide-ranging
action when the reported problem is "a check failed". The safe pre-flight is
`install.py . --dry-run`, which confirms the blast radius is exactly one
gitignored file. Neither the diagnostic nor the remediation text mentions
either command.

## Requirements

### Functional

- `pack.install-audit` must distinguish "the tree and the installed pack
  genuinely disagree" from "a gitignored per-working-copy file was stamped by
  something outside this branch".
- The diagnostic must name `provenance.json`, say that it is gitignored and
  therefore shared across branches in this working copy, and give the exact
  re-stamp command with its `--dry-run` pre-flight.
- A repository whose working copy is shared by concurrent sessions must not
  produce a check failure attributable to a branch that did not cause it.

### Non-functional

- No change to CI behavior; CI already regenerates the file cleanly.
- The audit must not start ignoring genuine version drift.

## Open questions

1. Should the audit treat a provenance version *ahead* of the tree differently
   from one behind? Ahead is the concurrent-session signature; behind is a
   stale install.
2. Should the file move to per-worktree state so branches and worktrees stop
   sharing it? That is the structural fix and is larger than the diagnostic fix.

## Acceptance Criteria

- [ ] `pack.install-audit` failing solely on a provenance mismatch names the
      file, its gitignored status, and the re-stamp command
- [ ] The diagnostic mentions `install.py . --dry-run` as the pre-flight
- [ ] A test covers the ahead-version case, distinguishing it from genuine drift
- [ ] Open question 2 is answered in `design.md` with a recommendation

## Notes

Filed 2026-08-07. Sixth session in which the shared-checkout hazard produced a
misleading failure; the first in which the concurrent session was positively
identified rather than inferred.
