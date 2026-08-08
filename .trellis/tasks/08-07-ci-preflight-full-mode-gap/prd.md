# CI runs the review preflight only in bookkeeping mode, so a full-mode head merges unvalidated

## Goal

Make the review preflight's validation run against the content it validates,
rather than only against heads the scope classifier happened to route down the
cheap lane. A head that changes `.trellis/**` must have that change validated
whether or not the classifier routed it `full` — including the initial head of a
pull request, which is always routed `full` and is therefore never validated
today.

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
checks are never applied to the content under review. The same script runs
repeatedly next door on invented trees while the content under review ships
unvalidated.

### What actually forces `full`, which is not what the diff contains

The intuitive story — a head classified `full` because it changes code as well as
`.trellis/**` — is not the dominant cause and should not be the one this task
rests on. The classifier's first gate is the event action, before any diff is
examined:

```bash
write_full_result "bootstrap_full"
if [ "$EVENT_NAME" = "pull_request" ] && [ "$EVENT_ACTION" != "synchronize" ]; then
  select_full "pull_request_action_not_synchronize"
fi
```

(`.github/workflows/tests.yml:136-139`). The workflow triggers on `pull_request`
with no `types:` filter (`:3`), so the actions it receives are `opened`,
`synchronize`, and `reopened`. Only `synchronize` survives that gate.

**Therefore the initial head of every pull request is classified `full` and is
never validated, whatever it contains.** A pull request whose diff is nothing
but `.trellis/tasks/**` records — the case the preflight exists for — is still
`full` on open. Validation happens only if someone later pushes again to the
same pull request, which is an accident of authoring rhythm, not a property of
the content. A pull request opened correct-looking and merged without a second
push is never validated at all.

The eleven remaining `select_full` reason codes (`:141`-`:182`) are all
degradation paths — unsupported event, invalid commit identity, prior classifier
missing, unsafe, or not base-identical — so `bookkeeping` additionally requires
trustworthy evidence from the predecessor head. That is deliberate and is not
the defect. The defect is that the *validation* was attached to the mode rather
than to the content, so every one of those safety fallbacks silently disables
validation as a side effect.

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

| Run | Head | Action | Mode | `Validate bookkeeping head` | Conclusion |
|---|---|---|---|---|---|
| 31229940165 | `4cd89b5e` | opened | full | skipped | **success** |
| 31230376921 | `8a72d5fb` | synchronize | bookkeeping | failure | failure |

Both figures were read from the Actions API, not from a run page. The action
column is derived from run creation time against the pull request's own
`created_at`: PR #358 was created at `00:23:07Z` and run 31229940165 at
`00:23:10Z`, three seconds later, so that run is the `opened` event; run
31230376921 was created at `00:32:18Z`, nine minutes after open, so it is a
`synchronize`. This matches the gate at `:137` exactly and is the mechanism,
not a coincidence of what each diff touched.

The reference itself is byte-identical across the two heads — same line 103,
same content hash — and was removed in `765c0f74`. The heads are not otherwise
identical: `8a72d5fb` also corrected a `base_branch` in the same task's
`task.json`. That difference is unrelated to the reference and does not affect
the comparison, but saying the heads "differ only in mode" would be false. Had
the author not happened to push a second time, the reference would have merged.

### Reproduced by the pull request that filed this task

PR #365 — the pull request carrying this PRD — is a cleaner instance, because it
has no content confound at all. Its diff is seven files, every one of them under
`.trellis/tasks/`, and nothing else. It was created at `01:46:20Z`; its only
`Tests` run, 31233436772 on head `7c9c0075`, was created at `01:46:23Z`, so it
is the `opened` event. The `CI scope` job's step conclusions, read from the jobs
API:

```
2. Check out exact event head              = success
4. Classify exact-head CI scope            = success
5. Install review preflight coverage tooling = skipped
6. Validate bookkeeping head               = skipped
7. Report review preflight JavaScript coverage = skipped
8. Summarize CI scope                      = success
```

