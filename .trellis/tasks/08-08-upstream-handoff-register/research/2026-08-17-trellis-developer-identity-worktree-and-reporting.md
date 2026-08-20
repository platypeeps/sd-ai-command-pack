# Trellis upstream: developer identity in linked worktrees, and its reporting

Paste-ready material for register entries 13 and 14. Both halves are owned by
the Trellis fork; `.trellis/scripts/**` in this repository is vendored 0.6.14
and `AGENTS.md:25-28` forbids a local upstream pull request without explicit
per-PR approval. Nothing here writes into `~/repos/ai/Trellis`; that checkout is
externally owned and was read only.

Origin: task `08-08-developer-identity-not-in-worktrees` (this repo). Its
reporting half was split out on 2026-08-17 into
`08-17-trellis-identity-message-consistency`.

## Entry 13 — the worktree fallback: already implemented upstream

`.trellis/.developer` is gitignored, so a linked worktree never receives it. In
vendored 0.6.14 `get_developer()` reads only the current root's copy, so every
identity-dependent script fails in a fresh worktree — `add_session.py` most
visibly, since the journal path derives from the identity.

**Upstream already fixes this.** At
`packages/cli/src/templates/trellis/scripts/`:

| location | what it does |
|---|---|
| `common/paths.py:121-160` | `get_developer` = env `TRELLIS_DEVELOPER`, then the local file, then the main working tree's file |
| `common/paths.py:83-118` | `_safe_developer_name` / `_read_developer_file` — rejects path-escaping and empty names |
| `common/git.py:143-192` | `main_worktree_root` + `_probe_main_worktree_root` |

The mechanism is worth keeping as-is: `_probe_main_worktree_root` asks Git
(`git worktree list --porcelain`, first record is the main working tree, plus a
`bare` check, and `main_root == current_root` returns `None`). A plumbing-parsing
resolver — read the `.git` gitfile, walk to the parent of `commondir` — was
designed in this repo and **withdrawn**: it misidentifies a bare repository
nested inside an unrelated checkout, which the porcelain listing cannot do.

History, for anyone cutting a patch nearby: the fallback arrived in `0740d1d6`
(2026-08-09) on `chore/task-backlog-2026-08`. That commit is **not** a usable
patch base — `_safe_developer_name` (`b21a6675`, `5a9f5f9a`) and the
~900-line `add_session.py` rewrite (`76c53c5a`) postdate it. Use the branch head
(`454046ca` at writing) and re-read the files; the branch moves.

Upstream also ships tests for it: `packages/cli/test/regression.test.ts` carries
eleven `[worktree-identity]` cases (`:12526-12723`) covering a fresh worktree with
no setup, a later main-checkout change, the full `--assignee > TRELLIS_DEVELOPER >
local file > main checkout` precedence, traversal- and drive-letter-shaped
identities, a whitespace-only env var, the no-identity-anywhere message, a linked
worktree of a bare repo, **a bare repo nested inside an unrelated checkout that
must not leak that checkout's identity** (`:12692`), and a non-repository
directory. That nested-bare-repo case is the one the withdrawn plumbing-parsing
resolver would have failed, tested upstream by name.

**Resolution class: upgrade-delivered, unreleased.** `0740d1d6` is untagged and
not on `fork/main`, so this repository cannot take the fix through a vendored
refresh yet. Task `08-08` is parked on exactly that release chain.

### Evidence: the staged suite, run against both trees

`.trellis/tasks/archive/2026-08/08-08-developer-identity-not-in-worktrees/research/staged_test_worktree_identity.py`
(this repo) gates every behavioral test on a throwaway-fixture probe rather than
a symbol name, and resolves its scripts directory from
`SD_DEVELOPER_IDENTITY_SCRIPTS`. It sits in `research/` rather than `tests/`
because `Makefile:49` fails this repository's gate on any skip, and the suite
skips until the release lands; the never-skipping half (`.developer` stays
gitignored) lives in `tests/test_developer_identity.py`. Two runs, reported as
two:

```text
# vendored 0.6.14 — .trellis/scripts
Ran 9 tests in 1.261s
OK (skipped=9)

# a mktemp -d copy of upstream's scripts/ at 454046ca
Ran 9 tests in 4.021s
OK
```

