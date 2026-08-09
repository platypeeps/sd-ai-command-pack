# Upgrade vendored Trellis 0.6.7 to 0.6.14

## Problem

The pack vendors Trellis 0.6.7 in `.trellis/scripts/`; the fork at
~/repos/ai/Trellis is at 0.6.14 — seven releases ahead. Verified 2026-08-08:
the pack's `.trellis/scripts` tree is byte-identical to the 0.6.7 release
templates (`diff -rq --exclude=__pycache__` exit 0) — no local script patches
to preserve, so the upgrade carries no merge risk on the scripts surface.
(Original framing called this a "file swap"; the mechanism was amended in
planning to the official `trellis update` covering the whole vendored
surface — see requirement 1 and design.md.)

Staying on 0.6.7 keeps live defects the upstream already fixed:

- `task.py create` seeds `base_branch` from the currently checked-out branch
  (fixed upstream in >=0.6.8, commit 113cb5fb/9846fe66: resolves the repo
  default branch). Observed live during the 2026-08-08 backlog consolidation:
  ten tasks created on `chore/backlog-consolidation` all seeded
  `base_branch: chore/backlog-consolidation` and required manual correction.
- Hook UTF-8 stdin fixes (fixed upstream). Note: the statusline-specific fix
  does NOT land here — the statusline hook is opt-in, excluded from
  `trellis update`, and not installed in this checkout.
- Journal merge conflicts (upstream adds `merge=union` for journals).
- No machine-readable output: `task.py --json` exists in 0.6.14; pack wrappers
  currently parse console prose.

## Requirements

1. Upgrade the Trellis-owned template surface to 0.6.14 and verify
   `.trellis/scripts` byte-identity against the 0.6.14 release afterward.
   Scope amendment (2026-08-08 planning): the pack's local
   `.trellis/.template-hashes.json` tracks 114 Trellis template files well
   beyond `.trellis/scripts` — trellis-* skills for five platforms
   (`.claude/skills`, `.agents/skills`, `.opencode/skills`, `.github/skills`),
   `.claude/agents`, `.claude/hooks`, `.claude/commands`,
   `.claude/settings.json`, `.codex/hooks`, `.gemini/hooks`,
   `.github/copilot*`, `.opencode/*`, `AGENTS.md` managed block, and
   `.trellis/workflow.md`. A scripts-only swap would leave those at 0.6.7
   against 0.6.14 scripts; the upgrade must move the whole vendored surface
   together via the official `trellis update` mechanism (see design.md).
2. Re-run the vendored-path preflight lanes and the full suite; the
   byte-identical-to-release property is the compatibility proof.
3. Adopt `task.py --json` in pack wrappers that parse console prose (enumerate
   with a repo-wide grep for `task.py` invocations that pipe/parse output).
4. Post-upgrade verification feeds 08-06-task-create-base-branch-seed (seed
   correctness) and 08-08-upstream-handoff-register (uptake evaluation of the
   three 07-09 upstream items originally gated on 0.6.8).

## Acceptance criteria

- [ ] `.trellis/scripts` byte-identical to Trellis 0.6.14 templates.
- [ ] Whole vendored surface converged: post-apply `trellis update --dry-run`
      reports zero pending template changes.
- [ ] `.trellis/.version` reads 0.6.14.
- [ ] `task.py create` on a feature branch seeds `base_branch` = repo default.
- [ ] `make release-prep` green (regenerates exact-payload release evidence,
      then runs the `make check` maintainer gate: test + lint + audit +
      full-check); preflight 0 failures.
- [ ] Wrapper `--json` adoption list enumerated and either done or split out;
      adoption follows template-first discipline with manifest/changelog/
      release bookkeeping.
- [ ] Downstream evidence packet recorded in the research/ dirs of
      08-06-task-create-base-branch-seed and 08-08-upstream-handoff-register.

## Evidence

2026-08-08 five-agent review + cross-repo consolidation session; byte-identity
verified against installed @mindfoldhq/trellis 0.6.7 package.
