# Check enumeration at fix time (2026-08-08)

Enumerated from `runReviewPreflight`'s registration block,
`scripts/sd-ai-command-pack-review-preflight.mjs:229-240` — exactly 12
`runCheck(...)` registrations, matching `grep -c "runCheck('" == 12`.
Scoping read from each check body (mechanism column cites the line the
scoping call appears on). The PRD's 2026-08-08 snapshot predates the
root-task base_branch rule (added by 08-06-task-create-base-branch-seed
inside the topology check), confirming the re-enumeration requirement was
not theoretical.

Evidence column filled at implementation step 11 (2026-08-09): every row
carries CI-demo evidence, a stated local exercise with its exact FAIL
line, or an explicit reason a CI demo was not published. No row is
blank. Legend:
- diff-scoped = walks only `currentChangedPaths()` /
  `currentReviewDiffStats()` output (base ref decides the window — the
  checks this task's base change affects)
- repo-wide = walks the filesystem/tracked tree regardless of diff (mode
  gap affected them; base does not)
- hybrid = compares working tree against a baseline ref

| # | Check (label) | Fn (line) | Scope | Mechanism | Disposition | Path family | Evidence (step 11) |
|---|---------------|-----------|-------|-----------|-------------|-------------|--------------------|
| 1 | package override sources of truth | `checkPackageOverrides` (:2819) | repo-wide | reads `package.json` directly | fail | `package.json` npm overrides | Local exercise (step 10 probe): duplicate `demo-pkg` override injected → `FAIL package.json defines "demo-pkg" both globally and under c8 > demo-pkg.`; restored. Unreachable via demo PR without polluting `package.json` on a published branch. |
| 2 | copied template diff disclosure | `checkCopiedTemplateDiffDisclosure` (:2861) | diff-scoped | `currentChangedPaths()` (:2862) | warn only | copied `templates/**` twins | Advisory; no `templates/**` twin changed in any demo. Executed as empty-set pass in every run listed in `evidence-demos.md` (window correctness shared with rows 5/6/8 — same `currentChangedPaths()` over the same event base). |
| 3 | documentation path hygiene | `checkDocumentationPathHygiene` (:2940) | repo-wide | `documentationGuardFiles()` filesystem walk (:4584) | fail | docs/prompt/spec markdown (personal absolute paths) | Local exercise (step 10 probe): personal macOS absolute path injected into `research/local-replays.md` → `FAIL ...local-replays.md:51 includes a personal macOS absolute path...`; restored. Not demoed in CI to avoid publishing a personal path. |
| 4 | documentation path references | `checkDocumentationPathReferences` (:2898) | repo-wide | `documentationGuardFiles()` filesystem walk | fail | docs/prompt/spec markdown (path references) | Demo A (run 31291939696, full): `FAIL ...gap-a/prd.md:8 references missing path docs/demo-preflight-gap-does-not-exist.md.`; Demo B push-2 (run 31292345434, bookkeeping): same shape at `prd.md:11`. See `evidence-demos.md`. |
| 5 | changed Trellis task metadata integrity | `checkChangedTrellisTaskMetadata` (:2973) | diff-scoped | `currentChangedPaths()` (:2975); calls `validateTrellisTaskMetadataLinks` (:3030) | fail | `.trellis/tasks/**/task.json` | Demo C push-2 (run 31292345966, bookkeeping) and Demo D push-2 (run 31292347063, full): `FAIL ...-parent/task.json field children references missing task ...-child.` (:3541) — visible only in the PR-base window, proving the base fix. See `evidence-demos.md`. |
| 6 | changed Trellis task topology semantics | `checkChangedTrellisTaskTopologySemantics` (:3045) | diff-scoped | `currentChangedPaths()` (:3047) | fail | `.trellis/tasks/**/task.json` + parent `prd.md` child maps + root `base_branch` (post-snapshot rule) | Local exercise (`local-replays.md` replay 1): `base_branch: "chore/demo-bad-base"` injected → `FAIL ... field root task base_branch "chore/demo-bad-base" must equal the repository default branch "main" ...` under `BASE_REF=origin/main`; restored, replay 2 clean pass. |
| 7 | completed Trellis task location | `checkCompletedTrellisTaskLocation` (:3815) | repo-wide | walks `.trellis/tasks` root | fail | active-root task records | Local exercise (step 10 probe): task record flipped to `status: "completed"` in active root → two FAIL lines (field status + archive instruction); restored. CI demo would require publishing a bogus completed record. |
| 8 | Trellis task context manifests | `checkTrellisTaskContextManifests` (:3703) | diff-scoped | `currentChangedPaths()` (:3705) | fail | `implement.jsonl`/`check.jsonl` | Local exercise (step 10 probe): malformed line prepended to this task's tracked `implement.jsonl` → `FAIL ...implement.jsonl:1 is not valid JSONL...` with `BASE_REF=origin/main`; restored via `git checkout`. |
| 9 | Trellis journal records | `checkTrellisJournalRecords` (:3966) | hybrid | `journalBaselineRef()` + `gitFilesAtRef` (:3969-3971) — baseline ref IS the review base, so the base change alters what "historical" means | fail | `.trellis/workspace/**/journal-*.md` + index | Local exercise (step 10 probe): historical Session 302 line edited inside a `## Session` block → `FAIL .trellis/workspace/sdelmas/journal-7.md:10 modifies historical Session 302 from origin/main; Trellis journal history is append-only...` with `BASE_REF=origin/main`; restored. Confirms baseline = review base. |
| 10 | first-review risk sweep | `checkReviewRiskSweep` (:4136) | diff-scoped | `currentChangedPaths()` (:4137) | warn only | changed code paths | Fired in `local-replays.md` replay 2 (boundary-risk advisory on the workflow shell changes, counted in `1 warning(s)`), dispositioned in PR #386 body. |
| 11 | diff size warning | `checkDiffSize` (:4181) | diff-scoped | `currentReviewDiffStats()` (:4182) | warn only | every changed path (`isSourceReviewPath`) | Advisory; every demo diff under threshold → executed without warning in all runs (`Review preflight: 0/1 failure(s)` totals confirm the check ran). Demo E's marker file counts toward its stats (per design's Demo E claim-precision note). |
| 12 | tooling/generated scope advisory | `checkScopeAdvisory` (:4243) | diff-scoped | diff-derived advisory | warn only | changed path classification | Fired in fix PR #386 run 31291158452 (tooling/generated scope advisory, one of the `2 warning(s)`), dispositioned in the PR body's scope section. See `evidence-fix-pr.md`. |

## Consequence for this task's fix

- Checks 5, 6, 8 are the diff-scoped FAILING checks whose window the base
  change corrects (the PRD snapshot's three, with the base_branch rule
  now inside 6). Check 9's baseline is the same base ref — the hybrid
  fourth.
- Checks 2, 10, 11, 12 are diff-scoped but advisory (warn) — the base
  change widens their window too; no fail path changes.
- Checks 1, 3, 4, 7 are repo-wide: the MODE gap (gap 1) silenced them on
  full heads; the base (gap 2) never affected them. Demo A's broken
  reference is caught by check 4 the moment the preflight runs at all.
