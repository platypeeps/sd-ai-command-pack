# Design: resolve the developer identity from the main working tree

## Current lines

The PRD's line references were written on 2026-08-08 and some had drifted; they
were corrected in `prd.md` on 2026-08-16 to the positions below, so the two
artifacts now cite the same lines. Verified in this checkout's **vendored 0.6.14
copy**; upstream's current source has moved well past it, and every line cited
for the patch itself is an upstream line, marked as such where it appears:

| What | Position |
|---|---|
| `.developer` gitignore entry | `.trellis/.gitignore:2` |
| `get_developer()` — the owning resolver | `common/paths.py:69` |
| its read/parse body | `:83-94` |
| the `name=` split that can yield `""` | `:90` (its `startswith("name=")` guard is `:88`) |
| `check_developer()` | `:97`, returning `get_developer(...) is not None` at `:106` |
| `ensure_developer()` message + remedy | `common/developer.py:161-163`, including the `sys.exit(1)` |
| `show_developer_info()` tolerating absence | `:166` (def), `:177-178` (the tolerated branch) |
| `get_developer.py` bare message | `:21` |
| `add_session.py` near-dead branch | `:527-529` (its message is `:528`) |
| its preceding `ensure_developer` | `:524` |

The vendored copy's `common/paths.py` imports only `re`, `datetime`, and
`pathlib`. That constraint shaped the withdrawn design below and no longer
applies: upstream's `common/git.py` already runs Git, and its resolver calls it.
The concern it came from — `add_session.py` running with `--no-commit` because a
nested process may not touch the index — is about writing the index, not about
running `git worktree list`, which is a read.

## Ownership: this lands upstream first

`.trellis/scripts/**` is vendored. Its entire local history is two vendored
refreshes plus the bootstrap (`d10d4e95`, `146a5ede`, `2ca8cbbf`) — there is no
local divergence today.

A local edit would not be *silently* reverted: Trellis 0.6.14 classifies a
hash-divergent vendored file as user-modified and prompts, overwriting without
asking only under `--force` (`~/repos/ai/Trellis/packages/cli/src/commands/update.ts:1025,1133`),
and this repository's own prior refresh ran that forced path behind a two-part
safety gate (`.trellis/workspace/sdelmas/journal-7.md:1773`). The cost is subtler and worse: the
divergence becomes a prompt every operator must answer correctly, forever, in a
tree where the pack has no drift gate to notice a wrong answer — surface
closure covers `templates/**` and its mirrors, not `.trellis/scripts/**`. A
single `--force` refresh, which is the path this repository has actually taken,
drops the edit with no gate firing.

So the deliverable of this task is **an upstream handoff**, per `AGENTS.md:25-28`,
and the local landing happens through the normal vendored refresh. The PRD
anticipated exactly this and asked for the decision here rather than during
implementation.

### What upstream already has — checked, not assumed

The fork at `~/repos/ai/Trellis` has **already implemented requirement 1**, on
branch `chore/task-backlog-2026-08`. `0740d1d6` (2026-08-09, *feat(scripts):
resolve developer identity in linked worktrees*) introduced it; the branch has
moved on since, so **the base for everything below is that branch's head**, at
this writing `454046ca`, not `0740d1d6` itself. Three later commits matter:
`76c53c5a` rewrites `add_session.py` (≈900 lines, which is why its line numbers
differ so far from the vendored copy's), and `b21a6675` plus `5a9f5f9a` add and
extend `_safe_developer_name`. Line numbers below are that head's:

- `common/paths.py:121-160` — `get_developer` resolves `TRELLIS_DEVELOPER`, then
  the local `.developer`, then `main_worktree_root(repo_root)`'s copy.
- `common/git.py:143-192` — `main_worktree_root` asks Git rather than parsing
  plumbing: `git worktree list --porcelain`, whose first record *is* the main
  working tree, plus a `bare` check, and a final `main_root == current_root`
  test that returns `None` in the main checkout itself.
- `common/paths.py:83-118` — `_read_developer_file` routes the value through
  `_safe_developer_name`, which rejects `""`, `.`, `..`, and anything carrying a
  separator or a colon. That helper is `b21a6675`/`5a9f5f9a`, not `0740d1d6`; at
  `0740d1d6` the same empty-name case was already closed more narrowly by
  `line.split("=", 1)[1].strip() or None` (`paths.py:95` there).

None of it is on **a tag or on `fork/main`** — `git tag --contains` is
empty, `git describe --contains` fails, and `git branch -r --contains` names only
`fork/chore/task-backlog-2026-08`. The published version is still `0.6.14`, which
is what this repository vendors. So the fix exists in source and is unreachable
by `trellis update` today.

Executed, not read: a throwaway primary-plus-worktree fixture against a copy of
that source, calling `paths.get_developer(root)` directly.

| fixture | result |
|---|---|
| primary checkout, `name=probe-dev` | `'probe-dev'` |
| linked worktree, nothing copied in | `'probe-dev'` |
| worktree with local `name=` (empty value) | `'probe-dev'` — no `''`, requirement 6 |
| worktree with a `.developer` holding no `name=` line | `'probe-dev'` |
| worktree with local `name=local-dev` | `'local-dev'` — precedence holds |

No warning was emitted for either unusable local file: requirement 7, still open.

Two consequences for this plan, and both matter more than any wording in it:

1. **Do not hand upstream a second implementation of requirement 1.** It is
   written, and by a better mechanism than the one designed below.
2. **The gaps that remain are requirements 3, 4, 5, and 7**, all still open in
   that same source. Those are the handoff.

Requirement 6's empty-`name=` hole (`get_developer` returning `""`, which
`check_developer` accepts) is closed upstream by `_safe_developer_name`; it is
open only in the vendored 0.6.14 copy, so it needs no patch — only the refresh.

