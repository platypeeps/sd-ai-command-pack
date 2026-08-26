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

> Correction, 2026-08-25, left in place rather than rewritten because the
> sentence above is the original report. "Only scope ... defined to run" is
> true of the ship flow, not of the tool:
> `test_bookkeeping_reentry_has_its_own_bounded_round_budget`
> (`tests/test_review_controller.py:2734`) drives `--successor bookkeeping` at
> `--scope branch` and reaches `ready` today. The deadlock is specific to PR
> scope, which is what the rest of this PRD describes; nothing below depends
> on the stronger claim.

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

## Open question, settled

Settled 2026-08-25 after reading the code. The PRD offered two answers;
neither is the one taken, because the investigation found a fact the PRD did
not have.

### What the investigation found

`skipped` is doing double duty, exactly as the PRD suspected, and the second
meaning is not theoretical. `_aggregate_outcome` reaches `skipped` two ways:

```python
def _aggregate_outcome(attempts):
    if not attempts:
        return "skipped"                              # (a) nobody was asked
    ...
    if statuses <= {"clean", "skipped"}:
        return "clean" if "clean" in statuses else "skipped"   # (b) all declined
```

Case (b) is reachable. `_parse_argv_payload` accepts any provider-reported
status that is in `OUTCOMES`, and `OUTCOMES` contains `skipped`:

```python
if not isinstance(value, dict) or value.get("status") not in OUTCOMES:
    return None
```

So an argv-adapter provider can run, report `skipped`, and produce an
aggregate `skipped` that means "providers were asked and declined to answer".
That is an unexplained absence of evidence. Case (a) is a deliberate
zero-selection. Accepting one is reasonable; accepting the other is a hole.

This rules out PRD option 1. Accepting `skipped` alongside `clean` on the
absent-router PR branch, to match the non-PR branch, would let a PR reach
`ready` with no routed review *and* no local review, on the strength of
providers having declined.

### Why not a new outcome word either

PRD option 2 -- give the zero-selected case its own outcome -- is the larger
change, and it is unnecessary, because the unconflated fact is already in the
receipt. `build_plan` records the selection:

```python
"providers": [_provider_row(item) for item in selected],
```

`plan["providers"] == []` is precisely "zero providers were selected", with no
ambiguity to resolve. Case (b) has a non-empty `plan["providers"]`.

This is the same shape as the fix taken in
`08-25-aggregate-outcome-masks-provider-failure`, and deliberately so. There
the remote gate stopped reading `outcome` as a verdict and drew a separate
`degraded` signal from `confidence.limitations`, a fact the receipt already
recorded. Here the router stops reading `outcome` as a verdict and draws the
"was anything actually asked" fact from `plan["providers"]`, which the receipt
already records. **The shared decision, stated once for both tasks: `outcome`
describes what the providers found; it is not a verdict, and it must not be
widened to carry one. When a gate needs a fact `outcome` cannot express, it
reads that fact from where the receipt already keeps it.**

`review.py` already works this way in one place, which is corroboration rather
than coincidence -- `_router_local_summary` disambiguates a `skipped` outcome
by reading `plan["policyId"]`:

```python
    if outcome == "skipped":
        policy_id = plan.get("policyId")
        summary["skipReason"] = (
            "bookkeeping-successor"
            if policy_id == "bookkeeping-successor"
            else "explicit-none"
            if policy_id == "explicit-none"
            else "not-requested"
        )
```

That mapping is not reused as the predicate, for two reasons. It is
incomplete -- `build_plan` also produces `f"{risk_class}-skip"`, a fourth
deliberate zero-selection that the mapping labels `not-requested` -- and it is
indirect: after the policy chain, `selected.extend(by_id[item] for item in
required if item not in selected_ids)` can add required providers back, so a
`policyId` naming a zero-selection policy does not guarantee a zero selection.
`plan["providers"]` survives both. `skipReason` stays as it is, for reporting.

### The decision

Accept `skipped` on the absent-router PR branch **only when the plan selected
zero providers**, and pin the non-PR branch to the same predicate.

### The consequence that is not a bug fix

Today the non-PR branch accepts every `skipped`, case (b) included. Under one
shared predicate it no longer does. That is an intended tightening, not a
side effect: a non-PR review in which every provider was asked and declined
gives zero assurance, and reporting `ready` for it is the same defect in the
other branch. It is called out here because it is a behavior change beyond the
reported symptom, and it belongs in the changelog as one.

### Two things the code review turned up, recorded so they are not re-litigated

**The documented rule already promises this fix.**
`templates/docs/SD_AI_COMMAND_PACK.md:1037` states the absent-router rule in
terms of the gate, not the outcome:

> When integration is optional and the descriptor is absent, only a local
> receipt whose `remoteGate.state` is `eligible` may complete, with
> `router-not-configured` and `zero-remote-confidence` limitations.

A zero-selected receipt has no outstanding findings and no terminal failure, so
`_remote_gate` returns `{"state": "eligible", "reason": "local-stage-terminal"}`
for it -- the same reason a clean receipt carries, which is why the doc's
enumeration of four gate reasons does not need a fifth entry; one of the four
simply covers two receipt shapes. Under the documented rule it may already complete. The code refuses it
only because `route()` asks `local_status != "clean"` instead. So this is not a
new permission being granted; it is the code being brought to the rule the docs
already state.

**But reading the gate is not the fix either.** The obvious simplification --
replace the predicate with `receipt["remoteGate"]["state"] == "eligible"` and
match the docs exactly -- was checked and rejected. `_remote_gate` returns
`eligible / local-stage-terminal` for case (b) as well: providers that were
asked and declined leave no outstanding findings and no terminal failure, so
the gate cannot tell (a) from (b) any more than `outcome` can. Aligning to the
gate would move the conflation rather than resolve it. The plan's provider list
remains the only unconflated source.

The consequence is that the code will be *stricter* than the documented rule
for case (b). That divergence has to be written into the doc paragraph, not
left implicit -- see the implementation plan's docs step.

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
