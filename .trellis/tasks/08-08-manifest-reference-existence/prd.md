# The preflight validates manifest reference *shape* but never whether the referenced file exists

## Goal

Make `checkTrellisTaskContextManifests` reject a `{"file": ...}` row whose path
does not exist, so a task context manifest cannot cite a file that was never
written, was renamed, or was deleted.

The rule already exists and is already enforced — by Trellis's own
`task.py validate`. What is missing is that the pack's merge-gate preflight
reimplements a *subset* of that validator and drops its existence rule, so the
gate passes manifests `task.py validate` rejects — and that the sub-agent context
loader then silently skips.

## Problem

`scripts/sd-ai-command-pack-review-preflight.mjs:3643-3753` collects changed
`implement.jsonl` / `check.jsonl` files and validates each row through
`findTrellisTaskContextIssues` (`:3874-3903`). That function emits exactly three
issue kinds:

- `malformed` — the line is not parseable JSON (`:3886`);
- `seed` — the row still carries the generated `_example` key (`:3891`); and
- `reference` — `isTrellisTaskContextReference(record.file)` returned false
  (`:3899`).

There is no fourth kind for a missing path, and `isTrellisTaskContextReference`
(`:3851`) cannot supply one — it is pure string work:

```js
return (
  pathWithoutTrailingSlash === '.trellis/spec' ||
  pathWithoutTrailingSlash.startsWith('.trellis/spec/') ||
  /^\.trellis\/tasks\/(?:archive\/\d{4}-\d{2}\/)?[^/]+\/research(?:\/.+)?$/.test(pathWithoutTrailingSlash)
);
```

It answers "is this path shaped like a spec or research reference," which is a
different question from "is this a file."

This is not a missing capability. The existence primitives are already in scope
in the same function: `pathEntryExists(normalized)` guards the layout failure at
`:3665`, and `isRegularFile(file)` guards the read loop at `:3703`. Both are
applied to the manifest file itself. Neither is applied to the paths the
manifest names. The sibling check immediately below,
`checkCompletedTrellisTaskLocation` (`:3755`), calls `existsSync` at `:3758` —
so the preflight does probe the filesystem, just not here.

Meanwhile `.trellis/scripts/common/task_context.py::_validate_jsonl`
(`:115-165`) — reached by `task.py validate` — does exactly the missing check,
and distinguishes entry types while doing it:

```python
full_path = repo_root / file_path
if entry_type == "directory":
    if not full_path.is_dir():
        ... f"{file_name}:{line_num}: Directory not found: {file_path}"
else:
    if not full_path.is_file():
        ... f"{file_name}:{line_num}: File not found: {file_path}"
```

Trellis enforces the same rule at *write* time too. `cmd_add_context`
(`task_context.py:52-59`) refuses a path that is neither a directory nor a file,
and derives `entry_type` from the filesystem rather than trusting a declared
value:

```python
entry_type = "file"
if full_path.is_dir():
    entry_type = "directory"
    ...
elif not full_path.is_file():
    print(colored(f"Error: Path not found: {path}", Colors.RED))
    return 1
```

So Trellis checks existence when a row is written and again when it is
validated. The pack's preflight checks it at neither point, and the preflight is
the one wired into the merge gate — `task.py validate` and `task.py add-context`
are operator commands nobody is required to run, and a manifest hand-edited in a
text editor bypasses both.

The consequence is not cosmetic. These manifests are what load context into
sub-agent dispatch, and the loader swallows a missing path without a word.
`.claude/hooks/inject-subagent-context.py::read_file_content` (`:134-143`)
returns `None` when the path is absent (`:143`), and the caller at `:239-242` drops it:

```python
content = read_file_content(base_path, file_path)
if content:
    results.append((file_path, content))
```

No branch handles the `None`. A row naming a path that does not exist yields a
sub-agent that silently starts with less context than the task author believed
it had — the failure mode is degraded output, not an error, which is why nobody
notices. (The seeding contract that creates these files is
`task_store.py:346-356`, writing each seed at `:355`.)

`isTrellisTaskContextReference` is also exported (`:3851`). Its contract does
not change here — existence belongs to the caller — so its existing tests should
still pass untouched, and needing to edit them is a signal the change went into
the wrong layer.

## Reproduction

On a branch, write two rows whose paths have correct shape and have never
existed:

