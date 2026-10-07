---
title: Ship a PR in a second repo under one item, one command, one first error
created: 2026-10-04
branch: ship-foreign-item-hint
item: sd:2576
---
# PRD — ship a PR for another repository's item

## Problem

An item belongs to one repository. Its work can still land in a second one:
on 2026-10-03, sd:2300 (traces-research) shipped PRs in traces-poc and
trace-classifier. From the second checkout, `sd-ship prepare --item 2300`
refused with `item repository does not match this checkout's origin`. The
refusal names no way forward. Three more refusals followed, each revealed only
after the previous one was fixed:

1. `prepare --item 2300`: item repository does not match this checkout's origin.
2. `prepare --no-item --review-id X`: no no-item record X exists.
3. `review --no-item --create-record`: requires `--assert-new-work`.
4. `review --create-record --review-id X`: cannot name an existing `--review-id`.

The merge lane works around the same wall: its helper ships a cross-repository
item as `--no-item --review-id` and writes the item's note by hand.

sd:2022 (absorbed here) asked that the `review_identity_required` refusal name
the allocation command. Its PRD is
`docs/work/2026-09-28-ship-review-id-hint/prd.md`. Refusals 2 to 4 now name
`sd-ship review --no-item --create-record --assert-new-work` (sd:2008, sd:2026),
so that PRD's requirements hold on main. Refusal 1 is the one left.

## Requirements

1. From a checkout whose origin differs from item N's repository, the first
   refusal of `prepare`, `merge`, `observe` or `reconcile --item N` names the
   working path: the allocation command, then the same command with
   `--no-item --review-id <review_id>`.
2. It names both repositories, so the caller can choose to run from the
   item's own checkout instead.
3. It says the PR is not recorded on item N, and names `sd task note N` as the way to record it.
4. `hold` and `release` name the item's repository and nothing else: there is no itemless hold.
5. Each site gets its code, boundary, state and next action from one definition.

## Acceptance

- A test runs `prepare --item N` from a checkout whose origin differs from
  N's repository and asserts that the refusal's `next_action` contains the
  allocation command and `prepare --no-item --review-id`.
- What is refused does not change; only the message and its workflow fields do.

## Out of scope

- `prepare --item N` accepting another repository's item. That is a decision
  on trust and semantics; `design.md` records it as open.
