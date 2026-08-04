# Pack follow-ups for 0.64.4 (after 0.64.3 fleet closes)

Two systemic fixes surfaced during the 0.64.3 rollout. Both are pack-source
changes -> next release (0.64.4), NOT patched into consumers mid-0.64.3-rollout.

## 1. Prevent missing `--description` on Trellis task create

Root cause: campaign #2 hoa-manager task was created without `--description`, so
`task.json.description` was empty. The completion finish-work receipt validator
(`review-preflight.mjs` `validateTrellisBookkeepingMetadata`) rejects an empty
description as `task_metadata_invalid` + `completion_source_metadata_invalid`,
but only at MERGE time (baked into the base commit) -> unfixable without history
rewrite. Caught far too late.

Fix options (pick in 0.64.4 design):
- **A. Early guard in fleet checkout-validation** (preferred, no consumer churn):
  the fleet controller / SKILL checkout-validation step asserts the freshly
  created task's `task.json.description` is non-empty before advancing; fail the
  stage with an actionable message if empty. Catches it at task-creation time,
  the only place it is cheaply fixable.
- **B. task.py `create` requires a non-empty `--description`** (source template
  `.trellis/scripts/task.py`): make it required, OR default it from the title
  when omitted, OR emit a hard error. Ships to every consumer on next install.
- Recommend A + B together: B stops the mistake at the source; A is a
  belt-and-suspenders gate that also covers pre-existing tasks.

## 2. Do not stall on a non-CLEAN mergeStateStatus that is actually actionable

Root cause: PR #201 reached `mergeable=MERGEABLE`, 10 checks SUCCESS + 3 SKIPPED,
0 pending, 0 failures -- but `mss=BLOCKED` because branch protection has
`required_conversation_resolution=true` and Copilot left ONE unresolved review
thread. A settle-watch whose only success exit is `mss==CLEAN` polls until
timeout even though nothing is running: the block is an ACTIONABLE state (resolve
threads), not a transient one.

Fix (0.64.4 watch-coordinator / merge-eligibility):
- Classify a BLOCKED-but-mergeable PR: when `pending==0 && failures==0 &&
  mergeable==MERGEABLE` and `mss!=CLEAN`, STOP polling and diagnose the specific
  block:
  - unresolved review threads + `required_conversation_resolution` -> surface an
    actionable "resolve N unresolved threads" (the review loop already authorizes
    resolving), then re-check.
  - stale/out-of-date branch (`strict` protection) -> actionable "update branch".
  - missing required check that is SKIPPED -> surface which required context is
    unsatisfied.
- Distinguish "BLOCKED because still-converging" (checks pending) from "BLOCKED
  because needs a bounded operator/loop action" so the coordinator returns an
  actionable outcome instead of timing out.

Applied MANUALLY to hoa PR #201 this campaign: detected 0-pending/0-fail +
MERGEABLE + BLOCKED -> found 1 unresolved Copilot thread on vendored
status.py:905 -> replied (out-of-scope: installer-managed/hash-vouched; routed
upstream) + resolved -> mss went CLEAN -> merged. This manual path is what
0.64.4 should automate.

## 3. Eliminate merge-stage head-advance (the loadsmith killer) — HIGH value

Root cause: the controller assumes ONE head-advance at merge. `sd-finish-work`
run at the merge stage advances the PR (archive+journal commits) -> controller
issues a successor publication (only at attempt<2). loadsmith advanced TWICE
(archive+journal, then a journal placeholder fix) -> attempt>=2 -> `retry-exhausted`,
unrecoverable -> had to park the lane and merge via the housekeeping gate manually.

Fix: make finish-work part of the PUBLISHED head instead of a merge-stage step.
Bundle `task.py archive` + `add_session.py` (+ placeholder fill) INTO the branch
BEFORE pr-publication, so the reviewed head already contains all bookkeeping and
the merge stage has ZERO head-advance and NO successor-publication cycle. This is
exactly what was done manually for hoa PR #201 this campaign (clean single-shot
merge). Systematizing it removes the entire double-advance failure class.

## 4. add_session.py should write the real commit subject, not `(see git log)` — MEDIUM

Root cause: `add_session.py` writes `(see git log)` placeholders in the journal
commit table. For loadsmith this tripped a whole-file CI placeholder gate and had
to be filled manually before push; for hoa it was benign (different
PLACEHOLDER_PATTERNS) but still hand-filled. The script already has the `--commit`
hashes -> it can resolve `git log -1 --format=%s <hash>` and write the real
subject at generation time.

## 5. Lightweight task create should not seed `_example` scaffold jsonl — MEDIUM

