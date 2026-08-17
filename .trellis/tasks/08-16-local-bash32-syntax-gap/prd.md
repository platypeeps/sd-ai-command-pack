# PRD: Local gates accept shell that bash 3.2 rejects

Recorded 2026-08-16 as a follow-up from `08-09-machine-status-copy-unavailable`
(PR #491), where this gap cost a CI round-trip.

## Goal

`make check` validates shell scripts with whichever `bash` the developer has on
`PATH`. On a machine with Homebrew bash 5 that is bash 5, so a construct only
bash 3.2 rejects passes every local gate and fails on the macOS CI leg, several
minutes later, with a message that points at the wrong line.

Close the gap between what the local gate validates and what CI validates,
without adding a second CI leg — the macOS leg already exists and works.

## What happened

`templates/scripts/sd-ai-command-pack-pack-update.sh` gained a comment inside a
`$( ... )` command substitution containing an apostrophe ("the caller's
message"). bash 3.2 — still `/bin/bash` on macOS — mis-scans that apostrophe as
an unterminated quote and rejects the entire file:

```
line 282: unexpected EOF while looking for matching `''
```

The reported line is the end of the file, not the comment, so the message does
not name the defect. Locally:

- `bash -n` with bash 5.3.15 on `PATH`: exit `0`
- `/bin/bash -n` with bash 3.2.57: exit `2`

`make check` exited `0`. The failure surfaced as
`unittest (macos-latest, 3.13)`, in `tests/test_review_scope.py`'s
`test_installed_shared_scripts_and_prism_rules_are_valid`, which shells out to
`bash -n` and therefore inherits the same `PATH`-dependent interpreter.

The gotcha itself is now recorded in
`.trellis/spec/backend/quality-guidelines.md`, next to the existing note that
the macOS leg protects bash-3.2 behavior Ubuntu cannot exercise. This task is
about the gate, not the rule: a documented rule does not fail a build.

## Requirements

1. A local run of the repository's standard gate must reject a shell script
   that `/bin/bash -n` rejects on macOS, on a developer machine whose `PATH`
   bash is newer. Prove it with a deliberately broken fixture, not by asserting
   the command was added.
2. Enumerate the shell scripts to check from the filesystem — the tracked
   `*.sh` set — rather than from a maintained list. A list drifts as scripts
   are added; the defect this task exists to catch would then reappear in an
   unlisted file.
3. Decide and record what happens on a platform with no bash 3.2 available.
   Linux developers have no `/bin/bash` at 3.2, so the check either degrades to
   a documented no-op there or uses another mechanism. A check that silently
   passes because the interpreter is missing is the same failure in a new
   place, so a skip must be visible.
4. Do not add a CI leg. The macOS leg already catches this; the point is to
   catch it before the push, and a second leg would only duplicate cost.

## Open question for design

Whether this belongs in `tests/test_review_scope.py` — pinning the interpreter
that test invokes — or as a `.sd-ai-command-pack/check.json` row, or in the
review preflight. The test already walks installed shared scripts, so pinning
its interpreter may be the smallest correct change; a check row is more visible
in the gate output. Design should pick one and say why, not do both.

## Acceptance criteria

- [ ] A fixture carrying the exact bash-3.2 construct fails the local gate on a
      machine whose `PATH` bash is 5.x, demonstrated by running it.
- [ ] The scripts checked are enumerated from tracked `*.sh` at run time.
- [ ] The no-bash-3.2 platform behavior is decided, implemented, and visible in
      the gate output rather than silent.
- [ ] No new CI job or leg is added.
- [ ] `make check` passes.
