---
title: the citation gate skips a citation shape it cannot match, and says nothing
status: planning
created: 2026-09-04
---

# PRD — a gate that skips silently is a gate that passes

## Problem

`tests/test_doc_citations.py` validates that a `path:line` citation in the docs
still points at the symbol it names. It finds citations with one regex:

```python
PAIR = re.compile(r"`([^`\n]+)`\s*\(?`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`")
```

`\s*` matches whitespace. It does not match a comma. So a citation written

```markdown
(`test_the_dashboard_stays_under_its_ceiling`, `tests/test_loc_caps.py:215-226`)
```

is not matched, is not validated, and **produces no complaint** — it is
indistinguishable to the gate from prose that contains no citation at all.
Confirmed directly:

```
as written      -> NO MATCH (skipped by CI)
adjacent form   -> MATCH  anchor=test_the_dashboard_stays_under_its_ceiling
```

This is not hypothetical damage. During #732 a single citation in that comma
shape went stale **four times** across four review rounds while `make check`
passed green each time. Every other citation in the same file was caught by the
gate on the first run. The gate was working; that one line was invisible to it.

The file already knows this is the failure mode it must avoid — `PAIR` has a
dedicated self-test at `tests/test_doc_citations.py:153-154` asserting the regex
does *not* tolerate arbitrary text between the two backticked halves. It runs
`PAIR.search` over two strings built from the same symbol and the same file
reference: the adjacent form, asserted to match, and the two halves separated by
the words "is reported by", asserted to return `None`. (They are described rather
than quoted, for the reason immediately below.) That test defends against a regex
too *loose*. Nothing defends against a citation too loose for the regex.

**A third property, found while writing this PRD.** The paragraph above originally
reproduced those two assertions verbatim, as a `python` code block. `make check`
then failed on *this file*:

```
docs/work/2026-09-04-the-citation-gate-skips-what-it-cannot-match/prd.md:
  `status_filter` is not at bin/sd:1378
```

The gate cannot distinguish a citation from a quotation of a citation. Quoting the
regex's own example inside a document makes it a live claim about this repository,
and it is false here because the example was written for a different one. That is
its own question — see below — and it is recorded rather than merely worked around,
because it is the second thing this gate does that nobody had written down.

## Why this is not a one-line regex change

Adding `,?` to `PAIR` is the obvious fix and it is a trap. A repo-wide sweep for
the comma shape finds **24** citations:

| Where | Count | State of the cited file |
|---|---|---|
| `docs/work/2026-09-02-dashboard-ack-and-mutation-count/prd.md` | 1 | live — already fixed in #732 |
| `CHANGELOG.md` | 1 | `internal/review/rules.go` — never existed in this repo |
| `docs/work/archive/**` | 22 | mostly the retired stack: `install.py`, `installer/registry.py`, `review-local.py`, `templates/scripts/*` |

Widening the regex turns 23 silent skips into 23 red failures pointing at files
that were deleted when the thin-only install landed. The gate would be correct and
the build would be permanently broken, which is a worse gate than the one that
skips.

So the question this item exists to answer is not "how do we match the comma" but
**"what should a citation into a file that no longer exists do?"** — and that
question has to be answered before the regex moves.

## What the gate currently does about missing files

Unknown, and it must be established before anything else. `test_doc_citations.py`
has a guard (`tests/test_doc_citations.py:119-124`) asserting the corpus was
reached and at least one citation compared — a defence against `PAIR` matching
nothing at all. Whether a matched citation into a nonexistent path fails, skips or
throws is the first thing to find out, because it determines whether archived
items can be validated at all.

## Acceptance criteria

1. The behaviour of a citation into a deleted file is established by experiment
   and written down, before any regex changes.
2. Every one of the 24 comma-shaped citations is enumerated from the filesystem —
   not from the list in this PRD, which is a snapshot and will drift.
3. A decision is recorded on archived items: validated, exempted by path, or
   exempted by a frontmatter marker. Whichever it is, the reason is in the record.
4. After the change, a citation written in the comma shape either validates or
   fails. It must not skip. A test asserts this directly, in the same place
   `PAIR`'s existing self-test lives.
5. `make check` is green with no citation newly exempted by accident — the count
   of *validated* citations goes up, and the number is asserted or reported.

## Open questions

1. Should the comma shape be **accepted** (widen `PAIR`) or **rejected** (a
   separate test that fails on comma-shaped citations, forcing the adjacent form)?
   Rejecting is stricter and keeps one canonical spelling; accepting is kinder to
   prose that reads better with the comma.
2. Are there other shapes the gate skips? The comma was found by a reviewer
   reading the regex, not by a test. The same reading should be finished rather
   than stopped at the first hit — an em dash, a semicolon, `and`, a line break
   between the halves.
3. Does `CHANGELOG.md` belong in the corpus at all? It cites a `.go` file from
   another project.
4. Should a citation inside a fenced code block be validated? Today it is, which
   is why this PRD could not quote the gate's own test. The argument for keeping
   it: a code block is where a citation is most likely to be copied from and go
   stale. The argument against: a document explaining the gate cannot show an
   example, and a document quoting another repository's code is making a claim
   about this one. Whichever way it goes, it wants a way to write a citation that
   is deliberately inert.
