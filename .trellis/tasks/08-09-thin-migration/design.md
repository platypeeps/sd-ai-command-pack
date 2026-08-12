# Design: thin-mode migration, consumer CI cleanup, gate retirement

Refines the parent `08-09-deployment-thin-consumers` design section
"Migration" (requirements 3, 5, 6). Prerequisites are shipped:
`thin-surface-partition`, `thin-plugin-packaging`,
`thin-machine-installer`, and `thin-fleet-status-pins` are all archived
`completed`. Those four no longer block anything; children 1, 2, and 2b
of *this* task do, and child 2b is a hard prerequisite for the first
conversion (see "Child map"). Nothing external remains.

This task is a **parent of ordered children**. It owns the migration
contracts and the cross-child acceptance criteria below; each child owns
one independently verifiable deliverable.

## Evidence this design is built on

Measured against the shipped artifacts on `main` at `d7913054`, not from
memory:

- `docs/fleet/surface-partition.json` schema 1, 724 rows,
  `counts = {machine-claude: 79, machine-other: 88, repo-native: 551,
  consumer-config: 6}`.
- Platform dispositions: `claude`, `gemini`, `opencode`, `shared` are
  `machine`; the other 14 registry platforms are `repo-native`. No
  platform carries `provisional: true`. Only `shared` carries
  `retainVendoredFor: ["codex", "pi"]`.

  > Superseded after this snapshot, and left standing because the
  > section is a measurement at a named commit rather than a current
  > claim: 0.71.2 removed `codex` from that list on executed probe
  > evidence that Codex reads `$HOME/.agents/skills`, which the machine
  > installer already writes. `shared` now carries `["pi"]`. Re-measure
  > before relying on any figure here; the row count has also moved.
- `docs/fleet/consumers.json` schema 5: 8 consumers, cohorts
  `canary` (rwbp-coordinator, loadsmith, hoa-manager, sequential),
  `post-canary` (rwbp-website, mezmo_benchmark, se-ai-command-pack,
  sd-github-review, bounded-parallel max 2), `final`
  (anomaly-metric-creator, sequential).
- **Every consumer declares exactly `["claude", "gemini", "github",
  "opencode"]`.** Intersecting that with the partition yields **167
  machine-scope rows** (53 `machine-claude` claude + 19 `machine-other`
  gemini + 19 `machine-other` opencode + 50 `machine-other` shared + 26
  `machine-claude` shared) and **27 kept rows** (21 `repo-native` github
  + 2 `consumer-config` claude + 4 `consumer-config` shared).
  **That 167 is current-partition arithmetic, not a deletion count.**
  Measured against the eight real checkouts, the per-consumer operation
  is **166** machine files — `scripts/sd-ai-command-pack-pack-update.sh`
  is in the current partition but in none of the receipts — plus 13
  retired files, plus the four special cases below.
- **The consumers are not at one pin.** Measured 2026-08-10:
  rwbp-coordinator `0.64.4`, loadsmith `0.64.27`,
  se-ai-command-pack `0.64.33`, the other five `0.64.3`. Their
  installed-targets receipts nevertheless agree exactly — 210 entries
  each, 166 machine / 27 kept / 13 retired / 4 special — so uniform
  arithmetic here is an observed coincidence of these pins, never a
  property to rely on. Conversion recomputes per consumer.
- **Correction to the ancestor design.**
  `08-09-deployment-thin-consumers/design.md` says "`github` surfaces
  (23 files) are repo-native by construction". The shipped partition
  artifact has **21** `github` rows, all `repo-native`. The count is
  stale; the classification is right. Recomputed 2026-08-10; use the
  artifact, never either number.
- `retainVendoredFor` is **inert today**: no consumer declares `codex`
  or `pi`, so zero `.agents/**` rows are retained anywhere. The resweep
  gate below still exists, because a consumer using codex/pi without
  declaring it is exactly the case that must block rather than silently
  delete.
