# Design

## Boundary

The agent-owned finish-work lifecycle produces a final branch head after task
and journal commits. The shell command owns the irreversible merge. Connect the
two with an explicit `--finish-work-head <oid>` argument captured only after
finish-work, push, and required checks complete.

The merge gate compares the supplied OID to the current local branch head
before comparing local, remote, and PR heads. An absent or stale OID adds an
anomaly and returns without merge. The option is irrelevant to post-merge
cleanup, so those paths do not require it.

## Source and Generation Flow

Change source-owned files under `templates/` first:

1. shared `sd-housekeeping` and `sd-ship` skills;
2. neutral, Claude, and Gemini housekeeping adapters;
3. the shipped housekeeping shell template;
4. pack documentation and focused tests.

Run the repository generator and `make sync` to update all generated platform
surfaces and dogfood mirrors. Do not hand-maintain generated root copies.

## Compatibility

This is a compatible safety fix. Direct callers that auto-merge an open PR must
now pass the exact post-finish head. Cleanup-only callers retain the existing
command. The manifest receives a patch bump and the changelog records the new
required merge handoff.

## Validation

The hermetic script self-test covers absent, stale, and matching evidence. The
Python subprocess suite covers public argument validation and generated-surface
consistency. `make check` remains the release gate.
