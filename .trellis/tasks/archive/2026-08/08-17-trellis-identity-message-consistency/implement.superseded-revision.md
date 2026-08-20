<!-- Superseded revision, preserved 2026-08-20. Written by a planning agent
     that was still running when this task was archived as won't-do; it landed
     at the live task path after the archive had moved the directory. Kept for
     reopen value only. The authoritative artifacts are implement.md in this
     directory. This task will not be implemented — see prd.md Closure. -->

# Implementation: one identity diagnosis, several renderings

Design: [`design.md`](design.md). Requirements: [`prd.md`](prd.md).

## The two-repo workflow, stated once

This task's code lands in a **different repository** than the task lives in. Get
this straight before Step 0, because every rule below follows from it.

| Repo | Role | What this task does to it |
|---|---|---|
| `~/repos/ai/Trellis` (fork, branch `main` @ `2749d3b4`, `0.6.16-sd.7`) | where the behavior belongs | **read only.** Never write. It is externally owned and currently dirty. |
| `/Users/sven/repos/platypeeps/sd-ai-command-pack` (this repo) | where the task, the patch, the staged tests, and the handoff live | commits the patch file, the staged suite, and the register update |
| `$SCRATCH` (a `mktemp -d`) | where the edits are actually made and tested | created, edited, applied to, `rm -rf`'d |
| `.trellis/scripts/` (here) | vendored copy of the fork's tree | **read only.** The PRD forbids editing it. |

The vendored tree and the fork tree are byte-identical at this base (verify in
Step 0). So the *authoring* copy is taken from `.trellis/scripts` — no reason to
read a dirty external checkout — while the patch is still expressed against the
fork's path layout and must apply there.

Only the **uptake** waits on the upstream file → release → refresh chain.
Everything below is executable here today. The task stays **open** after Step 5,
not parked, with its behavior criteria unticked.

## Step 0 — preconditions and re-enumeration

Run all of it. Reconcile any difference against `prd.md`'s table *before*
writing a line of code; a site that moved is a finding worth recording in the
handoff, not a silent adjustment.

```bash
cd /Users/sven/repos/platypeeps/sd-ai-command-pack
FORK=~/repos/ai/Trellis
T="$FORK/packages/cli/src/templates/trellis/scripts"

# P1 — the base is what the artifacts assume
git -C "$FORK" rev-parse --short HEAD                  # expect 2749d3b4 (branch main)
grep '"version"' "$FORK/packages/cli/package.json"     # expect 0.6.16-sd.7
diff -rq --exclude=__pycache__ "$T" .trellis/scripts   # expect EMPTY
```

**P1 is a gate.** Empty diff → author from `.trellis/scripts`. Non-empty →
the fork has moved: author from `$T` instead, and re-derive every line number in
`prd.md` and `design.md` before proceeding.

```bash
# P2 — nothing of this task has landed
grep -rn 'resolve_developer\|DeveloperResolution' .trellis/scripts   # expect 0 hits
```

```bash
# P3 — enumerate the reporting sites, both passes
grep -rn 'Developer not initialized\|No developer set\|Developer not set\|Not initialized' \
  .trellis/scripts --include='*.py'                    # expect 9 lines across 7 files
grep -rn 'get_developer(' .trellis/scripts --include='*.py' \
  | grep -v 'def get_developer'                        # expect 16 caller lines
grep -rn 'ensure_developer(' .trellis/scripts --include='*.py' \
  | grep -v 'def ensure_developer'                     # expect exactly 1: add_session.py:1260
```

The message grep misses `common/task_queue.py:138` (it raises, it does not
print). The caller grep cannot tell a reporter from a consumer. Both passes are
needed; classify each of the 16 callers as reporter or consumer, and only
reporters take the formatter. `prd.md` lists the consumers that must stay
untouched.

```bash
# P4 — read the pinned contract before touching any message
grep -n '\[worktree-identity\]' "$FORK/packages/cli/test/regression.test.ts"   # 11 cases, :12717-12921
sed -n '12846,12867p' "$FORK/packages/cli/test/regression.test.ts"             # the no-identity case
```

Line `:12863` is `expect(payload.error).toBe("No developer set")` — **exact
equality**. `task.py`'s JSON `error` value is frozen (`prd.md` requirement 5).
Everything else in that case is `toContain`.

## Step 1 — build the working copies

```bash
REPO=/Users/sven/repos/platypeeps/sd-ai-command-pack
SCRATCH="$(mktemp -d)"
cp -R "$REPO/.trellis/scripts" "$SCRATCH/scripts"        # or "$T" if P1 was non-empty
find "$SCRATCH/scripts" -name __pycache__ -type d -prune -exec rm -rf {} +
cp -R "$SCRATCH/scripts" "$SCRATCH/scripts.pristine"     # for run A, never edited
git -C "$SCRATCH/scripts" init -q
git -C "$SCRATCH/scripts" add -A
git -C "$SCRATCH/scripts" -c user.name=t -c user.email=t@t commit -q -m base
```

