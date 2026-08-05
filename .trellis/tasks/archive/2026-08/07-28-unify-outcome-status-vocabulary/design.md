# Design — unify the outcome and status vocabulary

## Scope boundary

Payload **envelopes** — the top-level keys of documents these scripts emit as
`--json` or write as receipts. Not every dict key named `status` anywhere in the
codebase. The distinction is the whole design, see below.

## R1's rule needs a scope, or it condemns 148 call sites

Measured 2026-07-28 across `scripts/`, `.github/scripts/`, `installer/`:

```
["status"] / .get("status")   148 sites
["outcome"] / .get("outcome")  16 sites
```

Sampling the 148 shows the overwhelming majority are **per-entity state on a
nested object**, not verdicts and not sd-status documents:

- `scripts/sd-ai-command-pack-status.py:519` — `task["status"] == "in_progress"`
- `scripts/sd-ai-command-pack-fleet-controller.py:911` — `lane["status"] == "waiting"`
- `scripts/sd-ai-command-pack-review.py:1108` — `dispatch.get("status")`
- `scripts/sd-ai-command-pack-work-loop.py:499` — `state["status"] not in STATUSES`
- `scripts/sd-ai-command-pack-status.py:2259` — `item.get("status") == "available"`

None of these confuse anyone. `task["status"]` is unambiguous *because it is
qualified by the object it hangs off*. R1 as written — "`status` is reserved for
an embedded sd-status document" — would rename all of them, which is a
several-hundred-site refactor with no confusion resolved and R5's dual-emit
obligation attached to each.

**The rule that actually fixes the finding:** at the **top level of an emitted
payload**, `status` means an embedded sd-status document and nothing else; a
verdict is `outcome`. Nested per-entity state keeps `status` when its owning
object disambiguates it. `review-local.py:2041`'s `"status": row["status"]` is
inside a `providers[]` row, so it is already qualified — the renaming case there
is weaker than the PRD's R1 implies, and worth re-deciding rather than assuming.

The genuine top-level collisions are exactly two, both confirmed:

1. `housekeeping-result.py:358-359` — `"status": status` (a whole sd-status
   document) and `"outcome": classify_outcome(...)` returning
   `{"status": <enum>, "reasonCodes": [...]}` (`:258`). Same document,
   `result["status"]` is a document and `result["outcome"]["status"]` is an enum.
2. `review-local.py:2035` vs `:2064` — `"outcome": receipt["outcome"]` in
   `_remote_summary` and `"status": receipt["outcome"]` in `_report`. Identical
   source value, two key names.

Scoping R1 to envelopes reduces this task from "several hundred renames" to
"two payloads plus their consumers" — which is what the evidence actually
supports.

## Consumer enumeration (R6 / AC6)

Every reader of a key this task would rename, with `file:line`:

### `outcome.status` / `outcome.reasonCodes` (housekeeping)

| reader | what it reads |
|---|---|
| `.agents/skills/sd-housekeeping/SKILL.md:75` | "Interpret its `status`, `reasonCodes`" |
| `.agents/skills/sd-housekeeping/SKILL.md:113` | "it is additive and never changes `outcome`" |
| `.agents/skills/sd-housekeeping/SKILL.md:120` | "`outcome.status` is `clean`, `blocked`, `indeterminate`, or `failed`" |
| `.agents/skills/sd-housekeeping/SKILL.md:121` | "stable `outcome.reasonCodes`" |
| `.agents/skills/sd-housekeeping/SKILL.md:130` | "A clean result has `outcome.status: clean`" |
| `docs/SD_AI_COMMAND_PACK.md:1154` | `environmentBlocks` array in the `--json` result |

### `{status, reasonCodes}` verdict shape (eligibility family)

| reader | what it reads |
|---|---|
| `scripts/sd-ai-command-pack-pr-eligibility.py:1254` | `result.get("reasonCodes")` |
| `scripts/sd-ai-command-pack-pr-eligibility.py:1257` | `result.get("status", "indeterminate")` |
| `scripts/sd-ai-command-pack-pr-eligibility.py:246` | `finishWorkReceipt["reasonCodes"]` |
| `scripts/sd-ai-command-pack-pr-eligibility.py:393`, `:403` | `observed.get("reasonCodes")` |
| `scripts/sd-ai-command-pack-housekeeping-result.py:186` | `eligibility["reasonCodes"]` validation |
| `scripts/sd-ai-command-pack-housekeeping-result.py:233` | `eligibility.get("reasonCodes", [])` |
| `scripts/sd-ai-command-pack-review-preflight.mjs:601` | emits `reasonCodes` |

