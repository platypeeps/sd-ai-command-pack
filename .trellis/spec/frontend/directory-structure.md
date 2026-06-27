# Directory Structure

> How user-facing prompt and command files are organized in this project.

---

## Overview

This repository does not contain a browser frontend, React app, or visual UI.
The frontend-like surface is the set of platform command and prompt adapters
that users invoke from Gemini, GitHub Copilot, and OpenCode.

## Directory Layout

```text
templates/
├── .agents/skills/<command>/SKILL.md               # Shared workflows
├── .gemini/commands/trellis/<command>.toml         # Gemini command adapters
├── .github/prompts/<command>.prompt.md             # GitHub Copilot prompts
└── .opencode/commands/trellis/<command>.md         # OpenCode command adapters
```

## Module Organization

- Put reusable workflow instructions in the shared skill.
- Put only platform-specific command wrappers in platform adapter files.
- Keep generated or local Trellis runtime files outside the pack payload unless
  they are intentionally added to `templates/` and `manifest.json`.

## Naming Conventions

- Use command names consistently across platform adapters, such as
  `review-pr`, `full-check`, and `housekeeping`.
- Keep Trellis command files under a `trellis/` command namespace.
- Use platform-native file formats: TOML for Gemini commands and Markdown for
  GitHub Copilot and OpenCode prompts.

## Examples

- `templates/.gemini/commands/trellis/review-pr.toml` contains a short prompt
  that tells Gemini to load the matching shared skill.
- `templates/.github/prompts/review-pr.prompt.md` mirrors the same entry-point
  instructions for GitHub Copilot.
- `templates/.opencode/commands/trellis/review-pr.md` mirrors the same
  entry-point instructions for OpenCode.
