# Preserve file modes and exec bits in installer atomic writes

## Goal

Fix a verified HIGH defect in `install.py` (`atomic_write_bytes`,
lines 580-603): `tempfile.NamedTemporaryFile` creates the temp file
with mode 0600 and `os.replace` preserves it; there is no
`chmod`/`copymode` anywhere in install.py. Every installed file lands
as `-rw-------`, including `scripts/sd-ai-command-pack-record-session.py`
(mode 100755 in the pack — its shebang and exec bit signal intended
direct execution). Consequences: `--force` refreshes silently downgrade
pre-existing 0644/0755 targets to 0600 on every run; direct execution
(`./scripts/...`) fails with Permission denied after install; shared
checkouts / CI containers reading the repo as a different UID get
EACCES on all pack files.

## Requirements

- R1: After writing the temp file, apply a sane default mode
  (`0o666 & ~umask`) before `os.replace`, so installed files match
  normal file-creation semantics.
- R2: Preserve the pack source's executable bits: a template tracked
  as 100755 installs as executable (respecting umask).
- R3: Behavior is consistent across all write paths that funnel
  through `atomic_write_bytes`/`atomic_write_text` (plain files,
  managed blocks, receipt, provenance, gitignore).
- R4: Tests cover: fresh install produces group/other-readable files;
  `--force` refresh over an existing 0644 file does not downgrade it;
  the executable script installs with exec bits.

## Acceptance Criteria

- [ ] `stat` on freshly installed files shows umask-derived modes, not
  0600; `sd-ai-command-pack-record-session.py` is executable.
- [ ] `--force` refresh preserves sane modes on existing targets.
- [ ] Full battery green: unittest suite, 100% coverage on install.py
  (new branches covered), full-check, shellcheck.

## Notes

- Origin: 2026-07-06 deep review (Python M1, verified end-to-end by a
  fresh install). Docs mostly invoke scripts via `bash`/`python3`,
  which masked the exec-bit loss; the 0600 read restriction is the
  sharper consumer-facing issue.
