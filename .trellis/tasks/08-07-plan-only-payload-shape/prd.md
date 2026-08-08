# Plan-only and executed local-review reports have divergent payload shapes

## Goal

Make `sd-ai-command-pack-review-local.py --json` emit payloads a consumer can
dispatch on, so a path written for one mode fails loudly against the other
instead of silently reading `null`.

## Problem

One command name, `sd-review-local-stage`, emits two structurally unrelated
JSON documents depending on whether `--plan-only` was passed.

Executed run — `_report`, `:2173-2185`:

```json
{
  "schemaVersion": 1,
  "command": "sd-review-local-stage",
  "outcome": "...",
  "status": "...",
  "run": "executed",
  "receipt": {
    "schemaVersion": 1,
    "receiptId": "...",
    "attemptId": "...",
    "target": {...},
    "plan": {...},
    "outcome": "...",
    "attempts": [...],
    "findings": [...],
    "disposition": {...}
  },
  "remoteSummary": {...}
}
```

Note that the executed report is not wholly nested: `schemaVersion`, `command`,
`outcome`, `status`, `run` and `remoteSummary` stay at the root. What moves is
`target`, `plan` and everything per-attempt — which is precisely the set a
comparison harness needs. Receipt fields are as constructed at `:2107-2116`.

Plan-only — `:2310-2317`:

```json
{
  "schemaVersion": 1,
  "command": "sd-review-local-stage",
  "status": "planned",
  "target": {...},
  "plan": {...}
}
```

Same `schemaVersion`. Same `command`. `plan` lives at the root in one and under
`.receipt` in the other. `target` is at the root in one and under `.receipt` in
the other. `attempts`, `receiptId`, `run` and `remoteSummary` exist only in the
executed shape.

### Why this is a defect and not merely an asymmetry

There is no field a consumer can branch on that is present in both and means
"which shape is this". `command` is identical. `schemaVersion` is identical.
`status` exists in both but carries a verdict in one (`clean`, `findings`,
`failed`) and a mode in the other (`planned`) — so distinguishing them requires
knowing the closed set of verdict values in advance, which is the coupling the
envelope exists to avoid.

The only reliable test is probing for a key's *absence*, and absence is exactly
what the failure mode disguises:

```
$ jq -S 'keys' plan-only.json
["command","plan","schemaVersion","status","target"]

$ jq -S '{providers: .providers, policyId: .policyId, outcome: .outcome}' plan-only.json
{"outcome": null, "policyId": null, "providers": null}
```

`jq -r` on a missing path prints `null` and exits 0. A comparison harness that
reads the wrong paths on *both* sides of a before/after diff compares `null` to
`null` and reports success while verifying nothing.

### This has already bitten

Verified against `4378d37b`. Planning for
`08-07-default-local-review-lanes` wrote an acceptance check whose `jq`
expressions read `providers`, `policyId` and the digests from the JSON root.
The check passed. It was asserting nothing — all three fields resolved to
`null`, because no plan field lives at the root of *either* shape. The defect
survived two adversarial review rounds and was caught only in round 3, then
required a hand-written non-null guard to make wrong paths fail loudly:

```bash
jq -e '.receipt.plan.policyId != null and (.receipt.attempts | length) > 0' "$f" > /dev/null \
  || { echo "FAIL: wrong jq path or wrong flags"; exit 1; }
```

Every consumer of this command has to reinvent that guard. That is the signal
the envelope is wrong, not the consumers.

## Scope

In scope:

- Making the two `--json` payloads distinguishable without probing for absent
  keys.
- Preserving the executed shape's existing consumers. `.receipt` is the
  documented location and the deprecation window for the `outcome`/`status`
  dual-emit (`DEPRECATED_PAYLOAD_KEYS`, removal at `0.66.0`) is already in
  flight; this must not collide with it.

Out of scope:

- The receipt's internal structure. `plan`, `attempts`, `findings` and
  `disposition` are correct as they stand.
- `sd-ai-command-pack-review.py`, the coordinator. It consumes the executed
  shape only and is unaffected by whichever option is chosen.
- The `--plan-only` flag's semantics. Planning without executing is the right
  capability; only its envelope is at issue.

## Candidate directions

Not a decision — the tradeoff belongs to the maintainer. Recorded so the
implementation session does not restart the analysis.

1. **Distinct `command` value.** `--plan-only` emits
   `command: "sd-review-local-stage-plan"`. One-line change, makes dispatch
   trivial, and breaks any consumer currently matching on the shared string.
2. **Nest plan-only under `.receipt` too**, with `attempts: []` and no
   `receiptId`. Gives one shape and one set of paths. Arguably dishonest —
   there is no receipt, because nothing ran.
3. **Explicit discriminator field**, e.g. `mode: "planned" | "executed"` at the
   root of both. Additive, breaks nothing, and leaves the shapes divergent —
   it makes the divergence *checkable* rather than removing it.

Option 3 is the cheapest and the least likely to break a consumer; option 1 is
the most self-describing. Option 2 is the only one that removes the divergence
outright, at the cost of asserting a receipt that does not exist.

## Acceptance criteria

- **AC1** — Given only a `--json` payload and no knowledge of which flags
  produced it, a consumer can determine the mode by reading a field that is
  present in both shapes. Demonstrate with a single `jq` expression that
  returns a correct, non-null answer for both inputs.
- **AC2** — The executed payload's existing paths are unchanged. Root:
  `.schemaVersion`, `.command`, `.outcome`, `.status`, `.run`, `.remoteSummary`.
  Nested: `.receipt.target`, `.receipt.plan.providers[].id`,
  `.receipt.plan.policyId`, `.receipt.plan.configurationDigest`,
  `.receipt.plan.policyDigest`, `.receipt.attempts[].status`,
  `.receipt.attempts[].provider.id`, `.receipt.outcome`, `.receipt.receiptId`.
  Assert each is non-null on a real executed run, not by reading the source.
- **AC3** — `tests/test_review_stage.py` passes unmodified, or every
  modification is justified as an intended contract change rather than a test
  bent to fit.
- **AC4** — The coordinator, `sd-ai-command-pack-review.py`, still succeeds
  end-to-end. It reads the executed shape at `:950-951` and `:974`; a change
  that only looks safe in the stage must be proven safe in the caller.
- **AC5** — `SD_AI_COMMAND_PACK.md` documents both shapes and the discriminator.
  The defect that motivated this filing was written by someone reading the
  source; the documentation is what should have prevented it.
- **AC6** — If the chosen option changes any emitted field, the manifest version
  is bumped with a matching CHANGELOG heading. `CONTRIBUTING.md:136-142`, gated
  in CI by the Release payload gate job.

## Verification notes

AC1 must be shown against two payloads captured from actual runs, not
constructed by hand. A hand-written fixture will have the shape the author
believes is emitted, which is precisely the assumption that failed here.

For AC2, assert non-null rather than diffing. A diff of two wrong paths passes;
that is the entire failure mode this task exists to close.

## Not approved for implementation

`task.py start` has not been run; this task is `status: planning`.
