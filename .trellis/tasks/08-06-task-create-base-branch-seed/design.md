# Design: root-task base_branch gate + description-requirement disposition

## Scope decision (settles the PRD's open questions)

The upstream seeding half is DONE: 08-08-trellis-upgrade delivered Trellis
0.6.14, whose `task.py create` resolves the repository default branch
(probed on a feature branch 2026-08-08: seeded `base_branch: main`; evidence
in this task's `research/2026-08-08-trellis-0-6-14-seed-probe.md`). This
task therefore ships ONLY the pack-local deterministic gate (R2), the
remediation of surveyed records (R4), and the pack-side remainder of the
absorbed description requirement. No vendored file under `.trellis/scripts/`
changes — that surface just became byte-identical to the 0.6.14 release and
must stay that way; any further create-time behavior change is the Trellis
fork's `08-08-create-empty-metadata-rejection` task, tracked, not
implemented here. The PRD's "Adversarial review dispositions" section
records which carried acceptance criteria are parked on that upstream
delivery.

## The new preflight rule (R1/R2)

Location: `scripts/sd-ai-command-pack-review-preflight.mjs` (+ byte-identical
`templates/scripts/` mirror), alongside the existing task-metadata rules.

Shape: a separate exported pure function
`validateTrellisRootTaskBaseBranch(record, defaultBranchName)` following the
`validateTrellisPlanningBaseInheritance` pattern (preflight.mjs:3213) —
pure and injectable so the node-side unit harness can exercise it without a
git fixture. Git resolution happens once per run at the call site.

Population — delta-scoped, like every existing task-metadata rule: the
preflight validates only task.json files present in the intended
branch/working-tree diff (`changedTaskFiles`, preflight.mjs:3075; the
integrity walk at :2990 has the same population — its pass message is "no
changed Trellis task metadata records require integrity checks"). The new
rule gets its own loop over changed ACTIVE task records with
`parent === null`, regardless of status — it must NOT reuse the child rule's
loop, whose filter (`status === 'planning' && branch === null`) is specific
to planning-base inheritance. Delta scope satisfies PRD R2 and the PRD's
"catches every future occurrence" claim because every future defective
record can only enter the repository through a PR whose diff contains that
task.json — exactly what PR #342 did. At-rest records predating the rule
are invisible to the gate by design; that residue is precisely what the
one-time R4 remediation clears.

Enforcement points, stated honestly: the PRIMARY catch point is the local
pre-publication gate — `sd-create-pr` runs the preflight against the
complete intended branch and working-tree diff before any push, which is
how every SD-flow-authored record (the PR #342 shape) is created. CI
enforcement is secondary and currently BOUNDED by a known, separately
owned gap: full-mode CI runs skip the preflight entirely, and bookkeeping
runs diff from the previous head, so whole-PR CI coverage is not
guaranteed. That gap predates this task and is the explicit scope of
`08-07-ci-preflight-full-mode-gap` (see its PRD's incremental-base
section); this task depends on it for CI-side guarantees and does not
duplicate it. When that task lands, this rule inherits full CI coverage
with no further change here.

Root predicate: `parent === null || parent === undefined` — the existing
metadata validator explicitly permits an absent `parent` field
(preflight.mjs:3316), so a record with no `parent` key is a root and must
not slip past a literal-null check. The new loop keeps its own inspection
counter and failure-aware pass line, matching the sibling loops' accounting
(the planning-inheritance tail at ~:3191 must not report an unqualified
pass when the root loop has failed).

Default-branch resolution — deliberately NOT `defaultReviewBaseRef()`
(preflight.mjs:4625). That resolver answers "what do I diff against" and
falls back through env overrides (`SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF`
may legitimately point at a stacked-PR feature base), the current branch's
upstream, then the alphabetically first remote ref — each of which can bless
an arbitrary branch as "the default" and make the gate wrong in both
directions. This rule uses a dedicated, conservative resolver:

1. `SD_AI_COMMAND_PACK_DEFAULT_BRANCH` env var, trimmed non-empty — an
   explicit, authoritative statement of the default branch (NOT a diff
   base; the existing `..._REVIEW_PREFLIGHT_BASE_REF` is deliberately
   ignored because its value is a diff baseline — in CI an exact SHA —
   with different semantics). The CI preflight step (tests.yml:253) is
   amended to export it from `${{ github.event.repository.default_branch }}`,
   because the CI checkout pins an exact SHA and never establishes
   `origin/HEAD` — without this, the CI bookkeeping gate would silently
   skip the rule whenever it does run.
2. Otherwise `git symbolic-ref --quiet --short refs/remotes/origin/HEAD`,
   verified to exist, with the leading `origin/` stripped — the local-
   checkout path.
3. Anything else (no remote, no origin/HEAD ref, no env) → resolution
   fails and the rule is SKIPPED for the run. Unverifiable is not failable
   for root tasks: failing every remoteless checkout would break local
   preflight runs the pack supports.

Pass/fail, given a resolved default `D`:

- PASS when `base_branch.trim() === D`. Trim tolerance is deliberate and
  documented: `set-base-branch` persists its argument raw
  (task_store.py:873), so `" main "` is normal user residue, not a defect.
- PASS when the record carries a recorded exemption:
  `meta.base_branch_exemption` is a string whose `.trim()` is non-empty
  (written via 0.6.14 `task.py set-meta <dir> base_branch_exemption
  "<reason>"`; set-meta stores raw values, task_store.py:940, so the gate
  trims before judging). Non-string or whitespace-only exemption values do
  NOT exempt. This satisfies "deliberate, recorded exception" (R2) and the
  no-inference constraint: the gate never guesses from branch names.
- Otherwise FAIL with a diagnostic naming the task path, offending value,
  resolved default, and the exemption escape hatch:
  `<taskdir>/task.json: root task base_branch "<value>" must equal the
  repository default branch "<D>" or carry meta.base_branch_exemption
  (task.py set-meta <dir> base_branch_exemption "<reason>")`.

R3 safety: this rule keys on `parent === null`; the child rule
(`validateTrellisPlanningBaseInheritance`) keys on a non-null parent.
Disjoint populations, no interaction. A child targeting the parent's active
branch still passes.

## Remediation (R4)

Survey re-run 2026-08-08 (fresh, per PRD): exactly 4 root records, down from
the PRD's 6 (consolidation removed two):

- `08-06-session-followups` → `fix/work-loop-stop-after-pause`
- `08-07-local-finding-rebuttal-channel` → `chore/task-file-session-defects`
- `08-07-provenance-concurrent-session-collision` → same
- `08-07-status-housekeeping-anomaly-disagreement` → same

Both named branches have **0 matching refs** locally or on origin as of the
2026-08-08 re-check (the PRD's 2026-08-07 table still showed 2 refs for
`fix/work-loop-stop-after-pause`; that branch has since been deleted) — dead
references; nothing can read those values as a real PR target. Disposition:
correct all four to `main` via `task.py set-base-branch <dir> main`. No
exemptions enrolled — the exemption mechanism exists for future legitimate
integration-branch targets, not for these.

Evidence sequencing inside one PR (delta-scope-honest — a bare gate run
CANNOT see at-rest records, so "run gate, expect 4 failures" is not a
meaningful pre-remediation criterion):

1. Rule lands with unit tests; the PR #342 replay test is the proof the
   rule catches the historical defect class.
1b. Pre-remediation sweep satisfying the PRD's "before remediation" AC
   literally: a one-off node script imports the exported pure rule
   function and runs it over EVERY active task.json (survey harness, not
   the delta-scoped gate) → must report exactly the freshly surveyed set
   (the 4 records) and no others. Output captured in the implementation
   log.
2. Live negative demo, BEFORE remediation: set one record to a bad value
   that DIFFERS from its stored one (`set-base-branch
   08-06-session-followups chore/task-file-session-defects` — the other
   surveyed dead-branch value). It must differ because `set-base-branch`
   writes only the field (task_store.py:874) — re-applying the identical
   value leaves the file byte-identical and outside the diff; and the demo
   must precede remediation because once corrections are pending, reverting
   a record to its committed value drops it back out of the diff. Gate run
   → exactly 1 failure naming that record.
3. Remediate all 4 to `main` → the 4 corrected records are now in the
   diff → gate run reports 0 failures.
   Both run outputs are captured in the implementation log.

## Description requirement — pack-side remainder

Fresh survey 2026-08-08: **0** active records with empty/whitespace
description — the backfill AC is already satisfied; the criterion becomes a
verified assertion, not work. Remaining pack-side pieces:

- Create-time refusal (nonzero exit, no directory) is vendored-upstream
  behavior — 0.6.14 still only warns (task_store.py:352) after
  `ensure_tasks_dir` (task_store.py:265). Parked on the Trellis fork task
  `08-08-create-empty-metadata-rejection`; disposition recorded in the PRD.
  This task does not patch `task_store.py`.
- Predicate divergence, measured 2026-08-08 (node 24 / CPython 3.14
  probes): JS `String.trim()` strips U+FEFF but NOT U+0085; Python
  `str.strip()` strips U+0085 but NOT U+FEFF. The two predicates disagree
  on BOTH characters, in opposite directions. Tests pin the full
  classification matrix — for each character, the gate's actual verdict
  (U+FEFF-only description: JS-empty → gate FAILS it; U+0085-only:
  JS-non-empty → gate passes it) AND the Python-side `strip()`
  classification computed in the same test — so the divergence is an
  explicit, named assertion. The PRD's original equality test ("fail if
  creation and gate classify differently") is impossible while the
  create side lives upstream; it converts to this divergence pin now and
  flips to an equality assertion at upstream uptake (recorded in the PRD
  dispositions).
- Documented invocations: repo-wide audit for `task.py create` examples
  (including `.agents/`, `.github/`, `.gemini/`, `.trellis/`). Each hit is
  classified: pack-owned surfaces get `--description` added; Trellis-managed
  or vendored surfaces (e.g. `.trellis/workflow.md`, `.trellis/scripts/
  task.py` usage text, Trellis-installed skills) must NOT be edited — byte-
  identity/managed-file contract — and are recorded in the upstream handoff
  register evidence instead. Classifier: the Trellis template-hash manifest
  plus the vendored-surface rule; classification per hit goes in the
  implementation log.
- Gate rule at preflight.mjs:3348 (non-empty title/description) is NOT
  relaxed.
- Fleet consumers: seed verification on consumers is parked until each
  consumer's own Trellis upgrade delivers >=0.6.8; recorded in the PRD
  dispositions and the seed-probe research note. This repo's verification
  is done (probe evidence above).

## Tests

Driver: `tests/test_review_preflight.py` (existing harness — node-side unit
scripts via subprocess for pure rule functions, InstallTestCase git fixtures
for full-script runs; match the established pattern per case). Cases:

1. Root task, `base_branch: chore/task-preflight-bare-filename-references`
   (PR #342 replay) vs default `main` → FAIL, diagnostic contains task path,
   value, and default. Covered TWICE: as a pure-function unit case AND as a
   full-script git-fixture run (fixture with `origin/HEAD` →
   `origin/main`, the defective root task.json present in the fixture
   diff, asserted nonzero exit + diagnostic) — the integration test binds
   resolver, diff population, and loop together; the manual demo is not a
   regression test.
1b. Env-override resolution (CI shape): fixture with NO `origin/HEAD` but
   `SD_AI_COMMAND_PACK_DEFAULT_BRANCH=main` exported → rule active,
   defective record FAILS. Absent-`parent` record (no key at all) with a
   bad value → FAIL (root-predicate pin).
2. Root task, `base_branch` equal to the default → PASS; padded value
   `" main "` also PASS (trim tolerance pinned).
3. Child task targeting the parent's active branch → PASS (R3 regression;
   existing child rule untouched).
4. Root task, feature-branch value + `meta.base_branch_exemption:
   "integration branch"` → PASS. Whitespace-only exemption → FAIL.
   Non-string exemption (e.g. `true`) → FAIL.
5. Unresolvable default (no origin/HEAD in fixture) → rule skipped, no
   failure — full-script fixture run.
6. Predicate divergence matrix: U+FEFF-only and U+0085-only descriptions —
   assert the gate's verdict for each AND the in-test Python `strip()`
   classification, naming the expected divergence.

## Bookkeeping / rollout / rollback

`review-preflight.mjs` is shipped payload: manifest version bump, changelog
heading, `make release-prep` (ledger). Mirror byte-identity proven by
`diff`. Rollback is SPLIT: reverting the rule (code) is a normal PR revert;
the 4 record corrections are data fixes that stand on their own merits and
must NOT be reverted with the code — restoring dead feature-branch
references would re-create known-invalid metadata.
