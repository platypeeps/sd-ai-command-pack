# Close Drift-Gate Absence Blindness And Refresh Dogfood Copies Design

## Overview

The current pack drift gate compares existing installed twins but skips missing
ones. This task should make absence, orphan templates, and case-only target
collisions first-class failures, then refresh the pack repo's own dogfood
copies.

## Proposal

Extend `tests/test_pack_drift.py` to treat root platform directories that exist
in this repo as opt-in dogfood installs. For each manifest entry whose platform
directory exists at the root, require the installed target to exist and match
the template bytes. Shared files should remain required as they are today.

Add a tracked-template completeness assertion by comparing `git ls-files
templates` to manifest sources. Exclude non-payload artifacts only if they are
intentionally not shipped and documented in the test. Add a casefold uniqueness
assertion over manifest targets to catch APFS collisions on Linux CI.

Finally run the installer against this repo with `--force` to restore missing
root copies, then reconcile the wording in maintainer instructions so the
claim matches what the tests enforce.

## Boundaries And Non-Goals

Do not build the adapter generator here. This task closes the absence blind
spot and refreshes current dogfood copies only.

## Affected Files

- `tests/test_pack_drift.py`
- `tests/test_generated_parity.py` if casefold target checks already live
  there
- Root `.claude/`, `.gemini/`, `.github/`, and `.opencode/` adapter copies
- `AGENTS.md` and `.github/copilot-instructions.md`

## Risks And Edge Cases

Some platform directories may exist for Trellis-owned local state rather than
pack-owned dogfood. Keep the rule tied to manifest targets and existing root
platform directories, not every possible platform.

## Validation

Run the focused drift/parity tests, `python3 install.py . --dry-run`, and the
pack full-check with local AI reviewers disabled.
