---
description: Run one exact-scope local and routed-remote Software Delivery review lifecycle.
---

# Software Delivery Review

Run the unified exact-scope review lifecycle for local changes, a branch, the
checked-out codebase, or a pull request.

1. Resolve the `sd-review` skill by name using the agent's trusted skill discovery mechanism for installed skills.
2. Resolve the pack toolchain with the documented bootstrap — the `SD_AI_COMMAND_PACK_TOOLCHAIN` override, then the checkout's own `scripts/` copy, then the machine install under `$HOME/.agents/bin` — and reach the typed review coordinator only through it. Do not probe `PATH`: a `PATH` entry can name a different install than the one the running skill text came from. If the skill is missing, malformed, ambiguous, or unsafe, or if the bootstrap finds no toolchain, stop and report the exact blocker.
3. Use the skill as the primary instructions. Parse only its documented `scope=`, `local=`, `remote=`, `fix=`, `pr=`, and `attempt=` controls; reject unknown or duplicate controls before execution.
4. Invoke the typed coordinator through the pack toolchain wrapper. Do not reconstruct provider planning, router discovery, direct reviewer dispatch, receipt polling, or exact-head readiness in adapter prose, and never fall back to `sd-review-pr`.
5. Follow the skill's finding-disposition and exact-head re-entry loop until the typed result is ready, a user-owned structured decision is required, the configured round limit is reached, or a blocked/failed/indeterminate result requires intervention. Relay the full result, limitations, provider cost/latency evidence, and exact next action.
