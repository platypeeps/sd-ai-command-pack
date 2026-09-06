---
name: sd-rust-design
description: Use when designing, writing, or restructuring Rust types and domain models — a new struct or enum, a state machine, typestate transitions, newtype wrappers, or a public API's type surface — and the goal is a design whose illegal states are unrepresentable.
---

# sd-rust-design

Model the domain with types before writing any logic. Enums carry states and
variants, structs carry the data of a single state, and newtypes enforce
semantic boundaries. The compiler is the first reviewer: a type surface that
composes under check and lint before any behavior exists catches design
errors at the cheapest possible moment.

## When to use

Use when introducing or reshaping a Rust type surface: a new struct or enum,
a domain model, a state machine, a constrained value type, or the shape of a
public API. Use it as the modeling reference while laying a skeleton under
`sd-typed-holes`.

Do not use for module and crate layout — that is `sd-rust-modules` — or for
async and concurrency structure — that is `sd-rust-async`. For judging a
finished diff, `sd-rust-review` applies this bar as a local lens, and the
`sd-review` lane owns the verdict.

## Arguments

None.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. List the domain's states, transitions, and invariants before touching
   code. Every rule you can name is a candidate for a type that enforces
   it; a rule with no enforcing type is a runtime bug waiting for a caller.
2. Make illegal states unrepresentable. Treat every `Option<T>` field and
   boolean flag as a potential leak: replace state-dependent optionals
   with enum variants that each carry exactly the data their state needs,
   and model "at least one of" with variants rather than runtime
   assertions.

   ```rust
   // Weak: optional fields only meaningful in some states.
   struct Connection {
       socket: Option<TcpStream>,
       error: Option<String>,
   }
   // Strong: each variant carries exactly its own data.
   enum Connection {
       Idle,
       Connected { socket: TcpStream },
       Failed { error: String },
   }
   ```

3. Encode state machines as typestate. Each state is its own type; a
   transition consumes the current state and returns the next, so the
   compiler enforces the transition graph. "Verified" is a transition that
   produces a new type, not a boolean property on the old one.
4. Choose the wrapper discipline per value:
   - a newtype with a public field when every inner value is valid and
     only identity confusion is at stake (a user id versus a team id);
   - a constrained type with a private field and a single validating
     constructor when only some values are valid (email format, non-zero
     port, bounded range).
   Implement `Display` and `AsRef` as the value warrants; never
   `DerefMut`, which bypasses the constraint. Keep test-only constructors
   behind a gate: `#[cfg(test)]` reaches unit tests in the same crate and
   nothing else, so a `tests/` integration test that needs one requires a
   `#[cfg(feature = "test-util")]` constructor instead. Nothing turns that
   feature on for you — no profile implies it — so the test run enables it
   explicitly (`cargo test --features test-util`, or a self path
   dev-dependency that carries it). Pick the gate from who must call it,
   and never ship an ungated one.
5. Parse, don't validate. Fallible constructors return
   `Result<Self, Error>` with the error enum written up front; downstream
   code accepts only already-valid types, so no check is ever repeated and
   no validate-then-use gap can open.
6. Compose errors railway-style: propagate with `?`, convert at
   boundaries with `.map_err()` or, where the crate derives its error
   types with `thiserror` or a similar macro, `#[from]` — that attribute
   is the derive's, not the language's, so name the dependency before
   reaching for it. Keep low-level error types out of domain signatures.
   Use combinators for linear `Option`/`Result` chains and `match` where
   branching is what the code is doing — a two-variant match that stays
   exhaustive beats a combinator chain that hides the second arm. Keep
   exhaustiveness either way: no `_` wildcard on enums you own.
7. Treat `.clone()` as a design decision, not a compiler fix. When the
   borrow checker objects, try in order: restructure scope, take a
   reference, narrow the borrow, `Cow` for sometimes-owned data,
   `Arc`/`Rc` for genuinely shared ownership — and only then clone, with
   a comment saying why.
8. Mark intent on the surface: `#[must_use]` where ignoring a return is a
   bug, `#[non_exhaustive]` on public enums that may grow, concrete error
   enums rather than boxed trait objects in library code.
9. Compile and lint the type surface before implementing behavior.
   Inspect every derive whose behavior is not obvious from the type —
   an untagged serde enum with overlapping variant shapes deserializes by
   declaration order at runtime and the compiler never flags it. For
   skeleton-first delivery, hand the surface to `sd-typed-holes`.

## Safety rules

- Never invent a domain rule to justify a type; every constraint must
  trace to a stated requirement or an observed invariant in the sources.
- Never weaken an existing invariant while reshaping types. Removing a
  validating constructor or exposing a private field is a design change
  the user must see called out, not a side effect.
- Do not claim compiler guarantees the compiler does not give: derive
  behavior, serialization, and runtime semantics need inspection, not
  assertion.
- This skill informs design and authoring. It carries no review verdict;
  the `sd-review` lane owns review outcomes.

## Final report

- **Type map** — each public type, the single business rule it enforces,
  and the illegal state it forbids;
- **Transitions** — the state types and the consuming transitions between
  them, with any path the compiler now forbids;
- **Validation boundary** — where raw input becomes valid types and which
  error enum reports each failure;
- **Ownership notes** — clones that survived the avoidance ladder and why;
- **Open risks** — derives or runtime behavior the type surface cannot
  prove, flagged for review.
