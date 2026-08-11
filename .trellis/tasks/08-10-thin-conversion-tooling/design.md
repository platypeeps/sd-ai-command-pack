# Design: thin conversion tooling

Child 1 of `08-09-thin-migration`. Implements parent contracts C-A
(two-phase fail-closed conversion), C-B (receipt-first enumeration),
C-C (merge semantics for `.claude/settings.json`), and C-D (one-command
revert with a two-root preflight).

Pack-internal. No consumer repository is mutated by this task; the
tooling is exercised against disposable checkouts and fixtures.

## Evidence

Read from the tree at `d7913054`, not from memory:

- `install.py:794` `main` dispatches on `args.machine`, then
  `--status/--check`, then `--remove`, then the install path. `ROOT` is
  the pack checkout (derived from the installer package location,
  `installer/registry.py:8`); `target` is resolved separately at
  `install.py:803`. One process legitimately holds both roots.
- `installer/provenance.py:222` `read_existing_installed_targets`
  returns the receipt as a set of newline-separated paths, skipping
  blanks and `#` comments. `read_existing_installed_targets_for_remove`
  is the swallow-errors variant.
- `installer/removal.py:185` `may_remove_pack_file` refuses a file whose
  content differs ("content differs from installed pack version"), and
  `remove_installed_pack` still returns zero at `:408`. That is right
  for `--remove` and wrong for conversion — see "Fail-closed
  preflight" below.
- `installer/removal.py:256` `retire_stale_targets` iterates a fixed
  `RETIRED_TARGETS` (157 entries), not the receipt.
- `installer/fileops.py:709` `remove_marked_block` already strips a
  managed block from a consumer-owned file and reports
  `UNCHANGED / "managed block not present"`, `UPDATED` when text
  survives, or `REMOVED` when nothing does. `.gitignore` needs no new
  machinery — it needs to be routed here instead of to file deletion.
- **The thin pin is the provenance receipt.**
  `DEFAULT_FLEET_PIN_PATH` is `.sd-ai-command-pack/provenance.json`
  (`scripts/sd_ai_command_pack_fleet_lib.py:27`), and
  `read_consumer_pin` (`scripts/sd-ai-command-pack-status.py:2873`)
  reports `present` when that file is a JSON object carrying a
  non-empty `version` string. Every consumer's existing
  `provenance.json` already has `{"pack": ..., "version": "0.64.x"}`.
- `scripts/sd-ai-command-pack-install-audit.py:880` takes `--repo`,
  repeatable `--expected-platform`, and `--upstream-manifest`; it
  enumerates tracked pack-like paths independently of the receipt.

## The three bookkeeping files, resolved

Parent contract C-B names them as a special case without saying what
happens to each. Four existing readers settle it — and the first draft
(delete two, keep one) breaks three of them.

| File | Fate |
|---|---|
| `.sd-ai-command-pack/provenance.json` | **kept, rewritten**: residual `files` map, `version`, `pack`, plus the thin pin — `mode: "thin"`, `platforms`, `consumer`, `settingsAdditions`, `forced` |
| `.sd-ai-command-pack/installed-targets.txt` | **kept, rewritten** to the derived residual set |
| `.sd-ai-command-pack/manifest.json` | **kept, rewritten** to describe the residual payload |

All three survive because all three are required:

- `install.py --status/--check` treats the footprint as incomplete
  unless every one of `_RECEIPT_PATHS = (PACK_MANIFEST_FILE,
  PROVENANCE_FILE, INSTALLED_TARGETS_FILE)` is occupied
  (`installer/inspection.py:30`, `:253`). Deleting `manifest.json`
  yields `installed pack footprint is incomplete; missing: ...` and
  `state: invalid`.
- The install audit requires `provenance.json` to carry a non-empty
  `files` **map**, failing with `provenance.json has no files map` or
  `... has an empty files map`
  (`scripts/sd-ai-command-pack-install-audit.py:701-712`). A thin
  receipt of only `version`/`mode`/`settingsAdditions` fails it. The
  residual `files` map is not a workaround: those files really are
  installed and really do have hashes, so it is the honest content.
- The audit uses the receipt as its allowlist
  (`allowed = set(targets) | LOCAL_ALLOWED_PACK_FILES`, `:632`) and
  requires every listed target to be *present* (`:616-626`), reporting
  everything else as `unlisted-pack-like` (`:640`). A missing receipt
  makes both checks fail at once.
- The audit's expected-target completeness check is manifest-derived
  (`expected_targets_from_manifest`), so it demands every surface the
  pack ships for the consumer's platforms and fails a thin consumer on
  all ~167 deleted files. It ships to consumers while the partition does
  not, so it cannot recompute the residual: when provenance pins
  `mode: "thin"` it skips *only* that check and keeps every
  receipt-to-disk check. Verifying the receipt itself against the
  expected residual stays with the source-checkout `install.py --check`.
- The pin carries `platforms` because a thin receipt no longer proves
  which platforms the consumer selected — `_manifest_platforms`
  intersects the manifest against the receipt, which for a converted
  consumer collapses to its repo-native platforms and makes every fleet
  reader reject the mismatch against the registry.
- `read_consumer_pin` needs only a non-empty `version`
  (`scripts/sd-ai-command-pack-status.py:2911`), which is exactly why
  it cannot be the only interface consulted: `sd-status` would report a
  healthy `present` pin while `--check` and the audit both fail.

**The residual set is derived, not looked up.** It is:

```
residual = pre-conversion receipt
         − delete − retire
         − any blockStrip file that came back REMOVED
```

asserted against the filesystem before it is written. A
partition-derived residual would be wrong by a wide margin: the
partition carries 557 `repo-native` + `consumer-config` rows, of which
only 26 exist in `rwbp-coordinator` (the rest are platforms that
consumer never installed), and it carries no row at all for `.gitignore`,
which every receipt does list. Writing the partition's kept rows as the
receipt would produce ~531 `installed target is missing` failures.

The half-converted hazard still needs naming: a conversion that deleted
the payload but left the receipts untouched would report a `present`
pin at the old version, so `sd-status fleet` would show a healthy thin
consumer that is not one. `mode: "thin"` in the provenance file is the
discriminator every thin-aware reader keys on, and the conversion
asserts the rewrite landed. `read_consumer_pin` ignores extra keys, so
adding it is additive.

## Verification interfaces must become thin-aware

This is the part the first draft missed entirely, and it is larger than
the receipt schema.

`install.py --check` decides `state` by **dry-running a full install of
the source payload** and counting would-be changes
(`installer/inspection.py:374-395`): `change_count` sums
`_CHANGE_INSTALL_STATUSES` over every source target. In a thin
consumer, 166 machine files are deliberately absent, so a refresh would
report them all as `CREATED`, `change_count` is large, and the state is
`refresh-required` — permanently, no matter what the receipts say.

That is not cosmetic. `scripts/sd-ai-command-pack-fleet-review-classify.py:212`
runs `install.py --check --json` and requires `state: current`, so every
converted consumer would classify as needing a refresh forever.

So child 1 owns a fourth surface beyond the converter: `--status` and
`--check` must read `mode: "thin"` from the provenance receipt and
compare against the **residual** payload rather than the full one.

**The expected residual is computed from the source, not from the
receipt.** This is a different computation from the conversion-time
residual and the difference matters:

```
expected_residual(source, consumer) =
    { target ∈ source manifest
      | partition[target].category ∈ {repo-native, consumer-config}
        AND ( partition[target].platform ∈ consumer.platforms
              OR partition[target].category == "consumer-config" ) }
  ∪ { target ∈ source manifest
      | partition[target].category ∈ MACHINE_CATEGORIES
        AND retained_for_consumer(partition[target], consumer.platforms) }
  ∪ every MANAGED_BLOCK_REMOVAL_TARGETS member that exists in the target
  ∪ the three .sd-ai-command-pack/ bookkeeping files
```

**The second clause is R17-C1 and was missing until round 17.** It is the
same `retained_for_consumer` predicate `classify_target` uses to decide a
machine row's bucket — provisional platform, or `retainVendoredFor`
intersecting the consumer's declared platforms. Omitting it here while
the classifier applies it there makes the two disagree by exactly the 75
targets a declared-`codex` consumer keeps: conversion leaves them in
place, `--check` does not expect them, and the consumer reports
`refresh-required` forever for files that are correctly present. Whatever
the classifier calls `keep`, this set contains — that equivalence is
asserted in both directions in `tests/test_conversion_plan.py`.

**The platform predicate is the part round 2 left undefined, and it is
measured rather than assumed.** Without it, hundreds of `repo-native`
rows for platforms a consumer never installed would be "expected" and
`--check` would report `refresh-required` forever. With it, against
`rwbp-coordinator` (`platforms: claude, gemini, github, opencode`):

- keep-category rows whose platform is declared: **23**, of which
  **23 are present** and 0 absent
