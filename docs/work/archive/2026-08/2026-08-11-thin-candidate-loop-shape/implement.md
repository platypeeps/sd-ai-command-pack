# Implement — rescope the candidate validator loop to the thin shape

Design is `design.md`. D1-D5 answer the PRD's C-1 through C-4; D6 and D7 answer
two defects the planning review found in D5's own first draft. Read it before
editing — three of the four original concerns are dissolved by the shape
decision rather than worked around, so an implementation that reintroduces
`install.py --thin` into the loop is not a variation, it is the rejected design.

## Step 0 — before editing

- [x] `trellis-before-dev`: `.trellis/spec/backend/index.md`, the
      manifest-and-filesystem spec (the candidate-ledger and surface-partition
      sections), and the tooling spec index.
- [x] **Baseline captured before the first code edit** — measured on
      `feat/thin-candidate-loop-shape` at `015903d8` plus planning artifacts,
      with no pack payload modified.

      **`make release-prep`** — exit 0. The candidate line:

      ```text
      release prep: candidate ledger is current; skipping fleet validation
      ```

      The validator therefore does **not** run today on an unchanged payload.
      That is the 0.69.0 behavior working as designed, and it means every
      later gate-2 run must be read against this line: an edit to
      `fleet-candidate-check.py` moves `validatorDigest`, which is what turns
      this skip into a run.

      **`docs/fleet/consumers.json`** — schema 5, eight consumers, exactly one
      distinct key set across all eight:

      ```text
      candidateChecks, candidatePrepare, candidateTimeoutSeconds, github,
      name, pathHint, platforms, rolloutPriority
      ```

      `any('mode' in record)` is `False`. File digest
      `sha256:ab9b5ed56dcd3d25707f4abae77a2f8f6d19dd04fd28b95620458616883a8bb7`
      — this is the byte-identity baseline acceptance criterion 2 compares
      against, and the reason it compares bytes rather than `mode` values.

      **Fresh resweep, `sd-github-review`** (`thin-resweep.py sd-github-review
      --json`, exit 1) — the consumer with the smallest 2026-08-10 blocker
      count, chosen so a re-measure is cheap:

      | field | 2026-08-10 scan | now |
      | --- | --- | --- |
      | `verdict` | `blocked` | `blocked` |
      | `counts.blockers` | 16 | 16 |
      | `counts.packDefects` | 15 | 15 |
      | `counts.advisories` | — | 76 |
      | `missingFiles` | — | 0 |
      | `worktreeClean` | — | `True` |

      `reasons`: `16 consumer reference(s) to removed paths`, `15 pack-owned
      reference(s) to removed paths`. `head 8a5493b4`, `classifierDigest
      sha256:c6ce23fe`.

      The `packDefects` column is **not** stale after all for this consumer —
      `08-10-thin-prompt-surface-repoint` and `08-11-thin-undeclared-codex-marker`
      did not reduce it, so `design.md`'s "must be re-measured, not carried" was
      right to demand the measurement and wrong to predict its result.

      This baseline was then read as meaning D4 would fail release-prep on 15
      pack defects, which produced Step 2b below. That reading was wrong; see
      Step 2b for the correction and what it cost.

## Step 2b — clear the pack-owned defects the policy would fail on

Not in the original plan. The Step 0 baseline forced it: D4 makes
`packDefects > 0` fail release-prep, and a full-fleet resweep at HEAD measured
**130 pack defects across all eight consumers, none at zero**. Shipping D4
without this step turns `make release-prep` red on merge and keeps it red.

Full fleet, measured this run (`thin-resweep.py <name> --json`, all exit 1):

| consumer | verdict | blockers | packDefects | advisories | missing | clean |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `anomaly-metric-creator` | blocked | 207 | 15 | 154 | 0 | no |
| `rwbp-website` | blocked | 68 | 17 | 105 | 0 | yes |
| `loadsmith` | blocked | 56 | 17 | 163 | 0 | no |
| `rwbp-coordinator` | blocked | 52 | 17 | 115 | 0 | yes |
| `mezmo_benchmark` | blocked | 47 | 15 | 97 | 0 | no |
| `hoa-manager` | blocked | 37 | 17 | 127 | 0 | yes |
| `se-ai-command-pack` | blocked | 27 | 17 | 828 | 0 | yes |
| `sd-github-review` | blocked | 16 | 15 | 76 | 0 | yes |

