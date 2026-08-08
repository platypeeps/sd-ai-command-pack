# CI never fully validates a pull request's Trellis content: full mode skips the preflight, bookkeeping mode runs it against the previous head

## Goal

Make the review preflight's validation run against the content it validates.
Two gaps stop that happening today.

"Fully" in the title is load-bearing, and so is the difference between coverage
and a guarantee. Plenty of pull requests are in fact completely covered: the
repo-wide checks fire whenever the preflight runs at all, and a pull request
whose every change lands on a successful bookkeeping successor head has its
diff-scoped content checked too. What is missing is any *guarantee* — nothing
in the workflow makes whole-pull-request coverage a property of the pull
request rather than an accident of its event actions and push rhythm. The claim
here is the absence of that guarantee, not that complete validation is
impossible.

1. **Which lane.** The preflight runs only when the scope classifier routes a
   head `bookkeeping`. Every pull request's initial head is routed `full`, so
   it is never validated whatever it contains.
2. **Which diff.** In the lane that does run, the preflight's base is the pull
   request's own previous pushed head, so its diff-scoped checks see only the
   newest push. Anything an earlier push committed is never re-examined.

A head that changes `.trellis/**` must have that change validated regardless of
classified mode, and against the pull request's base rather than an incremental
window.

The classifier itself is correct and stays. What is wrong is which lane the
validation is attached to, and which base it is handed.

## Problem

`.github/workflows/tests.yml` classifies each exact head as `full` or
`bookkeeping`, then runs the review preflight in the `ci-scope` job under:

```yaml
      - name: Validate bookkeeping head
        if: steps.classify.outputs.mode == 'bookkeeping'
```

(`.github/workflows/tests.yml:230-232`). The two executing invocations of
`node scripts/sd-ai-command-pack-review-preflight.mjs` are inside that step
(`:254` and `:261`). Two sibling steps carry the same `bookkeeping` gate rather
than living inside it: the coverage tooling the step needs (`:225-227`) and the
coverage report (`:280-282`).

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
with no `types:` filter (`:3-4`), so the actions it receives are `opened`,
`synchronize`, and `reopened`. Only `synchronize` survives that gate.

**Therefore the initial head of every pull request is classified `full` and is
never validated, whatever it contains.** A pull request whose diff is nothing
but `.trellis/tasks/**` records — the case the preflight exists for — is still
`full` on open. Validation happens only if someone later pushes again to the
same pull request, which is an accident of authoring rhythm, not a property of
the content. A pull request opened correct-looking and merged without a second
push is never validated at all.

The eleven remaining `select_full` call sites (`:141`-`:182`), carrying eight
distinct reason codes between them, are all
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

PR #365 — the pull request carrying this PRD — is a cleaner instance, because
its first head needs no comparison at all to make the point. Its diff is seven
files, every one of them under
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
the picture, on one branch — with the event action differing, and, as the
paragraph after the table records, not only the event action:

| Run | Head | Action | Mode | `Validate bookkeeping head` | `CI Result` |
|---|---|---|---|---|---|
| 31233436772 | `7c9c0075` | opened | full | skipped | success |
| 31233932809 | `0f4a8eb3` | synchronize | bookkeeping | ran, success | success |

On the second head every expensive job — `unittest`, `Shell coverage`, `lint`,
`security`, `Release payload gate` — reported `skipped`, and the coverage
tooling, validation, and coverage report steps all ran.

Do not oversell that second row. The two heads are not content-identical:
`0f4a8eb3` rewrote this PRD's own attribution of the `full` cause and touched
`task.json` with it (105 insertions, 19 deletions across two files), which is
the correction recorded in the Notes below. So the pair is not a controlled
comparison, any more than PR #358's was.

The demonstration does not need the pair. The first row stands alone: a diff of
nothing but `.trellis/tasks/**` had its validation step `skipped` and `CI Result`
report `success`. No property of that content can explain a step that never ran,
and the gate at `:137` names the mechanism directly. The second row is
corroboration that the same branch does get validated once the event action
changes — not proof that the action was the only thing that changed.

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
`Validate bookkeeping head = skipped`, read from the jobs API, so it degrades
to `full` like everything else.

