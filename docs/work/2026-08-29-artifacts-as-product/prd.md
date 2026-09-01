---
title: sd-ai-command-pack v1.0 — artifacts as product
status: in_progress
branch: task/08-29-artifacts-as-product-m0
created: 2026-08-29
---

# PRD — artifacts as product

## Problem

The maintainer spends too much time managing Trellis, three packs, and the workflow itself. Principles:
prd/design/implement discipline lives in GitHub; the framework helps enforce, never a burden of
conflicting approvals; KISS; honor preexisting repo/org setups; zero externally visible footprint
beyond doc artifacts; collaborators never need to adopt the framework; old ways are removed after
agreement (ratchet). The framework must serve research, prototyping, development, and personal
work; OSS participation respects target-project processes (fork-first); sub-agents and worktrees
are encouraged; sessions stick to their repos.

## Measured cost

| Cost | Number |
|---|---|
| Commits, 60 days | 2,968 (532 PRs, ~9 PRs/day) |
| Bookkeeping share of non-merge commits | 1,187 / 2,428 = **49%**; 389 are `chore: record journal` |
| PRs whose last commit is `feat` | **10 of 532 (2%)** |
| Open Trellis tasks in pack | 101; **98 about pack machinery**; 100 never left `planning` |
| Fleet-wide open tasks | ~306 Trellis tasks across 10 consumers at r1 (217 item dirs in the 7 platypeeps repos, re-counted 2026-08-29), 300 in `planning` |
| Most churned file | `review-preflight.mjs` (historical — since deleted, lives in git history): 125 commits, 79 fixes, 6,448 LOC at peak |
| Releases since 07-30 | 126 (4.2/day); all 10 consumers 4 versions behind |
| Copies of every shipped script | 4 |
| Tests vs code | tests 92k lines > scripts 54k + installer 11k |
| Per-session injection | ~16 KB per SessionStart; consumer settings.json hooks block ~67 lines (r1's "2,632" not reproducible — struck) |
| Consumer footprint | 45–80k LOC per repo, 40–60% of tracked files |
| Friction clusters from memory (13) | **11 pack/Trellis machinery, 1 mixed (Copilot rounds), 0 product** |
| system repo | 55 tools, 30 launchd jobs; dashboard.py 1,728 LOC (2,475 with the rest of the dir — r1's 3,177 was wrong), stdlib, tailnet-bound, iOS PWA in use |
| Skill-intake pipeline outcome | 10 proposals → 8 declined, 2 filed, **0 adopted** (6 stages, 4 repos) |
| Rollout ceremony | 8 releases × 10 consumers ≈ 80 two-line PRs in 4 days; skew structural |

**Root cause.** The pack gates the *process* (receipts, ledgers, digests, session numbers) instead
of the *artifacts*. Every process gate stores state that drifts from git/GitHub and then needs its
own repair machinery. Second cause: built for a fleet operator across 18 platforms; the audience is
one engineer plus agents.

## Requirements

1. The unit of work is a git-tracked artifact set (`prd.md`, optional `design.md` /
   `implement.md`) under `docs/work/<date>-<slug>/`; no runtime state is committed.
2. Merge authority is GitHub branch protection **where protection is enforcing**; local
   tooling mirrors it read-only and reports the gap where it is not, rather than asserting a
   guarantee the config does not provide.
3. The framework never edits a tracked repo file for its own purpose; the entire
   tracked footprint in a consuming repo is `<work>/**` (+ opt-in CI workflow files).
4. Collaborators never adopt the framework: CI checks report-and-pass for unlisted
   authors; `minimal`/`guest` modes cannot grow it.
5. One prefix (`sd-*`), one repo, machine-scope install, no release train.
6. Old mechanisms are removed as their replacements land (ratchet); no new
   gate/ledger/hook/rule without a linked incident and a deletion criterion.
7. Session handoff on the same machine works without git or GitHub.
8. Codex lanes run on the ChatGPT subscription only, never API billing.

## Acceptance criteria

- [ ] M0 tombstone release 0.72.0 tagged; `Pack version update check` on any consumer names it.
- [x] Step 0: release/gate jobs deleted; every remaining CI job green.
- [x] Steps 1–3: one copy of every shipped file; `.trellis` gone from the pack; new installer + 12 skills land; scratch-repo `sd-plan` → `sd-ship` E2E merges a PR with only `<work>/**` tracked.
- [x] Step 3-c: one removal PR per consumer (9); zero trellis/router greps per repo; CI green.
- [ ] Steps 4–7: routers retired, se-* folded as sd-*, machine cleanup leaves `handoff/`+`intents/` intact, backlog parked, 1.0.0 tagged.
- [ ] Steps 8–11: plugin interface, sd-writing-pack migrated, vault move last with golden-corpus byte-compare green.
- [ ] 60-day criteria evaluated for R10-D1 (backlog lane) and R10-D3 (handoff hook).
- [ ] `chore: record journal` commits = 0; bookkeeping share of non-merge commits < 5%.

**2026-09-01 — two of the unticked boxes above are half-true, and are left
unticked rather than rounded up.** Checked from the repository and the remote,
not from `implement.md`'s prose.

- *M0 tombstone 0.72.0.* The tag half holds: `git ls-remote --tags origin`
  returns `fea7e1331d1dad25ed4d1ab81abebf03f8f156ee	refs/tags/v0.72.0`. The
  consumer half has no subject any more — the `Pack version update check` that
  was to name the release went with the rest of the framework footprint in the
  nine step 3-c removal PRs, and the string now survives only in `CHANGELOG.md`
  and in this file. A clause whose subject was deleted is not a clause that
  passed, so the box stays open and this says why.
- *Steps 4–7.* Four of five clauses verify. The four router repositories all
  report `archived: true` (`sd-github-review`, `sd-review-test`,
  `sd-github-review-pilot`, `sd-review-control-plane`). `skills/` holds 76
  `sd-*` directories and zero `se-*`. `docs/work/archive/` carries **100** files
  with a `parked:` line, and `sd-status` reports `488 items (2 active)` against
  a ceiling of 20 — mezmo_benchmark's 48 are outside D2's scope under the R11-D7
  freeze, so they do not count against this. `git ls-remote --tags origin`
  returns `daebee6c6cd456a81cbbbba91de6196c8b8b7de0	refs/tags/v1.0.0`. The
  fifth is half-met: the state root `~/.local/state/sd-ai-command-pack/` is
  exactly `handoff/` and `installed.json`, so `handoff/` survived the cleanup —
  but `intents/` has never existed, because the `item set-status` lane that
  creates it was deliberately not built (`implement.md:563-567`, step P3's
  "Deliberately not built" list) — step 6 recorded the same thing at the time
  (`implement.md:1429`). "Leaves `intents/` intact" is vacuous rather than
  passed, and the box waits on the lane being built or the clause being
  rewritten.

## References

- Full decision record: `design.md` (rounds r1–r9c + R10/R11, adversarially reviewed).
- Execution sequence: `implement.md`.

## Log

- 2026-08-29 created; M0 tombstone PR opened from this branch.
