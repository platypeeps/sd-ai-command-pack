# Trellis identity reporting: one diagnosis across every site

## Goal

When the developer identity cannot be resolved, every Trellis script that
reports it should agree on *what happened* and on *what to do about it* — and
none of them should tell an operator to create a second identity when the
existing one is merely unreadable.

## Origin

Split out of `08-08-developer-identity-not-in-worktrees` on 2026-08-17. That task
owns the worktree-resolution half (its requirements 1, 2, 6), which the Trellis
fork has already implemented in `0740d1d6` on `chore/task-backlog-2026-08`. Its
requirements 3, 4, 5, and 7 are the reporting half and they are reproduced below
verbatim as this task's requirements 1 to 4. It parks on the release; this one is
independent upstream work.

The split happened because the reporting half turned out to be much larger than
the two call sites the original PRD named: eight reporting gates in four
different output media, one of them a JSON contract with an upstream regression
test. Growing that inside a task about worktrees would have hidden it.

**This task is not parked.** `08-08` is, because nothing is left to do there but
wait. Here the patch, the staged tests, and the register update are all
executable in this repository today; only the *uptake* waits on a Trellis release
and a vendored refresh. Marking it blocked would hide available work from the
backlog selector.

## Problem

Every site delegates to `get_developer`, which answers a name or `None`. `None`
cannot distinguish "no identity file anywhere" from "the identity file exists and
is unreadable", so no site can say which happened, and each recommends
`init_developer.py` — creating a *second* identity — even when the first one
exists and is simply broken. The workspace journal path derives from the
identity, so a silently forked identity splits a developer's history.

**What upstream already unified, so this task does not claim it.** `DEVELOPER_HINT`
(`common/paths.py:46-50`) is one shared string naming `TRELLIS_DEVELOPER` and the
worktree inheritance, and three sites already append it — `common/developer.py:164`,
`common/task_store.py:326`, `task.py:381` — while `task.py:351` carries it as the
JSON `hint`. The residual defect is narrower than "eight sites invent eight
messages":

- the leading sentence differs per site (`Developer not initialized` /
  `No developer set` / `Not initialized`), so the same condition is
  unrecognizable across tools;
- four gates carry no hint at all — `get_developer.py:21`,
  `common/session_context.py:602`, `common/session_context.py:821` (counted
  separately, as everywhere else here), and `common/task_queue.py:138`. The
  other four are exactly the sites that name `DEVELOPER_HINT` in source:
  `common/developer.py:164`, `common/task_store.py:326`, `task.py:381`, and
  `task.py:351`; and
- **no** site distinguishes an unusable file from an absent one, which is the
  part `get_developer`'s return type makes impossible rather than merely
  inconsistent.

### The sites, enumerated from source rather than assumed

At `chore/task-backlog-2026-08`'s head (`454046ca`), under
`packages/cli/src/templates/trellis/scripts/`:

| Site | Medium | Current text |
|---|---|---|
| `common/developer.py:161-165` (`ensure_developer`) | stderr prose, `sys.exit(1)` | `Error: Developer not initialized.` + `Run: ... init_developer.py <your-name>` + `DEVELOPER_HINT` |
| `get_developer.py:21` | stderr prose, exit 1 | `Developer not initialized` — no remedy |
| `common/task_store.py:325` | stderr prose, colored | `Error: No developer set. Run init_developer.py first or use --assignee` |
| `task.py:351` | **JSON** on stderr | `{"error": "No developer set", "hint": DEVELOPER_HINT}` |
| `task.py:380` | stderr prose, colored | `Error: No developer set. Run init_developer.py first` |
| `common/session_context.py:602` (`get_context_text`, `:578`) | a line inside a returned context **document** | `ERROR: Not initialized. Run: ... init_developer.py <name>` |
| `common/session_context.py:821` (`get_context_text_record`, `:803`) | a line inside a returned context **document** | same text, separate branch |
| `common/task_queue.py:138` | **raised `ValueError`** | `Developer not set` |

Plus `add_session.py:1108-1110`, which requirement 3 deletes.

Enumerate again at implementation time. The message-string grep alone misses
`task_queue.py`, because it raises rather than prints; the `get_developer(`
caller grep alone cannot tell a reporter from a consumer. Both passes are
needed, and consumers — `common/safe_commit.py:95`, `common/paths.py:209`,
`common/session_context.py:506` and `:736` — must stay untouched, as must
`show_developer_info` (`common/developer.py:168`), a deliberate non-error path.

## Requirements

