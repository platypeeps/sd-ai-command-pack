# Fix Session Recorder For Untracked Workspaces Design

## Overview

The recorder wrapper already owns retry safety around Trellis
`add_session.py`. The missing piece is that its git-status discovery ignores
individual journal files when `.trellis/workspace/` is fully untracked, which
is common for local-only installs.

## Proposal

Change `modified_workspace_journals()` in
`scripts/sd-ai-command-pack-record-session.py` and its template twin to ask git
for untracked files under `.trellis/workspace` with `--untracked-files=all`
while preserving the existing NUL-delimited parser and rename/copy handling.
Keep the scope limited to workspace journal Markdown paths containing
`/journal-` so unrelated untracked files under `.trellis/workspace/` are not
treated as session journals.

Add an end-to-end regression in `tests/test_record_session.py` that seeds
Trellis tooling without tracking `.trellis/workspace/`, forces the first
record attempt to fail after `add_session.py` writes the journal, and reruns
the exact command. The final journal should contain one session, proving the
retry path patches the existing uncommitted entry instead of appending another.

## Boundaries And Non-Goals

Do not change Trellis-owned `.trellis/scripts/add_session.py`. The pack wrapper
is the durable source for this behavior until upstream exposes a cleaner
session API.

## Affected Files

- `templates/scripts/sd-ai-command-pack-record-session.py`
- `scripts/sd-ai-command-pack-record-session.py`
- `tests/test_record_session.py`
- Possibly `docs/SD_AI_COMMAND_PACK.md` and the template twin if retry
  behavior needs a user-facing note

## Risks And Edge Cases

Adding `-uall` can reveal more paths than before. The path filter must continue
to require Markdown journal files under `.trellis/workspace`, and the existing
zero/multiple ambiguity errors must remain fail-closed.

## Validation

Run `python3 -m unittest tests.test_record_session`, then the shipped-scripts
coverage gate and pack drift checks to prove the script/template twins remain
byte-identical.
