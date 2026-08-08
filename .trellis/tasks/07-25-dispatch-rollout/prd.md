# Roll out dispatch protocols to sd-test-gaps, sd-update-deps, sd-fleet-refresh

Parent: `.trellis/tasks/07-25-agent-artifacts` (Tier 1 rollout). Settled inputs: parent
`design.md` section 1 and `research/cross-platform-agent-support.md`.

## Goal

Extend the validated per-unit dispatch pattern to three more commands: sd-test-gaps
(per-file test authoring), sd-update-deps (per-PR classification only), and
sd-fleet-refresh (per-repo workers inside controller waves).

## Requirements

- R1: Apply the pattern validated in 07-25-fix-ci-dispatch (capability-first prose, inline
  fallback, trust restatement, parent-owned assembly). Divergences require a recorded
  reason.
- R2: sd-test-gaps: one worker per ranked gap file (bounded by `max-gaps`); worker authors
  tests for its file only; parent re-measures coverage and owns the report.
- R3: sd-update-deps: ONLY the 4-axis per-PR classification parallelizes. Merges remain
  strictly sequential — the existing "never merge dependency PRs in parallel" rule is
  restated inside the dispatch section.
- R4: sd-fleet-refresh: workers operate per consumer repo within waves planned by the
  existing deterministic controller; the controller remains the sole owner of the campaign
  ledger and timing records; serialized housekeeping merges unchanged.
- R5: Deliberate serializations elsewhere stay untouched (sd-work-backlog task loop,
  sd-housekeeping collector).

## Acceptance Criteria

- [ ] All three command bodies carry dispatch sections; `make generate` byte-stable;
      catalog regenerated.
- [ ] sd-update-deps merge-serialization rule verifiably present in the new text.
- [ ] Fleet controller contract unchanged (scripts untouched or additively extended).
- [ ] Version bump + changelog; pattern-conformance note recorded before archive.

## Dependencies / order

- BLOCKED until 07-25-fix-ci-dispatch is completed and reviewed.

## Notes

- Medium task; per-command review of unit boundaries required. Planning complete
  2026-07-28: `design.md` and `implement.md` added.
- **The three commands are not three instances of one pattern.** They differ on the axis
  that matters — whether workers write — and R1 requires a recorded reason per divergence:

  | command | worker unit | worker writes? | serialization owner |
  |---|---|---|---|
  | sd-update-deps | one dependency PR | no | prose (`SKILL.md:78`) |
  | sd-fleet-refresh | one issued controller action | no | `fleet-controller.py` |
  | sd-test-gaps | one ranked gap file | **yes** | prose (`SKILL.md:71-72`) |

- **R2 conflicts with the sd-test-gaps skill text, and with the pattern R1 imports.**
  Verified 2026-07-28: `sd-test-gaps/SKILL.md:71-72` reads "for each of the top `max-gaps`
  files (default 3), **one file at a time**" — R2 parallelizes a step whose current text
  forbids it, which is a behavior change, not prose cleanup. And these workers **write**,
  where `07-25-fix-ci-dispatch` R2 ("workers are read-only; fixes are applied by the
  parent") and parent R6 ("read-only/limited roles") make read-only the rule. The
  divergence is justified — a read-only worker returning proposed test source makes the
  parent absorb every worker's output and cannot run the per-file implement/check loop
  (`:75-76`) — but it must be recorded in the AC4 conformance note, because
  `07-25-worker-agents` turns these protocols into capability-restricted agent
  definitions.
- **sd-test-gaps brings collision surface the read-only cases do not.** `SKILL.md:80` tells
  workers to "extend the file's existing test module when one exists", so two gap files
  targeting one module means two workers editing one file. The parent must partition by
  **target test module**, not by product file, and arbitrate fixture names (`:78`).
  `max-gaps` defaults to 3, which is what bounds the blast radius.
- **R4 understates the fleet controller: it already returns the fan-out.**
  `scripts/sd-ai-command-pack-fleet-controller.py:959` `issue_next` returns a **list** of
  actions, one per eligible lane, and `_eligible_lanes` at `:940` is where the policy
  lives — `checkout-validation` gated on the wave/canary plan (`lane["name"] in starts`)
  and `merge` gated on `lane["name"] == merge_candidate`, so **at most one merge lane is
  ever eligible**. Consequences: the dispatch unit is "one worker per action returned by a
  single `next` call", not "one worker per consumer repo" (a per-consumer framing licenses
  a worker to drive several stages, which `SKILL.md:90` forbids); merge serialization is
  enforced by code, not by the prose this task adds; and preflight (`:967-969`) plus any
  `reconcile` lane (`:971-973`) are barriers no worker can run past. R4's "scripts
  untouched" is met by touching nothing.
- **Workers must not call `next` or `record`.** Both take the campaign file lock
  (`:297`, lock path `:231`) so concurrency is safe, but a second `next` issues duplicate
  actions and `SKILL.md:118-120` rejects conflicting receipts, duplicate actions, and
  "invalid concurrent start" — with manual state edits forbidden. Parent calls `next`
  once, fans out, collects, then records.
- **R3 is the clean case and its risk reads backwards.** `sd-update-deps/SKILL.md:60`
  (4-axis classification) and `:78` (strictly sequential merge) are already a workflow
  boundary, and `:89` delegates the merge mutation out of the skill entirely. `:96` notes
  bots may rebase between classification and merge — parallel classification **narrows**
  that staleness window rather than widening it. Worth one sentence in the new text or a
  reviewer will raise it as an objection.
- **Recommended commit order is sd-update-deps → sd-fleet-refresh → sd-test-gaps**, not the
  title order: cleanest first, and the only commit that changes a serialization sentence
  last. AC4's conformance note is three entries — two conformances and one recorded
  divergence.

## Rescope (2026-08-08)

Parked; surviving scope is the sd-update-deps piece only. R4 is dropped per
this task's own notes.