Name the cause correctly, because the intuitive one is wrong: base-identity
comparison is restricted to `pull_request` events
(`.github/workflows/tests.yml:163`) and so cannot be what rejects a push. The
classifier instead walks the commit range and returns `history_contains_merge`
(`.github/scripts/bookkeeping_ci_scope.py:193`) as soon as it sees a merge
commit. The conclusion is unchanged; only its mechanism is.

So there is no net *dedicated* to merged content: nothing re-examines a commit
because it landed on `main`.

Resist the absolute here, because the repository has already disproved it. The
four repo-wide checks re-scan the whole tree on any run where the preflight
executes, so merged content can still be caught later — by an unrelated pull
request that happens to draw a `bookkeeping` head. That is not hypothetical: on
2026-08-08 two broken documentation references sitting on `main` surfaced exactly
that way, on a branch that had nothing to do with them, and had to be repaired
before an unrelated pull request could go green.

The accurate statement is narrower and worse. Merged content is caught by
accident or not at all: normally by a repo-wide check, on some later unrelated
head that happens to route `bookkeeping`. The diff-scoped checks revisit it only
if some later diff
happens to select the same path again — a change to that record, or to a sibling
that drags it into the working set — which is a coincidence of what someone edits
next, not a net. Detection is displaced onto whoever is unlucky enough to open
the next qualifying pull request.

### The one lane that does validate sees only the newest push

Two conditions must both hold for a defect to be caught: the head has to
classify `bookkeeping`, and the defect has to fall inside the diff the
preflight is pointed at. The second condition is not the pull request's diff,
and this section is why "push a second time and it gets validated" is only
half true.

The validating step sets the preflight's base to `BEFORE_SHA`:

```yaml
SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF="$BEFORE_SHA" \
  "${c8_run[@]}" node scripts/sd-ai-command-pack-review-preflight.mjs
```

(`.github/workflows/tests.yml:253-254`.) That value reaches the step as the
classifier's `before_sha` output (`:235`, written at `:121` from the
classifier result), which is seeded from `github.event.before` (`:56`). The
workflow states what it is, in its own comment: "On a pull_request, BEFORE_SHA
is the PR's own previous head" (`:157`). The preflight turns that into
`diff <base>...HEAD`
(`scripts/sd-ai-command-pack-review-preflight.mjs:4666`), so its branch diff
spans the newest push alone — never the pull request.

Two properties decide whether a given check can hide a defect this way: does
its body consult that diff, and can it `fail()` at all. Classifying the twelve
checks `runReviewPreflight` registers (`:229-241`) on both axes — diff basis
by whether the body reaches `currentChangedPaths`, `currentDiffSources`,
`currentReviewDiffStats`, or a baseline-ref helper:

- **Repo-wide and failing** — unaffected by the base, because they re-scan the
  repository every run: package overrides, documentation path hygiene
  (personal absolute paths), documentation path references, completed Trellis
  task location.
- **Diff-scoped and failing** — the exposure: changed Trellis task metadata,
  changed Trellis task topology semantics, Trellis task context manifests.
- **Hybrid** — Trellis journal records. It parses every journal file and walks
  every current session repo-wide (`:3947`, `:4970`), so its placeholder and
  structural rules still see an earlier push's journal. But the baseline reaches
  further than the historical-edit comparison alone, and an implementer who
  assumes otherwise will under-scope the fix: the contradictory-validation
  fallback rules are also suppressed for any session byte-identical to its
  baseline copy (`:4991-5003`, where `unchangedFromBaseline` gates
  `findContradictoryJournalValidationFallbacks`). Under an incremental base a
  session committed by an earlier push *is* identical to the baseline, so those
  rules go quiet on exactly the sessions this gap leaves unexamined. Treat the
  baseline-dependent share as larger than the name "historical edits" suggests,
  and re-derive it at design time rather than trusting this paragraph.
- **Diff-scoped and advisory** — affected but harmless, since none calls
  `fail()`: copied template diff disclosure, first-review risk sweep, diff
  size. An incremental base makes these under-report rather than let anything
  through.
