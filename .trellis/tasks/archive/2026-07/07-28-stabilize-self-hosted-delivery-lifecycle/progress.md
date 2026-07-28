# Stabilization progress

This file is the durable cross-session checkpoint for the single-merge
stabilization campaign. Update it only after a focused package commit and its
local checks/review have completed.

## Campaign

- Branch: codex/stabilize-self-hosted-delivery-lifecycle (from clean main 0f3323b)
- Planning baseline: 6b8a8f8 (first bounded commit; planning + handoff surface)
- Lifecycle activation: d79ba90 — umbrella + all 11 work packages set to
  in_progress and assigned the shared branch; investigation and rollout tasks
  remain planning.
- Current package: 11 / 11 — 07-28-standardize-environment-blocked-recovery-evidence (complete)
- Last verified commit: 6682f8e9
- Cumulative matrix: not run (all 11 packages done; next is umbrella cumulative integration)
- Pull request: none
- Finalization receipt: none
- Pre-start separation: resolved. Unrelated task
  `07-28-bound-review-learnings-unsafe-path-diagnostics` is preserved at commit
  `22aa265` on local branch
  `codex/plan-bound-review-learnings-unsafe-path-diagnostics` and is absent
  from the umbrella working tree.

## Work packages

| Order | Task | State | Commit | Focused checks | Local review |
| ---: | --- | --- | --- | --- | --- |
| 1 | `07-28-clarify-completion-housekeeping-obligations` | done | 2616735 | unittest (completion_lifecycle 9, sdlc_commands, help_command, surface_generation, generated_parity, pack_drift, install) + ruff + mypy green | self-review clean; candidate-ledger digest deferred to cumulative integration |
| 2 | `07-28-decide-housekeeping-result-schema-compatibility` | done | 78b7b05 | test_housekeeping_result (15, +3 migration) + generated_parity + pack_drift + ruff + mypy green | self-review clean; explicit no-alias migration, reconciled with parent R6 |
| 3 | `07-24-support-planning-only-pr-finalization` | done (validated) | 7bf587a | finalization lifecycle battery 212 tests green (bookkeeping_validator, review_preflight, pr_eligibility, housekeeping, housekeeping_result, review_stage) | integration proof; feature already in origin/main, not re-implemented |
| 4 | `07-28-validate-finish-work-receipt-path` | done | 6f873db | test_housekeeping (39, +8 receipt-path) + generated_parity + pack_drift (56) + ruff + shellcheck green | self-review clean; early fail-fast before side effects, downstream eligibility unchanged |
| 5 | `07-28-route-housekeeping-by-pr-lifecycle-state` | done | 865d169 | test_housekeeping (42, +3 lifecycle routes) + test_housekeeping_result (15) + pr_eligibility + generated_parity + pack_drift + ruff + mypy + shellcheck green | self-review clean; single resolved identity, sole merge owner preserved, eligibility null on merged route |
| 6 | `07-28-enforce-pre-archive-acceptance-readiness` | done | 9eaf2ee2 | test_bookkeeping_validator (44, +8) + test_review_preflight + test_sdlc_commands + test_completion_lifecycle + test_generated_parity + test_pack_drift green; ruff clean | self-review clean; completion-ready-gated, read-only, no false positives (handoff prose / non-canonical / fenced boxes) |
| 7 | `07-25-user-scope-toolchain-caches` | done | 715559ab | test_script_lib (27, +3 uid/ownership) + test_generated_parity + test_pack_drift (56) green; ruff clean | self-review clean; security code already shipped by H06, this pins acceptance properties + documents the guarantee, no re-route |
| 8 | `07-25-fix-work-loop-lock-race` | done | 18739c75 | test_work_loop (78, +3 concurrent-recovery/helper) + test_generated_parity + test_pack_drift (56) green; ruff + mypy clean | self-review clean; identity-checked rename-aside recovery, error strings + `--recover-stale-lock` flow unchanged, no consumer touched |
| 9 | `07-25-backlog-selector-blocked-markers` | done | b233db10 | test_work_loop (81, +3 block-status/rank-order + envelope update) + test_generated_parity + test_pack_drift (56) green; ruff + mypy clean on both work-loop copies | self-review clean; formalized existing PARKED convention (no parallel one), Trellis-core task.py not forked, selector view provides AC1 machine-visible distinction |
| 10 | `07-24-track-clean-recovery-artifacts` | done | 1aa2359d | recovery+housekeeping suites (90) + test_generated_parity + test_pack_drift (56) + test_install_audit (59) + surface generation/drift (28) green; ruff + mypy (35 files) + shellcheck + housekeeping self-test clean; only deferred `provenance.candidate-stale` remains for release prep | self-review clean; pre-existing registry/classify/cleanup integrated (not forked); housekeeping is the sole general cleanup owner, creating workflow owns success-path cleanup, ambiguous/unique defaults to preserve, sd-status stays read-only; new shared reference fanned out via manifest, both copies byte-identical; no consumer touched |
| 11 | `07-28-standardize-environment-blocked-recovery-evidence` | done | e0e9e4f9..6682f8e9 (8) | test_script_lib (composer + tool-cache) + test_work_loop + test_record_session + test_update_spec_kb + test_housekeeping_result + test_generated_parity + test_pack_drift = 242 green; ruff + mypy (35 files) clean | self-review clean; six R4 boundaries integrated owner-side only (no stderr classifier), managed-payload reserved as enum with no producer, additive schemaVersion-1 fragment, skills-render + handoff to 07-22 as research/ file (07-22 not edited) |