- plus the **4** `shared` `consumer-config` rows (`.gito/config.toml`,
  `.gito/sd-ai-command-pack.env`, `.prism/rules.json`,
  `.prism/rules.schema.json`), which are platform-independent and
  present
- total **27** keep-category rows, exactly the set that exists in that
  checkout — zero missing, zero extra

The full expected residual adds the 2 managed-block files and the 3
bookkeeping files to that, and because
`.github/copilot-instructions.md` is both a keep row and a managed-block
file the union is **31**, not 32. Measured against `rwbp-coordinator`:
31 expected, 31 present, 0 absent.

The `consumer-config` disjunct is not a special case bolted on; those
four rows carry `platform: shared` and belong to a consumer regardless
of which agent platforms it declares.

**Managed-block members are included unconditionally**, not only when
they carry a partition row. `.gitignore` has no row, but after a
`UPDATED` block strip the file still exists and is still in the
receipt-derived residual; excluding it from the source-derived set
would make the two disagree on exactly the fixture where consumer
`.gitignore` lines survive — which is the normal case, not an edge one.
A member that came back `REMOVED` is absent from both sets because it
no longer exists, which the "exists in the target" qualifier expresses.

**Presence is checked on the filesystem, not through `git ls-files`.**
Platform adapters may be installed and gitignored — `install-audit.py`
walks with `rglob` and downgrades gitignored findings to warnings for
exactly this reason (`:558`). A `git`-based presence check would report
an installed-but-ignored adapter as missing.

Using the rewritten receipt as the expected set would be wrong in a way
that gets worse over time: a newly shipped `repo-native` file would
never appear in a converted consumer, and `--check` would report
`current` forever. Using all partition keep rows would be wrong in the
other direction — 557 rows against 26 present files. The source
manifest intersected with the partition's keep categories is the only
set that is both current and installable, and it is the same
`classify()` the plan builder uses.

`current` then means "the residual slice matches the source's residual
slice, and the machine supplies the rest"; the machine half is already
reported separately by `sd-status`'s `machineScope`.

**Managed-block files compare by block, not by bytes.** A `.gitignore`
that came back `UPDATED` still exists and still belongs to the residual
set, but its bytes are consumer-owned and will never equal any source
file. The thin comparison asserts the *pack's block is absent* from a
`blockStrip` member and *present and current* in a `keep` member
(`.github/copilot-instructions.md`) — the same marker-pair check
`installer/fileops.py` already performs — and never hashes the whole
file. A `blockStrip` member that came back `REMOVED` leaves the
residual set entirely, because the file is gone.

Two interfaces are explicitly *not* changed by this task, and the
reason is recorded so a later reader does not assume coverage:

- The fleet candidate checker force-installs a fresh fat payload into a
  scratch copy and audits that
  (`scripts/sd-ai-command-pack-fleet-candidate-check.py:226`). It does
  not read a live thin receipt, so it does not break — but it also
  proves nothing about thin behavior. That gap is child 2's subject,
  and this task must not claim it as covered.
- `sd-status fleet` and the fleet preflight need only the pin version
  and keep working unchanged.

## Surfaces

### 1. `scripts/sd-ai-command-pack-thin-resweep.py` (new, read-only)

Standalone rather than an `install.py` mode: it is read-only, it must
run against a consumer without loading install semantics, and it
mirrors `install-audit.py`'s existing shape.

**The resweep is a fleet-operator tool and is not shipped into
consumers.** Round 1 raised the opposite — put the shared builder in a
shipped module so an installed resweep could import it — and that turns
out to be impossible, not merely awkward. A resweep running inside a
consumer would have no classification data at all: `manifest.json`
ships neither `installer/**` nor `docs/fleet/surface-partition.json`,
and no `fleet-*.py` script ships either (`fleet-candidate-check`,
`fleet-wave-plan`, `fleet-preflight`, `fleet-review-classify` are all
absent from the manifest, while `install-audit.py` and `status.py` are
present). Shipping the resweep would mean shipping the partition,
`RETIRED_TARGETS`, and `MANAGED_BLOCK_REMOVAL_TARGETS` alongside it —
new distribution surface for a tool only a fleet operator runs.

It therefore lives in `scripts/` **only**, with no `templates/scripts/`
counterpart and no `manifest.json` row, exactly like every other
`fleet-*` script, and it takes `--repo PATH` the way they do. Children
3–5 run it from the pack checkout against each consumer, which is where
conversion is driven from anyway.

That resolves the placement question: the shared plan builder lives
under `installer/`, where `RETIRED_TARGETS` and
`MANAGED_BLOCK_REMOVAL_TARGETS` are directly importable and the 100%
coverage gate already applies. Both `install.py --thin` and the resweep
import it from there.

The closing check is a manifest assertion, not a code reading: the
resweep appears in no `manifest.json` row and in no
`templates/scripts/` path. A row for it is failure — it would begin
shipping classification data into every consumer.

```
sd-ai-command-pack-thin-resweep.py --repo PATH [--consumer NAME]
    [--fleet-manifest PATH] [--out PATH] [--json]
```

Emits a schema-versioned verdict object:

```json
{
  "schemaVersion": 1,
  "kind": "thin-resweep-verdict",
  "consumer": "<registry name>",
  "repo": "<absolute path>",
  "head": "<40-char SHA>",
  "indexDigest": "sha256:<hash of `git ls-files -s` output>",
  "indexFlagsDigest": "sha256:<hash of `git ls-files -v` output>",
  "hiddenBytesDigest": "sha256:<hash over the contents of every flagged path>",
  "worktreeDigest": "sha256:<hash over dirty paths and their contents>",
  "worktreeClean": true,
  "receiptOccupancyDigest": "sha256:<hash over what each receipt target is on disk>",
  "executableBitsDigest": "sha256:<hash over the exec bit of every enumerated file>",
  "symlinkTargetsDigest": "sha256:<hash over what each symlink resolves to>",
  "platformMarkerDigest": "sha256:<hash over platform-directory occupancy and the marker hits>",
  "scannedBytesDigest": "sha256:<hash over every path the scan read and its bytes>",
  "binaryFiles": 0,
  "missingFiles": [],
  "classifierDigest": "sha256:<hash over the pack-side inputs below>",
  "verdict": "clear" | "blocked",
  "blockers": [{"kind": "...", "file": "...", "line": 12, "detail": "..."}],
  "packDefects": [{"file": "...", "line": 37, "detail": "..."}],
  "scheduled": [{"file": "...", "line": 7, "detail": "..."}],
  "advisories": [{"file": "...", "line": 3, "detail": "..."}]
  // line is null for whole-file and directory-existence blockers
  // (a `.codex/` directory has no line); consumers of the verdict must
  // handle null rather than assume every blocker cites a line
}
```

Every digest field above is load-bearing, and the list is the one the
research scanner arrived at after two rounds of finding inputs that
changed a classification while every recorded field stayed identical: a
gitignored receipt target appearing (`receiptOccupancyDigest`), `chmod +x`
on a tracked Markdown file under `core.fileMode=false`
(`executableBitsDigest`), a sparse or unreadable checkout
(`missingFiles`, which forces `blocked`), and an `assume-unchanged`
or `skip-worktree` entry whose bytes change invisibly to `git status`
(`indexFlagsDigest` **and** `hiddenBytesDigest`), a symlink whose
*resolution* changes because an ignored intermediate directory link was
repointed (`symlinkTargetsDigest` — the link is bound, the thing it
reaches was not), and the **pack's own** hidden bytes
(`packIndexFlagsDigest`, `packHiddenBytesDigest`). That last pair is not
symmetry for its own sake: ownership of a force-preserved consumer file
is decided by comparing it against the pack's shipped `templates/` bytes,
so `skip-worktree` on `templates/.github/PULL_REQUEST_TEMPLATE.md` moved
five consumers' pack defects from 16 to 14 and their blockers up by one,
with every recorded binding — consumer *and* pack — unchanged. That last pair is one
field split in two after round 10 showed the first was not enough:
`git ls-files -v` binds the flag letter and the path, not the content
behind them, so a file already carrying `skip-worktree` could have its
bytes rewritten with `head`, `indexDigest`, `indexFlagsDigest`,
`git status`, `worktreeDigest`, and `worktreeClean` all unchanged while
the scanner and the converter read different bytes. `hiddenBytesDigest`
hashes the contents of each flagged path, so the flag can no longer hide
what it covers. An earlier revision of this schema listed only
`head`, `indexDigest`, `worktreeClean`, and `classifierDigest`, which
would have shipped a verdict *less* reproducible than the research
measurement it is derived from.

