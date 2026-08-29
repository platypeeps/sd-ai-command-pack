---
title: Fix vendored pack-source lint and robustness findings (0.64.1)
status: done
created: 2026-08-03
---
# Fix vendored pack-source lint and robustness findings (0.64.1)

## Context

During the sd-ai-command-pack 0.64.0 fleet refresh, consumer PR reviewers
(Copilot / github-code-quality) repeatedly flagged the same defects in the
**vendored, installer-managed** pack scripts shipped into each consumer. Those
files are regenerated verbatim on every refresh, so they cannot be fixed in a
consumer — the fix belongs in this pack's source. Findings were captured in
`scratchpad/upstream-pack-findings.md` during the rollout.

The source of truth for shipped scripts is `templates/scripts/` (install.py
reads from `templates/`); `scripts/` holds byte-identical twins used for the
maintainer gate. Every edit must land in **both** trees, byte-identical.

## Problem

The captured findings were recorded across a long session and the source has
moved since; at least one is already fixed on HEAD. Shipping "fixes" for
already-correct code, or fixing one twin only, would regress the pack. We need
a verified pass that changes only what is genuinely still defective.

## Goal

Harden the flagged pack-source scripts, release the result as **0.64.1**, and
leave the fleet on a clean vendored surface so future consumer refresh PRs stop
re-surfacing the same lint. No behavior change beyond the stated hardening.

## Requirements

- Re-verify each captured finding against HEAD before touching it; fix only
  confirmed-still-defective code.
- Apply every fix identically in `scripts/` and `templates/scripts/`.
- No behavior change beyond the stated hardening; new code paths get tests.
- Release as 0.64.1 through the pack's normal release machinery
  (`.github/scripts/prepare-release.py`, `make generate`, `make sync`,
  `make check`).
- Re-fanout to consumers is deferred (out of scope).

## In-scope findings (re-verify, then fix confirmed)

- `sd-ai-command-pack-recovery-artifacts.py` — empty pass-only `except`
  handlers (CodeQL `py/empty-except`, e.g. L202/207/211 and the `_CleanupLock`
  acquire/release blocks) — fix **structurally** with `contextlib.suppress`, not
  a comment (a comment does not clear CodeQL). `read_text` L216/L969 already
  pass `encoding="utf-8"`, so the raw "missing `errors=`" finding is moot; the
  only real gap is that invalid UTF-8 (`UnicodeError`) is uncaught — rebut or
  harden per design §2.
- `sd-ai-command-pack-work-loop.py` — same classes (empty except L1143-1144;
  `read_text` L2293 already utf-8).
- `sd-ai-command-pack-update-spec-kb.py` — `file_ends_with_kb_copy_marker`
  (**L553**) reads the whole file to test a short trailing marker; read only the
  tail.
- `sd-ai-command-pack-status.py` — `collect_recovery` accepts any dict from the
  dynamically loaded helper without a `schemaVersion` check (dict-check ~L1226,
  add check after it); the dynamic-import guard uses `is_file()` which follows
  symlinks (L1196, and a second identical guard at L800).

## Out of scope / already resolved

- `sd-ai-command-pack-review-scope.sh` — **already fixed on HEAD**:
  `resolve_pr_body_scope_state` checks the provided
  `SD_AI_COMMAND_PACK_SCOPE_PR_BODY` at **L189-190**, before the `gh_disabled`
  branch (L199 is blank). No change.
- The install-audit depth-3 `references/` "gap" from anomaly #314 — rebutted and
  confirmed a non-issue (`fnmatch` `*` crosses `/`). No change.
- Re-fanning-out 0.64.1 to consumers — deferred to the next natural refresh.

## Acceptance Criteria

- [ ] Each captured finding re-verified against HEAD and recorded as
  confirmed-and-fixed or already-resolved, with file:line evidence.
- [ ] All confirmed fixes applied identically in `scripts/` and
  `templates/scripts/` (verified byte-identical by diff).
- [ ] No behavior regression: existing tests pass; new code paths
  (schemaVersion fail-closed, symlink reject, tail-read) have coverage.
- [ ] `make check` passes clean (test + 100% coverage gate, shipped-script
  coverage/docs gates, lint, audit, full-check).
- [ ] `manifest.json` `version` bumped to 0.64.1 by hand and the `CHANGELOG.md`
  top heading updated (both before `make release-prep`, which validates the
  gate); `.sd-ai-command-pack/provenance.json` hashes and the dogfood install
  refreshed via `make sync`; install-audit passes. (`manifest.json.files[]` is
  routing metadata with no hashes and does not change.)
- [ ] CHANGELOG updated.
- [ ] Merged to pack `main` green. Fleet re-fanout NOT performed.

## Notes

- Severity of every confirmed finding is low (hygiene / robustness); none is
  functional-breaking. This is a quality + release task, not a hotfix.

## References

Research notes that lived beside this item's Trellis record and were not carried
into docs/work. Recover the bodies from git history under `.trellis/tasks/archive/2026-08/08-03-fix-vendored-source-findings`:

- research/phase-a-verified-findings.md
