# Trellis identity reporting: one diagnosis across every site

## Closure — 2026-08-20: WILL NOT DO (declined, not fixed)

Decided by the repository owner on 2026-08-20. **The defect described below is
real and remains in the tree.** This task is closed because the cost was judged
not worth paying, not because the problem went away. Do not read the archived
`status: completed` as "delivered" — Trellis has no won't-do status, so the
decision is recorded here and in `meta.closure`.

### What remains broken, on purpose

Verified 2026-08-20 against the vendored tree (0.6.16-sd.7):

- Nine gate sites still emit **five different leading sentences** for one
  condition: `Developer not initialized.` / `Developer not initialized` /
  `No developer set` / `Not initialized` / `Developer not set`.
- Four gates still carry no hint: `get_developer.py:21`,
  `common/session_context.py:602`, `:821`, `common/task_queue.py:138`.
  `get_developer.py:21` still offers no remedy at all.
- No site can distinguish an **absent** identity from an **unusable** one.
  `_read_developer_file` (`common/paths.py:104-118`) returns `None` for both, so
  every gate recommends creating a second identity even when one already exists
  and is merely malformed. This is a type-level limit, not a wording one.
- An unusable local `.developer` is still silently replaced by the main
  checkout's at `common/paths.py:152-160`, with no trace — the forked-identity
  case. This is the sharpest surviving symptom.

Decisive proof that nothing landed: `grep -rn 'resolve_developer' .trellis/scripts`
returns zero hits.

### Why it was declined

The work is a ~400-500 line refactor across seven files in the **upstream fork**
(`~/repos/ai/Trellis`), not in this repository, plus ~300 lines of staged
pack-side test, a patch artifact, and a handoff-register entry. It cannot be
delivered by editing strings: requirements 1 and 4 need a new
`DeveloperResolution` type and a `resolve_developer()` resolver before any gate
can say anything it cannot say today.

It also carries a breaking-change tail. Upstream `test/regression.test.ts`
(~`:12846`) asserts `expect(payload.error).toBe("No developer set")` — exact
equality, not `toContain` — so unifying the diagnosis is a breaking test change
against a string that is pinned deliberately.

Against that: the failure mode is a confusing error message on an uncommon
path, and the one case with real consequences (a forked identity from a
malformed local file) requires a malformed `.developer` to exist in the first
place.

### What is NOT part of this decision

The sibling defect — a fresh `git worktree` having no identity file at all — is
**fixed**, not declined. `get_developer` falls back to the main checkout via
`main_worktree_root` (`common/paths.py:152-160`), shipped in 0.6.16-sd.7.
Verified 2026-08-20 in a throwaway worktree with no `.developer`:
`python3 ./.trellis/scripts/get_developer.py` printed `sdelmas`, exit 0. Note
the docstring's warning that the main file is *read, never copied* — copying it
into a worktree is the anti-pattern, since the copy goes stale and shadows later
changes.

### If this is ever reopened

The patch base is live: `~/repos/ai/Trellis` `main` is `2749d3b4`
(`0.6.16-sd.7`), and `diff -rq --exclude=__pycache__` between the fork's
`packages/cli/src/templates/trellis/scripts` and this repo's `.trellis/scripts`
is empty. The `design.md` in this directory is accurate and its line numbers are
valid as-is. The "blocked on uptake" framing in the body below is stale and was
already false at closure time.



## Goal

When the **developer identity** cannot be resolved, every Trellis script that
reports it should agree on *what happened* and on *what to do about it* — and
none of them should tell an operator to create a second identity when the
existing one is merely unreadable.

"Developer identity" means `.trellis/.developer` and `TRELLIS_DEVELOPER`
(`common/paths.py:41-50`, `:104-160`). It is unrelated to the Trellis runtime
version; nothing in this task touches versioning.

## Origin

Split out of `08-08-developer-identity-not-in-worktrees` on 2026-08-17. That task
owns the worktree-resolution half (its requirements 1, 2, 6). Its requirements 3,
4, 5, and 7 are the reporting half and are reproduced below as this task's
requirements 1 to 4.

