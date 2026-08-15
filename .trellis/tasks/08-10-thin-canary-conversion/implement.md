# Implement: convert the canary cohort to thin mode

Ordered. A phase does not start until the previous phase's validation line
passes. `<pack>` is this repository; the three canary checkouts are:

```
rwbp-coordinator  ~/repos/rwbp/rwbp-coordinator
loadsmith         ~/repos/platypeeps/loadsmith
hoa-manager       ~/repos/platypeeps/hoa-manager
```

All three were measured clean and on `main` at
`e76ca314` / `280cc49f` / `ab755cfe` on 2026-08-15.

## Phase 0 — repoint the pack's own 15 citations (pack repo)

- [ ] 0.1 Read all six templates in full before editing; the citations sit in
      managed blocks whose emission differs from the file on disk.
- [ ] 0.2 Edit `templates/.github/copilot-instructions.sd-ai-command-pack.md`
      (7 hits), `templates/.github/PULL_REQUEST_TEMPLATE.md` (2),
      `templates/.github/prompts/sd-housekeeping.prompt.md` (2),
      `templates/.github/prompts/sd-review-learnings.prompt.md` (2),
      `templates/.github/prompts/sd-review.prompt.md` (1),
      `templates/.github/prompts/sd-status.prompt.md` (1), per design D2's
      three kinds.
- [ ] 0.3 Cascade: `make sync`, `make generate`, candidate-check,
      `make generate`, version bump to `0.71.12`, CHANGELOG heading,
      `make sync`.
- [ ] 0.4 `make check` and `make release-prep` exit 0.
- [ ] 0.5 Answer design O1: read the emitted review-guidance block for a fat
      consumer before and after, and record what changed for a fat reader.
- [ ] 0.6 PR, Copilot review loop, merge.

**Validation:** deferred by design D2a. The claim "the pack no longer cites
removed paths" is proven by the first phase-2 resweep reporting
`packDefects: 0`, not by grepping what I just wrote.

## Phase 1 — machine scope to 0.71.12

- [ ] 1.1 `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- install.py --machine`
- [ ] 1.2 `claude plugin marketplace update sd-ai-command-pack` then
      `claude plugin update sd@sd-ai-command-pack`. The marketplace refresh
      alone does not move an installed plugin and `plugin install` reports
      "already installed" rather than upgrading (recorded 2026-08-12).
- [ ] 1.3 Record the `sd-status fleet --json` machine scope block.
- [ ] 1.4 Answer design O3: the install audit lists every script the rewritten
      call sites will resolve.
- [ ] 1.5 Re-record PRD requirement 3's three machine-provisioning lines at
      the new version. They currently cite 2026-08-12 at 0.71.2; that gate is
      the reason conversion is safe for a Codex user, and it must cite the
      provisioning that is actually in front of the conversion.

**Validation:** `machineScope.state == "installed"`,
`packVersion == pluginVersion == 0.71.12`, `comparison == "current"`, against
`targetPackVersion 0.71.12`. Measured before this phase: `0.71.2` / `0.71.2` /
`current` against a target of `0.71.11` — `comparison` relates the plugin to
the machine payload, not to the target, so `current` at a stale version is
correct and is not the reading that matters here.

## Phase 2 — refresh the three canaries to 0.71.12

Per consumer, in cohort order (rwbp-coordinator, loadsmith, hoa-manager):

- [ ] 2.1 `git -C <path> status --porcelain` empty; on `main`; record HEAD.
- [ ] 2.2 Install the refresh. Installer-managed files only — no product code
      in this phase's diff.
- [ ] 2.3 That consumer's own full check passes.
- [ ] 2.4 Consumer PR, land green.
- [ ] 2.5 `install.py <path> --check --json` reports state `current`.
- [ ] 2.6 Re-run the resweep and record `packDefects`. **This closes phase 0.**

**Validation:** all three at `0.71.12`, `packDefects: 0` for each. A non-zero
count here means phase 0 missed a surface; return to phase 0 rather than
proceeding with a partial fix.

## Phase 3 — rewrite each canary's own citations

Measured 2026-08-15, per canary, before any rewrite:

| consumer | blockers | files |
|---|---:|---:|
| rwbp-coordinator | 49 | 8 |
| loadsmith | 50 | 5 |
| hoa-manager | 34 | 9 |