- **Diff-based but independently based** — the scope advisory. It shells out
  to `scripts/sd-ai-command-pack-review-scope.sh`, whose `scope_base_ref`
  consults
  `SD_AI_COMMAND_PACK_SCOPE_BASE_REF`, then
  `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF`, then its discovered default branch
  (`:56-64`). CI sets neither, so it is not narrowed by `BEFORE_SHA` at all.

The exposure is therefore narrow and specific: three checks that can fail
outright, plus the baseline-dependent half of journal validation. Every one of
them is Trellis bookkeeping content, which is what this task exists to protect.

That split explains an otherwise puzzling detail of the PR #358 evidence
above: the broken documentation reference was byte-identical across both heads
and still failed the `synchronize` run, because reference resolution is
repo-wide. An invalid *task record* committed in an earlier push behaves the
opposite way.

Demonstrated on `3d8abb41`, the commit that added
`08-08-codex-lane-consent-gate/task.json` with an empty `description`. One
worktree, one script, the defect present throughout; only the base ref
differs:

```text
$ SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF="$(git rev-parse HEAD^)" \
    node scripts/sd-ai-command-pack-review-preflight.mjs
FAIL .trellis/tasks/08-08-codex-lane-consent-gate/task.json field description
     must be a non-empty string.
Review preflight: 1 failure(s), 0 warning(s).

$ SD_AI_COMMAND_PACK_REVIEW_PREFLIGHT_BASE_REF="$(git rev-parse HEAD)" \
    node scripts/sd-ai-command-pack-review-preflight.mjs
PASS no changed Trellis task metadata records require integrity checks.
Review preflight: 0 failure(s), 0 warning(s).
```

The second invocation is what CI runs on a later push to that branch — on those
that classify `bookkeeping`, which is the only lane the step runs in at all
(`.github/workflows/tests.yml:230-232`). The first is what it never runs, in
either lane.

So for the diff-scoped checks a second push validates the second push, and the
first head's content stays unexamined by every later run whose diff does not
happen to select it again. A
branch that commits a task record and then pushes twice more has that record
checked by CI in neither mode: `full` skips the step, and `bookkeeping` runs it
against a base that already contains the record.

#### How the two gaps interact, which is not simple addition

Be precise about the residual, because the obvious framing overstates it. Once
gap 1 is closed and every head runs the preflight, most content is caught on
arrival: the push that introduces a bad record has that record inside its own
incremental diff, so an incremental base still sees it.

What survives a gap-1-only fix is the case where a **later push invalidates
content an earlier push committed**, so the offending state is never inside any
single incremental window. Take push 1 adding a parent `task.json` that names a
child directory, and push 2 deleting that child. Three code paths have to miss
it, and all three do:

- `checkChangedTrellisTaskMetadata` collects only `task.json` files present in
  the diff (`:2984-2986`). The parent's record did not change in push 2, so it
  is never inspected, and `validateTrellisTaskMetadataLinks` (`:3030`) is never
  reached for it.
- The deleted child's own `task.json` *is* in push 2's diff, but is loaded with
  `deletedIsMissing: true` and skipped outright (`:2991-2994`).
- The rule that would catch it — `references missing task` at `:3481`, inside
  `loadReferencedTrellisTaskRecord` — fires only from the parent record's link
  validation, which the first bullet already excluded.

`checkChangedTrellisTaskTopologySemantics` does not save it either: it is
diff-scoped through the same `currentChangedPaths` (`:3047`), and both of its
work sets are keyed off changed paths — changed task files at `:3075`, changed
task directories at `:3113` — so an untouched parent enters neither.

Do not reach for a manifest-and-spec version of this example. Deleting a spec
file selects no context manifest for inspection — `:3651-3659` admits a changed
path only if it is itself an `implement.jsonl`/`check.jsonl` or a `task.json`,
and a changed non-planning `task.json` then pulls in both of its manifests
(`:3690-3696`), so the working set is wider than "changed manifest paths" but
still never reaches a spec file — and manifest entries are validated for allowed
path *shape* only — `isTrellisTaskContextReference` at `:3851` — with no
existence check anywhere in `checkTrellisTaskContextManifests` (`:3643-3753`
contains no `existsSync`). A manifest citing a file that never existed passes
today, incremental base or not. That is a separate gap, out of scope here, and
it is not a demonstration of this one.

