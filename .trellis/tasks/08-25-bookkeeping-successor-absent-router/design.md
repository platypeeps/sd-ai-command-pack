# Design — reachable bookkeeping successor under an absent router

Reads on the decision settled in `prd.md`. That decision is shared with
`08-25-aggregate-outcome-masks-provider-failure` and is not re-argued here.

## Boundary

One file changes: `templates/scripts/sd-ai-command-pack-review.py` (source of
truth; the other three copies are generated). No change to
`sd-ai-command-pack-review-local.py`, no change to `OUTCOMES`, no change to any
receipt field. The receipt already carries everything the router needs.

## Contract

A new module-level helper, placed next to `_local_outcome` (`:854`), which is
where the router's other reads of the local report live:

```python
def _local_selected_nothing(local: object) -> bool:
    """Did the local plan select zero providers?

    ``outcome == "skipped"`` cannot answer this. It is reached both when no
    provider was asked (``not attempts``) and when every asked provider
    reported ``skipped`` in its own payload -- ``_parse_argv_payload`` accepts
    any status in ``OUTCOMES``. The plan's provider list separates the two
    without ambiguity.
    """
```

It returns `True` only for a receipt whose `plan["providers"]` is a list and is
empty. Anything malformed -- no receipt, no plan, a non-list `providers` --
returns `False`, so a receipt the router cannot read is never treated as a
deliberate skip.

A second helper expresses the acceptance rule once, so the two branches cannot
drift:

```python
def _local_silence_is_accounted(local: object, outcome: object) -> bool:
    return outcome == "clean" or (
        outcome == "skipped" and _local_selected_nothing(local)
    )
```

## Call sites

Both are in `route()`.

- **Non-PR branch, `:2119`.** `if local_status in {"clean", "skipped"}:` becomes
  the helper. The failure return below it already exists and already carries
  `limitations=(f"local-{local_status}",)`; the newly-rejected case (b) falls
  into it and reports `local-skipped`, which is accurate.
- **Absent-router PR branch, `:2145`.** `if local_status != "clean":` becomes
  `if not _local_silence_is_accounted(local, local_status):`. Note that by this
  point `local_status` can only be `clean` or `skipped` -- the guard at `:2103`
  rejects everything outside `{clean, skipped, unavailable, failed, cancelled}`
  and the early return at `:2110` takes the other three -- so today's
  `!= "clean"` is exactly `== "skipped"`. The rewrite narrows that to the
  case (b) subset.

The diagnostic on the PR branch changes from "optional router absence requires
a clean local review" to one that names the real requirement, since the branch
no longer requires `clean`.

## Attribution

The success return on the absent-router branch already reports
`limitations=("router-not-configured", "zero-remote-confidence")`. A skipped
local review adds a third entry naming the policy that produced it, taken from
`plan["policyId"]` verbatim:

```
("router-not-configured", "zero-remote-confidence", f"local-skipped:{policy_id}")
```

`policy_id` is `str(plan.get("policyId") or "unknown")`. Reaching this line
means `_local_selected_nothing` already returned `True`, so `plan` is a Mapping
with a list `providers` -- but `policyId` itself is not re-validated there, and
a missing key would otherwise render as the string `local-skipped:None`, which
reads like a policy name and is worse than admitting the gap.

Verbatim, not mapped. The mapped form is `_router_local_summary`'s `skipReason`,
which is incomplete (see `prd.md`); a limitation string that silently relabels
`trivial-skip` as `not-requested` would be the same class of defect this task
exists to fix. `limitations` is a free-form `Sequence[str]` in `_report`
(`:1755`), so this needs no schema change.

This is the safety case for the whole change: the run reaches `ready`, and the
report says on its face that no router was configured, that there is zero
remote confidence, and which policy chose to ask no local provider. Nothing is
silently accepted.

## The alternative that was checked and rejected

Reading `receipt["remoteGate"]["state"] == "eligible"` instead, which would
match `templates/docs/SD_AI_COMMAND_PACK.md:1037` word for word, does not work:
`_remote_gate` returns `eligible / local-stage-terminal` for case (b) too,
because providers that declined leave no outstanding findings and no terminal
failure. The gate is subject to the same conflation as `outcome`. Recorded here
because the simplification is attractive and someone will reach for it.

## Compatibility

- **Widened:** an absent-router PR with a zero-selected local plan now reaches
  `ready` instead of `indeterminate`. This is the reported defect.
- **Narrowed:** a non-PR review whose providers all reported `skipped` now
  fails instead of reaching `ready`. Intended; see `prd.md`. Reachable only via
  an argv-adapter provider that reports `status: "skipped"`; the `prism` and
  `gito` adapters emit only `clean`/`findings` (`:1862`, `:1917`), so no
  bundled provider can trigger it.
- Unchanged: every other branch, the round-limit grant, the receipt schema,
  `_router_local_summary`, and the exit-code mapping.

## The round-limit interaction

`BOOKKEEPING_REENTRY_ROUNDS = 2` (`:66`) is granted at `:1897` only when
`--successor bookkeeping` carries `--bookkeeping-evidence` with `--local auto`
and no family evidence. The deadlock the PRD reports needs both halves to be
visible at once: with the grant the attempt is legal but could not reach
`ready`; without it the attempt is refused at `:1898` before routing. A test
that exercises only one half sees no deadlock, which is why criterion 5 asks
for them together.

## Rollback

Revert the commit. Both helpers are additive and both call sites are
single-expression swaps; no state file, receipt, or digest changes shape, so a
receipt written under either version is readable by the other.
