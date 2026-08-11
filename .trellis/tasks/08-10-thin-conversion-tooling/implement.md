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
  the **unchanged fat path** and reports **`invalid`** — measured, not
  predicted; see the correction below, which supersedes the
  `refresh-required` this line originally guessed (R20-C7). The fat path
  really is unchanged: the receipt still lists the deleted targets, so
  `inspect_receipts` calls them missing-or-invalid exactly as it always
  has. `mode: "thin"` remains the only discriminator, and this fixture
  does not carry it.
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
`blockers`, `advisories` — each step failing closed, **plus the
undeclared-platform marker pass** (`prd.md:19`): a **populated** codex or
pi directory, a surviving `$CODEX_HOME` reference, a pi adapter file, or
the `codex` CLI invoked in command position, in a consumer whose registry
`platforms` omits that platform. Four markers, not three, and each is
bucketed by `design.md`'s ownership prerequisite rather than blocked
unconditionally — pack-owned content gives a `packDefect`, a stripped
block gives `scheduled`, everything else blocks. An empty directory and a
prose mention of the command are not markers. The
execution-surface prefixes are enumerated from `PLATFORM_REGISTRY` rather
than re-typed from `design.md`'s prose. Records the full
binding set from `design.md`'s verdict schema: `head`, `indexDigest`,
`indexFlagsDigest`, `hiddenBytesDigest`, `symlinkTargetsDigest`,
`platformMarkerDigest`, `scannedBytesDigest`, `worktreeDigest`,
`worktreeClean`, `receiptOccupancyDigest`, `executableBitsDigest`,
`binaryFiles`, `missingFiles`, and `classifierDigest`. The short list this step
used to name — `head`, `indexDigest`, `worktreeClean`,
`classifierDigest` — would have shipped a verdict *less* reproducible
than the research measurement it derives from: every field added after
that list was added because something changed a classification while the
short list stayed identical.

`classifier_digest` in `installer/conversion.py` gains **four** inputs in
the same commit, not one. `scripts/sd-ai-command-pack-thin-resweep.py`
because the builder decides what is removed while the resweep decides
what counts as a hit, as the execution surface, and as a citation —
without it an edit to the surface rule or the glob matcher leaves an
existing `clear` verdict valid under an unchanged digest. And
`manifest.json`, `installer/manifest.py`, and the bytes of every
force-preserved template the manifest names, because the force-preserved
ownership proof compares a consumer's file against the pack's shipped
template: a changed template flips
`.github/PULL_REQUEST_TEMPLATE.md` between `packDefects` and `blockers`
while every input the function hashes today stays byte-identical.

Those three have been in `design.md` §2 since round 7 (`R7-8`) and are
**absent from the shipped function** — `installer/conversion.py:372`
hashes six paths plus the consumer entry. Step 1 shipped the gap and no
round caught it, because every round measured the research scanner and
this is production code the research scanner does not call. Step 3 closes
it, and the closing check is a fixture that edits a shipped template and
asserts `classifierDigest` moves.

`research/fleet-blocker-scan.py` is the reference implementation of the
rule and the source of the measurement below. The shipped resweep
supersedes it; the research copy stays so the counts can be re-derived.

Checks:
- Two references to the same removed file, in two different surviving
  files, produce **two** `scheduled` entries. The research scanner
  records one entry per removed file rather than per reference — stated
  at `design.md`'s scheduled definition and harmless there, because its
  output is a summary — but the shipped resweep emits a verdict, and the
  four-bucket claim is per citation. Round 16 noted this as the one
  research-to-production divergence the harness cannot currently see.
- Editing a shipped force-preserved template moves `classifierDigest`.
  Without it the four new digest inputs above are asserted by nothing.
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
what make a rerun comparable.

> **Superseded measurement — kept for the shape, not the numbers
> (R17).** The per-consumer counts in the next paragraph are an early
> reading and disagree with the current one. Every later round moved
> them, and the authoritative figures are the most recent ledger entry at
> the end of this file. Read this paragraph for *what* the citations are
> — CI workflows, `package.json` scripts, repo-owned tests, shell
> preflights, agent instruction files, PR-template checklists — and never
> for *how many*.

Consumer-authored executable callers of
removed paths: `sd-github-review` 15 hits in 11 files,
`se-ai-command-pack` 26/11, `hoa-manager` 39/14, `mezmo_benchmark` 47/27,
`rwbp-coordinator` 52/11, `loadsmith` 56/8, `rwbp-website` 67/10,
`anomaly-metric-creator` 206/22 — CI workflows, `package.json` scripts,
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
  a **populated** `.codex/` or `.pi/` directory, a `$CODEX_HOME`
  reference, a pi adapter file, and a `codex` CLI invocation in command
  position each block when the registry `platforms` omits that platform,
  and each clears when it is declared. Four markers, not three; an empty
  directory is not usage and must not block (R14-C1), and prose naming
  the command must not block (R16-C2). Each disposition is decided by
  ownership first, per step 3's table.

### 4. Argument compatibility matrix

Every row of the design's matrix, as its own test: opposing mutators,
mutator-with-inspection, `--thin` without `--resweep-verdict`,
`--resweep-verdict` without `--thin`, payload selectors with **either**
direction, `--force` on revert, `--consumer` alone and with each
non-conversion mode, and the allowed rows. Land this before the mutators
so dispatch order can never silently pick a winner.

Two rows are not about flag pairs and were lost because of that. Both
are **shipped** as of round 19 rather than deferred to this step, because
each guards a command that exists today and corrupts a thin consumer:

- **`--remove` on a thin consumer refuses** (R18-C2). It deleted
  provenance while leaving the plugin enabled and the registry saying
  `thin`.
- **Ordinary `install.py TARGET` refuses** (R19-C1). This is the worse
  one because it is routine: a fleet refresh rewrites the receipt without
  the pin and discards `settingsAdditions`, silently de-thinning every
  converted consumer at once while the registry still reads `thin`.

Both read `conversion.thin_pin_state()`, not `read_thin_receipt` as this
step originally said — that reader collapses "fat" and "damaged" into the
same `None`, which is right for narrowing a payload and wrong for a
destructive guard (R19-C4). `malformed` refuses alongside `thin`.

Refusal rather than thin-awareness, for both, on the argument the matrix
gives: refreshing or undoing a thin consumer needs the pack root as well
as the target, and neither command takes one. **A thin-aware refresh is a
real surface and it is not optional** — `sd-fleet-refresh` runs ordinary
install against every consumer, so a converted consumer cannot be
refreshed until it exists. It is filed as its own step below and blocks
the canary, not this task's shipping.

Check: each rejected row exits nonzero with a message naming both flags;
each allowed row reaches its handler. A row that merely "does something
reasonable" is failure — the point is that it is specified. For the
`--remove` row specifically: assert on a converted fixture that the
command exits nonzero, that `.claude/settings.json` is byte-unchanged,
and that `.sd-ai-command-pack/provenance.json` still exists — the three
facts round 18's probe found false (`pluginStillEnabled=true`,
`settingsUnchanged=true`, `provenanceExists=false`). Assert the fat path
is untouched by running the existing `--remove` suite unchanged.

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
- **One injection per write step, not one for the pair (R19-C6).** The
  design fixes the order — settings, receipts with provenance last,
  deletions, registry — precisely so each interruption is a named state.
  Inject a failure after each and assert the state the table predicts,
  **and** that re-running the same command converges:
  - after the settings merge → reads fat with additions; re-run is a
    no-op merge and completes;
  - between the three receipt rewrites → `--check` says `invalid`
    (`inspection` requires all three); re-run completes;
  - immediately after provenance, before any deletion → `--check` says
    thin, the payload is still present, re-run deletes exactly the
    remainder;
  - part-way through the deletions → same, and the second run's plan is
    the remainder rather than the original 179.
  The negative is the point of the ordering: assert that no injection
  produces a consumer with deleted machine surfaces and a *fat* receipt,
  which is the one state a re-run cannot tell from a botched manual
  deletion.
- `--force` scope (R19-C6): a forced conversion overrides removal drift
  in **all three** buckets — a drifted delete target, a drifted retire
  target, and a drifted block-strip file — and overrides nothing else. A
  settings collision, a stale receipt, an unwritable root, and a missing
  resweep verdict each still refuse under `--force`. One test per row;
  the matrix previously said "delete drift, nothing else" while this plan
  applied it to three buckets and the reused helper honored all three.

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

**The two sets diverge when the receipt is stale, and right now they do
(R19-C2).** All eight consumer receipts hold 210 entries and none of
them lists `scripts/sd-ai-command-pack-pack-update.sh`, which the current
manifest ships and the partition classifies as a `shared` machine row —
so a consumer declaring `codex` retains it. Round 19 measured the gap
with the production functions:

```text
planned residual:  106
expected residual: 107
missing from every planned residual: scripts/sd-ai-command-pack-pack-update.sh
```

A receipt-derived residual can therefore convert cleanly and fail
`--check` on the next command, for a file the conversion never had a
chance to keep because the consumer never had it. This is not a bug in
either formula: one describes what is here, the other what should be,
and a stale install makes them different by construction.

**Conversion requires a current install, checked explicitly.** Before
planning, compare the consumer's installed version against the source
manifest version and refuse when they differ, naming both and the
`install.py TARGET` that fixes it. The version comparison is the cheap
proxy; the exact assertion is the one that matters, so also compute both
residuals and refuse when the source-derived set is not a subset of the
receipt-derived one, naming every missing target. That second check
catches a consumer whose version matches but whose tree was refreshed
against a partially applied install.

Rejected alternative: having conversion *add* the missing retained
targets. It sounds accommodating and it makes conversion a partial
installer — a two-root command that writes new files into a consumer
while deleting 179 others, in a single PR whose reviewers were told it
only removes. The resweep verdict would also not cover the added files.
A conversion that refuses a stale consumer costs one `install.py` run.

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
The marketplace **source locator** is in neither manifest. Declare
`PACK_REPOSITORY = "platypeeps/sd-ai-command-pack"` in
`installer/registry.py` and validate `ROOT`'s `origin` remote **against**
it per `design.md` §4 — normalize the remote to `<owner>/<name>` and
require exact equality. **Block** on a non-GitHub host, a missing or
unparseable `origin`, an owner mismatch, **or a different repository
under the same owner** (R18-C3: an owner-only check passes
`platypeeps/sd-ai-command-pack-fork` and writes it into every consumer).
Write no `autoUpdate` key. For this pack the merged additions are exactly
`{"extraKnownMarketplaces": {"sd-ai-command-pack": {"source": {"source":
"github", "repo": "platypeeps/sd-ai-command-pack"}}}, "enabledPlugins":
{"sd@sd-ai-command-pack": true}}` — assert that literal, not a shape.

Checks:
- Every residual entry exists on disk, asserted before the write.
- `install-audit.py --repo FIXTURE` exits **0**. Not "these three
  messages are absent" — a message-subset check passes while the audit
  fails on `provenance.json has no files map`.
- `install.py --check` on the fixture reports `state: current`.
- `read_consumer_pin` reports `state: "present"` with the expected
  version **and** `mode: "thin"` and a populated `settingsAdditions`.
- The written `extraKnownMarketplaces` entry equals the literal above,
  byte for byte after `json.dumps(sort_keys=True)`.
- A pack checkout whose `origin` is `git@gitlab.com:platypeeps/sd-ai-command-pack.git`
  blocks; so does one whose `origin` owner is `someone-else`; **so does
  `git@github.com:platypeeps/sd-ai-command-pack-fork.git`** — the
  same-owner wrong repository the owner-only rule accepted. Also cover a
  missing `origin` and a URL with three path segments. None writes any
  part of `settings.json` — the locator is validated in the plan phase,
  before the first consumer deletion.
