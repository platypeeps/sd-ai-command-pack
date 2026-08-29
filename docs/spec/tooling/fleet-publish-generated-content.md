# Fleet publish: generated content belongs in the work commit

Scope/trigger: any pack-managed content that a consumer regenerates from a
script — `docs/repomix-map.md`, the `.gitignore` `.obsidian-kb` block, and
anything added later. Established by
`.trellis/tasks/archive/2026-08/08-12-fleet-publish-ignore-block-ordering`
after campaign `refresh-0.71.2-20260813T014138Z-c3`.

Cite the archive path, not the active one. `task.py archive` moves the whole
task directory, so a spec that cites the task establishing it by its
pre-archive path fails the documentation path-reference gate the moment that
task is archived — in the same finalization that publishes the spec.

## The rule

`scripts/sd-ai-command-pack-fleet-publish.py` [absent: removed with the release train in 0.72.0] must regenerate every piece of
pack-managed generated content **before** `work_commit()`, and every such path
must be allowed by the publish gate.

Both halves are required and neither is sufficient alone:

- Regeneration alone fails when the operator already ran housekeeping, because
  the tree is then dirty before publish starts and the allowlist refuses it.
- Allowlisting alone fails on an untouched tree, because the file is still clean
  at publish time and there is nothing to allow.

The allowlist has two sources, and generated content usually needs the first:

- the residue constants — paths the installer does not own, kept in the script
  with an ownership comment per entry. `DEFAULT_ALLOWED_PREFIXES` holds
  directories, `DEFAULT_ALLOWED_EXACT` holds files. `docs/repomix-map.md` and
  `.gitignore` are in the exact one because no payload target names them.
- `derive_allowed_paths()` — read at runtime from the consumer's
  `.sd-ai-command-pack/manifest.json`, so every installed payload target is
  allowed without a code edit.

Generated content is written by a script rather than installed, so it is
normally absent from the manifest and must be added to a residue constant.
Add it there only after confirming no payload target already names it;
duplicating a manifest-derived path in the constant is harmless but hides who
owns the file.

Put a file in `DEFAULT_ALLOWED_EXACT`, never in the prefix tuple. Prefix
entries are matched with `startswith`, so a generated file listed as a prefix
also sanctions any editor backup whose name extends it — a `.bak` or `.orig`
suffix on the same path — which then rides into the publication commit. That is
the leakage this gate exists to stop.

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

Decide that state from the file, not from the exit code. A generator can fail
after it has already written the content publish cares about:
`sd-ai-command-pack-update-spec-kb.py` calls `ensure_gitignore()` before it
copies anything, then exits `3` when only the KB copies conflict and `2` on a
hard `OSError` partway through. Reporting `failed` on an exit `3` would tell an
operator the block is stale when it is refreshed and already inside H1.

## Ordering among generators

Run content generators before the repomix map. A block can newly ignore a path,
and repomix must index the final ignore state or housekeeping's later run
rewrites the map — reintroducing the same dirty-tree failure one step removed.

Tests: `tests/test_fleet_publish.py` [absent: removed with the release train in 0.72.0]. The ordering rule is pinned by
`test_publish_captures_a_stale_ignore_block_in_the_work_commit`, which runs
`publish()` end to end and asserts `.gitignore` is in H1 — a test that only
calls the generator cannot catch the regression. Also
`test_gitignore_is_in_the_default_allowlist` for the allowlist half, and
`test_ignore_block_refresh_reports_refreshed_when_a_failing_helper_still_wrote_it`
for the exit-code-versus-file rule above.
