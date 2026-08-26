# Implementation plan — `AGENTS.md` routing managed block

Read `design.md` first. Every decision below is settled there; this file is the
ordering, the commands, and the gates.

Environment note: a linked worktree has no `.venv` of its own. Point `PY` at the
interpreter in the main checkout's virtual environment:

```bash
PY="$(git rev-parse --path-format=absolute --git-common-dir)/../.venv/bin/python"
```

Use `PYTHON_BIN="$PY"` for `.github/scripts/run-tests.sh`, and `"$PY"` directly
for `install.py` instead of `make sync`.

---

## Step 0 — branch

```bash
git switch -c feat/agents-routing-managed-block
```

Rollback point: `git switch main` (nothing written yet).

---

## Step 1 — registry constants and the shared spec table

`installer/registry.py`, beside `MANAGED_BLOCK_KIND` (line ~2326):

- `AGENTS_ROUTING_TARGET = Path("AGENTS.md")`
- `AGENTS_ROUTING_START = "<!-- SD-AI-COMMAND-PACK:ROUTING:START -->"`
- `AGENTS_ROUTING_END = "<!-- SD-AI-COMMAND-PACK:ROUTING:END -->"`
- `MANAGED_BLOCK_SPECS` — target string → spec carrying `start`, `end`,
  `label`, `preserve_invalid_utf8`, `adopt_on_thin`, `create_if_absent`,
  `strip_on_thin`. Three entries:

  | target | create_if_absent | adopt_on_thin | strip_on_thin |
  | --- | --- | --- | --- |
  | `.gitignore` | yes | yes | yes |
  | `.github/copilot-instructions.md` | yes | no | yes |
  | `AGENTS.md` | **no** | no | **no** |

  `strip_on_thin` is what lets the two thin-side tables stop hardcoding
  targets; see design §3.
- Add all four names to `__all__`.

Validation:

```bash
"$PY" -c "import installer.registry as r; print(sorted(r.MANAGED_BLOCK_SPECS))"
```

Expect exactly the three targets. No behaviour change yet.

---

## Step 2 — parameterize the merge and the writer

`installer/fileops.py`:

1. `merge_managed_block(current, block, *, start, end, label)` — markers become
   arguments. Body otherwise unchanged (design §3: do not invent a second merge
   semantics).
2. `normalize_managed_block_template` — validate the target's own marker pair.
3. `install_managed_block` — replace the `!= COPILOT_INSTRUCTIONS_TARGET`
   assert with a `MANAGED_BLOCK_SPECS` lookup; keep the `SystemExit` for an
   unknown target. Before the `destination.exists()` branch, add the
   defence-in-depth guard:

```python
if not destination.exists() and not spec.create_if_absent:
    return InstallResult(file, InstallStatus.PRESERVED)
```

4. **`selected_files` — the actual enforcement point** (design §2.1). At the
   **top of the per-file loop** (`installer/fileops.py:226`), before every
   install-mode branch. The row is `install: "always"` (Step 5), so the
   `ALWAYS_INSTALL` branch at `installer/fileops.py:227-229` short-circuits and
   every branch below it — the platform filter, the anchor gate, the
   active-platform check — is dead for this row. The top of the loop is the
   only reachable placement. Skip a managed-block row whose target is absent
   and whose spec does not authorize creation:

```python
spec = MANAGED_BLOCK_SPECS.get(file.target.as_posix())
if spec is not None and not spec.create_if_absent:
    if not path_is_occupied(target / file.target):
        skipped.append((file, f"{file.target} not present; block not created"))
        continue
```

   `path_is_occupied` (`installer/fileops.py:256-257`), **not** `.exists()`:
   `.exists()` follows symlinks and is `False` for a dangling `AGENTS.md`
   symlink, which would silently skip the case the writer must report as a
   symlink conflict. Test 15 is what catches this.

   This is not a nicety. `installed_targets_content` is built from `selected`
   (`installer/provenance.py:71-77`), so a selected-then-preserved row is
   written into `.sd-ai-command-pack/installed-targets.txt`, and
   `audit_structural_state` then fails with `installed target is missing:
   AGENTS.md` (`sd-ai-command-pack-install-audit.py:693`) because `AGENTS.md`
   is tracked, not gitignored. `--check` reports `audit: failed`. Step 9's
   first fixture case is what proves this did not happen.