Two more fields, each from a round that found the previous list still
incomplete. `platformMarkerDigest` binds *directory occupancy*: git does not track
a directory, so adding or emptying `.codex/` moves no file-oriented
binding at all. R14 then corrected what occupancy *means* — an empty
`.codex/` is not a marker and does not block; a populated one is and
does — but the digest records occupancy either way, so the fixture that
proves the empty case harmless is bound to the verdict just as tightly
as the populated case that blocks. `scannedBytesDigest` binds the bytes
themselves — every path the scan read, paired with its content hash.
R13-C3 built a `.gitattributes` clean filter that maps any worktree
content to the committed blob: after one `git add` refreshes the stat
cache, `git status` is empty, `worktreeClean` is true, `worktreeDigest`
sees nothing, and the file on disk still says `bash <removed script>`.
Every other binding is a *proxy* for the bytes the classification reads,
and each round found another way for a proxy to be wrong; this one is the
bytes. It does not retire the proxies — `head` and the index digests are
what make a verdict comparable to a git state a human can check out — but
it is the field that closes the class.

`blockers` and `packDefects` both stop conversion — the verdict is
`clear` only when both are empty. They are separate arrays because they
have different owners: a blocker is the consumer's to fix, a pack defect
is ours. `scheduled` is informational — the pack references that live
inside files this conversion deletes anyway. Per contract C-A,
`docs/SD_AI_COMMAND_PACK.md` hits land in `scheduled`, which is the whole
reason any consumer can reach `clear`.

**Classification rule, corrected against measurement.** The rule this
design first stated — "`scheduled` when the hit's file is in the computed
delete set, `blocked` otherwise" — fails on the ordinary case. Measured
in `rwbp-coordinator` — counting files that mention the pack *by name*,
which is the population the old rule would have blocked on: 138 files
mention it, conversion removes 179 targets, and 53 mentioning files
survive. 13 of those survivors are pack-managed receipt entries: `.github/copilot-instructions.md`,
`.github/PULL_REQUEST_TEMPLATE.md`, four `.github/prompts/*.prompt.md`,
`.claude/rules/sd-planning-adversarial-review.md`, `.gito/config.toml`,
`.prism/rules.json`, `.gitignore`, and the three `.sd-ai-command-pack/`
bookkeeping files. Those are pack-shipped surfaces whose content the pack
owns; blocking the consumer on them reproduces exactly the C-A failure
this task exists to avoid. **`.prism/rules.json` is the exception that
proves the ownership test is per-line, not per-file**: the pack ships the
file, but `rwbp-coordinator`'s copy has drifted, and the removed paths it
cites are not in `templates/.prism/rules.json`. Ownership is decided by
comparing against the pack's shipped bytes, so those lines are
consumer-authored blockers (R10-C6) even though the file is pack-shipped. Reproduce with `research/fleet-blocker-scan.py`
(command below).

Four buckets, decided in order. Every step is measured below, and every
step fails **closed** — an input the rule cannot read or verify becomes
more blocking, not less.

1. **Does the hit's file disappear?** — it is in the computed delete or
   retire set. Then every reference inside it is `scheduled`. This is
   contract C-A's exemption and nothing else qualifies for it.

   A `block_strip` target is a third case and belongs here too, but only
   partly: the file survives while the pack's managed block inside it
   does not. A hit **inside** the block the conversion strips is
   `scheduled`; a hit outside it is judged by the steps below. Deciding
   that needs the block's line span, which the strip already computes, so
   the resweep reads the span rather than re-deriving it. Every one of the
   8 consumers exercises this: `.gitignore` is a `block_strip` target, and
   its surviving `obsidian-kb` block names the removed KB script — a hit
   *outside* the stripped span, in a file that survives, which is why it
   is a `packDefect` and not `scheduled`. An earlier revision of this
   paragraph called the case hypothetical; it was hypothetical only while
   the span was computed per file instead of per block.

2. **Otherwise the file survives. Is it still byte-for-byte the pack's?**
   — present in the pre-conversion installed-targets receipt *and* its
   sha256 matches the digest provenance recorded for it. Receipt
   membership alone is not enough: a consumer that edited a kept target
   would inherit the exemption forever. A receipt entry with no recorded
   digest, or a digest that no longer matches, is consumer-authored from
   here on.

   Digest comparison cannot decide every case, and where it cannot the
   rule must not silently pick "consumer". Provenance deliberately never
   records a whole-file digest for managed-block, force-preserved, or
   generated targets (`installer/provenance.py:114`). Three resolutions,
   one per class:

   - **Managed blocks** — the markers decide. Content between the pack's
     `SD-AI-COMMAND-PACK:*:START` and `:END` delimiters is the pack's,
     content outside them is the consumer's, in the same file. Markers
     that are unterminated, nested, or unbalanced are *unresolvable*, and
     the file falls to pack-owned rather than to a guessed span:
     `installer/fileops.py:138` rejects exactly those cases, and treating
     an unterminated start as a block running to EOF would label consumer
     tail content as the pack's — failing open in the one place the rule
     claims to fail closed.
   - **Force-preserved targets** — compared against the pack's own
     shipped bytes. Concluding "consumer's" from the missing digest alone
     was wrong: `.github/PULL_REQUEST_TEMPLATE.md` is force-preserved
     (`installer/registry.py:2265`), its shipped template cites the
     removed full-check script at line 14, and five of eight consumers
     carry a byte-identical copy. Where the bytes match the template it is
     pack content and a pack defect; where they differ the consumer has
     taken it over, and it is judged as theirs.
   - **Generated bookkeeping** — the three `.sd-ai-command-pack/` files
     describe the install and are rewritten by it; they are not a source
     of citations.

   A receipt entry that is a symlink, or whose bytes cannot be read, is
   unverifiable and blocks as a pack defect rather than passing.

   A surviving pack file that cites a path this conversion removes is a
   `packDefects` entry, and it **blocks**. The earlier draft called this
   `scheduled` on the reasoning that a later release would fix it; that
   recorded an obligation no artifact tracks and shipped known breakage
   in the meantime. Measured: **16 hits in 7 files** for the five
   consumers that have not edited their PR template, **14 in 6** for the
   three that have (`mezmo_benchmark`, `sd-github-review`,
   `anomaly-metric-creator`) — there the template is the consumer's, and
   its stale citations are blockers instead:

   - `.github/copilot-instructions.md`, seven hits — inside the pack's own
     managed block, citing `docs/SD_AI_COMMAND_PACK.md`,
     `scripts/sd-ai-command-pack-install-audit.py`, and two
     `.agents/skills/sd-*/SKILL.md` globs whose whole matched population
     the conversion removes. The two globs were invisible until round 9
     deleted the discovery prefilter, which could not see a glob because a
     glob shares no literal substring with what it selects. Line numbers
     move with the consumer's own preamble above the block
     (26/27/36/51/54/106/108 in `rwbp-coordinator`,
     46/47/56/71/74/126/128 in `mezmo_benchmark`), so the
     resweep reports them, artifacts do not hard-code them. Reached only
     through the marker rule above; digest comparison alone reports this
     file as consumer-authored and misses it.
   - `.github/prompts/sd-housekeeping.prompt.md` 37–38,
     `sd-review-learnings` 44/46, `sd-review` 43, `sd-status` 43 — each
     telling an agent to run something conversion removes. These are
     whole-file pack targets, so their line numbers are stable fleet-wide.
   - `.github/PULL_REQUEST_TEMPLATE.md` 7 and 14 — a scope instruction
     citing removed operator documentation, and a checklist item telling a
     human to run the removed full-check script.
   - `.gitignore`, one hit inside the surviving `obsidian-kb` block: the
     block's generated-by header names the removed KB refresh script. The
     file is in `block_strip`, so a rule keyed on the *file* calls this
     `scheduled` and loses it; only the span the conversion actually
     removes — `trellis-gitignore` — is scheduled.

   `sd-help.prompt.md` is deliberately **not** here, and for a rule
   reason rather than a judgement call: it says to read
   `references/command-catalog.md` relative to a *resolved skill*, not
   relative to a path in the repository, so no static matcher can tie it
   to a removed path without guessing. An earlier count included it via
   exactly that guess.

   Fixing these is pack work that must land before any consumer converts,
   so the resweep names it rather than deferring it.

3. **Otherwise the file is consumer-authored. Does it cite a path this
   conversion removes?** Checked against the computed delete and retire
   sets — not against the string `sd-ai-command-pack`. A consumer test
   asserting on `.sd-ai-command-pack/provenance.json` names a path the
   conversion **keeps**, so it is not a blocker; one invoking
   `scripts/sd-ai-command-pack-full-check.sh` names a path that
   disappears, so it is. Five forms, because one is not enough, and each
   later one exists because an earlier round produced a case the ones
   before it missed: the exact path; a tail of the cited token **at a
   path boundary**; the token resolved relative to the citing file; a
   glob whose **whole** matched population the conversion removes; and a
   bare basename that is both unique to the removal set and
   pack-distinctive. `prd.md:42` is the authoritative statement of the
   five; this paragraph and the list at the end of this document restate
   it and must not drift from it. The glob form is not hypothetical —
   `loadsmith/.github/workflows/ci.yml:149` addresses the deleted
   population as `scripts/sd-ai-command-pack-*.sh` and names no exact
   path or basename anywhere.

   All five are a **lower bound**, and the design says so rather than
   implying coverage it does not have: a path composed at runtime from
   variables is invisible to any static reader. What makes the conversion
   safe is `--revert-thin` restoring the payload, not the resweep being
   exhaustive. The resweep raises confidence; reversibility is the
   guarantee.

