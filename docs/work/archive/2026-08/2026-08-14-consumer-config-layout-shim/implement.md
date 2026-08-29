# Implementation plan — consumer-config layout shim

Source of truth for every payload edit is `templates/`. Editing the generated
copy (`scripts/`, `docs/`, `plugins/sd/**`) is silently reverted by `make sync`
— this cost a round last session on `docs/SD_AI_COMMAND_PACK.md`.

## 1. Make the resolver self-contained (D3)

- [x] 1.1 In `templates/scripts/sd-ai-command-pack-review-layout.py`, replace
      `from sd_ai_command_pack_lib import CommandError, resolve_state_root`
      with local definitions of both, each carrying a comment naming
      `scripts/sd_ai_command_pack_lib.py:248-292` as the repo-side original.
- [x] 1.2 Add `tests/test_review_layout.py` cases asserting the carried ladder
      and `resolve_state_root` agree on all five rungs: explicit `state_home`,
      `SD_AI_COMMAND_PACK_STATE_HOME`, `XDG_STATE_HOME`, `LOCALAPPDATA`, and
      the `home` fallback. **AC4.**
- [x] 1.3 Add a case that imports the module with `sd_ai_command_pack_lib`
      absent from `sys.path` and resolves a thin layout successfully. **AC3.**
      Use the existing `importlib.util.spec_from_file_location` loader; a
      subprocess would inherit a `sys.path` that hides the failure.

Validation: `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- -m unittest tests.test_review_layout -v`

**Rollback point A** — the file still works in both existing layouts at this
point; nothing is registered yet.

## 2. Register the second install target (D1, D2)

- [x] 2.1 Add the manifest row: `platform: "shared"`, `kind: "script"`,
      `source: "templates/scripts/sd-ai-command-pack-review-layout.py"`,
      `target: ".sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py"`,
      `install: "always"`. The basename is kept deliberately (D2, resweep
      rule 5); do not shorten it.
- [x] 2.2 Add `(".sd-ai-command-pack/bin/**", CONSUMER_CONFIG, False)` to
      `TARGET_OVERRIDES` in `.github/scripts/partition-surfaces.py`, in the
      consumer-config block **above** the `scripts/**` entry (first match wins).
- [x] 2.3 Record the category counts before and after. Expect
      `consumer-config` 6 → 7 and no other category to move. **AC1.**

Validation:
```
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  .github/scripts/partition-surfaces.py
bash scripts/sd-ai-command-pack-toolchain.sh run-python -- \
  .github/scripts/partition-surfaces.py --check
```

## 3. Tests that would catch this being wrong

- [x] 3.1 `tests/test_conversion_plan.py`: a consumer whose declared platforms
      exclude `claude` still has the target in `expected_residual_targets`.
      **AC2.**
- [x] 3.2 A resweep fixture holding a reference to
      `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py` reports
      **not** a blocker, and the same fixture holding
      `scripts/sd-ai-command-pack-review-layout.py` reports a blocker. Both
      directions. **AC7.**
- [x] 3.3 Shell, Python, and Node callers return the same answer for one
      `--resolve` query. **AC5.** Extend the existing binding-agreement test
      rather than adding a third.
- [x] 3.4 Pin the documented `--path` bound (D5b): in a converted layout, a
      `scripts/sd-ai-command-pack-*.py` path classifies `authored`, because the
      query answers about the current install rather than about history. The
      test asserts the documented answer, so a later change to it fails here.
      **AC9.**

## 4. Point the bindings at the vendored path (D4)

**Done 2026-08-14 — the premise was wrong, so 4.1 and 4.2 are not changes.**
Neither binding carries a repo-root literal. `review-scope.sh:364` invokes
`"$SCRIPT_DIR/sd-ai-command-pack-review-layout.py"` and
`review-preflight.mjs:249` uses `resolve(scriptDir, ...)` — both resolve a
sibling. Both bindings are themselves `machine-claude`, so under thin they and
the resolver travel together into the agents-bin directory and sibling
resolution keeps working. Repointing them at `.sd-ai-command-pack/bin/` would
replace a self-relative reference with a CWD-relative one and make a
machine-installed binding depend on which consumer it happens to be run from.
Left alone deliberately.

- [x] 4.1 `templates/scripts/sd-ai-command-pack-review-scope.sh` — no literal
      to repoint; verified sibling resolution.
- [x] 4.2 `templates/scripts/sd-ai-command-pack-review-preflight.mjs` — same.
- [x] 4.3 Confirm no residue-gate violation: the plugin build refuses repo-root
      pack path literals in shipped `bin/` scripts unless allowlisted
      (`installer/references.py:108`). The new literal is not a repository-root
      path, but confirm rather than assume.
- [x] 4.4 **Found while testing, not fixed here.** `review-scope.sh:6` sets
      `REPO_ROOT="$SCRIPT_DIR/.."` and passes it as `--root`. Under fat that is
      the consumer, because `scripts/` is inside it; under thin the script
      lives in the agents-bin directory and `$SCRIPT_DIR/..` is `~/.agents`,
      not the consumer being asked about. It degrades quietly rather than
      failing — the machine receipt still resolves, so the report says `thin`
      and classifies — but the root is wrong. Out of scope (this task changes
      no binding) and recorded as a follow-up; the AC5 test compares both
      callers against the same root so it tests delegation rather than
      asserting around this.

