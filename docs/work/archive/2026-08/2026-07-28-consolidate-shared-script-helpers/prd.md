---
title: Consolidate duplicated script helpers into the shared library
status: done
created: 2026-07-28
---
# Consolidate duplicated script helpers into the shared library

## Goal

Collapse four separate duplication clusters into `scripts/sd_ai_command_pack_lib.py`, so each contract has one owner and divergence between copies stops being possible.

## Requirements

- **State root (A-046):** move `STATE_HOME_ENV`, `resolve_state_root`, and `ensure_private_directory` into the shared lib with one blocked-write contract. Callers keep only their subdirectory name. Four current copies: work-loop.py:295, recovery-artifacts.py:123, fleet-timing.py:371, fleet-controller.py:212 — and they disagree on which env vars they honor.
- **Git invocation (A-076):** migrate the three lib-bypassing callers (work-loop.py:202, review-local.py:541, surface-check.py:124) onto the lib's `run_git`, then collapse the five delegating adapters to two lib shapes with a per-script error adapter passed via `context=`.
- **Cache-env contract (A-080):** have cache-env emit the key set as data that shell validates generically, replacing the hard-coded key lists at shell-lib.sh:194, toolchain.sh:425, and the partial copy in the doctor heredoc at toolchain.sh:308, plus the magic arity assertions (shell-lib.sh:210 asserts `-ne 7`, toolchain.sh:435 asserts `-eq 7`).
- **Atomic write (A-085):** move the hardened `atomic_write_text` (review-learnings.py:290 — cross-device guard, directory fsync, TOCTOU re-check) and `default_text_file_mode` into the lib and delete the two unhardened copies at record-session.py:71 and update-spec-kb.py:393.
- All four sub-changes must preserve existing `environment_blocked` evidence behavior.

## Acceptance Criteria

- [x] With `SD_AI_COMMAND_PACK_STATE_HOME` set, work-loop and fleet state resolve to the same root (today they diverge).
- [x] Adding an eighth cache variable requires no shell-side edit.
- [x] Session receipts and the KB write through the hardened atomic writer.
- [x] No script constructs a git environment outside the lib.
- [x] `make check` passes.

## Notes

