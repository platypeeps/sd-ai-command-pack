# Prompt And Adapter Guidelines

> Project-specific guidance for the user-facing skill and platform adapters.

---

## Scope

Use these specs when changing any skill or command adapter under `templates/`.
Do not work from a list written here: command surfaces are added and retired,
and a hand-maintained inventory in a spec file goes stale silently. Enumerate
the live set instead:

```bash
# every shipped skill
ls templates/.agents/skills
# every generated adapter for one surface, across all platforms
git ls-files 'templates/**/*<surface>*'
# the authored neutral bodies the generators read
ls .github/command-sources
```

`manifest.json` is the authority on what ships; `.github/command-sources/` is
the authority on what is authored by hand. The generated adapters under
`templates/.claude/`, `templates/.commands/`, `templates/.gemini/`, and
`templates/.github/prompts/` derive from those two, so edit the source and run
`make generate` rather than editing an adapter directly.

The primary surfaces to know are `sd-check` (deterministic verification) and
`sd-review` (the routed review lifecycle); `sd-ship` composes the
publish-to-merge chain and `sd-housekeeping` owns the merge gate.

OpenCode command targets install from the generated guarded
`templates/.commands/` sources. Hand-authored neutral bodies live under
`.github/command-sources/`; do not add duplicate OpenCode command source files
under `templates/.opencode/commands/`.

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
5. Read `tests/test_generated_parity.py` and any affected focused test module
   if the installed file set changes.

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
