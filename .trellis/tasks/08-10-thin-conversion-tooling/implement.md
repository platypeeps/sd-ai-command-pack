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

#### What step 2 actually cost — measured, not planned

Narrowing the payload was one line. Three further readers turned out to
ask the same wrong question, each found by running the converted fixture
rather than by reading:

1. **The pack's `.gitignore` block is reinstalled unconditionally.**
   `_install_payload` calls `install_trellis_gitignore` outside the
   selected-files loop (`install.py:526-528`), so a thin consumer whose
   block was stripped reports a pending change forever and relists
   `.gitignore` as an installed target. Fixed with an explicit
   `install_gitignore` parameter, false only on the thin path.
2. **Installed platforms are inferred from the receipt.**
   `_manifest_platforms` intersects the manifest against the receipt, so
   a thin consumer reports only its repo-native platforms — measured as
   `claude, github` where the registry declares
   `claude, gemini, github, opencode`. `validate_inspection` rejects
   that mismatch before it ever looks at `state`. The provenance pin now
   carries `platforms` and `inspect_receipts` prefers it.
3. **The shipped structural audit fails a thin consumer outright.**
   `--check` runs it (`audit_requested = args.audit or args.check`) and
   a failed audit makes the report `state: invalid`, not
   `refresh-required`. Its expected set is manifest-derived
   (`expected_targets_from_manifest`) — the wrong question for a
   deliberately reduced payload. Because the audit ships to consumers and
   the partition does not, it cannot recompute the residual: it now skips
   only the manifest-derived completeness check when provenance pins
   `mode: "thin"`, keeping every receipt-to-disk check. The division is
   deliberate — the shipped audit proves receipt ↔ disk, the source-side
   `--check` proves receipt ↔ expected residual.

Two corrections to the checks above, from measurement:

- The half-converted fixture reports **`invalid`**, not
  `refresh-required`: the receipt still lists the deleted targets, so
  `inspect_receipts` emits `installed target is missing or invalid` per
  file and the report never reaches a change count. That is strictly
  louder than the planned expectation; the test asserts `invalid`.
- `fleet-review-classify` was verified at its gate
  (`run_install_inspection` + `validate_inspection` against the
  converted fixture), not end to end — the full classifier additionally
  requires a registry entry, a base commit, and a remote, none of which
  a temporary fixture has. `validate_inspection` returning cleanly is
  the whole of what step 2 can break.

Carried into step 6: the conversion must write its receipts from
*exactly* the inputs the inspection recomputes — the same narrowed
`selected`, the same `_install_payload` dry-run results, the same pin —
or `--check` reports a phantom change. The first fixture attempt passed
`results=[]` and produced a spurious `installed-targets.txt` update.

### 3. Resweep script + verdict schema

`scripts/sd-ai-command-pack-thin-resweep.py` — `scripts/` only, no
`templates/scripts/` counterpart and no `manifest.json` row, like every
other `fleet-*` script. Imports step 1's builder for the removal set and
applies `design.md`'s four-bucket rule — `scheduled`, `packDefects`,
`blockers`, `advisories` — each step failing closed. Records the full
binding set from `design.md`'s verdict schema: `head`, `indexDigest`,
`indexFlagsDigest`, `worktreeDigest`, `worktreeClean`,
`receiptOccupancyDigest`, `executableBitsDigest`, `binaryTrackedFiles`,
`missingTrackedFiles`, and `classifierDigest`. The short list this step
used to name — `head`, `indexDigest`, `worktreeClean`,
`classifierDigest` — would have shipped a verdict *less* reproducible
than the research measurement it derives from: every field added after
that list was added because something changed a classification while the
short list stayed identical.

`classifier_digest` in `installer/conversion.py` gains
`scripts/sd-ai-command-pack-thin-resweep.py` in the same commit. The
builder decides what is removed; the resweep decides what counts as a
hit, as the execution surface, and as a citation. Without that input an
edit to the surface rule or the glob matcher leaves an existing `clear`
verdict valid under an unchanged digest.

`research/fleet-blocker-scan.py` is the reference implementation of the
rule and the source of the measurement below. The shipped resweep
supersedes it; the research copy stays so the counts can be re-derived.

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
  `scheduled`. If it reports `blocked`, the C-A remediation did not
  land. It proves that and only that — the earlier claim that this
  criterion "proves any real consumer can convert at all" is retracted;
  see the measurement below.
- A fixture whose pack references live in **kept** pack-managed files
  and cite only paths the conversion **keeps** → `clear`, and those
  references appear in **no bucket at all**. A citation of a surviving
  path is not a hit; recording it as `scheduled` would misreport it as
  something the conversion removes. Measured: 13 of `rwbp-coordinator`'s
  53 surviving pack-mentioning files are pack-managed, so a rule that
  blocks on pack-managed files as such cannot clear any consumer.
- A fixture whose kept pack-managed file cites a **removed** path →
  `blocked`, that hit in `packDefects`, not `scheduled`. Measured:
  **16 hits in 7 files** for the five consumers that have not edited
  their PR template, **14 in 6** for the three that have — four surviving
  pack prompts (`sd-housekeeping` 37/38, `sd-review-learnings` 44/46,
  `sd-review` 43, `sd-status` 43), the pack's managed block in
  `.github/copilot-instructions.md` (7 hits, at consumer-dependent line
  numbers), `.github/PULL_REQUEST_TEMPLATE.md` 7 and 14, and the
  surviving `obsidian-kb` block in `.gitignore`. Calling any of
  that `scheduled` would ship known breakage against a release obligation
  no artifact tracks.
- A fixture managed-block target whose **in-block** content cites a
  removed path → `packDefects`; the same file with the citation
  **outside** the block → judged as consumer-authored. Provenance never
  vouches managed-block targets (`installer/provenance.py:114`), so
  digest comparison cannot reach this case at all — measured: it is how
  `.github/copilot-instructions.md`'s 7 hits were missed entirely by the
  digest-only rule.
- A receipt entry that is a **symlink**, and one whose bytes are
  **unreadable** → `packDefects` with a stated reason, not silently
  skipped. Fail-closed is a claim the plan makes; these are the two
  inputs that test it.
