# Design: one identity diagnosis, several renderings

Requirements are in [`prd.md`](prd.md). This design is the reporting half of
`08-08-developer-identity-not-in-worktrees`, moved here on 2026-08-17 when the
enumeration showed eight reporting gates rather than two. Everything below is a
change **on top of `chore/task-backlog-2026-08`'s head** in
`~/repos/ai/Trellis/packages/cli/src/templates/trellis/scripts/` — `454046ca` at
writing. `0740d1d6` is history, not a base: it predates `_safe_developer_name`
(`b21a6675`, `5a9f5f9a`) and the `add_session.py` rewrite (`76c53c5a`, ~900
lines), so a patch cut against it will not apply. Re-read the files before
diffing; that branch moves.

The worktree fallback itself is already implemented there and is not this task's
business. What is missing is a resolution that carries a *reason*, and reporting
sites that agree about it.

## The resolution

`get_developer` still answers one question — the name, or `None` — and the
remaining call sites need different sentences from it. `None` cannot carry
"absent everywhere" versus "the primary copy is unreadable", so the reporting
sites cannot agree without each re-deriving the state. The change is one
resolution function that returns the reason, with `get_developer` kept as its
thin wrapper:

```python
class DeveloperResolution(NamedTuple):
    name: str | None
    source: Path | None      # the file the name came from, if any
    local_state: str         # "ok" | "missing" | "unusable"
    local_path: Path         # always the local candidate, existing or not
    fallback_state: str      # "ok" | "missing" | "unusable" | "unavailable"
    fallback_path: Path | None


def resolve_developer(repo_root: Path | None = None) -> DeveloperResolution
def get_developer(repo_root: Path | None = None) -> str | None   # .name
```

It reuses upstream's parts rather than replacing them: `main_worktree_root`
from `common/git.py` for the fallback root, `_read_developer_file` widened to
return a state alongside the name, and `_safe_developer_name` unchanged — a
name it rejects is `unusable`, which is the classification requirement 4 needs
anyway. `TRELLIS_DEVELOPER` keeps winning ahead of every file, and an
environment-supplied identity resolves with no diagnostic and no file paths in
any message.

`get_developer` keeps its exact signature and return type, so every existing
caller — including `check_developer` (upstream head `common/paths.py:163`;
`:97` in the vendored copy) and `show_developer_info` — keeps
working unchanged and inherits the fallback (`prd.md` requirement 6). One call site
does change, and only to get a reason rather than a bool: see `ensure_developer`
under Call-site messages.

`local_path` is always populated and `source` never substitutes for it. The
warning and the message shapes below must name *the file that is unusable*,
which is precisely the file `source` is not: with an unusable local copy and a
good fallback, `source` is the primary file; with nothing resolvable, `source`
is `None`. A resolution carries both paths so the formatter never has to
reconstruct one. `fallback_path` is `None` only when `fallback_state` is
`unavailable`.

An empty or whitespace `name=` value belongs in `unusable`, and upstream already
returns `None` for it through `_safe_developer_name`. Keep the classification
explicit anyway — `unusable`, not "not found" — because requirement 4's warning
must tell the two apart, and because it is what makes requirement 3's deletion
provably safe: that empty value was the one live input reaching
`add_session.py`'s branch in the vendored 0.6.14 copy, where `get_developer`
returned `""`, `check_developer` accepted it, and `if not developer:` rejected
it.

`unavailable` is distinct from `missing`: it means there is no main working
tree to consult (a primary checkout, or a `.git` this code cannot interpret),
not that the main working tree lacks the file. The difference matters only for
the messages.

### Precedence and warnings

| local `.developer` | main working tree | result |
|---|---|---|
| ok | anything | local name, no diagnostic |
| missing | ok | main name, **no diagnostic** |
| missing | missing / unavailable | `None`, caller reports "not initialized" |
| missing | unusable | `None`, caller names the primary path |
| unusable | ok | main name, **warning naming the local file** |
| unusable | missing / unavailable | `None`, caller names the local file |
| unusable | unusable | `None`, caller names both files |

Two rows carry the sharpest requirements. The `missing -> ok` row must stay
silent — that is `08-08`'s territory and upstream already satisfies it; a fresh
worktree is the normal case, not a degraded one, and this task must not add a
diagnostic to it. The `unusable ->
ok` row must warn (requirement 4), because a typo'd local identity silently
replaced by the primary one is a fork of the developer identity with no trace.

