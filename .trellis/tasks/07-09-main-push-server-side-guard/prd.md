# Add server-side backstop for direct main pushes

## Goal

Add a server-side (CI) backstop so the "chore commits may go straight to main,
everything else via PR" policy is enforced by GitHub, not only by an opt-in
local hook — reducing the single-maintainer bus-factor risk.

## Problem

The pack's branch protection requires the `CI Result` context but deliberately
leaves `enforce_admins` off, and the only thing policing direct-to-main pushes
is the opt-in local `.githooks/pre-push` hook (`07-03-chore-push-scope-guard`),
which the maintainer can bypass with a documented env var and which does not
run at all on a machine where `core.hooksPath` is not armed. The 2026-07-09
review flagged this as the main bus-factor exposure: with one human maintainer
(`git shortlog`: Sven Delmas 338 + sventhegrinch 99, same person), a mistaken
or unarmed direct push touching non-chore paths has no server-side check.

Note this interacts with `07-09-shell-hook-hardening` R1 (the same guard is
rename-blind); the server-side check should apply the corrected scope logic.

## Requirements

- R1: A CI job triggered on pushes to `main` fails when the pushed diff
  touches any path outside the allowed chore scope (`.trellis/tasks/**` and
  `.trellis/workspace/**`, matching the pre-push hook), so a non-chore direct
  push is caught server-side even when the local hook is unarmed or bypassed.
- R2: The check uses rename-aware diffing (`--no-renames` or equivalent) so a
  rename into a chore path cannot smuggle a source deletion past it — same
  correction as the local hook.
- R3: The failure is visible and actionable (clear message naming the
  offending paths); document the policy and the backstop in README /
  CONTRIBUTING alongside the existing direct-to-main section.

## Acceptance Criteria

- [ ] A push to main touching a non-chore path fails a CI check (verified via
      a scratch branch/commit or a dry-run of the check logic).
- [ ] Rename-into-chore is caught (mirror the hook test).
- [ ] Policy + backstop documented; interaction with the local hook explained
      (defense in depth, not a replacement).

## Non-goals

- Turning on `enforce_admins` / removing the maintainer bypass — this adds a
  detective control, it does not change the intentional chore-push policy.
- Multi-maintainer / access-governance changes beyond the technical backstop.
