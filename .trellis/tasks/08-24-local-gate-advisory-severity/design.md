# Design — advisory severity ceiling and the miscited disposition

**Task:** `08-24-local-gate-advisory-severity`
**Baseline:** `manifest.json` 0.71.46; `templates/scripts/sd-ai-command-pack-review-local.py`
(85278 bytes). All line numbers below are that file unless another is named.

---

## 1. Where the change lands

Two functions and one config validator. Nothing else moves.

| Site | Today | After |
| --- | --- | --- |
| `POLICY_KEYS` `:149-156` | 4 keys | +`localAdvisorySeverityCeiling` |
| `_parse_config` policy block `:506-530` | validates 3 fields | + ceiling validation |
| `_remote_gate` `:1945-1970` | `(outcome, outstanding, local_policy, family_gate, findings_present=)` | + `findings`, + `ceiling` |
| call site `:1936` (`_redispose_receipt`) | passes count | passes findings + ceiling |
| call site `:2122` (fresh receipt) | passes count | passes findings + ceiling |
| `LOCAL_DISPOSITION_VALUES` `:77` | `{"rebutted"}` | `{"rebutted", "miscited"}` |

**The reason this is small:** the classification already survives all the way to
the receipt and is discarded only at the decision point. `severity` is recorded
per attempt (`:1640-1642`) and across the merge (`:1815-1817`), normalized from
integers (`:1580-1599`), ranked (`FINDING_SEVERITY_RANK`, `:69`), and merged by
**maximum** (`:1824-1827`). No provider plumbing changes.

---

## 2. Contracts

### 2.1 Policy input (new, optional)

```jsonc
// .sd-ai-command-pack/review.json
"policy": {
  "allowedDataHandling": ["private-network"],
  "documentation": "cheapest",
  "metadata": "cheapest",
  "requiredProviders": [],
  "localAdvisorySeverityCeiling": "medium"   // NEW, optional
}
```

Accepted values: `"low"`, `"medium"`. **Not** `"high"` and **not**
`"unspecified"`.

- `"high"` is rejected because accepting it would let a policy author lower the
  floor to nothing, which R2 forbids. Rejecting it at parse time makes that a
  configuration error rather than a silently permissive gate.
- `"unspecified"` is rejected because rank 0 is the "provider told us nothing"
  sentinel; a ceiling there would release exactly the findings we trust least.
- Absent means strict. `None` is not a ceiling — it is the absence of one, and
  every comparison below short-circuits on it (R5).

Validation sits in the existing policy block at `:517-520`, matching the shape
already used for `documentation` / `metadata`, and raises `ReviewInputError`
with a bounded message. It flows into `configurationDigest` (`:2293`) and thus
`plan["policyDigest"]` (`:1309`) with no extra work, which is what makes a
ceiling change visible in the receipt identity.

### 2.2 The advisory predicate

```python
def _is_advisory(finding: Mapping[str, Any], ceiling: str | None) -> bool:
    if ceiling is None:
        return False                                    # R5: absent is strict
    severity = str(finding.get("severity") or "unspecified")
    rank = FINDING_SEVERITY_RANK.get(severity, 0)
    if rank == 0:                                       # unspecified / unknown
        return False                                    # property 3
    if rank >= FINDING_SEVERITY_RANK["high"]:
        return False                                    # property 2: the floor
    return rank <= FINDING_SEVERITY_RANK[ceiling]
```

Note `FINDING_SEVERITY_RANK.get(severity, 0)`: a severity string the vocabulary
does not know ranks 0 and is therefore blocking, same as `unspecified`. The
`rank >= high` line is redundant while the accepted ceilings are `low`/`medium`,
and is kept deliberately as a floor that survives someone widening the accepted
set later. **That redundancy is load-bearing and must not be "cleaned up"** —
the test at T4 pins it.

### 2.3 Outstanding, recomputed

Today (`:2100`):

```python
outstanding = sum(1 for item in findings if item["disposition"] == "outstanding")
```

After — three counts, because R4 needs the receipt to say *why* a gate opened:

```python
outstanding  = # disposition == "outstanding" AND not advisory
advisory     = # disposition == "outstanding" AND advisory
dispositioned= # disposition in LOCAL_DISPOSITION_VALUES
```

`outstanding` keeps its exact present meaning when no ceiling is set, which is
what makes R5 checkable by running the existing suite unchanged.

### 2.4 Disposition vocabulary (extended)

```python
LOCAL_DISPOSITION_VALUES = frozenset({"rebutted", "miscited"})
FINDING_DISPOSITIONS = frozenset(
    {"outstanding", "fix", "fixed", "rebutted", "resolved", "miscited"}
)
```

`miscited` carries an evidence obligation `rebutted` does not. The CLI form
extends the existing `<id>=<value>` grammar (`_parse_local_dispositions`,
`:1862-1878`) with a required citation suffix:

```
--local-disposition '<stable-id>=miscited@<path>:<line>'
```

The parser splits on the last `=` today (`rpartition`), so the citation rides
inside the value and the id grammar is untouched. The path and line supplied by
the caller are recorded in the receipt beside the finding's own cited location,
so a reader can see both what the provider claimed and what the caller checked.