## Last checkpoint

Package 11 (`07-28-standardize-environment-blocked-recovery-evidence`) complete
across eight staged commits `e0e9e4f9..6682f8e9`: `e0e9e4f9` (shared composer +
validator), `18966e9f` (tool-cache), `749f457a` (work-loop user-state),
`9e446497` (record-session git-metadata), `98751eb3` (update-spec-kb kb-target),
`965439fa` (housekeeping `environmentBlocks`), `7bc8cd40` (skills-render), and
`6682f8e9` (doc note). The contract (R1/R3) is one reusable `environment_blocked`
fragment (schemaVersion 1) in `sd_ai_command_pack_lib.py`:
`build_environment_blocked_evidence` + `validate_environment_blocked_evidence`,
bounded `boundary`/`mutationState`/`recoveryAction` enums, a redacted secret-safe
`diagnostic`, and `retryable` rejected whenever `mutationState` is `unknown`. Six
R4 owning operations emit it strictly from their own control flow — never from
parsed stderr, so a repository defect can never be mislabeled a permission issue:
tool-cache (shared-lib cache setup `--json`), user-state (work-loop private-dir
create + CLI state write), git-metadata (record-session post-append commit;
housekeeping fetch/prune and merged-branch delete), and kb-target (update-spec-kb
refresh = `partial-recoverable`, inspect = `none`; housekeeping KB refresh). Each
preserves its prior exit and fail-closed behavior (R4); an unknown failure keeps
its existing command-owned result rather than being guessed into the contract
(R2/R5). The fragment is additive (R7): it rides each command's existing result
object without changing that object's own schemaVersion or exit, and an
unsupported consumer ignores it and keeps its prior bounded diagnostic.

