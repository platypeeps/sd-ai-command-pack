# Design — branch-field finalization deadlock

## Decision 1: fix the ordering *and* the comparison — both are required

The PRD requires picking one of two resolutions for the pre-archive stop. An
earlier draft of this design picked neither: it changed only the comparison at
`:1502` and asserted the stop was resolved by consequence. That was wrong, and
the reason is worth stating because it is the whole shape of the defect.

`sd-finish-work/SKILL.md:60-64` is unambiguous about what a compliant run does
when the pre-archive gate returns `invalid`:

> A missing helper, malformed/unsupported result, nonzero exit, `invalid`, or
> `indeterminate` result stops before `task.py archive`, journal creation,
> staging, or commit. Report its stable reason codes and exact repo-relative
> paths; do not attempt a repair by mutating the task.

So a compliant run **never reaches the bundle gate**. It halts at `:700` with
`task_branch_invalid` and has no sanctioned exit at all. The comparison fix
alone would only help an operator who deviates from step 4 — which is what
happened in the live incident, and is not a contract anyone should rely on.
AC 3 is unreachable without changing the ordering.

**Both changes ship:**

1. **Ordering (prevention).** `sd-finish-work` step 4 gains an explicit
   instruction: when the selected task's `branch` is null, record it with
   `task.py set-branch` and commit it as a scoped branch-metadata commit
   *before* capturing the finalization base — not a "work commit", which
   `trellis-finish-work` reserves for pre-invocation Phase 3.4 code commits
   (`:8`, `:69`). The branch is then present in the source record at
   `baseOid`, the archive move changes only `status` and `completedAt`, and
   both gates pass with no exception needed. This is what the 7-of-8 archived
   tasks that carry a branch did by luck of ordering; it becomes a contract.
2. **Comparison (recovery).** The `:1496-1504` tolerance below. Prevention
   helps a run that has not started; it does nothing for a run already past
   base capture, and step 7 forbids amending or dropping the archive and
   journal commits. Without the tolerance the only exit stays a hand-authored
   correction commit against an archived artifact.

Consequence: `templates/.agents/skills/sd-finish-work/SKILL.md` **is** in
scope, and both mirrored pairs regenerate. The earlier draft avoided this to
keep the change small; a smaller diff that leaves an acceptance criterion
unmet is not smaller, it is incomplete.

### Why not relax `task_branch_invalid` instead

The PRD's other option — stop firing `:700` when the branch is inferable from
the current checkout — is rejected, but not for the reason an earlier draft
gave. That draft claimed a detached-HEAD CI recompute would break eligibility.
That story is false and is retracted: the supported caller refuses a detached
HEAD before eligibility is ever reached
(`sd-ai-command-pack-housekeeping.sh:929-931` adds a `detached_head` anomaly
and returns), and it contradicted this design's own statement that producer and
consumer share one checkout.

The real reason is reproducibility. Both gates compare **committed content**:
the source blob at `baseOid` against the archived blob at head. A verdict
derived from live git state instead — `bookkeepingRepositoryEvidence()` reads
`git symbolic-ref --quiet --short HEAD` and stores `branch || null`
(`:1067-1090`) — could no longer be reproduced from the two commits alone. That
matters concretely because `pr-eligibility.py:345-419` re-runs the validator and
compares the entire recomputed document against the receipt: any input that is
not the commits themselves is a way for the two runs to legitimately disagree.
Today the only such input is guarded by a precondition in a *different* script.
Adding more runtime-state dependence would deepen a coupling that is already
the fragile part of the design, so the gates stay content-only.

## Decision 2: asymmetric, not unconditional

Adding `branch` to the stripped set unconditionally would also stop the gate
from catching a branch being **rewritten** or **erased** during an archive move,
which is exactly the smuggling the check exists to prevent.

Tolerate one transition and no other:

| source (at base) | archived (at head) | verdict |
|---|---|---|
| `null` | non-empty string | **allowed** — late record of a fact |
| `null` | `null` | allowed — unchanged, as today |
| absent | anything different | blocked — see below |
| `"x"` | `"y"` | blocked — rewrite |
| `"x"` | `null` | blocked — erasure of a recorded fact |
| `"x"` | `"x"` | allowed — unchanged, as today |
| any | `""` / whitespace | blocked — `:2545` already rejects empty strings |

**The exception tests `=== null` only, not `== null`.** An absent `branch` key
is a distinct state from an explicit `null`: `:2545` guards with
`record.branch !== null && record.branch !== undefined`, so metadata validation
tolerates an absent key, but `task_store.py:324` seeds every Trellis-created
task with an explicit `"branch": None`. A record reaching this gate with the
key absent was not produced by `task.py` and is outside the deadlock this task
exists to fix. Widening the exception to cover it would license adding a field
to a foreign record during an archive move for no benefit.

