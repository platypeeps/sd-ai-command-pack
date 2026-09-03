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
| **3-c** | Consumer PRs, **one per repo**, removal only (M2): trellis payload, router removal via `--remove-legacy`, dotfiles, path rewrites, across the 9 repos of the wave — a tenth, `mezmo_benchmark`, is frozen under D7 and gets no PR | per repo: zero trellis/router greps; CI green |
| **3-d** | `sd-review setup-github`: build the subcommand behind `SETUP_GITHUB_SEAM` in `bin/sd-review`, prove the routed lane green on the pack itself, then one opt-in PR per remaining `mode: full` repo | `setup-github` refuses in `minimal`/`guest` (R10-D5) and over a legacy footprint without `--remove-legacy`; one routed PR per full-mode repo shows a `route()` plan in the check output |
| **P1** | Cross-platform sweep: delete 19 legacy gemini TOMLs (render 0 — r9b) + 19 opencode entries before re-render | `test ! -e ~/.gemini/commands/sd`; opencode `grep -c '^sd-'` = 12; 3 antigravity skill roots free of `sd-*` residue |
| **P2** | Vendor kimi agents ×5 + codex-rescue + 3 codex skills → uninstall kimi/codex plugins (kills both Stop gates) | vendored agents resolve post-uninstall |
| **P3** | installed.json canonicalization; dashboard lands on :8768 beside system one | `curl :8768/api/state` ≥10 repos; --dump diff empty |
| **P4** | Retarget nightly skill-proposal-accept routine (before step 5) | routine files an item or cleanly no-ops |
| **P5** | Agent hygiene (tools: declarations, agent entries in ~/.codex/config.toml — external format, D-C1 exemption — caveman fork drops review lane) | sd-status drift clean |
| **4** | Retire router repos (archive with pointers); delete remote half | `git grep -c remoteIntegration bin/` = 0 |
| **4b** | Reconcile r3 round-2 assumptions (schema, names); new index populated **alongside** the live system dashboard (collectors untouched until 6b) | issue table populates in one refresh; :8767 unchanged |
| **5** | Fold se-ai-command-pack (64 skills + 5 agents, all renamed se-* → sd-*; machine locations replaced). **Vault-side first:** retarget the 8 scheduled-routine callers (`se-research` ×6, `se-scan` ×2 under `System/Scheduled Tasks/`) to `sd-*`, then delete old se-* renders | `grep -rln 'se-research\|se-scan' 'System/Scheduled Tasks/'` = 0 before deletion; count = 64; collision check vs 11 commands = 0; `ls ~/.claude/skills \| grep -c '^se-'` = 0; sdw-research resolves; next nightly routine run green |
| **5b** | `sd-skill-adopt` lands; retire skill-proposal-accept + file-trellis-task.py; delete legacy gito/prism skill folders (backend rows stay) | adopt-lint green on all installed skills |
| **6** | Machine cleanup = M3 (receipt-driven, legacy subdirs by name) | find both spellings = 0; plugin rows = 0; `handoff/` + `intents/` untouched (a packet written before the step is restorable after) |
| **6b** | Eight PRs, not one — order fixed by R11-D12 and R11-D13, then amended by R11-D21, which made Queues a sixth plugin tab landing after the write path rather than a backbone tab landing before Now: registration slice (`sd plugin add` and `sd plugin list` plus the manifest read, pulled forward from 8) → the plugin loader → the five plugin tabs → backbone tabs → Now → `RUN_ALLOWLIST` + `sd-dashboard install` → swap to :8767 → delete system `dashboard.py` | `lsof -i :8767` one listening process and it is the pack's; rm-test passes; Now emits every rank-0/rank-1 row it emits today; loader PR reports its LOC against the dashboard cap's remaining headroom, and the backbone-render PR re-derives that cap from files that exist (R11-D17: 4,000) |
| **7** | Park backlog (D2), triage survivors, delete `migrate-trellis` (~~`migrate-vault` survives to step 11~~ -- it was never written; see step 11), verify protection, tag 1.0.0 | `grep -rli trellis` → archive only; sd-status ≤20 active; `sd-status --parked` lists every swept item |
| **8** | Plugin interface in backbone **less the registration slice, which moved to 6b** (R11-D13): `sd store`/`sd config`, `sd plugin lock`, vault driver, golden-corpus byte-compare | direct-write-then-query freshness test green |
| **9** | Vault-side retarget of 6 pack.py callers (5 routines + the permission grant, which goes **last**), BEFORE deletion | `grep -rln pack.py 'System/Scheduled Tasks/'` = 0 |
| **10** | sd-writing-pack migration PR (manifest, store clients, delete ~1,280 LOC, and the hardcoded vault root at `pack.py:146` goes with them -- the driver takes `OBSIDIAN_VAULT`) | `grep -c -e BI_DB -e SP_DB -e TT_DB -e TP_DB -e VAULT pack.py` = 0; E2E on one piece |
| **11** | Vault move, **last** — **superseded 2026-09-02: nothing moves.** The per-base list was put to the user and both live dispositions were reversed; the row's other three claims were each false. See *Step 11 moves nothing* below | **no longer applicable.** Closing evidence is the enumerated per-base list and the four corrections, not a byte-compare of a move that does not happen |

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
- [x] 3 — new installer + 12 skills + sd-review backends. **Split into reviewable sub-PRs
  (2026-08-29): step 3 replaces ~56k LOC of `templates/scripts/` + `installer/` with ~7k under
  `bin/`; landing that as one pull request would be unreviewable, and the old world must keep
  working until the new installer is proven. Sub-PRs land on `main` in order, each independently
  green; 3-c does not begin until all of them have landed, so the "consumers cannot plugin-update
  between step 1 and step 3" window is unchanged.**

  **Closed 2026-08-30, on the row's own check and not a proxy for it.** The table row gates
  step 3 on "scratch-repo sd-ship E2E; installer parity test green". The parity test has been
  green since 3e; the end-to-end ran at 3f in two halves — the local stages in a fixture, the
  push/PR/settle/merge sequence against `platypeeps/sd-e2e-scratch` — and its findings are
  recorded there rather than summarized away. All seven sub-items are ticked — 3a, 3b,
  3c-review, 3c-cwd, 3d, 3e, 3f — each against the check it named, except 3c-cwd, which named
  no check because it was not a planned sub-item at all: it is the R10-D6 follow-up found while
  reviewing 3c-review, and it carries its own evidence in its entry.
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
  - [x] 3d — the 12 command skills + templates (#607). Twelve directories under `skills/`,
        one per command, and the five templates `sd-plan` renders (`prd`, `design`,
        `implement`, `decision`, `work-README`). The frontmatter contract is a test:
        `tests/test_skill_frontmatter.py` verifies every documented flag exists in the tool
        the skill names, reading the `bin/` modules that tool imports so a surface split
        across files is read whole.
  - [x] 3e — machine-scope installer + `installed.json` + parity tests; deletes the legacy render
        payload. Landed as two commits in one pull request: `feat` adds `bin/sd_install.py` and
        `tests/test_sd_install.py`, `refactor!` deletes what it replaces. Reviewable apart,
        atomic on merge. **365 files, 183,433 deletions against 1,343 insertions.**

        Six things worth recording, because each was a call rather than a mechanical step.

        **The deleted set was larger than the row above predicted.** The row named
        `templates/scripts/**`; the whole of `templates/` is render payload — 175 files, 64,142
        lines — and keeping the other 143 would have left committed per-platform copies with no
        generator, which is the committed-derived-state failure this rollout exists to end. Found
        by enumerating the tracked tree rather than by following test failures one at a time, and
        that enumeration is also what surfaced `.github/skills/trellis-*` (43 files),
        `.github/prompts/`, `.github/command-sources/`, `docs/fleet/`, `generated/`, `plugins/`
        and `.claude-plugin/`.

        **Scope was held at what this commit orphaned, and the rest named rather than swept.**
        Deleted here: the two generated command surfaces whose generator this step removes, and
        two orphaned root doc copies. Left standing: trellis, fleet and plugin residue, which
        steps 4 and 7 own. Widening a deletion because the tree is already open is how a
        reviewable pull request becomes an unreviewable one. `docs/FLEET_ROLLOUT.md`,
        `docs/fleet/**`, and `docs/spec/**` therefore still describe machinery that no longer
        exists; `CONTRIBUTING.md` says so rather than letting a reader find out.

        **`bin/migrate-trellis` keeps its `templates/scripts/` reference and is correct.** It
        probes for that path in a *consumer* checkout, not in this one, so the deletion does not
        reach it. Checked rather than assumed, because it is the one surviving `bin/` file naming
        a deleted path.

        **The coverage floor moved from files to statements.** `check-installer-coverage.sh`
        guarded a 17-file surface with `MIN_FILES=17`; against a one-file surface a file floor
        catches nothing — the module can be gutted to a stub and still satisfy it. `MIN_STATEMENTS=450`
        is now the floor that can actually fail (the surface is 513), and `MIN_FILES=1` survives
        as the cheaper check with the readable message if the file is deleted outright. Coverage
        is 100% line and branch, reached by writing tests rather than by lowering the gate: the
        first full run measured 76%.

        **`--home` escaped its sandbox three times, and only the third fix is structural.** All
        three are one bug: a second source of truth about where "home" is. (1) Git's global config
        is per-user, not per-`$HOME`-argument, so an unsandboxed `core.excludesFile` lookup reaches
        the real home whatever `--home` says — patched by threading a `sandboxed` flag through the
        excludes helpers. (2) A test then constructed a `Context` without that flag and appended
        `CLAUDE.local.md` to the developer's actual global excludes; `sandboxed` became a derived
        property, `home != expanduser("~")`, which a caller cannot forget. (3) CI caught the third:
        the XDG variables. `main()` rewrote both roots under `--home`, which protected callers that
        came through `main()` and not the tests, which build a `Context` directly —
        `RendererParityTests` asked `platform_homes(scratch_home, os.environ)` where the surfaces
        should be and, on a runner with `XDG_CONFIG_HOME=/home/runner/.config` set, was told the
        runner's real home. The install itself stayed contained; the question about it did not.

        Two things are worth carrying forward from that. The escape was invisible locally because
        both XDG variables are unset on this machine, so both sides agreed — reproducing it took
        `XDG_CONFIG_HOME=... XDG_STATE_HOME=... make check`, which now passes with the variables
        set *and* unset. And the entrypoint fix was the wrong shape twice running: a rule enforced
        where it is convenient protects the path someone remembered. `xdg_root()` enforces
        containment where the roots are resolved, so a sandboxed run honours an XDG override only
        while it stays inside the given home, and an unsandboxed one is left alone — including the
        unusual but legitimate XDG root outside `$HOME`, which is not this installer's to redirect.

        **The no-shipped-shell invariant R11-D6 requires is `tests/test_no_shipped_shell.py`.**
        It enumerates tracked files from git and flags shell by suffix *or* shebang, asserts the
        render surface under `skills/` is markdown only, and confines shell to `.github/scripts/`.
        Verified by breaking it: staging one `.sh` under `skills/` fails all three assertions.
  - [x] 3f — the scratch-repo end-to-end this step's own check names. The table row at the
        top of this file gates step 3 on "scratch-repo sd-ship E2E; installer parity test
        green". The parity test has been green since 3e. **The end-to-end had not been run when
        this box was opened**, and 3-c went ahead of it. It was kept as an open box rather than
        absorbed into a ticked parent, because a step marked done on a check that never ran is
        the exact failure critique 4 exists to end; the tick below is the check having run. Half of the verification section's step-3 paragraph is
        already covered by fixtures — a markdown-only change plans `skip`
        (`test_documentation_only_change_plans_skip`) and an unmatched change falls back to
        the default tier (`test_an_unmatched_change_falls_back_to_the_default_tier`), both in
        `tests/test_sd_route.py`. The uncovered half needs an agent driving `sd-plan` and
        `sd-ship` in a scratch repository that already has `docs/adr/` and a Makefile, ending
        in a merged pull request and an adoption-purity assertion (B5a): `git status
        --porcelain` shows only `<work>/**`.

        **Run 2026-08-30, and it earned its keep on the first attempt.** A scratch repository
        was built with a preexisting `docs/adr/`, a Makefile, and a small Python package, then
        driven through the sd-plan and sd-ship stages by hand — both are skills with no
        `bin/` implementation, and both say so in their own "State of the tooling" section.
        Four checks passed: `sd-check` reported `entrypoints: makefile (Makefile defines check,
        test, lint)` and ran the repository's own `make check`, deduping `test` and `lint` as
        already covered by it; B5a adoption purity held with zero paths
        outside `docs/work/`; `sd-docs-lint` was clean with rule 4 declining to demand a
        `docs/spec/` the repository does not have; and both stated route shapes were right —
        markdown-only planned `skip` with no providers, `requirements.txt`-only planned
        `standard`. Acceptance criteria were verified from real output rather than exit codes
        (`Ran 2 tests ... OK`, `greet("world") -> 'Hello, world!'`).

        The fifth check found a routing defect that no fixture covered: a category that lowers
        the tier matched on any path, so one markdown file took a reviewer off a source change
        (R11-D9, #620). That is the return on running the check — the two shapes the
        verification section names are both single-category, and neither could ever have found
        it. The wave itself had been printing the defect: of the six routed pull
        requests, five planned `tier deep` and `hoa-manager#300` planned `tier standard`,
        because its diff also carried a documentation file. Visible in the check output the
        whole time, and read by nobody until it was compared against the other five. Two smaller observations kept rather than fixed: rule 4 *no-ops* when `docs/spec/`
        is absent rather than indexing the preexisting `docs/adr/`, so the pack does not block
        the repository but does not detect its ADR location either (that detection lives in
        `sd-plan --decision`, unimplemented); and the fixture initially failed adoption purity
        on a `src/__pycache__/` its own `make check` produced, which is the scratch repository
        lacking a `.gitignore` any real Python repository has, not a pack defect — the fixture
        was corrected and the correction is recorded here rather than quietly re-measured.

        **The remaining half ran the same day, against a live repository.** A throwaway
        private repository, `platypeeps/sd-e2e-scratch`, took the same fixture, and the
        `sd-ship` push/PR/settle/merge sequence ran end to end: pull request #1 opened with a
        `Work:` line resolving to the item, Copilot requested once for head `048d0889`, and the
        squash merge landed as `0d6e93dd` with an explicit `-t`/`-b`, so `git log main
        --format=%s | grep -c '^wip:'` is 0. B5a was re-measured on the merged `main` rather
        than on the branch: seven tracked files, `git status --porcelain` empty, and zero
        tracked paths matching `.trellis`, `.claude`, `.sd-*`, or the pack's name — the only
        thing the flow added to somebody else's repository is `docs/work/`.

        The settle loop earned the round trip. Copilot's one inline comment was correct: the
        pull request's own motivation is a caller who wants no terminal punctuation and used
        `rstrip("!")` to get it, and that was the single path with no test — also the path
        where `rstrip` is wrong, because a name ending in `!` loses a character it owns. The
        test was added, `make check` stayed green, the thread got a reply naming the fix
        commit, and only then did the merge run.

        **What this run does not prove, stated rather than implied:** the scratch repository
        has no branch protection and no CI checks at all, so the merge was gated on
        mergeability and a human reading the review, and nothing else. That is the honest
        shape of critique 4's conditional doctrine rather than a hole in the exercise — the
        settle loop's behaviour against required contexts is what the six consumer pull
        requests of 3-c exercised, in repositories that do enforce them.
- [x] 3-c — consumer removal PRs (9); removal only
      - [x] the tool the wave runs on: `migrate-trellis --consumer`, with tests
      - [x] the nine removal pull requests, opened 2026-08-30 and merged the same day on the
            user's word, never unasked
      - [x] the follow-up pass: references the removal left behind, one PR per repo — eight
            of the nine, all merged 2026-08-30. `sd-github-review` is the one exception and a
            deliberate one: step 4 archives that repository, so a residue pass there would
            polish something already on its way out. Named here rather than left as a silent
            gap in the count.
      - [x] the acceptance criterion the wave had *not* met, met 2026-08-30. `prd.md`'s Step
            3-c box reads "one removal PR per consumer (9); zero trellis/router greps per
            repo; CI green". The first and third held from the start. The second was swept on
            2026-08-30, after step 3 closed, and it did not: the follow-up pass had removed
            *machinery* and left *prose*. Both halves are recorded below — what the sweep
            found, and what closed it the same day — because the finding is the useful part
            and a tick that erased it would teach nobody anything.

            Machinery was clean. Enumerated from each default branch's tree rather than from
            the merge output, the five retired paths — `.trellis/`, `.sd-ai-command-pack/`,
            `ai-review-router.yml`, `sd-review.yml`, `sd-github-review.json` — appear in zero
            of the nine, except `sd-github-review` itself, which carries the two router
            workflows because they *are* its product and step 4 retires the repository whole.

            Prose was not. Three repositories were still shipping a spec guide teaching a
            procedure for a framework that no longer exists.
            `docs/spec/guides/code-reuse-thinking-guide.md` carried a `## Template File
            Registration (Trellis-specific)` section — `trellis update`,
            `src/templates/trellis/index.ts`, an rsync that synced `.trellis/scripts/` against
            a template copy — and `docs/spec/guides/cross-layer-thinking-guide.md` taught from
            Trellis command templates, in `hoa-manager`, `people-profiles` and
            `rwbp-coordinator`, byte-identical copies in all three. Both live under
            `docs/spec/`, the repository's own standing guidance rather than an archived work
            item, so an agent reading them was told to maintain a template tree deleted at
            step 1.

            One file the sweep flagged is **not** residue, corrected here rather than carried:
            `people-profiles`'s `docs/spec/frontend/hook-guidelines.md` matches on the word but
            reads "This page previously documented … the agent platform integration that
            Trellis and the SD AI command pack installed … None of that exists here any more."
            It is already the record of its own removal. A grep for a name cannot tell a live
            instruction from an obituary, which is why every hit above was opened.

            Clean by the same sweep, and named so the exceptions are not mistaken for gaps:
            `loadsmith` and `rwbp-website` carry the word only in archived work items and
            `.gitignore`'s deliberate `.trellis/` entry; `anomaly-metric-creator` has one hit,
            a citation of an archived item's path; `se-ai-command-pack` has 63 and is folded
            whole at step 5. The four `~/repos/copilot-worktrees/` directories are not git
            repositories at all, so the first pass over them returned zero for every
            repository and meant nothing — the numbers above come from real checkouts and
            from two shallow clones for the repositories that have none.

            **Closed the same day, on the user's word.** One pull request per repository,
            the same edit applied by one script to files that were byte-identical in all
            three: `hoa-manager#301` (`0ebf1dac`), `people-profiles#24` (`db061865`),
            `rwbp-coordinator#272` (`759ce65c`). Each removes the retired framework's
            procedures and leaves a dated record where the section was, in the same shape
            `people-profiles`'s own `hook-guidelines.md` already used — so a reader who
            remembers a section learns it was removed rather than finding a silent gap. One
            example is kept and re-marked as history, because the manual file list that
            drifted from `getAllScripts()` illustrates asymmetric mechanisms well and the
            lesson does not depend on the framework being reachable.

            Copilot found two real defects in the first draft, and both were fixed in all
            three copies rather than in the repository that raised them, so the files stay
            byte-identical: the kept example spelled the JavaScript iteration form `for..of`,
            which is not valid syntax, and the sentence describing the duplicated sections
            scanned as a missing verb. Two of the three pull requests read `BLOCKED` until
            those threads were resolved — those repositories require conversation resolution,
            `rwbp-coordinator` has no such rule and read `CLEAN` throughout, which is the
            per-repository enforcement variance R11-D3 exists to report rather than assume.

            One gap found while doing it and fixed in the same pull request, because it is the
            same residue: `people-profiles`'s `.gitignore` had no `.trellis/` entry, unlike
            every sibling in the wave, so the leftover working-tree directory showed as
            untracked and was one `git add -A` from being committed back. Deleting it from the
            machine stays step 6's job.

            **Re-swept after the merges**, and the honest form of the result is not a count of
            zero: `docs/spec/` in `hoa-manager`, `people-profiles` and `rwbp-coordinator` still
            matches the word, in the removal records themselves, and
            `anomaly-metric-creator` still matches in citations of an archived item's path.
            Every remaining hit was opened and read. No live instruction survives — which is
            the criterion, and is why the check is a reading rather than a grep count.

            Carried, not closed: `se-ai-command-pack` holds byte-identical copies of both
            guides and is folded whole at step 5. It was left alone deliberately, and is named
            here so the fold does not carry the defect into the backbone.
- [x] 3-d — `sd-review setup-github`, its own step
      - [x] the subcommand behind `SETUP_GITHUB_SEAM` in `bin/sd-review` — #615. The
            dispatch in `bin/sd-review` is three lines; the installer is
            `bin/sd_setup_github.py`, a module of its own because two guards said so and
            neither was loosened to fit. The review lane's then-1,400-line sub-cap fired at
            1,589 (the cap and the guard behind it are corrected below, R11-D8),
            and `tests/test_sd_review_boundary.py` proves `bin/sd-review` never posts and
            never writes by reading it as text and as an AST — an installer living inside
            that file would have made the proof unprovable rather than merely false.
      - [x] the routed lane proven green on the pack repository first — run 33338797058, the
            `route` check, printing `tier deep  category review-lane` for this repository's
            own pull request. It failed on its first real run: `cannot resolve a base branch:
            no origin/HEAD, and neither main nor master exists`. `actions/checkout` leaves a
            detached HEAD, and `persist-credentials: false` means nothing can fetch a
            symbolic ref. Fixed with `git remote set-head origin "${GITHUB_BASE_REF}"` — a
            purely local write needing no credentials — and the line is asserted by a test.
            No local test could have found this, which is the argument for proving the lane
            on the pack before offering it to any other repository.
      - [x] one opt-in PR per remaining `mode: full` repository — six of them, all opened
            and merged 2026-08-30 on the user's word:
            `anomaly-metric-creator`, `hoa-manager`, `loadsmith`, `people-profiles`,
            `rwbp-coordinator`, `rwbp-website`. `mezmo-world-simulator` is an employer
            repository and gets none. `sd-github-review` is retired at step 4 and
            `se-ai-command-pack` is folded at step 5, so neither grows a workflow it would
            only lose again. Named by ownership rather than read from configuration:
            `~/.config/sd-ai-command-pack/config.json` has no repository entries yet, so no
            repository declares a mode at all. `setup-github`'s own `minimal`/`guest` refusal
            is what will enforce the distinction once they do; today it is a list in this file,
            which is why it is written out repository by repository rather than as a count.
            Merged as amc#424, hoa-manager#300, loadsmith#264, people-profiles#23,
            rwbp-coordinator#271, rwbp-website#284. Verified on the six default branches
            rather than from the merge output: the workflow is present in all six with
            identical content, pinned to `50b2c0e7`, `ref: refs/pull/N/head` on line 61.

            The wave cost four defects in the generated file, each found by a consumer's own
            reviewer and each fixed in the generator rather than in the copy — a header naming
            a policy file no consumer has, a concurrency group eaten by the f-string so every
            pull request in a repository shared one, a checkout that failed on conflicted pull
            requests, and the fix for *that* which broke fork pull requests (#617, #618, #619).
            The sequencing is what made them cheap: proving the lane on one repository before
            fanning out meant each defect was fixed in one place and regenerated six times,
            never hand-edited in six.

      **The lane is report-only** (user, 2026-08-30). It prints the `route()` plan to the job
      log and the step summary; it requests no reviewer and posts no comment. That is what
      keeps the opt-in workflow inside P6 — a repository that installs it gains a check that
      observes and never acts — and it means a routing defect costs a wrong line of output
      rather than a wrong review on somebody's pull request.

      **Three line-budget guards were measuring something other than what they named
      (R11-D8).** Found while writing the sentence above that credits the 1,400 sub-cap with
      forcing the split — the claim did not survive being checked. The sub-cap read
      `bin/sd-review` alone, so moving 294 lines into `bin/sd_setup_github.py` took the number
      from 1,589 to 1,367 and the guard went green on a lane that had **grown**. The lane is
      1,661 against a 1,400 budget; a cap you can duck by adding a second file is not a cap.
      The ceiling guard summed every file in `bin/` including `bin/migrate-trellis`, which the
      design places outside it — 1,250 lines of the backbone's 8,000 spent by a tool deleted at
      step 7. And `migrate-*`'s own 1,500 ceiling, promised in the design, had no test at all.

      All three now enumerate their set: the lane from `bin/sd-review`'s import graph minus
      shared core, the ceiling and the migration budget by partitioning `bin/` on disk. Each
      was proven to bite by breaking it — the lane fails at 1,660, the shared-core exemption
      fails on a misspelt module name. The sub-cap then moves to 1,700, in a change that does
      not need the room; the guard was corrected first and the number set to what it measures,
      because 1,700 against a one-file guard would have been a number with nothing behind it.

      Parked with a trigger, not a date: the design's core line reads ~1,800 for eight
      commands and the ones that exist already total 2,811 (2,776 until #620 added 35 lines to
      `bin/sd_route.py`; the figure is restated here because a parked number that silently
      drifts is how a parked concern becomes a forgotten one). That is a stale estimate rather
      than a busted ceiling — `bin/` is 6,276 once `migrate-*` is excluded — and re-deriving it
      against a half-built `bin/` would swap one guess for another. The next command to land
      under `bin/` re-derives it.

      **`setup-github` leaves 3-c and becomes its own step** (user, 2026-08-30), reversing the
      R3-D16 shape that had each full-mode repository's removal PR also carry the routing
      workflow. Two reasons, one practical and one structural. `sd-review setup-github` is
      unbuilt — `bin/sd-review:69` is a seam, not an implementation — so pairing them blocks a
      removal that is ready on a feature that is not. And a pull request that deletes a
      thousand files is already the largest thing a reviewer will read this rollout; adding an
      opt-in CI lane to it means the two cannot be reverted apart.

      Recorded before the wave, because measuring the consumers changed four things the
      plan row asserted.

      **There are eight consumers, not nine.** Enumerated from disk by looking for
      `.trellis/` or `.sd-ai-command-pack/`: six live repositories plus `sd-github-review`
      (which step 4 retires) and `se-ai-command-pack` (which step 5 folds). The ninth in the
      plan is `mezmo_benchmark`, frozen under D7 and not read. `ai/Trellis` also matches the
      probe and is not a consumer — it is the upstream fork the payload came from.

      **Then nine.** `mezmo-world-simulator` was added to the wave by the user on
      2026-08-30 — it carries both installers, 312 tracked framework files, and an
      `AGENTS.md` that is 57 of 57 framework lines. It is an employer repository, so the
      D7 freeze is what kept it out; the user lifted the freeze for this one repository
      and for this one purpose, and `mezmo_benchmark` stays frozen and unread. Its pull
      request is opened, not merged, like the other eight.

      **Removal needs three authorities, and only two installers left receipts.** Three
      installers wrote into these trees. The pack's own receipt covers 2 of loadsmith's 228
      four-tree files; Trellis's `.template-hashes.json` covers 51. What closes the gap is the
      consumer's own `.sd-ai-command-pack/manifest.json` — 740 source-to-target rows — read
      against the `v0.72.0` tombstone blobs, which is the whole reason M0 had to be tagged
      before step 1. Authorities in descending strength: receipt plus tombstone byte-compare,
      Trellis hash match, then name alone for the framework's own `trellis*` / `sd-*`
      namespaces. A file no authority reaches is kept and reported, never guessed at, and a
      receipted file whose bytes drifted is kept too — an edit is the one signal that says a
      human wanted it.

      **The removal was going to delete the artifacts.** `--consumer` short-circuited before
      the import that the default mode has always run, so the plan deleted `.trellis/tasks`
      outright: 886 work items across the eight repositories, none of which have a `docs/work`
      yet — eight because that was the wave when the count was taken; `sd-github-review`
      joined it nine minutes later and brought 18 more item directories with it. That is the
      product, not the packaging. The import now runs first and both modes
      read one `planned_imports()` — counting for the plan and enumerating for the run out of
      two code paths is how a plan starts describing something other than what happens.

      **Every remaining defect was one kept list or another, and they were found by measuring
      rather than by testing.** The pattern is worth naming once because it recurred five times
      in a single sitting:

      - *The four platform trees* were a constant. There are five — nothing had heard of
        `.codex/`, which carries Trellis agents, hooks and its own copy of the
        `security-best-practices` skill the same constant deleted from the other four. Nor of
        `.github/agents/`, nor of the nested `.github/copilot/hooks/`. The set is now derived:
        a tree is whatever directly contains a render subdirectory, at one level or two, minus
        the two trees `wholesale_verdicts` already owns entire. That found 531 files the
        constant walked past.
      - *Empty-directory pruning* walked its own list of trees, which had drifted past
        `.prism/` and `.gito/`. It derives the set from the paths actually deleted now.
      - *`AGENTS.md` markers* were coded against a spelling no repository uses. The real files
        carry two marked blocks, and in `sd-github-review` all 57 lines sit inside them, so the
        verdict there is `delete` — a plan that says `edit` and then unlinks the file is
        describing something else.
      - *`.opencode/package.json`* drew two verdicts, a keep and a delete, from two
        classifiers; and the surviving rule asked what the file contained before asking whether
        anything it configures survives, so a two-line `{"type": "module"}` was left as the
        sole occupant of an emptied tree.
      - *An empty pathspec list* made `git ls-files` enumerate the whole repository. That one
        the tests caught, which is the only reason it is in this list rather than in a
        consumer's pull request.

      **Surviving files that name a deleted path are reported, never rewritten.** 160 of them
      across the eight: Swift sources citing a spec path in a comment,
      `scripts/check_review_readiness.sh`, `tests/review-guard.test.mjs`, a repository's own
      `.instructions.md`. They are the repository's own files and correctly left alone — which
      is exactly why they have to be surfaced, because a removal that silently breaks a
      consumer's test suite has negatively affected their pull requests, and that is the one
      thing this conversion may not do.

      **The sixth defect was not a kept list — it was an authority that lived outside git.**
      `.trellis/.template-hashes.json` is gitignored in six of the nine consumers, so the
      throwaway clones the trial ran in had it (they were made from working directories) and
      the pull-request worktrees did not. The tool did not fail: `trellis_hashes()` returned an
      empty map, every file that map would have condemned fell through to `no authority reaches
      it`, and the plan printed `keep 27` for `people-profiles` as though that were a result.
      Comparing the wave's keep counts against the trial's is what surfaced it: 412 keeps in
      the worktrees against 259 for the same nine repositories once the map is in place. The
      tool now refuses when Trellis is installed, the map is unusable, and something actually fell through as a result; the remedy is to copy the file
      in from a checkout where Trellis is installed, never to regenerate it from the files it
      is meant to judge. A missing authority is not a licence to guess, and a silent
      downgrade to `keep` is a half-removal wearing a success message.

      Measured across all nine, applied in worktrees off `origin/main`: 7,883 files removed,
      7 edited, 888 work items and 198 spec files imported, 172 dangling references reported,
      zero deletions outside the framework prefixes, zero empty directories left. All 259
      survivors are repo-own skills the carve-out protects (`playwright`,
      `security-threat-model`, `amc-server-compatibility`, `loadsmith-swift-app`,
      `hoa-manager-payload-tenant-safety`, `rwbp-next-payload`) or files edited since install.
- [x] P1 — cross-platform sweep, 2026-08-30. All three checks pass:
      `~/.gemini/commands/sd` is gone (the whole `commands` tree with it, since the TOML
      renderer was deleted at R9b-D1 and renders nothing to replace it); the OpenCode
      commands directory holds exactly 12 `sd-*` entries, which are the 12 surfaces and
      not a survivor among them; all three candidate Antigravity skill roots hold zero
      `sd-*` files (`~/.gemini/antigravity-cli/skills` does not exist, the other two do
      and are clean). `--user` then rendered 46 files to 3 platforms and moved the
      serving checkout off the stale `wt-3e` scratchpad worktree onto
      `~/repos/platypeeps/sd-ai-command-pack`, which is what D-R4-8 asks for.
  - The step also found three defects in the legacy lane, all fixed here, because the
    step could not be honestly reported without them. `--adopt-legacy` deleted 112 files
    and said `removed 5`: it counted the survivors *after* pruning and reported them as
    the whole population. The count is the only output the step has, so a count read
    after the fact is not a smaller bug than a wrong deletion — it is the same bug seen
    from the operator's chair. Second, adoption never retired the receipt, so `--status`
    went on advising `--adopt-legacy` after the migration was complete. Third, the
    `--status` banner counted a recorded path as legacy without asking whether the
    current render owns it, so after `--user` overwrote the five colliding OpenCode names
    it pointed at the installer's own fresh output and called it someone else's leftovers.
    Five regression tests, four of which fail without the fix.
  - The `~/.agents` tree holds 1,391 files against a 117-row receipt, which looked like a
    receipt-driven removal about to leave 1,274 files behind. It is not: `~/.agents/skills`
    is a shared root, and the other 1,299 files belong to `cmux` (26), `pp` (8),
    `hyperframes` (8), `caveman` (6) and a long tail of single-skill packs. M1 touched only
    its own rows, which is the design. Recorded because the number is alarming until you
    know why it isn't.
- [x] P2 — 2026-08-30, executed as pure deletion. `codex@openai-codex` and
      `kimi@kimi-marketplace` uninstalled; both Stop gates gone (`Stop` hooks across every
      live plugin: 1, and it is claude-mem's, kept whole by R6-D10). The one SessionStart
      hook this pack owns, `sd-handoff-restore` on `startup|clear`, is untouched, as are
      the machine-level `cbm-*` hooks the plan leaves alone.
  - **Nothing was vendored, and the step is smaller than it was written.** P2 said "vendor
    kimi agents ×5 + codex-rescue + 3 codex skills". Neither half survives contact:
    - All seven kimi agents are gated on the `/kimi:setup` PreToolUse hook, and that hook
      was never registered on this machine — `~/.claude/settings.json` has no kimi entry.
      They have been refusing with `*_HOOK_NOT_INSTALLED` the entire time they appeared in
      the agent list. Vendoring five of them would have copied dead surfaces into the
      backbone and called it a migration.
    - `codex-rescue` is a forwarder, not an implementation: its skill contract is
      `node "${CLAUDE_PLUGIN_ROOT}/scripts/codex-companion.mjs" task "<args>"`, a 30.5 KB
      plugin-owned Node script. Vendoring the four markdown files without it yields an
      agent invoking a deleted path. Vendoring the script instead would put 30 KB of
      Node into a pack whose `bin/` is stdlib Python under an 8,000-line cap, with a
      `test_no_shipped_shell.py` already enforcing the opposite.
  - Nothing is lost, because the capability was never in the plugins. Both CLIs are on
    PATH independently (`/opt/homebrew/bin/kimi`, `/opt/homebrew/bin/codex`) and survive
    the uninstall; `bin/sd-review:214` already carries kimi as an argv backend row with
    the CLI's real prompt-driven invocation, and codex-rescue's stated purpose — hand a
    substantial coding task to Codex — is what `sd-ship --backlog --agent codex` (R10-D1)
    was built to replace, ranked above manual rescue in the model-economics section.
  - Blast radius swept before uninstalling: references to any of these surfaces exist only
    in this work item's own `design.md` and `implement.md`. Zero in `bin/`, zero in
    `~/repos/system`, the vault's `System/`, shell config, `~/.claude/hooks`, or
    `~/.codex/config.toml`.
  - **Not verified in this session, by construction:** the agent registry is read at
    session start, so `kimi-*` and `codex:codex-rescue` still appear in this session's
    agent list and their absence can only be confirmed after a restart.
  - Left for step 6 (M3), named so it is not rediscovered: the two marketplaces stay
    registered (`kimi-marketplace`, `openai-codex` — a source list injects nothing), and
    their `~/.claude/plugins/cache/` trees are still on disk.
  - The installer grew no agent lane. It renders `skills/sd-*/SKILL.md` only, so an
    `agents/` directory would not have installed anywhere — but building the lane with
    nothing to put in it is machinery ahead of need (standing rule 1). It belongs to
    step 5, which folds five real `se-*` agents and gives the lane its first content.
- [x] P3 — 2026-08-30, in two PRs because the step has two unrelated halves and a
      five-line ordering fix does not belong in the same review as a new server.
  - **installed.json canonicalization (#627).** `owned` was written in render order and
    agreed across runs by accident; sorting it by path after the hook row is appended
    makes the receipt a diffable artifact rather than one whose rows churn when the
    render loop is nested the other way. Verified: two runs of the same checkout write
    identical bytes, and the live receipt's 47 rows are sorted.
  - **Dashboard on :8768.** Both named checks pass against the running server:
    `curl :8768/api/state` reports **78 repos** (the check asks for ≥10), and
    `sd-dashboard index --dump` twice is byte-identical. `:8767` answered 200 throughout,
    so the two dashboards coexist as the 3c-to-6b window requires. `POST /api/state`
    returns 501 — the handler implements `do_GET` and nothing else, which is the design
    rather than an omission: a server that cannot write cannot drift into committing,
    pushing, or running agents on a page load, and the test asserts the absence of
    `do_POST`/`do_PUT`/`do_DELETE` so a future tab cannot quietly add one.
  - 372 lines across `dashboard/` and `bin/sd-dashboard`, against the design's 2,500 cap.
    22 tests over real git repositories in a scratch root — a mocked git would only prove
    the mock agrees with itself.
  - **Deliberately not built, so the gap is a record and not a discovery later:**
    - Three of the five verbs. `install` (the LaunchAgent), `item set-status` (the intents
      lane) and `export --obsidian` land with the tabs they serve, under the parity
      checklist. Shipping them as stubs would put three verbs in an inventory that is
      supposed to be a promise.
    - Eight of the nine tabs, the plugin manifest contract (`dashboard.tile` +
      `dashboard.tabs`), and `RUN_ALLOWLIST`.
      P3's checks name `/api/state` and the dump; the tabs are 4b and 6b work.
    - The SQLite index. `sd-dashboard index` collects and reports; it writes no store,
      because step 4b is where the schema and names are reconciled and inventing a
      JSON one here would be a second store to migrate.
  - **D14 bound loopback because it was undecided; it is now decided as (c)** — see
    R11-D10 in `design.md` (user, 2026-08-31). P3 shipped the option that cannot expose
    the fleet while a decision is open, which was correct then and is what a decision
    record, not a flag somebody sets in passing, was owed. The consequence lands at 6b,
    not here: the replacement takes `:8767` with the tailnet reach and the token-gated
    writes the phone uses today. Until then this file's `do_GET`-only assertion in
    `tests/test_sd_dashboard.py` stays exactly as written — it is what stops a tab
    quietly growing a write endpoint in the meantime — and 6b replaces it with the
    stronger one (writes exist, Host-allowlisted, token-gated, no CORS header emitted)
    rather than deleting it. Today's tailnet PWA writes remain on `:8767` until then, so
    nothing regresses in either direction.
  - The repo root comes from `SD_REPO_ROOT`, never from an argument. R10-D6 holds here
    like everywhere else: the dashboard reads many repos and is aimed at none, and a test
    asserts no verb grows `--repo`/`--root`/`--checkout`/`--directory`.
  - Noted, not fixed: `LINT_RUFF_PATHS`/`LINT_MYPY_PATHS` in the Makefile are still a
    hand-maintained list directly under a comment explaining that a hand-maintained list
    is how every `bin/` file went unlinted in CI until 2026-08-29. `dashboard/` and
    `bin/sd-dashboard` are added to both, but the next file added will face the same
    trap. Deriving the list is its own change.
- [x] P4 — 2026-08-30. The nightly `skill-proposal-accept` routine files its one
      authorized outward write into `sd-ai-command-pack` again, as a work item.
  - **It had been failing, not idling.** Gate 4 of its preflight required
    `se-ai-command-pack/.trellis/scripts/task.py`. Trellis was removed from the pack at
    step 2 and the pack itself is folded at step 5, so that path had not existed for some
    time and every 03:00 run stopped at the gate. The retarget is therefore a repair with
    a rename in it, not a rename.
  - **Vault-side, in one commit** (`b6bd433`, six enumerated paths): `System/Scripts/
    file-work-item.py` replaces `file-trellis-task.py`, which is deleted; the routine's
    `SKILL.md`; `blog-idea-accept`'s one cross-reference; `System/Schema.md`'s `task-path`
    row; and the `VAULT-STRUCTURE.md` authorization callout. That callout had to move in
    the same change as the script — gate 2 greps it for the repository name, so a
    preflight looking for a name the block no longer carried would stop the routine before
    it filed anything. The vault said so itself at line 388, which is why the instruction
    was there.
  - **One authority moved rather than being renamed.** The old wrapper refused to
    hand-author `task.json` because that schema belonged to another repository, so the
    only honest way to produce one was to run that repository's own creator. A work item
    has no creator — it is a directory and a markdown file — but it does have a schema,
    and `bin/sd-docs-lint` enforces it. So `file-work-item.py` writes the item and then
    runs *this repository's* linter over the result: failures naming the new item roll it
    back and leave nothing behind, and failures elsewhere in `docs/work` are reported but
    change nothing, because they are not that run's doing.
  - `task-path` keeps its name in the note frontmatter. It names *where the filed artifact
    landed*, `Writing/Skill Proposals.base` displays it under that name, and renaming it
    would orphan the one note already carrying a value for a field whose meaning did not
    change.
  - **A gate was removed rather than repaired.** The preflight's first check compared this
    routine's "live copy" against its "mirror" — both of which resolve to the same file,
    since `VAULT-STRUCTURE.md` recorded the move to one copy per routine and this gate was
    left behind. It could only compare a file to itself, so it passed unconditionally
    while reporting like a check that had run. Three gates now, all of which can fail.
  - **Verified in two halves, because a no-op cannot exercise a write.** The routine's own
    check is "files an item or cleanly no-ops": all ten Skill Proposals notes are terminal
    (8 `declined`, 2 `filed`), zero `accepted` and zero off-vocabulary, so the next run
    passes its three gates and reports "nothing waiting" — the clean no-op. The write path
    was exercised directly instead: five refusals each fire with their own message (empty
    body, dated slug, malformed slug, empty title, an `anthropic-key` shape in the PRD);
    the happy path wrote a lint-clean item and `sd-docs-lint` reported `clean`; a re-run
    with the same slug refused the collision; a stubbed linter naming the new item rolled
    it back with nothing left on disk; and a stubbed linter naming some *other* item left
    the new one in place. The scratch items were removed and the checkout is clean.
  - Not pushed. `vault-cleanup` pushes that repository every morning at 07:01, and a
    routine's commit riding its own scheduled push is the existing arrangement.
- [x] P5 — 2026-08-30, and smaller than planned once measured. Two of the five installed
      agents claimed to be read-only in their own prose while declaring no `tools:` at
      all, so the registry handed them every tool including `Write`, `Edit` and `Bash`.
      `se-claim-verifier` now declares `Read, Grep, Glob`; `se-source-reader` declares
      those plus `WebFetch`, because its brief names "a document, page, transcript" and
      refusing the fetch would make the page case impossible. All five now declare
      `tools:`, which is what the taxonomy requires of an agent. Takes effect next
      session — the agent registry is read at session start.
  - **The source fix was attempted first and reverted, deliberately.** These five render
    from `se-ai-command-pack/templates/agents/`, so fixing only the machine copy is the
    "fixed the render, not the source" trap. The templates were edited, regenerated
    cleanly, and then `make check` there failed on that repository's release payload gate:
    `payload changed without a version bump (version is still 0.72.0)`. 0.72.0 is the M0
    tombstone — the terminal release, and the only reach-back signal a second machine can
    ever get. Shipping two frontmatter lines by cutting a release past the tombstone
    trades a real invariant for a small convenience, so the branch was deleted and that
    repository is untouched. **Step 5 must carry the same two declarations into the fold**
    — `templates/agents/se-claim-verifier.md` gets `tools: [Read, Grep, Glob]` and
    `templates/agents/se-source-reader.md` gets `tools: [Read, Grep, Glob, WebFetch]` —
    or the fold re-imports the ungoverned version and undoes this.
  - **The codex half is a named gap, not a silent one.** The agents install to
    `~/.codex/agents/*.toml`, not to `~/.codex/config.toml` as the plan row says. That
    render carries `model` and `sandbox_mode` and never `tools`, and no template sets
    `sandbox_mode`, so on the codex side all five run under the default sandbox. The fix
    would be `sandbox_mode: read-only` on the same two agents; it is not applied here
    because nothing on this machine can confirm codex accepts the key — the generator
    supports it but no template has ever used it, and an unverified key in an external
    format could reject two working agent files, which is worse than the gap. It belongs
    to step 5, where the codex render is rebuilt anyway.
  - **The caveman review lane is left alone and named.** The plan row says "caveman fork
    drops review lane". There is no fork: the marketplace entry points at upstream
    `JuliusBrussee/caveman`, so `caveman:cavecrew-reviewer` cannot be dropped without
    forking a third-party plugin. That is a decision, not a sweep item — **since taken as
    R11-D11 (user, 2026-08-31): the plugin stays installed and the reviewer is demoted to
    a scratch tool.** `sd-review` remains the only lane producing a recorded verdict; no
    enforcement code is written, because `git grep -l cavecrew -- bin/` printing nothing
    is the whole invariant and a check for it would be the gate standing rule 1 forbids.
  - `sd-status` reports `legacy residue: none found` and the installer reports
    `0 missing, 0 modified`, which is the step's stated check.
- [x] LOC caps — `tests/test_loc_caps.py`, folded in here on purpose while every cap
      still passes, so it lands as a guard rather than as a negotiation. `bin/` 6,458 of
      8,000 · `bin/migrate-*` 1,250 of 1,500 · `dashboard/` 308 of 2,500. Enumerated from
      `git ls-files`, never from a list: a hand-written list cannot see the thirteenth
      file, and walking the directory is how `find bin -type f` once reported this
      repository at 8,862 lines — over its own cap — by counting `__pycache__/*.pyc`.
      Each test asserts its enumeration is non-empty *before* the cap, because a pathspec
      that stopped matching would count zero and report a clean pass, which is the one way
      a cap test fails at its job while looking like it worked. Verified in both
      directions: green as written, and red with `6458 not less than or equal to 100` when
      the ceiling is lowered under the real count.
- [x] 4 — 2026-08-31. Four router repositories archived, each carrying a pointer
      rather than a redirect nobody can read.
  - **The stated check was already met before the step began**, though not in the
    spelling the table gives it. `git grep -c` prints one `path:count` line per file
    that matches and *nothing at all* when none do, exiting 1 — so "`git grep -c
    remoteIntegration bin/` = 0" describes an output the command cannot produce. What
    was actually run, and what a reader should run: `git grep -q remoteIntegration --
    bin/` exits **1**, and `git grep -l` prints nothing. Zero matches, and zero since
    the remote half went at steps 1 and 2. So step 4 was never about deleting code
    from here; it was about the repositories that code used to talk to, and the check
    confirms there is nothing left pointing at them from `bin/`.
  - Archived: `sd-github-review` (public, 5.1 MB), `sd-review-test`,
    `sd-github-review-pilot`, and `sd-review-control-plane` (archived 2026-08-30, the
    day before the rest). Each was verified first: 0 stars, 0 forks, 0 open issues,
    0 open pull requests, and last commit already the 3-c footprint removal.
  - **One live caller survives, named rather than assumed away.**
    `mezmo/mezmo_benchmark` still has two workflows with `uses:
    platypeeps/sd-github-review@…`. It is the D7 freeze repository, so it was matched
    by filename and not opened. Archiving does not break it — GitHub serves an Action
    from an archived repository — and that was verified rather than believed:
    `action.yml` at tag `v0.6.1` still resolves, 12,799 bytes, after the archive
    flag was set. Nothing else in the organisation calls the Action; the remaining
    hits are two clone lists in `system` and two orphaned
    `config/routed-review-setup-v1.json` descriptors, in `se-ai-command-pack` and
    `people-profiles`. `people-profiles` was not a consumer in the 3-c wave and is
    the one new name this sweep turned up.
  - **`sd-github-review` got a real README tombstone**, not the description-only
    fallback `sd-review-control-plane` had to take. Its protection carries
    `enforce_admins: true` but requires **0** approving reviews, so a pull request
    with green CI lands — #166, merged. The former README is kept below the notice as
    the record of what the Action did, and the notice says plainly that pinned
    callers keep working, because a tombstone that reads like a breakage announcement
    would send someone editing a workflow that is fine. The two private repositories
    got the same treatment by direct commit; all four also carry a `RETIRED <date>`
    line in their description, which is the part visible without opening the repo.
  - **Deliberately not swept here.** `docs/FLEET_ROLLOUT.md` (510 lines) and
    `docs/fleet/consumers.json` (330) describe a rollout that has completed and a
    fleet walk R10-D6 dropped; no code reads either, only `CONTRIBUTING.md` and two
    spec pages. `docs/spec/` still runs to 7,839 lines, much of it documenting
    machinery steps 0 through 2 deleted — `adapter-guidelines.md` still specifies a
    coordinator at `templates/scripts/sd-ai-command-pack-review.py` and a
    `.sd-ai-command-pack/review.json` schema, neither of which exists. That is step
    7's "triage survivors", and folding it in here would have made a repository
    archive into a documentation rewrite. Recorded so the next pass finds it by
    reading rather than by grepping.
  - The three `bin/` files that still name `sd-github-review` — `migrate-trellis`,
    `sd_setup_github.py`, `sd-status` — keep it on purpose. They name the retired
    footprint in order to detect and remove it from consuming repositories, and
    archiving the source does not remove the footprint from anywhere it landed.
- [x] 4b-i — 2026-08-31. The issue index and the GitHub tracker, split off from 4b
      because this half alone satisfies the step's stated check ("issue table populates
      in one refresh; :8767 unchanged") and the other half — Jira, the Issues tab,
      `sd-plan --from` — needs none of it decided differently.
  - **The store is a cache and says so in its own docstring.** `dashboard/store.py`:
    two tables, `issue` and `tracker_watermark`, at
    `~/.cache/sd-ai-command-pack/index.sqlite`. The cache root and not the state root,
    deliberately: `~/.local/state/` holds the handoff packets, which cannot be
    regenerated, and step 6's cleanup deletes legacy subdirectories under that root by
    name. A rebuildable database sitting beside unrebuildable packets is an invitation
    to exactly the sweep that must never reach them. A test asserts the path is not
    under `.local/state`.
  - **Rows are never deleted, and both halves of that are tested.** An issue that closes
    is updated in place; an issue that stops matching the search is left alone with the
    `last_seen` that says when the index last had evidence. The named gap, in the
    docstring rather than discovered later: because collection is windowed, a close that
    happens outside every future window is never seen, so the index can hold an `open`
    row for something long closed. That is why `last_seen` is a column. The answer is not
    a wider window — it is remembering this is a cache and the tracker is the truth.
  - **Four searches, not one.** `involves:@me` would collect the same rows in one call
    and lose *why* each arrived, which is the entire value: "three people want your
    review" and "you opened three issues" are the same count and different mornings.
    So `assignee`/`mentions`/`review-requested`/`author` are queried separately and
    unioned by URL with the reasons accumulated into `why[]`. `why` is replaced rather
    than merged on each collect, because a reason that stopped being true must stop
    being displayed.
  - **The watermark moves only on a successful collect**, and that is the property most
    worth protecting here. Rows from a partial collect are still written — they are real,
    and this is a cache — but advancing the watermark past a bucket that failed would
    step the window over those issues permanently rather than temporarily. A test drives
    a failing bucket and asserts both halves: the rows land, the watermark does not move.
  - **Pagination was not in the design and the first run proved it necessary.** One page
    of 100 per bucket looked sufficient until the first real collect reported
    `page ceiling hit: review-requested, author` — a 90-day first window against an
    account with 532 PRs in 60 days. Following the cursor to a ceiling of 10 pages turned
    1,130 rows into the answer instead of 203. The ceiling itself is still reported when
    hit, because a capped collect that renders as a complete one is worse than a failed
    one: it looks right.
  - **`--dump` stays offline.** It is the canonical-diff check, and putting a wall clock
    and a remote service inside a check whose whole value is being repeatable offline
    would end it. A test replaces both the subprocess runner and `store.connect` with
    functions that raise, then asserts `--dump` still exits 0.
  - **A defect found by running the check, not by reading the code.** Wiring the refresh
    into `index` made `tests/test_sd_dashboard.py::test_index_reports_counts` run a real
    `gh` against the network and write the operator's real `~/.cache` — a test escaping
    its sandbox into a home directory. The fix went into the shared `run_cli` helper
    rather than into the one test that needed it, so the next verb to grow a side effect
    inherits the redirection instead of discovering it. Proof: the real index file's
    checksum is identical before and after `python3 -m unittest tests.test_sd_dashboard`.
  - Checks, run: `python3 bin/sd-dashboard index` on the real machine printed
    `78 repos, 4 dirty, 0 ahead` then `issues: 0 new, 4 updated, 18 open` against 1,130
    indexed rows with the watermark at `2026-08-31T08:38:18Z` — the table populates in
    one refresh. `lsof -i :8767` still shows the system dashboard (PID 48405) and
    `git -C ~/repos/system status --porcelain` is empty, so :8767 is unchanged.
    `make check` exits 0; `dashboard/` is 846 lines of its 2,500 cap.
  - Deferred to 4b-ii, named rather than stubbed: the Jira collector (~90 LOC lifted),
    the Issues tab and "Needs you", `sd-status` `issues:` lines, and
    `sd-plan --from gh:o/r#N|jira:KEY`. An empty Jira collector in the inventory would
    answer nothing while reading as a feature that exists.
- [x] 4b-ii — 2026-08-31. The Jira collector, into the same index. Surfaces (Issues
      tab, "Needs you", `sd-status issues:` lines, `sd-plan --from`) are 4b-iii: this
      step finishes the collectors, and a tab over one and a half trackers would have to
      be revisited the moment the second landed.
  - **`trackers.py` is renamed to `github.py`, because it only ever held GitHub.** The
    two collectors share exactly one thing — the five-key contract
    `collect.refresh_issues` calls — and nothing else, because the services differ:
    GitHub is reached through the `gh` CLI and answers GraphQL, Jira over HTTP with
    basic auth and answers JQL. A shared base class would abstract over that split and
    buy nothing at two implementations.
  - **Three things carried over verbatim from the system dashboard, each learned the
    hard way.** `myself` is the availability check rather than the search, because bad
    credentials do not make a JQL search fail — Jira answers 200 with
    `{"issues": [], "isLast": true}` since `currentUser()` resolves to anonymous, who is
    assigned nothing, so the search cannot tell "your credentials are wrong" from "you
    have nothing to do". The account id and not the email is what issues are matched
    against, because Jira hides `emailAddress` on any site with the privacy setting on
    and empty-equals-empty marks every issue as both yours and theirs. And
    `watches.isWatching` is read rather than derived, because Jira has already computed
    it for the authenticated user.
  - **Three things deliberately changed, and the middle one would have been a defect.**
    *No default base URL:* the system dashboard falls back to a specific Atlassian host
    and this backbone carries no employer footprint, not even as a fallback, so an unset
    `JIRA_BASE_URL` is "not configured" and never a guess. *The window replaces the
    open-only filter:* a worklist wants open issues, but an index that never sees a
    close leaves the row saying `open` forever. *The window is relative minutes, never a
    timestamp:* JQL date literals resolve in the **Jira account's** configured timezone,
    which this machine has no way to know, and `-180m` has no timezone to get wrong.
    A straight port would have shipped a window silently offset by the account's UTC
    offset.
  - **Watermarks are per tracker, and a test proves one cannot step the other's.** Jira
    being unconfigured neither blocks GitHub from collecting nor lets GitHub's success
    advance Jira's window over a gap it never read.
  - **Two environment-dependent tests, caught before review this time.** The refresh test
    and the CLI harness both let Jira read the ambient environment, so a machine with all
    three `JIRA_*` variables exported would have had the suite open a socket against a
    real tenant. Both now pin `jira.settings`. This is the same defect class Copilot
    found in 4b-i's harness one PR earlier, which is why it was looked for.
  - Checks, run: `python3 bin/sd-dashboard index` on the real machine printed
    `issues[github]: 0 new, 5 updated, 18 open` and
    `issues[jira]: not collected (JIRA_BASE_URL and JIRA_EMAIL not set)` — one line per
    tracker, and the unconfigured one names the variables and reports no value.
    `make check` exits 0 over 59 dashboard tests; `dashboard/` is 1,195 lines of its
    2,500 cap.
  - **Named gap, not a fabricated check: the live Jira path is unverified on this
    machine.** `JIRA_API_TOKEN` is present in the environment; `JIRA_BASE_URL` and
    `JIRA_EMAIL` are not — they exist only in the system repo's `.env`, which this pack
    must not read, so no run here can reach a real tenant. What *is* verified: the
    not-configured path, live, against the real environment; and every parse, window,
    identity, paging and upsert path against fixtures shaped from the field list the
    system dashboard has been using in production. What would settle the rest is one
    run with the two variables exported — it belongs to whoever has them, and until then
    this row says unverified rather than green.
  - **Narrowed 2026-08-31 by the Jira MCP, which reaches the same tenant over a
    different transport.** The user pointed out the session already has it. It settles
    the half of the gap that is about *the query* rather than *the plumbing*: the
    collector's `DEFAULT_JQL` is valid against the real tenant and returns issues
    (RS-9, RS-8, RS-54 for a 3-hour window), the field list is accepted rather than
    rejected as unknown, and the paging shape matches the `nextPageToken` form the
    collector reads. What that run cannot touch, because the MCP authenticates itself:
    the HTTP path, basic auth from `JIRA_EMAIL` + `JIRA_API_TOKEN`, the `/myself`
    availability check, and `isLast` semantics on a real response. Those four are what
    "unverified" now means here — a smaller claim than yesterday's, and still not green.
- [x] 4b-iii — 2026-08-31. The surfaces over the finished index: Issues tab,
      "Needs you", and `sd-status issues:` lines. `sd-plan --from` moves to 4b-iv: it is
      a *seeding* path into a work item, not a view over the index, and it needs a
      documented resolution procedure because there is no `bin/sd-plan` to put it in.
  - **"Needs you" is a predicate on the row, not a fourth collector.** `store.needs_you`
    is open ∧ (`assigned` ∨ `review-requested`) — the two reasons that mean someone is
    blocked on the operator. `mentioned` and `author` are not: being named in a thread
    or having opened the thing is context, and a worklist that says fifteen items need
    you when three do is a worklist nobody reads. It lives in `store.py` beside the rows
    so the dashboard and `sd-status` cannot drift into two different definitions.
  - **`/api/issues` checks for the index by existence, not by opening it.** `store.connect`
    creates the database if it is absent, so the obvious implementation would make a GET
    that quietly writes a file. The endpoint stats the path and reports "no index yet"
    when it is missing.
  - **`sd-status` reports GitHub rows for this repo and names the Jira gap rather than
    guessing at it.** GitHub rows carry `repo`, so they match `pr_state.remote_slug(root)`
    exactly. Jira rows carry no repo and there is no config key mapping a project to a
    checkout — inventing one here would be machinery ahead of need, so the section says
    so in one line instead of attributing a Jira issue to whatever directory you happen
    to be standing in.
  - **An absent index is a reported state, like every other section here.** No index, no
    remote, and an unimportable `dashboard` package each print a reason and exit 0. The
    last of those was a real regression this step introduced: `bin/sd-status` imports
    `dashboard.store` from one level up, and the read-only suite deliberately runs a copy
    of `bin/` alone, where no such package exists. That test failed, which is how it was
    found; the import is now guarded and the degraded path has its own test.
  - **Five Copilot findings, all five real and all five mine.** The two that
    changed behaviour: `indexedAt` was derived from the *open* rows, so an index
    holding only closed issues would have reported never having been collected
    and the page would have called a fresh index stale — it now reads
    `MAX(last_seen)` over every row, because staleness is a fact about the
    collect and not about the queue. And the Jira fixture was shaped like a
    GitHub pull request, so the test asserting Jira rows are not attributed to a
    checkout would have passed against a filter that only compared repo slugs; a
    realistic Jira row (no repo, no number, a browse URL) now proves the real
    case and a second test keeps the repo-bearing row to prove the `tracker`
    half of the filter is load-bearing. Both guards were mutation-tested: revert
    either and exactly the new test fails. The other three were correct and
    cheap — `role="tablist"/"tab"/"tabpanel"` wiring behind the `aria-selected`
    the markup already carried, `rel="noopener noreferrer"` spelled out rather
    than relying on `noreferrer` implying it, and `sys.path` restored around the
    test helper's import so no later import in the module resolves differently
    depending on test order.
  - Checks, run: `make check` exits 0 (53 tests in `test_sd_status`, 36 in
    `test_sd_dashboard_index`, all suites green). Live `python3 bin/sd-status` in this
    checkout prints `issues (this repo, from the index)` / `none open` — verified genuine
    rather than an empty filter, by querying the index directly: 18 open rows, 15 needing
    me, **0** for `platypeeps/sd-ai-command-pack`. The empty is the right answer.
- [x] 4b-iv — 2026-08-31. `sd-plan --from gh:o/r#N|jira:KEY` gets a resolution path:
      `bin/sd-trackers ref`, one verb, printing the citation bullet the flag was
      always described as producing. The flag row had been in the skill since step 3
      with nothing behind it, which is the failure this step exists to close: a
      documented flag with no procedure resolves to whatever the session improvises.
  - **It does not read the index, and that is the whole design question.** The
    obvious implementation queries the SQLite index 4b-i and 4b-ii filled — it is
    right there, and it is free. It is also wrong: the index holds `involves:@me`
    and nothing else, so an issue nobody has assigned to you is absent from it and
    always will be. Planning against someone else's report is the ordinary case for
    `--from`, so reading the index would make the answer depend on the operator's
    involvement rather than on the reference. Both halves fetch live.
  - **One REST call covers both spellings.** `repos/{o}/{r}/issues/{n}` answers for
    a pull request too — GitHub numbers them in one sequence — so `gh:o/r#N` does
    not have to say which it meant, and the collector's GraphQL search stays a
    search. `pull_request` in the payload tells them apart.
  - **The link is the tracker's, never assembled.** An issue and a pull request
    differ in that path segment, so constructing `/issues/N` from the reference
    yields a link that redirects today and breaks whenever GitHub stops. Pinned by
    a test whose payload deliberately answers `/pull/8` to a `#8` reference;
    mutation-tested (build the URL instead and exactly that test fails).
  - **`merged` is a third state, and only here.** The index stores open or closed;
    this row never reaches it. A citation calling a landed pull request "closed"
    reads as work abandoned, which is the opposite of what happened.
  - **The bullet, not the section.** First draft printed `## References` and a
    blank line with it — and the PRD template already ships that heading, so every
    seeded item would have grown a second one. Caught by writing the paste down
    rather than by reading the code; the test now asserts both halves, that the
    output starts with `- [` and that the template still carries the heading.
  - **No issue body.** Jira v3 returns descriptions as Atlassian Document Format,
    a JSON tree, and rendering it would put a markdown converter inside a reference
    lookup. The deeper reason applies to GitHub too: prose copied into a work item
    is stale the first time somebody edits the issue. The citation carries the
    link; the issue keeps its own text.
  - **Exit 1 and exit 2 stay distinct.** 1 is "asked, and the reference did not
    resolve" — no such issue, a repository you cannot see, or an answer the client
    could not read; 2 is "could not ask" (`gh` unauthenticated, Jira variables
    unset, or a reference that does not parse, the accepted spellings being
    `gh:owner/repo#123` and `jira:KEY-123`). Collapsing them would make a mistyped
    issue number indistinguishable from an unconfigured tracker, and the skill's
    instruction —
    never hand-write a citation the command refused to produce — needs the operator
    to know which happened. The Jira half names the absent variables and never
    their values, with a test asserting the token value cannot reach the output.
  - **`jira.state_of` extracted rather than copied.** The collector and the
    reference lookup have to agree about what closed means; two copies of that rule
    is how they would stop agreeing.
  - **The Makefile's lint list now enumerates from the index**, which
    `tests/test_loc_caps.py` had already named as a trap in its own docstring. It
    was one: the list was missing `bin/sd_setup_github.py`, which had therefore
    been lint-clean by never having been linted since it landed. It passes ruff and
    mypy now that it is actually checked, but that was luck, not a gate.
  - **Named rather than quietly left:** `--from-suggestion` and `--from-proposal`
    are still rows with no procedure behind them. They land with `sd-suggest` and
    `sd-skill-adopt`; the skill now says so out loud instead of reading as though
    all three flags work.
  - Checks, run: `make check` exits 0 — 23 shards, 23 `OK`, 0 failures, including
    the 18 new tests in `test_sd_trackers`. Live against this repository:
    `sd-trackers ref gh:platypeeps/sd-ai-command-pack#636` prints the merged-pull
    citation, `#999999` exits 1 with `gh: Not Found (HTTP 404)`, `nonsense` exits 2
    naming both spellings, and `jira:ABC-1` exits 2 naming `JIRA_BASE_URL` and
    `JIRA_EMAIL` — the two unset on this machine — while never naming the one that
    is set. Three mutations were introduced and each failed the test written for it.
- [x] 5-i — 2026-08-31. The five agents, folded and governed. `agents/sd-*.md` in
      the checkout, rendered by the installer to `~/.claude/agents/`. Split off from
      step 5 because it is the half that can land without touching a single vault
      caller: agents have no scheduled consumers, so nothing outside this repository
      changes when they move.
  - **The `tools:` declarations were the reason to do this first.** Two of the five
    upstream templates — `se-claim-verifier` and `se-source-reader` — declare no
    tools at all. The governed versions existed only as files somebody had edited
    in place under `~/.claude/agents`, which the next install from the old pack
    would have silently overwritten with the ungoverned ones. The fold takes the
    *installed* tool sets, not the templates', and a test now asserts every agent
    declares some; a second asserts that an agent whose description calls itself
    read-only holds no `Edit`/`Write`. Both mutation-tested.
  - **`Bash` is deliberately not counted as a write tool.** `sd-rust-reviewer` calls
    itself read-only and holds `Bash`, because that is how it runs `cargo check`.
    Putting `Bash` in the write set would either fail a correct agent or push the
    rule back into prose; the check pins what it can actually decide.
  - **Agents render to Claude only, and that is a stated limit rather than an
    oversight.** Codex agents are TOML with the instructions embedded in a triple-
    quoted string. Emitting that is a translation layer, which is precisely what
    `render` refuses to be — its docstring's argument is that byte-identical files
    let the parity test assert agreement rather than assert that a translation ran.
    A converter nobody can byte-check is worse than a documented gap, so the gap is
    documented in the README and pinned by a test asserting nothing lands in
    `~/.codex/agents`. The five `se-*.toml` files there are old-pack renders; what
    to do about them is 5-iv's call, and it is a real one — deleting them without a
    replacement loses the Codex agent lane.
  - **The `sandbox_mode` question step 5 owns, answered:** the key is *absent* from
    all five `~/.codex/agents/se-*.toml`. Nothing enforced read-only there; the
    property was prose inside `developer_instructions` and nothing else. So there is
    no setting to carry across, and the honest statement is that the Codex lane
    never had the guarantee the Claude lane now has in frontmatter.
  - **Trellis residue removed at the fold, not after.** All five bodies told the
    worker that "when a Trellis task is active the line reads `Active task: <task
    path>`". Trellis is retired; the sentence now names the work item. A test fails
    on `Trellis` or a surviving `se-` anywhere under `agents/`.
  - **Naming.** `se-rust-*` → `sd-rust-*`, `se-claim-verifier` → `sd-claim-verifier`,
    `se-source-reader` → `sd-source-reader`. No collisions. Their descriptions cite
    `sd-typed-holes`, a skill that arrives in 5-ii — a one-pull-request window where
    the citation names something not yet folded. It resolves nothing at runtime, so
    it breaks nothing; named here rather than discovered later.
  - **The survey that preceded this, since it corrected the plan twice.** Counted
    from disk: 68 skills in `templates/skills/` (not 67 — `se-coherence-audit`
    landed 2026-08-28), so 65 fold rather than 64 after the three retirements. And
    the collision check the plan predicted at zero is **three**: `se-plan`,
    `se-status` and `se-handoff` are knowledge-work skills that collide with three
    engineering commands of the same name and are not the same tools. Resolved by
    the user, 2026-08-31: name them for the artifact they produce —
    `sd-objective-plan`, `sd-status-update`, `sd-continuity-packet`. The remaining
    62 rename mechanically. That lands in 5-ii.
  - Checks, run: `make check` exits 0 — 24 shards, 24 `OK`, including 11 new tests
    in `test_sd_agents`. Three mutations introduced (drop a `tools:` block, give the
    claim verifier `Write`, and the earlier render-kind change), each caught.
- [x] 5-ii — 2026-08-31. What the 65 skills need before they can arrive: the
      installer ships a skill's companion files, and a companion cited by many
      skills is stored once. Landed ahead of the fold, on fixtures, so the payload
      pull request is a rename and nothing else. (Renumbered: the vault retarget is
      now 5-iv.)
  - **The gap that forced this.** The old pack's skills carry `references/` and
    `scripts/` directories — 54 of the installed 67 have one — and this installer
    copied `templates/*.md` and nothing else. Folding as-is would have shipped 65
    skills whose instructions cite files that were never installed: the model is
    told to read `references/source-standards.md`, the read fails, and the run
    continues on whatever it remembered. Found by looking at the source tree before
    writing the rename script, not after.
  - **Extras are now derived, not named.** Every file under a skill directory
    renders at the path it already has. A skill that grows a `scripts/` ships it
    without the installer learning the word — the same rule the surface discovery
    itself follows.
  - **One stored copy, fanned out by citation.** Three files carry most of the
    references: `source-standards.md` is cited 90 times, `argument-vocabulary.md`
    55, `personal-profile-contract.md` 21. The upstream layout keeps them in
    `_shared/references/` and its installer copies them into each citing skill, so
    the machine has 54 copies and the repository has one. Committing the fan-out
    instead would put the same paragraph in git fifty-four times — "four copies of
    every shipped script" is on the diagnosis table this rebuild exists to answer.
    So `skills/_shared/references/` holds one copy and the render fans out.
  - **Driven by the citation, never by a list.** A file lands in a skill because
    that skill's text says `references/<name>.md`. A skill that stops citing one
    stops shipping it, with nothing to remember and no list to go stale. Pinned by
    a test asserting a non-citing skill gets no `references/` directory at all;
    mutation-tested by making the fan-out copy everything, which fails two tests.
  - **A skill's own file wins over the shared one of the same name**, so a skill
    that needs its own variant keeps it. Mutation-tested.
  - **The citation pattern has a boundary.** `docs/references/x.md` names a file in
    somebody's repository, not a companion; without the lookbehind the installer
    would hunt the shared directory every time a skill mentioned another project's
    path. This is the third time in two days that a bare substring match was the
    defect — the vault survey's `se-positives`, the agent test's `case-sensitive`,
    and now this — so it was written with the boundary rather than fixed into one.
  - **An unresolvable citation is reported, not fatal.** Same reasoning
    `sd-dashboard` uses for a tracker it cannot reach: the other seventy skills
    install correctly, and refusing all of them because one cites a missing file
    would make the installer withhold what it can still do. CI holds the number at
    zero — `test_skill_companions` fails on any citation this checkout cannot
    resolve — so the warning is for a checkout mid-edit, not a licence.
  - **Receipt kind renamed `template:` → `companion:`**, because these are
    references and scripts now and a kind naming one of the three reads as a bug in
    the other two. Kind is metadata; `prune` keys on the path, so an existing
    receipt rewrites its rows without touching a file.
  - Checks, run: `make check` exits 0 — 25 shards, 25 `OK`, including 11 new tests
    in `test_skill_companions`. Three mutations introduced (copy every shared file,
    let shared win over local, drop the citation boundary), each caught.
- [x] 5-iii — 2026-08-31. Sixty-four skills folded, in two commits so the first
  one is provable. The plan said 64 and the source tree holds 68, which is the
  same number once the retirements are counted: `se-help`, `se-brand-voice`,
  `se-humanizer`, and a fourth decided in this step.

  - The fourth retirement is `se-review-skills`, raised as a decision because it
    is not a prose skill: 3,258 lines of which 2,115 are
    `scripts/skill_review.py`, whose `_discover` is hard-coded to two layouts
    that no longer exist — `templates/skills` and `templates/.agents/skills` —
    and which reads a `.se-ai-command-pack/provenance.json` this pack does not
    write and a `generated/skills/` it does not produce. It has no scheduled
    caller and `skills/` is under no LOC cap, so folding it would have landed a
    broken script uncapped, and retargeting it meant owning a 2,115-line
    discovery path of unmeasured coupling depth. Retired. What is lost, named
    rather than waved away: there is now no deterministic multi-skill audit, and
    no usage evidence was available either way — if it turns out to be run, this
    was the wrong call and folding it back is a decision record, not a chore.
    `sd-skill-retro` says so in its own scope section rather than pointing at a
    surface that is gone.
  - Three names collide with a command, so those three are named by the artifact
    they produce rather than mechanically (user, 2026-08-31): `se-plan` →
    `sd-objective-plan`, `se-status` → `sd-status-update`, `se-handoff` →
    `sd-continuity-packet`. The other sixty-one rename mechanically. Collision
    check against the twelve: zero.
  - The rename map is anchored, not substring. `(?<![\w-])se-` is the whole
    difference between a correct fold and a broken one: the unanchored spelling
    matches inside `prose-lint`, `use-case`, `case-study`, `database-update` and
    nine more, and would have rewritten ordinary English into `sd-` tokens. Same
    defect class as three earlier this week, caught here before it was written
    rather than after.
  - The first commit is mechanical by construction and was checked that way:
    re-running the map over the source reproduces all 71 files byte for byte,
    no file is missing, and none is shipped that the source did not have. The
    check is what makes the second commit readable — everything a reviewer has
    to think about is in it.
  - The second commit carries what the byte-diff cannot see, because in the
    source it all resolved. Retired skills still cited: `sd-prose-lint` handed
    rewrite-shaped findings to `sd-humanizer` at six places including step 7 of
    its own procedure; `sd-technical-editor` gave house-voice conformance to
    `sd-brand-voice`; three more routed to the humanizer. Trellis surfaces still
    named: seven skills shared one dispatch boilerplate opening a worker prompt
    with `Active task: <task path from task.py current>`, retargeted to the item
    directory as the agents were in 5-i; `trellis-check` and `task.py` went to
    `sd-check` and `sd-status`; `sd-skill-retro` still sent fixes to
    `templates/skills/<name>/SKILL.md`. And `sd-retro` was telling itself to
    route to `sd-retro` — the name it meant belonged to the Trellis-era pack,
    which is the one hazard of a one-prefix fold: a reference that was to
    *another* pack silently becomes a reference to this one. Audited by
    enumerating every pre-existing `sd-` token in the source: 36 of them, 30
    being "the sd-review lane" (still correct) and one being that self-route.
  - Two spellings survived the rename because the map's lookahead required a
    lowercase letter after the prefix: three `se-*` globs, and — found in
    Copilot's third round, not by me — the H1 of every one of the sixty-four
    folded skills, still reading `# SE Typed Holes` while the directory,
    frontmatter, and every cross-reference in the same file already read
    `sd-typed-holes`. This is the sharpest statement of what a byte-diff does
    and does not buy: it proves the map was applied consistently, never that
    the map was complete, and a check derived from the map cannot find what the
    map never matched. The guard added for it compares each title to its own
    directory name rather than banning a spelling, so it needs no list and the
    next stale title fails whatever it says.
  - `tests/test_skill_frontmatter.py` pinned the tree to exactly twelve
    surfaces, so the fold could not land without it. A roster of every surface
    is what stops working at seventy-six; the half worth keeping is the other
    half. The commands are exactly these eleven — twelve named surfaces less
    `sd-help`, which the taxonomy makes a skill because a catalog authorizes
    nothing — and skill-ness is asserted per file, no `disable-model-invocation`
    and no `tools:`, for every surface that is not one of them. A sixty-fifth
    skill needs no edit here; a twelfth command still fails, which is what
    standing rule 2 asks for. The two tool-contract suites are scoped to the
    twelve named surfaces: a folded skill documents no CLI, so it has no `bin/`
    absence to disclose.
  - The retired-selector drift guard fired on
    `sd-coherence-audit/references/ledger-format.md`, which numbers its
    redundancy findings `R-4`. `\bR-\d` is a shape, not a claim. The exemption
    is written as "this file declares its own class-letter id scheme" rather
    than "this file does not mention `sd-status`", because the second spelling
    would have disarmed the guard over `skills/sd-plan/templates/prd.md` — an
    empty template naming no command, and exactly where a retired selector could
    reappear unread. Two tests hold it: neither status surface can claim the
    exemption, and the set of files that do is asserted to be the one.
  - Checks, run: `make check` exits 0 — 25 shards, 25 `OK`. The installer
    dry-run renders 76 surfaces (485 files) to three platforms with no
    missing-citation warning, so every `references/` path the folded skills cite
    resolves through 5-ii's fan-out. Three mutations on the drift guard (plant
    `R-7` in `sd-status`, plant `F/T/R` inside the exempt file, give
    `prd.md` the four sibling class letters), each caught; two more on the
    fold guards (remove four folded skills, restore a `# SE ` title), each
    caught.
- [x] 5-iv — 2026-08-31. Retarget, install, delete, in that order. Two of the
  three enumerations I started from were wrong, and both were wrong the same
  way: written from the plan instead of read off the machine.

  - The vault half was smaller than the plan implied and needed no decision.
    Eight tokens in two Scheduled Task files — `se-research` ×6, `se-scan` ×2 in
    `market-watch` and `blog-idea-accept` — retargeted and committed before
    anything was deleted, because `market-watch` runs unattended at 03:00 and a
    routine naming a skill that no longer exists fails into whatever the session
    improvises. The "five live vault docs citing `se-ai-command-pack`" I had
    flagged as a decision are not callers: `VAULT-STRUCTURE.md` and `Schema.md`
    name the old pack **inside a retarget note dated 2026-08-30**, which is the
    sentence explaining what moved; `Vault Map.md`, `Schema.md:105` and
    `vault-normalize.py:202` carry it as a **project-slug vocabulary value**, and
    deleting the slug would orphan every note already tagged with it. Left alone,
    deliberately.
  - The Codex agent lane is retired (user, 2026-08-31). Five hand-written
    `~/.codex/agents/se-*.toml` had no producer in the new pack, and the
    alternative was a TOML emitter — the first non-verbatim render in a pack
    whose whole install is byte copies, and a translation layer whose output
    could only be checked by asserting the translation ran. Cost checked before
    proposing it rather than after: three folded skills name the agent trio, and
    all three make the delegation optional (`sd-typed-holes` says "optionally
    delegate", `sd-research` says a unit "may be dispatched"), so a Codex session
    degrades to running the passes inline. Nothing in `~/.codex/config.toml`
    referenced them.
  - **Two roots the plan did not know about**, found by running the old pack's
    own `remove --dry-run` instead of deleting the four paths from the checklist:
    `~/.config/agents/skills/` held 196 files, and `~/.se-ai-command-pack/` held
    the receipt. 599 files removed in total; the dry-run was first checked to
    contain zero `sd-` paths. The remover preserved two agents whose content
    differed from what it installed — `se-claim-verifier` and `se-source-reader`,
    the same two whose installed `tools:` had drifted from their templates, which
    is how 5-i found them — plus 56 `.bak` files it never owned. Deleted by hand
    after confirming the `sd-*` successors carry identical tool sets.
  - **The enumeration I got wrong, and only found by breaking it.** I swept the
    vault and `~/repos/system` for callers and deleted. `sd-writing-pack` points
    an `Agent` at `~/.claude/skills/se-research/SKILL.md` and
    `~/.claude/skills/se-fact-check/SKILL.md` by absolute path, from four
    pipeline steps — so the delete broke it, and the doctrine this step is built
    on ("retarget before deletion") was satisfied for two consumers out of three.
    Fixed in `sd-writing-pack@1010ec4`: `sd-research`, `sd-fact-check`,
    `sd-propose-skills` across eight files. The lesson is the same one as the H1
    miss in 5-iii, in a different shape: a sweep over the consumers I could name
    cannot find the consumer I did not think of. The check that would have caught
    it is grepping for the *installed paths* about to be deleted, machine-wide,
    rather than for the skill names in the repositories I had in mind.
  - The break exposed a claim that was false before the fold. Four places in
    `sd-writing-pack` said these skills carry `disable-model-invocation: true`
    and are therefore slash commands the pipeline cannot fire. The evidence
    against that is in the pack the claim was written about:
    `~/repos/platypeeps/se-ai-command-pack/tests/test_generate.py:320` asserts
    the marker is **absent** from `se-research`. That checkout is archived at
    step 7, so the claim carries forward here instead —
    `KindMarkerTests.test_skills_do_not` asserts every surface that is not one of
    the eleven commands, `sd-research` and `sd-fact-check` among them, carries no
    `disable-model-invocation`. The sub-agent handoff
    is still right — a research pass reads a great deal and none of it belongs in
    the pipeline's context — so the mechanism stayed and the reason was corrected.
    Same for `model: opus`, which the frontmatter never pinned.
  - **Correction to the bullet above, from evidence found while starting 5b.**
    `local-cron-jobs/logs/market-watch.log` records the 2026-08-27 unattended run
    stopping on a blocker it quotes verbatim: *"Skill se-research cannot be used
    with Skill tool due to disable-model-invocation."* So the marker was really
    there — on the **installed render**, which is what an unattended routine
    reaches. The template it was rendered from did not carry it, which is what
    `test_generate.py:320` asserts and what I checked. Both facts are true and I
    reported only one of them: installed had drifted from template, the same
    class of drift 5-i found in the two agents' `tools:` and the same reason.
    `sd-writing-pack`'s claim was therefore right about the machine and wrong
    about the source, and what I wrote flattened that into "false". The
    mechanical cause is gone — `disable-model-invocation` appears zero times in
    `~/.claude/skills/sd-research/SKILL.md` — so a routine naming `sd-research`
    can now reach it. **Not verified:** that it does, which is still the
    2026-09-01 03:00 run's evidence and not something a grep can stand in for.
  - Checks, run: `ls ~/.claude/skills | grep -c '^se-'` = 0, same for
    `~/.codex/skills` and `~/.config/opencode/commands`; `~/.claude/agents` holds
    5 `sd-*` and 0 `se-*`; `~/.codex/agents`, `~/.config/agents` and
    `~/.se-ai-command-pack/` no longer exist. 76 surfaces render to three
    platforms. `grep -rn 'se-research\|se-scan' 'System/Scheduled Tasks/'` = 0,
    and `sd-research`/`sd-scan` both resolve. Every `~/.claude/skills/<name>`
    path in `sd-writing-pack`'s live surfaces now points at a directory that
    exists. **Not verified:** the next unattended `market-watch` run at 03:00 —
    that is tomorrow's evidence, and nothing here can stand in for it.
- [x] 5b-i — 2026-08-31. `bin/sd-skill-adopt`: the five stages in one place,
  and the one design decision that made the step's own check possible.

  - **The stage split is the whole design.** `--lint-only` runs stage 2 and
    stops. That is not an economy, it is what makes "adopt-lint green on all
    installed skills" a check that can pass at all: stage 1 screens *untrusted*
    text for the shapes that make an arbitrary file dangerous, and the patterns
    it matches — `ignore all previous`, `mcp__gmail__*`, `curl | sh` — are
    exactly the ones a document *about* prompt injection quotes. Pointing it at
    a tree of skills you already trust reports the documentation as the threat,
    starting with this pack's own `sd-skill-adopt`. Stage 2 asks only "is this
    the shape of a skill", which is worth asking of every skill on the machine.
    `LintTests.test_the_lint_does_not_run_the_pre_screen` pins the split so it
    cannot erode into one stage later.
  - **Every scanner rule is pinned from both sides.** A pre-screen that refuses
    everything passes every test written from hostile fixtures alone, and a wall
    is the failure this command exists to replace — ten proposals, six stages,
    four repositories, zero adopted. So `PrescreenAcceptanceTests` carries a
    skill that fetches a page, one that names the environment variable its tool
    needs, and one that mentions an address, and each must pass clean.
  - **Exfiltration is the pair, not either half.** A network verb is ordinary
    and a credential-shaped env-var name is documentation; together they are the
    shape that sends one to the other, and nothing in a static read can say
    which line feeds which. So `curl` alone warns, `GITHUB_TOKEN` alone warns,
    and the combination refuses. Reading a credential *store* (`~/.ssh`,
    `auth.json`, `.netrc`, `.env`, an environment dump) refuses on its own,
    because no skill's job is that wide.
  - **A finding names its rule and its line and never quotes the match.**
    Scanning for a credential means one may well be there, and a report that
    echoes the hit to be helpful publishes the thing the scan was for.
    `FindingHygieneTests` asserts a planted secret appears in no rendered
    finding.
  - **The command marker is a stage-3 refusal, not a stage-2 shape error.** The
    marker is legitimate — eleven surfaces here carry it — so the lint only
    requires it to be a boolean. What may not happen is an incoming file
    arriving with standing authority to act: granting that is a decision record,
    not a flag. Keeping it out of the lint is also what stops `--lint-only` from
    refusing this pack's own commands.
  - **Every refusal test asserts the destination is still empty**, not merely
    that the exit code was 1. A tool that writes and then reports a refusal has
    refused nothing. A URL is fetched into memory and screened there, so a
    hostile candidate leaves nothing on disk at all.
  - `--from-repo` without `--list` exits 2 rather than falling through to a
    write. Report-only is the flag's only mode, not a convention to be
    remembered — the same reasoning that made `--lint-only` on an empty tree
    exit 2 instead of 0, since "I linted nothing" reported as a pass is how a
    mistyped path becomes a green check over a directory nobody read.
  - Landing the tool moves the surface from `UnbuiltSurfaceTests` to
    `DocumentedFlagTests`, so the skill lost its "there is no `bin/`" section and
    every flag it documents now has to exist. It also corrected a count the
    skill had carried since it was written: the collision check is against
    **eleven** commands, not twelve — `sd-help` is the taxonomy's stated
    exception and was never one.
  - Checks, run: `--lint-only ~/.claude/skills` → **138 skills, 0 findings,
    exit 0**; `~/.codex/skills` → 79, 0, exit 0; this repository's `skills/` →
    76, 0, exit 0. Mutation-checked rather than trusted: a fixture with a
    mismatched `name` and an empty `description` produces exactly those two
    findings and exit 1, so the zero above is a result and not an empty loop.
    `make check` exit 0, 47 new tests. `bin/` is 7,487 lines against the 8,000
    cap.
  - **A path traversal, found in review and fixed in the code rather than in a
    test.** Copilot asked for a test pinning that a hostile `name:` from stdin
    or a URL is refused. There was no such test because there was no such
    refusal: on those two paths there is no directory for the frontmatter to
    disagree with, so `name:` alone decided the destination, and
    `name: ../../evil` resolved outside the skills root — in the one tool whose
    entire job is handling files nobody has vetted. The fix is a lint rule that
    a name is a single path segment, chosen after measuring rather than before:
    all 138 names under `~/.claude/skills` and all 79 under `~/.codex/skills`
    already sit inside `[A-Za-z0-9._-]`, so the rule costs nothing real. It went
    in the *lint* rather than at the write so every path that writes a skill is
    covered once, with a resolved-inside-root assertion at the write as the
    check that survives a later refactor adding a path that skips the lint.
  - **What the tool found on its first real use, which is the argument for
    having built it.** Surveying `sd-writing-pack` reported "no skills found"
    for a repository holding twelve: `--from-repo` looked one level down, and
    repository skills live under `.claude/skills/`, `.agents/skills/`,
    `templates/skills/`. Fixed by walking rather than by listing the
    conventional places, since a list would reproduce the bug at the next
    convention. Re-run, the survey then found something else: **nine tracked
    `.github/skills/trellis-*` directories still live in this repository**, 43
    files, Copilot-facing on every pull request here, instructing on machinery
    step 2 removed. Step 2's check was `ls .trellis` fails, and `.github/skills/`
    is not `.trellis/`. Recorded here and left for **step 7** — *reversed the
    same day: Sven pulled it into 5b, and 5b-ii deletes it. The survey had
    undercounted it too; see below.*
  - The survey also measured the thing the stage split was argued from rather
    than leaving it asserted: across this repository's 85 skill files the
    pre-screen flags exactly two, `sd-skill-adopt` (6 rules) and `sd-review`
    (1). Both are surfaces that *document* the patterns. Across
    `sd-writing-pack`'s 13, it flags none.
- [x] 5b-ii — 2026-08-31. The retirements, and one deletion pulled forward.
  Three repositories, because the thing being retired lived in three.
  - **`skill-proposal-accept`, retired.** Order matters and was: unschedule
    (`cron-jobs.sh uninstall`, so nothing could fire mid-edit), then delete the
    files, then clean the rosters. It went on its own evidence rather than on
    the plan's say-so: the database holds **8 declined, 2 filed, 0 pending**, so
    retiring it stranded no decision. `System/Scripts/file-work-item.py` went
    with it — the routine was that script's only caller.
    Vault `c64ea2e`, system `e397f8a`.
  - **The vault now writes nothing outside itself at all.** The "one authorized
    outward write" carve-out in `VAULT-STRUCTURE.md` had exactly one consumer
    and one implementation, and both are gone. The carve-out text is struck
    through rather than deleted: a permission that once existed is worth being
    able to read back, and it is the shape any future outward write should have
    to argue against.
  - **Two of the three enumerated targets were already gone**, and are recorded
    as findings rather than claimed as deletions this step performed:
    `file-trellis-task.py` (succeeded by `file-work-item.py`; only a stale
    `__pycache__` entry and a lineage mention remained) and the legacy
    gito/prism skill folders (absent from every render root and from
    `installed_plugins.json` — most likely swept by 5-iv's 599 files).
  - **The roster sweep missed three files, and the miss is the lesson.** The
    first pass cleaned the vault and the cron job and reported clean. Re-running
    the enumeration from the filesystem afterwards found three live claims left
    in `~/repos/system`: the dashboard's `machine` map, which said `filed` on
    Skill Proposals is written by `skill-proposal-accept` — so the dashboard's
    refusal message named a routine that no longer exists — the dashboard
    README's status table saying the same, and `local-obsidian-review`'s README
    listing it among the nightly routines that act on the digest buttons. Fixed
    in system `da1b27b`. The check that caught it is the one that should have
    run first: grep every repo that *names* the thing, not the two you edited.
  - **What survives deliberately.** `filed` stays a view on Skill Proposals —
    two notes carry it, they are history, and history stays visible. The
    Accept/Decline buttons stay with nothing behind them: the decision is the
    whole record now, and adoption goes through `sd-skill-adopt`.
  - **The Copilot-facing Trellis render, deleted — pulled into 5b by Sven,
    reversing 5b-i's "leave it for step 7".** And it was larger than 5b-i's
    survey reported. The survey found nine `.github/skills/trellis-*`
    directories because it was looking for skills; enumerating the directory
    instead found the whole platform render: **51 files, 6,395 lines** — those
    nine skill trees, three `.github/agents/trellis-*.agent.md`, and two
    SessionStart/userPromptSubmit hooks wired by `.github/copilot/hooks.json`
    and `.github/hooks/trellis.json`. Every one of them reads `.trellis/`, which
    step 2 deleted, so this has been **dead since step 2** while still being
    injected into every Copilot session on every pull request here. A tool that
    surveys skills finds skills; the directory listing found the rest.
  - Two stale entries went with it, both found by checking whether the paths
    exist rather than by reading the list: `.gitattributes` held nothing but a
    whitespace exemption for `.claude/skills/trellis-*` and
    `.agents/skills/trellis-*`, neither of which has existed for several steps,
    so the file is deleted outright; and ruff's `extend-exclude` named
    `.github/skills` and `tests/fixtures/trellis-scripts`, the second of which
    was also already gone.
  - **`.github/copilot-instructions.md` was the other half, and Copilot found
    it.** The review flagged two deleted paths the file still named. Enumerating
    every path it named found the real state: of the vendored-payload families
    it listed — `.trellis/scripts/**`, platform skill and command trees under
    seventeen tool directories, `.github/copilot/**`, `scripts/trellis-*.sh`,
    `.gito/`, `.prism/`, `.sd-ai-command-pack/`, `docs/SD_AI_COMMAND_PACK.md` —
    **not one still exists as tracked content**, and `scripts/` is not a
    directory in this repository at all. So the primary Copilot instruction
    surface was telling the reviewer, on every pull request in this rollout, to
    treat as untouchable vendored payload a set of files that is empty, and
    offering a handoff-comment protocol for routing fixes upstream to a Trellis
    that is gone. Rewritten to what is true: no file here is a copy, so there is
    no file to decline to review on ownership grounds. The two guidance markers
    went with it — nothing reads them. My own grep had missed this file because
    I truncated the enumeration with `head -30`; the finding is Copilot's.
  - Checks, run: `routine_skill_drift` **1 → 0** (the vault's own normalizer
    caught the intermediate state — a `.job` pointing at a deleted `SKILL.md` —
    and cleared once the system-repo half landed); `machine-setup.sh status`
    reports every cron entry ok; `grep -rn skill-proposal-accept` across vault
    and system returns only dated history and one deliberate lineage comment;
    `~/repos/system/local-project-dashboard/dashboard.py` compiles. In this
    repository, `ls .github/` is down to
    `scripts/`, `workflows/`, and five files, none of them Trellis.
- [x] 6 — 2026-08-31. M3, the machine cleanup. Deletion by name, because the
  receipt grants no authority over any of it: these directories were written by
  the fleet installer the receipt replaced, so `--uninstall` would correctly
  refuse to touch them. That is the reason the plan says "by name" rather than
  "receipt-driven" for this half.
  - **Nothing read them.** Checked before deleting, across the pack's `bin/`,
    `tests/`, `skills/` and `agents/`, the whole `~/repos/system` tree, and every
    installed render on all four platform homes: **zero references** to
    `work-loops`, `fleet-timing`, or `fleet-campaigns`.
  - Deleted under `~/.local/state/sd-ai-command-pack/`: `work-loops/` (10
    digest-keyed loop states, newest 2026-08-29), `fleet-timing/` and
    `fleet-campaigns/` (release-refresh timings back to 0.55.2 in July), and
    `machine/`, which was **already empty**. State root is now exactly
    `handoff/` and `installed.json` — nothing else.
  - **`handoff/` survived with its pre-step timestamps** (created 2026-08-29
    18:55, mtime 18:56), which is the check: not "the directory exists" — a
    delete-and-recreate would satisfy that — but that it was never touched.
    `intents/` does not exist yet; the dashboard creates it at 6b, so there was
    nothing to protect and the record says so rather than claiming a pass.
  - The plan's real check here was "a packet written before the step is
    restorable after", and `handoff/` was empty, so that check had no subject.
    Ran the mechanism end-to-end against the post-cleanup state root instead:
    `sd-handoff --cwd <scratch>` wrote a 703-byte packet, `--show` read it back,
    and a second `--show` refused — *"a packet loads exactly once"*. Probe
    packet removed; `handoff/` back to empty.
  - **Plugin rows: 7 → 0.** One user-scope and six project-scope rows for
    `sd@sd-ai-command-pack 0.71.62`, all pointing at the same cache install. The
    user row went through `claude plugin uninstall`, leaving six. Exactly one of
    those six went the same way — the run in `anomaly-metric-creator` that
    showed why the other five could not. Run from a project directory the CLI
    *creates* a `.claude/settings.json` holding `{"enabledPlugins": {}}` in a
    repository that had none, which is the framework altering a repo file for
    its own purpose: `git status` went from clean to `?? .claude/settings.json`.
    The stub was removed and that repository is clean again, but the lesson
    stood, so the **remaining five** rows were removed from the global
    `installed_plugins.json`, which is where they actually live, touching no
    repository. `claude plugin list` agrees: four plugins left, none of them sd.
  - Marketplace registration and the 0.71.62 cache install removed with it. The
    M0 tombstone is unaffected — it is a published release on GitHub, not a
    local registration, so the reach-back signal for the second machine still
    stands.
  - **Both spellings, zero.** `find` over `$HOME` for `work-loops`/`work_loops`,
    `fleet-timing`/`fleet_timing`, `fleet-campaigns`/`fleet_campaigns`, and for
    an underscore `sd_ai_command_pack` root under `.local`, `.cache`, `.config`:
    nothing.
  - **The re-render, which the status line asked for.** `--status` reported
    "3 modified". They were not hand edits: the three `sd-skill-adopt` renders
    (claude, codex, opencode) were stale against 5b-i's rewrite of that skill.
    `--pull` re-rendered; `--status` now reads the merged commit with **0
    missing, 0 modified**, 76 surfaces on each of three platforms.
  - **OmniRoute residue (R11-D2) is already gone**, so the list this step was to
    print is empty: `~/repos/ai/OmniRoute`, `~/repos/system/local-OmniRoute`,
    and `~/repos/platypeeps/omniroute-test` are all absent, `~/.claude.json`
    holds no matching project entry, and no `OMNIROUTE_*` name is exported.
    Recorded as a finding, not claimed as a deletion this step performed.
  - **The plugin residue: listed as a decision for Sven, then swept when he
    took it** (2026-08-31, in the session that ran this step). Three orphaned
    cache trees survived their uninstalled plugins under
    `~/.claude/plugins/cache/` — `kimi-marketplace` (45M), `google-gemini`
    (8.6M), `openai-codex` (320K) — plus two `temp_git_*` directories there and
    a `google-gemini` entry in `extraKnownMarketplaces` in
    `~/.claude/settings.json`. The first version of this record filed them under
    steps 3a/3b; that was wrong, and P2's own record says so: *"Left for step 6
    (M3), named so it is not rediscovered: the two marketplaces stay registered
    … and their `~/.claude/plugins/cache/` trees are still on disk."* They were
    always this step's.
  - **Checked before deleting, because the check nearly reversed the decision.**
    `openai-codex/codex/1.0.6/agents/codex-rescue.md` and the kimi 1.9.5 tree
    are the *only* copies of those agent definitions on this machine — the pack
    vendored none of them, and `agents/` holds five `sd-*` files and nothing
    else. That looked like deleting the last copy of something P2 was supposed
    to preserve. P2's record settles it: nothing was vendored **on purpose** —
    the kimi agents are gated on a `/kimi:setup` hook never registered here, and
    `codex-rescue` is a forwarder to a plugin-owned Node script, so vendoring
    either would have copied dead surfaces. The caches are dead weight, not the
    last copy of anything wanted. Swept: **54 MB**, cache down to the four live
    plugins, `claude plugin list` unchanged at four enabled.
  - **`PATH` in `~/.claude/settings.json`, three dead entries removed.** Only
    one of the four plugin `bin` directories it named exists (caveman); the
    other three — claude-mem's, naming 13.13.1 while 13.18.0 is installed, plus
    codex's and claude-hud's — point at versions that are gone, and **no version
    of those plugins ships a `bin` directory at all**, so there was nothing to
    repoint them at. Removed rather than updated. Verified after: 22 segments,
    zero empty ones, the surviving plugin entry resolves, and both
    `sd-handoff-restore` hook rows are intact.
  - Six non-plugin `PATH` entries also name directories that do not exist —
    `~/bin/x86_64_Darwin`, `~/.composer/vendor/bin`, `/pkg/env/global/bin`, and
    three macOS `cryptexd` bootstrap paths. Left alone: they are user tooling
    and OS-managed paths that come and go, not framework residue, and a missing
    directory on `PATH` costs nothing. Named so the next reader does not take
    the plugin sweep for a full audit.
- [x] 6b — dashboard swap to :8767 behind the parity checklist. Nine
  sub-steps, closed 2026-09-01 with 6b-9.
  - **The checklist is written, and it lives here.** It was drafted as a
    separate `dashboard-parity.md` and `sd-docs-lint` refused it — *"a work item
    holds prd.md, design.md and implement.md only"*, rule 1, on the pack's own
    work item. The gate was right and the file was folded in rather than the
    rule relaxed; the tables below are that checklist. Written 2026-08-31,
    before any swap.
  - Both columns are enumerated **from the running code**, not from design.md,
    and that matters: design.md names the target tabs as "Now · Work · PRs ·
    Issues · Repos · Queues · Suggestions · Skills · Sessions", and only three
    of those nine are tabs the system dashboard actually has. That list is the
    destination, not an inventory.
  - **What each side serves today.** The system dashboard
    (`~/repos/system/local-project-dashboard/dashboard.py:1455`) has fifteen
    tabs from thirteen collectors: Needs you
    and Projects (both derived client-side, no collector), Work
    (`collect_work` rollup plus `/api/work` for the timeline), Research
    (`collect_research`, checkouts carrying `research.conf.py`), Repos
    (`collect_repos`, the `repo-sync` profile plus on-disk checkouts), Issues (`collect_issues` +
    `collect_github_issues` + `collect_jira`), Vault (`collect_areas`) and Briefs
    (`collect_briefs`, both read the vault), Toolbox (`collect_toolbox`,
    `launchctl list` for `com.sven.*` and the job logs), Ports
    (`collect_ports`, `machine-setup.sh candidates service`), and five `db-*` queue tabs — blog,
    tip, skill, topic, watch — from `collect_queues`. Two collectors feed no
    tab of their own: `collect_prs` and `collect_rtk`.
    The pack dashboard had, when this was surveyed, **two** tabs -- Repos and
    Issues -- from two collectors and four HTTP routes (`/`, `/app.js`,
    `/api/state`, `/api/issues`). `sd-dashboard index --dump` returns 79
    checkouts, so the Repos half is real and not a stub. *(The survey is left
    at its date, as the rest of this entry is; the `Built?` column below is the
    live one, and it is what the swap gate reads. Today: three backbone tabs
    and five plugin tabs, six routes -- `/api/work` and `/api/plugins` joined
    the four.)*
  - **Where each tab lands**, per design.md's rule that system views stay
    system-owned behind plugin tabs declared in a registered manifest while
    the shell and the
    framework-native facts fold into the backbone:

    | Tab | Destination | Built? |
    |---|---|---|
    | Repos | backbone | **yes** |
    | Issues | backbone — the one migrating view (R3-D13) | **yes** |
    | Work | backbone | **yes** — 6b-5a, a rewrite against `docs/work/` and not the port this row implied |
    | Now · PRs | backbone | **yes** — Now at 6b-5b, PRs at 6b-5c |
    | Queues | **plugin tab** — moved from backbone by R11-D21: it was a vault view with a write path, like Vault and Briefs | **yes** — 6b-6, read-only; the write did not come with it (R11-D25) |
    | Skills · Sessions | backbone, **new** — no system counterpart | **yes** — 6b-5d |
    | Suggestions | backbone, **new** — **blocked on `sd-suggest`**, which is unbuilt (R11-D22): no producer, no draft, nothing to render | n/a until the command exists |
    | Toolbox · Briefs · Vault · Research | **plugin tab**, stays system-owned | **yes** — 6b-4, through `~/repos/system`'s own manifest |
    | ~~Jira personal~~ | **no such tab** — enumerated 2026-08-31; Jira renders inside `issues`, which is already backbone | n/a |
    | Projects | derived; folds into Now/Work rather than porting | n/a |
    | Ports | **plugin tab** beside Toolbox (R11-D12) | **yes** — 6b-4, the fifth declared tab |
    | rtk savings | rides Toolbox — it is a card in `renderToolbox()`, not a tab | n/a |
  - **The verdict as surveyed on 2026-08-30: two of fifteen tabs existed and
    thirteen did not**, four of those thirteen being new surfaces with no
    system counterpart to port from. *(Enumerated live 2026-09-01, from `app.js`'s tab list and the
    loader's own reply rather than from this paragraph: **thirteen tabs
    serve** -- seven backbone (`repos`, `issues`, `work`, `now`, `prs`,
    `skills`, `sessions`) and six plugin (`toolbox`, `briefs`, `vault`,
    `research`, `ports`, `queues`). Two of the four new surfaces shipped at
    6b-5d and Queues at 6b-6; what is left is Suggestions, which R11-D22
    blocked. An earlier revision of this note said eight, and it was already
    stale when the PRs tab landed; this one said twelve and went stale the
    same day -- which is the argument for enumerating rather than updating,
    and the reason the enumeration is dated.)*
  - Three pieces of the contract are absent beyond the tabs: no plugin-tab
    loader at all (five tabs are supposed to arrive through one — 6b-2 has
    since built it, recorded in its own entry below rather than backdated into
    this survey), no
    `RUN_ALLOWLIST`, and `sd-dashboard` ships two of its five
    verbs — `install`, the one that performs the swap, is among the three that
    do not exist.
  - So **6b is not a port swap gated by a checklist**: it is thirteen tabs, a
    plugin contract, an allow-list and three verbs, and the swap is its last
    step. The plan's one-line row understates it, which is the finding.
  - One thing the checklist raises and does not settle:
    `~/repos/system/local-project-dashboard/dashboard.py` is one 1,728-line
    file serving all fifteen tabs, so it cannot be deleted per-tab — the two
    dashboards coexist for the whole of 6b rather than for a short window. The
    risk register names that window; this makes its length concrete.
  - **The Ports and rtk question turned out to be a Now question, and it is
    now R11-D12.** Chasing where those two land found that `attentionItems()`
    draws Needs-you from six sources — `toolbox`, `repos`, `queues`, `prs`,
    `ports`, `areas` — and **three of the six are plugin-bound**, owning nine
    of the thirteen rows the view can emit. Worse than the count: the view
    sorts by rank, and **every rank-0 and rank-1 row comes from a plugin-bound
    source** — cron exited non-zero, vault collector errored, cron silent, cron
    failure logged, task overdue. The specified `dashboard.tile` contract
    renders into its own tab and cannot put a row in somebody else's view, so
    the swap as designed would have left Now with no rank-0 or rank-1 row at
    all while Now still rendered — a silent regression. R11-D12
    adds one optional key: a plugin tab may return rows shaped like the ones
    `add()` already takes. It also flips 6b's order — the plugin loader comes
    before the tabs, because Now depends on it.
  - The same look settled the two smaller ones without a decision: **rtk** is a
    card inside `renderToolbox()`, so it rides Toolbox and never needed a
    destination — this checklist's first draft mis-filed it by reading
    "collector with no tab" as "fact with no home". **Ports** gets its own
    plugin tab rather than folding into Toolbox: same owner, but its own tab
    and its own alert identity today.
  - **A second ordering problem, found before building anything, and it
    crosses steps rather than sitting inside 6b.** The loader cannot scan for
    plugins — design.md says registration is `sd plugin add` only — so it needs
    a registry, and `bin/` has no `sd` at all: no verb groups, no manifest
    parser, no registry format. All of it is scheduled at step 8, *after* 6b.
    **R11-D13** pulls the smallest unblocking slice forward — `sd plugin
    add|list` plus the manifest read, and nothing else from step 8 — as 6b's
    first PR. The rejected alternative was a private registry file for the
    loader, folded into `sd plugin` later: it defines the same disk format
    twice, and it makes the first consumer an exception to "no disk scanning",
    which is how that rule would stop being one.
  - **The manifest parser reads everything and validates what it uses**
    (user, 2026-08-31): `prefix` and `dashboard.tile` are checked; `kinds.*`,
    `issues.repo` and `vendor.*` are read and carried. Step 8 adds enforcement
    to an existing reader instead of writing a second one. It is also the only
    honest option today — enforcing `kinds.*` means checking the closed 8-key
    vocabulary, and **that vocabulary was not written down anywhere in this
    repository**: standing rule 2 fixes it at eight and makes changes decision
    records, while the enumeration survived only in the r5 round artifact,
    under `/private/tmp`, backed up by nothing. **R11-D14** transcribes it into
    design.md — `fields`, `initial-status`, `protected-fields`, `transitions`,
    `human-only`, `unique-fields`, `floor`, `sections` — keeping the kebab-case
    spellings exactly as ruled, since renaming them while transcribing would be
    a vocabulary change wearing a format change's clothes.
  - **The dashboard LOC cap is measured, not raised.** Splitting both system
    files by where the code lands after the swap: 301 py + 317 js leave the cap
    for `~/repos/system`; 124 py is already built here; the backbone-side lift
    is 79 py + (829 − 145) js = **763**, against the cap's stated justification
    of "457 lifted". With `dashboard/` at 1,499 tracked and the cap at 2,500,
    that leaves ~240 lines for the loader and `RUN_ALLOWLIST`. The three
    missing `sd-dashboard` verbs are not in that number: the test charges
    `bin/sd-dashboard` to `bin/` deliberately so the caps do not overlap
    (`tests/test_loc_caps.py`'s `test_the_dashboard_stays_under_its_ceiling`).
  - **`bin/` is the tighter cap, and the rollout hits it first.** Counted:
    `bin/` core is **7,492 of 8,000 — 508 lines left** (`migrate-*` is excluded
    under its own 1,500 ceiling, which is why a raw 8,742 total still passes).
    design.md's itemisation predicts ~7,170 for the **finished** pack: the
    built-so-far total already exceeds that by 322 lines, with seven commands
    still to write. Into the 508 go **seven unbuilt commands** — `sd-plan`, `sd-ship`,
    `sd-spec`, `sd-deps`, `sd-help`, `sd-suggest`, `sd-map` — plus the whole
    `sd` CLI whose first slice R11-D13 just scheduled, plus the three
    `sd-dashboard` verbs. It does not fit. That changes no decision here, but
    it names which ceiling breaks first and when: inside 6b, not at step 8.
    Neither cap is raised on an estimate; both get re-derived from an itemised
    count at the landing that measures the overrun, never in the PR that trips
    `tests/test_loc_caps.py`.
  - **6b-1 landed, and its measurement answers the cap question: `bin/`
    busts.** `bin/sd` with `plugin add|list` and the whole-manifest reader is
    **264 lines**, taking `bin/` core from 7,492 to 7,756 and the headroom from
    508 to **244**. Still to fit in those 244: **seven commands** — `sd-plan`,
    `sd-ship`, `sd-spec`, `sd-deps`, `sd-help`, `sd-suggest`, `sd-map` — plus
    `sd store|issue|config` and the three `sd-dashboard` verbs. The five
    commands already built run 279 to 1,368 lines, median 631; at the size of
    the *smallest* one the remaining headroom holds **none of the seven**. This
    is no longer a projection, and R11-D13's stated trigger has fired: the
    `bin/` cap is re-derived from an itemised list in its own decision record,
    **before the dashboard tabs start**, not in the PR that trips
    `tests/test_loc_caps.py`.
  - **The cap is re-derived: `bin/` is 14,000 (R11-D15).** 6b-1 was the
    landing R11-D13 said would decide it, and it decided against the estimate.
    Derived from code that exists rather than scope that does not: shared
    support 3,720 + five built commands 3,772 + `bin/sd` 264 = **7,756 today**;
    six remaining commands at the built mean of 754 = 4,524; `sd store|issue|
    config` at the design's own 1,400 sub-cap; three `sd-dashboard` verbs ~300.
    **13,980, so 14,000.** Bounded rather than pinned, because a mean over five
    samples spanning 279 to 1,368 is a weak instrument: at the smallest built
    command (`sd-check`, 279) the total lands at 11,130, at the largest
    (`sd-review`, 1,368) at 17,664. Every version clears 8,000 by thousands, which is
    the part that does not depend on the estimator. `tests/test_loc_caps.py`
    updated; it may only be re-derived **downward** when the last command
    lands.
  - **`sd-help` was already a skill; only design.md hadn't caught up.** Asking
    whether all seven remaining commands earn their lines found six that pass
    the taxonomy test outright (including `sd-deps`, thin on spec but squarely
    a pre-authorised side effect) and one that fails — and step 5b had already
    settled it. `skills/sd-help/SKILL.md` exists, `test_skill_frontmatter.py`
    pins eleven commands, `sd-skill-adopt`'s collision check was corrected to
    eleven when it landed. design.md's command table still said twelve, four
    sections above its own taxonomy paragraph calling `sd-help` a skill, plus
    three other recitations. Fixed. It moves no budget — the derivation counts
    six remaining commands, never seven.
  - **6b-2 landed: the plugin loader, and the dashboard cap now shows the
    same shape `bin/` did (R11-D16).** `dashboard/plugins.py` reads the
    registry by shelling out to `sd plugin list --json` rather than parsing a
    manifest of its own -- no second reader, and the no-disk-scanning rule
    comes free because the loader never looks at a directory. The tile
    protocol is specified for the first time, and it is **per tab**: the
    manifest declares `dashboard.tabs: ["toolbox", "ports", ...]`, the loader
    runs `<tile> <name>` once per declared name, and each call answers
    `{title?, html?, rows?}` for that one tab -- `html` is markup rendered into
    it, `rows` are R11-D12's typed alert rows with `href` confined to an
    in-page anchor. *(Removed by R11-D19 while scoping 6b-5: the anchor had no
    reachable target and nothing read it.)*
    **Two drafts were wrong before this one, and each was corrected by
    building against it rather than by reading it.** The first fixed a plugin
    at one tab; starting 6b-3 found that one repository has one manifest while
    `~/repos/system` owns five of the views, so the payload became a list of
    tabs. That was still wrong, and timing the real collectors is what showed
    why: `collect_toolbox` 3.78s, `collect_ports` 2.84s, `collect_areas` 0.03s,
    `collect_briefs` 0.01s, `collect_jira` 0.00s -- **6.66s in sum against a 5s
    per-tile budget**, so the single command would have been killed on every
    load, permanently, while each individual collector fits the budget four
    times over. Per tab, 5s keeps meaning one thing no matter how many tabs a
    plugin serves, a slow tab can no longer starve its siblings, and the tabs
    run concurrently behind a four-worker ceiling so a plugin does not get to
    choose how many processes the dashboard starts. Tab names are validated at
    registration (`^[a-z][a-z0-9-]{0,31}$`, no duplicates) because a name
    reaches the tile as a command-line argument; `title` became optional, since
    the declared name is the identity and the fallback.
    The addition to R11-D12: **a tab that goes dark becomes a rank-0 row.**
    Non-zero, timed out, oversized, unparseable, or emitting a refused row --
    each produces a row naming the tab and the reason, because a failed tile
    treated as "no rows" is indistinguishable from a quiet machine, which is
    R11-D12's own complaint one layer down. 43 tests, all against a real
    subprocess: neither the 5s deadline (which kills the process group, so a
    backgrounded child cannot outlive it) nor the 64KB ceiling (enforced while
    reading, not after) survives being mocked.
    **The measurement:** `dashboard/` is **2,067 of 2,500, 433 left**. The
    loader cost 568 against the ~240 R11-D13 left for the loader *and*
    `RUN_ALLOWLIST` together. R11-D13's backbone-side lift is 763; 763 into 433
    does not fit, so `dashboard/` projects to ~2,830 with `RUN_ALLOWLIST` still
    uncounted. Not raised here -- the test passes at 2,067, and the cap gets
    re-derived from counts at the landing that carries the backbone renders.
    The loader also refuses a tile that prints good JSON and then exits
    non-zero: closing stdout is not exiting, and the status is inside the
    budget (found in review -- the first version killed the process on the
    success path too, recording -SIGKILL and reading its own kill as clean).
  - **6b-3 landed: the backbone renders plugin tabs, and the two questions
    R11-D16 could not answer are answered by R11-D17.** The loader had nobody
    to render it: `dashboard/app.js` drew a repo table and an issue table and
    nothing else, so a plugin tab loaded, validated and budgeted was reaching
    no screen at all. It now builds a nav button and a panel per tab from
    `/api/plugins`, rebuilding only when the payload changes -- the poll is
    every ten seconds and a rebuild destroys the panel, which is where a typed
    filter and a chosen sort order live.
    **Interaction is declared, not shipped.** The tabs being folded in are
    searchable and sortable today, so a port without that is a regression the
    parity checklist would catch. The user chose the third of three options
    over letting a plugin ship script: a table carries `data-sd-search` and
    `data-sd-sort`, a `<th data-sort="num">` says how a column compares, and
    the backbone provides the behaviour for every plugin at once.
    **The boundary needed a filter, not a reassurance.** `innerHTML` does not
    run `<script>`, which is the fact that makes people stop looking; `onclick`
    runs as written and `<img src=x onerror=…>` needs no click. So
    `dashboard/markup.py` filters the markup on the way out of the loader --
    server-side, because `/api/plugins` is a surface of this server and a
    sanitiser in `app.js` would leave the endpoint serving whatever a tile
    printed. Allow-list, three outcomes: kept, unwrapped (box lost, text kept),
    or erased with its subtree. Every drop is a rank-0 row, because markup
    rewritten in silence looks to its author exactly like markup that rendered.
    **Verified in a browser engine, not only by `node --check`:** headless
    Chrome against a two-tab plugin renders both buttons and both panels, two
    filter inputs, four sortable headers, an alert strip carrying all four
    rows, and `<div onclick="steal()">` arriving as `<div>`. The comparator's
    NaN handling was checked separately, since a cell holding no number must
    sink rather than sort as zero. What is **not** verified: a real click on a
    header. There is no JS test harness in this repository and adding one was
    out of scope for this change.
    **The measurement, and the cap:** `dashboard/` is **2,488** with 6b-3 in
    it, which fits the 2,500 cap with twelve lines to spare -- so R11-D16's
    trigger fires exactly as written, and **R11-D17 re-derives the ceiling at
    4,000** in its own record rather than in a change that busted the old one:
    2,488 measured, plus R11-D13's 763-line backbone lift, plus estimates of
    ~120 for Now and ~200 for the write path, is ~3,571; 4,000 is that plus
    room for this repository's comment convention. Downward only, like
    `bin/`'s 14,000. *(Both estimates were later overrun and both overruns are
    recorded where R11-D17 says they belong: Now cost 212 at 6b-5b, the write
    path 330 at 6b-7. The derivation stands as written; the cap is not
    re-derived twice.)*
  - **6b-3b: the loader keeps the tile's last words (R11-D18).** Writing the
    first real tile refused five tabs with `exited 2` and no reason --
    `bounded_run` opened the process with `stderr=subprocess.DEVNULL`, so the
    loader that exists to stop a plugin going quiet was throwing away the
    plugin's account of why it had. Stderr is now read in the same `select`
    loop as stdout and its last 512 bytes ride back in the refusal.
    Read rather than merely piped, and that distinction is measured: a child
    writing 400KB into an unread pipe on this machine is still blocked after
    three seconds, so the end-of-run fix would have turned every long traceback
    into a timeout. Three tests: the reason carries what the tile said, a 20KB
    stderr yields a bounded row that keeps the end rather than the start, and a
    tile that floods stderr and then prints good JSON is served rather than
    killed.
  - **6b-4 landed, in `~/repos/system` rather than here: the five system views
    are a plugin now (platypeeps/system#186, +652/-7 across 4 files).** The
    repository grew an `sd-plugin.json` declaring prefix `sys` and five tabs,
    and an `sd_tile.py` that answers `dashboard.sh tile <name>` once per
    declared name. Nothing crossed the boundary that was not supposed to: the
    tile returns `{title?, html?, rows?}` and the styling stayed system-side,
    so the numbers cross and the boxes do not.
    **The budget is not theoretical, and the first tile broke it.** A cold
    load through the pack's loader timed out on `sys/toolbox`, which is how
    R11-D19 found its rank-0 case -- a row sourced to a tab that was never
    served. Profiled rather than guessed: `machine-setup.sh status` cost
    **3.57s** of the 5s per-tab budget -- 90-95% of the tile's whole runtime
    (re-timed at 3.50s while writing this entry, which is the same finding and
    not a competing figure: the cost belongs to the command, not to that
    afternoon),
    and the nightly `machine-setup-drift` job already runs that exact command
    at 03:30 and writes its output verbatim to a log. Reading the log instead
    costs **1.8ms** on today's 89KB, and stays in milliseconds as it grows: the
    read walks backwards in doubling windows, and a 2.16MB synthetic log with
    a 100KB final block resolves in 3.8ms (platypeeps/system#188).
    **Freshness became the thing to report rather than the thing to lose.**
    A nightly number shown as a live one is worse than a slow tile, so the
    tab carries a `drift checked` figure, and where the figure cannot be
    trusted -- no log, a run still going, a run that died before reporting, a
    stamp that will not parse, or a measurement past 48h -- it raises a rank-1
    row saying which. Seven review rounds, one of them rebutted with a
    constructed case rather than complied with: dropping the first line of
    each backward-read window cannot return a stale run, because a window that
    opens on the newest `starting` stamp contains nothing older by
    construction.
    **After:** the five tabs cost 0.12s, 0.06s, 0.08s, 0.39s and 2.16s timed
    one at a time, and the loader returns all five with nine alert rows in
    **2.33s** -- not their sum, because `dashboard/plugins.py` runs the tabs
    concurrently, so the wall clock is the slowest of them plus overhead and
    `sys/ports` is now what the budget is spent on. Every row is sourced to a
    tab that was actually served.
  - **6b-5a landed: the Work tab, and it was never a port (#657, +483/-1
    across 4 files).** The parity table above called it backbone and implied a
    lift from the system dashboard. That tab reads
    `.trellis/workspace/journal-*.md`; step 2 replaced that layout with
    `docs/work/`, and exactly one checkout fleet-wide still has a
    `.trellis/workspace`. The row is corrected above rather than left to be
    re-derived.
    **What `docs/work/` actually holds was bigger than the scoping note, and
    the note was measured on one repository.** Enumerated from the filesystem
    across the fleet: **twelve repos, 310 active items, 1,226 archived**, and
    `300 planning · 6 in_progress · 1 done · 3 with no status`. So the full
    inventory is one value repeated three hundred times across twelve
    repositories, and the tab does not render it -- it renders the six that
    are moving and carries every status as counts in the summary, because six
    rows without "300 planning" beside them would read as the whole set.
    **Moving is defined by exclusion, and that is the design decision.** Not
    an allow-list of interesting statuses: an allow-list needs editing every
    time the templates grow a word, and until someone noticed, the item would
    be missing from the only view that would have shown it. A status this
    module has never seen surfaces itself instead.
    Three shapes the fleet contains that the obvious implementation gets
    wrong, each now carrying a test: `archive/` matches the same glob as an
    item and holds no `prd.md`, so it reported once per repository as an item
    whose state could not be read -- which is the row that is supposed to mean
    something; `status: blocked | phase: check | diagnostic: ...` is a real
    line, and the reason is the most useful thing on the row; and three items
    have no `prd.md` at all, which earns them their own table rather than a
    blank status cell, because a blank cell is how they stay unnoticed.
    **Two of the tests proved nothing, and a mutation found the second one.**
    The frontmatter cap test first repeated a single key, so the dict stayed
    small whether the cap held or not; the repair sized its fixture as
    `FRONTMATTER_LINES + 5`, which scales with the constant under test, so
    raising the cap raised the fixture and moved the assertion out of the way.
    Both survived removing the cap entirely. The fixture is a literal now, and
    mutating the constant does fail it. Worth recording because the second
    version looked correct and was reached by fixing the first.
    **The measurement, and the cap:** `dashboard/` is **2,930 of 4,000, 1,070
    left**. Setting that against R11-D17's ~1,083 of remaining estimate says
    the two just crossed over by thirteen lines -- and that subtraction is
    wrong, which is worth recording because it is the one a later reader will
    redo. The estimate was drawn at 2,488; part of it has since landed *inside*
    the 2,930, and part left the cap altogether. R11-D13 splits its 763 into 79
    collector lines (queues, research, work) and 684 of JS: `research` shipped
    as a plugin tab in 6b-4 and R11-D21 moved `queues` to one, so both leave
    `dashboard/` entirely, and `work` is built and already counted in the
    2,930. Of the 684, the system dashboard's Work render is 128 lines
    (`assets/dashboard.js:673-800`), rewritten here in about 60. So what is
    still to fit is ~556 of backbone JS plus R11-D17's ~120 for Now and ~200
    for the write path -- **~876 against 1,070 left**, under rather than over.
    No re-derivation either way: R11-D17 rules one out and asks instead that
    Now and the write path be measured against their own estimates, so 6b-5b
    reports its LOC the way 6b-2 did.
  - **6b-5b landed: Now, and it is the tab that opens.** The alert strip that
    said *"shown here on every tab until Now lands"* is deleted; there is a
    view now. Fourteen rows on this machine, reconciled against both halves
    rather than eyeballed: nine from the loader, five from the fleet, and the
    two sources agree with `/api/plugins` and `/api/state` exactly.
    **The merge is server-side, and that was a testability decision before it
    was an architectural one.** The rows arrive on two clocks from two routes
    and the page could have joined them, but then the ranking, the ids and the
    row text would exist only once a browser was running -- which is how 6b-5a
    shipped its render untested. `/api/now` merges instead, `dashboard/now.py`
    is ten unit tests, and what stays in the page is what cannot leave it: the
    severity band, and the panel id a row links to.
    **Severity comes from `rank` and nothing else** (R11-D20). The bands are
    chosen here because choosing them is a rendering decision: 0-1 broken,
    2-3 look, 4+ queued, and the nav badge counts everything not queued. Nine
    of the fourteen, which is the number the operator is being asked to care
    about.
    **A row's destination is looked up and never recomputed.** The renderer
    records the panel id it assigned, keyed on the `source` the loader
    stamped; `panelId` normalises many-to-one, so re-deriving it would send a
    row to a sibling tab's panel, which is worse than not linking. All
    fourteen resolved here. The three sources that name no served panel are
    exactly the failures, and those render unlinked by design.
    **Two rules found by writing tests that could fail.** Ahead and dirty are
    one row, not two -- the same repository at two ranks reads as two problems
    -- and the sort key is `(rank, id)`, not `rank`: rank ties are the common
    case, the git fan-out is a thread pool, and a rank-only sort reshuffles
    the list under the operator every ten seconds. Both mutations were run and
    both fail their test.
    **And one bug the browser would have shown and no unit test could.** With
    no Chrome available the client was run under a stub DOM against the live
    server, which caught the plugin poll winning the load race and repainting
    Now from an empty list -- flashing *"nothing is asking for anything"*
    across the one view whose job is never to say that when it does not know.
    `nowRowsSeen` is `null` until the first fetch answers.
    **The measurement, and the finding R11-D17 asked for:** `dashboard/` is
    **3,142 of 4,000, 858 left**, and Now cost **212** against R11-D17's
    estimate of ~120. That is materially over, which that record names as a
    finding for this one rather than grounds for a second re-derivation, so
    here it is. What is left to fit is ~556 of backbone JS plus ~200 for the
    write path -- **~756 against 858**, still under, by about a hundred lines.
    The estimate that is now worth doubting is the ~556: it covers the PRs tab
    and three surfaces with no system counterpart, and one tab just cost 212.
  - **6b-5c landed: PRs, and the collector it was supposed to need already
    existed.** The parity row implied porting `collect_prs` -- a `gh search
    prs --author @me` shell-out on a timer. It is not needed: GitHub's search
    does not separate issues from pull requests, `type: ISSUE` returns both,
    and the pack's index has been storing them side by side under `kind` since
    step 4. There were **17 open pull requests already indexed** and the
    Issues tab was rendering them as issues. So this is one `kind` filter in
    `store.issues`, one generalised payload serving two routes, and one
    renderer serving two tabs -- 117 lines, against a row that read like a
    network collector.
    **The bug it fixes is the one it was not looking for.** Issues showed 18
    rows, of which 17 were pull requests. It shows one now, and the test that
    pins the split says why the filter is the only thing keeping them apart.
    **Staleness replaced age, and the index forced the question.** The system
    view ranked a PR by how long ago it was opened; there is no `created_at`
    column and adding one means migrating a cache that has no migration
    machinery. Rather than build that for the worse question, the question
    changed: a three-week PR still being pushed to is working as intended, and
    a fortnight of silence is the thing worth a row. Ranked from `updated_at`,
    which the index has had all along.
    **Two mutation-checked rules.** The staleness threshold is real (`days >=
    0` fails the fresh-PR test), and the row id does not carry the day count
    (adding it fails the ack test) -- keyed with the age, a dismissed PR would
    un-dismiss itself every morning, which is the one row guaranteed to come
    back forever.
    **After:** Now carries **31 rows** -- 9 plugin, 5 fleet, 17 pull requests
    -- and all 31 resolve to a panel. `dashboard/` is **3,259 of 4,000, 741
    left**.
  - **6b-5d landed: Skills and Sessions. Suggestions did not, and R11-D22
    says why.** The three were one parity row -- new surfaces with no system
    counterpart -- and two of them had data waiting the moment they were
    asked. The third has no producer: `sd-suggest` is one of the six `bin/`
    commands that do not exist, there is no draft directory and no schema for
    one, and a tab whose only content is *"the command that fills this has not
    been written"* is worse than no tab. The parity row splits rather than the
    gate being weakened.
    **Sessions replaces a ledger with no ledger.** Trellis wrote
    `.runtime/sessions`; no hook carries over, and nothing replaces it -- a
    worktree is registered in git's own `.git/worktrees/` and a running
    command is in the process table, both already true without anything having
    recorded them. Read from files rather than through `git worktree list`:
    the fleet is 79 checkouts and the repo table already fans `git` across all
    of them, so a second fan-out to answer a question three `open()` calls
    settle would double a page load for nothing. **0.030s** for the fleet.
    **And it found something on the first run.** Eight worktrees registered
    across eight repositories, **all eight abandoned** -- every one pointing at
    a scratchpad path from an earlier parallel run that no longer exists, each
    still holding a branch reference. Invisible from every other tab, nothing
    fails because of it, and it accumulates. Now carries it as one rank-3 row
    rather than eight: eight of them is one piece of housekeeping, and eight
    rows would push the fleet's real problems off the top of the view to say
    so eight times.
    **And that row put a `ps` on the ten-second poll, which review caught.**
    Now took the whole Sessions payload for one number, so `/api/now` forked a
    process every ten seconds for a count that came from file reads -- whether
    or not the tab was open. Split: `fleet_worktrees` is **2.4ms**,
    `collect_sessions` is **30.2ms**, so the subprocess was 27.8ms of it and
    the poll was spending ten seconds an hour on it.
    **Skills is the gap between two directories, and the gap runs both ways.**
    76 ship here, 138 are installed, **0 unadopted and 62 from somewhere
    else**. Counted as two numbers rather than one because they are different
    facts: shipped-and-not-installed is a skill the agent cannot reach, while
    installed-and-not-shipped is not this repository's business. The 138
    corroborates the `--lint-only ~/.claude/skills` run recorded at step 5.
    **The measurement, and it is the tight one:** `dashboard/` is **3,640 of
    4,000 -- 360 left**, and 6b-5d cost **381**. Two tabs at roughly the price
    R11-D17 estimated for the whole of Now. What still has to fit is the
    write path (~200) and 6b-6's pack-side half, against 360. The cap may only
    move downward (R11-D17), so this does not get raised; what it means is
    that `sd-dashboard install` must land in `bin/sd-dashboard`, which
    `tests/test_loc_caps.py` charges to the `bin/` ceiling on purpose and
    where there are 6,211 lines of headroom. If the write path lands over
    ~200, the honest move is to say so and re-scope, not to re-derive a cap
    twice in one step.
  - **6b-7 landed: the write path, and the promise it replaced.** The
    dashboard had one guarantee that was easy to state -- *GET is the only
    verb* -- and R11-D21 made it untenable: the five queue tabs exist to be
    decided in, and ported read-only they become a list of questions nobody
    can answer while Now still emits rows pointing at them. So the guarantee
    moved rather than went. **No GET has a side effect.** Writing is POST,
    POST is Host-allowlisted and token-gated, and every mutation resolves to
    an id in `RUN_ALLOWLIST` -- the server never builds a command from
    anything a caller sent, and `bounded_run` takes a list and never a string.
    **The shape being refused is a real one, in the code being replaced.**
    `~/repos/system/local-project-dashboard/dashboard.py:1714` answers
    `GET /api/state?refresh=1` by starting a rebuild behind the Host check
    alone, while its POST twin at `:1788` demands the token -- so a link, a
    prefetch or an `<img src>` on any page the operator has open can start it.
    That is pinned two ways rather than asserted: `do_GET` is read out of the
    syntax tree and must call neither `actions.run` nor anything in
    `subprocess`, and every route the handler serves is walked live, with and
    without `?refresh=1`, against a recorder that stays empty. Both halves
    fail if the hole is reintroduced, which is how they were checked.
    **A plugin may declare actions, and the id is the trust boundary.** A
    manifest names actions beside its tile, `bin/sd` validates the block at
    registration and reports it in `plugin list`, and the id is namespaced
    with the plugin's prefix exactly as its rows and tabs are. A plugin
    declaring `index` gets `sys/index`; the backbone's `index` is untouched.
    Tested by trying it, and by two plugins declaring the same name.
    **Four mutations, four failures.** Remove the namespacing, remove the Host
    check from `do_GET`, make the token comparison unconditional, or add a
    `?refresh=1` rebuild -- each one turns a passing suite red, and the last
    one reds both halves of the no-GET pin.
    **Two bugs came from pressing the button rather than from reading it.**
    `RUN_ALLOWLIST` first named `sd-dashboard` and got a 502: the pack's
    `bin/` is not on this machine's `PATH`, and under launchd it would be on
    launchd's. It resolves from `__file__` now, the way `plugins.SD` already
    did. Second, the handler defaulted a missing `Content-Length` to zero, so
    a chunked POST -- which is what a client that does not set the header
    sends -- was read as an empty body and answered *"no action named"*: a
    request that was fine, refused with an error pointing at the allow-list.
    It is a 411 now. Neither was reachable from a unit test of either half.
    **Five review rounds, and the last three findings were the interesting
    ones.** `catalog()` sorted by id -- contradicting R11-D23, written in the
    same change, which chose a list over an object keyed by id *to keep
    declaration order*. `allowed_hosts()` forked `tailscale status` lazily
    inside `host_ok`, which `do_GET` calls first, so the first page load after
    a restart wore a ten-second timeout; it is resolved before the socket
    opens now, pinned by position. And the page was served with no cache
    headers while carrying a per-process token -- a cached copy persists a
    secret to disk, which is the opposite of what minting it in memory was
    for, and POSTs a dead token after a restart. `no-store` on everything:
    every route here serves live fleet state.
    **Review found two more of the same kind, both about a wrong error rather
    than a missing guard.** A `Content-Length: -1` parses, so the negative case
    fell through the size cap into `read(0)` and answered *"no action named"*
    -- the identical misdirection the missing header had just been fixed for,
    one branch over. And `/api/actions` dropped the failure string
    `plugins.catalog` returns, so a registry that will not parse rendered as
    *"no actions declared"*: a broken loader reported as a machine with no
    plugins, which is the exact quiet that module refuses everywhere else.
    **`sd-dashboard install` is the third verb, and it is in `bin/`.** The
    plist is rendered from the command every time rather than edited in place,
    and `bootout` precedes `bootstrap` because `bootstrap` over a loaded label
    fails and a reinstall that quietly kept the old arguments is the failure
    the verb exists to prevent. launchd refusing is printed, not an exit code:
    the plist is written and correct, and saying otherwise would suggest the
    install did not happen. It does not yet *replace* the system LaunchAgent
    -- that is 6b-8's swap, and until then they are two services under two
    labels on two ports, deliberately.
    **Three things R11-D10 named that 6b-7 did not build, said here rather
    than left to be noticed at the swap.** It names three endpoints carried
    from the system dashboard -- `POST /api/update`, `/api/ack`,
    `/api/refresh`. One route exists, `/api/run`, and that is a deliberate
    replacement rather than a shortfall for two of the three: R11-D21 turned
    `/api/update`'s `{key, stem, field, value}` into a named action, and
    `/api/refresh` is the `index` action. **`/api/ack` has no counterpart and
    no producer.** R11-D20 says an alert id *is* an ack key, and nothing in
    `dashboard/` stores an ack -- so the parity gate's "Now emits every rank-0
    and rank-1 row it emits today" is satisfiable while the row the operator
    already dismissed comes back every ten seconds. That is a tab-scoped
    version of the dead-destination failure R11-D19 was written about, and it
    belongs to whichever step builds the ack store, not to this one.
    **And R11-D10's own deletion criterion is not measurable as built.** It
    says the write path is deleted if, sixty days after the swap, the index
    shows fewer than ten mutating requests from a tailnet Host. Nothing counts
    them: `/api/run` writes no record of having run, the index has no table
    for it, and the criterion therefore evaluates to "no evidence" rather than
    to a number. Either the count lands with the swap or the criterion is
    re-stated against something that does exist -- recorded now because a
    deletion criterion nobody can evaluate is the failure mode standing rule 1
    exists to prevent, and it would otherwise be discovered on day sixty.
    **The manifest key R11-D21 left open is now decided: R11-D23.** It had to
    be, to have a write path at all -- `{"id", "label", "run"}` under
    `dashboard.actions`, id shaped like a tab name and namespaced by prefix,
    validated at registration in `bin/sd`. The record carries the edge that
    matters for 6b-6: an action is a command and not a form, so it takes no
    arguments from the page, and Queues either declares one action per outcome
    or R11-D21's mechanism needs a second record for parameters.
    **The measurement, and it is the one this record was told to make.**
    `dashboard/` is **4,000 of 4,000 -- nothing left**, and 6b-7 cost **343**
    against the ~200 the 6b-5d entry estimated. Over by 72%, said here rather
    than absorbed. `install` went to `bin/` as that entry required, where the
    total is now 7,925 of 14,000. Two reductions were taken inside this change
    rather than after it -- `send_body` grew a status parameter so the POST
    stopped hand-rolling a response, and `resolve()` replaced three copies of
    the same merge -- and the prose written this step was tightened. What is
    left is nothing at all, and **6b-8 needs more than that**: R11-D10's correction
    of 2026-08-31 says the reach is two paths, a direct tailnet bind *and* a
    `tailscale serve` proxy, and binding a second address is ~20 lines in
    `serve()`. The cap may only move downward (R11-D17), so the choice at 6b-8
    is a deliberate reduction change before it, or knowingly dropping the
    IP-URL path that exists for a phone whose resolver ignores MagicDNS.
    R11-D10 already framed that as "carry both or knowingly drop one"; this is
    the point at which it stops being hypothetical.
  - **The cap is re-derived and split: R11-D24.** 6b-7 finished at **4,000 of
    4,000**, and the honest account of its last hour is that it was spent
    deleting rationale to fit a branch -- a docstring, a comment, three
    separate passes, each trimming an explanation somebody had written because
    they needed it. The change was not oversized and `install` had already
    gone to `bin/` as required. What ran out was the allowance R11-D17 made
    *for prose*, in its own words: "4,000 is that plus room for this
    repository's comment convention."
    **Measured rather than argued:** 4,000 lines, **2,141 carrying code and
    1,859 comments, docstrings and blanks -- 46%**. R11-D17's "roughly half"
    was right and its allowance for that half was not. One ceiling over both
    halves puts a branch and a paragraph in a bid for the same line, and the
    paragraph loses every time, because the branch is what the change is for.
    **So the ceiling is two numbers: 4,300 total, 2,300 carrying code.** The
    total is 4,000 measured plus an itemised ~175 for what is left (6b-8's
    second address bind ~25, the ack store and its control ~100, swap-time
    carry ~50) times the overrun this project has now measured twice -- Now at
    +77%, the write path at +69%. The code half is 2,141 plus the ~54% of that
    remainder which is code rather than prose. They bind at nearly the same
    point on purpose: work in house style exhausts both together, and work
    that is only code hits the code cap first.
    **What the split is worth, checked by breaking it.** 200 lines of pure
    code reds the code cap while the total still passes; 200 lines of pure
    comment passes both; 400 lines of pure comment reds the total. Prose can
    grow into the room the raise bought and code cannot, which is the entire
    point and would be a claim rather than a fact without those three runs.
    **And the downward-only clause moved rather than went.** R11-D17 said
    4,000 could only fall. This raises it, once, in its own record, by a
    change that fits under the old ceiling -- and hands the clause to the code
    cap, which may only fall. `bin/`'s 14,000 keeps the original rule
    untouched and is not close to binding at 7,925. Today: **4,000 of 4,300,
    300 left; 2,141 of 2,300, 159 left.**
    **The adversarial pass found one overlap and rebutted one figure.** The
    layout table listed `sd-dashboard` inside the `dashboard/` bucket and hung
    the new ceiling on that bucket, while `tests/test_loc_caps.py`'s `test_the_dashboard_stays_under_its_ceiling` charges
    the CLI to `bin/` on purpose -- so the written cap covered a file the
    enforced cap did not, and the two would have overlapped the moment anyone
    reconciled them. The layout line now says where the CLI charges. The
    figure challenged and kept: `bin/` at **7,925**, which is a raw count of
    9,175 minus the `migrate-*` tools that hold their own 1,500 ceiling --
    correct as written, and only correct because the cap test enumerates the
    same way.
    **Review found two ways the measure could fail for the wrong reason.**
    The counter routed every non-Python file through the JavaScript rule, so a
    `README.md` dropped into `dashboard/` would have had every line of prose
    counted as code -- the cap failing on exactly the thing it exists to make
    free. It now dispatches by extension: Python tokenised, `.js` by the crude
    rule, everything else zero and still charged to the total, which is where
    a large prose file belongs. And the block-comment guard rejected the
    substring `/*` anywhere in the file, so `const glob = "src/*.js"` would
    have failed a check about comment style; it now looks only at what a line
    opens with. Both mutation-checked: reverting the first reds the prose
    fixture, adding a real block comment reds the second, and the string
    literal that used to fail it now passes.
    **The parity table's live column was wrong while all this was being
    measured.** `Now · PRs` still read *no* after 6b-5b and 6b-5c built both,
    and the verdict paragraph said eight tabs exist when twelve serve. Fixed
    by enumerating from `app.js`'s tab list and the loader's own reply, not by
    editing the number -- an updated count goes stale on the next landing and
    an enumerated one does not.
- [x] **6b-6 — Queues as a sixth plugin tab, read-only (R11-D25).** The last
  unported tab, and the one R11-D21 moved out of the backbone. Zero lines of
  pack code: the tab, its collectors and its actions are all in
  `~/repos/system`, which is what "plugin tab" was supposed to mean and the
  first time it has been proved by a tab that did not exist when the loader
  shipped.
  - **The edge R11-D23 recorded came due, and the answer was neither option.**
    An action is a command, not a form. Setting a note's status needs
    `{key, stem, field, value}`; one action per outcome cannot name the note,
    and parameters would put caller text into an argv — the one property 6b-7
    was built not to have — for ~100 lines against the 159 R11-D24 left. So
    the tab reads and Obsidian keeps the writing, which is where it already
    happened and where `update_note`'s guard against becoming the second
    writer of a machine-owned field lives. **A carry-down, not a carry**, and
    the swap gate should read it as one.
  - **Each queue declares one action instead**, which is a fixed command with
    the queue named in the manifest rather than by a caller. `sys/queue-blog`
    and four siblings are the first plugin-declared actions to exist, so
    R11-D21's mechanism and R11-D23's namespacing were exercised by something
    other than the backbone's own `index` for the first time. *Pinned* in the
    gate's sense means fixed in the manifest and never sent by the page:
    `sd-plugin.lock` is in the layout and does not exist yet, so nothing here
    is pinned by a hash, and the tick above should be read as claiming the
    first and not the second.
  - **Measured, not assumed:** the tile answers in **0.076s and 5.7KB** against
    a 5s / 64KB budget, and the sanitiser drops nothing — `data-sd-sort` and
    `data-sd-search` both survive, which matters because the table is only
    sortable if they do. 80 notes wait across three queues today, the oldest
    24 days.
  - **End-to-end against a live server:** six plugin tabs load, `/api/now`
    carries three rank-3 queue rows, an unknown id is 404, a missing token is
    403, and pressing `sys/queue-blog` returns `opened blog in Obsidian`. One
    row per queue in Now rather than one per note: 80 waiting notes is one decision
    session, not 80 things asking for attention.
  - **A search URL, not `obsidian://open`**, which wants a file — the thing to
    open is a folder's worth of undecided notes, and `path:` plus the decide
    status is exactly the set the table counted. Built in `~/repos/system`'s
    `sd_tile.py` and not its `dashboard.py`, because that file is deleted two
    steps from here. Every file named in this entry is that repository's, not
    this one's: 6b-6 changed no pack code.
  - **What must be true before the swap**, the gate itself:
    - [x] every tab marked "backbone" above serves from the pack dashboard
          — all nine routes answer with data: 79 repos, 6 moving work items,
          44 Now rows, 138 skills, 8 worktrees, 23 PRs needing you
    - [x] every tab marked "plugin tab" loads through `~/repos/system`'s own
          registered manifest and its tile, code and pinned actions still
          system-owned — 6b-4 for five, 6b-6 for Queues; six tabs and five
          `sys/`-namespaced actions verified against a live server
    - [x] Ports and rtk have a recorded decision — R11-D12, 2026-08-31
    - [x] Now emits every rank-0 and rank-1 row it emits today, from plugin
          sources as well as backbone ones — checked against `attentionItems()`
          rather than assumed: the system's own function, run over its live
          state, yields **7 rows at rank ≤1** and the pack's `/api/now` yields
          **the same 7 signals**: one cron exit, five cron failure lines, and
          one overdue-tasks row that counts 52. Seven rows, not fifty-eight --
          the overdue row is a count, which is what makes it one row and what
          brings it back when the count changes. Every one of them arrives
          through a plugin tile, which is what R11-D12's row key was for
    - [x] `RUN_ALLOWLIST` exists and every UI mutation maps 1:1 to a `bin/`
          command — 6b-7. One action today (`index`); 6b-6's queue actions
          arrive through the manifest and the same map
    - [x] `sd-dashboard install` exists and replaces the system LaunchAgent
          — `com.sven.project-dashboard` stopped and unloaded,
          `com.sven.sd-dashboard` bootstrapped in its place
    - [x] `index --dump` diffed against the system `/api/state` is empty for
          every shared fact — **0 differences** over 79 repositories and the
          12 fields both report, against a system state refreshed first so the
          diff could not be staleness
    - [x] tailnet reach and token-gated writes carried, not regressed —
          three sockets, the same three the system dashboard held, and
          `/api/actions` answers over the tailnet v4 bind. The v6 path is the
          one thing not provable from this host: the system dashboard's own v6
          socket times out from here too
    - [x] `lsof -i :8767` shows exactly one listening process, and it is the
          pack's dashboard rather than the system one — pid 83558,
          `bin/sd-dashboard serve --port 8767`
- [x] **6b-8 — the swap. The pack dashboard holds :8767.** The system
  dashboard is stopped and unloaded; `com.sven.sd-dashboard` is bootstrapped in
  its place, binding the same three addresses on the same port. Every gate item
  above is now ticked, and each was measured rather than asserted.
  - **The bind was the part that could not be assumed.** R11-D10's correction
    said the reach is two paths and 6b had to carry both or knowingly drop one.
    `serve` now binds one server per address and never the wildcard, which
    would publish this on every network the machine joins. **An address it
    binds is an address it must answer to** — the allow-list holds the bound
    addresses as well as the MagicDNS names, or the bind serves 403s to the one
    path it exists for. Review found two more: one probe now feeds both the
    allow-list and the binding, since asking twice lets the tailnet come up in
    between; and `tailscale ip` is trusted only when it succeeded and only for
    lines that parse as addresses.
  - **launchd's PATH was the quiet one.** It holds neither `git` nor
    `tailscale`, so the installed service would have read the fleet as zero
    repositories and bound nothing but loopback — a dashboard that looks calm
    rather than broken. The plist sets a PATH and turns the bind on, and the
    test reads the parsed plist rather than the template.
  - **What the parity checks actually found: nothing.** 79 repositories, 12
    shared fields, zero differences; seven rank-≤1 rows on both sides. That is
    the outcome the four preceding sub-steps were building toward, and it is
    worth recording that the diff was empty on the first run rather than after
    a round of corrections.
  - **What did not come across, stated plainly.** `/api/ack` has no counterpart
    here, so a dismissed row will return; the system dashboard's per-note
    status writing went with Queues under R11-D25; and the v6 URL is unverified
    from this machine because nothing on it can reach a tailnet v6 address,
    including the dashboard being replaced.
  - **Cost:** +93 lines in `dashboard/`, which stands at **4,093 of 4,300** and
    **2,186 of 2,300 carrying code**. R11-D24 itemised ~25 for this bind and
    it took ~60 once the review fixes were in — another overrun, after Now at
    +77% and the write path at +69%, and the reason that record multiplied its
    estimates rather than trusting them. The ~175 it budgeted has ~93 spent
    and the ack store still unbuilt.
  - Remaining in 6b: the deletion of the system `dashboard.py`, which cannot be
    a bare `rm` — `sd_tile.py` imports it for the collectors behind all six
    plugin tabs, so the server half goes and the collectors stay.
- [x] **6b-9 — the deletion, and what it could not be.** `rm dashboard.py`
  would have taken the six plugin tabs with it: `sd_tile.py` imports that file
  for the collectors behind every one of them. So the 1,854-line server was
  split rather than deleted — `collectors.py` is the 19 functions the tiles
  transitively need, carried over by line-range deletion so every comment
  survives verbatim, and the 37 that served a page are gone: `Handler`, `page`,
  `listen`, `rebuild`, `set_field`, `update_note`, the ack store, and the
  repos, work, PR, issue and Jira collectors whose replacements are this
  repository's. With it went the LaunchAgent and its captured copy, `assets/`,
  and eight `dashboard.sh` verbs. `tile` and `queue-open` are what the manifest
  names, and they are what is left (platypeeps/system#190).
  - **The check was named before the work, and it was the tiles.** All six
    payloads captured byte-for-byte *before* the first edit; after it, five
    identical and `toolbox` differing only in log-age hours, which advance with
    the clock. Running the old and the new code back to back in the same second
    gives **15,107 identical bytes** — without that, the drift would have hidden
    whatever else changed. `--url blog` identical, the exit codes still the
    plugin contract's, and the live server on `:8767` renders all six tabs
    `ok`.
  - **What a diff does not show: three docstrings still spoke of the system
    dashboard in the present tense**, including the one on the Queues tab
    explaining what it "edits". Fixed rather than left — that file outlived the
    thing they describe. Two citations in *this* repository had the same
    problem and are now marked as pointing into history: `dashboard/actions.py`
    and design.md's write-path survey. Four more were in the system
    repository's own README and CLAUDE.md, and review found them one at a
    time rather than as a set: the port table still handed `8767` to
    `local-project-dashboard` with a `PROJECT_DASHBOARD_PORT` override
    that exists nowhere any more, and three others described things this
    change deleted — the LaunchAgent, the vendored `tokens.css`, and the
    startup probe that WARNed within 15s when `brew upgrade python`
    dropped the Full Disk Access grant. That last one documented a
    *recovery*, so it was replaced rather than removed:
    `collectors.vault_blocked()` names the same fix on whichever
    vault-reading tile is asked first — later, and only when looked at,
    which is written down rather than implied to be parity. **The lesson
    is the enumeration**: `grep -rn 8767` across the repo found all four
    in one pass, and the review that found them found one.
  - **The rm-test, which is step 6's own end-to-end check, and did not pass
    quietly.** "Remove the cache and state; only acks, intents and time are
    lost." Rebuilding the index into an empty `XDG_CACHE_HOME` gave **1,135
    rows against the live 1,175**, and the 48 missing ones split in two: 5
    `review-requested` rows that no longer match their search — the documented
    `last_seen` gap, behaving as designed — and 43 `author` rows lost to a walk
    that stopped at exactly 1,000 and called itself complete.
  - **That second half was a bug, and the fix is #667.** GitHub's search hands
    over at most 1,000 results and answers `hasNextPage: false` at that
    boundary: the same answer as an exhausted list. `MAX_PAGES * PAGE_SIZE` is
    also exactly 1,000, so the page ceiling never fired first and `search()`'s
    promise that *"a capped collect never renders as a complete one"* could not
    hold for the one bucket that overflows. Measured on this account
    2026-09-01: ten clean pages to 1,000 rows while `issueCount` read **2,968**
    on every one of them. The walk now finishes against that count, and the
    live first collect says `(incomplete: author)` -- reworded in review from
    "page ceiling hit", which named the one cause that never fires.
  - **So the rm-test's claim stands, but narrower than written.** A rebuilt
    index loses history beyond what the trackers will still hand over — all of
    it closed or merged, none of it anything currently waiting — and it now
    says so out loud instead of reporting a full collect. Nothing currently
    open was lost on this machine.
  - **Nine review rounds, and at round 5 the split stopped being pure
    movement.** Three live bugs in the carried half, none of them written
    here and all three exposed by moving the code out from under the
    server. `collect_ports()` could never report a conflict: `CLASH` and
    `BUSY` are emitted *after* the service rows they refer to, so a
    per-row match scored 0/0 on a transcript holding one of each — and
    6b-4 had already recorded that gap in `sd_tile.py` and deferred it
    "upstream in the collector", so this is the deferral coming due, not
    a new discovery. `vault_blocked()` told the operator to grant Full
    Disk Access for a path that does not exist, because
    `VAULT.parent.exists()` was the only check and TCC was blamed for
    everything else. And `collect_briefs` and `db_rows` read the vault
    unguarded while `collect_areas` did not — the two with nowhere to put
    an error, where an empty list is indistinguishable from an empty
    vault, which is the failure the probe exists to prevent. Under
    launchd an ungranted read does not fail, it waits, so those tiles
    would have blown the 5s budget rather than reported. A deletion PR
    carrying three fixes is not the shape that was planned; it is the
    shape the work turned out to have, and hiding it in a follow-up
    would have made the parity claim above less true, not more.
  - **Cost:** +4 lines of code in `dashboard/`, which stands at **4,119 of
    4,300** and **2,190 of 2,300 carrying code**. The system repository lost
    **4,313 lines** and gained 1,145 across 22 files — measured at the
    squash (87a7d5e), not at the first push, because four review rounds
    landed between them and the earlier figure (4,112 and 844) counted
    neither the fixes nor the docs they invalidated.
- [x] 7 — tag 1.0.0. Does **not** restore the macOS CI leg: that moved to a
  manual trigger at the end of the rollout (R11-D4 amendment, 2026-08-31),
  so step 7 keeps "verify protection" and nothing else changes here.
  - **The park was fleet-wide, and D2 says so.** `design.md:725` decides
    `D2 backlog = bulk-park`; `design.md:549` makes the 45-day rule its
    *intake counterpart*, "so the backlog drains whether or not a worker
    runs." The sweep keeps the backlog from re-accumulating and is not the
    instrument for draining it once. Read the other way round — sweep only —
    step 7 parks **1 item of 102** in this repository and its own `≤20 active`
    check cannot pass. That reading was tried first, in four repositories,
    before the decision records were read properly; the age-sweep pass
    survives in those PRs as the first of two commits rather than being
    rewritten away.
  - **237 items across seven repositories**, each `status: planning` with no
    `branch:`, moved to `docs/work/archive/2026-09/` carrying a dated `parked:`
    line in their own frontmatter — **172 read `bulk-park (D2)` and 65 read
    `age-sweep`**, because the four repositories worked before the decision
    records were read properly kept their age-sweep pass as the first of two
    commits rather than having it rewritten away. Saying all 237 name D2 was
    the tidier sentence and it was false in 65 places. This
    repository: 100 of 102 (#670). rwbp-website 46, hoa-manager 50,
    anomaly-metric-creator 20, loadsmith 18, se-ai-command-pack 2,
    rwbp-coordinator 1. `mezmo_benchmark`'s 46 are untouched under the D7
    freeze, and `sd-github-review`'s 17 are committed but unpushed — GitHub
    reports that repository `archived: true`, so it is read-only. Parking an
    already-frozen repository is close to moot; the commit is left on a local
    branch rather than worked around.
  - **Three survivors fleet-wide, every one kept by the rule rather than by an
    exception.** Each carries a `branch:` and reads `in_progress`: this
    rollout, `2026-08-21-port-integration-only-profile` here, and
    `2026-08-17-store-decomposition-pr8` in loadsmith. The rollout being
    protected by the rule and not by a special case in the script is the point
    — a sweep that needs a hardcoded exemption for the thing running it is a
    sweep nobody can trust to run again.
  - **What the backlog was.** `prd.md:28` measured it: 101 open tasks, **98
    about pack machinery**, 100 never left `planning`. A backlog of machinery,
    in a repository whose thesis is that it built too much machinery. Listing
    it once a day did not make it a plan. Parked is recoverable with `git mv`
    and is not hidden: `sd-status --parked` derives the list from the
    frontmatter field rather than a ledger, so it needed no change to report
    all 100.
  - **`git mv` silently drops an edit made before the move.** It relocates the
    blob already in the index, so edit-then-move stages the *pre-edit*
    content. Three of the six agents running this sweep hit it independently;
    one caught 14 files staged `AM` with the old blob and said it would have
    shipped 14 files that looked parked and were not. The order that works is
    move first, then edit, then `git add` — or verify the index with
    `git show :<path>`, never the working tree.
  - **The check that was missed, and how.** Every repository verified that its
    items moved correctly. None verified that anything pointing *at* them
    still resolved. Copilot found it in two repositories; enumerating from the
    filesystem found it in **four** — loadsmith 18 items referenced from
    `ARCHITECTURE.md` and two spec files, hoa-manager 5 from four docs,
    anomaly-metric-creator 4, rwbp-website 3, and several repositories carry a
    generated `docs/repomix-map.md` that has to be regenerated when docs move.
    This is the standing rule about scoping a check to the blast radius rather
    than to what was edited, failed in the most ordinary way available: a
    rename is exactly the case where the interesting files are the ones you
    did not touch.
  - **Protection: three of four gaps closed, and the fourth should not be.**
    `route` is now a required check (verified it runs on every pull request
    with no path filter, four for four green); squash commits build from
    `PR_TITLE` / `PR_BODY` instead of `COMMIT_OR_PR_TITLE` /
    `COMMIT_MESSAGES`, so a carrier branch's `wip:` subjects stop reaching
    main's history; rebase merging is disallowed for the same reason. All
    three were confirmed by `sd-status` re-reporting each gap as gone, not by
    reading back the call that set it. The fourth used to read *"a review
    requirement exists but asks for 0 approving reviews, so it gates
    nothing"* — and closing it by raising the count locks the repository:
    `enforce_admins` is on, GitHub does not let an author approve their own
    pull request, and there is one maintainer.

    **"Gates nothing" was wrong, and the plan written from it was wrong the
    same way (2026-09-01).** This paragraph said deleting the requirement
    "leaves behaviour identical". It does not. The
    `required_pull_request_reviews` object is what requires a pull request at
    all; `bin/sd-status:501-506` reports its *absence* as
    `no pull-request review is required on {default_branch}` — the same `reviews`
    gap id, a strictly worse state, on a branch anybody could then push to
    directly. The DELETE was refused by the permission classifier before it
    ran, which is the only reason the plan's error stayed on paper. The gap
    text now says what is true — *"a pull request is required but no approving
    review is: 0 approvals, so one with green CI self-merges"* — matching
    what this journal already said correctly 1,700 lines above, at the
    `sd-github-review` tombstone: "requires **0** approving reviews, so a pull
    request with green CI lands". The first correction read *"nothing blocks a
    self-merge"*, which over-claimed in the other direction: the required
    status checks do block it, which is the whole reason 0 approvals is
    survivable here. `test_zero_required_approvals_is_a_gap` now asserts the
    message verbatim, so tightening it again fails the test rather than
    silently leaving this quote stale — which is exactly how it went stale the
    first time. `test_a_missing_review_object_is_the_worse_gap_not_the_same_one`
    pins the other branch, because both emit `reviews` and an assertion on the
    id alone passes for either.

    **Decision: left open, deliberately (user, 2026-09-01).** Not deferred and
    not forgotten. Raising the count to 1 locks a single-maintainer repository
    with `enforce_admins` on; deleting the object removes the requirement that
    a pull request exist. Neither is an improvement, so the repository keeps a
    review requirement that mandates the pull request and asks for zero
    approvals, and `sd-status` goes on reporting it. A gap reported every run
    with a recorded reason is the honest state; the failure mode this replaces
    is a gap closed by making the tool stop mentioning it.

    **Accepted policy now, with a mechanism (user, 2026-09-01, #680).** The
    paragraph above stands as written — it was true on the day, and "left
    open, deliberately" is what the decision was. What changed is the
    reporting, not the branch: `sd-status` reads `.github/sd-status.json`, a
    tracked sibling of `.github/sd-review.json`, and prints this finding as
    `ok  [reviews] accepted 2026-09-01: …` with its ending condition on the
    line below. Not suppressed and not deleted. The row still prints every
    run and still names the state; `--json` moves it out of
    `protection.gaps` into `protection.accepted`, so a consumer counting gaps
    counts the open ones only and never mistakes an accepted finding for an
    absent one. The all-clear line is guarded too: "protection is fully
    enforcing" no longer prints over the top of an accepted finding.

    The incident is the one this bullet already described from the other
    side. A gap that prints on every run with nothing to do about it is what
    teaches a reader to skim the section — and the protection section is
    where a real regression would arrive. The deletion criterion lives in the
    file rather than here: `until: a second account with merge rights on this
    repository exists, or enforce_admins is turned off`. When that comes true
    the entry is deleted and the gap returns on its own; nothing in
    `bin/sd-status` has to change for that to happen.

    **Keyed on the observed protection state, never on the gap id** — the
    correction two paragraphs up, made executable rather than restated. Both
    `reviews` branches emit the same id, so an entry matched on the id would
    accept *no pull request is required at all* while meaning *a pull request
    is required and asks for zero approvals*. An entry therefore pins facts —
    `required_pull_request_reviews: true`, `required_approving_review_count: 0`,
    `enforce_admins: true` — and any drift stops it applying, at which point
    the gap prints as a gap carrying a line that an acknowledgement exists and
    no longer matches.
    `test_the_zero_approval_entry_never_accepts_the_missing_review_object`
    holds that line, built on the
    `test_a_missing_review_object_is_the_worse_gap_not_the_same_one` that
    found the distinction in the first place. A malformed file accepts
    nothing at all and reports each fault as its own gap: it fails closed, and
    loudly.
  - **`migrate-trellis` deleted (#669), and the evidence is on disk rather
    than in a ticked box.** `git ls-files .trellis` returns **0** in all nine
    consumer repositories of the 3-c wave; what remains is 17–41 untracked
    files each, which belong to `sd-status`'s `RESIDUE` table — it survives
    this step and prints the exact removal command. `~/repos/ai/Trellis` has
    1,461 tracked and is the upstream project, not a consumer.
  - **Step 7's `grep -rli trellis` → archive only cannot mean what it says,
    but the park brought it most of the way.** Before the 100 items moved,
    139 files outside `docs/work/archive/` named it; after, **42 do, against
    534 inside the archive.** The fall is real and is a side effect rather
    than an achievement — those journal entries did not stop naming it, they
    became archive. What is left is not residue, and each group has to stay:
    **18** under `docs/spec/`, a tree already known-stale and scheduled
    separately; **5** belonging to the two work items still active, three of
    them this record; `bin/sd-status`'s `RESIDUE` row, which *is* the detector
    for the residue; and the rest — `CHANGELOG.md`, `.gitignore`, `AGENTS.md`,
    `CONTRIBUTING.md`, the two tests, the two `dashboard/` docstrings — naming
    it in past tense, which the supersede-don't-backdate convention exists to
    protect. Reaching zero needs a rename that makes the record less true.
    Read as live code paths it is met: `bin/migrate-trellis` and
    `tests/test_migrate_trellis_consumer.py` are gone, no code reads
    `.trellis` at all, and the one comment left in `bin/sd_setup_github.py`
    is past-tensed.
  - **One citation was wrong before this step touched it.** CONTRIBUTING.md
    and `.gitignore` both said the managed-block markers were kept "only so
    `migrate-trellis` can find and remove the equivalent block in consumer
    repos" — but `grep '\.gitignore' bin/migrate-trellis` returned nothing.
    It stripped marker pairs from `AGENTS.md`, never from a gitignore. The
    markers were kept for a dependency that never existed. Said plainly rather
    than dropped, and left in place because
    `docs/spec/backend/manifest-and-filesystem.md:1868` still specifies them
    and that tree is already known-stale.
  - **The park invalidated two of this repository's own docstrings**, which is
    the same class of bug step 6b's round 8 found in the system repo and the
    reason that lesson is worth repeating. `dashboard/work.py` argued its
    design from "of 310 active items fleet-wide, 300 read `planning`" and
    `tests/test_dashboard_work.py` restated it; parking 237 items made both
    false while every test still passed, because the numbers live in prose. Now
    57 and 47, measured from the collector rather than estimated. The ratio the
    argument rests on did not move — which is exactly why the stale figure
    would have survived a reading that only checked whether the point still
    held.

  - **`v1.0.0` is tagged at `daebee6c`**, the merge of the record above, so the
    tagged tree carries its own CHANGELOG entry rather than promising one. It
    is a lightweight tag, matching `v0.72.0` and everything before it, and no
    release workflow fires: the two that remain are `sd-review-route.yml` and
    `tests.yml`. Verified from the remote rather than from the local ref —
    `git ls-remote --tags origin v1.0.0` returns `daebee6c`;
    `git show v1.0.0:CHANGELOG.md` opens on `## 1.0.0 - 2026-09-01`; and
    `git cat-file -e v1.0.0:bin/migrate-trellis` exits non-zero on a path
    that does not exist, with `bin/sd-status` as the control that it does
    resolve. That last one replaced `git ls-tree v1.0.0 bin/`, which was
    correct — the trailing slash makes it list the 15 entries under `bin/`
    rather than the tree entry itself — but which silently proves nothing if a
    later reader drops the slash. A check whose validity turns on one
    character is worth trading for one that cannot be read two ways.
  - **Step 7's three checks, at the tag.** `sd-status` active is **2** against
    a ceiling of 20; **100** archived items carry `parked:` and
    `sd-status --parked` lists them; the `grep -rli trellis` criterion reads
    42 outside the archive against 534 inside, which is the bullet above —
    met as live code paths, unmeetable as written. The box is ticked on the
    first two and on the substantive reading of the third, with the literal
    reading recorded as unsatisfiable rather than quietly counted as passed.

  - **The tag shipped a CHANGELOG line that overclaims, and this is the
    correction.** `v1.0.0`'s entry says every parked item carries a `parked:`
    line "naming the decision (D2) that moved it". 65 of the 237 name
    `age-sweep` instead, so the sentence is wrong for the four repositories
    that ran the sweep pass first. Found from a Copilot comment on one line of
    one file in `hoa-manager` — it checked that a doc's claim about frontmatter
    matched the frontmatter, which pointed straight at the same claim made
    fleet-wide two documents away. `main` is corrected here; the tagged tree
    keeps the wrong line, because retagging to hide it would be worse than a
    superseded sentence that the record explains.

  - **`sd-github-review`'s 17 items are parked locally and will stay that way,
    decided rather than deferred (user, 2026-09-01).** The commit is `414ff39`
    on the local checkout and it is not pushed, because GitHub reports the
    repository `archived: true` — it was retired at step 4 and carries a README
    tombstone saying so. Unarchiving to push, then re-archiving, is three state
    changes on a retired repository, each one leavable half-done, and it buys
    nothing anyone reads: the park is already effective everywhere it is read.
    The local tree has **0 active items and 17 under `archive/2026-09/`, all
    carrying `parked:`**, and the dashboard — which enumerates checkouts from
    the filesystem, not from GitHub — contributes **0 rows** for this
    repository to `moving` or `unstated`. The cost is that the checkout sits
    one commit ahead of its origin permanently, which is a trap for whoever
    finds it later; that is what this paragraph is for. If the repository is
    ever unarchived for an unrelated reason, push `414ff39` then.
  - **Superseded the same day — the push happened, and the trap is gone
    (2026-09-01).** The bullet above was true when written and its operative
    half is now false, so it stays and this says what changed. The repository
    was unarchived, `414ff39` was pushed as `task/09-01-bulk-park`, and
    [PR #167](https://github.com/platypeeps/sd-github-review/pull/167) —
    *"chore(work): bulk-park 17 planning items with no branch (D2)"* — opened
    at `2026-09-01T20:25:23Z` and merged at `2026-09-01T20:28:52Z`, head sha
    `414ff3971a38581afadfc5b4b6af3f2822874371`. The repository is archived
    again: `gh api repos/platypeeps/sd-github-review` returns
    `{"archived":true,...,"pushed_at":"2026-09-01T20:28:53Z"}`, one second
    after the merge. All three state changes the bullet declined to make were
    made, and none was left half-done.
  - **The premise that failed was "the park is already effective everywhere it
    is read."** It was effective everywhere the *dashboard* reads, which
    enumerates checkouts from the filesystem — that part of the bullet was
    right and stays right. Anything reading the remote saw the opposite: #167's
    own body records that `main` was still reporting **17** active items that
    had already been parked locally. A finished commit on an unpushed branch is
    invisible to every check that reads GitHub, which is a second reader the
    cost/benefit line did not count.
  - **The trap the bullet existed to warn about no longer exists, so do not act
    on its standing instruction.** In `~/repos/platypeeps/sd-github-review`,
    `git rev-list --left-right --count origin/main...HEAD` prints `0	0`,
    `git branch -a --list '*bulk-park*'` prints nothing, and
    `git ls-remote --heads origin` returns exactly one ref,
    `dd9293dcb16a7de6792891061a6f0d81d930bbb8	refs/heads/main` — the merge of
    #167. "If the repository is ever unarchived for an unrelated reason, push
    `414ff39` then" has nothing left to do.
  - **What it cost, priced honestly.** Three state changes on a retired
    repository, plus one the original did not price: a pull request merged into
    an archived repository's `main`, which is a branch-protection surface
    nobody maintains any more. What it bought is that the two readers now
    agree. The park's shape did not change — #167 is 49 files with **17**
    additions, every file `R100` except each `prd.md` at `R099` for its one
    added `parked: 2026-09-01 bulk-park (D2)` line. Pure renames, nothing
    rewritten, and the local numbers the bullet above quotes are now the
    numbers on `origin/main`.

### `sd sweep` — the intake counterpart, as a reporter (2026-09-01)

D2's one-time park drained 237 items and `design.md:549` names the 45-day rule
as its intake counterpart, "so the backlog drains whether or not a worker
runs." Nothing ran it. `sd_lib` defined the `parked:` field, `sd-status
--parked` read it, and the writing half existed only as a sentence: the design
puts the sweep inside `sd-plan`'s first commit (`design.md:106`), and
`bin/sd-plan` is one of the six commands R11-D15 lists as still unwritten. So
the rule that keeps the backlog drained has never executed once.

`sd sweep` reports and does not park. That is a deviation from `design.md:106`,
which has the sweep parking as a side effect of `sd-plan`, and it is
deliberate: the parking half stays with `sd-plan` when that gets built, and
what shipped here is the half that was missing entirely — the ability to see
the backlog refilling. Two failures from the bulk-park argue against an
unattended writer landing first. `git mv` relocates the blob already in the
index, so an edit staged before the move is dropped and the commit still looks
clean; three separate agents hit that. And parking broke every document citing
an item's old path, needing hand-written fixes in four of the seven
repositories, each one caught by review rather than by a script. Thirteen
checkouts, unattended, with nobody reading the result, reproduces both.

**The first run found 31 items over the threshold, and 34 before a
one-character fix.** `design.md:106` writes the rule as ">45 days" and `:550`
as "past 45 days"; the first implementation read it as `>=`, which swept three
items sitting at exactly 45 days. The corrected operator is in
`bin/sd_sweep.py` with both design lines cited beside it, and
`test_the_boundary_is_exclusive_as_the_design_writes_it` pins it from both
sides — a fixture asserting only that 46 is due passes against `>=` too.

**All 31 sit in `mezmo/mezmo_benchmark`**, which is 48 of the fleet's 57 active
items and was never in D2's scope — the park covered the seven platypeeps
repositories. So the sweep's first output is not a report on the parked fleet
at all; it is the observation that the one repository the park did not reach is
where the entire remaining backlog lives. The other five checkouts with live
items owe nothing: 3, 2, 2, 1, 1 active and zero due.

**No path argument, in either mode.** R10-D6 says an `sd-*` command never takes
a path to somebody else's repository. Per-repo mode reads the checkout it was
run in; `--fleet` reads `SD_REPO_ROOT` from the environment — the same setting
`dashboard/collect.py` reads, rather than a second way to say where the repos
are. `test_verb_inventory.py`'s R10-D6 assertion covers this and passes.

**Undated items are reported, never swept.** An item with no parseable
`created:` and no `YYYY-MM-DD-` directory prefix has no age the module can
prove. The alternatives are to call it zero days old, which hides it forever,
or infinitely old, which sweeps whatever nobody dated. Fleet-wide there are
currently 0 of these, which is a fact worth having rather than an unexercised
branch — the tests carry the fixtures.

**A stale duplicate of the `bin/` ceiling came out with it.** R11-D15
re-derived that cap at 14,000 two commits ago and updated
`tests/test_loc_caps.py` and `tests/test_verb_inventory.py`, but a third copy
in `tests/test_sd_review_boundary.py:285` still said 8,000 and failed the
moment `bin/` grew — at 8,166 lines against a governing ceiling of 14,000.
Removing the duplicate is not raising a cap in the PR that busts it: the
governing number was set in its own decision record with headroom, and this was
a copy D15 missed. `test_loc_caps.py` enumerates from `git ls-files` rather
than from the directory, so it is also the copy that cannot count a stray
`__pycache__` entry. The migration-tool cap is duplicated the same way and
currently agrees, which is the state the `bin/` ceiling was in before it
drifted; the comment left behind says so.

**Scheduled, and not by this pack.** The first plan here was a second
LaunchAgent beside `sd-dashboard`'s, which `design.md:620` forbids in as many
words: *"The backbone ships no scheduler and schedules nothing… Sole pack-owned
LaunchAgent = `sd-dashboard install`"*, with cron ownership assigned to
`local-cron-jobs`. So the job is `jobs/sd-sweep-weekly.job` in the system
repository (platypeeps/system#191), Monday 07:15, a quarter hour after
`secret-scan-weekly` so the two do not contend for the same wake. Weekly rather
than nightly because a 45-day threshold reprints substantially the same list 45
times otherwise. It exits 0 whether or not anything is due — finding items is
the rule working, and failing would fire the banner every week the sweep did
its job, which is the opposite call from `secret-scan-weekly` where findings
*are* the incident.

The check that mattered was not that launchd loaded it. `bin/sd-dashboard`
carries a comment about exactly this: under launchd's own PATH
(`/usr/bin:/bin:/usr/sbin:/sbin`) a fleet walk can read as zero repositories
and look like a quiet job rather than a broken one. Run under `env -i` with
that PATH, `python3` resolves to the system **3.9.6** and the sweep still
reports 57 active — so it is reading the fleet, not an empty one.
`cron-jobs.sh verify` says `ok`, `run` exits 0 and logs `done`, and
`failures.log` has no entry for it.

### Two gates that certified nothing, and the vault root (2026-09-01)

Found while scoping step 8, before writing any of it. All three are checks or
facts the plan already carried; none is a design change.

**Step 10's criterion was vacuous.** It read `grep -c 'System/Databases'
pack.py` = 0. That returns **1** today, and the one hit is a *comment* --
`pack.py:838`, `# Not "Mezmo": \`System/Databases/Market Watch/Mezmo.md\`
already holds`. The four real bindings are built with `os.path.join(VAULT,
"System", "Databases", ...)` at `pack.py:147-150`, so they never produce that
literal, and **40 call sites** reference the joined constants. Deleting one
comment would have passed the gate with the entire migration undone. Replaced
with a check that names the constants the migration has to remove rather than
a string that happens to appear near them. The lesson is the one this rollout
keeps re-learning: a check built from a string you expect to see cannot find
what you did not know was there.

**And the replacement was vacuous too, for a third reason.** It was first
written `grep -cE 'BI_DB\|SP_DB\|TT_DB\|TP_DB\|VAULT' pack.py`, because a `|`
inside a markdown table cell has to be escaped to survive the table. Markdown
renders that back to a bare `|`, but the raw source is what anybody copies,
and `\|` in an ERE is a *literal pipe* -- so the pasted command searches for
one long string containing pipes, matches nothing, and reports `0`. Measured
against today's unmigrated `pack.py`: the escaped form returns **0** and the
correct form returns **43**. A third gate certifying nothing, in the commit
written to fix the first two, and it would have read as a pass. Now
`grep -c -e BI_DB -e SP_DB -e TT_DB -e TP_DB -e VAULT pack.py`, which needs no
alternation and so needs no escaping. Any verification command living in a
table has this hazard; the fix is to write it pipe-free rather than to escape
it correctly, because the escape is invisible in every rendered view of the
document where somebody might check it.

**Step 9's caller list named the wrong sixth file.** `design.md:289` listed
`market-watch`; `grep -c "pack\.py"` on that SKILL.md returns **0**. The real
sixth is `settings.vault.json` -- the permission grant,
`"Bash(python3 .../pack.py *)"`, which is what makes the other five legal.
That is not a bookkeeping fix: it **inverts the migration order**. The five
routines retarget first and the grant goes **last**, because a grant rewritten
early leaves every routine unable to run `pack.py` mid-migration, with the
replacement not yet reachable. `tips-weekly/SKILL.md:110` constrains the
replacement further -- "If a mechanical need shows up that `pack.py` doesn't
cover, extend `pack.py` -- the grant covers it automatically" -- so `sd store`
needs an equivalently narrow single-binary grant, or all five settings files
need editing again later.

**The vault root is two names, not one, and two callers defect.** The
convention is a two-layer one and it is coherent where it is followed:
`OBSIDIAN_VAULT` is the public knob a person sets, and the shell resolves it
into `VAULT` for the process it launches --
`task-actions.sh:19` (`VAULT="${OBSIDIAN_VAULT:-$HOME/Documents/Sven Delmas Vault}"`,
re-exported at `:52`), `obsidian-tasks.sh:14`, `obsidian-review.sh:13`,
`machine-setup.sh:911`. Two callers break it:

- `local-project-dashboard/collectors.py:48` reads **`VAULT`** directly with
  its own default, and nothing resolves `OBSIDIAN_VAULT` into it any more. Its
  own comment at `:27` records why -- "with the server went the shell that used
  to resolve them". The file is still live: 6b-8 deleted the server half and
  kept the collectors. This is *not* a broken promise inside that repository:
  `dashboard.sh:80` documents `VAULT` as the knob, "vault path, read by
  collectors.py itself", so the repo is internally consistent and setting the
  name it documents works. The defect is fleet-level -- one path with two
  documented names, each correct in its own README -- which is why it reads as
  fine from inside either one.
- `pack.py:146` reads **neither**. `grep -cE 'os.environ|getenv' pack.py` is
  **0**; the root is a hardcoded absolute string with a username in it.

Step 8's vault driver has to pick one, and the answer is `OBSIDIAN_VAULT` as
the knob with `VAULT` reserved for process-internal handoff -- five files to
one, and it is the name the READMEs already document.

**The two defectors get different dispositions, and neither gets a linter.**
`pack.py` is not fixed at all: step 10 deletes those four bindings outright
when `sd store` replaces them, so an env-var patch now is work thrown away.
It is added to step 10's scope explicitly rather than left implicit, because
"the migration removes it" is exactly the kind of assumption that survives a
step being descoped. The one thing that would change this is step 10 slipping
far: the root is a hardcoded absolute string with a username in it, which is a
portability defect on its own terms and would then be worth one line.

`collectors.py` is a small standalone change in the system repo -- read
`OBSIDIAN_VAULT`, fall back to `VAULT`, then the default -- which is
backward-compatible, since nothing that sets `VAULT` today stops working. It
is worth doing only because it is cheap; it fixes nothing that is broken now.

What neither disposition buys is prevention, and that is deliberate. Nothing
enforces this convention, and nothing should: R10-D6 keeps `sd-*` commands out
of other repositories, so the pack cannot lint for it, and a cross-repo checker
built for two files whose count is about to become one is more machinery than
the problem. The convention is enforced where it is *read* -- step 8's driver,
one place -- and documented everywhere else. That is the honest state, and it
is written down here so the next person does not rediscover the divergence and
assume it was missed.

**One thing the driver must carry across regardless of the name.**
`collectors.py:173-227` wraps its vault read in a subprocess with a 15-second
timeout, because macOS TCC turns an unauthorized read of `~/Documents` into a
*silent hang* rather than an error. A driver that distinguishes only "path
missing" from "path present" will hang instead of reporting, and an unattended
caller will look slow rather than blocked.

  - **7-triage — 2026-09-01. The survivors, enumerated.** Step 7's checklist row
    said "triage survivors" and the step closed without it; the step 4 entry said
    the next pass should "find it by reading rather than by grepping", so this is
    that pass. Three trees, **25 tracked files, 15,006 lines**, every one of them
    dispositioned against the working tree rather than against the earlier note.
    **Nothing was deleted.** 7,839 lines of specification is a content decision
    for the maintainer, so what landed is the non-destructive half: a dated
    notice at the top of every stale page, `CONTRIBUTING.md` and `AGENTS.md`
    corrected, and the delete column left standing as a recommendation with its
    evidence attached.

    **The recorded note was right about the fleet files and wrong about
    `docs/spec/`, and the difference matters.** "No code reads either, only
    `CONTRIBUTING.md` and two spec pages" holds for `docs/FLEET_ROLLOUT.md` and
    `docs/fleet/**` — verified rather than trusted, below. It does **not** hold
    for `docs/spec/`, which three live code paths and one skill still touch:
    `bin/sd-docs-lint` rule 4 enumerates the tree at run time and fails a spec
    directory that holds pages without an `index.md` linking each of them;
    `.github/sd-review.json:19` and `bin/sd_route.py:24` both carry
    `docs/spec/**` in `never_skip`, so a change there is never routed past
    review; and `skills/sd-spec/SKILL.md` writes into it as `sd-ship`'s second
    stage. The tree is a live surface whose *content* is stale — not orphan
    text. That is why the delete column below carries an ordering constraint the
    fleet files do not: rule 4 tolerates an index linking a page that is gone,
    so a page may leave alone, but a directory has to leave **with** its index.

    **Where the "nothing reads this" claim was checked, since it is only as good
    as the grep behind it.** Inside the repository: every tracked and untracked
    file except `.git`, for `FLEET_ROLLOUT`, `docs/fleet`, `consumers.json` and
    `surface-partition.json` — six files match, and all six are prose:
    `CONTRIBUTING.md`, `CHANGELOG.md` (history), `docs/review-learnings.md`
    (historical PR entries), `docs/spec/backend/manifest-and-filesystem.md`
    (itself stale), the rollout journal, and `docs/FLEET_ROLLOUT.md` itself. No
    hit in `bin/`, `dashboard/`, `skills/`, `tests/`, `.github/`, `actions/` or
    `agents/`. Outside it: `~/.claude/skills`, `~/.claude/agents`,
    `~/.claude/commands`, `~/.claude/plugins`, `~/.claude/*.json|*.md` and
    `~/.config` — **0**; and all seventeen sibling repositories under
    `~/repos/platypeeps/` plus `~/repos/system`, `~/repos/mezmo`, `~/repos/rwbp`,
    `~/repos/hoa`, `~/repos/ai` and `~/repos/github-commit-audit` — **0**. The
    three consumer repositories that have a `docs/spec/` of their own have their
    own, and do not reference this one.

    **The existence check was mechanical, not impressionistic.** Every
    backticked token in every page that parses as a path was resolved against
    `git ls-files` (script kept out of tree; the counts are reproducible from
    it). Aggregate: **807 path citations across the 23 markdown pages, 681 of
    them naming something that is not in the tree.** Per-page counts are in the
    table. It is a floor, not a ceiling — it cannot see a command name or a
    schema field that no longer exists, only a path.

    | File | Lines | Missing/total paths | What it specifies | Disposition |
    |---|---:|---:|---|---|
    | `docs/spec/backend/index.md` | 59 | 7/11 | Scope and checklist for `install.py`, `manifest.json`, `installer/`, `tests/install_test_support.py` | **delete** — conditional |
    | `docs/spec/backend/directory-structure.md` | 88 | 22/23 | `install.py` + six `installer/` modules + `manifest.json` + `templates/` + `scripts/` layout; `PLATFORM_REGISTRY` | **delete** |
    | `docs/spec/backend/error-handling.md` | 198 | 2/2 | `install.py` exit-code contract; three transferable diagnostic lessons | **stale-notice** |
    | `docs/spec/backend/fleet-consumer-conversion.md` | 140 | 3/4 | running `install.py <consumer>` across the fleet; `--thin`/`--resweep-verdict`; `sd-status fleet` | **delete** |
    | `docs/spec/backend/logging-guidelines.md` | 80 | 1/2 | installer status lines; `_SECRET_SHAPES` in `templates/scripts/sd_ai_command_pack_lib.py` | **delete** |
    | `docs/spec/backend/manifest-and-filesystem.md` | 2,998 | 302/377 | the whole manifest/installer/plugin-generation/payload-gate/fleet-campaign model | **stale-notice** |
    | `docs/spec/backend/quality-guidelines.md` | 2,015 | 67/80 | 18 named contracts for deleted shipped scripts; the live bash 3.2 gate; "Silent Paths Must Say Why" | **stale-notice** |
    | `docs/spec/frontend/index.md` | 76 | 14/16 | `templates/`, `.github/command-sources/`, `manifest.json`, `make generate` | **delete** |
    | `docs/spec/frontend/directory-structure.md` | 60 | 9/9 | the per-platform adapter layout under `templates/` | **delete** |
    | `docs/spec/frontend/adapter-guidelines.md` | 2,042 | 81/93 | 13 `Scenario:` sections, each a deleted command surface; the review coordinator and `.sd-ai-command-pack/review.json` | **delete** |
    | `docs/spec/frontend/quality-guidelines.md` | 83 | 11/11 | adapter drift rules keyed on `manifest.json` | **delete** |
    | `docs/spec/guides/index.md` | 183 | 8/11 | thinking-guide index + AI-review verification checklists | **stale-notice** |
    | `docs/spec/guides/code-reuse-thinking-guide.md` | 223 | 9/9 | general reuse guidance; a Trellis-CLI tail that never applied here | **stale-notice** |
    | `docs/spec/guides/cross-layer-thinking-guide.md` | 281 | 22/22 | general cross-layer guidance; three template/docs-site sections that do not | **stale-notice** |
    | `docs/spec/tooling/index.md` | 81 | 24/26 | scope list of six deleted scripts and two deleted test modules | **delete** |
    | `docs/spec/tooling/bookkeeping-validator.md` | 226 | 8/9 | `review-preflight.mjs` internals; Trellis bundles and receipts | **delete** |
    | `docs/spec/tooling/fleet-publish-acceptance-criteria.md` | 112 | 6/7 | `fleet-publish.py` PRD tick; `sd-fleet-refresh`; `task.py archive` | **delete** |
    | `docs/spec/tooling/fleet-publish-generated-content.md` | 110 | 9/10 | `fleet-publish.py` ordering; `docs/repomix-map.md`; `.obsidian-kb` block | **delete** |
    | `docs/spec/tooling/review-attempt-state.md` | 145 | 3/3 | the deleted review coordinator's per-attempt state cache | **delete** |
    | `docs/spec/tooling/runtime-coverage-lanes.md` | 97 | 14/16 | the kcov shell-coverage lane, retired by R11-D6 | **delete** |
    | `docs/spec/tooling/surface-retirement-doc-gates.md` | 126 | 23/25 | two doc gates that were themselves deleted at 3e | **delete** |
    | `docs/spec/tooling/vendored-trellis-compatibility.md` | 214 | 26/29 | wrappers around `.trellis/scripts/task.py` and `add_session.py` | **delete** |
    | `docs/FLEET_ROLLOUT.md` | 510 | 10/12 | the campaign controller, refresh shape, cohort waves, thin conversion | **delete** |
    | `docs/fleet/consumers.json` | 330 | n/a | schema-5 rollout order, cohorts and install mode for ten consumers | **delete** |
    | `docs/fleet/surface-partition.json` | 4,529 | 731/740 targets | the 0.72.0 payload partitioned across eighteen platforms | **delete** |

    **Keep 0, stale-notice 6, delete 19.** No page in these trees is accurate as
    it stands, which is why the keep column is empty rather than generous — the
    six marked stale-notice are mixed, not correct.

    **The one conditional row, and it is a real constraint rather than a
    hedge.** `docs/spec/backend/index.md` is the rule-4 index for a directory
    three of whose seven pages are staying. Deleting it while `error-handling.md`,
    `manifest-and-filesystem.md` and `quality-guidelines.md` remain makes
    `sd-docs-lint` fail on `docs/spec/backend` — "every spec directory has an
    index.md". So it is delete-with-the-directory or rewrite-down-to-the-
    survivors, never delete alone. `docs/spec/frontend/` (4 files) and
    `docs/spec/tooling/` (8 files) carry no such constraint: every page in each
    goes, index included, and the directory leaves whole. `docs/spec/guides/`
    stays whole.

    **Two facts that would change a disposition if they turned out otherwise,
    stated so they can be checked rather than assumed.** First, the
    `docs/spec/backend/manifest-and-filesystem.md` Trellis-gitignore section is
    load-bearing in one direction: `CONTRIBUTING.md` keeps the vestigial
    `SD-AI-COMMAND-PACK` markers in `.gitignore` *because* that section still
    specifies them, so deleting the page without settling the markers moves the
    problem rather than closing it. Second, that page's Machine-Scope Installer
    section is the design `bin/sd_install.py` implements, told through
    `installer/machinescope.py`, `installer/machinepayload.py` and
    `bin/sd-machine-install` — files that no longer exist. It is a design
    record, and whether a design record belongs in `docs/spec/` or in
    `docs/work/archive/` is the question its disposition actually turns on.
    Neither was decided here.

    **Three things were decided against.** Rewriting the six mixed pages down to
    their true parts — that is a content rewrite wearing a triage's clothes, and
    it would have destroyed the record of what the machinery was, which is the
    only thing these pages are still good for. Putting the notice inside the two
    JSON files — JSON takes no comment, and inventing a `"_stale"` key changes a
    schema to carry prose; `docs/fleet/README.md` says it beside them instead.
    And retitling each page the way the `sd-github-review` README tombstone
    retitled its repository — the H1 of a spec page is not a claim that can go
    stale, so the notice carries the date and the H1 is left alone.

    **Verified**: `make check` green before and after
    (`VENV=/Users/sven/repos/platypeeps/sd-ai-command-pack/.venv`, since a fresh
    worktree has none) — "All checks passed!"; `bin/sd-docs-lint` clean, which is
    the check that matters here because rule 4 is the only automated thing that
    reads this tree.
### Step 8, slices i-iii: the manifest gets teeth, and the vault gets read (2026-09-01)

Three PRs, landed in order. Step 8 is not done -- the write verbs and the
golden-corpus baseline are still ahead -- and what is here is written down now
rather than at the end, because two of the three carry findings that outlived
their slice.

**8-i (#678) -- enforce the manifest, and pin it.** `sd plugin add` validated
`prefix` and `dashboard.tile` and nothing else; the `kinds`, `issues` and
`vendor` blocks it accepted since 6b-1 were accepted *unread*. All three are
now checked generically -- the backbone learns that a kind is well formed and
internally consistent and never learns what a `score` or a `tip` is -- and
`sd plugin lock` writes the `sd-plugin.lock` the layout has always named and
nothing has ever produced. The manifest half of that lock hashes the **bytes on
disk**, not re-serialised JSON, so a key reorder is drift.

The consistency checks are the point, not the type checks. A `protected-fields`
naming a field the kind does not declare protects nothing and reads in every
review as though it protects something -- the vacuous-check failure this
rollout keeps finding, this time in its own new code before it shipped. `test_the_shape_6b_accepted_is_now_refused` keeps the manifest 6b-1
would have taken, verbatim, as the record of what the inversion was.

**Two review findings, one accepted and one that taught a lesson about
probes.** Copilot's first pass was right: `sections.template` checked existence
only, so a *directory* at `templates/tip.md` registered clean and failed at
render -- exactly the deferral registration exists to prevent. Fixed with a
regular-file check; `vendor.*.path` still takes either, because a vendored tree
is the ordinary case, and both are pinned.

Its second pass said `inside()` could raise out of a symlink loop. I probed
3.9.6 and 3.14.7, found the loop harmless on both -- `resolve()` returns the
link itself and `exists()` swallows the `OSError` -- found a *different* real
crash (a NUL byte, which JSON can write and no filesystem can hold), fixed
that, and declined the loop half in the commit message. **CI failed on
`unittest (ubuntu-latest, 3.10)` with a traceback out of the loop.** On
3.10-3.12 `resolve()` raises `RuntimeError("Symlink loop from ...")`, which is
neither of the classes I had caught. The two ends of the supported range agree
with each other and disagree with the middle, and the middle is an interpreter
the pull request was already testing against. **Sampling the extremes is not
sampling the range** -- and the check that caught it was one CI already ran, not
one I chose. `inside()` now catches all three classes, and the loop test asserts
a refusal naming the offending key rather than one particular sentence, because
the wording legitimately differs by version.

**8-ii (#681) -- one resolution home for plugin settings.** `sd config
get|set|unset|list`, with the keys **declared in the manifest** (`description`
required, `pattern` optional and compiled at registration) and the values
namespaced under the machine config's `config` key. `set` matches with
`re.fullmatch`, so an unanchored pattern cannot be quietly permissive.

**8-iii -- the `store` block and the vault driver.** `sd store list|get`, and
the answer to a gap the plan carried without noticing: **the eight keys have no
slot for where a kind is kept.** R11-D26 puts it in a `store` block beside
`dashboard` rather than in a ninth key, so standing rule 2's count is untouched
and step 11 reorganises the vault by rewriting `bases`.

Three things in it are load-bearing beyond the verbs:

- **The root is `$OBSIDIAN_VAULT`, never a literal path, and has no default.**
  `pack.py:146` is the incident. An unset variable is a sentence naming the
  knob; a default would be a fourth spelling of a path that already has three.
- **The 15-second probe came across from `collectors.py:173-227`**, as the
  2026-09-01 scoping entry required. macOS answers an ungranted `~/Documents`
  read by waiting, not by failing; a driver that told "missing" from "present"
  apart and nothing else would inherit that 1605-second hang.
- **`fields` now keeps its declared order.** 8-i sorted it, which was invisible
  until `sd store list` needed a column order and printed `score, status` for a
  kind that declares `status, score`. `pack.py` printed status first for three
  databases. Sorting discarded information no other key carries.

The acceptance criterion is `FreshnessTests.test_a_note_written_directly_into_
the_vault_is_visible_to_the_next_query`, and it is written as a *direct* write
on purpose: the note is created with `write_text`, never through `sd`, and then
a query has to see it. A test that wrote through `sd` and read back through
`sd` would pass against a purely in-memory store and prove nothing about the
vault. Three reads, no writes through the tool: empty reports empty, a note
dropped in by hand is listed, an edit made in place is reflected.

**What is left of step 8.** The write verbs (`sd store add|set`, which is where
`protected-fields`, `transitions`, `human-only`, `floor` and `sections` stop
being declarations and start being enforcement) and the golden-corpus baseline,
which must be captured **before** any vault move because step 11 compares
against it.

**8-iv has a design now, and the table row above cannot see it (2026-09-01).**
The step 8 row's criterion is "direct-write-then-query freshness test green",
which 8-iii met -- so the row reads satisfied while two thirds of the step is
unbuilt. The row is left as written rather than edited, per this rollout's
habit of superseding instead of backdating; what it needs is stated here.
**8-iv's criterion is the inverse of 8-iii's**: a note created through
`sd store add` and read back with `read_text`, plus a `set` against a note
carrying a list value that asserts the edited key changed *and* the list
survived byte-identical. R11-D27 records why -- `frontmatter()` is a lossy
reader, and 244 of the 244 notes in the live bases lose data to a
parse-and-rewrite. A write-through-`sd`, read-through-`sd` test passes against
an in-memory store and would not see it. The golden-corpus baseline (8-v)
keeps the criterion the row already gives it.

**The project's own planning-review rule still does not resolve.**
`.claude/rules/sd-planning-adversarial-review.md` points at
`../sd-ai-command-pack/planning-adversarial-review.md`, which does not exist
from that directory or anywhere on this machine. Flagged a second time here.
This run appends an implementation journal and a decision record and reaches no
planning convergence boundary -- no implementation approval is being requested
and nothing moves to `in_progress` -- so the contract does not gate it, and no
review lane is being claimed.

### The sweep the planning contract asks for, run late and finding three (2026-09-01)

The step 8 i-iii entry above ends by saying the project's planning-review rule
points at a file that "does not exist from that directory or anywhere on this
machine." **That is wrong, and it is wrong twice over.**
`.claude/rules/sd-planning-adversarial-review.md` links
`../sd-ai-command-pack/planning-adversarial-review.md`, which from
`.claude/rules/` resolves to `.claude/sd-ai-command-pack/planning-adversarial-review.md`.
That file exists, is tracked, and is 4.6K. I resolved the relative link from
the repository root and from `~/.claude`, neither of which is the directory the
link is written from, and then reported the absence as a finding -- twice, the
second time into a journal entry that merged.

The entry above stands as written; this is the correction beside it, per the
supersede convention. What follows is the review it should have carried,
against the artifact set that batch changed (`design.md` R11-D26 and the step 8
entry). The contract's own emphasis is the cross-artifact sweep -- "search for
each value instead of reading the artifacts in sequence: the stale copy is the
one you did not think to open" -- and that is what found all three.

**C-1 (addressed) -- one incident, two different counts.** `bin/sd:323` said
the vacuous-check failure had been "found three times"; `implement.md:2956`
said "four times", describing the same `protected-fields` check in the same
pull request. Neither number could be checked against anything: the record they
both gesture at is the 2026-09-01 entry titled *Two gates that certified
nothing*, which enumerates two, and the third and fourth were being counted by
memory. **A tally nobody can verify is the vacuous form of the failure it
counts**, so both sentences now say "keeps finding" and the number is gone,
with the reason left in `bin/sd` where the next person will meet it.

**C-2 (addressed) -- the 14,000 derivation no longer describes its own code.**
`design.md:1153` itemises `bin/sd, registration slice | 264`. `bin/sd` is
**1,553 lines** at this commit -- close to six times that -- so the table
deriving `13,980 -> cap 14,000` sums line items one of which is short of
reality by more than a thousand lines. Nothing is *broken* -- `bin/` measures
9,574 against the 14,000 cap, and the cap is
enforced by `tests/test_loc_caps.py` from `git ls-files` rather than from that
table -- but a derivation whose inputs have drifted cannot be re-run to check
the number it produced. Corrected beside the table rather than in it: 264 was
true when written and is the measurement 6b-1 landed on.

**C-3 (rebutted) -- the `sd store|issue|config` sub-cap holds, measured.**
Same table, 1,400 lines. Measured from the source rather than assumed: the
config block is 167 lines and the vault-driver-plus-store block is 294, so 461
of 1,400 with `sd issue` and the store write verbs still unwritten. No change.

**Implementation is unblocked.** No concern blocks; the only additional lane
this repository could define, it does not define, so no lane was skipped.

**A fourth, found by review inside this correction.** The first draft of the
paragraph above said 1,548, measured before the same commit added six lines of
docstring to `bin/sd` -- so the note correcting stale figures went stale inside
itself, between measurement and commit. The number is now 1,553 with "at this
commit" beside it and the durable claim stated as a ratio, close to six times
264, because that is the part that stays true while the count moves. **A figure
in prose is a measurement with no owner**; the one that cannot rot is
`tests/test_loc_caps.py`, which enumerates `git ls-files` at every run.

**And the cheap check that would have caught the original error:** resolve a
relative link from the directory the link lives in, not from the one you happen
to be standing in. `ls "$(dirname RULE)/../sd-ai-command-pack/"` answers it in
one command and does not depend on remembering where `.claude` roots.

- [x] 8 (slices i-vi, 2026-09-01/02) / [x] 9 (2026-09-02, below) / [x] 10 (2026-09-02, in slices b-i through b-iv-iv and then the closing slice below) / [x] 11 (collapsed -- see *Step 11 moves nothing, and the row was wrong four ways*)

### The delete column, executed (2026-09-01)

The 2026-09-01 triage produced a per-file disposition -- keep 0, stale-notice
6, delete 19 -- and stopped there, because 7,839 lines of specification is a
content decision for the maintainer rather than a triage's call. The maintainer
took the delete column the same day. This entry records what that cost and the
two places it could not be a straight deletion.

**Eighteen files, 9,324 lines.** Not nineteen. `docs/spec/backend/index.md`
carried a `delete` verdict marked *conditional*, and the condition bound:
`sd-docs-lint` rule 4 requires an `index.md` in any spec directory that still
holds pages, and three of `docs/spec/backend/`'s seven pages are staying. The
triage stated the choice as delete-with-the-directory or
rewrite-down-to-the-survivors, never delete alone. It was rewritten -- from 88
lines to 42, an index of the three survivors plus a record of what left. Its
Scope, Pre-Development Checklist and Quality Check sections went with the pages
they pointed at, rather than standing as instructions a tree cannot follow.
`docs/spec/frontend/` (4 of 4) and `docs/spec/tooling/` (8 of 8) left whole,
index included, exactly as the triage said they could.

**`docs/fleet/README.md` changed job rather than leaving.** It was written on
2026-09-01 to carry a stale notice for two JSON files that cannot hold one.
With both files deleted a notice about them is a tombstone, so it was rewritten
as one: what each file was, why annotate-then-delete happened hours apart, and
where the fuller record lives. It stays at its path because `CONTRIBUTING.md`,
`CHANGELOG.md` and archived work items link into `docs/fleet/`, and a link that
404s teaches nothing.

**The reasoning that lasted a few hours, named rather than buried.** Earlier the
same day the two JSONs were annotated instead of deleted, on the argument that "a
registry nothing reads is a record, and correcting a record in place is how a
repository loses the ability to say what it once believed." That argument was
right about correcting in place and wrong about the cost of keeping: the same
triage had already recorded what both files were, in a table, with line counts
and per-file citation counts. Keeping 4,859 unread lines to preserve a record
that exists in two places is paying storage for the second copy. Git history
holds the first.

**What was deliberately not touched.** The six stale-notice pages keep their
bodies. The triage decided against rewriting them down to their true parts --
that is a content rewrite wearing a triage's clothes, and it destroys the record
of what the machinery was, which is the only thing they are still good for.
`docs/spec/backend/manifest-and-filesystem.md` gained one dated line saying
three of its citations became absent rather than stale the same day, and its
302/377 figure was **left as measured** rather than re-run: a figure in prose is
a measurement with no owner, and re-measuring only moves the date it goes stale.
Its two open questions -- the vestigial `SD-AI-COMMAND-PACK` gitignore markers
it is the sole justification for, and whether its Machine-Scope Installer
section belongs in `docs/spec/` or `docs/work/archive/` -- are still open and
were not resolved by this pass. `docs/review-learnings.md` still cites
`docs/FLEET_ROLLOUT.md` in three entries marked **historical**; they are
quotations from #184 and #188 review comments, true when written, and they stay.

**The recommendation this pass corrected in itself.** The status report that
proposed this work said to "lift out the bash 3.2 gate section and the
planning-review checklist first, because they are live." Both were already
safe: the bash 3.2 gate lives in `docs/spec/backend/quality-guidelines.md` and
the planning-review checklist in `docs/spec/guides/index.md`, and **both pages
are stale-notice, not delete**. The lift-out was work invented by not re-reading
the verdict column before acting on a memory of it. Nothing was lifted, and
nothing needed to be.

**Verified.** `bin/sd-docs-lint` exits 0 -- "rule 4 spec index: checked 2 spec
directory(ies)", down from 4, which is the two directories that left showing up
in the checker's own enumeration rather than in a count I typed. `make check`
exits 0. `git ls-files docs/spec | wc -l` is 7, down from 22. A path-exact grep
for every deleted file across the tree returns hits only from `CHANGELOG.md`,
`docs/work/**`, `docs/review-learnings.md` and the three rewritten pages -- all
history or deliberate.


## Risks (consolidated)

- Step 0 is the largest PR (pure deletion); mitigated by all-remaining-jobs-green check.
- Regrowth: same author, 2,968 commits/60d. Defenses: standing rules, CI LOC caps, no release
  train, r7's measured journal-rebirth checks, per-mechanism deletion criteria.
- Two dashboards during 3c→6b window (parity checklist owns swap date). D14 is decided as (c)
  (R11-D10), so the phone-write regression risk is closed; what replaces it is the narrower risk
  that 6b carries the writes without carrying all three guards, which is why its check asserts
  Host allowlist, token, and CORS absence rather than asserting the endpoints exist.
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

### Step 8-iv built, and the criterion above did not cover all of it (2026-09-01)

**8-iv's stated criterion is narrower than what 8-iv ships.** The criterion
recorded above is the write-through-`sd`, read-bytes-back property and the
list-survives-byte-identical case. Both are met. But `design.md` also assigns
the *declaration-side* tightening to this slice -- "8-iv closes it on the
declaration side ... a tightening of 8-i's validator, landed in 8-iv because
that is when it became falsifiable" -- and no criterion above mentions it, so
the slice could have read satisfied with `validate_kind` untouched. What it
ships: `transitions` and `human-only` are refused at registration on a kind
declaring no `status` field, pinned by
`test_transitions_without_a_status_field_refuses_at_registration` and
`test_human_only_without_a_status_field_refuses_at_registration`.
`initial-status` is deliberately excluded, for the reason `design.md`'s
2026-09-01 correction gives, pinned by
`test_a_statusless_kind_is_still_registerable`. 8-iv also gives `sections.order`
a consequence for the first time -- `validate_sections` never opened the
template, so an order naming headings the template does not render registered
clean; `test_a_template_that_does_not_render_the_declared_order_refuses` closes
it.

**A code change silently invalidated three citations in `design.md`.** Growing
`bin/sd` from 1,553 lines past 2,000 moved `frontmatter()` off 1231, the reader's
`.strip('"')` off 1252, and `status_filter` off 1350. All
three were correct on `main` and all three were wrong on the branch that
changed the file, in the same branch that edits `design.md`. They are corrected
to the post-merge line numbers. The general hazard is unfixed and worth naming:
a `bin/sd:NNNN` citation is invalidated by any insertion above its target, no
gate checks them, and this rollout cites that file 4 times across the task
directory. The cheap enumerating check is the one used to find these -- read
each cited line and confirm it is the thing the prose says it is -- and it
belongs in the planning-review sweep rather than in a reviewer's memory.

*Superseded the same day: `tests/test_doc_citations.py` now runs that check on
every change rather than at planning boundaries only, which is where the hole
was -- a pure code change edits none of the three planning artifacts, so no
sweep fires, and 8-iv was swept only because it happened to edit `design.md`
too.* The rule is adjacency: a citation directly following a backticked symbol
is a claim about that symbol and must find it at the cited line; anything with
prose in between is skipped rather than guessed at. Archived documents and
citations to files that no longer exist are skipped for the same reason -- an
archive is supposed to cite the code as it stood.

**Two more stale citations, in prose this branch never touched.** The gate
found them on its first run. `panelId` was cited at `dashboard/app.js:255` and
is at 450, corrected. `showAlerts` was cited at `dashboard/app.js:265` and no
longer exists at all -- deleted at `56f16c7b`, 6b-5b -- so the line number is
dropped rather than corrected, on the ground that a pointer with nothing to
point at is not a citation. The observation stays as the dated one it was, and
its load-bearing claim, that nothing reads `row.href`, is explicitly marked as
not re-verified against the renderer that replaced `showAlerts`.

One citation the gate deliberately does **not** check is worth recording,
because an earlier draft did check it and was wrong: `bin/sd-status:501-506`
is an accurate pointer to a docstring that does not repeat the key name in the
sentence before it. Taking the nearest backticked symbol within 90 characters
reported it as stale. A gate whose failures need interpreting teaches people to
interpret failures away, so the rule was narrowed until its false-positive
count was zero rather than left wide with an exception list.

**Eight review rounds each found one more value the writer let through, so the
class was enumerated instead of waited on.** Every round of review on this
branch surfaced a different scalar that round-trips through `frontmatter()` and
is read differently -- or not at all -- by a real YAML parser, which matters
because the vault is read by Obsidian too. Rather than converge one round at a
time, 39 values were rendered and handed to PyYAML: 21 did not survive. Five
were hard parse errors -- values opening `- `, `? `, `,`, `]` or `}` produced a
note nothing could read -- and `NEEDS_QUOTING` now quotes those five. `- ` and
`? ` are matched with their following space, separately from the character
class, because `-3` and `?x` are ordinary scalars and quoting a leading dash
outright would turn every negative number in the vault into a string. Across
1,463 vault notes and 7,869 bare values, **zero** change classification under
the new rule: it catches only what was already broken.

The other 16 are type coercions -- `true` reads back as a boolean, `0755` as
493, `12:30` as 750 -- and those are **deliberately left alone**. `sd store
set` takes its value from `argv`, so every value arrives as a string and the
writer has no declared type to consult; quoting would mean guessing. The cost
of guessing is concrete, because a hand-written note in the vault holds bare
`true`, and a quoted `"true"` from `sd` would read as a different type than the
note beside it. Numbers, the case `floor` depends on, are unaffected either
way. `0755` and `12:30` are YAML 1.1 warts and are the two entries worth
revisiting, but Obsidian applies the same warts to a hand-written note.
`test_the_types_a_real_reader_infers_are_left_to_the_corpus_convention` pins
the inventory so that leaving it alone stays a decision rather than decaying
into an oversight.

PyYAML is not a dependency of `sd`, and R11-D27's rejection of taking one for
the write path stands. It is used here as a probe, and the test that uses it
skips where it is absent, standing beside a concrete case that always runs.

*Superseded the same day, before this branch merged: the enumeration above was
not one.* Probing 39 hand-picked values found five parse errors and read as
complete. It was not. A brute force over every string up to length three in the
indicator alphabet found **3,690 broken values out of 24,439** still getting
past the rule that paragraph describes. Three whole shapes were missing:

- A leading `'`, which opens a single-quoted scalar and swallows the rest of
  the block. `"` was refused outright and `'` was never considered beside it.
- A **trailing** colon. The rule matched `:\s`, a colon before a space, so
  `note: See also:` -- an ordinary sentence -- emitted bare and turned the
  value into an unterminated mapping key. This is the likeliest of the three to
  occur in real use, and both hand enumerations missed it.
- An embedded tab, which `render_value` lets past its control-character check
  deliberately and which a plain scalar cannot hold.

`-`, `?` and `=` standing alone were missing too; the rule matched `- ` and
`? ` with their following space and nothing matched the bare character.

The lesson is the reason the brute force is now the test rather than the
scaffolding that produced the fix. Two enumerations written by hand were each
confidently wrong, and the second was written immediately after the first was
caught -- knowing the failure mode did not prevent repeating it.
`test_no_short_value_over_the_yaml_indicators_breaks_a_real_parser` renders the
space and parses each value, so the next hole fails a test without anyone
having had to think of it. It calls `render_value` in process because 24,439
subprocesses would cost minutes; the two end-to-end cases beside it run the
real command.

Corpus collateral was re-measured against the final rule and is still **zero**
of 7,869 bare values across 1,463 notes.

### Step 8-v: the baseline is recorded, and it is deliberately not in this repo (2026-09-02)

`bin/migrate-golden-corpus capture` has run. **782 notes across 14 bases**,
root `d3758e14`, recorded 2026-09-02 -- before any vault move, which is the
whole condition step 11's row places on it. `verify` reports all 782
byte-identical.

**The layout changed after approval, on a fact that was not on the table when
it was given.** The accepted design committed the manifest to
`tests/fixtures/golden-corpus.sha256` as `sha256  relative/path`, sold on
"hashes are reviewable in CI, note bodies never leave the machine". Both
halves were true and both missed the point: **this repository is public, and a
note's path is its title.** Committing that file would have published 782
titles -- `Market Watch/` company names, `TaskNotes/Tasks/` personal task
titles -- permanently, into the history of a public repo.

The second fact is that **CI can never run this check at all.** GitHub Actions
has no access to the vault, so the reviewability the layout was chosen for does
not exist. What committing actually buys is tamper-evidence: proof a baseline
was taken when it says it was and has not been quietly re-captured after a
botched move to make `verify` pass. That needs a hash, not the titles.

So the manifest and the note bodies live at `~/.local/state/sd/golden-corpus/`
(`$SD_GOLDEN_CORPUS` overrides), and what is committed is
`tests/fixtures/golden-corpus.root` -- four lines: capture date, note count,
base count, and one sha256 over the sorted manifest. `verify` authenticates the
local manifest against that root *before* it compares any row, because a
manifest edited to agree with a damaged vault would otherwise make every
comparison pass.

**Checked by enumeration, not by inspection.** Every one of the 782 titles was
taken from the local manifest and searched for across the whole repository
working tree, tracked and untracked. Seven matched, all coincidental generic
words that are also ordinary English in these documents (`Learning`,
`Observability`, `Traversal`, `Baseten`). Exactly one full relative path
appears, at line 2722 of this file, and it predates this step by a month. It
is deliberately not repeated here: naming it again would add a second copy of
the one string this whole layout exists to keep out, and a line number points
at it just as well. 8-v introduces no note title to the repository.

**Two things the base list records that the step-11 row gets wrong.** "Tips" is
`System/Databases/Tips and Tricks`; there is no `Tips`. And `System/Databases/`
holds three bases the per-base list never names -- `Companies`, `Tool Stack`,
`space` -- all three empty today and all three listed anyway, because a move
relocates an empty directory too and its disappearance should be loud. Two
pairs read as duplicates and are not: `Learning` and
`System/Databases/Learning` are different directories, and the second is the
one holding 56 notes under `Books/`, `Courses/` and `YouTube/`.

An earlier count in this session said 446 notes across 10 bases. That was
wrong: it used a top-level glob where the scan is recursive, and it missed
`TaskNotes/` 280 notes in `Archive/`, `Tasks/` and `Views/` along with the 56
under `System/Databases/Learning`. 782 is the measured figure.

The tool is `migrate-`-prefixed and outside the `bin/` line cap because it is
deleted at step 11 with the rest of the migration tooling. All four sabotages
of it are caught: disabling the root check, making the scan non-recursive,
removing the re-capture guard, and skipping a base that stopped existing.

### Step 8-vi, which the plan did not have: `add` could not write a tip (2026-09-02)

Step 9's row asks for `grep -rln pack.py 'System/Scheduled Tasks/'` = **0**.
Step 8 was declared complete on 2026-09-02 and step 10a's manifest merged the
same day. Neither of those was wrong on its own terms, and together they were
not enough: **the `sd store add` step 8 shipped cannot write a tip note**, so
`tips-weekly` could not stop calling `pack.py` and step 9's criterion was
unreachable.

`pack.py tips add` writes two list-valued frontmatter keys (`contexts:` and
`tags:`, each a `  - ` block sequence) and three sections of generated prose
(`## Tip`, `## Score`, `## Provenance`). `sd store add` wrote frontmatter as
flat `field: value` -- `render_value` refuses a newline -- and a body copied
from a static template, with no way to put text in it. The gap was found while
enumerating step 9's call sites, not while reading the plan, which is the
order that keeps finding things in this rollout.

Put to Sven as three options: extend `sd`, add template interpolation, or
relax step 9's criterion so `pack.py` keeps the creator role its own
`tips-weekly/SKILL.md:15` already documents. **He chose extending `sd`**, which
keeps both criteria as written and keeps one writer.

**Standing rule 2 is not touched, and that is the substantive decision here.**
The obvious shape for this was a ninth `kinds.*` key -- `list-fields` -- naming
the fields that hold sequences, and the vocabulary's own comment invites it by
saying a ninth is a decision record. It is not needed, and a worse fit than it
looks:

- On the **write** side the distinction `add` needs is per-invocation, not per
  kind. `--field NAME=VALUE` stays a scalar and a repeat stays the mistake it
  usually is; `--field NAME+=VALUE`, repeated, builds a sequence. Folding every
  duplicate `=` into a list instead would have made `--field score=7 --field
  score=8` a two-item list rather than a typo, and no manifest key can tell
  those apart.
- On the **edit** side a declaration would have protected the wrong set. The
  hazard is `edit_field` replacing `contexts:` and orphaning the `  - ` items
  under it, and the notes at risk are the **244 in the corpus carrying
  `contexts:` and `tags:` today**, which no manifest declares at all. So
  `refuse_list_value` reads the note's own bytes: a key with no inline value
  followed by an indented `- ` is refused, whatever the manifest says.

That second one is R11-D27 reached from the other side. D27 is why the write
path is a line edit rather than a parse-and-rewrite; this is the one case a
line edit gets wrong by itself, and it was reachable before this commit for any
field a manifest declared. Step 10a omitted `contexts` and `tags` from every
`fields` list precisely to stay away from it. With the guard in place they can
be declared.

**Verified by sabotage, three times.** Deleting the `refuse_list_value` call
fails 2 of its 4 cases and leaves the two that pin it as *not* over-broad --
an inline value still edits, and a following key is not read as a
continuation. Forcing `render_field` down its scalar branch fails 2. Making
`fill_sections` return the body unchanged fails 3. Full suite **1035 tests, no
skips**; `make lint` clean including mypy, which caught the one place the
runtime guard was real but the type was not.

One shape is refused that a reader might expect to work: section text carrying
its own `## ` heading. `store_add` compares the template's headings against
`sections.order` *after* the fill, so a smuggled heading would either fail that
comparison with a message blaming the template, or match it and write a note
with the heading twice.

**Three edge cases Copilot found, all real (2026-09-02).** The review carried
zero inline comments and named three shapes in its summary line; each was
probed against the code rather than taken on trust, and each reproduced.

A **YAML comment between a key and its items** bypassed the list guard
entirely. `contexts:` / `# where these came from` / `  - Personal` returned at
the comment, which is not a value, and handed the note to the orphaning edit
the guard exists to prevent. Comments are now skipped exactly as blanks are.

An **indented `   ## Score`** slipped past the smuggled-heading refusal.
CommonMark renders a heading indented by up to three spaces, so it reaches
Obsidian as a heading while `body_headings` -- which reads column 0 by design
-- does not see it. The refusal now matches `^ {0,3}## `; the *finder* still
reads column 0, because widening it would change how existing templates are
compared against `sections.order`.

The **CRLF** case is real in `fill_sections` and **not reachable through the
CLI**, which is worth writing down rather than quietly fixing. `read_template`
opens the template in text mode, so universal newlines have already turned
`\r\n` into `\n` before the fill runs: a CRLF template yields an all-LF note,
not a mixed one. The hardcoded `"\n"` was still wrong -- `edit_field` takes
each line's own ending and this did not -- so it is fixed, and pinned by two
tests that say which is which: one through the CLI asserting the
normalisation, one calling `fill_sections` directly with a `\r` still
attached. Claiming a CLI test had proved the ending logic would have been a
vacuous check with a passing result.

Each fix sabotaged: removing the comment skip, narrowing the heading pattern
back to `startswith`, and restoring the hardcoded `"\n"` each fail exactly one
case. Suite **1039 tests, no skips**; `make lint` clean.

**The template could not say the note's own title (2026-09-02).** Found while
sizing the tip template, the same way the trailing space was: by rendering
what `sd` would write and comparing it against what the base holds, rather
than by reading either.

Every tip carries `# The title` under the frontmatter, written by `pack.py`
from the same string that names the file. `sections.template` is static, so
without a placeholder the template must either omit the H1 -- making every
note `sd` adds differ from the fourteen beside it -- or hardcode one title for
all of them. `--section` cannot help: an H1 is not one of the `## ` sections.

`{{title}}`, and deliberately nothing else. Every other value a note needs is
already a `--field` or a `--section`, and a second engine for rendering notes
is exactly what `sections.template` exists to avoid. A placeholder that is not
`{{title}}` is refused rather than passed through, because `{{titel}}` left in
place ships as literal text into every note written from that template and is
noticed by a reader rather than an author.

**The scan runs before the substitution, and a test caught that it had not.**
Scanning the filled body put the note's own title through the check, so a tip
genuinely called `About {{x}} syntax` was refused -- the name of a note
deciding whether the note could exist. The test was written from the property
rather than from the implementation, which is why it failed on first run
instead of passing vacuously.

Sabotaged both ways: removing the substitution fails 2 cases, removing the
stray-placeholder guard fails 1. Suite **1045 tests, no skips**.

### Step 11 moves nothing, and the row was wrong four ways (2026-09-02)

The per-base list the row asks for was enumerated from the filesystem and put
to Sven. **Both of its live dispositions came back reversed**, which leaves
step 11 with nothing to do. The enumeration also found that three of the row's
remaining claims were false. Recording all four, because the row read as a
checked plan and was not one.

**Fourteen bases, 784 notes** at enumeration -- two above the 782 the step 8-v
baseline recorded, both written by routines the same morning.

**1. `Followups` is not empty, and retiring it would have been the largest
change in the step.** The row calls it "empty Followups → retire". It holds a
MOC note, six Obsidian `.base` view files, and a `space/def.json`. **283 notes
reference `Followup - `**, among them `Vault.md`, `VAULT-STRUCTURE.md`,
`WIKILINKS.md` and the vault's own `CLAUDE.md`. The MOC states the design
outright: a follow-up note lives anywhere in the vault and joins a queue by
pointing `related` at one of those views. Retiring the folder deletes six live
queries that 283 notes depend on. *Decision: keep, untouched.*

**2. `Skill Proposals → files store` names a driver that does not exist.**
`DRIVERS = frozenset({"vault"})` -- `vault` is the only one. The underlying
R2-D12 line reads "Skill Proposals → files, rest keep", meaning out of the
vault into plain files, with no destination or format ever specified. The
queue is also dead: 10 notes, **8 `declined` and 2 `filed`**, nothing creates
them and no routine sets their status. *Decision: leave them in the vault.*
Moving ten dead notes buys nothing and spends the only irreversible action the
step had.

**3. The acceptance criterion cannot be met by any vault that is in use.** It
asks for the golden-corpus byte-compare "green". Run on the day it was
written, against a vault nobody had migrated:

    1 changed, 0 missing, 2 unrecorded of 782 recorded notes

-- today's intel brief, a new blog idea, and a `TaskNotes` edit, all written
by routines, and `verify` exits 0 regardless. "Green" was never going to mean
782 identical. The signal a bad move actually produces is **`missing`**: a
note that was recorded and is now gone. Had step 11 moved anything, the
criterion would have been 0 missing plus 0 changed among the moved bases, not
0 changed overall.

**4. `bin/migrate-vault` was never written.** The row says "then delete
`migrate-vault`" and makes it the enforcer of "refuses if any reader still
points at the old path"; step 7's row says it "survives to step 11". It is not in
the tree, and `git log --all -- bin/migrate-vault` prints nothing in this
clone -- which is the verifiable claim, rather than one about every branch
that has ever existed anywhere. Three documents named it as shipped, and one
of them made it responsible for the step's safety. All three are corrected in
this commit: the step 7 row, `design.md`'s CLI inventory, and `CHANGELOG.md`.

**What is left of step 11.** Nothing to move, nothing to build, nothing to
delete. `bin/migrate-golden-corpus` is the open question rather than a
decision taken here: it carries the `migrate-` prefix, which step 7 defined as
tooling deleted at step 11, and the baseline it maintains was captured to
guard a move that will not happen. It does still detect vault drift. That is
the same "a registry nothing reads is a record" argument this repository
already rejected once, at `docs/fleet/README.md:34`, so it should be answered
deliberately and not by leaving the file in place. *(Answered 2026-09-02:
kept through 10b as a bracket, deleted when 10b lands. See "`migrate-golden-corpus`
answered" at the end of this file.)*

### `migrate-golden-corpus` answered, 2026-09-02

Step 11's record left this open and said it "should be answered deliberately
and not by leaving the file in place". Answered here: **kept through step 10b,
used as a bracket, deleted when 10b lands.**

**What it detects.** Whole-note sha256 across 782 notes in 14 bases, reported
in three classes -- `changed`, `missing`, `unrecorded`. Re-run 2026-09-02
07:56 against a baseline captured 04:27, three and a half hours earlier, with
nothing migrated in between:

    1 changed, 0 missing, 2 unrecorded of 782 recorded notes

The overnight daily brief, an ideate run's new blog idea, and a `TaskNotes`
edit. All three legitimate. That is the noise floor of a live vault, and it
rises with the age of the baseline.

**Why "drift detector" was the wrong frame for it.** Two of the three classes
are noise against a vault that launchd routines write to on schedule; only `missing`
still means something a day later. Kept as a standing baseline the tool
reports normal activity as drift, and a check whose output its reader learns
to skip is worse than no check -- the same argument this repository already
used to reject keeping a registry, at `docs/fleet/README.md:34`.

**Why it is not deleted now.** Step 10b retargets the vault-facing half of
`pack.py` at `sd`, which puts a **second writer** on those notes for the first
time. A retargeted verb that resolves the wrong base path, or a `sd store set`
line edit that orphans a list continuation, changes bytes nothing should have
touched -- and R11-D27's whole lesson is that such a note still parses, so
nothing else downstream complains. Captured immediately before a retarget and
verified immediately after, the noise window is minutes rather than a day, so
`changed` becomes as readable as `missing`. That is the bracket, and it is the
only use the tool has left.

**What it does not do**, and no document should claim it does: it is not a
check that `sd` writes what `pack.py` wrote. It snapshots one vault; it does
not compare two writers. That comparison is the same note written both ways
into a scratch vault and diffed, which is what 8-vi did by hand three times.

**Cost of keeping it.** 6.3 MB of bodies and manifest under
`~/.local/state/sd/golden-corpus/`, outside the repository; 360 lines in
`bin/` plus `tests/test_migrate_golden_corpus.py`; both outside the `bin/` cap
under the `migrate-*` allowance, which is now 360 of 1,500 with
`migrate-trellis` gone.

**What this corrects.** Step 7 defined the `migrate-` prefix as tooling
deleted at step 7 or 11, and three documents still scheduled this file by that
rule after step 11 collapsed. The tool's own module docstring was the worst of
them -- written entirely around step 11 relocating live bases, and the first
thing a 10b run would read. All three are corrected in this commit: the
docstring, `design.md`'s cap paragraph, and `prd.md`'s steps 8-11 acceptance
clause.

### Step 9: the vault's routines call `sd`, and the `pack.py` grant is gone (2026-09-02)

Step 9 was "retarget the vault's scheduled routines off `pack.py`". Seventeen
lines across six files named `pack.py`; **six of them were commands a routine
issues** and one was the Bash grant that let them run. The rest was prose about
who writes what, which is the part that goes stale silently.

**The six commands, and what replaced each.** Two sit in fenced blocks; the
other four are inline in a sentence, which is why a scope built from "the code
blocks" would have found a third of the work.

| Where | Was | Is |
| --- | --- | --- |
| `intel-brief/SKILL.md:23` (fenced) | `pack.py topics list --status active --full` | `sd store list sdw.topic --status active --full` |
| `intel-weekly/SKILL.md:162` | same | same |
| `tips-weekly/SKILL.md:34` | same | same |
| `tips-weekly/SKILL.md:38` | `pack.py tips list` | `sd store list sdw.tip` |
| `tips-weekly/SKILL.md:57` (fenced) | `pack.py tips add` (8 flags) | `sd store add sdw.tip` (14) |
| `aaif-brief-compile/SKILL.md:82` | `pack.py config get google_account` | `sd config get sdw.google_account` |

Three further mentions in `tips-accept/SKILL.md` (:161, :221, :225) name the
writer rather than issue a command, and were retargeted with it. Two more there
named `pack.py tips attach`, which **does** exist -- `scripts/pack.py:520`, with
its parser at `:2376`, contrary to a mid-session note that called it
prose-only. It has no `sd` equivalent, so those two now name the *action* and
not the tool: "attachment takes the `## Tip` section and ships it verbatim" is
true whichever binary performs it, and survives 10b's port unchanged.

Each read verb was run against the live vault before its SKILL.md was touched:
`config get` returns the account, `store list sdw.tip` reports 14 notes,
`store list sdw.topic --status active --full` reports 9. `store add` was proved
in a scratch vault rather than the real one, against the real
`sd-writing-pack/sd-plugin.json`, and its output diffed against a
`pack.py`-written tip: identical structure, **offset by exactly one line**, the
empty `acted-on:` key that `sd` writes because the kind declares it and
`pack.py` does not.

**The block grew from eight flags to fourteen, and that is the honest cost.**
`pack.py tips add` filled in `contexts`, `area`, `content-type`, `dateCreated`
and four `tags` from inside the function. `sd store add` writes what it is
given and nothing else, so those defaults are now typed in the skill. Two
things had to be said in prose that the function used to enforce: the date must
be a literal `YYYY-MM-DD`, because `$(date +%F)` is a command substitution and
a prefix grant does not match one -- a Sunday 07:00 run that stops for a
permission prompt produced nothing; and a backtick in the tip text is a
substitution too, which silently deletes the words inside it from a note that
ships verbatim under Sven's name.

**`sdw-tips` did not move, and saying so was the point.** `tips-weekly`'s
opening paragraph claimed both paths "write identical notes because both go
through `pack.py tips add`". Retargeting one half made that false. The blocker
is real rather than clerical: `sdw-tips` passes the tip text as `--tip-file`
precisely to escape the backtick problem above, and **`sd store add` has no
`--section-file` twin** -- `grep -n 'section-file\|field-file' bin/sd` returns
nothing. *(Superseded the same day by* Step 10b-i, *below: the grep now returns
the two flags, and the split it describes now waits only on the retarget.)* Moving it inline would reintroduce the loss that flag exists to
prevent. So the paragraph now states the split, names the one-key difference in
the output, and points at 10b. **Step 10b needs `--section-file` / `--field-file`
before `sdw-tips` can move**, on top of the section-editing verbs already
recorded there.

**Five reference documents asserted things step 9 made false**, and none of
them is a caller: `System/Schema.md` twice (that `pack.py topics list` "is what
a routine calls at the start of a run", and that the non-drifting parts "live
in `pack.py tips add`"), `CLAUDE.md`'s repo table, `TAGS.md`'s two-path
paragraph, and `VAULT-STRUCTURE.md`'s grant paragraph. Each is corrected with a
dated note rather than a rewrite. Finding them took a vault-wide `grep -rIl`,
not a look at the directory being edited -- the six files step 9 scoped were
the six with *invocations*, and the inventory of files with *claims* is a
different and larger set.

**The grant, removed last.** `Bash(python3 .../pack.py *)` came out of
`.claude/settings.json` only after every caller had moved, and
`System/Scheduled Tasks/settings.vault.json` was refreshed in the same pass so
the mirror does not sit a day stale waiting for `vault-cleanup`. Four grants
before, four after; `Bash(/Users/sven/repos/platypeeps/sd-ai-command-pack/bin/sd:*)`
replaced it rather than joining it. The new grant matches on an absolute path
because **`sd` is not on `PATH`** -- `which sd` finds nothing -- which is why
every retargeted call, including the ones inside prose sentences, spells the
path out in full.

**Criterion, and where it does not read zero.** The step's check was
`grep -rln pack.py "System/Scheduled Tasks/"` = 0. Invocations are 0 and grants
are 0, both verified. The grep is 1: `tips-weekly/SKILL.md` still names the old
grant string in the sentence explaining what replaced it. That line is worth
more than a clean grep, so it stays and the gap is named here instead of being
edited away.


### Step 10b-i: the two flags `sdw-tips` cannot move without (2026-09-02)

Step 9 moved all six of the vault's `pack.py` invocations and left one caller
standing outside it: `sdw-tips`, which lives in the plugin repository rather
than in the vault. The blocker it named was one missing flag -- `sdw-tips`
passes its tip text as `--tip-file` so a backtick in the prose is not run by
the shell, and `sd store add` had no twin for it. This adds the twin -- `--field-file
NAME=PATH` and `--section-file NAME=PATH` -- and nothing else.

**Why it is a slice on its own.** The rest of 10b writes to the live vault and
to the sibling plugin, which is what the `migrate-golden-corpus` bracket exists
for. This touches neither: 107 added lines in `bin/sd` (111 changed) and 167
of tests, no note changes bytes, and no bracket is needed to say so. Landing it first also
means the flags are proven before the retarget depends on them, rather than
during it.

**One list, in the order it was typed.** `--field` and `--field-file`
accumulate into the same destination through one `argparse.Action`, rather than
into two `append` lists merged afterwards. With two lists, `--field tags+=a
--field-file tags+=b --field tags+=c` writes a, c, b -- the order of a block
sequence would depend on which spelling supplied each item rather than on where
it was typed. A note's tag order is visible in its frontmatter and
`migrate-golden-corpus` compares whole notes, so that reordering would surface
during the 10b bracket as drift with no author, which is precisely the reading
the bracket is meant to make possible.

**The pair is re-spelled, not split.** A `--field-file score=PATH` becomes
`score=<the file's text>` and goes through `parse_assignments`; a
`--section-file` pair goes through `parse_sections` the same way. So a
file-supplied value meets the refusals the inline spelling meets -- a smuggled
`## ` heading, a field the kind does not declare, a `+=` on a field something
compares as a scalar -- instead of reaching the write down a second, laxer
path. It is safe because a field or section name holds neither `=` nor `+` and
both parsers partition on the *first* separator: a file whose text is literally
`score=9 and tags+=x` lands whole, and there is a test that says so.

**The file is not opened inside the argparse action, and that is an exit
code.** `Refusal` is 1 and a usage error is 2; anything raised inside an action
reaches the user as an argparse error, so reading there would have made a
missing file exit 2. The action records which spelling matched and the handler
does the reading, which keeps `interface = 1`'s promise about exit codes intact
-- a missing or unreadable file is 1, a pair with no separator in it is 2.

**`.strip()` and the empty refusal are the incumbent's**
(`resolve_text_pairs`, `sd-writing-pack/scripts/pack.py:2226`), kept rather than
reconsidered. Both writers are live until 10b lands and the notes they write
have to stay identical while that is true; a difference in trailing-newline
handling would show up as exactly the whole-note drift the bracket reports.

**No decision record.** These are CLI spellings, not a ninth `kinds.*` key, and
`parse_assignments` already recorded that reasoning when `+=` was added.
Standing rule 2 stays where it is.

**What deliberately did not move.** `sd store set` takes its value
positionally and gets no file twin here -- the section-editing verbs and
whatever they need are 10b's, and a half-present flag reads in review as a
supported one, so there is a test asserting the flags are on `add` only. And
`sdw-tips` itself has not moved: that is a plugin and vault change, and it is
bracketed.

**The test suite passed and would have failed CI.** Three of the new cases
spelled a backslash inside an f-string expression, which is Python 3.12
syntax; the local interpreter is 3.14, so `pytest` was green while the 3.10 leg
of the matrix (`.github/workflows/tests.yml`) could not have imported the
module at all. `ruff` caught it -- `invalid-syntax: Cannot use an escape
sequence (backslash) in f-strings on Python 3.10`. Worth recording because the
green suite was not evidence of anything here: **a test run on one interpreter
says nothing about the floor of the matrix**. And `ruff` was the only check
that could have caught it: `mypy` pins 3.10 explicitly in `pyproject.toml`,
but `make -s lint-mypy-paths` lists eighteen paths under `bin/` and
`dashboard/` and no `tests`, where `make -s lint-ruff-paths` ends in `tests`.
The one linter whose scope includes the test suite is the one that reads
`requires-python`.

**And it happened a second time, one push later, in the same test.** The
backtick case runs its text through a real `/bin/sh` to show what the inline
spelling loses, and asserted the shell exits 0 with the words gone. That is
bash's behaviour, and `/bin/sh` is bash on macOS. On the CI runners it is
dash, which does not run `Bash(sd:*)` as a substitution at all -- it refuses to
parse it: `/bin/sh: 1: Syntax error: word unexpected (expecting ")")`, exit 2,
empty stdout. Both matrix legs failed on the assertion, not on the code under
test.

The fix is not a second branch for dash. **Asserting the shape of one shell's
failure was the error; the portable claim is that no shell hands the text
back intact**, so the case now asserts that stdout is neither the text nor
contains the backticked words, which both shells satisfy for their own
reasons. Recorded next to the f-string finding because they are one lesson
twice: this developer's machine is a single point in a matrix, and an
assertion pinned to what it happens to do there is a test of the machine.

**Copilot's review: one finding valid, one not found.** It flagged two things
in its summary and left no inline comment on either. *Valid:* `--field-file`'s
help said "the same, with the value read from a file" and never mentioned that
`NAME+=PATH` appends to a list, which it does and which a test exercises -- so
`--field` documented the `+=` spelling and its file twin hid it. Corrected, and
`--section-file`'s help now names its reason rather than pointing at the flag
above it. *Not found:* "a truncated refusal message". Every message this adds
renders whole -- checked by reading all three and running the two that a
fixture can reach. The nearest thing to the claim is that `--field-file score=`
refused with "names no file", which is terse rather than truncated; it now says
"no path after the separator" and has a case of its own, because the branch had
none. A finding taken as far as the evidence supports, and no further.

**The second review found the same nit twice over, and one of them was mine.**
Its headline repeated "a user-facing refusal message that is visibly
truncated/incomplete" with, again, no located instance; its one concrete
comment was a grammar note on a test docstring. The truncation claim is
rebutted with the rendering rather than with a reading this time -- all five
messages the change adds, put through `resolve_pair_files` directly:
`--field-file score: no path after the separator` · `--field-file score:
cannot read /nope/x: [Errno 2] No such file or directory: '/nope/x'` ·
`--field-file score: /tmp/_sd_empty.txt is empty; a note written from it would
be too` · `'score' is not name=path or name+=path` · `'Tip' is not name=path`.
Every one is a whole sentence. **The grammar note, though, sat on top of a real
defect it did not mention:** the same docstring said step 9 retargeted "five of
the vault's six" invocations and left `sdw-tips`, which is the error this
entry's own opening paragraph was corrected for two commits earlier --
`sdw-tips` is not one of the vault's six, it is in the plugin repository. Fixed
in one artifact and left standing in its copy, which is precisely the shape the
cross-artifact sweep predicts and the reason it is run by searching for the
value rather than by rereading the file that was edited.

**Criterion, and the result.** The check named before the work was
`python3 -m pytest tests/test_sd_store.py` with the new cases passing and no
existing case failing, plus `ruff` and `mypy` as CI runs them. Full suite:
`1067 passed, 5 skipped, 848 subtests passed`. `ruff check` on the two changed
files: `All checks passed!`. `mypy` over `make -s lint-mypy-paths`:
`Success: no issues found in 30 source files`.

**No figure in `design.md` is edited, and that is the disposition rather than
an omission.** `bin/sd` is 2,550 lines at this commit and `bin/` measures
10,571 against the 14,000 cap. The `sd store|issue|config` slice grew by that
same 111, and this deliberately does not turn that into a total: the sub-cap
paragraph's 461 was measured on 2026-09-01, before 8-iv and two later steps
added to the same slice, so 461 + 111 would be a figure with a superseded
baseline inside it -- the exact shape the sweep that found it is for. Nothing
in the tree enforces that sub-cap in any case. The cap
paragraph there already carries three dated measurements, each bound to its own
commit, and `tests/test_loc_caps.py` enforces the cap from `git ls-files`
rather than from any of them. A fourth append would grow the very list that
paragraph exists to say is not the authority.

**One claim this makes false, named rather than fixed early.**
`System/Scheduled Tasks/tips-weekly/SKILL.md:17` says `sd store add` "has no
`--section-file` twin yet". The vault calls this checkout by absolute path, so
that sentence is true until this merges and false afterwards -- correcting it
before the merge would simply be wrong in the other direction. It is corrected
immediately after, in the same session, and the split it describes still
stands until `sdw-tips` moves.

### Step 10b-ii: the split closes, and step 9's delta was wrong by two (2026-09-02)

`sdw-tips` was the one caller step 9 could not move. 10b-i landed the flag it
was waiting for, so this moves it: the add call to
`sd store add sdw.tip … --section-file Tip=<path>`, and the two read verbs it
uses to gather and dedupe to `sd store list`. Landed as
`sd-writing-pack` #5. Both halves of the two-path tip contract now write
through the same command, which is what the contract has claimed since step 9
and what was not true until today.

**Proved before the skill was edited, not after.** A tip whose text carries
both a backtick and a `$(date)` substitution, written into a scratch vault
against the real `sd-plugin.json`, comes back verbatim. That is the check the
flag exists for, and running it against a scratch vault rather than the live
one is the same choice step 9 made for the same reason.

**Step 9 recorded the delta as "exactly one line" and it is three.** Measured
this time against a `pack.py`-written note in the live vault rather than
recalled: `sd` writes `acted-on:` **and** `url:` -- both declared by the kind,
both omitted by `pack.py` -- and `pack.py` writes `description:` always quoted
where `render_value` quotes only when the value needs it. The `url` line was
not step 9's error: `sd-writing-pack` #4 added that key to the kind after step
9 measured, so the record went stale rather than starting wrong. The quoting
difference is the one step 9 could have caught and did not, because it compared
*structure* and quoting is not structural. **With both paths now on `sd`, all
three are history inside the notes written before today rather than drift
between two live writers**, which is the only reason this does not need fixing.

**The floor stopped being one constant, and that is a real cost of the
migration.** `pack.py` had a single `SCORE_FLOOR = 6` that the tip, blog-idea
and skill-proposal floors all read, so the three could not drift apart. The
manifest declares `"floor": {"score": 6}` once per kind, three times over, and
nothing checks that they agree. This is inherent to a per-kind declaration
rather than a defect in one -- the eight `kinds.*` keys describe what a kind
*is*, and a constant shared across kinds has no home there. Named in the skill
and here rather than papered over; `sd-writing-pack` ships no test harness to
enforce it, and building one for a single shared integer is not worth the
surface.

**What the bracket proves, stated narrowly.** `migrate-golden-corpus verify`
read `784 notes byte-identical to the baseline` before the work and again
after. The corpus records notes under the declared bases, so it does not track
`SKILL.md` or `System/Schema.md` at all: what this run proves is that **no note
was written by accident**, which is the useful half for a slice that was only
ever meant to change prose. It is not evidence about the edit. Saying so
matters because a verify that reports clean over files it never recorded is the
vacuous-check shape this rollout keeps meeting.

**One flag, two answers, because the constraint is the grant.** `sdw-tips` can
use `--section-file`; `tips-weekly` cannot, and its SKILL.md now says why
rather than pointing at a flag it must not call. Reading text from a file means
writing that file first, and the vault's only Bash grant is `bin/sd` itself --
a `Write` at 07:00 on a Sunday stops for a permission prompt nobody is there to
answer, which is the 2026-07-28 failure step 9 already recorded once. The
attended path has a person at the keyboard and the unattended one does not, so
the same tool gets different instructions. Checked against
`.claude/settings.json` before the sentence was written, because the tempting
edit -- "the twin exists, use it" -- would have broken the routine.

**Still on `pack.py` for tips:** `tips attach`, which appends a section to an
existing note and has no `sd` equivalent, and the `gh` verbs. 10b-iii and
10b-iv respectively.

### Step 10b-iii: sections get a writer, and two ways to eat a note (2026-09-02)

`tips attach` was the verb 10b-ii could not move, because `sd store` could
write frontmatter and a whole body and nothing in between. This lands the
missing half as two verbs -- `sd store set-section`, which replaces or creates
one declared H2, and `sd store get --section`, which reads one back. Landed as
#705. Five `pack.py` writers are now expressible in `sd`; the census that
sized them found no writer that reads `frontmatter()` on the note it is about
to edit, which is why a section verb was enough and a parser was not.

**`set-section` is a sibling verb, not a flag on `set`.** `set` takes four
positionals (`kind title field value`) and a section body is not a field value:
it is multi-line, it is addressed by heading rather than by key, and it has a
`--section-file` twin that `set` has no use for. Folding it in would have made
the positional grammar conditional on a flag.

**R11-D27 extends to sections unchanged: edit by the line, never parse and
rewrite.** The frontmatter is carried through the splice as raw lines and is
never handed to `frontmatter()`, which is deliberately lossy -- block sequences
read back as `""` and quoted scalars lose their quotes. Against the real
corpus that is not a hypothetical: **14 of 14 tips carry a block sequence and
10 of 14 carry a quoted scalar**, so a parse-and-rewrite `set-section` would
have damaged every tip in the vault on first use. The tests assert the
frontmatter byte-for-byte rather than field-by-field, because a field
comparison is exactly the check that would pass while the quotes went missing.

**Copilot found two note-corrupting defects, and both were in the same
function.** `note_heading_lines` scans for headings, and a heading it misses
becomes a *second* heading with the same name on the next write.

* **Indentation.** The scanner read column 0; CommonMark allows up to three
  leading spaces and Obsidian renders `   ## Score` as a heading. Proved by
  running both scanners over one note: `fixed scanner sees: ['Tip', 'Score']`
  against `old scanner saw: ['Tip']`. The codebase already knew this -- step
  8-vi taught `parse_sections` to match `^ {0,3}## ` and left a comment saying
  why. The new scanner did not read its own neighbour.
* **Fence run length, which is the worse one.** A fenced block is closed only
  by a run of the same character at least as long as the opener, and the
  scanner was treating any ``` line as a closer. A tip quoting a ``` block
  inside a ```` block therefore looked closed at the wrong line: the scanner
  reported `[(4, 'Tip'), (8, 'Score')]` where line 8 is *inside* the code
  sample and the real `## Score` is at line 11. A `set-section` against that
  note deletes the rest of the sample, its closing fence, the real heading and
  its text in one atomic write. Fixed with a `CODE_FENCE` pattern that keeps
  the opening run and compares length.

Neither was reachable by the tests as written, which is the useful part: both
were found by reading, and both are now regression cases. 35 `SetSectionTests`
cover the pair, including the nested-fence shape above and three indentations.

**A declared-but-absent section reads as empty and exits 0.** That is a
decision, not an oversight. `pack.py topics_add_feed` is two branches -- one
`re.sub` when `## Feeds` exists, a different `re.sub` against a named anchor
when it does not -- and reading absent-as-empty collapses both into one
read-edit-write. It also removes the anchor: `topics_add_feed` dies outright on
a note with no `## Provenance`, because the anchor is how it decides where to
insert. `insertion_point` takes the position from the manifest's
`sections.order` instead, so a note missing the anchor is written correctly
rather than refused, and headings the manifest does not declare are stepped
over rather than treated as the boundary.

**The census also found a live `pack.py` bug, which is not this rollout's to
fix.** `topics_add_feed`'s existing-section branch matches
`^(## Feeds\n(?:.*\n)*?)(\n## )` -- it requires a *following* heading and has no
end-of-file fallback. `## Feeds` is currently never last, so the bug is
unreachable today; if it ever were, the `re.sub` no-ops silently and stderr
still prints the success line. Recorded here because 10b-iv deletes the caller
and the defect goes with it, so filing it separately would be filing a ticket
against code that is scheduled to disappear.

**10b-iv's target is restated to ~2,000 lines, from ~1,250.** `design.md`
carried the lower figure and it was never reachable. Two things were wrong with
it. It counted `gh` and `review adversarial` as deleted, and both still have
live callers, so the deletion 10b-iv can actually make is 519 lines -- 493 of
function bodies plus 26 of argparse wiring -- and `pack.py` lands at 2,013.
Granting that assumption anyway reaches only 1,863, because the floor is not
the verbs: `pieces` is 214 lines addressing git files under
`content/<year>/<slug>/`, which `store.driver = vault` cannot address at all;
`main` is 198 today and 172 once its wiring goes, holding the entire argparse
tree; and 769 beyond that are
imports, constants and module-level code. Measured from the AST rather than
estimated.

*(Superseded at 10b-iv, and again at 10b-iv-iv. The deletion was made and
`pack.py` landed at 1,857 rather than the 2,013 predicted here, then at 1,712
once the `protected-fields` decision freed the last two verbs. `design.md`
carries whatever the current measurement is; this paragraph is kept as what was
believed on the way there, not as facts, and makes no new estimate of its own
-- the figures above are the measured outcomes that replaced the prediction.)*

**The first census of that deletion was wrong twice, both in the same
direction as wanting the number to be small.** It counted function bodies only,
missing 26 lines of argparse wiring, and it counted `vault_title_taken` as
deleted when the surviving `topics_seed` still calls it. The corrected census
closes the cut set under "a survivor calls it" and adds the wiring, which is
the shape any later deletion census here should take: a verb is not deletable
because its name matches a prefix, only because nothing that stays reaches it.

The goal 10b set -- get the vault-facing half of `pack.py` onto `sd` -- is
unaffected; only the number attached to it was wrong.

### Step 10b-iv: the deletion, and the one it could not make (2026-09-02)

Twenty-one `pack.py` invocations across six `sd-writing-pack` skills, two
reference documents and `.gitignore` moved to `sd`; twenty-one `pack.py`
functions went with them; and
`pack.py` fell from 2,532 lines to **1,857** (`sd-writing-pack` #7). Ten places
in the vault's own prose still described the deleted verbs in the present tense
and were corrected in the same pass.

**The number missed the restated target in both directions, which is worth
more than the number.** The section above set ~2,000 and predicted 2,013. The
actual figure is 156 lines lower, and the two errors point opposite ways:

* **Upward.** The 2,013 assumed `ideas add` and `ideas set-published` were
  deleted. They are not (below). Retaining them alone would have landed the
  file higher than predicted.
* **Downward, and further.** The census counted function bodies and argparse
  wiring, which is what the previous correction had just taught it to count. It
  still did not count what a deletion *orphans*: nine module-level constants
  (`TT_DROPDOWN`, `SURFACED_STATUS`, `TOPIC_SURFACED_STATUS`, `RATING_DBS`,
  `DRIVE_DOCS_HEADER`, `CONFIG_PATH`, `CONFIG_KEYS`, `DRIVE_URL`, `DRIVE_ID`)
  and two catalogue blocks in the module docstring that named verbs no longer
  present.

That is the third consecutive census of this same deletion to come out wrong,
and the pattern across all three is the same: each counted the code it could
*see from the verb* and missed the code the verb was the only remaining reason
to keep. A deletion census is a reachability question, not a text-span
question. The check that would have caught all three on the first pass is the
one that was eventually run at the end: delete, then ask the tooling what is
now unreferenced, rather than asking a reading of the source what should be.

#### Two verbs the deletion could not make

`ideas add` and `ideas set-published` both write `url`. `blog-idea` declares
`url` in `protected-fields`, and `sd store` enforces `protected-fields` on
`add` as well as on `set`, so both are refused. Both stay on `pack.py`.

The question underneath is whether `protected-fields` means *never
machine-writable* or *not editable after creation*. `tip` is why 10b-ii never
met it: `tip` protects exactly one field, `my-rating`, which genuinely is the
first thing -- Sven's own signal, which no run may write at any time.

`blog-idea` protects six, and that list is the actual finding, because it
**mixes both categories in one key**: `my-rating` is never machine-writable,
while `url`, `content-type`, `dateCreated`, `brief-item` and `source-brief` are
values a creating run is exactly the right writer for and a later run is not.
`skill-proposal` is mixed the same way. `topic` is not, and the way it differs
is the point: it protects `content-type`, `dateCreated` and `slug`, all three
creation-time, and no `my-rating` at all.

So the four kinds land in three groups, not two -- `tip` protects only the
never-writable field, `topic` protects only creation-time ones, and `blog-idea`
and `skill-proposal` protect both through one key. A rule that reads
`protected-fields` one way serves `tip`; the other way serves `topic`; neither
serves the two in the middle.

So the decision cannot be a single global reading of `protected-fields`. Either
the vocabulary grows a way to say which of the two a field is, or the four
manifests move the creation-time fields out of that key and something else
carries them -- and the second is not free, because nothing else currently
stops a *later* run from rewriting a `dateCreated`.

That is a change to the closed 8-key `kinds.*` vocabulary, so under standing
rule 2 it is a decision record, not a call to be made inside a deletion. It is
not made here.

Two things about the current behaviour belong in that record when it is
written. `sd store add sdw.blog-idea` does not refuse when a protected field is
merely *absent* -- it succeeds and writes `content-type:` and `dateCreated:`
empty, where `pack.py` filled them in. So the protection is loud on the path
nobody takes and silent on the path every caller takes, which is backwards. And
the same rule reaches an *edit* verb, not only creation: `ideas set-published`
is blocked for writing the `url` of a piece that has just gone live, which is
the one moment the value is knowable.

#### What retargeting cost and what it bought

Two of the seven retargets are not one-for-one.

`ideas set-drive-docs` merged a partial set of URLs into whatever the section
already held, and both call sites depend on that merge -- each supplies only
the URLs it has. There is no `sd` verb for "merge into a section", so it became
an explicit read-edit-write: `sd store get --section`, edit, `sd store set
--section-file`.
That is more lines at the call site and the merge is now the skill's
responsibility rather than the tool's. It is the honest shape of what was
always happening.

`tips set-published` went the other way and got smaller. It wrote three fields
in three sequential `pack.py` calls, which could stop after the first and leave
a tip published with no URL -- a state the vault's schema forbids and nothing
enforced. `sd store set` takes all three in one atomic write (#707), so that
state is now unreachable. `sd` is also stricter here than what it replaced: it
refuses to publish a tip that never reached `approved`, which `sdw-publish`'s
own step 1 already required and `pack.py` never checked.

#### A single-writer property genuinely lost

`## Ground truth` and `## Feeds` on a topic note each had exactly one writer:
`topics set-ground-truth` replaced the section wholesale and restamped the
date, and `topics add-feed` / `topics rm-feed` added or removed one
duplicate-checked entry. All three are deleted, and both sections are now
edited through the generic `sd store set-section`.

`sd` keeps the structural half of what they guaranteed -- it refuses an
undeclared heading, refuses a note whose heading appears twice, and edits by
the line rather than by parse-and-rewrite. It cannot keep the shape *inside*
the section: the ground-truth date stamp with its re-verification caveat, and
the one-entry-per-line duplicate check on feeds. Those lived in the deleted
functions.

This is written into `System/Schema.md` as a loss rather than smoothed into a
rename, because `## Ground truth` going quietly stale is precisely the failure
the stamp existed to make visible, and a routine that inherits the section
without inheriting the caveat will not know it was ever promised.

#### The blast-radius grep found what the work missed

The check named before the deletion was a repo-and-vault-wide grep for
`pack.py <deleted verb>`, expecting only past-tense prose. It found two live
sites the retargeting pass had missed -- `sdw-ideate/SKILL.md:50`, a
`topics list` inside a bullet rather than in a fenced block, and the
`.gitignore` comment describing `scripts/config.json` as written by
`pack.py config set`. Both were fixed before the commit.

It also found that `scripts/config.example.json` documented the shape of a file
nothing reads any more; it is deleted. `scripts/config.json` stays ignored so a
leftover copy on an existing checkout is never committed, and all three of its
values were verified byte-identical to `sd`'s config store *before* anything
was deleted.

Verified: no new ruff finding (rule-code counts identical except `ISC004`
2 -> 1; no `F401`, no `F821`); every surviving subcommand group parses and
`pieces list` still returns its ten pieces; each deleted verb exits non-zero;
and `migrate-golden-corpus verify` still reports `784 notes byte-identical to
the baseline`.

#### The deletion had a gap, and the check that cleared it could not see it

`sd-writing-pack` #8, immediately after. `vault set-score` moved a note's
`score` field and its `## Score` body together, and its `RATING_DBS` named
three databases:

```python
RATING_DBS = {"blog-ideas": BI_DB, "skill-proposals": SP_DB, "tips": TT_DB}
```

For `blog-ideas` and `tips` the replacement was already standing when the verb
was deleted: both kinds declare `sections`, so
`sd store set --field score=N --section 'Score=...'` is the same work in one
atomic write. `skill-proposal` declared none -- 10b-iv-ii had added `sections`
to `blog-idea` and `topic` and stopped there, because those were the two kinds
the retargeting needed. So for that one database the capability was **deleted
rather than moved**, and stayed that way until #8 declared `sections` for it.

The verification above is not wrong; it is answering a narrower question than
it appears to. "Each deleted verb exits non-zero" and "no live caller" are both
true and neither one asks *whether the thing the verb did is still possible*. A
deletion is safe when every capability it removes has somewhere to land, and
call-site enumeration cannot establish that -- a capability with no caller
today is exactly the case where the grep says yes and the answer is no.

The check that would have caught it is cheap and is worth naming for the
remaining steps: for each verb being deleted, name the `sd` invocation that
replaces it and **run that invocation** against the kinds it applied to. Three
of `set-score`'s databases, three runs, one of which would have refused with
`the kind 'sdw.skill-proposal' declares no sections to edit`.

Same shape as the census errors above, one level up. Those counted the code
they could see from the verb; this counted the callers it could see from the
verb. Neither asked what the verb was for.

#8 also confirmed the `protected-fields` finding on a third kind:
`sd store add sdw.skill-proposal` writes `content-type:` and `dateCreated:`
empty. `skill-proposal` protects four fields and only `my-rating` is genuinely
never-machine-writable, so it joins `blog-idea` as the second of the four kinds
mixing both meanings in one key -- which, with `tip` and `topic` sitting at
either pure extreme, is the evidence the open decision needs.

### Step 10b-iv-iv: `protected-fields` decided, and the last two verbs moved (2026-09-02)

`sd-writing-pack` #9. `protected-fields` now declares `my-rating` and nothing
else, `ideas add` and `ideas set-published` are gone, and `pack.py` is 1,712
lines. This is the decision record standing rule 2 asked for -- and the answer
is that no vocabulary change is needed, which is why it can live here rather
than as a change to the eight keys.

#### The key was carrying two meanings

`my-rating` is never machine-writable. `System/Schema.md` states that more
plainly than any other rule in the vault: *"No routine may ever write, edit, or
clear a `my-rating`"*, because a default would destroy the distinction between
"I read this and it was a 3" and "nobody has looked". Everything else in the
key was creation-time data -- a value a creating run is the right writer for
and a later run is not.

**The corpus decided it, not the argument.** Across all 207 notes in the four
databases, `content-type` equals the kind name 207 times with no exceptions and
`dateCreated` is set 207 times. Neither is caller data at all: one is the
kind's own name, the other is the day the note was made. `slug` differs from
the filename in 4 of 11 topics, so that one *is* data. Two of the four disputed
fields turned out not to be a policy question, and the tension mostly went with
them.

So: `protected-fields` holds `my-rating`, omitted entirely for `topic`, which
declares no `my-rating`. The validator requires a non-empty list when the key
is present, and `if key in kind` makes omission the supported way to say none.

#### Why this reading and not the other

It fixes the silent empty-write **by construction**. `store_add` iterates the
fields it was given when refusing, then writes every declared field with absent
ones as `""`, so a protected field could neither be supplied nor omitted
correctly. The only field still protected is the one whose empty value is
*meaningful*, so absent now means the right thing rather than the wrong one.

`floor` had already found and fixed this exact bug inside the same function.
`refuse_protected` (`bin/sd:2339`) loops over the fields the *caller supplied*.
`refuse_below_floor` (`bin/sd:2361`) loops over the fields the *kind declares*,
twenty-two lines below it, under a comment saying in as many words why the
first shape is wrong -- iterating the supplied values let a floor be skipped by
omitting the field.

Two loops, two different key sets, close enough to read in a single screen: one
of them had already been corrected and the other had not. The same lesson
reached `protected-fields` by removing the fields that made it necessary rather
than by adding a second loop.

One meaning also means the key reads the same on `add` and `set`, so no
verb-scoping rule is needed; and none of it touches the eight-key vocabulary.
Nothing is given up, either: `pack.py` wrote `url`, `dateCreated` and
`content-type` freely, so the exposure is unchanged rather than new.

**Rejected:** *not editable after creation* -- allow on `add`, refuse on `set`.
It would let a creating run write `my-rating: 7`. That one reading cannot cover
both fields is the whole finding.

**Deferred, not rejected:** a ninth key so the store derives `content-type`
(it knows the kind) and `dateCreated` (it knows the date). That is the better
end state and it removes two flags from every caller. It is worth opening the
closed vocabulary for once there is a second reason to, and one reason is not
enough.

#### What the move cost, and what it caught

`sdw-ideate` now spells out every default `ideas add` supplied, with
`$(date +%F)` in place of `today()`. One thing had to *move* rather than be
translated: `pack.py`'s floor refusal printed a warning that re-running with an
inflated score is the one failure the floor cannot survive, and `sd`'s refusal
is terse. The warning now lives in the skill beside the call. That is the third
leg of the tool-swap rule -- what it is called, what authorizes it, and what it
can *do* -- and what a tool stops saying is part of the third.

`sdw-publish` gets stricter for free. `ideas set-published` did a blind
`re.sub` and would publish an idea straight out of `inbox`. `sd store set`
walks the transition graph, where only `drafting` reaches `published` and
`accepted` is `human-only` besides.

Eight orphans went with the two functions, and **four were left behind by #7**:
`SP_DB`, `db_rows`, `db_show`, `topic_path`. That sweep enumerated orphaned
*constants* and never asked the same question about *functions*. Third instance
of this shape in the rollout, after the two census errors above, so the sweep
here closes over both kinds of definition and repeats until it reaches a fixed
point instead of running once. `remaining orphans: none` is the output that
ends it, and that is the form the check should take from here on: not a list of
what to look for, but a loop that stops when it finds nothing.

The fixed-point sweep still missed a whole category, because it enumerated
*definitions*. Three comment blocks in `pack.py` outlived the code they
described, and no orphan check can see them: the floor block and the
`my-rating` naming block had no code under them at all after #7 and #9 --
they sat between two unrelated constants, describing `SCORE_FLOOR` and a
creation path that no longer existed -- and the `tips` header block still
said the floor came from "the same constant", when there is no constant and
the value is declared per kind in `sd-plugin.json`. Copilot found the first
one; enumerating the others took grepping the *claims* (`enforced here`,
`Same constant`, `SCORE_FLOOR`) rather than the symbols.

That is the same third leg again, one level up. Deleting a verb changes what
the file *does* and what it *says it does*, and a Python orphan sweep is
blind to the second by construction: a comment references nothing, so
nothing can be found dangling. The check that catches it is a grep for the
claim, and the claim has to be written down before the deletion to be
grepped for after it. Two more of these turned up in the same pass --
`topics seed`'s docstring and its refusal text both still directed the
reader to `topics add`, deleted at 10b-iv -- and the corrected comments now
name where each rule is enforced instead of implying `pack.py` still holds
it. The final measured floor is **1,712** lines, nine below the figure
taken before the comments were swept.

### Step 10 closes: the last two vault reads, and a bug the check found (2026-09-02)

`sd-writing-pack` #10. The step's own check is `grep -c -e BI_DB -e SP_DB -e
TT_DB -e TP_DB -e VAULT pack.py` = 0, and three things stood between 10b-iv-iv
and that number.

`tips attach` and `tips render` opened a tip note by path. They read one
through `sd store get --json` now, which returns frontmatter and body in a
single call -- so the status gate and the `## Tip` section come from one read
of one version of the note rather than two reads that could disagree. That was
not the reason for the change, but it is the reason the shape is a single
`sd_note()` rather than two calls.

`topics seed` was deleted. It refused to run against a database holding
anything at all, and Topics has held eleven notes for weeks, so it had been
unreachable from the moment it ran. 10b-iv's lesson -- *"no caller today" is
not "no capability needed"* -- is the check that applies, and it passes for a
different reason than usual: the capability is not needed *because it is
spent*, not because something replaced it. Nothing writes `active` now, which
is what the vault's `Schema.md` already described as correct.

The vault root went with them. It had been an absolute path to one machine's
home; `sd-plugin.json`'s `store.root` holds it as `$OBSIDIAN_VAULT`.

#### The check the step wrote returns 1, and the honest answer is to say so

`grep -c ... -e VAULT` is a substring match, and the file now carries
`$OBSIDIAN_VAULT` in a comment explaining where the root went. The literal
form of the step's own check therefore reports 1 rather than 0. Rewording that
comment to make the number come out right would be choosing the check after
the fact -- so the record carries all three readings: literal 1, `grep -cw` 0,
and 0 again with comments and strings stripped before counting. The one hit is
the replacement, not a residue.

#### `tips render` had been broken on seven of ten pieces

The step's second check is "E2E on one piece", and the first piece failed. Not
because of anything this slice changed: `frontmatter()` never stripped trailing
YAML comments, and the piece template writes

```
tip: null            # vault Tips and Tricks note title; set by sdw-publish
```

so the value read back as that whole string. It is not `null`, so `tips
render` sailed past its own "no tip attached" guard and went looking for a
note by that name. Seven of the ten pieces in `content/` carry that default.
The only supported way to build `publish/mezmo.md` -- a function whose own
docstring says the hand-rolled pipeline it replaced left this repo with a
paste target 83 lines behind its draft for a day -- failed on all seven.

Reproduced on the unmodified file before touching it, which is the step that
separates "my change broke this" from "my check found this".

Two more shapes of the same bug came out of review, and the pattern in how
they were found is the point. Round one fixed `\s+#`. Round two found that a
mapping header (`published_urls:      # filled by ...`) has no whitespace left
before the `#` after `key:\s*` consumes it, so both `_urls` keys read back as
their own comments. Round three found that single-quoted scalars need `''`
unescaped. The first two checks tested the shapes I had thought of. The check
that actually closed it ran `frontmatter()` over all ten pieces and printed
every key's distinct values, then asserted none still contains a `#` --
enumerated from the files rather than from my own list, which is the
difference the verification doctrine names.

#### A fourth orphaned comment block, found the same way as the first three

`# ---- topics ----` and the paragraph under it survived the deletion of
`topics seed`, leaving a section header above `pieces_set_published_url`
claiming "every consumer reads them from here" about code that is no longer
there. Same class as the three in #711, found the same way: by review, not by
a sweep. An orphan sweep enumerates definitions and a comment defines nothing,
so this will keep happening until the sweep greps claims as well as symbols.
Nothing was lost with it -- the history it carried is in the vault's
`Schema.md`, in a fuller form.

#### Ten review rounds, and one position reversed

The review loop ran to ten rounds, most of them hardening the new `sd`
subprocess call against failures the file already handled next door in
`_meter_json` and `_meter_bin`: `X_OK` rather than `isfile`, a timeout, a
guarded `json.loads`, `(stderr or stdout)`, explicit UTF-8, and `realpath`
rather than `abspath` -- the last because the comment claimed `abspath`
resolves symlinks and it does not.

One finding was rebutted and then taken, which is worth recording as a shape.
"Validate the types of `fields` and `body`" was declined: a wrong type there
raises immediately and names the value. It came back as "validate that the
JSON root is an object", and that one went in, because a JSON array makes `k
not in note` test *membership in a list* and `sorted(note)` report elements as
keys -- a wrong answer rather than a noisy one. The distinction the first
rebuttal turned on is exactly what the second finding cleared. Asking twice is
not an argument; having a better argument is.

`pack.py` is **1,590** lines, from 1,712. It was 1,557 before those ten rounds
added the hardening back.

**Not fixed here, and named so it is not rediscovered:**
`content/2026/effort-dial-cost-attribution/publish/mezmo.md` is nineteen lines
behind its draft in git -- the exact drift `tips render` exists to prevent,
surfaced by running the E2E. Regenerating it is a content change and Sven's
call, so the render output was reverted rather than committed.