The split happened because the reporting half turned out to be much larger than
the two call sites the original PRD named: eight live reporting gates in four
different output media, one of them a JSON contract pinned by an upstream
regression test with an **exact-equality** assertion. Growing that inside a task
about worktrees would have hidden it.

## State of the base (verified 2026-08-20)

The framing this PRD carried until 2026-08-20 — "blocked, because the patch base
`0740d1d6` is untagged and not on `fork/main`" — **is no longer true and has been
removed.** The worktree fallback shipped:

| Fact | Verified value |
|---|---|
| `git -C ~/repos/ai/Trellis rev-parse --short HEAD` (branch `main`) | `2749d3b4` |
| `packages/cli/package.json` version | `0.6.16-sd.7` |
| `diff -rq --exclude=__pycache__ <fork>/packages/cli/src/templates/trellis/scripts .trellis/scripts` | **empty** |
| `grep -rn 'resolve_developer\|DeveloperResolution' .trellis/scripts` | **0 hits** |

Three consequences, and they set the whole shape of this task:

1. **The patch base is live.** The fallback (`common/paths.py:121-160` with
   `common/git.py:143-192`) is on `fork/main`, tagged into `0.6.16-sd.7`, and
   already vendored here. There is no release chain to wait on before authoring.
2. **The vendored tree and the fork tree are byte-identical.** Every line number
   in this task's artifacts is therefore valid against *both*, and the patch can
   be built from the pack's own `.trellis/scripts` copy without reading the
   externally-owned fork. Re-run that `diff` before trusting this; a non-empty
   result means the fork moved and the copy must come from the fork instead.
3. **None of this task has landed.** `resolve_developer` does not exist, the
   patch file does not exist, and this task directory has no `research/`
   subdirectory. Everything below is unstarted work, not verification of
   something already shipped.

What *does* still wait on a release chain is only the **uptake** of this task's
own patch: it must be filed upstream, released, and re-vendored before the
behavior criteria below can be ticked here. That is ordinary upstream-handoff
latency, not a blocker on authoring. **This task is open and selectable, not
parked.**

## Problem

Every site delegates to `get_developer` (`common/paths.py:121-160`), which
answers a name or `None`. `None` cannot distinguish "no identity file anywhere"
from "the identity file exists and is unusable", because
`_read_developer_file` (`common/paths.py:104-118`) returns `None` for a missing
file, an unreadable file, a file with no `name=` line, and a `name=` value
`_safe_developer_name` (`:83-101`) rejects. So no site can say which happened,
and each recommends `init_developer.py` — creating a *second* identity — even
when the first one exists and is simply broken. The workspace journal path
derives from the identity, so a silently forked identity splits a developer's
history.

**What upstream already unified, so this task does not claim it.**
`DEVELOPER_HINT` (`common/paths.py:46-50`) is one shared string naming
`TRELLIS_DEVELOPER` and worktree inheritance, and four sites already carry it —
`common/developer.py:164`, `common/task_store.py:350`, `task.py:391`, and
`task.py:361` as the JSON `hint`. The residual defect is narrower than "every
site invents its own message", and it is three things:

- **Five different leading sentences for one condition** —
  `Developer not initialized.` / `Developer not initialized` /
  `No developer set` / `Not initialized` / `Developer not set` — so the same
  condition is unrecognizable across tools, by an operator or by a grep.
- **Four live gates carry no hint at all**: `get_developer.py:21`,
  `common/session_context.py:602`, `common/session_context.py:821`, and
  `common/task_queue.py:138`. `get_developer.py:21` offers no remedy either — it
  prints four words and exits.
- **No site can tell an unusable file from an absent one.** This is a *type*
  problem, not a wording problem: requirements 1 and 4 below are unreachable by
  editing strings, because the information does not survive `get_developer`'s
  return type. Any plan that proposes only message edits has misread the defect.

A fifth consequence follows from the same gap: an unusable local `.developer` is
silently replaced by the main checkout's at `common/paths.py:152-160`, with no
trace. That is the forked-identity case, and today nothing reports it.

