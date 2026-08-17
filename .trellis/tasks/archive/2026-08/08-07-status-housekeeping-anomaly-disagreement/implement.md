# Implementation plan

Source of truth is `templates/scripts/`; `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` are generated. Tests load the collector
from `templates/scripts/` directly, so a template edit is immediately live for
`-m unittest` and a red check must be taken in a separate worktree at the
pre-fix commit.

Interpreter: `.venv/bin/python -m unittest` (no pytest in this repo). Export
`SD_AI_COMMAND_PACK_PYTHON` when running in a scratch worktree.

## Step 0 — red check first

Before any edit, in a throwaway worktree at the current `main`, confirm the
behavior the PRD reports still reproduces:

```bash
git worktree add /tmp/redcheck-08-07 HEAD
cd /tmp/redcheck-08-07
export SD_AI_COMMAND_PACK_PYTHON="$PWD/.venv/bin/python"
```

Record: a repository with one extra local branch, run with `--expect-clean`,
exits 1 and prints `extra local branches remain`. This is the before-state the
final report compares against. Rollback point: nothing has been edited yet.

## Step 1 — classification in the collector

`templates/scripts/sd-ai-command-pack-status.py`

1. In `collect_git` (`:455`), after `state["branchesHeldElsewhere"]`
   (`:505-519`), add merge evidence: one
   `git for-each-ref --format=%(refname:short) --merged refs/heads/<default>
   refs/heads` call, guarded on the local default ref existing. Store as
   `state["mergedIntoDefault"]: list[str] | None` (`None` when the default ref
   is missing or the command fails). Do **not** add a second worktree probe —
   the inventory at `:343` is authoritative.
2. Add `classify_local_branches(git, github)` returning the
   `localBranchClassification` block from `design.md`. Rules, exactly:
   - skip the default branch;
   - `heldByWorktree` from `worktrees.rows` (`path` where `branch` matches and
     `current` is false), `safe_text`-bounded;
   - `merged` when the branch is in `mergedIntoDefault`;
   - otherwise require all three evidence gates (`openPrsStatus == "available"`,
     `len(openPrs) < MAX_ITEMS`, local default exists **and**
     `defaultMatchesRemote is True`) before claiming
     `unmerged-without-pull-request`; any gate failing yields `unknown` with
     the named reason;
   - `unmerged-with-pull-request` when an `openPrs` entry's `head` equals the
     branch, carrying its `number`;
   - sort by branch, cap at `MAX_ITEMS`, set `truncated`.
3. Call it in `build_local_report` **unconditionally** (not under
   `expect_clean`), and store under `report["localBranchClassification"]`.
4. Document the squash/rebase false-`unmerged` risk in the function docstring
   (design.md → Risks).

## Step 2 — typed anomalies with severity

Same file.

1. Introduce a helper (`add_anomaly(report, code, message, severity)`) and
   convert every existing append site to it, per the design's code table:
   `:525`, `:550`, `:2501-2503` (roadmap diagnostics →
   `roadmap_source_unreadable`), `:2508`, `:2513`, `:2521`, `:2536`.
2. Change `--prior-anomaly` to `nargs=2` (`CODE MESSAGE`) and mirror the
   caller's severity through `ADVISORY_CALLER_ANOMALY_CODES` (unknown code ⇒
   blocking). Update the one caller, `housekeeping.sh:1229-1233`, to pass
   `"${ANOMALY_CODES[$index]}" "${ANOMALIES[$index]}"` the way `emit_json_result`
   already does at `:1188-1190`. Reject a one-value invocation loudly — a silent
   accept would let an old caller's message be read as a code. Two existing
   test call sites pass the old one-value form and must be updated:
   `tests/test_status.py:2071` and `tests/test_housekeeping.py:483`.
3. `strict_anomalies` (`:2108`) returns `(code, message)` pairs instead of bare
   strings. **Delete** the extras block (`:2140-2146`). Add the source-branch
   postcondition: when `source_branch` is set, is not the default, `dry_run` is
   false, and `source_branch` is still in `git["localBranches"]` — blocking
   `local_source_branch_retained`, or advisory
   `local_source_branch_held_elsewhere` naming the holder when the branch is in
   `git["branchesHeldElsewhere"]`. `strict_anomalies` therefore needs the
   worktree data; pass the `git` mapping it already receives.
