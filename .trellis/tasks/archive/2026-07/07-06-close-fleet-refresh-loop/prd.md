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

- [x] Every fleet repo: pack version 0.5.28 (or later), install audit
  exit 0, evidence linked.
- [x] All four outstanding thread/AC items resolved with links.
- [x] Archived PRDs reconciled; journal duplicate resolved with root
  cause noted.

## Reconciliation Evidence - 2026-07-09

Fleet inventory found five actual consumer repositories in the archived task
evidence and rollout history. The older "six consumer" wording described the
rollout PR stream, not a sixth distinct current repository. All five default
branches now carry `sd-ai-command-pack` provenance version `0.7.0`, satisfying
the `0.5.28 or later` floor:

- [`platypeeps/anomaly-metric-creator`](https://github.com/platypeeps/anomaly-metric-creator/blob/main/.sd-ai-command-pack/provenance.json):
  local install audit passed, 80 targets verified.
- [`platypeeps/rwbp-website`](https://github.com/platypeeps/rwbp-website/blob/main/.sd-ai-command-pack/provenance.json):
  temp default-branch clone install audit passed, 80 targets verified.
- [`platypeeps/rwbp-coordinator`](https://github.com/platypeeps/rwbp-coordinator/blob/main/.sd-ai-command-pack/provenance.json):
  local install audit passed, 91 targets verified; one repo-local legacy-name
  warning remains outside the pack payload.
- [`platypeeps/loadsmith`](https://github.com/platypeeps/loadsmith/blob/main/.sd-ai-command-pack/provenance.json):
  local install audit passed, 80 targets verified; stale command-name warnings
  remain in generated repo docs only.
- [`answerbook/mezmo_benchmark`](https://github.com/answerbook/mezmo_benchmark/blob/main/.sd-ai-command-pack/provenance.json):
  local install audit passed, 80 targets verified; one repo-local warning
  remains in a local review-cycle checker.

Named review-thread promises are resolved or obsolete on merged PRs:

- mezmo PR #313 comment
  [3522276141](https://github.com/answerbook/mezmo_benchmark/pull/313#discussion_r3522276141)
  was replied to and the thread is resolved; PR #313 merged on
  2026-07-04.
- anomaly-metric-creator PR #193 comment
  [3522597638](https://github.com/platypeeps/anomaly-metric-creator/pull/193#discussion_r3522597638)
  is resolved/outdated with shipped-fix evidence; PR #193 merged on
  2026-07-04.
- rwbp-website PR #85 comment
  [3522597484](https://github.com/platypeeps/rwbp-website/pull/85#discussion_r3522597484)
  is resolved/outdated with shipped-fix evidence; PR #85 merged on
  2026-07-04.
- loadsmith PR #48 comments
  [3522664869](https://github.com/platypeeps/loadsmith/pull/48#discussion_r3522664869),
  [3522664879](https://github.com/platypeeps/loadsmith/pull/48#discussion_r3522664879),
  and
  [3522664881](https://github.com/platypeeps/loadsmith/pull/48#discussion_r3522664881)
  are resolved/outdated with shipped-fix evidence; PR #48 merged on
  2026-07-04.
- mezmo PR #314 comment
  [3522423050](https://github.com/answerbook/mezmo_benchmark/pull/314#discussion_r3522423050)
  and rwbp-coordinator PR #75 comment
  [3522422385](https://github.com/platypeeps/rwbp-coordinator/pull/75#discussion_r3522422385)
  are resolved/outdated for the 0.5.12 traversal hardening follow-up; both
  PRs merged on 2026-07-04.

Duplicate Session 29/30 root cause is pack-owned, not Trellis-owned:
`scripts/sd-ai-command-pack-record-session.py` called Trellis
`add_session.py --no-commit`, then staged/committed the workspace itself. If
the Trellis append succeeded but the later pack-owned `git add` or
`git commit` failed, rerunning the wrapper called `add_session.py` again and
appended a duplicate. The wrapper now detects a modified journal whose latest
session heading matches the retry title and patches that existing entry before
staging/committing. Regression coverage:
`test_record_session_wrapper_reuses_uncommitted_retry_entry`.

Upstream issue 5 was not filed. Reroute recorded 2026-07-09: the duplicate
session root cause was fixed locally in
[sd-ai-command-pack PR #77](https://github.com/platypeeps/sd-ai-command-pack/pull/77),
and the issue draft remains in `07-07-file-upstream-trellis-issues` as
historical evidence marked "do not file".

## Superseding Inventory Note - 2026-07-10

The 2026-07-09 reconciliation evidence above undercounted the active consumer
fleet when it described five actual repositories. The current checked-in fleet
manifest and the 0.8.6 rollout task confirm six active consumers:
`platypeeps/anomaly-metric-creator`, `platypeeps/hoa-manager`,
`platypeeps/loadsmith`, `answerbook/mezmo_benchmark`,
`platypeeps/rwbp-coordinator`, and `platypeeps/rwbp-website`.

The correction landed with the 0.8.6 fleet rollout: all six consumer PRs were
merged green on 2026-07-10, all six post-merge install audits passed with
explicit expected platforms, and all six local checkouts ended clean on
`main` matching `origin/main`. Treat `hoa-manager` as a real fleet consumer in
future reconciliation and rollout work.

## Notes

- Origin: 2026-07-06 deep review Trellis-task cross-check. Process
  note for the future: substantial work in journal sessions 29-41
  (create-pr expansion PR #37, the --remove feature PR #38, PRs
  #43/#44, versions 0.5.20-0.5.26) shipped without Trellis tasks —
  consider restoring the task-per-change discipline going forward.
