# Prompt And Adapter Guidelines

> Project-specific guidance for the user-facing skill and platform adapters.

---

## Scope

Use these specs when changing files under `templates/`, especially:

- `templates/.agents/skills/sd-review-pr/SKILL.md`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.agents/skills/sd-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-work-backlog/SKILL.md`
- `templates/.agents/skills/sd-start/SKILL.md`
- `templates/.agents/skills/sd-continue/SKILL.md`
- `templates/.agents/skills/sd-finish-work/SKILL.md`
- `templates/.agents/skills/sd-full-check/SKILL.md`
- `templates/.agents/skills/sd-housekeeping/SKILL.md`
- `templates/.agents/skills/sd-update-spec/SKILL.md`
- `templates/.claude/commands/sd/start.md`
- `templates/.claude/commands/sd/continue.md`
- `templates/.claude/commands/sd/finish-work.md`
- `templates/.claude/commands/sd/full-check.md`
- `templates/.claude/commands/sd/housekeeping.md`
- `templates/.claude/commands/sd/work-backlog.md`
- `templates/.claude/commands/sd/review-pr.md`
- `templates/.claude/commands/sd/update-spec.md`
- `templates/.commands/sd-start.md`
- `templates/.commands/sd-continue.md`
- `templates/.commands/sd-finish-work.md`
- `templates/.commands/sd-full-check.md`
- `templates/.commands/sd-housekeeping.md`
- `templates/.commands/sd-work-backlog.md`
- `templates/.commands/sd-review-pr.md`
- `templates/.commands/sd-update-spec.md`
- `templates/.gemini/commands/sd/start.toml`
- `templates/.gemini/commands/sd/continue.toml`
- `templates/.gemini/commands/sd/finish-work.toml`
- `templates/.gemini/commands/sd/full-check.toml`
- `templates/.gemini/commands/sd/housekeeping.toml`
- `templates/.gemini/commands/sd/work-backlog.toml`
- `templates/.gemini/commands/sd/review-pr.toml`
- `templates/.gemini/commands/sd/update-spec.toml`
- `templates/.github/prompts/sd-start.prompt.md`
- `templates/.github/prompts/sd-continue.prompt.md`
- `templates/.github/prompts/sd-finish-work.prompt.md`
- `templates/.github/prompts/sd-full-check.prompt.md`
- `templates/.github/prompts/sd-housekeeping.prompt.md`
- `templates/.github/prompts/sd-work-backlog.prompt.md`
- `templates/.github/prompts/sd-review-pr.prompt.md`
- `templates/.github/prompts/sd-update-spec.prompt.md`
- `templates/.opencode/commands/sd-start.md`
- `templates/.opencode/commands/sd-continue.md`
- `templates/.opencode/commands/sd-finish-work.md`
- `templates/.opencode/commands/sd-full-check.md`
- `templates/.opencode/commands/sd-housekeeping.md`
- `templates/.opencode/commands/sd-work-backlog.md`
- `templates/.opencode/commands/sd-review-pr.md`
- `templates/.opencode/commands/sd-update-spec.md`

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

1. Read `templates/.agents/skills/sd-review-pr/SKILL.md`; it is the
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
