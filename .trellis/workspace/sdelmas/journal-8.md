# Journal - sdelmas (Part 8)

> Continuation from `journal-7.md` (archived at ~2000 lines)
> Started: 2026-08-09

---



## Session 351: sd-status worktree inventory shipped: held branches and leaked worktrees visible

**Date**: 2026-08-09
**Task**: sd-status worktree inventory shipped: held branches and leaked worktrees visible
**Branch**: `main`

### Summary

Planned, implemented, and finished 08-07-status-worktree-invisibility (PR #393, merged 59912b94, v0.64.32; feature commit ad6b1279 carried the collector, tests, and task artifacts and is cited in prose because the journal-recovery window only accepts non-task-path commits). sd-status previously had zero worktree awareness: a local branch checked out in a linked worktree looked identical to a free one, and leaked worktrees never surfaced. The collector now enumerates `git worktree list --porcelain -z` (NUL-delimited; worktree paths are externally controlled and may contain newlines) through a pure raw-value parser (parse_worktree_porcelain) into an additive git.worktrees JSON block plus a derived git.branchesHeldElsewhere set, with a `==> Worktrees` human section (porcelain row order, `(reporting)` marker, explicit none/unavailable states) and a ` [worktree]` suffix on held branches. Cleanliness probes run `git --no-optional-locks status --porcelain` only after a git-common-dir identity check, so a stale path reused by an unrelated repository reports clean: null, never the stranger's state, and no probe writes a foreign index. Schema stays version 2 (additive-key precedent 7ba4d0c9). Planning went through the full adversarial contract: 3 host findings plus two Codex rounds (8 concerns round 1, 5 round 2 - `-z` parsing, no-optional-locks, refusal-set circularity/forced-duplicate scoping, current-row detection from linked worktrees, stale-path identity, receipt-modification coverage, fail-before vs regression-invariant classification), all remediated before task.py start. Copilot round 1 raised one valid finding (a worktree HEAD symref'd outside refs/heads/ would leak a non-branch ref into branchesHeldElsewhere) - fixed by intersecting with localBranches plus a symref regression test; round 2 clean. Backend spec's stale "schema version 1" claim corrected to 2.

### Main Changes

- templates/scripts/sd-ai-command-pack-status.py + root twin: parse_worktree_porcelain (pure NUL-record parser, raw values; sanitization only at serialization), collect_worktrees (unavailable shape on any enumeration failure; identity-checked --no-optional-locks probes; resolved --show-toplevel current-row detection with OSError raw fallback), collect_git wiring with localBranches-intersected branchesHeldElsewhere, render_local Worktrees section + held-branch marking
- tests/test_status.py: 13 new test methods - porcelain row parity, external checkout-refusal oracle (hooks neutralized, `already used by worktree` stderr match, finally-restore), explicit empty state, read-only invariant (sentinel receipt tree + per-worktree index bytes + worktree-list bytes), recovery-classifier independence, prunable-not-pruned, dirty worktree, PATH-stub unavailable inventory, adversarial -z parser input, >300-char-path integration probe, linked-worktree --repo invocation, stale-path-reuse guard, non-branch symref exclusion
- Spec: manifest-and-filesystem.md delegation section gained the worktree-inventory contract; stale "schema version 1" corrected to 2
- Docs: sd-status SKILL.md step-4 report list gained the worktree inventory; command-catalog surfaces regenerated
- Release: 0.64.32 manifests + changelog + candidate ledger via make release-prep

### Git Commits

| Hash | Message |
|------|---------|
| `398c8cb5` | chore(release): prepare 0.64.32 |
| `611308bd` | fix(status): scope branchesHeldElsewhere to local branch names |

### Testing

- [OK] Baseline classification against `git show HEAD:` pre-change collector: 10 behavioral test methods fail before / pass after; the 2 regression invariants (read-only, recovery independence) pass on both sides; template restored byte-identical after the check
- [OK] Full tests.test_status suite: 68 tests OK (67 pre-Copilot-fix, 68 after the symref regression test)
- [OK] make release-prep exit 0 (full maintainer check gate)
- [OK] PR #393 CI fully green on both pushes; Copilot round 2 clean; 0 unresolved threads at merge

### Status

[OK] **Completed**

### Next Steps

- Return to 08-07-status-housekeeping-anomaly-disagreement (T-1): its worktree-held axis is now real; first correct its PRD's stale claim that this dependency was already "(merged)" before this task existed


## Session 352: Ship thin-surface-partition child: four-category partition artifact

**Date**: 2026-08-09
**Task**: Ship thin-surface-partition child: four-category partition artifact
**Branch**: `main`

### Summary

Converged thin-surface-partition planning through round-3 adversarial review, implemented partition-surfaces.py with fail-closed classification of all 776 manifest rows into four categories (593/94/83/6), committed docs/fleet/surface-partition.json with drift gate and 26 tests, merged as PR #395. Also pinned trellis-implement agent to Opus with CI guard test (PR #394).

### Git Commits

| Hash | Message |
|------|---------|
| `a37c7085` | (see git log) |
| `0fc5a4a1` | (see git log) |
| `545322d0` | (see git log) |
| `c2f9cf69` | (see git log) |
| `cef5903f` | (see git log) |

### Status

[OK] **Completed**


## Session 353: Thin plugin packaging: Claude Code plugin, marketplace, review-coordinator rebuttal fix

**Date**: 2026-08-09
**Task**: Thin plugin packaging: Claude Code plugin, marketplace, review-coordinator rebuttal fix
**Branch**: `feat/thin-plugin-packaging`

### Summary

Shipped the Claude Code plugin generator, plugins/sd tree, marketplace catalog, release-chain wiring, and CI strict validation for task 08-09-thin-plugin-packaging on PR #400. Fixed two pre-existing review-coordinator defects blocking the local rebuttal flow (cached-state rerun swallow; outcome-only findings gate) and validated the fix live by converging the PR review with same-attempt rebuttals. Verified AC1 via headless --plugin-dir smoke in a payload-free repo.

### Main Changes

- Plugin generator .github/scripts/generate-plugin.py with six fail-closed conditions and justified bin literal allowlist
- Generated plugins/sd tree (84 files) plus .claude-plugin/marketplace.json catalog
- Release chain: plugin generation in make generate/release-prep, payload classifier extensions, CI pinned claude plugin validate --strict
- Review coordinator: apply --local-disposition on rerun of cached attempt; gate on receipt disposition outstanding with fail-closed empty-findings guard; phase-rewind guard
- Spec: Script Sibling Resolution contract subsection in manifest-and-filesystem.md


### Git Commits

| Hash | Message |
|------|---------|
| `10b9013c` | feat(scripts): own-location sibling resolution for pack scripts |
| `0d971228` | feat(plugin): Claude Code plugin generator, marketplace catalog, generated tree |
| `303f49e3` | feat(plugin): wire generator into make generate, lint lanes; add test suite |
| `994af6cf` | feat(release): plugin generation in release chain, payload gates, CI validate, docs |
| `5bea9185` | docs(spec): capture script sibling-resolution contract |
| `7beccf32` | fix(review): apply local-disposition reruns and gate on outstanding findings |

### Testing

- [OK] make test: 1721 tests across 62 modules, 0 failures
- [OK] tests.test_review_controller: 34 tests OK incl 6 rebuttal-flow tests
- [OK] claude plugin validate plugins/sd --strict exit 0; generate-plugin.py --check clean
- [OK] AC1 smoke: claude --plugin-dir plugins/sd in empty repo exposes 21 sd: commands/skills
- [OK] sd-review PR 400 converged ready at head 7beccf32 via same-attempt rebuttals

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 354: Machine-scope installer for non-Claude surfaces + unified update action

**Date**: 2026-08-09
**Task**: Machine-scope installer for non-Claude surfaces + unified update action
**Branch**: `feat/thin-machine-installer`

### Summary

Implemented task 08-09-thin-machine-installer through seven checked steps: executed per-surface platform probes flipping gemini/opencode/shared to non-provisional MACHINE (codex to REPO_NATIVE, shared retainVendoredFor codex+pi), machine-scope engine with plan-before-apply, intent journal, backup-recording receipts and digest-verified restore, shared reference rewrite serving plugin and machine payloads, install.py --machine, plugin bundling with bin/sd-machine-install bootstrap, sd-pack-update with fail-closed plugin resolution, sd-status machine skew line, spec/docs/release chain at v0.64.35. Rebased onto origin/main (0.64.34) before first push; PR #411 opened, local review clean after one rebutted gito finding; Copilot refused on diff size. Manual acceptance items remain outstanding for a human pass.

### Main Changes

- Machine-scope engine installer/machinescope.py: five destination families, plan-before-apply, conflict refusal, --force with receipt-recorded .bak backups, intent journal, receipt-trust fail-closed, remove with digest-verified restore
- Shared rewrite installer/references.py with residue/closure/wrapped-reference gates; installer/machinestage.py payload staging; install.py --machine
- generate-plugin.py bundles installer/, machine-payload/, partition.json, bin/sd-machine-install; 8 fail-closed conditions; payload digest parity
- partition-surfaces.py dispositions flipped on executed probes; retainVendoredFor with fail-closed retention validation; manifest 776 to 777 rows
- sd-pack-update script with 11-row fail-closed failure table; sd-status machineScope states none/installed/invalid/unavailable with separate current/skew/unknown comparison
- Spec: Machine-Scope Installer section in manifest-and-filesystem.md; CHANGELOG 0.64.35; fleet candidate ledger refreshed 8/8


### Git Commits

| Hash | Message |
|------|---------|
| `a5387fb8` | docs(task): planning artifacts for 08-09-thin-machine-installer |
| `3ba985df` | feat(partition): flip machine dispositions on executed probes, add retainVendoredFor |
| `473a2389` | feat(installer): machine-scope engine with intent journal and backup-recording receipts |
| `6d09999e` | fix(installer): report kept rows on install and correct forced-remove accounting |
| `c278105b` | feat(installer): shared reference rewrite, machine payload staging, install.py --machine |
| `6da4f707` | feat(plugin): bundle machine installer, payload, and bootstrap into plugins/sd |
| `459a7b71` | feat(update): sd-pack-update script with fail-closed plugin resolution and skew report |
| `9c22f1cf` | feat(status): machine-scope skew line in sd-status |
| `edd0a1b2` | docs(release): machine-scope installer spec, user docs, changelog 0.64.35, fleet ledger |
| `ea0cfbe9` | chore(generate): rebuild payloads and fleet ledger after rebase onto 0.64.34 |
| `1c5c07fc` | chore(task): record branch for 08-09-thin-machine-installer |

### Testing

- [OK] make test: 2014 tests, 0 failures, coverage floors met (machinescope.py 100%)
- [OK] make generate clean; generate-plugin.py --check passes; claude plugin validate --strict passes
- [OK] review preflight 0 failures; make release-prep exit 0 at 0.64.35
- [OK] sd-review scope=pr attempt 1: gito clean after one verified rebuttal (generator-owned _example scaffold); Copilot refused >20k lines (anomaly)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 355: Retire the sd-full-check and sd-review-local command surfaces

**Date**: 2026-08-10
**Task**: Retire the sd-full-check and sd-review-local command surfaces
**Branch**: `feat/retire-full-check-review-local-surfaces`

### Summary

Deleted both retired command surfaces (53 manifest rows), the legacy review-local.sh runner, the 23 SD_AI_COMMAND_PACK_REVIEW_LOCAL_* keys, and the four FULL_CHECK fallback readers, ahead of pack 0.65.0. Kept full-check.sh, review-local.py, and sd-review-pr, all owned by 08-09. Updated and merged four consumer repos first so the fleet candidate ledger validates against their default branches.

### Main Changes

- Deleted both skills, their .github/command-sources/ bodies, and every generated adapter across templates/ and the installed roots
- Deleted scripts/sd-ai-command-pack-review-local.sh from all four script trees and registered the 23 REVIEW_LOCAL configuration keys on the retired-surface row so a reintroduced reader fails the drift lint
- Added 59 bounded CommandSurfaceAllowance rows, each naming one identifier and one concrete path pattern, driving the drift lint from 490 findings to clean
- Merged four consumer PRs (rwbp-coordinator#205, rwbp-website#221, loadsmith#215, anomaly-metric-creator#365) removing their assertions and links to the retired surfaces, then refreshed the candidate ledger
- Captured two doc gates and one test-discovery blind spot in .trellis/spec/tooling/surface-retirement-doc-gates.md, and replaced the frontend spec's hand-maintained adapter inventory with runtime enumeration


### Git Commits

| Hash | Message |
|------|---------|
| `a49e4332` | refactor(skills): repoint local-gate references from sd-full-check to sd-check |
| `3bbeb8a5` | refactor(commands): remove the retired sd-full-check and sd-review-local surfaces |
| `957f55b5` | docs(pack): settle the retirement's doc classification and stale references |
| `966cae62` | docs(task): record the retirement's follow-ups and audit-finding owners |
| `005b1197` | docs(spec): capture the two doc gates that fire when a surface is retired |
| `de29c7ff` | fix(tests): drop the deleted test_review_local module from the install facade |
| `1719f9a6` | docs(spec): make the adapter scope list enumerate instead of drift |
| `fc0372b4` | chore(task): record the finalization branch on 07-24 |

### Testing

- [OK] .github/scripts/check-command-surface-drift.py: clean; 988 files scanned, 272 allowed historical occurrence(s)
- [OK] unittest discover -s tests -p 'test_*.py': Ran 1984 tests, OK (CI's exact command; the sharded runner skips the facade that broke)
- [OK] make check: exit 0; make sync: exit 0
- [OK] fleet-candidate-check.py: 8/8 consumers passed, ledger written
- [OK] uninstall proven against a real 0.64.35 install: unchanged vouched copies removed, modified copy preserved and reported, dirs pruned, zero retired paths in the 0.65.0 receipt
- [OK] reintroduction proven both ways: planted retired target reported by install-audit as unlisted pack-like; planted identifier and env key reported by the drift lint as retired_identifier_live and stale_configuration_key

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 356: Fleet/status rework to pin + plugin inventory

**Date**: 2026-08-10
**Task**: Fleet/status rework to pin + plugin inventory
**Branch**: `feat/thin-fleet-status-pins`

### Summary

Bumped the fleet registry to schema 5 with per-consumer install mode and pin path, and taught sd-status fleet to report a thin consumer by its pin plus machine skew instead of installed-tree drift.

### Main Changes

- Fleet registry schema 4 -> 5: optional per-consumer mode (fat|thin) and pinPath, both defaulted so an all-fat schema-5 registry reports identically to the schema-4 one it replaces
- sd-status fleet reports a thin consumer by pin state (present|absent|unreadable), collects machine scope once per run, and raises pin/machine/plugin skew rows gated on at least one thin consumer
- Fixed follow-up truncation: F-* rows now derive from the complete row set with skew ranked ahead of advisory rows, so a skew row can no longer vanish behind advisory rows
- Pin paths validated at load (no absolute, Windows-absolute, .., or whitespace-padded values) and contained at read with resolve(strict=True) + relative_to


### Git Commits

| Hash | Message |
|------|---------|
| `ad12cc442a1d31c0ee0bed8d5ba2e3298bbc8863` | feat(fleet): report thin consumers by pin and machine skew |
| `0f15197a05e4ed6cb48a923cdd7acbd8bb040544` | fix(fleet): strip pinPath before validating and returning it |
| `028cd4b5` | chore(task): record branch for 08-09-thin-fleet-status-pins |
| `252a4675` | chore(task): mark thin-fleet-status-pins acceptance criteria satisfied |

### Testing

- [OK] python -m unittest discover -s tests -p 'test_*.py' — 1994 tests, OK
- [OK] make generate && make sync && make release-prep — exit 0, 65 OK blocks, ledger refreshed to 0.66.0
- [OK] AC3 paired all-fat proof over the real 8-consumer fleet: 8 rows, 2 nextSteps, 2 followUps identical apart from the additive fields; mutation defeat case exits 1

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 357: Repoint thin consumers' surviving pack surfaces off removed paths

**Date**: 2026-08-11
**Task**: Repoint thin consumers' surviving pack surfaces off removed paths
**Branch**: `feat/thin-prompt-surface-repoint`

### Summary

A thin conversion deletes the vendored payload but keeps the repo-native slice, so seven pack-shipped surfaces survived still naming scripts/<name> and docs/SD_AI_COMMAND_PACK.md - 17 packDefects the resweep reports, blocking every consumer conversion. The fix is a third RewriteProfile applied at payload_source_bytes(), the single point where a target's installed bytes are decided, so source_digest, provenance, and the bytes on disk all derive from one value. The conversion-time mechanism the design originally approved was refuted by measurement: it made install.py --check report state: invalid with 'vouched target content drifted' and the next refresh exit 2.

### Main Changes

- Add THIN_PROFILE and apply it at the installer's single content seam, payload_source_bytes(), rather than as a pass that edits files after writing them. An after-the-fact edit desynchronizes the receipt from disk; measured, that is state: invalid on --check and rc 2 on the next refresh.
- Thread is_thin through _install_payload, install_file, and normalize_managed_block_template so one authored Copilot block has two emissions. Fat is byte-identical by construction: is_thin false is the untouched code path.
- Add planned_repoints() and repointed_provenance_files() to the conversion, because the receipt vouching for the kept files is written before they are. Most repo-native targets fall outside the residual payload (measured: 4 selected, 0 prompts), so their digests are carried forward from the fat receipt and need the overlay.
- Change the KB script's .gitignore banner to name the pack instead of its own path - one hit per consumer, and the block is regenerated only by the script, never by the installer.
- Write the two consumer-side conversion steps into child 3's per-consumer sequence: regenerate the KB block, and resweep the consumer's own PR template. Both are invisible in a diff that looks finished.
- Reconcile four acceptance criteria that described the superseded D1/D2/D4 mechanism, and move two fleet-scoped halves to children 3-5, which hold the consumer-mutation authorization this task does not.


### Git Commits

| Hash | Message |
|------|---------|
| `be05935a` | feat(installer): repoint thin consumers' repo-native surfaces |
| `ffde1653` | docs(thin): write the two conversion steps a diff cannot show |
| `49b676f4` | test(installer): assert both managed-block emissions on the real template |
| `1a66c2e0` | docs(thin): reconcile acceptance criteria to the D6 mechanism |
| `b927dd51` | chore(trellis): record the task's branch before finalization |
| `040b86ae` | chore(task): archive 08-10-thin-prompt-surface-repoint |

### Testing

- [OK] make test / make check: MAKE-TEST-EXIT=0, MAKE-CHECK-EXIT=0, coverage gate fail-under=100 satisfied
- [OK] Per-surface acceptance on a converted fixture, scored by the shipped resweep classifier: 17 fat hits, 0 thin, across all seven surfaces
- [OK] Freshly converted consumer: install.py --check rc 0 (state: current), refresh rc 0, repoint still in place, --check after refresh rc 0
- [OK] ManagedBlockEmissionTests against the real shipped template; mutation-tested, disabling the rewrite fails 5 subtests
- [OK] Criterion 4 negative case measured: a converted fixture carrying the previous KB banner keeps the hit, proving the KB step is load-bearing
- [OK] Copilot review clean at head 49b676f4; its one suppressed finding about untested thin managed-block emission was correct and is fixed

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 358: Stop shipping the Codex review lane to consumers

**Date**: 2026-08-11
**Task**: Stop shipping the Codex review lane to consumers
**Branch**: `feat/thin-undeclared-codex-marker`

### Summary

Resolved the undeclared codex usage packDefect blocking all eight consumers' thin conversions. Split the planning adversarial review contract: the 80-line host contract keeps shipping, the Codex lane moves to docs/planning-adversarial-review-codex.md with no manifest row and nothing under templates/. Conditional shipping under a platform codex row was implemented in full, then refused by three tested invariants encoding that a marker-less registered platform ships no files; the operator chose to stop shipping the lane instead of amending three gates.

### Main Changes

- Split templates/.claude/sd-ai-command-pack/planning-adversarial-review.md from 129 to 80 lines, reconciling six leftover lane references; the contract now states it is the whole review and names no second-lane file
- Moved the Codex lane to docs/planning-adversarial-review-codex.md -- unshipped by construction, pointed at from AGENTS.md so the link checker gates the reference
- Abandoned PRD option 5 after full implementation: test_platform_registry_derives_consistent_tables, test_manifest_declares_current_trellis_platform_adapters, and test_tracked_pack_targets_match_templates each forbid a manifest row for a platform with no Trellis markers; giving codex markers would auto-select it in all eight consumers and reinstate the defect
- Fixed docs/SD_AI_COMMAND_PACK.md, which installs always and still described the planning review launching a codex exec peer lane -- found by Copilot as a suppressed comment, missed by my own sweep because it was scoped to edited files rather than every shipped surface naming the lane
- Recorded the constraint as a forbidden pattern in .trellis/spec/backend/manifest-and-filesystem.md with both correct alternatives
- Version 0.68.0 with matching CHANGELOG entry; no new manifest row, 724 files unchanged


### Git Commits

| Hash | Message |
|------|---------|
| `caf010c0` | docs(trellis): converge planning for 08-11-thin-undeclared-codex-marker |
| `70eb2017` | feat: stop shipping the Codex review lane to consumers |
| `d72737e9` | docs: record the marker-less-platform manifest constraint in spec |
| `792775fe` | fix: address Copilot review on the contract split |
| `a281da84` | fix: stop the shipped guide describing the planning Codex lane |
| `16547f3d` | docs(trellis): close acceptance criteria against measured evidence |

### Testing

- [OK] make test exit 0, 74 OK groups
- [OK] make check exit 0, release changelog gate and candidate ledger both valid
- [OK] resweep detector: three shipped surfaces FIRE [], unshipped appendix FIRES [24] -- the probe has bite
- [OK] tests/test_claude_planning_review.py 6/6, including test_appendix_is_absent_from_the_shipped_payload asserting no manifest row and no templates/ copy
- [OK] Copilot rounds 1-3: three findings verified and fixed, one suppressed finding acted on, 0 unresolved threads

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 359: Bind the candidate validator's own sources into the candidate ledger

**Date**: 2026-08-11
**Task**: Bind the candidate validator's own sources into the candidate ledger
**Branch**: `feat/candidate-validator-digest`

### Summary

make release-prep skipped fleet validation whenever the candidate ledger read as current, and ledger currency could not see the validator itself: scripts/sd-ai-command-pack-fleet-candidate-check.py has no manifest row and no templates/ twin, so editing it moved no payload source. A fourth binding, validatorDigest (schema 2 -> 3), closes that reachability gap; the digest takes a caller-supplied loader so a ledger recorded at a commit is paired with that commit's blobs rather than the working tree.

### Main Changes

- Added CANDIDATE_VALIDATOR_SOURCES and the candidate_validator_digest / filesystem_candidate_validator_digest pair to the authoritative template fleet_lib, bumped CANDIDATE_LEDGER_SCHEMA_VERSION to 3, and made expected_validator_digest a required keyword argument of validate_candidate_ledger
- Wired the digest through all three production call sites, including verify_candidate_ledger_at_commit, which reads its expected digest from the same commit as its ledger
- Excluded fleet_lib from the tuple deliberately: its manifest row's source is its templates/ twin, so payloadDigest already moves; naming it would hash the make sync mirror instead
- Excluded the executable bit, unlike payload_digest: the validator is invoked as sys.executable <path>, so chmod +x must not invalidate a byte-identical ledger
- Review round 1 (Copilot): the commit-scoped loader flattened six distinct tree-load failures into 'candidate validator source is absent'. Fixed by threading a subject through normalize_tree_path and payload_source_at_commit rather than re-wrapping at the call site, so each failure keeps its own reason
- Review round 2 (Copilot): removed an unreachable except FleetConfigError copied from payload_digest_at_commit, where it is live because payload_digest parses the manifest
- Recorded the mechanism, the loader seam, the executable-bit asymmetry, and the rename-the-subject rule in the manifest-and-filesystem code-spec; documented the new binding in docs/FLEET_ROLLOUT.md


### Git Commits

| Hash | Message |
|------|---------|
| `ff82e490` | feat: make release-prep reach a changed candidate validator |
| `9e8fead2` | fix: name the validator subject at each tree-load raise |
| `36e1958b` | fix: drop an unreachable FleetConfigError handler |
| `adcbe2ad` | chore: record the task branch before finalization |

### Testing

- [OK] Gate 2 end to end: one comment appended to the validator moved exactly one ledger field (validatorDigest), with packVersion, payloadDigest, and fleetManifestDigest byte-identical; release-prep then ran all 8 consumers instead of printing the skip
- [OK] Gate 3: a second release-prep on an unchanged tree printed 'candidate ledger is current; skipping fleet validation', exit 0
- [OK] Mutation testing over the digest comparison: 3 mutants, all killed (7/7/5 failures); a 4th mutant over the review fix reproduced the exact misreport the reviewer described
- [OK] Full suite: Ran 2378 tests, OK
- [OK] make check exit 0; review preflight 0 failures, 3 dispositioned warnings

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 360: Rescope the candidate validator loop to the thin shape

**Date**: 2026-08-11
**Task**: Rescope the candidate validator loop to the thin shape
**Branch**: `feat/thin-candidate-loop-shape`

### Summary

Rescoped the full-fleet candidate validator to exercise the thin install shape: a run-once pack-side artifact lane, per-consumer lane selection driven by the clone's recorded pin state, and a three-value candidate status whose blocked rows must carry reasons. Two design defects were found and corrected during implementation, and a Copilot review finding was fixed before merge.

### Main Changes

- Added a run-once thin artifact lane (plugin build and drift check, plugin manifest validation, machine install into a scratch prefix) whose failure is pack-owned and blamed on no consumer
- Selected the per-consumer lane from the clone's recorded pin state rather than the registry's declared mode, so the documented conversion skew is a note rather than an error
- Redirected HOME to the artifact lane's scratch machine install for the thin lane only, so a thin consumer's ~/.agents lookups resolve to the candidate under test instead of whatever pack the runner has installed
- Introduced three-value consumer status (passed / failed / blocked) where blocked requires non-empty reasons, and bumped the candidate ledger schema to v4
- C-11: corrected packDefects, which was a pre-rewrite count the resweep never rewrote; residue surviving check_text_residue after the conversion's own rewrite is the only real evidence of a pack-owned defect
- C-12: moved the resweep after the install and onto a committed clone; against a pristine clone it measured the previous release rather than the candidate
- Fixed the Copilot review finding: main() now skips consumer validation entirely when the artifact lane fails, instead of paying a clone and install per consumer to produce failed rows caused by the missing machine_home
- Captured the durable contract in .trellis/spec/backend/manifest-and-filesystem.md and released the change as 0.70.0


### Git Commits

| Hash | Message |
|------|---------|
| `686d077e` | docs(trellis): plan the thin candidate loop rescope |
| `da292873` | feat(fleet): validate the thin shape in the candidate loop |
| `0e86e0a8` | fix(fleet): measure pack defects after the rewrite, and resweep the installed clone |
| `3f45751f` | test(fleet): cover the thin candidate lane and its three-value status |
| `e7c90d23` | feat(fleet): release the thin candidate loop shape as 0.70.0 |
| `c71ac33b` | fix(fleet): skip consumer validation when the artifact lane fails |

### Testing

- [OK] .venv/bin/python -m unittest tests.test_fleet_candidate — 24 tests, OK, exit 0
- [OK] Four mutations, each caught by the test guarding its rule, each reverted with the tree verified clean
- [OK] make check — exit 0
- [OK] make release-prep — exit 0, manifest version 0.69.0 -> 0.70.0 with a matching changelog heading
- [OK] Full-fleet validator at HEAD — exit 0; 3 passed artifact steps, all 8 consumers blocked
- [OK] git diff --exit-code docs/fleet/consumers.json — clean, proving registry byte-identity across both lanes
- [OK] Gate 3: a broken build_files makes the validator exit 1 and make release-prep exit 2; reverted, generate-plugin.py --check exit 0
- [OK] sd-review scope=pr attempts 1 and 2 — status ready, 8 deterministic checks passed, local provider clean

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 361: File the layout-aware guard task from the fleet sizing

**Date**: 2026-08-11
**Task**: File the layout-aware guard task from the fleet sizing
**Branch**: `docs/layout-aware-guard-task-v2`

### Summary

Recorded the follow-up task from the 08-11-thin-candidate-loop-shape iteration's fleet sizing: five consumers each reimplemented the same pack-layout guard, and those scripts plus the tests pinning them carry 330 of the fleet's 510 thin-conversion blockers. The task ships one pack-owned replacement so each of those five ports becomes a delete.

### Main Changes

- Filed 08-11-pack-layout-aware-guard with the per-consumer and per-category blocker tables, the five named bespoke guards, and acceptance criteria that require reading all five before designing the replacement surface
- Curated both spec manifests with real entries instead of the generated _example scaffold, so the task dispatches with spec context
- Kept the task standalone: a declared parent, or an exact ID citation in the PRD, links the in_progress thin-deployment umbrella into the branch's planning closure, which the finalization gate refuses in both directions


### Git Commits

| Hash | Message |
|------|---------|
| `4f8ee61c` | docs(task): file the layout-aware guard task from the fleet sizing |

### Testing

- [OK] node scripts/sd-ai-command-pack-review-preflight.mjs — 0 failures, 0 warnings

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 362: Give shipped if-not-exists defaults a delivery path

**Date**: 2026-08-11
**Task**: Give shipped if-not-exists defaults a delivery path
**Branch**: `feat/provider-config-digest-history`

### Summary

Shipped a release-generated digest history so install.py can tell a stale shipped default from a customized file, refreshed the former, and made the population visible from both the consumer audit and sd-status fleet.

### Main Changes

- Added .github/scripts/generate-provider-config-history.py: seeds each if-not-exists source from the git log's own raw blob ids (rename-proof), refuses on a shallow clone, only ever appends, and runs before the self-sync install so the root docs/ copy comes from the install.
- Added installer/providerhistory.py and installer/fileops.is_previously_shipped_default, gating a new InstallStatus.REFRESHED that is vouched like any written file and is not gated on --force; every unreadable history resolves to preserved with a named reason.
- Taught the install audit and sd-status fleet to classify each consumer's if-not-exists configs as current, superseded, locally owned, or unknown, with a fleet step for the unknown case.
- Corrected design.md and implement.md where implementation refuted them: FORCE_PRESERVED_TARGETS is not a second population (excluding it made the feature inert), the artifact gained an explicit current field, and the symlink path stays PRESERVED deliberately.
- Filed 08-11-convert-fleet-provider-configs for the consumer conversion, which needs per-cohort authorization the autonomous loop does not hold.


### Git Commits

| Hash | Message |
|------|---------|
| `62176532` | feat(installer): give shipped if-not-exists defaults a delivery path |
| `9a324fd8` | fix: keep every unreadable provider-config input visible |
| `34c12e38` | fix: stop three provider-config paths from misnaming what they saw |
| `450c0a95` | fix: refuse malformed provider-config entries instead of dropping them |
| `140fd8ee` | chore(task): record branch for 08-06-fleet-provider-config-propagation |
| `21570ac5` | docs(task): record acceptance evidence and file the conversion follow-up |

### Testing

- [OK] make check exit 0 and make release-prep exit 0 at pack version 0.71.0
- [OK] Scratch consumer: both configs refreshed to byte-identical from the oldest recorded blob; both preserved byte-unchanged once customized
- [OK] Consumer-side audit reproduced both states: superseded shipped default, and matches no template this pack has shipped
- [OK] sd-status fleet --no-network across eight consumers: .gito 8/8 superseded; .prism one current, one superseded, six locally owned
- [OK] tests/test_provider_config_history.py 22 tests OK; three Copilot review rounds, all findings addressed and threads resolved

### Status

[OK] **Completed**

### Next Steps

- None - task complete
