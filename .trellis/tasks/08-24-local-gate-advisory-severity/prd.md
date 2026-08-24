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

- [ ] `policy.localAdvisorySeverityCeiling` is accepted in
      `.sd-ai-command-pack/review.json` for `low` and `medium` only, rejected
      with a bounded error for `high`, for `unspecified`, and for any value
      outside the severity vocabulary, and absent by default. Note `high` and
      `unspecified` are *in* the vocabulary and still rejected — the first
      because accepting it would let a policy author lower the floor, the second
      because rank 0 is the "provider told us nothing" sentinel.
- [ ] A finding at or below the ceiling does not block. Asserted by a test.
- [ ] A `high` finding blocks with the ceiling set to its maximum permitted
      value — the floor is not lowerable. Asserted by a test.
- [ ] A finding with `severity: "unspecified"` blocks with any ceiling set.
      Asserted by a test.
- [ ] `--local-disposition <id>=miscited` is accepted, requires the caller to
      supply the cited path and line, and is recorded in the receipt distinctly
      from `rebutted`.
- [ ] A `high` finding dispositioned `miscited` does not block, while a `high`
      finding with no disposition does. Asserted by one test that runs both.
- [ ] `remoteGate` distinguishes "no findings" from "released by ceiling" from
      "released by disposition"; the receipt carries counters for each.
- [ ] With no `localAdvisorySeverityCeiling` configured, every existing review
      test passes unchanged.
- [ ] `sd-review`'s public control list documents `--local-disposition`'s new
      ground and the policy field.
- [ ] The PR #70 three-round sequence, replayed against the new gate, terminates
      without a human `review.round-extension` decision.

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

**Note for anyone grepping**: the shipped rebuttal mechanism is *not* named
`_local_outstanding`, as the predecessor PRD says. It landed as an `outstanding`
count computed in `_redispose_receipt` and read by `_remote_gate`. Searching for
the upstream symbol reports the fix absent when it is present.