The warning names the malformed file and is rendered in the emitting gate's own
medium — a `stderr` line for most of them, a document line or a JSON `warning`
for the two that have no stderr of their own (see the medium table below). The
resolver returns a name regardless. Nothing about the warning changes an exit
code, a return value, or whether a call raises.

**Who emits it.** Not `resolve_developer`, and not `get_developer`: a resolver
that printed would add stderr to `safe_commit`, `paths:209`, and both
`session_context` consumers, which requirement 7 forbids.

`ensure_developer` alone is not enough either, and the call graph says so: it has
exactly **one** caller upstream, `add_session.py:1105`. Routing the warning only
through it would leave `task.py`, `task_store.py`, and `session_context.py` silent
about a forked identity.

So the rule is the same set this task already touches: **every reporting gate that
resolves the identity warns when the resolution came from a degraded local file.**
Each of the eight gates already branches on the resolution; the warning is the
truthy-but-degraded arm of the branch it is getting anyway, rendered in that
gate's own medium. `ensure_developer` and `get_developer.py` are two of those
gates, not a substitute for the rest.

**The medium must not be the failure medium.** A degraded resolution *succeeds*,
so the warning cannot ride the channel that gate uses to fail. Per gate:

| Gate | Failure medium | Degraded-success medium |
|---|---|---|
| `common/developer.py:161-165` (`ensure_developer`) | stderr prose + `sys.exit(1)` | stderr line, exit unchanged |
| `get_developer.py:21` | stderr prose, exit 1 | stderr line, name still on stdout, exit 0 |
| `common/task_store.py:325` | stderr prose | stderr line |
| `task.py:351` | JSON `{"error", "hint"}` on stderr | a **separate** JSON warning object on stderr, or a `warning` key — never an `error` key, which callers read as failure |
| `task.py:380` | stderr prose | stderr line |
| `common/session_context.py:602` | a line in the returned document | a warning line in the same document |
| `common/session_context.py:821` | a line in the record-mode document | a warning line in the same document |
| `common/task_queue.py:138` | a raised `ValueError` | **stderr line only** — see below |

`task_queue.py` is the one that forces the rule. Its `ValueError` is reachable
only when `get_developer` returns falsey (`:136-138`); a successful fallback
skips it entirely and returns tasks at `:140`. Raising in order to carry the
warning would break a call that currently works, and the existing success path
carries no channel of its own. So this gate warns on `stderr` and returns its
list unchanged — a library function writing one diagnostic line, which
requirement 7 permits because no consumer's return value or exit status moves.
If a reviewer rejects stderr from that module, the fallback position is to leave
`task_queue.py` out of requirement 4's warning set and say so in the patch,
never to raise.

Consumers — `safe_commit`, `paths:209`, `session_context:506`/`:736` — stay
silent, which is exactly the line requirement 7 draws: reporters may gain output,
consumers may not. The residual hole is therefore narrow and stated: code that
resolves the identity through a *consumer* path and never reaches a reporter
prints nothing. Closing that would require a printing resolver, which costs more
than it buys.

## Call-site messages

`resolve_developer`'s reason fields let every reporting site describe the same
condition the same way (requirement 2). Part of that is already shared and stays
shared: `DEVELOPER_HINT` (`common/paths.py:46-50`) names `TRELLIS_DEVELOPER` and
the worktree inheritance, and `common/developer.py:164`,
`common/task_store.py:326`, and `task.py:381` append it while `task.py:351`
carries it as the JSON `hint`. What is missing is the *leading* diagnosis, the
four gates that carry no hint at all (`get_developer.py:21`,
`common/session_context.py:602`, `common/session_context.py:821`,
`common/task_queue.py:138` — the complement of the four sites that name
`DEVELOPER_HINT` in source), and the
unusable-versus-absent distinction no site can currently make. One shared
formatter in `common/developer.py`, driven by a single rule: **name every file that exists
but is unusable, and recommend `init_developer.py` only when no consulted file
exists at all.** That rule produces the three shapes the precedence table needs:

- nothing anywhere → `Error: Developer not initialized.` plus the existing
  `Run: python3 ./.trellis/scripts/init_developer.py <your-name>` remedy and
  `DEVELOPER_HINT`. This case's substrings are pinned by
  `regression.test.ts:12655-12676`; keep them.
- the main checkout's copy is present but unusable → name that exact path and
  **do not** recommend `init_developer.py` (requirement 1): a second identity is
  not the fix for a corrupt first one.
