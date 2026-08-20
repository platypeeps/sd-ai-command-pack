<!-- Superseded revision, preserved 2026-08-20. Written by a planning agent
     that was still running when this task was archived as won't-do; it landed
     at the live task path after the archive had moved the directory. Kept for
     reopen value only. The authoritative artifacts are design.md in this
     directory. This task will not be implemented — see prd.md Closure. -->

# Design: one identity diagnosis, several renderings

Requirements are in [`prd.md`](prd.md). This is the reporting half of
`08-08-developer-identity-not-in-worktrees`, moved here on 2026-08-17 when the
enumeration showed eight live reporting gates rather than two.

## The base

Everything below is a change on top of `~/repos/ai/Trellis` branch `main` at
`2749d3b4`, `packages/cli/package.json` version `0.6.16-sd.7`, under
`packages/cli/src/templates/trellis/scripts/`.

The earlier framing — a patch on top of `0740d1d6` on
`chore/task-backlog-2026-08`, blocked because that commit was untagged and not on
`fork/main` — is obsolete and has been removed. The worktree fallback shipped:
it is on `fork/main`, it is in `0.6.16-sd.7`, and it is already vendored into
this repository. `diff -rq --exclude=__pycache__` between the fork's scripts
tree and `.trellis/scripts` here is **empty**, so:

- every line number in this document is valid against both trees;
- the patch can be cut from the pack's own copy without reading the
  externally-owned fork checkout, which is dirty;
- the equality itself is a precondition, re-checked at implementation time. A
  non-empty diff means the fork moved and the base must be re-read from it.

`resolve_developer` and `DeveloperResolution` do not exist anywhere in either
tree. This is unstarted work.

The worktree fallback itself is already implemented and is not this task's
business. What is missing is a resolution that carries a *reason*, and reporting
sites that agree about it.

## The resolution

`get_developer` (`common/paths.py:121-160`) answers one question — the name, or
`None` — and the reporting sites need different sentences from it. `None` cannot
carry "absent everywhere" versus "the primary copy is unusable", because
`_read_developer_file` (`:104-118`) collapses four distinct states into it: the
file is missing, the read raised `OSError`, there is no `name=` line, or
`_safe_developer_name` (`:83-101`) rejected the value. The reporting sites
therefore cannot agree without each re-deriving the state, and none of them can.

The change is one resolution function that returns the reason, with
`get_developer` kept as its thin wrapper:

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
(`common/git.py:143-192`) for the fallback root, `_read_developer_file` widened
to return a state alongside the name, and `_safe_developer_name` unchanged — a
name it rejects is `unusable`, which is exactly the classification requirement 4
needs. `TRELLIS_DEVELOPER` keeps winning ahead of every file, and an
environment-supplied identity resolves with no diagnostic and no file paths in
any message.

`get_developer` keeps its exact name, signature, return type, and docstring
contract, so every existing caller keeps working unchanged and inherits the
fallback (requirement 8). That includes `check_developer`
(`common/paths.py:163-172`), `show_developer_info`
(`common/developer.py:170-184`), and the four pack-owned `session-start.py`
sites in this repository. One call site does change, and only to get a reason
rather than a bool: see `ensure_developer` under Call-site messages.

`local_path` is always populated and `source` never substitutes for it. The
warning and the message shapes below must name *the file that is unusable*,
which is precisely the file `source` is not: with an unusable local copy and a
good fallback, `source` is the primary file; with nothing resolvable, `source`
is `None`. A resolution carries both paths so the formatter never has to
reconstruct one. `fallback_path` is `None` only when `fallback_state` is
`unavailable`.

An empty or whitespace `name=` value belongs in `unusable`, and upstream already
returns `None` for it through `_safe_developer_name`. Keep the classification
explicit anyway — `unusable`, not "missing" — because requirement 4's warning
must tell the two apart, and because it is what makes requirement 3's deletion
provably safe: that empty value was the one live input reaching
`add_session.py`'s branch back in the vendored 0.6.14 copy, where
`get_developer` returned `""`, `check_developer` accepted it, and
`if not developer:` rejected it.

