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
      - [x] the acceptance criterion the wave had *not* met, met 2026-08-30. `prd.md`'s Step 3-c box reads
            "one removal PR per consumer (9); zero trellis/router greps per repo; CI green".
            The first and third held. The second was swept 2026-08-30, after step 3 closed,
            and it does not: the follow-up pass removed *machinery* and left *prose*.

            Machinery is clean. Enumerated from each default branch's tree rather than from
            the merge output, the five retired paths — `.trellis/`, `.sd-ai-command-pack/`,
            `ai-review-router.yml`, `sd-review.yml`, `sd-github-review.json` — appear in zero
            of the nine, except `sd-github-review` itself, which carries the two router
            workflows because they *are* its product and step 4 retires the repository whole.

            Prose is not. Three repositories still ship a spec guide teaching a procedure for
            a framework that no longer exists: `docs/spec/guides/code-reuse-thinking-guide.md`
            carries a `## Template File Registration (Trellis-specific)` section — `trellis
            update`, `src/templates/trellis/index.ts`, an rsync that syncs `.trellis/scripts/`
            against a template copy — and `docs/spec/guides/cross-layer-thinking-guide.md`
            teaches from Trellis command templates, in `hoa-manager`, `people-profiles` and
            `rwbp-coordinator` — byte-identical copies in all three. These are `docs/spec/`,
            the repository's own standing guidance, not archived work items — an agent reading
            them is told to maintain a template tree that was deleted at step 1.

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
