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
  ∪ every MANAGED_BLOCK_REMOVAL_TARGETS member that exists in the target
  ∪ the three .sd-ai-command-pack/ bookkeeping files
```

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
  "worktreeClean": true,
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
this task exists to avoid. Reproduce with `research/fleet-blocker-scan.py`
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
   the resweep reads the span rather than re-deriving it. No consumer
   exercises this today — no `block_strip` target cites a removed path in
   any of the 8 — so it is correctness for the case that has not happened
   yet, and the research scanner does not implement it.

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
   generated targets (`installer/provenance.py:114`) — for managed blocks
   because ownership is genuinely shared. For those the **markers**
   decide: content between the pack's `SD-AI-COMMAND-PACK:*:START` and
   `:END` delimiters is the pack's, content outside them is the
   consumer's, in the same file. Force-preserved and generated targets are
   user-tunable by design and are judged as consumer-authored. A receipt
   entry that is a symlink, or whose bytes cannot be read, is
   unverifiable and blocks as a pack defect rather than passing.

   A surviving pack file that cites a path this conversion removes is a
   `packDefects` entry, and it **blocks**. The earlier draft called this
   `scheduled` on the reasoning that a later release would fix it; that
   recorded an obligation no artifact tracks and shipped known breakage
   in the meantime. Measured, and uniform across all 8 consumers — 13
   hits in 6 files:

   - `.github/copilot-instructions.md` 27, 51, 54, 106, 108 — inside the
     pack's own managed block, citing `docs/SD_AI_COMMAND_PACK.md` and
     `scripts/sd-ai-command-pack-install-audit.py`. Reached only through
     the marker rule above; digest comparison alone reports this file as
     consumer-authored and misses it.
   - `.github/prompts/sd-housekeeping.prompt.md` 37–38, `sd-review-learnings`
     44/46, `sd-review` 43, `sd-status` 43, `sd-help` 31–32 — each telling
     an agent to run or read something conversion removes.

   Fixing those is pack work that must land before any consumer converts,
   so the resweep names it rather than deferring it.

3. **Otherwise the file is consumer-authored. Does it cite a path this
   conversion removes?** Checked against the computed delete and retire
   sets — not against the string `sd-ai-command-pack`. A consumer test
   asserting on `.sd-ai-command-pack/provenance.json` names a path the
   conversion **keeps**, so it is not a blocker; one invoking
   `scripts/sd-ai-command-pack-full-check.sh` names a path that
   disappears, so it is. Three matchers, because one is not enough:
   exact/suffix path, basename, and `fnmatch` for globs. The glob matcher
   is not hypothetical — `loadsmith/.github/workflows/ci.yml:149`
   addresses the deleted population as `scripts/sd-ai-command-pack-*.sh`
   and names no exact path or basename anywhere.

   All three are a **lower bound**, and the design says so rather than
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
   - its basename is a build/CI entry point — `Makefile`, `package.json`,
     `pyproject.toml`, `tox.ini`, `noxfile.py`, `justfile`,
     `Taskfile.y*ml`, `.pre-commit-config.yaml`, `.gitlab-ci.yml`,
     `Dockerfile`;
   - it is under `.github/workflows/`, `.github/actions/`, `.circleci/`,
     `.devcontainer/`, or an agent-executed surface — `.github/prompts/`,
     `.github/instructions/`, `.claude/commands/`, `.claude/rules/`,
     `.claude/skills/`, `.agents/`, `.gemini/commands/`,
     `.opencode/command/`, `.codex/`;
   - its basename is a root agent instruction file — `CLAUDE.md`,
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

   Prose (`.md`, `.rst`, `.txt`), `.trellis/` history, and data-only
   config that nothing executes fall through to `advisories`.

   Discovery itself must also start from the removal set rather than from
   the pack's name — see the measurement correction below. A file citing a
   removed path without mentioning `sd-ai-command-pack` anywhere on the
   line is the case that a name-first search cannot see at all, and no
   amount of correct classification recovers a hit that was never found.

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

Consumer-authored executable callers, per consumer:
`sd-github-review` 6 hits in 4 files, `se-ai-command-pack` 12 in 7,
`loadsmith` 19 in 3, `hoa-manager` 27 in 7, `mezmo_benchmark` 26 in 14,
`rwbp-coordinator` 39 in 6, `rwbp-website` 51 in 5,
`anomaly-metric-creator` 181 in 17. Plus 13 pack defects in 6 files that
every consumer carries identically. They are CI workflows, `package.json`
scripts, repo-owned tests, and root agent instruction files that invoke
or assert on vendored pack paths.

**These figures are the second measurement, and the first was wrong in a
way worth recording.** The original scanner discovered candidate files by
grepping for the string `sd-ai-command-pack` and only then compared
tokens against the removal set — while this design's prose already said
the check was against removed paths, "not against the string
`sd-ai-command-pack`". The two are different sets, and the gap is not
theoretical: `sd-github-review/test/metadata.test.js:490` names the
removed `.agents/skills/sd-status/SKILL.md` with the pack name nowhere on
the line, and was absent from the first counts. Discovery now enumerates
tracked files and searches for the removal set itself — full paths, their
multi-segment suffixes, and pack-named basenames — with the pack name
retained only so glob citations stay discoverable. Every count above rose.
The lesson is specific: when prose and implementation describe the same
predicate, the implementation is the one that produced the number.

This is a real finding, not a tuning problem. It resizes children 3–5:
each consumer needs its execution surface repointed off the vendored
scripts **before** it can convert, and the pack must repoint its own
surviving prompts first. It also narrows what the step-3 fixture
criterion can claim — a synthetic fixture reaching `clear` proves the
C-A remediation landed, not that any real consumer can convert.

Codex/pi markers (`.codex/` directories, `$CODEX_HOME` references, pi
adapter files) are always `blocked` when the consumer's registry
`platforms` omits that platform, regardless of the delete set.

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

### 5. `install.py TARGET --revert-thin` (contract C-D)

Restores the fat payload, deletes the thin artifacts by reading
`settingsAdditions` from the thin receipt, writes the per-repo
`enabledPlugins` disable marker, and flips that consumer's `mode` back
to `fat` in `ROOT`'s `docs/fleet/consumers.json`.

**Consumer identity is carried, not inferred.** `--revert-thin` receives
only `TARGET`, but it must flip exactly one registry row. Inferring the
name from `pathHint` fails for a disposable checkout, a worktree, or an
alternate clone — and picking the wrong row silently mislabels two
consumers at once. The thin receipt therefore records the canonical
`consumer` name, `--consumer NAME` overrides it, and revert refuses on
a mismatch between receipt, registry, and flag rather than choosing.

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
| `--force` with `--thin` | allowed — overrides delete drift, nothing else |
| `--force` with `--revert-thin` | error — no drift decision exists to override |
| `--backup` with either direction | allowed — same semantics as `--remove` |

Every row is a test. An unspecified row is how a destructive selector
gets silently ignored.

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
