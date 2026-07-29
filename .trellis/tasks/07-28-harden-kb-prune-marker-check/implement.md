# Implementation — harden the KB prune ownership check

## Order

1. **Size the migration before writing code.** The `:256` branch is live: the
   current writer emits a plain file per source under a category folder, so the
   branch's population is the tool's own stale copies *plus* any user file in the
   same folders. Confirm that on disk rather than trusting this sentence:

   ```bash
   python3 scripts/sd-ai-command-pack-update-spec-kb.py --root . && find .obsidian-kb -type f -not -type l | head -20
   ```

   Then count how many of those files a marker check would strand:

   ```bash
   find .obsidian-kb -type f -not -type l -exec grep -L "sd-ai-command-pack-kb" {} + | wc -l
   ```

   **Gate:** record both numbers in `design.md`. They select option A
   (destination-reconstruction reconciliation) or B (leave unmarked files
   forever). If the second count is zero the KB is freshly generated and the
   number is meaningless — regenerate from a pre-change checkout first, or the
   migration is being sized against a population that does not exist.

2. **Write the survival test first.** In `tests/test_update_spec_kb.py`, create a
   KB root containing `Repository Overview/my-notes.md` — plain file, no marker,
   absent from `wanted` and `generated` — run the prune, assert it still exists.
   **Gate:** this must fail against unmodified source. If it passes, the fixture
   is landing in the `continue` at `:745` instead of reaching `:256`; fix the
   fixture before continuing.

3. **Write the marker at the point of copy.** `create_copies` (`:1315`) uses
   `shutil.copy2`, which reproduces the source byte-for-byte and therefore
   carries no provenance. Emit the marker into the copy. The copy is no longer
   byte-identical to its source — that is the intended, changelog-worthy
   difference, and the `filecmp.cmp(source, copy, shallow=False)` skip at `:1341`
   must be updated in the same edit or every run rewrites every copy.
   **Gate:** run the tool twice and diff the second run's output against the
   first. Non-empty means the idempotence skip was not updated.

4. **Gate the `:256` branch on the marker**, keeping the branch. Then apply the
   chosen migration: option A adds "or the path is a current/former
   `kb_destination_for_source` value"; option B adds nothing and accepts that
   pre-marker copies are never pruned. Under no option does a plain file survive
   the predicate on `is_managed_kb_category_path` alone.

5. **Add the convergence test.** Generate a KB, delete a source, regenerate,
   assert the orphaned copy is gone. This is the criterion the earlier
   delete-the-branch draft would have broken, and nothing else in the suite
   covers it.

6. **Leave the other two branches alone.** `:247` (legacy marker) and `:250`
   (symlink ownership) already prove ownership. Touching them widens a data-loss
   change for no benefit.

7. **Confirm the root symlink is untouched.** PRD R4 forbids restricting it.

   ```bash
   python3 -m pytest tests/test_update_spec_kb.py -k symlink -q
   ```

8. **Mirror to the template twin**, `make sync`.

9. **Re-run step 2's test** — must now pass.

## Validation

```bash
python3 -m pytest tests/test_update_spec_kb.py -q
```

```bash
make sync && make check
```

## Review gates

- Before step 3: both migration counts from step 1 are recorded in `design.md`,
  measured against a KB that predates the change — not assumed, and not measured
  against a KB regenerated after it.
- Before step 4: the migration option is chosen and written down. If B, state
  plainly in the changelog that pre-marker copies are never pruned; that is a
  known regression of the stale-document criterion, not an omission.
- Before completion: three tests pass together — the user-file survival test
  (step 2), the convergence test (step 5), and
  `tests/test_update_spec_kb.py:138` (root symlink assertion). Survival alone is
  not enough: a change that stops deleting everything passes it.

## Rollback

Revert the commit. `.obsidian-kb` is gitignored and regenerated per checkout, so
no state migration is owed. Note the asymmetry: this change prevents future
deletion of user files; it does not restore any already lost.
