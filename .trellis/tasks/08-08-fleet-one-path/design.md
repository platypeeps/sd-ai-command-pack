# Design: one canonical fleet path

PRD: [`prd.md`](prd.md). This design covers requirements 1 to 5 and names the
tasks that own the legs this one only consumes.

## What changed since the PRD was written

The PRD is dated 2026-08-08 and describes a fat fleet: "docs/fleet/consumers.json
carries per-consumer bespoke checks/prepares; the 8 consumers drift in Trellis
version, pack version, review path, and Copilot policy". The thin migration
landed in between, so two of those four premises now read differently.

Measured 2026-08-17 19:30 UTC from
`scripts/sd-ai-command-pack-status.py fleet --json` (pin from
`repositories[].pin.version`, Trellis from
`repositories[].report.versions.trellis`, cleanliness from
`repositories[].report.git.workingTree.state` — there is no `git.dirty` key):

| Consumer | Mode | Pin | Trellis | Tree | Branch |
|---|---|---|---|---|---|
| rwbp-coordinator | thin | 0.71.22 | 0.6.7 | clean | `deps/next-16.3.1` |
| loadsmith | thin | 0.71.22 | 0.6.7 | clean | `main` |
| hoa-manager | thin | 0.71.22 | 0.6.7 | **dirty** | `fix/staging-health-never-runs` |
| rwbp-website | thin | 0.71.22 | 0.6.7 | clean | `feat/rwbpr-024-slice-2-privacy-data-tool` |
| mezmo_benchmark | thin | 0.71.22 | 0.6.7 | clean | `lead/repomix-ordering-evidence` |
| se-ai-command-pack | thin | 0.71.22 | 0.6.7 | clean | `main` |
| sd-github-review | thin | 0.71.26 | 0.6.7 | clean | `main` |
| anomaly-metric-creator | thin | 0.71.22 | 0.6.7 | clean | `main` |

Source repository: pack 0.71.29, release target 0.71.29, Trellis **0.6.14**.
Machine scope: install 0.71.29, plugin 0.71.29 — `comparison: current`.
The skew that blocked the rollout is cleared; see *Gate A is satisfied*.

Four consequences for this task:

1. **All 8 consumers are `mode: thin`.** There is no vendored pack tree left to
   drift; the pack leg is now one number per consumer, its pin. Requirement 2 is
   therefore no longer about normalizing a vendored surface — it is only about
   `candidatePrepare` and `candidateChecks`, which are and remain repo-owned.
2. **The Trellis leg is the widest drift and the PRD does not mention its size.**
   Every consumer is on 0.6.7 while this repository vendors 0.6.14. The human
   fleet report cannot show it: a thin row prints the pin instead of an
   installed-versus-target pair, so `trellis` appears only in `--json`. Any
   verification of the PRD's third acceptance criterion has to read the JSON
   path above, and a reviewer checking the human rows would conclude the fleet
   is consistent when seven Trellis patch releases are missing. That finding
   is why the leg was split out: it is owned by
   `08-17-fleet-trellis-version-drift`, which carries both the upgrade pass and
   the reporting-visibility question. This task keeps the leg in the
   canonical-path doc and points there.
