# Upgrade vendored Trellis 0.6.7 to 0.6.14

## Problem

The pack vendors Trellis 0.6.7 in `.trellis/scripts/`; the fork at
~/repos/ai/Trellis is at 0.6.14 — seven releases ahead. Verified 2026-08-08:
the pack's `.trellis/scripts` tree is byte-identical to the 0.6.7 release
templates (`diff -rq --exclude=__pycache__` exit 0), so this upgrade is a file
swap, not a merge — no local patches to preserve.

Staying on 0.6.7 keeps live defects the upstream already fixed:

- `task.py create` seeds `base_branch` from the currently checked-out branch
  (fixed upstream in >=0.6.8, commit 113cb5fb/9846fe66: resolves the repo
  default branch). Observed live during the 2026-08-08 backlog consolidation:
  ten tasks created on `chore/backlog-consolidation` all seeded
  `base_branch: chore/backlog-consolidation` and required manual correction.
- Statusline UTF-8 stdin crash (fixed upstream).
- Journal merge conflicts (upstream adds `merge=union` for journals).
- No machine-readable output: `task.py --json` exists in 0.6.14; pack wrappers
  currently parse console prose.

## Requirements

1. Swap `.trellis/scripts/` to the 0.6.14 templates; verify byte-identity
   against the 0.6.14 release afterward.
2. Re-run the vendored-path preflight lanes and the full suite; the
   byte-identical-to-release property is the compatibility proof.
3. Adopt `task.py --json` in pack wrappers that parse console prose (enumerate
   with a repo-wide grep for `task.py` invocations that pipe/parse output).
4. Post-upgrade verification feeds 08-06-task-create-base-branch-seed (seed
   correctness) and 08-08-upstream-handoff-register (uptake evaluation of the
   three 07-09 upstream items originally gated on 0.6.8).

## Acceptance criteria

- [ ] `.trellis/scripts` byte-identical to Trellis 0.6.14 templates.
- [ ] `.trellis/.version` reads 0.6.14.
- [ ] `task.py create` on a feature branch seeds `base_branch` = repo default.
- [ ] Full check green; preflight 0 failures.
- [ ] Wrapper `--json` adoption list enumerated and either done or split out.

## Evidence

2026-08-08 five-agent review + cross-repo consolidation session; byte-identity
verified against installed @mindfoldhq/trellis 0.6.7 package.