Gate — the existing suite must be green **before** any manifest row exists, so
a regression here is unambiguous:

```bash
PYTHON_BIN="$PY" .github/scripts/run-tests.sh
```

Expect 83 modules, 0 failures. Rollback point: this step is behaviour-preserving
by construction; if the suite is red, the parameterization is wrong, not the
feature.

---

## Step 3 — removal

`installer/removal.py`:

- import the routing constants;
- add `AGENTS.md` to `MANAGED_BLOCK_REMOVAL_TARGETS` (line ~55);
- replace the two hand-written `remove_text_block_file` calls (lines ~334-356)
  with a loop over the strip-relevant `MANAGED_BLOCK_SPECS` entries, preserving
  the existing per-target `preserve_invalid_utf8` / `adopt` arguments.

Lines 109 and 154 derive from the set and need no edit — confirm by reading,
not by assuming.

**Also wire both thin-side tables to the shared spec** (design §3 promises
`fileops`, `thin`, and `removal` all read it, and Step 1 alone does not deliver
that):

- `installer/thin.py`'s `BLOCK_MARKERS` becomes a derived view of
  `MANAGED_BLOCK_SPECS` filtered on `strip_on_thin`, so `AGENTS.md` is absent
  by construction rather than by omission — the property design §5 needs.
- `scripts/sd-ai-command-pack-thin-resweep.py`'s `STRIPPED_BLOCK_LABEL`
  (canonical copy under `templates/scripts/`) becomes the same derived view.
  Its own comment already claims the mapping "is derived from the same
  constants removal uses, so the two cannot drift apart"; this is what makes
  that true instead of asserted.

**Do not let `adopt` leak into ordinary uninstall.** Today `.gitignore` is
adopted on thin conversion (`installer/thin.py:817-824`, `:1012-1023`) but
*removed* on ordinary uninstall, because `remove_text_block_file`'s `adopt`
defaults to `False` and `removal.py:334-343` does not pass it. The spec field
is named `adopt_on_thin` for that reason; the Step 3 removal loop must not pass
it. `tests/test_remove.py`'s existing `.gitignore` assertions are the guard —
if they change, the loop is wrong.

```bash
PYTHON_BIN="$PY" "$PY" -m unittest tests.test_remove -v 2>&1 | tail -5
```

---

## Step 4 — the template

`templates/AGENTS.sd-ai-command-pack.md`. Content rules from design §1.4 and
§1.5:

- routes by **intent**, not by an enumerated installed-skill inventory;
- opens with `AGENTS_ROUTING_START`, closes with `AGENTS_ROUTING_END`;
- carries the design §1.5 verification sentence verbatim;
- carries the standard "edits outside this block are preserved" note, matching
  the Trellis block's own wording register.

No test yet — it is validated by Step 7's install tests.

---

## Step 5 — manifest row and partition override

1. `manifest.json` — insert the row from design §4 **with `"install":
   "always"` and no `anchor`**, in the file's existing sort position. **Do not
   hand-edit the mirrors.**

   Omitting `install` defaults it to `if-anchor-exists`
   (`installer/manifest.py:91`), which for platform `shared` is never selected
   in a normal install: `shared` declares no activation markers
   (`installer/registry.py:403-406`), so `has_active_trellis_platform` returns
   `False` (`installer/fileops.py:208-210`). The row would install only under
   an explicit `--platform shared`. Step 9's second fixture case — a normal
   install with no `--platform` — is what proves this did not happen.
2. `.github/scripts/partition-surfaces.py` — add `("AGENTS.md", REPO_NATIVE,
   False)` to `TARGET_OVERRIDES` with the design §4 comment.

Order matters: the override hard-errors if it matches zero rows, so the
manifest row goes first.

```bash
"$PY" .github/scripts/partition-surfaces.py --check
```

Expect clean. A failure here means the override and the row disagree.

---

## Step 6 — the target-path sites (canonical, under `templates/`)

`templates/scripts/sd-ai-command-pack-install-audit.py:128` — add `"AGENTS.md"`
to `PROVENANCE_NEVER_VOUCHED_TARGETS`.

This is design §6.1: the site a marker sweep does not reach. Edit the
**template**; the `scripts/`, `plugins/sd/bin/`, and
`plugins/sd/machine-payload/scripts/` copies are regenerated in Step 8.

