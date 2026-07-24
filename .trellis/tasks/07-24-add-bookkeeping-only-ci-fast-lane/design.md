# Design: bookkeeping-only CI fast lane

## Design Summary

Keep one exact-head aggregate check, but precede expensive jobs with a
fail-closed scope job. The scope job proves whether the event is a linear,
bookkeeping-only successor of a previously successful head for the same PR or
protected branch. When proven, that same job runs cheap metadata validations
and selects `bookkeeping`; otherwise it selects `full`. Existing expensive jobs
become mode-conditional, and `CI Result` evaluates the appropriate lane set.

## Components

### Scope classifier

Add a small tested helper under `.github/scripts/` with a versioned JSON result
and a thin GitHub Actions adapter. Keep Git history classification separate from
API evidence parsing so both can be exercised with temporary repositories and
saved API fixtures.

The workflow writes `full` as its bootstrap default, then materializes and runs
the classifier from the exact before SHA rather than from the changed checkout.
If that prior-head helper is absent or cannot be validated, the decision stays
full. This makes the first implementation head full, lets its later
finish-work-only successor use the newly green helper, and ensures a future PR
that modifies the classifier is judged by the previously green version. Only
after that helper proves the delta contains no executable changes may the job
run current-head bookkeeping validators, which are then byte-identical to the
prior-head versions.

Inputs:

- event name and action;
- repository, workflow, PR number or protected ref;
- event-supplied before and after full SHAs;
- fetched Git objects for those SHAs;
- read-only GitHub Actions/check evidence for the before SHA.

Output shape:

```json
{
  "schemaVersion": 1,
  "mode": "bookkeeping",
  "reason": "verified_bookkeeping_successor",
  "beforeSha": "<40-char sha>",
  "afterSha": "<40-char sha>",
  "evidenceRunId": 123456,
  "evidenceScope": "pull_request:243"
}
```

`full` is the default result. Expected uncertainty—unsupported event action,
missing prior success, API unavailability, non-linear history, or an unapproved
path—returns a successful `full` decision with a stable reason. A malformed
contract or internal classifier failure is not converted to bookkeeping
success.

### History and path proof

For PR synchronize events, use the event's `before` value as the previously
published PR head and the event's current head SHA as `after`; do not assume
`HEAD^` is the previous PR head because finish-work can create archive and
journal commits locally before one push. For direct `main` pushes, use the push
event's before/after pair.

Verify:

1. both identities are full commit SHAs and exist locally;
2. before is an ancestor of after;
3. every intervening commit is linear and contains no merge parent;
4. `git diff --no-renames --name-only -z before after --` contains at least one
   path and every path is below `.trellis/tasks/` or `.trellis/workspace/`;
5. changed tree entries are regular, non-executable files, with no symlink or
   submodule modes and no disallowed type transition.

Using `--no-renames` deliberately supports a legitimate task archive by
validating both old and new paths independently instead of trusting rename
detection.

### Prior-head evidence

Query read-only GitHub workflow data for a completed successful `Tests` run on
the exact before SHA. For PRs, require association with the same PR number and
pull-request event; for main, require the protected main ref/push lineage. A
successful prior bookkeeping run is acceptable because each current run still
validates its own bounded delta and produces a new exact-head aggregate result.

Do not accept a same-named check from another PR/ref, a cancelled/in-progress
run, or a result whose repository/workflow identity is ambiguous. Use minimum
`actions: read`, `contents: read`, and, only if the chosen API requires it,
`pull-requests: read` permissions.

### Bookkeeping validation

After the history/path proof and prior evidence pass, check out the after head
and run the canonical validator published by
`07-24-validate-finish-work-bookkeeping-before-push` for task layout/topology,
context manifests, descriptions, lifecycle state, journal/index consistency,
placeholders, and whitespace. Accept its explicit completion or planning
finalization mode; mode selection remains owned by
`07-24-support-planning-only-pr-finalization`. Keep history/tree-mode
classification in this task rather than duplicating it in the bookkeeping
validator. The prior-head classifier has already proved that these helpers are
unchanged across a selected bookkeeping delta, so no changed checkout-owned
executable is run to decide eligibility.

### Workflow fan-out and aggregate

Add a first `ci-scope` job. It publishes `mode` and reason outputs and, for
bookkeeping mode, completes the cheap validation in the same runner. Condition
`unittest`, `lint`, `security`, and the PR release-payload gate on `mode ==
'full'`. Keep `main-push-scope` for main events because it enforces the direct
push boundary independently.

Keep the required job name exactly `CI Result`. Its script checks:

- `ci-scope` succeeded and returned a recognized schema/mode;
- full mode: all expensive jobs succeeded and bookkeeping-only outcomes are
  not being substituted;
- bookkeeping mode: the scope/metadata job succeeded and every expensive job
  is skipped;
- event-specific main/release jobs have only their permitted success/skipped
  states.

Actual main merge/release updates select full mode. `auto-tag-release` remains
dependent on a successful full aggregate and does not run for direct
bookkeeping-only pushes.

## Finish-work Interaction

The finalization skills create a completion archive/journal bundle or a
planning task/journal bundle locally and push after finalization completes.
Preserve that single-push boundary. A later review fix may legitimately require
a new finalization attempt and another bookkeeping successor; the fast lane
makes that new exact head cheap without pretending the older head is current.

Do not combine archive and journal into one commit merely to optimize Actions:
multiple local commits in one push create one evaluated PR head. If inspection
finds a path that pushes between those commits, fix that path to defer its push
until finalization completes.

## Compatibility And Rollout

- The required check name does not change, so branch protection needs no
  migration.
- The first code-bearing head that introduces the classifier and consumes the
  canonical bookkeeping validator runs full CI. Its
  later finish-work-only successor can dogfood the fast lane because the
  classifier/workflow are unchanged from the green prior head.
- Keep `cancel-in-progress` behavior for superseded PR heads.
- Rollback is a workflow-only revert that removes mode conditions and restores
  unconditional expensive lanes; it must not alter Trellis archives or review
  receipts.

## Trade-offs

- A scope job adds a small fixed cost to full runs, but eliminates several
  dependency-installing runners from validated bookkeeping successors.
- A broad path ignore would be cheaper but cannot produce the exact-head
  required result or validate malformed task metadata, so it is rejected.
- Requiring only the immediately preceding Git parent to have CI would reject
  the normal multi-commit, one-push finish-work shape. Event-supplied prior-head
  evidence preserves safety without forcing history rewriting.