## 5. Payload cascade — order is load-bearing

`candidate-check` digests the *current* `plugins/sd`, so `generate` runs on
both sides of it. Run these serially; overlapping background runs invalidate
each other's digest (cost a round last session).

- [x] 5.1 `make sync`
- [x] 5.2 `make generate`
- [x] 5.3 `sd-ai-command-pack-fleet-candidate-check.py`
- [x] 5.4 `make generate`
- [x] 5.5 Manifest version bump + matching `CHANGELOG.md` top heading
- [x] 5.6 `make sync` again for the `command-catalog.md` mirrors
- [x] 5.7 Confirm `shipped-surface closure: clean`
- [x] 5.8 The pack self-installs, so the new target appears as a tracked file
      in this repository too (`.sd-ai-command-pack/` is tracked here; only
      `installed-targets.txt` is ignored, `.gitignore:25`). Expect it in the
      diff and list it under the PR's generated scope rather than treating it
      as a stray.

## 6. Docs

- [x] 6.1 `templates/docs/SD_AI_COMMAND_PACK.md` — extend the
      `review-layout.py` bullet with the vendored path and when to use it.
      **Not** `docs/SD_AI_COMMAND_PACK.md`.
- [x] 6.2 `docs/FLEET_ROLLOUT.md` (or the conversion doc it points at) — record
      the five-step cohort ordering from D7. **AC8.**
- [x] 6.3 Check whether the shipped-script docs gate
      (`.github/scripts/check-shipped-script-docs.sh`) keys on the target path
      or the source path; a second target may need a second bullet.

## 7. Close the open questions (D8)

Each is a check with a stated failure meaning, not a look-over.

- [x] 7.1 **O1** — `sd-ai-command-pack-install-audit.py` after a self-install;
      `installed-targets.txt` must list both paths. A duplicate-source
      complaint means the two-row shape is rejected and D1 needs revisiting.
- [x] 7.2 **O2** — `make generate`; `plugins/sd/bin/` gains no second copy.
- [x] 7.3 **O3** — machine payload row count unchanged.
- [x] 7.4 **O4/O5** — compare installed file modes of both copies; confirm the
      consumer-config copy is absent from the machine receipt.

## 7b. Gates that fired unplanned

Four repo-owned gates rejected the change before `make check` passed. Recorded
because three were correct and one was a design conflict, not a nuisance.

- [x] **Plugin residue gate** — a comment naming `scripts/sd_ai_command_pack_lib.py`
      is a repository-root literal in a shipped `bin/` script. Reworded to name
      the module without its path.
- [x] **Machine-payload rewrite gate** — the new guide bullet contained the glob
      `scripts/sd-ai-command-pack-*.py`, which the reference rewriter cannot
      repoint. Reworded to prose.
- [x] **`test_committed_tree_carries_no_consumer_config_payload`** — checks the
      plugin tree for consumer-config *names* and *bytes* as proxies for a
      renamed copy. Sound only while a source's targets share one category;
      this source now has two. Tightened to assert the target path never ships,
      with the proxies kept for rows they can still judge and a guard that the
      exemption cannot widen to every row.
- [x] **`test_state_root_boundary`** — A-046's one-ladder gate. See design D3c:
      the alternative was vendoring a 1230-line library to avoid duplicating
      ~45 lines. Narrow exemption, justified in the gate file, with the
      no-drift property preserved by an agreement test the gate now requires to
      exist.
- [x] **`test_the_residual_is_the_measured_thirty_two_targets`** — the residual
      a converted consumer keeps grew 31 → 32, which is the change working.
      Count and name updated, and the new target asserted by path so the
      figure cannot drift back to being arithmetic nobody reads.

## 8. Gates

All four close **AC6**.

- [x] 8.1 `make check` exit 0
- [ ] 8.2 `make release-prep` exit 0 — run **after** the last task-artifact
      edit, or the run is stale
- [x] 8.3 Coverage floor 95 still met for the resolver (the inlined ladder adds
      statements; add tests, do not lower the floor)
- [x] 8.4 Every copy of the resolver byte-identical — the four existing paths
      plus the new installed target

## 9. PR

- [ ] 9.1 PR body with `## Tooling/generated scope:` — the new manifest row,
      the partition override, the regenerated mirrors, the version bump.
- [ ] 9.2 First-review risk disposition for the changed categories
      (`environment-global-state` for the inlined ladder above all).
- [ ] 9.3 Copilot round; resolve threads; merge when green and comment-clean.

**Rollback point B** — after step 5, rollback is `git revert` of the row and
override plus a regenerate. After a fleet refresh has shipped it, rollback
leaves a stale unreferenced file in consumers until their next refresh; that is
harmless only while no consumer references it, which is true until cohort
step 3 (D7).

## Not in this task

Rewriting the 68 consumer call sites, deleting the five bespoke guards,
resolving the 101 glob blockers, and converting any consumer. All cohort work.
