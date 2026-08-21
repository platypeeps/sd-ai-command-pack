# Correct the repo-relative claim the thin repoint contradicts

## Goal

Two authored command-source lines assert that a script path is reachable "at
that path relative to the repository root". The thin conversion rewrites that
path to an absolute `~/.agents/bin/...` location and leaves the assertion
standing, so every thin consumer carries a sentence that contradicts the path
in the same clause. Make the sentence true in both install shapes.

## Context

The two sources are `.github/command-sources/sd-review-learnings.md` and
`.github/command-sources/sd-housekeeping.md`. Each contains one instance of:

> ...is resolvable, either as a bare command on `PATH` or as a file at that
> path relative to the repository root.

In a **fat** install the claim holds: the path reads `scripts/sd-ai-command-pack-*`
and that file really is at that path under the repository root. In a **thin**
install `installer/thin.py` rewrites the path to `~/.agents/bin/...`, which is
neither a bare command nor repo-relative, while the clause still says it is.

Measured across every thin consumer on this machine — hoa-manager, loadsmith,
people-profiles, se-ai-command-pack, sd-github-review, anomaly-metric-creator —
each carries exactly two affected files, both under `.github/prompts/`, for 12
sites. Only the GitHub prompt surface survives conversion; the Claude and
opencode adapters resolve through the machine plugin and carry no such clause.

A third source uses the same closing words. `.github/command-sources/sd-audit-repo.md`
reads "either inside the installed skill payload or at
`.agents/skills/sd-audit-repo/charters/` relative to the repository root". It
does **not** carry this defect: the rewrite leaves that path alone, so the
sentence still calls a genuinely repo-relative path repo-relative. It is
internally consistent, which is the property this task is restoring.

It does have a smaller, different problem — measured on hoa-manager, a thin
consumer vendors no `.agents/skills/sd-*` at all, so that second arm of the
disjunction is unsatisfiable there. That is a dead fallback, not a
contradiction, and the first arm ("inside the installed skill payload") is the
one that holds. Recorded here so the next reader does not have to re-derive it;
not fixed here, because a fix means deciding whether the fat-install fallback
should survive at all, which is a different question from the one this task
asks.

### Why this was invisible

This is the second defect of its family found by onboarding one repository, the
first being the `sd-review` adapter naming a machine-scope script that thin
consumers do not carry. Both share a failure mode: the adapter surface survives
conversion while the thing it describes does not, and a thin consumer's resweep
has nothing left to remove, so it reports clear. They become visible only when a
fat consumer converts, and there had not been one in a long time.

## Requirements

- **Fix at the authored source, not the generated mirrors.**
  `.github/command-sources/*.md` feeds the generated surfaces; editing a mirror
  is undone by the next `make generate`.
- **The corrected sentence must be true in both shapes**, fat and thin, without
  the rewrite having to know about it. A conditional rewrite that strips the
  clause only during conversion would make the thin text correct by adding a
  second thing that can drift out of step with the first.
- **Do not touch `sd-audit-repo.md`.** Its use of the same closing words is
  internally consistent; its separate dead-fallback problem is recorded above
  and belongs to its own decision, not to this one.
- **Do not weaken any gate.** No test asserts this clause today; if one starts
  failing, the answer is to understand why, not to relax it.
- **Ship it.** A source fix that is not released reaches no consumer. The pack
  is at 0.71.41; this needs a version bump, a changelog entry, and a release
  prep, on the same path 0.71.41 itself took.

## Acceptance Criteria

- [x] Neither `.github/command-sources/sd-review-learnings.md` nor
      `.github/command-sources/sd-housekeeping.md` claims the path is relative
      to the repository root.
- [x] `.github/command-sources/sd-audit-repo.md` is unchanged.
- [x] `make generate` propagates the change to all generated mirrors, and no
      mirror still carries the clause for these two commands.
- [x] `make check` passes.
- [x] The whole-tree review preflight reports zero failures in this repository.
- [x] The version is bumped past 0.71.41 with a matching `CHANGELOG.md` entry,
      and the release prep is clean. Shipped as 0.71.42 in #531.
- [x] A converted-text check confirms the shipped thin rewrite of both prompt
      surfaces no longer contradicts itself.

## Out Of Scope

- Refreshing the six thin consumers onto the new version. They pick the fix up
  on their next refresh; the fleet refresh campaign is separately tracked and
  is not a precondition for landing this.
- The `sd-audit-repo.md` dead fallback arm, which is a different defect needing
  a different decision.