- `install.py` today has `--machine`, `--remove`, `--force`, `--backup`,
  `--dry-run`, `--status/--check --json`, `--configure-fleet`. It has
  **no** `--thin` and **no** `--revert-thin`. Nothing in the repository
  writes `extraKnownMarketplaces` or `enabledPlugins` into a consumer's
  `.claude/settings.json` — only this repo's own checked-in
  `.claude/settings.json` mentions them. Both surfaces are new code.
- `installer/removal.py` already owns vouched-vs-drifted deletion
  (`remove_installed_pack`, `may_remove_pack_file`,
  `retire_stale_targets`); `installer/provenance.py` owns receipt
  read/write. Conversion composes these rather than re-implementing
  deletion safety.
- The candidate loop is
  `scripts/sd-ai-command-pack-fleet-candidate-check.py`, whose
  `validate_consumer` performs the **fat** install and audit against a
  disposable checkout. `.github/scripts/prepare-release.py:342` invokes
  it as `CANDIDATE_CHECK`, and **skips it entirely** when
  `_candidate_refresh_required(report)` is false
  (`prepare-release.py:338`). `scripts/sd-ai-command-pack-fleet-preflight.py`
  only reports local refresh status and is not the candidate loop —
  naming it as such was wrong and is corrected here.

## Contracts this task owns

### C-A. Conversion is a two-phase, fail-closed operation

Phase 1 **resweep** (read-only, per consumer, at that consumer's exact
HEAD) and phase 2 **convert** (mutating). Convert refuses to run unless
a resweep verdict for the current HEAD says clear. The verdict is typed
and machine-readable, never prose a human eyeballs.

The resweep greps the consumer for:

1. references to paths that **do not survive** conversion, cited from
   files that **do** — workflows, git hooks, Make targets, agent
   prompts, repo-owned tests. A blocking hit names the file and line.

   **A reference inside an enumerated deletion target is not a
   blocker.** `docs/SD_AI_COMMAND_PACK.md` is itself a `machine-other`
   row and every consumer's copy references the pack in its opening
   lines; pack workflow steps are likewise scheduled for deletion. A
   resweep that blocked on those could never return `clear` for any
   consumer that exists today.

   **Nor is the mere string `sd-ai-command-pack` a blocker.** Measured
   across the fleet, a surviving file citing the pack is the ordinary
   case, not the exception (`rwbp-coordinator`: 53 surviving files cite
   it). What blocks is a surviving file citing a path this conversion
   *removes*. The resweep computes the removal set first and sorts hits
   into four classes, each failing closed:

   - *scheduled* — the hit lives in a file conversion removes.
     Informational, listed so the conversion PR can be read against it.
   - *packDefects* — a surviving file whose content is still the pack's
     own cites a removed path. **Blocking, and ours to fix**: measured
     16 hits in 7 files for the five consumers that have not edited their
     PR template, 14 in 6 for the three that have — four pack-shipped
     prompts telling an agent to run removed scripts, the pack's managed
     block in `.github/copilot-instructions.md`,
     `.github/PULL_REQUEST_TEMPLATE.md`, and the `obsidian-kb` block that
     survives in `.gitignore` while the `trellis-gitignore` block beside
     it is stripped. Ownership is proven three ways,
     because one is not enough: a receipt entry whose sha256 matches
     provenance; for managed-block targets, which provenance deliberately
     never vouches, content between the pack's block markers; and for
     force-preserved targets, which it also never vouches, comparison
     against the pack's own shipped bytes. Receipt membership alone does
     not confer the classification: a consumer-edited kept target is
     consumer-authored, and content outside a managed block is the
     consumer's even when the file is a pack target.
   - *blockers* — a consumer-authored file on the execution surface
     cites a removed path. **Blocking, and the consumer's to fix**;
     clearing it is explicit cleanup work carried in that consumer's
     conversion PR.
   - *advisories* — any other consumer-authored citation. Stale prose a
     human should fix, never a reason to refuse a conversion.

   The verdict is `clear` only when both blocking classes are empty.
   Child 1's `design.md` owns the decision procedure — what counts as
   the execution surface, and how a citation is matched — together with
   the fleet measurement behind it. That check matches a citation in five
   forms — the exact path; a tail of the cited token at a path boundary; a
   token resolved relative to the citing file; a glob whose **whole**
   matched population the conversion removes; and a bare basename that is
   both unique to the removal set and pack-distinctive — and is a
   **lower bound**: a runtime-composed
   path is invisible to any static reader, so reversibility via
   `--revert-thin` is what makes the conversion safe, not resweep
   exhaustiveness.

