# Unify the outcome and status vocabulary across script payloads

## Goal

`status` and `outcome` are used inconsistently enough that a consumer cannot tell
from a key name whether it is reading a verdict enum, a whole document, or a
per-attempt state — and in one payload both meanings of `status` appear at once.
Give the pack one verdict vocabulary and one naming rule, without breaking any
shipped consumer.

## Origin

Created 2026-07-28 from the repo audit with explicit user consent. Owns finding
A-077 (P2 · M · Plausible · design).

Post-completion residue of `07-28-analyze-recurring-trellis-workflow-instability`:
that task's design package A fixed only housekeeping's result contract and did
not unify the sibling vocabularies or the bare-string producers, and its
remediation child is archived. No task owned this.

## Evidence

The collision is real but narrower than "one payload assembled from four
producers." Precisely:

1. **Inside one document, `status` means two things.**
   `scripts/sd-ai-command-pack-housekeeping-result.py:358` sets `"status": status`
   where `status` is a whole sd-status document, and `:359` sets
   `"outcome": classify_outcome(...)` where `classify_outcome` (`:221`) returns
   `{"status": <enum>, "reasonCodes": [...]}` (`:258`). So the same result has
   `result["status"]` (a document) and `result["outcome"]["status"]` (an enum).

2. **The same value is emitted under both names, in one file.**
   `scripts/sd-ai-command-pack-review-local.py:2035` emits
   `"outcome": receipt["outcome"]`; `:2064`, in `_report`, emits
   `"status": receipt["outcome"]` — identical source, different key. The first
   dict also nests `"status": row["status"]` at `:2041` for per-provider attempt
   state, a third meaning in the same literal.

3. **Consumers must already know which `status` they hold.**
   `scripts/sd-ai-command-pack-pr-eligibility.py:1257` reads
   `result.get("status", "indeterminate")` beside `result.get("reasonCodes")` —
   the `classify_outcome` shape, not the document shape.

4. **Five verdict vocabularies, no shared enum.**
   - `classify_outcome` (housekeeping): `clean, blocked, indeterminate, failed`
   - `review-local.py:58` `OUTCOMES`: `clean, findings, unavailable, failed, cancelled, skipped`
   - `fleet-timing.py:62` `STAGE_OUTCOMES`: `passed, failed, skipped, interrupted`
   - `fleet-timing.py:64` `CONSUMER_OUTCOMES`: `at-target, refreshed-merged, pr-open, skipped, failed, blocked`
   - bare strings declared by no enum: `"blocked"` (`sd_ai_command_pack_lib.py:691`,
     `work-loop.py:2843`, `update-spec-kb.py:1542`, `record-session.py:292`),
     `"ok"` (`sd_ai_command_pack_lib.py:697`), `"recorded"` (`record-session.py:255`)

   Only `failed` appears in more than two. `clean`, `blocked`, and `skipped`
   each appear in two with compatible meaning; nothing else overlaps.

## Requirements

- R1: one naming rule, written down and applied. `outcome` is the verdict;
  `status` is reserved for an embedded sd-status document. Anything that is
  neither — per-provider attempt state at `review-local.py:2041`, for example —
  gets a name that is neither (`attemptState`, `providerState`) rather than
  reusing `status`.

- R2: one shared verdict enum in `scripts/sd_ai_command_pack_lib.py`, with the
  per-domain sets defined as explicit subsets of it rather than as independent
  frozensets. The five vocabularies are **not** merged into one flat list: a
  fleet consumer legitimately reports `at-target`, and a review stage
  legitimately reports `findings`. What must be shared is the common core and
  the guarantee that a value means the same thing everywhere it appears.

- R3: the bare-string producers declare their vocabulary. `"ok"` and
  `"recorded"` are currently emitted by no enum and are synonyms for a success
  verdict that other producers spell `clean` or `passed`. Either map them onto
  the shared core or record why the domain needs a distinct spelling.

- R4: housekeeping's own document stops carrying two meanings of `status`.
  Rename the embedded document key, or lift the enum out of `outcome`, or both —
  but `result["status"]` and `result["outcome"]["status"]` must not both exist
  with different types after this lands.

