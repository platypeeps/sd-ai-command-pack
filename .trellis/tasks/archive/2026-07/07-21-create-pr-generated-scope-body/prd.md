# Auto-add generated scope to sd-create-pr PR bodies

## Goal

Prevent bookkeeping-only pull requests created through `sd-create-pr` from
failing their first deterministic review gate solely because GitHub's
auto-filled body omitted the required `Tooling/generated scope:` section.

## Background

AMC PR #294 was created with `gh pr create --fill` after Trellis task archival,
journal recording, and a generated repository-map refresh. The branch changed
only Trellis bookkeeping and generated-map files, but the first
`sd-ai-command-pack-review-full-check.sh` run failed because the auto-filled PR
body did not contain a recognized tooling/generated scope heading. The body was
then edited manually and the next gate passed.

The pack already owns both sides of this contract:

- `templates/.agents/skills/sd-create-pr/SKILL.md` allows `--fill` when no
  custom body is supplied and requires literal `--body-file` handling for any
  generated Markdown.
- `templates/scripts/sd-ai-command-pack-pr-body-scope.py` and
  `templates/scripts/sd-ai-command-pack-review-scope.sh` classify changed paths
  and recognize `Tooling/generated scope:` headings.
- `.trellis/spec/frontend/adapter-guidelines.md` requires secure temporary-file
  creation and cleanup whenever `sd-create-pr` supplies generated Markdown.

## Requirements

- When `sd-create-pr` has no user-provided body and the branch diff is
  bookkeeping/tooling-generated-only, preserve the normal auto-filled PR title
  and summary while adding a recognized `Tooling/generated scope:` section
  before entering `sd-review-pr`.
- Use one existing pack-owned scope classification contract as the source of
  truth; do not create a second divergent path-pattern list in the skill.
- Do not add a tooling/generated section when authored implementation or other
  unmatched product files make the diff mixed-scope.
- Never overwrite or silently rewrite a user-provided PR body. Existing custom
  body validation remains authoritative.
- Materialize every generated or edited Markdown body through a secure regular
  temporary file and pass it only via `gh pr create --body-file` or
  `gh pr edit --body-file`; preserve option-safe cleanup on success, failure,
  and interruption.
- Apply the behavior to both standalone `sd-create-pr` and the verified
  `sd-ship` Stage 1 delegation without changing their lifecycle ownership or
  public invocation contracts.
- Update `templates/**` first, synchronize installed/root mirrors, and preserve
  generated-parity and install-audit guarantees.
- Add deterministic tests for classification, body composition, custom-body
  preservation, mixed-scope behavior, temporary-file safety, and both
  orchestration modes.

## Acceptance Criteria

- [ ] A bookkeeping-only branch created with the default fill path reaches
      `sd-review-pr` with a recognized `Tooling/generated scope:` section and
      retains the commit-derived title/body content.
- [ ] The first deterministic full-check passes the tooling/generated PR-body
      gate without a manual `gh pr edit` step.
- [ ] A mixed implementation-plus-generated diff does not receive a misleading
      automatic tooling-only declaration.
- [ ] A user-provided body is preserved byte-for-byte and remains subject to
      the existing scope validator.
- [ ] Generated Markdown never appears in an inline shell `--body` argument;
      tests cover secure temporary creation and cleanup paths.
- [ ] Standalone `sd-create-pr` still enters `sd-review-pr`, while verified
      `sd-ship` Stage 1 still returns after publication.
- [ ] Template/root copies, platform adapters, tests, and documentation remain
      synchronized; `make check` and the pack full-check pass.

## Out of Scope

- Auto-writing product, automation, CI, or user-facing documentation scope
  narratives for mixed PRs.
- Weakening or bypassing the existing PR-body scope checks.
- Changing remote-review, merge, finish-work, or housekeeping ownership.
- Opening a PR or starting implementation as part of this planning task.

## Open Questions

None blocking. Implementation research should choose the smallest way to reuse
the existing classifier while preserving GitHub's auto-filled content.