**Two traps in that grammar, both found by review of this design rather than in
implementation:**

1. **`rpartition` splits on the LAST `=`.** A citation path containing `=`
   turns `id=miscited@a=b.py:3` into identifier `id=miscited@a` and value
   `b.py:3`, which then fails the vocabulary check with a message about
   dispositions rather than about the path. Reject a citation path containing
   `=` explicitly, with its own message. Do not switch to `partition`: that
   would silently change how existing ids containing `=` parse.
2. **The stored disposition must be the bare value, not the raw argument.**
   `_apply_local_dispositions` (`:1880-1904`) writes its input straight onto
   `finding["disposition"]`. Storing `"miscited@path:3"` would put a string into
   that field that is not a member of `FINDING_DISPOSITIONS`, which `:898`
   validates elsewhere — a receipt that fails its own vocabulary check. Parse
   into `(disposition, citation)` at parse time; store `"miscited"` in
   `disposition` and the citation in its own field.

**What is deliberately not built:** the pack does not verify the citation
itself. Reading the checkout at gate time would make the gate depend on
worktree state that the receipt cannot pin, and a receipt is supposed to be
replayable from its own contents. The caller asserts, the receipt records, and
the assertion is auditable because both locations are stored. This is the same
trust posture `rebutted` already has.

### 2.5 Gate output (extended)

```python
{"state": "eligible", "reason": "local-stage-terminal"}          # unchanged, clean
{"state": "eligible", "reason": "local-advisory-released"}       # NEW: ceiling opened it
{"state": "eligible", "reason": "local-findings-dispositioned"}  # NEW: rebuttals opened it
{"state": "blocked",  "reason": "actionable-local-findings"}     # unchanged
```

Precedence when several apply: `blocked` wins over everything; among the
eligible reasons, `local-stage-terminal` (nothing was found at all) beats
`local-findings-dispositioned` beats `local-advisory-released`. Reporting the
*strongest* claim the receipt supports means a reader is never told "clean" for
a receipt that was actually released.

---

## 3. Control flow

```
findings ──> _apply_local_dispositions(findings, supplied)   # rebutted | miscited
         │
         ├──> outstanding    = outstanding AND NOT advisory
         ├──> advisory       = outstanding AND advisory
         └──> dispositioned  = disposition in LOCAL_DISPOSITION_VALUES
                     │
                     v
              _remote_gate(outcome, outstanding, local_policy, family_gate,
                           findings_present=, advisory=, dispositioned=)
                     │
   outstanding > 0 ──┴──> blocked: actionable-local-findings
   outcome == findings and not findings_present ──> blocked (unchanged)
   family_gate in {sibling-audit-required, round-extension-required} ──> blocked
   TERMINAL_FAILURES ──> eligible-with-limitations | blocked (unchanged)
   else ──> eligible, reason by precedence above
```

The `findings_present` guard at `:1956` is unchanged and still fires first: a
provider that says "findings" while listing none has given evidence nobody can
inspect, rebut, or classify by severity, so no ceiling releases it.

---

## 4. Test contract

Every one of these fails against today's code. That is the point — none may be
written after the fact.

