# task-context manifest lane passes when its selection rule inspected nothing

## Goal

Stop the Trellis task-context manifest lane from reporting success for a
repository whose manifests it structurally cannot reach, so a green preflight
means the manifests were checked rather than skipped.

## Problem

The lane in `templates/scripts/sd-ai-command-pack-review-preflight.mjs` ends
with (`:3738-3743`):

```js
if (inspectedFiles === 0) {
  if (failures.length === failureStart) {
    pass('no changed Trellis task context manifests require validation.');
  }
  return;
}
```

That `pass` is emitted whether the changed set genuinely held no manifests, or
the lane's own selection rule excluded every manifest in the repository. Both
render as green, and the second is reachable indefinitely.

A task's manifests enter `contextFiles` only when either the manifest file
itself is in the changed set (`:3675`), or its `task.json` changed **and**
(`:3691-3695`):

```js
if (
  isPlainObject(record) &&
  TRELLIS_TASK_STATUSES.has(record.status) &&
  record.status !== 'planning'
) {
  contextFiles.add(`${artifact.taskDir}/implement.jsonl`);
  contextFiles.add(`${artifact.taskDir}/check.jsonl`);
}
```

So a manifest owned by a task that stays in `planning` is never inspected
unless someone edits that manifest. Nothing else in the repository can bring it
into scope.

## Problem, observed

`platypeeps/hoa-manager` currently holds **20** manifests — 10 parked parent
tasks x `implement.jsonl` + `check.jsonl` — in which *both* entries violate
this lane's own root rule (`isTrellisTaskContextReference`, `:3891-3895`, which
admits `.trellis/spec/**` and `.trellis/tasks/**/research/**` only):

```text
{"file":".trellis/tasks/07-09-roadmap-trellis-consolidation/prd.md", ...}
{"file":"docs/ARCHITECTURE.md", ...}
```

Both lines are byte-identical across all 20 files. The first also points at a
directory that no longer exists — that task was archived to
`.trellis/tasks/archive/2026-07/` — so it is a dead path as well as a
disallowed root.

Every one of the 10 owning tasks is status `planning`, so the second selection
branch never fires. Those 20 files are **20 of that repository's 28 populated
manifest files (71%)**, and this lane has reported green on every pull request
throughout.

## Not confined to one consumer, and not a stale-install artifact

`platypeeps/loadsmith` carries the same shape at pack **0.64.27** — the current
target, fully refreshed:

```text
.trellis/tasks/07-20-release-compatibility-riders/check.jsonl:1
{"file":".trellis/tasks/07-20-release-compatibility-riders/prd.md",
 "reason":"Acceptance criteria for compatibility gates and shim removal."}
```

`.trellis/tasks/**` admits only `research/**`, so a task's own `prd.md` is out
of root. That task is status `planning`, so the same selection branch never
fires and the lane reports green there too.

Two consumers, one on an old pack and one fully current, both carrying invalid
manifests the gate structurally cannot see. A fleet sweep of the other six
repositories found no further instances, which is consistent with the mechanism:
the violations survive only where nobody has since edited the manifest.

## Why it matters beyond the one consumer

The failure mode is self-concealing. The population this lane misses is exactly
the population that accumulates: manifests nobody edits, in tasks nobody
starts. Manifests under active work are touched and therefore checked, so the
lane looks reliable precisely where it is not needed.

`no changed Trellis task context manifests require validation.` is literally
true and operationally useless — indistinguishable from "this lane is working."
The neighbouring success message is careful to report its denominator:

```js
`checked ${inspectedFiles} changed Trellis task context file(s) for ...`
```

That denominator is what the zero case drops.

## Requirements

### Functional

- A green result from this lane must distinguish "no manifests exist to check"
  from "manifests exist but the selection rule excluded all of them."
- Manifests already invalid before any change is made to them must be reachable
  by the gate. A repository must not be able to carry invalid manifests
  indefinitely while the lane reports green.
- Reference and JSONL validity must not depend on the owning task's lifecycle
  status. A hand-authored manifest is checkable whether or not the task has
  left `planning`.

### Non-functional

- The pristine `_example` scaffold exemption must keep working, so creating a
  task never fails the gate.
- No change to what counts as a permitted root.
- Any repo-wide read must stay bounded and must not make the common
  delta-scoped path materially slower.

## Open questions

1. Should the lane read outside the change delta at all? Every other preflight
   lane is delta-scoped; a repo-wide sweep would be the first exception, and
   that is a scope decision for the pack rather than a mechanical fix.
2. If a sweep is added, is it unconditional or behind a flag? Unconditional
   turns 20 pre-existing violations into a hard failure on the next unrelated
   pull request in any repository carrying them.
3. Is dropping `record.status !== 'planning'` sufficient on its own? It is
   narrower and cheaper, but it still cannot see a task nobody touches.

## Acceptance Criteria

- [ ] A repository containing an invalid manifest cannot produce a green result
      from this lane, regardless of whether that manifest is in the change set
- [ ] The zero-inspected message names why nothing was inspected, and is
      distinguishable from a genuine no-manifests-exist repository
- [ ] A test fixture with an invalid manifest owned by a `planning` task fails
      the lane
- [ ] Pristine `_example` scaffolds still pass
- [ ] Open questions 1 and 2 are answered in `design.md` with a decision and a
      migration note for repositories that already carry violations

## Notes

Filed 2026-08-07. Reproducible on pack source `main` @ `4378d37b` (0.64.27) at
`:3738` / `:3691`; same logic in installed 0.64.3 at `:3736` / `:3688`. Not a
stale-install artifact.

`scripts/sd-ai-command-pack-review-preflight.mjs` and its `templates/scripts/`
mirror are byte-identical today, so the line references above hold in both. Per
`.trellis/spec/tooling/index.md` the fix must land in both and the mirrors must
still `diff` clean afterward.

Related but distinct: `preflight-bare-filename-references` covers *what* a
reference may say. This covers *whether the check runs at all*.