- A fixture citing a removed path on a line that does **not** contain the
  string `sd-ai-command-pack` → `blocked`. Discovery must start from the
  removal set, not the pack name; measured live at
  `sd-github-review/test/metadata.test.js:490`, which names
  `.agents/skills/sd-status/SKILL.md`.
- A fixture root `CLAUDE.md` instructing an agent to run a removed script
  → `blocked`. Measured live at `mezmo_benchmark/CLAUDE.md:28`.
- The same fixture file, edited so its sha256 no longer matches the
  digest provenance recorded, is reclassified as consumer-authored.
  Receipt membership alone must not confer the pack exemption. Guard
  against the fail-open form specifically: provenance stores
  `sha256:<hex>` and a bare-hex comparison never matches, which empties
  `packDefects` while looking healthy — measured on the first run of
  `research/fleet-blocker-scan.py`, which reported `packDefects=0` for
  all 8 consumers until the prefix was handled.
- A fixture whose consumer-authored **test** asserts on
  `.sd-ai-command-pack/provenance.json` → `clear`. That path is kept, and
  blocking on the string rather than on the removed paths would fail
  this.
- A fixture whose `.github/workflows/ci.yml` invokes a **removed** pack
  script → `blocked`, naming file and line.
- A fixture citing removed scripts by **glob**
  (`scripts/sd-ai-command-pack-*.sh`) → `blocked`. Neither exact-path nor
  basename matching sees it; measured live at
  `loadsmith/.github/workflows/ci.yml:149`.
- A fixture citing a removed script from a **nested** executable path
  (`templates/skills/x/scripts/run.py`) → `blocked`. A root-anchored
  `scripts/` prefix misses it; measured live at
  `se-ai-command-pack/templates/skills/se-review-skills/scripts/skill_review.py`.
- A fixture whose consumer-authored `.github/prompts/x.prompt.md` tells
  an agent to run a removed script → `blocked`. An agent-executed prompt
  is an execution surface even though nothing about it is a shell file.
- A fixture whose `README.md` mentions a removed pack script → `clear`
  with an `advisories` entry. Prose staleness is a human's follow-up,
  never a reason to refuse a conversion.
- A `block_strip` target citing a removed path **inside** the managed
  block → `scheduled`; the same target citing one **outside** the block →
  judged normally, so a pack-owned outside-block citation is a
  `packDefects` entry. No consumer exercises this today, which is exactly
  why it needs a fixture rather than a measurement.
- `--thin` refuses on a verdict whose `blockers` is empty but whose
  `packDefects` is not. This is the only thing that makes a pack defect
  block rather than merely be recorded, so assert it against the refusal
  path, not against the verdict object.

**Measured before building: no registered consumer is `clear` today, and
the pack blocks every one of them.** Reproduce with:

```bash
.venv/bin/python .trellis/tasks/08-10-thin-conversion-tooling/research/\
fleet-blocker-scan.py --out .trellis/tasks/08-10-thin-conversion-tooling/\
research/fleet-blocker-scan.json
```

Per-consumer `head`, `indexDigest`, and `worktreeDigest` plus full
per-file results are committed in that JSON — several consumer trees are
dirty, and `head` alone cannot identify a dirty tree, so the digests are
what make a rerun comparable. Consumer-authored executable callers of
removed paths: `sd-github-review` 14 hits in 10 files,
`se-ai-command-pack` 21/7, `hoa-manager` 34/9, `mezmo_benchmark` 44/24,
`rwbp-coordinator` 48/7, `loadsmith` 53/5, `rwbp-website` 65/8,
`anomaly-metric-creator` 205/21 — CI workflows, `package.json` scripts,
repo-owned tests, shell preflights, root agent instruction files, and
PR-template checklists. Plus 16 pack defects in 7 files (14 in 6 where
the consumer has taken over its PR template).

Step 3 is therefore expected to return `blocked` for every real consumer
on its first run, and that is the correct answer, not a bug in the rule.
Two remediations follow: the pack must repoint its own seven surviving
surfaces — four prompts, the Copilot managed block, the PR template, and
the `obsidian-kb` block in `.gitignore` — off the deleted `scripts/`
paths, and each consumer must repoint its
execution surface. The first is pack work that gates all conversions; the
second belongs to children 3–5 and materially enlarges them.
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
  **And for an edit to `scripts/sd-ai-command-pack-thin-resweep.py`** —
  the builder decides what is removed, the resweep decides what counts as
  a citation, and a mutation test that only touches the builder leaves
  the second half unbound.
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

## Concern ledger — round 4 (step-3 planning edits)

New coherent edit batch, so the round budget restarts: step 3's
classification rule was rewritten mid-implementation after measurement
contradicted it, which materially changes `design.md`, `implement.md`,
`prd.md`, and the parent's C-A. Host lane completed. Codex lane completed
(`codex exec --cd . --sandbox read-only --ephemeral`, 6 blocking
concerns). The two lanes overlapped on four of six; none was rebutted.