- Source: `.trellis/audit/report-2026-07-28.md` — finding A-046 (P2 · M · state root), A-076 (P2 · M · git interfaces), A-080 (P2 · S · cache-env contract), A-085 (P2 · S · atomic write).
- The sub-changes are independent and can land as separate commits in this order: A-085 (smallest), A-080, A-046, A-076.
- `recovery-artifacts.py:119` already documents its own copy as "mirrors the work-loop patterns", and its twin at :155 lets raw `OSError` escape where the original raises `StatePersistenceError` with evidence.
- Cross-ref A-013 (fixed): the shared lib did land and five sites adopt it. This is the residue, not a regression of that fix.
- Related but out of scope: A-047 (exec_module cross-script imports) and A-081 (`run_command`'s hidden mkdir) — both touch the same lib and may be worth sequencing after this.
- **Citation corrections, re-derived 2026-07-28.** All four findings are P2, so the audit's citations were unverified pointers. Three of the four enumerations above are wrong:
  - **A-046:** `fleet-controller.py:212` is not a fourth copy of `resolve_state_root`. It is `default_state_home()` — different signature, no absolute-path validation, no Windows branch, `/fleet-campaigns` baked into the root. And the divergence is sharper than "disagree on which env vars they honor": `fleet-timing.py:371` and `fleet-controller.py:212` **do not honor `SD_AI_COMMAND_PACK_STATE_HOME` at all**. Only `work-loop.py:38` and `recovery-artifacts.py:49` define `STATE_HOME_ENV`.
  - **A-076:** there are **three** delegating adapters, not five — `record-session.py:102`, `pr-body-scope.py:277`, `review-learnings.py:992`. Exactly three files import `run_git as run_git_command`. `audit-route.py`, `fleet-review-classify.py`, and `recovery-artifacts.py` call the lib's `run_git` directly in list form and need no change; counting them produced "five".
  - **A-080:** the key set is written out **seven** times, not three — the two shell `case` globs plus `toolchain.sh:308`, `:362`, `:401-408` and both lib copies (`:38-45`, `:47-54`). AC2 is not reachable by converting only the three sites named above.
  - **A-085 is accurate** on the three copies, but the hardening delta is **two** mechanisms, not three: cross-device guard and directory fsync. The symlink refusal and file-level `os.fsync` are already in all three copies.
- **A-046 is a state relocation, not a refactor.** Because two of the four sites ignore `SD_AI_COMMAND_PACK_STATE_HOME` today, unifying them **moves** live fleet timing records and campaign state for any user who sets it. Old state is orphaned, not migrated. AC1 asks for exactly this convergence, so the change is intended — but the migration is unspecified. `design.md` offers read-through fallback or a documented one-time move; one must be chosen before implementation.
- **A-076 must not change git error policy.** `work-loop.py:202` returns `str | None` and never raises — every `OSError`, `UnicodeError`, `TimeoutExpired`, and non-zero exit becomes `None` — and roughly ten call sites read that `None` as "unavailable". It also uses `errors="strict"` where the lib defaults to `errors="replace"`, so migrating naively turns non-UTF-8 git output from "unavailable" into parsed mojibake. It keeps a local swallowing adapter over the lib call; rewriting those ten sites is a separate task.
- Created from the 2026-07-28 repo audit with explicit user consent via the `audit.followups` decision. Planning complete 2026-07-28: `design.md` and `implement.md` added.
- **Acceptance verified 2026-08-06.** Every criterion held against the tree, but the work reached `main` through two routes, not one. Commits 1 and 2 (A-085, A-080) shipped under this task. Commits 3 and 4 were split out mid-implementation — `implement.md:211` records why — into `08-05-consolidate-state-root-resolution` (A-046, owning AC1) and `08-05-consolidate-git-invocation` (A-076, owning AC4); both are themselves `completed` and archived under `.trellis/tasks/archive/2026-08/`. So this task was left `in_progress` with nothing outstanding: its own two commits had shipped and its other two criteria were satisfied by the tasks that inherited them. Each criterion was checked against the tree rather than against commit messages, because one message-grep match (`A-046` in `dde46efd`) was a stale cross-reference from a later task's body, not the implementing commit:
  - AC1 — `resolve_state_root` lives at `sd_ai_command_pack_lib.py:248`, and all four callers reach it: `work-loop.py:37`, `recovery-artifacts.py:53`, `fleet-timing.py:34`, `fleet-controller.py:32`. No `def resolve_state_root`, `def default_state_home`, or module-level `STATE_HOME_ENV` survives outside the lib, so the two sites that previously ignored the env var can no longer diverge.
  - AC2 — the shell no longer carries a key list or an arity assertion. `-ne 7` and `-eq 7` are both gone from `shell-lib.sh` and `toolchain.sh`; the only remaining mentions of `CACHE_ENV_KEYS` are comments naming the lib as the authority (`shell-lib.sh:191`, `toolchain.sh:306`, `:430`).
  - AC3 — `record-session.py:207` and `update-spec-kb.py:562`, `:1235`, `:1239` all call the lib's `atomic_write_text`.
  - AC4 — a repo-wide grep for a git subprocess constructed outside the lib (`subprocess.(run|Popen|check_output)` on a `git` argv) matches **0** files across `scripts/*.py` and `.github/scripts/*.py`.
  - AC5 — `make check` exits 0: 66, 103, 132, and 85 tests across four suites, all `OK`; `Review preflight: 0 failure(s), 0 warning(s)`.
- The install audit still emits eight `legacy pack reference remains` warnings (`TRELLIS_REVIEW_PR_PACK.md`, `sd-refresh-specs`, `trellis-review-pr`, and two retired script names, across `.trellis/spec/backend/manifest-and-filesystem.md`, `tests/install_test_support.py`, `tests/test_install_audit.py`, `tests/test_review_preflight.py`). They are warnings, not failures, predate this task, and are out of its scope — worth a separate task rather than a silent fix here.
