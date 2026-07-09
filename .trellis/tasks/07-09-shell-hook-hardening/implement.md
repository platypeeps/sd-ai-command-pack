# Shell And Hook Hardening Batch Implementation Plan

## Execution Order

1. Add pre-push behavioral tests around a temp bare remote and working clone.
2. Change the guard to rename-safe diffing and make the new test pass.
3. Add full-check temp registration/trap behavior in the template and sync the
   root script.
4. Update shell-lib header contract and any caller setup required by tests.
5. Replace housekeeping TSV parsing and add empty-field/empty-default-branch
   self-test coverage.
6. Run shell lint and script/template drift checks.

## Validation Plan

Run `python3 -m unittest tests.test_full_check tests.test_housekeeping` plus
the pre-push test file. Run `git ls-files -z '*.sh' | xargs -0 shellcheck -S warning .githooks/pre-push`
and `bash -n` on changed scripts.

## Documentation And Spec Updates

Update README/CONTRIBUTING only if the direct-push policy wording changes.
Keep shell-lib caller requirements in the script header close to the code.

## Review Notes

Reviewers should look for swallowed exit codes in trap code and shell arrays
that break under macOS bash 3.2.

## Follow-Ups

If pre-push test setup becomes bulky, split reusable git-fixture helpers into
test support in a later cleanup.
