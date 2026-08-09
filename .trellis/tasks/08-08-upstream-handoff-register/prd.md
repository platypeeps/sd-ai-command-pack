# Upstream handoff register

## Problem

Nine pure upstream-Trellis handoff items occupied nine task directories in
this repo's backlog, none executable here. The 2026-08-08 consolidation
absorbed them into this single register task; their full original PRDs are
preserved verbatim in this task's `research/` directory.

## Register

Each entry must resolve to exactly one of: a filed task in the Trellis fork
(~/repos/ai/Trellis), an upgrade-delivered fix (verify during
08-08-trellis-upgrade), or a deliberately kept pack workaround.

1. 07-27-upstream-claude-statusline-utf8-stdin-fix — upgrade-delivered
   (statusline fix in <=0.6.14); verify post-upgrade.
2. 07-30-upstream-task-start-branch-recording — Trellis fork task
   (start-time branch recording); the untested compensating-write-path gap is
   its own entry below.
3. 07-30 compensating-write-path test gap — flagged "pack-local test gap";
   stays pack-owned.
4. 08-04-trellis-upstream-archive-commit-lock-retry — Trellis fork task
   (archive index.lock retry).
5. 07-09-upstream-trellis-opencode-context-exec-hardening — Trellis fork
   runtime-hardening audit (kept pack workaround meanwhile).
6. 07-16-upstream-trellis-hook-shell-semantics — Trellis fork
   runtime-hardening audit (kept pack workaround meanwhile).
7. 07-27-upstream-trellis-subagent-context-read-hardening — Trellis fork.
8. 07-09-upstream-issue-closure-cleanup — post-upgrade uptake evaluation
   (originally gated on 0.6.8 reaching the fleet; evaluate during
   08-08-trellis-upgrade).
9. 07-09-upstream-platform-state — post-upgrade uptake evaluation (same).
10. 07-09-upstream-trellis-api-cleanup — post-upgrade uptake evaluation
    (same).
11. Create-time empty-metadata refusal — Trellis fork task
    `08-08-create-empty-metadata-rejection` (~/repos/ai/Trellis): `task.py
    create` must refuse a missing/blank description and blank title before
    creating directories. Parked from
    08-06-task-create-base-branch-seed (see its PRD "Adversarial review
    dispositions"); at uptake, the pack's description predicate-divergence
    pin flips to an equality assertion.
12. `task.py create` documented examples omit `--description` on
    Trellis-managed surfaces (added 2026-08-08 by
    08-06-task-create-base-branch-seed's docs audit; these files are owned
    upstream and must not be edited locally): `.trellis/workflow.md:46,317`,
    `.trellis/scripts/task.py` usage text (`:7`, `:381-384`, `:410-412`),
    and the four platform copies of `trellis-brainstorm/SKILL.md:37` plus
    `trellis-meta/references/local-architecture/task-system.md:62,109`.
    Upstream should carry `--description` in every runnable example once
    entry 11 makes it required.

## Acceptance criteria

- [ ] Every entry resolves to a named Trellis-fork task path, an
      upgrade-verification checkbox in 08-08-trellis-upgrade, or a recorded
      keep-workaround decision.
- [ ] `research/` holds all nine source PRDs verbatim.
- [ ] Register closes only when every entry is resolved.

## Evidence

2026-08-08 consolidation; source PRDs copied at drop time from git HEAD.
