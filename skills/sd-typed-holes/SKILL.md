---
name: sd-typed-holes
description: Use when starting a Rust feature, module, or rewrite skeleton-first — design the types and signatures, land a compiling skeleton whose bodies are todo!() as its own commit, then fill the holes in a separate later pass; never mix the two.
---

# SE Typed Holes

Split Rust work into two passes that never mix. First lay the complete type
surface — real signatures, real types, `todo!()` bodies — and prove it
composes under check and lint before any behavior exists. Then fill the
holes one at a time against that fixed surface. The compiler reviews the
design in the first pass; the second pass cannot silently change it.

## When to use

Use when starting a Rust feature, module, or rewrite where the type surface
deserves review before behavior exists, when splitting Rust work into
independently deliverable units, or when delegating implementation to
executors that must not redesign the surface they fill.

Do not use for one-line fixes or edits inside an existing surface, and do
not use it to model the types themselves — `sd-rust-design` owns the
modeling rules the skeleton must satisfy.

## Arguments

None.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Design the type surface with `sd-rust-design`: states as enums,
   transitions as consuming methods, constrained constructors returning
   `Result` with their error enums fully written. Record, per public
   type, the one business rule it enforces and the illegal state it
   forbids.
2. Lay the skeleton — the full surface and nothing else:
   - real signatures, derives, conversion impls, and leaf types; no
     placeholder `String` standing in for a type not yet written;
   - `todo!()` only in bodies with real behavior — parsing, rendering,
     assembly, anything with a decision in it;
   - trivial accessors implemented, not held open: a field read left as
     `todo!()` hides surface from the compiler instead of exposing it.
3. Mark the holes so they ask to be removed:
   - each `todo!()` function with parameters carries
     `#[expect(unused_variables, reason = "hole; filled by <unit>")]` —
     once the lint stops firing the marker warns; leave a hole unmarked
     wherever the lint could not fire in the first place and the
     expectation would go unfulfilled the moment it was written — a
     zero-parameter hole, a receiver-only one (`unused_variables` never
     fires on `self`), and one whose parameters are all
     underscore-prefixed, which is the same suppression by another name;
   - the module enters with `#![allow(dead_code)]`, removed slice by
     slice as the surface goes live;
   - both markers get explicit removal steps in the fill plan — a filled
     body that still ignores a parameter keeps its marker silent, so
     each fill sweeps by hand.
4. Gate the skeleton alone: workspace check and clippy with warnings
   denied, plus a format check, all green with every behavioral body
   still `todo!()` — the trivial accessors step 2 asks you to implement
   stay implemented. Then propose the skeleton as its own commit, so the
   reviewed design is a retrievable git object rather than a
   conversation, and let the user make it. Committing is theirs to
   authorize; this workflow reaching step 4 is not that authorization.
5. Track the holes deterministically — `todo!()` is a diverging panic the
   compiler happily accepts, so nothing tracks it for you. Prefer the
   clippy lint for `todo!()`: warn during the fill phase, deny as the
   completion gate. A `grep -rn 'todo!('` baseline is the fallback, and
   it is a lower bound rather than a census — it misses a hole written
   `todo! ()` or produced by a macro, and counts occurrences in comments
   and string literals. Take the baseline at the skeleton commit, account
   for every changed line per fill, and let the lint, never the grep,
   decide that the holes are closed.
6. Review the skeleton before any body lands: apply the
   `sd-rust-review` probe lens to the skeleton diff and route the change
   through the `sd-review` lane, which owns the verdict. Design repairs
   land as skeleton amendments, before filling starts.
7. Fill the holes in a later pass, one body at a time: run the check
   after each fill to narrow the next hole's types, sweep the filled
   function's marker, account for its inventory lines, and hold each
   body to `sd-rust-quality`. A fill that needs a signature, derive, or
   type change has found a skeleton defect — stop, amend the skeleton as
   its own reviewed change, then resume filling. Never let a fill mutate
   the surface in passing.
8. Optionally delegate the passes to the pack's agent trio: the
   `sd-rust-write` agent lays the skeleton, the `sd-rust-fill` agent
   fills named holes against a fixed surface, and the `sd-rust-reviewer`
   agent examines each pass. When the work spans multiple Trellis units,
   split it as one skeleton unit plus one unit per fill batch via the
   `task.py` surfaces, and gate each unit with `trellis-check`.
9. Close out: remove the remaining dead-code allowance, flip the hole
   lint to deny or show the grep returning nothing, and confirm the
   surface carries no marker whose reason is stale.

## Safety rules

- Never mix the passes: a change that both alters the type surface and
  implements behavior defeats the point and must be split before it
  lands.
- Never let a fill silently change a signature, derive, visibility, or
  error variant; surface changes are skeleton amendments with their own
  review.
- Do not over-claim what the green skeleton proves: it shows the design
  composes, not that behavior is correct — derives and runtime semantics
  still need inspection and tests.
- Keep the hole inventory honest: no fill unit closes while a hole it
  owns survives, and no marker outlives the truth of its reason.
- Review verdicts on either pass belong to the `sd-review` lane; this
  workflow schedules reviews, it does not decide them.

## Final report

- **Surface summary** — the public types with their business rules and
  forbidden states, per the design record;
- **Skeleton commit** — the commit that carries the surface and its
  green check, lint, and format evidence;
- **Hole inventory** — holes opened, holes filled, holes remaining, and
  the tracking mechanism (lint level or grep baseline);
- **Marker status** — expect-markers and dead-code allowances still
  standing and the units that will remove them;
- **Fill progress** — bodies filled this pass and the per-fill check
  results;
- **Handoffs** — units delegated to `sd-rust-write`, `sd-rust-fill`, or
  `sd-rust-reviewer`, and reviews routed to the `sd-review` lane.
