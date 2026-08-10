# Implementation plan: thin conversion tooling

Ordered. Each step names its own check and the result that means
failure. Nothing here mutates a real consumer repository.

## Hard constraints to plan around from step 1

**100% coverage on the installer.** `make test` runs
`coverage report --include="install.py,installer/*" --fail-under=100`
(`Makefile:51`). Every branch added to `install.py` or `installer/**` —
each refusal row in the argument matrix, each preflight branch, each
validation failure — needs a test that reaches it. Writing the code
first and backfilling coverage at the end is how this task overruns;
each step below lands its own tests.

**Shipped-script coverage does not apply here, and that is a decision,
not an oversight.** `.github/scripts/check-shipped-script-coverage.sh`
governs shipped `scripts/sd-ai-command-pack-*.py` files with a per-file
table; a new shipped script without a row inherits only the aggregate
floor (~76%). This task adds no shipped script — the resweep is
source-checkout-only — so no row is added. If a later change ships the
resweep, the row becomes mandatory in the same commit.

Its coverage instead comes from two places: the shared builder sits in
`installer/conversion.py` under the 100% gate, and the resweep's own CLI
layer gets a dedicated test module.

**`templates/**` is the source of truth** (`AGENTS.md:28-32`) *for
shipped files*; root `scripts/` mirrors it byte-for-byte. The resweep is
not shipped, so it lives in `scripts/` only — same as
`fleet-candidate-check.py` and every other `fleet-*` script — and has no
template counterpart. The shipped-script coverage gate above therefore
does not apply to it either; its coverage comes from the `installer/`
100% gate via the shared builder plus its own test module.

## Steps

### 1. Shared plan builder — `installer/conversion.py`

Under `installer/` because the resweep is **not shipped**: no `fleet-*`
script is in `manifest.json`, and neither is
`docs/fleet/surface-partition.json`, so a resweep running inside a
consumer would have no classification data at all. Keeping it a
source-checkout tool means the builder can import `RETIRED_TARGETS` and
`MANAGED_BLOCK_REMOVAL_TARGETS` directly and inherits the 100% coverage
gate.

Build `ConversionPlan` from a target checkout. Separate the two input
sets explicitly, because conflating them is what made the first draft's
"pure function" claim false:

- **Classification inputs** (pure): the parsed receipt *with its load
  state* (present / missing / unreadable — the parsed set alone cannot
  produce the required missing-receipt diagnostic, since
  `read_existing_installed_targets` returns `set()` for a missing file,
  `installer/provenance.py:222`), `surface-partition.json`, the
  consumer's registry entry, `RETIRED_TARGETS`,
  `MANAGED_BLOCK_REMOVAL_TARGETS`.
- **Preflight/mutation inputs** (impure): filesystem occupancy, the
  provenance hashes used for drift detection, the existing
  `settings.json` plus the two plugin manifests, and the structural
  audit result.

The plan's `retire` bucket holds only retired targets **present in this
checkout** — the existing helper scans all 157
(`installer/removal.py:273`), and conversion executes the validated
candidate list instead.

Checks:
- Against a fresh scratch install (198 entries), every entry classifies
  and `blocked` is empty. Assert the classification, not the integers.
- Against all eight real consumer checkouts, read-only: every receipt
  entry classifies, `blocked` is empty, and
  `.github/copilot-instructions.md` lands in `keep` for each. A
  `blockStrip` verdict for it is failure — it is `repo-native` because
  Copilot reads the repo and cannot see the machine.
- Missing receipt and unreadable receipt produce distinct diagnostics,
  not a silent empty plan.

### 2. Thin-aware `install.py --status` / `--check`

Before the converter, because without it every converted consumer is
permanently `refresh-required`: `--check` decides state from a dry-run
install of the **full** source payload
(`installer/inspection.py:374-395`), and
`scripts/sd-ai-command-pack-fleet-review-classify.py:212` requires
`state: current`.

Read `mode: "thin"` from the provenance receipt and compare against the
residual payload instead of the full one.