4. **Does that citation sit on the execution surface?** If yes it is a
   `blocker`; if no it is an `advisories` entry — real staleness a human
   should fix, never a reason to refuse a conversion.

   Execution surface is decided by properties, not by a list of top-level
   directories. The earlier draft's directory allowlist failed open twice
   under measurement: it was anchored at the repository root, so
   `se-ai-command-pack`'s `templates/skills/se-review-skills/scripts/skill_review.py`
   — real Python under a nested `scripts/` — fell through to advisory;
   and it had no notion of an agent-executed surface, so a prompt telling
   an agent to run a deleted script fell through as prose. A file is on
   the execution surface when **any** of these holds:

   - its suffix is one of `.sh .bash .zsh .py .mjs .cjs .js .ts .rb .pl`;
   - its basename is a build/CI entry point — `Makefile`, `makefile`,
     `GNUmakefile`, `package.json`, `pyproject.toml`, `tox.ini`,
     `noxfile.py`, `justfile`, `Justfile`, `Taskfile.y*ml`,
     `.pre-commit-config.yaml`, `.gitlab-ci.yml`, `Dockerfile`. The case
     variants are not decoration: `make` reads `GNUmakefile`, `makefile`,
     and `Makefile`, and R13-C6 found this list naming one of the three
     while the scanner tested all of them;
   - it is under `.github/workflows/`, `.github/actions/`, `.circleci/`,
     `.devcontainer/`, `.github/prompts/`, `.github/instructions/`,
     `.prism/`, or **any platform directory the registry defines**. That
     last clause is derived from `PLATFORM_REGISTRY`, not written down:
     R11-C4 found the hand-written list had drifted to a singular
     `.opencode/command/` that matched nothing (the registry says
     `.opencode/commands/`, `installer/registry.py:309`) and had omitted
     twelve platform directories outright — `.agent`, `.codebuddy`,
     `.cursor`, `.devin`, `.factory`, `.kilocode`, `.kiro`, `.pi`,
     `.qoder`, `.reasonix`, `.trae`, `.zcode`. An implementation that
     re-types the list re-acquires the drift; one that enumerates the
     registry covers a platform added later without anyone remembering
     this paragraph. `.github` is excluded from that clause and keeps its
     explicit sub-prefixes above: it is the host's shared directory rather
     than one agent's, so `.github/ISSUE_TEMPLATE/` is not an execution
     surface the way `.github/workflows/` is;
   - its basename — **at any depth, not only at the repository root** —
     is an agent instruction file: `CLAUDE.md`,
     `AGENTS.md`, `GEMINI.md`, `QWEN.md`, `copilot-instructions.md`,
     `.cursorrules`, `SKILL.md` — or ends in `.prompt.md` or
     `.instructions.md`. An agent reading "run this script" and running it
     is execution by proxy; measured counterexample under the earlier
     rule: `mezmo_benchmark/CLAUDE.md:28` tells the agent to run
     `scripts/sd-ai-command-pack-full-check.sh`, which conversion removes,
     and classified as advisory;
   - **any** path segment is `scripts`, `bin`, `tools`, `test`, `tests`,
     `.githooks`, or `.husky` — at any depth, not only the first; or
   - the file carries the executable bit.

   **Command position includes a direct path.** A line that begins with
   `./path` or `../path` — at the start of the line or after `;`, `&`,
   `|`, `(`, `&&`, or `||` — is an invocation naming no runner word at
   all. R14 piped exactly those bytes to bash and got them executed while
   the scanner filed the line as advisory, which does not block. A `./x`
   appearing mid-sentence in prose is not anchored and does not match.

   **What a file's bytes looking binary does and does not decide.** A NUL
   byte means the bytes read as an asset. It does not mean the file cannot
   execute, and it does not mean the file is unreadable. The full
   disposition, which R14 required be written down because three of its
   eight findings lived in the gaps between these cells:

   | Bytes | Path is an execution surface | Line is in command position | Disposition |
   |---|---|---|---|
   | text | yes | either | ownership rules, then `blockers` |
   | text | no | yes | `blockers` |
   | text | no | no | `advisories` |
   | asset | yes | either | classified as text: a NUL-bearing `.sh` still runs |
   | asset | no | yes | `blockers` — command position executes whatever the file is named |
   | asset | no | no | `advisories`, tagged `[asset bytes]` |

   **Two prerequisites sit above the matrix, and R15 found the second one
   missing from it.** First, ownership: a hit in content the pack
   demonstrably owns is a `packDefect` whatever the matrix would say, and
   a hit inside a `block_strip` span is `scheduled`. Second, *historical
   scope*: in a historical file — `.trellis/tasks/archive/`,
   `.trellis/workspace/`, `.trellis/audit/`, `.trellis/journal/`,
   `docs/review-learnings.md` — command position does **not** block. An
   archived plan quoting `bash scripts/<removed>.sh` is a record of what
   was run, not an instruction, and round 7 measured the unscoped rule
   putting 28 of `sd-github-review`'s 34 blockers in
   `.trellis/tasks/archive/**`. Execution-surface *paths* still block
   there, because a file that runs is a file that runs. Writing the matrix
   without this prerequisite would let an implementer reintroduce exactly
   the round-7 false blockers.

   Every matched citation lands in exactly one bucket; none is discarded.
   `unreadable pack target` is reserved for a read that actually failed
   (`OSError`) and for a receipt target that is a symlink. A managed file
   that is readable and contains a NUL is an asset the pack ships, not a
   defect — R14 blocked a conversion on a `.gitignore` carrying harmless
   NUL bytes and no citation at all.

   Prose (`.md`, `.rst`, `.txt`), Trellis history, and data-only config
   that nothing executes fall through to `advisories`. "Trellis history"
   is a named set, not all of `.trellis/`: `.trellis/tasks/archive/`,
   `.trellis/workspace/`, `.trellis/audit/`, `.trellis/journal/`, and
   `docs/review-learnings.md`. Live guidance under `.trellis/spec/` and an
   *unarchived* task's `implement.md` are deliberately not in it — an
   agent reads a spec and acts on it, which is why H-2 narrowed the
   earlier, looser rule.

   Discovery itself must also start from the removal set rather than from
   the pack's name — see the measurement correction below. A file citing a
   removed path without mentioning `sd-ai-command-pack` anywhere on the
   line is the case that a name-first search cannot see at all, and no
   amount of correct classification recovers a hit that was never found.

   **The population is the working tree, not the index**: `git ls-files`
   plus `git ls-files --others --exclude-standard`. A conversion mutates a
   working tree, so an untracked script invoking a removed path breaks
   exactly as hard as a committed one; six of `se-ai-command-pack`'s
   blockers live in untracked files. Ignored files stay out — the receipt
   targets among them are bound by `receiptOccupancyDigest`, and nothing
   ignored is part of a conversion PR. An implementation that enumerates
   only tracked files returns different answers from the reference
   scanner, which is exactly the drift this paragraph exists to prevent.

Every step answers from the same plan builder `--thin` uses, so the
resweep and the conversion can never disagree about what is being removed
— one enumeration, several readers.

**Measured fleet-wide result: no consumer is `clear` today, and the pack
itself blocks every one of them.** The scanner, its exact rule, the
per-consumer heads, and the full per-file results are committed at
`research/fleet-blocker-scan.py` and `research/fleet-blocker-scan.json`;
rerun with:

```bash
.venv/bin/python .trellis/tasks/08-10-thin-conversion-tooling/research/\
fleet-blocker-scan.py --out .trellis/tasks/08-10-thin-conversion-tooling/\
research/fleet-blocker-scan.json
```

The research scanner records one `scheduled` entry per removed file
rather than per reference; otherwise it implements the rule above,
including the `block_strip` span. Its output is a summary, not a verdict.

Consumer-authored callers in command position, per consumer:
`sd-github-review` 16 hits in 12 files, `se-ai-command-pack` 27 in 12,
`hoa-manager` 37 in 12, `mezmo_benchmark` 47 in 27,
`rwbp-coordinator` 52 in 11, `loadsmith` 56 in 8, `rwbp-website` 68 in 11,
`anomaly-metric-creator` 207 in 23. Plus the pack defects above. They are
CI workflows, `package.json` scripts, repo-owned tests, shell preflights,
root agent instruction files, and PR-template checklists that invoke or
assert on vendored pack paths.

**These are the sixteenth measurement, and the fifteen before them were
each wrong in a way worth recording**, because the same failure shape recurred:
a rule that reasoning found sufficient, and measurement did not.

The sixteenth is the first that equals its predecessor: round 17's two
defects were in `installer/conversion.py`, on the path only a consumer
declaring `codex` or `pi` takes, and none of the eight declares either.
An unchanged number is evidence about *where* the round looked, not that
the rule has stopped moving — round 17 reached production code the
scanner never calls, and found blockers there on its first look.

