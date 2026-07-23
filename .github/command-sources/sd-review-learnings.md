---
description: Detect or update repository review learnings.
---

# SD Review Learnings

In this pack, SD means Software Delivery. A skill is a project-installed Markdown instruction bundle resolved by the agent's trusted installed-skill resolver.

Detect recurring review feedback patterns and optionally update the repository learning file.

1. Resolve the `sd-review-learnings` skill by name using the agent's trusted skill discovery mechanism for installed skills.
2. Verify that `scripts/sd-ai-command-pack-review-learnings.py` exists relative to the repository root. If the skill or script is missing, unreadable, empty, resolves to more than one candidate, fails validation, defines contradictory steps that violate this command's safety rules, requires unavailable tools, or cannot execute, stop and report the exact blocker.
3. Use the skill as the primary instructions for interpreting review patterns.
4. From the repository root, use the first executable Python found in `./.venv/bin/python`, `./venv/bin/python`, `./env/bin/python`, `./.venv/Scripts/python.exe`, `./venv/Scripts/python.exe`, or `./env/Scripts/python.exe`; otherwise use `python3`. The script is stdlib-only, so do not install dependencies just for this command. Run `scripts/sd-ai-command-pack-review-learnings.py --include-working-tree` from the repository root for the local scan. If the script fails, stop and report the command, exit status, and complete stdout/stderr output.
5. Run read-only by default. Add `--update` only when the user's request clearly indicates intent to modify or persist a canonically resolved repository-local learning file, typically `docs/review-learnings.md`. An external write requires the skill's exact-path structured confirmation plus `--update-external` and the matching `--confirmed-external-target`; unavailable or noninteractive question capability stops without writing.
6. Report mode, canonical root and target, containment, detected patterns, proposed/applied changes, digests, write status and occurrence, and any external-service or command failures. Never stage, commit, push, or publish the learning update as part of this command.
