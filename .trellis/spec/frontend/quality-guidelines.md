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

- Every adapter must instruct the agent to read
  `.agents/skills/trellis-review-pr/SKILL.md`.
- Every adapter must mention the review loop, the sixth-loop stop condition,
  and the final documentation/pre-commit recommendations.
- New adapters need README documentation and installer tests.
- Markdown prompts should use concise numbered steps.
- The shared skill should keep safety rules and final report requirements in
  explicit sections.
- The shared skill should keep standing permission for review-thread
  reply/resolve actions scoped to fixed, rebutted, or already-addressed
  threads.

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
