# Implement — gito adapter drops the head ref

Source of truth is `templates/scripts/sd-ai-command-pack-review-local.py`. The
other three copies (`scripts/`, `plugins/sd/bin/`,
`plugins/sd/machine-payload/scripts/`) are generated; all four are byte-identical
today (`sha256` prefix `969c17addc6f`). Never hand-edit a generated copy.

## Order

1. **Red first — pin the defect from the test side.**
   In `tests/test_review_stage.py`, assert the constructed gito argv for all
   three scopes:
   - `branch_delta`: `--what <head>` before `--vs <base>`, pinning both **values**
     and their order, so a fix that swaps them into `head..base` fails rather
     than passing on argv length (PRD acceptance criterion 2).
   - `worktree`: carries `--vs <base>` and **no** `--what`.
   - `codebase`: `--all --path <repo>`, unchanged (PRD acceptance criterion 3).
   Run them; the `branch_delta` one must fail now. A test that passes before the
   change proves nothing.
   - Validation: `python3 -m pytest tests/test_review_stage.py -k argv` — expect
     failures naming the missing `--what`.

2. **Update the assertion that pins the old shape.**
   `tests/test_review_stage.py:597` asserts `"gito review --vs"`. Change it to
   the `branch_delta` shape. Leave the neighbouring `--filter` assertion alone.

3. **Add the head-binding refusal tests.** Two of them, because the refusal is
   provider-scoped:
   - A `branch`/`pr` run selecting **gito**, against a clean tree whose `HEAD`
     is not the requested head, must raise `ReviewInputError`. Assert on the
     message naming both oids, not on the exception type alone — the dirty-tree
     path raises the same type and a type-only assertion cannot tell the two
     refusals apart.
   - The same run selecting **prism only** must still succeed. This is the
     regression guard for the capability prism was shown to have; without it a
     later "simplification" into `resolve_target` passes its own tests.
   - Validation: run both; the first must fail now (today that resolve
     succeeds), the second must pass now and keep passing.

4. **Implement the refusal** as a declared provider property, not a check on
   `adapter == "gito"` at the call site: the built-in gito provider declares
   that it requires the tree to hold the planned head, and the stage refuses
   before dispatching any provider carrying that declaration for
   `branch_delta`. An `argv` provider wrapping gito must be able to opt in —
   `prism-chunked` is exactly that shape.
   Order the checks so a dirty tree still reports dirtiness rather than a
   confusing head mismatch.

5. **Implement the argv split** in `_expand_argv`'s gito branch: three cases —
   `codebase` unchanged; `branch_delta` gains `--what <head>`; `worktree` keeps
   `--vs <base>` with no `--what`. Do not key the new case off "not codebase".

6. **Regenerate the mirrors.** `make generate && make sync`.
   - Validation: all four copies hash-identical again:
     `for f in scripts templates/scripts plugins/sd/bin plugins/sd/machine-payload/scripts; do shasum -a 256 $f/sd-ai-command-pack-review-local.py; done | awk '{print $1}' | sort -u | wc -l` — expect `1`.

7. **Full gate.** `make check`.

## External evidence (PRD acceptance criterion 4)

Cannot be asserted from inside the pack. After the change is installed on the
machine, replay `sd-github-review` PR #70 **with gito selected as the provider**
from a tree that is **not** the head, and confirm the stage now refuses by name
rather than returning findings. Then replay from a worktree at the head and
confirm findings are confined to the range. The refusal is provider-scoped, so
the same replay under `prism` is expected *not* to refuse — that is the
regression guard, not a failure of this step. The refusal is the new expected result for the first half — the PRD's
criterion 4 was written before the experiment and says "returns findings
confined to the range"; that wording only holds for the second half, and the
PRD's acceptance criteria have been amended to say so.

## Rollback

Single revert; no persisted state, no receipt schema change.

## Not in this task

Auto-provisioning a worktree at the head, and the general provider-capability
declaration system this task stubs.

Not open any more: whether `prism` reads content from refs. It does — tested,
see `design.md`. That is why the refusal is provider-scoped.
