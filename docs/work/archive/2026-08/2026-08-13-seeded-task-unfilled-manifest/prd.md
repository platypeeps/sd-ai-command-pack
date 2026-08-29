---
title: Seeded-task gate accepts an unfilled context manifest
status: done
created: 2026-08-13
branch: task/seeded-task-unfilled-manifest
---
# Seeded-task gate accepts an unfilled context manifest

## Goal

The `seeded-task` stage shipped in 0.71.3 exists to assert, mechanically, that
a freshly created consumer task was actually filled in. It does not: a manifest
that was **emptied** rather than filled passes it. Close that hole, carry the
three findings deferred alongside it, and cut 0.71.4 so the blocked fleet
campaign can resume.

## How this surfaced

Campaign `refresh-0.71.3-20260813T163232Z`, canary `rwbp-coordinator`,
`local-checks`. The consumer's own gate ran Prism over the newly installed pack
and reported it. `sd-ai-command-pack-fleet-finding-classify.py` rated the
manifest gap `correctness`, which is a released-pack blocker, and returned
`pause-corrective-release`. The lane is terminal with blocker
`seeded-task-empty-manifest-gap`; seven consumers never started.

The gate did work on that same lane before stopping: it caught the
`base_branch` defect live, exactly as designed. This task is about the hole
next to it, not a retreat from the gate.

## Classifier ledger

| ID | Contract family | Evidence | Severity | Disposition | Fix | Regression |
| --- | --- | --- | --- | --- | --- | --- |
| `prism-empty-manifest-passes-seeded-gate` | correctness | `findTrellisTaskContextIssues` skips blank lines and only emits per-row defects; a manifest with no usable row yields no findings | blocker | block-corrective-release | requirement 1 | a seeded task whose manifest is emptied fails `seeded-task` |
| `prism-unknown-command-subject-hardening` | hardening | `printBookkeepingResult` composes its subject by excluding `final-bundle`; an unrecognized command silently reports a task count | deferred | defer-follow-up | requirement 2 | an unknown command fails loudly rather than printing a plausible subject |
| `prism-default-branch-env-undocumented` | documentation | the default-branch override variable outranks the consumer's `origin/HEAD` under `--repo`; that precedence appears in no operator-facing doc | deferred | defer-follow-up | requirement 3 | doc names the variable, its precedence, and the evidence field that records which answered |
| `prism-seeded-task-mode-undocumented` | documentation | `seeded-task` and the PRD placeholder ban are described only in `sd-fleet-refresh` SKILL.md | deferred | defer-follow-up | requirement 3 | doc describes the mode where an operator would look for it |

Refuted during triage, deliberately not carried: that an `indeterminate`
base-branch result fails to block (it blocks — SKILL.md requires
`status: valid`, and `indeterminate` is not `valid`); that no tests were added
(97 exist in `tests/test_bookkeeping_validator.py`, which consumers never
receive); and a speculative claim about dynamically constructed context
references with no cited path.

## The defect

`validateBookkeepingTaskContexts` reports defects **per row**, and
`findTrellisTaskContextIssues` reaches a row only when the line is non-blank.
The lone-`_example` scaffold is the single unfilled shape `seedReady` turns
off. Three shapes therefore pass a stage whose entire claim is that the
manifests were filled:

1. **Emptied** — the operator deletes the scaffold row instead of replacing it.
   Zero non-blank lines, zero findings.
2. **Whitespace-only** — same, with blank lines left behind.
3. **Rows carrying no `file` key** — `{}` or `{"note": "later"}` parse as JSON,
   match neither the `_example` branch nor the `file` branch, and produce
   nothing.

Shape 3 is not in the original report. It has the same root cause: "this
manifest contains no usable row" is not a property of any row, so a per-row
rule cannot express it.

## The documentation makes it worse

