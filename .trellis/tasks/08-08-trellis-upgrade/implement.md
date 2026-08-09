# Implementation plan: Trellis 0.6.7 → 0.6.14 upgrade

Branch: `chore/trellis-upgrade-0-6-14` off `main`. Commit 1: template
upgrade. Commit 2: status.py `--json` adoption + shipped-payload bookkeeping.
Commit 3: downstream evidence packets. Each separately revertable.

## Steps

1. **Preconditions + rollback baseline**
   - [ ] Working tree clean on `main`; create `chore/trellis-upgrade-0-6-14`.
   - [ ] `trellis --version` → 0.6.7 (record); `npm view @mindfoldhq/trellis
         version` → 0.6.14.
   - [ ] Record rollback baseline: `git status --porcelain` snapshot; copy
         `.trellis/.template-hashes.json` to the session scratchpad
         (gitignored — git cannot restore it); record content hashes of the
         gitignored protected files `.trellis/.developer` and
         `.trellis/.current-task`: presence/absence for both, plus content
         hash for each present file — `git status` cannot see them, so
         post-apply protection is proven by comparing this record (an
         absent file must remain absent, not just unhashed).
2. **Upgrade the CLI binary**
   - [ ] `npm install -g @mindfoldhq/trellis@0.6.14`; `trellis --version` →
         0.6.14. Packaged template root (verified layout on 0.6.7, confirm
         on 0.6.14): `$(npm root -g)/@mindfoldhq/trellis/dist/templates/`.
3. **Conflict-safety gate** (design.md gate, two parts)
   - [ ] `trellis update --dry-run`; capture full output. Every conflict
         ("needs confirmation") file must be byte-equal to its v0.6.7
         template counterpart (fork `git show v0.6.7:...`; the 0.6.7 npm
         package is gone after step 2) — except `AGENTS.md` and
         `.github/copilot-instructions.md` (expected managed-block
         conflicts) and `.opencode/package.json` (must classify
         user-deleted, not re-added).
   - [ ] Sandbox apply: `git clone` the repo into scratchpad, copy
         `.trellis/.template-hashes.json` and `.trellis/.developer` into the
         clone, run `trellis update --force` there. Verify in the clone:
         `AGENTS.md` and `.github/copilot-instructions.md` differ from the
         working tree only inside their managed blocks; review the new-file
         list; no migration ran (inventory: one optional 0.6.8 `.pi/skills`
         rename, inapplicable — no `.pi` surface, `--migrate` not passed).
   - [ ] Gate result: every conflict explained and clone outside-block diff
         empty → proceed. Otherwise STOP and report the unexplained files.
   - [ ] Note the updater backup dir the clone run created
         (`.trellis/.backup-<timestamp>/`) — the real run will create one
         too; record its path for rollback.
4. **Apply**
   - [ ] `trellis update --force` in the real tree.
   - [ ] Diff real tree vs sandbox clone result — must match byte-for-byte
         (excluding `.git`, `__pycache__`, backup dirs).
   - [ ] Protected-path check: `git status` for tracked protected paths
         (`.trellis/tasks|spec|workspace`) and presence/hash comparison
         against the step 1 baseline for the gitignored `.developer` /
         `.current-task` (absent must remain absent); no new platform
         directories.
5. **Verify (acceptance criteria) + commit 1**
   - [ ] Byte-identity: `.trellis/scripts` vs installed package
         `$(npm root -g)/@mindfoldhq/trellis/dist/templates/trellis/scripts`
         (authoritative — it wrote the files), cross-checked vs fork
         `git archive v0.6.14 packages/cli/src/templates/trellis/scripts` —
         `diff -rq --exclude=__pycache__` exit 0 for both.
   - [ ] Whole-surface check: re-run `trellis update --dry-run` — must
         report zero pending changes and zero conflicts beyond the two
         managed-block files now hash-tracked (expect fully clean).
   - [ ] `cat .trellis/.version` → `0.6.14`.
   - [ ] Base-branch seed fix live: on this feature branch,
         `task.py create "probe" --slug probe-base-branch-seed --no-start
         --description ... --assignee sdelmas` seeds `base_branch: main`;
         then delete the probe dir (probe, not a task).
   - [ ] `python3 .trellis/scripts/task.py current --json` returns valid
         JSON.
   - [ ] `node scripts/sd-ai-command-pack-review-preflight.mjs` → 0
         failures.
   - [ ] Commit 1: template-upgrade diff only.