4. Emit the two advisory entries derived from the classification, in **both**
   modes (`local_branches_unmerged_without_pr`,
   `local_branches_pr_state_unknown`), with the message shapes from the design
   including the `[held by <path>]` marking. Both blocks land between the
   `report` literal (`:2472`) and `followUps` (`:2551`), next to the existing
   `expect_clean` block at `:2540`; the classification reads `report["github"]`,
   which is populated inline in the literal at `:2482`.
5. Build `report["anomalyDetails"]` alongside `report["anomalies"]`; one
   construction path, so the parallel invariant cannot drift.
6. `:2334-2335` (`next_steps`) and `:2650-2654` (`render_local` `attention`)
   key on blocking entries only.
7. `render_local`'s `==> Anomalies` block (`:2875-2881`) prefixes advisory
   entries with `[advisory] `. Heading and `none` sentinel unchanged.
8. In `collect_follow_ups` (`:2160`), derive the anomaly row kind from severity
   (`issue` for blocking, `recommendation` for advisory, `:2192-2195`) and add
   the merged-and-not-held `action` row.
9. Exit rule at `:3637`: blocking entries only.

## Step 3 — worktree-aware housekeeping diagnosis

`templates/scripts/sd-ai-command-pack-housekeeping.sh`

1. Add a `default_branch_holder()` helper reading
   `git worktree list --porcelain -z`, returning the path of a non-current
   worktree whose branch is `$DEFAULT_BRANCH`.
2. `:547-552`: on switch failure, call it. Holder found →
   `default_branch_held_elsewhere` naming the path and the branch this checkout
   stays on. Not found → keep `default_branch_switch_failed`, appending git's
   bounded first stderr line.
3. `:925`: `branch_retained_default_held` when the default was held, otherwise
   `branch_switch_incomplete` unchanged.
4. **bash 3.2 gate.** `/bin/bash` on macOS is 3.2.57 and rejects an apostrophe
   inside a comment within `$( ... )`. After editing, run the enumeration
   sweep, not a single-file check:

```bash
for f in $(git ls-files '*.sh'); do /bin/bash -n "$f" || echo "BASH32-FAIL $f"; done
```

   Expect no `BASH32-FAIL` lines. (Mirrors will fail until Step 6; re-run after.)

## Step 4 — result classification

`templates/scripts/sd-ai-command-pack-housekeeping-result.py`

1. Add `ADVISORY_ANOMALY_CODES` next to `INDETERMINATE_ANOMALY_CODES` (`:54`).
2. In `classify_outcome` (`:229`): split `event_codes` into blocking/advisory.
   Order stays indeterminate → blocked → failed → clean, with the
   `INDETERMINATE_ANOMALY_CODES` check unchanged and evaluated first.
3. Replace the `status_anomalies` read (`:237`) with an `anomalyDetails`-aware
   one: blocking details only, appended as `status_<code>`; fall back to the
   current whole-list behavior plus the single `status_anomalies` code when
   `anomalyDetails` is absent.
4. Advisory event codes stay in `result["anomalies"]` untouched and never enter
   `reasonCodes`.

## Step 5 — tests

Each acceptance criterion gets a named test. Run
`.venv/bin/python -m unittest tests.test_status tests.test_housekeeping_result
tests.test_housekeeping -v`.

`tests/test_status.py` (class `StatusTests`; copy the real-worktree fixture
pattern at `:1780`):

