# Implementation — stop committing generated mirrors

## Blocking prerequisite

`07-28-regenerate-fleet-refresh-adapters` must land first. Until it does,
`install.py . --force` cannot regenerate the four source-only fleet-refresh
adapters (no manifest entry; `installer/removal.py:272-275` skips them), so
gitignoring the mirror roots deletes them permanently. Verify before starting:

Run this in a throwaway clone, never in the working checkout — the probe forces
a regeneration and an earlier draft did it behind `git stash -u`, which sweeps
every untracked file in the tree into a stash it never restores:

```bash
rm -rf /tmp/sdprobe && git clone -q . /tmp/sdprobe && python3 /tmp/sdprobe/install.py /tmp/sdprobe --force && git -C /tmp/sdprobe status --short .claude/commands/sd/fleet-refresh.md
```

**Gate:** the adapter must be regenerated, not reported deleted. If it is
deleted, stop — the prerequisite has not landed.

## Stage 1 — drop the duplicate manifest

1. Confirm the duplication is exact:

   ```bash
   cmp manifest.json .sd-ai-command-pack/manifest.json && echo identical
   ```

2. Coordinate with A-058 (orphan manifest targets) before removing any manifest
   entry. An orphaned target is a hard consumer-audit failure.

3. `git rm --cached .sd-ai-command-pack/manifest.json`, add the ignore rule,
   confirm `install.py` still produces it.

4. **Consumer proof** — the single most important check in this task:

   ```bash
   rm -rf /tmp/sdconsumer && mkdir -p /tmp/sdconsumer && git -C /tmp/sdconsumer init -q
   python3 install.py /tmp/sdconsumer && ls /tmp/sdconsumer/.sd-ai-command-pack/manifest.json
   ```

   **Gate:** land stage 1 alone, green, before touching anything else.

## Stage 2 — the mirrors

5. **Choose the bootstrap option** from `design.md` (A: CI bootstrap + documented
   local step; B: keep `.claude/`+`.agents/` tracked). Record the choice and why.
   **Gate:** decided before any `.gitignore` edit — it determines what gets
   ignored.

6. Add the CI bootstrap step (`install.py . --force`) **before** ignoring
   anything, and prove CI is green with it while the files are still tracked.
   Ordering matters: this way a CI failure means the bootstrap is wrong, not that
   the surface vanished.

7. Add the ignore rules and `git rm --cached` the chosen set.

8. Add the regeneration check. **Its shape depends on step 5's choice, and the
   two are not interchangeable:**

   - Under **B** (mirrors stay tracked): `install.py . --force` then
     `git diff --exit-code` over the mirror roots. A committed stale mirror
     shows as a diff and fails.
   - Under **A** (mirrors ignored and untracked): `git diff` reports nothing for
     ignored paths, so the diff check is **inert** — it would pass forever and
     read as coverage. Staleness of a committed file is also impossible by
     construction, because no mirror is committed. What must be checked instead
     is that regeneration *succeeds and is complete*: run `install.py . --force`
     into a clean clone and assert the expected target set exists and matches
     `manifest.json`. The failure this guards is a generator that silently stops
     emitting a target, not a mirror that drifted.

9. **Prove the step-8 check bites**, in the form matching the choice: under B,
   commit a deliberately stale mirror and confirm CI fails; under A, remove a
   manifest target's generator output and confirm the completeness assertion
   fails. **Gate:** a check that cannot be made to fail is not a check. If the
   chosen form has no reachable failure, say so and drop it rather than shipping
   a green light that means nothing.

10. Update the contributor quickstart with the one-step bootstrap.

## Stage 3 — machinery

11. Only after stage 2 has run green for a release cycle. Retire or collapse
    `tests/test_generated_parity.py` (94,825 B), `tests/test_pack_drift.py`
    (25,841 B), `scripts/sd-ai-command-pack-surface-check.py` (29,730 B),
    `.github/scripts/check-command-surface-drift.py` (23,219 B) — 173,615 B total.
    **Gate:** each module retired only once something else demonstrably covers
    what it covered. These suites are the safety net for stages 1 and 2.

## Validation

```bash
make sync && make check
```

```bash
git ls-files | grep -c "^\.sd-ai-command-pack/manifest.json"
```

Expect `0` after stage 1.

## Review gates

- Before anything: the fleet-refresh prerequisite verified by regeneration, not
  by reading a task status.
- Stage 1 lands and ships alone.
- Before stage 2 step 7: CI bootstrap proven green while files are still tracked.
- Stage 3 blocked until stage 2 has a release cycle of evidence.

## Rollback

Stages 1 and 2: revert plus re-add the files. Stage 3: not cheaply reversible —
that is why it is last.
