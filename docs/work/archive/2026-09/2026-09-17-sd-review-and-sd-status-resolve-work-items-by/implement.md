# Implement — sd-review-and-sd-status-resolve-work-items-by

## Step checklist

- [x] **1. `registered_base` and `Rows`.** Add `registered_base(root,
      sd_db, connection)` to `bin/sd_lib.py` as `design.md` sketches it;
      in `Rows.__init__`, after `connect` succeeds, set `self.base` from
      it. Tests in `tests/test_status_source.py`, class `TheRowDecides`:
      a bare remote under the fixture `tmp`, the original with `origin`
      pointing at it, a `git clone` beside it; `Rows(clone).external_id`
      equals `identity()`; `work_items(clone)` reports the seeded status;
      `picked()` evaluated over the clone names `ITEM`. Negative cases:
      a clone whose `origin` is a second bare remote nobody registered
      keys by its own path and says "holds no docs/work row"; a checkout
      with no `origin` does the same. The linked-worktree test is
      untouched and stays green. Green on its own: `python -m unittest
      tests.test_status_source` passes.
- [x] **2. `sd-status` from a clone.** In the same test module, render
      `work_section(clone)` and assert no `status-unreadable` row names
      `ITEM`; assert one does for the foreign-origin clone. Green on its
      own: the module passes with the two new assertions.
- [x] **3. `sd_handoff_rows.item_for`.** Replace the `main_worktree_root`
      call with `registered_base`. Test in `tests/test_sd_handoff_rows.py`:
      `item_for` from a clone of the registered remote returns the row
      the original registered. Green on its own: `python -m unittest
      tests.test_sd_handoff_rows` passes.
- [ ] **4. Measure and record.** From
      `/Volumes/sd-work/worktrees/981/10-1-44394d0e746a4d369ec0bd7bb24d25be`
      (or any clone of the pack's remote at another path), run `sd-status`
      and `sd-review --scope planning --explain` with the branch checked
      out; record the `status-unreadable` count and the explain line in
      `prd.md`'s Log with the commit. Expected: 7, and an explanation
      naming this item. Then `sd task status <work row> ready` if the
      registry lane runs clean, which is the promotion this plan withheld.
- [x] **5. Gate.** `make check` rc 0; `bin/sd-docs-lint` clean; `git diff
      --stat main -- bin/sd-review` empty. Ship as one slice; the diff is
      well under the review's large-change line.

## Verification

Named before the work: the check that catches this being wrong is the
clone test of step 1 run against *unchanged* `bin/sd_lib.py`, which must
fail with the item reported `unknown` and the clone's path in the key.
A new test that passes before the change tests nothing; run it red first.

Then, per step, the module named on the step; and once, at the end, the
live measurement of step 4, which is the only check that runs the real
database against a real clone at a different path. The unit tests build
their own registered repository under a private `$HOME`; they cannot
prove the operator's `repo` table carries the remote the dashboard clones
with, and step 4 is what proves that. If step 4's count is not 7, the
difference is a folder registered or archived since `22183d3c`, and the
registered checkout's own count on the same commit is the comparison,
not the number written here.

Not verifiable here: that every runner assignment clones with the
registered remote URL. The dashboard's note 2699 on sd:981 shows it did
for this one; a runner configured to clone over https from an
ssh-registered repository would resolve to itself, and `same_remote`'s
strictness is the library's decision. That case is named in `design.md`'s
risks and is not asserted by any test in this item.

## Log

- 2026-09-17 steps 1, 2, 3 and 5 done on `feat/sd-981-registered-base`
  over pack `10164281`: `registered_base` in `bin/sd_lib.py`, `Rows` and
  `item_for` call it; the clone tests ran red first against unchanged
  `bin/sd_lib.py` (the key carried the clone's path, `sd-status` emitted a
  `status-unreadable` row, `item_for` returned None), then `OK`; `make
  check` rc 0, `sd-docs-lint: clean`, `git diff --stat origin/main --
  bin/sd-review` empty. Step 4, the live measurement from the runner
  clone, is the owner's and is NOT VERIFIED here; no row was promoted.
