# The developer identity file is gitignored, so every fresh worktree fails record-session

## Goal

Make a newly created Git worktree usable for session recording without a manual
file copy, while keeping the developer identity out of version control.

## Problem

`.trellis/.developer` holds the local developer identity and is gitignored
(`.trellis/.gitignore:2`):

```
.developer
```

Gitignored files are not materialized in a new worktree. So a fresh worktree has
no identity file, and every command that *requires* the developer fails there.
(Not every caller does: `show_developer_info` handles the absence and returns
normally, `common/developer.py:175-178`.) Reproduced:

```
$ git worktree add wt-b --detach HEAD
$ cd wt-b && python3 .trellis/scripts/get_developer.py
Developer not initialized
```

Three call sites report this, and they do not agree on what to say:

- `common/developer.py:161-162` (`ensure_developer`) prints the message *and* the
  remedy, then exits:

  ```python
  print("Error: Developer not initialized.", file=sys.stderr)
  print(f"Run: python3 ./{DIR_WORKFLOW}/scripts/init_developer.py <your-name>", file=sys.stderr)
  ```

- `get_developer.py:21` prints `Developer not initialized` with no remedy.
- `add_session.py:468` prints `Error: Developer not initialized` with no remedy —
  and is unreachable in practice, because `ensure_developer(repo_root)` at `:464`
  already exits first.

Being gitignored is correct: the identity is per-developer and must not be
committed. Two things are wrong.

**The remedy is the wrong remedy.** In a linked worktree the operator is told to
run `init_developer.py <your-name>`, which writes a fresh worktree-local
`.trellis/.developer`. The identity already exists in the primary checkout; the
suggested fix creates a second one. Nothing reconciles them, so a typo or a
different spelling silently forks the developer identity across worktrees of the
same repository — and the workspace journal path is derived from it.

**Nothing bridges the existing identity into a worktree.** A linked worktree can
reach the primary checkout through the common Git directory, so the information
needed is available; it is simply never consulted.

### The owning function is one level below the reporting sites

All three reporting sites delegate to `get_developer` in
`.trellis/scripts/common/paths.py:69`, which reads only the worktree-local file.
Patching the reporting sites cannot produce consistent fallback behaviour; the
fix belongs in that resolver, and the reporting sites then only need their
messages reconciled.

### Why this is not a rare edge case

The pack's own workflows create worktrees. `sd-work-backlog` documents
`isolation: worktree` runs, `sd-status` classifies worktree recovery artifacts,
and housekeeping reconciles them. A repository whose tooling creates worktrees
should not have a required identity file that worktrees never receive.

Observed during the 2026-08-08 merge batch: every worktree created to hold a
branch checkout failed session recording until `.trellis/.developer` was copied
by hand from an existing checkout.

### Relationship to `08-07-sd-submit-pack-task`

That task already documents this failure (`prd.md:43-45`) and its requirement 8
(`:111-113`) makes *its own command* seed `.trellis/.developer` into the worktree
it creates. That is the right fix for that command and the wrong shape for the
general problem: it repairs one caller's worktrees and leaves every other
worktree — `git worktree add` run by hand, `sd-work-backlog`'s isolation runs,
anything future — still broken.

This task fixes the resolver so no caller needs to seed `.trellis/.developer`.
If it lands first, the `.trellis/.developer` portion of `08-07`'s requirement 8
becomes redundant. The rest of that requirement stands: it covers per-working-copy
files in the plural and defines missing-source precondition behaviour, neither of
which a developer-identity resolver addresses.

## Requirements

1. A newly created worktree resolves the developer identity without a manual
   copy. Resolution should fall back to the main working tree's copy — the
   common Git directory is reachable from any linked worktree — rather than
   requiring per-worktree initialization.
2. The identity file stays gitignored and uncommitted.
3. Once requirement 1 lands, "identity exists in the primary checkout" is no
   longer a failure at all — it resolves. The remaining failure is "no identity
   anywhere, or the primary copy is unreadable", and only that case recommends
   `init_developer.py`. An unreadable primary copy names the path it tried
   instead of telling the operator to create a second identity.
4. The remaining call sites — `ensure_developer` and `get_developer.py`, once
   requirement 5 removes the third — resolve identically and report identically.
   Today one prints a remedy and the other does not.
5. `add_session.py:467-469` is removed as dead code, since `ensure_developer`
   at `:464` already exits with the better message. Requirement 4's consistency
   rule then covers the two remaining sites.
6. A worktree with a readable `.trellis/.developer` keeps using it. The fallback
   applies when the local file is absent **or** unusable — `get_developer`
   (`common/paths.py:83-94`) already returns `None` for a file that is present but
   unreadable or missing its `name=` line, and that state must not silently
   resolve to nothing when the primary checkout has a valid identity.
7. A local file that is present but unusable is distinguishable from one that is
   absent. Falling back is correct in both cases, but only the unusable case
   warrants a warning naming the malformed file — otherwise a typo'd local
   identity is silently replaced by the primary one with no trace.

## Acceptance criteria

- A test creates a linked worktree, does not copy any file into it, and asserts
  `get_developer.py` resolves the same identity as the primary checkout.
- A test asserts a readable worktree-local `.trellis/.developer` takes precedence
  over the fallback.
- A test asserts a present-but-unusable local file (unreadable, or missing its
  `name=` line) falls back to the primary identity and emits a warning naming the
  file, rather than resolving to `None` as it does today.
- A test asserts the failure message names an initialization command when no
  identity exists anywhere.
- A test asserts that when the primary checkout has an identity, a worktree
  resolves it successfully and emits no diagnostic at all — the case that used to
  fail must now simply work.
- A test asserts an unreadable primary copy reports the path it tried and does
  not recommend `init_developer.py`.
- A test asserts the remaining call sites emit the same message for the same
  condition.
- A test covers `add_session.py` end to end in a fresh worktree, since that is
  the path that actually blocks finish-work.
- A test asserts `get_developer` (`common/paths.py:69`) itself resolves through
  the fallback, so callers added later inherit it without changes.
- `.trellis/.developer` remains gitignored: `git check-ignore -v .trellis/.developer`
  still matches.
- `make check` passes.

## Out of scope

- Changing what the identity file contains or how it is first created.
- Committing the identity, or adding any mechanism that would place it under
  version control.
- Nothing about the file's format or first creation.

## Ownership

`.trellis/scripts/**` is vendored from Trellis, and `AGENTS.md:26-28` requires a
paste-ready handoff rather than a local Trellis PR. This task is therefore
**upstream-handoff-first**: produce the patch and the handoff against Trellis,
and land it locally only through the normal vendored refresh.

The acceptance tests above are written against the local checkout because that
is where they can run. If the vendored copy cannot be modified before an upstream
release, the task parks on the handoff with the tests staged, rather than
carrying a local divergence — resolve that at planning, not during
implementation.