Checks:
- The existing inspection suite passes **unchanged** — a fat consumer
  must take the same path. Stated precisely, because "the suite still
  passes" only proves the asserted outputs are unchanged: the thin
  branch is entered from exactly one predicate, `mode == "thin"` read
  from the provenance receipt, and a test asserts that predicate is
  false for every existing fixture. That is what makes the unchanged
  suite meaningful rather than merely reassuring.
- Converted fixture reports `state: current` from `install.py --check`.
- `fleet-review-classify` against that fixture classifies it as not
  needing a refresh.
- A half-converted fixture (payload deleted, receipt still `fat`) takes
  the **unchanged fat path** and reports `refresh-required` — which is
  the honest answer, since files really are missing. Asserting `invalid`
  here would contradict the byte-identical-fat-path requirement two
  lines above: `mode: "thin"` is the only discriminator, and this
  fixture does not carry it.
- The half-converted case that matters is the inverse: receipt says
  `mode: "thin"` but the residual slice is incomplete. That reports
  `refresh-required` through the thin comparison, and `sd-status` shows
  a `present` pin — so the pin alone is not a health signal, which is
  why the acceptance criteria assert `mode` and the residual together.

### 3. Resweep script + verdict schema

`scripts/sd-ai-command-pack-thin-resweep.py` — `scripts/` only, no
`templates/scripts/` counterpart and no `manifest.json` row, like every
other `fleet-*` script. Imports step 1's builder to split hits into
`scheduled` and `blockers`. Records `head`, `indexDigest`,
`worktreeClean`, and `classifierDigest`.

Checks:
- The resweep appears in no `manifest.json` row and under no
  `templates/scripts/` path. A row for it is failure — it would ship
  classification data into every consumer.
- A directory-existence blocker (a `.codex/` directory) emits
  `line: null` and the verdict still validates. A schema that requires
  an integer line cannot express this blocker at all.
- A fixture with a workflow pack reference → `blocked`, naming file and
  line.
- A fixture whose only pack references are inside
  `docs/SD_AI_COMMAND_PACK.md` → `clear`, with those hits in
  `scheduled`. **This is the criterion that proves any real consumer can
  convert at all**; if it reports `blocked`, the C-A remediation did not
  land.
- Codex/pi markers, each asserted separately rather than as one case:
  a `.codex/` directory, a `$CODEX_HOME` reference, and a pi adapter
  file each block when the registry `platforms` omits that platform, and
  each clears when it is declared.

### 4. Argument compatibility matrix

Every row of the design's matrix, as its own test: opposing mutators,
mutator-with-inspection, `--thin` without `--resweep-verdict`,
`--resweep-verdict` without `--thin`, payload selectors with **either**
direction, `--force` on revert, `--consumer` alone and with each
non-conversion mode, and the allowed rows. Land this before the mutators
so dispatch order can never silently pick a winner.

Check: each rejected row exits nonzero with a message naming both flags;
each allowed row reaches its handler. A row that merely "does something
reasonable" is failure — the point is that it is specified.

### 5. `--thin` with plan-then-mutate

Validate fully — verdict binding (including `classifierDigest`),
`blocked` empty, no unforced drift **in `delete`, `retire`, or
`blockStrip` alike**, structural audit clean, **and both roots writable**
— before the first write. `--thin` writes the consumer *and* the pack
registry, so it carries the same two-root contract as revert; an
unwritable registry found after 166 deletions is the worse ordering, not
the safer one.

Checks:
- Disposable checkout converts; the post-conversion tree compared
  against the **pre-conversion receipt** shows exactly the planned
  deletions. A partition-only comparison is not accepted as evidence.
- Drifted pack file without `--force`: refuses, and the tree plus
  `.claude/settings.json` plus the registry are byte-identical
  afterward. Failure is any write at all, not just a wrong exit code.
- Drifted **retired** file: refuses. The existing helper preserves and
  continues (`installer/removal.py:263`); conversion must not.
