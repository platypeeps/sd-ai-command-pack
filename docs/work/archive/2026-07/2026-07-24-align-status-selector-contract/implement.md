# Implementation — align status and housekeeping selector contracts

**One commit.** Two token edits, one added sentence, one drift test, then sync
and release bookkeeping. The test and the edit ship together — a test committed
first fails on its own tree.

No change to `scripts/sd-ai-command-pack-status.py`. See step 1.

## Order

1. **Verify AC1 before writing anything — it is already satisfied.** The code
   half of this finding landed with `07-23-status-untracked-roadmap-items`:

   ```
   scripts/sd-ai-command-pack-status.py:559    select_items(..., prefix="T")
   scripts/sd-ai-command-pack-status.py:1715   select_items(..., prefix="F")
   scripts/sd-ai-command-pack-status.py:2295   select_items(..., prefix="F")
   ```

   `select_items` (`:478-481`) is the only producer of `selectionId`, and there
   is no third call.

   **Gate:** if the diff touches `sd-ai-command-pack-status.py`, stop. AC1 is a
   verification, not a deliverable. Confirm it and move on.

2. **Ignore the PRD's evidence line numbers; all three are wrong.**

   ```
   PRD: sd-status/SKILL.md:68-81         actual F-*/T-* definition: :74-89
   PRD: sd-status/SKILL.md:134-138       actual F/T/R token:        :140
   PRD: sd-housekeeping/SKILL.md:75-77   actual F/T/R mention:      :118
   ```

   **Gate:** `sd-housekeeping/SKILL.md:75-77` is the
   `sd-ai-command-pack-pr-eligibility.py` receipt contract — `status`,
   `reasonCodes`, `checks`, `reviewThreads`, `finishWork`, and
   `gh pr merge --match-head-commit`. It has nothing to do with selectors. If
   the diff touches those lines, the wrong citation was followed.

3. Edit `templates/.agents/skills/sd-status/SKILL.md:140`: `F/T/R` → `F/T`.
   Leave the rest of the paragraph alone — the sentence that a selection "does
   not retroactively authorize `sd-status` to mutate the repository or bypass
   the selected workflow's task, approval, and safety gates" is the safety
   contract and is unaffected.

4. Edit `templates/.agents/skills/sd-housekeeping/SKILL.md:118`:
   `F/T/R selectors,` → `F/T selectors,`. That satisfies R4 by itself —
   housekeeping relays the `sd-status` result, so it inherits the selector and
   `none` rules by reference rather than restating them.

5. **Add the R3 rejection sentence — without naming `R`.** After the existing
   paragraph at `sd-status/SKILL.md:140-144`:

   > A selector that is not an `F-*` or `T-*` row of this snapshot is
   > unsupported input: report it as unresolved against the current report and
   > take no action.

   **Gate:** writing "`R-*` is no longer supported" satisfies R3 and *fails
   R5's own drift test in the same commit* — the retired selector is back on a
   live surface. Reject by exclusion, never by naming. The generic form is also
   what makes AC4's "stale-snapshot" half work: `F-9` against a three-row
   report resolves to the same unresolved result.

6. **Do not edit `sd-status/SKILL.md:74-89`.** The `F-*`/`T-*` definitions —
   including the roadmap-source rules and "IDs are deterministic for the
   reported snapshot but are not durable task identities" — already say exactly
   what R2 requires.

7. **Write R5's drift test as an allowlist over the shipped surface.** Scan
   `templates/`, the root mirrors, `docs/`, and generated adapters for `F/T/R`,
   `` `R-*` ``, and separate-Roadmap-collection wording. **Never scan
   `.trellis/`.**

   **Gate:** the tempting shape is a repo-wide grep minus an exclusion list. It
   would have to exclude, today:

   ```
   .trellis/tasks/archive/2026-07/07-23-expand-sd-status-selectable-inventory/   (6 hits)
   .trellis/tasks/archive/2026-07/07-23-status-untracked-roadmap-items/prd.md    (1 hit)
   .trellis/workspace/sdelmas/journal-5.md:169                                   (1 hit)
   .trellis/tasks/07-24-align-status-selector-contract/prd.md                    (7 hits)
   .trellis/tasks/07-24-correct-sd-skill-contract-drift/prd.md                   (5 hits)
   .trellis/tasks/07-22-streamline-sd-skill-workflows/prd.md:70                  (1 hit)
   ```

   The last three are active task PRDs describing this very removal. A denylist
   breaks the next time anyone documents the history; an allowlist cannot.

   Do not hardcode the two mirror paths — `07-28-stop-committing-generated-mirrors`
   deletes them.

8. `make sync` (`install.py . --force`) regenerates
   `.agents/skills/sd-status/SKILL.md` and
   `.agents/skills/sd-housekeeping/SKILL.md`. Do not hand-edit the mirrors.

9. R6 bookkeeping: `SKILL.md` bodies are shipped payload, so both edits move the
   payload digest — version bump, changelog, candidate ledger restamp.

## Validation

The retired wording is gone from every live surface (AC5) and survives only
under `.trellis/`:

```bash
grep -rn 'F/T/R\|`R-\*`' templates/ .agents/ docs/ .claude/ .gemini/ .opencode/ .github/prompts/
```

Expect no hits. Before the edit this returns exactly 4 — two authored files and
their two mirrors.

The history is untouched:

```bash
grep -rln 'F/T/R\|`R-\*`\|R-1' .trellis/ | sort
```

Expect the same 6 paths listed in step 7, unchanged.

The code emits only `F` and `T` (AC1 — verification, not change):

```bash
grep -n 'select_items(' scripts/sd-ai-command-pack-status.py
```

Expect `prefix="T"` once and `prefix="F"` twice, and no diff to this file.

Template and mirror are byte-identical after sync (AC6):

```bash
diff -q templates/.agents/skills/sd-status/SKILL.md .agents/skills/sd-status/SKILL.md
```

```bash
python3 -m pytest tests/test_status.py -q
```

```bash
make check
```

**Not verified by any of the above:** AC4's behavioral half. Selector resolution
is skill prose executed by a model, not code — no test can assert that an `R-1`
request "returns a precise unsupported/stale-snapshot result and performs no
mutation". The greps prove the instruction is present and unambiguous; they do
not prove a host follows it. Say that in the AC4 record rather than marking it
met because the wording landed. Likewise AC3 (untracked roadmap items still
appear as deduplicated `F-*` with path/line evidence) is unchanged behavior
covered by existing `tests/test_status.py` cases — it is a regression guard
here, not new verification.

## Review gates

- No diff to `scripts/sd-ai-command-pack-status.py` (step 1).
- No diff to `sd-housekeeping/SKILL.md:75-77` (step 2).
- No diff to `sd-status/SKILL.md:74-89` (step 6).
- The rejection sentence does not contain the letter `R` as a selector
  (step 5) — check the diff, not the intent.
- The drift test scans an allowlist and never `.trellis/` (step 7).
- The drift test does not hardcode mirror paths (step 7).
- Mirrors changed by `make sync`, not by hand (step 8).
- No third selector category anywhere in the diff (PRD "Out of scope").

## Rollback

Straight revert. No data, no state, no consumer contract moves — the wording
described a capability the code had already lost, so removing it changes
nothing observable and restoring it would too.

The one coupling is the drift test: revert the prose edits without the test and
`make check` fails on the retired wording the revert restored. Revert both or
neither.