2. codex/pi usage markers (`.codex/` directories, `$CODEX_HOME`
   references, pi adapter files) — a hit in a consumer whose registry
   `platforms` array omits that platform is a **blocker**, not a
   warning. It clears only when the consumer declares the platform
   (turning `retainVendoredFor` retention on) or removes the usage.

The verdict binds to the **worktree**, not only to `HEAD`. A file can
change without `HEAD` moving, so a HEAD-keyed verdict can be stale at
the moment of a destructive conversion. The verdict therefore records a
worktree digest and requires a clean tree; conversion refuses when
either has moved.

It binds the **pack side** too. The resweep and the conversion are two
processes, so a shared plan builder guarantees the same result only if
the builder's inputs are identical. The verdict therefore also records a
digest over the partition, the consumer's registry entry, the plugin
manifests, the bytes of the modules that define `RETIRED_TARGETS`,
`MANAGED_BLOCK_REMOVAL_TARGETS`, and the builder itself, **and the bytes
of the resweep script**. The builder decides what is removed; the resweep
decides what counts as a citation, as the execution surface, and as
pack-owned content. Omitting the second leaves a `clear` verdict valid
under an unchanged digest after the rule that produced it changed. Binding pack
`HEAD` instead would bind a commit while leaving uncommitted edits to
those same files invisible.

The 2026-08-09 fleet sweep is a dated snapshot and carries no authority
here; every conversion resweeps.

### C-B. The deletion set is enumerated from the consumer, classified by the partition

The delete set starts from **the consumer's own installed-targets
receipt** (`installer/provenance.py:222`,
`read_existing_installed_targets`) — what that checkout actually has —
and each entry is then classified through
`docs/fleet/surface-partition.json`. Entries classified
`machine-claude` or `machine-other` are deleted; `repo-native` and
`consumer-config` entries are kept; entries whose platform carries a
`retainVendoredFor` intersecting the consumer's declared `platforms`
are kept.

**Starting from the pack's current partition instead would be wrong,
and this is measured, not predicted.** Every one of the 8 consumers
holds a 210-entry `.sd-ai-command-pack/installed-targets.txt`, of which
**17 entries have no row in the current partition**. The 17 are the
same set in all 8 checkouts even though their pins differ. They break
down as:

- **13** are retired command surfaces (`sd-full-check`,
  `sd-review-local` across `.agents`, `.claude`, `.gemini`, `.github`,
  `.opencode`, and `scripts/`) that left the manifest with
  `07-24-remove-retired-review-surfaces`. They are in
  `installer/removal.py`'s `RETIRED_TARGETS` (157 entries), so they are
  removed **only if conversion runs `retire_stale_targets`** —
  partition enumeration alone never names them.
- **3** are the install bookkeeping files themselves
  (`.sd-ai-command-pack/provenance.json`, `manifest.json`,
  `installed-targets.txt`). Thin mode **keeps all three and rewrites
  them** to describe the residual payload; `provenance.json`
  additionally becomes the thin pin. Replacing them with a single pin
  file would break two existing readers: `install.py --status/--check`
  requires all three to be occupied (`installer/inspection.py:30`,
  `:253`), and the structural audit requires `provenance.json` to carry
  a non-empty `files` map
  (`scripts/sd-ai-command-pack-install-audit.py:701`). Child 1's
  `design.md` carries the resolved schema.
- **1** is `.gitignore`, which the pack owns as a **managed block
  inside a consumer-owned file**. Conversion removes the block; it must
  never delete the file. Nothing about "delete the machine-scope rows"
  expresses that, which is exactly why it is named here.

  There is a second managed-block file, and it does *not* appear in
  this 17 because the partition does classify it:
  `installer/removal.py:55 MANAGED_BLOCK_REMOVAL_TARGETS` holds both
  `.gitignore` and `.github/copilot-instructions.md`. The latter is
  `repo-native` — every `github` row is, because Copilot reads the
  repository and cannot see the machine — so conversion keeps it with
  its block intact. Conversion enumerates that frozenset rather than
  naming `.gitignore`, and classifies each member through the
  partition; a member that is neither blocks.