The 130 are not 130 problems. They are **eight pack-owned files**, seven of
them cited by all eight consumers, and within those files a much smaller set of
distinct sentences repeated at shifting line numbers:

| file | consumers | distinct citations |
| --- | ---: | --- |
| `.github/copilot-instructions.md` | 8 | the entry-points sentence, `docs/SD_AI_COMMAND_PACK.md`, the `.agents/` glob line, the `scripts/sd-ai-command-pack-*` line, the install-audit line, the "source-checkout-only" line |
| `.github/prompts/sd-housekeeping.prompt.md` | 8 | step 3's existence check, step 4's `bash scripts/...` invocation |
| `.github/prompts/sd-review-learnings.prompt.md` | 8 | step 2's existence check, step 4's interpreter search |
| `.github/prompts/sd-review.prompt.md` | 8 | step 2's two-script existence check |
| `.github/prompts/sd-status.prompt.md` | 8 | the `toolchain.sh` citation |
| `.gitignore` | 8 | the `# Generated by scripts/...-update-spec-kb.py` banner, ×8 |
| `codex` | 8 | undeclared codex usage in a surviving pack file |
| `.github/PULL_REQUEST_TEMPLATE.md` | 5 | `docs/SD_AI_COMMAND_PACK.md`, `bash scripts/...-full-check.sh` |

**A decision was taken to fix those eight files here, and it was withdrawn
before any of them was edited. The premise was wrong.**

`packDefects` is a **pre-rewrite** count. The resweep records pack-owned
content that *cites* a removed path (`thin-resweep.py:1592-1598`) and never
calls `rewrite_text`. The conversion does: `thin.py:651` runs
`rewrite_text(text, profile=THIN_PROFILE, key=entry)` over every kept text
file, and `THIN_PROFILE` repoints exactly these citations. So a file in that
bucket says nothing about the release until the rewrite has been applied to it.

Measured, after the reading was questioned: `check_text_residue` over all seven
flagged files in this repository, and over the same files in the real
`sd-github-review` checkout, reports **0 files with residue**. Every one of the
130 is repointed by machinery that already exists.

Editing those eight files would have hardcoded `~/.agents/bin` into prose that
fat consumers read — a real regression, shipped to fix an imagined one.

**The fix belongs to the policy, not the files.** `surviving_pack_defects`
(Step 3) rewrites each flagged file under `THIN_PROFILE` and fails only on what
`check_text_residue` still rejects. A glob such as
`scripts/sd-ai-command-pack-*.py` is not a path the rewrite can repoint and
still fails; a plain citation does not. The raw count is recorded as a note so
it stays visible without being a verdict.

- [x] Step 2b is void. No pack file was edited under it. `design.md` D4 is
      amended to the residue rule, and Step 4 holds tests for both halves.
- [x] **Amend `prd.md` before `task.py start`** — done during the planning
      adversarial review; `research/planning-adversarial-review.md` records why.
      Requirement 1's third step, requirement 3's pin-not-mode wording, the two
      stale citations, acceptance criterion 2's byte-identity form, the mixed-pin
      fixture, and new criteria for D6 and D7 all landed. Kept below as the
      record of what was amended:
      - requirement 1's third step is `generate-plugin.py --check`, not the
        `claude --plugin-dir` load smoke, with the measured reason;
      - reconcile the stale line citations — the PRD cites
        `fleet-candidate-check.py:502` and `fleet_lib.py:829`, which moved to
        `:520` and `:902-906` in 0.69.0. Re-derive both from the file rather
        than copying `design.md`'s numbers;
      - acceptance criterion 2 (`prd.md:97`) says "the registry still reading
        eight `fat` entries afterward". No record carries a `mode` key, so as
        written the criterion cannot be ticked. Restate it as byte-identity of
        `docs/fleet/consumers.json`.
      An acceptance criterion naming a step that cannot pass is not tickable,
      so this is a precondition of starting, not a closing task.

