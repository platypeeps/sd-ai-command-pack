# 0.64.4 fleet-rollout hardening — execution plan

Single release branch (`feat/0.64.4-fleet-rollout-hardening`); one commit per
cluster. Ordered so shippable low-risk gate fixes land first, the high-value publish
helper mid, controller/wave changes (highest blast radius) last, release bump final.

## Test runner (authoritative — NOT pytest)

This repo uses `.venv/bin/python` + `unittest`, never pytest (`.venv/bin/pytest` is
absent). Commands:
- Focused: `.venv/bin/python -m unittest tests.test_<module>`
- Full suite: `make test` (parallel unittest runner → `unittest-output.log`)
- Release gate: `make check`

## Order & gates

### Phase A — PACK-shippable gate fixes (low risk, message/logic-local)
1. **C7 unsafe-sibling diagnostics** (child folded in) — `surface-check.py`,
   `status.py`, `recovery-artifacts.py`. Text/enum only, no control-flow change.
   - Gate: `.venv/bin/python -m unittest tests.test_surface_check tests.test_status`
     (loader security tests pass unchanged); new tests for refused-path message.
   - Rollback point: single commit; revert restores prior strings.
2. **C1b tolerate lone seed** — `review-preflight.mjs`
   `validateBookkeepingTaskContexts` / `findTrellisTaskContextIssues`.
   - Gate: node self-test on review-preflight; fixture: lone `_example` → advisory,
     mixed → still finding. (AC1.b)
3. **C5 closed-PR body bleed** — `review-scope.sh resolve_pr_body_scope_state`.
   - Gate: shell fixture — closed same-branch PR present → env body used, not closed
     body; open PR → open body used. (AC5.a)
   - **AC5.b verify-only:** grep the shipped PR-body template renders
     `## Tooling/generated scope:` (colon) and matches `SCOPE_BODY_PATTERN`; no code
     change expected (`pr-body-scope.py:73-75` already colon-correct).
4. **C6 KB read-only tolerance** — `housekeeping.sh refresh_obsidian_kb`.
   - Gate: self-test scenario with 0444 KB file → `kb_refresh_skipped` + continues;
     other failure → still blocks. (AC6.a)
5. **C3 BLOCKED-but-mergeable classify — ADDITIVE-ONLY** — `pr-eligibility.py`
   (817, 1155) + extend the `gh pr view --json` field list and add the bounded
   GraphQL thread/branch-protection fetch (design 1c).
   - Gate (AC3.a): fixture PR JSON (BLOCKED+MERGEABLE+0/0) → actionable anomaly.
   - Gate (AC3.c, NEGATIVE — required): assert the eligibility decision is
     byte-unchanged (`status="blocked"`), the auto-merge path (`gh pr merge`) is
     never entered, and the CLEAN path is unchanged. Existing pr-eligibility tests green.

### Phase B — high-value publish helper
6. **C2 finish-work publish helper** — new
   `scripts/sd-ai-command-pack-fleet-publish.py` codifying the scratch `publish-lane3`
   (scratch artifact to PORT — not a tree file); wire into fleet SKILL pr-publication
   step. Includes repomix-indexed detection, move-simulate, and the record-session
   wrapper for real journal subjects (AC2.c).
   - **Failure-safety (required):** dirty-tree/ownership preconditions; `trap …EXIT`
     transactional restore of the fs-move-simulated task dir on ANY error;
     update_repomix output-path allowlist (`docs/repomix-map.md` only); H1→H3
     `.trellis`-only delta assertion before push (design 2g).
   - Gate: run it against a **repomix-indexed CONSUMER clone** (e.g. mezmo_benchmark
     from consumers.json) — NOT this repo (this repo has no `scripts/update_repomix`
     / `docs/repomix-map.md`) — → receipt `valid`, drift test green, zero merge-stage
     successor (AC2.a/b). Compare output shape to the proven scratch `publish-lane3.sh`.
   - Gate: failure-safety unit — inject an error mid-move and assert the task dir is
     restored to its original path; refuse to run on a dirty tree.