`unavailable` is distinct from `missing`: it means there is no main working tree
to consult (a primary checkout, or a `.git` this code cannot interpret), not
that the main working tree lacks the file. The difference matters only for the
messages — `unavailable` has no path worth printing.

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

Two rows carry the sharpest requirements. The `missing → ok` row must stay
silent — that is `08-08`'s territory and upstream already satisfies it; a fresh
worktree is the normal case, not a degraded one, and this task must not add a
diagnostic to it. The `unusable → ok` row must warn (requirement 4), because a
typo'd local identity silently replaced by the primary one is a fork of the
developer identity with no trace, and `common/paths.py:152-160` produces it
today with no output at all.

The warning names the malformed file and is rendered in the emitting gate's own
medium. The resolver returns a name regardless. Nothing about the warning changes
an exit code, a return value, or whether a call raises.

**Who emits it.** Not `resolve_developer`, and not `get_developer`: a resolver
that printed would add stderr to `safe_commit.py:95`, `paths.py:209`, both
`session_context` consumers (`:506`, `:736`), `init_developer.py:37`, and all
four pack-owned session banners — which requirement 8 forbids.

`ensure_developer` alone is not enough either, and the call graph says so: `grep
-rn 'ensure_developer(' .trellis/scripts` finds exactly **one** caller,
`add_session.py:1260`. Routing the warning only through it would leave `task.py`,
`task_store.py`, `session_context.py`, and `task_queue.py` silent about a forked
identity.

So the rule is the set this task already touches: **every reporting gate that
resolves the identity warns when the resolution came from a degraded local
file.** Each of the eight live gates already branches on the resolution; the
warning is the truthy-but-degraded arm of the branch it is getting anyway,
rendered in that gate's own medium. `ensure_developer` and `get_developer.py`
are two of those gates, not a substitute for the rest.

**The medium must not be the failure medium.** A degraded resolution *succeeds*,
so the warning cannot ride the channel that gate uses to fail:

| Gate | Failure medium | Degraded-success medium |
|---|---|---|
| `common/developer.py:162-165` (`ensure_developer`) | stderr prose + `sys.exit(1)` | stderr line, exit unchanged |
| `get_developer.py:21` | stderr prose, exit 1 | stderr line, name still on stdout, exit 0 |
| `common/task_store.py:349-351` | stderr prose, red | stderr line |
| `task.py:359-364` | JSON `{"error", "hint"}` on stderr | a **separate** JSON warning object on stderr, or a `warning` key — never an `error` key, which callers read as failure |
| `task.py:389-392` | stderr prose, red | stderr line |
| `common/session_context.py:600-604` | a line in the returned document | a warning line in the same document |
| `common/session_context.py:819-823` | a line in the record-mode document | a warning line in the same document |
| `common/task_queue.py:136-138` | a raised `ValueError` | **stderr line only** — see below |

`task_queue.py` is the gate that forces the rule. Its `ValueError` is reachable
only when the resolved name is falsey (`:136-138`); a successful fallback skips
it entirely and returns tasks at `:140`. Raising in order to carry the warning
would break a call that currently works, and the existing success path carries
no channel of its own. So this gate warns on `stderr` and returns its list
unchanged — a library function writing one diagnostic line, which requirement 8
permits because no consumer's return value or exit status moves. **Fallback
position**, if a reviewer rejects stderr from that module: leave `task_queue.py`
out of requirement 4's warning set and say so in the patch. Never raise.

Consumers — `safe_commit`, `paths:209`, `session_context:506`/`:736`,
`init_developer.py:37`, `paths:542`, `check_developer`, `show_developer_info`,
and the four pack banners — stay silent, which is exactly the line requirement 8
draws: reporters may gain output, consumers may not. The residual hole is
therefore narrow and stated: code that resolves the identity through a *consumer*
path and never reaches a reporter prints nothing about a forked identity.
Closing that would require a printing resolver, which costs more than it buys.

