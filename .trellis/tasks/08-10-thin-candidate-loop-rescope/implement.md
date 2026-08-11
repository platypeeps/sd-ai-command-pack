# Implement — make release-prep reach a changed candidate validator

Narrowed scope: the mechanism only. The thin-shape rescope is
`08-11-thin-candidate-loop-shape`.

## Step 0 — before editing

- [x] `trellis-before-dev`: `.trellis/spec/backend/index.md`, the
      manifest-and-filesystem spec, and the tooling spec index.
- [!] **Not done.** This step was skipped — implementation started without
      running the baseline, and once the ledger was rewritten at schema 3 the
      original observation was no longer reproducible in place.

      What replaced it is derived from measurement rather than memory, and is
      stronger. Gate 2 appended one comment to the validator on a converged
      tree and `--check-ledger` reported **exactly one** changed field,
      `validatorDigest`; `packVersion`, `payloadDigest`, and
      `fleetManifestDigest` were all byte-identical. Schema 2's ledger had no
      `validatorDigest` field at all, so on that same edit its three fields
      would all have matched and `_candidate_refresh_required` would have found
      the ledger current — the skip, by construction. The "before" behavior is
      therefore established from the "after" measurement, not asserted from
      recollection.

      The reusable lesson: a baseline that a later step destroys must be
      captured before the first edit, not scheduled and skipped.

## Step 1 — the digest primitive

Edit **`templates/scripts/sd_ai_command_pack_fleet_lib.py`**, the authoritative
source. Not `scripts/sd_ai_command_pack_fleet_lib.py`, which is a `make sync`
mirror (`CONTRIBUTING.md:143`); editing the mirror is how this mechanism gets
erased before it is validated.

- [x] Add `CANDIDATE_VALIDATOR_SOURCES` naming **only**
      `scripts/sd-ai-command-pack-fleet-candidate-check.py`. Design D1 records
      why fleet_lib is deliberately absent — do not "fix" that by adding it.
- [x] Add `candidate_validator_digest(source_loader)` and
      `filesystem_candidate_validator_digest(root)` as two distinct names with
      distinct types (D1). Compose as `fleet_lib.py:736-741` composes, **minus
      the executable marker** at line 739 — the measured reason is in D1.
- [x] Bump `CANDIDATE_LEDGER_SCHEMA_VERSION` 2 → 3.
- [x] Add the required keyword-only `expected_validator_digest` to
      `validate_candidate_ledger`, appending an error in the same shape as the
      three existing field comparisons.

**Unplanned fix, found by the fixtures.** `filesystem_candidate_validator_digest`
originally trusted the caller's `root` in its containment check while resolving
the source path. Production callers pass `manifest_path.resolve().parent`, so
this never showed there — but every macOS temporary tree is handed out under
`/var`, a symlink to `/private/var`, and the mismatch rejected all of them as
escapes. The function now resolves `root` itself, as `filesystem_payload_digest`
already did. `test_digest_resolves_a_symlinked_root` pins it.

## Step 2 — producers and call sites

- [x] `scripts/sd-ai-command-pack-fleet-candidate-check.py` (no template; edited
      in place): extend `current_evidence` (line 323) to return the validator
      digest as a fifth value, so `check_ledger` (line 386) and
      `ledger_content` (line 337) read one expression (D3). Write
      `validatorDigest` next to `payloadDigest` (line 350).
- [x] `.github/scripts/release_identity.py`: add a `loader_at_commit`
      counterpart beside `payload_digest_at_commit`, then update **both** call
      sites — `:333` takes the working-tree digest, **`:283`
      (`verify_candidate_ledger_at_commit`) takes the digest at `commit_sha`**.
      Pairing `:283` with the working tree is the defect D1a exists to prevent.
- [x] Re-enumerate call sites from the filesystem before declaring this done —
      `grep -rn 'validate_candidate_ledger(' --include='*.py' .` — rather than
      trusting the three found during planning. The keyword argument is
      required, so a missed site is a `TypeError` under coverage.
      Result: the three planned production sites, plus one test. Enumerating
      `current_evidence` the same way found a **fourth** consumer the planning
      pass missed — `tests/test_pack_drift.py:91` unpacks its tuple.
- [x] Do **not** hand-edit `plugins/sd/bin/`,
      `plugins/sd/machine-payload/scripts/`, or the root `scripts/` mirror.
      They are regenerated in Step 4; `make generate` complaining about them
      means Step 4's order was skipped.

## Step 3 — tests