The upstream run is the evidence the fix works:
9 passed, 0 skipped, covering a fresh worktree, local precedence, an unusable
local file, an empty `name=`, `TRELLIS_DEVELOPER` precedence, `git worktree
move`, `--relative-paths` worktrees, and `add_session.py` end to end.

Two fixture facts cost a debugging round and are worth repeating in any
reimplementation:

- The fixture must **gitignore** `.trellis/.developer`. Committing it makes the
  worktree inherit the file and every test passes without any fallback.
- `get_workspace_dir` is `repo_root / .trellis/workspace/<developer>`, so
  `add_session.py` in a worktree writes into *that worktree's* workspace. The
  realistic fixture commits the workspace (Git carries it) while the identity
  stays ignored.

## Entry 14 — the reporting half: a fork task to file

Split out because the enumeration found **eight** reporting gates in four output
media, not the two the original PRD assumed. `get_developer` answers a name or
`None`, and `None` cannot distinguish "no identity file anywhere" from "the file
exists and is unreadable" — so no site can say which happened, and most of them
recommend `init_developer.py`, i.e. creating a *second* identity, even when the
first exists and is merely broken. Two do not even do that much:
`get_developer.py:21` prints no remedy and `common/task_queue.py:138` raises a
bare `Developer not set`. What upstream already shares is `DEVELOPER_HINT`
(`common/paths.py:46-50`), appended at `common/developer.py:164`,
`common/task_store.py:326`, and `task.py:381` and carried as the JSON `hint` at
`task.py:351`; the leading diagnosis is what disagrees. The workspace journal path derives from the
identity, so a silently forked identity splits a developer's history.

At `454046ca`, under `packages/cli/src/templates/trellis/scripts/`:

| Site | Medium |
|---|---|
| `common/developer.py:161-165` (`ensure_developer`) | stderr prose, `sys.exit(1)` |
| `get_developer.py:21` | stderr prose, exit 1 — no remedy at all |
| `common/task_store.py:325` | stderr prose, colored |
| `task.py:351` | **JSON** `{"error", "hint"}` on stderr |
| `task.py:380` | stderr prose, colored |
| `common/session_context.py:602` (`get_context_text`) | a line inside a returned context **document** |
| `common/session_context.py:821` (`get_context_text_record`) | a line inside the record-mode document |
| `common/task_queue.py:138` | a raised `ValueError("Developer not set")` |

Plus `add_session.py:1108-1110`, a dead `if not developer:` branch behind
`ensure_developer` at `:1105`, whose one live input (an empty `name=`) upstream
now rejects.

Enumerate with **two** passes, because neither alone is sufficient: a
message-string grep misses `task_queue.py` (it raises), and a `get_developer(`
caller grep cannot tell a reporter from a consumer.

"Report identically" cannot mean byte-identical output: `task.py:351`'s JSON is
parsed by `packages/cli/test/regression.test.ts:12655-12676`, the session-context sites
return whole documents, and `task_queue.py` raises. The contract is **one
diagnosis, several renderings** — which condition, which paths, and whether
`init_developer.py` is the remedy — rendered per medium.

Proposed shape: `resolve_developer()` returning a `DeveloperResolution`
(name, source, local state and path, fallback state and path) with
`get_developer()` kept as `resolve_developer(root).name`, signature and
`str | None` return unchanged, so every consumer is untouched. One formatter in
`common/developer.py`. Rule: **name every file that exists but is unusable, and
recommend `init_developer.py` only when no consulted file exists at all.** An
unusable *local* file that falls back to a good primary must warn naming that
file — otherwise a typo'd identity is silently replaced with no trace.

That warning belongs to **every** gate that resolves the identity, not to
`ensure_developer` (one caller upstream, `add_session.py:1105`) — and it must use
a medium that is not that gate's failure medium. `common/task_queue.py` is the
case that proves the point: its `ValueError` fires only when the name is falsey
(`:136-138`), so a successful fallback skips it; raising in order to carry a
warning would break a working call. That gate writes one stderr line and returns
its list unchanged.

Full requirements, precedence table, and step plan:
`.trellis/tasks/08-17-trellis-identity-message-consistency/` (`prd.md`,
`design.md`, `implement.md`). The patch itself is that task's Step 1 and does not
exist yet; filing the fork task is an operator action.

**Resolution class: Trellis fork task, to be filed.** No pull request is opened
against Trellis without explicit per-PR approval.
