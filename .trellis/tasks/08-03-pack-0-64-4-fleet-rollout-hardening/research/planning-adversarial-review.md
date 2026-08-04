# Planning adversarial review — 0.64.4 fleet-rollout hardening

Contract: `.claude/sd-ai-command-pack/planning-adversarial-review.md`. Triggered by
new/materially-changed `prd.md`, `design.md`, `implement.md` for task
`08-03-pack-0-64-4-fleet-rollout-hardening`.

## Lanes run

- **Host review** (this agent): full read of prd/design/implement + cross-artifact
  consistency + tree grounding. 8 concerns.
- **Codex CLI lane** (`codex exec --cd <root> --sandbox read-only --ephemeral`,
  read-only): exit 0. 7 findings; verdict "Planning is not ready to activate …
  six implementation blockers". No files written, no tests run.

Both lanes independently reached the same verdict and overlap on every material
concern. Codex confirmed the ownership classification (TRELLIS-upstream vs
PACK-shippable) as "substantially correct".

## Tree grounding (claims verified this run)

- the consumer-side `update_repomix` and `docs/repomix-map.md` are ABSENT in this checkout →
  this repo is NOT repomix-indexed (breaks implement.md Phase B "run against THIS
  repo (repomix-indexed)").
- `sd-ai-command-pack` is NOT in `docs/fleet/consumers.json` → the PRD
  "self-hosting: this repo is itself consumer sd-ai-command-pack" is false.
- `templates/scripts/sd-ai-command-pack-record-session.py` EXISTS → the pack already
  ships a real-subject compensating control for finding #4 (reuse, don't re-invent).
- Source findings doc = 13 numbered findings (#1-8, #10-13, #9), no #14 → "14
  findings" is a miscount.

## Merged concern ledger (host ∪ Codex, deduplicated)

| ID | Sev | Source | Concern | Disposition |
|----|-----|--------|---------|-------------|
| C-1 | BLOCKING (traceability) | host C-1 + Codex #7 | Count "14" wrong (actually 13); source doc lived in gitignored scratchpad, unverifiable from checkout. | **ADDRESSED** — count → 13 in prd/design/task.json; source doc copied to `research/pack-followups-0.64.4.md` (tracked, authoritative); PRD declared authoritative restatement. |
| C-2 | BLOCKING (factual) | host C-2 + Codex #3 | "this repo is itself consumer sd-ai-command-pack in the fleet" — false; not in consumers.json. | **ADDRESSED** — constraint corrected: this repo is the pack SOURCE (excluded alias, canonical pack); checks must pass here as the source build, not as a fleet consumer. |
| C-3 | BLOCKING (coverage) | host C-3 + Codex #3,#5 | AC1.a unconditional but undeliverable by pack; AC1.c/AC2.c/AC5.b missing implement steps; AC-R3 reduced to one consumer; task.json links only C7 while PRD declares C1-C8 children + "parent not implementation target". | **ADDRESSED** — AC1.a re-scoped Trellis-upstream-only (satisfied by filed upstream note); AC1.c/AC2.c/AC5.b added to execution; AC-R3 restated (repomix + non-repomix consumer); topology reconciled: parent IS the single-branch implementation target, clusters ship as per-cluster commits, only C7 is a pre-existing linked child. |
| C-4 | CRITICAL (integrity) | host C-4 + Codex #1 | C4a `resume --relink-pr` mutates `lane["head"]/["prNumber"]` directly → fails `validate_state` (fleet-controller.py:690) AND could let forged evidence redefine the expected publication epoch (guards at 1182 compare against mutable lane values). | **DESCOPED / PARKED** — removed from 0.64.4. Recovery stays the proven fresh-campaign redo (4× proven, documented). Filed as follow-up needing a typed recovery record (old/new PR+head, provenance, reset to pr-publication, head advances only on new receipt, misuse + persisted-state tests). No unsafe invariant change ships. |
| C-5 | BLOCKING (failure-safety) | host C-5 + Codex #4 | C2 publish helper: implement.md validates against THIS repo (NOT repomix-indexed); scratch `publish-lane3.sh` is not a tree file; move-simulate has no transactional restore/trap, no cleanliness/ownership precondition, no output-path allowlist. | **ADDRESSED** — validation target changed to an actual repomix consumer clone (consumers.json declares them); design gains a failure-safety subsection (trap/finally restore, preconditions, allowlist); #4 subject reuses the existing `record-session.py` wrapper; publish-lane3 noted as scratch-to-port. |
| C-6 | BLOCKING (correctness) | host C-6 + Codex #6 | implement.md cites `python3 -m pytest`; real runner is `.venv/bin/python -m unittest` / `make test` / `make check`; `.venv/bin/pytest` absent. | **ADDRESSED** — all pytest references replaced. |
| C-7 | BLOCKING (feasibility) | host C-7 + Codex #2 | C3 classifier branches on `mergeable` / `required_conversation_resolution` / required-context data the current `gh pr view` does not fetch; `parse_checks` knows observed states only, not which contexts are required. | **ADDRESSED (scope tightened)** — C3 becomes additive-only (MUST NOT flip eligibility; every non-CLEAN stays `blocked`); the needed fields are added to the fetch with an explicit query; sub-diagnoses that need data not fetchable are scoped out; a NEGATIVE test asserts BLOCKED+MERGEABLE never becomes eligible and never reaches `gh pr merge`. |
| C-8 | PARKED (in-impl gate) | host C-8 + design open-Q3 | Exact parked-canary halt path unconfirmed (investigator saw only pack-blocker sets `stop_starting`). | **PARKED as a Phase-C prereq spike** — C4d edit is GATED: confirm the halt path before editing. Scoped inside implementation, not a planning blocker. |

Design open questions resolved: Q1 accept Trellis-upstream scope = **yes**;
Q2 settle-watch = **classification-only now**; Q3 = **explicit `--allow-parked-canary`**.

## Verdict

Round 1 remediation applied to prd.md, design.md, implement.md, task.json.
- Blocking concerns C-1, C-2, C-3, C-5, C-6, C-7: **addressed** in-artifact.
- C-4: **descoped** (unsafe as designed; proven workaround retained; follow-up filed).
- C-8: **parked** as a scoped in-implementation gate (not an activation blocker).

**No unresolved blocking concern remains.** Planning is eligible to activate
(`task.py start`) pending the operator's implementation approval. Codex approval is
NOT claimed as a sign-off — the Codex lane RAISED blockers; those blockers are the
ones dispositioned above.