`templates/docs/SD_AI_COMMAND_PACK.md` tells operators the generated scaffold
"must be replaced or emptied before the task leaves planning" — emptying
presented as a sanctioned alternative to filling. So the pack does not merely
fail to catch shape 1 — it documents it as an approved path.

That is correct for the merge-time lane, where the exemption exists precisely
because an unfilled manifest cannot be told apart from an uncurated one. It is
wrong for a seeded consumer task, where the whole point of the stage is that
the manifests were filled. The documentation has to draw that line rather than
offer one instruction for two lanes with opposite requirements.

## The case that must not break

A **missing** manifest is not the same defect. `task.py create` seeds
`implement.jsonl` / `check.jsonl` only when `_has_subagent_platform` finds a
platform anchor; on an inline-platform consumer they are never written at all.
`validateBookkeepingTaskContexts` skips a path that does not exist, and that
skip is correct. A rule that demands presence unconditionally would fail every
inline-platform consumer for doing nothing wrong.

So the requirement is about a manifest that **exists and is unusable**, never
about one that was legitimately never seeded.

## Requirements

1. At `seedReady`, a context manifest that exists but contains no usable
   context row fails, with a finding that names the file and the repair. A
   usable row is a JSON object carrying a `file` key; the existing reference,
   self-reference, `_example`, and malformed rules continue to judge those rows
   on their own terms.

   A manifest that does not exist is not covered by this requirement and must
   keep passing, so an inline-platform consumer with no seeded manifests still
   validates.

   The rule applies only at `seedReady`. Merge time deliberately exempts the
   unfilled shape because there it is indistinguishable from a task whose
   manifests were never curated, and failing it produced a late completion-time
   failure. That reasoning is unchanged.
2. An unrecognized bookkeeping command fails loudly instead of composing a
   plausible-looking subject line. Today the subject excludes `final-bundle`
   and reports a task count for everything else, so a future command would
   report a count it never computed.
3. The operator-facing documentation states: that `seeded-task` exists and what
   it rejects; that a generated `TBD` PRD placeholder is grounds for rejection;
   and that the pack's default-branch override variable outranks the consumer's
   own `origin/HEAD` under `--repo`, with `evidence.defaultBranchSource`
   recording which one answered.

   It must also stop presenting "emptied" as an approved disposition of the
   scaffold without qualification. The merge-time exemption keeps its existing
   description; the seeded-task lane's opposite requirement is stated alongside
   it, so no operator can follow the documentation into the defect.
4. The change ships as 0.71.4 through the normal release path, with the
   full-fleet candidate ledger regenerated without a consumer filter.

## Acceptance Criteria

- [x] A seeded task whose `check.jsonl` is emptied fails `seeded-task` with a
      finding naming the file and the repair.
- [x] The same holds for a whitespace-only manifest and for a manifest whose
      only rows carry no `file` key.
- [x] A seeded task with no manifests at all still reports `seeded_task_valid`,
      proving the inline-platform consumer was not broken.
- [x] The lone-`_example` scaffold still passes merge-time validation and still
      fails `seeded-task`, unchanged from 0.71.3.
- [x] An unrecognized bookkeeping command fails loudly; a test pins it.
- [x] Each documentation surface in requirement 3 states the rule, and the
      template mirror and its generated copies agree byte-for-byte.
- [x] The scaffold passage no longer offers "emptied" as an unqualified
      approved disposition, and names the seeded-task lane's opposite rule.
- [x] `manifest.json` reads 0.71.4, CHANGELOG carries its heading, and the
      release payload gate reports the version transition.
- [x] `sd-check` passes and the full-fleet candidate ledger is regenerated
      without a consumer filter.

## Out of scope

Resuming the fleet campaign. That is the post-archive handoff for this task:
once 0.71.4 is merged and tagged, campaign
`refresh-0.71.3-20260813T163232Z` resumes from fresh preflight evidence, and
`rwbp-coordinator` is re-verified before anything touches it. It is not an
acceptance criterion here.