### Phase C — FLEET-tooling (controller/wave/timing) — highest blast radius, most tests
7. **C4 recovery + ergonomics** (relink DESCOPED — see below):
   - **C4b merge-queue transparency** — controller `_eligible_lanes` / candidate
     select. Gate: status JSON shows "held behind <consumer>" for a waiting
     non-candidate lane. (AC3.b)
   - **C4c peek + operator-decision provenance** — controller status/record parsers.
     Gate: `status --show-issued` returns actionId with no new action issued (AC4.b);
     `record --result operator-decision --provenance <file>` accepted.
   - **C4d parked canary doesn't halt** — `fleet-wave-plan.py` (+ controller 1636),
     `--allow-parked-canary`.
     - **PREREQ SPIKE (C-8, gates this edit):** confirm the EXACT halt path
       (investigator saw only pack-blocker sets `stop_starting`; verify the
       loadsmith park path) BEFORE editing.
     - Gate: wave test — parked (`operator-decision`) canary + `--allow-parked-canary`
       → campaign proceeds to post-canary. (AC4.a)
   - **C4a relink-PR — DESCOPED (C-4), do NOT implement this release.** File the
     typed-recovery-record follow-up in `research/trellis-upstream-notes.md`; document
     the fresh-campaign redo recovery in FLEET_ROLLOUT.md (AC4.c, Phase D).
8. **C8 timing cohort labels** — `fleet-timing.py parse_consumer` (597).
   - Gate: `init` with `canary|post-canary|final` succeeds; int input still works. (AC8.a)

### Phase D — docs + release
9. **C8 docs + C4 recovery doc** — `docs/FLEET_ROLLOUT.md`: Copilot recipe (AC8.b),
   campaign-state path, preflight-split, and the fresh-campaign redo recovery (AC4.c).
10. **Upstream notes** — write `research/trellis-upstream-notes.md` in this task:
    #1 require-desc, #5 seed-root, #4 add_session subject-root → file against the
    Trellis tool (out of this repo's shippable scope); PLUS the controller
    typed-recovery-record relink follow-up (C-4).
11. **Release bump** — version → 0.64.4 across manifest/VERSION; regenerate
    provenance/vouch for every changed shipped script.
    - Gate AC-R1: `python3 install.py $(pwd) --force …` + install-audit → vouched
      hashes match (this repo as SOURCE, not as a consumer).
    - Gate AC-R2: `make check` (full self-test + suite) green.
    - Gate AC-R3: `fleet-candidate-check.py --consumer <c>` dry-run passes for a
      REPRESENTATIVE set — one repomix-indexed consumer AND one non-repomix consumer.
    - Gate AC-R4: loader fail-safe tests byte-behavior unchanged.

## Review gates
- After Phase A and again after Phase C: run the pack's own review-preflight +
  self-test on the branch before proceeding.
- Planning-adversarial-review gate (project rule): DONE this planning batch — see
  `research/planning-adversarial-review.md` (round 1 remediation applied; no
  unresolved blocker). Re-run only if prd/design/implement materially change again.
- Human review gate: this is an outward-facing release; do NOT self-merge — open PR,
  request Copilot, land via the housekeeping gate (dogfood the very flow we hardened),
  and use the new publish helper (C2) to publish THIS task's own finish-work.

## Rollback points
- Per-cluster commits → revert any single cluster without unwinding others.
- Release bump is the LAST commit → revert it alone to un-release while keeping fixes
  staged.
- Consumers on 0.64.3 are unaffected until they choose to install 0.64.4.

## Validation command summary
- `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test`
- `node scripts/sd-ai-command-pack-review-preflight.mjs …` (per-fixture)
- `.venv/bin/python -m unittest tests.test_<module>` (focused) / `make test` (full)
- `python3 install.py $(pwd) --force --platform …` + `install-audit`
- `python3 scripts/sd-ai-command-pack-fleet-candidate-check.py --consumer <c>`
  (one repomix-indexed + one non-repomix)
- `make check` (release gate)