- *Discovery searched for the wrong thing.* The first scanner found
  candidate files by grepping for the string `sd-ai-command-pack`, then
  compared tokens against the removal set — while this design's prose
  already said the check was against removed paths, "not against the
  string `sd-ai-command-pack`". `sd-github-review/test/metadata.test.js:490`
  names the removed `.agents/skills/sd-status/SKILL.md` with the pack name
  nowhere on the line, and was absent from those counts. Discovery now
  enumerates every file in the working tree — tracked **and**
  untracked-but-not-ignored — and searches for the removal set itself.
- *Matching guessed.* Reference forms were widened to bare basenames,
  which let a surviving sibling collide with a removed path of the same
  name — `se-ai-command-pack/templates/skills/se-help/SKILL.md:51` cites
  its own `references/examples.md` and was recorded as a blocker.
  Matching is exact, tail-of-path, resolved relative to the citing file,
  glob-with-whole-population-removed, or a basename that is both unique to
  the removal set and pack-distinctive — the five forms `prd.md` states
  normatively, and nothing else. An earlier revision of this bullet ended
  at "relative to the citing file", which contradicted the rule the
  scanner implements; the two are one list now.
- *Enumerating execution surfaces did not converge.* Four consecutive
  rounds each found a file type the previous enumeration missed: nested
  `scripts/` directories, agent prompt files, root `CLAUDE.md`, PR
  templates, and — in round 10 — `.prism/rules.json`, a JSON file whose
  `.json` suffix reads as inert data while its contents are *required
  rules* an agent is expected to obey. The rule was generalized to
  classify by **citation syntax** —
  a path appearing in command position blocks regardless of the file it
  sits in — because the space of ways a command is written is far smaller
  and far more stable than the space of files that might run one.
- *Discovery and matching were never reconciled.* Even after discovery was
  rebuilt around the removal set, it stayed a substring prefilter: full
  removed paths, their multi-segment suffixes, and only those basenames
  carrying the pack name. Matching meanwhile grew two rules that share no
  literal substring with anything — a glob whose whole population is
  removed, and a bare distinctive basename — so those rules were largely
  unreachable. 512 lines across the eight consumers satisfied the matcher
  and were discarded before it ran, two of them per consumer inside the
  pack's **own** managed block in `.github/copilot-instructions.md`, which
  cites `.agents/skills/sd-*/SKILL.md` and `**/skills/sd-*/**`. Any
  substring gate has this failure mode. There is no prefilter now: the
  matcher sees every line of every enumerated file, which costs 11 seconds
  fleet-wide.

- *The regression harness was itself unverified.* Round 9 turned the
  accumulated counterexamples into `research/classifier-counterexamples.py`
  so "all counterexamples still pass" would stop being re-established by
  hand. Round 10 mutation-tested it — revert one scanner rule, re-run the
  scan, re-run the harness — and **four of nine reverted rules produced no
  failure**: two ownership proofs and the historical-scoping and
  interpreter-case rules had no fixture depending on them, and the fleet
  assertions read a stored JSON, so they could not detect a scanner
  regression at all. Two negative cases named files that **did not exist**
  at the recorded head, so they asserted nothing for two rounds. A test
  suite that has never been shown to fail is a claim, not a check; the
  harness now pins the scanner digest, verifies each consumer's head, and
  fails a case whose file is absent.

The lesson is specific and is why step 3 keeps the scanner as a committed,
re-runnable artifact rather than a number in prose: when prose and
implementation describe the same predicate, the implementation is the one
that produced the number, and only re-running it shows when the prose has
drifted again.

This is a real finding, not a tuning problem. It resizes children 3–5:
each consumer needs its execution surface repointed off the vendored
scripts **before** it can convert, and the pack must repoint its own
surviving prompts first. It also narrows what the step-3 fixture
criterion can claim — a synthetic fixture reaching `clear` proves the
C-A remediation landed, not that any real consumer can convert.

Codex/pi markers are evidence that the consumer uses a platform its
registry row omits, and they are bucketed by the same two prerequisites
as any other citation rather than blocked unconditionally. R16-C5 found
this sentence saying three markers, always `blocked`, while the PRD said
pack-owned markers are `packDefects` and the scanner did a third thing —
three artifacts, three dispositions, one input.

There are **four** markers: a **populated** platform directory (an empty
one is not evidence), a surviving `$CODEX_HOME` reference, a pi adapter
file the registry names, and the `codex` CLI invoked in command
position. And each lands where its content's ownership puts it:

| Where the marker lives | Bucket |
| --- | --- |
| content the pack demonstrably owns | `packDefects` |
| a block the conversion strips | `scheduled` |
| anywhere else | `blockers` |

A pack-owned marker is the pack shipping text that names a tool the
consumer never declared — a real defect, and not the consumer's verdict.
Ownership is the same per-content proof the classifier uses: whole-file
digest, managed-block span, or force-preserved comparison. Never receipt
membership, and never at file granularity for a proof that is per line.
Globally-configured usage leaves no repository trace and needs an
operator declaration instead; an unanswered question is not `clear`.

### 2. Verdict binding (contract C-A)

`head` alone is insufficient — a tracked file can change without `HEAD`
moving. The verdict therefore also records `indexDigest`, a hash over
`git ls-files -s` output (mode, blob SHA, stage, path for every tracked
file), and `worktreeClean` from `git status --porcelain`.

Binding the consumer alone is also insufficient. The resweep and the
conversion are two processes; "same plan builder" guarantees the same
result only if the builder's *inputs* are the same. The verdict
therefore also records `classifierDigest`, a hash over every pack-side
classification authority:

- `docs/fleet/surface-partition.json` bytes
- the consumer's exact entry in `docs/fleet/consumers.json`
- the sorted `RETIRED_TARGETS` and `MANAGED_BLOCK_REMOVAL_TARGETS` sets
- `.claude-plugin/marketplace.json` and
  `plugins/sd/.claude-plugin/plugin.json` bytes
- `installer/removal.py` and `installer/registry.py` bytes, because
  `RETIRED_TARGETS` and `MANAGED_BLOCK_REMOVAL_TARGETS` are code, not
  data, and an uncommitted edit to either silently changes the plan
- `installer/conversion.py` bytes — the shared builder itself. It is the
  single largest determinant of the plan, and omitting it would let an
  edit to the classification logic between resweep and conversion leave
  every other digest input unchanged while the delete set moved
- `manifest.json` bytes, `installer/manifest.py` bytes, and the bytes of
  every force-preserved template the manifest names. The force-preserved
  ownership proof compares a consumer's file against the pack's own
  shipped template, so all three are classification inputs: a changed
  template flips `.github/PULL_REQUEST_TEMPLATE.md` between `packDefects`
  and `blockers`, a changed manifest changes which template is compared,
  and `installer/manifest.py` decides that mapping. Omitting them would
  leave a `clear` verdict standing across exactly the release that
  invalidates it
- `scripts/sd-ai-command-pack-thin-resweep.py` bytes — the resweep
  itself. The builder decides what is removed, but the resweep decides
  what counts as a hit, what counts as the execution surface, and how a
  citation is matched. None of that lives in `installer/conversion.py`,
  so without this input an edit to the executable-surface rule or the
  glob matcher leaves an existing `clear` verdict valid under an
  unchanged digest — the verdict would still claim to have asked a
  question the tool no longer asks

The plugin manifests are in the digest even though they are mutation
inputs rather than classification inputs: they determine what the
conversion *writes* into `settings.json`, and a verdict that authorized
a write of different content is as stale as one that authorized a
different delete set. The digest is over "everything that determines
what this conversion does", which is a superset of the classifier
inputs.

Pack `HEAD` is deliberately **not** in the digest — it would bind a
commit while leaving uncommitted edits to the very files above
invisible. Hashing those files' bytes covers the committed and
uncommitted cases alike, so no clean-pack-tree requirement is needed.

`--thin` recomputes all of it and refuses on any mismatch. Untracked
additions are covered by the clean-tree requirement, tracked edits by
the index digest, and a partition or registry edit between resweep and
conversion by the classifier digest. Without the last one, a `clear`
verdict can authorize a delete set that no longer matches the one it
was computed from.

### 3. `install.py TARGET --thin --resweep-verdict PATH`

Verdict passed as a file rather than piped, so it can be archived by a
conversion PR and re-checked by a reviewer.

Plan-then-mutate, as a `ConversionPlan`:

```
delete:     receipt entries classified machine-claude | machine-other
retire:     RETIRED_TARGETS entries present in the checkout
blockStrip: managed-block files with no partition row (today: .gitignore)
receipt:    all three .sd-ai-command-pack/ files rewritten to describe
            the residual payload — none deleted
keep:       repo-native | consumer-config | retainVendoredFor matches,
            including managed-block files that carry a partition row
settings:   .claude/settings.json additions (merge)
blocked:    receipt entries none of the above classify
```