Two more target-path sites in the same class, both from design §6:

1. `templates/scripts/sd-ai-command-pack-review-learnings.py:153-157` — add
   `"AGENTS.md"` to `GENERATED_SIGNAL_PATHS`. The set drives comment
   classification (`:1117`) and planning-signal classification (`:1288`);
   without it, review feedback on the new pack-managed surface classifies as
   `SIGNAL_OTHER`.
2. `templates/scripts/sd-ai-command-pack-review-preflight.mjs:5012` — add
   `AGENTS.md` beside the `.github/copilot-instructions.md` literal in
   `isSdCommandPackCopiedPath`. `packInstalledTargets()` covers the target when
   the receipt is readable; the literal is the fallback for a missing or stale
   receipt, and without it the new managed-block target classifies as
   consumer-authored in exactly that case.
3. Shipped user-facing inventories that today name only the Copilot block:
   `README.md:41,647,667` and `templates/docs/SD_AI_COMMAND_PACK.md:563,2351`.
   Each recites what the pack installs, merges, or strips. Leaving them ships
   install/removal documentation that is false about the new target.

---

## Step 7 — tests

Write the fifteen tests from design §8 (test 7 has two parts), in the modules
named there. Three are
load-bearing and must be **shown to fail** against the implementation without
their guard:

- test 3 (`AGENTS.md` absent under an explicit `--platform` filter, and under
  `--all`) — fails if the skip sits below the `install_all or platform_filter`
  short-circuit;
- test 9 (a **stale/hand-authored** provenance entry for `AGENTS.md` produces no
  drift failure) — fails without Step 6. Note the shape: an ordinary install
  writes no `AGENTS.md` provenance entry at all, so a test that merely edits
  the file outside the markers passes with or without Step 6 and proves
  nothing. See design §8 test 9;
- test 15 (dangling `AGENTS.md` symlink) — fails against a `.exists()`-based
  gate.

Demonstrate all three by temporarily reverting the one line each depends on,
running the test, and restoring. Record the observed failure output in the PR
body.

```bash
PYTHON_BIN="$PY" .github/scripts/run-tests.sh
```

---

## Step 8 — regenerate the mirrors, in this exact order

The candidate ledger digests the *generated* plugins tree, so the candidate
check before the first `make generate` produces a ledger the second call calls
stale. Order is load-bearing:

```bash
"$PY" install.py . --force
make generate
"$PY" scripts/sd-ai-command-pack-fleet-candidate-check.py
make generate
```

Expect `shipped-surface closure: clean` from the final `make generate`.

**Expect this repository's own `AGENTS.md` to change.** `install.py . --force`
installs the pack into this checkout, so the routing block lands in the repo's
own `AGENTS.md`, appended after `## Contributor Entry Points`. That is the
pack dogfooding its own row and belongs in the diff; do not revert it. Check
that the existing `TRELLIS:START`/`TRELLIS:END` block and both maintainer
sections are byte-unchanged — this checkout is the richest real fixture the
change has.

Then confirm the four copies of the audit script are byte-identical:

```bash
for f in scripts plugins/sd/bin plugins/sd/machine-payload/scripts; do
  shasum -a 256 "$f/sd-ai-command-pack-install-audit.py"
done
shasum -a 256 templates/scripts/sd-ai-command-pack-install-audit.py
```

All four digests equal.

---

## Step 9 — end-to-end proof on a real fixture

Not a unit test — the thing a consumer actually sees. Build a fixture, install
**with no `--platform` flag** (that is the normal contract, and the flag hides
the C-6 failure mode entirely), and check the four cases by hand before opening
the PR:

```bash
C=$(mktemp -d)/consumer
mkdir -p "$C/.trellis" "$C/.github/skills/trellis-before-dev"
cd "$C" && git init -q .
printf 'version: 1\n' > .trellis/config.yaml
printf '# marker\n' > .github/skills/trellis-before-dev/SKILL.md
```

- **no `AGENTS.md`**: install, then assert the file is still absent, that
  `AGENTS.md` does **not** appear in
  `"$C"/.sd-ai-command-pack/installed-targets.txt`, and that
  `install.py "$C" --check` reports both `state: current` and `audit: passed`.
  The receipt line is what catches design §2.1's failure mode; `state: current`
  alone does not, because the audit result is reported separately.
