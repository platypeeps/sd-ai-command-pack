# CI runs the review preflight only in bookkeeping mode, so a full-mode head merges unvalidated

## Goal

Make the review preflight's validation run against the content it validates,
rather than only against heads the scope classifier happened to route down the
cheap lane. A head that changes `.trellis/**` must have that change validated
whether or not it also changes code.

The classifier itself is correct and stays. What is wrong is which lane the
validation is attached to.

## Problem

`.github/workflows/tests.yml` classifies each exact head as `full` or
`bookkeeping`, then runs the review preflight in the `ci-scope` job under:

```yaml
      - name: Validate bookkeeping head
        if: steps.classify.outputs.mode == 'bookkeeping'
```

(`.github/workflows/tests.yml:230-232`). The two executing invocations of
`node scripts/sd-ai-command-pack-review-preflight.mjs` are inside that step
(`:254` and `:261`), as is the coverage tooling it needs (`:225-227`) and the
coverage report (`:282`).

The validation lane and the expensive-job lanes are **disjoint, not nested**.
`unittest`, shell coverage, `lint`, `security`, and the release payload gate are
each gated on `needs.ci-scope.outputs.mode == 'full'` (`:348`, `:410`, `:484`,
`:529`, `:568`); the preflight step is gated on `bookkeeping`. Some steps are
ungated and run in both modes — checkout, Node setup, the classifier itself
(`:51`), and the scope summary (`:318`) — but none of them validates content, so
no *validating* step runs in both.

State the full-mode claim carefully, because the loose version is false and
invites dismissal. Full mode *does* execute the preflight, many times:
`tests/test_review_preflight.py` spawns
`node scripts/sd-ai-command-pack-review-preflight.mjs` as a subprocess throughout,
directly and through helpers, and `lint` additionally `node --check`s both the
`scripts/` and `templates/scripts/` copies (`:519-522`).

Do not quote a number for those executions. Three passes at counting them
produced three different answers — lines mentioning the script, direct call
sites, and call sites plus helper and loop expansion multiplied by the matrix
legs that run the suite — and none of them is the fact this task turns on. The
count is not load-bearing; where the executions point is.

Every one of them runs in a synthetic fixture root, against a tree the test
constructs for the assertion at hand. Not one is pointed at the checked-out event
head. That was confirmed in two independent review passes.

The precise claim is therefore: **in `full` mode nothing validates the exact head**.
The preflight's documentation path references, personal absolute paths,
changed-task-metadata, task-topology, journal-record, and task-context-manifest
checks are never applied to the content under review. A head that changes code
*and* `.trellis/**` is classified `full`, so its `.trellis/**` content ships
unvalidated while the same script runs repeatedly next door on invented trees.

### The naming invites the wrong assumption

"Full" reads as a superset of "bookkeeping". It is not. The design that
introduced the split said so plainly — `ci-scope` "publishes `mode` and reason
outputs and, for bookkeeping mode, completes the cheap validation in the same
runner"
(`.trellis/tasks/archive/2026-07/07-24-add-bookkeeping-only-ci-fast-lane/design.md:110-112`).
Attaching the cheap validation to the cheap mode was a deliberate placement, and
for the case that task was solving — a journal-only successor head — it is
correct.

The gap is the case it did not consider: bookkeeping *content* arriving on a
head that is not bookkeeping-only. The classifier answers "can I skip the
expensive jobs for this head", which is a cost question. The preflight answers
"is the Trellis and documentation content of this head valid", which is a
correctness question. The workflow currently uses one answer for both.

### Demonstrated on one pull request, same defect, opposite verdicts

PR #358 carried a `prd.md` reference to a repository-relative path that does not
exist here. The reference is present, once, in both of two consecutive heads —
verified by reading the file at each commit — and the runs disagree:

| Run | Head | Mode | `Validate bookkeeping head` | Conclusion |
|---|---|---|---|---|
| 31229940165 | `4cd89b5e` | full | skipped | **success** |
| 31230376921 | `8a72d5fb` | bookkeeping | failure | failure |

Both figures were read from the Actions API, not from a run page. The reference
itself is byte-identical across the two heads — same line 103, same content hash
— and was removed in `765c0f74`. The heads are not otherwise identical:
`8a72d5fb` also corrected a `base_branch` in the same task's `task.json`. That
difference is unrelated to the reference and does not affect the comparison, but
saying the heads "differ only in mode" would be false. Had the second head not
happened to classify `bookkeeping`, the reference would have merged.

