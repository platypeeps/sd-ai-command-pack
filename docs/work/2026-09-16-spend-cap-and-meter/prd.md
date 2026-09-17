---
title: The registry enforces the spend cap and reads the minimax meter
created: 2026-09-16
---

# PRD — spend cap and meter

## Problem

sd:10's criterion 6 stays open, and three of its parts were deferred to this
item by the owner's decision note 1942 (2026-09-14): the `minimax` meter, the spend cap,
and an audit of the attribution clauses whose names `SD_AUTHOR` and
`slice_base` have no hits in `bin/` or `tests/`. The deferral is recorded on
sd:10's pages
(`2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:1348-1351`);
the item itself had no page of its own, so this is its plan of record.

Measured 2026-09-16 at pack `2eafa78b` and system `a5347185`, with
`grep -rn -F <name> bin tests skills docs .github WORKFLOW.md providers.yaml`
per name; the "Elsewhere" column is those paths and no others:

| Name | `bin/` | `tests/` | Elsewhere | What that means |
|---|---|---|---|---|
| `token_plan` | 0 | 0 | 8 in sd:10's pages, 2 in `WORKFLOW.md`, 1 in `providers.yaml` | nothing reads the meter |
| `capped_bills` | 4, all `bin/sd_registry.py` | 4 | 1 in sd:10's `prd.md` | the refusal exists and has no production caller |
| `cap_usd_month` | 8 | 3 | 1 in `providers.yaml`, and `WORKFLOW.md` says "a recorded ceiling, not an enforced one" | the cap is stored, not enforced |
| `month's total` | 0 | 0 | 5 in sd:10's pages | no refusal names it |
| `reserve_call` | 0 | 0 | 0 | the reservation is not in `writes.py` under that name, and is not planned there |
| `SD_AUTHOR` | 0 | 0 | 1 in `WORKFLOW.md`, 11 in sd:10's pages | see the audit |
| `slice_base` | 0 | 0 | 13 in sd:10's pages | see the audit |

The exposure meanwhile: a `start` entry on a capped bill is refused outright
by `_provider` in `bin/sd_registry.py` ("is a 'start' entry on the capped bill"),
and a `url` entry on a capped bill is called with nothing refusing it.

## The attribution audit

Criterion 6's attribution clauses
(`2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:1262-1306`),
one row each, measured at `2eafa78b`. "Under another name" means the
behaviour exists and a test asserts it, spelled differently from the clause.

