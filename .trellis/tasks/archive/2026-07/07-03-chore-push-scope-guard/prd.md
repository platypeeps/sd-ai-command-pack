# Chore-scope pre-push guard for direct main pushes

## Goal

Formalize the branch-protection decision: Trellis chore commits may push
directly to `main` under the maintainer bypass; everything else goes
through pull requests — and make the bypass mechanically honest.

## Requirements

- R1: A tracked `.githooks/pre-push` hook rejects direct pushes to `main`
  whose diff touches any path outside `.trellis/tasks/**` and
  `.trellis/workspace/**`, listing the blocked paths and the remedy.
- R2: A documented one-shot bypass
  (`SD_AI_COMMAND_PACK_CHORE_SCOPE_BYPASS=1`) exists for deliberate
  exceptions; branch deletions and unknown remote heads are handled
  without false positives (deletion skipped, unfetched remote fails
  closed with a fetch hint).
- R3: The README documents the convention, the `core.hooksPath` install
  command, and the bypass; the hook itself passes the repo shellcheck
  gate.
- R4: A regression test drives the hook through allowed chore pushes,
  blocked code pushes, and the bypass path against a scratch origin.

## Non-goals

- No change to GitHub-side protection (`enforce_admins` stays off by
  design); no fleet distribution of the hook in this round — consumers
  have their own conventions, and shipping it as a pack template is a
  separate decision.

> **Deferral resolved 2026-07-07: keep the hook repo-local; no
> blanket fleet distribution.** Initial 10-of-10 sampled chore commits
> were PR-routed, but a fuller 100-commit-per-repo audit the same day
> corrected the picture: anomaly-metric-creator (2, 2026-06-26),
> rwbp-website (1, 2026-07-02), and rwbp-coordinator (1, 2026-07-03)
> each had rare human direct-to-main Trellis chore pushes, and
> loadsmith had 14 (~14% of commits — an active direct-push chore
> workflow). Outcome: `enforce_admins` was enabled on
> anomaly-metric-creator, rwbp-website, and rwbp-coordinator on
> 2026-07-07 (rare pushes become micro-PRs; no automation affected),
> making the hook definitively unnecessary there; mezmo_benchmark
> already had it on. loadsmith — whose workflow mirrored this
> pack-source repo (~14% direct chore pushes) — was also flipped to
> `enforce_admins` on later the same day by explicit owner choice,
> trading that convenience for uniform server-side enforcement. All
> five fleet repos now enforce PR-only mains; the hook is moot
> fleet-wide and remains exclusively in this pack-source repo, the
> only repo retaining the direct-to-main chore-commit model.

## Acceptance Criteria

- [x] Chore-only direct push to main succeeds; a push touching any other
      path is rejected naming the offending files; the bypass env allows
      it with a notice.
- [x] Hook passes `shellcheck -S warning`; README documents install and
      bypass; test covers all three paths.