## Step 1 — the status contract

Edit **`templates/scripts/sd_ai_command_pack_fleet_lib.py`**, the authoritative
source. Not `scripts/sd_ai_command_pack_fleet_lib.py`, which `make sync`
regenerates from it.

- [x] Bump `CANDIDATE_LEDGER_SCHEMA_VERSION` 3 → 4 (D4).
- [x] Widen `validate_candidate_ledger`'s consumer-status check to accept
      `blocked` **only** with a non-empty `reasons` array, keep rejecting
      `failed` and unknown statuses, and keep rejecting missing/unknown
      consumers. The Wrong/Correct pair is in D4; copy its shape.
- [x] Do not touch `validatorDigest`, `payload_digest`, or
      `candidate_validator_digest`. They shipped in 0.69.0 and this task has no
      quarrel with them.

## Step 2 — the thin artifact lane

Edit `scripts/sd-ai-command-pack-fleet-candidate-check.py` (no template; edited
in place).

- [x] Add the lane from D5, run **once** per candidate run before the
      per-consumer loop, inside the existing `work_root` temporary directory
      (`:480`). **Three** steps, not four: `generate-plugin.py --check --root`
      already builds and compares in one offline invocation, so a separate
      build-into-`<work_root>/pack` step would build the same plugin twice and
      is why the lane needs no scratch copy of the checkout at all. Then
      `claude plugin validate --strict`, then `install.py --machine` into
      `<work_root>/home` with `--state-home <work_root>/state`.
- [x] Do **not** add a `claude --plugin-dir` step. Measured, it exits 0 against
      a nonexistent plugin directory, so it cannot fail; it also needs a
      billable model call, which requirement 5's no-skip rule would then make
      mandatory for every `make release-prep`. D5 records the deviation and
      Step 0 amends the PRD.
- [x] Retain `<work_root>/home` and `<work_root>/state` for Step 3. The machine
      install is the thin lane's `HOME`, not a discarded artifact check.
- [x] Never write to the checkout. `generate-plugin.py --check --root` is
      the seam: it builds in memory and compares against the committed tree,
      writing nothing. A validator that rewrote its own input would repeat D1's
      error one directory over.
- [x] Resolve `claude` once; if it is unresolvable, report the steps as
      `unavailable` and exit nonzero (requirement 5). No skip flag, no
      environment escape, no degrade-to-fat.

## Step 3 — the per-consumer lane

- [x] Resweep the clone **after** the install, not before
      (`resweep_consumer(name, clone)` — it takes an explicit repo, so it reads
      the clone rather than the registered `pathHint`). Classify per D4:
      residue surviving the `THIN_PROFILE` rewrite → `failed`; `blockers` /
      `missingFiles` / dirty → `blocked` with reasons.

      **Corrected from "the pristine clone before any install".** A pristine
      clone carries whatever pack the consumer last installed, so a resweep
      there measures the previous release. Measured: `sd-github-review`'s
      vendored `planning-adversarial-review.md` still invoked the `codex` CLI,
      a defect this pack had already removed, and the candidate was failed for
      it. Installing dirties the tree and a dirty tree is a blocker, so the
      install is committed in the disposable clone first (`git add --all`, then
      a `--allow-empty` commit with an explicit identity). Blocker counts fell
      on five consumers once the ordering was fixed — direct evidence the
      pristine reading was measuring the wrong tree.
- [x] Branch the install on `conversion.thin_pin_state(clone)`, never on the
      registry's declared `mode` (D3). `fat` keeps today's
      `--force --platform ...`; `thin` drops `--platform` entirely; `malformed`
      fails with the pin state named.
- [x] Record a note when the clone's pin and the registry's `mode` disagree.
      It is the documented conversion skew, not an error.
- [x] **D6 — unresolvable thin checks.** Before running a thin clone's
      `candidateChecks`, resolve each command's program argument against the
      clone. Absent **and** manifest-declared is `blocked`, with a reason naming
      the command and the `~/.agents/bin/<name>` form the record should use.
      Absent and not manifest-declared stays `failed`. Two consumers are already
      in this state on paper — `se-ai-command-pack` runs
      `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test` and
      `rwbp-website` runs `node scripts/sd-ai-command-pack-review-preflight.mjs`,
      both manifest-declared. Do not rewrite the registry to fix them; that is
      the consumer's conversion PR.
