# Implement: root-task base_branch gate + remediation

Ordered checklist. Each step names its validation. Rollback points marked.

## 0. Preconditions (verify, no edits)

- [ ] On `main`, clean tree; `git fetch origin main` current.
- [ ] Re-confirm survey is still exactly 4 offending root records and 0
      empty descriptions (`.venv/bin/python` one-liner over active
      `task.json` files). If drifted, update design.md remediation list
      before proceeding.

## 1. Branch

- [ ] `git switch -c chore/root-task-base-branch-gate` from `origin/main`.

## 2. Preflight rule (R1/R2)

- [ ] In `scripts/sd-ai-command-pack-review-preflight.mjs`:
      - Add exported pure function
        `validateTrellisRootTaskBaseBranch(record, defaultBranchName)`
        near `validateTrellisPlanningBaseInheritance` (:3213). Semantics
        per design.md: applies to root records — `parent` null OR absent
        (:3316 permits undefined) — with a non-empty `base_branch` (the
        empty case stays owned by the existing rule at ~:3302 — no
        duplicate diagnostic); PASS on `base_branch.trim() ===
        defaultBranchName` or on `meta.base_branch_exemption` being a
        string with non-empty trim; FAIL diagnostic names task path,
        value, default, and the set-meta escape hatch.
      - Add dedicated resolver (design.md chain): 1)
        `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` env, trimmed non-empty; 2)
        `origin/HEAD` symbolic-ref, existing ref verified, `origin/`
        prefix stripped; 3) else empty → rule skipped this run. Do NOT
        reuse `defaultReviewBaseRef()` and do NOT read
        `SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF`.
      - Add a new loop over the changed active task records (same
        `changedTaskFiles` population as :3075, but WITHOUT the
        planning-only filter): any status, root predicate above → run the
        rule; resolve the default once before the loop. Give the loop its
        own inspection counter and failure-aware pass line matching the
        sibling loops' accounting (no unqualified pass after a root
        failure).
- [ ] Amend `.github/workflows/tests.yml` preflight invocation (~:253) to
      also export
      `SD_AI_COMMAND_PACK_DEFAULT_BRANCH="${{ github.event.repository.default_branch }}"`
      — CI pins an exact SHA and never sets `origin/HEAD`, so without
      this the CI gate silently skips the rule.
- [ ] Copy to `templates/scripts/sd-ai-command-pack-review-preflight.mjs`;
      prove byte-identity: `diff scripts/... templates/scripts/...` → no
      output.
- Validation: `node scripts/sd-ai-command-pack-review-preflight.mjs` on
  the branch (only planning-artifact changes in diff) → 0 failures, rule
  quietly active.
- Rollback point: revert the two-file edit.

## 3. Tests

- [ ] Extend `tests/test_review_preflight.py` following its existing
      patterns (node-side unit script via subprocess for the pure
      function; InstallTestCase git fixture for full-script runs — match,
      don't invent). Cases (design.md §Tests):
      1. Root task, `base_branch: chore/task-preflight-bare-filename-references`
         (PR #342 replay), default `main` → FAIL; diagnostic contains
         task path + value + default. Both as pure-function unit case AND
         full-script git fixture (`origin/HEAD` → `origin/main`,
         defective root task.json in fixture diff, nonzero exit +
         diagnostic asserted).
      1b. CI-shape fixture: no `origin/HEAD`,
         `SD_AI_COMMAND_PACK_DEFAULT_BRANCH=main` in env → rule active,
         defective record FAILS. Plus absent-`parent` (no key) record
         with bad value → FAIL (root-predicate pin).
      2. `base_branch: main` → PASS; `base_branch: " main "` → PASS
         (trim tolerance pinned).
      3. Child task targeting parent's active branch → PASS (R3
         regression; exercises existing child rule untouched).
      4. Feature-branch value + `meta.base_branch_exemption:
         "integration branch"` → PASS; whitespace-only exemption → FAIL;
         non-string exemption → FAIL.
      5. Full-script fixture with no `origin/HEAD` → rule skipped, no
         failure.
      6. Predicate divergence matrix (design.md): gate verdict on
         U+FEFF-only and U+0085-only descriptions via the :3348 rule,
         plus in-test Python `strip()` classification of the same
         strings; assert the exact expected divergence (JS strips U+FEFF
         not U+0085; Python strips U+0085 not U+FEFF).
- Validation: `make test` green (full suite, .venv harness — never bare
  python3.14).

## 4. Remediation (R4) — delta-scope-honest evidence sequence

- [ ] Pre-remediation sweep (PRD "before remediation" AC): one-off node
      script (scratchpad) importing the exported rule function, run over
      every active `.trellis/tasks/*/task.json` with default `main` →
      must report EXACTLY the 4 surveyed records and no others. Capture
      output.
- [ ] Live negative demo (MUST precede remediation; value MUST differ
      from the stored one — set-base-branch writes only the field, so an
      identical value stays out of the diff): `python3
      ./.trellis/scripts/task.py set-base-branch 08-06-session-followups
      chore/task-file-session-defects` → run
      `node scripts/sd-ai-command-pack-review-preflight.mjs` → EXACTLY 1
      failure naming that record. Capture output.
- [ ] Correct all 4 records with `task.py set-base-branch <dir> main`:
      - `08-06-session-followups`
      - `08-07-local-finding-rebuttal-channel`
      - `08-07-provenance-concurrent-session-collision`
      - `08-07-status-housekeeping-anomaly-disagreement`
- Validation: gate run again → 0 failures with all 4 corrected records
  present in the diff. Capture output. (A bare pre-remediation "expect 4
  failures" run is impossible under delta scope — at-rest records are not
  in any diff; the demo above plus test case 1 carry that evidence.)

## 5. Description remainder

- [ ] Record in execution log: fresh survey found 0 empty descriptions —
      backfill AC satisfied by assertion, no edits.
- [ ] Docs audit, repo-wide (per design.md):
      `rg -n 'task\.py create' --hidden -g '!.git' .` — classify EVERY
      hit: pack-owned surface → ensure the runnable example carries
      `--description` (template-first, mirror byte-sync where
      applicable); Trellis-managed or vendored surface (`.trellis/
      workflow.md`, `.trellis/scripts/**`, Trellis-installed skills under
      `.agents/`/platform dirs) → do NOT edit; list in the upstream
      handoff register evidence (`.trellis/tasks/
      08-08-upstream-handoff-register/research/`). Known upstream-owned
      hits from planning: `.trellis/workflow.md:46,317`,
      `.trellis/scripts/task.py:410`,
      `.agents/skills/trellis-brainstorm/SKILL.md:37`.
- [ ] Append parked-consumer note to
      `research/2026-08-08-trellis-0-6-14-seed-probe.md`: fleet-consumer
      seed verification parked until each consumer's Trellis upgrade
      delivers >=0.6.8 (PRD dispositions own the trigger).
- [ ] Note delegation in execution log: create-time refusal lives in
      Trellis fork task `08-08-create-empty-metadata-rejection`; no
      vendored changes here; PRD dispositions record the parked ACs.
- [ ] Register the parked fork task in the upstream handoff register's
      handoff list (`.trellis/tasks/08-08-upstream-handoff-register/` —
      PRD list or evidence note, matching that task's established
      format), so the named owner actually carries the entry.
- [ ] Refresh this task's `task.json` `description` (stale: present-tense
      seeding claim + six-record survey) to the rescoped statement
      (gate + remediation; upstream seed fix delivered in 0.6.14; 4
      records).
