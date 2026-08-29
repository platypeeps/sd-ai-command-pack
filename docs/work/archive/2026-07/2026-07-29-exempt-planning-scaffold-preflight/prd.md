---
title: Exempt untouched planning scaffolds from the review preflight task-context gate
status: done
created: 2026-07-29
---
# Exempt untouched planning scaffolds from the review preflight task-context gate

## Goal

`python3 .trellis/scripts/task.py create` seeds `implement.jsonl` and
`check.jsonl` with a generated `_example` row. The pack's own review preflight
failed on exactly those rows the moment they appeared in the diff, so creating a
Trellis task put the repo into a failing gate state until the author blanked or
rewrote both files by hand. Hit live during the v0.56.1 fleet rollout in
`platypeeps/rwbp-coordinator`, where it consumed the fleet-controller retry
budget for that lane.

The affected population is pack-installed repositories where task creation
actually seeds the manifests. Trellis writes them only when
`_has_subagent_platform` succeeds (`.trellis/scripts/common/task_store.py:146`,
`:346`). That predicate returns true as soon as **any** well-known sub-agent
config directory exists — `.claude` among them — and only falls through to the
Codex dispatch-mode check when none does. So the unaffected population is
narrow: repos with no such directory and either no `.codex` or Codex in inline
dispatch mode. A `.claude` repo is affected regardless of Codex's mode; this
worktree is one.

The failure is an internal inconsistency in the gate, not a Trellis defect:
`checkTrellisTaskContextManifests` pulls a task's sibling manifests in from a
changed `task.json` only when status is **not** `planning`, and never inspects
an unchanged planning scaffold — but it failed a newly created one
unconditionally.

## Constraints

- The scaffold text itself is Trellis-owned
  (`.trellis/scripts/common/task_store.py`, `_SEED_EXAMPLE`). `manifest.json`
  ships no `.trellis/**` path and CONTRIBUTING.md excludes Trellis-owned
  platform runtime, so the pack cannot change what `task.py create` writes.
  The fix must be entirely pack-side.
- The curation requirement at `task.py start` is deliberate and must survive:
  a task that reaches `in_progress` with scaffold rows still fails.
- `templates/**` is the source of truth; root `scripts/**` and `docs/**` are
  generated mirrors refreshed by `make sync`.
- Payload change requires a `manifest.json` version bump, a matching top
  `CHANGELOG.md` heading, and an all-pass `docs/fleet/candidate-validation.json`.

## Requirements

- R1. Neither seed-row enforcement lane may fail a planning task's untouched
  generated scaffold. There are two, both in
  `scripts/sd-ai-command-pack-review-preflight.mjs`: the diff-scoped review gate
  `checkTrellisTaskContextManifests`, and the bookkeeping / final-bundle
  validator `validateBookkeepingTaskContexts`, which emits a `task_context_seed`
  reason code. Exempting only one leaves task creation failing through the
  other.
- R2. The exemption predicate is **shape-based, not value-based**: a single
  non-blank row that parses to a plain object whose sole key is `_example`, in a
  non-archived task whose `task.json` parses and reads `"status": "planning"`.
  It does not compare the row's value against Trellis's `_SEED_EXAMPLE` string.
  That is deliberate — `_SEED_EXAMPLE` is Trellis-owned and changes with Trellis
  versions, so pinning it would re-break the gate on the next Trellis upgrade,
  reproducing this exact defect with a worse recovery path (consumers would have
  to wait for a pack release). Everything not matching the shape fails closed,
  including an unreadable, symlinked, or missing `task.json`.
- R3. A seed row surviving beside authored rows, or carrying extra keys such as
  `{"_example": "...", "file": "src/app.py"}`, still fails.
- R4. Malformed-JSONL detection and the `.trellis/spec/**` /
  `.trellis/tasks/**/research/**` reference-root check are unchanged.
- R5. The review gate's pass line reports how many scaffolds were exempted, so
  an exemption is visible in the receipt rather than silent.
