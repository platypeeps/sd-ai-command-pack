# Planning adversarial review — 08-20-retire-pre-0616-trellis-compat

Contract: `.claude/sd-ai-command-pack/planning-adversarial-review.md`.

## 1. Trigger and baseline

| Artifact | Before | After |
|---|---|---|
| `prd.md` | existed (`task.py create` seed) | materially rewritten |
| `design.md` | absent | new |
| `implement.md` | absent | new |

Trigger applies: all three are new or materially changed in one coherent batch.

## 2. Lanes

Host lane only. This repository defines no additional independent lane, so none
is reported as skipped. The host lane was held to the two-lane standard per §2.

## 3. Concern ledger

| ID | Severity | Concern | Evidence | Disposition |
|---|---|---|---|---|
| C-1 | **Blocking** | `implement.md` omitted the shipped-payload release obligations. This task edits `templates/scripts/*.py`, `templates/scripts/*.mjs`, and `templates/.agents/skills/sd-fleet-refresh/SKILL.md`, all shipped payload, which requires a `manifest.json` bump, a matching top `CHANGELOG.md` heading, and a refreshed `docs/fleet/candidate-validation.json`. | CONTRIBUTING "Release And Payload Rules"; `.github/workflows/tests.yml:641-662` runs `run_pack_source_drift_gates` and feeds `CI Result` | **addressed** — new `implement.md` §7b, gate in §8, acceptance criterion in `prd.md` |
| C-2 | Medium | R6 might have no `versions` payload for a fleet row, making the Trellis version unprintable. | `scripts/sd-ai-command-pack-status.py:4114-4120`: `local = item.get("report")` guards with `continue`; `versions = local["versions"]` sits inside that branch and precedes the thin/fat split, so it is available to both | **rebutted** — no change |
| C-3 | Low | `design.md` said the wrapper "no longer passes `--commit-subject`", implying removal of something never present. | `templates/scripts/sd-ai-command-pack-record-session.py:495-510` builds the command with `--title --summary --content-file --no-commit [--commit] [--branch]` only | **addressed** — `design.md` R3 reworded |
| C-4 | Medium | Deleting the commit-row loop would also delete a real integrity check ("runtime dropped a commit"), which is not version-compatibility machinery. | The loop returns `missing commit table row for <hash>` before any write | **addressed** — `design.md` R3 and `implement.md` §3 keep a presence assertion; parameter narrowed to the hash list |
| C-5 | Low | `prd.md` acceptance and `implement.md` V2 stated the same grep two different ways (different pattern, different argument order). | Cross-artifact sweep per contract §2 | **addressed** — reconciled to one form |
| C-6 | Low | A baseline was recorded for `test_record_session` but not for `test_status`, which the plan also edits. | `implement.md` §5, §8 | **addressed** — second baseline added as a pre-edit checkbox |
| C-7 | **Blocking** | The floor was stated as `>=0.6.16`. `0.6.16-sd.7` carries a prerelease segment and therefore sorts *below* `0.6.16` under semver, so that rule would classify all nine converged repositories as non-compliant — inverting the task's own premise. | semver prerelease ordering; `.trellis/.version` = `0.6.16-sd.7` in all nine checkouts | **addressed** — floor restated as an identity in `prd.md` R1, `design.md` R1, `implement.md` §1, and `task.json`; the semver trap is now spec content rather than a silent assumption |
| C-8 | Low | Parked task `07-09` cites `tests/install_test_support.py:457`; the asserted string is at `:641`. | `git grep -n "trellis@latest"` | **addressed** — correction folded into `implement.md` §6 |
| C-9 | Low | `design.md`'s escaping table asserted rendered escape sequences that are ambiguous in Markdown and overstated the pipe difference (both escape pipes identically). | `escape_markdown_cell` vs `subject.replace("|", "\\|")` | **addressed** — table restated by property, not by rendered literal |

No concern is parked. No concern is unresolved.

## 4. Convergence

Round 1: C-1 … C-9 raised and dispositioned.

Round 2 (cross-artifact sweep): the C-7 remediation itself left `>=0.6.16`
standing in three further places — `implement.md:15` and `task.json.description`
were genuinely stale, while `prd.md:89` and `design.md:36` cite the string
deliberately as the rule *not* to adopt. This is the exact failure shape the
contract predicts for a corrected value. Both stale copies were repaired and
re-verified by search rather than by re-reading.

Repairing `task.json` surfaced a runtime footgun worth recording:
`task.py set-meta <dir> description <text>` reports success but writes
`meta.description`, leaving the first-class `description` field untouched — a
shadow copy in a different namespace. There is no `set-description` subcommand,
so the record was repaired directly and the stray key removed. Verified after:
`task.py validate` → `All validations passed`; `current --json` → `stale: false`,
`base_branch: main`; JSON diff against the pre-edit backup shows only the two
intended changes.

Two rounds used; the third automatic round was not needed.

## 5. Completion

- Changed artifacts: `prd.md`, `design.md`, `implement.md`, plus `task.json`
  metadata repair.
- Host review: completed, two rounds.
- Concerns: 9 raised — 8 addressed, 1 rebutted (C-2), 0 parked, 0 unresolved.
- Implementation: **unblocked**.
