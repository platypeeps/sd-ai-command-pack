# Acceptance-criteria map (implement.md step 11, 2026-08-09)

AC numbering = order of the `- [ ]` bullets in `prd.md` "Acceptance
Criteria" (15 total). Every AC cites its evidence file and section; no AC
rests on prose alone where the PRD demands an observation.

| AC | Criterion (short) | Evidence |
|----|-------------------|----------|
| 1 | `full` head with broken documentation reference fails `CI Result`, mode read from run | `research/evidence-demos.md` § Demo A — run 31291939696, `CI_SCOPE_MODE: full` from CI Result job env, FAIL line at `prd.md:8`, `CI Result` failure |
| 2 | Specifically the **initial** (`opened`) head fails | Same section — `EVENT_ACTION: opened` read from the classify step env of that run |
| 3 | `bookkeeping` head with same defect still fails | `evidence-demos.md` § Demo B — push-2 run 31292345434, mode bookkeeping, FAIL at `prd.md:11`, `CI Result` failure |
| 4 | Valid-push-1 / invalidating-push-2 parent-child construction fails on second head; mode and base read from run | `evidence-demos.md` § Demo C — run 31292345966: mode bookkeeping, classifier `BEFORE_SHA: 9b071e33` vs validation `EVENT_BASE_SHA: 9252d01d`, dangling-child FAIL, `CI Result` failure |
| 5 | Same construction in **both** modes | § Demo C (bookkeeping) + § Demo D — run 31292347063, mode full via `.github/demo-marker.txt`, same FAIL |
| 6 | Diff-scoped checks re-enumerated from source at fix time | `research/diff-scope-enumeration.md` — 12 `runCheck` registrations from `:229-240`, scoping read per check body, includes post-snapshot `base_branch` rule |
| 7 | `full` head with no `.trellis/**` / documentation change still passes | `evidence-demos.md` § Demo E — run 31292003371, all jobs success, `0 failure(s)` |
| 8 | Bookkeeping successor still skips expensive lanes, from job conclusions | § Demo B — unittest/lint/security/release-payload all `skipped` on the failing bookkeeping run (cost saving + validation on one run) |
| 9 | c8 coverage non-zero AND zero-line guard shown able to fire | `research/evidence-fix-pr.md` — `40.36% (2193/5433 lines)` full-mode run; `research/local-replays.md` replay 4 — empty c8 dir → guard error, exit 1 |
| 10 | PR #358 `4cd89b5e` replay shape fails the gate | § Demo A — same defect class (broken repository-relative reference on a full head), fails closed in CI |
| 11 | Steps invoking preflight against event head enumerate to one shared definition | `evidence-demos.md` § Observations, "Single shared invocation" — one step (`Validate event head`); bookkeeping step's invocation is `final-bundle` only, drift-guarded by `tests/test_bookkeeping_ci_scope.py::test_bookkeeping_lane_reuses_canonical_validators` |
| 12 | Push-event base stated in workflow; classifier value read from an existing `main` push run | Workflow: `EVENT_BASE_SHA: ${{ github.event.pull_request.base.sha \|\| github.event.before }}` + comment in `.github/workflows/tests.yml`; observation: `evidence-demos.md` § Observations, main push run 31291862939 — `EVENT_BASE_SHA == event.before == 3c247269` |
| 13 | `CI Result` still the only required context (from branch protection), and failing validation fails it in both modes | § Observations — protection API `contexts == ["CI Result"], strict: true`; Demos A (full) and B/C (bookkeeping) each show validation failure → `CI Result` failure |
| 14 | No-relevant-path behaviour written down, not implicit | `Validate event head` comment block in `.github/workflows/tests.yml` (empty-set = pass by design) + § Demo E pass-line output (`no changed ... require ...`) |
| 15 | Path families enumerated **in full**; each exercised or unreachability stated — `package.json` and journal families named as floor | `research/diff-scope-enumeration.md` — evidence column complete for all 12 rows: families 4/5 (doc refs, task metadata) by CI demos; family 1 `package.json` overrides, 3 hygiene, 6 topology/base_branch, 7 completed-location, 8 manifests, 9 journal by stated local exercises with exact FAIL lines; advisory families 2/10/11/12 by run execution + fired-warning evidence |

No AC without evidence; no evidence claimed beyond what a run or a stated
local exercise produced.