- **Trellis-only `AGENTS.md`, normal install (no `--platform`)**: write the
  21-line Trellis block, run `install.py "$C"` with no platform flag, assert the
  routing block is present and follows `TRELLIS:END`, and that the Trellis slice
  is byte-unchanged. **This is the case that fails if the manifest row kept the
  default `if-anchor-exists`** — the row would be skipped with `active Trellis
  shared install not detected` and the file would come back without the block.
  Read the install output for that skip line, not only the file.
- **consumer prose survives**: add text above, between, and below the two
  blocks; re-install; assert it is all still there.
- **idempotence**: `shasum -a 256 "$C/AGENTS.md"` equal across two installs.

---

## Step 10 — changelog, version, spec

- `CHANGELOG.md` — new section.
- Bump `manifest.json`, `.sd-ai-command-pack/manifest.json`,
  `plugins/sd/.claude-plugin/plugin.json`. **Confirm the version is free** — a
  peer session is holding 0.71.55.
- `.trellis/spec/backend/manifest-and-filesystem.md` — a section recording:
  the managed-block spec table; the skip-when-absent contract and why it lives
  in `selected_files`; the `install: "always"` requirement for a marker-less
  platform; design §6.1's hardcoded target-path sites a marker sweep does not
  reach; and **design §1.5's verification statement verbatim** — the block is
  drift-checked against what the pack shipped, not against the consumer's
  installed skill set. The §6.1 convention is the durable one: without it the
  next managed-block target repeats the miss.
- Re-run `make generate` after the version bump — it names post-bump artifacts.
- Refresh the KB before any `sd-check`, or the deterministic
  `knowledge.obsidian-kb` check fails:

```bash
"$PY" scripts/sd-ai-command-pack-update-spec-kb.py --if-present
```

---

## Step 11 — final gate

```bash
PYTHON_BIN="$PY" .github/scripts/run-tests.sh
"$PY" .github/scripts/check-helper-resolution.py
"$PY" .github/scripts/partition-surfaces.py --check
make generate
```

`check-helper-resolution.py` is a **separate CI step, not part of the unittest
suite** — a green `run-tests.sh` does not cover it. Every fenced bash block
using `"$SD_PACK_TOOLCHAIN"` needs a byte-identical copy of the canonical 7-line
bootstrap; if Step 4's template or the spec section adds such a block, this is
what catches it.

Then ship through `sd-ship until=merge`.

---

## Step 12 — post-merge handoff: fleet rollout

Acceptance criterion 10 asks for "fleet rollout via normal refresh", and no
step above produces that evidence. It is **post-archive handoff**, not an
acceptance criterion blocking archival: it happens after the merge, on the
synchronized default branch.

Run the pack's normal fleet refresh for the merged version and record the
result. Nothing here is version-specific — the new manifest row rides the same
refresh every release uses — so the evidence to capture is simply that the
refresh ran clean at the merged head, and which consumers it reached.

---

## Review gates

- **After Step 2**, before the manifest row exists: full suite green. Proves the
  parameterization is behaviour-preserving.
- **After Step 5**: `partition-surfaces.py --check` clean. Proves the row and
  the override agree.
- **After Step 3**: `tests/test_remove.py`'s existing `.gitignore` assertions
  unchanged. Proves `adopt_on_thin` did not leak into ordinary uninstall.
- **After Step 7**: tests 3, 9, and 15 demonstrated failing without their
  guard. Proves they test something.
- **After Step 8**: `shipped-surface closure: clean` + four equal digests.
  Proves nothing was hand-edited in a mirror.
- **After Step 9**: the four fixture cases by hand, on a **no-`--platform`**
  install. Proves the consumer-visible contract, which no unit test fully
  covers, and is the only gate that catches a wrong `install` mode.

## Rollback points

| after step | rollback |
| --- | --- |
| 0-2 | `git switch main` — behaviour-preserving refactor only |
| 3-4 | revert the removal loop and the template; nothing installs yet |
| 5+ | drop the manifest row **and** the override row together — the override hard-errors alone |
| 8+ | re-run the Step 8 sequence after any revert; a reverted canonical file leaves stale mirrors |
