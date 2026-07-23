# Implementation plan: review-learnings write safety

## 1. Freeze Current Update Semantics

- Map target resolution, section parsing, parent creation, and write behavior.
- Add baseline scan/update fixtures before changing the interface.

## 2. Add Explicit Modes And Containment

- Make scan the default and update explicit.
- Add canonical repository containment and symlink-aware rejection.
- Add the exceptional exact-target external authorization path.

## 3. Make Writes Atomic

- Validate type/content, construct the complete result, and atomically replace
  the target only after a final path recheck.
- Emit structured before/after evidence and reason codes.

## 4. Strengthen The Skill Contract

- Add arguments, safety, mutation, interaction, failure, and report sections.
- Use the portable structured-question contract for external targets only.

## 5. Validate

- Run local/external/symlink/race/interruption/encoding fixtures, generated
  parity, `make sync`, and `make check`.

## Stop Points

- Stop if the external path cannot be bound to an exact resolved identity.
- Stop if an atomic update would cross filesystems; report and require a safer
  explicit workflow instead of degrading to a partial-copy risk.
