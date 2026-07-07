# Harden Obsidian KB runtime artifact exclusions

## Goal

Exclude Trellis runtime and backup artifacts from Obsidian KB source discovery so generated LLM-KB output is stable and repo-relevant.

## Problem

The Obsidian KB updater currently scans useful repo documentation, but its Trellis exclusion logic only skips generic excluded parts and `.trellis/workspace`. A local Trellis backup directory was discovered during review:

- a gitignored local `.trellis/.backup-<timestamp>/` tree (observed as
  `.backup-2026-07-06T01-42-40`) containing a copy of
  `trellis-meta/references/platform-files/agents.md`

That backup copy mapped into the generated KB as `Other Documentation/agents.md`, causing:

```text
python3 scripts/sd-ai-command-pack-update-spec-kb.py --check
...
conflicts:
  - Other Documentation/agents.md is not current
```

This makes the LLM-KB output depend on local Trellis runtime state instead of the repository's durable documentation.

## Requirements

- Update `scripts/sd-ai-command-pack-update-spec-kb.py` so source discovery excludes Trellis runtime and backup artifacts without excluding durable Trellis knowledge.
- Exclude at least:
  - `.trellis/.backup-*`
  - Trellis cache folders named `.cache`
  - Trellis runtime folders named `.runtime`
  - `.trellis/workspace`
  - Trellis worktree folders named `worktrees`
- Preserve inclusion of durable Trellis documentation that is useful to the KB, such as `.trellis/spec/`, `.trellis/tasks/`, `.trellis/workflow.md`, and other tracked repo guidance.
- Add focused regression coverage for hidden/runtime Trellis folders so future local artifacts cannot leak into the KB.
- Ensure existing generated KB naming and category behavior is unchanged for normal repo-owned source files.
- Keep the check deterministic when ignored local files exist in the working tree.

## Acceptance Criteria

- [ ] `python3 scripts/sd-ai-command-pack-update-spec-kb.py --check` passes in a checkout that contains a `.trellis/.backup-*` folder.
- [ ] Regression tests prove backup/runtime Trellis files are excluded while durable Trellis docs remain eligible.
- [ ] Existing `.obsidian-kb` copy generation still produces self-contained documents and dashboard links.
- [ ] No generated KB destination is sourced from Trellis backup, cache, runtime, workspace, or worktree folders.
- [ ] `python3 -m unittest discover -s tests` passes.
- [ ] `git diff --check` passes.

## Implementation Notes

- Start with `is_excluded()` in `scripts/sd-ai-command-pack-update-spec-kb.py`.
- Prefer path-aware checks over broad string matching so `.trellis/spec` and `.trellis/tasks` stay included.
- Add the regression in the existing KB-related test area before changing behavior, then make the smallest code change that satisfies it.

## Notes

- This task is the highest-priority follow-up from the architectural review because it affects the correctness of generated LLM-KB artifacts across consumer repos.
