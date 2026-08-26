# Implementation — stop refusing a base update over files both sides merely touched

Ordered. Each step ends green before the next begins. Canonical file is
`templates/scripts/sd-ai-command-pack-review-preflight.mjs`; the three mirrors
are regenerated, never hand-edited.

## Preconditions

- [ ] On a feature branch off `main`, clean tree.
- [ ] `.trellis/tasks/08-26-completion-successor-cc-overrefusal/design.md` read.
      Its "Decision" section is binding: the resolution is scope-checked against
      **its own call site's** allowlist, and neither allowlist is widened.
- [ ] `task.py start` has been run for this task. It has **not** been at the time
      of writing; this is a planning artifact, and implementation is gated on the
      adversarial-review contract in `.claude/rules/sd-planning-adversarial-review.md`.

## Step 1 — pin today's behavior before changing it

- [ ] 1.1 Confirm the existing fixture covers the case:
      `tests/test_bookkeeping_validator.py:2040` `make_base_update_repo`, whose
      `conflicted=True` variant resolves a real conflict on `feature.txt`.
- [ ] 1.2 Note that `feature.txt` is an **ordinary repository path**, which both
      allowlists permit. `test_completion_successor_rejects_a_conflicted_base_update`
      (`:2117`) therefore asserts the exact over-refusal this task removes, and
      its expectation must flip in step 4. Do not delete it — rename and invert it,
      so the diff shows the behavior change rather than hiding it as a deletion.
- [ ] 1.3 Add a second fixture variant whose resolution touches a **forbidden**
      path. The existing fixture already creates
      `.trellis/tasks/archive/2026-07/07-25-someone-else/prd.md` on the base
      (`:2055`); make the branch write that same file so the merge genuinely
      conflicts there. This is the guard's fixture and it must be built from a
      real conflict, not a synthesized range — PRD acceptance criterion 1.
- [ ] 1.4 `.venv/bin/python -m pytest tests/test_bookkeeping_validator.py -q`
      green before any source edit.

## Step 2 — A: classify accurately

- [ ] 2.1 In `classifyFirstParentMerge` (`:1851`), before the `--cc` call at
      `:1874`, run `git merge-tree --write-tree <fields[1]> <fields[2]>` and
      capture **both** its exit status and its stdout (the computed tree OID).
- [ ] 2.2 Return `'base-update'` only when exit is 0 **and** the computed tree
      equals the commit's own tree (`git rev-parse <oid>^{tree}`, or the tree
      field already available on `fields`). Exit 0 alone is not sufficient and
      must not be used alone — see 2.7.
- [ ] 2.3 Every other case — exit 1, exit 0 with a differing tree, an unusable
      exit, or a `merge-tree` that cannot run — continues to the `--cc` call,
      whose paths B then scope-checks. Do **not** route any of these to
      `'non-linear'`: on a pre-2.38 git the flag does not exist, and failing
      closed there would refuse every base update instead of degrading to
      today's behavior plus B.
- [ ] 2.4 Leave the existing `combined.status !== 0` → `'non-linear'` handling at
      `:1876` alone. That guards the `diff-tree` call, not the new one.
- [ ] 2.5 Replace the return at `:1879` so the `conflicted-base-update` verdict is
      reached only via 2.3.
- [ ] 2.6 Test: a clean auto-merge where both sides edit one file — the PRD's
      nine-line reproduction — classifies as `base-update`, not conflicted.
      This test fails before 2.1 and passes after; demonstrate both.
- [ ] 2.7 **Anti-smuggling test, and the reason 2.2 is a pair.** Build a merge
      that auto-merged cleanly and whose committer then hand-edited an unrelated
      file before committing. `merge-tree` exits 0 on it; its computed tree does
      not match the commit. Assert the commit is **not** classified
      `base-update`, and that the hand-edited path reaches the scope check.
      Written against the exit-0-only version of 2.2 this test must fail — run it
      that way once and record that it does, because it is the only thing
      standing between this task and re-opening the hole #558 closed.

## Step 3 — B: scope-check the resolution

- [ ] 3.1 **Site 1** (`evaluateActiveTaskSuccessorRange`, call at `:1915`,
      refusal at `:1926`): on `conflicted-base-update`, run the `--cc` paths
      through the allowlist at `:1955-1958`. A refused path emits
      `completion_successor_base_update_scope_invalid` naming that path; the
      commit then contributes nothing and the walk continues, exactly as
      `base-update` does at `:1917-1921`.
- [ ] 3.2 **Site 2** (call at `:2271`, refusal at `:2280`): push the `--cc`
      paths into `unionEntries` (`:2299`) so the existing union check at
      `:2341-2354` covers them. Do not add a parallel reporting path — the site
      already has one, and duplicating it is how these two sites drifted before.
