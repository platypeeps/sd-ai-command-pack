# Vendored Trellis compatibility contract

Scope/trigger: any pack wrapper that shells out to the vendored Trellis
scripts (`.trellis/scripts/task.py`, `add_session.py`), and any future
Trellis version bump. Established during the 0.6.7 → 0.6.14 upgrade
(task 08-08-trellis-upgrade, pack 0.64.29).

## Version-spread reality

The pack repo and each fleet consumer upgrade Trellis independently. A pack
wrapper MUST work against both the current vendored version and <=0.6.7
consumers until the fleet converges. Never assume the pack repo's Trellis
version when the wrapper runs with `--repo`/fleet scope.

## Signatures (vendored task.py, 0.6.14)

- `task.py current` → bare task path on stdout (empty when none), exit 0.
- `task.py current --json` → one JSON object:
  `{"current_task": {"dir","id","title","status","parent","children",
  "branch","base_branch"} | null, "source": str, "stale": bool}`.
- `task.py list --json` → machine-readable list (no pack consumer yet).
- <=0.6.7 rejects `--json` with an argparse error, exit 2.

## Wrapper contract (status collector pattern)

`scripts/sd-ai-command-pack-status.py` (template-first source under
`templates/scripts/`) resolves the active task as:

1. Run `current --json`; on exit 0 parse JSON and read `current_task.dir`.
2. Exit 0 but non-JSON stdout → treat stdout as the bare path (variant that
   ignores unknown flags).
3. Nonzero exit → re-run bare `current` and parse the path.

Tests: `tests/test_status.py`
`test_active_task_resolves_from_current_json_payload` and
`test_active_task_falls_back_when_current_rejects_json_flag`.

## Journal sections (add_session.py)

- <=0.6.7 always scaffolds `### Testing` / `### Next Steps` (with
  placeholder defaults such as `DEFAULT_TESTING`).
- >=0.6.14 omits any section with no content and has no `DEFAULT_TESTING`
  constant.
- The record-session wrapper therefore uses insert-or-replace
  (`replace_or_insert_section`) and must never fail on a missing section
  heading. Section order on insert: Testing before Next Steps.

## Upgrade procedure (validated 0.6.14 path)

1. Official `trellis update` only — never a manual scripts file swap; the
   hash manifest `.trellis/.template-hashes.json` (gitignored, local)
   drives conflict classification and platform scope.
2. Gate before `--force`: dry-run classification + a same-version rescan
   (`npx @mindfoldhq/trellis@<current> update --dry-run` in a clone proves
   pristine-vs-modified), and a sandbox-clone apply for the expected
   surface (copy the gitignored hash manifest into the clone first).
3. Protected gitignored files (`.trellis/.developer`, `.current-task`)
   are invisible to `git status`; verify via recorded presence/hash.
4. Acceptance: `.trellis/scripts` byte-identical to release templates,
   post-apply `trellis update --dry-run` reports zero pending changes,
   `make release-prep` green (shipped-payload wrappers changed → manifest
   version + changelog + regenerated candidate ledger).

## Testing a fix that lives upstream and is not released yet

Scope/trigger: a defect whose fix belongs in `.trellis/scripts/**` (vendored
Trellis, owned by the fork) and already exists upstream on an untagged branch.
Established by task `08-08-developer-identity-not-in-worktrees` (the developer
identity that a linked worktree never inherits).

The suite that proves the fix cannot live in `tests/`: `Makefile:49` fails the
gate on **any** skip
(`grep -Eq 'skipped=[1-9][0-9]*' unittest-output.log`), and such a suite skips
until the release lands. Weakening that grep is not the fix. Split it:

- the behavioral half goes to the owning task's
  `research/staged_test_<topic>.py`, resolving its scripts directory from an
  env var (`SD_..._SCRIPTS`) so one file runs against both the vendored tree and
  a `mktemp -d` copy of upstream's `scripts/`;
- the half that never skips — the repository-side fact the whole analysis rests
  on — stays in `tests/`. For the identity task that is one assertion:
  `git check-ignore -v .trellis/.developer` exits 0.

Record both runs in the handoff register entry, reported as two:
`OK (skipped=N)` against vendored, `OK` with 0 skips against upstream. The
zero-skip staged run is the resume trigger; name that file in `blockedOn`, never
the `tests/` half, which already reports zero skips today and would fire the
trigger immediately.

### Gate the skip on behavior, not on a symbol name

- WRONG: `if not hasattr(paths, "main_worktree_root"): skipTest(...)` — the name
  can exist while the resolver still ignores it.
- CORRECT: build a throwaway primary+worktree fixture, resolve through the real
  CLI, and skip unless it returns the primary's name.
- Scrub `TRELLIS_DEVELOPER` from the child environment once, at module level:
  the resolver consults it ahead of every file, so an operator who exports it
  makes the probe resolve their own name and skips the suite for an unrelated
  reason. Only the test about the override puts it back.

### Two fixture facts that cost a debugging round each

- **Gitignore `.trellis/.developer` inside the fixture** and commit the seed
  before writing it. A committed identity is handed to the worktree by the
  checkout, so every fallback test passes with no fallback running.
- `get_workspace_dir` is `repo_root / .trellis/workspace/<developer>`, so
  `add_session.py` in a worktree writes into *that worktree's* workspace. A
  realistic fixture runs `init_developer.py` in the primary and commits the
  workspace while the identity stays ignored.

### What such a suite cannot prove

`_read_developer_file` swallows `OSError` and returns `None`, so unreadable
files do not prove non-consultation: a resolver that reads both files and then
prefers the environment passes the same assertions. Claim only result
independence — the answer does not depend on the files' contents or readability
— and say that proving non-consultation needs syscall tracing.

## Wrong vs correct

- WRONG: `result = run([task_py, "current"])` then parse stdout as a path
  with no version awareness — silently misses structured fields and breaks
  when prose changes.
- CORRECT: `--json` first with the two fallbacks above; parse only
  documented fields; tolerate `current_task: null`.
- WRONG: asserting a journal section heading exists after `add_session.py`
  runs.
- CORRECT: insert-or-replace the section.
