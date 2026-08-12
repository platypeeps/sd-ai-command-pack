# Implement — rescope the candidate validator loop to the thin shape

Design is `design.md`. D1-D5 answer the PRD's C-1 through C-4; D6 and D7 answer
two defects the planning review found in D5's own first draft. Read it before
editing — three of the four original concerns are dissolved by the shape
decision rather than worked around, so an implementation that reintroduces
`install.py --thin` into the loop is not a variation, it is the rejected design.

## Step 0 — before editing

- [ ] `trellis-before-dev`: `.trellis/spec/backend/index.md`, the
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

      Two things this settles. The `packDefects` column is **not** stale after
      all for this consumer — `08-10-thin-prompt-surface-repoint` and
      `08-11-thin-undeclared-codex-marker` did not reduce it, so `design.md`'s
      "must be re-measured, not carried" was right to demand the measurement
      and wrong to predict its result. And 15 pack-owned defects means D4's
      `packDefects > 0` rule would fail release-prep for this consumer **today**
      — see Step 2b, added for that reason.

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

**Decision (user, this run): fix them here.** The alternative — ship the policy
and file a follow-up — leaves `main` unable to cut a release in between, which
is worse than a bounded scope increase. This is the same class of work as the
already-shipped `08-10-thin-prompt-surface-repoint`, applied to the `.github/`
surface that task did not reach.

- [ ] Repoint each citation to the form a thin consumer can satisfy, following
      `THIN_PROFILE`'s existing rules (`~/.agents/bin/<name>`,
      `~/.agents/docs`). Edit the **template** under `templates/`, never the
      generated copy.
- [ ] Two prompts already carry a newer "resolvable, either as a bare command
      on `PATH` or ..." phrasing in one consumer out of eight, and it is
      **still** a defect — the sentence continues to name
      `scripts/sd-ai-command-pack-*.py`. Do not treat that phrasing as the
      target state; it is a partial fix that did not clear the rule.
- [ ] The `codex` defect is a different shape: "undeclared codex usage: the
      codex CLI is invoked in 1 surviving file(s), e.g.
      `.claude/sd-ai-command-pack/planning-adversarial-review.md`". Its sibling
      task `08-11-thin-undeclared-codex-marker` is archived, so establish
      whether this is residue that task missed or a deliberate invocation that
      needs an allowlist entry with a written reason. Do not silence it either
      way without deciding which.
- [ ] Re-resweep all eight afterward. The gate is `packDefects == 0` on every
      consumer; anything left must be an explicit allowlist entry, not a
      remainder.
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

- [ ] Bump `CANDIDATE_LEDGER_SCHEMA_VERSION` 3 → 4 (D4).
- [ ] Widen `validate_candidate_ledger`'s consumer-status check to accept
      `blocked` **only** with a non-empty `reasons` array, keep rejecting
      `failed` and unknown statuses, and keep rejecting missing/unknown
      consumers. The Wrong/Correct pair is in D4; copy its shape.
- [ ] Do not touch `validatorDigest`, `payload_digest`, or
      `candidate_validator_digest`. They shipped in 0.69.0 and this task has no
      quarrel with them.

## Step 2 — the thin artifact lane

Edit `scripts/sd-ai-command-pack-fleet-candidate-check.py` (no template; edited
in place).

- [ ] Add the lane from D5, run **once** per candidate run before the
      per-consumer loop, inside the existing `work_root` temporary directory
      (`:480`). Four steps: build into `<work_root>/pack`, `plugin validate
      --strict`, `generate-plugin.py --check` against the checkout, `install.py
      --machine` into `<work_root>/home` with `--state-home <work_root>/state`.
- [ ] Do **not** add a `claude --plugin-dir` step. Measured, it exits 0 against
      a nonexistent plugin directory, so it cannot fail; it also needs a
      billable model call, which requirement 5's no-skip rule would then make
      mandatory for every `make release-prep`. D5 records the deviation and
      Step 0 amends the PRD.
- [ ] Retain `<work_root>/home` and `<work_root>/state` for Step 3. The machine
      install is the thin lane's `HOME`, not a discarded artifact check.
- [ ] Build into the scratch copy, never the checkout. `generate-plugin.py
      --root` is the seam. A validator that rewrites its own input repeats D1's
      error one directory over.
- [ ] Resolve `claude` once; if it is unresolvable, report the steps as
      `unavailable` and exit nonzero (requirement 5). No skip flag, no
      environment escape, no degrade-to-fat.

## Step 3 — the per-consumer lane

- [ ] Resweep the **pristine clone** before any install
      (`resweep_consumer(name, clone)` — it takes an explicit repo, so it reads
      the clone rather than the registered `pathHint`). Classify per D4:
      `packDefects` → `failed`; `blockers` / `missingFiles` / dirty → `blocked`
      with reasons.
