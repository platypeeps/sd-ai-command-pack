---
title: the citation gate has four silencers and none of them say anything
status: planning
created: 2026-09-04
---

# PRD — a gate that skips silently is a gate that passes

## Problem

`tests/test_doc_citations.py` validates that a `path:line` citation in the docs
still points at the symbol it names. When it declines to validate one, it says
nothing — the citation is indistinguishable from prose that contains no citation
at all. There are **four independent ways** to be declined, and this item exists
because they were found one at a time, by being bitten, rather than by reading
the file.

Measured against the merged tree, over every `*.md` in the checkout:

| Why a citation is not validated | Comma-shaped ones | Announced? |
|---|---|---|
| lives outside `docs/` — the corpus glob is `docs/**/*.md` | 1 (`CHANGELOG.md`) | no |
| lives under `docs/**/archive/**` — skipped by path part | 21 | no |
| names a file that does not exist — `is_inside_repo` requires `is_file()` | 1 | no |
| **punctuation alone** — `PAIR`'s `\s*` is not a comma, and nothing else would have skipped it | **0** | no |
| | **23** | |

The last row is zero *today* and that is not reassuring, because it was 1 an hour
ago. The 24th comma-shaped citation in this repository was in the first draft of
**this PRD**, and vanished when the draft was rewritten. The document was inside
its own corpus and its own count. Anything reading the table above as a standing
measurement rather than a snapshot will be wrong by the time it reads it, which
is why criterion 3 exists.

**The fourth cost four rounds.** During #732 one citation written
`` (`sym`, `path:line`) `` went stale **four times** across four review rounds
while `make check` passed green each time. Every other citation in that same file
was caught on the first run. The gate was working; that one line was invisible to
it, and nothing distinguished "checked and correct" from "never looked at".

`PAIR` is anchored deliberately — `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor`
(`tests/test_doc_citations.py:145-154`) asserts that a symbol and a citation
separated by prose do *not* match, so the anchoring is a design decision with a
test defending it, not an oversight. What has no test is the case where a real
citation is written in a shape the anchor rejects.

## What the first draft of this PRD got wrong

Recorded rather than deleted, because it is the same error the parent item's
review found four times over.

This PRD originally claimed that widening `PAIR` to accept the comma would
"turn 23 silent skips into 23 permanent red failures" against retired-stack files.
That is false, and review said so. It was written from the 24-citation grep
without checking what the gate does with each one. Measured:

- 21 are under `docs/**/archive/**`, which
  `anchored_citations` (`tests/test_doc_citations.py:79-101`) skips by path part
  regardless of regex.
- 1 is in `CHANGELOG.md`, which the corpus glob never reaches.
- 1 names a file deleted with the retired stack, which `is_inside_repo` skips.
- **1** was in a live document naming a file that exists — this PRD's own first
  draft, which quoted the parent item's citation while explaining it.

So widening `PAIR` would have newly checked **one** citation, and that one
passed. The change is cheap and nearly free of blast radius — the opposite of
what this PRD asserted before anyone ran it. Rewriting the draft removed that
citation, so the same measurement now returns 23 and zero, which is the strongest
possible argument for criterion 3: a count taken once is a count that was true
once.

The claim was written the way the parent item's C-22, C-25, C-30 and C-33 were
written: confidently, about behaviour nobody had executed. It is left standing
here because an item about a gate that hides things should not open by hiding
that its own premise was wrong.

## The finding that survives, and is larger

The interesting silencer is the third, not the fourth.

`is_inside_repo` exists for a real reason, stated in its own comment: `REPO_ROOT / path`
follows `..` out of the tree, so an edit to any document under `docs/` could make
CI read a file of its choosing, and `test_a_citation_cannot_send_this_test_outside_the_checkout`
(`tests/test_doc_citations.py:132-143`) defends that. It must stay.

But it answers two questions with one `continue`. *"This path escapes the
checkout"* is a security refusal and should be silent. *"This path is inside the
checkout and does not exist"* is a **stale citation** — precisely what the gate
was built to catch — and it is discarded through the same branch.

There is a live instance today, in the adjacent form, fully matched by `PAIR`,
skipped anyway:

```
docs/spec/backend/manifest-and-filesystem.md
  `_candidate_refresh_required` -> prepare-release.py    (file does not exist)
```

The same document says elsewhere that the script was *"removed with the release
train in 0.72.0"*. The gate holds both the citation and the evidence it is dead,
and reports neither.

## Acceptance criteria

1. A citation naming a path **inside** the checkout that does not exist fails, or
   is reported. A citation naming a path **outside** the checkout stays silent.
   The two are distinguished; today one `continue` serves both.
2. `docs/spec/backend/manifest-and-filesystem.md`'s `prepare-release.py` citation
   is resolved — corrected, marked historical, or removed — and whichever it is,
   the mechanism generalises to the next one.
3. Every count in this PRD is re-measured from the filesystem at implementation
   time rather than read from the table above, which is a snapshot and will drift.
4. A citation written in the comma shape either validates or fails. It must not
   skip. Asserted directly, beside `PAIR`'s existing self-tests.
5. The archive and corpus-glob exclusions are decided deliberately: kept with a
   stated reason, or narrowed. They are currently silent by accident of ordering,
   not by an argument anyone wrote down.
6. `make check` green, and the number of citations actually *validated* is
   reported rather than assumed — the control test
   `test_the_scan_reaches_the_documents` (`tests/test_doc_citations.py:116-130`)
   already exists for this reason and asserts only that the count is non-zero.

## Open questions

1. Should a stale citation in an **archived** item fail? Archived items are
   historical records; a citation into a file that has since moved is arguably
   correct-as-of-writing. But 21 comma-shaped citations sit there unexamined, and
   "we never look" is not the same answer as "we decided not to".
2. Should the corpus include `CHANGELOG.md`? It carries a citation into
   `internal/review/rules.go`, which has never existed in this repository.
3. **Can a document quote a citation without making it a claim?** Found by being
   caught: this PRD's first draft reproduced `PAIR`'s own self-test verbatim, and
   `make check` failed on *this file* — the example was written for a different
   repository, so quoting it asserted something false about this one. The gate
   cannot tell a citation from a quotation of one, which means a document
   explaining the gate cannot show an example. Some way to write a deliberately
   inert citation is wanted.
4. Are there shapes beyond the comma? The comma was found by a reviewer reading
   the regex, not by a test. That reading should be finished rather than stopped
   at its first hit: an em dash, a semicolon, a bare "and", a line break landing
   between the halves.