| ID | Lane | Concern | Disposition |
|---|---|---|---|
| W-1 | both | The execution-surface enumeration was a root-anchored directory allowlist and failed **open** twice. Codex: agent-executed surfaces (`.github/prompts/**`, `.claude/commands/**`, `.agents/skills/**`) were absent, so `rwbp-coordinator/.github/prompts/sd-housekeeping.prompt.md:35,38` — which tells an agent to run a deleted script — classified as advisory. Host: the allowlist was anchored at the repository root, so `se-ai-command-pack/templates/skills/se-review-skills/scripts/skill_review.py` (real Python under a nested `scripts/`) also fell through | addressed — the rule is now property-based and fails closed: suffix, build/CI basename, CI *or agent-executed* prefix, **any** path segment in `{scripts,bin,tools,test,tests,.githooks,.husky}` at any depth, or the executable bit. `design.md` §1 step 4; two fixture criteria added, one per measured counterexample |
| W-2 | both | The pack-managed exemption permitted known breakage. `scheduled` meant "inside a deleted file", then was overloaded to include kept files "a later release will fix" — an obligation no artifact tracks. Codex also noted receipt membership does not prove current bytes are still pack-owned, so a consumer-edited kept target inherited the exemption | addressed — new `packDefects` bucket that **blocks**, and the exemption now requires the file's sha256 to match the digest provenance recorded (unrecorded or mismatched ⇒ consumer-authored). Measured: 6 defects in 4 files, identical across all 8 consumers — four surviving pack prompts run deleted scripts. Filed as its own task; see W-2b |
| W-2b | host | The pack-side prompt repointing W-2 exposes gates every consumer conversion but is not this task's deliverable | **parked with a task** — `08-10-thin-prompt-surface-repoint`, blocking children 3–5. Trigger: before the first real conversion. Parked, not deferred: a `packDefects` verdict blocks `--thin` regardless |
| W-3 | both | Delete-set citation matching by exact path and basename has a real glob false negative. Codex: `loadsmith/.github/workflows/ci.yml:149` addresses the deleted population as `scripts/sd-ai-command-pack-*.sh`, naming no exact path or basename. Host: `se-ai-command-pack/repomix.config.json:57` does the same. Codex further noted the plan had no glob, constructed-path, or env-var fixture | addressed — three matchers (exact/suffix, basename, `fnmatch`), a glob fixture criterion, and an explicit statement in `design.md`, `prd.md`, and parent C-A that the check is a **lower bound**: runtime-composed paths are invisible to any static reader, and `--revert-thin` is the guarantee, not resweep exhaustiveness |
| W-4 | both | Six locations still asserted the superseded two-bucket rule: parent C-A, the parent's C-1 ledger row, child `prd.md` requirement 1 and acceptance criterion 1, child `design.md`'s `scheduled` definition, and child `implement.md` step 3 | addressed — all six rewritten. The child acceptance criterion no longer says a bare "pack reference" blocks; the parent C-1 row is marked superseded with a pointer here. Codex separately confirmed the retracted "docs-only fixture proves a real consumer can convert" claim has no surviving positive occurrence |
| W-5 | Codex | The fleet measurement was prose-only — no command, scanner, consumer heads, or per-consumer results — while materially resizing children 3–5. The "9 of 27 kept files" claim named only eight | addressed — `research/fleet-blocker-scan.py` + `research/fleet-blocker-scan.json` commit the rule, the command, each consumer's head and `worktreeClean`, and every per-file hit. The unverifiable claim is replaced by measured figures (138 citing files, 179 removed targets, 53 surviving citers, 13 pack-managed). Rerunning the scanner found a **fail-open bug in the measurement itself**: provenance stores `sha256:<hex>` and the first version compared bare hex, so `packDefects` was empty for all 8 consumers while appearing healthy. That is now its own fixture criterion |
| W-6 | Codex | `classifierDigest` binds the builder but not the resweep, so an edit to hit discovery or citation logic leaves an existing `clear` verdict valid under an unchanged digest | addressed — `scripts/sd-ai-command-pack-thin-resweep.py` bytes join the digest inputs in `design.md` §2 and in step 3's plan, with the reasoning stated: the builder decides what is removed, the resweep decides what counts as a citation, and neither substitutes for the other |

Round 4 verdict: six blocking concerns, six addressed, one carrying a
parked follow-up task that blocks children 3–5 rather than this task.
Two remediation rounds remain available under the contract.

## Concern ledger — round 5 (remediation of round 4)

Round 5 reviewed the round-4 remediations rather than re-listing them.
Host lane completed. Codex lane completed (7 blocking concerns). Every
one was verified against the cited evidence before acting; none was
rebutted. Three invalidated numbers this task had already published,
which is the reason the measurement is now committed as code.

