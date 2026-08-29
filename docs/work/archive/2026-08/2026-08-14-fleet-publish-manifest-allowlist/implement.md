# Implement — derive the fleet-publish allowlist from manifest.json

Single file plus its test module. No `make sync`, no manifest bump: the
`fleet-*` scripts are repo-owned (`scripts/` has no `templates/` twin for
them).

## 1. Narrow the constant to residue

`scripts/sd-ai-command-pack-fleet-publish.py:76-92`. Keep `.trellis/`,
`.sd-ai-command-pack/`, `docs/repomix-map.md`, `.gitignore`. Drop the ten
platform directories and `.codex/` (D4). Give each survivor a one-line
ownership comment naming who writes it — Trellis, the installer's receipts,
the map generator, housekeeping. Rewrite the block comment above the tuple:
it currently claims the tuple covers "the pack-managed platform surfaces the
installer just rewrote", which stops being true here.

## 2. Add the resolver

New module-level constant `PACK_MANIFEST_RELATIVE = ".sd-ai-command-pack/manifest.json"`
and:

```python
def derive_allowed_paths(repo: Path) -> tuple[tuple[str, ...], frozenset[str]]:
    """Return (prefixes, exact) for the consumer's installed payload."""
```

Two sets, per D3a: dotted roots and the residue are prefix-matched, non-dotted
targets are exact-matched. `is_allowed` grows an `exact` parameter and
`check_preconditions` threads it through; that is the only signature change.

Order of operations, each failure raising `PublishError(..., code=3)` with
its reason code in the message (D5):

1. `manifest_missing` — path does not exist or is not a file.
2. `manifest_unreadable` — `OSError`, or `json.JSONDecodeError`.
   Report the exception's message, not a bare code.
3. `manifest_malformed` — payload is not a mapping, or `files` is not a list.
4. Walk `files`. Skip a non-mapping entry, a missing/non-string/empty
   `target`, an absolute target, and any target with a `..` segment; count
   the skips.
5. Route each surviving target (D3/D3a): first segment starts with `.` → add
   that segment plus `/` to the prefix set; otherwise add the exact target to
   the exact set.
6. `manifest_targets_empty` if both sets came out empty of derived entries.
   Include the skip count in the message so a pathological manifest is
   distinguishable from an empty one.
7. Return `(tuple(sorted(set(DEFAULT_ALLOWED_PREFIXES) | derived_prefixes)),
   frozenset(derived_exact))`.

Sorted for a deterministic refusal message; the gate itself is order
independent.

## 3. Wire it into publish()

`:422`. Replace

```python
prefixes = tuple(DEFAULT_ALLOWED_PREFIXES) + tuple(args.allow_path_prefix or ())
```

with a `derive_allowed_paths(repo)` call whose prefix half is extended by
`args.allow_path_prefix`; the exact half passes through untouched. The
resolver must run before `check_preconditions` so a missing manifest refuses
with its own reason rather than as a dirty-tree failure. `repo` is already
bound at `:421`.

## 4. Improve the dirty-tree refusal message

`:209-215`. Append the derived-set provenance: the manifest path and how many
prefixes were derived. An operator seeing "unrecognized path" needs to know
whether the gate consulted 4 residue entries or 4 residue plus 21 derived
ones. Keep the existing "commit or stash unrelated work, or extend
--allow-path-prefix" tail; it is the documented override.

## 5. Tests — `tests/test_fleet_publish.py`

Fixture helper: write a `.sd-ai-command-pack/manifest.json` into the temp
consumer repo with a caller-supplied `files` list, so each test states the
payload shape it depends on instead of inheriting this repo's 725 entries.

Update the six existing call sites that pass `publish.DEFAULT_ALLOWED_PREFIXES`
(`:69,92,120,130,406,409`) to resolve through `derive_allowed_paths`
against a fixture manifest. `:406` asserts `.gitignore` is in the constant —
that assertion stays valid and should stay, since `.gitignore` is residue.

New cases, one per acceptance criterion plus the edges the design names:

1. **The criterion that motivated the task.** A manifest declaring
   `scripts/sd-ai-command-pack-check.py` makes that dirty path pass with no
   code edit. Assert on behavior, not on the returned tuple.
2. A dirty path in neither the derived set nor the residue still refuses with
   `code=3` and the existing message shape.
3. Missing manifest → refusal naming `manifest_missing`.
4. Unreadable/invalid JSON → `manifest_unreadable`.
5. `files` not a list → `manifest_malformed`.
6. All entries skipped (absolute target, `..` target, non-mapping row) →
   `manifest_targets_empty`, and the message reports the skip count.
7. Dotted-root collapse: a manifest target `.claude/skills/x/SKILL.md` allows
   a *sibling* dirty path `.claude/skills/x/other.md` that the manifest never
   names (D3's byproduct case).
8. Non-dotted exactness: a manifest target `scripts/a.py` does **not** allow
   dirty `scripts/b.py`. This is the pair that proves D3 is implemented as
   designed rather than collapsing everything to directories.
8a. **The D3a hole, asserted directly.** A manifest target `scripts/a.py`
   does not allow dirty `scripts/a.py.orig`. Case 8 passes under the naive
   prefix implementation and this one does not; without it the defect ships.
8b. `--allow-path-prefix docs/rep` still allows `docs/repomix-map.md`,
   proving the override kept prefix semantics while derived targets became
   exact.
9. Residue survives derivation: with a minimal manifest, `.trellis/…` and
   `.gitignore` still pass.
10. `--allow-path-prefix` still extends the resolved set.

## 6. Validation

```bash
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  -m unittest tests.test_fleet_publish -v
.venv/bin/python -m ruff check scripts/sd-ai-command-pack-fleet-publish.py tests/test_fleet_publish.py
.venv/bin/python -m mypy installer install.py scripts
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  scripts/sd-ai-command-pack-check.py --json
```

mypy is not optional: the CI `lint` lane runs it over `scripts/`, and local
ruff alone has passed while that lane failed before.

Blast-radius check before claiming done — enumerate rather than grep for what
was just typed:

```bash
grep -rn "DEFAULT_ALLOWED_PREFIXES" . --include=*.py --include=*.md \
  --include=*.sh --include=*.mjs | grep -v "^./.git/"
```

Every hit must be the script, its tests, or this task's artifacts. A hit in
`docs/`, a spec, or another fleet script means the constant's meaning is
documented somewhere that now describes the old behavior.

## 7. Rollback

Revert the single commit. No consumer state, no payload version, no
generated mirrors.