**The managed-block bucket is enumerated, not hardcoded.** There are two
such files, not one: `installer/removal.py:55`
`MANAGED_BLOCK_REMOVAL_TARGETS` holds `.gitignore` and
`.github/copilot-instructions.md`. The plan builder reads that frozenset
and classifies each member through the partition rather than naming
`.gitignore` directly, so a third managed-block file added later cannot
be silently dropped.

Their fates differ, and the partition is what decides:

- `.gitignore` has **no partition row**. Its managed block lists vendored
  pack paths that conversion deletes, so the block is stripped via
  `remove_marked_block`.
- `.github/copilot-instructions.md` is `{platform: github, category:
  repo-native}`. Every `github` row is `repo-native` precisely because
  Copilot reads the repository and cannot see the machine — stripping
  its block would destroy a surface the partition deliberately retains.
  It is kept, block intact.

A managed-block member that is neither (no partition row and not
`.gitignore`) goes to `blocked`. Guessing its fate is how a consumer
loses a surface silently.

Build, validate, then execute — never interleaved. Validation fails
(and nothing is written) when `blocked` is non-empty, when any
`delete` entry is drifted and `--force` was not passed, when the
structural audit reports a pack-like file outside the plan, or when the
verdict does not bind to the current worktree or the current
classifiers.

**Preflight covers `delete`, `retire`, and `blockStrip` alike.** Drift
refusal is not the only preserve-and-continue path: `retire_stale_targets`
preserves a drifted retired file and keeps going
(`installer/removal.py:263`), and managed-block removal can come back
`PRESERVED` on a malformed or unreadable target
(`installer/fileops.py:683`). Validating only ordinary `delete` drift
would let a conversion complete while a retired file or an unstrippable
managed block survives — exactly the half-converted state the thin pin
would then claim was clean.

**`--thin` is a two-root operation too, and carries the same preflight
as revert.** It deletes in the consumer and flips `mode` in the pack's
`docs/fleet/consumers.json`. Specifying the two-root writability
preflight only for `--revert-thin` would leave the worse ordering
unguarded: an unwritable registry discovered *after* 166 consumer files
are deleted produces a converted consumer the fleet still believes is
fat. Both roots are checked writable before either is written, in both
directions, and a mid-operation failure reports which half completed
and exits nonzero.

**Fail-closed preflight, unlike `--remove`.** ("All-or-nothing" would
overpromise: the two-root write can still complete one half and fail the
other, which is reported rather than rolled back. What is guaranteed is
that nothing is written until the whole plan validates.) `--remove` legitimately
preserves a drifted file and still succeeds; conversion cannot, because
enabling the plugin and writing a thin pin over surviving vendored
surfaces produces a repo that is neither fat nor thin while the pin
claims it is thin. Drift aborts the whole conversion.

**`--force`'s scope is all three removal buckets, stated once (R19-C5).**
The matrix used to say "delete drift, nothing else" while the
implementation plan applied force-aware preflight to delete, retire, and
block-strip — and the reused retirement helper does remove drifted
retired files when forced (`installer/removal.py:256`). Three artifacts,
three scopes. The rule: `--force` overrides *removal* drift wherever the
conversion removes something, which is all three buckets. It overrides
nothing outside removal — not a settings collision, not a stale receipt,
not an unwritable root, not a resweep verdict.

**Write order is part of the contract, because there is no rollback
(R19-C6).** The design promises no rollback, and the failure-injection
plan only covered "consumer completed, registry failed". Failure after
the fiftieth deletion, during the settings merge, or between the three
receipt rewrites are each a different half-state, and "consumer half
completed" is not a model of them. The order is fixed so that every
interruption lands in a state that is *recognizable* rather than
ambiguous:

1. Both roots validated writable; plan built; settings merge validated
   against §4's collision table; resweep verdict verified. Nothing is
   written. Every refusal in this task happens here.
2. `.claude/settings.json` merged. It is first among the writes because
   it is the only one that is a pure addition — reversible by deleting
   keys, with the file's prior bytes still fully derivable from the
   recorded additions.
3. The three receipts rewritten, **provenance last**. The pin is the
   discriminator every other command reads, so it is the commit point:
   before it, the consumer reads as fat with extra settings; after it,
   as thin.
4. The payload deleted.
5. The registry row flipped in `ROOT`.

Which yields exactly four interrupted states, each named and each
recoverable by re-running the same command:

| Interrupted after | Consumer reads as | Recovery |
| --- | --- | --- |
| settings merge | fat, with settings additions | re-run `--thin`; §4's idempotent row makes the merge a no-op |
| some receipts | fat or invalid — `inspection` requires all three | re-run `--thin` |
| provenance (the commit point) | thin, payload still present | re-run `--thin`; the plan is computed from the receipt, which is now thin, so it deletes exactly what remains |
| some deletions | thin, partially deleted | same |
| everything but the registry | thin; registry says fat | the pin-vs-mode skew the parent design already accepts and `sd-status fleet` reports |

Deleting the payload before writing the pin would produce the one state
that is *not* recognizable: a consumer with no machine surfaces and a fat
receipt, which `--check` calls `invalid` and which no re-run can
distinguish from a botched manual deletion. That is why the order is
specified rather than left to whatever the code does.

**R19-C4b — the pin is a single point of failure, and the fix belongs in
a second receipt.** R19-C4's guard reads `provenance.json` and answers
`fat` / `thin` / `malformed`. `malformed` is defined narrowly: the
receipt parses as an object and carries thin pin keys that do not
constitute a readable pin. Bytes that carry *no* legible thin evidence —
truncated, non-JSON, a JSON array, a symlink — answer `fat`, because
that is what the installer has always done with them and it does the
right thing: `test_install_recovers_from_malformed_provenance` rebuilds a
mangled fat receipt, and `test_install_conflicts_on_symlinked_provenance`
refuses a symlinked one with its own message and exit 2. Widening
`malformed` to swallow both was tried and reverted; it is not a stricter
guard, it is a different command that breaks two shipped behaviors.

That leaves one real gap: a *thin* consumer whose pin is destroyed
outright reads as fat, and an ordinary install would rebuild a fat
receipt over a narrowed payload. The pin cannot close this, because the
premise is that the pin is gone. Close it in a second receipt instead:
`manifest.json` — written **before** provenance in the order above, so it
is already thin whenever the pin is the thing that was lost — carries a
durable `mode: "thin"` marker, and the guard treats *either* receipt
saying thin as thin. Two independent witnesses, with the write order
guaranteeing the surviving one is the earlier.

Until that marker ships, the guard's honest coverage is: every thin
consumer with a legible receipt, and every consumer whose receipt was
edited rather than destroyed. Step 6 owns writing the marker; step 4
owns extending the guard to read it. Neither is a canary blocker on its
own — the canary converts consumers whose pins this run writes — but a
converted consumer is not safe against pin loss until both land.

### 4. `.claude/settings.json` merge (contract C-C)

Zero partition rows — entirely consumer-owned. The writer parses the
existing JSON, adds the marketplace entry and the enable entry,
preserves every other key and ordering, and creates the file only when
absent.

The two keys are `extraKnownMarketplaces` and `enabledPlugins`
(researched in
`.trellis/tasks/08-09-deployment-thin-consumers/research/claude-code-plugin-capabilities.md:59-65`;
`enabledPlugins` is honored from project settings, `pluginConfigs` is
not — which is why the thin footprint uses these two and nothing else).

Their **values are read from the pack's own manifests, never hardcoded
in the writer**: the marketplace name from
`.claude-plugin/marketplace.json` (`sd-ai-command-pack`) and the plugin
name from `plugins/sd/.claude-plugin/plugin.json` (`sd`). A rename in
either manifest must not require a matching edit in the converter, and
must never leave converted consumers pointing at a name that no longer
exists. This repo's own `.claude/settings.json` is not the reference
shape — it carries `enabledPlugins: {}` and no marketplace key, because
the pack source does not consume itself as a plugin. The exact additions are recorded in the thin receipt's
`settingsAdditions` so revert removes precisely those and nothing else.
A malformed existing `settings.json` is a blocker, not something to
overwrite.

**The exact merged JSON, normatively (R17-C3).** "Read the names from the
manifests" was underdetermined: `extraKnownMarketplaces` needs a *source
locator*, and neither manifest carries one. `marketplace.json` names the
owner (`owner.url`, `https://github.com/platypeeps`) and the marketplace
(`name`, `sd-ai-command-pack`); `plugin.json` names the plugin (`sd`).
Nothing there says which GitHub repository serves the marketplace, and an
implementer who guessed `owner-name/marketplace-name` would be guessing —
the two are equal here by coincidence, not by contract. The writer
therefore derives the locator from the pack source checkout it is already
running against, and refuses when the derivation is not unambiguous:

