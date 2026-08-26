# Make the bookkeeping successor reachable when no routed reviewer is configured

## Origin

Found on 2026-08-25 while driving PR #551 through `sd-ship until=merge` at pack
0.71.52. Stage 2b's successor-head re-entry could not reach `ready` through
its own documented route.

## Goal

A successor-head re-entry on a PR must be able to complete in a repository
that has no routed-review descriptor. Today it cannot, and the workaround
(`--remote none`) is discovered rather than documented.

## The defect

Two rules meet and contradict each other.

1. `--successor bookkeeping` deliberately selects **zero** local providers.
   In `build_plan` (`scripts/sd-ai-command-pack-review-local.py`):

   ```python
   elif successor == "bookkeeping":
       _validate_bookkeeping_evidence(bookkeeping_evidence, target)
       selected, policy_id = [], "bookkeeping-successor"
   ```

   With nothing selected, the local stage reports `outcome: "skipped"`.

2. The absent-router branch for PR scope in
   `scripts/sd-ai-command-pack-review.py` accepts only `clean`:

   ```python
   if cap_state == "absent":
       if local_status != "clean":
           return 3, _report(
               state=state, status="indeterminate",
               diagnostic="optional router absence requires a clean local review",
               limitations=("router-not-configured", f"local-{local_status}"),
           )
   ```

   The non-PR branch immediately above accepts both spellings:

   ```python
   if scope != "pr":
       if local_status in {"clean", "skipped"}:
           _advance(state_path, state, "ready")
   ```

PR scope is the only scope in which the successor-head re-entry is defined to
run, so the intended route is unreachable whenever the routed-review
descriptor is absent.

Observed on PR #551, attempt 6:

```
status: indeterminate
limitations: ['router-not-configured', 'local-skipped']
diagnostic: optional router absence requires a clean local review
```

## Why the obvious workaround is not a fix

Dropping `--successor bookkeeping` to get a real local review does not work
either. The bookkeeping grant is what makes a late attempt legal at all:

```python
BOOKKEEPING_REENTRY_ROUNDS = 2
...
if (args.successor == "bookkeeping" and args.bookkeeping_evidence
        and args.local == "auto" and not args.family_evidence):
    round_limit += BOOKKEEPING_REENTRY_ROUNDS
```

Without it, attempt 6 exceeds `roundLimit` (5) and fails with
`attempt exceeds remoteIntegration roundLimit`. So the two routes are mutually
exclusive: one reviews but is out of rounds, the other has rounds but cannot
reach `ready`.

The run was unblocked with `--remote none`, which is legitimate here only
because `remoteIntegration.requirement` is `optional` and the gate's own
`remote-intentionally-skipped` path returns `ready`. That is a property of
this repository's config, not a general answer.

## Open question to settle first

`skipped` is currently doing double duty. "Zero providers were selected"
and "providers ran and had nothing to say" are different facts wearing one
word. Decide whether the fix is:

- accept `skipped` alongside `clean` on the absent-router PR branch, matching
  the non-PR branch; or
- give the zero-selected case its own outcome, so the PR branch can accept
  *that* without also accepting a genuine provider skip.

The second is likely correct but is the larger change. Cross-reference
`08-25-aggregate-outcome-masks-provider-failure`, which is the same family:
the outcome vocabulary is serving as both "what happened" and "is this
acceptable", and the two branches disagree on the mapping.

## Acceptance criteria

- [ ] A `--successor bookkeeping` re-entry on a PR reaches `ready` with no
      routed-review descriptor configured and without `--remote none`.
- [ ] The chosen semantics for the zero-selected case are written down in the
      review spec, including whether `skipped` was split.
- [ ] A regression test covers the absent-router PR branch for the
      zero-selected case, asserting the outcome and not merely that the call
      succeeded.
- [ ] A test pins the non-PR and PR branches to the same mapping, so they
      cannot drift apart again.
- [ ] The round-limit interaction is covered: the grant and the reachable
      route are exercised together, since either alone hides the deadlock.
