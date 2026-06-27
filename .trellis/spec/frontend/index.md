# Prompt And Adapter Guidelines

> Project-specific guidance for the user-facing skill and platform adapters.

---

## Scope

Use these specs when changing files under `templates/`, especially:

- `templates/.agents/skills/trellis-review-pr/SKILL.md`
- `templates/.agents/skills/trellis-full-check/SKILL.md`
- `templates/.agents/skills/trellis-housekeeping/SKILL.md`
- `templates/.gemini/commands/trellis/review-pr.toml`
- `templates/.github/prompts/review-pr.prompt.md`
- `templates/.opencode/commands/trellis/review-pr.md`

This repo has no React app, browser UI, hooks, CSS, or client-side state. The
user-facing layer is prompt and command text that other AI platforms execute.

## Guides

| Guide | Use When |
|-------|----------|
| [Directory Structure](./directory-structure.md) | Adding, moving, or organizing template payload files |
| [Adapter Guidelines](./adapter-guidelines.md) | Changing shared skill text or platform command/prompt wrappers |
| [Quality Guidelines](./quality-guidelines.md) | Checking prompt consistency, install coverage, and adapter drift |

## Pre-Development Checklist

Before editing templates:

1. Read `templates/.agents/skills/trellis-review-pr/SKILL.md`; it is the
   detailed workflow source of truth.
2. Read every platform adapter for the same command so wording stays aligned.
3. Read `manifest.json` to confirm the template is installed.
4. Read `README.md` to confirm supported adapters and install behavior.
5. Read `tests/test_install.py` if the installed file set changes.

## Quality Check

Run:

```bash
python3 -m unittest discover -s tests
git diff --check
```

Also verify:

- Each platform adapter still tells the agent to read the shared skill.
- Detailed workflow shared skills include safety rules and final report
  expectations for their command.
- Any new adapter is listed in `manifest.json`, described in `README.md`, and
  covered by installer tests.