## Call-site messages

`resolve_developer`'s reason fields let every reporting site describe the same
condition the same way (requirement 2). Part of that is already shared and stays
shared: `DEVELOPER_HINT` (`common/paths.py:46-50`) names `TRELLIS_DEVELOPER` and
worktree inheritance, and four sites carry it — `common/developer.py:164`,
`common/task_store.py:350`, `task.py:391`, and `task.py:361` as the JSON `hint`.
What is missing is the *leading* diagnosis, the four gates that carry no hint at
all (`get_developer.py:21`, `common/session_context.py:602` and `:821`,
`common/task_queue.py:138` — precisely the complement of the four that name
`DEVELOPER_HINT` in source), and the unusable-versus-absent distinction no site
can currently make.

One shared formatter in `common/developer.py`, driven by a single rule: **name
every file that exists but is unusable, and recommend `init_developer.py` only
when no consulted file exists at all.** That rule produces the three shapes the
precedence table needs:

- **nothing anywhere** → the existing wording, preserved:
  `Error: Developer not initialized.` /
  `Error: No developer set. ...` per site, plus the existing
  `Run: python3 ./.trellis/scripts/init_developer.py <your-name>` remedy and
  `DEVELOPER_HINT`. This case's substrings are pinned upstream; keep them (see
  The pinned contract).
- **the main checkout's copy is present but unusable** → name that exact path and
  **do not** recommend `init_developer.py` (requirement 1): a second identity is
  not the fix for a corrupt first one.
- **the local copy is unusable and no fallback resolves** → name the local path,
  and the primary path as well only when that file also exists and is unusable.
  A missing or unavailable fallback has no path worth printing —
  `fallback_path` is `None` for `unavailable` — so the message names one file,
  not two. Still no `init_developer.py`: the file to repair is one the message
  just named. These are the table's last two rows, which the two shapes above do
  not cover.

`ensure_developer` prints it and exits 1 as it does today. It is the one call
site whose *plumbing* changes: today it asks `check_developer`
(`common/paths.py:163-172`) for a bool at `common/developer.py:161`, and a bool
cannot carry a reason, so it calls `resolve_developer` directly instead.
`check_developer` itself is untouched — it stays a re-exported public helper
(`common/__init__.py:73`) and keeps inheriting the fallback through
`get_developer`. `get_developer.py:21` prints the same diagnosis and exits 1,
gaining the remedy it lacks entirely. `add_session.py:1262-1265` loses its branch
(requirement 3).

**One diagnosis, several renderings.** "Report identically" cannot mean
byte-identical output, and the sites prove it: `task.py:359-364` emits JSON an
upstream test parses, `get_context_text` (`:578`) and `get_context_text_record`
(`:803`) return whole documents with their own headers, and
`common/task_queue.py:138` raises. What the formatter owns is the *diagnosis* —
which condition, which paths, whether `init_developer.py` is the remedy — and
each site renders it in its own medium. Requirement 2 is satisfied when no two
sites disagree about the condition or recommend different fixes for it, not when
their bytes match; requirement 7 exists so a reviewer cannot read requirement 2
as demanding the impossible.

## The pinned contract, and the one thing that cannot move

Upstream's regression suite constrains the wording harder than a reading of
requirement 2 suggests. In `packages/cli/test/regression.test.ts`, the suite
`describe("regression: a linked worktree inherits developer identity")` spans
`:12597-12922` and holds eleven `[worktree-identity]` cases at `:12717-12921`.
The one that matters is `:12846-12867`, "with no identity anywhere, the error
names all three sources":

```ts
expect(created.stderr).toContain("No developer set");      // task_store.py:349
expect(created.stderr).toContain("init_developer.py");
expect(created.stderr).toContain("TRELLIS_DEVELOPER");     // DEVELOPER_HINT
expect(created.stderr).toContain("linked git worktree");   // DEVELOPER_HINT
...
expect(payload.error).toBe("No developer set");            // :12863 — EXACT
expect(payload.hint).toContain("TRELLIS_DEVELOPER");
expect(payload.hint).toContain("linked git worktree");
```