- Malformed managed block: refuses. Block removal can return
  `PRESERVED` (`installer/fileops.py:683`).
- A tracked pack-like file absent from the receipt: refuses, both roots
  unchanged. This is what proves the structural audit is actually
  enforced before mutation rather than merely invoked.
- Receipt entry no rule classifies: refuses, names the file.
- Verdict from a different HEAD: refuses.
- File edited after the verdict with HEAD unchanged: refuses, tree
  unchanged. A HEAD-only binding would have missed this.
- Partition edited between resweep and conversion: refuses on
  `classifierDigest`. Same for a registry-entry edit, **and for an edit
  to `installer/conversion.py` itself** — the builder is the largest
  determinant of the plan, and a test that only mutates the partition
  would pass while a builder edit silently moved the delete set.
- Missing or unreadable receipt: refuses, with the two diagnostics
  distinguished.
- Read-only pack checkout with a writable target: `--thin` refuses
  before any deletion; the consumer tree is byte-identical. Without
  this, the failure surfaces only after the consumer is already gutted.
- Mid-operation failure injection on `--thin`: consumer written, registry
  write failing, reports which half completed and exits nonzero.

### 6. Receipt rewrite and `settings.json` merge

Rewrite all three bookkeeping files to describe the residual payload:
`provenance.json` (residual `files` map, `version`, `pack`, plus
`mode: "thin"` and `settingsAdditions`), `installed-targets.txt` (the
derived residual set), `manifest.json` (residual payload). None is
deleted — `_RECEIPT_PATHS` requires all three
(`installer/inspection.py:30`, `:253`) and the audit requires a
non-empty `files` map (`install-audit.py:701-712`).

The residual written into the receipt is derived from the
pre-conversion receipt minus delete, minus retire, minus any block-strip
file that came back `REMOVED` — never from the partition's kept rows
(557 of them, only 26 present in `rwbp-coordinator`).

This is *not* the same set step 2's `--check` compares against. That one
is computed from the **source**, per the design's formula: keep-category
source targets whose partition platform the consumer declares (or whose
category is `consumer-config`, which is platform-independent), plus
every existing `MANAGED_BLOCK_REMOVAL_TARGETS` member, plus the three
bookkeeping files.

Checks on the formula itself, each one able to fail:
- The two sets agree immediately after conversion **on a fixture whose
  `.gitignore` block strip returned `UPDATED`** — the normal case. This
  is the membership contradiction the partition-row-only version had:
  `.gitignore` has no partition row but survives.
- A new `repo-native` file added to the source for a platform the
  consumer **does** declare makes `--check` report `refresh-required`.
- A new `repo-native` file added for a platform the consumer **does
  not** declare leaves `--check` at `current`. Running only the first
  case would pass while the platform predicate was missing entirely.
- Against `rwbp-coordinator`'s shape the formula yields exactly **31**
  targets, all present: 26 keep-category partition rows, plus the 2
  managed-block files (`.gitignore` and
  `.github/copilot-instructions.md`, the latter also a keep row and so
  counted once), plus the 3 bookkeeping files. Any absent target is
  failure — that is the ~531-missing regression in miniature.
- An installed-but-gitignored platform adapter counts as present.
  Presence is a filesystem check, never `git ls-files`.

Merge `extraKnownMarketplaces` and `enabledPlugins` into
`.claude/settings.json`, reading the marketplace name from
`.claude-plugin/marketplace.json` and the plugin name from
`plugins/sd/.claude-plugin/plugin.json` rather than hardcoding either.

Checks:
- Every residual entry exists on disk, asserted before the write.
- `install-audit.py --repo FIXTURE` exits **0**. Not "these three
  messages are absent" — a message-subset check passes while the audit
  fails on `provenance.json has no files map`.
- `install.py --check` on the fixture reports `state: current`.
- `read_consumer_pin` reports `state: "present"` with the expected
  version **and** `mode: "thin"` and a populated `settingsAdditions`.
  Asserting `present` alone proves nothing: an untouched fat provenance
  already passes it.
