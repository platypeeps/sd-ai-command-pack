# Design: task-native SD workflow program topology

## Architecture

The program uses Trellis task ownership as its only live roadmap structure:

1. The parent owns the immutable finding ledger, child map, coordination rules,
   cross-child completion contract, and final closure decision.
2. Existing children own foundation and workflow implementation deliverables.
3. One new integration child owns the coupled end-to-end scenario matrix and
   publishes the evidence required for parent closure.
4. Written dependency sections in each child, not tree position or wave names,
   define execution ordering.

The parent remains PRD-only because it has no implementation target. Complex
implementation children may retain their own `design.md` and `implement.md`;
only the redundant program-level artifacts are retired.

## Content Migration Map

| Program content | Durable owner |
| --- | --- |
| Architecture stages for trust, questions, eligibility, review, workflow owners, and drift lint | Existing implementation child PRDs and explicit dependencies |
| Foundation and workflow sequencing | Dependency sections of the consuming child tasks |
| Eleven cross-child scenarios | New `validate-sd-workflow-program-integration` task |
| Shared exact-head, read-only, merge-authority, question, portability, and fail-closed invariants | New integration task requirements plus owning child requirements |
| Final validation commands and retired-surface checks | New integration task implementation and acceptance criteria |
| Version-based program rollback | New integration task design |
| Planning approval, task selection, stop rules, and program closure | Parent PRD |

## Integration Task Contract

The new task is one independently verifiable gate because every scenario uses
the same landed command surface, generated adapters, receipts, and repository
state. It must remain blocked until all selected implementation children are
archived or have an explicit accepted disposition recorded by the parent.

Its output is an evidence map from F01-F17 and each scenario to the landed
task, PR/commit, test, and final result. The parent consumes that map when
deciding whether the program can close.

## Reference Cleanup

Delete the four redundant parent files only after the parent and integration
PRDs contain their durable content. Search active tasks, specs, docs, and code
for exact deleted paths, generic wave labels, and statements assigning matrix
execution to the parent. Historical records stay immutable.

## Compatibility And Rollback

This changes planning topology only; it does not change a shipped command or
runtime contract. If validation finds lost content or invalid task metadata,
restore the deleted parent files and task links from Git, then correct the
migration before publication. Do not delete or recreate existing child tasks.
