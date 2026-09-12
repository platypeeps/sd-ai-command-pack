---
title: the citation gate has four silencers and none of them say anything
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

**Re-measured 2026-09-12, at implementation, per criterion 3.** The table above
is a snapshot from 2026-09-04 and every figure in it has moved. It is kept
because an item about a gate that hides things should not hide that its own
numbers drifted. What holds now, printed by the module on every run:

| bucket | live | archived | total |
|---|---:|---:|---:|
| `compared` | 38 | 15 | **53** |
| `no-adjacent-anchor` | 322 | 2,410 | 2,732 |
| `elided-path` | 176 | 2,180 | 2,356 |
| `archived-stale` | 0 | 277 | 277 |
| `anchor-not-a-symbol` | 13 | 131 | 144 |
| `separator-not-adjacent` | 20 | 114 | 134 |
| `declared-absent` | 1 | 0 | 1 |
| `target-missing` | 0 | 0 | **0** |
| `escapes-checkout` | 0 | 0 | **0** |
| `quoted` | 1 | 0 | **1** |
| | | | **5,698** |

Corpus: 1,096 tracked markdown files, `CHANGELOG.md` excluded by name. The
compared population was **36** under the predecessor's corpus immediately
before this work and is **53** after it, of which 38 are live. Two of the
seventeen were found by widening to the parenthesised comma, and both were
stale: `CITATION_RE` cited at `bin/sd-docs-lint:306` when it is at 351, and
`MODES` cited at `bin/sd_lib.py:32` when it is at 38. Neither was reachable
before. That is criterion 4 paying for itself on the day it landed.

`target-missing` and `escapes-checkout` are both empty, which is the reason
`make check` stays green through this change rather than a claim that nothing
is wrong: the one live missing target is criterion 2's, and it carries
`[absent: ...]`.

The last row is zero *today* and that is not reassuring, because it was 1 an hour
ago. The 24th comma-shaped citation in this repository was in the first draft of
**this PRD**, and vanished when the draft was rewritten. The document was inside
its own corpus and its own count. Anything reading the table above as a standing
measurement rather than a snapshot will be wrong by the time it reads it, which
is why criterion 3 exists.

**Re-measured 2026-09-07 on `405a9106`, and the table has already moved.** The
punctuation-alone row is 3, not 0; the archive row is not reproducible at 21
under any definition tried; and the largest silent class in the repository is
not in this table at all. The corrections, the commands that produced them and
what each one changes are in `design.md` under "What the PRD got wrong the
second time" — one copy, in the page that derived them, because a second copy
here is the failure mode this section is already about.

**The fourth cost four rounds.** During #732 one citation written
`` (`sym`, `path:line`) `` went stale **four times** across four review rounds
while `make check` passed green each time. Every other citation in that same file
was caught on the first run. The gate was working; that one line was invisible to
it, and nothing distinguished "checked and correct" from "never looked at".

`PAIR` is anchored deliberately — `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` (`source:tests/test_doc_citations.py::test_prose_between_a_symbol_and_a_citation_breaks_the_anchor`) asserts that a symbol and a citation
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
  `anchored_citations` (`source:tests/test_doc_citations.py::anchored_citations`) skips by path part
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
CI read a file of its choosing, and `test_a_citation_cannot_send_this_test_outside_the_checkout` (`source:tests/test_doc_citations.py::test_a_citation_cannot_send_this_test_outside_the_checkout`) defends that. It must stay.

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
   `test_the_scan_reaches_the_documents` (`source:tests/test_doc_citations.py::DocCitationTests`)
   already exists for this reason and asserts only that the count is non-zero.

## Open questions

1. **Answered 2026-09-07 — narrow it.** Should a stale citation in an
   **archived** item fail? Archived items are historical records; a citation
   into a file that has since moved is arguably correct-as-of-writing. But
   "we never look" is not the same answer as "we decided not to". *Decision:
   archived citations are compared and a stale one is reported, not failed —
   a new `archived-stale` reason and a census line, nothing red.* Measured, the
   population is **17** stale citations in three items, not the 21 this list
   originally claimed; that figure is not reproducible under any definition
   tried and `design.md` records the three that were.
2. **Answered 2026-09-07 — widen, and exclude `CHANGELOG.md` by name.** Should
   the corpus include `CHANGELOG.md`? It carries a citation into
   `internal/review/rules.go`, which has never existed in this repository.
   *Decision: the corpus becomes every tracked markdown file, asked of git, and
   `CHANGELOG.md` is excluded by name carrying rule 7's stated reason — the
   changelog names paths as they were at the time, the one place a reference
   that no longer resolves is still correct.* It holds **8** tokens, not the
   one this list assumed, six naming paths that do not exist.

   Both answers take the same shape, and it is the operator's ruling of the
   same day: take the coverage, and do not buy it by editing the historical
   record. The rejected options each did the opposite — one left the gate
   blind on purpose, the other paid for sight by rewriting archived documents.
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

- **C-34, found 2026-09-07 while repairing rule 6 after an unrelated edit.**
  Rule 6 checks that a recorded citation's *target* text is still at the
  recorded line. It never checks that the *citing* line still carries the
  citation. A row whose citation was deleted from the citing file therefore
  stays in `.citations.tsv` and keeps passing, because the target it names is
  untouched and nothing re-reads the source.

  Measured, not supposed. Item A's manifest held 25 rows; four of them —
  `implement.md:789` citing `prd.md:988-1002`, `:791` citing `:1600-1602`,
  `:795` citing `:997-999`, and `:802` citing `:959` — name citations that are
  absent from `implement.md` at `HEAD`, not only from the working tree:
  `git show HEAD:.../implement.md | grep -c '988-1002'` returns `0` for all
  four. They passed rule 6 on every run until an edit to `prd.md` moved the
  targets, at which point they failed as though they were live citations that
  had drifted. `--update-citations` then dropped them, correctly, and the
  count fell 25 to 21 with no other row changing.

  Two consequences, and the second is the one that matters. A deleted citation
  leaves a row that reports a false failure later, which is noise. Worse, the
  count in the manifest overstates how much of a page is actually cited, so
  "checked 24 citation(s)" is a number nobody can act on: it counts rows, not
  citations that exist. This is the same defect class this item already carries
  — the gate skipping what it cannot match — arriving from the other side: the
  gate *keeping* what no longer exists.

  Fix belongs with step 2's census, which already has to return bucket counts
  and conserve them. A row whose citing line no longer carries its citation is
  a bucket of its own, reported and dropped, rather than a silent survivor or
  a failure blamed on the target.
