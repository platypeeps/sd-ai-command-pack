---
description: Run one exact-scope local and routed-remote Software Delivery review lifecycle.
---

# Software Delivery Review

Run the unified exact-scope review lifecycle for local changes, a branch, the
checked-out codebase, or a pull request.

1. Resolve the `sd-review` skill by name using the agent's trusted skill discovery mechanism for installed skills.
2. Verify that `scripts/sd-ai-command-pack-review.py` and `scripts/sd-ai-command-pack-toolchain.sh` are resolvable, either as bare commands on `PATH` or as regular readable files at those paths relative to the repository root. If the skill or either script is missing, malformed, ambiguous, unsafe, or unavailable, stop and report the exact blocker.
3. Use the skill as the primary instructions. Parse only its documented `scope=`, `local=`, `remote=`, `fix=`, `pr=`, and `attempt=` controls; reject unknown or duplicate controls before execution.
4. Invoke the typed coordinator through the pack toolchain wrapper. Do not reconstruct provider planning, router discovery, direct reviewer dispatch, receipt polling, or exact-head readiness in adapter prose, and never fall back to `sd-review-pr`.
5. Follow the skill's finding-disposition and exact-head re-entry loop until the typed result is ready, a user-owned structured decision is required, the configured round limit is reached, or a blocked/failed/indeterminate result requires intervention. Relay the full result, limitations, provider cost/latency evidence, and exact next action.
