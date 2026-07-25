---
description: Run deterministic read-only Software Delivery checks and report a typed result.
---

# Software Delivery Check

Run the deterministic, read-only Software Delivery check for the current repository.

1. Resolve the `sd-check` skill by name using the agent's trusted skill discovery mechanism for installed skills.
2. If that skill is missing, unreadable, empty, duplicated, malformed, defines contradictory safety rules, or requires unavailable tools, stop and report the exact blocker.
3. Use the skill as the primary instructions and run the installed typed coordinator exactly once.
4. Keep the workflow read-only. Do not run an AI reviewer, dispatch GitHub review, refresh generated state, fix findings, stage, commit, push, merge, or switch branches.
5. Relay every `failed`, `skipped`, `unavailable`, `invalid`, and `indeterminate` row plus its remediation. Report success only when the aggregate result is `passed` and the state guard passed.