- The canonical identity is a declared pack constant,
  `registry.PACK_REPOSITORY = "platypeeps/sd-ai-command-pack"`. This is the
  one value that lives in no manifest: `marketplace.json` names the owner
  and the marketplace, `plugin.json` names the plugin, and neither says
  which repository serves them. Declaring it is not the hardcoding the
  rule above forbids — that rule is about names the manifests already own,
  and a constant nothing can derive is better written down once than
  guessed at each call site. `classifier_digest` already hashes
  `installer/registry.py`, so changing it moves the digest and invalidates
  every outstanding resweep verdict, which is exactly the behavior a
  marketplace relocation should have.
- `ROOT`'s `origin` remote is validated **against** that constant, not
  used as the source of truth. `git@github.com:owner/name.git`,
  `https://github.com/owner/name.git`, and
  `https://github.com/owner/name` all normalize to `owner/name`; the
  normalized value must equal `PACK_REPOSITORY` exactly. A host other
  than `github.com`, a missing `origin`, more than two path segments, an
  unparseable URL, **or any other repository — including a fork under the
  same owner** — is a **blocker**.

  R18-C3 is why the comparison is exact rather than owner-scoped. The
  round-17 rule derived the locator from `origin` and cross-checked only
  the owner, so `git@github.com:platypeeps/sd-ai-command-pack-fork.git`
  passed and would have been written into every converted consumer. An
  owner check answers "is this our GitHub account", and the question is
  "is this the repository the marketplace is served from". Deriving a
  value and then partially validating it is still guessing; the direction
  had to be inverted.
- The `extraKnownMarketplaces` key is `marketplace.json`'s `name`; the
  `enabledPlugins` key is `<plugin name>@<marketplace name>`.

For this pack that resolves to exactly:

```json
{
  "extraKnownMarketplaces": {
    "sd-ai-command-pack": {
      "source": { "source": "github", "repo": "platypeeps/sd-ai-command-pack" }
    }
  },
  "enabledPlugins": { "sd@sd-ai-command-pack": true }
}
```

**No `autoUpdate` key is written, deliberately.** The thin footprint is
version-bound: the pin records a version, `--check` compares against it,
and `--revert-thin` restores the payload that version shipped. A
marketplace that updated itself would move a converted consumer off its
pinned version with no PR, no resweep, and no receipt change — the pin
would claim a version the consumer no longer runs. Updates travel the
same path as every other pack change: a fleet refresh that rewrites the
pin. If a future settings schema makes auto-update the default rather
than an opt-in key, that is a change to this contract and gets written
down here, not absorbed silently.

**Collisions block; the writer never overwrites a value it did not write
(R18-C4).** "Preserves every other key and ordering" said what happens to
unrelated keys and left the interesting cases undefined — and each one
has a wrong answer that looks reasonable in isolation. The rules, per
case:

| Existing state | Conversion | Why |
| --- | --- | --- |
| Neither key present | writes both, records both | The ordinary path |
| `extraKnownMarketplaces["sd-ai-command-pack"]` present, byte-identical to what we would write | leaves it, **does not record it** | Already true; recording it would make revert delete a key the conversion did not add |
| Same key present, any other value | **blocks** | It points somewhere else. Overwriting silently repoints a consumer's marketplace; merging two sources is not a thing the schema supports |
| `enabledPlugins["sd@sd-ai-command-pack"]` is `true` | leaves it, does not record it | Same reasoning |
| That key is `false`, or any non-boolean | **blocks** | `false` is a deliberate disable. Flipping it is overriding a decision, and a non-boolean is a file we do not understand |
| `settings.json` is valid JSON but not an object | **blocks** | There is no object to merge into, and rewriting it destroys whatever it was |
| Either container key exists and is not an object | **blocks** | Same |
| `settings.json` absent | creates it with exactly the two containers, records both containers as created | |

A blocker here stops the whole conversion in the plan phase, before the
first deletion — settings validation is part of the two-root preflight,
not a step that runs after the payload is gone.

**`settingsAdditions` records what to undo, not what is true.** Its shape
is therefore the *added* pairs plus the containers the conversion
created:

```json
{
  "extraKnownMarketplaces": { "sd-ai-command-pack": { "source": {"source": "github", "repo": "platypeeps/sd-ai-command-pack"} } },
  "enabledPlugins": { "sd@sd-ai-command-pack": true },
  "createdContainers": ["extraKnownMarketplaces", "enabledPlugins"],
  "createdFile": true
}
```

`createdContainers` and `createdFile` exist because "remove what we
added" is ambiguous at the container boundary: a consumer who already had
an `enabledPlugins` object with three other plugins must keep it, and one
whose `enabledPlugins` we created must not be left holding `{}`.

**Revert removes only what still matches (R18-C4).** For each recorded
pair, `--revert-thin` compares the current value against the recorded
one and:

- byte-identical → removes the key;
- **different → leaves it and reports it**, because a consumer who edited
  the marketplace source after conversion made a decision, and revert is
  not entitled to discard it;
- already absent → nothing, and not an error.

Then each recorded created container is removed if and only if it is now
empty, and the file is removed if and only if `createdFile` is true and
the resulting object is empty. Reverting a consumer whose settings drifted
therefore succeeds with a report of what it left behind, rather than
either failing or silently reverting an edit it did not make. This is the
same asymmetry `--remove` already has for drifted files, and for the same
reason: destroying consumer work to reach a clean state is the one
outcome worse than an incomplete revert.

### 5. `install.py TARGET --revert-thin` (contract C-D)

Restores the fat payload, deletes the thin artifacts by reading
`settingsAdditions` from the thin receipt, writes the per-repo
`enabledPlugins` disable marker, and flips that consumer's `mode` back
to `fat` in `ROOT`'s `docs/fleet/consumers.json`.

**The disable marker and the ownership rule collide, and ownership wins
(R19-C5).** §4 says revert leaves a recorded value that has since been
edited, and never touches a key conversion did not add. This section says
revert writes `enabledPlugins["sd@sd-ai-command-pack"]: false`. For a key
that was already `true` before conversion, or edited after it, those two
cannot both happen. The precedence, and it is the same rule in three
cases:

| State of the plugin key at revert | Revert writes |
| --- | --- |
| Conversion added it, value still `true` as recorded | `false` — the marker. Not a deletion: a fat consumer with the plugin merely *absent* re-enables on the next `claude plugin` interaction, which is the state the marker exists to prevent |
| Conversion added it, value edited since | leaves it, reports it |
| Conversion did not add it (already `true`) | leaves it, reports it |

The marker is only ever written over a value this conversion wrote and
still owns. Where it is not written, revert says so explicitly — "the
plugin remains enabled by a setting this pack did not add" — because a
fat consumer running the plugin as well is a real double-surface state
and an operator has to know. What revert must never do is disable a
plugin someone else enabled: that is a decision about their tooling, made
by a command they ran to undo *ours*.

**Written during conversion, landed after it — one authoritative
sequence.** R11-C6: the conversion writes both roots in one invocation,
while child 3 requires the consumer PR to land green *before* the
registry says `thin`. Both are right, and they are about different verbs.
`--thin` **writes** the registry edit into the pack working tree as part
of the same validated, two-root, plan-then-mutate run — that is why an
unwritable pack checkout must be caught before the first consumer
deletion. It does not **land** it: the two edits travel in two pull
requests, and the pack PR merges after the consumer PR does. The
in-between window is a consumer whose tree is thin and whose registry row
still says `fat`; the parent design already accepts exactly that window
and points at `sd-status fleet`'s pin-vs-mode skew row as the thing that
makes it observable rather than silent. If the consumer PR is abandoned,
the pack-side edit is discarded with it and nothing needs undoing.

Stated as the sequence child 3 executes per consumer: resweep at the
exact head → `--thin` (writes consumer deletions **and** the registry
row) → open the consumer PR from the consumer edits → land it green →
land the pack PR carrying the registry row. "Flip the registry after the
consumer PR lands" therefore means *land the flip `--thin` already
wrote*, never *run a second tool*.

**Consumer identity is carried, not inferred.** `--revert-thin` receives
only `TARGET`, but it must flip exactly one registry row. Inferring the
name from `pathHint` fails for a disposable checkout, a worktree, or an
alternate clone — and picking the wrong row silently mislabels two
consumers at once. The thin receipt therefore records the canonical
`consumer` name, `--consumer NAME` overrides it, and revert refuses on
a mismatch between receipt, registry, and flag rather than choosing.

**A consumer may have put a file where the payload goes (R19-C3).**
Conversion deletes 179 paths; nothing stops the consumer from creating
one of them afterwards, and revert then restores onto an occupied path.
The reused helper already has an answer — `installer/fileops.py:365`
returns `conflict` unforced and `overwritten` forced, which round 19
confirmed by probe:

```text
unforced conflict
forced overwritten
```

But the matrix forbids `--force` with `--revert-thin`, on the ground
that revert makes no drift decision. That was true of *deletion* drift
and false of restore-path occupancy, so the rule is split rather than
loosened:

- Revert **preflights every restore path** before writing anything, and
  refuses the whole operation when any is occupied, listing them. It
  does not restore 178 files and stop at the 179th, and it does not flip
  the receipts or the registry.
