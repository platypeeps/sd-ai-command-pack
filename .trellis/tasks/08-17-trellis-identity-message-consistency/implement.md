# Implementation: one identity diagnosis, several renderings

Design: [`design.md`](design.md). Every behavior change lands **upstream**, in
the Trellis fork. This repository commits the patch, the handoff entry, and the
staged tests. Do not edit `.trellis/scripts/**` here, and do not write anything
into `~/repos/ai/Trellis` — that checkout is externally owned and currently
dirty. Read it and copy out of it; nothing else.

Only the *uptake* is blocked on the release chain
`08-08-developer-identity-not-in-worktrees` waits for; everything below is
executable here now. The task stays open after Step 4 — not parked — with its
behavior criteria unticked until a vendored refresh.

## Step 0 — re-enumerate before anything else

The site list in `prd.md` and `design.md` is a snapshot of `454046ca`. Rebuild
it, both passes, and reconcile any difference before writing code:

```bash
T=~/repos/ai/Trellis/packages/cli/src/templates/trellis/scripts
git -C ~/repos/ai/Trellis rev-parse --short HEAD        # the patch base
grep -n '\[worktree-identity\]' ~/repos/ai/Trellis/packages/cli/test/regression.test.ts
                                                        # the wording already pinned
grep -rn 'init_developer.py\|No developer set\|Developer not initialized' \
  "$T" --include='*.py'                                 # reporters that print
grep -rn 'get_developer(' "$T" --include='*.py' | grep -v 'def get_developer'
                                                        # every caller
```

The second pass exists because `common/task_queue.py:138` raises instead of
printing, so the first pass cannot see it. Classify each caller as reporter or
consumer; only reporters take the formatter. A new site found here is a finding
worth recording in the handoff, not a silent addition.

## Step 1 — the patch

Write a real patch file — a diff that applies to
`packages/cli/src/templates/trellis/scripts/` on the branch head from Step 0 —
and store it as
`.trellis/tasks/08-08-upstream-handoff-register/research/2026-08-17-trellis-identity-reporting.patch`,
in this repository's established home for upstream-owned material. Do not invent
a `docs/upstream/` location.

Produce it without touching the fork: `cp -R` the whole `scripts/` tree into a
`mktemp -d` twice — `scripts/` left pristine and `scripts.edit/` edited — then
diff in that order, so the patch's `a/` side is the tree it will later be applied
to:

```bash
PATCH="$PWD/.trellis/tasks/08-08-upstream-handoff-register/research/2026-08-17-trellis-identity-reporting.patch"
(cd "$SCRATCH" && git diff --no-index scripts scripts.edit) > "$PATCH"   # exit 1 = differences
```

That writes `a/scripts/...` and `b/scripts.edit/...` headers, so the patch applies
with **`-p2` from inside `$SCRATCH/scripts`** — verified against this exact
command, not assumed. Diffing the other way round (`scripts.edit scripts`) makes
an inverted patch that only applies inside `scripts.edit`, which is the mistake
worth naming. Record the apply command next to the patch; a handoff whose strip
depth is a guess is not paste-ready.

1. `common/paths.py` — widen `_read_developer_file` to return a state
   (`"ok" | "missing" | "unusable"`) beside the name, add `DeveloperResolution`
   and `resolve_developer()`, and keep `get_developer()` as
   `resolve_developer(repo_root).name` with its signature, docstring contract,
   and `str | None` return. Reuse `main_worktree_root` from `common/git.py`;
   do not add a second way to find the main working tree. A name
   `_safe_developer_name` rejects is `unusable`.
2. `common/developer.py` — one formatter turning a `DeveloperResolution` into the
   diagnosis the design's table specifies. `ensure_developer` (`:161-165`) calls
   `resolve_developer` instead of `check_developer` and prints it.
3. The remaining reporters, each rendering the same diagnosis in its own medium:
   `get_developer.py:21`, `common/task_store.py:325`, `task.py:380`,
   `common/session_context.py:602` and `:821` (separate functions, `:578` and
   `:803` — patch both), `common/task_queue.py:138`. With `ensure_developer` and
   `task.py:351` that is eight gates, not seven.
