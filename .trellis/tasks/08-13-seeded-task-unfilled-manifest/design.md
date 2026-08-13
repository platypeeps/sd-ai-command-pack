# Design

## Where the rule belongs

`validateBookkeepingTaskContexts` in
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`. It already owns the
per-file loop, already receives `seedReady`, and already decides the
lone-scaffold exemption there. `findTrellisTaskContextIssues` stays untouched:
it answers "what is wrong with this row", and the new rule is a property of the
file, not of any row. Pushing a file-level verdict into a row-level function is
what produced the gap in the first place.

## Expressing "no usable row"

The loop gains two counters per file:

- `usableRows` — rows that parsed as a plain object carrying a `file` key.
- `emittedForFile` — findings this file already produced.

A row counts as usable when it has a `file` key, **even when that reference is
rejected**. A manifest whose one row cites a forbidden path is filled-but-wrong,
and the reference or self-reference finding already names the real defect;
counting it unusable would stack a second, vaguer finding on top.

The new finding fires only when `usableRows === 0` **and**
`emittedForFile === 0`. The second condition suppresses double-reporting for
the shapes that already fail loudly:

| manifest content | today | after |
| --- | --- | --- |
| lone `_example` scaffold | `task_context_seed` | `task_context_seed` (unchanged) |
| only malformed lines | `task_context_malformed` | `task_context_malformed` (unchanged) |
| one row citing its own task directory | `task_context_self_reference` | unchanged |
| emptied / whitespace only | **passes** | `task_context_unfilled` |
| only `{}` or `{"note": "..."}` rows | **passes** | `task_context_unfilled` |
| file absent | passes | passes (unchanged) |

Counting usable rows needs the parse the loop already performs, so the counter
is incremented inside the existing iteration rather than by re-reading the text.
Because `findTrellisTaskContextIssues` returns issues rather than rows, the
count is taken from a small sibling that walks the same lines and reports how
many carried a `file` key. Both walk `text.split(/\r?\n/)` with the same
blank-line skip, so they cannot disagree about what a row is.

## Why `seedReady` only

Merge time keeps its exemption. There, an unfilled manifest is indistinguishable
from a task whose manifests were never curated, and failing it produced a late
completion-time failure — the reasoning recorded at the call site of
`isPristineTrellisTaskContextScaffold`. Checkout-validation has no such ambiguity:
the stage's purpose is to assert the manifests were filled, so unfilled is the
defect. `seedReady` already encodes exactly that distinction; the new rule sits
behind the same flag rather than inventing a second one.

## Not breaking the inline-platform consumer

`if (!pathEntryExists(file)) continue;` stays. `task.py create` writes the
manifests only when `_has_subagent_platform` finds a platform anchor, so on an
inline-platform consumer their absence is correct, not a defect. The rule
therefore reads "exists and is unusable", never "must exist". An acceptance
criterion pins this directly: a seeded task with no manifests at all must still
report `seeded_task_valid`.

## Message

The finding names the file and the repair, matching the convention the other
seeding findings now follow:

```
.trellis/tasks/<dir>/check.jsonl contains no context rows; add at least one
{"file": "<spec-or-research-path>", "reason": "<why>"} row
```

The message deliberately does **not** offer "or delete the file" as a repair,
even though a deleted file passes. Advertising that would document the way
around the gate, which is exactly the mistake the existing scaffold passage
makes with "or emptied".

## Known limit: deleting both manifests still passes

Absence has to pass, because an inline-platform consumer never has these files.
So an operator who deletes both manifests defeats the stage as thoroughly as one
who empties them.

Closing that would mean the validator deciding whether the consumer *should*
have manifests, which is `_has_subagent_platform` in vendored
`task_store.py:150` — a probe of well-known config directories plus a Codex
dispatch-mode read. Two reasons not to copy it here:

1. It is Trellis-owned and changes across versions. The pack already refuses to
   match Trellis's seed *text* for this reason and matches the scaffold *shape*
   instead; copying its platform list would reintroduce exactly that coupling,
   and a stale copy fails closed against innocent consumers.
2. The threat model does not support it. This gate catches an operator's
   mistake, not an adversary. Emptying is a plausible mistake and was until now
   the documented instruction; deleting both files is neither suggested by any
   document nor a natural slip.

Recorded as a deliberate limit rather than an oversight. If a lane is ever
observed reaching review with both manifests deleted, that is the evidence that
would justify the coupling, and it belongs to a task that has it.

## Unrecognized command

`printBookkeepingResult` composes its subject by excluding `final-bundle`, so a
future command inherits a task count it never computed — the same class of bug
as the `null bundle undefined..undefined` receipt fixed in 0.71.3, one step
removed. The fix is an explicit branch over the known commands with a `throw`
on anything else.

The throw is unreachable through the CLI: `status: valid` is only produced for a
command that already passed argument validation. That is the point. It converts
"a new command silently prints a wrong subject" into "a new command fails in the
test that exercises it".

`printBookkeepingResult` is not exported and writes to the console, so no test
can reach it. Rather than export a printing function, the subject composition
moves into an exported pure `bookkeepingResultSubject(result)` that returns the
string and throws on an unknown command; `printBookkeepingResult` calls it. The
repository already tests exported validator symbols this way — the harness in
`tests/test_review_preflight.py` imports them directly from the `.mjs` — so the
test drives a synthetic result through the exported function, which argv cannot
produce.

## Documentation surfaces

`templates/docs/SD_AI_COMMAND_PACK.md` is the source; `docs/` is regenerated by
`make sync` and the plugin payload by `.github/scripts/generate-plugin.py`. All
three must agree.

`.trellis/workflow.md` is **not** a pack surface — it ships with vendored
Trellis and `manifest.json` does not list it. Its prose ready gate stays where
it is; the pack documents its own mechanical stage instead. Editing a vendored
file here would be overwritten on the consumer's next Trellis update and would
put a pack rule in someone else's document.

Three statements land in the pack doc: what `seeded-task` rejects; that a
generated `TBD` PRD placeholder is grounds for rejection; and that the
default-branch override variable outranks the consumer's own `origin/HEAD` under
`--repo`, with `evidence.defaultBranchSource` recording which one answered.

A fourth edit is a correction, not an addition. The existing scaffold passage
says the scaffold "must be replaced or emptied before the task leaves planning".
That sentence is the documented route into the defect this task closes. It stays
true of the merge-time lane and becomes false at `seeded-task`, so the passage
gains the distinction instead of losing the sentence: emptying satisfies the
diff-scoped gate and the merge-time validator, and fails `seeded-task`, which
requires a real row. The paragraph is the one place both lanes are already
described together, so the correction belongs there rather than in a new
section. The
variable is named literally in the doc — the SKILL.md prohibition on the
`SD_AI_COMMAND_PACK_` prefix is enforced by `tests/test_sdlc_commands.py`
against skill files only, not documentation.

## Shipped-surface propagation

`templates/scripts/X` is the source. `scripts/X` is the dogfood install
regenerated by `make sync`; `plugins/sd/bin/X` and
`plugins/sd/machine-payload/scripts/X` by `generate-plugin.py`, which `make
sync` does not run; `docs/fleet/candidate-validation.json` carries the payload
digest regenerated by the fleet candidate check. `prepare-release.py` closes the
version transition. Skipping any one of them fails CI's release payload gate
rather than local `sd-check`, which does not contain that gate.

## Rollback

One commit range on a task branch, no migration, no persisted state. Reverting
restores 0.71.3 behaviour exactly: the new finding is additive and the
documentation is additive. The fleet campaign is already paused, so a revert
costs nothing beyond re-deciding the blocker.
