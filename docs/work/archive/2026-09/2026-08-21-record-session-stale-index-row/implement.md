# Implementation plan

Ordered. Each step names the command that shows it worked.

## 1. Read the call site and the reused function

- `scripts/sd-ai-command-pack-record-session.py:496-517` (the
  `add_session.py --no-commit` invocation), `:559-568` (the `patch_last_session`
  result and the `--no-commit` early return), `:573-598` (staging both files).
- `.trellis/scripts/add_session.py:190-207` (`count_journal_files`) and
  `:1066-1074` (`update_index`'s marker rewrite, as the reference for the block
  boundaries — not as code to call).

Gate: state in your own words why the refresh cannot go next to `git add`.
If that is unclear, stop and re-read `design.md`.

## 2. Add the loader

Private helper that puts `.trellis/scripts` (resolved absolute) at the front of
`sys.path`, loads `ADD_SESSION` by path via `importlib.util`, removes the
`sys.path` entry in a `finally`, and returns `count_journal_files` or `None`.
Catch `ImportError`, `OSError`, `SyntaxError`, and `AttributeError`; on any of
them print one stderr line and return `None`.

Validation:

```
python3 -c "import importlib.util,pathlib,sys; \
sys.path.insert(0,str(pathlib.Path('.trellis/scripts').resolve())); \
s=importlib.util.spec_from_file_location('_a','.trellis/scripts/add_session.py'); \
m=importlib.util.module_from_spec(s); s.loader.exec_module(m); \
print(m.count_journal_files(pathlib.Path('.trellis/workspace/sdelmas'),9))"
```

Expect the live table with `journal-9.md` marked `Active` and no other output.

## 3. Add the block rewriter

Private helper taking the journal path. Derives `active_num` from
`journals[0].stem` with the same `\d+` extraction `update_index` uses (`add_session.py:1027`); reads
`index.md` beside the journal; replaces only the lines strictly between
`<!-- @@@auto:active-documents -->` and `<!-- @@@/auto:active-documents -->`
with header, separator, and the `count_journal_files` output; writes atomically
with the module's existing `atomic_write_text`. Missing file, missing markers,
markers out of order, or any `OSError` prints one stderr line and returns
without raising.

## 4. Wire the call

Insert immediately after the `if error: ... return 1` block that follows
`patch_last_session`, above `if args.no_commit:`. Nothing else in `main` moves.

## 5. Tests

Extend `tests/test_record_session.py`, one test per acceptance criterion:

1. growth case — patch grows the journal; committed `index.md` row equals the
   journal's real line count (assert the exact number, never "it changed");
2. `--no-commit` — row already correct on disk when the wrapper returns;
3. retry path — modified journal already carrying the title, `add_session.py`
   not invoked this run, row still corrected;
4. journal with no trailing newline — counted as `add_session.py` counts it
   (this is why `splitlines()` and not `wc -l`);
5. absent and marker-less `index.md` — exit 0, journal entry intact,
   one stderr line;
6. no byte of `index.md` outside the block differs from what the current code
   produces.

Validation: `python3 -m pytest tests/test_record_session.py -q`.

## 6. Sweep the shipped copies

```
find . -name "sd-ai-command-pack-record-session.py" -not -path "./.git/*"
for f in <the four>; do shasum -a 256 "$f"; done
```

All four digests must match. Enumerate from `find`, not from this list.

## 7. Full gate

`make check`. Includes the shipped-script coverage gate that independently
re-checks step 6.

## Review gates

- After step 4: the diff must not touch `add_session.py`, `update_index`, any
  exit code, or any `_emit_recorded` output.
- After step 5: every assertion compares against a computed real line count.
  A test that only asserts inequality with the old value would pass against a
  wrong-by-one implementation and does not satisfy criterion 1.
- After step 6: the four digests are quoted in the commit or PR body.

## Rollback

Delete the two helpers and the one call. No state migration in either
direction: the row simply returns to being written pre-patch, which is today's
behavior.