- [x] **D7 — the thin lane's `HOME`.** Run a thin clone's `candidatePrepare` and
      `candidateChecks` with `HOME=<work_root>/home` and the state home from the
      artifact lane. Leave the fat lane's environment exactly as it is —
      `command_environment` (`:67-84`) must not start overriding `HOME` for
      everyone. Without this, a thin consumer's `~/.agents/bin` lookups resolve
      to whatever pack the invoking machine has installed, and the run certifies
      someone else's release.
- [x] Carry `reasons` into `CandidateResult` and into the ledger row.
- [x] Narrow the `:520` failure gate to "not `passed` **and** not `blocked`", so
      a fleet of blocked consumers still writes a truthful ledger.

## Step 4 — tests

- [x] Thin artifact lane: each of the three steps failing makes the run
      nonzero; a missing `claude` produces `unavailable` and nonzero, never a
      pass; a failed machine install hands no scratch prefix to the thin lane.
- [x] D6: a thin clone whose check names a manifest-declared missing path is
      `blocked` with the command in its reason; one whose check names a
      *non*-manifest missing path is `failed`. Both cases in one test file, so
      the distinction cannot be lost to a later simplification.
- [x] D7: assert the environment, not the outcome. A thin consumer's checks see
      `HOME == <work_root>/home`; a fat consumer's see the inherited `HOME`
      unchanged. A shared builder that started overriding `HOME` for both would
      pass an outcome-only test.
- [x] `thin_pin_state` branching: a fat clone gets `--platform`, a thin clone
      does not, a malformed pin fails. Assert on the argv, not on the outcome —
      C-3 is an argument-construction defect and only argv proves it.
- [x] Ledger matrix from D4: `passed`, `blocked` with reasons, `blocked`
      without reasons, `failed`, unknown status, missing consumer.
- [x] Registry immutability (acceptance criterion 2): `docs/fleet/consumers.json`
      byte-identical before and after a full run. Compare bytes, not parsed
      `mode` values — no record has that key, so a value comparison passes on a
      reader-supplied default and proves nothing.

      Proven at two levels. The criterion's own form is
      `git diff --exit-code docs/fleet/consumers.json` after a real full-fleet
      run — clean. A unit test cannot run the real fleet, so it guards the
      mechanism instead: `install.py --thin --consumer <name>` is what calls
      `flip_registry_mode`, and
      `test_pin_selects_the_lane_and_the_thin_lane_redirects_home` asserts on
      the argv that **neither** lane ever passes `--consumer`. Byte-identity is
      the outcome; the absent flag is the reason it holds.
- [x] Mixed registry (`fat` + `thin`) exercises both lanes, proven by the
      loop's own output naming each consumer and the mode it ran.
- [x] Re-enumerate call sites from the filesystem before declaring Step 1 done:
      `grep -rn 'validate_candidate_ledger(' --include='*.py' .` — the sibling
      task found a fourth `current_evidence` consumer that planning missed.

**Validation gate 1:**

```bash
.venv/bin/python -m unittest tests.test_fleet_candidate \
  tests.test_fleet_candidate_validator_digest tests.test_release_ledger \
  tests.test_release_identity tests.test_release_prep
PYTHONDONTWRITEBYTECODE=1 <mutation run over the blocked/passed branch>
```

The mutation run is not optional: a status check that accepts `blocked` without
reasons certifies a validation that never ran, which is the defect this task's
sibling exists to prevent at a different layer.

**Result — `tests.test_fleet_candidate` 23 tests, `OK`, exit 0.** Three
mutations run, each reverted and the tree verified clean afterward:

| mutation | caught by |
| --- | --- |
| thin lane drops `machine_home=` from `command_environment` | `test_pin_selects_the_lane_and_the_thin_lane_redirects_home` |
| ledger collapses the three-value status back to `!= "passed"` | `test_ledger_requires_reasons_for_every_blocked_consumer`, 5 of 8 subtests |
| D6 stops distinguishing manifest targets | `test_thin_clone_blocks_on_a_relocated_check_but_fails_on_its_own` and `test_unresolvable_thin_checks_only_covers_manifest_targets` |