That is the failure mode stated exactly: the required check is not wrong about
the head it evaluated, it simply never looked. And the head most likely to be
routed `full` is the one carrying the most content.

## Requirements

- The preflight's validation must run on any head whose diff touches the paths
  it validates, regardless of classified mode. Mode may continue to decide which
  *expensive* jobs run; it must not decide whether content is validated.
- `CI Result` must remain the single required context and must fail when the
  validation fails, in either mode. A validation that runs in a lane the
  aggregate ignores is not a fix.
- Do not collapse the two modes or remove the classifier. The cost saving on a
  bookkeeping-only successor head is real and is the reason the classifier
  exists.
- Do not duplicate the preflight invocation into a second definition. If it must
  run from more than one job, the invocation is shared, not copied — two copies
  drift, and a drifted copy validating less is indistinguishable from one
  validating correctly.
- Preserve the existing c8 coverage measurement of the preflight, including the
  guard that fails when c8 measures zero lines. If the invocation moves, the
  coverage plumbing moves with it and must still be able to fail closed.
- State what happens on a head that touches none of the validated paths. The
  Trellis validators must not fail closed on absence, and the answer must be
  stated rather than left to whatever the script currently does on an empty set.

## Acceptance Criteria

- [ ] A head classified `full` that contains a broken documentation path
      reference fails `CI Result`. Demonstrated on a real pull request, with the
      classified mode read from the run and shown to be `full` — not asserted,
      and not shown by a local run.
- [ ] A head classified `bookkeeping` with the same defect still fails, proving
      the existing coverage was not traded away for the new coverage.
- [ ] A head classified `full` with no `.trellis/**` and no documentation change
      still passes, proving nothing fails closed on absence.
- [ ] A bookkeeping-only successor head still skips `unittest`, shell coverage,
      `lint`, `security`, and the release payload gate. Verified from the run's
      job conclusions, so the cost saving is shown intact rather than assumed.
- [ ] The c8 coverage measurement of
      `scripts/sd-ai-command-pack-review-preflight.mjs` still reports a non-zero
      measured line count, and its zero-line guard is shown to still be able to
      fire.
- [ ] Replaying PR #358's head `4cd89b5e` content — the broken reference on a
      `full`-mode head — fails the gate, as a regression test against the
      observed occurrence.
- [ ] The set of workflow steps that invoke the preflight against the event head
      is enumerated, and every one of them resolves to the same shared definition
      — one step, one reusable action, or one script — rather than to a
      duplicated command body. The observable unit is the step, not the command
      occurrence: the current single step already contains two `node …` command
      lines and would trivially satisfy a "one occurrence" reading while the
      defect remains, so that reading is explicitly not what this asks.

## Out of scope

- Changing what the preflight checks, or any behaviour inside
  `scripts/sd-ai-command-pack-review-preflight.mjs`. This task moves when the
  script runs, not what it does. The eligibility rule for documentation
  references is a separate open task,
  `08-06-preflight-bare-filename-references`.
- Removing or re-tuning the scope classifier, its schema, or its reason codes.
- Teaching the preflight to resolve a path that lives in a different
  repository. A documentation reference to another repository's file cannot be
  validated from this checkout, and CI is not required to acquire that ability —
  recorded as an operator decision on 2026-08-07. The author-side convention is
  in the eligibility task above; nothing about it belongs in this workflow.
- The corresponding gap in the consumer repository `se-ai-command-pack`, whose
  CI runs the preflight in no mode at all. That is a different defect — no
  coverage rather than partial — in a workflow this repository does not own, and
  it is tracked there.
- `main`-push and release behaviour. `main-push-scope` enforces the direct-push
  boundary independently and `auto-tag-release` already requires a successful
  full aggregate.

## Notes

- Found on 2026-08-07 while tracing why PR #358 passed on one head and failed on
  the next with the same defect present in both. Every line number, mode, and
  run conclusion above was read from the working tree at `origin/main` or from
  the Actions API in that pass.
- The archived task that introduced the split is
  `07-24-add-bookkeeping-only-ci-fast-lane`, with follow-ups
  `07-27-republish-bookkeeping-ci-fast-lane-linear` and
  `07-28-pin-bookkeeping-ci-classifier-trust`. Read the first one's `design.md`
  before choosing a remedy: its aggregate contract already enumerates permitted
  per-mode job states, and any change here has to keep that contract coherent.
- Complex enough to need `design.md` and `implement.md` before `task.py start`.
  More than one remedy is available, they trade against each other, and each has
  to keep the c8 coverage plumbing and the aggregate's permitted-state table
  coherent. Comparing them is design work and is deliberately not done here.