Making `$SCRATCH/scripts` a throwaway git repo is what makes Step 3's patch
prefixes plain `a/` and `b/` over identical relative paths — so the patch applies
with `git apply -p1` from inside *any* copy of the scripts tree, in this repo or
the fork. Do **not** use `git diff --no-index scripts scripts.edit`: that
produces `a/scripts/...` against `b/scripts.edit/...`, an asymmetric patch whose
strip depth is a guess and which only applies in a directory named the way the
author happened to name it.

## Step 2 — the upstream edit, in `$SCRATCH/scripts`

Order matters: items 2-6 depend on item 1.

1. **`common/paths.py`** — widen `_read_developer_file` (`:104-118`) to return a
   state (`"ok" | "missing" | "unusable"`) beside the name; add
   `DeveloperResolution` and `resolve_developer()`; keep `get_developer()`
   (`:121-160`) as `resolve_developer(repo_root).name` with its name, signature,
   docstring contract, and `str | None` return intact. Reuse `main_worktree_root`
   (`common/git.py:143-192`); do not add a second way to find the main working
   tree. A name `_safe_developer_name` (`:83-101`) rejects is `unusable`, not
   `missing`. `TRELLIS_DEVELOPER` still wins ahead of every file, with no
   diagnostic and no paths in any message.
2. **`common/developer.py`** — one shared formatter turning a
   `DeveloperResolution` into the diagnosis `design.md`'s precedence table
   specifies. `ensure_developer` (`:152`, gate at `:162-165`) calls
   `resolve_developer` instead of `check_developer` at `:161` and prints it.
   Leave `check_developer` (`common/paths.py:163-172`) and its re-export
   (`common/__init__.py:73`) alone. Leave `show_developer_info` (`:170-184`)
   alone — deliberate non-error path.
3. **The six remaining live gates**, each rendering the same diagnosis in its own
   medium, per `design.md`'s medium table: `get_developer.py:21`,
   `common/task_store.py:349-351`, `task.py:389-392`,
   `common/session_context.py:600-604` and `:819-823` (**two separate
   functions**, `:578` and `:803` — patch both), `common/task_queue.py:136-138`
   (warns on stderr on the degraded path; **never raise to carry a warning**).
4. **`task.py:359-364`** — the JSON gate. Keep both keys. Keep
   `error == "No developer set"` **byte-for-byte**: `regression.test.ts:12863`
   asserts it with `toBe`. New detail goes in `hint` or an added key. If a
   deliberate change to that value is proposed, it is a breaking test change —
   update `:12863` in the same diff and record the reason in the handoff.
   `DEVELOPER_HINT` (`common/paths.py:46-50`) stays shared; do not inline its
   text anywhere.
5. **`add_session.py`** — delete the `if not developer:` branch (`:1263-1265`).
   `ensure_developer` at `:1260` already exited, and `_safe_developer_name`
   already rejects the empty `name=` that was its one live input.
6. **`packages/cli/test/regression.test.ts`** — touch only if item 4's frozen
   value or one of the four pinned prose substrings (`No developer set`,
   `init_developer.py`, `TRELLIS_DEVELOPER`, `linked git worktree`) is
   deliberately changed. The default is: do not touch it.

Sanity check inside `$SCRATCH/scripts` before cutting the patch:

```bash
"$REPO/.venv/bin/python" -m compileall -q "$SCRATCH/scripts"
grep -rn 'resolve_developer' "$SCRATCH/scripts" | wc -l    # now non-zero
```

## Step 3 — cut the patch

```bash
PATCH="$REPO/.trellis/tasks/08-08-upstream-handoff-register/research/2026-08-17-trellis-identity-reporting.patch"
mkdir -p "$(dirname "$PATCH")"
git -C "$SCRATCH/scripts" add -A
git -C "$SCRATCH/scripts" diff --cached > "$PATCH"
head -5 "$PATCH"      # expect a/common/paths.py  b/common/paths.py
```

`research/` under `08-08-upstream-handoff-register` is this repository's
established home for upstream-owned material (ten files already live there). Do
not invent a `docs/upstream/` location.

Record the apply command **next to the patch**, in the register's research doc —
a handoff whose strip depth is a guess is not paste-ready:

```
cd <trellis-fork>/packages/cli/src/templates/trellis/scripts
git apply --check -p1 2026-08-17-trellis-identity-reporting.patch
git apply        -p1 2026-08-17-trellis-identity-reporting.patch
```

Verify that claim rather than asserting it — Step 4 run B is the verification.

## Step 4 — the staged tests

