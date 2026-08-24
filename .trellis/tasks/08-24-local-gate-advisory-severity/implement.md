# Implement — advisory severity ceiling and the miscited disposition

**Task:** `08-24-local-gate-advisory-severity` · **Design:** [`design.md`](design.md)

Ordered. Each phase ends green; do not carry a red suite forward.

---

## Phase 0 — reconcile the predecessor record

`08-07-local-finding-rebuttal-channel` is PARKED with all five acceptance
criteria unchecked, while its functionality has been live since PR #402. Anyone
reading the backlog today concludes the rebuttal channel does not exist.

- [ ] **0.1** Tick the criteria that shipped, each with file:line evidence from
      `templates/scripts/sd-ai-command-pack-review-local.py` — not from the PR
      description, and not from the upstream symbol name.
- [ ] **0.2** Record in that task that `_local_outstanding` is **not** the
      shipped symbol: the mechanism landed as an `outstanding` count in
      `_redispose_receipt` read by `_remote_gate`. Grepping the old name reports
      the fix absent when it is present.
- [ ] **0.3** State what remains there and point at this task. Its Open
      Question 2 ("should a finding whose cited text does not exist be
      auto-invalidated") is answered here in `design.md` §2.4 — **no**, the pack
      records a caller assertion rather than reading the worktree at gate time.
      Record that answer in the predecessor, since its AC5 requires it.

## Phase 1 — config surface

- [ ] **1.1** Add `localAdvisorySeverityCeiling` to `POLICY_KEYS` (`:149-156`).
- [ ] **1.2** Validate in the policy block (`:506-530`): accept `low`/`medium`,
      reject `high`, `unspecified`, and anything else, with a bounded
      `ReviewInputError`. Absent stays absent — do not default it.
- [ ] **1.3** Thread it from `load_config` to the two `_remote_gate` call sites.
      Confirm by test that the digest differs between absent and set (T1); if it
      does not, the value is not reaching `configurationDigest` and everything
      downstream is untrustworthy.
- [ ] **T1, T2, T3** green.

## Phase 2 — the predicate and the gate

- [ ] **2.1** Add `_is_advisory` exactly as in `design.md` §2.2, including the
      redundant `rank >= high` floor. Comment it as deliberate.
- [ ] **2.2** Split the outstanding count three ways (§2.3) at **both** count
      sites — `:1922` in `_redispose_receipt` and `:2100` in the fresh-receipt
      path. (The gate *calls* are at `:1936` and `:2122`; the counts they
      consume are computed above them.) Both, or a re-run behaves differently
      from a first run.
- [ ] **2.2b** Trace `confidence.granted` (`:2129`) and
      `sd-ai-command-pack-review.py:1044` per `design.md` §5's open risk. A
      ceiling-released receipt is `outcome: "findings"` and therefore zero
      confidence while the gate says eligible. Record what consumes it. Phase 2
      is not done until this is answered in writing.
- [ ] **2.3** Extend `_remote_gate` with the new eligible reasons and the
      precedence order (§2.5). Leave the `findings_present` guard first.
- [ ] **T4–T8, T12, T13** green.
- [ ] **M1, M2, M3** each kill their named test and nothing else. If a mutation
      kills more than its target, the tests are coupled — split them.

## Phase 3 — the miscited ground

- [ ] **3.1** Extend `LOCAL_DISPOSITION_VALUES` and `FINDING_DISPOSITIONS`
      (`:71-77`).
- [ ] **3.2** Extend `_parse_local_dispositions` (`:1862-1878`) for
      `=miscited@<path>:<line>`. Keep `rpartition("=")` — the citation rides in
      the value, so the id grammar and its 240-char bound are untouched. Return
      `(disposition, citation)`, not the raw string: see `design.md` §2.4 trap 2.
- [ ] **3.3** Reject a citation path containing `=` with its own bounded message
      (§2.4 trap 1). Without this the `rpartition` split misreports it as an
      unsupported disposition.
- [ ] **3.4** In `_apply_local_dispositions` (`:1880-1904`) store the **bare**
      `"miscited"` in `finding["disposition"]` and the citation in its own
      field, beside the finding's own cited location. Storing the raw argument
      puts a non-member of `FINDING_DISPOSITIONS` into that field.
- [ ] **3.5** Reject `miscited` with no citation (T11).
- [ ] **T9, T10, T11** green, plus a case for a path containing `=`. **M4**
      kills T9.

## Phase 4 — documentation

- [ ] **4.1** `sd-review`'s public control list: the new disposition ground and
      the policy field. The consumer task notes `--attempt-id` is in the CLI and
      not in the skill — fix that here too while the file is open.
- [ ] **4.2** `CHANGELOG.md`: what changed, and explicitly that omission is
      strict, so an operator reading it knows adoption is opt-in.
- [ ] **4.3** Adoption note: a consumer's `.prism/rules.json` `severityOverrides`
      supplies the meaning of the ceiling, and that mapping must be read per
      repository rather than assumed.

## Phase 5 — release and consumer verification

- [ ] **5.1** Cut the pack release.
- [ ] **5.2** Refresh into `sd-github-review` and set the ceiling there.
- [ ] **5.3** Replay the PR #70 sequence. **Blocked today**: that consumer's
      `prism` credential returns `401 invalid_api_key`, which the harness reports
      as `prism:unavailable` and which degrades the gate to
      `eligible-with-limitations` — a green that proves nothing. Fix the
      credential first or this step cannot run.
- [ ] **5.4** Record the final criterion met, or **unmet with the reason**. Do
      not infer it from T5 passing; a unit test cannot demonstrate convergence
      across rounds.
- [ ] **5.5** Close out `sd-github-review!08-09-review-gate-advisory-convergence`.

---

## Validation commands

```bash
python -m pytest tests/test_review_stage.py tests/test_review_controller.py -q
python -m pytest tests/ -q                      # R5: whole suite, unchanged
make check                                      # repo gate
grep -n "localAdvisorySeverityCeiling" templates/scripts/sd-ai-command-pack-review-local.py
```

## Rollback points

Each phase is independently revertable. Phase 1 alone is inert — a config key
nothing reads. Phase 2 without Phase 3 ships a working ceiling and no miscited
ground; that is a coherent partial state if it has to be cut short, but note
`prd.md` warns it leaves the miscitation half open, so it ships as an
improvement rather than as the fix.