- The three URL spellings of the canonical remote (`git@github.com:…`,
  `https://…/name.git`, `https://…/name`) all normalize equal and all
  pass.
- No key named `autoUpdate` appears anywhere in the merged file.
  Asserting `present` alone proves nothing: an untouched fat provenance
  already passes it.
- Settings: the exact marketplace and plugin entries are asserted by
  value, not just "unrelated keys survived". Cover an
  already-present-value case (idempotent, no duplicate) and byte-compare
  everything outside the additions.
- Malformed existing `settings.json`: blocks, does not overwrite.
- Collision matrix (R18-C4), one test per row of `design.md` §4's table,
  each asserting **both** the exit status and that `settings.json` is
  byte-unchanged on the blocking rows:
  - marketplace key present with a *different* source → blocks;
  - `enabledPlugins["sd@sd-ai-command-pack"]` is `false` → blocks;
    same key holding a string or object → blocks;
  - `settings.json` is a valid JSON array or string → blocks;
  - `extraKnownMarketplaces` present but not an object → blocks;
  - either key present and already byte-identical → succeeds, writes
    nothing, and **does not appear in `settingsAdditions`** — the
    assertion that separates "already true" from "we made it true";
  - absent file → created, and `createdFile: true` with both containers
    in `createdContainers`.

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
- Revert ownership (R18-C4): a recorded key whose value was **edited
  after conversion** is left in place and named in the report, and the
  command still exits zero. A recorded key already absent is not an
  error. A created container is removed only when it ends up empty; a
  container the consumer already had keeps its other entries. `settings.json`
  itself is deleted only when `createdFile` is true and the object is
  empty.
- Disable-marker precedence (R19-C5), three tests against `design.md`
  §5's table: conversion-added and unedited → the key ends as `false`,
  not absent; conversion-added and edited since → left as edited, named
  in the report; already `true` before conversion → left `true`, named
  in the report. The third is the one that would be silently wrong: it
  disables a plugin the consumer enabled themselves.
- Restore-path collision (R19-C3): a consumer file created at a path the
  conversion deleted makes revert refuse **before any write**, naming
  every occupied path, with receipts and registry unflipped and the
  tree otherwise untouched. `--force` does not override it and is still
  rejected outright. A path re-created with bytes equal to the source is
  **not** a collision and reverts as a no-op.
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

### 9b. Thin-aware refresh (blocks the canary, not this task)

Ordinary `install.py TARGET` currently **refuses** a thin consumer
(R19-C1). That is fail-closed and it is not the end state: `sd-fleet-refresh`
runs exactly that command against every consumer, so no converted
consumer can receive a pack update until this step exists. Nothing is
converted yet, which is the only reason refusing is survivable.

The shape, reusing what step 2 already built:

- Narrow the payload with the same `_residual_files_for_thin` predicate
  `--check` uses, so refresh and inspection agree by construction rather
  than by a second formula.
- Carry the pin forward: `read_existing_provenance_pin` already exists
  and `_run_inspection` already passes it. The fat writer drops the pin
  deliberately (`provenance.py:88`); the thin path must pass it and
  update only `version`.
- Refuse a refresh that would change the residual *set* rather than its
  contents — a newly shipped repo-native file legitimately enlarges it,
  but a platform change does not belong in a refresh, and silently
  re-deriving the residual from a different platform set is how a refresh
  becomes an unreviewed conversion.
- `--platform`/`--all` stay rejected on a thin consumer: the pin owns the
  platform set.

Checks: a converted fixture refreshes to a new version, stays thin, keeps
`settingsAdditions` byte-identical, and reports `state: current`
afterwards; the machine payload is not re-created; a fat consumer's
refresh is unchanged.

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

### Round 10 (host lane)

Round 9's deliverable was an executable counterexample list. Round 10's
host lane began by asking the obvious question about it — *does it fail
when the scanner is wrong?* — and answered it by mutation: revert one
rule, re-run the scan, re-run the harness, see whether anything goes red.
Nine rules were mutated. **Four survived**, meaning four of the scanner's
rules had no fixture that actually depended on them.

| ID | Concern | Fix |
|---|---|---|
| H10-1 | **Untracked, non-ignored files were never classified.** The scan enumerated `git ls-files`; a conversion runs against a working tree. An untracked script invoking a removed path breaks exactly as hard as a committed one, and the only signal it existed was `worktreeClean` — which the verdict does not require. Measured: 8 untracked files fleet-wide, all in `rwbp-coordinator`, none citing a removed path | `--others --exclude-standard` joins the enumeration. Ignored files stay out: the receipt targets among them are bound by `receiptOccupancyDigest`, and they are not part of a conversion PR. The research scanner's deliberate divergence from the shipped rule — it does **not** gate `clear` on a clean tree, because six of eight consumers are dirty and gating would report `blocked` everywhere for an unrelated reason — is now stated at the verdict rather than left as a silent difference |
| H10-2 | **A fixture was tautological.** The R9-3 case asserted that the bare basename `review.md` does not match — while the fixture's own survivor set contained `docs/review.md`, which excluded that basename from `unambiguous` no matter what the pack-name rule did. Reverting R9-3 left the harness green | The survivor set no longer contains the basename the case is about. Reverting R9-3 now fails both the unit case and the `se-author` fleet case |
| H10-3 | **Fleet assertions could not detect a scanner regression at all.** They read a stored JSON, so they re-checked a result produced *before* whatever change is being tested. "Run after any scanner change" was the docstring's claim; nothing enforced the pairing | The harness compares the scan's recorded `scannerDigest` against the scanner's current bytes and refuses to assert fleet cases on a mismatch. "40 passed" is now a statement about this scanner rather than about some scanner |
| H10-4 | **Case-sensitivity was unexercised.** The `(?-i:` guard exists because "Python bytecode from scripts/*.py" once blocked — but that line stopped matching for an unrelated second reason (its argument is not path-shaped), so no fixture depended on the guard. Reverting it left everything green | A fixture that fails only on case: `Make ./scripts/<removed>.sh executable` must not be command context, `make -f scripts/<removed>.sh all` must be |
| H10-5 | **Historical scoping was unexercised.** Same shape: the `docs/review-learnings.md` fixture stopped depending on it once R8-4 made arithmetic non-matching | An archived task plan carrying `bash scripts/<removed>.sh` in plain command position — advisory *only* because the archive prefix is historical |
| H10-6 | **The force-preserved ownership proof was unexercised.** No fixture named `.github/PULL_REQUEST_TEMPLATE.md`, so disabling the shipped-bytes comparison changed nothing the harness could see | Two rows that are only correct together: `rwbp-coordinator`'s copy is `packDefects` (byte-identical to the shipped template), `sd-github-review`'s is `blockers` (edited, therefore consumer-owned). Weakening the digest proof to bare membership now fails the second |

Mutation results after the fixes — nine rules reverted one at a time,
each with a full re-scan:

```text
R9-1 URL guard                     caught
R9-3 pack-distinctive basename     caught (both levels)
R8-1 trailing-period strip         caught (both levels)
R8-2 per-block strip ownership     caught
R7-4 glob whole-population         caught
R8-4 arithmetic vs substitution    caught
R7-3 interpreter case-sensitivity  caught (after H10-4)
historical scoping                 caught (after H10-5)
ownership proofs (two forms)       caught (after H10-6)
no-op control                      no failures
```

The list grew by three fleet rows and two unit rows, none of them from a
new defect in the scanner — all five exist because a rule was correct and
unprotected:

```text
40 passed, 0 failed, 0 skipped (18 fleet + 22 unit)
```

**Eighth measurement.** Two figures moved and neither is a rule change:
`se-ai-command-pack` is 22 blockers in 8 files rather than 21 in 7,
because that consumer's tree changed under the scan — which is what the
recorded head and digests are for. Every other row is identical to the
seventh. The untracked-file scope added zero hits.

### Round 10 (Codex lane)

Six blocking concerns, two of them demonstrated against the current fleet
rather than constructed. The lane found nothing the host lane found — the
second consecutive round with zero overlap.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R10-C1 | Codex | **The counterexample harness could pass a scanner regression.** Its 18 fleet assertions only queried the committed JSON: never called `scan()`, never compared `scannerDigest`, never read a consumer head. A regression that skipped every regular file would leave all unit cases unchanged and all fleet cases reading the old JSON — green. The docstring's claim that a head mismatch becomes `skipped` was also false: it skipped only an absent or `error` row | The digest gate landed in the host lane's `2e384eeb`; this round added the head check the docstring already promised. The harness now runs `git rev-parse HEAD` per consumer and skips explicitly on mismatch |
| R10-C2 | Codex | **The U-2 counterexample was unguarded twice.** The fleet case named `.agents/skills/se-help/SKILL.md`, which does not exist at the recorded `se-ai-command-pack` head — the real file is `templates/skills/se-help/SKILL.md:51`. With an expected bucket of `None`, a file that does not exist passes by naming nothing. The matching unit case was tautological: the synthetic removal set held no colliding `references/examples.md`, so the predicate returned false whether or not bare-suffix guessing was restored. All three negative fleet cases used `line=None`, making them file-wide | Path corrected; all three negative cases anchored to lines (`templates/skills/se-help/SKILL.md:51`, `hoa-manager/scripts/update_repomix:8`, `templates/skills/se-author/SKILL.md:74`); `.agents/skills/sd-help/references/examples.md` added to the synthetic removal set; and a case whose file is absent at the recorded head is now a **failure**, not a silent pass. Verified by mutation: reverting the tail rule to plain `endswith` now fails 4 cases, including both U-2 forms — before this fix it failed neither |
| R10-C3 | Codex | **R9-C3's fix was the wrong fix.** `indexFlagsDigest` hashes `git ls-files -v`, which binds the flag letter and the path — not the bytes the flag hides. A file already carrying `skip-worktree` can have its contents rewritten with `head`, `indexDigest`, `indexFlagsDigest`, `git status`, `worktreeDigest`, and `worktreeClean` all identical, and the scanner and converter then read different bytes | `hidden_bytes_digest()` hashes the contents of every flagged path alongside its flag letter. `design.md`'s schema gains `hiddenBytesDigest`, and the "every digest field is load-bearing" paragraph now records that this one field is two, and why. Still empty fleet-wide: no consumer sets either flag |
| R10-C4 | Codex | **`resolve_link()` resolved lexically, not on the filesystem.** Only the final component was tested with `is_symlink()`, so `top -> alias/full-check.sh` where `alias -> scripts` returned `alias/full-check.sh` and the caller missed a symlink that ultimately executes a removed path. A broken chain returned its nonexistent lexical target instead of `None`, and the `is_symlink()` call sat outside the `try` | Rewritten to `(repo / relative).resolve(strict=True)` relative to the resolved repo root, with `OSError`/`RuntimeError`/`ValueError` all failing closed to `None` — which the caller already treats as an unresolvable-symlink blocker. Intermediate components, chains, cycles, and broken links are now one code path |
| R10-C5 | Codex | **Invalid UTF-8 was treated as harmless binary.** Any unmanaged `UnicodeError` went to `binaryTrackedFiles` and continued without blocking. An executable shell file with one Latin-1 comment and an invocation of a removed script is still executable; strict decoding skipped every line of it and could yield `clear`. "Not UTF-8" does not establish "binary asset that cannot carry a citation" | Read path is now `read_bytes()`; a NUL byte decides binary, and everything else is decoded with `errors="replace"` and classified normally. At the recorded rwbp head the 16 decode failures were genuine NUL-bearing PNG/ICO files, so the measured counts do not move — the class is closed before it has an instance |
| R10-C6 | Codex | **Demonstrated: Prism rules were classified advisory.** `rwbp-coordinator/.prism/rules.json:55` is a live Prism **required** rule naming three removed paths, recorded under `advisories`. `.prism/` was absent from the agent-executed prefixes: a `.json` suffix reads as inert data while the contents are rules an agent is expected to obey | `.prism/` added to `EXECUTABLE_PREFIXES`. Verified consumer-authored, not an eighth pack surface: the text is not in `templates/.prism/rules.json`, so the partition correctly keeps `.prism/` as `shared / consumer-config` and conversion leaves the rule behind. Filed as child 3's requirement 3 with its own acceptance criterion, not as child 2b work |