3. **The dirty set is volatile, and a snapshot of it is not a plan.** Three
   measurements of the same fleet on 2026-08-17:

   | Time (UTC) | Dirty | Consumers on a feature branch |
   |---|---|---|
   | ~15:30 | loadsmith, hoa-manager, mezmo_benchmark | 5 |
   | ~18:50 | loadsmith | 6 |
   | 19:30 | hoa-manager | 4 |

   Every consumer that was dirty in the first measurement was clean by the
   third, a different one had gone dirty, and four consumers changed branch
   inside forty minutes. These are other people's working trees; they move
   while the campaign runs.

   The consequence is not "the table above needs refreshing" — it is that
   **exclusion must be decided per consumer at the moment its lane starts, and
   re-checked immediately before any write to it.** A pass that computes its
   skip list once at preflight will write into a checkout that went dirty in
   between, which is the exact thing the standing rule forbids.
   `docs/FLEET_ROLLOUT.md:250` already stops such a consumer ("Stop when an
   unrelated active task or dirty Trellis state makes ownership ambiguous"), so
   the procedure is right; what this task must not do is precompute a skip list
   and treat it as authoritative.

   The PRD's "All 8 consumers on target" criterion therefore cannot be met in a
   single pass, and not because of any particular consumer — at any given
   moment some consumer is mid-work. See *Acceptance criteria that need
   restating*.

4. **Gate A is satisfied.** The machine install and the plugin both report
   0.71.29 against target 0.71.29, `comparison: current`. Every thin consumer
   resolves its surfaces from that install, so the precondition that blocked
   `implement.md` Step 6 is cleared. Two gates remain and neither is this
   task's to decide alone: the `08-08-copilot-request-policy` sequencing
   question, and whether a consumer sitting on an active feature branch counts
   as ambiguous ownership under `FLEET_ROLLOUT.md:250`. Four of eight are on
   one right now.

## The canonical path: four legs, four owners

The doc requirement 1 asks for is normative about the *value* of each leg and
about *which task owns changing it*. It decides nothing that
`08-08-ci-lane-cost` or `08-08-copilot-request-policy` owns.

| Leg | Canonical value | Observed | Mechanism | Owner |
|---|---|---|---|---|
| Trellis version | this repository's vendored version (0.6.14 today) | 8/8 at 0.6.7 | `trellis update` in the consumer, one PR | `08-17-fleet-trellis-version-drift` |
| Pack pin | the release target (0.71.29 today) | 7× 0.71.22, 1× 0.71.26 | `sd-fleet-refresh` campaign | this task |
| Review lane | router-owned Copilot dispatch with a durable head-bound receipt; no repo-level automatic review ruleset | three independent request surfaces | delete the skill's direct path, switch the rulesets off | `08-08-copilot-request-policy` |
| CI shape | bookkeeping fast lane wide enough to fire; shell coverage off the PR path; macOS main-only | `tests.yml` as shipped | edit `tests.yml`, propagate the pattern | `08-08-ci-lane-cost` |

Placement: `docs/FLEET_CANONICAL_PATH.md`, beside `docs/FLEET_ROLLOUT.md` rather
than under `docs/fleet/`, which holds only machine-read JSON
(`consumers.json`, `candidate-validation.json`, `surface-partition.json`).
`FLEET_ROLLOUT.md` stays the procedure authority and gains one link; the new doc
is the value authority. Two documents because they change on different triggers:
the procedure changes when the campaign machinery changes, the canonical values
change on every release.

The doc records, per leg, the canonical value, how to observe the real one, the
owning task, and what a deviation costs. It does not restate the procedure and
does not copy version numbers that a command can print — each leg's row names
the command instead, because a hardcoded 0.71.29 in prose is stale on the next
release and nothing fails when it is.

## Requirement 2: normalizing the candidate contract

Current declarations (`docs/fleet/consumers.json`):

| Consumer | `candidatePrepare` | `candidateChecks` |
|---|---|---|
| rwbp-coordinator | `bash scripts/update_repomix` | `node scripts/check-review-churn.mjs` |
| loadsmith | `bash scripts/update_repomix` | `bash scripts/check_review_readiness.sh --all --skip-build` |
| hoa-manager | `bash scripts/update_repomix` | `node scripts/check-review-preflight.mjs` |
| rwbp-website | `bash scripts/update_repomix` | pack preflight via `$HOME/.agents/bin/...`, then `node scripts/ops-check.mjs` |
| mezmo_benchmark | `bash scripts/update_repomix` | `python3 scripts/check-review-cycle-patterns.py --base HEAD --include-working-tree` |
| se-ai-command-pack | *(empty)* | pack housekeeping `--self-test` via `$HOME/.agents/bin/...` |
| sd-github-review | `npm ci` | `npm test`, `npm run check`, `npm run validate:metadata` |
| anomaly-metric-creator | `bash scripts/update_repomix` | `python3 tools/check_ci_review_contract.py`, `python3 tools/check_copilot_instruction_contract.py` |

Two hard constraints from the parser, `scripts/sd_ai_command_pack_fleet_lib.py:679-691`:
`candidateChecks` is parsed with `allow_empty=False` and `candidatePrepare` with
`allow_empty=True`. **A consumer cannot be normalized down to zero checks.** So
the target shape is not "delete the bespoke entries" — it is:

- **One pack-owned check, identical argv, on every consumer:**
  `bash "$HOME/.agents/bin/sd-ai-command-pack-housekeeping.sh" --self-test`.
  se-ai-command-pack already declares exactly that. It is the right canonical
  entry for three reasons: it is hermetic and read-only, which is what
  `candidateChecks` is specified to be; it is meaningful in a disposable clone of
  the default branch, where there is no PR and no diff; and the script itself
  documents CI use for that purpose
  (`scripts/sd-ai-command-pack-housekeeping.sh:1328-1333`, "Hermetic self-test of
  the auto-merge gate contract"). Both names exist on the machine install
  (verified in `~/.agents/bin`), so the argv resolves identically on every thin
  consumer.
  The alternative, rwbp-website's bare
  `node "$HOME/.agents/bin/sd-ai-command-pack-review-preflight.mjs"`, is
  **rejected as the canonical entry**: preflight's subject is a change set, and in
  a diff-less clone it can only report that there is nothing to inspect. A check
  that cannot fail is not a check.
- **At most one repo-owned check after it**, each annotated with the stack reason
  that keeps it. `npm test` on a Node router and
  `check_ci_review_contract.py` on a Python service are genuine stack
  differences; `check-review-churn.mjs` versus `check-review-preflight.mjs`
  versus `check_review_readiness.sh` are three names for review readiness and
  are the actual normalization target.
- **`candidatePrepare` stays repo-owned and is not normalized.** It is the only
  phase allowed to mutate generated artifacts (`docs/FLEET_ROLLOUT.md:67`),
  and `bash scripts/update_repomix` versus `npm ci` is a real difference in what
  the repository generates. What this task normalizes is its *contract*: prepare
  must be deterministic and must leave the disposable clone buildable. `npm ci`
  reaches the network, which the others do not; that asymmetry is annotated, not
  removed.

Annotation mechanism: a `deviations` object per consumer mapping the field name
to a reason string. The parser reads named keys and ignores unknown ones
(`_parse_fleet_consumers_without_policy`, same file), so the field is inert for
every existing consumer of the manifest — but *inert* also means nothing
enforces it. The gate that makes it real is a check in this repository asserting
that every non-canonical `candidateChecks` entry has a `deviations.candidateChecks`
reason, so a future bespoke entry added without a reason fails `make check`
rather than being noticed by a reader. Without that check, requirement 2's
acceptance criterion decays the first time someone edits the manifest.

## Requirement 3: private-repo cost guidance

Owned by `08-08-ci-lane-cost` (its acceptance criterion 4 explicitly says "Private-consumer
guidance updated (fleet one-path task carries propagation)"). This task carries
the *propagation*: the canonical-path doc's CI row states the lane policy and
links that task, and each consumer's rollout PR is where the policy lands in
that repository's own workflow.

The number that makes it matter, from that task's PRD: the macOS leg is 73% of
billable minutes at the 10× multiplier, and `$0` here only because this
repository is public. This task does not re-derive it and does not re-decide the
lane shape; a design that restated `08-08-ci-lane-cost`'s numbers would give
two artifacts to keep in sync and no extra guarantee.

## Requirement 4: Copilot policy propagation

Owned by `08-08-copilot-request-policy`. Its requirement 4 is an operator pass
switching the repo-level automatic review ruleset off on all 8 repos, and its
acceptance criteria include "One Copilot review per PR head observed on a smoke
PR (no duplicates)". That observation happens on **this** task's rollout PRs —
which is the whole reason the two tasks are sequenced rather than merged:
`08-08-copilot-request-policy` changes the request surfaces, this task provides
the eight real PRs that prove the change fleet-wide.

Sequencing consequence: a rollout pass that runs before
`08-08-copilot-request-policy` lands will show duplicate Copilot requests on its
PRs, and that is not this task's defect. Run that task first, or accept the
duplicates and record that the smoke observation is deferred. Do not "fix" it
inside a rollout lane.

## Requirement 5: rollout, and what the smoke PR is

**The refresh PR is the smoke PR.** The campaign already opens exactly one PR per
consumer from the recorded default-branch commit
(`docs/FLEET_ROLLOUT.md:243-258`), and `at-target` consumers are skipped
specifically to avoid empty PRs (`:129`). Inventing a second, synthetic PR per
repo would double the review cost the fleet is trying to cut and would prove
less, because it would not carry the pin change under test.

What each refresh PR must demonstrate, as an explicit checklist in the rollout
record:

1. the pin moves to the release target, and the consumer's own full check passes
   in its own CI;
2. exactly one Copilot review request per head — the
   `08-08-copilot-request-policy` observation, when that task has landed;
3. the review lane produces a durable head-bound receipt;
4. the housekeeping merge gate reports green and comment-clean before merge; and
5. after merge, `sd-status fleet --json` shows the consumer's `pin.version` at
   target.

The Trellis leg is a **separate PR per consumer**, not a rider on the refresh PR.
Reasons: the refresh PR's diff is the pin plus provider config, which the
candidate validator has already exercised in a disposable clone, while a
`trellis update` diff touches `.trellis/scripts/**` and can move behavior in the
consumer; and a mixed PR cannot be reverted along one leg. That separation is a
constraint this design imposes on the rollout, and the leg itself is executed by
`08-17-fleet-trellis-version-drift` (its requirement 2). The canonical-path doc
records the rule so a later operator does not combine them for convenience.

Order and concurrency come from the manifest's existing `rolloutPolicy` and are
not redesigned here: canary `rwbp-coordinator`, `loadsmith`, `hoa-manager`
sequentially, then post-canary `rwbp-website`, `mezmo_benchmark`,
`se-ai-command-pack`, `sd-github-review` at concurrency 2, then final
`anomaly-metric-creator`. The canary cohort is where the volatility bites
hardest: it is three named consumers run sequentially, and at each of the three
2026-08-17 measurements a different subset of it was dirty. The pass starts from
whichever canaries are clean when it starts, records the rest as skips, and does
not reorder the cohorts to route around a dirty one.

## Preconditions the rollout cannot start without

- **Machine install at the release target — satisfied 2026-08-17.** Every thin
  consumer resolves its surfaces from the machine install, so a refresh run
  against a behind machine would move eight pins to a version the machine cannot
  serve. It was 0.71.26 against a 0.71.29 target; `bash
  scripts/sd-ai-command-pack-pack-update.sh` from this checkout — a machine-scope
  write, and an operator action — brought it to 0.71.29.
- **Plugin and receipt reconciled — satisfied 2026-08-17.** Both now report
  0.71.29, `comparison: current`. It was plugin 0.71.22 against receipt 0.71.26.
  The update refused once with exit 12 on conflicting install paths: two
  project-scope plugin install records still pointed at the old cached version
  after user scope moved. They are removed with
  `claude plugin uninstall <id> -s project`, which also rewrites the
  repository's tracked `.claude/settings.json` and must be restored after.
- **Nothing dirty in the consumer being touched, checked at its lane.** No
  consumer is named here on purpose — consequence 3 records the dirty set
  changing three times in four hours. The precondition is a per-lane check
  immediately before the write, not a list. This task never cleans another
  checkout.

## Verification

```bash
# canonical values and the real ones, per consumer.
# The pin column is this task's criterion; the trellis column is context and
# belongs to 08-17-fleet-trellis-version-drift's ledger.
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-status.py fleet --json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(r["name"], r["pin"]["version"], r["report"]["versions"]["trellis"]) for r in d["repositories"]]'

# the manifest annotation gate
make check

```

Then, separately, the campaign machinery without mutation — `sd-fleet-refresh
dry-run`, which is a **command invocation, not a shell executable**: the
procedure is source-only and is loaded by reading
`.agents/skills/sd-fleet-refresh/SKILL.md` from this checkout. Nothing on `PATH`
answers to that name.

`dry-run` is the one end-to-end exercise available before the machine install is
at target: it "records preflight, marks current consumers `at-target`, marks the
remaining selected consumers skipped without mutation, then completes the
record" (`docs/FLEET_ROLLOUT.md:396`). It proves the manifest parses, the
cohorts resolve, and every consumer is reachable — and it proves nothing about
the pins, which only a real campaign moves.

## Acceptance criteria that need restating

The PRD's third criterion, "All 8 consumers on target pack + Trellis versions
after rollout", is not satisfiable as written while any consumer is dirty, and a
task whose criterion depends on other people's working trees can never be
closed. Replace it with a per-consumer ledger: every consumer is either at target
or carries a recorded reason (dirty tree, owner-blocked, deliberately deferred),
and the task closes when the ledger is complete rather than when the fleet is
uniform. The fourth criterion, about repo-level Copilot rulesets, belongs to
`08-08-copilot-request-policy` and is verified there; this task cites it.

That restatement is a PRD edit, and it was made in planning — `prd.md` carries the
dated 2026-08-17 amendment with the original wording preserved — not a quiet
reinterpretation during implementation. `implement.md`'s Step 1 therefore has
nothing to execute; it owns only the ledger the amended criterion requires.

## Rollback

- The canonical-path doc and the manifest annotations are additive text in this
  repository: revert the commit.
- The annotation gate is one check; reverting it restores the previous
  `make check` behavior exactly.
- A consumer rollout PR is reverted by closing it and deleting its branch, which
  is the campaign's own recovery path; a merged one is reverted in that
  consumer's repository by its owner.
- A `trellis update` PR is separate precisely so it can be reverted without
  touching the pin, and vice versa.

## Out of scope

- Re-deciding the CI lane shape (`08-08-ci-lane-cost`) or the Copilot request
  surfaces (`08-08-copilot-request-policy`).
- Writing into any consumer checkout, cleaning a dirty one, or running the
  machine-scope pack update without the operator asking for it.
- Changing `rolloutPolicy` cohorts or concurrency.
- Upgrading Trellis in this repository.
