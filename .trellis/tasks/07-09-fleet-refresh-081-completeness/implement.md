# Fleet Refresh To 0.8.1 With Install Completeness Verification Implementation Plan

## Execution Order

1. Add the fleet manifest with the six real consumers and platform sets,
   explicitly excluding stale clones.
2. Add a small preflight helper that reads consumer provenance, compares it to
   the pack `manifest.json` version, and reports skip/refresh-needed states.
3. Add an expected-target derivation helper that reuses installer selection
   logic and generated state paths.
4. Wire the expected-target helper into install audit or a rollout-only audit
   mode, then add failure output for missing expected files.
5. Reproduce the dropped `.claude/commands/sd/work-backlog.md` case in a temp
   repo; fix the installer if reproduced, otherwise document the negative
   result in this task.
6. Run the six consumer refreshes through PRs only after the checks are green.

## Validation Plan

Run focused installer/audit tests first, then the full installer coverage gate.
Before fleet PRs, run `python3 install.py <repo> --force --dry-run` and the new
preflight against at least one already-current fixture. After each consumer PR
merges, confirm provenance version, receipt completeness, and audit success.

## Documentation And Spec Updates

Document the fleet manifest, the at-target skip behavior, and the completeness
check in `README.md` and the installed guide twins. Add a note correcting the
archived close-loop task's five-consumer inventory if the task remains the
historical reference.

## Review Notes

Reviewers should check that no consumer-specific path is hardcoded into the
installer core. The rollout helper may know about the fleet; install/audit
libraries should remain generic.

## Follow-Ups

If the root cause of the broken 0.7.0 installs is not reproduced, create a
separate task only if later fleet evidence reveals the mechanism.
