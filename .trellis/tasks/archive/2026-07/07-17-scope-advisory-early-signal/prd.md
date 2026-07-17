# Early advisory for tooling/generated PR scope

## Problem

The tooling/generated PR-scope requirement only fails LATE — during
`full-check`, after the PR exists and its body is written. The local pre-PR
gate (`review:guard` → `sd-ai-command-pack-review-preflight.mjs`) does not
check scope at all, and `review-scope.sh` warns-and-skips without naming the
required section when no PR exists. The author gets a green pre-PR light,
writes the PR, and only then learns the body needs a scope section.

## Requirements

- R1. `review-scope.sh` gains an `advisory` mode
  (`SD_AI_COMMAND_PACK_SCOPE_CHECK=advisory`): classify the working/branch
  diff, and when a scope-requiring file is present, warn naming the exact
  required section (e.g. `Tooling/generated scope:`). No `gh`, no PR lookup,
  never fails, exit 0.
- R2. `review-scope.sh` no-PR path (normal mode) upgraded to name the required
  section in its warning instead of a bare "skipping".
- R3. `sd-ai-command-pack-review-preflight.mjs` adds a warn-only check that
  shells out to `review-scope.sh` in advisory mode and surfaces its message.
  All classification/heading policy stays in the bash script (no duplication).
- R4. `full-check.sh` hard-fail behavior and exit codes unchanged when a PR
  exists.
- R5. Env toggles (`SD_AI_COMMAND_PACK_SCOPE_CHECK`) disable both the advisory
  and the existing check (`off`/`disabled` → both skip).
- R6. Both twins byte-identical (scripts/ + templates/scripts/); docs updated;
  pack tests updated; manifest version bump + CHANGELOG.

## Acceptance Criteria

- [ ] A1. Changing a tooling/generated file and running the pre-PR preflight
  (no PR) prints a warning naming the required scope section.
- [ ] A2. full-check hard-fail behavior/exit codes unchanged with a PR present
  (existing tests stay green).
- [ ] A3. `SD_AI_COMMAND_PACK_SCOPE_CHECK=off` suppresses both early warning
  and existing check.
- [ ] A4. Twins byte-identical; `bash -n` + `node --check` clean; make test +
  make full-check green; version bumped with CHANGELOG.