Scope decision — `managed-payload`: PRD R4 names exactly six owners and none is a
managed-payload producer; the only natural producers are `install.py` managed
writes (which run in consumers, outside this single-merge boundary) and the
recovery-artifact lifecycle (owned by Package 10, `07-24-track-clean-recovery-
artifacts`). So `managed-payload` ships as a reserved enum boundary (R2 support)
with no producer wired here, consistent with contract-first "reconcile ownership;
do not duplicate their underlying fixes"; this consciously supersedes
`implement.md` step 5's "then managed payload writes." Skills-render (R6, step 7):
a new shared reference `sd-help/references/environment-blocked-recovery.md`
encodes the narrow-authority rules — report the exact boundary and checkpoint,
request only the narrow retry, treat `recoveryAction` as data not permission,
honor `mutationState`, and never let a block authorize a merge, branch deletion,
archive, force operation, or broad cleanup — registered in
`SHARED_SKILL_REFERENCES` and fanned out to 22 IDE namespaces by
`generate-command-surfaces.py`; `sd-housekeeping` (the additive `environmentBlocks`
array), `sd-finish-work` (recorder git-metadata), `sd-update-spec` (kb-target),
and `sd-work-backlog` (work-loop user-state) point at it, and
`SD_AI_COMMAND_PACK.md` documents the array (step 8). Step 9 handoff: the
environment-blocked and idempotent-retry scenarios are recorded as EB/IR/IC/FS
rows citing landed tests in Package 11's own
`research/workflow-program-handoff.md` for
`07-22-validate-sd-workflow-program-integration` to consume; 07-22 is
planning-status and outside this umbrella, so its artifacts were not edited — the
scenarios are fed in as a child-owned handoff, matching 07-22's "reference, do not
reimplement a child's behavior" design. The planning adversarial-review rule does
not fire: this window created or materially updated no active-task
`prd.md`/`design.md`/`implement.md` (Package 11's planning artifacts were authored
and reviewed at activation `d79ba90`; the handoff is a new `research/` file), and
the edits are lib/scripts/tests/skills/docs/handoff only. Templates edited first;
root mirrors byte-identical via `make sync` (`conflicts: none`); no consumer
touched. Version/changelog/fleet and the candidate-ledger `payloadDigest` restamp
stay deferred to cumulative integration and the post-STOP fleet boundary; the lone
`provenance.candidate-stale` surface finding is that expected deferral. Checks:
`test_script_lib` (composer + tool-cache) + `test_work_loop` + `test_record_session`
+ `test_update_spec_kb` + `test_housekeeping_result` + `test_generated_parity` +
`test_pack_drift` = 242 green; `ruff` + `mypy` (35 files) clean.

Package 10 (`07-24-track-clean-recovery-artifacts`) complete at commit
`1aa2359d`, the final of five staged subsystem commits: `5c90234c`
(recovery-artifact registry + read-only classify), `176041af` (proof-gated,
locked destructive cleanup), `7ba4d0c9` (sd-status surfaces artifact state
read-only), `5e61eedf` (coverage-floor + legacy-advisory gates), and this
`1aa2359d` (housekeeping reconcile + skill/doc lifecycle contract). The R1-R9
design is a receipt-gated ownership boundary: every pack-created recovery stash
or worktree carries a versioned, user-local, owner-only receipt keyed by
repository identity and a unique artifact ID, and cleanup acts only through
receipts (an artifact with no receipt is `unowned-artifact` and never touched).
The creating workflow `register`s the receipt atomically the instant after the
artifact exists and, on the success path, retires its own artifact and receipt
in a `finally` through `cleanup --mode owner --artifact-id` (owner mode is the
only lane that may prune a receipt whose Git object is already gone); an
interruption preserves both for recovery (R3/R4). `sd-status` classifies every
artifact read-only as `active`, `safe-cleanable`, `needs-review`,
`missing-artifact`, or `unowned-artifact` and moves nothing (R5). This commit
adds `cleanup --format shell` — one `\x1f`-delimited summary line (retired,
preserved, failed, first-failure detail), safe because `_bounded` strips all
control bytes — and wires `sd-ai-command-pack-housekeeping.sh`
`reconcile_recovery_artifacts()` to run `cleanup --mode housekeeping` after
branch/merge work and before the status report, skipped in dependency-PR mode
(mirroring its KB-refresh skip). Housekeeping retires only a stash proven
redundant/superseded at its exact object or a worktree clean at its exact
registered path with a matching common dir, no lock, and a reachable/retained
head (R6/R7); it preserves every ambiguous, `needs-review`, missing, or foreign
artifact (R8), surfaces retired artifacts as `recovery_artifacts_retired`
actions and refused/failed retires as `recovery_cleanup_*` anomalies, never
prunes receipts, never forces a removal, and always returns 0 so it cannot abort
housekeeping. The durable receipt JSON is bounded and exposes no secrets, remote
URLs, or raw filesystem errors (R9). The R1-R9 contract is authored once as a new
shared reference `sd-help/references/recovery-artifacts.md`, registered in
`SHARED_SKILL_REFERENCES` and fanned out across all IDE targets by
`generate-command-surfaces.py`; `sd-status`/`sd-housekeeping` SKILLs and
`SD_AI_COMMAND_PACK.md` point at it. No existing skill creates stashes or
worktrees today, so the register-then-`finally` protocol is authored as a
forward-looking contract rather than fabricated into current skill steps. This
commit edits scripts, tests, skills, and docs — no active-task
`prd.md`/`design.md`/`implement.md` was created or materially updated — so the
planning adversarial-review rule does not fire. Templates edited first; root
mirrors byte-identical via `make sync` (`conflicts: none`); no consumer touched.
Version/changelog/fleet and the candidate-ledger restamp are deferred to
cumulative integration and the post-STOP fleet boundary; the lone
`provenance.candidate-stale` surface finding is that expected deferral, not a
regression. Checks: recovery+housekeeping suites (90) + `test_generated_parity` +
`test_pack_drift` (56) + `test_install_audit` (59) + surface generation/drift
(28) green; `ruff` + `mypy` (35 files) + `shellcheck` + housekeeping self-test
clean.

