# Implement — commands on PATH

One PR: installer, tests, README, docstring, `AGENTS.md`. Each step is one
commit inside it, fail-first where a test is named; rule numbers are the item
body's, which `prd.md` Requirements keeps.

OWNER: `bin/sd_install.py` is a `sensitive` path in `.github/sd-review.json`,
so the owner reviews and merges the code PR, not a lane.

## Step checklist

- [ ] 1. Test 1 (rule 1, links), `tests/test_sd_install.py`, class
      `LinkTests`: `test_user_links_the_commands_and_the_receipt_names_them`.
      A `committed_checkout()` given two executables in `bin/` and one
      hand-made link already at `<home>/.local/bin/<first>`. After `--user`:
      both targets are symlinks to `<checkout>/bin/<name>`, the hand-made one
      keeps its inode, the receipt holds two `kind: link` rows with `path`
      and `target`. Red, then `link_plan`, `link_commands`, `--bin-dir` and
      the receipt rows (`design.md`, "Where the link step sits"), green.
- [ ] 2. Test 2 (rule 1, refusal): `test_user_refuses_a_foreign_file_at_a_target`.
      A regular file at `<home>/.local/bin/<name>` before `--user`: rc 1, the
      output names the path, no platform home holds a render, no receipt
      exists, the file's bytes are unchanged. Red, pre-flight refusal, green.
- [ ] 3. Test 3 (rule 1, uninstall): `test_uninstall_removes_the_links_and_nothing_else`.
      `--user`, an unrecorded link `<home>/.local/bin/sd-other` to a scratch
      file, `--uninstall`: every receipt-named link is gone, `sd-other` and
      the directory remain. Red, then `prune_links` and the `link` skip in
      `prune_stale`, green.
- [ ] 4. Test 4 (rule 2): `test_command_report_counts_per_command_links` in
      `StatusTests`, `_bin_with("sd", "sd-handoff", "sd-review")` and a
      `<home>/common` on PATH: two links give `2 of 3 resolve on PATH from
      this checkout` naming `sd-review`; three give `3 in bin/, 3 resolve on
      PATH from this checkout`; one link plus a foreign `sd-review` file on
      PATH keeps `shadowed by another install`. Red, per-name loop, green;
      the seven existing `command_report` tests stay green unchanged.
- [ ] 5. Docs (rule 3): the `--user` and `--uninstall` rows of the README
      install table, the `command_report` docstring, `USAGE` for `--bin-dir`,
      and `AGENTS.md` "Calling Convention" (bare `sd-*` resolves once
      `--user` has run; by-path still works and is what the hooks use). The
      "invoke by path" hint stays in the none-resolve branch.
- [ ] 6. Coverage (rule 4): tests for the sandboxed `--bin-dir` outside the
      home (exit 2) and `--dry-run` (`would link`). `make check` with the
      installer gate at 100%.
- [ ] 7. Mutations, one per rule test, byte-copy revert each: drop the
      `symlink_to` call (test 1, missing link); drop the foreign refusal
      (test 2, rc); make `prune_links` skip every row (test 3, surviving
      link); restore the directory test in `command_report` (test 4, count).

## Verification

- Steps 1-4 each quote `FAILED (failures=1)` before the fix and `OK` after.
- `make check VENV=/Users/sven/repos/platypeeps/sd-ai-command-pack/.venv`
  rc 0, `grep -c -E 'FAILED|ERROR'` 0, installer coverage 100%.
- `tests/test_doc_citations.py` green: `source:` locators only for symbols
  that exist today.
- Not verifiable from this lane, the owner runs it: on sol after merge,
  `--user` then `--status` prints `commands: 17 in bin/, 17 resolve on PATH
  from this checkout` and `ls -l ~/.local/bin/sd*` shows 17 links; on the
  second machine, that `~/.local/bin` is on PATH at all.

## Planning review completion report

- Changed artifacts: `prd.md`, `design.md`, `implement.md`, all new at
  `c6879551` (baseline: absent). The trigger applied because
  `bin/sd_install.py` is `sensitive` and the pages plan a change to it.
- Host review: completed, three rounds, cap 5 (Development / prd and design).
- Additional lanes: the pack defines none; Copilot's review of the planning
  PR folds through the ledger under `design.md` "Review" when it arrives.
- Concerns: C-1 to C-9 and C-12 addressed, C-10 rebutted, C-11 parked
  (size, owner's call, non-blocking). Ledger: `design.md`, "Review".
- Implementation: unblocked on the plan; blocked on the owner's three
  choices in `prd.md` and on the owner reviewing the code PR.
