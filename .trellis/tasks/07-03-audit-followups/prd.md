# Install audit follow-ups: receipt-policy tolerance and separator normalization

## Goal

Two audit refinements from the 0.5.9 fleet rollout. (1) rwbp-website's repo-local review guard enforces the OPPOSITE receipt policy (installed-targets must NOT list gitignored .claude/ files), and the pack audit errors on present-but-unlisted pack-like files, forcing that repo to run with SD_AI_COMMAND_PACK_INSTALL_AUDIT=0. (2) Copilot on mezmo_benchmark PR #313 (reply on comment 3522276141 promises this fix): normalize Windows-style separators in receipt targets so hand-edited receipts degrade gracefully on POSIX.

## Requirements

- R1: A pack-like file that exists but is not listed in the receipt is a
  warning (not a failure) when the file is gitignored in the checkout, so
  repos whose receipt policy excludes local-only adapters pass the audit.
  Tracked-but-unlisted pack-like files remain failures (real receipt drift).
- R2: Receipt target lines normalize Windows-style separators to `/` at load
  time (after the existing unsafe-path rejection), so `Path()`,
  `git check-ignore`, and provenance lookups behave identically on POSIX for
  hand-edited receipts.
- R3: The usage guide and the repo spec document the two supported receipt
  policies for gitignored adapters: record-and-warn (default installer
  behavior) and exclude-and-warn (repo-local guards like rwbp-website's),
  both passing the audit.

## Acceptance Criteria

- [ ] A repo with gitignored, present, unlisted claude wrappers passes the
      audit with a warning naming the files; a tracked unlisted pack-like
      file still fails.
- [ ] A receipt entry written as `scripts\sd-ai-command-pack-full-check.sh`
      audits identically to its forward-slash form.
- [ ] Twin gate, full suite, and docs/spec updates hold; mezmo PR #313
      comment 3522276141 can be pointed at the shipped fix.