Package 9 (`07-25-backlog-selector-blocked-markers`) complete at commit
`b233db10`. Formalized the already-present `PARKED:` title convention as the one
machine-visible "blocked on an external dependency" marker read by both the pack
status board (`sd-ai-command-pack-status.py` compiles the same
`PARKED_PREFIX_RE`) and the work-backlog selector, rather than inventing a
parallel field (R1 + the PRD reconciliation note). In the work-loop script:
`PARKED_PREFIX_RE`; `candidate_block_status`, which reads three compatible
surfaces (`blocked: true`, a `PARKED:` title prefix, or a `blockedOn`/
`blockedReason` string) and returns the most specific reason; and
`candidate_order`, a lightweight integer ordering signal. `rank_candidates` now
annotates every ranked item with `blocked`/`blockedReason`, sorts blocked
strictly after actionable (a blocked P0 never outranks an actionable P3), and
breaks ties inside a priority band by `order`; the `rank` CLI envelope gains
`actionableCount` so the selector can stop with `all_remaining_tasks_blocked`
when nothing is actionable. `sd-work-backlog/SKILL.md` and
`SD_AI_COMMAND_PACK.md` document the marker, the blocked-last ranking,
`actionableCount`, and the ordering signal. R4 migration: the 7 routed-review/
learnings tasks carry the `PARKED:` title prefix, and the two agent-artifacts
children with a hard sibling dependency — `07-25-worker-agents` (blockedOn
`07-25-agent-artifact-kind`) and `07-25-dispatch-rollout` (blockedOn
`07-25-fix-ci-dispatch`) — carry `PARKED:` plus a `blockedOn` naming the sibling;
the other two children are the blockers themselves and stay unmarked (the
`agent-artifact-kind` registry note is cross-*program* SE-pack coordination, not
an in-repo block). Per R5 the vendored Trellis-core `task.py` is not forked (its
`list` prints the directory name with only a `<- current` marker), so AC1's
"visibly distinct" is satisfied by the selector's view (the `rank` output flags
`blocked`, reports `blockedReason`, and sorts blocked last) while the pack board
reads the same convention. Package 9's own `design.md`/`implement.md` are
intentionally empty and only `task.json` titles/`blockedOn`, scripts, tests, and
docs changed — no active-task `prd.md`/`design.md`/`implement.md` was created or
materially updated, so the planning adversarial-review rule does not fire.
Template edited first; root mirrors (`work-loop.py`, `sd-work-backlog/SKILL.md`,
`SD_AI_COMMAND_PACK.md`) byte-identical via `make sync` (`conflicts: none`); no
consumer touched. Version/changelog/fleet deferred to cumulative integration and
the post-STOP fleet boundary. Checks: `test_work_loop` (81, +3 block-status/
rank-order regressions plus the empty-envelope `actionableCount` update) +
`test_generated_parity` + `test_pack_drift` (56) green; `ruff` + `mypy` clean on
both work-loop copies.