```jsonl
{"file": ".trellis/spec/backend/this-file-has-never-existed.md", "reason": "nonexistent path, correct shape"}
{"file": ".trellis/tasks/08-08-manifest-reference-existence/research/also-never-existed.md", "reason": "nonexistent research path, correct shape"}
```

`node scripts/sd-ai-command-pack-review-preflight.mjs` reports:

```
PASS checked 4 changed Trellis task context file(s) for valid JSONL, generated _example scaffold rows, and spec/research-only references.
```

The manifest check passes. In the same run, the documentation-reference check
fails on missing paths cited in prose — whether those particular failures are
right is a separate question, and they are not. What matters here is that the
check reaches the filesystem at all. That is what makes this gap specific rather
than general: the pack does probe existence for references, and does not do it
for the one artifact whose entire purpose is naming files to load.

## Requirements

1. A `{"file": ...}` row in a changed `implement.jsonl` / `check.jsonl` whose
   path does not exist in the working tree fails the preflight, with a
   `file:line`-anchored message naming the missing path.
2. Honour the `type` field `_validate_jsonl` honours: `"directory"`
   requires a directory, anything else requires a regular file. Do not silently
   accept a directory where a file was declared or the reverse. `cmd_add_context`
   derives that field from the filesystem, so a mismatch means the row was
   hand-written or the path changed kind — both worth reporting.
3. Rows that are already exempt stay exempt — a pristine lone `_example`
   scaffold (`isPristineTrellisTaskContextScaffold`, applied at `:3709`) is
   advisory and must not start failing on account of this change.
4. Shape and existence are separate failures with separate messages. A path that
   is both wrongly-shaped and missing should report the shape violation, which
   is the actionable one.
5. `isTrellisTaskContextReference` keeps its current pure-shape contract and
   signature. Existence belongs to the caller, not inside an exported string
   predicate.
6. A manifest row pointing at a file the same change deletes fails. The message
   need not distinguish "deleted" from "never existed" — one missing-path message
   is enough — but the deletion case must not slip through on the grounds that
   the path existed at the base commit.
7. The change lands in `templates/scripts/sd-ai-command-pack-review-preflight.mjs`
   first and the root mirror is synchronized from it. `templates/**` is the
   source of truth for shipped payloads and the root copy is a byte-verified
   mirror (`AGENTS.md:29-33`); editing only the root copy leaves the shipped pack
   wrong and fails mirror verification.

## Acceptance criteria

- The reproduction above fails the preflight, naming both missing paths with
  their line numbers.
- A manifest citing only existing spec/research paths still passes, and the
  existing `PASS checked N changed Trellis task context file(s)` summary still
  reports the same counts for unchanged inputs.
- A one-time audit reports zero missing-path errors across existing tasks, so
  landing this check cannot retroactively fail a task's manifest the next time it
  is touched:

  ```bash
  find .trellis/tasks -name 'check.jsonl' -o -name 'implement.jsonl' \
    | xargs -n1 dirname | sort -u | while read -r d; do
        bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
          .trellis/scripts/task.py validate "$d"
      done
  ```

  Enumerate from the manifests themselves, not from `.trellis/tasks/*/`:
  `task.py validate` takes one task directory positionally (`task.py:416-417`)
  and checks only that directory's two JSONL files without recursing
  (`task_context.py:100-103`), so a glob over `.trellis/tasks/*/` hands it the
  `archive/` container and silently skips every archived task inside it. The
  audit is a pre-landing sweep, not a new preflight behaviour; the check itself
  stays diff-scoped.
- Existing tests covering `isTrellisTaskContextReference` pass unmodified; new
  tests cover missing file, missing directory, type mismatch, deleted path, the
  untouched-scaffold exemption, and — for requirement 4 — a row that is both
  wrongly-shaped and missing, asserting the shape message wins.
- `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest discover -s tests -p 'test_review_preflight*.py'` passes.
- `make check` passes, including the template/root mirror byte-verification.
  A green unit-test run with a drifted mirror is not acceptance.

## Out of scope

- Making the *shipped check* validate tasks the current change does not touch.
  It is diff-scoped by construction (`currentChangedPaths()` at `:3645`) and
  stays that way. The repository-wide audit in the acceptance criteria is a
  one-time pre-landing sweep run by hand, not behaviour this task adds.
- Changing which roots are allowed. The spec/research-only rule is correct and
  unchanged.
- Reconciling the documentation-reference check's own false positives on prose
  that deliberately names absent paths. Separate defect, separate task.