4. `task.py:351` — keep the JSON schema. Its `error`/`hint` keys are parsed by
   `packages/cli/test/regression.test.ts:12655-12676`. That same suite —
   eleven `[worktree-identity]` cases at `:12526-12723` — also pins **prose**
   substrings for the nothing-anywhere case (`No developer set`,
   `init_developer.py`, `TRELLIS_DEVELOPER`, `linked git worktree`), so read it
   before rewording anything and update it in the same diff when a change is
   intended. `DEVELOPER_HINT` (`common/paths.py:46-50`) is already shared by
   four sites; keep it shared rather than inlining its text.
5. `add_session.py` — delete the `if not developer:` branch (`:1108-1110`);
   `ensure_developer` at `:1105` already exited.

Order: 2-5 depend on 1.

## Step 2 — the staged tests

New file `research/staged_test_identity_reporting.py` in this task directory —
**not** `tests/`. `Makefile:49` fails the repo gate on `skipped=[1-9]`, and this
suite skips until an upstream release lands, so it cannot live under the gate;
weakening the gate to house a suite that waits on someone else's release is the
wrong trade. Give it
`unittest.main()` and no `install` import so it runs standalone from a path, the
way `08-08`'s `research/staged_test_worktree_identity.py` does. At uptake it
moves into `tests/` and must then run with zero skips.

It must not skip on a symbol name — gate on the behavior, and resolve the scripts
directory from `SD_DEVELOPER_IDENTITY_SCRIPTS` when set so Step 3 can point it at
a patched copy:

```python
def require_shared_diagnosis(self, scripts):
    """Skip only while the resolved tree still reports per-site messages."""
    if not self.reports_shared_diagnosis(scripts):
        self.skipTest(
            "resolved Trellis scripts still emit per-site identity messages; "
            "upstream handoff pending"
        )
```

One test per acceptance criterion:

| Test | Asserts |
|---|---|
| `test_no_identity_anywhere_names_the_init_command` | message contains `init_developer.py` when no file exists |
| `test_an_unusable_main_copy_names_the_path_it_tried` | the exact path appears and `init_developer.py` does not |
| `test_an_unusable_local_file_falls_back_and_warns_from_add_session` | `add_session.py` (the only `ensure_developer` caller, `:1105`) resolves the main identity and warns naming the local file |
| `test_an_unusable_local_file_warns_from_get_developer_cli` | `get_developer.py` prints the name on stdout and the warning on stderr, exit 0 |
| `test_an_unusable_local_file_warns_from_a_reporter` | one non-`ensure_developer` reporter — `task.py list --mine`, whose identity gate is `task_queue.py:136-138` — also warns, so the coverage is the gate set and not one entry point. Assert both halves: the warning names the local file **and** the call still succeeds (exit 0, the task list printed, no `ValueError`). A degraded resolution must not become a failure to carry its own warning |
| `test_every_reporting_site_agrees` | enumerates sites by grepping the resolved scripts directory, then asserts one diagnosis across all of them |
| `test_the_json_site_stays_parseable` | `task.py --json --mine` without an identity emits parseable JSON with `error` and `hint` |
| `test_the_absent_case_keeps_its_pinned_substrings` | nothing-anywhere stderr still contains `No developer set`, `init_developer.py`, `TRELLIS_DEVELOPER`, `linked git worktree` — requirement 1's removal is scoped to the unusable-file case |
| `test_the_dead_branch_is_gone` | source assertion: no `if not developer:` guard after `ensure_developer` in `add_session.py` |
| `test_consumers_are_unchanged` | `safe_commit`, `paths:209`, `session_context:506`/`:736`, and `show_developer_info` behave as before |

Fixture notes:

- Build throwaway repositories under `mktemp -d`; never read or write the real
  `.trellis/.developer`.
- **Gitignore `.trellis/.developer` inside the fixture.** Committing it hands the
  file to the worktree through the checkout, and the fallback paths then pass
  without any fallback running — the false green `08-08` hit and fixed.