Root cause: `task.py create` seeds `implement.jsonl` / `check.jsonl` with a lone
`_example` scaffold row. The completion receipt validator rejects it as
`task_context_seed` at MERGE time (late). Had to empty both files manually for hoa.
Fix: `task.py create --no-start` (or a `--lightweight` flag) should leave the
manifests empty, OR the receipt validator should treat a lone-scaffold row as
"empty/unfilled" (advisory) rather than invalid, OR fleet checkout-validation
curates them. Same late-catch anti-pattern as #1.

## 6. focused-candidate PR-body scope check: chicken-and-egg + closed-PR bleed — MEDIUM

Two issues:
- The check needs the PR body's `Tooling/generated scope:` section, but the PR
  does not exist yet at focused-candidate time. Worse: a CLOSED same-branch PR's
  body is picked up by `gh pr view` and fails the check (hit this: closed #200
  bled into the #201 branch check). Fix: ignore CLOSED PRs when resolving a
  branch's body; rely on the env-provided intended body pre-publication.
- SCOPE_BODY_PATTERN requires a trailing COLON (`Tooling/generated scope:`). The
  shipped PR-body template/example should include the colon so generated bodies
  pass first time (the campaign-2 body used a heading without the colon).

## 7. Housekeeping KB refresh should not hard-block on read-only files — LOW/env

Root cause: `.obsidian-kb` symlinks into a personal wiki; a single 0444 file
hard-blocked loadsmith's merge gate (`kb_refresh_failed`). Fixed by `chmod u+w`.
KB refresh is advisory; it should skip / restore-write / warn-and-continue on a
read-only target rather than block the merge.

## 8. Wave planner halts the whole campaign on a parked/failed canary — LOW

Root cause: parking loadsmith's canary lane set `stop_starting=true`; `next`
returned empty and the campaign could not continue. Had to start a fresh campaign
so done consumers became at-target skips. Fix: let an `operator-decision`/parked
canary with recorded provenance count toward canary-success (or add
`--allow-parked-canary`) so the campaign continues without a full restart.

## 10. repomix-drift consumers: finish-work archive drifts docs/repomix-map.md, and the fix cannot live in the completion delta — HIGH for indexed repos

Root cause: consumers that ship a repomix index (`docs/repomix-map.md` +
`update_repomix`, e.g. mezmo_benchmark) enforce a drift test
(`test_docs_drift.py::test_repomix_map_matches_repository_inventory`) that
compares the map's `.trellis/tasks/**` paths against the on-disk tree. finish-work
`task.py archive` MOVES the active task active->archive, so the reviewed head's
map lists pre-archive paths while the tree has archived paths -> CI red.

The trap: regenerating repomix AFTER archive (a post-H3 commit) puts
`docs/repomix-map.md` into the completion finalization delta (base..head), which
the receipt validator rejects with `bundle_scope_invalid` — that delta may
contain ONLY `.trellis/tasks/` and `.trellis/workspace/` paths. So the fix is
NOT forward-patchable at the merge stage; it is unrecoverable once the branch is
built the naive way (this cost a full mezmo rebuild this campaign).

Fix (drift-safe publish, proven as `publish-lane3.sh` this campaign):
pre-compute the POST-archive repomix and fold it into the WORK commit BEFORE any
bookkeeping, so the finalization delta stays `.trellis`-only:
  1. filesystem-simulate the archive move (`mv task -> archive/<mon>/<slug>`),
     run `update_repomix`, then move the task back;
  2. WORK commit = pack refresh + active task + repomix(post-archive content) = H1;
  3. real `task.py archive` (H2, the actual move) + `add_session` journal (H3);
  4. completion receipt base=H1 head=H3 -> delta is archive-move + journal only,
     `.trellis`-scoped -> `valid`; repomix already correct for the archived tree.
This composes with #3 (finish-work bundled into the published head): the reviewed
head is drift-consistent AND merge-stage advance is zero. 0.64.4 should make the
fleet publish step do this automatically for any consumer whose tree contains
`update_repomix` + `docs/repomix-map.md`, and detect the indexed-repo
condition rather than relying on the operator to know.

## 11. Helper-loader diagnostics collapse "missing" vs "unsafe/unavailable" — MEDIUM (upstream, Copilot-surfaced on anomaly #315)

Copilot review on the 0.64.3 refresh flagged the TOCTOU-hardened helper loader:
- `sd-ai-command-pack-surface-check.py` `_load_source_module()` reports "missing
  source validator module" for several distinct path-policy failures, including
  platforms without `os.O_NOFOLLOW` where the module EXISTS but is refused as
  unsafe/unloadable. Misleading diagnostics.
- `sd-ai-command-pack-status.py` `collect_work_loop()` reports "work-loop helper
  is not installed" for any `_UnsafeSiblingPath`, same conflation.

0.64.4: distinguish "not present" from "present but rejected (unsafe / no
O_NOFOLLOW on this platform / unloadable)" in the surfaced message so operators
on `O_NOFOLLOW`-less platforms aren't told a present file is missing. Product-side
wording only; the security refusal behavior stays. Routed here from the vendored
refresh PR (hash-vouched files — not consumer-editable), threads resolved as
out-of-scope on the consumer PR.