- [ ] 3.3 Retire `completion_successor_base_update_conflicted` as a shape
      verdict at both sites. Grep the whole repo for the identifier afterwards;
      the only survivors should be changelog history.
- [ ] 3.4 Before removing it, confirm nothing consumes it:
      `grep -rn completion_successor_base_update_conflicted` across this repo and
      each fleet consumer checkout. Design assumes it is emit-only; **verify,
      do not assume** — a consumer keying on it would turn this into a breaking
      change.

## Step 4 — tests

- [ ] 4.1 Invert `:2117` per 1.2: a conflict resolved in an ordinary path now
      yields a valid receipt.
- [ ] 4.2 The 1.3 fixture asserts the guard: refused, **and the reason code is
      asserted**, not merely the invalid status — PRD acceptance criterion 2.
- [ ] 4.3 Cover **both** call sites, one test each — PRD acceptance criterion 4.
      Site 2 uses `run_completion_bundle`; site 1 needs an active-task range
      (`--mode planning` / active-task successor), which the existing suite
      exercises elsewhere — reuse that harness rather than writing a third.
- [ ] 4.4 The #560 regression pin — PRD acceptance criterion 5. A branch carrying
      `CHANGELOG.md` plus the three manifests, updated onto a base that bumped the
      same files, ends in a valid receipt.
- [ ] 4.5 Record the measured design fact as a test so it cannot regress
      silently: a conflicted base update whose resolution touches
      `.trellis/spec/**` is **allowed at site 2 and refused at site 1**. This is
      the divergence design.md declines to resolve; pinning it keeps the
      follow-up honest.

## Step 5 — artifacts that describe the rule

- [ ] 5.1 `templates/.agents/skills/sd-finish-work/SKILL.md:244` — "`git
      diff-tree --cc` reports nothing, meaning the update resolved no conflict"
      is false after step 2. Rewrite in terms of what git actually decides.
- [ ] 5.2 `templates/docs/SD_AI_COMMAND_PACK.md:1693` — "A base update that
      resolved a conflict is still refused" becomes wrong. Rewrite.
- [ ] 5.3 PRD acceptance criterion 3 is satisfied only when reason code,
      message, SKILL.md, and SD_AI_COMMAND_PACK.md all agree with the code.
      Re-read all four together, not one at a time.
- [ ] 5.4 `CHANGELOG.md` entry plus the manifest bump the release gate requires.

## Step 6 — mirrors and closure

- [ ] 6.1 `install.py . --force` then `make generate`; expect
      `shipped-surface closure: clean`.
- [ ] 6.2 PRD acceptance criterion 6 — all four copies byte-identical:

      ```bash
      find . -name sd-ai-command-pack-review-preflight.mjs -not -path './.git/*' \
        -print0 | xargs -0 shasum -a 256 | awk '{print $1}' | sort -u | wc -l
      # expect exactly 1
      ```

## Step 7 — gate

- [ ] 7.1 `.github/scripts/run-tests.sh` exits 0, zero failures.
- [ ] 7.2 `make check` green.
- [ ] 7.3 Review preflight: 0 failures.
- [ ] 7.4 `sd-ai-command-pack-fleet-candidate-check.py` — all consumers pass, and
      a regenerated all-pass `docs/fleet/candidate-validation.json` is committed.
      The release payload gate requires it alongside the manifest bump.

## Review gates

- After step 2: the classifier changed but nothing is unblocked yet. Both suites
  green here or the split in step 3 is built on a moving floor.
- After step 4: the behavior change is fully pinned. This is the last point at
  which reverting is a one-commit operation with no doc drift.
- Before step 7.4: fleet candidate check is the only gate that runs another
  repository's checks. A failure there is a fleet change, not a local one.

## Rollback

Revert the commit. Per design.md, the replacement refusal is strictly narrower
than today's, so a revert can only re-block what this change unblocks — it
cannot admit anything previously refused. No receipt migration.

A revert also restores the pre-2.38 behavior unconditionally, since A is the
only part that depends on the newer git; B carries the deadlock fix on its own.

If step 3.4 finds a consumer keying on the retired reason code: stop, keep the
code emitted alongside the new one for one release, and record the deprecation
in the changelog. Do not silently break a consumer to keep this task's diff
tidy.

## Out of scope, recorded

Unifying the two allowlists. Design.md rejects it with reasons; it changes what
a *linear* commit may contain, which is not this task's premise. File it as a
follow-up task when this lands, citing design.md's closing section and test 4.5.
