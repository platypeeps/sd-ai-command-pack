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

13. Developer identity in linked worktrees — **RESOLVED 2026-08-20: released
    and verified.** Shipped in the vendored refresh to 0.6.16-sd.7 (2bc34a9b).
    Reproduced this entry's own failure case in a throwaway worktree with no
    `.developer`: `python3 ./.trellis/scripts/get_developer.py` printed
    `sdelmas`, exit 0. The fallback at `common/paths.py:152-160` is live. Pack
    task `08-08-developer-identity-not-in-worktrees` archived the same day with
    `meta.closure = fixed-upstream`. Note: the main checkout's file is *read,
    never copied* — do not seed `.developer` into worktrees. The stale text
    below ("untagged and not on `fork/main`") described the state on 2026-08-17.
    Original entry:

    Developer identity in linked worktrees — upgrade-delivered but
    **unreleased**. `.trellis/.developer` is gitignored, so a fresh worktree has
    no identity and every identity-dependent script fails there. Upstream
    already resolves it through the main working tree
    (`common/paths.py:121-160` with `common/git.py:143-192`), introduced by
    `0740d1d6` on `chore/task-backlog-2026-08` — untagged and not on
    `fork/main`, so no vendored refresh can carry it yet. Pack task
    `08-08-developer-identity-not-in-worktrees` is parked on that release chain
    and holds a staged suite (that task's
    `research/staged_test_worktree_identity.py`, kept outside `tests/` because
    the repo gate fails on any skip) which skips entirely against vendored
    0.6.14 and passes 9/0 against a copy of upstream's scripts. Resume when a
    refresh makes it run with zero skips.
14. Identity reporting disagrees across eight gates — **RESOLVED 2026-08-20 as a
    recorded keep-workaround decision** (the third resolution form this
    register's acceptance criteria allow). The repository owner declined the
    work: pack task `08-17-trellis-identity-message-consistency` is archived
    with `meta.closure = wont-do`. No Trellis-fork task will be filed and the
    patch named below was never written. The defect is real and stays in the
    tree — five disagreeing diagnoses across nine gates, four with no hint, and
    no way to distinguish an absent identity from an unusable one. Declined on
    cost: a ~400-500 line refactor across seven upstream files, with a breaking
    change to `regression.test.ts` (~:12846), which asserts
    `expect(payload.error).toBe("No developer set")` by exact equality. Reopen
    criteria and full rationale are in that task's archived `prd.md`. Original
    entry:

    Identity reporting disagrees across eight gates — Trellis fork task to file,
    specified in pack task `08-17-trellis-identity-message-consistency`, which
    stays **open, not parked**: the patch, its staged tests, and this entry's
    update are all executable in this repository; only the uptake waits on the
    same release chain as entry 13. `get_developer` returns a name or `None`, so
    no site can tell "no identity anywhere" from "the identity file is
    unreadable", and most of them recommend creating a second identity for a
    broken first one (`get_developer.py:21` offers no remedy at all, and
    `common/task_queue.py:138` raises a bare `Developer not set`). The eight
    gates span four media: stderr prose, a JSON contract with an upstream
    regression test, two separate returned context documents, and a raised
    `ValueError`. Upstream's `[worktree-identity]` suite
    (`regression.test.ts:12526-12723` [absent: upstream Trellis repository]) already pins some of that wording. Needs
    one resolution carrying a reason plus one shared diagnosis, rendered per
    medium. The patch is that task's Step 1 and is not written yet.

## Acceptance criteria

- [ ] Every entry resolves to a named Trellis-fork task path, an
      upgrade-verification checkbox in 08-08-trellis-upgrade, or a recorded
      keep-workaround decision.
- [ ] `research/` holds all nine source PRDs verbatim, plus the
      paste-ready material for entries added after the consolidation.
- [ ] Register closes only when every entry is resolved.

## Evidence

2026-08-08 consolidation; source PRDs copied at drop time from git HEAD.

2026-08-20: entry 13 resolved (released in 0.6.16-sd.7, verified in a
throwaway worktree); entry 14 resolved as a keep-workaround decision after the
owner declined the upstream refactor. Two entries down; the register stays open
on the remainder.

2026-08-17: entries 13 and 14 added from
`08-08-developer-identity-not-in-worktrees` and its split successor
`08-17-trellis-identity-message-consistency`. Paste-ready material and the
two-tree test evidence are in
`research/2026-08-17-trellis-developer-identity-worktree-and-reporting.md`.
