# Planning adversarial review — 0.64.5 followup hardening

Contract: `.claude/sd-ai-command-pack/planning-adversarial-review.md`.
Reviewers: host (this agent) + Codex CLI (`codex exec --sandbox read-only --ephemeral`).
Passes run: 3 (initial + 2 remediation re-reviews) — contract cap reached.

## Verdict

**In-scope planning artifacts UNBLOCKED on host review.** All concerns that apply
to what 0.64.5 actually ships (A + C + B-fleet) are CLOSED. The one round-3 blocker
that touched deliverability (M-1) was resolved by removing B-store from the release
and handing it upstream; its sub-concerns (M-2, M-3) moved with it as requirements
on the upstream task and no longer bind any 0.64.5 deliverable.

**Honesty caveat (verification discipline):** the final remediation (Option A —
scoping B-store out) landed AFTER the 3rd/final review pass, so it was validated by
host review only; the Codex pass budget is exhausted and it was not re-reviewed by
Codex. The change is subtractive (removes a scope, files a handoff task), which is
low-risk, but "Codex-confirmed" is NOT claimed for it. This also means 3 remediation
rounds were used vs. the contract's nominal 2 — recorded here rather than hidden.

## Concern ledger

### Round 1 (initial) — C-1..C-9

| ID  | Concern | Disposition |
|-----|---------|-------------|
| C-1 | Completing the archive commit in fleet-publish skips `after_archive` hooks | ADDRESSED r1 — retry designed inside task_store (preserves hook lifecycle). Later mooted by M-1 (retry moved upstream); the pack no longer completes the commit. |
| C-2 | `git add -A` in fleet-publish stages unrelated work | ADDRESSED r1 — scoped staging preserved; no `git add -A`. Reaffirmed by loud-abort design. |
| C-3 | Stranded archive move on consumer failure | ADDRESSED — superseded by N-1 resolution (loud abort, no rollback). |
| C-4 | Retry key too broad (task.py's generic "Archive moved on disk" string) | ADDRESSED r1 — key on the commit's git stderr. Tightened further by M-3 (`index.lock` anchor) in the upstream spec. |
| C-5 | Test only exercised the advisory `lstat` branch; authoritative untested | ADDRESSED r1 — added authoritative-branch test (mock `os.lstat` regular → real `os.open(O_NOFOLLOW)` raises ENOTDIR). Codex pass-2/3 confirmed. |
| C-6 | Mirror edit order reversed (must be `templates/` first) | ADDRESSED r1 — Phase A edits `templates/` first, then syncs `scripts/`. |
| C-7 | C-phase test coverage (message assert + `main()` propagation) | ADDRESSED r1 — C3 asserts sd-finish-work message + `main()` exit-code propagation. Codex pass-3 confirmed (`main()` returns `error.code`). |
| C-8 | Stale caller-rewording claim + path-leakage AC conflict | ADDRESSED r2 — parent PRD now verify-only, repo-relative path explicitly allowed; consistent with child A + design §A. Codex pass-3 confirmed ADDRESSED. |
| C-9 | Recovery schema-mismatch already fixed → must be out of scope | ADDRESSED r1 — marked out of scope; `recovery-artifacts.py:459` already emits expected-vs-actual. Codex pass-3 confirmed. |

### Round 2 — N-1

| ID  | Concern | Disposition |
|-----|---------|-------------|
| N-1 | B's "roll back to pre-archive state" is incomplete — cmd_archive also writes status=completed, detaches children, clears sessions before the move (task_store.py:473-506); a dir+index-only rollback restores none of that | ADDRESSED r2 (user Option 1) — dropped rollback entirely. fleet-publish now FAILS LOUDLY (PublishError + recovery guidance), attempts no rollback. Nothing left to be incomplete. Codex pass-3 confirmed ADDRESSED. |

### Round 3 — M-1..M-3

| ID  | Concern | Disposition |
|-----|---------|-------------|
| M-1 | B-store patches `.trellis/scripts/common/task_store.py`, a Trellis-owned runtime copy the pack does not ship — README "Upstream Path" forbids it; the fix wouldn't survive a Trellis update or reach consumers | ADDRESSED r3 (user Option A) — B-store removed from 0.64.5; retry handed to the Trellis source owner as task `08-04-trellis-upstream-archive-commit-lock-retry`. The pack no longer patches Trellis-owned code. Host-verified (Codex budget exhausted). |
| M-2 | Plan said non-lock failure "returns False unchanged," but current code returns `not source_was_tracked` (True for untracked tasks) | RELOCATED r3 — no longer in 0.64.5 scope; captured as an explicit requirement on the upstream task (preserve `not source_was_tracked`, test tracked + untracked). |
| M-3 | `Unable to create` / `File exists` as standalone retry markers would match unrelated failures | RELOCATED r3 — no longer in 0.64.5 scope; upstream task requires anchoring the retry key on the `index.lock` substring. |

## 0.64.5 delivered scope (post-review)

- **A** — sibling-loader `ENOTDIR → missing` (both branches, both twins, templates-first;
  advisory + authoritative tests; caller wording verify-only; repo-relative path OK).
- **B** — pack-owned consumer safety only: `fleet-publish.py archive_and_journal`
  fails loudly on a non-zero archive result (PublishError + recovery), no rollback.
  Framework retry handed upstream.
- **C** — fleet-publish self-publish guard (bookkeeping-CI fingerprint → PublishError
  code 3 naming sd-finish-work) + consumer-only docs.
- **R** — version bump 0.64.5, CHANGELOG (A/B/C, B = fleet loud-abort only), release-prep, check, PR, tag.

## Out of this release (filed)

- `08-04-trellis-upstream-archive-commit-lock-retry` (standalone) — Trellis-owned
  archive auto-commit index-lock retry, carrying M-2 + M-3.

## Gate status

Planning-review gate is satisfiable for 0.64.5 on host review. Implementation
(`task.py start`) awaits explicit user go-ahead. No fleet campaign until the user
explicitly asks (standing constraint).
