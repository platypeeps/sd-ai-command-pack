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
normally, `common/developer.py:177-178`.) Reproduced:

```
$ git worktree add wt-b --detach HEAD
$ cd wt-b && python3 .trellis/scripts/get_developer.py
Developer not initialized
```

Three call sites in the **vendored 0.6.14 copy** report this, and they do not
agree on what to say (the same enumeration against upstream's head found eight
reporting gates, which is `08-17-trellis-identity-message-consistency`'s
business, not this task's):

- `common/developer.py:161-163` (`ensure_developer`) prints the message *and* the
  remedy, then exits:

  ```python
  print("Error: Developer not initialized.", file=sys.stderr)
  print(f"Run: python3 ./{DIR_WORKFLOW}/scripts/init_developer.py <your-name>", file=sys.stderr)
  ```

- `get_developer.py:21` prints `Developer not initialized` with no remedy.
- `add_session.py:528` prints `Error: Developer not initialized` with no remedy
  (the `if not developer:` guard is `:527`).
  It looks unreachable, because `ensure_developer(repo_root)` at `:524` already
  exits first — but it is not. A `.developer` whose `name=` line is empty makes
  `get_developer` return `""` (`common/paths.py:90`), which `check_developer`
  (`:106`) accepts as initialized while `if not developer:` rejects. Verified
  against this checkout: `get_developer -> ''`, `check_developer -> True`. So the
  branch fires for exactly one input, and with the worst message of the three.

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
3. **Moved** to `08-17-trellis-identity-message-consistency` (2026-08-17), as its requirement 1: only "no identity
   file anywhere" recommends `init_developer.py`; an existing-but-unusable file
   names the path it tried instead.
4. **Moved** to `08-17-trellis-identity-message-consistency` (2026-08-17), as its requirements 2 and 5. The
   enumeration is why: this requirement was written around two call sites, and
   the source has eight reporting gates in four media. That is its own change,
   not a footnote to a worktree fix.
5. **Moved** to `08-17-trellis-identity-message-consistency` (2026-08-17), as its requirement 3: delete
   `add_session.py`'s `if not developer:` branch. Upstream already rejects the
   empty `name=` that was its one live input, so the deletion is safe there on
   its own.
6. A worktree with a readable `.trellis/.developer` keeps using it, unless an
   explicit environment override outranks it. Upstream resolves
   `TRELLIS_DEVELOPER` first, then the local file, then the main checkout's;
   that order is accepted here — an operator naming an identity in the
   environment means it — and the requirement constrains only the two file
   cases. The fallback
   applies when the local file is absent **or** unusable — `get_developer`
   (`common/paths.py:83-94`) already returns `None` for a file that is present but
   unreadable or missing its `name=` line, and that state must not silently
   resolve to nothing when the primary checkout has a valid identity. A `name=`
   line whose value is empty or whitespace counts as unusable too. Today it
   resolves to `""`, which is not `None` and so passes every `is not None` gate
   while failing every truthiness test — the split that keeps requirement 5's
   branch alive.
7. **Moved** to `08-17-trellis-identity-message-consistency` (2026-08-17), as its requirement 4: warn, naming the
   malformed local file, when an unusable local copy is replaced by the main
   checkout's.

## Acceptance criteria

- A test creates a linked worktree, does not copy any file into it, and asserts
  `get_developer.py` resolves the same identity as the primary checkout.
- A test asserts a readable worktree-local `.trellis/.developer` takes precedence
  over the fallback.
- A test asserts a present-but-unusable local file (unreadable, or missing its
  `name=` line) falls back to the primary identity rather than resolving to
  `None` as it does today. *(The warning half moved to `08-17-trellis-identity-message-consistency`.)*
- *(moved to `08-17-trellis-identity-message-consistency`)* the failure message names an initialization command when
  no identity exists anywhere.
- A test asserts that when the primary checkout has an identity, a worktree
  resolves it successfully and emits no diagnostic at all — the case that used to
  fail must now simply work.
- *(moved to `08-17-trellis-identity-message-consistency`)* an unreadable primary copy reports the path it tried and
  does not recommend `init_developer.py`.
- A test asserts a `.developer` whose `name=` value is empty or whitespace is
  treated as unusable — it falls back rather than resolving to `""`.
- *(moved to `08-17-trellis-identity-message-consistency`)* every reporting site enumerated at patch time reports the
  same diagnosis for the same condition.
- A test covers `add_session.py` end to end in a fresh worktree, since that is
  the path that actually blocks finish-work.
- A test asserts `get_developer` (`common/paths.py:69`) itself resolves through
  the fallback, so callers added later inherit it without changes.
- A test asserts `TRELLIS_DEVELOPER` outranks both files, and that the result
  does not depend on either file's contents or readability — the observable half
  of "neither file is consulted". The unobservable half needs syscall tracing:
  the resolver swallows read errors (`_read_developer_file`), so no behavioral
  test can distinguish "never read" from "read and discarded", and this criterion
  deliberately does not claim otherwise.
- `.trellis/.developer` remains gitignored: `git check-ignore -v .trellis/.developer`
  still matches.
- `make check` passes.

## Out of scope

- Prescribing *how* the fallback finds the main working tree. Upstream resolves
  it by asking Git (`git worktree list --porcelain`), which covers layouts a
  plumbing-file parse cannot — a `--separate-git-dir` main checkout among them —
  and avoids one it would get wrong. Requirement 1 constrains the behavior, not
  the mechanism; see `design.md`.
- Changing what the identity file contains or how it is first created.
- Committing the identity, or adding any mechanism that would place it under
  version control.
- Nothing about the file's format or first creation.

## Ownership

`.trellis/scripts/**` is vendored from Trellis, and `AGENTS.md:25-28` requires a
paste-ready handoff rather than a local Trellis PR. This task is therefore
**upstream-handoff-first**: produce the patch and the handoff against Trellis,
and land it locally only through the normal vendored refresh.

**Update, 2026-08-17.** Requirements 3, 4, 5, and 7 — the reporting half — moved
to `08-17-trellis-identity-message-consistency`. The enumeration behind requirement 4 found eight reporting gates in
four output media, one of them a JSON contract with an upstream regression test;
that is a coherent upstream change of its own and does not belong inside a
worktree-resolution task. What stays here is requirements 1, 2, and 6.

**Update, 2026-08-16.** Requirement 1 is already implemented in the Trellis
fork: commit `0740d1d6` on `chore/task-backlog-2026-08`, carrying no tag and not
on `fork/main`. So it is unreachable by `trellis update` today, and this task
neither reimplements it nor waits for a design decision about it. What remains
for this half is the release and the vendored refresh that bring it here; the
reporting work that was also open upstream now belongs to
`08-17-trellis-identity-message-consistency`. Requirement 6's empty-`name=` hole
is closed upstream too and open only in the vendored copy.

The acceptance tests above are written against the local checkout because that
is where they can run. If the vendored copy cannot be modified before an upstream
release, the task parks on the handoff with the tests staged, rather than
carrying a local divergence — resolve that at planning, not during
implementation.

## Park note, 2026-08-17

**Parked on the upstream release chain.** Nothing about this half is undecided;
it is waiting on other people's release, and there is no local work left that
would not be a vendored divergence.

What was delivered instead of a fix:

- `research/staged_test_worktree_identity.py` — the acceptance suite, staged
  *outside* `tests/` because `Makefile:49` fails the repo gate on any skip and
  this suite skips until the release lands. It gates every behavioral test on a
  throwaway-fixture probe of the *behavior* (never a symbol name) and resolves
  its scripts directory from `SD_DEVELOPER_IDENTITY_SCRIPTS`. Against vendored
  0.6.14: `Ran 9 tests ... OK (skipped=9)`. Against a `mktemp -d` copy of
  upstream's `scripts/` at `454046ca`: `Ran 9 tests ... OK`, 0 skipped — the
  evidence the awaited fix works.
- `tests/test_developer_identity.py` — the one assertion that holds today and
  must keep holding, so it belongs under the gate: `.trellis/.developer` stays
  gitignored. 1 pass, 0 skips.
- Register entry 13 in `08-08-upstream-handoff-register`, with paste-ready
  material and both run results in that task's
  `research/2026-08-17-trellis-developer-identity-worktree-and-reporting.md`.
- The reporting half filed as `08-17-trellis-identity-message-consistency`.

**Status while parked: `planning`.** The iteration that produced this note ran
`task.py start` before the park decision, which left the record `in_progress`.
Every other parked task in this repository is `planning`, and the finalization
validator enforces the same shape — a planning-mode bundle requires `status`
`planning`, `completedAt` null, and `branch` null, at the bundle base as well as
in the bundle (`sd-ai-command-pack-review-preflight.mjs:2532` and `:2544`). The
record was returned to `planning` in the same branch. A resume starts the task
again; nothing here was implemented, so there is no in-flight work that status
would be hiding.

**What resumes it:** a Trellis release carrying `0740d1d6` reaching this
repository through a vendored refresh, after which the staged suite runs with
**zero skips** and moves into `tests/`. That is the resume trigger — not the fallback probe alone, which
already passes against unpatched upstream. The acceptance criteria stay unticked
until then.
