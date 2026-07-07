# task.py / get_context.py: add machine-readable (--json) output

## Summary

The Trellis workflow scripts emit human-formatted, colorized text only.
Automation built on top of Trellis has no stable way to ask "are there
active tasks?", "what is the current task?", or "what does record-mode
context contain?" — so it ends up grepping for literal sentence
fragments of the human output.

Concrete example from our tooling: a housekeeping script decides
whether a work stream is finished by running
`get_context.py --mode record` and grepping the output for the literal
string `(no active tasks assigned to you)`. If a future Trellis release
rewords that sentence, the check silently misclassifies the state — no
error, just a wrong branch taken. A code review flagged this as a
standing fragility, and it is representative: every consumer of these
scripts that is not a human reads them the same brittle way.

## Proposed upstream change

Add a `--json` flag (or a `TRELLIS_OUTPUT=json` env convention) to the
task and context entry points, emitting a stable schema, e.g.:

- `task.py list --json` → array of `{id, title, status, priority,
  assignee, dir}`
- `task.py current --json` → the current task object or `null`
- `get_context.py --mode record --json` → `{active_tasks: [...],
  git_status: {...}, recent_commits: [...], current_task: ...}`

Human output stays the default; the flag is additive and
non-breaking. Even a minimal first pass (list/current only) would let
downstream tooling drop sentence-grepping.

## Environment

Trellis CLI vendored scripts at `.trellis/.version` 0.6.5.
