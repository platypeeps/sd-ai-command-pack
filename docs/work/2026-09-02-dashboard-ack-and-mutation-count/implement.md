# Implement — the dashboard's three open gaps

Seven steps. The order is chosen so that the budget's answer arrives early: the
ledger is step 1 because it is the largest single estimate, and if 30 lines
turns out to be 45 the item finds out before four other steps have been built on
top of it.

Every step is independently landable and independently green. Steps 2, 3 and 4
each add one write site to the ledger from step 1 and are independent of each
other; steps 5 and 6 are the ack pair and 6 depends on 5.

## Step checklist

- [x] **1 — `bin/sd_ledger.py`.** `path()` and `append(kind, **fields)`.
      Exclusive `flock` over `O_APPEND`, one JSON object per line, `at` stamped
      by the writer. Every exception swallowed (D-6): this function cannot raise
      into a caller, and its own test asserts that against an unwritable path.
      Green when: `tests/test_sd_ledger.py` passes, including a
      concurrent-writer case that asserts no torn lines.

      **Landed in `bin/`, not `dashboard/`, and that changed D-1.** Written
      first into `dashboard/ledger.py`, it measured **64 code lines against a
      30-line estimate** and pushed `dashboard/` to 4,353 total against a 4,300
      cap — over, before three of the seven steps existed. The design's named
      fallback turned out to be unusable (see Budget), so the mechanism moved to
      `bin/`, where the PRD had already said gap 3's fix could go: "where its fix
      lands is a budget decision, not only a design one". The dependency already
      runs one way, `bin/sd-dashboard` imports `dashboard`, so the writer is
      passed *down* as a callable and `dashboard/` gains a parameter rather than
      an import.
- [x] **2 — the `mutation` record.** One `ledger.append` in `do_POST`
      (`dashboard/server.py:498`), after `actions.run` returns **and only when
      it returned a 2xx**, carrying `at`, `action`, and `tailnet_host` (the
      `Host` matched a tailnet address rather than loopback). Green when: a
      request through each of the four paths — host refused, token refused,
      unknown action, success — leaves exactly one record for the success and
      none for the other three. *The status guard is a review finding: the
      first version recorded every outcome, and this gate asserted otherwise
      without testing it.*
- [x] **3 — the `bind` record.** One `ledger.append` in `serve`
      (`dashboard/server.py:621`) after the bind loop and **before** the
      `SystemExit` that a total failure raises, carrying `requested`, `bound`
      and `tailnet` as counts. Green when: a fixture with a stubbed `tailscale`
      that exits non-zero records `requested: 1, bound: 1, tailnet: 0` and warns
      that no tailnet address was found, and one with two addresses records `3`,
      `3` and `2`. *Both the third count and the ordering are review findings:
      `requested` and `bound` agreeing hid an empty probe, and the `SystemExit`
      came first, so the worst start of all left no row at all.*
- [x] **4 — the bounded re-probe.** `bound_addrs` (`dashboard/server.py:129`)
      probes up to 3 times, 2 seconds apart, latching after the last attempt
      rather than the first (D-4). The sleep is injectable so the test does not
      spend 4 seconds. Green when: a stub returning empty twice then an address
      yields that address, and a stub always empty is called exactly 3 times and
      returns `[]`.
- [x] **5 — `POST /api/ack`.** Beside `/api/run`, behind the same three guards
      in the same order. The body carries an id; the id is written to the ledger
      as `kind: "ack"` and never reaches `actions.run` or an argv. `now` reads
      the ack ids once per render and drops matching rows. Green when: an acked
      id is absent from the next render and still absent after a simulated
      restart; and `grep` for interpolation (acceptance criterion 7) is clean.

      **The second half of that gate no longer holds, deliberately.** Branch
      review overturned D-2 (see `design.md`, C-27): an ack survives a restart
      but not the day it was taken, because count-keyed ids recur and a
      permanent ack hides the recurrence. The gate is now that an acked id is
      absent from the next render, absent after a restart on the same day, and
      **present again the next day**.
- [x] **6 — the dismiss control in `app.js`.** One button per Now row, posting
      the row's id to `/api/ack`, removing the row optimistically. Green when:
      the existing `app.js` tests pass and the new control's handler is covered.
- [x] **7 — D-3: `pr:` ids gain the rank band.** `dashboard/now.py:129` becomes
      `pr:{repo}#{number}:{rank}`. Green when: `tests/test_dashboard_now.py`
      passes with a case asserting a PR moving `FRESH → STALE` mints a new id.

## Budget

The design estimated ~91 code lines against 94 of `dashboard/` headroom. Both
halves of that were wrong, and the measured outcome is here rather than the
estimate:

| | `dashboard/` total | `dashboard/` code | `bin/` total |
|---|---|---|---|
| before | 4,190 / 4,300 | 2,206 / 2,300 | 12,217 / 14,000 |
| ledger in `dashboard/` (abandoned) | **4,353 — over by 53** | 2,285 | — |
| shipped, before review remediation | 4,294 / 4,300 | 2,257 / 2,300 | 12,354 / 14,000 |
| shipped, after the branch review's first round | 4,336 / 4,350 | 2,267 / 2,300 | 12,393 / 14,000 |
| **shipped, after its second round** | **4,348 / 4,350** | **2,269 / 2,300** | **12,416 / 14,000** |
| headroom left | **2** | 31 | 1,584 |

