# Implementation plan — retire the pre-0.6.16 vendored Trellis compatibility layer

Edit `templates/**` only; run the generators at step 7.

Baselines recorded before any edit:

- `.venv/bin/python -m unittest tests.test_record_session` → `Ran 13 tests … OK`
- `.venv/bin/python -m unittest tests.test_status` → `Ran 131 tests … OK`

## 1. Compatibility spec (R1)

- [ ] `.trellis/spec/tooling/vendored-trellis-compatibility.md`
  - [ ] Replace "Version-spread reality" with a "Supported floor" section
        naming the exact build `0.6.16-sd.7`, the rule that a checkout below it
        is upgraded rather than accommodated, and the semver caveat (the
        prerelease segment sorts below `0.6.16`, so the floor is an identity
        comparison, never a range).
  - [ ] Re-pin the signature table to the floor; add the six runtime facts
        listed in `design.md` (§R1).
  - [ ] Rewrite "Upgrade procedure" for fork distribution; state the npm
        downgrade hazard.
  - [ ] Update "Journal sections" to record *why* Testing/Next Steps patching
        survives (unconditional `bullet_prefix`), not that it is legacy.
  - [ ] Drop the wrong/correct entries that encode the removed fallbacks; add
        one for the commit-cell escaping.

## 2. Status collector (R2, R6)

- [ ] `templates/scripts/sd-ai-command-pack-status.py`
  - [ ] `collect_trellis`: collapse the three-way `current --json` branch to a
        single parse; absent/unparseable → no active task.
  - [ ] Carry `stale` (and `source`) from the payload into the collected record.
  - [ ] `render_fleet`: add the Trellis version to each row.
  - [ ] Surface `stale` in the human status output.

## 3. Record-session wrapper (R3)

- [ ] `templates/scripts/sd-ai-command-pack-record-session.py`
  - [ ] Delete the commit-row rewrite from `patch_last_session`: the `row_re`
        construction, the `_row_replacement` callable, and the per-hash loop.
  - [ ] Replace it with a presence assertion — every requested OID appears in
        the session block — preserving the "runtime dropped a commit" failure
        mode without the rendering.
  - [ ] Keep `JOURNAL_COMMIT_CELL_RE` (used by `recorded_commit_hashes`).
  - [ ] Keep the `commit_subject()` pre-flight probe and its exit-2 contract;
        keep the `PLACEHOLDERS` end-gate; keep `--branch` pass-through.
  - [ ] Narrow `patch_last_session`'s `subjects: dict[str, str]` parameter to
        the hash list the presence assertion needs; the resolved subjects stop
        crossing the boundary.
  - [ ] Refresh the module docstring and every `<=0.6.7` / "older Trellis"
        comment to describe the floor.

## 4. Base-branch guidance (R4)

- [ ] `templates/scripts/sd-ai-command-pack-review-preflight.mjs`: drop the
      "do not use `task.py create --base-branch`" clause from the
      `task_base_branch_invalid` remediation.
- [ ] `templates/.agents/skills/sd-fleet-refresh/SKILL.md`: replace the
      post-create `set-base-branch` step + rationale with
      `create --base-branch <default-branch>`.

## 5. Tests (R5)

- [ ] `tests/test_status.py`: re-point the `0.6.7` fixture to the floor; delete
      `test_active_task_falls_back_when_current_rejects_json_flag`.
- [ ] `tests/test_record_session.py`: delete the placeholder seeding and the
      prefilled-variant conditional swap; keep the end assertions.
- [ ] Add: a commit subject containing `\`, `|`, and internal whitespace runs
      renders correctly in the journal (the R3 regression fix).
- [ ] Add: `current --json` failing leaves the active task absent rather than
      falling back.

## 6. Task records (R7)

- [ ] Re-scope `08-17-fleet-trellis-version-drift`'s PRD: drift half resolved
      (record the 2026-08-20 all-nine measurement), visibility half delivered
      here.
- [ ] Add a Trigger Status entry to `07-09-trellis-version-compatibility`'s PRD:
      trigger fully fired, npm `latest` 0.6.15 below the floor, fork
      unpublished, `trellis update` downgrade hazard. Leave parked.
- [ ] While there, correct that PRD's stale citation
      `tests/install_test_support.py:457` — the asserted string is at `:641`.

## 7. Propagate and verify

- [ ] `make generate` then `make sync`.
- [ ] `cmp` all four copies of both changed scripts — byte-identical.
- [ ] `git diff --stat` shows no hand-edit outside `templates/`, `tests/`,
      `.trellis/spec/`, `.trellis/tasks/`.

## 7b. Release payload obligations

This task edits `templates/scripts/*.py`, `templates/scripts/*.mjs`, and
`templates/.agents/skills/sd-fleet-refresh/SKILL.md` — all shipped payload — so
CONTRIBUTING's payload rules apply and the `Release payload gate` CI job
(`.github/workflows/tests.yml:641`) runs `run_pack_source_drift_gates` against
the PR base. Skipping these fails `CI Result`, not just a local check.

- [ ] Bump `manifest.json` `version` (patch: behavior-compatible fix plus
      documentation).
- [ ] Add the matching top `CHANGELOG.md` heading describing the retirement, the
      commit-cell escaping fix, and the base-branch correction.
- [ ] `make release-prep` — regenerates surfaces, self-syncs, and refreshes
      `docs/fleet/candidate-validation.json` for the exact payload, then runs
      `make check`. Run this **after** all payload edits, never mid-cycle.

## 8. Gates

Run in this order; each must pass before the next.

- [ ] `.venv/bin/python -m unittest tests.test_record_session tests.test_status`
      — targeted, fastest signal.
- [ ] `make test` — must report **zero** skips (`Makefile` fails the gate on
      `skipped=[1-9]`).
- [ ] `make lint`
- [ ] `make audit`
- [ ] `make full-check`
- [ ] `make release-prep` (step 7b) — supersedes the above by ending in
      `make check`; run it last so no later edit invalidates its ledger.

## 9. Verification checks (named before the work)

Each names the result that means failure.

| # | Check | Failure |
|---|---|---|
| V1 | `make test` | any failure, or any skip |
| V2 | `git grep -n "0\.6\.7\|0\.6\.14" -- templates/scripts tests scripts` | any hit describing a *supported* runtime (historical prose in tasks/audit is exempt) |
| V3 | `git grep -n "row_re\|_row_replacement" templates/scripts` | any hit — the R3 removal is incomplete |
| V4 | New escaping test with subject `fix: a \| b and C:\tmp` | cell not escaped as `add_session.py` escapes it |
| V5 | `cmp` × 4 copies × 2 scripts after `make generate && make sync` | any difference |
| V6 | `python3 ./.trellis/scripts/sd-ai-command-pack-status.py fleet` human output | no Trellis version in a row |
| V7 | `git grep -n "unrecognized argument" -- templates/` | any surviving `--base-branch` prohibition |
| V8 | `Release payload gate` locally, via `make release-prep` | manifest/changelog/ledger not consistent with the payload |

V2 and V3 are the blast-radius checks: they enumerate from the tree rather than
re-reading the files I edited, so they catch a copy I did not know about.

## Rollback

`git revert` the merge commit. No migrations, no persistent state, no
consumer-side writes.
