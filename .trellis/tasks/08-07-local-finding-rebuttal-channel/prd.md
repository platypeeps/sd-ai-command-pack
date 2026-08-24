# PARKED (criteria all met 2026-08-24; unpark on PR #536 merge): Verified-false local review findings have no rebuttal channel

## Goal

Give a verified-false *local* provider finding the same disposition path a
remote finding already has, so a false positive cannot permanently block the
remote gate.

## Problem

`sd-review` instructs the caller to verify every finding and to "rebut rather
than comply when it is wrong". For remote findings that is actionable — the
coordinator accepts a disposition:

```text
--remote-disposition '<stable-id>=rebutted'
```

There is no local counterpart. The full flag list in
`scripts/sd-ai-command-pack-review.py:1653-1673` contains `--remote-disposition`
and nothing else that dispositions a finding. `--finding-family` and
`--family-evidence` only forward to the provider command
(`sd-ai-command-pack-review.py:718-721`); they do not clear anything.

Meanwhile the local receipt reader already understands the vocabulary
(`sd-ai-command-pack-review.py:899-909` accepts `rebutted` and `resolved`), and
any outstanding local finding blocks the gate:

```text
remoteGate: {"reason": "actionable-local-findings", "state": "blocked"}
```

So a local false positive is terminal. The only ways past it are to change the
file the provider misread, or to abandon the PR.

## Evidence: PR #353

PR #353 adds four `.trellis/tasks/` artifacts and no code file at all. The local
provider returned three findings, at `prd.md` lines 21, 54, and 94 — the three
fenced blocks where the PRD *quotes* `add_session.py` as evidence of the defects
being filed. The provider read quoted source inside a Markdown document as the
PR's own code and re-reported the documented defects as new ones.

That generalizes: every defect-filing PRD quotes the defect it documents, so
every such PR produces findings equal to the bugs it describes. The whole
task-filing workflow is a false-positive generator under the current reader.

Retagging the fences from `python` to `text` cleared all three. Re-review then
produced a fourth finding:

```text
Typographical error: 'descision' should be 'decision'   (prd.md:140)
```

Line 140 reads `decision`, spelled correctly. `grep -rn descision` returns
nothing in the file, the PR, or the repository. The finding is a hallucination,
and with no rebuttal channel it blocks the merge.

## Requirements

### Functional

- A local finding must be dispositionable as `rebutted` by stable ID, with the
  same shape and the same evidence expectations as `--remote-disposition`.
- A rebutted local finding must clear the `actionable-local-findings` gate while
  remaining visible in the receipt as rebutted, not deleted.
- The rebuttal must be recorded against the exact head, so it does not carry
  silently to a later head with different content.

### Non-functional

- Must not become a blanket suppression: rebutting is per-finding and per-head.
- The receipt must keep enough record for a reviewer to audit what was rebutted
  and why.

## Open questions

1. Should the fenced-code misread be fixed at the provider level instead — a
   Markdown file's fenced blocks are quotations, never the diff's own source?
   That fixes one large class but leaves hallucinated findings unaddressed.
2. Should a finding whose cited text does not exist at the cited line be
   auto-invalidated before it ever reaches the gate? That is a cheap,
   deterministic sanity check the coordinator could run itself.

## Acceptance Criteria

**Reconciled 2026-08-24 against the shipped code, not against PR #402's
description.** Three of five shipped; the record had left all five unchecked,
so the backlog read as though the rebuttal channel did not exist.

- [x] A local finding can be dispositioned `rebutted` by stable ID
      — `--local-disposition` at
      `templates/scripts/sd-ai-command-pack-review-local.py:2237`, parsed by
      `_parse_local_dispositions` (`:1862`), applied by
      `_apply_local_dispositions` (`:1880`).
- [x] A rebutted local finding clears the gate and stays visible in the receipt
      — `_remote_gate` (`:1945`) gates on the outstanding count only; the
      finding is dispositioned, never deleted. Asserted by
      `tests/test_review_stage.py:423`
      `test_rebutted_local_finding_clears_the_gate_but_stays_visible`, which
      checks the gate opens *and* that the finding survives with
      `disposition == "rebutted"`.
- [x] The disposition is bound to the exact head and does not carry forward
      — `_apply_local_dispositions` raises on an id matching no finding at the
      current head rather than no-opping, so a stale id cannot open the gate.
      Asserted by `tests/test_review_stage.py:510`
      `test_rebuttal_does_not_carry_to_a_different_head` and `:458`
      `test_local_disposition_rejects_an_id_matching_no_finding`.
- [x] A test covers the PR #353 case: a Markdown-only diff whose fenced blocks
      quote source
      — closed 2026-08-24 by
      `tests/test_review_stage.py::test_markdown_only_diff_misread_as_source_is_clearable_by_rebuttal`,
      with the provider fixture mode `markdown-fenced-quotes` reproducing the
      three findings at the three fences. It asserts the scenario's premise (no
      `.py` under review at all), that all three are rebuttable per finding,
      that the gate opens once every one is dispositioned, and that each survives
      **with its path, line and summary intact** — not merely as three entries.
      A mutation that keeps ids and drops the evidence kills it.

      Its sibling
      `test_the_hallucinated_typo_from_pr_353_takes_the_miscited_ground` covers
      the fourth finding, the `'descision'` hallucination at `prd.md:140`, on
      the `miscited` ground that did not exist when this task was filed.

      **Scope note.** What is pinned is the pack's half: findings on a diff with
      no source file in it are dispositionable and auditable. Making the provider
      stop reading a quoted fence as the diff's own source is not something this
      repository can assert, and Open Question 1 above — whether to fix it at the
      provider level — stays open.