## Implementation shape

`scripts/sd-ai-command-pack-review-preflight.mjs:1496-1504`. `stripLifecycle`
currently returns `stableJson` directly; it must return the object so the
conditional deletion can apply before serialization.

```js
const stripLifecycle = (record) => {
  const copy = { ...record };
  delete copy.status;
  delete copy.completedAt;
  return copy;
};
const sourceRecord = stripLifecycle(source);
const archivedRecord = stripLifecycle(archived);
// The pre-archive gate at :700 requires a completion-ready task to carry a
// non-empty branch. An operator who satisfies it after the finalization base
// is captured lands that write inside the archive commit, where this
// comparison would otherwise read it as smuggled content. Tolerate exactly
// that transition -- a rewrite or an erasure still fails.
const branchNewlyRecorded =
  sourceRecord.branch === null &&
  typeof archivedRecord.branch === 'string' &&
  archivedRecord.branch.trim().length > 0;
if (branchNewlyRecorded) {
  delete sourceRecord.branch;
  delete archivedRecord.branch;
}
if (stableJson(sourceRecord) !== stableJson(archivedRecord)) {
  add('completion_archive_identity_changed', `${mapping.archiveDir}/task.json`,
      'archive move changed fields other than status, completedAt, and a newly recorded branch');
}
```

The message text changes because the old text would be actively misleading
about what the gate now permits.

## Contracts and compatibility

- **No schema change.** `schemaVersion` stays 1, so
  `sd-ai-command-pack-pr-eligibility.py:224`'s exact-version check and
  `sd-finish-work/SKILL.md:127`'s "Require schema version 1" both hold.
- **No new reason code and no change to the valid-result shape.** A bundle that
  previously failed now returns `completion_bundle_valid` with `findings: []`,
  which is what `pr-eligibility.py:250-252` already requires. `:246`'s
  `reasonCodes == [f"{mode}_bundle_valid"]` check is unaffected.
- **Eligibility recomputation stays consistent.** `pr-eligibility.py:352-365`
  re-invokes the validator with the receipt's own mode/base/head and compares
  the recomputed document. Producer and consumer are the same file in the same
  checkout, so both sides move together. There is no window where a receipt
  produced by the fixed validator is re-checked by the old one within a single
  checkout; skew is only possible across pack versions, which the existing
  version gates already govern.
- **Existing archived records stay valid.** `branch: null` remains permitted at
  `:2545`; nothing forces a non-null archived branch.
- **The bundle gate never demanded a branch on either side.** `:1490` validates
  the source record with `completionReady = false`, and the archived record is
  checked the same way. Only the pre-archive gate demands one. Tolerating the
  transition therefore contradicts nothing inside this gate — it removes an
  interaction the gate never intended to police.

## Alternatives considered and declined

- **Relax `task_branch_invalid`.** Discards provenance, and makes the verdict
  checkout-dependent in a way that breaks eligibility recomputation. Declined
  with evidence under Decision 1.
- **Add `branch` to the unconditional strip set.** One line simpler, but blinds
  the gate to rewrites and erasures. Declined under Decision 2.
- **Ship only the ordering instruction, without the comparison change.** It
  prevents the deadlock for runs that have not started, but offers nothing to a
  run already past base capture — and step 7 forbids amending or dropping the
  archive and journal commits, so that run's only exit stays a hand-authored
  correction commit. Declined; both halves ship.
- **Tie the exception to the checked-out branch.** Requiring the newly recorded
  `branch` to equal `evidence.repository.branch` would stop an operator writing
  a false branch name. Declined for the reproducibility reason above — it makes
  a content comparison depend on live git state — and because the value is
  legitimately absent or different on the historical-successor path
  (`sd-finish-work/SKILL.md:68-72`), where finalization continues with no active
  task. The fabrication vector also predates this change and is strictly wider
  today: nothing stops a false branch name being written *before* base capture,
  where no gate examines it at all. Parked to the upstream fix below rather than
  solved here.
- **Have `task.py start` record the branch.** The true root cause
  (`task_store.py:324` seeds `None`, `:296-298` records the checkout branch as
  `base_branch` instead). It would also close the fabrication gap, since the
  value would come from the checkout rather than from an operator's typing.
  But `task_store.py` is Trellis-owned and out of pack scope. Worth a parked
  upstream task; does not belong here.

## Risk and rollback

Single function plus one skill step, no state, no migration. Rollback is
restoring the two-line `stripLifecycle`, the original message string, and the
prior step 4 text. The blast radius is one
reason code that today has **zero** regression coverage — `grep` finds
`completion_archive_identity_changed` only at its emit site, never in
`tests/test_bookkeeping_validator.py` — so this task adds the first tests for
it in either direction.