Four non-blocking contradictions were also fixed: `design.md`'s Copilot
block said five hits (now seven, with the two globs and both consumers'
exact lines); `thin-prompt-surface-repoint/task.json` said `14 in 7 / 12
in 6` (now `16 in 7 / 14 in 6`); `thin-canary-conversion/prd.md` said 14
in seven; and the parent `design.md` plus this task's `design.md`
summarized matching as exact/basename/glob against the authoritative five
forms in `prd.md:42`. All four now agree with the scanner.

**Ninth measurement.** Two figures moved, both from R10-C6 and both
verified genuine rather than a counting change: `rwbp-coordinator`
49 blockers in 8 files (was 48/7 — `.prism/rules.json:55` names three
removed paths) and `se-ai-command-pack` 23 in 9 (was 22/8 — its
`.prism/rules.json:43` names `scripts/sd-ai-command-pack-review-preflight.mjs`).
Every other row is identical to the eighth. `packDefects` unchanged at
16 in 7, or 14 in 6 where the consumer owns its PR template. No consumer
is `clear`. The harness is 40 passed, 0 failed, 0 skipped.

### Round 11 (host lane)

Round 10's method applied to round 10's own fixes: every rule that round
added was reverted, the scan re-run, and the harness re-run. **Three of
four survived** — the same shape round 10 found, one round later, which
is the argument for keeping the sweep rather than declaring the harness
done.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| H11-1 | host | **R10-C6's `.prism/` prefix had no fixture.** Reverting it left the whole harness green while `rwbp-coordinator/.prism/rules.json:55` silently fell back to `advisories` — the exact classification round 10 was opened to fix | Two fleet cases, `rwbp-coordinator/.prism/rules.json:55` and `se-ai-command-pack/.prism/rules.json:43`, both `blockers`. Two consumers rather than one, so the rule cannot be dismissed as a single consumer's drift. Reverting the prefix now fails 2 |
| H11-2 | host | **R10-C5's binary rule was unreachable from the harness.** It was an inline `if b"\0" in raw` inside `scan()`, so a fixture could only reach it by standing up a synthetic consumer with a receipt and a partition. A rule the harness cannot call is a rule the harness cannot protect | Extracted as `is_binary(raw)`, called from the same place. Three unit cases: a NUL-bearing PNG header is binary; a Latin-1 shell comment above `bash scripts/sd-ai-command-pack-full-check.sh` is **not**; plain ASCII is not. Reverting to round 9's strict-UTF-8-means-binary now fails the middle one |
| H11-3 | host | **R10-C4's symlink fix had fixtures for the shape that already worked.** The five existing cases were all symlinked *leaves*; the defect Codex constructed was an intermediate symlinked *directory*, and a broken chain returning its lexical target. Neither was covered | Two cases added: `through-directory -> alias/removed.sh` where `alias -> scripts` must resolve to `scripts/removed.sh`, and `broken-link` must be `None` rather than its nonexistent lexical target. Reverting to a lexical walk now fails 7 |
| H11-4 | host | **R10-C3's `hiddenBytesDigest` had no fixture.** Reverting it to the flag-and-path-only form it replaced left the harness green | A temporary git repository: commit a file, set `skip-worktree`, rewrite its bytes to invoke a removed path. The fixture asserts all three halves — `git status --porcelain` is empty, `git ls-files -v` is byte-identical, and `hiddenBytesDigest` **moves**. The first two are what make the third mean something; without them the case would not show that the flag hides anything |
| H11-5 | host | **The harness's own count line did not add up.** It printed `50 passed ... (20 fleet + 24 unit)`, because the unit total summed two of the three case groups. A summary line that is not derived from what ran is the same defect class as a fixture that asserts nothing — it just fails in the report instead of the check | The label now sums every group. Caught by reading the number, which is the only way this class is ever caught |

