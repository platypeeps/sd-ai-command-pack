---
title: Let the local gate release advisory findings by severity, and disposition a miscited one
status: done
created: 2026-08-24
branch: task/local-gate-advisory-severity
---
# Let the local gate release advisory findings by severity, and disposition a miscited one

## Why this exists

`_remote_gate` decides on an outstanding *count*. Severity and category are
carried on every normalized finding, merged correctly across providers, and then
discarded at the decision point. So a `low style` observation blocks a merge on
exactly the same terms as a `high correctness` defect.

Two consumers have measured what that costs, across nine review rounds:

| PR | rounds | findings | confirmed defects | overlap between rounds |
| --- | --- | --- | --- | --- |
| `sd-github-review#70` | 3 | 30 | 1 | rounds 1 and 2 shared none |
| `sd-github-review#99` | 6 | — | 0 | all six sets mutually disjoint |

The operative number is the overlap, not the count. **Each invocation emits a
fresh observation set**, so per-finding rebuttal disposes of one round's set and
the next round produces a different one. The loop is unbounded in rounds, not in
findings per round — which is why the rebuttal channel shipped in PR #402 was
necessary and is not sufficient.

PR #99 also showed *why* the findings were not defects, and one class defeats a
severity gate on its own:

- **Not a defect at all** — several were compliments on the diff ("improving
  accuracy of required update messages", "This is positive").
- **Describes code the diff removed** — one objected to a `JSON.stringify`
  comparison that the diff deleted.
- **Cites the wrong line** — a `laneRouteModeGate()` finding landed on a
  schema-2 migration test; a "must be last key" finding landed on a model-format
  error string; a "do not use `JSON.stringify`" finding landed on a closing brace.

Round 6 produced a **`high` finding that was false**: it claimed
`CONFIG_VARIABLES` was read against a manifest without version gating, and
tracing every use disproved it. A severity gate would correctly release the
compliments and would still let that one block. **Severity discrimination does
not fix a wrong-line citation**, which is why this task carries both halves.

## Goal

Let a review terminate when the providers return observations rather than
defects, without weakening the gate for real ones — and give a miscited finding
a disposition that does not require claiming it is merely rebutted.

## The design tension, and its resolution

Requirement R2 below forbids a disposition **inferrable from the provider's own
output**. R1 asks the gate to use **severity**, which *is* provider output.
Naively these contradict, and a naive implementation ships a gate a provider can
open by labelling its own finding `low`.

**Resolution: the provider supplies a key; policy supplies the meaning.** The
`severity` value is only ever a lookup key into a classification owned by the
reviewed repository, never a decision in itself. Three properties keep it sound:

1. **Policy is caller-side and digested.** The ceiling is resolved from
   `.sd-ai-command-pack/review.json`, which already feeds `configurationDigest`
   and through it `plan["policyDigest"]`, so a change to it is visible in the
   receipt and changes the receipt identity like any other policy change.
2. **A floor no policy can lower.** `severity: "high"` blocks regardless of
   configuration. A provider cannot label its way out and neither can a policy
   author.
3. **Unknown is blocking.** `severity: "unspecified"` (rank 0) is never
   advisory. A provider that omits classification gets the strict gate, so
   omission is never an escape.

## Why severity and not category

**Decided 2026-08-24 by the owner.** The family axis is a no-op by construction
and was rejected on measurement, not preference:

- `REVIEW_FINDING_FAMILY_IDS` = `task-metadata`, `boundary-validation`,
  `contract-documentation-drift`, `generated-surfaces`,
  `reviewer-test-harness-quality`, `other`.
- A representative consumer's prism `focus` = `bug`, `correctness`, `docs`,
  `maintainability`, `performance`, `security`, `style`, `testing`.
- **Set intersection: empty.** `review-local.py:1805-1806` flattens any
  non-member to `"other"`, so every prism finding reaches the gate as `"other"`
  and any family-keyed allowlist releases exactly nothing.

Severity does not have this problem: it is normalized (`:1580-1599`), ranked
(`FINDING_SEVERITY_RANK`, `:69`), and merged by **maximum** across providers
(`:1824-1827`), so an ensemble cannot lower a finding's severity by adding a
provider that rates it lower.

Two axes were considered and rejected. Keying on `sourceFamilies` (the raw
provider category, preserved at `:1819`) would work, but the lookup key becomes
arbitrary provider text and property 3 stops doing its safety work. Extending
the family vocabulary would also work and is the most principled, but that tuple
feeds `familyGate` and `_parse_family_finding`, so it changes repeated-family
round avoidance as a side effect.

## Requirements

- **R1 — severity usable in the gate decision.** An advisory-severity finding
  must not block indefinitely while a `high` finding still does.
- **R2 — do not weaken the gate.** An unaddressed real defect must still block,
  and no disposition may be inferrable from the provider's own output.
- **R3 — a miscited finding is dispositionable on that ground.** Distinct from
  `rebutted`, and distinct from a finding that is real but low-severity. The
  ground is checkable against the checkout: the cited path and line do not
  contain the described code.
- **R4 — visible in the typed result.** A reader must be able to tell a clean
  receipt from one that was released by ceiling or by disposition, and
  `remoteGate` must reflect which.
- **R5 — omission is strict.** A repository that sets no ceiling gets exactly
  today's behavior, byte for byte.

## Acceptance criteria

Ticked 2026-08-24 against the shipped code and a named test, not against a
description. Test names are in `tests/test_review_stage.py`.

- [x] `policy.localAdvisorySeverityCeiling` is accepted in
      `.sd-ai-command-pack/review.json` for `low` and `medium` only, rejected
      with a bounded error for `high`, for `unspecified`, and for any value
      outside the severity vocabulary, and absent by default. Note `high` and
      `unspecified` are *in* the vocabulary and still rejected — the first
      because accepting it would let a policy author lower the floor, the second
      because rank 0 is the "provider told us nothing" sentinel.
      — `ADVISORY_CEILING_VALUES` and the `_parse_config` policy block;
      `test_advisory_ceiling_rejects_high_and_unspecified_and_nonsense`.
- [x] A finding at or below the ceiling does not block. Asserted by a test.
      — `test_advisory_ceiling_releases_a_finding_at_or_below_it`, which also
      checks the released finding is still recorded `outstanding` rather than
      quietly dispositioned.
- [x] A `high` finding blocks with the ceiling set to its maximum permitted
      value — the floor is not lowerable. Asserted by a test.
      — `test_advisory_ceiling_does_not_release_a_high_finding`. The explicit
      `rank >= high` floor needs a second test to pin it, because at the
      permitted ceilings it is arithmetically redundant: see
      `test_advisory_predicate_keeps_a_floor_a_wider_vocabulary_cannot_lower`.
- [x] A finding with `severity: "unspecified"` blocks with any ceiling set.
      Asserted by a test.
      — `test_advisory_ceiling_never_releases_an_unclassified_finding`, which
      covers the `unspecified` sentinel and an invented severity in one place,
      since both rank 0 and both must block for the same reason.
- [x] `--local-disposition <id>=miscited` is accepted, requires the caller to
      supply the cited path and line, and is recorded in the receipt distinctly
      from `rebutted`.
      — `test_miscited_is_recorded_with_its_citation_and_not_as_rebutted`; the
      grammar's rejection cases are in
      `test_miscited_grammar_requires_a_usable_citation`.
- [x] A `high` finding dispositioned `miscited` does not block, while a `high`
      finding with no disposition does. Asserted by one test that runs both.
      — `test_miscited_releases_a_high_finding_that_otherwise_blocks`.
- [x] `remoteGate` distinguishes "no findings" from "released by ceiling" from
      "released by disposition"; the receipt carries counters for each.
      — `local-stage-terminal` / `local-advisory-released` /
      `local-findings-dispositioned`, with `outstanding`, `advisory` and
      `dispositioned` in the receipt's `disposition` block. Precedence asserted
      by `test_disposition_reason_outranks_advisory_release`; the counters by
      `test_one_advisory_finding_does_not_release_a_blocking_sibling`.
- [x] With no `localAdvisorySeverityCeiling` configured, every existing review
      test passes unchanged.
      — no existing test was edited. `test_no_ceiling_blocks_on_a_low_finding`
      pins omission explicitly, and mutation M3 (defaulting the absent ceiling
      to `medium`) kills it.
- [x] `sd-review`'s public control list documents `--local-disposition`'s new
      ground and the policy field.
      — plus two corrections the same pass forced: the local-completion rule now
      reads `remoteGate.state` instead of requiring a "clean" receipt, which
      would have made this feature inert in exactly the topology it targets;
      and `--attempt-id` is now documented as the optional control it is.
- [x] The PR #70 three-round sequence, replayed against the new gate, terminates
      without a human `review.round-extension` decision.
      — **MET 2026-08-25.** `remoteGate: {"state": "eligible", "reason":
      "local-findings-accepted"}`, `outstanding: 0`, `accepted: 2`,
      `advisory: 3`, one provider attempt, exit 0 in 37.0s. Receipt
      `01bc26a47bed8804…`. Verified on all three things this criterion turns on:
      `--round-extension-authorized` was never passed and no `roundExtension`
      appears in the receipt; the gate reached plain `eligible`, not
      `eligible-with-limitations`; and the `medium` ceiling was live, releasing
      three of five findings. Full record in the consumer's
      `08-09-review-gate-advisory-convergence` (archived), section
      "Third replay, 2026-08-25".
      **The prism 401 was routed around, not fixed.** `--local auto` under
      `substantive-ensemble` selected **gito alone**, so `prism-chunked` was
      never invoked and this run is no evidence about it. The criterion does not
      name a provider, so it is met — but the credential blocker this note
      recorded is still real for any future prism run.
      Two other things the replay depended on, recorded because they were
      prerequisites rather than incidental: the machine layer was eighteen
      versions behind (0.71.39 by its receipt) and had to be reinstalled to
      0.71.51 before `accepted` was even a recognised verb; and gito's head-ref
      defect (`08-25-gito-adapter-drops-head`) had to be worked around by
      building an overlay base so the working tree *was* the head. That defect
      is still open.

## Out of scope

- Changing what any provider is invoked with, its prompt, or its model.
- The `familyGate` / repeated-family machinery. Untouched by the severity axis,
  which is the reason that axis was chosen.
- Fixing the provider-side causes of miscitation. This task gives a miscited
  finding an exit; it does not stop one being emitted.

## Predecessor

`08-07-local-finding-rebuttal-channel` (PARKED) owns the rebuttal channel that
shipped in PR #402. Its acceptance criteria are still unchecked even though its
functionality is live; reconciling that record is step 0 of this task's plan.
Consumer evidence for both halves is `platypeeps/sd-ai-command-pack#406` and the
consumer task `sd-github-review!08-09-review-gate-advisory-convergence`.

**Note for anyone grepping**: in the local stage the shipped rebuttal mechanism
is *not* named `_local_outstanding`, as the predecessor PRD says. It landed as
an `outstanding` count computed in `_redispose_receipt` and read by
`_remote_gate`. Searching the local stage for the upstream symbol reports the
fix absent when it is present. A repo-wide grep does find `_local_outstanding`,
but in `sd-ai-command-pack-review.py`, where it is the controller's routing gate
consuming that same count — same name, different file, different job.