| Criterion | Test |
| --- | --- |
| 1, 7 | `test_advisory_and_strict_report_the_same_branch_findings` — one fixture with leftover branches, run `--expect-clean` and not, identical anomaly code sets and no `Anomalies: none` alongside a blocking verdict (this is criterion 7's "two surfaces agree" test) |
| 2 | `test_branch_dispositions_separate_merged_unmerged_and_prless` |
| 2/4 | `test_held_branch_carries_worktree_path_on_every_disposition` (the matrix: merged+held, unmerged-PR-less+held) |
| 3 | `test_unavailable_pr_evidence_reports_unknown_not_prless` (`--no-network`) |
| 3 | `test_full_pr_page_reports_unknown_not_prless` (exactly `MAX_ITEMS` open PRs) |
| 3 | `test_stale_default_branch_reports_unknown_not_prless` (default behind remote) |
| 5 | `test_leftover_branches_alone_exit_zero_under_expect_clean` |
| 5 | `test_dirty_tree_still_exits_nonzero_under_expect_clean` (and one per surviving strict code — this is the guard against a general exit-zero rule) |
| 5 | `test_retained_source_branch_still_blocks` (the postcondition the deleted entry covered) |
| 4/5 | `test_retained_source_branch_held_elsewhere_is_advisory` (real second worktree; exit 0, advisory code, holder path in the message) |
| — | `test_anomaly_details_parallel_the_anomaly_list` (length, order, message equality) |
| — | `test_blocking_prior_anomaly_code_still_exits_nonzero` and `test_advisory_prior_anomaly_code_does_not` — the replay channel carries severity |
| — | `test_prior_anomaly_requires_a_code_and_message` — one-value invocation is rejected |

`tests/test_housekeeping_result.py`:

| Criterion | Test |
| --- | --- |
| 6 | rewrite `test_status_anomalies_block_even_without_shell_anomaly` (`:244`) to pin `['status_working_tree_dirty']` |
| 6 | `test_legacy_status_without_details_still_blocks` (fallback path, pins `['status_anomalies']`) |
| 4 | `test_advisory_shell_anomaly_yields_clean_verdict` — **exact** `outcome["verdict"] == "clean"`, `reasonCodes == []`, both advisory codes present in `result["anomalies"]` (the absorbed 08-08 criterion; a negative assertion would also pass for `failed`/`indeterminate`, so assert the exact value) |
| — | `test_advisory_code_does_not_outrank_indeterminate` |
| — | `test_advisory_code_sets_agree_across_scripts` — load both modules and assert `status.ADVISORY_CALLER_ANOMALY_CODES == result.ADVISORY_ANOMALY_CODES`; the two-file severity table is only safe because this test pins it |

`tests/test_housekeeping.py`: a run with the default branch held by a second
worktree emits `default_branch_held_elsewhere` naming the holder path, and a
switch failure from another cause still emits `default_branch_switch_failed`.

**Red check (mandatory).** Run the new tests in the Step 0 worktree against
unmodified code and record which fail and how. Any test that passes there is
not testing this change.

## Step 6 — surfaces, docs, release

1. `templates/.agents/skills/sd-housekeeping/SKILL.md:132` — "no anomalies"
   becomes "no blocking anomalies", plus one sentence on the advisory class and
   where its evidence lives.
2. `templates/.agents/skills/sd-status/SKILL.md` — one line in the step-4
   inventory paragraph for the branch classification and the `[advisory]`
   marking.
3. Capture the convention in `.trellis/spec/backend/error-handling.md`: a
   fail-closed check whose condition is a normal steady state stops being
   information; classify instead of blocking, and keep severity ownership in one
   place.
4. `make sync` then `make generate`.
5. **Enumerate from the filesystem, not the edit list** — every copy carries the
   change and none carries the old text:

```bash
grep -rl 'extra local branches remain' templates/scripts scripts plugins || echo "OK: no stale copies"
grep -rlc 'localBranchClassification' templates/scripts/sd-ai-command-pack-status.py \
  scripts/sd-ai-command-pack-status.py \
  plugins/sd/bin/sd-ai-command-pack-status.py \
  plugins/sd/machine-payload/scripts/sd-ai-command-pack-status.py
```

   Expect 4 files listing for the second command and the `OK:` line for the
   first.
6. Bump `manifest.json` and add the `CHANGELOG.md` entry (behavior change:
   housekeeping no longer blocks on leftover branches; a reader upgrading will
   see `clean` where they saw `blocked`).
7. `make check`. Every payload edit re-stales
   `docs/fleet/candidate-validation.json`; clear it with `make release-prep`
   (which clones consumers into a temporary directory and never touches a real
   consumer checkout), then re-run `make check`.

## Validation summary

```bash
.venv/bin/python -m unittest tests.test_status tests.test_housekeeping_result tests.test_housekeeping
for f in $(git ls-files '*.sh'); do /bin/bash -n "$f" || echo "BASH32-FAIL $f"; done
make check
```

Plus the live before/after on this repository: `sd-status` and
`sd-housekeeping --json` on the same unchanged state, showing `blocked` +
`['status_anomalies']` before and `clean` + `[]` after, with the leftover
branches still reported and now classified.

## Rollback points

- After Step 2: collector changes are self-contained; reverting the file
  restores today's behavior including the exit rule.
- After Step 4: the result script's fallback path means an old collector and a
  new result script still block exactly as today, so a partial revert is safe in
  either direction.
- After Step 6: `make sync` / `make generate` are deterministic; regenerate
  rather than hand-editing any mirror.

## Out of scope

- Detaching or relocating a worktree that holds the default branch. The residual
  is reported, not resolved (design.md → Honest residual).
- Patch-id equivalence for squash/rebase-merged branches.
- Any change to merge, deletion, or eligibility gates.
