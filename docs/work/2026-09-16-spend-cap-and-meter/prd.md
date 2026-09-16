---
title: The registry enforces the spend cap and reads the minimax meter
created: 2026-09-16
---

# PRD — spend cap and meter

## Problem

sd:10's criterion 6 was closed with three parts deferred to this item by the
owner's decision note 1942 (2026-09-14): the `minimax` meter, the spend cap,
and an audit of the attribution clauses whose names `SD_AUTHOR` and
`slice_base` have no hits in `bin/` or `tests/`. The deferral is recorded on
sd:10's pages
(`2026-09-05-the-pack-runs-a-team-process-for-one-person/prd.md:1348-1351`);
the item itself had no page of its own, so this is its plan of record.

Measured 2026-09-16 at pack `2eafa78b` and system `a5347185`, with
`grep -rn -F <name> bin tests skills docs .github WORKFLOW.md` per name:

| Name | `bin/` | `tests/` | Elsewhere | What that means |
|---|---|---|---|---|
| `token_plan` | 0 | 0 | 8 in sd:10's pages, 2 in `WORKFLOW.md` | nothing reads the meter |
| `capped_bills` | 4, all `bin/sd_registry.py` | 4 | 1 in sd:10's `prd.md` | the refusal exists and has no production caller |
| `cap_usd_month` | 8 | 3 | `WORKFLOW.md` says "a recorded ceiling, not an enforced one" | the cap is stored, not enforced |
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
| `SD_AUTHOR=nosuch` is refused at commit naming the registry | Under another name: `--author nosuch` is refused with the registry's read error, or as "not an enabled author provider" | `source:bin/sd-ship::commit_paths` |
| The trailer forms the design page documents equal the forms `sd_lib.py` writes and reads, enumerated from the source | Unimplemented: no test reads the design page. The forms are the constants | `source:bin/sd_lib.py::AUTHORED_TRAILER`, `source:bin/sd_lib.py::ATTRIBUTES_TRAILER` |
| One `claude` and one `codex` trailer resolve to the first entry of neither vendor | Implemented in two halves: the scan returns both vendors, and the chain skips every entry of an author vendor | `FixReviewTests` in `tests/test_sd_review_ship.py`, "every actual squash author vendor is excluded"; `TheReviewerChain`, "an entry of the author's vendor is skipped" |
| No trailer and no `--author` is refused naming the flag | Implemented; the refusal names `sd attribute`, not `--author` | `source:bin/sd_lib.py::author_vendors`; `FixReviewTests`, "fix commit with no author trailer is refused" |
| An untagged commit before a tagged one is refused naming the commit and `sd attribute`; `sd attribute <sha> claude` resolves it, the attributing commit carrying `Authored-with: human` | Implemented | `source:bin/sd_lib.py::attribute`, `source:bin/sd::cmd_attribute`; `TheRoundTripTests` in `tests/test_sd_attribute.py` |
| A rebase refuses again; `sd attribute <from>..<to> claude` resolves it; the commit is asserted on the fixture remote after the push | Implemented up to the push; no test pushes | `TheRangeTests` in `tests/test_sd_attribute.py`, "a rebase loses the claim and one range attribution restores it" |
| Two slices, the first squashed and the default merged back, resolve by `slice_base`; a fresh branch from the default resolves the same | Under another name, in part: `authorship_base` is the merge base with the default, carried across passes by `sd-ship`. No row records a slice head, so a branch continued after its squash still scans the first slice's commits | `review` in `bin/sd-review` sets `authorship_base`; `source:bin/sd-ship::review_history` carries it |
| A session that edits and exits without committing adds its vendor to the row's `authors` (rounds 44 to 46) | Unimplemented. The only `authors` in `bin/` is the `authors` policy line of `.github/sd-review.json`, which is the consent clause, not a session row | `source:bin/sd-review::DEFAULT_POLICY` |
| Two clones attributing two commits of one branch both push without force | Designed, unasserted: the attribution is a commit and not a note, so the two do not diverge on a shared ref | `source:bin/sd_lib.py::attribute`, the docstring |
| `sd attribute <sha> human` on an untagged branch resolves to the first enabled entry | Implemented | `TheRoundTripTests`, "human writes the bare word and contributes no vendor" |
| `sd-review --author claude` is refused as not a review flag | Implemented by omission: `bin/sd-review` declares no `--author`, so `argparse` exits 2. No test names it | `bin/sd-review`, the parser |
| `SD_AUTHOR=codex` in the review's environment changes nothing | Cut: nothing reads `SD_AUTHOR`, so there is nothing to assert | `grep` above |

Disposition: three clauses are cut here rather than carried, because their
names describe a mechanism the pack did not build and does not need. The
`SD_AUTHOR` variable is `--author`; the environment clause is void with it;
the trailer-forms-equal-the-design-page test asserts a page against constants
and is a documentation check, not a behaviour. The `slice_base` and session
`authors` clauses stay open as requirement 5, because a branch continued after
a squash is a real shape (`sd-ship` merges by squash) and the scan today
reads the first slice's commits again.

## Requirements

1. The system library reserves each call's bound against the month's settled
   and reserved rows in one transaction, and refuses the call when the bound
   would pass `cap_usd_month`. This half is sd:234 slice 8a, delivered as
   `local-sd-db/sd_db/ledger.py` with `reserve`, `claim`, `settle`, `lose`,
   `release_orphans` and `exposure`. At `a5347185` that module does not exist
   yet; this item consumes it and does not build it.
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
      on it refuses naming the bill and the month's total.
- [ ] A test starts two calls concurrently against room for exactly one; one
      goes, one is refused, and the settled rows sum under the cap.
- [ ] A test reads a recorded `token_plan/remains` fixture, writes two `meter`
      rows, and asserts the skip and the refusal with each window at zero in
      turn.
- [ ] `grep -rn token_plan bin tests` counts more than 0 after slice 3.
- [ ] `make check` rc 0, and `bin/sd-docs-lint` ends `sd-docs-lint: clean`.

## References

- sd:10, criterion 6 and decision note 1942.
- sd:234 slice 8a, the system reservation ledger.
- `WORKFLOW.md`, the `cap_usd_month` paragraph, which says the ceiling is
  recorded and not enforced; it changes when slice 3 lands.

## Log

- 2026-09-16 created, with the attribution audit measured at `2eafa78b`.