- `add_session.py` writes into the *current* root's
  `.trellis/workspace/<developer>`, so a fixture that needs it must run
  `init_developer.py` in the primary and commit the workspace while the identity
  stays ignored.
- macOS resolves `/var` through a symlink — compare `Path(...).resolve()`.
- `test_the_dead_branch_is_gone` reads source rather than behavior on purpose:
  upstream already rejects the empty `name=` that was the branch's only live
  input, so no behavioral test can see the branch.

## Step 3 — run the suite where the behavior exists

```bash
REPO="$PWD"
STAGED="$REPO/.trellis/tasks/08-17-trellis-identity-message-consistency/research/staged_test_identity_reporting.py"
PATCH="$REPO/.trellis/tasks/08-08-upstream-handoff-register/research/2026-08-17-trellis-identity-reporting.patch"
SCRATCH="$(mktemp -d)"
cp -R ~/repos/ai/Trellis/packages/cli/src/templates/trellis/scripts "$SCRATCH/scripts"
SD_DEVELOPER_IDENTITY_SCRIPTS="$SCRATCH/scripts" .venv/bin/python "$STAGED" -v   # run A
(cd "$SCRATCH/scripts" && git apply --check -p2 "$PATCH")
(cd "$SCRATCH/scripts" && git apply -p2 "$PATCH")
SD_DEVELOPER_IDENTITY_SCRIPTS="$SCRATCH/scripts" .venv/bin/python "$STAGED" -v   # run B
rm -rf "$SCRATCH"
```

`-p2` strips `a/scripts/`, the prefix Step 1's diff order produces, and run B
applies it to the pristine copy run A just exercised. If `--check` fails on strip
depth, fix the patch's prefixes rather than guessing a different `-p`: the handoff
has to apply for someone who did not build it.

- **Run A, unpatched upstream:** the tests skip or fail — that is the current
  gap, and recording which is which is the evidence the task is needed.
- **Run B, patched:** every test passes, none skipped.

`git status --short -- .trellis/scripts` must print nothing afterwards, and
`git -C ~/repos/ai/Trellis status --short` must be unchanged from before.

## Step 4 — handoff, and no park

- Register entry 14 already names this defect, its resolution class (a Trellis
  fork task to file), and the eight gates with their media. Update it with the
  patch's location once Step 1 produces it, rather than adding a second entry.
- Extend the paste-ready material in that register task's
  `research/2026-08-17-trellis-developer-identity-worktree-and-reporting.md`
  (its "Entry 14" section): the enumeration output, the patch inline, run A and
  run B summary lines, and the design's precedence table.
- Filing the task in the fork is an **operator action**. No pull request is
  opened against Trellis; `AGENTS.md:25-28` requires explicit user approval for
  that specific PR.
- Do **not** park: at this point the authoring work is done and only uptake
  remains, so the task stays open with its behavior criteria unticked. Append a
  dated note to `prd.md` recording what shipped in the handoff and that uptake
  waits on a release plus a refresh, after which the staged suite must run with
  zero skips and move into `tests/`.

## Validation

```bash
STAGED=.trellis/tasks/08-17-trellis-identity-message-consistency/research/staged_test_identity_reporting.py
.venv/bin/python "$STAGED" -v                   # every test skipped, with reasons
git status --short -- .trellis/scripts          # empty
make check                                      # unaffected: the suite is not collected
```

Report three runs, not one: the vendored run (all behavior tests skipped), run A,
and run B. A skipped test is not a passing one.

## Rollback points

- After Step 2: the staged tests are inert (they skip, and the gate does not
  collect them) and independently committable.
- After Step 3: only a `mktemp -d` copy was touched; `rm -rf` undoes it.
- Nothing here changes shipped pack behavior, so there is no payload digest,
  manifest bump, or `make generate` step.

## Out of scope

- The worktree fallback and its mechanism — already upstream, owned by `08-08`.
- Editing `.trellis/scripts/**`, or writing into `~/repos/ai/Trellis`.
- Opening a Trellis pull request (needs explicit per-PR approval).
