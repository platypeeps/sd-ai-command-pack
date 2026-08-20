# Bare-filename documentation references are silently unchecked

## Goal

Widen the documentation path-reference check so a bare filename that is *cited
as a location* is validated, rather than skipped because it carries no directory
prefix.

## Rescoped 2026-08-20 — and why

The original requirements below asked for a basename-existence rule. That rule
was measured against this repository before being planned, and it fails its own
motivating example.

The original PRD's headline case was an unqualified `review.py` reference that
Copilot flagged on PR #339. There is no tracked file named `review.py`. The
real path is `scripts/sd-ai-command-pack-review.py`. Under a plain
basename-existence rule the gate would report the PRD's own example as a
missing path — the document describing the bug would fail the check it asks
for, which is the same self-defeat `08-18-preflight-path-refs-ignore-aware`
recorded twice.

That is not an isolated case. The pack's own prose systematically drops the
`sd-ai-command-pack-` prefix when naming its scripts: `full-check.sh`,
`install-audit.py`, `record-session.py`, `shell-lib.sh`, `work-loop.py`,
`fleet-controller.py`, `toolchain.sh`. These are deliberate shorthand, not
typos. A rule that cannot follow the pack's own naming convention reports 160
references across 43 documents as broken, none of which are.

### Measured blast radius

Two measurement runs are checked in under `research/` and are re-runnable.
Numbers below are from `09993578`, 287 guard files; they drift by a few percent
as tasks archive out of the guard corpus, and the implementation re-measures
rather than trusting this snapshot. The classification is stable across runs.

| Rule | Newly passing | Declined | Newly **failing** |
|---|---|---|---|
| Plain basename existence | 179 | 328 ambiguous | **160 refs / 43 files** |
| \+ pack-prefix expansion | 276 | 328 ambiguous | 63 refs / 26 files |
| \+ locator/noun split (proposed) | **107** locator-form | 556 noun-form or unsuffixed | **4 refs / 3 files** |

The 107 is exact, not a floor: 95 locator-form references resolve to a unique
or mirrored candidate set, and a further 12 — across `SKILL.md`, `design.md`,
`implement.md` and `prd.md` — resolve to several genuinely distinct files and
pass under R3. 107 + 4 + 556 = 667, the whole skipped population.

Only the **4** is an invariant. Every other figure moves as tasks archive and as
these very artifacts add references to the corpus — it drifted three times
during planning. Re-measure; do not cite this table as current.

Of the 667 bare-filename references the gate skips today, exactly **four** are
cited in locator form — with a line or range suffix — and fail to resolve. All
four were inspected; each is a real, correctable case, and none is a typo:

| Reference, in | Why it does not resolve |
|---|---|
| `08-07-default-local-review-lanes/prd.md` | names a surface deleted by `07-24-remove-retired-review-surfaces` |
| `08-08-upstream-handoff-register/prd.md` | cites a file in the upstream Trellis repository |
| `08-09-deployment-thin-consumers/research/consumer-ci-usage.md` (twice) | cites a workflow in a consumer repository |

Line numbers are deliberately omitted: these documents move. The
`08-08-upstream-handoff-register` site shifted from line 78 to 103 during
planning, under a concurrent session.

Four annotations is a landable change. 160 failures is not, which is why the
original design was rejected.

### The requirement defect this exposes

Original R1 asks for a bare filename "passing when the file exists, failing
when it does not". Resolution here happens *through* an index of tracked files,
so "matches a tracked file" and "the file exists" are the same predicate — under
a basename rule nothing can ever fail, and R1 is unsatisfiable as written.
R1 is restated below in terms that can actually be met: the failing case is a
reference in **locator form** that resolves to nothing.

## Requirements

- **R1** — A bare filename cited in **locator form** (followed by a line or
  line-range suffix, as in `review.py:555`) is validated: it passes when it
  resolves to a tracked file, and **fails** when it resolves to nothing.
- **R2** — Resolution honours the pack's own naming convention. A bare name that
  matches no tracked basename is retried against the pack's script-name
  prefixes before being called unresolved. The transformation set is closed and
  enumerated in code — no open-ended substring or fuzzy-distance matching.
- **R3** — A name that resolves to more than one tracked path is **not** reported
  as missing, whether those paths are copies of one logical file or genuinely
  different files.
- **R4** — A bare filename **not** in locator form stays declined. Prose uses a
  bare filename as a noun far more often than as a path, and this class carries
  the names of things that deliberately do not exist.
- **R5** — Every class the *checker* declines is enumerated in code with a
  stated reason **and pinned by a test**. There are exactly three, all decided
  on shape: no line suffix, a `..` segment, an extension outside
  `bareReferenceExtensions`. Foreign-repository references are **not** among
  them — the checker has no notion of a foreign repository and must not be
  documented as if it did. They are handled per site by `[absent: <reason>]`,
  whose reason names the owning repository (operator decision 2026-08-07).
- **R6** — The existing corpus produces the same failure set before and after,
  except genuinely broken references. Each of the four newly-failing references
  is corrected or marked with `[absent: <reason>]` in the same change.
- **R7** — The change is shipped payload and reaches nine consumer repositories.
  Eligibility must not widen in a way that can turn a consumer's corpus red on
  prose this repository has never seen.
- **R8** — The check stays local and deterministic: no network, and no
  per-reference subprocess where one batched query answers the whole file set.
- **R9** — A malformed or unreadable configuration fails closed — the references
  stay checked rather than being silently treated as valid.

## Constraints