One correction: the PRD describes `pr-eligibility.py:1257` as reading "the
`classify_outcome` shape". It reads the **eligibility evaluator's own** result,
which happens to have the same `{status, reasonCodes}` shape. The point survives —
a bare `status` is an enum here and a document there — but eligibility is a
sibling producer of that shape, not a consumer of housekeeping's.

### review-local report top-level verdict (renamed `status` -> `outcome`)

| reader | what it reads | disposition |
|---|---|---|
| `scripts/sd-ai-command-pack-review.py:1822` | `local.get("status")` — the report envelope verdict | migrated to `local.get("outcome", local.get("status"))` |
| `scripts/sd-ai-command-pack-review-local.py:_print_human` | `report["status"]` human line | migrated to `report["outcome"]` |
| `tests/test_review_stage.py` (multiple) | `report["status"]` assertions | unchanged; the deprecated alias keeps them green for the window |

Not renamed (nested per-entity state, kept per the envelope rule):

| reader | what it reads |
|---|---|
| `scripts/sd-ai-command-pack-review.py:837` | `receipt.get("outcome")` — receipt-level verdict, already `outcome` |
| `scripts/sd-ai-command-pack-review.py:1577` | re-emits `"status": row.get("status")` — per-provider attempt state inside `providers[]` |

Every `.agents/skills/**` path above ships to **11 platform roots** via
`manifest.json`, so each prose reference is eleven files after `make sync`.

## The consumer that changes the rollout shape

`.agents/skills/sd-housekeeping/SKILL.md:120` names the key path *and* enumerates
the enum values, in prose, for an agent to follow. That is a consumer R5's
dual-emit window does not protect:

- A **code** consumer reading a removed key raises `KeyError` or takes a default —
  loud, or at least deterministic.
- An **agent** consumer reading prose that names a key the payload no longer
  carries does not error. It improvises.

So the skill text must be updated in the **same release** that introduces the new
key — not at the end of the deprecation window. Dual-emit protects code
consumers; prose consumers need the doc and the payload to agree at every commit.
This is the single most important constraint in the task and the PRD does not
state it.

## R2 — subsets, not a merge

The five vocabularies stay distinct; only the common core is shared. From the
PRD's own evidence, `failed` appears in more than two and `clean`, `blocked`,
`skipped` each appear in two with compatible meaning. That is the core. Nothing
else overlaps, so the shared definition is small — roughly four members — and the
per-domain sets extend it.

The enforcement mechanism matters more than the enum: a test that fails when a
domain declares a verdict absent from the core *without an explicit opt-out*
(AC2). Without the opt-out escape hatch the test blocks legitimate values like
`at-target`; without the test the subsets drift straight back apart.

## R3 — `"ok"` and `"recorded"`

`sd_ai_command_pack_lib.py:697` emits `"ok"`; `record-session.py:255` emits
`"recorded"`. Both are success verdicts spelled differently from `clean` and
`passed`. Mapping them onto the core is the default; keeping them needs a written
reason. Note these are top-level payload keys, so they are in scope under the
envelope rule.

## Rollout and rollback

Per payload, not per key:

1. Emit the new key alongside the old; update the shipped skill prose and
   `docs/SD_AI_COMMAND_PACK.md` in the same commit.
2. Ship one full version with both.
3. Record a `removed_version` and drop the old key in a later release.

Rollback within a release is a plain revert while both keys are live. After step
3 it is a release-level rollback — which is the argument for keeping the window
honest rather than short.

## Risk

The failure mode is a rename that passes every test because the tests were
updated alongside it, while an agent following month-old skill prose silently
reads a missing key and reports a plausible wrong verdict. The mitigation is the
same-commit rule above, plus a fixture consumer written against the *old* names
that must keep passing for the whole window (AC5).