- `--force` stays rejected on `--revert-thin`. Overwriting a consumer's
  file to reach a state they had before is the wrong default *and* the
  wrong flag: the recovery is to move or delete the colliding file and
  re-run, which is a decision only they can make with the file in front
  of them. The refusal message names the paths so that is a two-minute
  job.
- A path occupied by a file whose bytes already equal the source is not
  a collision. Restoring it is a no-op, and refusing there would block
  revert on a consumer who simply re-created a pack file correctly.

**Byte-identical restoration is version-bound.** `install.py` installs
from the *current* checkout's manifest (`install.py:803`), so a newer
pack cannot reconstruct an older payload's bytes from a pin that
carries only a version string. Revert therefore requires
`pin.version == source manifest version` and refuses otherwise, naming
both versions.

**And `--force` narrows the promise, so the promise is qualified rather
than quietly broken.** `--thin --force` deletes a drifted file; revert
restores the *source* bytes for that path, not the drifted bytes, which
no longer exist anywhere. Byte-identical restoration is therefore
guaranteed only for a conversion that ran without `--force`. A forced
conversion records `forced: [<paths>]` in the thin receipt, revert
reports those paths as restored-to-source rather than restored, and the
acceptance criterion for byte-identical restoration is scoped to the
unforced case. `--backup` mitigates but does not close this: it is
optional, so it cannot carry an unconditional promise. Reverting onto a different pack version is a fat
*re-install at that version*, which is a legitimate thing to want but
is not what "restore to pre-conversion state" promises, so it is not
what this flag does.

Two-root preflight, per C-D's matrix: both roots are checked writable
**before either is written**. An unwritable pack checkout or an
unwritable target refuses up front, exits nonzero, and leaves both
unchanged. A mid-operation failure reports which half completed and
exits nonzero — never a silent partial success.

The command does not commit or push either side.

### 6. Argument compatibility matrix

`parse_args` already enumerates incompatibilities for the machine and
inspection modes (`install.py:451`); `--thin` and `--revert-thin` are
two more mutators entering the same dispatch, and dispatch order
silently picks a winner when two are passed. The matrix is declared and
tested, not left to ordering:

| Combination | Behavior |
|---|---|
| `--thin` + `--revert-thin` | error — opposing mutators |
| `--thin`/`--revert-thin` + `--remove` | error — opposing mutators |
| `--thin`/`--revert-thin` + `--machine` | error — different root |
| `--thin`/`--revert-thin` + `--status`/`--check` | error — mutator with inspection |
| `--thin`/`--revert-thin` + `--configure-fleet` | error — unrelated mutation |
| `--thin` without `--resweep-verdict` | error — verdict is mandatory |
| `--resweep-verdict` without `--thin` | error — meaningless elsewhere |
| `--thin` or `--revert-thin` + `--platform`/`--all`/`--local-only` | error — payload selectors do not apply in either direction |
| `--consumer` with `--thin` or `--revert-thin` | allowed — overrides the receipt's recorded name, refuses on registry mismatch |
| `--consumer` alone, or with `--remove`/`--machine`/inspection | error — identity override has no meaning outside the two conversion directions |
| `--dry-run` with either direction | allowed |
| `--force` with `--thin` | allowed — overrides removal drift on delete, retire, **and** block-strip; nothing outside removal |
| `--force` with `--revert-thin` | error — no drift decision exists to override |
| `--backup` with either direction | allowed — same semantics as `--remove` |
| **standalone `--remove` on a `mode: thin` consumer** | **error — names `--revert-thin` first** |

Every row is a test. An unspecified row is how a destructive selector
gets silently ignored.

**The last row is R18-C2, and it was unspecified in exactly that way.**
Round 18 simulated a thin conversion, then ran the shipped
`install.py --remove --skip-diff-check`. It succeeded, deleted
provenance, and left the plugin enabled with settings untouched:

```text
pluginStillEnabled=true
settingsUnchanged=true
provenanceExists=false
```

That is the worst reachable state: a repository with no pack files, no
receipt saying a pack was ever there, and a live plugin serving the pack
from the marketplace. `--remove` never learns about it, because the
dispatcher hands standalone removal straight to the existing remover
(`install.py:858`), which knows about installed targets, managed blocks,
provenance, and excludes — and knows nothing about settings or the fleet
registry (`removal.py:333`).

The two candidate fixes are "make `--remove` thin-aware" and "refuse".
Refusal wins on a structural argument rather than a preference:
`--remove` takes one root, and undoing a thin conversion needs two —
the registry row lives in `ROOT`'s `docs/fleet/consumers.json`, which
`--remove` has no argument for and no reason to have one. A thin-aware
`--remove` would therefore be a removal that *cannot finish*, leaving
the registry claiming `thin` for a consumer that no longer has the pack
at all, and re-introducing the pin-vs-mode skew as a permanent state
instead of a window between two PRs. So:

- `--remove` on a consumer whose provenance says `mode: thin` exits
  nonzero, changes nothing, and says: run `--revert-thin` first, then
  `--remove`.
- The check reads the same `read_thin_receipt` predicate everything else
  uses. A fat consumer is unaffected — this row adds no behavior to the
  path every existing consumer takes.
- `--revert-thin` followed by `--remove` restores the payload and then
  deletes it, which is wasteful and correct. Uninstalling is rare, the
  two commands are each individually reversible, and the alternative is
  a one-root command silently doing three-quarters of a two-root job.

### 7. Registry mode flip

`--thin` and `--revert-thin` write `mode` into `ROOT`'s
`docs/fleet/consumers.json` for the named consumer. Per-consumer, not
per-cohort: batching would make a partially converted cohort
unrepresentable, and the registry is the authority `sd-status` reads to
decide which shape each consumer is in.

Every flip changes the fleet-manifest bytes, so the pack-side change
needs `make release-prep` (parent contract C-G), not `make check`.

## Fixtures

Real consumers are not touched. Three fixture shapes:

1. **Two fat shapes, not one.** A current install produces a
   **198-entry** receipt — that is what this repo's own checked-in
   `.sd-ai-command-pack/installed-targets.txt` holds — because a normal
   install retires stale targets before rewriting it (`install.py:903`).
   The fleet's live consumers carry **210**.

   The delta is measured, not inferred: consumer minus current is
   exactly the **13** retired `sd-full-check` / `sd-review-local`
   surfaces (across `.agents`, `.claude`, `.gemini`, `.github`,
   `.opencode`, and `scripts/`), and current minus consumer is exactly
   **1**, `scripts/sd-ai-command-pack-pack-update.sh`, which no consumer
   receipt lists. So 198 + 13 − 1 = 210.

   This also reconciles the "17 unclassified" figure, which counts
   something different: 13 retired **plus** the 3 `.sd-ai-command-pack/`
   bookkeeping files **plus** `.gitignore` — the last four are present
   in both receipts and are unclassified because the partition has no
   row for them, not because they are stale. The two named special cases
   are the bookkeeping trio and the managed-block files.

   Both shapes are real and they exercise different code: the 198
   fixture proves the current shape converts, and an explicitly seeded
   210 fixture proves the `retire` bucket is reached at all. Asserting
   210 from a fresh install would silently test only the first.
2. **Synthetic codex consumer** — declares `codex` so the
   `retainVendoredFor: ["codex", "pi"]` retention path executes. No live
   consumer exercises it, and the task records that rather than implying
   fleet coverage.
3. **Adversarial fixtures** — pre-existing `settings.json` with
   unrelated keys; a malformed `settings.json`; a drifted pack file; a
   drifted *retired* file; a malformed managed block; a tracked
   pack-like file absent from the receipt; a receipt entry no rule
   classifies; a read-only root in each of the two positions; a verdict
   whose `classifierDigest` no longer matches.

## Tradeoffs

- **The resweep shares the plan builder with `--thin`.** A bug in the
  builder blinds both lanes at once. Accepted: the alternative is two
  enumerations that can disagree about what is being deleted, which is
  worse — the resweep would then clear a conversion that deletes
  something else.
- **`--thin` requires a clean worktree.** Slightly awkward operationally
  (no converting on top of local edits) but it is what makes the verdict
  binding meaningful.
- **The thin receipt reuses `provenance.json`.** It carries a different
  shape under the same name, which is mildly confusing to read. The
  alternative — a new file — would mean `pinPath` diverges from the
  schema-5 default in every consumer entry, for no gain.
- **This task now changes `install.py --status`/`--check`, not just adds
  flags.** That is more surface than "write a converter", and it raises
  the regression risk for the fat path. It is not separable: without it
  every converted consumer is permanently `refresh-required` and
  `fleet-review-classify` breaks, so shipping the converter alone would
  knowingly leave the fleet in a broken reporting state. The mitigation
  is that the thin branch is gated on `mode: "thin"` in the receipt, so
  a fat consumer takes byte-identical code paths — which the existing
  inspection suite must prove, unchanged, as part of this task.