Two different strengths, and the design turns on the difference:

- The **prose** assertions are `toContain`. Site 3's message may gain leading or
  trailing text, as long as those four substrings survive in the
  nothing-anywhere case. That is what makes requirement 1's removal of
  `init_developer.py` safe: it applies only to the unusable-file cases, which
  this test never exercises.
- The **JSON `error`** assertion is `toBe` — exact equality on `"No developer
  set"`. Site 4's `error` value is a frozen string, and no amount of "the sites
  should share one leading sentence" justifies rewording it silently. **Design
  decision: `error` keeps the value `"No developer set"` verbatim.** New
  information for the JSON site goes in `hint`, or in an additional key the
  parser ignores. The shared *diagnosis* is what unifies; the JSON `error` field
  is the diagnosis's identifier, not its prose.

The consequence for requirement 2 is worth stating plainly: the five leading
sentences do not all converge on one string. `Developer not set` (site 8) and
`Not initialized` (sites 6, 7) can and should adopt the shared phrasing, and
sites 1 and 2 can too. Site 4's `error` cannot. Unification is at the level of
the diagnosis — same condition, same paths named, same remedy or absence of one
— with one field pinned by an external test. If a future change does want to
move it, that is a deliberate breaking test change: update
`regression.test.ts:12863` in the same diff and say so in the handoff.

## The nine sites, and their media

| # | Site | Renders as |
|---|---|---|
| 1 | `common/developer.py:162-165` | stderr prose, then `sys.exit(1)` |
| 2 | `get_developer.py:21` | stderr prose, exit 1 |
| 3 | `common/task_store.py:349-351` | stderr prose, red |
| 4 | `task.py:359-364` | JSON `{"error", "hint"}` — `error` value frozen |
| 5 | `task.py:389-392` | stderr prose, red |
| 6 | `common/session_context.py:600-604` (`get_context_text`, `:578`) | a line inside a returned document |
| 7 | `common/session_context.py:819-823` (`get_context_text_record`, `:803`) | a line inside the record-mode document |
| 8 | `common/task_queue.py:136-138` | `ValueError` message |
| 9 | `add_session.py:1262-1265` | **deleted** — dead branch behind `ensure_developer` at `:1260` |

Eight live gates, not seven: rows 6 and 7 sit in different functions and are
patched separately, so counting them as one row is how a coverage assertion
misses one. Sites 4 and 5 likewise sit in one function (`cmd_list`, `task.py:344`)
over one resolution (`:349`) but in two arms, and both are patched.

Each takes the diagnosis, not the sentence. The JSON site keeps its keys and its
`error` value; the document sites keep their headers; the exception keeps being
an exception.

## Blast radius, and the two-repo split

**Upstream (`~/repos/ai/Trellis`), where all behavior changes:** seven files
under `packages/cli/src/templates/trellis/scripts/` —

| File | Change | Rough size |
|---|---|---|
| `common/paths.py` | `DeveloperResolution`, `resolve_developer`, widened `_read_developer_file`, `get_developer` as `.name` wrapper | ~80-110 new lines |
| `common/developer.py` | shared diagnosis formatter + `ensure_developer` rewiring | ~40-60 new lines |
| `get_developer.py` | gate rewrite | ~10-25 |
| `common/task_store.py` | gate rewrite | ~10-25 |
| `task.py` | two gate rewrites (JSON arm, prose arm) | ~20-40 |
| `common/session_context.py` | two gate rewrites | ~20-40 |
| `common/task_queue.py` | gate rewrite | ~10-25 |
| `add_session.py` | delete three lines | -3 |

Plus `packages/cli/test/regression.test.ts` if — and only if — the JSON `error`
value or a pinned prose substring is deliberately changed. Roughly 400-500 lines
of upstream diff. This is a refactor, not a string sweep, and estimating it as
one is the mistake that hid it inside `08-08`.