- Settings: the exact marketplace and plugin entries are asserted by
  value, not just "unrelated keys survived". Cover an
  already-present-value case (idempotent, no duplicate) and byte-compare
  everything outside the additions.
- Malformed existing `settings.json`: blocks, does not overwrite.

### 7. `--revert-thin`, two-root preflight, consumer identity

Checks:
- Converted fixture reverts: tree byte-identical to pre-conversion
  except the `enabledPlugins` disable marker, and
  `docs/fleet/consumers.json` reads `mode: fat` again. **Scoped to an
  unforced conversion.**
- A `--force` conversion that deleted a drifted file reverts to the
  *source* bytes for that path, not the drifted bytes — those no longer
  exist. The receipt's `forced` list names the path and revert reports
  it as restored-to-source. Asserting byte-identical here would be
  asserting something impossible.
- Only the recorded `settingsAdditions` are removed; an unrelated key
  added after conversion survives.
- Pin version ≠ source manifest version: refuses, naming both. Byte
  restoration is not reconstructible across versions
  (`install.py:803`).
- Consumer identity: a checkout whose path does not match any
  `pathHint` still reverts using the receipt's recorded `consumer`; a
  receipt/registry/`--consumer` mismatch refuses rather than picking.
- Read-only pack checkout: refuses before any write; both roots
  byte-identical. Same for a read-only target.
- **Mid-operation failure injection**: one root written, the second
  failing, must produce the documented partial-completion diagnostic
  naming which half completed, and exit nonzero. Preflight tests alone
  do not reach this branch.

### 8. `--dry-run` on both directions

Prints the exact planned change set; nothing is written either way.

The printed set covers everything conversion touches, not just file
deletions: deletes, retires, managed-block edits, the three receipt
rewrites, the `settings.json` additions, and the registry `mode` flip.

Check: run `--dry-run`, then run for real, and compare the printed set
against the executed run's actual changes across all six categories.
"The tree was unchanged" is satisfied by an empty or wrong printout, and
a delete-only comparison passes while the settings and registry writes
go unannounced.

### 9. Retention fixture

Synthetic consumer declaring `codex` so `retainVendoredFor` executes.
Assert retention across the **whole** shared platform — `.agents/**` and
`scripts/**` both — since `retainVendoredFor` is declared per platform,
not per directory.

Record in this file, on completion, that no live consumer exercises this
path: the coverage is synthetic and must not be reported as
fleet-proven.

### 10. Spec and release obligations

Update `.trellis/spec/backend/manifest-and-filesystem.md` with the
conversion contract: plan-then-mutate, the verdict's consumer *and*
classifier binding, the three residual bookkeeping files, thin-aware
inspection, the argument matrix, and the two-root revert matrix.

If `templates/**` or `docs/SD_AI_COMMAND_PACK.md` changed, bump
`manifest.json` and add the matching top `CHANGELOG.md` heading — the
release payload gate is CI-only (`.github/workflows/tests.yml:639`) and
`make check` will not catch a missing bump.

## Explicitly out of scope, recorded so it is not assumed covered

The fleet candidate checker force-installs a fresh fat payload and
audits that (`scripts/sd-ai-command-pack-fleet-candidate-check.py:226`).
It does not read a live thin receipt, so nothing here breaks it — and
nothing here proves thin behavior through it either. That is child 2's
subject. This task must not report candidate-loop coverage.

## Final validation

In order, last:

1. `make sync` then `make generate` (generate validates the root mirror,
   so it must follow sync; if generate rewrites a template, repeat once).
2. `make release-prep` if this task changed the payload or
   `docs/fleet/consumers.json`; `make check` otherwise. Parent contract
   C-G.
3. Coverage: `install.py` and `installer/*` at 100% per `Makefile:51`.
   No new row in `.github/scripts/check-shipped-script-coverage.sh` —
   this task ships no script. If the resweep ever appears in
   `manifest.json`, that gate applies and the row is required.

## Rollback points

