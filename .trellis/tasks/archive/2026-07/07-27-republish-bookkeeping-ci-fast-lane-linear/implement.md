# Implementation Plan: Linear replacement publication

## 1. Establish the replacement branch

- Fetch `origin/main` and record its exact OID.
- Create `codex/republish-bookkeeping-ci-fast-lane-linear` from that OID.
- Verify PR #270 remains open and unchanged at `3d1a827`.
- Verify the original fast-lane task exists on the new base.

## 2. Activate lifecycle ownership

- Start `07-24-add-bookkeeping-only-ci-fast-lane` on the replacement branch.
- Start `07-27-republish-bookkeeping-ci-fast-lane-linear` last so it remains
  the session's current task.
- Load `trellis-before-dev` and the backend quality guidelines before editing.

## 3. Replay reviewed content

- Apply the nine-file functional diff from `origin/main` to PR #270 head
  `3d1a827`, explicitly excluding `.trellis/tasks/` and
  `.trellis/workspace/`.
- Preserve the reviewed task implementation note on the original active task
  while keeping its new branch/lifecycle identity.
- Record recovery evidence on the recovery task.
- Confirm the nine functional paths are byte-identical to `3d1a827`.
- Run `git diff --check`, the 31 directly affected workflow tests, and
  actionlint.

## 4. Validate and commit work

- Run `make check` with the linked KB current.
- Run `trellis-check` in inline mode and address only verified findings.
- Commit the functional replay and active-task evidence as scoped work commits.
- Re-run exact-head `sd-check --json` and require 8/8 with an unchanged state
  guard.

## 5. Finalize both tasks

- Capture the finalization base at the last work commit.
- Run `pre-archive --task-dir` with both exact active task directories.
- Archive both tasks without touching unrelated active tasks.
- Record one journal session using
  `sd-ai-command-pack-record-session.py --no-commit`, then commit only its
  journal and sibling index.
- Run `final-bundle --mode completion` across the captured base-to-head range
  and retain the valid private receipt.

## 6. Publish and converge the replacement PR

- Push the new branch and create a ready replacement PR whose body links PR
  #270 and explains the linear-history recovery.
- Run the `sd-review-pr` cycle, require all CI checks green, require the
  configured reviewer to review the exact head, and resolve every handled
  thread.
- Re-run finish-work receipt validation after any allowed review-successor
  commit.

## 7. Supersede PR #270

- Confirm the replacement PR remains mergeable, review-clean, CI-green, and
  backed by a valid exact-head completion receipt.
- Comment on and close PR #270 as superseded, linking the replacement PR.
- Leave the replacement PR open and ready for the user's merge decision.

## Validation Commands

```bash
.venv/bin/python -m unittest \
  tests.test_bookkeeping_ci_scope \
  tests.test_generated_parity.GeneratedParityTests.test_ci_dependency_and_main_push_guards_are_bounded \
  tests.test_release_ledger
ACTIONLINT_GOPATH=/private/tmp/sd-actionlint-go \
ACTIONLINT_GOCACHE=/private/tmp/sd-actionlint-cache \
GOPATH="$ACTIONLINT_GOPATH" GOCACHE="$ACTIONLINT_GOCACHE" \
  go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 \
  .github/workflows/tests.yml
make check
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-check.py --json
```

## Stop Conditions

- PR #270's head changes unexpectedly.
- Current `main` no longer contains the expected original planning task.
- Functional replay differs from the reviewed reference without an explained
  current-main conflict.
- Pre-archive or final-bundle validation is not exactly valid.
- Any operation would require force-pushing, rewriting, deleting, or merging.
