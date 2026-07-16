# Installer write-safety: atomic script writes + symlink guards

## Problem

Audit findings A-010 and A-002 (both P2, correctness), 2026-07-15 @ f6f3932:

- A-010: sibling scripts rewrite pre-existing files with non-atomic
  `write_text`: `scripts/sd-ai-command-pack-record-session.py:200` rewrites
  the entire journal; `scripts/sd-ai-command-pack-update-spec-kb.py:486`
  rewrites the user's `.gitignore`/`.git/info/exclude` (also `:1157`,
  `:1160`); `scripts/sd-ai-command-pack-review-learnings.py:773`. A crash or
  ENOSPC mid-write truncates session history or the user's `.gitignore` —
  the installer core avoids exactly this via `atomic_write_bytes`
  (`installer/fileops.py:88`).
- A-002: the managed-block/gitignore/receipt writers
  (`installer/fileops.py:390`, `:406`; `installer/provenance.py:163`) have no
  `is_symlink()` guard; `_require_file_destination` (fileops.py:196) follows
  symlinks, so `os.replace` silently converts a symlinked `.gitignore` or
  `.github/copilot-instructions.md` into a regular file, orphaning the link
  target. Diverges from `install_file` (:230, symlink-conflict) and
  `remove_text_block_file` (:533, preserves).

## Goal

No pack write can truncate pre-existing user data on failure, and no pack
writer silently replaces a symlink with a regular file.

## Requirements

- Route the sibling-script rewrites through a temp-file + `os.replace`
  atomic helper (shared or per-script, matching installer semantics).
- Add `is_symlink()` conflict/preserve handling to the three text writers,
  consistent with `install_file`'s existing `symlink-conflict` behavior.
- Behavior change must be covered by tests (crash-safety via forced failure
  or write interposition; symlink targets in temp repos).

## Acceptance Criteria

- [x] Journal, KB-gitignore, and learnings writes are atomic (temp+replace).
- [x] Symlinked gitignore/copilot-instructions targets produce a conflict or
      are preserved — never silently replaced-through.
- [x] New tests cover both behaviors; coverage floors hold.

## Implementation Notes

- Added local atomic text writers to the shipped recorder, review-learnings,
  and update-spec KB helpers, mirrored in `templates/scripts/`.
- Added symlink-conflict handling for generated installer text files, including
  `.gitignore`, Copilot guidance, pack manifest, provenance, and installed
  targets receipts.
- Updated the update-spec KB helper so a symlinked ignore file reports a
  partial refresh conflict rather than writing through or replacing the link.
- Captured the generated-text write contract in
  `.trellis/spec/backend/manifest-and-filesystem.md`.
