# Design — roll out dispatch protocols to sd-test-gaps, sd-update-deps, sd-fleet-refresh

## Scope boundary

Prose in three skill bodies, one commit each. No script changes. R4 says the
fleet controller stays the sole owner of the campaign ledger — that is stronger
than "scripts untouched": the controller *already* implements the concurrency
model this task is documenting, so touching it would be redoing work that
exists.

Blocked on `07-25-fix-ci-dispatch`. That task's design settles three things
this one inherits: where the section goes (skill body, not the 16-line command
source), how trust is restated (carry the command-resolved state forward; do
not copy the generator-owned classifier), and the read-only-worker rule.

The three commands are **not** three instances of one pattern. They differ on
the single axis that matters — whether workers write — and R1 requires a
recorded reason for each divergence. Reasons are below.

| command | worker unit | worker writes? | serialization owner |
|---|---|---|---|
| sd-update-deps | one dependency PR | no | prose (`SKILL.md:78`) |
| sd-fleet-refresh | one issued controller action | no | `fleet-controller.py` |
| sd-test-gaps | one ranked gap file | **yes** | prose (`SKILL.md:71-72`) |

## sd-update-deps — the clean case. Land first.

The workflow already has the boundary R3 wants. `SKILL.md:60` is "Classify
every dependency PR on four axes"; `SKILL.md:78` is "Process the auto-merge
class strictly sequentially, one PR at a time". Step 4 (`dry-run`) stops
between them. Classification is a pure read pass over independent PRs; merging
is a strictly ordered mutation pass. Dispatch step 2, leave step 5 alone.

Merge authority is already delegated out of this skill: `SKILL.md:89` routes
the mutation to the installed housekeeping owner via
`gh pr merge --match-head-commit` and says "Do not reconstruct checks, thread,
head, or mergeability logic in this skill." A classification worker touching
any of that is out of contract twice over.

One thing worth stating in the prose because it reads backwards: `SKILL.md:96`
notes dependency bots may rebase when the default branch moves, so an
eligibility judgement can go stale between classification and merge.
Parallelizing classification **narrows** that window rather than widening it —
it is an argument for the change, not a risk of it. Say so, or a reviewer will
raise it as an objection.

R3's requirement that the merge-serialization rule be restated *inside* the
dispatch section is the right call and is the one AC that is mechanically
checkable.

## sd-fleet-refresh — the controller already returns the fan-out

R4 describes "workers per consumer repo within waves planned by the existing
deterministic controller". Measured, the controller is more specific than that,
and the prose should match it exactly.

`issue_next` (`scripts/sd-ai-command-pack-fleet-controller.py:959`) returns a
**list** of actions, one per eligible lane, and sets `lane["issuedAction"]` and
`lane["status"] = "issued"` for each. `_eligible_lanes` (`:940`) is where the
policy lives:

```python
if lane["stage"] == "checkout-validation":
    if not _current_attempt_receipts(lane) and lane["name"] in starts:
        eligible.append(lane)
    continue
if lane["stage"] == "merge":
    if lane["name"] == merge_candidate:
        eligible.append(lane)
    continue
eligible.append(lane)
```

Three consequences:

1. **The dispatch unit is "one worker per action returned by a single `next`
   call", not "one worker per consumer repo."** The returned list already
   encodes the wave/canary policy (`plan["canStart"]`) and the stage each
   consumer is at. A per-consumer framing invites a worker to drive a consumer
   through several stages, which is exactly what "Drive work only from issued
   actions" (`SKILL.md:90`) forbids.
2. **Merge serialization is enforced by code, not prose.** At most one lane in
   `merge` stage is ever eligible — `lane["name"] == merge_candidate`. R4's
   "serialized housekeeping merges unchanged" is a property of
   `_eligible_lanes`, not something the dispatch section needs to promise.
3. **Preflight is a campaign-wide barrier.** `issue_next` returns early unless
   `preflight["status"] == "passed"` (`:967-969`), and any lane in `reconcile`
   sets the campaign to `blocked` and returns nothing (`:971-973`). No worker
   can run ahead of either gate.

**Workers must not call `next` or `record`.** Both go through the campaign file
lock (`:297 locked()`, lock at `:231`), so concurrent calls serialize anyway —
but a second `next` would issue duplicate actions, and `SKILL.md:118-120` says
a conflicting receipt, duplicate action, or "invalid concurrent start" is
rejected. The parent calls `next` once, fans out the returned actions, collects
one result per worker, then calls `record` per result. That keeps the
controller's single-writer invariant intact and is also why R4's "controller
remains the sole owner of the campaign ledger" is satisfiable without any code
change.

One wrinkle to note rather than solve: `checkout-validation` creates and
activates "one dedicated lightweight Trellis task for this consumer"
(`SKILL.md:134`). That task lives in the *consumer's* checkout, so parallel
workers do not contend for one `task.py current` — but the `Active task:`
dispatch prefix inherited from `07-25-fix-ci-dispatch` refers to the *source*
repo's task. Two different task contexts in one prompt. State which is which.

