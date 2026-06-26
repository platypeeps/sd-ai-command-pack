# Quality Guidelines

> Code quality standards for backend and CLI development.

---

## Overview

Prefer small, explicit stdlib Python over framework code. The installer should
remain easy to audit because it writes files into other repositories.

## Forbidden Patterns

- Do not overwrite user files unless `--force` is set.
- Do not stage, commit, or modify the target repo beyond the manifest-listed
  files.
- Do not duplicate platform install rules in several places; update
  `manifest.json` and let `selected_files()` apply the rules.
- Do not replace structured parsing with ad hoc string parsing for JSON.

## Required Patterns

- Use `pathlib.Path` for filesystem work.
- Keep pack files declared in `manifest.json`.
- Keep platform selection behavior covered by tests when adding adapters or
  install modes.
- Run `git diff --check` after writes unless `--skip-diff-check` is requested.

## Testing Requirements

Run the installer tests with:

```bash
python3 -m unittest discover -s tests
```

Add or update tests when changing:

- CLI flags or argument behavior
- conflict and force handling
- platform selection and anchor rules
- template paths or manifest semantics

## Code Review Checklist

- Does the change preserve existing target files by default?
- Are new templates listed in `manifest.json` and documented in `README.md`?
- Do tests exercise the behavior through the CLI, not only helper functions?
- Does the installer still work with only Python 3.10+ stdlib dependencies?
- Is terminal output concise and stable enough for users to understand failures?