Both merge green. That is the independent half of this defect, and it is why
the base has to become the pull request's base rather than the previous head —
not merely so every head runs the preflight, but so each run sees the whole
change it is certifying.

Gap 2 also constrains how gap 1 may be fixed. On an `opened` event
`github.event.before` is not a commit at all, so a remedy that routes full-mode
heads through the existing step must choose a base for that case regardless.
Choosing the pull request's base closes both; choosing anything else re-opens
this one.

### Invalid records that already merged

The blast radius below is about pull requests that *can* merge unvalidated.
Four records already did. Each shipped an empty `description`, violating
`validateTrellisBookkeepingMetadata`
(`scripts/sd-ai-command-pack-review-preflight.mjs:3348-3351`) — a diff-scoped
failing check. The rule was correct and present when every one of them was
created, and all four reached `main` anyway.

They are not all evidence for the same thing, and the distinction matters:

**Attributable to the current pair.** `08-08-codex-lane-consent-gate`, added in
`3d8abb41` on 2026-08-08 and repaired in `08a3daf0`. Both gaps were deployed;
this record passed through them.

**Evidence of an earlier, total absence.** `07-25-agent-artifacts`,
`07-25-harden-toolchain-failure-paths`, and
`07-25-reduce-review-tooling-spawns`, all added in `d97244e3` on 2026-07-25
and repaired by PR #379. At that revision
`.github/workflows/tests.yml` ran no event-head preflight at all — the
`Validate bookkeeping head` step first appears in `b16d9e69` on 2026-07-27, two
days later. These three predate the lane and cannot be attributed to the mode
or the base; what they show is that the class of defect is real and recurring,
which is why the lane was introduced.

None of the four was found by CI. The 2026-08-08 record was found by hand at
the pre-archive gate, when PR #376's finalization refused to proceed — the
latest possible moment and the most expensive one, because by then the task is
finished and the operator is mid-merge. The other three were found by auditing
`main` on 2026-08-08, not by any gate.

Read this as a lower bound rather than a measurement: it counts one rule, on
one field, in one of the three diff-scoped failing checks, and one of the four
is direct evidence for the pair rather than the class.

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
them has been validated by CI. Any of them can be merged today, with no
downstream stage that will look at it — only the accidental repo-wide re-scan
described above, on whatever unrelated pull request draws a `bookkeeping` head
next.

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
- The diff-scoped checks must be evaluated against the pull request's base, not
  against the previous pushed head. Running the preflight on every head is not
  sufficient on its own: with the base still set to `BEFORE_SHA`
  (`.github/workflows/tests.yml:253`) a record introduced by an earlier push
  stays outside the window and stays unchecked. Both halves are one fix or the
  gap only appears closed.
- State the base for `push` events too. `BEFORE_SHA` is the natural value there
  and may well remain correct, but the pull-request and push bases are now
  different questions and the answer must be written down rather than inherited.
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
- [ ] A pull request whose **first** push is valid on its own and whose
      **second** push invalidates it — the parent/child construction above,
      where the only `task.json` in push 2's diff is the deleted child's own,
      and the parent record that now dangles is untouched — fails `CI Result`
      on the second head. This is the incremental-base criterion,
      and it must be built this way rather than as "push 1 carries the defect".
      That simpler shape cannot isolate the base: once the mode gap is fixed
      push 1 fails, and a failed predecessor makes the classifier return
      `prior_success_missing` and route push 2 `full`
      (`.github/scripts/bookkeeping_ci_scope.py:425-433`, with the
      `conclusion != "success"` requirement at `:297` and `:325`), so the
      criterion would never exercise the bookkeeping lane's base at all.
      Demonstrate on a real pull request, with the classified mode and the base
      the preflight used both read from the run.
- [ ] The same construction is demonstrated in **both** modes, or the reason
      one mode is unreachable is stated with evidence. A remedy that corrects
      the base only where the preflight runs today, or only where it runs
      after the mode fix, leaves the other lane incremental while every other
      criterion here reports green.