Package 8 (`07-25-fix-work-loop-lock-race`) complete at commit `18739c75`. Two
processes recovering the same stale work-loop lock could both acquire it: the
three recovery sites deleted the lock by path (`lock_path.unlink()`), so once the
first recoverer removed the stale lock and `O_EXCL`-created its own, a second
recoverer's unlink deleted that fresh competitor lock and let both runs proceed
concurrently. Added `_recover_locked_path`, which renames the lock aside under a
private `.recovering-<uuid>` name and deletes it only while its identity still
matches what was judged — `runId` for a stale lock, unreadable for a malformed
one — and, if a competitor already replaced the lock, restores the moved bytes
via `os.link` without clobbering the newer lock (so the caller re-observes it and
refuses to double-acquire) before failing closed on any restore error. Wired the
three unlink-by-path sites (`acquire_lock` malformed + stale, `acquire_terminal_lock`
stale) to it; the operator-facing error strings (`cannot recover {unreadable,
stale} work-loop lock`, `stale terminal reconciliation lock`) and the documented
`--recover-stale-lock` flow (`sd-work-backlog` `ownership-recovery.md`) are
byte-for-byte unchanged. Package 8's own `design.md`/`implement.md` are
intentionally empty — the umbrella design of record plus the child `prd.md` drive
the work, so no active-task planning artifact was created or materially updated
and the planning adversarial-review rule does not fire for these script/test
edits. The regression test `test_concurrent_stale_recovery_cannot_both_acquire`
drives a deterministic delete-time interleave (a competitor fully recovers and
acquires as `run-3` while the first recoverer holds a stale-judgment) and asserts
the late recoverer restores `run-3` and refuses to acquire; two unit tests pin the
match (delete) and mismatch (preserve competitor, no `.recovering-` residue)
branches of the helper directly. Template edited first; root mirror byte-identical
via `make sync` (`conflicts: none`); no consumer touched. Version/changelog/fleet
deferred to cumulative integration and the post-STOP fleet boundary. Checks:
`test_work_loop` (78, +3) + `test_generated_parity` + `test_pack_drift` (56)
green; `ruff` + `mypy` clean on both work-loop copies and the test.

Package 7 (`07-25-user-scope-toolchain-caches`) complete at commit `715559ab`.
Its security defect — a co-tenant pre-creating the toolchain resolver's Python
bytecode / uv / uv-tool / ruff cache directories and having planted content
executed under the victim's identity — is already remediated in code by the
COMPLETED predecessor `07-24-standardize-sandbox-safe-tool-cache-routing` (H06),
which centralized cache/env routing in `sd_ai_command_pack_lib.py`
`build_tool_environment` (unchanged in `origin/main`): the private namespace name
embeds the UID (`_cache_namespace_name`), every cache class is created 0700
(`_ensure_private_directory` / `_prepare_namespace`), and a pre-existing path not
owned by the resolving user is rejected. The PRD's cited defect site
(`configure_cache_defaults` / `prepare_gito_uv_env` / the unqualified
`${TMPDIR:-/tmp}/sd-ai-command-pack-*` directory) no longer exists; surviving
matches are `mktemp` random-suffix templates (not pre-creatable named paths).
Per the PRD reconciliation note this package does not re-route or re-implement;
it closes the two residual gaps on top of H06: (1) three regression tests pinning
the acceptance-criteria properties H06 left unpinned — the namespace and every
default per-tool cache path embed the current UID, `_ensure_private_directory`
rejects a foreign-owned path (unit branch), and `build_tool_environment` rejects
a pre-created 0700 namespace owned by a different user end to end (the prior
suite covered only the `chmod 0o755` permission branch); and (2) an explicit
fleet-facing security guarantee in `SD_AI_COMMAND_PACK.md` (UID-embedded, 0700,
foreign-owned rejection, naming the co-tenant plant-and-execute threat) replacing
text that merely said "per-user". No `sd_ai_command_pack_lib.py` change; no
consumer touched. Version/changelog/fleet deferred to cumulative integration and
the post-STOP fleet boundary. Task deliverable recorded in the task
`validation.md`. Template edited first; root doc mirror byte-identical via
`make sync` (`conflicts: none`). Checks: `test_script_lib` (27, +3) +
`test_generated_parity` + `test_pack_drift` (56) green; `ruff` clean.

