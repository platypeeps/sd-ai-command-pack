# Design — ship a PR for another repository's item

## Change: the first refusal names the working path

One factory, `foreign_item(item, item_repository, repository, command)` in
`bin/sd_ship_no_item.py`, beside `review_identity_required` and
`missing_record`. Both raise sites in `bin/sd-ship` call it: `Ship.__init__`
and `hold_command`.

| Field | Value |
|---|---|
| `code` | `item_repository_mismatch` |
| `boundary` | `input` |
| `state` | `operator_decision` |
| message | `item sd:N belongs to <item repository>, not this checkout's origin <repository>` |

The `next_action` for `prepare`, `merge`, `observe` and `reconcile` has three parts:

1. To ship under sd:N, run from a checkout of `<item repository>`.
2. To ship this checkout's PR without an item, run
   `sd-ship review --no-item --create-record --assert-new-work`, then
   `sd-ship <command> --no-item --review-id <review_id>` with the
   `review_id` it prints. An itemless merge also needs `--manual --expected-head SHA`.
3. The itemless path records nothing on sd:N; record the PR there with
   `sd task note N`.

For `hold` and `release` the `next_action` is only part 1: no itemless hold exists.

The message keeps the old wording as its prefix (`item repository does not match
this checkout's origin`), so a caller that matches on it still matches.

## What does not change

Nothing new is accepted. No record is allocated implicitly: the refusal names
the allocation command and the caller runs it, so a missing ID still never
allocates a review budget. The refusals that follow on the itemless path
already name the command (sd:2008, sd:2026).

## Open decision, parked: accept another repository's item

Option (a) of sd:2576: let `prepare --item N` take an item whose repository
differs, as `--associate-only`, and record the PR on N. It needs these calls first:

- **Item status.** An associate-only receipt never delivers N. Does a merge in
  the second repository write N's delivery note, and may it ever close N?
- **Lock and hold.** The ship lock and `hold` are per repository. N could then
  be in two lanes at once, one per repository.
- **Branch check.** N's `branch` names a branch of its own repository. The
  check `item belongs to a different branch` would need a rule for the second one.
- **Gate and policy.** The checkout's repository decides the gate, review policy
  and protection. N's repository then has no say in work recorded on N.

Until those are decided, the itemless path with a note on N is the supported route.