- [ ] The diff-scoped checks are re-enumerated from the implementation's own
      source at the time of the fix, rather than taken from this PRD's list.
      The list is a 2026-08-08 snapshot of `runReviewPreflight`, and a check
      added or converted since then would inherit the same defect silently.
      Enumerate by reaching into each check body for `currentChangedPaths`,
      `currentDiffSources`, `currentReviewDiffStats`, and the baseline-ref
      helpers — a grep for the phrase "changed" in check names misses
      `checkDiffSize` and `checkCopiedTemplateDiffDisclosure`.
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
- [ ] The base used on `push` events is stated in the workflow, and the value
      the classifier emitted is read from an existing `main` push run rather
      than from the workflow source. Three of the requirements above are
      satisfiable by writing prose alone — this one, the aggregate contract
      below, and the no-relevant-path behaviour — so each gets a criterion that
      requires an observation. This is an observation of a run, not a change to
      push behaviour, which stays out of scope below. Retaining `BEFORE_SHA`
      here is an acceptable outcome; leaving it unstated is not.
- [ ] `CI Result` is shown to still be the only required context after the
      change, read from the repository's branch-protection settings and not from
      the workflow file, and a run whose validation fails is shown to make
      `CI Result` fail in **both** modes. The mode fix necessarily adds a
      validating step to a lane whose `needs` relationship to the aggregate was
      never load-bearing before, which is precisely how a validation lands in a
      lane the required context ignores.
- [ ] The behaviour on a head touching none of the validated paths is written
      down — in the workflow, in a comment, or in the check's own output — rather
      than left implicit in a passing run. The adjacent criterion proves it does
      not fail closed; this one proves a future reader can tell that was
      intended, which is what stops the next person from "fixing" it.
- [ ] The validated path families are **enumerated in full** from the twelve
      registered checks, and every one is either exercised by a criterion above,
      exercised by this criterion, or accompanied by the stated reason it is
      unreachable in CI. "At least one more family" is not sufficient and is
      explicitly rejected: it leaves a path-filtered remedy free to miss the
      fourth. The requirement says "the paths it validates", and every other
      criterion here instantiates that with the two families this task happened
      to be found through — documentation references and Trellis task records —
      so without the full enumeration a remedy can satisfy every criterion on
      this list and still validate a strict subset of what the preflight covers.

      At least two families are reachable and exercised by no other criterion:
      `package.json`, read by `checkPackageOverrides`
      (`scripts/sd-ai-command-pack-review-preflight.mjs:2819-2821`), and
      `.trellis/workspace/**/journal-*.md`, read by
      `checkTrellisJournalRecords` (`:3906-3912`). They are named here so the
      enumeration cannot be satisfied by re-listing the two already covered;
      they are examples of the obligation, not the whole of it.

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
- Changing `main`-push and release behaviour. `main-push-scope` enforces the
  direct-push boundary independently and `auto-tag-release` already requires a
  successful full aggregate. Reading what an existing `main` push run already
  did — which the push-base criterion above requires — is an observation, not a
  change, and is not excluded by this bullet.

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
- Widened on 2026-08-08. The task as filed described one half of the gap: the
  mode the validation is attached to. Auditing `main` for the cost of that half
  turned up four merged records violating a diff-scoped rule, and reproducing
  one of them showed the second half — the validating lane's base is the
  previous pushed head, so its diff-scoped checks never look at anything an
  earlier push already committed. Both were found the same way, by pointing an
  existing gate at content it was supposed to have covered.
- The 2026-08-08 widening was itself corrected in adversarial review before
  landing, and the corrections are worth keeping because each is a trap for the
  implementer. The first draft (a) claimed six diff-scoped failing checks when
  crossing diff basis against `fail()` capability gives three, plus journal
  validation as a hybrid; (b) listed the scope advisory as affected, when it
  reads `SD_AI_COMMAND_PACK_SCOPE_BASE_REF` and
  `SD_AI_COMMAND_PACK_FULL_CHECK_BASE_REF` rather than the preflight's base ref
  and so is untouched by this defect; (c) stated the acceptance criterion as
  "push 1 carries the defect", which cannot exercise the bookkeeping lane once
  gap 1 is fixed, because a failed predecessor routes push 2 `full` through
  `prior_success_missing`; (d) attributed all four merged records to the current
  pair when three predate the bookkeeping lane by two days; and (e) titled the
  task with an absolute "never validates" that the PRD's own repo-wide evidence
  refutes. Every one of these would have survived into an implementation that
  looked correct.