- R5 (hard constraint): **backward compatibility.** These payloads cross into
  shipped skills, the fleet consumer path, and `--json` output that agents parse.
  Every rename ships additively first: emit the new key alongside the old, mark
  the old deprecated in `docs/SD_AI_COMMAND_PACK.md`, and remove it only in a
  later version with a recorded `removed_version`. No consumer may break on the
  version that introduces the rename.

- R6: enumerate the consumers before changing any producer. A rename with an
  unenumerated reader is a silent break — `pr-eligibility.py:1257` reads a key
  the producer never names in the same file, so grep-by-key is the only way to
  find these. The consumer list belongs in `design.md`.

## Acceptance Criteria

- [ ] R1/R4: no payload in `scripts/` contains a `status` key whose value type
      differs from another `status` key in the same document; asserted by a test
      that walks the emitted shapes, not by inspection.
- [ ] R2: the per-domain outcome sets are derived from one lib-level definition,
      and a test fails if a domain declares a verdict absent from the shared core
      without an explicit opt-out.
- [ ] R3: `"ok"` and `"recorded"` either resolve to a declared enum member or
      carry a recorded justification in this PRD.
- [ ] R5: for one full version, every renamed key is emitted under both names,
      and a fixture consumer written against the old names still passes.
- [ ] R6: `design.md` lists every reader of every key this task renames, with
      `file:line` for each.
- [ ] Template/generated parity holds and `make sync` passes.
- [ ] `make check` passes.
- [ ] Changelog + version; deprecations recorded with a `removed_version`; fleet
      rollout via normal refresh.

## Notes

- Audit source: `.trellis/audit/report-2026-07-28.md` — A-077 (P2 · M ·
  Plausible · design).
- The audit's `fix:` line — "standardize on top-level `outcome: {status, reasonCodes}`"
  — reproduces the exact collision it is trying to fix: it puts an enum named
  `status` inside `outcome` while `status` also names the embedded document.
  That is today's `classify_outcome` shape (`:258`). R1/R4 supersede it: the
  enum inside `outcome` should not be called `status`.
- The audit's framing said four producers compose one payload. Verified 2026-07-28:
  they do not. `work-loop.py:2843`, `update-spec-kb.py:1542`, and
  `record-session.py:292` emit *separate* top-level payloads that happen to share
  a key name. The genuine single-payload collision is housekeeping's, item 1
  above. Scope this task to the naming contract across payloads, not to a
  fictional merge.
- Effort is M in the audit, but R5 and R6 make the real cost the consumer
  enumeration and the deprecation window, not the renames.
- **R1 needs a scope, measured 2026-07-28.** `scripts/`, `.github/scripts/` and
  `installer/` contain 148 `status` reads against 16 `outcome` reads, and the
  large majority are per-entity state on a nested object (`task["status"]`,
  `lane["status"]`, `dispatch.get("status")`, `item.get("status")`) that nothing
  confuses with a verdict. Applied literally, R1 renames all of them and attaches
  R5's dual-emit obligation to each. `design.md` scopes the rule to **payload
  envelopes** — top-level keys of emitted documents — which reduces the task to
  the two genuine collisions the Evidence section names.
- **The rollout constraint the PRD omits.**
  `.agents/skills/sd-housekeeping/SKILL.md:120` names `outcome.status` and
  enumerates its four values in prose, for an agent to follow, and each such
  reference is 11 files after `make sync`. A dual-emit window protects code
  consumers, which fail loudly on a missing key; an agent reading stale prose
  does not fail, it improvises. Shipped skill prose must be updated in the **same
  commit** as the payload change, not at the end of the deprecation window.
- Minor correction: `pr-eligibility.py:1257` reads the **eligibility evaluator's
  own** `{status, reasonCodes}` result, not housekeeping's `classify_outcome`
  output. Same shape, sibling producer. The Evidence item 3 point survives.
- Planning complete 2026-07-28: `design.md` and `implement.md` added.
  `design.md` carries the R6 consumer enumeration.
