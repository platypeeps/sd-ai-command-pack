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

## Phase 0 — unblock conversion at the source (pack repo)

Rewritten after review round 2. The six templates are **not** edited: their fat
wording is correct and the conversion already repoints it (design D2).

- [x] 0A.1 Teach the resweep to scan post-repoint bytes for kept, pack-owned
      files, sourcing the rewrite from `installer.thin.planned_repoints` rather
      than restating the rules in the scanner.
- [x] 0A.2 Keep the change off every other bucket: `blockers` still scan the
      bytes as written, because nothing rewrites a consumer's own file.
- [x] 0A.3 Tests, both directions: a pack-owned kept file whose citation the
      repoint fixes is **not** a `packDefect`; one whose citation survives the
      repoint still **is**. A one-directional test here passes by never firing.
- [x] 0B.1 Change the `.agents/skills/sd-*/SKILL.md` literal rewrite to name
      `~/.agents/skills`, per design D2c and mirroring `AGENTS_DOC_DIRECTORY`'s
      recorded reasoning about suffix matching.
- [x] 0B.2 Test that the rewritten text no longer ends with a removed path.
- [x] 0.3 Cascade: `make sync`, `make generate`, candidate-check,
      `make generate`, version bump to `0.71.12`, CHANGELOG heading,
      `make sync`.
- [x] 0.4 `make check` and `make release-prep` exit 0.
- [x] 0.5 Answer design O1 — **superseded**: no template text changes, so the
      emitted block is unchanged for a fat reader. Record that and close it.
- [ ] 0.6 PR, Copilot review loop, merge.

**Validation:** local and immediate. With the canaries untouched at 0.71.6, all
three resweeps report `packDefects: 0`, down from 15. Measured before: 15 / 15
/ 15, identical by file and text. The negative direction is 0A.3's second test,
not a re-run of the same command.

## Phase 1 — machine scope to 0.71.12

- [x] 1.1 `bash scripts/sd-ai-command-pack-toolchain.sh run-python -- install.py --machine`
- [x] 1.2 `claude plugin marketplace update sd-ai-command-pack` then
      `claude plugin update sd@sd-ai-command-pack`. The marketplace refresh
      alone does not move an installed plugin and `plugin install` reports
      "already installed" rather than upgrading (recorded 2026-08-12).
- [x] 1.3 Record the `sd-status fleet --json` machine scope block.
- [x] 1.4 Answer design O3: the install audit lists every script the rewritten
      call sites will resolve.
- [x] 1.5 Re-record PRD requirement 3's three machine-provisioning lines at
      the new version. They currently cite 2026-08-12 at 0.71.2; that gate is
      the reason conversion is safe for a Codex user, and it must cite the
      provisioning that is actually in front of the conversion.

**Validation:** `machineScope.state == "installed"`,
`packVersion == pluginVersion == 0.71.12`, `comparison == "current"`, against
`targetPackVersion 0.71.12`. Measured before this phase: `0.71.2` / `0.71.2` /
`current` against a target of `0.71.11` — `comparison` relates the plugin to
the machine payload, not to the target, so `current` at a stale version is
correct and is not the reading that matters here.

## Phase 2 — refresh the three canaries to 0.71.13

**Ran once at 0.71.12 and stopped on its own validation line, 2026-08-15.** The
refresh installed `.sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py`
-- the second `consumer-config` target 0.71.11 added, which no consumer had
carried before -- and its docstring and one inline comment named two
machine-scope scripts. `packDefects` went 0 to 2 on all three canaries at once,
identical file and lines. Conversion keeps that file and repoints none of those
forms, so it was a permanent defect, not a rewrite away.

That is what this validation line is for, so it was followed rather than worked
around: back to phase 0, fixed in 0.71.13 with a guard that enumerates every
`consumer-config` target from the surface partition and fails if its shipped
source names a removed path. The version below is 0.71.13 for that reason.

Per consumer, in cohort order (rwbp-coordinator, loadsmith, hoa-manager):

- [x] 2.1 `git -C <path> status --porcelain` empty; on `main`; record HEAD.
- [x] 2.2 Install the refresh. Installer-managed files only — no product code
      in this phase's diff.
- [x] 2.3 That consumer's own full check passes.
- [x] 2.4 Consumer PR, land green.
- [x] 2.5 `install.py <path> --check --json` reports state `current`.
- [x] 2.6 Re-run the resweep and record `packDefects`. **This closes phase 0.**

**Validation:** all three at `0.71.13`, `packDefects: 0` for each. A non-zero
count here means phase 0 missed a surface; return to phase 0 rather than
proceeding with a partial fix. *Exercised once already -- see the note above.*

**Closed 2026-08-15 at 0.71.13.** All three merged to their default branches
and re-measured there:

| consumer | PR | merge | install | blockers | packDefects |
|---|---|---|---|---:|---:|
| rwbp-coordinator | #226 | `b62ee75d` | `current 0.71.13` | 48 | **0** |
| loadsmith | #223 | `97d358f3` | `current 0.71.13` | 23 | **0** |
| hoa-manager | #252 | `359a9020` | `current 0.71.13` | 34 | **0** |

`packDefects: 0` on all three is the reading that closes phase 0. The verdicts
stay `blocked` on consumer-owned citations, which is phase 3's work.

Two check failures on the way, neither caused by the pack and both recorded so
a rerun does not rediscover them: rwbp's PR-body scope gate reads the *live* PR
body, which still described 0.71.12 until it was rewritten; and hoa-manager's
e2e hit `relation "users" does not exist` because the compose volume was empty
on first boot and Payload created the schema during that same failing run.

Two consumers needed work beyond the installer to pass their own gate, both
about `docs/repomix-map.md` and resolved differently because the two repos
generate it differently:

- **loadsmith** embeds file bodies, and the refresh changed
  `docs/SD_AI_COMMAND_PACK.md` under its `docs/**` include, so the freshness
  gate failed. Regenerating would have satisfied it and been wrong: that payload
  is installed, not authored. Excluded from `scripts/update_repomix` *and* from
  `is_repomix_input_path` in `scripts/check_review_readiness.sh` -- they have to
  agree, or a refresh reports the map stale and regenerating changes nothing.
  The map lost 2,338 lines, none of them loadsmith's code, and blockers fell
  50 to 23. This is design D3a's exclusion, carried out.
  The exclusions are globs rather than exact paths: repomix writes its ignore
  list into the generated header, so naming `docs/SD_AI_COMMAND_PACK.md`
  exactly put a citation of it straight back into the map that excluding it had
  just removed.
- **hoa-manager** generates `--no-files`, a metadata listing. Regeneration was
  checked against the measurement rather than assumed: 34 blockers before, 34
  after, and the map itself contributes 0. Plain regeneration was correct there
  and no product change was made.

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
