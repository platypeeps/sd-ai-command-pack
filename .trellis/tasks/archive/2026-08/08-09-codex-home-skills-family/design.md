# Design: Retire the codex vendored-retention carve-out

## The one-line change and everything it drags

`PLATFORM_RETAIN_VENDORED_FOR["shared"]` goes from `("codex", "pi")` to `("pi",)`
in `.github/scripts/partition-surfaces.py:170-172`. Everything else in this task
is the blast radius of that: two generated artifacts, one spec section, four
comments that justify the old value, one conversion-tooling blocker whose premise
it was, and the tests pinning all of it.

## What is deliberately *not* changed

**No `$CODEX_HOME/skills` destination family.** Probe 1 shows Codex reads that
root, so the family would work. It would also be redundant: the `agents-skills`
family already lands in `$HOME/.agents/skills`, which probe 2 shows Codex reads
unconditionally. A second path to the same 49 files buys nothing and adds a
family, a root resolver, a receipt allowlist entry, and a removal path.

**`codex` stays `repo-native`.** Tempting to read "Codex reaches machine rows" as
"codex is a machine platform"; it is not, and flipping it would break the build.
`platform_category` maps a non-claude machine platform to `machine-other`, so the
`.codex/**` rows would enter the machine payload — where they have no destination
family:

```
.codex/config.toml                            -> None
.codex/hooks/x.json                           -> None
.agents/skills/sd-status/SKILL.md             -> DestinationFamily(name='agents-skills', ...)
scripts/sd-ai-command-pack-status.py          -> DestinationFamily(name='agents-bin', ...)
```

`machinepayload.py:47-49` is explicit that an unmatched row "matches no family
and fails closed rather than landing somewhere by accident, which is what keeps
the two inventories from drifting silently." That is correct behavior and this
task must not trip it.

The two facts are independent and both true: **codex's own adapter rows are
repo-native, and codex reads the shared platform's machine-installed rows.**
`retainVendoredFor` is keyed on the *shared* platform, which is why the second
fact — not the first — is the one that governs retention.

## Change surface

| # | File | Change |
|---|------|--------|
| 1 | `.github/scripts/partition-surfaces.py:170-172` | `("codex", "pi")` → `("pi",)` |
| 2 | `.github/scripts/partition-surfaces.py:140-142` | codex disposition rationale: drop the false clause, give the real reason |
| 3 | `.github/scripts/partition-surfaces.py:163-169` | retention rationale: Codex no longer among those needing a vendored copy |
| 4 | `docs/fleet/surface-partition.json` | regenerated |
| 5 | `plugins/sd/machine-payload/partition.json` | regenerated |
| 6 | `.trellis/spec/backend/manifest-and-filesystem.md:125-133` | `["codex", "pi"]` → `["pi"]`; rewrite the Codex clause |
| 7 | `scripts/sd-ai-command-pack-thin-resweep.py:657-704, 705-713, 788-890` | marker blocking derived from the partition |
| 8 | `installer/conversion.py:310-320` | R17-C1 comment cites a codex-declaring consumer's "102 residual targets"; restate against `pi` |
| 9 | `CHANGELOG.md` | new entry; the 0.64.35 entry stays as shipped history |

Items 2, 3, 6, and 8 are comment/prose corrections with no behavior change. They
are in scope because the false claim is the thing this task exists to retire, and
leaving it in four places guarantees it gets cited again.

## The marker rule, derived rather than restated

`thin-resweep.py` raises a **blocker** when a consumer shows codex or pi usage its
registry row does not declare. The stated reason (`:659-665`) is that
`retainVendoredFor` intersects *declared* platforms, so an undeclared Codex user
gets `.agents/**` deleted and "Codex cannot consume the machine-installed plugin
at all". The plugin clause is true and irrelevant — the `.agents` families are the
machine installer's, not the Claude plugin's — and the deletion consequence
disappears once `codex` leaves the retention list.

The module already contains the disqualifying standard, at `:691-694`, for the
empty-directory case:

> blocking on it asks for a declaration that changes nothing

After change 1, that is true of *every* codex marker, not just the empty-directory
one. So the rule generalizes rather than gaining an exception.

**Design choice: derive the blocking set from the partition instead of hardcoding
it.** `MARKER_PLATFORMS` keeps both platforms so detection and pack-defect
classification are untouched; what becomes conditional is the bucket a
*consumer-owned* hit lands in:

- platform appears in some `retainVendoredFor` list in the partition → `blockers`
- otherwise → `advisories`

`advisories` is an existing first-class bucket (`:1384`, `:1581`, `:1605`,
counted at `:1757`) meaning real information that is not a reason to refuse a
conversion — precisely this. The `:199` remark that a rule "never moves one to
advisory" is scoped to the U-1 command-position citation rule, not a global
prohibition on the bucket.

**Verified, because the whole downgrade rests on it:** `decide()` (`:1710-1727`)
builds its reasons from `blockers`, `packDefects`, `missingFiles`, and a dirty
worktree. `advisories` and `scheduled` are never read. So routing a hit there
genuinely clears the verdict rather than relabelling a block — if `advisories`
had fed `decide()`, this design would be cosmetic and wrong.

