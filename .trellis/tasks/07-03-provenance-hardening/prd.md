# Provenance hardening from consumer-PR review round

## Goal

Copilot review of the six 0.5.10 refresh PRs surfaced audit gaps in the
vendored copies. Close them upstream and ship as 0.5.11, then refresh the
six open consumer PRs.

## Requirements

- R1: Any symlink at a vouched path fails the audit, even when it points at
  content whose hash matches (`is_file()` follows symlinks, so symlink swaps
  previously passed verification and could redirect outside the repo).
- R2: A vouched target that is missing while not gitignored fails, even
  when the receipt no longer lists it — provenance is the tamper-evidence
  of last resort for the remove-from-both bypass. Gitignored-absent vouched
  targets skip, consistent with the structural policy.
- R3: The provenance file itself must be a regular file, judged via
  `lstat` semantics: a symlinked, dangling-symlinked, or otherwise
  non-regular provenance fails, and an `lstat` error (e.g. permission
  denied on the containing directory) fails rather than silently skipping
  verification. Genuine absence keeps pre-0.5.10 behavior.
- R4: The installer's provenance reader ignores a symlinked provenance file
  during merge and atomically replaces it with a regular file on write.
- R5: `read_text` calls in the audit and installer provenance paths carry
  an explicit `errors=` policy (consumer defect-pattern guards flag the
  vendored lines otherwise).
- R6: README, usage guide, and the manifest-and-filesystem spec state the
  strengthened contract; version bumped to 0.5.11.

## Acceptance Criteria

- [x] Symlink-to-valid-copy at a vouched path fails with "not a regular
      file"; removal from disk and receipt fails with "vouched target is
      missing"; symlinked and dangling provenance fail with "must be a
      regular file"; un-lstat-able provenance fails with "cannot be
      inspected".
- [x] Installer rebuilds a regular provenance file over a symlink and
      ignores symlink-fed entries in the merge.
- [x] Full suite green at 100% install.py coverage; full-check clean; twins
      in sync.
- [ ] The six consumer refresh PRs are updated to 0.5.11 and their review
      threads answered against the shipped fix (post-merge step).
