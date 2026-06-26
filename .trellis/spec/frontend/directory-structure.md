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
├── .agents/skills/trellis-review-pr/SKILL.md       # Shared workflow
├── .gemini/commands/trellis/review-pr.toml         # Gemini command adapter
├── .github/prompts/review-pr.prompt.md             # GitHub Copilot prompt
└── .opencode/commands/trellis/review-pr.md         # OpenCode command adapter
```

## Module Organization

- Put reusable workflow instructions in the shared skill.
- Put only platform-specific command wrappers in platform adapter files.
- Keep generated or local Trellis runtime files outside the pack payload unless
  they are intentionally added to `templates/` and `manifest.json`.

## Naming Conventions

- Use the command name `review-pr` consistently across platform adapters.
- Keep Trellis command files under a `trellis/` command namespace.
- Use platform-native file formats: TOML for Gemini commands and Markdown for
  GitHub Copilot and OpenCode prompts.

## Examples

- `templates/.gemini/commands/trellis/review-pr.toml` contains a short prompt
  that tells Gemini to load the shared skill.
- `templates/.github/prompts/review-pr.prompt.md` mirrors the same entry-point
  instructions for GitHub Copilot.
- `templates/.opencode/commands/trellis/review-pr.md` mirrors the same
  entry-point instructions for OpenCode.
