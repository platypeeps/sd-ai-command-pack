---
title: Implementation — artifacts as product
item: 2026-08-29-artifacts-as-product
---

# Implementation plan

Ratchet: every step is one PR; each deletes what it replaces. Checkboxes track landed steps.

Dogfood from step 0: this redesign lives at `docs/work/2026-08-29-artifacts-as-product/`.

| Step | Content | Key check |
|---|---|---|
| **M0** | Tombstone plugin 0.72.0 | second-machine pointer exists |
| **0** | Kill release train + gate stack (delete the release/gate jobs — `release-payload-gate`, `main-push-scope`, `ci-result`, `auto-tag-release` + their preflight — of today's 9; `.githooks`, receipt validators, candidate ledger) | `git grep -l candidate-validation -- . ':!.trellis' ':!CHANGELOG.md' ':!docs'` = 0 (the .trellis hits fall at step 2; CHANGELOG is history, exempt); every remaining job green |
| **1** | One copy of every file (delete twins, mirrors, generators). Consumers cannot plugin-update between here and step 3 — acceptable **only because M0 is the terminal release**; M0 must be tagged before this lands | ≤2 copies of review script; M0 tag exists |
| **2** | `docs/work` replaces `.trellis` in pack; land sd_route.py + fixtures; delete hooks, journals, TRELLIS blocks | `ls .trellis` fails; sd-docs-lint green |
| **3** | Pack PR: new installer (M1 `--adopt-legacy`) + 12 skills + sd-review backends | scratch-repo sd-ship E2E; installer parity test green |
| **3-c** | Consumer PRs, **one per repo** (M2, 9 repos: trellis payload, router removal via `--remove-legacy`, dotfiles, path rewrites; for `mode: full` repos the same PR carries `sd-review setup-github` output — R3-D16 revised, pack PR proven green first) | per repo: zero trellis/router greps; CI green; full-mode repos: one routed PR each shows a `route()` plan in the check output |
| **P1** | Cross-platform sweep: delete 19 legacy gemini TOMLs (render 0 — r9b) + 19 opencode entries before re-render | `test ! -e ~/.gemini/commands/sd`; opencode `grep -c '^sd-'` = 12; 3 antigravity skill roots free of `sd-*` residue |
| **P2** | Vendor kimi agents ×5 + codex-rescue + 3 codex skills → uninstall kimi/codex plugins (kills both Stop gates) | vendored agents resolve post-uninstall |
| **P3** | installed.json canonicalization; dashboard lands on :8768 beside system one | `curl :8768/api/state` ≥10 repos; --dump diff empty |
| **P4** | Retarget nightly skill-proposal-accept routine (before step 5) | routine files an item or cleanly no-ops |
| **P5** | Agent hygiene (tools: declarations, agent entries in ~/.codex/config.toml — external format, D-C1 exemption — caveman fork drops review lane) | sd-status drift clean |
| **4** | Retire router repos (archive with pointers); delete remote half | `git grep -c remoteIntegration bin/` = 0 |
| **4b** | Reconcile r3 round-2 assumptions (schema, names); new index populated **alongside** the live system dashboard (collectors untouched until 6b) | issue table populates in one refresh; :8767 unchanged |
| **5** | Fold se-ai-command-pack (64 skills + 5 agents, all renamed se-* → sd-*; machine locations replaced). **Vault-side first:** retarget the 8 scheduled-routine callers (`se-research` ×6, `se-scan` ×2 under `System/Scheduled Tasks/`) to `sd-*`, then delete old se-* renders | `grep -rln 'se-research\|se-scan' 'System/Scheduled Tasks/'` = 0 before deletion; count = 64; collision check vs 12 commands = 0; `ls ~/.claude/skills \| grep -c '^se-'` = 0; sdw-research resolves; next nightly routine run green |
| **5b** | `sd-skill-adopt` lands; retire skill-proposal-accept + file-trellis-task.py; delete legacy gito/prism skill folders (backend rows stay) | adopt-lint green on all installed skills |
| **6** | Machine cleanup = M3 (receipt-driven, legacy subdirs by name) | find both spellings = 0; plugin rows = 0; `handoff/` + `intents/` untouched (a packet written before the step is restorable after) |
| **6b** | Dashboard swap to :8767 (parity checklist complete); retire system dashboard collectors; delete system dashboard.py | `lsof -i :8767` one process; rm-test passes |
| **7** | Park backlog (D2), triage survivors, delete `migrate-trellis` (`migrate-vault` survives to step 11), verify protection, tag 1.0.0 | `grep -rli trellis` → archive only; sd-status ≤20 active; `sd-status --parked` lists every swept item |
| **8** | Plugin interface in backbone (manifest parser, sd store/plugin/config, vault driver, golden-corpus byte-compare) | direct-write-then-query freshness test green |
| **9** | Vault-side retarget of 6 pack.py callers, BEFORE deletion | `grep -rln pack.py 'System/Scheduled Tasks/'` = 0 |
| **10** | sd-writing-pack migration PR (manifest, store clients, delete ~1,280 LOC) | `grep -c 'System/Databases' pack.py` = 0; E2E on one piece |
| **11** | Vault move, **last** — per the r2 D12 per-base list (Skill Proposals → files store; Tips / Blog Ideas / Topics / Market Watch / Briefs / Prompts / TaskNotes / Learning → keep; empty Followups → retire — each confirmed by the user first), enumerated coordinated list in the PR; then delete `migrate-vault` | golden-corpus byte-compare (baseline captured at step 8, **before** any move) green; `migrate-vault` refuses if any reader still points at the old path; every vault routine's next run green |

## Step checklist

- [x] M0 — tombstone 0.72.0 (#596, tag v0.72.0 at fea7e133)
- [x] 0 — kill release train + gate stack. Verified 2026-08-29 by re-running the step's own
  check rather than by memory: the four unconditional jobs (`unittest`, `shell-coverage`,
  `lint`, `security`) are all that remain in `.github/workflows/`, and the release, payload-gate,
  `ci-result`, `main-push-scope` and auto-tag jobs are gone. (A fifth job, `bash 3.2 syntax`,
  was added on 2026-08-29 by R11-D5 — after this verification, and not a restoration of any
  deleted gate. `shell-coverage` goes at 3e per R11-D6, returning the count to four.) **The stated check was
  `candidate-validation` greps = 0 and it is 2**, so the gap is named instead of ticked past:
  `bin/sd-status` carries the string because it *detects* legacy residue by that name, and
  `templates/scripts/sd-ai-command-pack-review-preflight.mjs` is old-world payload that 3e
  deletes. Neither is a gate. When 3e lands, the second hit goes and only the detector is left.
- [x] 1 — one copy of every file. Check was "≤2 copies of the review script"; `git ls-files
  templates` matches exactly 2 (`review-local.py`, `review-preflight.mjs`), and tag `v0.72.0`
  exists, which was the precondition for landing this at all.
- [x] 2 — `docs/work` replaces `.trellis`; sd_route.py. `ls .trellis` fails, `bin/sd_route.py`
  and `tests/test_sd_route.py` are in place, and `sd-docs-lint` reports clean on this repo.
- [ ] 3 — new installer + 12 skills + sd-review backends. **Split into reviewable sub-PRs
  (2026-08-29): step 3 replaces ~56k LOC of `templates/scripts/` + `installer/` with ~7k under
  `bin/`; landing that as one pull request would be unreviewable, and the old world must keep
  working until the new installer is proven. Sub-PRs land on `main` in order, each independently
  green; 3-c does not begin until all of them have landed, so the "consumers cannot plugin-update
  between step 1 and step 3" window is unchanged.**
  - [x] 3a — `bin/sd_lib.py` + `bin/sd-check` (#601); `bin/sd-handoff` + `bin/sd-handoff-restore` (#602, R10-D3). Additive only.
  - [x] 3b — `bin/sd-status` + `bin/sd-pr-state` (#603). Read-only, GitHub-derived. `sd-status` reports
    branch-protection **enforcement state**, not just presence: `enforce_admins`, `strict`, the
    required contexts diffed against the checks the repo's workflows actually produce, and the
    PR-review requirement. Each missing leg prints as a named gap. This is what makes the
    merge-authority doctrine conditional in tooling rather than only in prose (critique 4).
  - [x] 3c-review — `bin/sd-review` + provider seam + backends + `sd-review.json` policy.
    The local lane only: `sd-check` → `route()` → backends on the exact diff → findings
    dispositioned locally and never posted. `setup-github` is deliberately **not** in this
    PR (it writes workflow files into other repos); the seam it will need is named
    `SETUP_GITHUB_SEAM` in `bin/sd-review`.
  - [x] 3c-cwd — **R10-D6 follow-up, found while reviewing 3c-review.** Two shipped sd-*
    commands take a repository path: `bin/sd-check --repo` and `bin/sd-docs-lint --repo`.
    R10-D6 says every sd-* command resolves its repo from cwd only, and `bin/sd-review`
    already holds that line with a structural test. Remove both options and land the
    verb-inventory test the design promises — one that enumerates `bin/` from the
    filesystem and asserts no sd-* command accepts a repo path, rather than checking the
    files someone remembered to list. `migrate-*` is out of scope: a migration tool
    targeting a consumer checkout is what it is for, and it is deleted at step 7.
  - [ ] 3d — the 12 command skills + templates
  - [ ] 3e — new machine-scope `install.py` + `installed.json` + parity tests; deletes the legacy
        `templates/scripts/**`, `installer/**`, and `manifest.json` once the E2E passes
- [ ] 3-c — consumer removal PRs (9) incl. `setup-github` for full-mode repos
- [ ] P1 / P2 / P3 / P4 / P5 — platform sweep (renamed from `3a`–`3e` on 2026-08-30;
      the step-3 sub-PRs keep those letters, which five merged PRs already cite)
- [ ] 4 / 4b
- [ ] 5 / 5b
- [ ] 6 / 6b
- [ ] 7 — tag 1.0.0
- [ ] 8 / 9 / 10 / 11

## Risks (consolidated)

- Step 0 is the largest PR (pure deletion); mitigated by all-remaining-jobs-green check.
- Regrowth: same author, 2,968 commits/60d. Defenses: standing rules, CI LOC caps, no release
  train, r7's measured journal-rebirth checks, per-mechanism deletion criteria.
- Two dashboards during 3c→6b window (parity checklist owns swap date). Phone-write regression only
  if D14 picks (a)/(b); (c) is the proposed default.
- Codex/Copilot-CLI sessions run without per-repo local guidance in v1 (D15/D16 accepted).
- Autonomous lane is the plan's only unattended writer. Bounded by worktree isolation, draft-
  only PRs, `--cap`, and wall-clock budgets — but a bad run still costs review attention on
  drafts nobody asked for. `--cap 3` default is deliberately small; raise only on evidence.
- R10-D3 reopens SessionStart, the surface the journals grew from. Bounded by explicit-write-
  only, 8 KB, consumed-once, 14-day expiry — but the regrowth pressure is real and the
  60-day criterion must actually be checked, not assumed.
- Vault driver is a second note-writer — bounded by verbatim port + golden-corpus byte-compare.
- Copilot round volume only partially addressed; Copilot cloud can't see untracked conventions
  (user-committed stanza SUGGEST only).
- Unverified items carried honestly: OpenCode instructions live-probe, Antigravity paid-tier/
  opt-out/skill-root/non-TTY output (V1′/V2′/P1/P2), Copilot billing API from personal account,
  greptile semantics, plugin-uninstall scope semantics (M3 checks outcomes, not commands).

## Verification (end-to-end)

After step 3: scratch repo with preexisting `docs/adr/` + Makefile → `sd-plan demo`, edit, `sd-ship`
→ PR merged; `git status --porcelain` shows only `<work>/**` (adoption purity, B5a); markdown-only
branch routes skip $0.00; requirements.txt-only routes standard. After 3c: dashboard `--dump` diff
empty; derive_status fixture parity across lint/status/indexer. After 6: dual-spelling find = 0;
rm-test (cache+state) loses acks/intents/time only. After 8–10: direct vault write visible to next
`sd store query`; golden-corpus byte-compare green; every sdw flow E2E on one test piece. After 7,
60 days: R10-D3 criterion — packets auto-loaded >= 5 and median age at load <= 7d, else
delete the hook; packet files never exceed 8 KB and never appear in `git status`;
R10-D1 criterion — items merged via `--agent codex` >= 5, else delete the flag; restore-hook
matrix: `clear` restores, `compact`/`resume` leave the packet untouched, `SD_HANDOFF_RESTORE=0`
leaves it untouched, EnterWorktree write + fresh-session restore in that worktree meet on one
digest, reused-path packet refused via `git cat-file -e`, fork-origin switch restores with a
warning;
`chore: record journal` = 0; share of non-merge commits touching only work/archive/index
paths < 5% (vs 49% baseline); `git log main --format=%b | grep -c '^wip:'` = 0; no `make check`
staleness in claude-mem for two weeks; sd-handoff meets its usage criterion or folds back to docs.
