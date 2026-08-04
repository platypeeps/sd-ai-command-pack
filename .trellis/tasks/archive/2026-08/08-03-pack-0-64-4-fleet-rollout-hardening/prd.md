# 0.64.4 fleet-rollout hardening (13 findings)

## Goal

Fold the 13 findings surfaced across the 0.64.3 fleet rollout (campaigns #1–#4)
back into pack source so the next rollout does not re-hit them. Each fix is a
pack-source change that ships to every consumer on next install; several convert
a LATE, merge-time, unrecoverable failure into an EARLY, cheaply-fixable one.
Target release: **0.64.4**.

## Source of findings

`research/pack-followups-0.64.4.md` (13 numbered items — #1-8, #10-13, #9;
authored live during the rollout, copied here as tracked task research). This PRD
is the durable, **authoritative** restatement as requirements + acceptance
criteria. Finding numbers below match that doc.

## Constraints

- **No behavior weakening of security fixes.** 0.64.3 was a corrective TOCTOU
  helper-loader hardening release. Diagnostics-wording fixes (#11) must not relax
  any fail-safe path — message text only.
- **Backward compatible.** Consumers on 0.64.3 must install 0.64.4 with no manual
  migration. Existing campaign ledgers/state must still load.
- **No consumer churn required.** Fixes live in pack source + installer; a consumer
  gets them by re-installing, not by hand-editing.
- **Deterministic + hash-vouched.** Any new/changed shipped script stays within the
  provenance/vouch system (install audit must pass post-change).
- **Source-repo self-check (NOT self-hosting).** This repo is the pack SOURCE — the
  canonical pack, an *excluded* alias, NOT a fleet consumer (it is absent from
  `docs/fleet/consumers.json`). The new checks must pass here as the source build
  (self-test + install-audit on this repo), not because this repo is refreshed as a
  consumer.

## Requirements & Acceptance Criteria (grouped by deliverable cluster)

### C1 — Task-create hygiene (findings #1, #5)
- R1.1 `task.py create` requires a non-empty `--description` (hard error, OR
  default from title). **TRELLIS-upstream** — `.trellis/scripts/task.py` /
  `task_store.py` are scaffolded by the external `trellis init`, NOT shipped by
  this pack. Delivered as a filed upstream note, NOT a pack code change.
- R1.2 The completion receipt validator treats a lone `_example` scaffold row as
  "unfilled/advisory" not `task_context_seed`. **PACK-shippable** (review-preflight).
- AC1.a *(Trellis-upstream — satisfied by the filed upstream note, not by this
  release's shippable payload)* Upstream `task.py create` with `--description ""`
  (or omitted) should fail with an actionable message. Tracked in
  `research/trellis-upstream-notes.md`; not a pack acceptance gate.
- AC1.b A freshly created `--no-start` task passes the completion receipt validator
  w.r.t. `task_context_seed` without manual `: > file` emptying. **(pack gate)**
- AC1.c Fleet checkout-validation asserts non-empty `task.json.description` before
  advancing (belt-and-suspenders; actionable failure if empty). **(pack/fleet gate,
  has a dedicated implement step.)**

### C2 — Finish-work in published head + drift-safe + real journal subjects (findings #3, #10, #4)
- R2.1 Provide a first-class publish path (systematize the proven scratch
  `publish-lane3`): finish-work (`task.py archive` + `add_session`) is folded into
  the branch BEFORE pr-publication so the reviewed head already contains all
  bookkeeping and the merge stage has ZERO head-advance / no successor-publication.
- R2.2 For repomix-indexed consumers (tree has the consumer's `update_repomix` +
  `docs/repomix-map.md`), pre-compute the POST-archive repomix into the WORK commit
  so the completion finalization delta stays `.trellis`-only (no `bundle_scope_invalid`).
- R2.3 Real commit subjects in the journal: **reuse the existing shipped
  `record-session.py` wrapper** (`templates/scripts/sd-ai-command-pack-record-session.py`,
  already required by `sd-finish-work`), which resolves `git log -1 --format=%s`.
  The publish helper invokes that wrapper; the root `add_session.py` placeholder is a
  filed Trellis-upstream note, not a pack code change.
- AC2.a A refresh built with the new path merges with zero merge-stage head-advance
  (no `pr-head-advanced` successor issued at merge).
- AC2.b On a repomix-indexed consumer, the completion receipt is `valid` (no
  `bundle_scope_invalid`) AND the repomix drift test passes at the reviewed head.
- AC2.c Journal commit table shows real subjects; the whole-file placeholder CI gate
  passes without manual fill (via the record-session wrapper). **(has an implement step.)**

### C3 — Settle/merge intelligence (findings #2, #13)
- R3.1 Classify a BLOCKED-but-mergeable PR: when `pending==0 && failures==0 &&
  mergeable==MERGEABLE && mss!=CLEAN`, STOP polling and emit an actionable diagnosis.
  **ADDITIVE-ONLY: this MUST NOT change any eligibility decision** — a non-CLEAN PR
  stays `status="blocked"` and never reaches `gh pr merge`. It only adds an anomaly.
  The evaluator must FETCH the data it branches on (`mergeable`,
  `required_conversation_resolution`, review-thread resolution) via an explicit
  query; sub-diagnoses needing data not fetchable from `gh`/GraphQL are out of scope.
- R3.2 Merge-queue transparency: `status`/`next` surface "merge held behind
  <consumer> (lower priority, not yet merged)" so a serialized wait is not misread
  as a stall.
- AC3.a A BLOCKED-but-mergeable PR yields an actionable anomaly (not a poll-to-timeout).
- AC3.b A lane at `merge/waiting` reports WHY (held behind which consumer) in `status`.
- AC3.c *(negative)* A BLOCKED+MERGEABLE PR is NEVER classified eligible and the
  auto-merge path is never entered — proven by a dedicated negative test.

### C4 — Controller recovery + ergonomics (findings #12, #8, #9)
- R4.1 *(descoped for 0.64.4)* Redo-lane relink is NOT shipped this release. Direct
  mutation of `lane["head"]/["prNumber"]` breaks the publication-epoch invariant
  (`validate_state`) and could let forged evidence redefine the expected epoch. The
  supported recovery remains the proven **fresh-campaign redo** (attest
  checkout-validation..local-checks as `passed`, record pr-publication with the
  existing head+PR). A typed-recovery-record relink is filed as a follow-up.
- R4.2 A parked/`operator-decision` canary with recorded provenance does not halt the
  whole campaign (`stop_starting`); explicit `--allow-parked-canary` opt-in lets the
  campaign continue. **PREREQ:** confirm the exact halt path before editing (C-8).
- R4.3 Ergonomics: a `--peek`/`--show-issued` query returns an already-issued action's
  actionId without a state-file read; `operator-decision` accepts
  `--provenance <file>` first-class; document that campaign state lives at
  `<state-home>/<repo-sha256>/<campaign>.json` and that `preflight` is a stage run via
  `fleet-preflight.py` (not a `fleet-controller` subcommand).
- AC4.a A parked canary leaves the campaign able to continue to post-canary
  (with `--allow-parked-canary`).
- AC4.b Issued-action actionId is retrievable via a documented CLI query
  (`status --show-issued`).
- AC4.c The fresh-campaign redo recovery is documented in `docs/FLEET_ROLLOUT.md`.

### C5 — Review-preflight scope check (finding #6)
- R5.1 Resolving a branch's PR body ignores CLOSED same-branch PRs (a closed PR body
  must not bleed into the check).
- R5.2 Ship a PR-body template/example whose scope heading includes the required
  trailing colon (`## Tooling/generated scope:`) so generated bodies pass first time.
- AC5.a A branch with a CLOSED prior same-branch PR passes focused-candidate scope
  without env overrides.
- AC5.b The shipped template renders a body that satisfies `SCOPE_BODY_PATTERN`
  (verify-only — `pr-body-scope.py:73-75` is already colon-correct). **(has a verify step.)**

### C6 — Housekeeping KB robustness (finding #7)
- R6.1 `refresh_obsidian_kb` does not hard-block the merge gate on a read-only KB
  target: skip / restore-write / warn-and-continue instead of `kb_refresh_failed`.
- AC6.a A merge gate with a 0444 file under `.obsidian-kb` completes (warns, does not
  block). A non-read-only refresh failure still blocks.

### C7 — Helper-loader unsafe-sibling diagnostics (finding #11) — [child: improve-unsafe-sibling-diagnostics]
- R7.1 `surface-check.py` `_load_source_module()` and `status.py` `collect_work_loop()`
  distinguish "not present" from "present but refused (unsafe / no `O_NOFOLLOW` /
  symlink / non-regular / unloadable)". Recovery schema-version mismatch error names
  expected-vs-actual.
- R7.2 No change to the fail-safe refusal behavior — message text only.
- AC7.a On an `O_NOFOLLOW`-less path or symlinked helper, the surfaced message says
  "present but refused (…reason)" not "missing/not installed".
- AC7.b All existing security tests for the loader still pass unchanged.

### C8 — Timing + doc ergonomics (finding #9 timing, Copilot-request recipe)
- R8.1 `fleet-timing.py init` accepts cohort labels (`canary/post-canary/final`) and
  maps to ints (or the wrapper translates); int input still works.
- R8.2 Rollout docs carry the working Copilot-request recipe
  (`gh api …/requested_reviewers -f "reviewers[]=Copilot"`) and note the MCP/`--add-reviewer`
  failure modes.
- AC8.a `fleet-timing.py init` with cohort labels succeeds.
- AC8.b `docs/FLEET_ROLLOUT.md` documents the Copilot-request recipe.

## Release-level acceptance
- AC-R1 Manifest/version bumped to 0.64.4; provenance/vouch regenerated; install
  audit passes on this repo.
- AC-R2 Full pack self-test + existing test suite green (`make check`).
- AC-R3 A dry-run fleet candidate-check (disposable clones) passes for a
  **representative consumer set**: at least one repomix-indexed consumer (exercises
  C2 drift-safe path) AND one non-repomix consumer.
- AC-R4 No security-behavior regression (loader fail-safe tests unchanged byte-behavior).

## Deliverable map (single-branch release)

This parent task IS the implementation target for 0.64.4: all clusters ship on the
one release branch as **per-cluster commits** (C1, C2, …), not as separate child
tasks. Only C7 pre-existed as a linked child task
(`08-03-improve-unsafe-sibling-diagnostics`) and is folded in here. The parent also
owns cross-cluster ACs, the version/provenance bump, and release verification
(AC-R1..R4).

- C1 task-create-hygiene *(R1.1/AC1.a → Trellis-upstream note; R1.2/AC1.b/c → pack)*
- C2 finish-work-published-head-driftsafe
- C3 settle-merge-intelligence *(additive-only)*
- C4 controller-recovery-ergonomics *(relink descoped; parked-canary + ergonomics only)*
- C5 review-preflight-scope
- C6 housekeeping-kb-readonly
- C7 improve-unsafe-sibling-diagnostics  *(pre-existing child, folded in)*
- C8 timing-and-doc-ergonomics

## Out of scope
- Any consumer-side hand edits.
- New features beyond the 13 findings.
- Re-litigating the 0.64.3 security design.
- **Redo-lane `resume --relink-pr`** — descoped (C-4); needs a typed recovery-record
  design; fresh-campaign redo is the supported recovery for 0.64.4.
- Trellis-upstream root fixes to `.trellis/scripts/*` (findings #1 require-desc, #5
  seed-root, #4 add_session subject) — filed upstream, not shipped from this pack.