- [ ] 3.1 rwbp-coordinator: `.github/workflows/ci.yml` (4),
      `.prism/rules.json` (1, PRD requirement 4),
      `.trellis/spec/web/operations/local-development.md` (1),
      `package.json` (1), `scripts/check-full.test.mjs` (1),
      `scripts/check-review-churn.mjs` (36), `scripts/classify-ci-changes.sh` (4),
      `scripts/lib/check-full.mjs` (1).
- [ ] 3.2 loadsmith: `.github/workflows/ci.yml` (2),
      `.trellis/spec/guides/operations-and-release.md` (1),
      `docs/repomix-map.md` (30 — **exclude pack payload from
      `scripts/update_repomix`, then regenerate**; regenerating alone
      reproduces all 30, see design D3a),
      `scripts/check.sh` (2), `scripts/check_review_readiness.sh` (15).
- [ ] 3.3 hoa-manager: `.github/workflows/ci.yml` (4),
      `.trellis/spec/web/testing/verification-commands.md` (3),
      `.trellis/tasks/08-07-task-manifest-context-roots/prd.md` (1 — annotate
      with a dated note; do not rewrite the historical line, design D3b),
      `docs/REVIEW_PATTERNS.md` (1), `package.json` (3),
      `scripts/check-full-prelude.mjs` (3), `scripts/check-full-prelude.test.mjs` (1),
      `scripts/check-review-preflight.mjs` (5),
      `scripts/check-review-preflight.test.mjs` (13).
- [ ] 3.4 Answer design O2 before editing rwbp-coordinator: does the
      `.sd-ai-command-pack/*` citation need an edit at all, given conversion
      keeps that directory?
- [ ] 3.5 Each consumer's own full check passes after its rewrite.

**Validation:** per consumer, the resweep reports `blockers: 0` and verdict
`clear`. Both directions matter: a `clear` verdict with a dirty tree is not
`clear`, because `decide()` counts worktree cleanliness as a reason.

## Phase 4 — convert, per canary, in cohort order

The literal sequence is PRD requirement 1 and is not restated here. Per
consumer:

- [ ] 4.1 `install.py <path> --check --json` state `current`.
- [ ] 4.2 Clean tree; resweep to `/tmp/<consumer>-verdict.json`; verdict `clear`.
- [ ] 4.3 `install.py <path> --thin --resweep-verdict /tmp/<consumer>-verdict.json`.
- [ ] 4.4 Step 2b: `~/.agents/bin/sd-ai-command-pack-update-spec-kb.py --if-present`.
- [ ] 4.5 Step 2c: post-conversion resweep; repoint anything it still reports
      **in this same PR**.
- [ ] 4.6 Consumer PR; land green; verify zero pack CI steps by grepping that
      consumer's `.github/workflows/` at its post-merge HEAD.
- [ ] 4.7 Pack PR carrying that consumer's `mode: thin` row, written by
      `--thin` and not by hand. `make release-prep` — not `make check` alone,
      because each flip changes the fleet-manifest digest pinned into
      `docs/fleet/candidate-validation.json`
      (`scripts/sd_ai_command_pack_fleet_lib.py:766`).
- [ ] 4.8 Compare the post-conversion tree against that consumer's
      **pre-conversion installed-targets receipt**, not against the current
      partition. Record the removal count per consumer; the PRD's 179 dates
      from 0.71.2 and is recomputed, not assumed.

**Validation:** `sd-status fleet --json` shows, for each converted canary,
`installMode == "thin"`, `pin.state == "present"`,
`pin.version == machineScope.packVersion`.

## Phase 5 — revert proof on loadsmith

- [ ] 5.1 `install.py <loadsmith> --revert-thin` at a named commit.
- [ ] 5.2 loadsmith CI green in the reverted state.
- [ ] 5.3 Confirm the only residue is the `enabledPlugins` disable marker.
- [ ] 5.4 Fresh exact-head resweep against the **reverted** tree.
- [ ] 5.5 Re-convert on that fresh verdict.

**Validation:** the reverted commit is named, its CI run is cited, and the
re-conversion used a verdict whose recorded head equals the reverted head.

## Stop conditions

- A `blocked` verdict stops that consumer **and the cohort** (PRD requirement 2).
  It is reported with its reasons and not worked around.
- A dirty, missing, or externally owned consumer checkout stops that consumer.
  Nothing is stashed, reset, cleaned, force-pushed, or cloned.
- Any consumer outside the three named canaries is out of scope, including one
  that a resweep happens to name.

## Rollback points

Design D6, per phase. The two that need a command at hand:

```bash
git -C <path> checkout -- .              # abandon an uncommitted conversion
git checkout -- docs/fleet/consumers.json # and its registry half
```