**This repository:** nothing outside this task directory, the patch file under
`08-08-upstream-handoff-register/research/`, and register entry 14. Explicitly
**not** `.trellis/scripts/**` (vendored) and **not** the four pack-owned
`session-start.py` sites (see `prd.md`; verified unchanged, not modified).

## Compatibility

- `get_developer`'s name, signature, `str | None` return, and silence are
  unchanged, so all 16 caller lines keep compiling and behaving. Fifteen of them
  are untouched; only `common/developer.py:161` moves, from `check_developer` to
  `resolve_developer`.
- `check_developer` stays exported from `common/__init__.py:73` with the same
  bool contract, so any out-of-tree caller is unaffected.
- `DeveloperResolution` and `resolve_developer` are **additive**. A tree that has
  not taken the patch has no such symbol, which is what makes
  `grep -rn 'resolve_developer' .trellis/scripts` a clean landed/not-landed
  signal — it returns 0 hits today and must return non-zero after uptake.
- The JSON schema at site 4 is unchanged: same two keys, same `error` value. A
  `warning` key may be *added* for the degraded case; nothing is removed or
  renamed.
- Python floor: `NamedTuple` with class syntax and `X | None` annotations are
  already used throughout `common/paths.py`, so the patch introduces no new
  version requirement.

## Rollout and rollback

Rollout is a chain this task only starts:

1. Patch authored and verified here (run A / run B in `implement.md`).
2. Handoff register updated; the operator files the task in the fork. **No pull
   request is opened against Trellis from this session** — `AGENTS.md:25-28`
   requires explicit per-PR approval.
3. Upstream merges and releases.
4. A vendored refresh brings it into `.trellis/scripts`.
5. The staged suite moves from `research/` into `tests/` and must then run with
   **zero skips**.

Rollback, per repo:

- **This repository, before uptake:** delete the patch file, the staged suite,
  and revert the register entry. Nothing shipped behavior-wise, so there is no
  payload digest, manifest bump, or `make generate` step to undo. `git status
  --short -- .trellis/scripts` must be empty at every point — if it is not, the
  scope rule was violated and that is the rollback.
- **Scratch trees:** every apply/run happens in a `mktemp -d` copy; `rm -rf`
  undoes it completely.
- **The fork:** nothing is written to it, so there is nothing to roll back.
  `git -C ~/repos/ai/Trellis status --short` must be identical before and after.
- **After uptake, if the change proves wrong:** the additive shape makes reverting
  cheap — restore `get_developer`'s body, drop `resolve_developer` and the
  formatter, and revert the nine site edits. No caller outside the gates changed,
  so no consumer needs touching.

## Risks

- **Seven files upstream for a message contract.** Real, and the reason this is
  its own task: it is one coherent change, but not a small one, and it should not
  ride inside a worktree bug fix.
- **One pinned string is pinned by equality, not containment.** `payload.error`
  at `regression.test.ts:12863` is the trap: a reviewer reading "unify the
  leading sentence" will reach for it first, and `toBe` turns that into a red
  suite. The design freezes it explicitly for that reason.
- **Enumeration drifts.** The site list is a snapshot of `2749d3b4`; the
  acceptance test greps the tree instead of trusting it, so a site added later
  fails the test rather than escaping it.
- **Message-shape assertions pin wording.** If upstream words the shared
  diagnosis differently from this patch, the staged tests need updating at
  uptake. That is the cost of specifying messages, and it is smaller than eight
  gates disagreeing.
- **The fork moves under the patch.** The base is `main` today, but `main` is not
  frozen. The `diff -rq` precondition catches it before the patch is cut, not
  after; if it is non-empty, re-read the files and re-derive the line numbers
  rather than rebasing blind.
- **Uptake latency.** The patch may sit unreleased for a while. That is expected
  and is why the staged suite lives outside the repo gate (`Makefile:49` fails on
  any skip) rather than the gate being weakened to accommodate it.