Had the delete set been enumerated from the current partition and the
result verified against that same partition, all 17 would have survived
and the check would still have reported success — the partition never
mentioned them. So the delete set is: receipt entries classified
`machine-claude`/`machine-other`, **plus** `retire_stale_targets`'
retired-target pass, **plus** the two named special cases above. Any
receipt entry still unclassified after that blocks the conversion and
is reported — never deleted, never silently kept. Verification compares
the post-conversion tree against the pre-conversion receipt (see the
acceptance criteria of children 1 and 3–5).

A platform entry with `provisional: true` is treated as `repo-native`
and stays vendored.

The consumer's declared `platforms` in `docs/fleet/consumers.json` is
the single authority for retention decisions; conversion never sniffs
the consumer repo to decide what a platform is.

A consumer with no readable installed-targets receipt cannot be
converted safely by enumeration and blocks with that diagnostic.

Deletion runs through `installer/removal.py`'s existing vouched/drifted
rules: a drifted file is preserved and reported, never silently deleted,
unless `--force` is passed exactly as `--remove` already requires.

**But preserving a drifted file mid-conversion is not acceptable here,
and that differs from `--remove`.** `remove_pack_file` reports a
differing file and the removal operation can still return success
(`installer/removal.py:185`, `:408`). For `--remove` that is right — the
repo simply keeps a file. For conversion it is not: enabling the plugin
and writing a thin pin on top of surviving vendored surfaces produces a
repository that is neither fat nor thin, with duplicate or stale
surfaces the pin claims are gone. So conversion computes and validates
the **complete** plan before touching anything; any unforced drift
aborts with the tree unchanged and with no settings write, no pin, and
no mode flip.

**The receipt is necessary but not sufficient.** A tracked pack-like
file that the receipt never listed would survive conversion *and* pass a
receipt-based comparison. `scripts/sd-ai-command-pack-install-audit.py`
already enumerates tracked pack-like paths independently of the receipt,
and `.trellis/spec/backend/manifest-and-filesystem.md:1008` makes an
unlisted one a failure. Conversion therefore runs that structural audit
before mutating, and verification after conversion scans for tracked
pack-like files outside the thin allowlist rather than trusting the
receipt subtraction alone.

### C-C. Conversion adds exactly three things

`.claude/settings.json` marketplace + enable entries; the pin receipt;
and the `mode: thin` flip in `docs/fleet/consumers.json` (which lives in
*this* repo, so every conversion is a two-repo change: one consumer PR
plus one pack PR, or one pack PR batching a cohort's flips — the child
picks one and states it).

`.claude/settings.json` is **not a pack-managed path**: it has zero rows
in `docs/fleet/surface-partition.json`, so a consumer's copy is entirely
consumer-owned and may contain unrelated keys. The writer therefore
merges — it adds `extraKnownMarketplaces` and `enabledPlugins` entries,
preserves every other key byte-for-byte, and creates the file only when
absent. Revert removes exactly the entries conversion added and leaves
the rest, which is why conversion must record what it added rather than
inferring it later.

### C-C2. A converted consumer requires a provisioned machine

Conversion removes the repository's agent surfaces on the assumption
that the machine supplies them. For anyone whose machine has no plugin
install and no machine-installer receipt, conversion is
indistinguishable from deletion. So each conversion cohort states the
operator prerequisite — plugin installed from the marketplace, machine
install run, both verifiable through `sd-status`'s machine scope — and
records it before mutating. This is a communication and verification
step, not code; naming it here is what stops it being discovered by a
developer whose skills vanished.

### C-D. Revert is one command and is proven, not asserted

`install.py TARGET --revert-thin` restores the fat payload, removes the
thin artifacts conversion added, and writes a per-repo `enabledPlugins`
disable so the machine-wide plugin does not produce duplicate surfaces
in that repo. That disable marker is the one intentional residue;
everything else conversion added is gone.

