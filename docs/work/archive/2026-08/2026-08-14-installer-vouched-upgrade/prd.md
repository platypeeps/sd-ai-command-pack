---
title: Installer upgrades vouched pack files without --force
status: done
created: 2026-08-14
branch: fix/installer-vouched-upgrade
---
# Installer upgrades vouched pack files without --force

## Goal

Make a normal tracked install upgrade a pack-owned file whose content the
installer itself last wrote, instead of reporting it as a conflict that only
`--force` can clear.

## Problem

`installer/fileops.py::install_file` classifies an `install: always` target as
`CONFLICT` whenever the destination exists and its bytes differ from the new
template. It never consults `.sd-ai-command-pack/provenance.json`, which
records the sha256 of exactly what the previous release installed at that
path. Every pack file whose template changed between two releases therefore
conflicts on upgrade, even in a tree no human has touched.

Reproduced in a pristine target that only the installer ever wrote:

```
$ python3 install.py --platform claude <target>     # 0.71.1, clean install
$ python3 install.py --platform claude <target>     # 0.71.4
conflict    scripts/sd-ai-command-pack-review-preflight.mjs
conflict    docs/SD_AI_COMMAND_PACK.md
conflict    .agents/skills/sd-help/references/command-catalog.md
conflict    .claude/skills/sd-help/references/command-catalog.md
Re-run with --force to overwrite these files.
```

Exactly four templates changed between `v0.71.2` and `v0.71.4`, and the
conflict set is exactly the installed copies of those templates. Provenance
vouches all four:

```
scripts/sd-ai-command-pack-review-preflight.mjs
  recorded=sha256:fbb7b31b9d9ad6bdad3aa04f94cd25e6ad40ae2be33a1406143e9f8220f51309
  on-disk =sha256:fbb7b31b9d9ad6bdad3aa04f94cd25e6ad40ae2be33a1406143e9f8220f51309
  vouched =True
```

The installer holds the proof that nobody edited these files and refuses
anyway.

## Impact

- Every consumer upgrade needs `--force`, so `--force` becomes the routine
  invocation rather than the exception.
- `--force` cannot distinguish a pack-owned file from a consumer-edited one,
  so the habit it creates silently discards genuine local edits — the exact
  outcome the conflict gate exists to prevent.
- The reported reason is wrong. All 8 consumers in campaign
  `refresh-0.71.4-20260813T212139Z` hit the same four-file conflict set, and
  each was investigated as local drift before being forced. That
  investigation cost was spent on a false signal.
- README (`conflicting files`, `--force to overwrite`) and
  `docs/SD_AI_COMMAND_PACK.md` describe `--force` as the way to displace
  *customized* files. Behaviour and documentation disagree.

The machine-scope installer already gets this right: `installer/machinescope.py`
classifies a receipt-recorded target whose bytes match the *old* receipt entry
as `owned-stale` and updates it without `--force`. The repository-scope
installer has the same evidence available and no equivalent classification.

## Requirements

- A source-backed `install: always` target whose on-disk bytes match the digest
  recorded for that target in the consumer's `provenance.json` must install the
  new template without `--force`, and report a status distinct from a forced
  overwrite.
- A target whose on-disk bytes match neither the new template nor the recorded
  provenance digest must still be `CONFLICT` without `--force`. Real drift is
  unaffected.
- A target absent from provenance must still be `CONFLICT`. Byte identity to
  some past release is not proof when the record is missing.
- Unreadable, symlinked, or malformed provenance must fall back to the current
  conflict behaviour, never to a silent overwrite.
- Provenance left behind by an interrupted run — files written, provenance not
  yet rewritten — must conflict, not upgrade. Absent evidence fails closed.
- `PRESERVED` / `REFRESHED` targets (`if-not-exists`, `FORCE_PRESERVED_TARGETS`)
  keep their present handling; this change must not touch that path.
- Symlink and non-file destination handling is unchanged: those statuses are
  reached before any content comparison and are never displaced.
- The plan-before-apply preflight and the apply pass must agree, so the
  preflight cannot report a status the apply pass would not produce.
- No backup is written for a vouched upgrade. `--backup` documents displaced
  *user* content; a vouched file is the pack's own previous release, already
  recoverable from the pack.

## Acceptance Criteria

- [x] A vouched changed target reports the new status and is rewritten without
      `--force`.
- [x] A locally edited target still reports `conflict` and is left untouched
      without `--force`.
- [x] A changed target with no provenance entry still reports `conflict`.
- [x] A changed target whose provenance is missing, symlinked, or malformed
      still reports `conflict`.
- [x] `--force` behaviour, `--backup` behaviour, and every `preserved` target
      are byte-for-byte unchanged.
- [x] The 0.71.1 -> 0.71.4 repro upgrades all four files with no conflict and
      no `--force`, and the install audit passes afterwards.
- [x] The full `unittest discover -s tests` suite passes under the toolchain
      interpreter, including the updated
      `test_audit_clean_source_changed_target_requires_refresh`, which today
      asserts the defective behaviour.
- [x] `.trellis/spec/backend/manifest-and-filesystem.md` and the installer
      documentation describe the new classification.
