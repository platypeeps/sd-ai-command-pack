# Design — record the advisory classification on the finding

## Boundary

One file: `templates/scripts/sd-ai-command-pack-review-local.py` (source of
truth; the other three copies are generated). No change to `_is_advisory` --
the PRD's first non-goal -- and no change to which findings the ceiling
releases.

## The field

Every **outstanding** finding gains `"advisory": true | false`, written at the
moment the classification is made. Not only the released ones: a reader
partitioning `findings[]` should be reading a recorded answer, not inferring
one from an absent key. Absence would also be indistinguishable from a receipt
written before this change.

The partition a reader can then make with no severity logic of its own:

| record | meaning |
| --- | --- |
| `disposition != "outstanding"` | the caller dispositioned it |
| `disposition == "outstanding"`, `advisory == true` | the ceiling released it |
| `disposition == "outstanding"`, `advisory == false` | it is holding the gate |

The field is written **only when a ceiling is configured**. With no ceiling
there is no classification to record -- `_is_advisory` returns `False` for
everything before it looks at the finding -- and writing `advisory: false`
everywhere would change every receipt in every repository that never opted in.
That is the PRD's requirement 4, and it is the same reasoning the plan already
applies to the ceiling key itself (`:1463`).

A reader facing a receipt with no `advisory` key anywhere is not left guessing
which kind of absence it is: `plan.localAdvisoryRecordVersion` (below) is
present exactly when the classification is being recorded, so the plan answers
"strict repository" versus "receipt older than this change" without inspecting
a single finding.

## One decision, not two

`_disposition_counts` is renamed `_classify_findings` and records as it counts.
The counts and the records are then the same traversal of the same predicate;
there is no second place for them to disagree, which is what requirement 2
asks for.

The rename is not cosmetic. A function called `_disposition_counts` that
mutates its argument is a trap for the next reader, and both call sites already
hold the findings list mutably. No test references the old name.

The write is conditional; the **removal is not**. Every pass pops `advisory`
from every finding first, and writes it back only on the findings that are both
outstanding and under a configured ceiling. That leaves one invariant with no
exceptions: `advisory` is present exactly where the current plan's ceiling
classified it, this pass.

The unconditional pop costs nothing against requirement 4. Today's code never
writes `advisory` on a finding, so no receipt this tool has ever produced
carries the key, and popping an absent key changes no byte of any of them. What
it does buy is the two cases a conditional pop gets wrong:

- The re-disposition path (`_redispose_receipt`, `:2367`) recomputes on a
  stored receipt after a caller rebuts or accepts something. A finding that was
  released and is now rebutted must not keep `advisory: true` -- that is this
  task's own defect, one disposition later.
- Any finding that leaves `outstanding` by any route. The write is conditional
  on being outstanding, so the removal has to cover every finding that is not,
  and making it unconditional means there is no second condition to get wrong.

A ceiling *change* needs no removal branch at all: it changes `policyDigest`,
so the stored receipt is at a different identity and is never reloaded. That is
worth stating because it is the case a reader will reach for first, and it is
the one the pop does not exist for.

## Receipt identity

`_receipt_identity` (`:2505`) digests `{schemaVersion, target, policyDigest,
plan.providers}` -- not the findings. So a new finding field does not change
identity on its own, and a repository that **already** has a ceiling
configured would reuse a cached pre-change receipt and serve findings with no
`advisory` key. That is precisely what requirement 3 forbids.

The lever is the plan, which is digested into `policyDigest` and thence into
the identity. A version marker is emitted beside the ceiling, under the same
condition:

```python
ceiling = policy.get("localAdvisorySeverityCeiling")
if ceiling is not None:
    plan["localAdvisorySeverityCeiling"] = ceiling
    plan["localAdvisoryRecordVersion"] = 1
```

- ceiling configured -> the plan changes -> `policyDigest` changes -> the
  receipt identity changes -> the cached receipt is not reused, and the next
  run writes the field. Requirement 3.
- no ceiling -> no key emitted -> the plan, the digest, and the receipt are
  byte-identical to today. Requirement 4.

Emitting the marker unconditionally would invalidate cached receipts
fleet-wide for a feature nobody turned on -- the failure the comment at `:1463`
was written to prevent. Tying it to the same condition is not a trick; the
marker is only meaningful where a classification exists.

## The one existing test this changes

`tests/test_review_stage.py:2022`,
`test_advisory_ceiling_reaches_the_plan_and_changes_the_policy_digest`, asserts
that the ceiling is the *only* plan key the ceiling configuration adds:

```python
self.assertEqual(
    set(ceiling_plan) ^ set(strict_plan), {"localAdvisorySeverityCeiling"}
)
```

The marker makes that symmetric difference two keys, so this test goes red by
design. It is updated to expect both, not relaxed to a subset check: it was
written to fail when an unintended key reaches the plan -- exactly the failure
mode this change walks past -- and that guard is worth keeping. This is the
only existing test the design expects to change; another one going red means
the change is wider than described here and the design is wrong, not the test.

## Compatibility

- A receipt from a ceiling-configured repository gains a field and a new
  identity. Its old cached receipt is not reinterpreted; it is superseded.
- A receipt from a repository with no ceiling is unchanged, byte for byte.
- A cached pre-change receipt is not rejected -- it is never looked up.
  `execute` (`:2548`) derives the receipt path from the identity, so a changed
  `policyDigest` points at a different filename; the old file is orphaned, the
  run proceeds fresh, and the operator sees no error. `_validate_reusable`
  (`:2516`) is the second line, not the first: it rejects a receipt whose
  stored `plan` differs from the computed one, which a hand-edited or
  half-migrated file could still reach.
- Nothing reads `findings[].advisory` yet. The field is a record, and acting
  on it per finding is the follow-on the PRD names as the reason to have it.

## Rollback

Revert the commit. Receipts written under this version carry an extra finding
field and a plan key, so after the revert their identity no longer matches what
the reverted code computes: they are orphaned rather than misread, and the next
run writes a fresh receipt at the old identity. Nothing has to be migrated or
deleted, and no run fails because of one.