Package 6 (`07-28-enforce-pre-archive-acceptance-readiness`) complete at commit
`9eaf2ee2`. Extended the existing read-only `pre-archive` bookkeeping validator
in `sd-ai-command-pack-review-preflight.mjs` (no second validator) to evaluate
the canonical acceptance section from the Package 1 lifecycle contract. An
unchecked required item in the single `## Acceptance Criteria` section fails
closed with `pre_archive_acceptance_incomplete` before any Trellis mutation;
malformed/duplicate sections and checkbox-shaped `## Post-archive handoff`
bullets fail with `pre_archive_acceptance_malformed`. Prose handoff bullets,
unchecked boxes outside the canonical section, and fenced-code checkbox examples
never produce false failures (fence mask + canonical-section scoping). The
evaluation is gated on the completion-ready pre-archive path only, so planning
finalization and post-archive completion-successor validation keep their
semantics; it never rewrites a PRD, checks a box, or mutates metadata/pointers/
branches/journals, and acceptance readiness stays bookkeeping evidence, not
merge authorization. Package 6's own `design.md`/`implement.md` are intentionally
empty: the umbrella's design of record plus the complete child `prd.md` drive
the work, so no active-task planning artifact was created or materially updated
(the planning adversarial-review rule does not fire for these script/doc/test
edits). Template edited first; root mirror and `SD_AI_COMMAND_PACK.md` kept
byte-identical via `make sync`; generated surfaces unchanged (94). Checks:
`test_bookkeeping_validator` (44, +8 acceptance-readiness cases) +
`test_review_preflight` + `test_sdlc_commands` + `test_completion_lifecycle` +
`test_generated_parity` + `test_pack_drift` green; `ruff` clean. (`make check`
mypy/shellcheck scopes exclude the edited `.mjs`; the candidate-ledger
`payloadDigest` stays stale until release preparation, by design.)

Package 5 (`07-28-route-housekeeping-by-pr-lifecycle-state`) complete at commit
`865d169`. Replaced the unconditional merge-then-cleanup pair in the housekeeping
script with `route_branch_pr_lifecycle`, which resolves one bounded PR identity
and lifecycle state before choosing work. OPEN keeps the exact-head eligibility
gate, re-resolves after the merge attempt, and cleans up only if the merge
landed (else one `pull_request_open` anomaly, branch untouched); MERGED skips
eligibility and cleans up from the resolved identity (no finish-work receipt
required, `eligibility` stays null); CLOSED stops with `pull_request_not_merged`;
an unresolvable identity or unexpected state fails closed with a bounded anomaly,
and the new `pull_request_state_indeterminate` code was added to the result
composer's indeterminate set so the composed outcome is `indeterminate`, not
`blocked`. The exact-head cleanup body was extracted into `cleanup_merged_branch`
(the working-tree gate now lives there, inspected once per run). Housekeeping
remains the sole merge/cleanup owner. Template edited first; root mirror, doc
(`SD_AI_COMMAND_PACK.md`), and composer kept byte-identical via `make sync`.
Checks: `test_housekeeping` (42, +3 lifecycle-route tests, 2 message updates, 1
source-order update) + `test_housekeeping_result` (15) + `test_pr_eligibility`
+ `test_generated_parity` + `test_pack_drift` green; `ruff`, `mypy` (result
composer), and `shellcheck -S warning` clean.