- Validation: the `rg` output pasted into execution log with a
  disposition per hit; zero unclassified hits.

## 6. Bookkeeping

- [ ] `manifest.json` version bump (patch), `CHANGELOG.md` heading with
      bullets (new preflight rule + exemption mechanism, record
      remediation, description predicate pins/docs audit).
- [ ] `make release-prep` (regenerates fleet candidate ledger, then runs
      `make check`). Must be green.
- Rollback point: rule code revertable as a normal PR revert; the 4
  record corrections are data fixes and are NOT reverted with the code
  (design.md rollback split).

## 7. Publish & converge

- [ ] Update this file's execution log (deviations, captured outputs).
- [ ] `sd-create-pr` flow: update-spec pass, stage intended paths only,
      preflight gate, push, PR with body-file.
- [ ] Request Copilot review; reply/fix/re-request until converged; CI
      green (11 checks).
- [ ] On user instruction: merge (merge commit), `task.py finish`
      (no argument), journal via record-session, `task.py archive`,
      push main.

## Execution log

2026-08-08, single session, branch `chore/root-task-base-branch-gate`.

- Step 0: survey re-confirmed — exactly 4 offending root records
  (08-06-session-followups → fix/work-loop-stop-after-pause; the three
  08-07 tasks → chore/task-file-session-defects), 0 empty descriptions,
  55 active records.
- Step 2: `validateTrellisRootTaskBaseBranch` (exported pure function) +
  `trellisRootDefaultBranchName()` resolver + root loop with own
  `inspectedRootBases` counter added to the topology check; pass message
  now reports all three counters. Mirror copied; `diff` proved
  byte-identity. `tests.yml` bookkeeping step exports
  `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` from the event payload.
- Deviation: the drift gate demanded documentation for the new env var —
  added to `docs/SD_AI_COMMAND_PACK.md` (+ template twin), not in the
  plan.
- Deviation: two existing tests asserted the old topology pass message;
  updated to the three-counter wording.
- Step 3: unit asserts (replay, trim tolerance, absent-parent root,
  child ignored, exemption trim/non-string, empty-default skip,
  U+FEFF/U+0085 gate pins) + 3 full-script fixtures (origin/HEAD replay,
  env-default CI shape, no-default skip) + Python-side divergence matrix.
  `make test`: all suites green (test_review_preflight: 71 tests OK).
- Step 4 evidence:
  - Sweep (exported function over all 55 active records, default
    `main`): reported exactly the 4 surveyed records, no others.
  - Live negative demo (`set-base-branch 08-06-session-followups
    chore/task-file-session-defects`): gate reported EXACTLY 1 failure —
    `FAIL .trellis/tasks/08-06-session-followups/task.json field root
    task base_branch "chore/task-file-session-defects" must equal the
    repository default branch "main" ...`.
  - Remediation (all 4 → `main` via set-base-branch): gate reported
    `0 failure(s)` with `5 root task base branch(es)` inspected (the 4
    corrected records + this task's own record in the diff).
- Step 5: 0 empty descriptions (assertion). Docs audit: repo-wide rg;
  the only pack-owned runnable gap was
  `sd-fleet-refresh/references/controller-recovery.md:130` (now carries
  `--description`; template + installed copy synced). All other
  no-description runnable examples are Trellis-managed
  (workflow.md:46,317; vendored task.py usage text;
  trellis-brainstorm/SKILL.md:37 ×4 platforms; trellis-meta
  task-system.md:62,109 ×4) — recorded as entry 12 in the upstream
  handoff register, alongside new entry 11 for the parked create-time
  refusal (fork task 08-08-create-empty-metadata-rejection). Remaining
  hits are prose mentions, tests, comments, or journals — not runnable
  examples. Seed-probe research note gained the parked fleet-consumer
  section; task.json description refreshed to the rescoped statement.
- Step 6: manifest 0.64.30, changelog heading, `make release-prep`.