- [x] New `tests/test_fleet_candidate_validator_digest.py` per design D5:
      stability, path-qualification, the six error-matrix rows, the
      historical-vs-working-tree test that fails if `:283` is fed the working
      tree, and fail-closed on a source missing at a commit. 13 tests.
- [x] Update the fixtures fail-closed loading breaks (C-7):
      `tests/test_fleet_candidate.py:388` and
      `tests/test_release_identity.py:87,117` build trees containing no
      validator source. Materialize it; do not weaken the loader to tolerate
      its absence. `tests/test_release_ledger.py` and `tests/test_pack_drift.py`
      needed the same treatment; the loader was not weakened.
- [~] **Deviation.** `tests/test_release_prep.py` mocks the surface-check report
      wholesale, so at that layer "the validator digest differs" is not
      representable — it is just `stale=True`, and both branches of the skip
      already have a test there
      (`test_clean_candidate_runs_ordered_prep_and_skips_fleet`,
      `test_stale_candidate_runs_fleet_once_then_requires_clean_closure`).
      A third mocked test would be duplicate coverage wearing a new name. The
      claim that only needed proving — *a validator-only edit makes the ledger
      stale* — is proven where it is real, in
      `test_ledger_detects_payload_and_fleet_drift`: the payload source is
      restored, the ledger reads clean, and then editing only the validator
      produces a `validatorDigest` error and no `payloadDigest` error.
- [x] Update `tests/test_fleet_candidate.py:541` for the new keyword argument.

**Unplanned, found by `make generate`.** `CANDIDATE_VALIDATOR_SOURCES` is a
repository-root `scripts/` literal inside a script that ships into the plugin's
flat `bin/`, which `check_executable_residue` forbids by default. It is layout
data, not sibling resolution — the digest takes a caller-supplied loader
precisely so those names can be read from a working tree *or* a commit's blobs —
so it takes a justified `BIN_LITERAL_ALLOWLIST` entry, recorded in both
`installer/references.py` and `tests/test_script_sibling_resolution.py` because
an equality test holds the two copies together. The design comment was reworded
to stop naming the fleet_lib mirror path in prose: allowlisting a literal that
appears only in a comment would dilute the entry's meaning.

**Validation gate 1:**

```bash
.venv/bin/python -m unittest tests.test_fleet_candidate_validator_digest \
  tests.test_fleet_candidate tests.test_release_identity tests.test_release_prep
PYTHONDONTWRITEBYTECODE=1 <mutation run over the digest comparison>
```

The mutation run is not optional: a comparison that passes when digests differ
reproduces the exact defect this task exists to fix.

**Validation gate 2 — acceptance criterion 1, end to end:**

```bash
# ledger current from Step 0; now change only the validator's source
<edit a comment in scripts/sd-ai-command-pack-fleet-candidate-check.py>
make release-prep
```

Expected: the validator **runs**. Seeing the skip message here means the
mechanism did not land. Revert the comment edit and verify the revert.

**Validation gate 3 — the skip survives (criterion 2):** run
`make release-prep` twice on an unchanged clean tree; the second reports the
ledger current and does not rerun fleet validation.

## Step 4 — close

- [x] Regenerate in the order this repository requires. **The order written
      here during planning was wrong**: `make sync` mirrors surfaces that
      `make generate` rewrites, so sync-then-generate leaves `mirror.stale`,
      and any regeneration after the candidate check leaves `payloadDigest`
      stale again. The three steps are mutually recursive and there is no
      hand order that converges. `prepare-release.py` is the sequencer that
      does — generate, partition, plugin, sync, KB, surface-check, and only
      then the candidate check, re-checking closure afterward. Run it rather
      than reproducing it by hand.
- [x] A shipped-payload change requires a `manifest.json` version bump against
      `origin/main`; release-prep fails closed before it ever reaches the
      candidate step. Bumped 0.68.0 → 0.69.0 with a CHANGELOG entry.
- [x] Confirm `make sync` propagated the template edit into the root mirror and
      the two plugin copies, rather than reverting it — the C-5 failure mode,
      checked rather than assumed.
- [x] `make check` exits 0. Exit 0; preflight 0 failures, 3 dispositioned warnings.
- [x] Tick every `prd.md` acceptance criterion against measured evidence before
      `task.py archive`. The pre-archive gate requires checked boxes; a
      blockquote explaining an unchecked box does not satisfy it.

## Rollback

`git revert` of the commit. The ledger self-migrates in both directions (design
D4), so no rollback-only code and no cleanup step exists.

## Out of scope

- The thin-shape rescope, in any part — `08-11-thin-candidate-loop-shape`.
- Any consumer repository mutation; children 3–5, blocked on explicit
  per-cohort user authorization.
