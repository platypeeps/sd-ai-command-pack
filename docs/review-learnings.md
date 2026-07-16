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
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: The Session 107 entry describes install-audit gitignore batching, but the Main Changes bullets were updated to audit follow-up items (A-027/ledger/task metadata). This makes the journal entry internally inconsistent; th... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: Session 107 Testing now lists commands and PR #132 verification, which does not match the Session 107 scope/date (install-audit batching on 2026-07-15). This should be reverted (and the detailed testing belongs in the S... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: Session 118 Summary states the concrete audit follow-up work performed, but Main Changes still says no bullets were supplied. This is inconsistent with the summary (and with the bullets currently placed under Session 10... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: Session 118 Testing says validation was not recorded, but this PR description (and the commands currently recorded under Session 107) indicates verification was performed. Consider recording the actual validation steps ... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/audit/report-2026-07-16-follow-up.md`: This follow-up report references PR #131 CI being green, but the follow-up artifacts for this change set are tracked as PR #132 elsewhere in this PR (journal entry, summary). To avoid confusion, the report should refere... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: This "Main Changes" list is under Session 108 (installer layout docs/versioning policy), but the bullets describe the A-027 audit follow-up work. This makes the session record internally inconsistent with the session ti... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #132 `.trellis/workspace/sdelmas/journal-3.md`: This "Testing" list is under Session 108 but records commands/PR validation for the later audit-follow-up PR (#132). The testing section should reflect Session 108’s own validation, or fall back to the prior placeholder... (https://github.com/platypeeps/sd-ai-command-pack/pull/132)
- **historical** PR #131 `installer/fileops.py`: The apply-path reuse of `planned_result` runs before the `destination.is_symlink()` / existence checks, so a target that changes between preflight and apply (e.g., created as a symlink or file by another process) can be... (https://github.com/platypeeps/sd-ai-command-pack/pull/131)
- **historical** PR #130 `.trellis/spec/backend/manifest-and-filesystem.md`: The shipped helper library section lists `run_command(..., env, ...)` and `repo_root(start)`, but `scripts/sd_ai_command_pack_lib.py` (added in this PR) does not expose an `env` parameter and `repo_root` takes `fallback... (https://github.com/platypeeps/sd-ai-command-pack/pull/130)

### Suggested Preventive Actions
- Move repeated mechanical findings into local checks where possible.
- Keep Copilot instructions focused on current, non-outdated unresolved findings.
- Treat generated or copied payloads as source/sync-contract review surfaces, not style-review surfaces.
<!-- sd-review-learnings:end -->