**It also flips `mode` back to `fat`.** The registry lives in the pack
checkout the command runs from, so one command genuinely writes both
repositories — that is what the parent PRD's "one command" requires, and
it is achievable precisely because `install.py` executes from the pack
checkout. What the command cannot do is commit or push the pack-side
change; that stays a normal reviewed pack PR. `implement.md`'s rollback
step says the same thing, and the two must not drift apart: a plan that
says "run the command, then also revert the registry by hand" would
contradict this contract.

The mechanism works because `ROOT` derives from the installer package's
own location (`installer/registry.py:8`), independently of the CLI
target resolved in `install.py:803` — one process legitimately holds
both roots.

Two roots means two ways to fail, and both are specified rather than
discovered:

**The matrix governs `--thin` as well as `--revert-thin`.** Conversion
also writes both roots — it deletes in the consumer and flips `mode` in
the registry — and the forward direction has the worse failure ordering:
an unwritable registry discovered after 166 consumer files are gone
leaves a converted consumer the fleet still believes is fat. Child 1's
`design.md` carries the failure-injection cases for both directions.

| ROOT (pack checkout) | TARGET (consumer) | Behavior |
|---|---|---|
| writable | writable | Both writes happen. Exit 0. |
| **not** a writable pack checkout | writable | **Preflight refuses before any write.** Exit nonzero, tree unchanged, registry unchanged. |
| writable | not writable | **Preflight refuses before any write.** Exit nonzero, both unchanged. |

Both roots are checked **before** either is written; the command never
starts a revert it cannot finish. If a write nonetheless fails
mid-operation, the command reports which half completed and exits
nonzero — a consumer reverted to fat while the registry still says thin
is exactly the skew state this migration exists to make visible, and it
must be reported rather than absorbed. Never a silent partial success.

Revert is verified by executing it on a converted consumer and
confirming CI stays green — not by reading the code.

### C-E. Gates retire by enumeration, after the last conversion

What retires is **consumer fat installation and audit**, which lives in
`scripts/sd-ai-command-pack-fleet-candidate-check.py`'s
`validate_consumer` — not in `make check`.

What must **not** retire is
`scripts/sd-ai-command-pack-surface-check.py`, which `make check`
reaches through `scripts/sd-ai-command-pack-full-check.sh:612`. That
checker validates template registration and root mirror bytes *inside
this repository* — the exact source-of-truth gate `AGENTS.md:29`
requires. "Retire the shipped-surface closure gate" and "keep the
pack-internal mirror gate" name overlapping machinery, and treating
them as two separable switches is how the mirror gate gets removed by
accident.

So child 5 retires by **enumerating the exact functions and tests it
removes or rescopes**, and proves afterwards that the surviving mirror
gate still fails on a deliberately introduced drift. The spec/doc sweep
is a grep of install/fleet spec surfaces whose passing form enumerates
from the filesystem — zero descriptions of consumer vendoring as
*current* behavior may survive.

### C-F. The candidate loop is rescoped before the first conversion

The loop to change is
`scripts/sd-ai-command-pack-fleet-candidate-check.py` — specifically
`validate_consumer`, which today does the fat install and audit. It must
also validate the thin shape (plugin build,
`claude plugin validate --strict`, `claude --plugin-dir` load smoke,
machine install into a scratch prefix) against disposable consumer
checkouts, keeping each consumer's repo-owned `candidateChecks`.

Two properties of the current wiring make the naive version of this
contract vacuous, and the rescope must defeat both:

- **All eight registry entries omit `mode`, so every one defaults to
  `fat`** (`scripts/sd_ai_command_pack_fleet_lib.py:26`). "Exercise each
  consumer in its declared mode" would therefore exercise zero thin
  checkouts before child 3 — the gate would pass while validating
  nothing new. The rescope must run the thin shape against disposable
  checkouts *regardless* of the modes currently declared.
- **`prepare-release.py:338` skips the validator entirely** when the
  candidate ledger is already current, so a green `make release-prep`
  is not by itself evidence the loop ran.

