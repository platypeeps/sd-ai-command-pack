---
title: Propagate the narrowed gito exclusion to the eight consumers still blanket-excluding pack config
status: planning
created: 2026-08-28
---
# Propagate the narrowed gito exclusion across the fleet

## Goal

A pull request whose entire diff is repo-owned configuration under
`.sd-ai-command-pack/` must leave a non-empty local review scope, so it is
reviewed rather than emptied out of scope.

This narrows exclusions only. It does not change how the adapter reports a scope
that is genuinely empty: a PR touching nothing but excluded generated surfaces
still surfaces as `local provider failure blocks remote routing` rather than as
an empty diff. That mapping is tracked as a non-goal below, with the residual
risk stated.

## Background

Every consumer's `.gito/config.toml` excludes all of `.sd-ai-command-pack/**`.
That path mixes two different things: installed payload the pack owns and
overwrites, and configuration the repository owns and edits. Excluding the
whole prefix excludes both.

When a PR touches only the repo-owned half, gito has nothing left in scope. It
prints `All changes belong to excluded files, nothing to review`, produces no
structured report, and exits in a way the adapter maps to a provider failure.
The coordinator then stops the review with `local provider failure blocks
remote routing` — a diagnostic that sends the operator looking for a broken
reviewer instead of an empty scope.

This is the same failure the `.trellis/workspace/**` carve-out already documents
in the same file. That comment explains why the journal and its index were
deliberately left reviewable: a finalization bundle is journal-only, so
excluding them left finalization PRs with nothing in scope. The
`.sd-ai-command-pack/` prefix has the identical shape and was not given the
identical treatment.

## Evidence

Observed 2026-08-28 on sd-github-review PR #161, which added the `codex` lane to
the repository's own `.sd-ai-command-pack/review.json`. The first review returned
`status: failed`, `diagnostic: "local provider failure blocks remote routing"`,
with gito `failed`. Running gito directly produced
`All changes belong to excluded files, nothing to review.`

Fixed there in `fd2263a` by replacing the blanket entry with the four copied and
generated surfaces by name — `bin/**`, `installed-targets.txt`, `manifest.json`,
`provenance.json` — leaving repo-owned files in scope. gito then reported
`No issues found in 2 files` and the review converged.

The fix was never propagated. Eight of the nine consumers still carry the
blanket exclusion:

| Consumer | Exclusion | Repo-owned config under the prefix |
| --- | --- | --- |
| rwbp-coordinator | blanket | none |
| loadsmith | blanket | `review-preflight.json` |
| hoa-manager | blanket | none |
| rwbp-website | blanket | `review-preflight.json` |
| mezmo_benchmark | blanket | `pr-body-scope.json` |
| se-ai-command-pack | blanket | `check.json` |
| people-profiles | blanket | `check.json` |
| anomaly-metric-creator | blanket | `pr-body-scope.json`, `review-preflight.json` |
| sd-github-review | narrowed | `review.json` |

Six of the eight own config under that prefix today, so the failure is reachable
for them now, not hypothetically. rwbp-coordinator and hoa-manager are latent
until they add repo-owned config.

Pack-refresh PRs are safe only by accident: `AGENTS.md` is not excluded, so a
version adoption keeps a non-empty scope even with the blanket entry in place.
That is why the 0.71.62 rollout never surfaced this.

## Requirements

- Replace the blanket `.sd-ai-command-pack/**` entry with the copied and
  generated surfaces by name in every consumer that still carries it.
- Derive the excluded set from what the installer actually writes rather than
  from a list transcribed into this PRD; a hand-copied list drifts the next time
  the installer's target set changes.
- Carry the explanatory comment, as `sd-github-review` and the
  `.trellis/workspace/**` carve-out both do. The next person to widen the
  exclusion needs to find the reason next to the entry.
- Fold the change into the 0.71.63 refresh campaign rather than opening a second
  round of PRs against the same eight checkouts.

## Non-goals

- Changing how the gito adapter maps an empty scope. Reporting an empty diff
  distinctly from a provider failure is a real improvement, but it is a separate
  change with its own blast radius.

  Residual risk of deferring it: a PR whose diff is entirely excluded generated
  surfaces — a provenance-only or manifest-only change, for instance — still
  reports as a provider failure after this task ships. Narrowing the exclusions
  removes the reachable cases enumerated above; it does not remove the class.
  Anyone who hits the residual case will see the same misleading diagnostic.
- Adding repo-owned config to the two consumers that have none.

## Acceptance Criteria

- [ ] No consumer's `.gito/config.toml` contains a blanket
      `.sd-ai-command-pack/**` entry; verified by enumerating the consumers from
      `docs/fleet/consumers.json` and grepping each checkout, not by checking the
      repositories this task happened to touch.
- [ ] For each consumer owning config under the prefix, a diff limited to that
      file leaves a non-empty gito scope.
- [ ] The excluded entries in each consumer match the installer's actual target
      set for that repository.
- [ ] Each edited file carries the explanatory comment.