## 12. Redo of a published PR is a ledger dead-end in-campaign; fresh campaign is the recovery — HIGH

Root cause: the merge/review head-advance recovery (`retryable-failure
--reason-code pr-head-advanced`) issues a SUCCESSOR pr-publication that HARD-REQUIRES
reusing the same PR number: `PR republication must reuse the current PR number`.
When a lane is redone the clean way (close the broken PR, new branch, new PR —
because force-push to rewrite consumer history is banned), the successor rejects
the new PR number and the lane is stuck with no forward path (hit on mezmo:
successor wanted #415, rebuild was #416).

Recovery that worked: start a FRESH campaign. In a fresh ledger the rebuilt PR is
a FIRST publication, so there is no continuity constraint. Two sub-learnings:
- The fresh campaign does NOT require rebuilding the work. mezmo's #416 branch +
  valid receipt already existed; drove checkout-validation..local-checks as
  attestation `passed` (work already done + independently verified: CI green,
  receipt valid), then pr-publication recorded the existing head + PR #416.
  Fresh ledger accepted it; merged clean in-controller.
- This is the same "fresh campaign so done consumers become at-target skips"
  escape used for the loadsmith park (#8) and the hoa redo. Pattern is now proven
  three times — 0.64.4 should either (a) let a redone lane re-point its successor
  publication at a new PR number, or (b) provide a first-class
  `resume --relink-pr <consumer> <new-pr>` so a redo doesn't force a whole new
  campaign.

## 13. Merge queue serializes by manifest priority — a waiting lane is not a stall — LOW/doc

Observed: se-ai-command-pack reached stage `merge` with status `waiting` and
`next` returned EMPTY, which looks like a stall. It was not: merges serialize in
rolloutPriority order (mezmo 50 -> se 60 -> sd-github 70 -> anomaly 90), and se's
merge was correctly held until mezmo merged. Diagnosing this needed a `status`
read. 0.64.4: `status`/`next` should surface "merge held behind <consumer> (lower
priority, not yet merged)" so the operator doesn't misread queue ordering as a
hang and start poking at it.

## 9. Ergonomics — LOW
- `next` can return EMPTY while a lane sits `status: issued` for a DIFFERENT lane
  (or the same one) — an already-issued action is never re-surfaced. To recover a
  stuck lane's actionId you must read campaign state at
  `<state-home>/<repo-sha256>/<campaign>.json` (note the per-repo hash subdir) and
  pull `lanes[].issuedAction.actionId`. A `--peek`/`--show-issued` query would
  remove this.
- `preflight` is NOT a `fleet-controller` subcommand — it is a campaign STAGE
  issued by `next`, and the work is run via the separate
  `fleet-preflight.py`. Non-obvious; document the split.
- Copilot review request: `gh api repos/<o>/<r>/pulls/<n>/requested_reviewers -X
  POST -f "reviewers[]=Copilot"` works (literal login `Copilot`). The GitHub MCP
  `request_copilot_review` 403s on the PAT, and `gh pr edit --add-reviewer
  github-copilot[bot]` fails login resolution. Ship the working recipe in the
  rollout docs.
- Validation win (not a defect): #3 (finish-work bundled into published head) +
  #10 (drift-safe repomix) held for 4/4 merges this campaign — ZERO merge-stage
  head-advance, ZERO housekeeping-gate anomalies across mezmo/se/sd-github/anomaly.
  The double-advance + drift failure classes are gone when publish-lane3 is used.
- `fleet-timing.py init` rejects cohort labels ("priority must be an integer");
  it should accept `canary/post-canary/final` and map to ints, or the wrapper
  should translate.
- `controller next` is not idempotent (it issues the action; a second `next`
  returns empty). Capturing the actionId requires reading campaign state. Consider
  a `--peek` / idempotent query, or documenting the read-from-state path.
- `operator-decision` parking needed a hand-authored provenance JSON; consider a
  first-class `record --result operator-decision --provenance <file>` path.