- A second review round caught two more. The rewritten acceptance criterion
  said push 2 "changes no `task.json`", which contradicts this PRD's own
  observation that the deleted child's record *is* in that diff and is skipped
  as missing; and it offered a manifest-and-spec alternative that does not
  work at all, because manifest entries are shape-validated with no existence
  check (`checkTrellisTaskContextManifests`, `:3643-3753`, contains no
  `existsSync`). The second is worth keeping visible: a manifest citing a file
  that never existed passes today in any mode, which is a distinct gap this
  task does not own. The absolute framing also needed a second pass — the
  accurate claim is the absence of a whole-pull-request coverage *guarantee*,
  not that complete coverage never happens.
- A third review round, before the widening landed, found six more. Two are
  substantive. (a) The journal check's baseline dependence is wider than
  "historical edits": `unchangedFromBaseline` also gates the
  contradictory-validation fallback rules (`:4991-5003`), and under an
  incremental base those go quiet on precisely the sessions the gap leaves
  unexamined — so the hybrid bucket's affected share was undercounted. (b) The
  claim that content merging unvalidated is "never validated, before or after"
  is false: the four repo-wide checks re-scan the tree on any run where the
  preflight executes, and on 2026-08-08 two broken references sitting on `main`
  surfaced on an unrelated branch and had to be repaired before that pull
  request could go green. The accurate statement is narrower and worse —
  detection is displaced onto whoever opens the next qualifying pull request.
  The other four were accuracy repairs: PR #365's two heads are not a controlled
  comparison (`0f4a8eb3` rewrote this PRD and its `task.json`, 105 insertions
  across two files), so the demonstration now rests on the first head alone,
  which needs no comparison; "eleven remaining reason codes" is eleven
  `select_full` call sites carrying eight distinct codes; four citations were
  off by a line or a range; and four requirements had no acceptance criterion,
  three of them satisfiable by prose alone.
- A fourth round found that the third round's own repairs had overshot in one
  direction and undershot in another, which is worth recording because both are
  easy to repeat. Conceding that repo-wide checks can catch merged content
  introduced three fresh absolutes in the opposite direction — "never revisit it
  under any circumstances", "however many times CI runs afterwards", "nothing
  downstream will look at it afterwards" — each of which ignores that a later
  diff can select the same path again. The honest claim is that revisiting is a
  coincidence of what someone edits next, not that it cannot happen. In the
  other direction, the new acceptance criterion asking for "at least one"
  additional validated path family let a path-filtered remedy satisfy every
  criterion on the list and still miss a fourth family, so it now demands the
  full enumeration; and the new push-base criterion read as requiring a change
  to `main`-push behaviour, which Out of scope excludes — it asks for an
  observation of an existing run, and the Out of scope bullet now says so.
  Separately, the context-manifest working set is wider than "changed manifest
  paths": a changed non-planning `task.json` pulls in both of its manifests
  (`:3690-3696`).
- A fifth and final round found two defects in the fourth round's own repairs,
  both of them overcorrection. The rewritten post-merge passage still said
  merged content is caught "only by the repo-wide checks" one sentence before
  conceding that a diff-scoped check can catch it too; and the tightened
  path-family criterion demanded every family be exercised by a *preceding*
  criterion, which no remedy could satisfy, because `package.json` overrides and
  journal records are reachable families that no preceding criterion touches.
  The criterion now allows itself to be the exercising one and names those two
  families as the floor. This round was the contract's last permitted review, so
  these two repairs carry host verification only and were not re-reviewed by the
  second lane — read them with that in mind.
- The remedy has to address both gaps. A fix for the mode alone leaves the
  cross-push case merging green, and would report green while doing it.
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
