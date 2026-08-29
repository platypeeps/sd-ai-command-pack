# Surface Retirement Doc Gates

> Two doc gates fire when a command surface or shipped script is deleted, and
> both fail in ways that look unrelated to the deletion. Read this before
> retiring a surface.

## Scenario: retiring a shipped surface

### 1. Scope / Trigger

Trigger this spec when a change deletes any of:

- a shipped script listed in `manifest.json` with `"kind": "script"`,
- a command surface (skill + generated adapters + `.github/command-sources/`
  body), or
- any file a Trellis `prd.md` or `research/*.md` cites by path.

Both gates below are repo-wide: they scan files the deletion never touched.

### 2. Signatures

```bash
PYTHON_BIN=".venv/bin/python" bash .github/scripts/check-shipped-script-docs.sh
node templates/scripts/sd-ai-command-pack-review-preflight.mjs
```

`make check` runs both. The first is its own step; the second runs inside
`templates/scripts/sd-ai-command-pack-full-check.sh`.

### 3. Contracts

**Public/internal classification** (`check-shipped-script-docs.sh`). Every
manifest `script` target is either public or internal, and the two markers must
agree:

| Marker | Location | Shape |
|---|---|---|
| public | `docs/SD_AI_COMMAND_PACK.md` | a list bullet matching `^- \`<target>\`:` |
| internal | `INTERNAL_ALLOWLIST` in the gate script | the target's **basename** |

The entry-bullet regex anchors on `- ` at line start and requires a colon
directly after the closing backtick. Any other mention — prose, a
troubleshooting bullet like ``- `scripts/x` is missing: reinstall`` — does not
count.

**Documentation path references** (`review-preflight.mjs`,
`checkDocumentationPathReferences`). Every backticked code span and Markdown
link whose target starts with a configured reference prefix must resolve to an
existing path. Exempt: `docs/SD_AI_COMMAND_PACK.md`, `docs/repomix-map.md`,
`.trellis/tasks/archive/**`, and `design.md`/`implement.md` under
`.trellis/tasks/` (forward-looking by definition). **Not exempt:** `prd.md` and
`research/*.md` under `.trellis/tasks/`.

A span without a directory prefix is not a path reference, so a bare filename
is the supported way to cite a file that no longer exists.

### 4. Validation & Error Matrix

| Condition | Error |
|---|---|
| manifest script has neither an entry bullet nor an allowlist entry | `shipped scripts with neither a guide entry bullet ... nor an internal allowlist entry` |
| manifest script has **both** | `internal-allowlisted scripts with an explicit guide entry bullet ... (drop the allowlist entry or the bullet)` |
| allowlist basename matches no manifest script | `internal allowlist names scripts missing from the manifest` |
| prefixed path span in a guarded doc resolves to nothing | `<file>:<line> references missing path <target>.` |

### 5. Good/Base/Bad Cases

- **Good:** a deleted script's `prd.md` citation becomes
  `` `review-local.sh` (then under `scripts/`, since deleted) `` — the fact
  survives, the span is not a path reference.
- **Base:** deleting a public script removes its entry bullet; nothing else
  changes.
- **Bad:** deleting the entry bullet for script A when script B's only mention
  lived *inside* A's bullet as prose. B's mention is reflowed into a bullet of
  its own, B is now classified public, and the gate reports a contradiction for
  a file the change never edited.

### 6. Tests Required

The gates are the tests; run both against the full tree, not the diff:

- `PYTHON_BIN=".venv/bin/python" bash .github/scripts/check-shipped-script-docs.sh`
  — assert `Shipped-script doc coverage OK: N targets, M allowlisted internal.`
- `node templates/scripts/sd-ai-command-pack-review-preflight.mjs` — assert
  `0 failure(s)`; warnings are advisory.

Do not scope either to changed files. Both failures land in files the deletion
did not touch, which is exactly what a diff-scoped check cannot see.

**Deleting a test module needs a third check.** `tests/test_install.py` is a
compatibility facade that imports every other test module; the sharded runner
in `.github/scripts/run-tests.sh` skips it by name (its `load_tests` returns an
empty suite, so `unittest tests.test_install` would exit 5). A dangling import
there is therefore invisible to `make test` and only surfaces in the CI shell-
coverage job, which uses plain discovery. After deleting any `tests/test_*.py`,
run discovery the way CI does:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Assert exit 0 — a `ModuleNotFoundError` here is reported as one errored test,
so the run count barely moves and the summary line is easy to misread.

### 7. Wrong vs Correct

#### Wrong

```markdown
- `<scripts-dir>/a.sh`: does a thing. Distinct from the similarly named
  `<scripts-dir>/b.py`, which is the internal stage.
```

(The example writes `<scripts-dir>/` rather than a real prefix on purpose: a
span carrying a real directory prefix and a name nothing resolves to would
itself fail the path-reference gate this spec documents.)

Deleting the `a.sh` bullet leaves the `b.py` sentence as a new top-level
bullet, silently promoting an allowlisted internal script to public.

#### Correct

Keep the internal script's description out of another script's bullet. When the
host bullet is deleted, delete the collision note with it — the collision it
described no longer exists — and leave the allowlist entry as the single
classification marker.