New file: this task's `research/staged_test_identity_reporting.py` — **not**
`tests/`. `Makefile:49` fails the repo gate on `skipped=[1-9][0-9]*`, and this
suite skips until uptake, so it cannot live under the gate; weakening the gate to
house a suite that waits on someone else's release is the wrong trade. Give it
`unittest.main()` and no `install` import so it runs standalone from a path, the
way `08-08`'s `research/staged_test_worktree_identity.py` does. At uptake it
moves into `tests/` and must then run with zero skips.

It must not skip on a symbol name — gate on behavior, and resolve the scripts
directory from `SD_DEVELOPER_IDENTITY_SCRIPTS` when set so Step 5 can point it at
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
| `test_an_unusable_local_file_falls_back_and_warns_from_add_session` | `add_session.py` (the only `ensure_developer` caller, `:1260`) resolves the main identity and warns naming the local file |
| `test_an_unusable_local_file_warns_from_get_developer_cli` | `get_developer.py` prints the name on stdout and the warning on stderr, exit 0 |
| `test_an_unusable_local_file_warns_from_a_reporter` | one non-`ensure_developer` reporter — `task.py list --mine`, whose identity gate is `task_queue.py:136-138` — also warns, so coverage is the gate set and not one entry point. Assert **both** halves: the warning names the local file **and** the call still succeeds (exit 0, list printed, no `ValueError`) |
| `test_every_reporting_site_agrees` | enumerates sites by grepping the resolved scripts directory, then asserts one diagnosis across all of them. Compares the count it *found* against the enumeration it *built* — never a hardcoded 8 or 9 |
| `test_the_json_site_stays_parseable` | `task.py list --json --mine` without an identity emits parseable JSON with `error` and `hint`, and `error == "No developer set"` exactly |
| `test_the_absent_case_keeps_its_pinned_substrings` | nothing-anywhere stderr still contains `No developer set`, `init_developer.py`, `TRELLIS_DEVELOPER`, `linked git worktree` |
| `test_the_dead_branch_is_gone` | source assertion: no `if not developer:` guard after `ensure_developer` in `add_session.py` |
| `test_consumers_are_unchanged` | `safe_commit.py:95`, `paths.py:209`, `paths.py:542`, `session_context.py:506`/`:736`, `init_developer.py:37`, `check_developer`, and `show_developer_info` behave as before |
| `test_pack_session_start_banners_are_unchanged` | the four pack-owned banners (`.claude`/`.gemini` `:716`, `.codex:382`, `.github/copilot:381`) still print `Developer: (not initialized)` with no identity and `Developer: <name>` with one — the pack-side half of requirement 8 |

Fixture notes:

- Build throwaway repositories under `mktemp -d`; never read or write the real
  `.trellis/.developer`.
- **Gitignore `.trellis/.developer` inside the fixture.** Committing it hands the
  file to the worktree through the checkout, and the fallback paths then pass
  without any fallback running — the false green `08-08` hit and fixed.
- `add_session.py` writes into the *current* root's
  `.trellis/workspace/<developer>`, so a fixture that needs it must run
  `init_developer.py` in the primary and commit the workspace while the identity
  file stays ignored.
- Unset `TRELLIS_DEVELOPER` in every fixture environment — it wins ahead of both
  files and would make every absent/unusable case resolve.
- macOS resolves `/var` through a symlink — compare `Path(...).resolve()`.
- `test_the_dead_branch_is_gone` reads source rather than behavior on purpose:
  upstream already rejects the empty `name=` that was the branch's only live
  input, so no behavioral test can see it.

## Step 5 — run the suite where the behavior exists

```bash
REPO=/Users/sven/repos/platypeeps/sd-ai-command-pack
STAGED="$REPO/.trellis/tasks/08-17-trellis-identity-message-consistency/research/staged_test_identity_reporting.py"
PATCH="$REPO/.trellis/tasks/08-08-upstream-handoff-register/research/2026-08-17-trellis-identity-reporting.patch"

# vendored run — against the untouched vendored tree
"$REPO/.venv/bin/python" "$STAGED" -v

# run A — unpatched pristine copy
SD_DEVELOPER_IDENTITY_SCRIPTS="$SCRATCH/scripts.pristine" "$REPO/.venv/bin/python" "$STAGED" -v

# apply, then run B — same copy, now patched
git -C "$SCRATCH/scripts.pristine" init -q 2>/dev/null || true
(cd "$SCRATCH/scripts.pristine" && git apply --check -p1 "$PATCH")
(cd "$SCRATCH/scripts.pristine" && git apply        -p1 "$PATCH")
SD_DEVELOPER_IDENTITY_SCRIPTS="$SCRATCH/scripts.pristine" "$REPO/.venv/bin/python" "$STAGED" -v

rm -rf "$SCRATCH"
```

