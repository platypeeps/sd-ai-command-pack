---
name: sd-rust-quality
description: Use when writing, editing, or planning Rust code — .rs files, Cargo.toml, lint configuration, or clippy fixes — to hold the idiomatic bar covering error type design, clippy posture, Rust API guidelines conformance, naming, and recurring anti-patterns.
---

# sd-rust-quality

Hold every Rust change to the idiomatic bar. Prefer the named idioms, reject
the named anti-patterns, and keep error types, lints, and names conforming
to the Rust API guidelines. The recurring failures this skill exists to stop
are the ones models repeat: cloning past the borrow checker, speculative
fallbacks, verbose match chains, and weak error modeling.

## When to use

Use for any Rust authoring or editing work: new code, refactors, clippy
cleanups, `Cargo.toml` changes, and lint configuration. Load it alongside
whatever task is producing the code.

Do not use it to model a new type surface — that is `sd-rust-design` — or
to lay out modules and visibility — that is `sd-rust-modules` — or for
async structure — that is `sd-rust-async`. For judging a finished diff,
`sd-rust-review` applies this bar as a local lens, and the `sd-review` lane
owns the verdict.

## Arguments

None.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Establish the posture before editing: edition, workspace lint
   configuration, existing error-handling style, and the conventions the
   surrounding code already follows. Match them; do not import a foreign
   style into a consistent codebase.
2. Design errors deliberately. Libraries expose concrete error enums
   (derive-based error types in the `thiserror` style); applications may
   collapse to a catch-all (`anyhow` style) at the top. At every public
   boundary the error enum distinguishes the failure modes a caller acts
   on differently and collapses the ones it must not. No boxed
   `dyn Error` in library signatures; convert at boundaries with
   `#[from]` and `.map_err()` so low-level errors never leak into domain
   signatures. `#[from]` is the weaker of the two: it keeps the source
   type inside the variant, so the wrapped type joins the crate's public
   contract. Use it where that type is one you are willing to publish and
   version; map to an owned variant where it is not.
3. Prefer the named idioms:
   - `transpose()` for `Option<Result<T, E>>` conversions;
   - `Arc::clone(&x)` over `x.clone()` on reference-counted types;
   - `if let` over a single-arm `match`;
   - `.to_owned()` over `.to_string()` on `&str`;
   - `.map_err(Variant)` over `.map_err(|e| Variant(e))` — a tuple
     variant is already a constructor function, so the closure only
     restates it; where the variant also derives `#[from]`, drop the
     `map_err` and let `?` convert;
   - explicit enum arms over `_ =>` on enums you own;
   - a type alias over suppressing the type-complexity lint;
   - newtype wrappers over stringly-typed parameters;
   - sealed traits for public API stability;
   - `#[derive]` over hand-written impls the derive already covers.
4. Reject the recurring anti-patterns on sight:
   - a `clone()` inserted to satisfy the borrow checker instead of
     restructuring ownership — the top model-authored smell;
   - sprawl: a helper, trait, or abstraction serving a single call site;
   - speculative fallback paths for failures that have never manifested —
     log, test, and add the fallback when reality demands it;
   - matching the same value three or more times in sequence — the data
     model is wrong; fix the enum or use combinators;
   - `use` of a crate that is not in `[dependencies]` — compiling through
     a transitive dependency is fragile;
   - guard conditionals or temporaries created only to start an iterator
     chain — chain directly on the expression.
5. Keep comments earning their place: they explain why when it is not
   apparent, never how. No restating types or signatures, no narration of
   the next line, no change narration ("previously", "now uses"), no
   descriptions of behavior owned by other code — all of it goes stale.
6. Name to the Rust API guidelines: `as_`/`to_`/`into_` by conversion
   cost, iterator methods `iter`/`iter_mut`/`into_iter`, getters without
   a `get_` prefix, no stuttering with the module path.
7. After adding an enum variant, build the whole workspace immediately
   and fix every non-exhaustive match in one pass, not one per build
   cycle.
8. Keep the clippy baseline honest: lint groups at warn in workspace
   configuration, stricter lints adopted progressively, and every
   `#[allow]` carrying a written reason or replaced with `#[expect]`.

## Safety rules

- Never silence a lint wholesale to make a diff green; suppression is
  per-site, reasoned, and visible in the change.
- Stay inside the requested scope: apply the bar to the code being
  written or edited, and report — do not drive-by rewrite — conforming
  neighbors that merely look improvable.
- Never delete behavior while "cleaning up"; idiom fixes preserve
  semantics, and anything that does not is a design change to call out.
- This skill informs authoring. It carries no review verdict; the
  `sd-review` lane owns review outcomes.

## Final report

- **Posture** — edition, lint configuration, and error-handling style the
  work conformed to;
- **Idioms applied** — the named preferences used, with locations;
- **Anti-patterns removed** — each rejected pattern found, its location,
  and the repair;
- **Error design** — boundary error types touched and what each variant
  distinguishes;
- **Lint status** — build and clippy results, plus every suppression that
  remains and its reason;
- **Open items** — conforming-but-improvable code observed and left
  untouched, for the user to decide on.