Two errors the estimate made, recorded because the next item will make them
again otherwise:

1. **It sized the code cap and ignored the total cap.** The total busted first,
   at 4,353 against 4,300, while the code cap still had 15 lines free. This
   repository documents heavily and prose counts toward the total, so an
   estimate in code lines alone cannot answer whether something fits.
2. **The named fallback was not deletable.** The design nominated
   `dashboard/plugins.py:678-713` for being fixture-covered. It is `alert_rows`,
   which turns plugin failures into Now rows and carries per-complaint ids
   precisely so dismissing one cannot hide its siblings. Deleting it would make
   plugin losses silent — the exact failure class this item exists to fix.
   Coverage is not deletability, and the function should have been opened before
   it was named.

A third error, caught last and worth the most: **the "shipped" row was measured
twice before the work was finished.** The table read 4,266 from an audit taken
after step 5, when step 6 had yet to add the dismiss control; corrected to 4,294,
it was then overtaken by the branch review's remediation. A budget measured
before the work is finished is an estimate wearing a measurement's clothes, and
the only defence is to re-run the tokeniser after the last commit rather than
after the last one you remember. The row above is measured at this branch's tip.

**The cap.** Raising `DASHBOARD_CODE_CAP` was never available
(`tests/test_loc_caps.py:20`, downward-only), and it is not needed: 2,269 of
2,300. `DASHBOARD_CAP` **is** raisable, was the binding constraint at six lines
before remediation and would have been red after it, and is not raised here.
`test_loc_caps.py`'s docstring says a cap "is never raised in the PR that busts
it" and that each re-derivation landed "in its own decision record by a change
that fit under the ceiling it replaced". So it moved in R11-D29, in a change
touching nothing under `dashboard/`, merged immediately before this one. This
branch is rebased on it and measures 4,348 against 4,350.

Two lines. The table above has four "shipped" rows because each round of review
moved the number, which is the honest shape of this item's budget and the reason
the cap record was re-derived from the branch each time rather than once. Two
lines is not slack; it means the next change under `dashboard/` opens by writing
its own re-derivation, which is what `test_loc_caps.py` asks for and what this
item spent a separate pull request learning.

## What the branch review changed

The lane (`sd-review --scope branch --challenge`, codex and prism) ran after all
seven steps were green and returned eleven findings against work that had
already passed its own gates. Seven were real, and they are worth listing
because five of the seven are the same mistake: a claim the design made about
behaviour that nothing exercised.

| Finding | What it was |
|---|---|
| Permanent acks hide a returning count | D-2's justification, disproved. Acks now hold for a day |
| A refused or failed action recorded a mutation | Step 2's own gate claimed otherwise and never tested it |
| `[::1]:8767` classified as tailnet demand | `split(":")[0]` yields `[`; `host_ok` had the right parser 200 lines up. One parser now, two callers |
| A total bind failure recorded nothing | `SystemExit` came before the row, so the worst start looked like no start |
| An empty tailnet probe reported a clean bind | `requested` was `[host]`, so the counts agreed and nothing warned |
| A damaged ledger 500'd the page | `UnicodeDecodeError` is a `ValueError`, and the guard caught `OSError` |
| Mutation tests exercised stand-ins | They asserted properties of hand-written look-alikes, not of `do_POST` |

Two test defects went with them: a monkeypatched `tailnet_addrs` with no
restore, and a dismiss control that treated a 403 as success.

## Verification

Named before the work, per the repository's own standard:

- **The budget.** `python3 -m pytest tests/test_loc_caps.py` passes.
  Failure means `dashboard/` code exceeded 2,300 and the named cut is due. This
  is the check most likely to fail, which is why it is first.
- **Each step's own gate**, as listed above. A step is not done because its code
  exists; it is done when its named test passes.
- **The whole suite.** `make check` passes with no new failures against the
  1,140 tests and 875 subtests currently green.
- **No caller-supplied value reaches an argv** (acceptance criterion 7):
  `grep -rn 'argv' dashboard/` reviewed by eye against every `RUN_ALLOWLIST`
  entry, and the ack path asserted to contain no `subprocess` call at all.
- **Mutation-tested, not merely covered.** For steps 2, 3 and 4, the test is
  run against a deliberately broken implementation before the real one: a
  `do_POST` that records on refusal, a `serve` that records only on success, a
  `bound_addrs` that latches on the first probe. Each must fail. A gate that
  has never failed has not been shown to work.

  *Half-done, and review said so.* The first version asserted those properties
  of stand-ins written beside the handler rather than of the handler, which
  proves the stand-ins correct and nothing else. The gates now read the guard
  out of `server.py` itself, so deleting `if 200 <= status < 300:` from
  `do_POST` fails a test instead of silently widening what gets counted.

**Cannot be verified here, stated rather than faked:** the acceptance criterion
that asks for *"pressing the real button on the real machine"* needs the
installed service and a phone on the tailnet. The fixtures cover the four guard
paths and both bind failures; they do not cover the launchd boot race that
produced the original observation, because reproducing it means rebooting a Mac
with a stopwatch. That gap is the PRD's C-6 and C-7, already recorded there.
