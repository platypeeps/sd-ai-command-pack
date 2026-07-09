# Constrain --remove to manifest-recognized targets

## Goal

Close a data-loss defect: `install.py --remove` can delete arbitrary
in-repo files — including `.git/config` — when the consumer-resident
`provenance.json` / `installed-targets.txt` receipt names them. Removal
must never trust an unbounded path set that originates from a file living
inside the target working tree.

## Problem

`may_remove_pack_file` (`installer/removal.py:59-64`) authorizes deletion
whenever the on-disk file's SHA-256 matches the hash recorded in the
consumer's `provenance.json`. The candidate set
(`installed_target_candidates`) and the hash map both come from files
inside the target repo (`.sd-ai-command-pack/installed-targets.txt` and
`provenance.json`), which are not integrity-protected — the installer
writes them, but nothing prevents a bad merge, an errant edit, or a
malicious PR from adding entries.

Reproduced during the 2026-07-09 deep review (use a throwaway repo, never
a real one): adding `".git/config": "sha256:<real hash>"` and
`"USER_DATA.txt": "sha256:<real hash>"` to a target's `provenance.json`,
then running `install.py <repo> --remove`, prints `removed .git/config`
and `removed USER_DATA.txt` and deletes both. `prune_empty_parent_dirs`
then walks up removing now-empty directories.

The existing path-traversal guards do not help: these paths are
legitimately *inside* the repo root, so `removal_target_destination`'s
escape check passes. The vulnerability is trust, not traversal.

## Requirements

- R1: A candidate is eligible for removal only if its target path is a
  recognized pack artifact for the current manifest — i.e. it appears in
  the manifest's target set (or is a pack-owned generated receipt such as
  `installed-targets.txt` / `provenance.json` / the local-only marker).
  A hash-matched receipt entry that is not a recognized target is ignored
  and reported, never deleted.
- R2: Nothing under `.git/` is ever a removal candidate, regardless of
  receipt contents, manifest state, or `--force`.
- R3: `--force` removal keeps its current power over recognized pack
  targets but gains no ability to delete unrecognized paths; force does
  not bypass R1/R2.
- R4: When a receipt names a path that R1/R2 reject, the run surfaces it
  as a skipped/ignored entry (visible in output and in `--dry-run`) so a
  corrupted receipt is diagnosable rather than silently honored.

## Acceptance Criteria

- [ ] A regression test adds `".git/config"` and an arbitrary tracked
      non-pack file to a temp repo's `provenance.json`, runs `--remove`,
      and asserts both files still exist and the run reported them as
      ignored (mirror the reproduction above).
- [ ] A test asserts a hash-matched receipt entry whose target is absent
      from the manifest is not removed.
- [ ] Existing removal tests (`tests/test_remove.py`) still pass;
      legitimate pack-target removal and drifted-file preservation are
      unchanged.
- [ ] `--dry-run --remove` lists the same ignored entries and mutates
      nothing.
- [ ] 100% line+branch coverage on `installer/removal.py` maintained.

## Non-goals

- Cryptographically signing receipts. The fix is scoping the candidate
  set, not authenticating the receipt file.
- Changing the install-time provenance format.
