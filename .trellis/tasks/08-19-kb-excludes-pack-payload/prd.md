# Stop copying pack-installed payload into the Obsidian KB

## Goal

`scripts/sd-ai-command-pack-update-spec-kb.py` copies every platform-adapter
tree it finds into the consumer's Obsidian KB, without distinguishing content
the repository owns from payload this pack installed. The result is the same
pack payload duplicated into eight separate vaults. Exclude the installed
payload and keep the repository-owned guidance.

## Problem

Operator decision, 2026-08-19, from the same fleet review that produced
`08-18-fleet-repomix-map-staleness`. Surveyed by enumerating the checkouts from
`docs/fleet/consumers.json` and reading each vault under
`~/Documents/sdelmas-llm-wiki/raw/<repo>`:

| Consumer | Files in "Agent and Platform Guidance" |
| --- | --- |
| se-ai-command-pack | 183 |
| rwbp-coordinator | 104 |
| rwbp-website | 103 |
| hoa-manager | 102 |
| mezmo_benchmark | 102 |
| loadsmith | 96 |
| anomaly-metric-creator | 96 |
| sd-github-review | 84 |

The section is populated from `PLATFORM_GUIDANCE_ROOTS`
(`scripts/sd-ai-command-pack-update-spec-kb.py:96`), which lists eighteen
adapter roots — `.agents`, `.claude`, `.gemini`, `.github`, `.opencode`, and
the rest. Most of what lands there is this pack's own installed payload:
`claude-*.md` command files, `codex-*.md`, `claude-settings.json`. The same
bytes, eight times over, with the pack source checkout as the real home.

This has no effect on any consumer's tracked tree. `.obsidian-kb` is a symlink
to `~/Documents/sdelmas-llm-wiki/raw/<repo>` in all eight checkouts, is ignored
by the pack-managed `/.obsidian-kb` rule, and `git ls-files .obsidian-kb`
returns nothing in every one. The cost is vault noise and duplicated review
surface, not repository pollution.

## Requirements

- Exclude pack-installed payload from the KB copy. Decide membership from the
  consumer's own `.sd-ai-command-pack/installed-targets.txt` receipt, not from
  `PLATFORM_GUIDANCE_ROOTS`. The roots are the whole adapter surface, and
  excluding them wholesale would also drop guidance the repository owns —
  `anomaly-metric-creator`'s `.agents/skills/amc-server-compatibility/`,
  Trellis's `.claude/agents/trellis-*.md`, and the repository-authored parts of
  `.github/copilot-instructions.md` are all in those roots and none of them is
  pack payload. The receipt already draws the line, and it is present on disk in
  every consumer.
- Leave `ensure_gitignore()` and the helper's exit-code semantics untouched.
  `.trellis/spec/tooling/fleet-publish-generated-content.md` documents that the
  publish path reads the file rather than the exit status precisely because this
  helper writes the ignore block before it copies anything, then exits `3` when
  only KB copies conflict and `2` on a hard `OSError` partway through. A change
  to copy behavior must not perturb either.
- Handle a consumer whose receipt is absent or unreadable by copying as it does
  today rather than by excluding everything. A missing receipt is not evidence
  that a file is pack payload.
- Do not delete already-copied payload from existing vaults as part of this
  change unless the helper's normal reconciliation already removes files that
  are no longer selected. If it does not, say so and leave cleanup to the
  operator.

## Acceptance Criteria

- [ ] For every consumer enumerated from `docs/fleet/consumers.json`, no file
      listed in that consumer's `.sd-ai-command-pack/installed-targets.txt`
      appears in its vault under `~/Documents/sdelmas-llm-wiki/raw/<repo>`.
- [ ] Repository-owned adapter content still appears. Verified against at least
      `anomaly-metric-creator`, whose `.agents/skills/amc-server-compatibility/`
      and `.claude/agents/trellis-*.md` are not pack payload and must survive.
- [ ] A consumer with no readable receipt produces the same KB content it does
      today.
- [ ] `ensure_gitignore()` behavior and the exit-2 / exit-3 contract are
      unchanged, with the existing tests covering them still passing.
- [ ] The disposition of payload already copied into existing vaults is stated
      explicitly: either the helper's normal reconciliation removes it on the
      next run, verified against one vault, or the task records that it does not
      and names the manual cleanup the operator owns. An unstated outcome here
      leaves eight vaults in an unknown state and does not satisfy this
      criterion.

## Out of scope

- Untracking `docs/repomix-map.md` and excluding pack surfaces from the
  generated map. That is the operator's other decision from the same review and
  is owned by `08-18-fleet-repomix-map-staleness`.
- Any change to which repositories have a KB, or to the `.obsidian-kb` symlink
  and ignore-block arrangement, which is uniform and correct across all eight.