| id | assertion |
| --- | --- |
| T1 | `localAdvisorySeverityCeiling: "medium"` accepted; digest changes vs absent |
| T2 | `"high"` rejected with a bounded `ReviewInputError` |
| T3 | `"unspecified"` and `"nonsense"` rejected likewise |
| T4 | ceiling `medium` + `high` finding ⇒ **blocked** (floor not lowerable) |
| T5 | ceiling `medium` + `low` finding ⇒ eligible, `local-advisory-released` |
| T6 | ceiling `medium` + `unspecified` finding ⇒ **blocked** (property 3) |
| T7 | ceiling `medium` + severity `"bizarre"` ⇒ **blocked** (unknown ranks 0) |
| T8 | no ceiling + `low` finding ⇒ blocked (R5, today's behavior) |
| T9 | `=miscited@path:line` accepted; recorded distinctly from `rebutted` |
| T10 | `high` + `miscited` ⇒ eligible; `high` + nothing ⇒ blocked. One test, both. |
| T11 | `miscited` without `@path:line` ⇒ bounded input error |
| T12 | mixed set: one advisory + one outstanding `high` ⇒ blocked, and the receipt shows advisory=1 |
| T13 | precedence: dispositioned + advisory both present ⇒ `local-findings-dispositioned` |

**Mutation checks** (each must fail one named test alone):
M1 delete the `rank == 0` guard → T6, T7.
M2 change `rank >= high` to `rank > high` → T4.
M3 make absent ceiling default to `"medium"` → T8.
M4 fold `miscited` into `rebutted` in the receipt → T9.

---

## 5. Compatibility and rollout

**Backward compatible by omission.** No repository has
`localAdvisorySeverityCeiling` today, so every consumer gets byte-identical
behavior until it opts in. AC "existing tests pass unchanged" is the check.

**Rollback** is a one-line config removal in the consuming repository, with no
pack downgrade and no reinstall: delete the key, the gate is strict again.

**Adoption, per consumer.** A consumer's `.prism/rules.json` `severityOverrides`
already assigns the meaning — in `sd-github-review` it pins `bug`, `correctness`
and `security` to `high` and every advisory category to `medium` or `low`, so
`"localAdvisorySeverityCeiling": "medium"` releases exactly
`docs`/`maintainability`/`testing`/`performance`/`style` and holds the rest.
That mapping is per-repository and must be read before adopting, not assumed.

**Open risk — the confidence claim. SETTLED 2026-08-24, and it found a
different defect than the one it was looking for.**

The trace, on the shipped code:

- The local receipt sets `confidence.granted = outcome == "clean"`
  (`review-local.py:2308`). Its only reader is `_remote_summary` (`:2348`),
  which copies it into the report verbatim. **Nothing branches on it.**
- `review.py:1044` computes `confidence = 90 if outcome == "clean" else 0` into
  the router summary. Also never read as a condition.
- The one `confidence.get("granted") is False` test in the pack
  (`review-learnings.py:1657`) reads `confidenceCredit` on a *planning signal* —
  an unrelated structure that happens to share the word.

So no code refuses to proceed on zero confidence, and a ceiling-released receipt
carrying `outcome: "findings"` with zero confidence breaks nothing mechanical.
That much matches the "nothing consumes it" branch.

**But the clean/not-clean distinction does have a consumer, and it is prose.**
`sd-review/SKILL.md` said: *"A router classified `absent` may complete locally
only when routing is optional and the local receipt is clean."* That is the
governing rule for exactly the topology this task targets — a consumer whose
remote lane is `absent` by design. Under it, the gate would have said `eligible`
and the agent still could not have completed, because the receipt is not clean.
The feature would have shipped inert. The rule now reads `remoteGate.state`,
and names the three eligible reasons.

**Second finding from the same trace, unrelated to confidence.**
`_router_local_summary` bucketed local finding dispositions with a terminal
`else: raise ReviewError("local receipt finding disposition is invalid")`, and
`miscited` was in no bucket — so a receipt carrying one is refused outright, not
miscounted. Fixed by adding it to the `rebutted` bucket (terminal, no
fix-commit evidence), where `resolved` already sits for the same reason.

**Reachability, measured rather than assumed** — the first write-up of this
said "any receipt carrying one", which is wrong. `_router_local_summary`
returns `None` for `outcome not in {clean, unavailable, failed, cancelled,
skipped}`, so an ordinary `findings` receipt never reaches the loop, and
`_aggregate_outcome` gives `findings` precedence over every other status. The
reachable shape is a provider that emits findings and then exits non-zero: the
attempt's status is `failed`, the aggregate is `failed`, and the findings list
is still non-empty. Probed across all six outcomes to confirm.
`tests/test_review_controller.py::test_router_summary_buckets_miscited_instead_of_rejecting_the_receipt`
pins both the bucket and the narrow reachability; reverting the bucket kills
that test and nothing else.

**Third finding, and it needed no code change — which is the problem.**
The controller's own routing gate reads `disposition["outstanding"] != 0`
(`_local_outstanding`, called at `:2055`). Because the ceiling removes advisory
findings from `outstanding`, that gate now opens for a released receipt with no
edit at all, which is the behaviour we want. But the comment beside it asserts
"Every provider finding carries a caller disposition", which a ceiling-released
receipt falsifies. Comment corrected; had it not been, the next reader would
conclude the gate was still counting something it is not.

*(Also: `_local_outstanding` **does** exist — in the controller. The note in
this task and its predecessor saying the symbol does not exist was about
`review-local.py`, where it indeed does not. Grepping the whole repo finds it
and finds the wrong file.)*

**Correction to §4's mutation contract.** M2 (`rank >= high` → `rank > high`)
does **not** kill T4, and the claim above that "the test at T4 pins it" was
wrong. With the accepted ceilings `low`/`medium`, a `high` finding is already
refused by `3 <= 2`, so T4 passes with the floor deleted. Pinning it requires
calling `_is_advisory` directly with a ceiling the config layer refuses —
T4b, `test_advisory_predicate_keeps_a_floor_a_wider_vocabulary_cannot_lower`.
Measured: M1 kills T6/T7 only, M2 kills T4b only, M3 kills T8 and T4b, M4 kills
T9 only.

**Risk that survives.** A provider that inflates every finding to `high` defeats
the ceiling entirely. That is the intended failure direction — it fails closed,
into today's behavior — but it means the ceiling's usefulness depends on the
provider rating honestly. The `miscited` ground exists partly to give a false
`high` an exit that does not require lowering the floor.

---

## 6. What this does not close

The final acceptance criterion — replaying PR #70's three rounds and terminating
without a human round-extension — cannot be asserted by a unit test. It needs a
real branch, real providers, and a consumer whose credentials work. It is listed
as an acceptance criterion because it is the actual objective; it will be
verified in a consumer, and if it cannot be, that must be recorded as unmet
rather than inferred from T5 passing.
