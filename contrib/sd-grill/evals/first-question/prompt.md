---
description: >-
  Requirement 1 of the 2026-09-04 sd-grill item: the opening turn asks one
  question, open rather than from an assistant-written option set, and writes
  nothing.
runs: 2
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

Run sd-grill on this. input="Our team CLI should get a --watch mode for the log viewer, so people stop re-running it." bounds="at most 4 questions"