- **Vendored run:** every behavior test skips, with reasons. This is the "not
  landed here yet" state.
- **Run A, unpatched copy:** the tests skip or fail — that is the current gap,
  and recording which is which is the evidence the task is needed.
- **Run B, patched copy:** every test passes, **zero skipped, zero failed**.

If `git apply --check` fails, fix the patch's prefixes (Step 1's git-repo trick
produces `-p1`), never guess a different `-p`. The handoff has to apply for
someone who did not build it.

Report all three runs. **A skipped test is not a passing one.**

## Step 6 — handoff, and no park

- Update **register entry 14** in
  `.trellis/tasks/08-08-upstream-handoff-register/prd.md` rather than adding a
  second entry. Two edits are needed:
  - add the patch's location and its `-p1` apply command;
  - **correct its stale framing.** Entry 14 currently inherits entry 13's
    "`0740d1d6` … untagged and not on `fork/main`" premise and cites
    `regression.test.ts:12526-12723`. Both are wrong at `2749d3b4`: the fallback
    is released in `0.6.16-sd.7` and vendored here, and the suite is at
    `:12597-12922` with the eleven cases at `:12717-12921`. Entry 13's own
    framing belongs to `08-08` — flag it, do not silently rewrite another task's
    entry beyond entry 14.
- Extend the paste-ready material in that register task's
  `research/2026-08-17-trellis-developer-identity-worktree-and-reporting.md`
  (its "Entry 14" section): the Step 0 enumeration output, the patch inline, the
  three run summaries, `design.md`'s precedence table, and the frozen-`error`
  constraint with its `regression.test.ts:12863` citation.
- Filing the task in the fork is an **operator action**. No pull request is
  opened against Trellis; `AGENTS.md:25-28` requires explicit user approval for
  that specific PR.
- Do **not** park. At this point the authoring work is done and only uptake
  remains, so the task stays open with its behavior criteria unticked. Append a
  dated note to `prd.md` recording what shipped in the handoff and that uptake
  waits on a release plus a refresh, after which the staged suite must run with
  zero skips and move into `tests/`.

## Review gates

Each must hold before the next step starts; a failure stops the step rather than
being noted and worked around.

| After | Gate |
|---|---|
| Step 0 | P1 diff empty (or base re-derived); P2 zero hits; P3 counts reconciled against `prd.md`; `:12863` read |
| Step 2 | `compileall` clean; every one of the eight live gates edited; `add_session.py:1263-1265` gone; no consumer touched; `error == "No developer set"` unchanged |
| Step 3 | `head -5 "$PATCH"` shows `a/`+`b/` over identical relative paths |
| Step 5 | run B: zero skips, zero failures; run A recorded; vendored run recorded |
| Step 6 | entry 14 updated *and* de-staled; `git -C ~/repos/ai/Trellis status --short` byte-identical to before |

## Validation

```bash
cd /Users/sven/repos/platypeeps/sd-ai-command-pack
STAGED=.trellis/tasks/08-17-trellis-identity-message-consistency/research/staged_test_identity_reporting.py
.venv/bin/python "$STAGED" -v                   # every behavior test skipped, with reasons
git status --short -- .trellis/scripts          # MUST be empty
git -C ~/repos/ai/Trellis status --short        # MUST match the pre-task snapshot
grep -rn 'resolve_developer' .trellis/scripts   # MUST still be empty here (landed upstream, not vendored)
make check                                      # passes; the staged suite is not collected
```

Take the `git -C ~/repos/ai/Trellis status --short` snapshot in Step 0 and diff
against it at the end. "I did not write to the fork" is a claim; the two
snapshots are the check.

## Rollback points

- **After Step 3:** the patch file is a single untracked/uncommitted file —
  `rm "$PATCH"`.
- **After Step 4:** the staged tests are inert (they skip, and the gate does not
  collect them) and independently committable or removable.
- **After Step 5:** only `$SCRATCH` was written; `rm -rf "$SCRATCH"` undoes it
  entirely. No copy of the fork was modified.
- **After Step 6:** revert the register entry and the research-doc section; both
  are documentation-only.
- **Whole task:** nothing changes shipped pack behavior, so there is no payload
  digest, manifest bump, or `make generate` step to undo. The complete rollback
  is deleting three files' worth of additions and reverting one entry.

## Out of scope

- The worktree fallback and its mechanism — already upstream, released in
  `0.6.16-sd.7`, vendored here; owned by `08-08`.
- Editing `.trellis/scripts/**`, or writing anything into `~/repos/ai/Trellis`.
- The four pack-owned `session-start.py` identity lines — verified unchanged
  (Step 4's last test), never modified. See `prd.md` for the reasoning.
- Opening a Trellis pull request (needs explicit per-PR approval).
