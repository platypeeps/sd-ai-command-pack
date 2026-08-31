---
name: sd-rust-modules
description: Use when planning, creating, splitting, or reorganizing Rust modules and crates — mod declarations, file layout, visibility, re-export facades, crate boundaries — or when a module is growing into a god module.
---

# SE Rust Modules

Keep module and crate boundaries deliberate. Files are organized by domain
concept, visibility starts closed and widens only for a named consumer, and
the public API stays flat behind re-export facades while the internal tree
nests freely.

## When to use

Use when adding, splitting, moving, or renaming Rust modules and files;
when deciding visibility for an item; when shaping a crate's public API
surface; or when a module has grown past cohesion into a god module.

Do not use for the code inside the modules — idioms and anti-patterns are
`sd-rust-quality`, type modeling is `sd-rust-design`. For judging a
finished diff, `sd-rust-review` applies this bar as a local lens, and the
`sd-review` lane owns the verdict.

## Arguments

None.

This skill takes no `key=value` arguments.
Unknown argument names are an error — stop and report them before starting.

## Workflow

1. Read the existing layout first and match it. A codebase that uses
   `mod.rs` keeps using `mod.rs` when you edit it; modernize only on an
   explicit refactor request, never as a drive-by.
2. For new code, use the sibling file pattern — no `mod.rs`:

   ```text
   src/
   ├── lib.rs
   ├── billing.rs          <- declares `mod invoice;`
   └── billing/
       └── invoice.rs
   ```

3. Default visibility closed and widen deliberately, one rung at a time.
   Check first whether widening is needed at all: a descendant module
   already sees its ancestors' private items, so a child consuming a
   parent's item needs no marker and adding one only widens the surface.
   Otherwise: private until a consumer outside that subtree exists,
   `pub(super)` when the only consumer is the parent module,
   `pub(in path)` when it is one known ancestor, `pub(crate)` when the
   consumer is elsewhere in the crate, and bare `pub` only when an
   external consumer needs it. Reaching straight for `pub(crate)` when
   `pub(super)` would do is the same overshoot as reaching for `pub`. Every widening names the consumer that forced it —
   a `pub` with no external caller is API surface you now maintain for
   free.
4. Keep the public API flat behind facades. Internal trees nest as deep
   as the domain wants; the parent re-exports what callers need, so they
   write `use crate::billing::Invoice`, never a path through the internal
   tree. Removing a re-export is a breaking change; treat it as one.
5. Co-locate tightly coupled types. An `Invoice`, its state enum, and its
   error type belong in one file — not scattered across `models.rs`,
   `enums.rs`, and `errors.rs` buckets. No `utils` dumping ground: a
   helper belongs with the domain concept it serves.
6. Name without stuttering. The module already provides the namespace:
   `billing::Invoice`, not `billing::BillingInvoice`; `config::Source`,
   not `config::ConfigSource`.
7. Split a module only for cause: the file exceeds roughly 400 lines
   **and** contains distinct domain concepts, or a privacy boundary is
   needed to hide internal helpers from the rest of the crate. Never
   split on size alone — a cohesive 500-line module beats three
   fragmented ones. When splitting, cut by domain concept, and keep the
   facade so callers see no path change.
8. Reach for a new crate only when there is a real boundary to enforce:
   an independently reusable unit, a compile-time firewall, or a
   dependency direction the type system should police. A crate created
   for tidiness is a version number and a build unit you pay for forever.

## Safety rules

- Moving files and renaming modules must preserve behavior; verify the
  crate still builds and its tests still pass after every move, and
  report the verification.
- Never widen visibility to make a test or a quick call site compile;
  widen for a named consumer or restructure so the narrow visibility
  works.
- Never break the public API silently: removed or moved re-exports,
  renamed public modules, and path changes are breaking changes the user
  must see listed.
- Stay inside the requested scope; a layout defect observed outside it is
  reported, not repaired in passing.
- This skill informs structure. It carries no review verdict; the
  `sd-review` lane owns review outcomes.

## Final report

- **Layout** — the resulting module tree and where it intentionally
  matches legacy conventions;
- **Visibility ledger** — each item whose visibility changed, the new
  level, and the consumer that justified it;
- **Facade** — the public paths callers use and the re-exports backing
  them;
- **Splits and merges** — each module split or merged, the domain-concept
  cut line, and why size alone was not the reason;
- **Breaking changes** — public paths that changed, or an explicit
  statement that none did;
- **Verification** — the build and test evidence that the reorganization
  preserved behavior.
