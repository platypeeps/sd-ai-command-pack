# Implementation plan: read-only `sd-check`

## 1. Freeze executable contracts

- Add focused fixtures for strict schema-version-1 configuration, normalized
  outcomes, aggregate precedence, bounded output, and exit codes.
- Add mutation-boundary fixtures for tracked, untracked, ignored generated,
  index, ref, cache, and provider/GitHub dispatch state.
- Preserve the child task as owner of the registry-derived shipped-surface
  graph; define its result-row integration without implementing a second graph.

## 2. Implement the coordinator

- Add `templates/scripts/sd-ai-command-pack-check.py` using only stdlib and the
  shipped `sd_ai_command_pack_lib.py` helper.
- Implement strict config/path/argv/timeout validation before execution.
- Implement the closed built-in inventory, configured prerequisite/check
  execution, cache routing, bounded diagnostics, state snapshots, deterministic
  JSON/human renderers, and stable exit semantics.
- Keep the root `scripts/` mirror byte-identical to the template.

## 3. Generate and install the command surface

- Add `sd-check` to the command registry as read-only locally/remotely and add
  the neutral command source plus canonical shared skill.
- Run the command-surface generator to create every platform adapter and
  manifest command entry.
- Add the coordinator script to the manifest and install/audit/provenance tests.
- Keep `sd-full-check` live but independent until the dedicated retirement
  task; add no alias, redirect, or fallback.

## 4. Rewire current callers

- Replace `sd-review-pr`'s review-full-check selector with the typed coordinator
  invocation and update focused orchestration tests.
- Update `sd-create-pr`, `sd-ship`, and `sd-work-backlog` wording/tests wherever
  they reconstruct the deterministic gate or name `check:full`.
- Leave provider review, routing, fixes, publication, waiting, merge, and
  generated refresh with their existing owners.

## 5. Document and validate

- Document `sd-check`, `check.json`, statuses, exits, remediation ownership,
  cache routing, and the temporary independent legacy surface.
- Bump the pack version/changelog for the shipped payload, run `make generate`
  then `make sync`, and refresh exact-payload release evidence only after the
  payload converges.
- Run focused coordinator/config/mutation/caller tests, generated parity,
  install audit, `git diff --check`, and `make check`.
- Start the child shipped-surface task next; do not mark the parent program
  complete until that graph and the later retirement/integration tasks close.