| Clause | Finding | Where |
|---|---|---|
| Two commits shipped under `SD_AUTHOR=codex` carry `Authored-with: codex/openai` | Under another name: `sd-ship prepare --author <entry>`; no environment variable | `source:bin/sd-ship::commit_paths` writes the trailer; `ShipCase` in `tests/test_sd_ship.py` asserts `Authored-with: author/firstvendor` |
| Resolution skips every openai entry, and still does after the `codex` entry is repointed or removed | Implemented for the skip; the repoint and removal cases are unasserted | `source:bin/sd_lib.py::author_vendors`, `source:bin/sd_registry.py::reviewer_chain`; `TheReviewerChain` in `tests/test_sd_registry.py` |
| `SD_AUTHOR=nosuch` is refused at commit naming the registry | Under another name, unasserted: `--author nosuch` is refused with the registry's read error, or as "not an enabled author provider"; no test in `tests/` carries that message or an unknown `--author` | `source:bin/sd-ship::commit_paths` |
| The trailer forms the design page documents equal the forms `sd_lib.py` writes and reads, enumerated from the source | Unimplemented: no test reads the design page. The forms are the constants | `source:bin/sd_lib.py::AUTHORED_TRAILER`, `source:bin/sd_lib.py::ATTRIBUTES_TRAILER` |
| One `claude` and one `codex` trailer resolve to the first entry of neither vendor | Implemented in two halves: the scan returns both vendors, and the chain skips every entry of an author vendor | `FixReviewTests` in `tests/test_sd_review_ship.py`, "every actual squash author vendor is excluded"; `TheReviewerChain`, "an entry of the author's vendor is skipped" |
| No trailer and no `--author` is refused naming the flag | Cut, the refusal stands: the untagged commit is refused, naming `sd attribute`. `--author` is `sd-ship prepare`'s flag and applies to a commit not yet made; the refusal names the one repair that applies to a commit that exists. Naming the flag would point at a tool that cannot fix the commit | `source:bin/sd_lib.py::author_vendors`; `FixReviewTests`, "fix commit with no author trailer is refused" |
| An untagged commit before a tagged one is refused naming the commit and `sd attribute`; `sd attribute <sha> claude` resolves it, the attributing commit carrying `Authored-with: human` | Implemented | `source:bin/sd_lib.py::attribute`, `source:bin/sd::cmd_attribute`; `TheRoundTripTests` in `tests/test_sd_attribute.py` |
| A rebase refuses again; `sd attribute <from>..<to> claude` resolves it; the commit is asserted on the fixture remote after the push | Implemented and asserted up to the push; the post-push half is unasserted, no test pushes | `TheRangeTests` in `tests/test_sd_attribute.py`, "a rebase loses the claim and one range attribution restores it" |
| Two slices, the first squashed and the default merged back, resolve by `slice_base`; a fresh branch from the default resolves the same | Under another name, in part: `authorship_base` is the merge base with the default, carried across passes by `sd-ship`. No row records a slice head, so a branch continued after its squash still scans the first slice's commits. Measured 2026-09-16 in a throwaway repository: `c1` and `c2` on `feature`, squashed to `S` on `main`, `main` merged back, `c3` added; `merge-base feature main` is `S`, and `git log --no-merges S..feature`, the range `commit_messages` scans, lists `c3`, `c2` and `c1`, because a squash makes neither original commit an ancestor of `S`. The missing scenario is exactly that one; a fresh branch from the default resolves the same as today | `review` in `bin/sd-review` writes `authorship_base` into the report; `Ship.review_inputs` in `bin/sd-ship` checks it against the report's subject base, and the merge reads it from the last pass's report |
| A session that edits and exits without committing adds its vendor to the row's `authors` (rounds 44 to 46) | Unimplemented as a session row. The `authors` the grep finds in `bin/` are the policy line of `.github/sd-review.json` (read by `sd-review` and `sd_setup_github.py`, echoed into the review report), the local list `sd-ship` builds from `authored_with` and trailers for the squash, and the local reviewer list in `sd-pr-state`; no session writes an `authors` row and none of these feeds the reviewer's vendor set from a session | `source:bin/sd-review::DEFAULT_POLICY`; `review_history` and `merge` in `bin/sd-ship`; `bin/sd-pr-state`, the reviewer list |
| Two clones attributing two commits of one branch both push without force | Unasserted, and not true as stated: each attribution is an empty commit on the clone's head, so two clones from one tip diverge and the second push is non-fast-forward. The sync protocol is: rebase before push; a non-fast-forward refusal is the signal, and the rebase keeps both `Attributes:` lines because the sha they name is unchanged | `source:bin/sd_lib.py::attribute`, the docstring |
| `sd attribute <sha> human` on an untagged branch resolves to the first enabled entry | Implemented | `TheRoundTripTests`, "human writes the bare word and contributes no vendor" |
| `sd-review --author claude` is refused as not a review flag | Implemented by omission: `bin/sd-review` declares no `--author`, so `argparse` exits 2. No test names it | `bin/sd-review`, the parser |
| `SD_AUTHOR=codex` in the review's environment changes nothing | Cut: nothing reads `SD_AUTHOR`, so there is nothing to assert | `grep` above |

Disposition, by row label. **Cut** (two rows, dropped on purpose): the
no-trailer refusal naming `--author`, because the refusal names the repair
and not the flag; and `SD_AUTHOR=codex` in the review's environment, because
nothing reads the variable. **Under another name** (three rows, the
behaviour stands under `--author` and `authorship_base`; one of them
unasserted): the two `SD_AUTHOR` commit rows and the `slice_base` row.
**Unimplemented** (two rows): the trailer-forms-equal-the-design-page test,
which is dropped as a documentation check rather than a behaviour and is not
planned here; and the session row's `authors`, which stays open. **Open**
(requirement 5): the `slice_base` slice row and the session `authors` row,
because a branch continued after a squash is a real shape (`sd-ship` merges
by squash) and the scan today reads the first slice's commits again.
Unasserted halves are named in their rows and are not planned here.

## Requirements

1. The system library reserves each call's bound against the month's settled
   and reserved rows in one transaction, and refuses the call when the bound
   would pass `cap_usd_month`. This half is sd:234 slice 8a, delivered as
   `local-sd-db/sd_db/ledger.py` with `reserve`, `claim`, `settle`, `lose`,
   `release_orphans` and `exposure`, landed in `platypeeps/system` #406 at
   `4b240d28` (absent at `a5347185`); this item consumes it and does not
   build it. `claim` is the transition just before the request goes on the
   wire, `reserved` to `sending`, and the pack calls it.