- [x] Open question 2 is answered in `design.md`
      — answered in the successor's design instead, since this task has no
      `design.md`:
      `08-24-local-gate-advisory-severity/design.md` §2.4. The answer is **no**.
      The pack does not verify a citation by reading the checkout at gate time,
      because that makes the gate depend on worktree state the receipt cannot
      pin, and a receipt must be replayable from its own contents. Instead the
      caller asserts `miscited` and supplies the path and line; both the
      caller's citation and the finding's own are recorded, so the assertion is
      auditable. Same trust posture `rebutted` already has.

### What remains here

**Nothing.** All five criteria are met as of 2026-08-24; the regression test
landed with `08-24-local-gate-advisory-severity` (PR #536), which is where the
`miscited` ground its sibling test needs also lives. Ready to unpark and
archive once that PR merges.

Open Question 1 — fixing the fenced-code misread at the provider level — is
**not** an acceptance criterion here and is not closed by the above. File it
separately if it is still wanted.

**The severity half of the problem is not this task's** — it moved to
`08-24-local-gate-advisory-severity`, which carries the second failure mode
recorded below (non-convergence) plus the PR #99 miscitation evidence.

### Naming trap, recorded so nobody re-derives it

The shipped mechanism is **not** called `_local_outstanding`, as the section
below states, and the trap has two halves.

In `templates/scripts/sd-ai-command-pack-review-local.py` — the file that owns
the gate — that symbol does not exist. The rebuttal gate landed as an
`outstanding` count computed in `_redispose_receipt` and read by `_remote_gate`.
Grepping the local stage for `_local_outstanding` reports the fix absent when it
is present, which is exactly the mistake a downstream consumer made on
2026-08-09.

But a **repo-wide** grep does find `_local_outstanding` — in
`templates/scripts/sd-ai-command-pack-review.py`, where it is the *controller's*
routing gate reading the count the local stage computed. Same name, different
file, different job. Corrected 2026-08-24; the earlier note here said the symbol
did not exist at all, which sends the next reader looking in the right file for
the wrong reason.

## Notes

Filed 2026-08-07 while shipping PR #353, which is blocked by exactly this gap.
Sibling of `08-06-review-check-receipt-pinning` (T-27) and
`08-06-local-provider-empty-scope` (T-28): all three are local-provider
evidence-handling defects.

## Second failure mode: non-convergence, not false positives (2026-08-09)

Filed from `platypeeps/sd-github-review` on `0.64.3`, which predates PR #402's
`_local_outstanding` rebuttal gate. The evidence is still current for this task,
because it describes a shape the rebuttal channel alone does not close.

The PR #353 evidence above is about findings that are *wrong* — a misread fence,
a hallucinated typo. A rebuttal channel answers that. This is the other case:
findings that are individually defensible and still never terminate.

### PR #70: three rounds, thirty findings, zero confirmed defects

Three rounds against the same branch, each at a new head after real fixes:

| Round | prism | gito | Overlap with prior round |
| --- | --- | --- | --- |
| 1 | 9 findings | clean | — |
| 2 | 11 findings | clean | none |
| 3 | 10 findings | clean | 2 residuals of one family |

Every finding was verified against the checkout. The two that claimed a real
defect were refuted by the code. The one genuine signal — managed-resource
enumeration drift, which that repository's own `review-recurrence-prevention`
rule targets — recurred across all three rounds and was fixed, with rounds 2 and
3 confirming the fix by narrowing it.

Rounds 1 and 2 shared **no finding at all**. That is the operative evidence: the
provider emits a fresh observation set per invocation, so a fourth round
converges on nothing. Per-finding rebuttal disposes of each round's set and the
next round produces a different one — the loop is unbounded in rounds, not in
findings-per-round.

The upstream cause is configuration this repository does not own: `.prism/rules.json`
sets `focus` across eight categories including `docs`, `maintainability`, and
`style`. That produces useful signal, but most of it is commentary on the change
rather than a defect in it, and `_remote_gate` cannot tell the two apart —
`if outstanding or outcome == "findings"` blocks on any finding of any category
at any severity.

### The documented local-only escape is unreachable in this topology

`sd-review`'s rule is that "a router classified `absent` may complete locally
only when routing is optional and the local receipt is clean". That consumer's
remote lane is `absent`/`setup-descriptor-absent` **by design** — its
`08-09-descriptor-contract-path` moved the published setup descriptor off the
probe path precisely so the router does not self-match its own artifact. So the
escape's precondition holds on the routing side and fails on the receipt side:
the receipt can never be clean while any advisory finding stands.

The other documented exits do not apply either:

- `--successor bookkeeping` requires evidence that the whole `base..head` delta
  is bookkeeping. False for any real change.
- `--successor low-risk` still selects a provider, which returns a fresh set.
- `--remote-disposition <id>=rebutted` is remote-receipt-only and explicitly not
  for an unfixed finding.
- `review.round-extension` asks a human every time. That is a prompt in place of
  a gate, not convergence. PR #70 required it after three rounds.

### Requirement this adds

Severity or category must be usable in the gate decision, so an observation-only
category cannot block indefinitely while a `high correctness` finding still does.
A per-finding rebuttal channel is necessary but not sufficient: without a
category dimension, a converging PR still pays one manual disposition per
advisory finding per round, forever.

Corresponding acceptance criterion: replaying the three-round PR #70 sequence
against the new gate terminates without a human `review.round-extension`
decision, while a synthetic `high correctness` finding with no disposition still
blocks.

Tracked in that consumer as `08-09-review-gate-advisory-convergence`, parked
there on this repository's ownership of `_remote_gate`.