### The sites, enumerated from source

At fork `main` `2749d3b4` / vendored `0.6.16-sd.7` (identical trees), under
`.trellis/scripts/` here and
`packages/cli/src/templates/trellis/scripts/` upstream:

| # | Site | Medium | Failure behavior | Current leading text | Hint? |
|---|---|---|---|---|---|
| 1 | `common/developer.py:162-165` (`ensure_developer`, `:152`) | stderr prose | `sys.exit(1)` | `Error: Developer not initialized.` + `Run: ... init_developer.py <your-name>` | yes |
| 2 | `get_developer.py:21` | stderr prose | `exit 1` | `Developer not initialized` — **no remedy** | no |
| 3 | `common/task_store.py:349-351` | stderr prose, red | `return 1` | `Error: No developer set. Run init_developer.py first or use --assignee` | yes |
| 4 | `task.py:359-364` (`cmd_list`, JSON arm) | **JSON on stderr** | `return 1` | `{"error": "No developer set", "hint": DEVELOPER_HINT}` | yes (`hint` key) |
| 5 | `task.py:389-392` (`cmd_list`, prose arm) | stderr prose, red | `return 1` | `Error: No developer set. Run init_developer.py first` | yes |
| 6 | `common/session_context.py:600-604` (`get_context_text`, `:578`) | a line inside a returned **document** | none — document is returned | `ERROR: Not initialized. Run: ... init_developer.py <name>` | no |
| 7 | `common/session_context.py:819-823` (`get_context_text_record`, `:803`) | a line inside the record-mode **document** | none | same string, separate branch | no |
| 8 | `common/task_queue.py:136-138` | **raised `ValueError`** | raises | `Developer not set` | no |
| 9 | `add_session.py:1262-1265` | stderr prose | `return 1` | `Error: Developer not initialized` | no |

**Nine sites, eight of them live.** Site 9 is dead: `ensure_developer` at
`add_session.py:1260` has already `sys.exit(1)`-ed on an unresolvable identity,
and `_safe_developer_name` (`common/paths.py:83-89`) already returns `None` for
the empty `name=` value that was the branch's one remaining live input. It is
deleted by requirement 3 rather than rewritten.

Rows 6 and 7 are counted separately on purpose: they are the same string in two
different functions and must be patched twice. Collapsing them to one row is
exactly how the count came out wrong before.

**Re-enumerate at implementation time; do not trust this table.** Two passes are
required, and neither alone is sufficient:

```bash
grep -rn 'Developer not initialized\|No developer set\|Developer not set\|Not initialized' \
  .trellis/scripts --include='*.py'        # 9 lines across 7 files at this base
grep -rn 'get_developer(' .trellis/scripts --include='*.py' | grep -v 'def get_developer'
                                          # 16 caller lines at this base
```

The message grep misses `common/task_queue.py:138`, because it raises rather
than prints. The caller grep cannot tell a reporter from a consumer. Consumers
must stay untouched: `common/safe_commit.py:95`, `common/paths.py:209`,
`common/session_context.py:506` and `:736`, `common/paths.py:172`
(`check_developer`), `common/paths.py:542`, and `init_developer.py:37`. So must
`show_developer_info` (`common/developer.py:170-184`), a deliberate non-error
path.

### The four pack-owned sites, and why they are out of scope

This repository owns four more places that render the identity, printing a fifth
wording:

- `.claude/hooks/session-start.py:716`
- `.gemini/hooks/session-start.py:716`
- `.codex/hooks/session-start.py:382`
- `.github/copilot/hooks/session-start.py:381`

All four are the same line — `lines.append(f"Developer: {developer or '(not
initialized)'}")` — over a `get_developer(repo_root) if get_developer else None`
resolution, and all four are tracked independently (there is no generator; `git
ls-files | grep session-start.py` returns exactly these four).

