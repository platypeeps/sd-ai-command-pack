# Implement — serving tree

One pull request. The design is in [design.md](design.md).

sd:3009 deleted steps 1, 3 and 7 and the slot build, lock and put-back of step 2; design.md has the plain clone.

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
- [x] 6. `--serve` (`cmd_serve`, `_clone_serving_tree`, `serving_tree`) and
      the `make setup` step that runs it, with `SERVE=no`. Size S.
- [x] 7. Receipt-recorded links move to the next checkout (`link_plan`
      state `recorded`, `_replace_link`). Size S.
- [x] 8. Tests: `ServeTests`, three `LinkEdgeCaseTests`, and the recipe in
      `tests/test_sd_lib.py` `SetupStaysLocalTests`. Size S.

## Cutover (operator)

These steps are not in the pull request. The pull request body lists them.

1. After the merge, run `make setup` in the working checkout. It clones the
   serving tree, renders from it, and moves the receipt's links in
   `~/.local/bin` there.
2. Point `~/bin/common` at the serving tree:
   `SD_PACK_ROOT="$HOME/.local/share/sd-ai-command-pack/serving" sh ~/repos/system/local-bin-links/bin-links.sh install`.
3. Check it: `python3 ~/.local/share/sd-ai-command-pack/serving/bin/sd_install.py --verify --json`.
4. Roll back the switch: `python3 bin/sd_install.py --user` in the working
   checkout moves the receipt's links back, and `bin-links.sh install`
   without `SD_PACK_ROOT` moves `~/bin/common` back.
