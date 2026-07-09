# Fix Session Recorder For Untracked Workspaces Implementation Plan

## Execution Order

1. Update the template recorder first, adding `--untracked-files=all` to the
   `git status --porcelain -z` call.
2. Copy the template change to the root `scripts/` twin.
3. Add a focused test that leaves `.trellis/workspace/` untracked and simulates
   a post-write failure using the existing git-stub pattern.
4. Assert the retry keeps the final `## Session` count at one and updates the
   journal/index consistently.
5. Keep the existing rename, branch, unknown-hash, and variant tests green.

## Validation Plan

Run `python3 -m unittest tests.test_record_session`. Then run the relevant
coverage command with absolute coverage env paths and `git diff --check`.

## Documentation And Spec Updates

No broad documentation should be needed unless the behavior changes user-facing
exit messages. If a note is added, update both installed guide twins.

## Review Notes

The reviewer should pay close attention to the status parser. It must still
skip the second token of rename/copy entries and must not stage unrelated
workspace files.

## Follow-Ups

If this exposes Trellis upstream behavior that should be fixed at the source,
write a paste-ready handoff instead of opening an upstream Trellis PR.
