# Directory Structure

> How user-facing prompt and command files are organized in this project.

---

## Overview

This repository does not contain a browser frontend, React app, or visual UI.
The frontend-like surface is the set of platform command and prompt adapters
that users invoke from Claude, Cursor, Gemini, GitHub Copilot, and OpenCode.

## Directory Layout

```text
templates/
├── .agents/skills/<command>/SKILL.md               # Shared workflows
├── .claude/commands/sd/<command>.md                # Claude command adapters
├── .cursor/commands/sd-<command>.md                # Cursor command adapters
├── .gemini/commands/sd/<command>.toml              # Gemini command adapters
├── .github/prompts/sd-<command>.prompt.md          # GitHub Copilot prompts
└── .opencode/commands/sd-<command>.md              # OpenCode command adapters
```

## Module Organization

- Put reusable workflow instructions in the shared skill.
- Put only platform-specific command wrappers in platform adapter files.
- Keep generated or local Trellis runtime files outside the pack payload unless
  they are intentionally added to `templates/` and `manifest.json`.

## Naming Conventions

- Use command names consistently across platform adapters, such as
  `continue`, `finish-work`, `review-pr`, `full-check`, `housekeeping`, and
  `update-spec`.
- Keep pack-owned command adapters under the `sd` namespace so they do not
  collide with Trellis-owned generated command files. Claude and Gemini express
  that namespace through directories; Cursor, GitHub Copilot, and OpenCode
  express it through flat `sd-<command>` filenames that their command lists can
  surface.
- Do not flatten Gemini command files. `.gemini/commands/sd/review-pr.toml`
  becomes `/sd:review-pr` because Gemini maps command subdirectories to colon
  namespaces.
- Use platform-native file formats: TOML for Gemini commands and Markdown for
  Claude, Cursor, GitHub Copilot, and OpenCode prompts.

## Examples

- `templates/.gemini/commands/sd/review-pr.toml` contains a short prompt
  that tells Gemini to load the matching shared skill.
- `templates/.cursor/commands/sd-review-pr.md` mirrors the same entry-point
  instructions for Cursor.
- `templates/.github/prompts/sd-review-pr.prompt.md` mirrors the same entry-point
  instructions for GitHub Copilot.
- `templates/.opencode/commands/sd-review-pr.md` mirrors the same
  entry-point instructions for OpenCode.
