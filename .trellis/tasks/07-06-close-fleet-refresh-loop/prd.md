# Close the fleet refresh loop and reconcile task records

## Goal

The single biggest open thread across the entire task history is the
six-consumer-repo fleet refresh loop, and the archive/journal never
record it closing:

- Six archived tasks (07-03-provenance-hardening,
  07-03-audit-traversal-hardening, 07-03-pack-shell-lint,
  07-03-empty-root-cd-guard, 07-04-cd-option-terminator, plus the
  recorder series 0.5.16-0.5.19) all carry unchecked "fleet refresh
  PRs updated / threads answered (post-merge step)" acceptance
  criteria.
- 07-03-provenance-overwritten-fix has an unchecked PRE-merge AC:
  "AMC #193 and website #85 branch worktrees pass the install audit
  after re-running the fixed installer".
- 07-03-audit-followups has an unconfirmed external follow-through:
  answer mezmo PR #313 comment 3522276141 against the shipped fix.
- Journal Session 41 (2026-07-06) records 0.5.28 rollout PRs being
  OPENED across the fleet; no merge is recorded anywhere.
- Journal integrity: Sessions 29 and 30 are byte-identical duplicates
  (a recorder double-write) — worth a quick root-cause look given the
  recorder-hardening series.

## Requirements

- R1: Enumerate the consumer fleet (the six repos referenced across
  the archived tasks: mezmo_benchmark, anomaly-metric-creator,
  rwbp-website, rwbp-coordinator, loadsmith, + remaining) and verify
  each is on pack 0.5.28 with a passing install audit; merge or
  refresh the open rollout PRs as needed.
- R2: Answer/resolve the outstanding review-thread ACs: mezmo #313
  comment 3522276141, AMC #193, website #85, loadsmith threads from
  0.5.15.
- R3: Update the archived tasks' PRDs: check off ACs now satisfied,
  or annotate ones that are moot, so the archive reads true.
- R4: Investigate the Session 29/30 duplicate journal write in
  `sd-ai-command-pack-record-session.py` / `add_session.py`
  interaction; fix or file a follow-up if a double-fire path exists;
  deduplicate the journal entries. (Duplicate bodies verified
  byte-identical on 2026-07-07.) An upstream bug-report draft exists in
  `07-07-file-upstream-trellis-issues` (issue 5) — file it upstream if
  the root cause is in Trellis-owned `add_session.py`, otherwise fix
  here and update that draft.
- R5: Record completion in the journal so the loop is visibly closed.

## Acceptance Criteria

- [ ] Every fleet repo: pack version 0.5.28 (or later), install audit
  exit 0, evidence linked.
- [ ] All four outstanding thread/AC items resolved with links.
- [ ] Archived PRDs reconciled; journal duplicate resolved with root
  cause noted.

## Notes

- Origin: 2026-07-06 deep review Trellis-task cross-check. Process
  note for the future: substantial work in journal sessions 29-41
  (create-pr expansion PR #37, the --remove feature PR #38, PRs
  #43/#44, versions 0.5.20-0.5.26) shipped without Trellis tasks —
  consider restoring the task-per-change discipline going forward.