- Steps 1 and 3–4 add code paths reached by nothing shipped; revert is a
  plain `git revert`.
- Step 2 modifies existing inspection behavior and is the highest-risk
  step. Its gate is the unchanged existing inspection suite; if that
  cannot pass, stop rather than adjusting the suite.
- Steps 5 onward add `--thin` and `--revert-thin` as additive flags;
  reverting them cannot affect the fat install path, and step 5's checks
  include a run of the existing install/remove suites to prove it.
- No step here can damage a consumer: every fixture is a scratch
  directory, the eight real checkouts are read only, and the registry
  writes are to this repo's own tracked file, reviewable in the PR diff.

## Concern ledger — round 1

Host lane (H-*) and Codex lane (X-*). Every finding was verified against
the tree before disposition; nothing was accepted on assertion.

| ID | Lane | Concern | Disposition |
|---|---|---|---|
| H-1 | host | Deleting `installed-targets.txt` makes the audit report a missing receipt and flags every survivor `unlisted-pack-like` (`install-audit.py:293`, `:632`, `:640`) | addressed — receipt kept, rewritten to the derived residual |
| H-2 | host | Residual computed from the partition's kept rows would list 557 paths, of which only 26 exist in `rwbp-coordinator` → ~531 `installed target is missing` failures | addressed — residual derived from the pre-conversion receipt minus the plan's removals, asserted against the filesystem |
| H-3 | host | `blockStrip` hardcoded to `.gitignore`; `MANAGED_BLOCK_REMOVAL_TARGETS` (`removal.py:55`) holds two files | addressed — bucket enumerated from the frozenset; `.github/copilot-instructions.md` classified `keep` (it is `repo-native` because Copilot cannot see the machine) |
| H-4 | host | Settings keys and values invented rather than read from the pack manifests | addressed — marketplace name from `.claude-plugin/marketplace.json`, plugin name from `plugins/sd/.claude-plugin/plugin.json` |
| X-1 | codex | Thin receipt breaks `_RECEIPT_PATHS` (`inspection.py:30`, `:253`) and the audit's non-empty `files` map requirement (`install-audit.py:701`) | addressed — all three bookkeeping files kept and rewritten to the residual; step 6 asserts audit exit 0, not a message subset |
| X-2 | codex | Verdict binds consumer state but not the pack-side classification authorities | addressed — `classifierDigest` over partition, registry entry, `RETIRED_TARGETS`, `MANAGED_BLOCK_REMOVAL_TARGETS`, both plugin manifests, pack HEAD |
| X-3 | codex | `ConversionPlan` not a pure function of the named inputs; receipt load state indistinguishable from empty (`provenance.py:222`); retirement helper scans all 157 (`removal.py:273`) | addressed — classification and preflight inputs separated in step 1; typed receipt load state; only validated candidates executed |
| X-4 | codex | Fresh install yields 198 entries, not 210 (`install.py:903` retires before rewriting) — the stated fixture cannot produce its asserted plan | addressed — two fixtures, 198 fresh and 210 explicitly seeded |
| X-4b | codex | "design says `.github/copilot-instructions.md` has no partition row" | **rebutted** — the design says the opposite. `.gitignore` has no partition row; copilot-instructions is `{platform: github, category: repo-native}` and is classified `keep` for exactly that reason. Codex inverted the pair. |
| X-5 | codex | Builder under `installer/` is unimportable from the shipped resweep (`installer/**` absent from `manifest.json`) | **superseded by Y-4** — the round-1 fix (ship the builder as `scripts/sd_ai_command_pack_conversion_lib.py`) was the wrong branch of the two Codex offered. Round 2 measured that the partition is not shipped either, so a shipped resweep cannot classify at all. Do not implement this row |
| X-6 | codex | Argument-combination behavior unspecified; dispatch order would silently pick a winner (`install.py:451` precedent) | addressed — full matrix in the design, one test per row, landed before the mutators |
| X-7 | codex | "All-or-nothing" validated only `delete` drift; `retire` preserves and continues (`removal.py:263`) and block removal can return `PRESERVED` (`fileops.py:683`) | addressed — preflight covers all three buckets; drifted-retired and malformed-block fixtures added |
| X-8 | codex | Revert has no durable consumer identity, and byte-identical restoration is not reconstructible across pack versions (`install.py:803`) | addressed — canonical `consumer` in the receipt plus `--consumer` override with mismatch refusal; revert requires pin version == source version |
| X-9 | codex | Eight stated checks pass while behavior is broken (pin `present` alone, single codex-marker case, settings by-shape not by-value, audit "clean" unproven, dry-run output never compared, `retainVendoredFor` scoped to `.agents/**` only, no mid-operation revert failure, shipped-script coverage aggregate-only) | addressed — each rewritten as an assertion that can fail: audit exit 0, `mode`+`settingsAdditions` asserted, three separate marker cases, settings asserted by value, rogue-pack-like fixture, dry-run output compared to the executed run, retention across `scripts/**` too, mid-operation failure injection, per-file coverage rows |
| X-10 | codex | `install.py --check` computes state from a dry-run of the **full** payload (`inspection.py:374-395`), so a thin consumer is permanently `refresh-required` and `fleet-review-classify:212` breaks | addressed — new step 2 makes `--status`/`--check` thin-aware ahead of the converter; recorded in the design's tradeoffs as real scope growth |

