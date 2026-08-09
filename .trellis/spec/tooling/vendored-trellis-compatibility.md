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

## Wrong vs correct

- WRONG: `result = run([task_py, "current"])` then parse stdout as a path
  with no version awareness — silently misses structured fields and breaks
  when prose changes.
- CORRECT: `--json` first with the two fallbacks above; parse only
  documented fields; tolerate `current_task: null`.
- WRONG: asserting a journal section heading exists after `add_session.py`
  runs.
- CORRECT: insert-or-replace the section.