Two claims the harness makes about itself were also verified rather than
assumed, since round 10 found both of them false at the time: a fleet case
naming a nonexistent file **fails** (probed with
`.prism/does-not-exist.json` — `FAIL fleet PROBE: ... does not exist; a
case that names no file asserts nothing`), and a consumer whose head has
moved is **skipped**, with exit status 1 rather than 0 (probed by
rewriting one consumer's recorded head — `SKIP fleet R10-C6:
rwbp-coordinator is at 5044c11de3ab, the scan recorded 000000000000`, five
cases skipped, `skip-exit=1`).

Harness is now 50 passed, 0 failed, 0 skipped — 20 fleet and 30 unit. The
control re-run with no mutation applied produces no failures, so the
sweep's failures are attributable to the mutations and not to a dirty
substrate. Measurement unchanged from the ninth: no rule changed, only its
coverage.

### Round 11 (Codex lane)

Six blocking concern groups. Two of them — R11-C1 and R11-C2 — say the
same thing the host lane had just said, and say it about the host lane's
own fix: a stored result is not evidence, and a rule with no failing
fixture is not protected. The host lane fixed four such rules; Codex found
five more it had not thought to mutate.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R11-C1 | Codex | **Demonstrated: the harness accepted a stale row at an unchanged HEAD.** Codex swapped one consumer's fresh row for the committed one. Same HEAD, 23 blockers recorded against 29 actually present, and all 40 cases passed — six of the missing ones live in *untracked* files, which no recorded binding covers. Two rounds of trying to make a stored result trustworthy (H10-3 pinned the scanner bytes, R10-C1 checked HEAD) had not, and could not, close this | The fleet cases no longer read a stored row at all. They call `scan()` on the consumer, in-process, with the scanner that is on disk. Nothing is left to go stale; the binding fields exist to make the *committed measurement* re-derivable, not to certify a cached assertion. Cost: ~11 seconds. The committed JSON is still read for one purpose — to say out loud, as a skip, when the artifacts' figures came from different scanner bytes than the assertions just ran against |
| R11-C2 | Codex | **Demonstrated: five more load-bearing rules had no falsifying fixture.** Reverting each left 40/0/0 while changing real consumer results: `.prism/` (blockers to advisories in two consumers), fenced/continued command recognition (5 real blockers in `loadsmith`, 2 in `se-ai-command-pack`, 1 in `sd-github-review`), generated-bookkeeping scheduling (182 scheduled to 179, +1055 advisories per consumer), untracked enumeration (`se-ai-command-pack` 29 to 23), NUL-based binary detection. Also constructed: moving a negative case's cited line to 999999 left the harness green, because "no bucket holds this file at this line" is trivially true of a line that does not exist | Live scanning (R11-C1) makes every fleet case detect a scanner regression, and eight fixtures were added on top: two fleet cases for fence/continuation (`loadsmith/docs/repomix-map.md:1388`, `sd-github-review/.trellis/tasks/08-09-review-coordinator-stale-check/implement.md:139`), one for generated bookkeeping, four unit cases for `command_lines`, and three for enumeration. `enumerate_files()` was extracted from `scan()` for the same reason `is_binary()` was in round 11's host lane: a rule the harness cannot call is a rule it cannot protect. A cited line that does not exist is now a **failure**. Verified by re-running the sweep: every one of the five reverts now fails |
| R11-C3 | Codex | **Demonstrated against five consumers: the pack's own hidden bytes were unbound.** `shipped_template_digests()` reads the pack's `templates/` to decide whether a force-preserved consumer file is pack-owned or consumer-owned, so the pack worktree is an input to every consumer's classification. `skip-worktree` on `templates/.github/PULL_REQUEST_TEMPLATE.md` plus a byte change moved five consumers' pack defects 16 to 14 and their blockers up by one, with every recorded binding identical. R10-C3 closed this on the consumer side and left the identical hole on the pack side. Separately, constructed: an *ignored* intermediate symlink repointed from `scripts` to `safe` changes what a tracked link resolves to, and nothing bound the resolution | `packIndexFlagsDigest` and `packHiddenBytesDigest` at the payload top level, and `symlinkTargetsDigest` per consumer over what each symlink actually resolves to. `design.md`'s "every digest field is load-bearing" paragraph names all three and why |
| R11-C4 | Codex | **Demonstrated from the registry: the execution-surface list was hand-written and had drifted.** It named `.opencode/command/`; the registry's surface is `.opencode/commands/` (`installer/registry.py:309`), so the prefix matched nothing. Enumerating `PLATFORM_REGISTRY` found the typo was the small half: **twelve** further platform directories — `.agent`, `.codebuddy`, `.cursor`, `.devin`, `.factory`, `.kilocode`, `.kiro`, `.pi`, `.qoder`, `.reasonix`, `.trae`, `.zcode` — were absent outright, every one of them holding commands, rules, or skills an agent executes | Derived from `PLATFORM_REGISTRY` instead of written down, so a platform added later is covered without anyone remembering this file. `.github` stays excluded from the wholesale rule and keeps its explicit sub-prefixes: it is the host's shared directory, not one agent's. A property fixture asserts every registry platform directory has a matching prefix — the check enumerates from the source rather than searching for the strings just typed. Fleet delta: **zero**. Twelve missing platform directories and not one consumer file under them cites a removed path, so the class is closed before it has an instance |
| R11-C5 | Codex | **The production spec contradicted the round-10 untracked fix.** `design.md` specified enumerating tracked files and matching every line of every tracked file, while the scanner adds untracked, non-ignored files — a difference worth 6 real blockers in `se-ai-command-pack`. An implementer following the design would produce different answers from the reference | The resweep spec now states the population explicitly — `git ls-files` **plus** `git ls-files --others --exclude-standard`, ignored files excluded — and says why, at the point where an implementer reads it. The retrospective bullets and the `executableBitsDigest` schema line were corrected the same way |
| R11-C6 | Codex | **Canary sequencing was incompatible with the specified `--thin`.** Child 3 requires "convert, open PR, land it green, then flip `mode: thin`"; child 1 defines `--thin` as writing both roots in one invocation, which is why it refuses unless both are writable | One authoritative sequence, written into both tasks. `--thin` **writes** the registry edit as part of the same validated two-root run; it does not **land** it. The two edits travel in two pull requests and the pack PR merges after the consumer PR. The window between them is exactly the pin-vs-mode skew the parent design already accepts and `sd-status fleet` reports. Child 3's requirement 1 now says *land the flip `--thin` already wrote*, never *run a second tool* |

Both non-blocking contradictions were fixed: the parent's "Ships the
resweep" now says shipped **in the pack release**, source-only, never
installed into a consumer (the child PRD's `prd.md:70` is the
authoritative statement), and `design.md`'s Prism paragraph no longer
reads as though a pack-shipped file is pack-owned line by line —
ownership is decided against the pack's shipped bytes, which is what makes
`rwbp-coordinator`'s drifted rule a consumer-authored blocker.

**Tenth measurement.** One figure moved: `se-ai-command-pack` 29 blockers
in 10 files, up from 23 in 9, because that consumer's untracked working
tree changed again between rounds — the same volatility R11-C1 showed a
stored row cannot survive. Every other row is identical to the ninth.
`packDefects` unchanged. No consumer is `clear`. Harness 63 passed, 0
failed, 0 skipped — 23 fleet and 40 unit, up from 50, and every addition
exists because a mutation proved the old set could not tell.

### Round 12 (Codex lane)

Five blocking groups. The first is the largest single finding of the
twelve rounds: a **requirement the PRD has stated since round 1 was never
implemented**, and every published blocker count was understated because
of it.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R12-C1 | Codex | **Demonstrated against all eight consumers: the undeclared-platform marker pass does not exist.** `prd.md:19` and parent `design.md:150` both require it — a codex or pi usage marker in a consumer whose registry `platforms` omits that platform is a **blocker** — and `scan()` had no such pass, only citation matching. Every consumer has a `.codex/` directory; no registry row declares `codex`. The reason this matters is not bookkeeping: `retainVendoredFor` intersects the consumer's *declared* platforms, so an undeclared Codex user has `.agents/**` deleted, and Codex cannot consume the machine-installed plugin at all | Three markers implemented, aggregated one entry each: a platform directory probed **from the filesystem** (so an empty or wholly untracked one counts), a surviving `$CODEX_HOME` reference, and a registry adapter-marker file. `PlatformInfo.trellis_local_only` excludes Trellis's own `.codex/` paths — the pack's own constant saying which paths are not its concern — so a Trellis repository is not blocked for a reason the conversion does not cause. Removed files and historical prefixes are excluded for the reasons those buckets already exist. **Seven of eight consumers gained a blocker**; `sd-github-review` is the one with a wholly Trellis-local `.codex/` and no surviving `$CODEX_HOME`, which is what makes the rule falsifiable rather than universal |
| R12-C2 | Codex | **Demonstrated: a directory is invisible to every recorded binding.** An empty `.codex/` added to a clean checkout leaves `head`, both index digests, hidden bytes, worktree digest and cleanliness, receipt occupancy, executable bits, symlink targets, binary count, and the missing-file list byte-identical — while the verdict must change from `clear` to `blocked`. Git does not track a directory | `platformMarkerDigest` binds the occupancy. The fixture is exact: build a synthetic consumer, scan it, `mkdir .codex` **after** the commit, scan again, and assert that every one of the eleven other bindings is unchanged and this one moved |
| R12-C3 | Codex | **Three claimed fail-closed rules were mutation-invisible, and the `.github` exclusion was only positively fixtured.** Reverting "unreadable unmanaged file → `missingTrackedFiles`", "symlinked receipt target → `packDefects`", and "malformed markers → pack-owned" each left 63/0/0. Including `.github/` wholesale moved two real advisories to blockers and also left 63/0/0 | These rules describe filesystem states no fleet consumer is in, so no real-consumer fixture could reach them and no pure predicate exposed them. The harness now **builds a consumer**: a temporary git repository with a real receipt, which `scan()` runs on end to end. Six synthetic fixtures cover the three rules, the `.github/ISSUE_TEMPLATE/` negative, the empty directory, and R12-C4. Verified by mutation: each revert now fails |
| R12-C4 | Codex | **Constructed and executable: NUL means "binary", and binary does not mean "cannot execute".** Codex fed bash a NUL-bearing source stream and it ran. A shell script carrying one NUL plus an invocation of a removed path could therefore clear. The only fixture was a NUL-bearing PNG | The NUL test now decides only whether the *bytes* look like an asset; it is not licence to skip a file the execution-surface rule says can run. A file that is both is decoded leniently and classified like any other. Fixture: a synthetic `nul.sh` carrying a NUL and a removed-path invocation must block |
| R12-C5 | Codex | **The production spec still described the pre-round-11 execution list.** The scanner derives prefixes from `PLATFORM_REGISTRY`; `design.md` still hand-listed directories, kept the singular `.opencode/command/` that matches nothing, and omitted the twelve round-11 additions. Step 3 says to apply the design's rule. The same checklist claimed the full binding set and omitted `symlinkTargetsDigest` | The design's clause is now "any platform directory the registry defines", with the drift it replaced named so a future editor does not re-type the list; `.github`'s exclusion and its explicit sub-prefixes are stated in the same place. Step 3 names `symlinkTargetsDigest` and `platformMarkerDigest`, and now also names the marker pass, which it had never mentioned |

Both non-blocking items fixed: `scheduled` is now defined in the PRD as
"a file the conversion rewrites rather than leaves alone" — which covers
both the removed files and the three kept-and-rewritten bookkeeping ones,
and explains the 182-vs-179 difference at the definition instead of
leaving it to a later paragraph — and the matcher docstring says five
ways, matching what it then lists.

One environment note, recorded because it would otherwise look like a
missing consumer: the review prompt named
`/Users/sven/repos/platypeeps/mezmo_benchmark`, which does not exist. The
registry's `pathHint` resolves to `/Users/sven/repos/mezmo/mezmo_benchmark`
and that is the checkout both the scanner and the review used. The
scanner has never read the path from prose.

**Eleventh measurement.** Seven rows moved, all from R12-C1 and all
verified by naming the marker that fired: `rwbp-coordinator` 51 blockers
in 10 files, `loadsmith` 55 in 7, `hoa-manager` 36 in 11, `rwbp-website`
67 in 10, `mezmo_benchmark` 46 in 26, `se-ai-command-pack` 30 in 11,
`anomaly-metric-creator` 206 in 22. `sd-github-review` holds at 14 in 10.
`packDefects` unchanged at 16 in 7, or 14 in 6 where the consumer owns its
PR template. No consumer is `clear`. Harness 78 passed, 0 failed, 0
skipped — 27 fleet and 51 unit.

**Fleet consequence, recorded in child 3 rather than here.** Every canary
must now either declare `codex` in its registry row or stop using Codex,
before conversion. If any declares it, `retainVendoredFor` retention runs
against a real consumer for the first time — the parent design calls that
path untested — so its residual is compared against that consumer's own
receipt rather than assumed.

### Round 13 (Codex lane)

Six blocking groups, and five of the six attack round 12's own fixes one
round after they landed. Round 12 fixed the missing marker pass; round
13 showed the fix was wrong in both directions at once.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R13-C1 | Codex | **The Trellis-local exemption hid real usage and invented false blockers, demonstrated both ways.** A synthetic consumer whose entire Codex surface was `.codex/config.toml` returned `clear` — and `sd-github-review` is that consumer, with a project-scoped `config.toml`, an undeclared registry row, and `.agents/skills/**` in its receipt that `retainVendoredFor` keeps only for a declared codex or pi consumer. It was the one consumer round 12 reported as marker-free, which the ledger cited as proof the rule was falsifiable. Conversely an empty `.codex/hooks/` blocked. And the exemption never worked for pi at all: `is_trellis_local` matched patterns ending in `/` with a literal `startswith`, so `.pi/skills/trellis-*/` never matched the glob it contains | The exemption is gone and `prd.md:19` is implemented as written: the directory blocks, unqualified. Its premise was that Trellis-local content is usage the conversion does not affect, and that is false — whoever wrote those files runs Codex in that repository, and conversion deletes `.agents/**` regardless of which tool authored the `.codex/` file. The resolution was never "do not block": it is the canary's recorded choice, declare `codex` or remove the usage. `sd-github-review` gains its first marker; `se-ai-command-pack` gains a directory marker beside its `$CODEX_HOME` one |
| R13-C2 | Codex | **The pi adapter branch had no fixture.** Disabling only `if adapters:` left the harness at 78 passed, 0 failed. The directory and `$CODEX_HOME` mechanisms were separately protected; the third of the three markers `prd.md:204` requires was not | A synthetic consumer carrying `.pi/prompts/trellis-continue.md` — one of the registry's own marker paths — asserts both that the directory blocks and that the adapter is a **separate** entry naming that file. Reverting the branch now fails |
| R13-C3 | Codex | **A clean filter hides the bytes from every binding.** Codex built a repository whose `.gitattributes` maps a file through a clean filter to the committed blob. `git status` is empty, `worktreeClean` is true, `worktreeDigest` — which hashes only the paths git reports dirty — sees nothing, and all twelve per-consumer bindings including `platformMarkerDigest` stay identical, while the worktree file says `bash <removed script>` and the verdict moves `clear` to `blocked` | `scannedBytesDigest`: every path the scan read, paired with the hash of the bytes it read. Every other binding is a proxy for those bytes, and five rounds each found a different way for a proxy to be wrong. The fixture reproduces the state exactly, including the `git add` that refreshes the stat cache — without it git reports the file modified forever and the construction proves nothing |
| R13-C4 | Codex | **The synthetic consumer was not one.** Its receipt listed three targets, omitted the three generated bookkeeping files, gave `manifest.json` no `files` list and `provenance.json` an empty map. The production structural audit rejects that repository with five errors, so assertions that `scan()` classifies it correctly say nothing about whether `--thin` would ever reach those states | The fixture writes the receipt the installer would have written: all six entries, a real `files` list, and a provenance map that vouches exactly what production vouches — **not** the managed-block and force-preserved targets, which is why the scanner has three separate ownership proofs. A synthetic case runs `scripts/sd-ai-command-pack-install-audit.py` against the fixture and requires exit 0 with no error lines, so the fixture's faithfulness is itself a checked assertion. Vouching `.github/copilot-instructions.md` immediately broke the malformed-marker case, which is the rule working |
| R13-C5 | Codex | **Round 12 closed only the path half of the NUL fail-open.** Execution is decided by path — `nul.sh` is a script — *and* by content: a line in command position runs what follows whatever the file is named. Codex built the other combination, a NUL-bearing `notes.dat` whose second line invokes a removed script, and it returned `clear` while the identical file without the NUL blocked | An unmanaged asset is no longer skipped. It is decoded leniently and read for command position only: the one form that executes still blocks, and the weaker citation forms stay suppressed, which is what the NUL test is actually for — a PNG whose bytes happen to contain a path is not a citation. Fixtures assert both halves: `notes.dat:2` blocks, and nothing from that file reaches `advisories` |
| R13-C6 | Codex | **Four remaining divergences between the production spec and the scanner.** The normative verdict object omitted `platformMarkerDigest`; the design's execution list named `Makefile` and `justfile` while the scanner also tests `makefile`, `GNUmakefile`, and `Justfile`; the design scoped agent instruction files to the repository root while the scanner tests the basename at any depth; and the PRD's unqualified marker rule disagreed with the scanner's exemption | The schema names `platformMarkerDigest` and `scannedBytesDigest`; the basename list is the scanner's, with the reason the case variants matter (`make` reads all three spellings); the agent-instruction clause says "at any depth, not only at the repository root"; and R13-C1 removed the disagreement by making the scanner do what the PRD says |

Both non-blocking items fixed. `binaryTrackedFiles` and
`missingTrackedFiles` are now `binaryFiles` and `missingFiles`: the
population has included untracked, non-ignored files since H10-1, so the
old names described the wrong set — ledger rows above round 13 keep the
names they were written with. And the canary task named
`platypeeps/rwbp-coordinator`; the owner is `rwbp`, which is also what
its `pathHint` resolves to.

**Twelfth measurement.** `sd-github-review` 15 blockers in 11 files (it
gains the marker R13-C1 found), `se-ai-command-pack` 25 in 11,
`hoa-manager` 36 in 11, `mezmo_benchmark` 46 in 26, `rwbp-coordinator`
51 in 10, `loadsmith` 55 in 7, `rwbp-website` 67 in 10,
`anomaly-metric-creator` 206 in 22. `packDefects` unchanged at 16 in 7,
or 14 in 6 where the consumer owns its PR template. No consumer is
`clear`. `se-ai-command-pack` moved 30 to 25 for the reason it has moved
every round: its worktree is dirty and its HEAD advanced between scans,
which is what the binding fields exist to record. Harness 89 passed, 0
failed, 0 skipped — 28 fleet and 61 unit.

Mutation sweep over the round-13 rules, each a true revert against a
regenerated scan: directory marker off → 7 failed; pi adapter branch off
→ 1 failed; `scannedBytesDigest` pinned to a constant → 1 failed; assets
skipped before command-position detection → 1 failed; control → 89
passed, 0 failed.

### Round 14 (Codex lane)

Eight blocking groups. Six of the eight fault a round-13 fix, and one
faults a round-13 fix that was itself a correction of a round-12 fix.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R14-C1 | Codex | **The unqualified marker rule is wrong in both directions, demonstrated.** Not sufficient: an empty `.codex/` blocks, while the conversion plan against a consumer holding one is byte-identical — 166 delete, 13 retire, 27 keep either way. Blocking there demands a declaration that changes nothing. Not necessary: on a temporary `sd-github-review` with `.codex/` deleted the marker set is empty, while its surviving guidance invokes `codex exec`. And nothing repository-visible exists at all for a consumer whose Codex use is global | Three changes. The directory marker requires at least one file under it. A fourth marker matches the `codex` CLI in surviving files, the same way `$CODEX_HOME` is matched. And both content markers now exclude **pack-managed** files: a fat install ships pack guidance naming `codex exec`, and reading that back as consumer usage would fire on every consumer that installed the pack. The global case is not closed by the scanner and is not pretended to be — it is an operator declaration in child 3, recorded beside the marker evidence, and an unanswered question is not a `clear` verdict |
| R14-C2 | Codex | **`scannedBytesDigest` did not bind the bytes ownership was decided from.** `scan()` hashed the first `read_bytes()`, then `file_digest(full)` **re-read the same path** for the ownership comparison. Codex made the two reads disagree with a split-read fixture and moved a cited line from `packDefects` to `advisories`, verdict `blocked` to `clear`, `changedBindings: []` — then reproduced the fail-open form with an ACL race | There is no second read. Ownership is decided from the same bytes the digest hashed, so a second-read disagreement cannot exist. Fixture: poison `file_digest` for every path inside the consumer and require every bucket to be identical — it is still the pack's own templates' honest reader, which is a different tree |
| R14-C3 | Codex | **The synthetic consumer still was not a `--thin` input.** It passed the structural audit added in round 13 and then failed `install.py --check`: `state=invalid`, `.trellis/config.yaml` missing; and after that file was added, `refresh-required` with `changeCount=84`. Six hand-written receipt entries and two manifest rows resemble no real install | The fixture is built by **running the installer**. `install.py <tmp> --platform claude --platform github` against a seeded git repository produces a 160-entry receipt, and three assertions hold the preconditions: audit exit 0 with no error lines, `--check` `state=current` with `changeCount=0`, and a conversion plan with nothing blocked. Everything the fixtures assert is now about a tree the production path accepts |
| R14-C4 | Codex | **A direct-path command was not command position.** `./scripts/sd-ai-command-pack-full-check.sh` is the canonical way to run a repository script and names no runner word; Codex executed exactly those bytes. The plain form landed in `advisories`, which does not block, and the NUL-bearing form landed in no bucket at all | `COMMAND_CONTEXT` matches `./path` and `../path` anchored at the start of a line or after `;`, `&`, `|`, `(`, `&&`, `\|\|`, so a `./x` mid-sentence in prose stays prose. Both fixtures — plain and asset — assert a blocker. Writing it revealed a second bug worth recording: the first attempt put `{1,2}` inside an f-string, where it is a tuple expression, and the regex silently compiled to something that matched nothing |
| R14-C5 | Codex | **A readable managed file containing NUL falsely blocked.** The asset branch emitted a whole-file `unreadable pack target` defect for any managed file with a NUL in it. A `.gitignore` carrying harmless NUL bytes and **no citation at all** produced `verdict=blocked`. The read succeeded — "contains NUL" and "could not be read" are different facts | `unreadable pack target` is reserved for the `OSError` handler and the symlinked-receipt-target case. A managed asset is an asset; the pack ships binary files |
| R14-C6 | Codex | **Three remaining spec-to-scanner divergences, each changing `clear` versus `blocked`.** The design said a path in command position blocks while the scanner omitted direct paths; the PRD said every hit lands in exactly one of four buckets while a weak citation in an asset was silently discarded; and no authoritative rule permitted a readable managed NUL file to become a whole-file defect | The design carries the direct-path grammar and the full eight-cell disposition matrix over (bytes look binary) × (path is an execution surface) × (line is in command position), plus the rule that `unreadable pack target` means a read that failed. Weak asset citations are recorded as `advisories` tagged `[asset bytes]` rather than dropped, so the four-bucket claim is true again |
| R14-C7 | Codex | **The canary's "declare codex" branch contradicts its own residual criterion.** `retainVendoredFor` is keyed on the *shared* platform's disposition, not on `.agents/**`. Measured identically against all three canaries: declaring Codex moves the plan from 166/13/27 to **91/13/102** — 75 further retained targets, being 49 `.agents/**`, 25 `scripts/**`, and `docs/SD_AI_COMMAND_PACK.md` — and the removal total becomes 104, not 179. The task simultaneously permits that branch and requires no residual beyond `repo-native` + `consumer-config` | The canary PRD states the derived retention set with its measured figures, and its acceptance criterion compares the executed tree against that consumer's own receipt **under its recorded platform choice** rather than against one fixed slice |
| R14-C8 | Codex | **The canary named the wrong GitHub owner and had no executable command sequence.** `gh api repos/rwbp/rwbp-coordinator` returns 404; `platypeeps/rwbp-coordinator` returns 200, which is also what the registry and the checkout's `origin` say. Round 13 changed this line to `rwbp/` on the strength of the *local checkout path* `~/repos/rwbp/`, which is a different fact. The PRD also contained none of `--out`, `--resweep-verdict`, `--consumer`, or the resweep script's name, and its revert proof did not require a fresh resweep before re-conversion | Owner restored to `platypeeps`, with the path-versus-slug distinction written down so it is not "corrected" a third time. Requirement 1 carries the literal three-command sequence, the reason the verdict travels as a file, and the recovery for an abandoned attempt. The revert proof requires a fresh exact-head resweep against the reverted tree, because the revert changes the tree and the first verdict does not authorize the second conversion |

All three non-blocking items fixed: the two renamed fields' remaining
mentions were stale comments, `is_binary`'s docstring no longer claims an
asset "cannot carry a citation" (R13 made that false), and the design's
"`.trellis/` history" is now the named set the scanner implements —
archive, workspace, audit, journal, plus `docs/review-learnings.md` —
with live `.trellis/spec/` guidance explicitly outside it.

**Thirteenth measurement.** `sd-github-review` 15 blockers in 11 files,
`se-ai-command-pack` 26 in 11, `hoa-manager` 39 in 14, `mezmo_benchmark`
47 in 27, `rwbp-coordinator` 52 in 11, `loadsmith` 56 in 8,
`rwbp-website` 67 in 10, `anomaly-metric-creator` 206 in 22.
`packDefects` unchanged at 16 in 7, or 14 in 6 where the consumer owns
its PR template. No consumer is `clear`. Markers per consumer after
R14-C1: three for `rwbp-coordinator`, `loadsmith`, and
`mezmo_benchmark`; two for `hoa-manager`, `rwbp-website`, and
`se-ai-command-pack`; one for `sd-github-review` and
`anomaly-metric-creator`. Harness 100 passed, 0 failed, 0 skipped — 28
fleet and 72 unit.

Mutation sweep, each a true revert against a regenerated scan: direct
path grammar removed → 2 failed; ownership re-read restored → 1 failed;
empty directory blocking restored → 2 failed; codex CLI marker off → 1
failed; pack-managed exclusion off → 4 failed; managed NUL as unreadable
target restored → 1 failed; asset weak citations dropped → 1 failed;
control → 100 passed, 0 failed.

### Round 15 — Codex lane against `844650bb`

Five blocking groups. Four fault a round-14 fix, and the fifth faults the
round-14 documentation of a rule the scanner had implemented correctly
since round 7. The pattern of the last three rounds holds: the defects
are no longer in the classification rules themselves but at the seams
between them — what counts as ownership, what counts as an invocation,
which bytes a binding actually covers.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R15-C1 | Codex | **Receipt membership still masqueraded as pack ownership in marker discovery.** R14 excluded pack-managed files from content markers by skipping every receipt member — the exact test `prd.md:197` forbids elsewhere. Codex installed a real 160-entry consumer, edited its receipt-member `.prism/rules.json` to say `Run codex exec, then bash scripts/…`, and watched the ordinary classifier call the bytes consumer-owned while the marker pass hid them | `platform_marker_hits` takes a `pack_owned` set built from the same three proofs the classifier uses — provenance digest, managed-block span, force-preserved comparison. `scan()` collects `proven_pack_owned` as it classifies and passes it in. Receipt membership excludes nothing |
| R15-C2 | Codex | **The CLI marker was neither an invocation nor complete.** It searched whole file bodies for four adjacent words. `"This repository does not use codex exec; that command is prohibited."` blocked, while `codex -C . exec`, `codex review`, and `codex e` — all documented forms, confirmed against the local `codex --help` — did not | The pattern accepts global options before the subcommand and the full subcommand set including the `e` alias, and the hit must be in command position: an existing command line, a line that starts with `codex` after Markdown leaders are stripped, or an imperative anchored at the start of the line. "does not use codex exec" is none of those |
| R15-C3 | Codex | **Ownership still consumed unbound bytes.** R14 removed the second read of the *consumer* file, but ownership also reads the provenance record, and `scannedBytesDigest` skipped generated bookkeeping. Codex fed different provenance bytes to ownership, moved a citation from `blockers` to `packDefects`, and every binding stayed identical — `changedBindings: []`, same `scannedBytesDigest`, same `receiptOccupancyDigest`. The exact failure class R14-C2 claimed closed | The three generated bookkeeping files are hashed into `scannedBytesDigest`. Provenance decides ownership, so provenance bytes are a scan input; a read failure there routes to `missing` rather than silently vanishing |
| R15-C4 | Codex | **The direct-path grammar missed execution and blocked prose.** It understood separators but not shell control prefixes. A temp `.envrc` containing `if ./scripts/sd-ai-command-pack-full-check.sh; then :; fi` executed and printed `R15_EXECUTED` while the scanner filed it as an advisory; conversely `After setup; ./scripts/…sh is obsolete prose.` blocked | `direct_path_lines` is file-aware. `SHELL_PREFIX` covers `if`, `while`, `until`, `then`, `else`, `elif`, `do`, `time`, `command`, `exec`, `env`, `nohup`, `sudo`, `!`, and leading assignments. A path at line start counts everywhere; a path after a separator counts only outside prose suffixes, because a semicolon in Markdown is punctuation |
| R15-C5 | Codex | **The "full" disposition matrix omitted historical scope.** The matrix said `text × non-execution path × command position` is a blocker; the scanner suppresses command-position blocking in historical files, and an archived `implement.md` reciting `bash scripts/…full-check.sh` produced an advisory. Claimed-complete specification and implementation disagreed on a real input | Historical scope is written as an explicit prerequisite above the matrix, alongside ownership, naming the five historical roots and the reason: an archived plan quoting a command is a record of what was run. Execution-surface *paths* still block there. Round 7 measured what the unscoped rule costs — 28 of `sd-github-review`'s 34 blockers were archived plans |

Three non-blocking items fixed. Canary requirement 5 no longer states 179
removals as unconditional; it names the declaration branch's 104 and the
75 retained targets that produce it. The parent's `--thin` acceptance
criterion now requires the residual to include everything the recorded
platform choice retains, not only `repo-native` + `consumer-config`. The
pre-R14 "directory existence is the marker" wording is gone from the
canary PRD and the design's `platformMarkerDigest` paragraph. Codex's
third note — that calling the canary's command sequence "literal" is
overstated while child 1's script does not yet exist — is accurate and
needs no edit: the sequence is the contract child 1 must satisfy.

`prd.md`'s marker acceptance criterion now names **four** markers rather
than three, adds the two negative fixtures R14 and R15 forced (empty
directory, prose prohibition), and states that ownership there means a
proof rather than receipt membership.

**Fourteenth measurement.** `sd-github-review` 15 blockers in 11 files,
`se-ai-command-pack` 26 in 11, `hoa-manager` 36 in 11, `mezmo_benchmark`
47 in 27, `rwbp-coordinator` 51 in 10, `loadsmith` 56 in 8,
`rwbp-website` 67 in 10, `anomaly-metric-creator` 206 in 22.
`packDefects` unchanged at 16 in 7, or 14 in 6 where the consumer owns
its PR template. No consumer is `clear`. The R15-C1 and R15-C2 fixes move
in opposite directions and both landed: excluding proven-pack-owned
content dropped `hoa-manager` from 39 to 36 and `rwbp-coordinator` from
52 to 51, while the corrected CLI marker found `loadsmith` and
`mezmo_benchmark` invoking `codex` in command position. Markers per
consumer: three for `loadsmith` and `mezmo_benchmark`; two for
`rwbp-coordinator`, `hoa-manager`, `rwbp-website`, and
`se-ai-command-pack`; one for `sd-github-review` and
`anomaly-metric-creator`. Harness 107 passed, 0 failed, 0 skipped — 28
fleet and 79 unit.

Mutation sweep, each a true revert against a regenerated scan: ownership
exclusion back to receipt membership → 1 failed; CLI marker without
command position → 1 failed; CLI marker's old four-word pattern → 1
failed; bookkeeping bytes unbound → 1 failed; direct-path grammar off →
2 failed; prose separator re-enabled → 2 failed; control → 107 passed, 0
failed. Two of these misfired on the first attempt in a way worth
recording: `str.replace(old, new, 1)` hit an identical line inside
`platform_marker_hits` instead of the classification site, and renaming a
parameter left `managed` undefined rather than reverting behavior. A
mutation that crashes proves nothing; both were redone with index
targeting so the reverted scanner still runs.

### Round 16 — Codex lane against `eec09c8c`

Five blocking groups, and every one of them lands inside a round-15 fix.
That is the fourth consecutive round to fault its predecessor, but it is
also the first round to find **no new defect class**: R16-C1 through
R16-C5 map one-to-one onto R15-C1 through R15-C5. The rules are no longer
wrong; the *granularity and completeness* of four specific seams were.

| ID | Lane | Concern | Resolution |
| --- | --- | --- | --- |
| R16-C1 | Codex | **Ownership was neither complete nor correctly ordered.** R15 passed the marker pass a set of whole-file paths, but managed-block ownership is a per-line span, so the same `codex exec --help` line inside and outside the pack's block got the same verdict. A digest-proven pack file invoking codex produced **no entry in any bucket** — the hit was dropped, not classified, which makes the four-bucket claim false. And a consumer-edited force-preserved PR template with an unmatched marker was called a `packDefect`, because the malformed-marker rule overrode the shipped-bytes comparison that actually decides that file | Ownership is recorded per file as evidence — whole-file proof, pack-block spans, stripped spans, malformed flag — and `owned_at(relative, line)` answers the question at the granularity the proof has. Markers are bucketed rather than dropped: pack-owned to `packDefects`, inside a stripped block to `scheduled`, everything else to `blockers`. Force-preserved targets are decided by the shipped-bytes comparison alone; markers do not speak for them |
| R16-C2 | Codex | **The subcommand list was the wrong axis.** Round 15 replaced four adjacent words with an enumeration of accepted subcommands, and one round broke it from both ends: `codex plugin list` and a bare interactive `codex <prompt>` are invocations the list omits, a `package.json` script `"agent": "codex exec --help"` ran under npm with no marker emitted, and `worker: codex exec --help` in a Procfile and `& codex exec --help` in PowerShell both failed detection — while the Markdown sentence `` `codex exec` is prohibited here. `` blocked | The enumeration is gone. The marker is the command **word** in command position, which is the rule this scanner already applies to `./path` and to runners: `codex(?![\w./:-])` excludes the `.codex/` path segment, a `codex:` key, and `codex-cli`. Position covers line start behind shell prefixes, shell separators including PowerShell's `&`, assignments, and structured-data command values. The backtick left the Markdown leader class — stripping it turned an inline code span into a line that starts with the command |
| R16-C3 | Codex | **`scannedBytesDigest` still hashed a different read from the one ownership parsed.** R15 bound the bookkeeping bytes without making them the *same* bytes: ownership parsed provenance at one call site and the digest hashed it at another. Codex's split-read fixture moved a hit from `blockers` to `packDefects` with `changedBindings: []` and an identical `scannedBytesDigest` | The generated bookkeeping files are read once, before anything consults them; `provenance_digests` takes bytes rather than a path. The marker pass reads from the same preloaded bytes, because a marker is a classification too. The fixture poisons every read after the first and asserts all four buckets are unchanged |
| R16-C4 | Codex | **The direct-path grammar failed in both directions outside its two fixtures.** `env -i ./scripts/…full-check.sh` executed and was filed as an advisory, because the prefix rule demanded the path immediately after the keyword and real prefix commands take their own options. And valid JSON whose `"description"` read "After setup; ./scripts/…sh is obsolete prose." blocked, because `.json` is not a prose suffix — the suffix test was standing in for two different questions | `SHELL_PREFIX` allows a prefix word its own options. Structured data is a third file class, not a subcase of shell: in JSON the document is parsed and the command strings are the values hanging from execution keys — `scripts` at any depth, `command`, `run`, `entrypoint` — matched in their **quoted** form so a sentence quoting a path is not the path. In mapping formats the key decides; in a Procfile every line is a process, so every key does |
| R16-C5 | Codex | **The normative artifacts permitted three different dispositions for one input.** The PRD required `packDefects` for a pack-owned marker, `design.md` listed three markers and said they are always blocked, `implement.md`'s step-3 checklist omitted the CLI marker entirely, and the scanner did a fourth thing | One rule in all three. The design carries the four markers and a disposition table keyed on ownership, with the two negatives (empty directory, prose mention) and the operator declaration for global configuration. Step 3 carries the same four and points at the ownership prerequisite instead of saying "is a blocker" |

Two further defects were found by reading the plan rather than by the
review lane, and are fixed in the same commit. **`classifier_digest` has
been under-binding since step 1 shipped**: `design.md` §2 has required
`manifest.json`, `installer/manifest.py`, and every force-preserved
template's bytes since round 7 (`R7-8`), and `installer/conversion.py:372`
hashes six paths plus the consumer entry. It is the same failure the
digest exists to prevent — a template edit flips
`.github/PULL_REQUEST_TEMPLATE.md` between `packDefects` and `blockers`
while every hashed input stays identical — and no round caught it because
every round measured the research scanner, which does not call that
function. Step 3 now gains four digest inputs rather than one, with a
fixture that edits a shipped template and asserts the digest moves. Step
3's marker sentence was also still the pre-R14 three-marker form.

**Fifteenth measurement.** `sd-github-review` 16 blockers in 12 files,
`se-ai-command-pack` 27 in 12, `hoa-manager` 37 in 12, `mezmo_benchmark`
47 in 27, `rwbp-coordinator` 52 in 11, `loadsmith` 56 in 8,
`rwbp-website` 68 in 11, `anomaly-metric-creator` 207 in 23.
`packDefects` moved for the first time since round 7, 16 to **17** in 8
files (15 in 7 where the consumer owns its PR template): every consumer
now carries one pack-owned codex invocation that round 15 dropped on the
floor. Three consumer markers each for `rwbp-coordinator`, `loadsmith`,
`hoa-manager`, `rwbp-website`, `mezmo_benchmark`, and
`se-ai-command-pack`; two each for `sd-github-review` and
`anomaly-metric-creator`. No consumer is `clear`. Harness 120 passed, 0
failed, 0 skipped — 28 fleet and 93 unit.

Mutation sweep, each a true revert against a regenerated scan: ownership
back to whole-file → 1 failed; pack-owned markers dropped → 2 failed;
force-preserved decided by markers → 1 failed; codex subcommand
enumeration restored → 4 failed; provenance read twice → 1 failed; shell
prefix without options → 1 failed; JSON matched by bare substring → 1
failed; structured data treated as text → 1 failed; Procfile keys
filtered by the exec list → 1 failed; control → 121 passed, 0 failed.

Two of those survived their first valid run, and both were holes in the
*fixtures* rather than in the code — worth recording because a surviving
mutation is ambiguous evidence and the ambiguity has to be resolved
before it is reported as either. The ownership mutation was never reached
because the stripped-span test runs first, so both existing cases
returned `scheduled` whichever way the branch went; the missing case is a
marker inside a pack block the conversion *keeps*, which is the only
shape that exercises per-line proof. The force-preserved mutation was
never reached because the fixture wrote its marker label in lowercase and
`BLOCK_START` requires `[A-Z-]+`, so `malformed_markers` stayed false and
the branch under test never ran. Both fixtures were corrected and both
mutations then failed.

The first attempt at the mutation sweep was invalid and is recorded
because the failure is easy to repeat: it mutated an isolated *copy* of
the scanner and ran the harness with `--scan` pointing at that copy's
output. Every mutation "passed", including the control, because the
harness imports the scanner from its canonical path — only the fleet rows
saw the mutant and the 92 unit fixtures exercised pristine code. A
mutation sweep that reports no failures is a broken sweep until proven
otherwise. The valid form mutates the scanner in place and restores it in
a `finally`.


### Round 17 — Codex lane against `ef9e8fe5`, unaimed

Round 16 returned no new defect classes, which is the stop condition this
task has been running toward. It did not count, and the reason is worth
recording: the round-16 prompt named round 15's five fixes as the place
to look, so "no new classes" was partly a description of the prompt. Round
17 was launched deliberately unaimed — told not to assume recent changes
are the likely defect site, and told that the production `installer/` code
the research scanner never calls is fair game. It returned three blockers,
two of them in that production code, on the first look.

| ID | Source | Defect | Fix |
| --- | --- | --- | --- |
| R17-C1 | Codex | **`expected_residual_targets()` never applies `retainVendoredFor`.** `classify_target` keeps a machine row whose platform is retained for a declared consumer platform; the residual formula considered only ordinary keep categories. A `codex` consumer's 75 retained targets were kept by the conversion and absent from what `--check` expects, so a correctly converted consumer would report refresh-required forever. `design.md:142` stated the same incomplete formula | The residual now walks machine rows through the same `_retained_for_consumer` predicate the classifier uses. Three unit tests, one of them asserting the two functions agree in *both* directions on the same target — the assertion that fails if either side is changed alone |
| R17-C2 | Codex | **An unknown consumer platform failed open.** `build_conversion_plan()` never validated the supplied platforms against the partition's platform map. An unrecognized name retains nothing, so every machine surface a real declaration would have kept was classified for deletion, with `blocked` empty and `is_convertible` true. `prd.md:152` requires an unknown platform to stop the conversion | The plan blocks before classification, naming every unrecognized platform, with an empty delete set. Two unit tests, the second asserting all unknown platforms are reported rather than the first |
| R17-C3 | Codex | **The settings writer could not derive its own required configuration.** "Read the values from the manifests, never hardcode" is not satisfiable: `extraKnownMarketplaces` needs a GitHub source locator and neither manifest carries one. An implementer would have had to guess `owner-name/marketplace-name`, which is correct here by coincidence | `design.md` §4 now defines the locator normatively: derived from `ROOT`'s `origin` remote, normalized to `<owner>/<name>`, cross-checked against `marketplace.json`'s `owner.url`, blocking on a non-GitHub host, a missing or unparseable remote, or an owner mismatch. The exact merged JSON is written out literally, and `autoUpdate` is deliberately absent with the reason — a self-updating marketplace moves a converted consumer off its pinned version with no PR, no resweep, and no receipt change |

Three non-blocking items, all fixed in the same commit: the canary's
global-Codex declaration is now an acceptance gate with a stated form and
three answers rather than a paragraph the sequence could advance past;
the scanner docstring and step 3's later checklist still said "three
markers"; and the early per-consumer measurement table is now labeled
superseded, with a pointer to the current ledger.

**Harness blindness, demonstrated rather than argued.** Codex mutated the
research scanner so `build_conversion_plan()` received an empty platform
set, and all eight fleet rows plus all 121 unit cases were unchanged. The
platform set reaching the plan was unbound by anything. It is unbound
because the consumer platform argument changes the plan only through
`retainVendoredFor`, and none of the eight consumers declares `codex` or
`pi` — so the whole fleet is blind to it by construction. The synthetic
case that already scans the same checkout with and without `codex`
declared now also asserts `removedTargets` *falls* when it is declared.
Re-running the same mutant against that case: `FAIL unit R17-C1 ... 121
passed, 1 failed`.

**Sixteenth measurement, and the first that equals its predecessor.**
`sd-github-review` 16 blockers in 12 files, `se-ai-command-pack` 27 in 12,
`hoa-manager` 37 in 12, `mezmo_benchmark` 47 in 27, `rwbp-coordinator` 52
in 11, `loadsmith` 56 in 8, `rwbp-website` 68 in 11,
`anomaly-metric-creator` 207 in 23; `packDefects` 17 in 8 files, 15 in 7
where the consumer owns its PR template; 0 of 8 clear. Both fixes are on
the declared-`codex` path, which no consumer takes, so an unchanged
measurement is what a correct fix looks like here. Harness 122 passed, 0
failed, 0 skipped — 28 fleet and 94 unit. Production suite unchanged and
green.

Codex's own verdict: not converged, and it expects another round to find
more, "because examining production code that the scanner never calls
immediately exposed two blockers — and the actual converter, settings
merge, and revert mutators do not exist yet." That last clause is the
honest limit of this whole review sequence: sixteen rounds have hardened a
plan and a research scanner, and the three mutators the plan describes
have no code to review. Round 18 is authorized and runs against this
commit, again unaimed.

### Round 18 — Codex lane against `56b60da6`, unaimed again

Round 17's unaimed prompt found two blockers in production code on its
first look, so round 18 repeated the method and pointed harder: the
`installer/` modules the plan reuses, the shipped behavior of `--remove`
/ `--check` / `--status`, and the fact that the converter, the settings
merge, and the revert mutator **do not exist yet** and are therefore
unverified assertion. It returned four blockers and one harness hole,
every one of them in the cross-command lifecycle rather than in the
research scanner sixteen rounds have been polishing.

| ID | Source | Defect | Fix |
| --- | --- | --- | --- |
| R18-C1 | Codex | **A corrupt thin pin certified itself as `current`.** The unknown-platform guard R17-C2 added lived only in `build_conversion_plan`, and nothing re-read the pin afterwards. Codex converted a real install, edited its provenance to declare `not-a-platform`, and got `{"audit":"passed","changeCount":0,"state":"current"}`. The pin *chooses* the residual it is then measured against, so an unusable pin narrows to a slice that is intact by construction | `unusable_thin_pin_reason()` in `installer/conversion.py`, consulted by `_residual_files_for_thin`. An unknown platform — or an empty platform set, the same failure with no name to report — falls back to the full payload, which reports every deleted machine surface. Measured: narrowed by the corrupt pin, `changeCount` 1; falling back, 79 |
| R18-C2 | Codex | **Standalone `--remove` strands an enabled thin plugin.** `install.py --remove --skip-diff-check` on a converted consumer succeeded and deleted provenance while leaving `pluginStillEnabled=true, settingsUnchanged=true, provenanceExists=false` — a repository with no pack files, no receipt that a pack was ever there, and a live plugin serving it from the marketplace. The argument matrix never defined the row | The matrix gains it, and the answer is refusal rather than thin-awareness — on a structural argument, not a preference: `--remove` takes one root and undoing a conversion needs two, so a thin-aware `--remove` would be a removal that cannot finish and would leave the registry claiming `thin` for a consumer that no longer has the pack. Landed in step 4 with the other matrix rows, because it guards an *existing shipped command* |
| R18-C3 | Codex | **The R17-C3 locator accepted a same-owner wrong repository.** Deriving `owner/name` from `origin` and cross-checking only the owner passes `git@github.com:platypeeps/sd-ai-command-pack-fork.git`, which would then be written into every converted consumer. One guess had been replaced with another | The direction is inverted: `registry.PACK_REPOSITORY` declares the canonical identity once — it is the one value no manifest owns — and `origin` is validated *against* it by exact equality. `classifier_digest` already hashes `installer/registry.py`, so a marketplace relocation moves the digest and invalidates outstanding verdicts |
| R18-C4 | Codex | **Settings collision and revert ownership were undefined.** "Preserves every other key" said what happens to unrelated keys and left the interesting cases open: marketplace key pointing elsewhere, plugin key already `false`, a container that is not an object, and a converter-owned key edited between conversion and revert | `design.md` §4 gains a collision table where every ambiguous case **blocks** rather than overwrites, and a `settingsAdditions` shape carrying `createdContainers`/`createdFile` so "remove what we added" is answerable at the container boundary. Revert removes only values that still match what was recorded; an edited value is left in place and reported, and the command still exits zero |
| R18-C5 | Codex | **R17-C1's counterexample did not exercise its own production fix.** Codex true-reverted the retained-machine-row clause in `expected_residual_targets`: two production unit tests failed and the harness still reported 122 passed. The R17-C1 case checks `removedTargets`, which is the *plan* side; it never calls `expected_residual_targets` | Two cases that call it directly, asserting the residual grows when `codex` is declared and that every target it adds is one `classify_target` puts in `keep`. The same revert now fails the harness. Non-blocking, because the production tests caught it — but a harness that cannot see a rule it claims to protect is worth exactly its coverage |

**What round 18 says about the previous seventeen.** Every blocker is in
a place the review had never looked: two shipped commands, one declared
constant, one undefined contract. Rounds 13 through 16 each aimed at the
previous round's fixes and each found defects only there — which read as
convergence and was actually a description of the prompt. Two unaimed
rounds in a row have found blockers immediately. The stopping rule this
task has been using ("a round that finds no new defect classes") is only
meaningful for a round that was free to look anywhere.

Harness 124 passed, 0 failed, 0 skipped — 28 fleet and 96 unit. Fleet
measurement unchanged from the sixteenth: no scanner rule moved this
round, and the scan was regenerated only because it records the harness
digest. Production suite green, installer coverage 100%.

Codex's verdict: not converged, expecting further defects in cross-command
thin lifecycle, fail-closed pin validation, settings identity and drift,
and "write ordering, rollback, and partial-failure behavior in the
still-unimplemented converter and revert mutators." That last one is not
something another review round can fix. Three of the four blockers this
round were in code that exists; the fourth was in a contract for code
that does not. The remaining review surface is thinning, and what is left
is mostly a demand for implementation rather than for more planning.

### Round 19 — Codex lane against `08e76be9`, unaimed, third in a row

Round 18's fixes were named in the prompt as **not** the likely defect
site. Round 19 returned six blockers and opened its verdict by answering
the question the prompt asked: none of them is merely a demand to write
the missing mutators — each is a contract gap that has to be resolved
*before* that code can be written safely. Two were live defects in
shipped commands.

| ID | Source | Defect | Fix |
| --- | --- | --- | --- |
| R19-C1 | Codex | **Ordinary `install.py TARGET` silently de-thins a consumer.** A converted fixture followed by a plain refresh exited 0, rewrote provenance without `mode: thin`, and discarded `settingsAdditions` — while the plugin stayed enabled and the registry still read `thin`. This is the command `sd-fleet-refresh` runs against every consumer, so one fleet refresh would have de-thinned the whole fleet at once. The matrix guarded `--remove` and had no row for the routine case | **Shipped**: ordinary install and `--remove` both refuse a thin or malformed consumer, before any work. Thin-aware refresh is filed as step 9b and **blocks the canary** — a converted consumer cannot receive a pack update until it exists. Refusing is survivable only because nothing is converted yet |
| R19-C2 | Codex | **A receipt-first residual can convert cleanly and immediately fail `--check`.** Conversion derives the residual from the old receipt; inspection derives expectations from the current source. All eight receipts hold 210 entries and none lists `scripts/sd-ai-command-pack-pack-update.sh`, a shared machine row a `codex` consumer retains. Measured: `planned residual 106, expected residual 107` | Conversion requires a current install — version equality as the cheap check, plus the exact assertion that the source-derived residual is a subset of the receipt-derived one. Rejected the accommodating alternative: having conversion *add* the missing targets makes it a partial installer that writes new files into a consumer in a PR whose reviewers were told it only removes, and the resweep verdict would not cover them |
| R19-C3 | Codex | **Revert has an unhandled restore collision.** A consumer may create a file at a path the conversion deleted; `fileops` returns `conflict` unforced and `overwritten` forced, but the matrix forbids `--force` on revert on the ground that revert makes no drift decision — true of deletion drift, false of restore-path occupancy | Revert preflights every restore path and refuses the whole operation, listing the occupied paths, before touching receipts or registry. `--force` stays rejected: overwriting a consumer's file to reach a state they had before is the wrong default and the wrong flag. A path re-created with source-equal bytes is not a collision |
| R19-C4 | Codex | **The planned thin-removal predicate was not fail-closed.** `read_thin_receipt` collapses unreadable, malformed-mode, and fat provenance to the same `None` — right for narrowing a payload, wrong for a destructive guard. A receipt carrying thin pin keys under `mode: "thin-corrupt"` read as fat. And `platforms: [1]` reached `unusable_thin_pin_reason`, which raised `TypeError` joining it | **Shipped**: `thin_pin_state()` returns `fat` / `thin` / `malformed`, and the guards refuse on the last two. `malformed` means the receipt parses and carries thin pin keys that are not a readable pin — **not** merely "unreadable"; see the correction below. Platform parsing is all-or-nothing: `["claude", 1]` filtered element-wise yields `{"claude"}`, which looks like a deliberate single-platform declaration |
| R19-C5 | Codex | **Settings ownership and the disable marker cannot both hold.** §4 says revert leaves an edited recorded value and never touches a key conversion did not add; §5 says revert writes the plugin key as `false`. For a pre-existing `true`, or a value edited after conversion, both are impossible | A precedence table. The marker is written only over a value this conversion wrote and still owns; otherwise revert leaves it and says so. Disabling a plugin someone else enabled is a decision about their tooling made by a command they ran to undo ours |
| R19-C6 | Codex | **`--force` scope stated three ways, and no partial-failure model.** The matrix said "delete drift, nothing else", the plan applied force to delete/retire/block-strip, and the reused helper honors all three. Separately, failure injection covered only "consumer completed, registry failed" — not failure after the 50th deletion, during settings, or between the three receipt rewrites | Force covers removal drift in all three buckets and nothing outside removal. Write order is now part of the contract: settings, then receipts with **provenance last**, then deletions, then registry — which yields four named interrupted states, each recoverable by re-running the same command. One injection per step, each asserting convergence |

**Why the order in C6 is the load-bearing part.** Provenance is the
discriminator every other command reads, so writing it *before* the
deletions makes an interrupted run read as thin-with-payload — and a
re-run computes its plan from the now-thin receipt and deletes exactly
the remainder. Deleting first would produce a consumer with no machine
surfaces and a fat receipt: `--check` calls that `invalid`, and nothing
can distinguish it from a botched manual deletion. There is no rollback,
so the only available guarantee is that every interruption lands
somewhere nameable.

**Three unaimed rounds, three sets of blockers, and a shifting location.**
Round 17 found two in production code the scanner never calls. Round 18
found four in the cross-command lifecycle. Round 19 found six, of which
two were in shipped commands that predate this task. The research scanner
— sixteen rounds of polishing — has produced nothing new since round 16.
The defects are all in the seam between the conversion and the installer
that already exists, which is exactly where a plan gets least attention:
it is not new code, so it does not feel like something being designed.

Harness unchanged at 124 passed, 0 failed (28 fleet + 96 unit); no
scanner rule moved. Round 19 independently re-ran R18-C5's mutation and
confirmed both layers now catch it: `122 passed, 2 failed`.

Codex's verdict: not converged, expecting more in ordinary-install/thin
lifecycle transitions, typed pin-state discrimination, source-versus-receipt
freshness, restore-path collisions, disable-marker ownership, and
intra-root write ordering. Four of those six are the classes this round
just addressed, which is the first time the expected-next list has been
mostly a restatement of the current one.

**Correction inside round 19, found by the gate rather than by Codex.** The
first `thin_pin_state` answered `malformed` for anything it could not read:
unparseable bytes, a JSON array, a symlink. The unit suite was green and the
100%-coverage gate was not: `tests/test_install_audit.py:1389` and `:1417`
failed. Both are shipped behaviors the guard had preempted — install *rebuilds*
a mangled fat provenance, and a symlinked provenance already has its own
refusal with its own message and exit code. "Refuse when unsure" read as the
safer default and was not: it replaced two working recoveries with a dead end,
for consumers that were never thin.

`malformed` is now positive evidence only — the receipt parses as an object and
carries thin pin keys that do not form a readable pin, which is exactly
R19-C4's demonstrated case. Both branches were true-reverted after narrowing:
disabling the install guard fails 3 tests, disabling the `PIN_KEYS` branch
fails 2.

The residual gap — a thin consumer whose pin is destroyed outright — is real
and is not closable by reading a pin that is gone. It is filed as R19-C4b: a
durable thin marker in `manifest.json`, which the fixed write order guarantees
is already thin whenever provenance is the receipt that was lost.

The generalizable part: the unit suite passing is not the gate passing, and the
difference here was entirely tests I did not write and had not read. A guard
added to a shipped command is a behavior change to that command, and the
question to ask before adding one is not "is this safe" but "which existing
behaviors does this now come before".

### Round 20 — Codex lane against `460c52e9`, unaimed, fourth in a row

Seven blockers and one non-blocking contradiction. Round 20 was asked
directly to attack R19-C4b's claim that total pin destruction is the only
way a genuinely thin consumer reads as `fat`. It refuted that claim by
construction on its first attempt.

| ID | Defect | Disposition |
| --- | --- | --- |
| R20-C1 | **A symlinked thin provenance is classified `fat` and ordinary install damages the consumer.** It built a thin consumer, moved the pin bytes to a sibling, and symlinked provenance at them — the pin intact and readable, not destroyed. Install exited 2 with `symlink-conflict`, and the machine witness went `absent` → `present`. The payload preflight (`install.py:956`) covers selected files only; the three receipts are written afterwards by a different path, so their conflicts were detected *after* the payload had landed | **Shipped**: the preflight now checks the three receipt destinations before the first payload write, and refuses with `nothing was installed`. New test asserts a removed payload file is **still absent** after the refusal — the pre-existing symlink test only checked the exit code and passed throughout |
| R20-C2 | **Byte-identical revert cannot restore the 13 retired files.** All 13 are in the live 210-row receipts and absent from the manifest, source tree, and templates; provenance keeps hashes, not bytes (`provenance.py:136`). A same-version checkout cannot recreate them | Open. Three ways out: preserve the bytes durably, leave legacy retired files in place, or narrow the revert guarantee. The last is probably right — revert restores what the pack can still produce — but it changes what `--revert-thin` promises and must be said in prd.md, not assumed |
| R20-C3 | **The R19-C6 write order destroys its own recovery inventory.** It rewrites `installed-targets.txt` to the residual before deleting, but `build_conversion_plan` discovers deletion candidates *from* that receipt (`conversion.py:204`). After the rewrite, an interrupted rerun cannot find what remains undeleted — the exact opposite of the property the order was specified to guarantee | Open, and it invalidates the table of four interrupted states. Needs a durable removal inventory or journal that survives until deletion completes. This is the finding that most argues for writing code rather than more contract |
| R20-C4 | **The freshness preflight invalidates the canary's acceptance figures.** The 210-row totals reproduce against the stale receipts, but R19-C2 now requires a current install first, and a fresh 0.66.1 install measures **198**: `167 delete + 0 retire + 27 keep + 3 receipts + 1 strip` without Codex, `91 + 0 + 103 + 3 + 1` with. The refresh drops the 13 retired rows and adds the pack-update target | Open. The canary prd still asserts 210/13 (`prd.md:114`). 210 can stay as a compatibility fixture but cannot be the expected post-refresh result |
| R20-C5 | **R19-C4b's second thin marker exists in design.md and nowhere in the checklist.** Step 4 defines mode recognition around `thin_pin_state` alone; step 6 rewrites the manifest without specifying a mode witness; no disagreement, pin-loss, or symlinked-thin test is listed | Open. As written, the remedy for R20-C1's class would never get implemented |
| R20-C6 | **Fleet refresh skips damaged same-version thin consumers.** Preflight declares a consumer at target on provenance version alone (`fleet-preflight.py:93`), so a same-version thin consumer with a corrupted residual never reaches the repair path. Step 9b covers version-bump refresh only | Open, folded into step 9b |
| R20-C7 | **Two expected states for one fixture.** Step-1 checks said a half-converted consumer reports `refresh-required`; the measured correction below said `invalid`. Tests follow `invalid` | **Fixed** in this file: the guess is replaced by the measurement, with the reasoning that the fat path really is unchanged |
| R20-C8 | Candidate checking clones the consumer's default branch and force-installs into the clone (`fleet-candidate-check.py:138`), so once a default branch is thin the R19 guard refuses it — the parent design says the scratch checkout is always fat | Non-blocking; the candidate-loop sibling owns this and remains a hard pre-canary dependency |

**What round 20 says about the review loop itself.** Three of its seven
findings (C2, C3, C4) are defects *in round 19's fixes*, and round 19 did
the same to round 18. The loop is now generating contracts about
unwritten code faster than it retires them, and C3 is the clearest
example: "the write order destroys its own recovery inventory" cannot be
fixed on paper with any confidence, because the fix is a durable removal
inventory — an artifact that has to exist before rerun-after-interruption
can be tested at all.

So the disposition for this round is deliberately uneven: C1 and C7 are
closed now, and C2, C3, C4, C5, C6 stay open as inputs to steps 3 and 6
rather than as another round of prose. They are recorded here with enough
measurement to be actionable — 198 rows not 210, deletion discovery reads
the receipt, the 13 retired files have no surviving bytes — which is what
a contract needs to be worth writing.

Round 20's verification: harness 124 passed, 0 failed; production suite
`Ran 2078 tests in 482.294s OK`; true-revert of `_retained_for_consumer`
produced `121 passed, 3 failed`; restore digest matched before and after;
724 partition rows matched 724 manifest rows with declared counts
`6 / 79 / 88 / 551` correct; worktree clean at exit.

### Step 3 — built

`scripts/sd-ai-command-pack-thin-resweep.py` ships, `classifier_digest`
gains its four inputs, and `tests/test_thin_resweep.py` carries 27
fixtures.

**Where the rule lives, changed from the plan.** Step 3 said the builder
belongs under `installer/` because that inherits the 100% coverage gate,
and I first read that as applying to the rule too. It does not, and
shouldn't: `installer/` is the *installed* library and the resweep never
ships, so putting 573 statements of classification there would hold
non-shipping research code to a stricter bar than the installer it is
not part of. The deciding argument is the digest: `classifier_digest`
hashes `scripts/sd-ai-command-pack-thin-resweep.py`, and that only binds
the rule if the rule is in that file. Split across a module, an edit to
the classification could move a verdict while the hashed path stayed
byte-identical — the exact failure the four new digest inputs exist to
prevent. So the rule sits in the script, under the shipped-script
coverage floor, mirroring the research scanner's own shape.

**The port reproduces the reference exactly.** Independent code path,
same consumer, same numbers: `rwbp-coordinator` → `blockers 52,
packDefects 17, scheduled 182, advisories 115`, matching
`research/fleet-blocker-scan.json` field for field. That is the check
worth having, because a port is precisely where a rule quietly changes.

**Two divergences from the research copy, both deliberate:**

- The scan no longer decides. `decide()` owns the verdict and returns
  *reasons*, plural — a caller told `blocked` and not why cannot act, and
  "the tree was dirty" and "the pack ships a broken reference" call for
  opposite responses. The shipped tool refuses a dirty worktree
  (`prd.md:62`); the research copy must not, since six of eight consumers
  are dirty and gating on cleanliness would report `blocked` everywhere
  for a reason unrelated to conversion.
- `scheduled` is per citation. Verified rather than assumed: two
  references to the same removed path in two surviving files produce two
  entries.

**What the fixtures caught about the plan's own description.** Platform
markers are recorded against the *platform* as subject — `codex`,
`$CODEX_HOME` — with the citing file in `detail`, not against the file.
That is right (one undeclared platform is one finding however many files
evidence it) and it is not what step 3's prose implies. Two of my first
assertions encoded the prose and failed; the code was correct.

**Mutation evidence.** `is_executable_surface` forced to `False` fails 1
fixture; `cites_removed_path` forced to `None` fails 3. File digest
identical before and after each restore.

Coverage: the new script measures 76%, at the shipped-script aggregate
floor. Uncovered lines are concentrated in the symlink-resolution and
managed-block-span branches, which no fixture reaches yet — recorded
here rather than left implicit, since 76% is the floor and not a target.

### Step 4 — built

`install.py` gained the four conversion flags — `--thin`, `--revert-thin`,
`--resweep-verdict`, `--consumer` — and one function,
`_reject_incompatible_conversion_flags`, called at the end of `parse_args`.
Landed before the mutators, as the step requires: once two mutators can both
be passed, dispatch order picks a winner silently, and the winner is decided
by whichever `if` an unrelated edit happens to move.

**The matrix is declared, not ordered.** Every rejection names both flags in
its message, so the operator learns which pair conflicted rather than which
one the parser noticed first. `tests/test_thin_argument_matrix.py` covers 15
argv rows: opposing mutators, `--remove`, `--machine`, both inspections,
`--configure-fleet`, all three payload selectors against both directions,
`--thin` without a verdict, a verdict without `--thin`, `--force` on revert,
`--consumer` outside a conversion, plus the allowed rows.

**Mutation evidence, argv layer.** `_reject_incompatible_conversion_flags`
replaced by `pass` fails 9 of 15. Restored: 15 pass.

**The rows argv cannot express.** `--remove` alone is legal argv; whether it
is refused depends on the target, not the arguments. So `ConvertedFixtureTests`
builds a real installed tree, flips its provenance to `mode: thin`, and asserts
the three facts round 18's probe found false: exit 2, `.claude/settings.json`
byte-identical, `provenance.json` still present.

Two honesty notes on that fixture, both recorded rather than papered over:

- The `settings.json` assertion is not live today. Today's `install.py` never
  writes that file at all — verified by probing a fat `--remove`, which leaves
  a fixture-written `settings.json` byte-identical whether or not the guard
  exists. Step 6's conversion is the first code that will touch it, so this is
  a guard registered ahead of the mutator that can break it, and the comment
  in the fixture says exactly that.
- A refusal test alone passes on an installer that refuses *every* `--remove`.
  `test_the_same_removal_on_a_fat_consumer_still_works` deletes `mode` from the
  same fixture and asserts exit 0 with the receipt gone, so the refusal is
  provably about the pin.

**Mutation evidence, tree layer.** `if thin_state != conversion.PIN_STATE_FAT`
forced to `if False` fails 2 of the 3 fixture tests; the fat control correctly
still passes.