Round 1 verdict: no unresolved blocking concern at the time. Round 2
then found that several of these dispositions were claimed rather than
implemented — recorded below rather than quietly re-fixed.

## Concern ledger — round 2

Round 2 reviewed the round-1 remediations rather than re-listing round 1.
It confirmed the X-4b rebuttal and raised eight further blockers, seven
of which were genuine contradictions introduced or left by the round-1
edits.

| ID | Concern | Disposition |
|---|---|---|
| Y-1 | The fates table said all three bookkeeping files are kept while the normative `ConversionPlan` block still said `manifest.json deleted` | addressed — the plan's `receipt` row now reads "all three rewritten, none deleted". A self-contradicting artifact would have been resolved at implementation time by whichever line the implementer read first |
| Y-2 | "Residual payload" had no source-side computation, so thin `--check` was undefined; using the receipt would miss newly shipped retained files, using partition keep rows recreates the 531-missing failure | addressed — the expected residual is defined as source-manifest targets whose partition classification is a keep category for this consumer, plus partition-carrying managed-block files, plus the bookkeeping trio. A test asserts it diverges correctly from the receipt-derived set when a new `repo-native` file ships |
| Y-2b | A `.gitignore` returning `UPDATED` stays in the residual but can never byte-match any source file | addressed — managed-block members compare by marker-pair presence, never by whole-file hash |
| Y-3 | Step 2 required both an unchanged fat path and an `invalid` verdict for a `mode: fat` half-converted fixture; the gate is `mode: "thin"`, so that fixture necessarily takes the fat path | addressed — the assertion is now `refresh-required`, which is the honest fat-path answer, and the case that actually matters (`mode: "thin"` with an incomplete residual) is asserted separately |
| Y-4 | The shipped builder was to import `MANAGED_BLOCK_REMOVAL_TARGETS` from unshipped `installer/removal.py` | addressed by **reversing round 1's X-5 choice**. Measured: `manifest.json` ships no `fleet-*` script and not `docs/fleet/surface-partition.json`, so a shipped resweep could never classify anything. The resweep is source-checkout-only, the builder moves to `installer/conversion.py`, and the closing check became a manifest assertion |
| Y-4b | `classifierDigest` mixed classification and mutation inputs, and pack `HEAD` binds commits while leaving uncommitted edits invisible | addressed — the digest is redefined as "everything that determines what this conversion does", covering the plugin manifests deliberately, and `HEAD` is replaced by the bytes of `installer/removal.py` and `installer/registry.py` so uncommitted edits are caught too |
| Y-5 | "198 plus 12 retired" contradicted the 17-unclassified figure, and the two special cases were never named | addressed with a measurement: consumer − current is exactly 13 retired surfaces, current − consumer is exactly `scripts/sd-ai-command-pack-pack-update.sh`, so 198 + 13 − 1 = 210. The 17 counts 13 retired + 3 bookkeeping + `.gitignore`; the two special cases are the bookkeeping trio and the managed-block files, now named |
| Y-6 | `--thin` also writes two roots (registry flip) but the two-root preflight was specified only for revert | addressed — the preflight and mid-operation diagnostic apply in both directions, with a read-only-pack fixture for `--thin` specifically. An unwritable registry discovered after 166 deletions is the worse ordering |
| Y-7 | `--force` deletes drifted bytes that revert's byte-identical promise cannot restore | addressed — the promise is scoped to unforced conversions, forced paths are recorded in the receipt's `forced` list, and revert reports them as restored-to-source |
| Y-8 | Matrix left `--revert-thin` + payload selectors and all `--consumer` combinations unspecified | addressed — rows added for both directions and for `--consumer` alone and with each non-conversion mode |
| Y-9 | Dry-run compared only delete/add sets while conversion also writes blocks, three receipts, settings, and the registry | addressed — the comparison spans all six categories |
| Y-10 | "Unchanged inspection suite" proves unchanged outputs, not an unchanged path | addressed — the thin branch has exactly one entry predicate and a test asserts it is false for every existing fixture |
| Y-11 | A directory-existence blocker cannot supply the mandatory `line` | addressed — `line` is explicitly nullable in the verdict schema, with a test |