### The plumbing-parsing resolver is withdrawn

Everything under "Rejected alternative" below was designed
before that source was read. It is kept as the rejected alternative, because its
rejection is evidence: upstream's docstring names a failure it cannot survive —
a **bare repository sitting inside an unrelated checkout** (`~/repos/project.git`
under a `~/repos` that is itself a repository). Deriving the main working tree as
the parent of the common directory then lands on a real checkout with a real
`.developer`, and the wrong identity is indistinguishable from a hit. `git
worktree list --porcelain` cannot make that mistake, because Git reports the main
working tree instead of the resolver inferring it.

The empirical verification recorded below still stands as far as it goes — the
guards do accept plain, moved, and `--relative-paths` worktrees and do reject a
copied one — and it is exactly the kind of check that cannot catch a case its
author never imagined. Upstream shelling out to `git` also disposes of the
`--separate-git-dir` exclusion this design had to declare out of scope, and of
the `subprocess`-free constraint the module no longer honours (upstream's
`common/git.py` already runs Git).

### Why not fix it in a pack-owned wrapper instead

`scripts/sd-ai-command-pack-record-session.py` already wraps `add_session.py`
and could seed the identity into a worktree itself. Rejected: it repairs one
caller, which is the exact shape the PRD rejects for `08-07`'s requirement 8.
`get_developer.py`, `ensure_developer`, and every future caller would still
fail, and the pack would own a permanent workaround for a resolver bug it
cannot see. A wrapper is the right place for pack policy, not for the meaning
of "who is the developer".

## The reporting half moved out

The resolution-with-a-reason design (`DeveloperResolution`, `resolve_developer`,
the precedence table, and the shared formatter across every reporting site) moved
to `08-17-trellis-identity-message-consistency` on 2026-08-17, together with `prd.md` requirements 3, 4, 5, and 7. It
lives there in full; this file does not keep a copy, because two copies of a
behavior table is how they start disagreeing.

What remains here: the worktree resolution itself, which upstream has already
implemented, and the evidence above that it works.

## Rejected alternative: finding the main working tree without `git`

A linked worktree's `.git` is a *file*:

```text
gitdir: /path/to/primary/.git/worktrees/wt-b
```

and that directory contains a `commondir` file pointing at the common `.git`
(normally `../..`).

**A `.git` file is not by itself a linked worktree.** `git init
--separate-git-dir` produces a primary checkout whose `.git` is also a gitfile
(`gitrepository-layout(5)`), and Git guarantees only that the common directory
is the main worktree's `$GIT_DIR` — not that it sits inside the main worktree
(`git-worktree(1)`). So neither "`.git` is a file" nor "the common dir's parent
is the main worktree" is sound on its own, and a `--separate-git-dir` layout
would send the resolver somewhere that is not a working tree at all.

Two guards close that, and the resolver returns `None` unless both hold:

1. **Discriminate on the worktree administrative layout, not on the gitfile.**
   A linked worktree's `$GIT_DIR` is `<common>/worktrees/<name>` and contains
   both a `commondir` and a `gitdir` file. Require the directory named by
   `gitdir:` to contain `commondir`, to contain `gitdir`, and to have a parent
   named `worktrees`. A `--separate-git-dir` primary satisfies none of these.

   Existence checks alone are not enough — a fabricated or stale tree can
   satisfy them — so require the two relationships Git actually guarantees
   (`gitrepository-layout(5)`), both after `resolve()`:

   - the private directory *is* `<resolved commondir>/worktrees/<name>`:
     `admin_dir.parent.parent == common_dir`; and
   - `<admin_dir>/gitdir` names *this* worktree's gitfile: its contents resolve
     to `repo_root/.git`.

   Every one of these paths may be relative, and each has its own base: the
   gitfile's `gitdir:` is relative to `repo_root`, while `commondir` and `gitdir`
   inside the administrative directory are relative to `admin_dir`. `git
   worktree add --relative-paths` (Git 2.48+) writes all three in relative form —
   observed here as `gitdir: ../primary/.git/worktrees/wt-rel` with an inner
   `gitdir` of `../../../../wt-rel/.git` — so a resolver that assumed absolute
   paths would reject exactly the layout that is most portable. Resolve both
   sides of every comparison; on macOS `/tmp` and `/var` are symlinks, and an
   unresolved comparison fails on paths that are in fact identical.

   The second is what a copied-rather-than-`git worktree move`d directory fails:
   its `gitdir` still names the original checkout, and a resolver that trusted it
   would answer for a repository the caller is not standing in.