6. **status.py `--json` adoption + bookkeeping (commit 2)**
   - [ ] Template-first (`AGENTS.md:29`): edit
         `templates/scripts/sd-ai-command-pack-status.py` active-task read:
         try `task.py current --json`, parse `current_task.dir`; on nonzero
         exit fall back to the existing bare `current` prose parse (0.6.7
         consumer repos). Sync the root mirror
         `scripts/sd-ai-command-pack-status.py` byte-identically.
   - [ ] Tests: add JSON-success fixture and nonzero-exit-fallback fixture
         (existing fixture emits prose regardless of `--json`, so it cannot
         cover the new path).
   - [ ] Shipped-payload bookkeeping per CONTRIBUTING: manifest version
         bump, changelog heading, release evidence.
   - [ ] `bash scripts/sd-ai-command-pack-toolchain.sh run-python --
         scripts/sd-ai-command-pack-status.py --json` succeeds on this repo
         (0.6.14) with active-task fields populated.
   - [ ] Commit 2.
7. **Downstream evidence (commit 3) + full suite + publish**
   - [ ] Downstream evidence packet (PRD requirement 4), written and
         committed BEFORE publication: record in
         `08-06-task-create-base-branch-seed/research/` the seed-probe
         result (branch, seeded base_branch, commit SHA), and in
         `08-08-upstream-handoff-register/research/` the upgrade commit SHA
         plus the `current --json` contract sample. Commit 3 (touches other
         task dirs — expect the preflight multi-task-dir advisory warning,
         which is acceptable). Packets cite branch and commit SHAs only —
         durable identifiers; the PR is discoverable from the SHA. No
         post-publication amend or extra commit for the PR number.
   - [ ] `make release-prep` (CONTRIBUTING shipped-payload contract:
         regenerates the exact-payload fleet ledger / release evidence,
         then runs `make check` = test + lint + audit + full-check) →
         green with all three commits present. Commit any regenerated
         release-evidence files into commit 2 (amend) or commit 3.
   - [ ] `sd-create-pr` flow (update-spec, preflight, push, PR).

## Validation commands (single list)

```bash
trellis --version                       # 0.6.14
cat .trellis/.version                   # 0.6.14
diff -rq --exclude=__pycache__ .trellis/scripts \
  "$(npm root -g)/@mindfoldhq/trellis/dist/templates/trellis/scripts"
trellis update --dry-run                # zero pending changes post-apply
python3 .trellis/scripts/task.py current --json
node scripts/sd-ai-command-pack-review-preflight.mjs
make release-prep   # regenerates release evidence, then runs make check
```

## Execution log (2026-08-08)

All steps executed; deviations from the plan as written:

- **Commit 1 scope widened** to include a record-session compatibility fix
  discovered by the full suite: 0.6.14 `add_session.py` omits journal
  sections with no content, and the pack wrapper failed on the missing
  `### Testing` heading. Fixed template-first
  (`templates/scripts/sd-ai-command-pack-record-session.py` +
  mirror + guard-test update) inside commit 1 so that commit is green on
  its own.
- **Gate outcome**: dry-run showed 26 conflicts; a 0.6.7 rescan
  (`npx @mindfoldhq/trellis@0.6.7 update --dry-run` in a clone) classified
  the whole surface pristine except one hash-verified Trellis-written file,
  and the sandbox 0.6.14 apply left `AGENTS.md` / copilot-instructions
  entirely untouched (managed blocks unchanged). Real apply matched the
  sandbox byte-for-byte.
- **status.py hardening beyond plan**: exit-0-but-prose output (a variant
  ignoring unknown flags) also falls back to the path parse.
- Commits: `d10d4e95` (upgrade + record-session compat), `3328a1ec`
  (status --json + 0.64.29 bookkeeping), commit 3 (evidence + planning
  artifacts). `make release-prep` green after commit 2 content.
- Seed probe: `base_branch: main` on feature branch — captured in
  `08-06-task-create-base-branch-seed/research/`.

## Rollback points

- After step 4, pre-commit: restore only updater-owned paths from the step 1
  inventory (`git checkout -- <path>` per path; `git clean -fd` scoped to
  the recorded new-file list — never blanket `git checkout -- .`); restore
  the saved `.template-hashes.json`.
- After commits: revert commit(s); restore saved `.template-hashes.json`.
- Both: `npm install -g @mindfoldhq/trellis@0.6.7`; verify
  `.trellis/.version` → 0.6.7 and a 0.6.7 `trellis update --dry-run`
  reports no unexplained changes.
