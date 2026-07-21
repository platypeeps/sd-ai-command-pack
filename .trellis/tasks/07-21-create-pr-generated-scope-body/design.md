# Auto-add generated scope to sd-create-pr PR bodies — Design

## Overview

Extend the `sd-create-pr` publication path so a PR whose entire diff is already
classified as bookkeeping/tooling-generated receives the recognized scope
section before the review handoff. Keep classification and heading recognition
owned by the existing PR-body scope machinery rather than embedding glob rules
in the orchestration skill.

## Proposed Flow

1. After the base branch is fetched and the intended commit set is known,
   obtain the changed-path set against `origin/<base>`.
2. Ask a pack-owned classifier whether every changed path is covered by the
   tooling/generated category and whether any unmatched authored path exists.
3. If the caller supplied a body, leave it unchanged and use the current strict
   validation path.
4. If no body was supplied and the diff is not tooling/generated-only, retain
   the existing `gh pr create --fill` behavior.
5. If no body was supplied and the diff is tooling/generated-only, preserve the
   commit-derived title/body and append a concise recognized section such as:

   ```markdown
   Tooling/generated scope:

   - Changes are limited to generated or repository-bookkeeping surfaces.
   ```

6. Materialize the final Markdown through a secure temporary regular file and
   create or edit the PR with `--body-file` before Step 6 hands control to
   `sd-review-pr`.

Implementation research may choose either of these compatible mechanisms:

- compose the body before creation if GitHub's fill content can be reproduced
  without losing information; or
- create with `--fill`, fetch the resulting body, append the section, and edit
  via `--body-file` before review starts.

Prefer the second mechanism if it is the only way to preserve GitHub's exact
fill behavior. In both cases the PR must never enter review with a known-missing
required section.

## Contracts

- **Classification:** one pack-owned classifier determines
  tooling/generated-only eligibility; target-repository config remains
  authoritative.
- **Body preservation:** user-provided bodies are immutable unless the user
  explicitly asks for an edit.
- **Shell safety:** Markdown is file content, never shell syntax. Temporary
  files are regular files, option-safe, and removed through a trap.
- **Lifecycle:** standalone review handoff and private `sd-ship` Stage 1 return
  semantics remain unchanged.
- **Parity:** templates are source; installed/root mirrors are regenerated and
  byte-checked.

## Validation Matrix

| Case | Expected result |
| --- | --- |
| Only Trellis journal/task/map files | Auto-filled body gains tooling/generated section |
| Generated files plus authored runtime source | Existing fill path; no tooling-only claim |
| User supplies a compliant custom body | Body preserved; validation passes |
| User supplies a non-compliant custom body | Body preserved; existing validator reports the omission |
| Classifier unavailable or malformed | Stop before review with a concrete diagnostic |
| PR creation succeeds but body edit fails | Stop; do not enter review with incomplete scope metadata |
| Verified `sd-ship` Stage 1 | Publication result returned only after body compliance |

## Compatibility And Rollback

No public command or environment variable is added. Reverting the orchestration
and classifier changes restores the existing manual-body-correction behavior;
the validator and review gates remain independently authoritative throughout.

## Affected Surfaces

- `templates/.agents/skills/sd-create-pr/SKILL.md` and installed mirrors
- pack-owned PR-body classification/composition helper if an API extension is
  needed, plus its template/root pair
- `.trellis/spec/frontend/adapter-guidelines.md`
- `tests/test_sdlc_commands.py`, PR-body scope tests, install/parity tests
- `README.md` / `docs/SD_AI_COMMAND_PACK.md` and template mirrors when behavior
  is user-visible