Round 2 verdict: every blocker addressed; one round-1 decision (X-5)
reversed on measurement. The X-4b rebuttal was independently confirmed.

## Concern ledger — round 3

Round 3 audited the Y-* dispositions and confirmed Y-1, Y-3, Y-4, and
Y-5 through Y-11 as genuinely addressed. Three blockers remained.

| ID | Concern | Disposition |
|---|---|---|
| Z-1 | The source-derived residual included managed-block files only when they carry a partition row, but `.gitignore` has none and survives an `UPDATED` block strip — so the two residual sets disagree on the normal fixture | addressed — every existing `MANAGED_BLOCK_REMOVAL_TARGETS` member is in the source-derived set unconditionally; a `REMOVED` member is absent from both because it no longer exists |
| Z-2 | `classify(target, partition, consumer.platforms)` was used as though it filtered platforms the consumer never installed, but no rule defined that; an unsupported-platform `repo-native` target would cause perpetual `refresh-required` | addressed with a measurement — the predicate is `platform ∈ consumer.platforms OR category == "consumer-config"`, which against `rwbp-coordinator` yields 21 `github` + 2 `claude` + 4 `shared` consumer-config = 27, exactly the present set, 0 absent and 0 extra. Two tests, one per branch: a new `repo-native` file for a declared platform must move `--check` to `refresh-required`, one for an undeclared platform must not |
| Z-2b | Presence of gitignored-but-installed adapters was unproven | addressed — presence is a filesystem check, matching `install-audit.py:558`'s `rglob` walk; a `git ls-files` check would misreport them, and a test covers it |
| Z-3 | `classifierDigest` was absent from the normative verdict schema, and omitted `installer/conversion.py` — the builder whose logic most directly determines the plan | addressed — added to the schema block and to the digest inputs, with a test that edits the builder between resweep and conversion |
| Z-4 | "All-or-nothing" overpromised: the two-root write can complete one half and fail the other | addressed (non-blocking) — renamed to fail-closed preflight, with the guarantee stated as "nothing is written until the whole plan validates" rather than atomicity |

**Verification status of this round, stated plainly:** rounds 1–3 each
ran the full host + Codex lanes. These Z-* remediations were applied
after round 3 returned and have **not** been through a fourth
adversarial round; the review contract caps automatic rounds at three.
Z-2's formula is the one carrying independent evidence — it was
measured against a real consumer checkout, not reasoned — while the
others are corrections to artifact text whose defects round 3 stated
precisely.