The corollary is a real limit, not a loose end: **pack-owned hits keep routing to
`packDefects`, which still blocks.** That is correct — a surviving pack directory
for a platform the registry omits is the pack shipping something broken, a fact
retention never bore on — but it means this change clears the codex blocker for
the *consumer-owned* case only.

Deriving it, rather than writing `BLOCKING_MARKER_PLATFORMS = {"pi"}`, matters
for one reason: it makes the invariant structural. The marker exists *because*
declaration changes the plan; reading that from the same artifact the conversion
reads means the two cannot drift, and a future pi probe retires the pi blocker by
editing one tuple instead of two files that must agree.

Plumbing is small: `scan()` already loads the partition at `:1360` and calls
`platform_marker_hits` at `:1628`, so this is one added parameter, not a new
load path. Alternative considered and rejected: dropping `codex` from
`MARKER_PLATFORMS` entirely — simpler, but it also deletes codex pack-defect
detection and the informational signal, and it hardcodes what the partition
already knows.

## Preserving retention coverage

The live risk in this change is silent: `codex` is the platform the retention
tests are written against, so removing it can retire a tested mechanism while
every test still passes because it was rewritten to not exercise it.

Two things keep it exercised:

1. **`pi` remains in the real partition**, so `_retained_for_consumer`,
   `classify_target`, and `expected_residual_targets` keep a live retained
   platform in production configuration.
2. **Synthetic-fixture tests keep their own partition dicts.**
   `tests/test_conversion_plan.py:107` builds its partition inline. That is a
   fixture, not an assertion about the shipped value, and it should keep
   exercising retention — retargeted to `pi`, or left on a synthetic platform id
   where the test is about the mechanism rather than about codex.

The two kinds are easy to confuse and `test_partition_surfaces.py` contains both.
Sorting them by what they read:

| Test | Reads | Change |
|------|-------|--------|
| `:136-143` | `committed["platforms"]["shared"]` | → `["pi"]`; its `:130-131` comment also repeats the falsified claim |
| `:488` | `build_partition(root)` output | → `["pi"]` |
| `:158-168` | iterates `retainVendoredFor` | none — confirm it still passes |
| `:170-190` | iterates `retainVendoredFor` | none — confirm it still passes |
| `test_conversion_plan.py:107` | its own inline dict | fixture — retarget, keep retention exercised |

`:136-143` is the one to miss: it asserts the whole `shared` dict rather than the
field, so a search for the field name alone does not surface it.

The R17-C1 regression test — the one asserting `classify_target` and
`expected_residual_targets` agree in both directions on the same target — must
survive and keep executing, because it is the test that catches a converter and
inspector disagreeing about a retained row. It is retargeted, never deleted.

## Failure modes

**Fail-open direction.** Every other change in this family removed a way to
convert; this one removes a blocker. If the probe conclusion is wrong, a real
Codex user loses their skills quietly, at conversion time, with no error. Three
things bound it: the probe carries negative controls in two dimensions
(`CODEX_HOME` and `HOME`); the canary task independently requires machine scope
`installed` before the first consumer mutation, so the machine copy is proven
present before a vendored copy is removed; and conversion is revertible from the
receipt.

**Version dependence.** `$HOME/.agents/skills` resolution is `codex-cli 0.147.0`
behavior with no compatibility guarantee. The pack cannot pin a user's Codex
version. Accepted and recorded — not mitigated — so that a future report of
"Codex lost its skills after conversion" has a documented first suspect.

**Stale figures.** Measured consequences of codex retention — the 75-target
figure in the canary PRD, the `102` residual in `conversion.py`'s R17-C1 comment
— describe a configuration that stops existing after this change. They must be
found by search rather than by reading the files this task happens to open.

Searching for the bare numbers does not work, and implement.md step 7 says so
explicitly: `77`, `102`, and `179` each match hundreds of dependency hashes in
`requirements-dev.txt`. The sweep anchors on the claim (`never reads
~/.agents/skills`, `codex ... retain`) instead. Note that `77` is simultaneously
this task's own *live, verified* baseline — 49 + 26 + 2, confirmed twice, from
the machine receipt families and from `classify_target` — so it is stale only
where it is asserted as a post-change property.

## Validation

The load-bearing check is a property, not a count: **for a consumer whose declared
platforms differ only by `codex`, the two conversion plans are identical.** That
is exactly what "retention no longer triggers on codex" means, it fails loudly if
requirement 1 is reverted, and it needs no measured row count to stay true.

Supporting: `partition-surfaces.py --check` byte-compares both generated
artifacts; a codex-undeclared consumer is advisory while a pi-undeclared one still
blocks; `make check`.

## Rollback

Restore `("codex", "pi")` and regenerate. The change is pack-only and touches no
consumer repository, so rollback is a pack release with no consumer-side action.
A consumer converted while the carve-out was gone is not corrupted by the
revert — it would simply retain rows on its next refresh that it does not need.