`unittest` (three legs), `Shell coverage`, `lint`, `security`, and
`Release payload gate` all ran and all succeeded, which is how the `full`
classification is known without reading the step summary. `CI Result` was
`success`. So a pull request consisting exclusively of Trellis records had those
records validated by nothing, and the required check said so was fine.

Pushing the correction to that same pull request then produced the other side of
the control, on one branch, with only the event action differing:

| Run | Head | Action | Mode | `Validate bookkeeping head` | `CI Result` |
|---|---|---|---|---|---|
| 31233436772 | `7c9c0075` | opened | full | skipped | success |
| 31233932809 | `0f4a8eb3` | synchronize | bookkeeping | ran, success | success |

On the second head every expensive job — `unittest`, `Shell coverage`, `lint`,
`security`, `Release payload gate` — reported `skipped`, and the coverage
tooling, validation, and coverage report steps all ran. This is a stronger
demonstration than PR #358 because there is no content confound in either
direction: the same branch, validated on one head and not on the other, decided
solely by whether the event was an open or a push.

That is the failure mode stated exactly: the required check is not wrong about
the head it evaluated, it simply never looked. And the head guaranteed to be
routed `full` is the first one — which every pull request has, and which some
have only one of.

### There is no post-merge net either

The reasonable assumption is that a defect merging unvalidated gets caught by the
`push` run on `main` — the action gate at `:137` only applies to `pull_request`
events, so a push is free to classify `bookkeeping`. It does not happen. The
three most recent `main` push runs at the time of writing — 31196858902
(`4378d37b`), 31194382584 (`cdc17dd1`), 31193550256 (`15df0841`) — each show
`Validate bookkeeping head = skipped`, read from the jobs API. A merge commit
does not satisfy the classifier's base-identity and prior-evidence conditions, so
it degrades to `full` like everything else.

Content that merges unvalidated is therefore never validated, before or after.

### Measured blast radius, at the time of filing

This is not a latent risk awaiting a future pull request. Of twelve open pull
requests in this repository, five have exactly one commit and one `Tests` run —
so their only head is the `opened` head — and every one of them is `CLEAN` and
mergeable:

| PR | Files | All under `.trellis/`? | `Validate bookkeeping head` |
|---|---|---|---|
| #363 | 4 | yes | skipped |
| #362 | 12 | yes | skipped |
| #359 | 4 | yes | skipped |
| #357 | 4 | yes | skipped |
| #356 | 4 | yes | skipped |

Every one is a planning-artifact filing — precisely the content the preflight's
Trellis and documentation-reference checks exist to validate — and not one of
them has been validated by CI. Any of them can be merged today, and nothing
downstream will look at it afterwards.

Do not treat the specific numbers as durable: the set changes as pull requests
open, merge, and receive second pushes, and the count must be re-derived rather
than quoted at implementation time. What is durable is the shape — a pull request
that is authored once, opened, reviewed, and merged without a second push never
has its Trellis content validated, and single-commit planning filings are the
normal case in this repository, not an edge case.

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
- [ ] Specifically, the **initial** head of a newly opened pull request carrying
      the defect fails `CI Result`, with the triggering action shown to be
      `opened`. This is the criterion that actually closes the gap: it is the
      guaranteed-`full` case (`.github/workflows/tests.yml:137-139`), it is the
      one every pull request has, and a fix demonstrated only on a `synchronize`
      head would leave it open while looking green.
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
- Corrected on 2026-08-07 after PR #365 was opened, by that pull request's own
  CI. The PRD as first written attributed `full` classification to diff content
  — "a head that changes code *and* `.trellis/**`" — which is not the dominant
  cause. The classifier's first gate is the event action
  (`.github/workflows/tests.yml:137-139`), so every `opened` head is `full`
  regardless of its diff. PR #365 proved it against itself: a diff of nothing but
  `.trellis/tasks/**` was classified `full`, its validation step skipped, and
  `CI Result` reported success. The finding is therefore broader than filed —
  every pull request's first head is unvalidated — and the original framing would
  have let a fix be demonstrated on a `synchronize` head while leaving the real
  case open, which is why an acceptance criterion now names the `opened` action
  explicitly.
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