Doing this before any consumer converts means the pre-release full-fleet
gate never has a window where it validates a shape no consumer runs. It
depends on child 1, because converting a disposable checkout to the thin
shape is `--thin`.

### C-G. Differing fleet-manifest bytes at a merge boundary are a release-prep event

`docs/fleet/consumers.json` is the fleet manifest whose digest
(`fleet_manifest_digest`, `scripts/sd_ai_command_pack_fleet_lib.py:766`)
is pinned into `docs/fleet/candidate-validation.json` and compared by
equality (`:784`) inside `make check`.

Stated precisely: **at each child's merge boundary, fleet-manifest bytes
that differ from the pinned ones invalidate the ledger.** A forward
`fat` → `thin` edit always does that. The checker keeps no transition
history, so restoring the exact pinned bytes makes the old ledger
current again, and ledger consumer rows do not bind the validated mode
(`:823`) — which is why the contract is about differing bytes at a merge
boundary, not about mode-flip events as such.

A child that flips a mode and claims "`make check` passes" is therefore
asserting something that cannot be true until the ledger is refreshed,
and the refresh is what `make release-prep` does (`CONTRIBUTING.md:122`)
— regenerate, self-sync, refresh exact fleet evidence, then check.

Children 1–5 therefore gate on `make release-prep` whenever the payload
or the fleet manifest changed, and on `make check` otherwise.

## Child map (ordered)

| # | Child | Scope | Authority |
|---|-------|-------|-----------|
| 1 | `thin-conversion-tooling` | resweep verdict + `--thin` + `--revert-thin` + settings/pin writers | pack-internal |
| 2 | `thin-candidate-loop-rescope` | C-F | pack-internal |
| 2b | `thin-prompt-surface-repoint` | the seven pack-shipped surfaces that survive conversion and still cite removed paths | pack-internal |
| 3 | `thin-canary-conversion` | rwbp-coordinator, loadsmith, hoa-manager + the executed revert proof | **converts real consumer repos** |
| 4 | `thin-post-canary-conversion` | rwbp-website, mezmo_benchmark, se-ai-command-pack, sd-github-review | **converts real consumer repos** |
| 5 | `thin-final-conversion-gate-retirement` | anomaly-metric-creator (incl. `sd-ai-command-pack-sync.yml` + the advisory `pr-body-scope.py` CI step), then C-E | **converts a real consumer repo** |

Children 1, 2, and 2b are ordinary pack-repo work. Child 2b is a hard
prerequisite for 3–5 and the tool enforces it: its surfaces are
`packDefects`, a `packDefects` entry makes the verdict `blocked`, and
`--thin` refuses without `clear`. Children 3–5 mutate
repositories outside this one and are **gated on explicit user
authorization per cohort**; the autonomous run-level authority does not
extend to them. Each of 3–5 carries a `blockedOn` marker until that
authorization is given, so the backlog ranker cannot select them.

## Tradeoffs accepted

- **Two-repo conversion.** The `mode` flip lives in the pack registry
  while the deletion lives in the consumer, so a conversion is never
  atomic. Accepted: `sd-status fleet` already reports pin-vs-mode skew
  as a first-class row (shipped in `thin-fleet-status-pins`), so the
  window is observable rather than silent.
- **`retainVendoredFor` ships untested against a real consumer**
  because no consumer declares codex or pi. Child 1 covers it with a
  synthetic fixture consumer; that is weaker than a live conversion and
  is recorded as such rather than claimed as fleet-proven.
- **Uniform arithmetic today does not mean uniform arithmetic
  tomorrow.** The measured 166/27 per-checkout split — and the 167
  current-partition figure it differs from — are measurements of one
  moment, not constants; conversion recomputes per consumer every time
  and asserts nothing about the count.

## Rollout / rollback shape

Children land 1 → 2 → 3 → 4 → 5. Fat mode stays fully supported until
child 5 completes. Rollback for any converted consumer is C-D's single
command, available from child 1 onward and re-verified in child 3. If
child 3 fails on a canary, children 4 and 5 do not start — the fleet
stays mixed-mode indefinitely without harm, which is the property that
makes cohort ordering worth having.
