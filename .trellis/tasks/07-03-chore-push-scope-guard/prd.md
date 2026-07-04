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

## Acceptance Criteria

- [x] Chore-only direct push to main succeeds; a push touching any other
      path is rejected naming the offending files; the bypass env allows
      it with a notice.
- [x] Hook passes `shellcheck -S warning`; README documents install and
      bypass; test covers all three paths.
