# Implement — serving tree

One pull request. The design is in [design.md](design.md).

## Step checklist

- [x] 1. `previous_commit` and the receipt's `previousCommit`, in
      `bin/sd_install.py` `cmd_user`. Size S.
- [x] 2. `--pull` in a detached serving tree (`cmd_pull_serving`, `_activate`,
      `_git`). A checkout on `main` keeps the fast-forward. Size S.
- [x] 3. `--rollback` (`cmd_rollback`), with usage, modes and the `--bin-dir`
      containment check. Size S.
- [x] 4. Tests, in `tests/test_sd_install.py` `ServingTreeTests`: refresh,
      rollback, dirty refusal, drift under `--verify`, and the error paths the
      installer coverage gate needs. Size M.
- [x] 5. README section "A dedicated serving tree", and a CHANGELOG entry.
      Size S.

## Cutover (operator)

These steps are not in the pull request. The pull request body lists them.
