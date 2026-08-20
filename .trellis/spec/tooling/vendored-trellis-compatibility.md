# Vendored Trellis compatibility contract

Scope/trigger: any pack wrapper that shells out to the vendored Trellis
scripts (`.trellis/scripts/task.py`, `add_session.py`), and any future
Trellis version bump. Established during the 0.6.7 → 0.6.14 upgrade
(task 08-08-trellis-upgrade, pack 0.64.29). Rewritten at the 0.6.16-sd.7
convergence (task 08-20-retire-pre-0616-trellis-compat).

## Supported floor

Pack wrappers target the vendored Trellis build **`0.6.16-sd.7`**, the value in
`.trellis/.version`. A checkout below the floor is a violation to be upgraded,
not a configuration to be supported. Wrappers MUST NOT carry branches for older
vendored runtimes.

This replaces the previous open-ended rule ("MUST work against both the current
vendored version and <=0.6.7 consumers until the fleet converges"), which named
no condition under which a compatibility branch could ever be deleted, so every
one of them accumulated. Measured 2026-08-20: this repository and all eight
fleet consumers report `0.6.16-sd.7`.

**The floor is an identity, not a range.** `0.6.16-sd.7` carries a prerelease
segment, so under semver it sorts *below* `0.6.16`. A plausible-looking check
for `>=0.6.16` therefore rejects every repository in the fleet. Compare the
recorded build string; never evaluate a range. Nothing in the pack compares
Trellis versions programmatically today, and that is the intended state.

## Signatures (vendored task.py / add_session.py, 0.6.16-sd.7)

- `task.py current` → bare task path on stdout (empty when none), exit 0.
- `task.py current --json` → one JSON object:
  `{"current_task": {"dir","id","title","status","parent","children",
  "branch","base_branch"} | null, "source": str, "stale": bool}`.
- `task.py list --json` → `{"tasks": [{"dir","id","title","status",
  "display_status","priority","assignee","parent","children","package"}]}`,
  active tasks only. No pack consumer; see the status collector note below.
- `task.py create` accepts `--base-branch`. Without it, the base resolves from
  `origin/HEAD` and falls back to the **checked-out branch**, which is wrong on
  any lane that creates a task after switching to a work branch.
- `task.py set-meta <dir> <key> <value>` writes into the `meta` object. A key
  that collides with a first-class field (`description`, `title`, …) creates a
  shadow copy in `meta` and reports success while the real field is unchanged.
  There is no `set-description`; repair such a field in `task.json` directly and
  re-run `task.py validate`.
- `add_session.py resolve_commit_subject` peels with `^{commit}` and returns
  `EMPTY_SUBJECT` (`"(empty subject)"`) for a commit with an empty message;
  `None` only when git cannot resolve the object at all.
- `add_session.py build_commit_evidence` fails before any mutation on an
  unresolvable OID — there is no placeholder path.
- `add_session.py escape_markdown_cell` collapses whitespace, then escapes `\`
  and `|`. Subjects truncate at `MAX_SUBJECT_LEN = 500`.
- `add_session.py --commit-subject <oid>=<subject>` overrides resolution for an
  OID that cannot be resolved locally.

## Wrapper contract (status collector pattern)

`scripts/sd-ai-command-pack-status.py` (template-first source under
`templates/scripts/`) resolves the active task by running `current --json` and
parsing the one documented shape. A non-zero exit or unparseable stdout means
**no active task** — not a reason to fall back to parsing prose.

The three-way fallback this section used to prescribe (parse JSON, else treat
stdout as a bare path, else re-run bare `current`) existed only for `<=0.6.7`
and was removed at the floor.

Test: `tests/test_status.py` `test_active_task_resolves_from_current_json_payload`.

The collector still enumerates `.trellis/tasks/*/task.json` from the filesystem
rather than calling `list --json`. That walk is not a version workaround: it
carries explicit symlink hardening and avoids one subprocess per repository in
fleet scope. `list --json` covers every field it reads, so the swap remains
available; it has been considered and declined rather than overlooked.

## Journal sections (add_session.py)

`_render_bullet_section` applies its `bullet_prefix` **unconditionally**, and
Testing renders with `bullet_prefix="- [OK] "`. So delegating the record-session
wrapper's Testing lines to `--test` would produce `- [OK] [WARN] flaky lane` for
a line already carrying a status marker, and `- [OK] - already bulleted` for a
pre-bulleted line. `--next-step` has the same shape with `- `.

The wrapper therefore keeps its own marker-aware normalization and its
insert-or-replace patcher (`replace_or_insert_section`), and must never fail on
a missing section heading — a section with no content is omitted entirely from
the rendered entry. Section order on insert: Testing before Next Steps.

This is a deliberate exception, not leftover compatibility code: it survives the
floor because no native equivalent exists.

## Distribution: the runtime is a fork, not the npm package

The vendored runtime is built from the fork `github.com:sdelmas/Trellis`
(`packages/cli/package.json` version `0.6.16-sd.7`). It shares the npm *name*
`@mindfoldhq/trellis` but is **never published**: npm `latest` is `0.6.15`, and
no `-sd` tag exists upstream.

Two consequences, both load-bearing:

- Any procedure written as `npx @mindfoldhq/trellis@<version>` or
  `npm install -g @mindfoldhq/trellis@latest` reaches upstream, not the fork,
  and so cannot produce or validate the vendored tree.
- A CLI installed from npm is **below this floor**. Running `trellis update`
  from it downgrades a converged repository's `.trellis/scripts/**`. Treat an
  unexpected downgrade in a refresh diff as this cause first.

The pack itself does not ship `.trellis/scripts/**` — `manifest.json` sets
`requiresTrellis: true`, a boolean precondition with no version component, and
the consumer's own CLI writes that tree. So the pack cannot correct a
below-floor consumer by installing; the consumer's CLI has to be the fork.

The consumer-facing install instructions still say
`npm install -g @mindfoldhq/trellis@latest`. That is a known, filed defect —
see parked task `07-09-trellis-version-compatibility` — not an endorsement.

## Upgrade procedure (validated 0.6.14 → 0.6.16-sd.7 path)

1. Official `trellis update` only — never a manual scripts file swap; the
   hash manifest `.trellis/.template-hashes.json` (gitignored, local)
   drives conflict classification and platform scope.
2. Run it from a **built fork checkout**, not from npm (see above). Gate before
   `--force` with dry-run classification plus a same-version rescan in a clone
   to prove pristine-vs-modified, and a sandbox-clone apply for the expected
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

- WRONG: `result = run([task_py, "current"])` then parse stdout as a path —
  silently misses structured fields and breaks when prose changes.
- CORRECT: `current --json`; parse only documented fields; tolerate
  `current_task: null`. A non-zero exit or unparseable stdout means no active
  task — do not fall back to prose parsing.
- WRONG: asserting a journal section heading exists after `add_session.py`
  runs.
- CORRECT: insert-or-replace the section.
- WRONG: re-rendering a commit-table cell in the wrapper after
  `add_session.py` has written it (`subject.replace("|", "\\|")`) — that
  escapes pipes but leaves backslashes raw, preserves whitespace runs that can
  break the row, and skips the 500-character truncation.
- CORRECT: pass the OIDs and let `escape_markdown_cell` render them. Assert the
  requested OIDs are present; do not rewrite their cells.
- WRONG: `task.py create` followed by `set-base-branch` to correct the base on
  a lane that already switched branches — a window exists in which `task.json`
  records the work branch as its base.
- CORRECT: `task.py create --base-branch <default-branch>`. `set-base-branch`
  remains the repair for an already-created task.
- WRONG: `task.py set-meta <dir> description "..."` to fix a task description —
  reports success, writes `meta.description`, leaves the real field stale.
- CORRECT: edit `task.json` directly, then `task.py validate`.
