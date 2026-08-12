# Planning adversarial review — 08-11-thin-candidate-loop-shape

Contract: `.claude/rules/sd-planning-adversarial-review.md`. Edit batch under
review: `design.md` and `implement.md`, both created this run (no pre-edit
content hash — neither file existed). `prd.md` unchanged by this run; reviewed
for cross-artifact consistency only.

Lane: host review. Rounds: 2 (round 1 found six concerns, round 2 swept the
edited set for residual contradictions and found four). Convergence limit of
three rounds not reached.

## Round 1

| ID | Concern | Verdict | Disposition |
| --- | --- | --- | --- |
| C-5 | `design.md` asserted "every consumer still reads `mode: fat` — all eight" | **confirmed defect** | Fixed. No record carries a `mode` key; the earlier verification used `c.get("mode", "fat")`, which supplied the default and hid it. Rewritten to state the measured key set, and the conclusion re-derived (it is strengthened, not weakened). |
| C-6 | D5's `claude --plugin-dir` load smoke | **confirmed defect, blocking** | Fixed. Measured: `claude --plugin-dir /nonexistent/plugin/path -p "say ok"` prints `ok`, exit 0. It cannot fail, needs a billable model call, and its own help scopes it to a session. Replaced with `generate-plugin.py --check`. Deviation from PRD requirement 1 recorded, and a PRD amendment added to Step 0 as a precondition of `task.py start`. |
| C-7 | Two consumers' `candidateChecks` invoke pack-owned scripts by repo-relative path | **confirmed gap** | Fixed. `se-ai-command-pack` and `rwbp-website` name manifest-declared `scripts/` targets; the `agents-bin` family relocates those to `<home>/.agents/bin` on conversion. New D6 classifies this as `blocked` with a reason, not `failed`. Step 3 + Step 4 test added. |
| C-8 | `command_environment` does not set `HOME` | **confirmed gap** | Fixed. A thin consumer's `~/.agents/bin` lookups would resolve to the invoking machine's installed pack, certifying someone else's release. New D7 sets `HOME=<work_root>/home` for the thin lane only, reusing D5's machine install. Mechanism measured (`Path.home()` honors `HOME`). Test asserts both halves. |
| C-9 | `prd.md` line citations predate 0.69.0 | **confirmed** | Scheduled. PRD cites `fleet-candidate-check.py:502` / `fleet_lib.py:829`; actual are `:520` / `:902-906`. `prd.md` is outside this edit batch, so the correction is a Step 0 amendment rather than an edit here. `design.md`'s own `:519` was also off by one and is corrected to `:520`. |
| C-10 | `packDefects` attributed per consumer though pack-owned | **refuted** | No change. The resweep scans *that consumer's* tree for citations of removed pack paths, so the count varies with which surfaces the consumer vendors — the 2026-08-10 scan measured a 15-17 spread, not a constant. Collapsing to one run-level failure would discard which consumer surfaces the defect. Reasoning recorded in D4. |

## Round 2 — residual contradictions in the edited set

All four introduced by the round-1 edits or newly visible because of them.

- D1's concern text still claimed an "all eight still `fat`" property. Restated
  as registry byte-stability.
- D1's prose and its Correct block still said the loop reads `mode` to choose a
  lane, contradicting D3's pin-not-registry rule. Both corrected.
- The lane summary still listed "smoke" as the third step. Now "drift-check".
- `implement.md`'s gate-2 expectation and `prd.md:97`'s acceptance criterion 2
  both still named eight `fat` entries. The former is fixed; the latter is
  `prd.md`, so it joins the Step 0 amendment list — as written it is untickable.

## Blocking concerns outstanding

None for the artifacts under review. One **precondition** carries forward: the
Step 0 `prd.md` amendment (C-6, C-9, and criterion 2) must land before
`task.py start`, because two acceptance criteria as currently written cannot be
satisfied by any correct implementation.

## Post-start corrections (implementation phase)

Recorded here for continuity, not as a fourth review round. Both were found by
measurement after `task.py start`, so they are implementation findings against
the shipped design rather than planning concerns against an unapproved batch.
`design.md` and `implement.md` are amended in place, each amendment labelled.

| ID | Finding | Verdict | Disposition |
| --- | --- | --- | --- |
| C-11 | D4's `packDefects > 0` rule measured the wrong thing | **confirmed defect** | `packDefects` is a *pre-rewrite* count and `THIN_PROFILE` repoints exactly those citations at conversion time. Measured: `check_text_residue` over every flagged file, here and in the real `sd-github-review` checkout, reports 0 with residue. The rule is now residue **after** `rewrite_text`, implemented as `surviving_pack_defects`. Acting on the raw count would have hardcoded `~/.agents/bin` into prose fat consumers read. Step 2b, added on the wrong reading, was withdrawn before any file was edited. |
| C-12 | D2's "resweep the pristine clone before any install" measured the previous release | **confirmed defect** | A pristine clone carries whatever pack that consumer last installed. Measured: `sd-github-review`'s vendored `planning-adversarial-review.md` still invoked the `codex` CLI, a defect this pack had already removed, and the candidate was failed for it. The resweep now runs after the install, on a clone where the install has been committed. Blocker counts fell on five consumers once the ordering was fixed. |

C-12 was found *because* C-11 forced a re-reading of the same code path; the
second defect was invisible while the first was believed.
