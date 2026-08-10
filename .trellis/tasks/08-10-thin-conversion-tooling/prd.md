# Thin conversion tooling: resweep verdict, `--thin`, `--revert-thin`

Child 1 of `08-09-thin-migration`. Pack-internal: this task ships the
tooling that later children point at real consumer repositories. It
mutates no consumer.

## Problem

`install.py` has `--machine`, `--remove`, `--force`, `--backup`,
`--dry-run`, `--status/--check --json`, and `--configure-fleet`. It has
no `--thin` and no `--revert-thin`. Nothing in the repository writes
`extraKnownMarketplaces` or `enabledPlugins` into a consumer's
`.claude/settings.json` — the only file mentioning them is this repo's
own checked-in `.claude/settings.json`. Converting a consumer today
would be a hand-edited deletion of 166 files with no reversal path.

## Requirements

1. **Resweep verdict, read-only and typed.** A command that inspects one
   consumer checkout and emits a machine-readable verdict (`clear` or
   `blocked` with reasons carrying file and line). It greps for pack
   references and for codex/pi usage markers (`.codex/` directories,
   `$CODEX_HOME` references, pi adapter files). A codex/pi marker in a
   consumer whose registry `platforms` omits that platform is a blocker,
   not a warning.

   **Pack references inside the conversion's own deletion targets do not
   block** (parent contract C-A). `docs/SD_AI_COMMAND_PACK.md` is a
   `machine-other` row and every consumer's copy references the pack in
   its opening lines, so a resweep that blocked on it could never return
   `clear` for any consumer that exists today. The resweep computes the
   removal set first and sorts every hit into four buckets, each failing
   closed: *scheduled* (the hit lives in a file conversion removes —
   informational), *packDefects* (a surviving file whose content is still
   the pack's own cites a removed path — blocking, and ours to fix),
   *blockers* (a consumer-authored file cites a removed path in command
   position — blocking, and the consumer's to fix), and *advisories*
   (any other consumer-authored citation — stale prose a human should
   fix, never a reason to refuse). `design.md` carries the decision
   procedure and the measurement behind it.

   The citation check matches a removed path exactly, as a tail of the
   cited token, resolved relative to the citing file, or by glob — and
   nothing looser. Bare-basename matching was tried and removed: the
   removal set contains names like `SKILL.md` and `config.toml`, so it
   manufactured blockers out of surviving sibling files. The check is a
   **lower bound** by construction: a path composed at runtime from
   variables is invisible to any static reader. Reversibility via
   `--revert-thin`, not resweep exhaustiveness, is what makes conversion
   safe.

   **The verdict binds to a worktree digest and requires a clean tree**,
   not just to `HEAD` — a file can change without `HEAD` moving, and a
   destructive conversion must not accept evidence that stale. It binds
   the **pack side** as well: the partition, the consumer's registry
   entry, the plugin manifests, and the bytes of the modules defining
   `RETIRED_TARGETS` and `MANAGED_BLOCK_REMOVAL_TARGETS`. Binding pack
   `HEAD` instead would leave uncommitted edits to those files invisible.

   The resweep is a **fleet-operator tool and is not shipped** into
   consumers: `manifest.json` carries no `fleet-*` script and not
   `docs/fleet/surface-partition.json`, so a resweep running inside a
   consumer would have no classification data at all. It lives in
   `scripts/` with no template counterpart, like every other fleet
   script.

   Blocker `line` is nullable: a `.codex/` directory has no line.
2. **`install.py TARGET --thin`** refuses to mutate unless a `clear`
   resweep verdict for the current HEAD is present. It computes the
   delete set per contract C-B in the parent `design.md`: start from the
   consumer's **installed-targets receipt**
   (`installer/provenance.py:222`), classify each entry through
   `docs/fleet/surface-partition.json`, delete the `machine-claude` and
   `machine-other` entries, keep `repo-native`, `consumer-config`, and
   `retainVendoredFor` matches. Never from a list stored in this task or
   in code, and never from the current partition alone. Measured across
   all 8 consumers: each receipt holds 210 entries, 17 of which no
   current partition row classifies. Conversion therefore also runs
   `installer/removal.py:256` `retire_stale_targets` (covering 13 of the
   17 through `RETIRED_TARGETS`) and handles two named special cases.

   **The three `.sd-ai-command-pack/` bookkeeping files are all kept and
   rewritten**, not replaced by a single pin. `install.py --status/--check`
   treats the footprint as incomplete unless all three are occupied
   (`installer/inspection.py:30`, `:253`), and the structural audit
   requires `provenance.json` to carry a non-empty `files` map
   (`scripts/sd-ai-command-pack-install-audit.py:701`). Each is rewritten
   to describe the residual payload; `provenance.json` additionally
   carries `mode: "thin"` and the recorded settings additions.

   **Managed blocks are enumerated, not named.** The pack owns blocks in
   two consumer-owned files, not one:
   `installer/removal.py:55 MANAGED_BLOCK_REMOVAL_TARGETS` holds
   `.gitignore` and `.github/copilot-instructions.md`. Their fates differ
   and the partition decides: `.gitignore` has no partition row and its
   block is stripped; `.github/copilot-instructions.md` is `repo-native`
   — every `github` row is, because Copilot reads the repository and
   cannot see the machine — so it is kept with its block intact. Neither
   file is ever deleted. A managed-block member that is neither blocks.

   Deletion goes through `installer/removal.py`'s existing
   vouched/drifted rules. Conversion then adds the
   `.claude/settings.json` marketplace + enable entries and rewrites the
   receipts.

   **Unlike `--remove`, conversion fails closed at preflight.**
   `remove_pack_file` reports a drifted file and the operation can still
   succeed (`installer/removal.py:185`, `:408`); for conversion that
   would leave a repo that is neither fat nor thin, with a pin claiming
   surfaces are gone while they are still present. The complete plan is
   computed and validated first, and any unforced drift aborts with the
   tree unchanged and no settings write, no pin, and no mode flip.

   **Before mutating, run the structural install audit**
   (`scripts/sd-ai-command-pack-install-audit.py`), which enumerates
   tracked pack-like paths independently of the receipt. A tracked
   pack-like file the receipt never listed would otherwise survive
   conversion and still pass a receipt-based comparison.
3. **`.claude/settings.json` is consumer-owned** — zero rows in the
   partition artifact. The writer merges: it adds the marketplace and
   enable entries, preserves every other key unchanged, creates the file
   only when absent, and records what it added so revert can remove
   exactly that.
4. **`install.py TARGET --revert-thin`** restores the fat payload,
   removes the thin artifacts `--thin` added, writes the per-repo
   `enabledPlugins` disable marker, **and flips that consumer's `mode`
   back to `fat` in `docs/fleet/consumers.json` in the pack checkout it
   runs from** — one command, both repositories, per parent contract
   C-D. It does not commit or push the pack-side change. The disable
   marker is the only intentional residue in the consumer.

   Both roots are preflighted **before either is written**, per C-D's
   write-order matrix: an unwritable pack checkout or an unwritable
   target refuses up front, exits nonzero, and leaves both unchanged.
   The command never starts a revert it cannot finish, and never
   reports a partial revert as success.
5. **Fail closed on unknown scope.** A partition platform entry carrying
   `provisional: true` is treated as `repo-native` and its rows stay
   vendored. A receipt entry no partition row classifies **blocks the
   conversion and is reported** — it is never deleted and never silently
   kept. A missing or unreadable installed-targets receipt blocks with
   that diagnostic. An unknown platform or a missing partition artifact
   stops the run — never a partial deletion.
6. **`--dry-run` support on both directions**, printing the exact delete
   and add sets without touching the target.
7. The `mode: thin` registry flip in `docs/fleet/consumers.json` is
   in scope as a documented, testable operation; whether it batches per
   cohort or lands per consumer is decided in this task's `design.md`.
8. **`install.py --status`/`--check` become thin-aware.** This was not in
   the task's original scope and is not separable from it. `--check`
   decides state by dry-running an install of the **full** source
   payload and counting would-be changes
   (`installer/inspection.py:374-395`); a thin consumer is missing 166
   machine files by design, so it would report `refresh-required`
   permanently. `scripts/sd-ai-command-pack-fleet-review-classify.py:212`
   requires `state: current`, so shipping the converter without this
   would knowingly leave every converted consumer misreported. The thin
   branch is gated on `mode: "thin"` in the receipt so fat consumers take
   unchanged paths.

## Non-goals

- Converting any real consumer repository. That is children 3–5.
- Retiring any gate. That is child 5.

## Acceptance criteria

- [ ] The resweep emits `blocked` with file and line for a fixture
      consumer whose workflow cites a path the conversion removes, and
      `clear` for one whose only pack references are to paths the
      conversion keeps. A bare "pack reference" is not the criterion:
      every consumer has hundreds, and blocking on them is the C-A
      failure this task exists to avoid.
- [ ] The resweep classifies each of these fixture cases correctly, one
      case per bucket boundary the measurement proved wrong: a removed
      path cited by a glob (`scripts/sd-ai-command-pack-*.sh`); a removed
      path cited from a nested `templates/**/scripts/*.py`; a removed
      path cited by an agent-executed `.github/prompts/*.prompt.md`; a
      removed path cited only in prose (`advisories`, not blocking); and
      a *kept* path cited from a workflow (neither, verdict stays
      `clear`).
- [ ] A surviving pack-managed file citing a removed path lands in
      `packDefects` and blocks; the same file, once edited by the
      consumer so its digest no longer matches provenance, is
      reclassified as consumer-authored. Receipt membership alone must
      not confer the exemption.
- [ ] Ownership is decided for the two target classes provenance
      deliberately never vouches, not defaulted: a **managed-block**
      target by marker position, with malformed markers falling to
      pack-owned rather than to a guessed span; and a **force-preserved**
      target by comparison against the pack's own shipped bytes, so a
      pack-identical `.github/PULL_REQUEST_TEMPLATE.md` is a `packDefect`
      while a consumer-edited one is a `blocker`.
- [ ] The resweep emits `blocked` for each of three separate marker
      fixtures whose registry `platforms` omits the platform — a
      `.codex/` directory, a `$CODEX_HOME` reference, and a pi adapter
      file — and `clear` for each once the platform is declared. One
      combined case would pass while two of the three markers were never
      implemented.
- [ ] `install.py --check` on the converted fixture computes its
      expected residual as keep-category source targets whose partition
      platform the consumer declares, plus platform-independent
      `consumer-config` rows, plus every existing managed-block file,
      plus the three bookkeeping files — measured at exactly 31 targets
      for `rwbp-coordinator`'s shape, all present (26 keep rows + 2
      managed-block files + 3 bookkeeping files, with
      `.github/copilot-instructions.md` counted once in the union). A new `repo-native`
      file for a **declared** platform must move `--check` to
      `refresh-required`; one for an **undeclared** platform must not.
      Testing only the first passes while the platform predicate is
      missing entirely.
- [ ] `--thin` on a disposable fat checkout of a real consumer's shape
      deletes exactly the enumerated set and leaves the `repo-native` +
      `consumer-config` slices intact, verified by comparing the
      post-conversion tree against **the pre-conversion installed-targets
      receipt**, not against the current partition — a partition-only
      comparison passes even when orphans survive, which is the defect
      this criterion exists to catch.
- [ ] A fixture consumer whose receipt lists a file that is absent from
      the current partition, absent from `RETIRED_TARGETS`, and not one
      of the named special cases **blocks** conversion, naming that
      file. The same fixture converts cleanly once the file is
      classified.
- [ ] A fixture consumer carrying the 17 real orphan entries observed
      on the fleet converts with all 13 `RETIRED_TARGETS` entries
      removed, the pack's `.gitignore` managed block removed while the
      consumer's own `.gitignore` lines survive,
      `.github/copilot-instructions.md` kept with its block intact, and
      all three `.sd-ai-command-pack/` bookkeeping files rewritten to the
      residual payload. This fixture is seeded to the 210-entry fleet
      shape explicitly: a fresh `install.py` produces 198 entries because
      it retires stale targets before rewriting the receipt
      (`install.py:903`), so a fresh install would never reach the
      `retire` bucket at all.
- [ ] `scripts/sd-ai-command-pack-install-audit.py --repo FIXTURE` exits
      **0** against the converted fixture, and `install.py --check`
      reports `state: current`. Asserting the absence of selected audit
      messages is not accepted: that passes while the audit fails on
      `provenance.json has no files map`.
- [ ] `read_consumer_pin` on the converted fixture reports
      `state: "present"` **and** `mode: "thin"` with a populated
      settings-additions record. `present` alone proves nothing — an
      untouched fat `provenance.json` already satisfies it.
- [ ] The existing inspection test suite passes **unchanged**, proving
      fat consumers take byte-identical paths through the thin-aware
      `--status`/`--check` change.
- [ ] A fixture consumer with a pre-existing `.claude/settings.json`
      carrying unrelated keys keeps every one of them after `--thin`,
      and after `--revert-thin` differs from its original only by the
      `enabledPlugins` disable marker.
- [ ] `--thin` refuses to run without a `clear` verdict, refuses when
      the verdict was produced against a different HEAD, and **refuses
      when a file changed after the resweep without `HEAD` moving** —
      the last case proven by editing a file post-verdict and asserting
      an unchanged tree afterward.
- [ ] A drifted pack file makes `--thin` **abort** without `--force`,
      leaving the tree byte-identical and writing no settings entry, no
      pin, and no mode flip — verified by comparing the full tree before
      and after the refused run. Preserve-and-continue, which is
      `--remove`'s behavior, fails this criterion.
- [ ] A tracked pack-like file absent from the receipt is caught by the
      pre-conversion structural audit and blocks, rather than surviving
      conversion while the receipt comparison still passes.
- [ ] `--revert-thin` on an **unforced** converted disposable checkout
      restores the fat payload byte-identically, leaves only the
      `enabledPlugins` disable marker behind, verified by a tree
      comparison against the pre-conversion state, **and flips that
      consumer's registry entry back to `mode: fat`** — asserted by
      reading `docs/fleet/consumers.json` after the command, not by
      inspecting the code.
- [ ] A `--force` conversion that deleted a drifted file reverts that
      path to **source** bytes, with the path named in the receipt's
      `forced` list and reported as restored-to-source. The drifted bytes
      no longer exist anywhere, so byte-identical restoration is scoped
      to the unforced case rather than promised unconditionally.
- [ ] Failure injection on both roots, in **both directions**: a
      read-only pack checkout and, separately, a read-only target each
      make `--thin` *and* `--revert-thin` refuse before any write, exit
      nonzero, and leave **both** the consumer tree and the registry
      byte-identical. `--thin` flips the registry too, so an unwritable
      pack checkout discovered after 166 consumer deletions is the
      failure this criterion exists to prevent.
- [ ] `--dry-run` output is compared against the executed run across all
      six change categories — deletes, retires, managed-block edits, the
      three receipt rewrites, the settings additions, and the registry
      flip. An unchanged tree alone is satisfied by an empty printout.
- [ ] `retainVendoredFor` retention is exercised by a synthetic fixture
      consumer declaring `codex`; the task records explicitly that no
      live consumer exercises it.
- [ ] `make release-prep` passes if this task changed the payload or
      `docs/fleet/consumers.json` (contract C-G — a `mode` flip moves
      the fleet-manifest digest pinned into the candidate ledger);
      `make check` otherwise. If this task touched `templates/**` or
      `docs/SD_AI_COMMAND_PACK.md`, `manifest.json` is bumped with a
      matching top `CHANGELOG.md` heading — `make check` does not run
      the release payload gate (`.github/workflows/tests.yml:639`), so
      its passing is not evidence for this item.