- R6. `templates/docs/SD_AI_COMMAND_PACK.md` documents the new behavior for both
  lanes. Its prior text asserted the opposite ("Changed planning manifests that
  still contain generated scaffolds fail") and would otherwise be wrong.

## Out of Scope

- Changing the scaffold row Trellis writes, or its instruction text. That text
  says only "Put spec/research files only" and never names the two allowed
  roots, so a good-faith author citing a repo doc still fails the reference
  check. Recorded against the parent task; the gate's own failure message names
  both roots.
- Relaxing the reference-root check itself.
- Pinning the exemption to Trellis's exact `_SEED_EXAMPLE` text. See R2 for why.
  The accepted residual: inside planning only, an `_example`-only row whose
  value was hand-edited is also exempt. It is still an uncurated scaffold with
  no `file` key, it is still worthless as sub-agent context, and it still fails
  the moment the task leaves planning.

## Acceptance Criteria

- [x] A1. A freshly created planning task with both scaffolds present passes the
  review preflight, and the pass line names the exempted count.
- [x] A2. A seed row beside an authored row fails; a seed row with extra keys
  fails; a seed row in an `in_progress`, `review`, `completed`, or archived task
  fails.
- [x] A3. `tests/test_review_preflight.py` covers A1 and A2 at both the unit
  level (`isPristineTrellisTaskContextScaffold`) and end-to-end against an
  installed repo fixture, and the prior assertion that encoded the defect is
  corrected. The end-to-end statuses exercised are `planning`, `in_progress`,
  `completed`, and archived; `review` is not exercised separately because the
  exemption turns on a single `status === 'planning'` equality. The fixtures
  write scaffold rows directly rather than invoking `task.py create`, so they
  test the shape predicate of R2, not byte-equality with Trellis's current
  `_SEED_EXAMPLE`. Byte-level agreement with the real generator is covered by
  the live dogfood under Verification, not by the suite.
- [x] A4. `tests/test_bookkeeping_validator.py` asserts the second lane both
  ways: a planning task's pristine scaffold emits no `task_context_seed`, and
  the same scaffold beside an authored row does.
- [x] A5. `make test` passes with zero skips; `make lint` passes; `make generate`
  reports a clean shipped-surface closure.
- [x] A6. Version bumped to 0.56.2 with a matching `CHANGELOG.md` heading and an
  all-pass fleet candidate ledger whose `payloadDigest` matches the current
  payload.

## Verification

- `make test` — 49 `OK` blocks, 0 `FAILED`, 0 skips.
- `make lint` — ruff `All checks passed!`, mypy `Success: no issues found in 38
  source files`.
- `make generate` — `shipped-surface closure: clean` (the changed-path and
  affected-node counts move with each bookkeeping commit and are not recorded
  here).
- `scripts/sd-ai-command-pack-fleet-candidate-check.py` — 8/8 consumers passed
  at candidate 0.56.2, including `platypeeps/rwbp-coordinator`. The ledger is
  regenerated after the last payload edit; `--check-ledger` is the read-only
  way to confirm its `payloadDigest` still matches.
- Live dogfood: creating this task and running the preflight returned
  `PASS ... 2 untouched planning scaffold(s) are exempt until the task leaves
  planning.` against the scaffold Trellis itself wrote. This is the only
  evidence that the shape predicate accepts the real generator's output. The
  receipt is historical — it was observed while this task was in `planning`,
  before its own manifests were curated at `task.py start`, so re-running the
  preflight now reports the same check with no exemptions.

## Notes

- Parent: `07-28-analyze-recurring-trellis-workflow-instability`.
- Implementation landed before this task record was created; the record is
  retroactive and the acceptance criteria above are checked against evidence
  already collected, not asserted in advance.
- Planning adversarial review (host + Codex lanes) ran against this record and
  the landed diff. Ledger: `research/adversarial-review-2026-07-29.md`. All four
  concerns are addressed; none is deferred.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-07/07-29-exempt-planning-scaffold-preflight`:

- research/adversarial-review-2026-07-29.md
