# Design: refresh the active-documents row after the journal is patched

## Boundary

One new private helper in `scripts/sd-ai-command-pack-record-session.py` and one
call site. Nothing else in the wrapper changes, and `.trellis/scripts/add_session.py`
is not touched.

## Where the call goes

`main` currently reads:

```python
error = patch_last_session(journals[0], args.title, hashes, tests, next_steps)
if error:
    print(f"error: {error}", file=sys.stderr)
    return 1

if args.no_commit:                      # <-- refresh must be above this line
    _emit_recorded(journals[0], committed=False, as_json=args.json)
    return 0
```

The refresh goes immediately after the `if error: return 1` block. That single
position satisfies three requirements at once:

- it is after the only mutation that grows the journal, so the count is final;
- it is above the `--no-commit` early return, so that path gets the corrected
  row too;
- it is on the retry path as well, because the retry path joins the normal path
  at `patch_last_session` and differs only in how `journals` was resolved.

Putting it lower — beside the `git add` — would miss both `--no-commit` and any
future early return, which is exactly the class of bug being fixed.

## How the row is computed

Reuse, do not reimplement. `add_session.py` already exposes
`count_journal_files(dev_dir, active_num) -> str`, which returns the complete
set of table rows, re-reading every journal from disk with
`len(f.read_text(encoding="utf-8").splitlines())`. That is the measure the
committed row must agree with, so importing the function is what keeps the two
from drifting.

Loading it is not a one-liner, and the obvious shape fails. Two facts were
checked rather than assumed:

- `.trellis/scripts/__init__.py` **exists**, so that directory is a package.
- `add_session.py:57` does `from common.paths import (...)` — a sibling
  absolute import that resolves only when `.trellis/scripts` is itself on
  `sys.path`.

So a bare `spec_from_file_location(...)` + `exec_module` raises
`ModuleNotFoundError: No module named 'common'`. The load must insert
`.trellis/scripts` (resolved absolute) at the front of `sys.path`, load the
module by path against the existing `ADD_SESSION` constant, and remove the
entry again in a `finally`, so the wrapper does not leave the vendored script
directory on the import path for anything that runs after it.

Verified against the real checkout: with that insertion the module imports
cleanly, emits nothing on stdout or stderr (its entrypoint is guarded by
`if __name__ == "__main__"` at `:1605`), exposes `count_journal_files`, and
returns the correct rows for the live workspace.

Guard the whole load: on `ImportError`, `OSError`, `SyntaxError`, or a missing
attribute, report and skip rather than fall back to a hand-rolled count. A
second implementation of the measure is the failure mode this design exists to
avoid.

## How the block is rewritten

`index.md` delimits the table with `<!-- @@@auto:active-documents -->` and
`<!-- @@@/auto:active-documents -->`. Replace only the lines strictly between
those markers — header row, separator, and body. Preserve the marker lines
themselves and every byte outside them, which is what keeps session number,
title, commit display, and date untouched.

The header and separator live *inside* the markers, emitted by
`update_index` at `add_session.py:1069-1070`. Reproduce them as the exact
literals it writes, not as re-derived padding, or the block churns on every
run and acceptance criterion 6 fails:

```
| File | Lines | Status |
|------|-------|--------|
```

followed by `count_journal_files(dev_dir, active_num)`.

`update_index` is deliberately **not** reused even though it also rewrites this
block: it rewrites the session metadata as well, and calling it here would
record the session a second time.

## Failure posture

The journal entry is the deliverable; the index row is bookkeeping derived from
it. Every failure in this path is therefore reported to stderr and skipped, not
fatal:

- `index.md` absent — skip. `git add` already tolerates this via the
  `if path.exists()` filter on the stage list.
- markers absent or out of order — skip with a message naming the file.
- `index.md` unreadable or unwritable — skip with the OSError text.
- `add_session.py` not importable — skip.

Exit status and the `_emit_recorded` output are unchanged in all of these cases.
The wrapper must not start failing runs that succeed today over a derived row.

## Active journal number

`count_journal_files` needs `active_num` to mark exactly one row `Active`.
Derive it from `journals[0].stem` with the same `\d+` extraction `update_index`
uses (`add_session.py:1027`), so the two agree on which file is active. `journals[0]` is
already resolved to exactly one path by the checks above the call site.

## Compatibility and rollout

Behavior-visible only in `index.md` content. No CLI surface, exit code, JSON
field, or commit message changes, so no consumer coordination is required. The
change ships to consumers through an ordinary release and fleet refresh.

Rollback is deleting the helper and its call — the wrapper returns to writing a
stale row, which is the current state, so there is no migration either way.

## Sweep

Four shipped copies, enumerated from the filesystem rather than memory:

```
find . -name "sd-ai-command-pack-record-session.py" -not -path "./.git/*"
```

`plugins/sd/bin/`, `plugins/sd/machine-payload/scripts/`, `scripts/`,
`templates/scripts/`. All four must end byte-identical; `make check` includes
the shipped-script coverage gate that enforces it.