Package 4 (`07-28-validate-finish-work-receipt-path`) complete at commit
`6f873db`. Added `validate_finish_work_receipt` to the housekeeping script and
call it in `main()` right after the repository root is resolved (so relative
receipt paths resolve identically to downstream eligibility) and before cache
prep, Obsidian KB refresh, network access, or Git mutation. It requires an
existing readable regular file and rejects symlinks (checked first), missing
paths, directories, and other non-regular files with stable exit-code-2
diagnostics that never echo the path. `--self-test` (exits earlier) and
dependency-PR mode (empty receipt) are unaffected; downstream exact-head
eligibility revalidation is unchanged. Template edited first, root mirror kept
byte-identical via `make sync`. Checks: `test_housekeeping` (39, +8 receipt-path
cases) + `test_generated_parity` + `test_pack_drift` (56) green; `ruff` and
`shellcheck -S warning` clean. (`make check` mypy scope excludes `tests/`; the
only non-test edit is the shell script, covered by shellcheck.)

Package 3 (`07-24-support-planning-only-pr-finalization`) validated at commit
`7bf587a`. Its deterministic completion/planning finalization machinery
(`final-bundle` evaluator, finish-work mode gate, typed eligibility evidence,
retired `finishWorkHead`) already shipped to `origin/main` in prior releases and
is not re-implemented; the campaign records integration validation on the branch
head. Focused finalization lifecycle battery (`bookkeeping_validator`,
`review_preflight`, `pr_eligibility`, `housekeeping`, `housekeeping_result`,
`review_stage`) = 212 tests green. Deliverable is `validation.md`; dogfood and
program integration (H09/07-22) are satisfied/deferred by the umbrella itself.

Package 2 (`07-28-decide-housekeeping-result-schema-compatibility`) complete at
commit `78b7b05`. Consumer inventory proved no shipped/documented/tested consumer
reads `invocation.finishWorkHead`; decided an explicit documented in-major
migration (schema stays 1, no alias, no deprecation window), consistent with
parent task 07-24 R6. Recorded the decision in the task `decision.md`, documented
the retirement + verified replacement in the result composer docstring
(template + byte-identical root), and pinned it with 3 new tests (absence with
and without a receipt, verified head relocated to `identity.finishWork.headOid`,
restored `--finish-work-head` rejected). Checks: `test_housekeeping_result` (15),
`test_generated_parity` + `test_pack_drift` (56), ruff, mypy all green.

Package 1 (`07-28-clarify-completion-housekeeping-obligations`) complete at
commit `2616735`. Added the shared `sd-help/references/completion-lifecycle.md`
contract (registered in `SHARED_SKILL_REFERENCES`), a matching
`## Completion boundary` section in sd-finish-work, sd-housekeeping,
sd-review-pr, and sd-ship, an installed-guide pointer, and
`tests/test_completion_lifecycle.py` (9 tests). Regenerated command surfaces,
both manifests, and root mirrors via `make generate` + `make sync`.

Checks: `unittest` on completion_lifecycle (9) + sdlc_commands + help_command +
surface_generation + generated_parity + pack_drift + install all green; ruff
and mypy clean. Local review: self-review of the 16-file diff, scope matches the
intended set, no second merge authority introduced. Deferred, by design, to
cumulative integration: `candidate-validation.json` `payloadDigest` (refreshed
by release preparation), so `make generate` surface-check still reports the
candidate-ledger digest as stale until then.

Next: all 11 work packages are done. Begin umbrella cumulative integration —
R7 stability matrix, template/root sync + install audit + `make check`, release
preparation (including the candidate-ledger `payloadDigest` restamp via fleet
candidate validation), and cumulative adversarial review — then publish one PR,
resolve exact-head remote review + CI, run one multi-task pre-archive gate,
archive the umbrella and all 11 packages, record one journal entry and one
completion receipt, merge once via sd-housekeeping, verify clean synchronized
main, and publish the stabilized successor release. STOP before fleet rollout
(`07-28-roll-out-stabilized-pack-release-to-fleet`) and touch no consumer.
