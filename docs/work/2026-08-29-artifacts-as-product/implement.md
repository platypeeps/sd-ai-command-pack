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
        atomic on merge. **365 files, 183,494 deletions against 1,343 insertions.**

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
    - Eight of the nine tabs, the `dashboard.d/*.py` plugin contract, and RUN_ALLOWLIST.
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
  - **Vault-side, in one commit** (`b6bd564`, six enumerated paths): `System/Scripts/
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
    `dashboard.py` compiles. In this repository, `ls .github/` is down to
    `scripts/`, `workflows/`, and five files, none of them Trellis.
- [ ] 6 / 6b
- [ ] 7 — tag 1.0.0. Does **not** restore the macOS CI leg: that moved to a
  manual trigger at the end of the rollout (R11-D4 amendment, 2026-08-31),
  so step 7 keeps "verify protection" and nothing else changes here.
- [ ] 8 / 9 / 10 / 11

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
