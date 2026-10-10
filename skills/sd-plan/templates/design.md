---
title: <one line, what this delivers>
created: <YYYY-MM-DD>
item: sd:<id>
---

# Design — <slug>

Write this page only when the shape needs agreement before the code.
The item's row holds status, progress and decisions; this page holds the shape.

## Problem

<What is wrong today, in terms someone outside this work would recognise.>

## Approach

<The shape of the solution, and the alternative you rejected with the reason.>

## Non-goals

<What this change does not do, so a reviewer does not ask for it.>

## Failure table

<Required when the change moves state in steps; omit it otherwise.>

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| <step> | <what is written or moved> | <what can fail there> | <how the next run finishes or undoes it> | <the test that stops the process there> |

## Slices

<The ordered PRs. For each, name what it leaves working on every machine. Omit this section for a single-PR change.>

## Acceptance criteria

- [ ] <A check with a result, not an intention: "`pytest tests/auth` passes with 0 failures".>

## Risks

<What could make this wrong. Name the risks you accept, not only the ones you mitigate.>
<For each check that grants a pass, name what ties its evidence to the subject: head, event, repository or inputs.>
