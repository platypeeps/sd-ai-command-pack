# Implementation plan

## 1. Provenance lookup helper

- [ ] In `installer/fileops.py`, add a module-level helper that answers one
      question: do these destination bytes match the digest provenance recorded
      for this target? Compare `"sha256:" + sha256(current).hexdigest()` against
      the mapping value, exactly as `may_remove_pack_file` does. Absent key,
      empty mapping, or `None` mapping answers False.
- [ ] Keep it pure: it takes the already-read `current` bytes and the mapping,
      and performs no filesystem access of its own.

## 2. `install_file` classification

- [ ] Add keyword-only `provenance_files: Mapping[str, str] | None = None`.
- [ ] In the `destination.exists()` branch, after the `UNCHANGED` return and
      after the `IF_NOT_EXISTS` / `FORCE_PRESERVED_TARGETS` branch, before
      `if not force:`, return `InstallStatus.UPDATED` when the helper answers
      True — writing `new_content` with the source executable bit, honouring
      `dry_run`, and taking no backup.
- [ ] Leave the `force` path untouched below it. A forced run over a vouched
      file now takes the `UPDATED` path before reaching it, which is correct:
      nothing was displaced, so nothing needs backing up.

## 3. Thread the mapping

- [ ] In `install.py::_install_payload`, read the mapping once with
      `read_existing_provenance_files(target)` and pass it to every
      `install_file` call.
- [ ] Confirm all five `_install_payload` call sites now carry it (normal
      preflight + apply, revert-thin preflight + apply, conversion).
- [ ] Do not touch `install_managed_block` or the generated-file writers.

## 4. Tests — `tests/test_install_core.py`

Extend the direct-engine coverage next to
`test_install_file_unit_covers_core_status_branches`:

- [ ] Vouched stale content + changed template, no `--force` -> `updated`,
      destination holds the new template, no `.bak` written.
- [ ] Locally edited content + changed template, provenance recording the
      *old pack* digest -> `conflict`, destination untouched.
- [ ] Changed template with the target absent from the mapping -> `conflict`.
- [ ] Empty mapping (stands for missing/symlinked/malformed provenance, whose
      reader already normalises to `{}`) -> `conflict`.
- [ ] `dry_run=True` over a vouched file reports `updated` and writes nothing.
- [ ] An `if-not-exists` target with a vouched-stale digest still reports
      `preserved`, proving the new branch sits after that one.

## 5. Tests — end-to-end upgrade

- [ ] **Update the existing test that encodes the defect.**
      `tests/test_install_inspection.py::test_audit_clean_source_changed_target_requires_refresh`
      (line 222) builds exactly the vouched-stale shape — it rewrites a target
      and rewrites that target's provenance digest to match — and then asserts
      `payload["counts"]["conflict"] > 0`. Under this change that target
      classifies `updated`, so the assertion must become
      `counts["updated"] > 0`. `state` stays `refresh-required` and the exit
      code stays `REFRESH_REQUIRED_EXIT`, because `UPDATED` is already in
      `_CHANGE_INSTALL_STATUSES`; assert that both are unchanged rather than
      deleting them. Failing to update this test is the expected first red
      run, not a sign the change is wrong.
- [ ] Add an end-to-end upgrade test in the same file, reusing its
      `install_current_fixture` + `run_install_inproc` harness: install, rewrite
      one vouched target and its provenance digest, then run a real install
      with no `--force` and assert exit `0`, an `updated` line for that target,
      the destination back to template bytes, no `.bak` sibling, and
      `--check --audit` reporting `audit: passed` afterwards. A unit test alone
      would not have caught the fleet regression, which only appears when a
      prior release's bytes meet a changed template.
- [ ] Confirm `test_vouched_content_drift_is_invalid_with_or_without_audit`
      (line 246) still passes untouched: it leaves provenance recording the old
      digest, which is drift, not a vouched upgrade.

## 6. Spec and docs

- [ ] `.trellis/spec/backend/manifest-and-filesystem.md`, "Plan-Before-Apply
      And Concurrency": document the vouched-upgrade classification and its
      relationship to machine-scope `owned-stale`.
- [ ] `README.md`: correct the conflict paragraph so `--force` is described as
      displacing *customized* files, not as the way to take a release.
- [ ] `templates/docs/SD_AI_COMMAND_PACK.md`: same correction in the installed
      documentation. Refresh the repo's own `docs/SD_AI_COMMAND_PACK.md` by
      running the installer against this checkout rather than editing it.
- [ ] `CHANGELOG.md`: entry for the behaviour change.

## Validation

Run every Python command through the toolchain wrapper. A bare `python3` here
fails at import with `ModuleNotFoundError: No module named 'yaml'`, because
`tests/install_test_support.py` needs the pack's selected interpreter.

- [ ] `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest discover -s tests -p 'test_install_core.py'`
- [ ] `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest discover -s tests -p 'test_install_inspection.py'`
      (baseline before the change: `Ran 18 tests ... OK`)
- [ ] `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest discover -s tests` (full suite)
- [ ] Repro replay, the decisive check: install `v0.71.1` into a scratch
      target, then install this branch's payload without `--force`. Expect
      `updated` for the four previously conflicting paths, exit `0`, and
      `install.py --check --audit` reporting `audit: passed`. Any `conflict`
      line in that output is failure.
- [ ] `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- scripts/sd-ai-command-pack-check.py --json`
- [ ] `node scripts/sd-ai-command-pack-review-preflight.mjs`

## Rollback

Single commit touching `installer/fileops.py`, `install.py`, tests, spec, and
docs. Revert restores the current refuse-without-force behaviour; no receipt,
provenance, or on-disk format changes, so a consumer installed by either
version is readable by the other.