## sd-test-gaps — the divergence, and it is the whole task's risk

R2 asks for "one worker per ranked gap file (bounded by `max-gaps`); worker
authors tests for its file only". Two conflicts, neither flagged in the PRD.

**Conflict 1: the skill explicitly serializes this step.** `SKILL.md:71-72` —
"**Author** — for each of the top `max-gaps` files (default 3), **one file at a
time**". The rollout parallelizes a step whose current text forbids it. That
text has to change, and changing it is a behavior decision, not prose cleanup.

**Conflict 2: these workers write.** Every other worker in this program is
read-only. `07-25-fix-ci-dispatch` R2 — "Workers are read-only; fixes are
applied by the parent" — is the load-bearing constraint of the pattern R1 says
to apply, and R6 of the parent task (`07-25-agent-artifacts`) says the first
named agents are "read-only/limited roles … not general-purpose workers".
sd-test-gaps workers author test files.

R1 says divergences require a recorded reason. The reason is that the
alternative is worse: a read-only worker that returns proposed test source for
the parent to write means the parent absorbs every worker's full test output,
which defeats the point, and the parent cannot run the per-file
implement/check loop the skill requires (`SKILL.md:75-76`) without the files
existing. So writing workers are the right call here — but the divergence must
be written down, and it brings collision surface the read-only cases do not
have:

- **Shared test modules.** `SKILL.md:80` — "extend the file's existing test
  module when one exists." Two gap files whose tests belong in the same module
  produce two workers editing one file. The parent must partition by *target
  test module*, not by product file, or serialize any group that collides.
- **Shared fixtures.** `SKILL.md:78` — "Add fixtures only when the new tests
  need them." Two workers can add the same fixture with different shapes, or
  the same name with different content.
- **Bounded blast radius.** `max-gaps` defaults to 3, so the realistic fan-out
  is 3 writers. That is what makes the risk tolerable — it is not a
  hundred-worker mutation fan-out.

Parent keeps: baseline (`SKILL.md:58`, abort-on-red), ranking (`:66`),
re-measure (`:81-84`, including "no other file regressed" — a global property
no single worker can assert), and the report. `file=<path>` short-circuits the
ranking and yields exactly one unit, so it degenerates to today's flow.

## Contract

Common to all three, inherited from `07-25-fix-ci-dispatch`:

- capability-first phrasing with the inline sequential fallback
- `Active task: <path>` prefix when a Trellis task is active
- one line carrying the command's resolved `checkout-trust: <state> (<reason-code>)`;
  workers do not reclassify
- parent owns assembly, mutation of shared state, and the final report
- report contracts unchanged in all three commands

Per-command divergence, recorded per R1:

- sd-update-deps: none.
- sd-fleet-refresh: the unit is a controller-issued action, not a repo; workers
  never call `next`/`record`.
- sd-test-gaps: **workers write files.** Reason above. Requires parent-side
  partitioning by target test module.

## Compatibility

R5 holds without effort: sd-work-backlog's task loop and sd-housekeeping's
final-state collection are not touched by this task and no dispatch section is
added to either.

All three report contracts stay as they are — `sd-test-gaps` per-gap
before/after table (`SKILL.md:116`), `sd-update-deps` per-PR classification,
`sd-fleet-refresh` receipts and campaign status. Dispatch changes production,
not shape.

Inline platforms produce today's behavior in all three, which is what makes
this shippable ahead of the Tier 2 agent artifacts.

## Rollout and rollback

Three commits, in this order: sd-update-deps (clean, proves the copied
pattern), sd-fleet-refresh (documents an existing code contract, adds no new
concurrency), sd-test-gaps (the only one that changes serialization and lets
workers write). Each is `make generate` + catalog + changelog + version.

Every commit reverts cleanly on its own — the sections are additive prose over
paths that still work sequentially. sd-test-gaps is the exception in one
direction: reverting it restores "one file at a time", so any in-flight
parallel run must finish or be discarded first.

Record the pattern-conformance note (AC4) as three entries, not one — the
sd-test-gaps entry is a recorded divergence, not a conformance.

## Risk

1. **sd-test-gaps workers colliding on a shared test module or fixture.** The
   only mutating fan-out in the program, and `SKILL.md:80` actively encourages
   the collision by telling workers to extend existing modules.
2. **sd-fleet-refresh prose framed per consumer instead of per issued action.**
   Reads harmless; licenses a worker to drive a consumer through multiple
   stages and breaks the single-writer receipt model.
3. **A worker calling `next` or `record`.** The lock prevents corruption but
   not duplicate issuance; the controller then rejects the receipt and the
   campaign needs manual reconciliation — with `SKILL.md:120` forbidding manual
   state edits.
4. **Copying the pattern before `07-25-fix-ci-dispatch` is reviewed.** Both
   PRDs state the ordering. Three more bodies carrying a wrong shape is the
   cost.
5. **sd-update-deps.** Low. The workflow boundary already exists and the merge
   path is delegated out of the skill.
