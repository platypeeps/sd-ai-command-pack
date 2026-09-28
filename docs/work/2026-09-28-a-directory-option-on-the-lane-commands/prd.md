---
title: A -C directory option on the lane commands
created: 2026-09-28
---
# PRD — a directory option on the lane commands

## Problem

A session's permission layer approves an `sd-ship merge` line through an allow
rule, `Bash(sd-ship:*)`, and an allow rule matches a whole command line. A
session that spans repositories has to write `cd <checkout> && sd-ship merge …`,
and that compound line is not the allowed command: it goes to the auto-mode
classifier, which denied two such merges on 2026-09-28 while the bare form in
the session's own checkout ran unasked. The operator ran those merges by hand.

R10-D6 forbids the option that would fix this: an `sd-*` command resolves its
repository from the working directory and takes no path to another one, so
that a session cannot be pointed at another checkout. The rule's premise was
that the checkout is the boundary a session stays inside. The permission layer
is that boundary now, and it reads the command line: a `-C <dir>` is visible
there, and a `cd &&` compound is where the reach hides. The rule as written
makes the visible form impossible and leaves the hidden one.

## Requirements

1. `sd-ship`, `sd-check`, `sd-review`, `sd-review-ack` and `sd-pr-state` take
   a global `-C <dir>` before any other argument, spelled as `git -C` is: the
   command changes its working directory to `<dir>` once, before anything
   resolves the repository, and everything after that reads the working
   directory as it does today. No long spelling; `--directory` and the other
   names R10-D6 bans stay banned.
2. A `<dir>` that does not exist, or is not a directory, is a usage error
   naming it: exit code 2, or `sd-ship`'s usual refusal object.
3. `sd-review`'s `setup-github` dispatch accepts a leading `-C <dir>`.
4. R10-D6 is amended, not repealed: its subject names the five lane commands'
   `-C` as the one exception and says why. `tests/test_verb_inventory.py` keeps
   banning the repository-path spellings everywhere and also fails when `-C`
   appears on any other file under `bin/`. `repo_root(args.` stays banned.
5. The three skills that teach the rule say it as amended:
   `skills/sd-check/SKILL.md`, `skills/sd-ship/SKILL.md` and
   `skills/sd-review/SKILL.md`.
6. `CHANGELOG.md` records the change under Unreleased with this item's id.

Out of scope: the other cwd-bound commands (`sd-docs-lint`, `sd-rules`,
`sd-status`, `sd-note`, `sd-handoff`, `sd work`, the research and fleet
verbs). None of them was blocked; a second item adds `-C` where a session
shows the need.

## Acceptance criteria

- [x] `sd-check -C <other checkout> --dry-run --json` from an unrelated
      directory reports that checkout's root; without `-C` it reports the
      current one. (`tests/test_lane_chdir.py`; and from the ui-design
      checkout, `sd-review-ack -C ~/repos/system --pr 7 --check --json`
      reported `"root": "/Users/sven/repos/system"`.)
- [x] Each of the five commands with `-C <empty non-repository directory>`
      fails with the "not inside a git repository" message naming that
      directory, which proves the change of directory happened before
      resolution. (`tests/test_lane_chdir.py`.)
- [x] Each of the five with `-C <missing path>` fails naming the path.
      (`tests/test_lane_chdir.py`.)
- [x] `tests/test_verb_inventory.py` passes, and adding `-C` to a sixth
      command turns it red. (`LANE_COMMANDS` is the allow-list; a sixth file
      declaring `-C` is an offender.)
- [ ] A bare `sd-ship -C <checkout> merge …` from another repository's
      session runs under `Bash(sd-ship:*)` without a prompt. Operator-observed:
      a session cannot verify its own permission layer.
- [x] `make check` passes. (Second run, exit 0. The first found two more
      enforcement tests: `tests/test_sd_status.py`'s parser scan, which now
      allows `-C` on `sd-pr-state` for the same reason, and the review-lane
      line cap in `tests/test_sd_review_boundary.py`, raised 3702 to 3710
      with the spend written down.)

## References

- `bin/sd_rules.py`, R10-D6.
- `tests/test_verb_inventory.py`, `REPO_PATH_OPTIONS` and
  `test_no_command_accepts_a_repository_path`.
- `bin/sd_lib.py`, `repo_root`.
- ui-design session of 2026-09-28: PR #9 merged by the bare form; system PR #7
  was denied twice in the `cd &&` form.

## Log

- 2026-09-28 created; the operator chose the five lane commands over
  `sd-ship` alone.
- 2026-09-28 built on `feat/lane-chdir`. The auto-mode classifier denied
  four of the edits as a bypass until the operator added an `Edit` allow
  rule for the pack: a change to the tools the permission boundary runs
  reads, to it, as reaching around it.
- 2026-09-28 finding: an uncommitted edit to `bin/sd-ship`, `bin/sd-review`,
  `bin/sd-check` or `bin/sd_lib.py` changes `sd_ship_bindings.review_binding`
  for every repository whose installed commands are this checkout's
  symlinks. system PR #7's merge refused "review tools or repository policy
  changed after review" until this work was stashed. Land or stash pack tool
  changes before merging elsewhere; a landed change moves the binding for
  every open record, which then needs one more review pass.
