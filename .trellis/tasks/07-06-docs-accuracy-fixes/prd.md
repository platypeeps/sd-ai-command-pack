# Fix documentation accuracy gaps

## Goal

Fix the documentation defects that sit in the blind spots of the
pack's otherwise excellent drift gates (2026-07-06 deep review):

1. **`SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR` documented nowhere**
   (HIGH): used in `templates/.agents/skills/sd-review-pr/SKILL.md:66,73`
   (the error message instructs users to set it) and exported in
   `sd-create-pr/SKILL.md:213`; zero hits in README.md and
   `docs/SD_AI_COMMAND_PACK.md`. Root cause: the full-check drift gate
   only requires SCRIPT-read vars to be documented; skill-only vars are
   exempt (full-check.sh:618-627).
2. **Two dead TOC anchors in the guide shipped to every consumer**
   (HIGH): `docs/SD_AI_COMMAND_PACK.md:16` links `#local-commands` but
   the heading is `## Commands`; line 18 links
   `#install-or-refresh-this-pack` but the heading is
   `## Updating the pack`. Template twin has the same bug.
3. **AGENTS.md lacks the templates-are-source-of-truth rule** (LOW):
   the crucial "root copies are byte-verified mirrors of templates/**;
   review the templates side" note exists only in
   `.github/copilot-instructions.md:1-10` where non-Copilot agents
   never see it. The Trellis-managed block in AGENTS.md explicitly
   preserves outside edits, so a paragraph can be added.
4. **Truncated per-command platform lists in README** (LOW): e.g.
   README:91-92/111-112/123-124 name 4 platforms where the full
   mapping (README:79-84) covers far more. Replace parentheticals with
   "(see platform mapping above)".

## Requirements

- R1: Document `SD_AI_COMMAND_PACK_REVIEW_PR_SELECTOR` in
  `docs/SD_AI_COMMAND_PACK.md` and README's configuration quick
  reference.
- R2: Widen the full-check drift gate to include user-facing
  skill-only env vars in the undocumented-var check (so this class
  cannot recur), or record an explicit decision not to.
- R3: Fix both TOC anchors in `templates/docs/SD_AI_COMMAND_PACK.md`
  first, then re-sync the installed copy; verify all remaining
  quick-link anchors resolve.
- R4: Add the templates-source-of-truth paragraph to AGENTS.md outside
  the Trellis block.
- R5: Fix the truncated platform lists.

## Acceptance Criteria

- [ ] Grep finds the selector var documented in both surfaces; drift
  gate decision recorded.
- [ ] All docs-guide quick links resolve to existing headings
  (template and installed copies identical).
- [ ] Full battery green (drift gates pass); template twins
  byte-identical.

## Notes

- Origin: 2026-07-06 deep review (Docs findings 1, 6, 5, 7).
