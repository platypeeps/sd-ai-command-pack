# Design — sd-review-and-sd-status-resolve-work-items-by

## Approach

One resolver in `bin/sd_lib.py`, and the two readers that hold a
connection call it.

```python
def registered_base(root, sd_db, connection) -> str:
    """The registered checkout this one is, spelled as the `repo` table spells it."""
    base = str(main_worktree_root(pathlib.Path(root).resolve()))
    registered_for = getattr(getattr(sd_db, "repos", None), "registered_for", None)
    if registered_for is None:
        return base                       # requirement 5: an older library
    origin = git_output(["remote", "get-url", "origin"], pathlib.Path(root))
    return str(registered_for(connection, base, origin or None))
```

`source:bin/sd_lib.py::Rows` sets `self.base` from `main_worktree_root`
before it opens anything, in `Rows.__init__`, and that stays the value
for the no-database and no-library cases: a machine with nothing to read
keeps the key it has today, and `opened` stays the distinction it is. Once
`connect` succeeds and before `opened` is set, `__init__` reassigns
`self.base = registered_base(root, sd_db, self._connection)`. Everything
downstream (`Rows.external_id`, `Rows.item`, `Rows.activity`,
`Rows.completed`) reads `self.base` and changes nothing.
`Rows.item` already passes a path relative to `_root_of(item_dir)`, which
is the clone's root, so `item_for_artifact(connection, base, relative)`
receives the registered base and a relative path, the pair the row was
written with.

`source:bin/sd_handoff_rows.py::item_for` replaces its
`sd_lib.main_worktree_root(root)` call with the same call; it already holds `connection` and `sd_db`. Its
`item_by_external` fallback, for a library without `item_for_artifact`,
keeps `sd_lib.external_id`, which is path-keyed: a library that old has
no `registered_for` either, and requirement 5 says that machine keeps
today's behaviour.

Why `main_worktree_root` first and `registered_for` second, rather than
`registered_for` alone on the worktree path: a linked worktree of the
registered checkout has the same origin, so `registered_for` would answer
the same either way, but only after failing the path lookup and reading
the remote. Resolving the worktree to its main checkout first keeps the
ordinary case (`sd-status` in the registered checkout or one of its
worktrees) at one indexed lookup with the origin read but unused, and it
keeps `test_a_linked_worktree_reads_the_main_checkout_s_row` an exact
statement of what happens.

**Rejected: register the clone.** `sd_db.upsert_repo(clone_path, remote=...)`
would make the path lookup succeed, and every row would still be keyed by
the original path, so the reader would find its own registration and not
the rows. The `repo` table is a list of the checkouts the operator
registered, not a cache of where the runner has cloned to; a runner that
registers every clone leaves a row per assignment behind.

**Rejected: `sd-review` resolves the item itself.** It is the sensitive,
owner-merged file (`.github/sd-review.json`, `sensitive`), and the pick is
three lines in `source:bin/sd-review::resolve_subject` that call
`source:bin/sd_lib.py::work_items`. A fix
there would leave `sd-status` and `sd-note` with the defect and put the
sensitive file on the diff for a change that belongs one layer down.

**Rejected: key rows by remote instead of by path.** That is a schema
change in the system library, reaches every writer, and `registered_for`
exists precisely so the path stays the key while a clone can still find
it. Out of scope by an order of magnitude.

## Decisions

- **The origin is read once per `Rows`**, not once per item, and only when
  a `row` marker is present (the only case `Rows` is built). Decided by
  this plan, 2026-09-17. Reversed if a reader is found that constructs
  `Rows` per item, in which case the git call moves behind the path
  lookup.
- **A foreign or remote-less checkout resolves to itself**, which is what
  `registered_for` already does; this plan adds no second rule and no
  refusal. Decided 2026-09-17. Reversed if an operator wants a clone of an
  unregistered remote to say so out loud; today `status-unreadable` says
  it, with the clone's own path in the key, and that is enough.
- **`sd task add --here`, `--belongs-to`, and `brief_for` stay path-keyed.**
  Decided 2026-09-17; a follow-up note on sd:981 carries them. Reversed
  when a runner needs to file a task from inside a clone, which no
  assignment does today.
- **No `sd_lib.external_id` change.** Its one caller is the old-library
  fallback. Decided 2026-09-17, reversed only if a caller with a
  connection starts using it, and that caller should call
  `registered_base` instead.

## Risks

- **Two registered checkouts of one remote.** `registered_for` returns the
  first by path order. The writer (`register`) picks the same one, so a
  row registered from a clone and read from a clone agree; but a folder
  registered from the *second* checkout by path is keyed by that path and
  a clone resolves to the first. Accepted: the pack is registered once on
  this machine (`SELECT path, remote FROM repo` returns one row for its
  remote, measured 2026-09-17), the rule is the library's, and the
  failure is the one `status-unreadable` already reports.
- **`same_remote` is strict.** An https clone of an ssh-registered
  repository resolves to itself and stays unreadable. Accepted, and named
  in `prd.md`'s assumptions: the dashboard clones with the registered
  URL, and widening the comparison is the library's call.
- **The `git` call in `Rows.__init__`.** Adds one subprocess to every
  `sd-status` and `sd-review --scope planning` on a row-mode checkout.
  `git_output` returns `None` on failure, `registered_for` treats `None`
  as "no origin", and the path lookup still runs, so a broken git answers
  as today. Accepted for the cost of one process per enumeration.
- **Message text.** `status-unreadable` findings and `Rows.status`'s
  "holds no docs/work row for `<base>::...`" now print the registered
  base for a resolved clone, not the clone's path. Tests that match the
  sentence match against `identity()`, which is the registered spelling,
  so they are unaffected; a reader who copied the clone path out of an
  old finding sees a different one. Accepted; the new sentence is the one
  a `sd work register` from that clone would have written.
