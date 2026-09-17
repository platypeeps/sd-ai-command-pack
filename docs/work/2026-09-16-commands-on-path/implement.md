# Implement — commands on PATH

One PR: installer, tests, README, docstring, `AGENTS.md`. Each step is one
commit inside it, fail-first where a test is named; rule numbers are the item
body's, which `prd.md` Requirements keeps.

OWNER: `bin/sd_install.py` is a `sensitive` path in `.github/sd-review.json`,
so the owner reviews and merges the code PR, not a lane.

## Step checklist

- [x] 1. Test 1 (rule 1, links), `tests/test_sd_install.py`, class
      `LinkTests`: `test_user_links_the_commands_and_the_receipt_names_them`.
      A `committed_checkout()` given three executables in `bin/`, one
      hand-made absolute link already at `<home>/.local/bin/<first>` and one
      hand-made relative link at `<second>`. After `--user`: all three are
      symlinks that resolve to `<checkout>/bin/<name>`, the two hand-made
      ones keep their inodes, the receipt holds three `kind: link` rows with
      `path` and `target`. Red, then `link_plan`, `link_commands`,
      `--bin-dir` and the receipt rows (`design.md`, "Where the link step
      sits"), green. Done 2026-09-16: red `FAILED (failures=1)`
      (`.local/bin/sd-review is not a symlink`), green `OK`; C-35 folded,
      the test asserts the `not on PATH` warning with the directory off
      PATH and its absence with it on.
- [x] 2. Test 2 (rule 1, refusal): `test_user_refuses_a_foreign_file_at_a_target`,
      run three times over the three foreign shapes (`subTest`): a regular
      file, a dangling symlink, and a symlink into a second checkout's
      `bin/<name>`. Each: rc 1, the output names the path, no platform home
      holds a render, no receipt exists, the entry is unchanged (`lstat`
      before and after), and a library fixture's expired trial is still a
      row, since the pre-flight runs before `expire_trials`. Red, pre-flight
      refusal, green. Done 2026-09-16: red `FAILED (failures=3)` (`'not a
      link to' not found`, the trial had been ended), green `OK`; C-28
      folded, a fourth `subTest` over a directory, foreign on arrival.
- [x] 3. Test 3 (rule 1, uninstall): `test_uninstall_removes_the_links_and_nothing_else`.
      `--user` over the three commands of test 1, then: an unrecorded link
      `<home>/.local/bin/sd-other` to a scratch file, the first recorded link
      retargeted to a scratch file, the second replaced by a regular file.
      `--uninstall`: the third link is gone, the retargeted link and the
      regular file are `left in place (not our link)`, `sd-other` and the
      directory remain. Red, then `prune_links` and the `link` skip in
      `prune_stale`, green. Done 2026-09-16: red `FAILED (failures=1)` (`our
      link was left`), green `OK`; C-34 folded, the relative link is the one
      removed and the regular file takes the third slot; C-33 folded, a
      `link` row without a `target` is `left in place (malformed link row)`,
      red before the code, green after.
- [x] 4. Test 4 (rule 2): `test_command_report_counts_per_command_links` in
      `StatusTests`, `_bin_with("sd", "sd-handoff", "sd-review")` and a
      `<home>/common` on PATH: two links give `2 of 3 resolve on PATH from
      this checkout` naming `sd-review`; three give `3 in bin/, 3 resolve on
      PATH from this checkout`; one link plus a foreign `sd-review` file on
      PATH keeps `shadowed by another install`. Red, per-name loop, green;
      the seven existing `command_report` tests stay green unchanged. Done
      2026-09-16: red `FAILED (failures=1)` (`'3 in bin/, 2 of 3 resolve on
      PATH from this checkout' not found in 'commands: 3 in bin/, not on
      PATH -- invoke by path (bin/sd)'`), green `OK`, the seven unchanged.
- [x] 5. Docs (rule 3): the `--user` and `--uninstall` rows of the README
      install table; the README "What it writes on a machine" list gains
      `<bin-dir>/sd-*` links, `~/.local/bin` by default; the README ownership
      paragraph says a link row records its target where a render row
      records a digest; the `command_report` docstring; `USAGE` for
      `--bin-dir`; and `AGENTS.md` "Calling Convention" (bare `sd-*` resolves
      once `--user` has run; by-path still works and is what the hooks and
      the lane brief use). `docs/lane-brief.md` keeps its by-path rule as a
      deliberate exception, with one clause saying why. The "invoke by path"
      hint stays in the none-resolve branch. Test 5, the rule's own:
      `test_the_link_rule_is_stated_where_the_no_link_rule_was` in
      `tests/test_sd_install.py` asserts the phrase "links no executable"
      is gone from `README.md`, `AGENTS.md` and the docstring, and that each
      names the link directory. Red before the edits, green after. Done
      2026-09-16: red `FAILED (failures=2)` (`README.md does not name the
      link directory`, `AGENTS.md still says it links no executable`),
      green `OK`; the docstring had changed with step 4, mutation 5 covers
      it.
- [x] 6. Coverage (rule 4): tests for the sandboxed `--bin-dir` outside the
      home under both `--user` and `--pull` (exit 2 before any pull: the
      fixture checkout's commit is unchanged), a `--bin-dir` under a
      symlinked parent that resolves outside the home (exit 2), `--dry-run`
      (`would link`), a partial link failure (`os.symlink` patched to raise on
      the second call: rc 1, the first link is gone, no receipt), and
      `command_report` with `PATH=":"` and the command in the working
      directory (`not on PATH`). `make check` with the installer gate at
      100%. Done 2026-09-16: `LinkEdgeCaseTests`, green on arrival for the
      branches steps 1-4 landed; the round-5 items red first in one commit
      (`FAILED (failures=4, errors=2)`) then green: C-30 the receipt's
      `binDir` reused by a flagless run and a new flag relocating in one run,
      C-31 `Path.mkdir` patched to raise (`error: could not link`, rc 1, no
      receipt), C-32 `PATH="."` beside `PATH=":"`, C-33 `prune_links` on a
      malformed row; C-29 the two-run recovery after the partial failure.
      Installer gate `bin/sd_install.py 951 0 368 0 100%`.
- [x] 7. Mutations, one per rule test, byte-copy revert each: drop the
      `symlink_to` call (test 1, missing link); drop the foreign refusal
      (test 2, rc); make `prune_links` unlink without the `_resolves_to`
      check (test 3, the retargeted link gone); restore the directory test
      in `command_report` (test 4, count); put "links no executable" back
      in the docstring (test 5). Done 2026-09-16: five mutations, each
      `FAILED` (1, 4, 1, 1, 1 failures), each byte copy restored with
      `diff -q` silent.

## Verification

- Steps 1-5 each quote `FAILED (failures=1)` before the fix and `OK` after.
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
- Host review: completed, five rounds, cap 5 (Development / prd and design),
  the cap spent; round 4 folded Copilot's 15 findings on PR #1000 and round
  5 its 8 findings on the round-4 push, in the ledger only.
- Additional lanes: the pack defines none; Copilot's review of the planning
  PR folds through the ledger under `design.md` "Review" when it arrives.
- Concerns: C-1 to C-9, C-12 to C-27 addressed, C-10 and C-29 rebutted
  (C-10 re-measured in C-19), C-11 parked (size, owner's call), C-28 and
  C-30 to C-35 parked on the code lane; no parked concern blocks. Ledger:
  `design.md`, "Review".
- Implementation: the owner's choices in `prd.md` are decided (note
  #2616); the code PR #1006 awaits the owner's review and merge.

## Log

- 2026-09-16 steps 1-7 ticked by lane code-969; C-28 and C-30 to C-35 folded
  where their tests land, C-29 tested as the two-run recovery; the code PR is
  the owner's to review and merge.
- 2026-09-16 review round 1 on PR #1006 (the cap round): six findings. Folded:
  the receipt's `binDir` gets the flag's containment test under `--home`
  (rc 2 before a render or a pull), a `kind: link` row without a `path` is
  reported as a malformed row, the README uninstall row and the module
  docstring describe the links as recorded. Rebutted by measurement on the
  required interpreter (3.13): non-strict `Path.resolve` returns a symlink
  loop unchanged and `shutil.which` with an empty path returns `None`, so
  neither needs a guard; both are pinned by tests.