2. `bin/sd-review` supplies `capped_bills` to `reviewer_chain` and `pick`, so
   fallthrough passes over a bill at its cap and `--provider` on it refuses
   with the month's total.
3. The `minimax` meter reads the two remaining percents from a recorded
   `token_plan/remains` answer and writes `meter` rows; a bill whose window
   reads zero is skipped in fallthrough and refused by name on a direct pick.
4. A `path:line` on these pages passes `tests/test_doc_citations.py` and
   `bin/sd-docs-lint` rule 6.
5. Open: the second-slice author set excludes the first slice's commits, and
   a session that exits without committing is carried in the slice's author
   set. Not planned on these pages; they wait on a row the store does not have.

## Acceptance criteria

- [ ] `tests/test_sd_registry.py`: a test writes cost rows against
      `cap_usd_month`, and `reviewer_chain` passes over the bill, and `pick`
      on it refuses naming the bill and the month's total, carried to both
      as `capped_bills: Mapping[str, str]`, bill name to the exposure line
      (`design.md`, the API change).
- [ ] An integration test through `review` in `bin/sd-review`: an at-cap bill
      in the database reaches fallthrough, which passes over it, and
      `--provider` on it, which refuses; both with the call site wired and
      neither with `capped_bills` handed in by the test.
- [ ] A test starts two calls concurrently against room for exactly one; one
      goes, one is refused, and the settled rows sum under the cap.
- [ ] Four boundary tests through `review`: `sd_handoff_rows.library()`
      refusing (no `sd_db`) and `connect` refusing (a database that will
      not open), each once with an uncapped bill, which is dispatched as
      today, and once with a capped bill, which is refused naming the
      fault; no test bypasses the cap or blocks an uncapped review.
- [ ] A preflight test: `--preflight` on a capped `url` entry leaves one
      ledger row for the probe, `run` or `bound`, never none.
- [ ] A lifecycle test with a fake client: the row is `sending` when the
      client is called, `run` with the usage after a response that carries
      it, `bound` after a timeout, and no row exists after a `REFUSED`
      returned before the request is built.
- [ ] A test reads the recorded `tests/fixtures/minimax/token_plan_remains.json`
      (#1001), selects the `general` entry, writes two `meter` rows, and
      asserts the skip and the refusal with each window at zero in turn; a
      second asserts that a metered bill with no row, or a newest row older
      than the five-hour window, is skipped and refused the same way, naming
      the missing or stale reading; a third, one edited fixture per case,
      asserts that a missing `general` entry, two of them, and a window
      field that is missing, a string, a boolean, NaN, an infinity or
      outside 0 to 100 caps the bill naming the field and the value and
      writes no row.
- [ ] A pinned-meter test: `meter:` naming another scheme (the same-host
      `http://` value among the cases), host, port or path is refused naming
      the value and the pinned four, and no request is sent; a bill with
      `meter:` and no `meter_env:` is refused at registry read naming the
      bill.
- [ ] `grep -rn token_plan bin tests` counts more than 0 after slice 4.
- [ ] `make check` rc 0, and `bin/sd-docs-lint` ends `sd-docs-lint: clean`.

## References

- sd:10, criterion 6 and decision note 1942.
- sd:234 slice 8a, the system reservation ledger, `local-sd-db/sd_db/ledger.py`
  at system `4b240d28` (#406), and sd:234's prd, the claim paragraph.
- `WORKFLOW.md`, the `cap_usd_month` paragraph, which says the ceiling is
  recorded and not enforced; it changes when slice 3 lands.

## Log

- 2026-09-16 created, with the attribution audit measured at `2eafa78b`.
- 2026-09-16 planning review, five rounds: the ledger landed at system
  `4b240d28` and the pack's pin followed in #999, so slices 1 and 2 are
  done by other items; the lifecycle, the estimate's name, the meter's
  pin, credential, selection and order, and the boundary tests are the
  review's additions.
- 2026-09-16 slice 3 landed: `sd-review` charges every `url` call through
  `sd_db.calls.call`, a bill at its cap is passed over and refused by name,
  and a `url` entry on a capped bill without the bound's inputs is refused
  at read; the two meter tests of 3a move to slice 4, for the reason
  measured on that step.