1. Only "no identity file anywhere" recommends `init_developer.py`. A file that
   exists but is unusable — the local copy, the main checkout's, or both — names
   the exact path it tried and does not recommend creating another identity.
   (Was `08-08`'s requirement 3.)
2. Every reporting site resolves identically and reports the same *diagnosis*
   for the same condition. Enumerate the sites from the source being patched,
   never from a list in a document. (Was `08-08`'s requirement 4.)
3. `add_session.py`'s `if not developer:` branch (`:1108-1110` at that head) is
   removed: `ensure_developer` at `:1105` already exited, and upstream's
   `_safe_developer_name` already rejects the empty `name=` that was its one live
   input. (Was `08-08`'s requirement 5.)
4. A local file that is present but unusable is distinguishable from one that is
   absent, and only the unusable case warrants a warning naming the malformed
   file — otherwise a typo'd local identity is silently replaced by the main
   checkout's with no trace. The warning is emitted by **every reporting gate
   that resolves the identity** — the same eight this task already touches —
   never from inside `get_developer`: a resolver that printed would add stderr
   to every consumer and break requirement 7. Routing it through
   `ensure_developer` alone is equally wrong: that function has exactly one
   caller upstream (`add_session.py:1105`), so `task.py`, `task_store.py`,
   `session_context.py`, and `task_queue.py` would stay silent about a forked
   identity. Each gate renders the warning in a medium that does **not** change
   its success behavior — no new exit code, and no exception where the call
   currently succeeds. (Was `08-08`'s requirement 7.)
5. Upstream's own regression suite constrains the wording. `regression.test.ts`
   carries eleven `[worktree-identity]` cases (`:12526-12723`); the
   no-identity-anywhere case (`:12655-12676`) asserts that **stderr prose**
   contains `No developer set`, `init_developer.py`, `TRELLIS_DEVELOPER`, and
   `linked git worktree`, and that the JSON `hint` contains the last two. The
   pinned contract is therefore not only the JSON: requirement 1 removes
   `init_developer.py` from the *unusable-file* case only, and the
   nothing-anywhere case keeps every substring that suite names unless the diff
   updates those expectations deliberately.
6. "Report identically" means one diagnosis, several renderings. Byte-identical
   output is impossible here and must not be required: `task.py:351` emits JSON
   that an upstream regression test parses
   (`packages/cli/test/regression.test.ts:12655-12676`),
   `get_context_text` / `get_context_text_record`
   (`common/session_context.py:578`/`:803`, whose identity lines are `:602` and
   `:821`) return whole documents with their own headers, and
   `common/task_queue.py:138` raises. Each renders the shared
   diagnosis in its own medium; the JSON stays parseable with its `error` and
   `hint` keys.
7. No consumer changes behavior, and `get_developer` keeps its signature, its
   `str | None` return, and its silence, so nothing outside the eight reporting
   gates is affected. A gate's own diagnostic line is not a behavior change for
   its callers: no return value, exit status, or raised exception moves.

## Acceptance criteria

- A test asserts the failure message names an initialization command when no
  identity file exists anywhere.
- A test asserts an unreadable main-checkout copy reports the path it tried and
  does **not** recommend `init_developer.py`.
- A test asserts an unusable local file falls back and warns naming that file, at
  more than one gate: `add_session.py` (the only `ensure_developer` caller), the
  `get_developer.py` CLI, and one ordinary reporter. One warning test would pass
  while the other gates stayed silent about a forked identity.
- The reporter case also asserts the call still **succeeds** — exit 0, output
  produced, no exception. `common/task_queue.py:136-138` raises only on a falsey
  name, so a patch that raised in order to carry the warning would turn a working
  fallback into a failure and still satisfy a warning-only assertion.
- A test enumerates the reporting sites by grepping the resolved scripts
  directory and asserts every one of them reports the same diagnosis for the same
  condition — a site added upstream later fails it rather than escaping it. It
  must count what it found and compare against the enumeration, never assert a
  hardcoded eight: a fixed number passes while missing one of the two
  `session_context` branches, which is exactly how the count was wrong before.
- A test asserts the JSON site stays parseable and keeps its `error` and `hint`
  keys.
- A test asserts the nothing-anywhere case still contains every substring
  upstream's `[worktree-identity]` suite pins in stderr prose — `No developer
  set`, `init_developer.py`, `TRELLIS_DEVELOPER`, `linked git worktree` — so
  requirement 1's removal stays scoped to the unusable-file case.
- A test asserts `add_session.py` no longer contains the `if not developer:`
  guard after `ensure_developer` — a source assertion, because behavior tests
  cannot see a branch that is already unreachable.
- A test asserts each consumer listed above still behaves as it did.
- `make check` passes in this repository.

## Ownership and blockers

`.trellis/scripts/**` is vendored, and `AGENTS.md:25-28` requires a paste-ready
handoff rather than a local Trellis pull request. This task therefore produces a
patch against the fork plus a register entry, and lands here only through a
vendored refresh. Filing it in `~/repos/ai/Trellis` is an operator action; that
checkout is externally owned and currently dirty, so nothing here writes into it.

**Blocked on uptake, not on authoring.** The patch sits on top of `0740d1d6`,
which is untagged and not on `fork/main`, so the change cannot reach this
repository until a release and a refresh. Everything this task actually produces
— the patch file, the staged tests, the register entry — can be written now, so
the task stays open and selectable rather than parked. Its acceptance criteria
about behavior remain unticked until uptake; the authoring criteria do not.

## Out of scope

- The worktree fallback itself, its mechanism, and requirement 6 of `08-08`
  (empty `name=`) — all already implemented upstream.
- Changing what the identity file contains, or how it is first created.
- Editing `.trellis/scripts/**` in this repository, or writing into the fork.
