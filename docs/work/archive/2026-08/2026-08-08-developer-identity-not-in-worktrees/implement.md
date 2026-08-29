# Implementation: developer identity resolves from the main working tree

Design: [`design.md`](design.md). The behavior change lands **upstream** in the
vendored Trellis tree, and it is already written there, so this task writes no
patch: it commits the staged tests, the handoff register entry, and the park. Do not edit `.trellis/scripts/**` here — see the design's
ownership section for why a local edit becomes a prompt every operator must
answer correctly forever, and is dropped outright by the `--force` refresh this
repository has actually used.

## Step 0 — red check first

Prove the failure in this checkout before writing anything, from a scratch
worktree in a directory this step creates — never in an existing checkout.
`SCRATCH` is not set by the repository or the workflow; define it first, or an
unset expansion writes to `/wt-identity`:

```bash
SCRATCH="$(mktemp -d)"
git -C "$PWD" worktree add "$SCRATCH/wt-identity" --detach HEAD
(cd "$SCRATCH/wt-identity" && python3 .trellis/scripts/get_developer.py; echo "exit=$?")
```

Already run once during planning, at `c08d2bda`: the worktree printed
`Developer not initialized` with `exit=1` while the primary checkout printed
`sdelmas`. Re-run it at implementation time against the then-current head rather
than trusting this record. The plumbing details that run also recorded belonged
to the withdrawn design; do not re-derive them. Remove the worktree with
`git worktree remove "$SCRATCH/wt-identity"` when done, then `rm -rf "$SCRATCH"`;
a leftover worktree is exactly the recovery artifact `sd-status` reports.

## Step 1 — check upstream before writing anything