- [ ] Branch the install on `conversion.thin_pin_state(clone)`, never on the
      registry's declared `mode` (D3). `fat` keeps today's
      `--force --platform ...`; `thin` drops `--platform` entirely; `malformed`
      fails with the pin state named.
- [ ] Record a note when the clone's pin and the registry's `mode` disagree.
      It is the documented conversion skew, not an error.
- [ ] **D6 — unresolvable thin checks.** Before running a thin clone's
      `candidateChecks`, resolve each command's program argument against the
      clone. Absent **and** manifest-declared is `blocked`, with a reason naming
      the command and the `~/.agents/bin/<name>` form the record should use.
      Absent and not manifest-declared stays `failed`. Two consumers are already
      in this state on paper — `se-ai-command-pack` runs
      `bash scripts/sd-ai-command-pack-housekeeping.sh --self-test` and
      `rwbp-website` runs `node scripts/sd-ai-command-pack-review-preflight.mjs`,
      both manifest-declared. Do not rewrite the registry to fix them; that is
      the consumer's conversion PR.
- [ ] **D7 — the thin lane's `HOME`.** Run a thin clone's `candidatePrepare` and
      `candidateChecks` with `HOME=<work_root>/home` and the state home from the
      artifact lane. Leave the fat lane's environment exactly as it is —
      `command_environment` (`:67-84`) must not start overriding `HOME` for
      everyone. Without this, a thin consumer's `~/.agents/bin` lookups resolve
      to whatever pack the invoking machine has installed, and the run certifies
      someone else's release.
- [ ] Carry `reasons` into `CandidateResult` and into the ledger row.
- [ ] Narrow the `:520` failure gate to "not `passed` **and** not `blocked`", so
      a fleet of blocked consumers still writes a truthful ledger.

## Step 4 — tests

- [ ] Thin artifact lane: each of the four steps failing makes the run
      nonzero; a missing `claude` produces `unavailable` and nonzero, never a
      pass.
- [ ] D6: a thin clone whose check names a manifest-declared missing path is
      `blocked` with the command in its reason; one whose check names a
      *non*-manifest missing path is `failed`. Both cases in one test file, so
      the distinction cannot be lost to a later simplification.
- [ ] D7: assert the environment, not the outcome. A thin consumer's checks see
      `HOME == <work_root>/home`; a fat consumer's see the inherited `HOME`
      unchanged. A shared builder that started overriding `HOME` for both would
      pass an outcome-only test.
- [ ] `thin_pin_state` branching: a fat clone gets `--platform`, a thin clone
      does not, a malformed pin fails. Assert on the argv, not on the outcome —
      C-3 is an argument-construction defect and only argv proves it.
- [ ] Ledger matrix from D4: `passed`, `blocked` with reasons, `blocked`
      without reasons, `failed`, unknown status, missing consumer.
- [ ] Registry immutability (acceptance criterion 2): `docs/fleet/consumers.json`
      byte-identical before and after a full run. Compare bytes, not parsed
      `mode` values — no record has that key, so a value comparison passes on a
      reader-supplied default and proves nothing.
- [ ] Mixed registry (`fat` + `thin`) exercises both lanes, proven by the
      loop's own output naming each consumer and the mode it ran.
- [ ] Re-enumerate call sites from the filesystem before declaring Step 1 done:
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

**Validation gate 2 — acceptance criteria 1 and 2, end to end:**

```bash
make release-prep
git diff --exit-code docs/fleet/consumers.json   # C-1: must be clean
```

Expected: output naming the four thin steps it executed, and a byte-identical
registry afterward. `git diff --exit-code` is the whole check — do not
substitute a parsed comparison of `mode` values, which no record carries.

**Validation gate 3 — the gate still blocks (criterion 3):** break the plugin
build deliberately, confirm `make release-prep` exits nonzero, revert, and
verify the revert.

## Step 5 — close

- [ ] Regenerate by running `prepare-release.py` rather than sequencing
      `make sync` / `make generate` / candidate-check by hand. They are mutually
      recursive and no hand order converges; the sibling task established this
      the expensive way.
- [ ] A shipped-payload change requires a `manifest.json` version bump against
      `origin/main`, with a CHANGELOG entry.
- [ ] Update `.trellis/spec/backend/manifest-and-filesystem.md`: the schema 4
      row, the three-value status contract, the `reasons` requirement, the
      `thin_pin_state`-not-registry-mode rule, and D4's policy answer with its
      reasoning.
- [ ] `make check` exits 0.
- [ ] Tick every `prd.md` acceptance criterion against measured evidence before
      `task.py archive`.

## Rollback

`git revert` of the commit. The ledger self-migrates in both directions, so no
rollback-only code exists.

## Out of scope

- Converting any consumer — children 3-5, blocked on explicit per-cohort user
  authorization.
- Re-measuring the fleet as a deliverable. The resweep numbers this task
  produces are evidence, not a migration authority.
