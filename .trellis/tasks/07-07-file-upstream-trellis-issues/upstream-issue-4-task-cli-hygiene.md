# task.py create: blank descriptions accepted; current-task pointer moves on every create

Two small UX/hygiene issues in the task CLI, observed while batch-
creating tasks.

## 1. Blank descriptions are accepted silently

`task.py create <title>` without `--description` produces a task whose
metadata description is the empty string, and nothing later flags it —
tasks can be completed and archived with blank descriptions. In our
repo three archived tasks with substantive PRDs carry empty
descriptions, which hurts searchability and later task audits.

**Proposal**: warn on `create` when the description is empty, and/or
warn on `finish`/`archive` when completing a task whose description is
still blank. (Rejecting outright is probably too strict — a warning
with a `--allow-empty-description` escape hatch matches existing CLI
conventions.)

## 2. `create` moves the current-task pointer

Each `task.py create` appears to set the current-task pointer to the
newly created task. When creating one task and immediately starting it,
that is convenient; when batch-creating a backlog (we created 20 in one
session), the pointer silently ends up on the *last* created task —
which the next `continue`-style workflow then treats as the active work
item. We had to notice this and run `task.py finish` to clear it.

**Proposal**: only set the pointer via the explicit `task.py start`
command (or add `--no-start` / respect an existing pointer if one is
already set). At minimum, print a line saying the pointer moved so the
behavior is visible.

## Environment

Trellis CLI vendored scripts at `.trellis/.version` 0.6.5.