- `templates/` is the source of truth. Every shipped script exists in four
  copies refreshed by `make sync` and `make generate`; editing any other copy is
  a defect.
- **Eligibility never consults the index; resolution always does.**
  `shouldCheckDocumentationPathReference` decides *shape* only — no `/`, no
  `..`, a line/range suffix, an allowed extension. Whether a tracked file backs
  the name is answered later, by the resolver. This is what preserves R1's
  failing half: an unresolvable locator such as `nope-xyz.py:9` [absent: illustrative]
  is eligible, then reported missing. An eligibility gate that consulted the
  index would make "eligible" and "resolves" the same predicate, and nothing
  could ever fail.
- `resolveDocumentationReference`
  (`scripts/sd-ai-command-pack-review-preflight.mjs:5197`) is **not** exported
  today, though 40 siblings are. It must be exported, because R2 and R3 are
  claims about resolution and are otherwise only reachable end-to-end. The
  basename index is injected into it through the existing `options` argument so
  those assertions need no repository behind them.
- The `design.md` / `implement.md` and `.trellis/tasks/archive/` exemptions at
  `scripts/sd-ai-command-pack-review-preflight.mjs:3184-3194` keep their current
  behaviour.

## Acceptance criteria

Every criterion below must be able to fail against the *unmodified* checker.
Nothing bare is eligible today, so an assertion of the form
`shouldCheckDocumentationPathReference('review.py') === false` passes already and
proves nothing; each criterion is therefore phrased so the current code fails it.

- [ ] A test asserts a locator-form bare filename resolving to a tracked file
      **is eligible and passes**, and one resolving to nothing **is eligible and
      is reported missing** (R1). Both halves fail today: neither is eligible.
- [ ] A test asserts against the **exported** `resolveDocumentationReference`
      that `review.py:9` resolves via the `sd-ai-command-pack-` prefix, and that
      a name reachable only by substring or by an invented third prefix resolves
      to nothing (R2). Eligibility cannot carry this test — a near-miss name is
      eligible by shape, exactly as `nope-xyz.py:9` [absent: illustrative] is.
- [ ] A test asserts a name with several tracked matches resolves and is not
      reported as missing (R3).
- [ ] A test asserts a bare filename with **no** line suffix is not eligible
      while the *same* name with a suffix is (R4). The pair is the assertion; the
      first half alone passes today.
- [ ] `node scripts/sd-ai-command-pack-review-preflight.mjs` exits 0 and prints
      the `PASS documentation path references resolve…` line, with zero
      `FAIL … references missing path …` lines (R6).
- [ ] `research/measure-proposed.mjs` reports a locator-form residual of zero
      after the four references are corrected or marked (R6).
- [ ] **R5 is discharged by a test, not by a comment.** For each declined class,
      an assertion pins the behaviour: an unsuffixed bare name is not eligible;
      a name with `..` is not eligible; an extension outside
      `bareReferenceExtensions` is not eligible. A code comment enumerating the
      classes accompanies these but does not substitute for them.
- [ ] A test asserts a **well-formed** `bareReferenceExtensions` array in
      `.sd-ai-command-pack/review-preflight.json` widens the set — a reference
      with an extension absent from the defaults becomes checked. Without this
      the config wiring can be omitted entirely and every other criterion still
      passes (R9, positive direction).
- [ ] A test asserts a **malformed** `bareReferenceExtensions` (non-array) leaves
      the built-in set in force and the reference still reported, rather than
      universally accepted (R9, fail-closed direction).
- [ ] **R7:** a test asserts that a bare filename naming no tracked file and
      carrying no line suffix stays unreported, which is the property that keeps
      an unmeasured consumer corpus green.
- [ ] **R8:** the batched-query property is asserted directly — resolving a
      document containing many bare references issues **one** `git ls-files`
      invocation, not one per reference. A counting stub or a spy on the git
      helper discharges this; `design.md` records why a naive implementation
      violates it.
- [ ] `manifest.json` is bumped, `CHANGELOG.md` carries a matching entry,
      `make sync` and `make generate` are clean, and
      `docs/fleet/candidate-validation.json` is refreshed — this changes shipped
      payload under `templates/**`.
- [ ] `make check` passes, including template/root mirror verification.

## Background

This is phase 2 of the documentation path-reference work. It was originally
task `08-06-preflight-bare-filename-references`, absorbed into
`08-08-preflight-absent-path-prose` on 2026-08-08 as a phase-2 requirement
sequenced strictly after that task's absent-path escape hatch, and restored here
as its own task when 08-08's work completed.

Predecessor: `08-08-preflight-absent-path-prose`, which shipped the
`[absent: <reason>]` marker. The sequencing is the point: widening eligibility
without a way to mark an intentional absence grows the false-positive class.
That marker now exists, so this task is unblocked — and it is the mechanism the
four newly-failing references use.

`shouldCheckDocumentationPathReference` validates a reference only when it is
one of eight enumerated top-level files or begins with one of 26 directory
prefixes. The skip is the final line of the function, at
`scripts/sd-ai-command-pack-review-preflight.mjs:5179`: a bare filename has no
`/`, matches no prefix, and returns false.

## Out of scope

- The absent-path marker itself, which `08-08-preflight-absent-path-prose`
  delivered.
- Making CI run the preflight in full mode; that is
  `08-07-ci-preflight-full-mode-gap`.
- Reporting multi-match names as an error. R3 forbids it, and the classification
  work that would make it viable is recorded in `design.md` rather than done.
- Correcting the 59 noun-form references. They are declined by R4, not
  suppressed, and most name things that deliberately do not exist.
