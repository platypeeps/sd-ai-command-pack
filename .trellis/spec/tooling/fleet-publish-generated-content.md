# Fleet publish: generated content belongs in the work commit

Scope/trigger: any pack-managed content that a consumer regenerates from a
script — `docs/repomix-map.md`, the `.gitignore` `.obsidian-kb` block, and
anything added later. Established by
`.trellis/tasks/08-12-fleet-publish-ignore-block-ordering` after campaign
`refresh-0.71.2-20260813T014138Z-c3`.

## The rule

`scripts/sd-ai-command-pack-fleet-publish.py` must regenerate every piece of
pack-managed generated content **before** `work_commit()`, and every such path
must appear in `DEFAULT_ALLOWED_PREFIXES`.

Both halves are required and neither is sufficient alone:

- Regeneration alone fails when the operator already ran housekeeping, because
  the tree is then dirty before publish starts and the allowlist refuses it.
- Allowlisting alone fails on an untouched tree, because the file is still clean
  at publish time and there is nothing to allow.

## Why the ordering is not negotiable

A completion bundle admits exactly one shape: work commit (`h1`) → archive →
journal tail (`h3`). Generated content that lands after `h1` cannot be folded
in later:

- a receipt whose span contains a non-bookkeeping path is rejected with
  `bundle_scope_invalid`, and neither `docs/repomix-map.md` nor `.gitignore` is
  a bookkeeping path;
- a second bundle covering the later commit is rejected with
  `completion_archive_move_missing`, because the archive move happens once.

So the failure is unrecoverable in place. Repair costs a `git reset --hard`, a
rebuilt bundle, an operator-run force push, and a second review and CI cycle —
per consumer. That is why this is an ordering contract and not a lint.

The trap is that the drift only appears at the *merge gate*, when
`sd-ai-command-pack-housekeeping.sh` runs the same generator. A lane looks green
through review and dies at housekeeping with `working tree has uncommitted
changes`.

## Match the housekeeping invocation exactly

Publish and housekeeping must produce identical content, so publish must invoke
each generator with the same argument form housekeeping uses. Two live traps:

- `sd-ai-command-pack-update-spec-kb.py` — housekeeping passes **no**
  `--if-present`, so publish must not either. `--if-present` returns early when
  `.obsidian-kb` is absent and would skip the ignore block housekeeping still
  writes.
- The same helper resolves its own root via `git rev-parse --show-toplevel`, so
  it must run with the **consumer worktree** as cwd. Invoked from the source
  checkout it silently rewrites the wrong repository.

## Failure is advisory, not fatal

A consumer that does not ship a generator, or whose target is read-only, must
still publish. `.obsidian-kb` is regenerable and ignored; its refresh failing is
not a reason to fail a pack refresh. Report the condition and continue — see
`refresh_managed_ignore_block()`, which returns `refreshed` / `absent` /
`failed` into the publish result rather than raising.

## Ordering among generators

Run content generators before the repomix map. A block can newly ignore a path,
and repomix must index the final ignore state or housekeeping's later run
rewrites the map — reintroducing the same dirty-tree failure one step removed.

Tests: `tests/test_fleet_publish.py`,
`test_ignore_block_refresh_writes_before_the_work_commit` and
`test_gitignore_is_in_the_default_allowlist`.