The fork already implements requirement 1 (`0740d1d6` on
`chore/task-backlog-2026-08`; see the design's "What upstream already has").
Confirm that against the source rather than trusting this note, because
everything below is scoped by it:

```bash
T=~/repos/ai/Trellis/packages/cli/src/templates/trellis/scripts
sed -n '121,160p' "$T/common/paths.py"        # get_developer, with the fallback
sed -n '143,192p' "$T/common/git.py"          # main_worktree_root, to its returns
git -C ~/repos/ai/Trellis tag --contains 0740d1d6      # expect: empty
git -C ~/repos/ai/Trellis branch -r --contains 0740d1d6
```

That checkout is externally owned: read it, copy out of it, never write into it
and never run anything that mutates it.

If the fallback is present and untagged, the deliverable is what Step 1b through
Step 4 describe: the staged tests, the register entry, and the park. If it has
since been released, stop and re-plan — the task's shape changes again, and a
vendored refresh may close it outright.

## Step 1b — none: the residual patch moved out

The reporting half — requirements 3, 4, 5, and 7, eight gates in four media —
moved to `08-17-trellis-identity-message-consistency` on 2026-08-17, with its own patch procedure and tests. This task
writes no upstream patch at all. Its deliverable is the verification above, the
staged tests below, the register entry, and the park.

## Step 2 — the staged tests

Two files, because this repository's gate forbids a skip. `Makefile:49` fails the
whole run on `skipped=[1-9]`, and a suite waiting on someone else's release skips
by construction — so the behavioral suite is staged **outside** `tests/`, as
`research/staged_test_worktree_identity.py` in this task directory, with
`unittest.main()` and no `install` import so it runs standalone from a path. The
one assertion that holds today and forever, `test_the_identity_stays_ignored`,
stays in `tests/test_developer_identity.py` where the gate collects it. Weakening
the skip gate to house the rest would trade a real deterministic check for a
parked task's convenience; at uptake the staged file moves into `tests/` and runs
with zero skips.

Every test that needs the new behavior guards on **the behavior**, never on the
symbol:

```python
def require_worktree_fallback(self, paths):
    """Skip only while the vendored resolver still cannot see the primary."""
    primary, worktree = self.make_primary_and_worktree(name="probe-dev")
    if paths.get_developer(worktree) != "probe-dev":
        self.skipTest(
            "vendored Trellis resolver does not fall back to the main working "
            "tree; upstream handoff pending"
        )
```

A symbol probe (`getattr(paths, "resolve_developer", None)`) would be wrong
here: the design accepts that upstream may implement this differently — inside
`get_developer` itself, under another helper name — and a symbol gate would
then skip every behavioral test forever while the behavior was actually
present. Gating on a disposable fixture makes the suite go live the moment any
implementation lands, whatever it is called, and it still cannot produce a
false green: the probe's failure mode is `skipTest`, never a pass.

One test per acceptance criterion this task kept. Load the
resolver through one indirection so Step 2.5 can point the same suite at a
patched copy: resolve the vendored scripts directory from
`SD_DEVELOPER_IDENTITY_SCRIPTS` when that variable is set, else from
`.trellis/scripts`.

The table:

| Test | Asserts |
|---|---|
| `test_a_fresh_worktree_resolves_the_primary_identity` | worktree created, nothing copied, `get_developer.py` prints the primary name, exit 0 |
| `test_a_fresh_worktree_emits_no_diagnostic` | same run's stderr is empty — the case that used to fail now simply works |
| `test_a_local_identity_takes_precedence` | worktree with its own readable `.developer` resolves that name, not the primary's |
| `test_an_unusable_local_file_falls_back` | local file present but missing `name=` (and, separately, unreadable) resolves the primary name instead of `None`. The *warning* half of the old criterion moved to `08-17-trellis-identity-message-consistency` |
| `test_the_environment_override_outranks_both_files` | `TRELLIS_DEVELOPER` wins over a readable local file and over the primary's, and the answer is independent of those files' contents and of whether they are readable at all. It does **not** assert that no read occurred: `_read_developer_file` swallows `OSError`, so a resolver that read both and then preferred the environment passes too. Proving non-consultation needs syscall tracing, which this suite does not do |
| `test_add_session_runs_in_a_fresh_worktree` | `add_session.py --no-commit` end to end in a worktree — the path that actually blocks finish-work |
| `test_get_developer_itself_resolves_through_the_fallback` | `paths.get_developer(worktree_root)` returns the primary name without going through any CLI |
| `test_an_empty_name_is_unusable` | a local `.developer` containing `name=` (and one containing `name=   `) falls back to the primary identity instead of resolving to `""`, and `check_developer` reports uninitialized when there is no fallback |
| `test_moved_and_relative_worktrees_still_resolve` | `git worktree move` and `git worktree add --relative-paths` both keep resolving the primary identity; skip the relative case when the local Git predates 2.48 |

Fixture notes:

- Build the primary checkout as a temporary Git repository with its own
  `.trellis/.developer`; do not read the real one, and never write into the
  developer's actual `.trellis/`.
- **Gitignore the identity inside the fixture.** A fixture that commits
  `.trellis/.developer` hands it to the worktree through the checkout, and every
  test then passes with no fallback involved — the exact false green this suite
  exists to prevent. Assert `git check-ignore` on it while building the fixture.
- `get_workspace_dir` is `repo_root / .trellis/workspace/<developer>`, so
  `add_session.py` in a worktree writes into *that worktree's* workspace. Mirror
  the real repository: run `init_developer.py` in the primary and commit the
  workspace (Git carries it) while the identity stays ignored. Hand-writing
  `.developer` without a journal makes `add_session.py` exit 1 with
  "no journal file to append to".
- Probe `--relative-paths` support by matching `relative-paths`, not
  `--relative-paths`: Git prints the negatable spelling `--[no-]relative-paths`,
  so the stricter match silently skips the relative case on a Git that has it.
- macOS resolves `/var` through a symlink, so compare `Path(...).resolve()` on
  both sides of every path assertion.
- Remove each worktree in `addCleanup`, and prefer
  `git worktree remove --force` there so a failed assertion cannot strand one.

`test_the_identity_stays_ignored` — the one in `tests/` — needs no skip guard: it
holds today and must keep holding.

## Step 2.5 — run the suite where the behavior exists

The tests skip against the vendored tree, so on their own they validate nothing.
Run them against a copy of upstream's source, which already has the fallback.
Never in `.trellis/scripts/**`, and never inside the fork:

```bash
STAGED=.trellis/tasks/08-08-developer-identity-not-in-worktrees/research/staged_test_worktree_identity.py
SCRATCH="$(mktemp -d)"
cp -R ~/repos/ai/Trellis/packages/cli/src/templates/trellis/scripts "$SCRATCH/scripts"
SD_DEVELOPER_IDENTITY_SCRIPTS="$SCRATCH/scripts" .venv/bin/python "$STAGED" -v
rm -rf "$SCRATCH"
```

Every test in this task's table must pass there, none skipped. That run is the
independent check on `0740d1d6`: a failure is a finding worth more than the rest
of this task, because it would mean the fix this repository is waiting for does
not do what it claims.

A smaller version of it already ran during planning, directly against
`paths.get_developer`: a linked worktree resolved the primary `probe-dev`, a local
`name=` with an empty value and a `.developer` with no `name=` line both fell back
to `probe-dev`, and a valid local `name=local-dev` won. No warning was emitted for
the unusable local files, which is the gap `08-17-trellis-identity-message-consistency` owns.

`git status --short -- .trellis/scripts` must print nothing afterwards, and
`git -C ~/repos/ai/Trellis status --short` must be unchanged from before.

## Step 3 — the handoff, through the existing register

This repository already has a convention for upstream-owned work, and it is not
a `docs/` folder: `.trellis/tasks/08-08-upstream-handoff-register` holds a
numbered register whose entries each resolve to exactly one of a filed task in
the Trellis fork (`~/repos/ai/Trellis`), an upgrade-delivered fix, or a
deliberately kept pack workaround, with the original PRDs preserved verbatim
under that task's `research/`. Use it; do not invent a second location.

- Add the next numbered register entry naming this defect, its resolution class,
  and where each half now lives. The class is split, and the entry must say so:
  requirements 1, 2, and 6 are **already fixed upstream and awaiting release**
  (`0740d1d6`, untagged, on `chore/task-backlog-2026-08` only), while
  requirements 3, 4, 5, and 7 became `08-17-trellis-identity-message-consistency` — an open Trellis fork task with its
  own patch, covering eight reporting gates in four media rather than the two this
  PRD originally named.
- Put the paste-ready material in the register task's `research/`, matching how
  the nine absorbed handoffs are stored: the Step 0 reproduction with its exact
  output, the Step 1 evidence that the fallback is already implemented and
  untagged, the Step 2.5 run summary, and a pointer to `08-17-trellis-identity-message-consistency` for the reporting
  patch.

Nothing needs filing upstream for *this* task — the fix is already written there.
What the entry records is a release-and-uptake dependency. Filing the reporting
task in the fork is an **operator action** owned by the other task; no pull
request is opened against Trellis here, and per `AGENTS.md:25-28` that would need
the user's explicit approval for that specific PR.

## Step 4 — park the task

The acceptance criteria describe behavior this repository cannot exhibit until
a vendored refresh. Park rather than archive:

- Append a dated park note to `prd.md` naming the upstream dependency — a
  Trellis release containing `0740d1d6`, then a vendored refresh — the handoff
  path, and what resumes the task: a refresh after which **the staged suite runs
  against the vendored tree with zero skips**. Name that file, not
  `tests/test_developer_identity.py`: the file under the gate holds only the
  gitignore invariant and already reports zero skips today, so a trigger pointing
  at it is satisfied in the unfixed state. Do not state the trigger as
  `resolve_developer` arriving either — the tests deliberately do not care what
  upstream names the helper, and a name-shaped trigger would keep the task parked
  through a differently-named fix that already works. The reporting half is no
  longer part of this trigger; it left with
  `08-17-trellis-identity-message-consistency`.
- Set the blocked markers the ranking helper reads, following this repository's
  existing parked tasks rather than inventing a third shape: prefix `title` with
  `PARKED: ` and add a top-level `blockedOn` string naming the upstream
  dependency, as `.trellis/tasks/07-25-worker-agents/task.json` does. The helper
  reads exactly `blocked`, `blockedOn`/`blockedReason`, and the `PARKED:` title
  prefix off the candidate record
  (`templates/scripts/sd-ai-command-pack-work-loop.py:860-875`); a
  `meta.blockedOn` — which `08-10-thin-final-conversion-gate-retirement` uses —
  reaches it only if the candidate builder lifts it, so do not rely on that
  form here.
- Do not tick the acceptance criteria. They are unmet here by construction, and
  the pre-archive gate is not the thing to argue with.

## Validation

```bash
STAGED=.trellis/tasks/08-08-developer-identity-not-in-worktrees/research/staged_test_worktree_identity.py
.venv/bin/python "$STAGED" -v                 # every test skipped, with reasons
.venv/bin/python -m unittest tests.test_developer_identity -v   # 1 pass, 0 skips
git status --short -- .trellis/scripts                          # empty
git check-ignore -v .trellis/.developer
git worktree list                                               # no strays
make check
```

Three runs, reported as three:

- **The staged suite against the vendored tree:** every test skipped, each with
  its reason. A skipped test proves nothing about the fix, and calling this run
  "passed" records unrun checks as green ones.
- **The gate half:** `tests/test_developer_identity.py`, one pass and no skips —
  which is also what keeps `make check` green.
- **The staged suite against upstream's copy** (Step 2.5): all pass, none
  skipped. That run is the evidence the fix this task waits for actually works.

Report all three, with the skip count from the first and the pass counts from the
others.

## Rollback points

- After Step 1: nothing has changed anywhere; the step is reading.
- After Step 2: tests alone are inert (they skip) and independently committable.
- Step 2.5 touches only a `mktemp -d` copy; rolling it back is `rm -rf`.
- After Step 3: the handoff is a document; reverting is one `git revert`.
- Nothing in this task changes shipped pack behavior, so there is no payload
  digest, manifest bump, or `make generate` step.

## Out of scope

- Editing `.trellis/scripts/**` in this repository, or writing anything into
  `~/repos/ai/Trellis` — that checkout is externally owned and currently dirty.
- Reimplementing requirement 1. It exists upstream at `0740d1d6`; this task
  verifies it and waits for the release.
- The reporting half — requirements 3, 4, 5, and 7 — which is `08-17-trellis-identity-message-consistency`.
- Opening a pull request against Trellis (needs explicit per-PR approval).
- The identity file's format, its first creation, or `init_developer.py`.
- `08-07-sd-submit-pack-task`'s requirement 8, which keeps its seeding until the
  refresh lands.
