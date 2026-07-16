# Review Learnings

## Curated Lessons

- When editing Trellis journal entries, target the intended session heading
  explicitly. Avoid broad replacement of fallback text such as "Detailed change
  bullets were not supplied" or "Validation was not recorded"; older sessions
  often contain the same fallback text and must remain historically accurate.
  The distributed review preflight now enforces this by rejecting changes to a
  review-base session older than the current session.

<!-- sd-review-learnings:start -->
## SD Review Learnings

_Last updated: 2026-07-16_

### Local Pattern Findings
- No local review-cycle findings detected in the scanned diff.

### Recent Copilot Review Signals
- **historical** PR #133 `templates/scripts/sd-ai-command-pack-review-preflight.mjs`: `findHistoricalTrellisJournalSessionEdits` only flags sessions where the same session number exists in both baseline and current. If a historical session (present at the review base) is deleted or renumbered in the... (https://github.com/platypeeps/sd-ai-command-pack/pull/133)
- **historical** PR #133 `templates/scripts/sd-ai-command-pack-review-preflight.mjs`: `normalizeJournalSessionContent` normalizes line endings and trims the end of the block, but it does not normalize per-line trailing whitespace. The updated quality guidance explicitly calls out trailing-whitespace... (https://github.com/platypeeps/sd-ai-command-pack/pull/133)
- **current** PR #133 `tests/test_review_preflight.py`: The new historical-session guard is documented/spec’d to catch renumbering, but this test only covers modification, whitespace-only changes, and deletion. Consider adding an explicit renumbering regression (e.g.,... (https://github.com/platypeeps/sd-ai-command-pack/pull/133)
- **current** PR #133 `docs/review-learnings.md`: These auto-recorded “Recent Copilot Review Signals” bullets appear truncated mid-word (e.g., "th...", "S...") which makes the guidance hard to read and looks like an incomplete summarization/export. Consider... (https://github.com/platypeeps/sd-ai-command-pack/pull/133)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: The Session 107 entry describes install-audit gitignore batching, but the Main Changes bullets were updated to audit follow-up items (A-027/ledger/task metadata). This makes the journal entry internally... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: Session 107 Testing now lists commands and PR #132 verification, which does not match the Session 107 scope/date (install-audit batching on 2026-07-15). This should be reverted (and the detailed testing belongs in... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: Session 118 Summary states the concrete audit follow-up work performed, but Main Changes still says no bullets were supplied. This is inconsistent with the summary (and with the bullets currently placed under... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: Session 118 Testing says validation was not recorded, but this PR description (and the commands currently recorded under Session 107) indicates verification was performed. Consider recording the actual validation... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/audit/report-2026-07-16-follow-up.md`: This follow-up report references PR #131 CI being green, but the follow-up artifacts for this change set are tracked as PR #132 elsewhere in this PR (journal entry, summary). To avoid confusion, the report should... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: This "Main Changes" list is under Session 108 (installer layout docs/versioning policy), but the bullets describe the A-027 audit follow-up work. This makes the session record internally inconsistent with the... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: This "Testing" list is under Session 108 but records commands/PR validation for the later audit-follow-up PR (#132). The testing section should reflect Session 108’s own validation, or fall back to the prior... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #131 `installer/fileops.py`: The apply-path reuse of `planned_result` runs before the `destination.is_symlink()` / existence checks, so a target that changes between preflight and apply (e.g., created as a symlink or file by another process)... (https://github.com/platypeeps/sd-ai-command-pack/pull/131)

### Suggested Preventive Actions
- Move repeated mechanical findings into local checks where possible.
- Keep Copilot instructions focused on current, non-outdated unresolved findings.
- Treat generated or copied payloads as source/sync-contract review surfaces, not style-review surfaces.
<!-- sd-review-learnings:end -->