2. **Prove the candidate root is the working tree that owns this common dir.**
   Having derived `root = common_dir.parent`, require `root/.git` to resolve
   back to `common_dir` — the directory itself, or a gitfile naming it — and
   require `root/DIR_WORKFLOW` to be a directory. A layout where the common dir
   lives outside its working tree fails the first check and falls back to
   today's behavior rather than guessing.

```python
def _main_worktree_root(repo_root: Path) -> Path | None:
    marker = repo_root / ".git"
    if not marker.is_file():
        return None                      # ordinary primary checkout
    ...read "gitdir:", resolve relative to repo_root -> admin_dir...
    ...require admin_dir/commondir, admin_dir/gitdir, admin_dir.parent.name == "worktrees"...
    ...require admin_dir/gitdir to resolve to repo_root/.git...
    ...read admin_dir/commondir, resolve relative to admin_dir -> common_dir...
    ...require admin_dir.parent.parent == common_dir...
    root = common_dir.parent
    if not _git_dir_of(root) == common_dir:      # guard 2
        return None
    return root if (root / DIR_WORKFLOW).is_dir() else None
```

Every failure returns `None` rather than raising: this runs inside a resolver
that many commands call, and an unparseable or unusual `.git` must degrade to
today's behavior, not to a traceback. A `--separate-git-dir` main checkout is
therefore not *supported* by this withdrawn design — it is *excluded* from it,
which was the correct outcome for a layout whose main working tree the plumbing
does not name. That exclusion died with the design: upstream asks Git, and Git
knows. `prd.md` records the live position — the mechanism is upstream's to
choose, and this layout needs no carve-out.

An ordinary primary checkout still pays only one `is_file()` on a path the
caller is already standing in.

Verified against Git 2.50.1 with a throwaway repository, running these exact
guards over four layouts: a plain `git worktree add`, one relocated with `git
worktree move`, one created with `--relative-paths`, and the primary checkout
itself. The three worktrees each resolved to the primary root; the primary
returned `None`, as did a worktree directory copied with `cp -R` instead of
moved with Git, whose inner `gitdir` still names its original location.

## Blast radius

Nothing upstream is this task's to change: requirement 1 is already implemented
on `chore/task-backlog-2026-08`, and the reporting patch belongs to `08-17-trellis-identity-message-consistency`.

Local: the staged tests, one entry plus paste-ready material in the
`08-08-upstream-handoff-register` task, and nothing under `.trellis/scripts/**`.
`.trellis/.gitignore` is untouched — the identity stays uncommitted (requirement
2), and the fallback reads the main checkout's copy through the filesystem, never
through Git object storage.

## Risks

- **The parked task reads as unfinished work.** It is: the repository cannot
  demonstrate the fix until a release and a refresh. The mitigation is that the handoff and
  the staged tests are both committed, so the refresh that lands the resolver
  turns the tests green with no further planning.
- **Upstream may implement it differently.** The staged tests assert behavior
  (a worktree resolves the primary identity, local precedence, an unusable local
  file falling back — but not the *warning*, which left with the reporting half),
  never
  the helper's name, and their skip probe is itself behavioral: it builds a
  throwaway primary-plus-worktree fixture and asks whether the resolver already
  finds the primary identity. An upstream fix written directly into
  `get_developer` therefore turns the suite live exactly like one adding
  `resolve_developer`. The probe fails to *skip*, never to a false green.
- **The split parks one task and leaves the other selectable.** This one parks:
  nothing remains here but waiting. `08-17-trellis-identity-message-consistency`
  stays open, because its patch, staged tests, and register update are all
  writable today and only its *uptake* waits on the same release. The register
  entry names both so neither is lost.
- **The uptake is a release away, and not this repository's to schedule.** The
  fix sits on an unmerged fork branch with no tag. Merging it, cutting a release,
  and refreshing the vendored tree are three separate operator actions, and the
  task stays parked across all of them.
- **`commondir` is plumbing** — applies to the withdrawn design only, kept with
  it for the record: It is stable, documented in `gitrepository-layout`,
  and already what Git itself reads; the guarded parse degrades to today's
  behavior if it ever changes.
