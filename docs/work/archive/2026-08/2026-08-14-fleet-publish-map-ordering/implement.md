# Implementation plan

## 1. Guard

Edit the payload source, `templates/scripts/sd-ai-command-pack-review-preflight.mjs`.
`scripts/sd-ai-command-pack-review-preflight.mjs` is the installed copy and is
rewritten by `make sync`; editing it directly is lost on the next sync.

- [x] Add `generatedStructuralMaps: ['docs/repomix-map.md']` to
      `defaultConfig()`, and add the key to the array-merge list in
      `loadConfig` so a repository can extend it (array keys union).
- [x] Add `parseGeneratedStructuralMapEntries(text)` (skipping backtick-fence
      lines) returning
      `{ entries: [{path, line}], parsed: bool, reason }`, confined to the
      `# Directory Structure` section, rejecting odd or skipped indentation.
- [x] Add `checkGeneratedStructuralMapPaths()`: for each configured map that
      exists, parse it, then `fail` for each `.trellis/`-prefixed entry whose
      path does not `exists()`. Cap at 20 reported failures plus a remainder
      count. `pass` with a stated reason when there is nothing to check.
- [x] Register it in `runReviewPreflight` after
      `runCheck('documentation path references', ...)`.

## 2. Ordering

- [x] Rewrite the `pr-publication` bullet in
      `.agents/skills/sd-fleet-refresh/SKILL.md` as the four-step sequence from
      `design.md`, keeping the existing head-advance and corrective-recovery
      sentences intact at the end.
- [x] Add the non-helper fallback sentence (regenerate the map after
      `task.py archive`, before the finish-work push).
- [x] Update the numbered rollout steps 4-6 in `docs/FLEET_ROLLOUT.md` (run
      `candidatePrepare` and commit; classify; push and open the PR) so their
      order matches, and point at the skill as the single statement of the
      sequence.

## 3. Tests

- [x] `tests/test_review_preflight.py`:
      - map naming a missing `.trellis/tasks/<slug>/prd.md` fails, and the
        message names file, line, and path;
      - map whose `.trellis/` entries all exist passes;
      - repo with no `docs/repomix-map.md` passes;
      - map with no `# Directory Structure` section passes;
      - map whose missing entries are all outside `.trellis/` passes;
      - malformed indentation warns and does not fail.

## 4. Release plumbing

- [x] `make generate`, then `make sync` to install the edited template into
      `scripts/`.
- [x] Bump `manifest.json` version and add the `CHANGELOG.md` section; the
      Release payload gate requires it because shipped payload changed.

## Validation

- [x] `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_review_preflight -v`
- [x] Full suite: `make check` / the typed `sd-check` gate.
- [x] Negative proof: reproduce the campaign defect by hand — archive a task,
      leave the map naming the pre-archive path, and confirm the new check
      fails; regenerate and confirm it passes.

## Rollback

Each of the three parts is independent. Reverting the check leaves the
documented ordering intact; reverting the docs leaves the check enforcing the
outcome. Reverting both returns to the current state with no migration.
