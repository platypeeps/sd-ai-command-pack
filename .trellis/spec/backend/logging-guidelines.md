# Logging Guidelines

> How logging is done in this project.

---

## Overview

The installer does not use a logging framework. It prints a compact,
script-friendly summary of what it did.

## Log Levels

There are no formal log levels. Use plain `print()` output for:

- pack name and version
- target path
- dry-run mode
- per-file install statuses
- conflict summaries
- optional tooling warnings

## Structured Logging

Keep output stable and easy to scan. Existing per-file lines use an aligned
status followed by the target path:

```text
created     .agents/skills/trellis-review-pr/SKILL.md
skipped     .opencode/commands/trellis/review-pr.md (anchor .opencode not present)
```

## What to Log

- Print every selected file result.
- Print every skipped file and the reason.
- Print conflict paths and the exact retry hint.
- Print `git diff --check` output when that validation fails.

## What NOT to Log

- Do not log environment dumps, auth tokens, secrets, or unrelated target repo
  files.
- Do not add verbose progress output for simple filesystem copies.
- Do not print stack traces for expected installer outcomes.