- the local copy is unusable and no fallback resolves → name the local path, and
  the primary path as well only when that file also exists and is unusable.
  A missing or unavailable fallback has no path worth printing —
  `fallback_path` is `None` for `unavailable` — so the message names one file,
  not two. Still no `init_developer.py`: the file to repair is one the message
  just named. These are the table's last two rows, which the two shapes above do
  not cover.

`ensure_developer` prints it and exits 1 as it does today. It is the one call
site whose *plumbing* changes: today it asks `check_developer`
(upstream head `common/developer.py:161`) for a bool, which cannot carry a
reason, so it calls `resolve_developer` directly instead. `check_developer`
itself is untouched — it stays a re-exported public helper
(`common/__init__.py:73`) and inherits the fallback through `get_developer`.
`get_developer.py` (`:21`) prints the same diagnosis and exits 1, gaining the
remedy it lacks. `add_session.py` loses its branch (`:1108-1110`, behind
`ensure_developer` at `:1105`) — requirement 3.

**One diagnosis, several renderings.** "Report identically" cannot mean
byte-identical output everywhere, and the sites prove it: `task.py:351` emits
`{"error": ..., "hint": ...}` as JSON that an upstream regression test parses
(`packages/cli/test/regression.test.ts:12655-12676`), and
`get_context_text` / `get_context_text_record`
(`common/session_context.py:578`/`:803`, whose identity lines are `:602`/`:821`)
return whole context documents with their own headers. What the formatter owns is the *diagnosis* — which condition, which
paths, whether `init_developer.py` is the remedy — and each site renders it in
its own medium: prose to stderr, a `hint` field in JSON, a line inside a context
document. Requirement 2 is satisfied when no two sites disagree about the condition or
recommend different fixes for it, not when their bytes match — which is
requirement 5, stated so a reviewer cannot read requirement 2 as demanding the
impossible.
`common/task_queue.py:138` is a reporter too, in a fourth medium: it raises
`ValueError("Developer not set")`, so it carries the diagnosis in the exception
message.

`show_developer_info` (`common/developer.py:168`) keeps tolerating absence and
stays a non-error path, as do the consumers `prd.md` enumerates.

## The eight gates and their media

| Site | Renders as |
|---|---|
| `common/developer.py:161-165` | stderr prose, then `sys.exit(1)` |
| `get_developer.py:21` | stderr prose, exit 1 |
| `common/task_store.py:325` | stderr prose, colored |
| `task.py:351` | JSON `{"error", "hint"}` — schema preserved |
| `task.py:380` | stderr prose, colored |
| `common/session_context.py:602` | a line inside a returned document |
| `common/session_context.py:821` | a line inside the record-mode document |
| `common/task_queue.py:138` | `ValueError` message |

Eight, not seven: the two `session_context` branches sit in different functions
(`get_context_text` at `:578`, `get_context_text_record` at `:803`) and are patched
separately, so counting them as one row is how a coverage assertion misses one.

Each takes the diagnosis, not the sentence. The JSON site keeps its keys; the
document sites keep their headers; the exception keeps being an exception.

## Blast radius

Upstream only, and only within
`packages/cli/src/templates/trellis/scripts/`: `common/paths.py`,
`common/developer.py`, `get_developer.py`, `common/task_store.py`, `task.py`,
`common/session_context.py`, `common/task_queue.py`, `add_session.py` (deletion),
plus whatever `packages/cli/test/regression.test.ts` needs if the JSON `hint`
text changes. Nothing in this repository outside this task directory, the staged
tests, and the handoff register.

## Risks

- **Eight files upstream for a message contract.** Real, and the reason this is
  its own task: it is one coherent change, but not a small one, and it should not
  ride inside a worktree bug fix.
- **The wording has tests upstream, and not only for the JSON.**
  `regression.test.ts` carries eleven `[worktree-identity]` cases
  (`:12526-12723`). The no-identity-anywhere case (`:12655-12676`) asserts
  `created.stderr` contains `No developer set`, `init_developer.py`,
  `TRELLIS_DEVELOPER`, and `linked git worktree`, and that the parsed JSON
  `hint` contains the last two. So a reworded *prose* diagnosis can break the
  suite exactly like a reworded `hint`. Read those cases before touching any
  message, and update them in the same diff when a change is intended.
- **Enumeration drifts.** The site list is a snapshot; the acceptance test
  greps the tree instead of trusting it, so a site added later fails the test
  rather than escaping it.
- **Message-shape assertions pin wording.** If upstream words the shared
  diagnosis differently, the staged tests need updating at uptake. That is the
  cost of specifying messages, and it is smaller than eight sites disagreeing.
