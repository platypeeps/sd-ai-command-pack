# Design: finish-work bookkeeping validator

## Design Summary

Extract task/archive/journal rules into one side-effect-free validator and run
it at two lifecycle boundaries: before any selected task is archived and after
all archive/journal work is complete but before the final push. The same helper
also powers the bookkeeping CI lane.

## Validator Modes

`pre-archive` receives exact task directory arguments. It validates each active
task's bounded regular artifacts, identity, required descriptive metadata,
lifecycle state, topology, branches, and context placeholders without scanning
unrelated historical tasks.

`final-bundle` receives base/head or an explicit changed-path set. It validates
the complete archive/journal delta, including move identity, final lifecycle
metadata, supported layout, journal/index consistency, referenced commits,
real content, placeholders, and whitespace.

Both modes produce the same schema-versioned finding/result shape. CI may use
the committed before/after form; local finish-work uses exact paths and Git
state. Rule implementations are shared.

## Lifecycle Integration

1. `sd-finish-work` resolves tasks selected for archive.
2. Run `pre-archive`; stop without mutation on failure.
3. Delegate archive and record the journal through existing owners.
4. Run `final-bundle` against every resulting bookkeeping commit.
5. Record the exact validator result for later review/ship/housekeeping use.
6. Permit the existing single push only after success.

If step 4 fails, local commits remain for bounded recovery. The workflow does
not reset, amend, delete, or push. The user receives exact failing fields and
the command to revalidate after correction.

## Safety And Compatibility

- Templates remain authoritative for the wrapper/helper payload.
- Upstream Trellis is unchanged; the pack surrounds its archive/journal
  operations with validation.
- Existing exact-head review, CI, thread, and merge gates remain independent.
- Rollback removes wrapper invocation but does not rewrite task history.