**Decision: out of scope for the diagnosis, in scope for the compatibility
check.** They are not gates. They set no exit code, block nothing, recommend
nothing, and produce a status label inside a session banner — structurally
identical to `show_developer_info`, which this PRD already exempts as a
deliberate non-error path. Unifying a *failure* diagnosis into a banner would
put a remedy sentence and two file paths in front of every session start,
including the overwhelmingly common case where the operator is not failing at
anything. And the change would cost four hand-edits in this repository for a
task whose entire deliverable is one upstream patch, muddying the handoff.

What they *are* in scope for: requirement 7 says no consumer changes behavior,
and these four are the pack's only consumers of the vendored resolver. Making
`get_developer` a `.name` wrapper must leave all four printing exactly what they
print today. That is an acceptance criterion below, not a code change.

If a future task decides a degraded identity deserves a banner line, it owns
these four sites and should say so explicitly; this one does not.

## Requirements

1. Only "no identity file anywhere" recommends `init_developer.py`. A file that
   exists but is unusable — the local copy, the main checkout's, or both — names
   the exact path it tried and does not recommend creating another identity.
   (Was `08-08`'s requirement 3.)
2. Every reporting site resolves identically and reports the same *diagnosis*
   for the same condition. Enumerate the sites from the source being patched,
   never from a list in a document — including this one.
   (Was `08-08`'s requirement 4.)
3. `add_session.py`'s `if not developer:` branch (`:1263-1265`) is removed.
   `ensure_developer` at `:1260` already exited, and `_safe_developer_name`
   already rejects the empty `name=` that was its one live input, so the branch
   is unreachable by two independent routes. (Was `08-08`'s requirement 5.)
4. A local file that is present but unusable is distinguishable from one that is
   absent, and only the unusable case warrants a warning naming the malformed
   file — otherwise a typo'd local identity is silently replaced by the main
   checkout's with no trace. The warning is emitted by **every reporting gate
   that resolves the identity** — the eight live gates above — never from inside
   `get_developer`: a resolver that printed would add stderr to every consumer
   and break requirement 7. Routing it through `ensure_developer` alone is
   equally wrong: that function has exactly one caller in the whole tree
   (`add_session.py:1260`), so `task.py`, `task_store.py`, `session_context.py`,
   and `task_queue.py` would stay silent about a forked identity. Each gate
   renders the warning in a medium that does **not** change its success
   behavior — no new exit code, and no exception where the call currently
   succeeds. (Was `08-08`'s requirement 7.)
5. **The JSON `error` value is pinned by exact equality and must not change.**
   `packages/cli/test/regression.test.ts:12863` asserts
   `expect(payload.error).toBe("No developer set")` — `toBe`, not `toContain`.
   Site 4's `error` string is therefore a frozen contract, not a message to
   reword: any new detail for the absent case goes in `hint` or in an additional
   key, never in `error`. Changing that value is a **breaking test change** and
   must be planned and executed as one, in the same diff that updates the
   assertion, with the reason stated in the handoff.
6. The surrounding prose is pinned too, but only by substring. The same case
   (`regression.test.ts:12846-12867`, one of eleven `[worktree-identity]` cases
   at `:12717-12921` inside the suite at `:12597-12922`) asserts that **stderr
   prose** from `task.py create` contains `No developer set`,
   `init_developer.py`, `TRELLIS_DEVELOPER`, and `linked git worktree`, and that
   the JSON `hint` contains the last two. That prose comes from site 3
   (`common/task_store.py:349-351`), so requirement 1's removal of
   `init_developer.py` is scoped to the **unusable-file** case only; the
   nothing-anywhere case keeps every substring the suite names.
7. "Report identically" means one diagnosis, several renderings. Byte-identical
   output is impossible here and must not be required: site 4 emits parsed JSON,
   sites 6 and 7 return whole documents with their own headers, and site 8
   raises. Each renders the shared diagnosis in its own medium; the JSON stays
   parseable with its `error` and `hint` keys.
8. No consumer changes behavior, and `get_developer` keeps its name, signature,
   `str | None` return, docstring contract, and its silence, so nothing outside
   the eight live gates is affected — including the four pack-owned
   `session-start.py` sites. A gate's own diagnostic line is not a behavior
   change for its callers: no return value, exit status, or raised exception
   moves.

## Acceptance criteria

Behavior criteria (tickable only against a patched tree, and here only after
uptake):

- [ ] A test asserts the failure message names an initialization command when no
      identity file exists anywhere.
- [ ] A test asserts an unreadable main-checkout copy reports the path it tried
      and does **not** recommend `init_developer.py`.
- [ ] A test asserts an unusable local file falls back and warns naming that
      file, at more than one gate: `add_session.py` (the only `ensure_developer`
      caller), the `get_developer.py` CLI, and one ordinary reporter. One warning
      test would pass while the other gates stayed silent about a forked
      identity.
- [ ] The reporter case also asserts the call still **succeeds** — exit 0, output
      produced, no exception. `common/task_queue.py:136-138` raises only on a
      falsey name, so a patch that raised in order to carry the warning would
      turn a working fallback into a failure and still satisfy a warning-only
      assertion.
- [ ] A test enumerates the reporting sites by grepping the resolved scripts
      directory and asserts every one of them reports the same diagnosis for the
      same condition — a site added upstream later fails it rather than escaping
      it. It must count what it found and compare against the enumeration, never
      assert a hardcoded eight or nine: a fixed number passes while missing one
      of the two `session_context` branches, which is exactly how the count was
      wrong before.
- [ ] A test asserts the JSON site stays parseable, keeps its `error` and `hint`
      keys, and that `error` is still **exactly** `No developer set`
      (requirement 5) unless the same change set updates
      `regression.test.ts:12863` deliberately.
- [ ] A test asserts the nothing-anywhere case still contains every substring
      upstream's `[worktree-identity]` suite pins in stderr prose — `No developer
      set`, `init_developer.py`, `TRELLIS_DEVELOPER`, `linked git worktree`.
- [ ] A test asserts `add_session.py` no longer contains the `if not developer:`
      guard after `ensure_developer` — a source assertion, because behavior tests
      cannot see a branch that is already unreachable.
- [ ] A test asserts each consumer listed above still behaves as it did,
      including the four pack-owned `session-start.py` sites still printing
      `Developer: (not initialized)` for an absent identity and `Developer:
      <name>` otherwise.

Authoring criteria (tickable now, in this repository):

- [ ] The patch file exists at
      `.trellis/tasks/08-08-upstream-handoff-register/research/2026-08-17-trellis-identity-reporting.patch`,
      records its apply command and strip depth, and passes `git apply --check`
      against a clean copy of the base tree.
- [ ] The staged suite exists at this task's
      `research/staged_test_identity_reporting.py`, runs standalone, and is
      recorded with three results: vendored (skips, with reasons), run A
      (unpatched copy), run B (patched copy — zero skips, zero failures).
- [ ] Register entry 14 in `08-08-upstream-handoff-register/prd.md` is updated
      with the patch location and its stale "untagged and not on `fork/main`"
      framing corrected.
- [ ] `make check` passes in this repository.

## Ownership and blockers

`.trellis/scripts/**` is vendored, and `AGENTS.md:25-28` requires a paste-ready
handoff rather than a local Trellis pull request. This task therefore produces a
patch against the fork plus a register entry, and lands here only through a
vendored refresh. Filing the task in `~/repos/ai/Trellis` is an **operator
action**; that checkout is externally owned and currently dirty, so nothing here
writes into it.

The base is live (see "State of the base"), so authoring is unblocked today. Only
the behavior criteria wait on the upstream file → release → refresh chain.

## Out of scope

- The worktree fallback itself, its mechanism, and requirement 6 of `08-08`
  (empty `name=`) — all already implemented upstream and vendored here.
- Changing what the identity file contains, or how it is first created.
- The Trellis runtime version and anything about vendoring mechanics.
- Editing `.trellis/scripts/**` in this repository, or writing into the fork.
- The four pack-owned `session-start.py` identity lines, for the reasons stated
  above; they are verified unchanged, not modified.
- Opening a Trellis pull request (needs explicit per-PR approval).