**Validation gate 2 — acceptance criteria 1 and 2, end to end:**

```bash
make release-prep
git diff --exit-code docs/fleet/consumers.json   # C-1: must be clean
```

Expected: output naming the three thin artifact steps it executed, and a byte-identical
registry afterward. `git diff --exit-code` is the whole check — do not
substitute a parsed comparison of `mode` values, which no record carries.

**Result — `make release-prep` exit 0**, and a full-fleet validator run at the
same HEAD exit 0:

```text
passed      thin artifact: plugin build and drift check (0.2s)
passed      thin artifact: plugin manifest validation (0.2s)
passed      thin artifact: machine install into a scratch prefix (0.2s)
blocked     P10 platypeeps/rwbp-coordinator … blocked     P90 platypeeps/anomaly-metric-creator
```

All eight `blocked`, each with reasons, zero surviving pack defects.
`git diff --exit-code docs/fleet/consumers.json` clean afterward — criterion 2.

Note on reading gate 2: release-prep skips fleet validation when the ledger is
already current, which is the 0.69.0 behavior and the Step 0 baseline line. The
full-fleet run above is the evidence the validator actually ran; the release-prep
exit is the evidence it does not block a clean tree.

**Validation gate 3 — the gate still blocks (criterion 3):** break the plugin
build deliberately, confirm `make release-prep` exits nonzero, revert, and
verify the revert.

**Result — blocked at both levels.** With `build_files` raising:

- the candidate lane's own step fails and refuses the ledger —
  `thin artifact validation failed for 1 step(s); ledger was not updated`,
  validator exit 1, and the two later steps still ran and reported;
- `make release-prep` exits 2.

Reverted from a pre-break copy; `git diff --exit-code
.github/scripts/generate-plugin.py` is clean and `generate-plugin.py --check`
exits 0 afterward.

**Measured nuance worth keeping.** `make release-prep` fails at its *own*
generate step, which runs before the candidate lane, so its nonzero exit is not
by itself proof the lane blocks — the validator run above is. And a
hand-edited committed plugin never reaches the lane during release-prep at all:
release-prep regenerates `plugins/sd` (204 files) first, repairing the drift
before anything reads it. Measured — a deliberate edit to
`plugins/sd/.claude-plugin/plugin.json` left `make release-prep` at exit 0 while
`generate-plugin.py --check` on the same tree exited 1. The drift half of
`--check` is therefore load-bearing at `make check` and in CI, where nothing
regenerates first; inside release-prep the step's value is catching a generator
that fails outright.

## Step 5 — close

- [x] Regenerate by running `prepare-release.py` rather than sequencing
      `make sync` / `make generate` / candidate-check by hand. They are mutually
      recursive and no hand order converges; the sibling task established this
      the expensive way.
- [x] A shipped-payload change requires a `manifest.json` version bump against
      `origin/main`, with a CHANGELOG entry. 0.69.0 → 0.70.0; release-prep
      confirmed both gates:
      `release version gate: shipped payload changed; manifest version 0.69.0 -> 0.70.0`
      and
      `release changelog gate: manifest version bump has matching top heading '## 0.70.0 - 2026-08-11'`.
- [x] Update `.trellis/spec/backend/manifest-and-filesystem.md`: the schema 4
      row, the three-value status contract, the `reasons` requirement, the
      `thin_pin_state`-not-registry-mode rule, and D4's policy answer with its
      reasoning.
- [x] `make check` exits 0. Measured: exit 0.
- [x] Tick every `prd.md` acceptance criterion against measured evidence before
      `task.py archive`. All nine ticked, each with the command or test that
      proves it.

## Rollback

`git revert` of the commit. The ledger self-migrates in both directions, so no
rollback-only code exists.

## Out of scope

- Converting any consumer — children 3-5, blocked on explicit per-cohort user
  authorization.
- Re-measuring the fleet as a deliverable. The resweep numbers this task
  produces are evidence, not a migration authority.
