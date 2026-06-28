# Quality Guidelines

> Quality standards for prompt and command adapter files.

---

## Overview

The adapter files are intentionally small. Quality means they are easy to read,
point to the shared skill, and do not drift from each other. The shared skill
must stay precise enough that agents can run the PR review loop without
guessing.

## Forbidden Patterns

- Do not duplicate the full PR review workflow in every adapter.
- Do not add platform-specific behavior to an adapter unless the shared skill
  cannot express it.
- Do not mention unsupported trigger mechanisms as facts.
- Do not leave adapter templates out of `manifest.json`.
- Do not edit only one adapter when the same summary text appears in the other
  adapters.

## Required Patterns

- Every pack-owned workflow adapter must instruct the agent to read the
  matching shared skill under `.agents/skills/<command>/SKILL.md`. The
  adapter-only `continue`, `finish-work`, and `refresh-specs` wrappers are the
  exception: they read Trellis-provided skills from the target repo instead.
- Codex-visible `sd-*` wrappers live under `.agents/skills/` because Codex
  command completion surfaces enabled skills, not the other platforms' command
  adapter files. Keep their behavior aligned with the platform `sd` adapters.
- GitHub Copilot prompt adapters must use flat `sd-<command>.prompt.md`
  filenames with a description and `mode: agent` frontmatter.
- Gemini command adapters must use `.gemini/commands/sd/<command>.toml`; do
  not flatten them to `sd-<command>.toml`, because the `sd/` directory is what
  Gemini maps to the `/sd:<command>` namespace. Each file must include a useful
  `description` and a `prompt` string.
- OpenCode command adapters must use flat `.opencode/commands/sd-<command>.md`
  filenames so slash completion can find them by the `sd` prefix.
- Every adapter must mention its command's core loop or task list, safety
  stop condition, and final report expectation.
- New adapters need README documentation and installer tests.
- Markdown prompts should use concise numbered steps.
- The shared skill should keep safety rules and final report requirements in
  explicit sections.
- The shared skill should keep standing permission for review-thread
  reply/resolve actions scoped to fixed, rebutted, or already-addressed
  threads.
- The housekeeping skill should keep its expected clean-state output and
  anomaly reporting explicit.

## Testing Requirements

Run:

```bash
python3 -m unittest discover -s tests
```

When adding or changing adapter templates, test that the installer copies the
right file for the right platform and respects anchor/default behavior.

## Code Review Checklist

- Does the adapter remain a thin entry point?
- Is the shared skill still the only detailed workflow source of truth?
- Are all adapter file paths represented in `manifest.json`?
- Does README list the supported adapter and install behavior?
- Does `git diff --check` pass after template changes?
- Do all adapters still describe the same command behavior?