| ID | Lane | Concern | Disposition |
|---|---|---|---|
| V-1 | Codex | The rebuilt execution-surface rule still failed open: root agent instruction files were absent from it, so `mezmo_benchmark/CLAUDE.md:28` — which tells an agent to run `scripts/sd-ai-command-pack-full-check.sh` — was recorded as an advisory | addressed — `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `QWEN.md`, `copilot-instructions.md`, `.cursorrules`, `SKILL.md`, `*.prompt.md`, `*.instructions.md`, and the `.claude/rules/`, `.claude/skills/`, `.agents/`, `.github/instructions/`, `.codex/` prefixes joined the surface. That file is now a blocker; `mezmo_benchmark` went 23/11 → 26/14 |
| V-2 | Codex | `packDefects` could not recognize all pack-owned content: provenance deliberately never records a whole-file digest for managed-block, force-preserved, or generated targets (`installer/provenance.py:114`), and the digest-only rule declared every one of them consumer-authored. `.github/copilot-instructions.md`'s pack block tells Copilot to run the removed install-audit script and was recorded as advisory | addressed — ownership is now proven two ways: digest match, or position between the pack's `SD-AI-COMMAND-PACK:*:START`/`:END` markers for targets provenance cannot vouch. Force-preserved and generated targets stay consumer-authored by design. `packDefects` went 6 hits in 4 files → **13 in 6**, and the new child's PRD was rewritten around the larger, differently-shaped set |
| V-3 | Codex | The counts were reproducible but wrong. The scanner discovered candidates by grepping the literal `sd-ai-command-pack` while the prose claimed matching against removed paths. `sd-github-review/test/metadata.test.js:490` cites the removed `.agents/skills/sd-status/SKILL.md` with the pack name nowhere on the line, so the published `5/3` was at least `6/4` | addressed — discovery now enumerates tracked files and searches for the removal set itself (full paths, multi-segment suffixes, pack-named basenames), keeping the pack name only so globs stay discoverable. Codex's predicted `6/4` is exactly what the rerun produced. **Every fleet figure in this task, the parent, and the new child was restated**; all rose |
| V-4 | Codex | The committed measurement was not reconstructible: pack and five consumer trees were dirty, and the payload recorded only `HEAD` plus a boolean, so different uncommitted bytes at the same HEAD are indistinguishable | addressed — the payload records `indexDigest` and `worktreeDigest` per consumer, plus `packWorktreeDigest` and the scanner's own digest, at `schemaVersion: 2` |
| V-5 | Codex | "Blocks until a release fixes it" was not an executable dependency: the parent's implementation plan still said five children and omitted 2b, and the canary child still required only children 1 and 2 | addressed — 2b is in the parent's ordered list and gate section, and the canary PRD names it. The stronger point is stated in both: the dependency is enforced by the tool, not the list — a `packDefects` entry makes the verdict `blocked` and `--thin` refuses without a `clear` one |
| V-6 | Codex | Fail-closed edge cases unimplemented and untested: the scanner silently skipped unreadable hits and followed symlinks, contradicting the fail-closed claim; `block_strip` was documented as unimplemented while `implement.md` called the scanner the reference implementation | addressed — symlinked and unreadable receipt entries are recorded as `packDefects` with a stated reason instead of skipped, `block_strip` spans are implemented, and both got fixture criteria. The remaining stated divergence is one line: the scanner records `scheduled` per removed file rather than per reference |
| V-7 | Codex | Three normative disagreements: step 3 expected kept-path citations in `scheduled` while `design.md` reserved it for removed files and the PRD said neither bucket; parent C-A's digest contract omitted the resweep bytes child `design.md` requires; and the new child called the prompts `machine-other` when the partition classifies them `repo-native` | addressed — a citation of a surviving path is now stated to appear in **no** bucket; parent C-A carries the resweep bytes with the reasoning; the child PRD says `repo-native` (`platform: github`), verified against `docs/fleet/surface-partition.json` rather than assumed |

Round 5 verdict: seven blocking concerns, seven addressed. One
remediation round remains available under the contract.

**What round 5 changed about how this task treats evidence.** Three of
the seven were not reasoning errors but measurement errors, and each was
found by someone re-deriving a number rather than reading the prose that
quoted it. The scanner is committed for that reason. Where prose and
implementation state the same predicate, the implementation produced the
number, and only the implementation can be checked.

## Concern ledger — round 6 (final permitted round) — **DOES NOT PASS**

Round 6 is the third automatic round; the contract permits no fourth.
Host lane completed. Codex lane completed. **Five concerns survive, all
verified against their cited evidence.** Implementation of step 3 is
therefore **blocked pending user judgment** under
`.claude/sd-ai-command-pack/planning-adversarial-review.md` §4.

The host lane found one of these independently before Codex returned
(U-2's false positives): 67 fleet-wide entries matched only a generic
bare basename — the removal set contains `SKILL.md`, `config.toml`, and
`ci.yml` — of which 12 were in the two blocking buckets. Tightening the
matcher to multi-segment suffixes plus pack-named basenames moved
`mezmo_benchmark` from 27/15 to 26/14 and left every other figure
unchanged. That fix is already in; the residual false positives below are
a different, narrower case.

| ID | Lane | Concern | Disposition |
|---|---|---|---|
| U-1 | Codex | **Execution surface still incomplete.** `sd-github-review/.github/PULL_REQUEST_TEMPLATE.md:15` is a checklist telling a developer to run the removed `scripts/sd-ai-command-pack-full-check.sh`; PR templates are not an execution surface in the rule, so it records as an advisory | **unresolved** — verified. The fix is one more surface class, but the pattern across rounds 4/5/6 is that each round found a *new* class the previous round's enumeration missed (nested `scripts/`, agent prompts, root `CLAUDE.md`, now PR templates). The open question is not this row but whether an enumerated surface list can converge at all |
| U-2 | Codex | **A real citation is still undiscovered, and false positives remain.** `mezmo_benchmark/scripts/preflight-pr.sh:1449` assigns `"$repo_root/scripts/sd-ai-command-pack-review-learnings.py"`; tokenization yields `repo_root/scripts/...`, which exact and suffix matching both reject — no runtime-prefix normalization. Conversely `se-ai-command-pack/templates/skills/se-help/SKILL.md:51` cites its own **surviving** sibling `references/examples.md` and is recorded as a blocker via suffix collision with a removed skill copy | **unresolved** — both verified. These are opposite errors from one matcher, which is the uncomfortable part: tightening for the false positive worsens the false negative |
| U-3 | Codex | **Pack ownership still wrong in two ways.** Malformed markers are not rejected — an unterminated start extends the block through EOF, so consumer tail content can be labelled pack-owned, while `installer/fileops.py:138` rejects incomplete and duplicate markers. And force-preserved targets are unconditionally consumer-authored: `.github/PULL_REQUEST_TEMPLATE.md` is force-preserved (`installer/registry.py:2265`), its shipped template cites the removed full-check script at line 14, and **rwbp-coordinator and loadsmith carry byte-identical copies** — verified by digest | **unresolved** — verified. This makes child 2b's scope wrong: the PR template is a seventh surviving pack surface where unmodified, and the "six files" figure in four artifacts would move again |
| U-4 | Codex | **V-4's reconstructibility fix does not work.** `worktreeDigest` hashes `git status --porcelain` — the dirty *path set*, not file contents — so different bytes under the same dirty paths produce the same digest. Five consumer trees are dirty | **unresolved** — verified by reading the scanner. The fix is to hash contents, not status output |
| U-5 | Codex | **Residual contradictions.** `design.md:328` says the scanner does not implement `block_strip`, `design.md:456` says it does; `implement.md:294` still says "four surviving prompts" against five elsewhere; and the child PRD says all five prompts instruct agents to run removed scripts when `sd-help` instructs the agent to *read references* — the distinction that makes its suffix matches arguable rather than clear-cut | **unresolved** — verified. Three are text; the `sd-help` one is substantive and interacts with U-2 |

Codex confirmed one area clean: every per-consumer figure quoted in
`design.md`, `implement.md`, the parent PRD, the canary PRD, and child
2b matches the committed JSON exactly on current bytes. The figures are
transcription-correct and substantively still moving.

**Why this stops rather than continuing.** The remediations are known
and each is small. What is not known is whether they are *complete* —
and the evidence from three rounds is that they have not been: every
round produced a new surface class, a new matcher failure, or a new
ownership case that the previous round's enumeration did not contain, and
each was found only by an independent lane re-deriving the measurement.
Applying a fourth round of fixes with no review budget left would encode
a rule whose incompleteness is demonstrated but unmeasured. The contract
requires stopping here for user judgment, and the contract is right.

### Round 6 remediation (user-authorized past the §4 cap)

The user authorized continuing past the contract's three-round cap:
apply the known fixes, then keep running rounds until one returns clean
or stops finding new classes. All five concerns are now addressed, plus
two the host lane found while fixing them.

| ID | Fix |
|---|---|
| U-1 | Generalized instead of enumerated. Rounds 4, 5, and 6 each found a file type the previous enumeration missed, so the rule no longer classifies by file type alone: a citation appearing in **command position** blocks regardless of the file it sits in (`COMMAND_CONTEXT`, `fleet-blocker-scan.py`). The file-type list is retained as an additional trigger, so this only ever adds blockers. Scoped away from `.trellis/tasks|workspace|audit|journal/**`, which are archived records *of* commands — without that scoping 28 of `sd-github-review`'s 34 blockers were months-old history. `.trellis/spec/**` stays live |
| U-2 | Both directions fixed with one change. Bare-suffix guessing is gone; matching is exact, tail-of-path, or resolved relative to the citing file. `preflight-pr.sh:1449` is now caught by relative resolution of `$repo_root/scripts/...`; `se-help/SKILL.md:51` no longer collides with a removed skill copy. Accepted consequence, stated rather than hidden: `sd-help.prompt.md` leaves `packDefects` and child 2b's scope changes shape again |
| U-3 | Managed-block spans are parsed strictly; unterminated, nested, or unbalanced markers return *unresolvable* and the file falls to pack-owned rather than to a span running to EOF. Force-preserved targets are compared against the pack's own shipped bytes via `load_manifest()`, so `.github/PULL_REQUEST_TEMPLATE.md` is a `packDefect` where it is byte-identical to the template and a `blocker` where the consumer has taken it over |
| U-4 | `worktreeDigest` and `packWorktreeDigest` now hash the dirty file *contents* (`git status --porcelain -z`, then each path's bytes), not the status output |
| U-5 | All three text contradictions corrected; the fourth was substantive and resolved by U-2 — `sd-help` is out of the pack-defect set, and both `design.md` and child 2b's PRD now say why, as a rule consequence rather than a judgement call |

Two further defects the host lane found while verifying the above, both
of which had been silently passing:

- **Digest prefix mismatch.** Provenance stores `"sha256:<hex>"`; the
  scanner compared bare hex, so *every* pack file looked
  consumer-authored and `packDefects` read 0 for all 8 consumers while
  the report looked healthy. This is the failure mode the four-bucket
  rule exists to prevent, reproduced inside the tool that measures it.
- **`sd-help` false positive persisted after the U-2 tightening**,
  because `references/examples.md` still matched by suffix. That is what
  forced bare-suffix matching out entirely rather than merely narrowing
  it.

Verified after the fixes — all eight known counterexamples, each the
subject of a prior round's concern:

```
se-help SKILL false positive gone? True
preflight-pr.sh:1449 caught? True
PR template packDefect where unmodified? True
PR template blocker where edited? True
mezmo CLAUDE.md blocker? True
metadata.test.js:490 blocker? True
archive history in blockers? False
consumers with a clear verdict: 0 of 8
```

Additional fixture criteria this round adds, on top of those above:

- A removed path cited in **command position** inside a file type the
  execution-surface list does not name → `blocked`. This is the
  generalization; without a case for it the rule silently degrades back
  to enumeration.
- The same citation inside `.trellis/tasks/archive/**` → **not** a
  blocker. Historical records of commands are not an execution surface,
  and treating them as one made 82% of one consumer's blockers noise.
- A managed-block target with an **unterminated** start marker →
  `packDefects` with `[malformed markers]` stated, not a block running
  to EOF.
- A force-preserved target byte-identical to the shipped template →
  `packDefects`; the same target with one consumer edit → judged as
  consumer-authored. One case per side; either alone passes while the
  other is unimplemented.
- Two runs over the same dirty tree with **different bytes under the
  same paths** → different `worktreeDigest`. The previous fix passed a
  test that only changed which paths were dirty.
- A provenance digest recorded as `sha256:<hex>` matched against a file
  whose bare hex is identical → recognized as pack-owned. The
  fail-open direction is the one that matters: this bug reported zero
  pack defects, not spurious ones.

### Round 7 — the first round where both lanes converged

Host lane and Codex lane ran against the round-6 remediation. **Both
independently found the same three defects** (live task artifacts wrongly
scoped as historical, the interpreter regex matching the English word
"Python", and generated bookkeeping drowning the advisory list), which is
the first time in four rounds that the two lanes agreed on the defect set
rather than each finding classes the other missed. Codex found six more
the host lane had not; the host lane found two Codex did not. Every one is
fixed and each has a counterexample in the fixture list.

| ID | Lane | Concern | Fix |
|---|---|---|---|
| R7-1 | Codex | **Live agent guidance still advisory.** `anomaly-metric-creator/.trellis/spec/amc/backend/testing-quality.md:288` says "Use `scripts/sd-ai-command-pack-full-check.sh` as the local review gate" — an instruction that causes execution with no interpreter token anywhere on the line, so the "live spec stays live" scoping had nothing to act on | `COMMAND_CONTEXT` gained an imperative-plus-runnable-path alternative. The agent supplies the interpreter; the instruction is the command |
| R7-2 | both | **Historical scoping too broad.** All of `.trellis/tasks/**` was treated as historical, so an *unarchived* task's `implement.md` — a plan someone is about to follow — was advisory. `mezmo_benchmark/.trellis/tasks/07-02-audit-s3-iam-runscope-kms/implement.md:83` is `status: planning` and says `bash scripts/sd-ai-command-pack-full-check.sh` | Narrowed to `.trellis/tasks/archive/`. Only an archived task is a record of what was already run |
| R7-3 | both | **The interpreter regex matched English.** `\bpython3?\s` under `IGNORECASE` matched the word "Python": `rwbp-website/.gitignore:165`, the comment "Python bytecode from scripts/*.py", was a blocker | Interpreters are matched case-sensitively and must be followed by something path-shaped. "make sure" and "the node is" stop matching; `make -C build` and `python3 scripts/x.py` still do. Six prose lines left `blockers`, all verified as prose |
| R7-4 | Codex | **Broad globs falsely blocked.** `hoa-manager/scripts/update_repomix:8` passes `INCLUDE_PATTERNS="...,docs/**,.trellis/spec/**,..."`. Those globs match removed files *and* surviving ones, so the script keeps working — but a glob matching *any* removed entry was a hit | A glob is a hit only when **nothing it selects survives**. A population that still exists needs no repoint |
| R7-5 | Codex | **The PR-template remediation was unreachable.** Child 2b claimed that fixing the shipped template fixes the five byte-identical consumers. It cannot: `install_file()` returns `PRESERVED` for a force-preserved target whose bytes differ from the shipped ones, *even under `force=True`* (`installer/fileops.py:366`), so changing the template guarantees every existing copy is preserved forever | Planning fix, not a code fix. The pack edit is for fresh installs; all eight existing consumers repoint their own template in their conversion PR, where the classification already puts it once the shipped bytes change. Child 2b's PRD now says this and carries an acceptance criterion that the refresh reports `PRESERVED` |
| R7-6 | Codex | **Duplicate complete marker pairs were accepted.** `block_spans()` took `START/END/START/END` as two valid spans while `installer/fileops.py:150` rejects any repeat of either marker | Duplicate detection now keys on the marker *label*, because one file legitimately carries several distinct blocks — `rwbp-website/.gitignore` has `trellis-gitignore` and `obsidian-kb`. A repeated label is malformed; two different labels are not |
| R7-7 | Codex | **Gitignored files escaped every binding.** `occupied_receipt_targets()` tests filesystem existence, and `design.md:190` records that installed adapters can be gitignored — so an adapter could appear or disappear, changing the plan, while `head`, `indexDigest`, `worktreeDigest`, and `worktreeClean` all stayed identical | New `receiptOccupancyDigest` over every receipt target's on-disk state and bytes. Git's view is not the plan's view |
| R7-8 | Codex | **`classifierDigest` omitted its newest inputs.** The force-preserved ownership proof reads `manifest.json` and the shipped template bytes through `installer/manifest.py`; none of the three were in the normative digest list, so a template change could flip a file between `packDefects` and `blockers` with the digest unchanged | All three added to `design.md`'s list |
| R7-9 | Codex | **The parent's authoritative child map omitted 2b**, going straight from child 2 to child 3, while the parent PRD, parent implement plan, canary PRD, and 2b's own metadata all stated the dependency | Map row added, with the tool-enforced rationale next to it |
| R7-10 | host | **Fenced blocks and shell continuations were invisible.** The fleet writes long invocations as `bash toolchain.sh run-python -- \` with the script path on the next line, and puts bare invocations inside ```bash fences. Both put the removed path on a line carrying no command token — `se-ai-command-pack/.trellis/spec/backend/quality-guidelines.md:552` and `loadsmith/docs/repomix-map.md:1388` | Fence and continuation state are tracked per file. Fences must carry an **explicit** runnable tag: a bare ` ``` ` only ever closes, because real files nest fences and parity tracking desynchronised and then labelled ordinary prose as command context |
| R7-11 | host | **Every checklist item was command context.** Trellis PRDs state acceptance criteria as checklist items, so the rule that caught the PR template's "- [ ] Local gate: `bash …`" also caught "- [ ] A **real** pack refresh that modifies `docs/SD_AI_COMMAND_PACK.md` is …" | A checklist item qualifies only when the line also names a file with a runnable extension |
| R7-12 | both | **Generated bookkeeping was 93% of every advisory list.** `manifest.json` alone names every shipped target, so removing 179 of them produced 1055 "citations" per consumer. The design already said generated bookkeeping is not a citation source; the scanner did not implement it | The three `.sd-ai-command-pack/` files are `scheduled` — the conversion does rewrite them. Advisory lists went from ~1139 to ~84 per consumer and became readable |

Fixture criteria this round adds:

- A live `.trellis/spec/**` line saying "Use `<removed>.sh` as the gate" →
  `blocked`; the same path in a descriptive sentence → advisory.
- A removed path on a **continuation line** whose command token is on the
  previous line → `blocked`.
- A removed path inside a ```` ```bash ```` fence → `blocked`; inside an
  untagged fence in a file with nested fences → not a blocker, and no
  prose outside any fence is marked.
- A glob matching both removed and surviving files → **not** a hit; a
  glob whose entire population is removed → a hit.
- Two **distinct** managed blocks in one file → both parsed; the **same**
  block label twice → malformed, `packDefects`.
- A receipt target that exists on disk but is gitignored → changes
  `receiptOccupancyDigest`. `head`, `indexDigest`, and `worktreeDigest`
  cannot see it.
- A refresh of an existing consumer whose `.github/PULL_REQUEST_TEMPLATE.md`
  differs from the newly shipped template → `PRESERVED`, and the resweep
  reports its stale line as a `blocker`, not a `packDefect`.

**Fifth measurement** (all figures in the artifacts restated against it):
`sd-github-review` 14 blockers in 10 files, `se-ai-command-pack` 18/5,
`mezmo_benchmark` 29/19, `hoa-manager` 31/9, `rwbp-coordinator` 40/7,
`loadsmith` 53/5, `rwbp-website` 58/7, `anomaly-metric-creator` 168/20.
`packDefects` unchanged at 12 hits in 6 files, or 11 in 5 where the
consumer owns its PR template. No consumer is `clear`.

All 17 counterexamples accumulated across rounds 4–7 pass simultaneously.
That was the first time the fixture list closed rather than being extended
mid-round — but round 8 extended it again, so "closed" meant "closed
against the counterexamples known then", which is the only sense any
version of that sentence has ever had.

### Round 8

Four blocking concerns, one blocking contradiction, three smaller ones.
Codex found all of the blocking set; the host lane found two more while
probing the round-7 rules. Convergence did **not** hold: round 7's
agreement was about the defects already visible, not evidence that the
rule had stopped having new ones.

| ID | Lane | Concern | Fix |
|---|---|---|---|
| R8-1 | Codex | **Sentence-final punctuation lost the citation entirely.** The token pattern keeps `.` so extensions survive, but the cleanup strip did not remove a trailing period — so `scripts/sd-ai-command-pack-update-spec-kb.py.` matched nothing. Every one of the 8 consumers carries that exact line in `.gitignore`, and it appeared in **no bucket at all** | Trailing punctuation is stripped after the token is cut. Leading `./` is preserved, so `./scripts/x.sh` still resolves |
| R8-2 | Codex | **`block_strip` ownership was keyed by file, not by the block actually removed.** Conversion strips one exact marker pair per file (`installer/removal.py:337`); the scanner treated *every* pack block in a listed file as stripped. Each consumer's `.gitignore` carries two — `trellis-gitignore`, which goes, and `obsidian-kb`, which stays and whose generated-by header names the removed KB script | The stripped span is resolved from the same marker constants removal uses, so the two cannot drift. The surviving block's citation is now a `packDefect`. **This is a seventh surviving pack surface**, and child 2b's scope grew accordingly |
| R8-3 | Codex | **Two classification inputs were unbound.** `is_executable_surface()` reads the filesystem exec bit, which no digest recorded — with `core.fileMode=false`, `chmod +x` on a tracked Markdown file moves it onto the execution surface while `head`, `indexDigest`, `worktreeDigest`, `worktreeClean`, and `receiptOccupancyDigest` all stay identical. Separately, an unreadable tracked file was silently skipped despite the comment claiming it was reported | `executableBitsDigest` over every tracked file. Unreadable files are split: `binaryTrackedFiles` counts present-but-not-UTF-8 assets, `missingTrackedFiles` lists tracked-and-absent paths, and a non-empty `missingTrackedFiles` makes the verdict `blocked` — a sparse checkout is a tree the scan did not read, not a tree it cleared |
| R8-4 | Codex | **Command-shaped prose in a review ledger blocked.** `anomaly-metric-creator/docs/review-learnings.md` quotes reviewers verbatim, so it contains both `python3 scripts/….py` and `$((delay * 2))`; the second matched an unconditional `$(` alternative that was never about arithmetic | Command substitution must contain a command, not arithmetic. And `docs/review-learnings.md` — the pack's own generated ledger, path taken from `registry.py:1589` rather than guessed — joins `.trellis/audit/` as a record of the past |
| R8-5 | host | **Bare basenames were unmatchable after round 6.** Round 5 matched any basename and produced false blockers; round 6 removed basename matching outright and lost every citation that never spells a path. Real, in three consumers: `REPO_ROOT / "scripts" / "sd-ai-command-pack-full-check.sh"` | A basename owned by exactly **one** removed path and by **no** surviving file carries no ambiguity to lose. 36 real citations recovered across `mezmo_benchmark`, `se-ai-command-pack`, and `anomaly-metric-creator`; the `se-help` false positive stays gone, because `examples.md` names a survivor |
| R8-6 | host | **Symlinks to removed paths were skipped.** Only a symlinked *receipt* target was reported; a consumer symlink pointing at a removed path was silently dropped, and following a symlink is the most direct execution there is | Classified. No consumer has a tracked symlink today — which is the point: "measured zero" and "never looked" are different claims |
| R8-7 | Codex | **The canary PRD overstated destructive scope.** It described "166 machine files plus 13 retired files plus the four special cases" — 183 deletions — while every JSON row records 179 removed targets. The four special cases are not deletions: three bookkeeping files are kept and rewritten, and `.gitignore` survives with one block removed | Corrected, with the reason stated. This wording governs destructive work in someone else's repository |
| R8-8 | Codex | Two false statements in the scanner's own comments (`make -C build` claimed to match when it does not; "five consumer trees are dirty" when six are), and the parent design's opening claim that "nothing blocks the first conversion" contradicting its own child-2b prerequisite | All three corrected |

Fixture criteria this round adds:

- A removed path followed by a sentence period → a hit. This one is worth
  a fixture precisely because it failed *silently*: not misclassified,
  absent.
- A file in `block_strip` carrying two differently-labelled pack blocks →
  only the span the conversion removes is `scheduled`; a citation in the
  surviving block is a `packDefect`.
- A tracked Markdown file made executable → `executableBitsDigest`
  changes. `indexDigest` under `core.fileMode=false` does not.
- A tracked path absent from the worktree → verdict `blocked`, listed in
  `missingTrackedFiles`.
- `$((x * 2))` quoted in prose → not command context; `$(dirname x.sh)` →
  command context.
- A bare basename unique to the removal set → a hit; a basename shared
  with any surviving file → not.
- A tracked symlink whose target is removed → `blocked`.

**Sixth measurement.** Blockers: `sd-github-review` 14 hits in 10 files,
`se-ai-command-pack` 19/5, `hoa-manager` 32/9, `mezmo_benchmark` 39/24,
`rwbp-coordinator` 40/7, `loadsmith` 53/5, `rwbp-website` 59/7,
`anomaly-metric-creator` 191/21. `packDefects` **14 hits in 7 files**, or
12 in 6 where the consumer owns its PR template. No consumer is `clear`.

All 21 accumulated counterexamples pass together.

### Round 9

Ten concerns: three from the host lane and seven from Codex, with **no
overlap at all** — the first round where the two lanes found disjoint
sets. The host lane's three are one defect wearing three faces: the
boundary between **discovery** (which lines get looked at) and
**matching** (which lines count). Every previous round had improved one
or the other and never checked that they still agreed. Codex reviewed
`87ec77cd` and went after the *claims* instead — every place a ledger
said "fails closed" or "is bound" and the code or the schema did not
keep the promise. Five of its seven are empty classes today; that is the
point, since each was already being asserted as covered.

| ID | Lane | Concern | Fix |
|---|---|---|---|
| R9-1 | host | **A URL tail-matched as a repository citation.** `TOKEN` cannot contain `:`, so `https://example.com/docs/SD_AI_COMMAND_PACK.md` tokenizes to `//example.com/docs/SD_AI_COMMAND_PACK.md`, whose path tail is a removed file | A token beginning `//` is a URL authority, not a path; no repository-relative path can start that way. Measured **zero** occurrences in the blocking buckets of all 8 consumers when the fix landed — this closes the class before it has an instance, and the ledger says so rather than implying a defect was found |
| R9-2 | host | **The discovery prefilter hid what the matcher would have caught.** `needle_pattern` searched for full removed paths, their ≥2-segment suffixes, and only pack-named basenames. Matching meanwhile accepts a glob whose whole population is removed (R7-4) and a bare distinctive basename (R8-5) — neither of which shares a literal substring with anything in the needle set. **512 lines across the 8 consumers satisfied `cites_removed_path` and were dropped before it ran.** Two per consumer were inside `.github/copilot-instructions.md`, the pack's own managed block, which ships `.agents/skills/sd-*/SKILL.md` and `**/skills/sd-*/**` | The prefilter is gone, not widened: any substring gate has this failure mode, because a glob shares no substring with what it selects. The matcher now sees every line of every tracked file. Cost: 11 seconds fleet-wide. `packDefects` rose from 14/7 to 16/7 uniformly across all 8 consumers, and the Copilot block is a **7-hit** surface, not 5 |
| R9-3 | host | **The unambiguous-basename rule was still a guess.** "Owned by one removed path and no survivor" is not "can only mean that path": the survivor test only sees tracked files, and prose often names something the repository does not contain. Exposed the moment R9-2 let those lines through — `se-ai-command-pack/templates/skills/se-author/SKILL.md` says "`review.md`: findings, decisions, approved edits", a workspace artifact the skill writes at runtime, and it matched the removed `.claude/commands/sd/review.md`. Same shape as the round-6 `references/examples.md` false blocker, one level in. `security.md` and `update-spec.md` collide identically | The basename must also carry the pack name. `sd_ai_command_pack_lib.py` carries its own proof; `review.md` carries none. All 36 recoveries R8-5 was added for survive; the scan is now an explicitly distinctively-named-only lower bound on that rule |

| R9-C1 | Codex | **The shipped verdict schema was less bound than the research JSON.** `design.md`'s normative object listed `head`, `indexDigest`, `worktreeClean`, `classifierDigest` — and nothing else — while rounds 7 and 8 had added four more binding fields to the scanner precisely because each one could change a classification invisibly. The implementation checklist repeated the short list | The schema and the checklist now carry the full set, including `indexFlagsDigest` from R9-C3. The planned production artifact cannot be *less* reproducible than the research measurement it derives from |
| R9-C2 | Codex | **`R8-3` still failed open on a present-but-unreadable file.** `OSError` and `UnicodeError` shared one handler; a `PermissionError` on a readable-as-text file counted it as a binary asset and cleared it. Round 8's ledger claimed unreadable files were reported | The two are separate handlers. Binary means "decoded as not-UTF-8"; an `OSError` means bytes this scan did not read, which is the same epistemic state as absent, so it joins `missingTrackedFiles` and forces `blocked` |
| R9-C3 | Codex | **`assume-unchanged` and `skip-worktree` were unbound.** Either flag hides a file from `git status`, so its bytes can change while `head`, `indexDigest`, `worktreeDigest`, `worktreeClean`, `executableBitsDigest`, and `missingTrackedFiles` all stay identical — and the scanner reads the new bytes anyway | `indexFlagsDigest` over `git ls-files -v`, which prefixes each path with its flag letter. Empty across the fleet: no consumer sets either flag |
| R9-C4 | Codex | **R8-6's symlink handling missed three forms.** An absolute target was compared as-is against a relative removal set; a link pointing at another link was never followed; an unreadable link `continue`d silently. "Fails closed" was a claim the code did not keep | `resolve_link()` follows chains with a depth limit, rebases absolute in-repo targets, and returns `None` — classified as a blocker — for unreadable, cyclic, or outside-the-repository links. Still zero tracked symlinks fleet-wide |
| R9-C5 | Codex | **The R8-4 remediation was too narrow.** `\$\(\s*[\w./-]+\s` requires an argument, so `$(dirname x.sh)` matched but `$(pwd)` did not — and `tool="$(pwd)/scripts/removed.sh"` could stay advisory. R8's ledger claimed only arithmetic had been excluded | The trailing class accepts a closing paren. `$((delay * 2))` still fails at the first character, which is where arithmetic was always distinguishable |
| R9-C6 | Codex | **Child 2b counted seven surfaces and cleared six.** It claimed all seven were `repo-native` partition rows — `.gitignore` has no partition row and survives as a `block_strip` target — and then accounted for "five rewritten surfaces plus the template". The `obsidian-kb` block is rewritten only when `sd-ai-command-pack-update-spec-kb.py` *runs*; a pack refresh installs the corrected script and leaves the old block in place | Three routes to zero, not two, with the KB refresh named as an explicit consumer step in the children 3–5 checklist and a negative acceptance criterion — refreshed-but-not-KB-refreshed must still report the `packDefect`. Without it the pack side looks complete and `--thin` keeps refusing |
| R9-C7 | Codex | **Two normative passages stated different citation rules.** `prd.md` said matching is exact, tail, relative, or glob "and nothing looser", with bare-basename matching "tried and removed"; the scanner and `design.md` elsewhere implement the narrow unambiguous-basename rule. An implementer could conform to either and produce different verdicts | One authoritative list of five forms in `prd.md`, with `design.md` pointing at it. The narrow rule is stated as what it is — uniqueness against the tracked tree **and** a pack-distinctive name — rather than as the removed rule returning |

The counterexample list is no longer prose. `research/classifier-counterexamples.py`
executes it: 15 fleet assertions naming a real consumer, file, line, and
expected bucket, plus 20 predicate-level assertions, each tagged with the
round that found it. "All counterexamples still pass" was re-established
by hand every round until now, which meant it could not survive a context
break and could not be checked by anyone else.

```text
35 passed, 0 failed, 0 skipped (15 fleet + 20 unit)
```

Fixture criteria this round adds:

- A URL whose path ends in a removed file → no hit; the same path written
  bare on the same line → a hit.
- A file citing a removed population **only** by glob, with the pack name
  absent from the line → a hit. This is the case the prefilter dropped.
- A managed-block file whose in-block content cites a removed population
  by glob → `packDefects`, not `advisories`.
- A bare basename that is unique to the removal set but carries no
  pack-distinctive marker → **no** hit, even though it is unambiguous
  against the tracked tree.
- A tracked file that is present and unreadable → `missingTrackedFiles`
  and verdict `blocked`, not counted as a binary asset.
- A symlink whose target is absolute and inside the repository, and one
  whose target is another symlink → both resolve to the removed path; one
  pointing outside the repository, and a cycle → `blocked`.
- `$(pwd)/scripts/<removed>.sh` → command context; `$((delay * 2))` still
  not.
- A consumer refreshed to the fixed pack but **not** KB-refreshed → the
  `obsidian-kb` hit is still a `packDefect`.

**Seventh measurement.** Blockers: `sd-github-review` 14 hits in 10 files,
`se-ai-command-pack` 21/7, `hoa-manager` 34/9, `mezmo_benchmark` 44/24,
`rwbp-coordinator` 48/7, `loadsmith` 53/5, `rwbp-website` 65/8,
`anomaly-metric-creator` 205/21. `packDefects` **16 hits in 7 files**, or
14 in 6 where the consumer owns its PR template. No consumer is `clear`.
Every count rose or held; none fell, which is what a hidden-lines defect
predicts and a mis-tightened rule would not.
