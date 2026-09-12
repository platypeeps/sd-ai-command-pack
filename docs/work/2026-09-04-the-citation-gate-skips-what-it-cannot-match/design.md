# Design — a gate that skips silently is a gate that passes

## Approach

### First, the size of the thing

Every number below was measured on this worktree at `405a9106`, by walking
`git ls-files -- '*.md'` and re-implementing the gate's own predicates against
it. None is copied from the PRD's table, which criterion 3 already warns is a
snapshot; where the two disagree the disagreement is recorded rather than
smoothed over, in "What the PRD got wrong the second time" below.

The gate applies five filters in source order, each a `continue` or a
non-entry, and none of them counts what it dropped:

| # | filter | keeps | drops |
|---|---|---|---|
| 1 | `glob("docs/**/*.md")` | 977 files | 112 files, 8 `path:line` tokens |
| 2 | `"archive" in doc.parts` | 24 files | 953 files, 2,947 tokens |
| 3 | `PAIR.finditer` | 52 matches | 306 of the 358 tokens in the survivors |
| 4 | `is_symbol(anchor)` | 45 | 7 |
| 5 | `is_inside_repo(target)` | 44 | 1 |

Filter 3's 306 is counted against `PAIR`'s own path class, which requires at
least one character before the colon. The classification below does **not**
adopt that class, and the difference is the largest single finding on this
page: an elided-path citation such as `` `:391-414` `` is a `path:line` token
that `PAIR` cannot see, so counting the corpus with `PAIR`'s class hides the
very population the census exists to reveal. The enumerator the census uses is
written down in the next section, and under it the live corpus holds **520**
tokens at `405a9106`, not 358. The 358 is the right denominator for the
sentence "what does today's gate walk past"; 520 is the right denominator for
"how many citations are there". Both appear below and each is labelled.

**Forty-four.** The checkout holds 3,313 backticked `path:line` tokens across
1,089 tracked markdown files, and the gate compares 44 of them — 1.3%. Zero of
the 44 are stale today. That is the whole reading, and it is the reason this
item is not a regex patch: the PRD's four silencers are real, but three of them
are filters 1, 2 and 5, and the largest single loss by an order of magnitude is
filter 3, which the PRD counted at zero.

### Criterion 5: the ordering that causes the silence

The exclusions are not silent because anyone argued for silence. They are
silent because the enumeration is a **filter chain rather than a
classification**, and the only control over it is a non-emptiness assertion.

`anchored_citations` (`source:tests/test_doc_citations.py::anchored_citations`) is a loop whose every
rejection is a `continue` into the next iteration. Nothing accumulates. The
list it returns holds survivors and carries no record of the population it was
drawn from, so no caller can ask how many were dropped, and none does.

The control is `test_the_scan_reaches_the_documents` (`source:tests/test_doc_citations.py::test_the_scan_reaches_the_documents`). Its own docstring explains, correctly, why
it must not assert a count: "asserting *how many* citations exist makes the
control fail whenever the prose is reorganised". So it asserts two
non-emptinesses instead — the document list is not empty, and the citation list
is not empty. Measured against the chain above, the first passes at 24 and the
second at 44. **Both would still pass at 1.** A tightened `PAIR`, a moved
document tree, an accidental `docs/spec/**` glob: any of them could take the
chain from 44 to 1 and every test in the module would stay green.

That is the ordering argument criterion 5 asks for, and it settles the shape of
the fix. The chain does not need reordering. It needs to stop being a chain.

### The chain becomes a classification

`anchored_citations` returns a row for **every** `path:line` token it finds in
its corpus, not only the ones it kept. Each row carries a `reason` drawn from a
closed vocabulary:

- `compared` — the anchor was checked against the cited line.
- `escapes-checkout` — the path resolved outside the tree. Silent by design,
  and the only one of these that is a security refusal.
- `target-missing` — the path is inside the tree and there is no file there.
  This is a stale citation and it fails; see criterion 1 below.
- `declared-absent` — the same, but the citation carries `[absent: <reason>]`.
  Not a failure, and not the same bucket, because the marker is a claim that
  can itself go stale; see criterion 2.
- `anchor-not-a-symbol` — the token before the citation is a path or a phrase,
  so there is nothing to check a line against.
- `elided-path` — the citation names a line and no file, because the prose
  named the file already. It is a token, it is not anchorable, and it is the
  largest bucket after `no-adjacent-anchor`; see question 4 below.
- `separator-not-adjacent` — the citation is preceded by a backticked token
  with exactly one comma or semicolon between them, matched by `SEPARATED_PAIR`
  and by nothing looser. This is question 4's whole subject and it needs its
  own bucket: folded into the one below, the comma population would be
  uncountable, which is how it stayed at "0" for three days. The definition is
  a named regex rather than a character distance on purpose — a distance bound
  was tried first, and sweeping the bound from one character to ten moved the
  bucket from 0 to 132 with no principled stopping point, which is not a
  classification, it is a dial.
- `no-adjacent-anchor` — the citation matched no anchoring shape at all.
- `quoted` — the citation carries `[quoted: <reason>]`; see criterion 3.

### The enumerator, written down

Three things the first draft of this page left to the reader's imagination, each
of which a reviewer found by trying to implement it:

**`TOKEN` is `` `([A-Za-z0-9_./-]*):(\d+)(?:-(\d+))?` ``** — `PAIR`'s path
class with `+` relaxed to `*`, so the elided form is enumerated. `tokens_found`
in the conservation assertion means the matches of exactly this pattern and
nothing else. The relaxation is what admits a non-citation, so it was measured:
across the live corpus it adds 166 matches, **all 166** of them the elided
form, and it introduces zero matches whose path is neither a file name nor
empty. The nearest thing to a false positive in the tree is a backticked ISO
timestamp, and `` `2026-09-06T19:11:39Z` `` does not match either form, because
the seconds field puts a colon where the pattern needs a closing backtick. A
timestamp written to minute precision would match; there is none in the
checkout, and the census would show it as a `no-adjacent-anchor` row rather
than as a silent drop, which is the point of counting rather than filtering.

**One row per token, keyed by offset.** A citation's anchor can itself be a
`path:line` token: `` (`bin/sd-review:514`, `skills/sd-review/SKILL.md:39`) ``
is one `PAREN_PAIR` match containing two `TOKEN` matches. 4 of the 7 live
`PAREN_PAIR` matches are this shape. The rule is that classification iterates
over `TOKEN` occurrences, not over anchor-citation pairs: the subject token
gets `compared`, the anchor token gets its own row on its own terms, and no
token is consumed by being another token's anchor. Without that rule the
buckets under-count against the corpus and conservation fails on the real tree
rather than on a fixture.

**The marker read is line-aware, and the flattening does not prevent it.**
`anchored_citations` flattens with `.replace("\n", " ")`
(`tests/test_doc_citations.py:377`), which a reviewer read as making 0.71.34's
"same line" rule unimplementable. It does not: the substitution is one
character for one character, so offsets in the flattened text are offsets in
the original. `marker_after()` matches against the flattened text and then
asserts `"\n" not in raw[citation_end:marker_end]`. The grammar keeps its
line-terminator clause and the negative fixture "a marker on the next line does
not exempt" can fail, which under a genuinely lossy flatten it could not.

**`classify()` takes its corpus as a parameter.** `anchored_citations()` is
nullary today: it reaches for `REPO_ROOT.glob` itself, so nothing in the module
can be run against anything but this repository as it happens to stand.
`classify(docs)` defaults to the live glob and accepts a list, for the reason
the sweep item gave for handing `scan()` its branch set rather than letting it
build one — a function that fetches its own input can only be tested against
whatever it fetches, and the reasons that matter most here are the ones with no
instance in the tree today. `escapes-checkout` has zero live instances and
`quoted` will have zero until step 7; without an injectable corpus neither
branch is reachable in a test, and the conservation assertion would be proved
only on the shapes that happen to exist.

Two things then become assertable that are not assertable today, and neither is
a count:

**Conservation.** Every token in the corpus lands in exactly one bucket. The
sum of the buckets equals the number of tokens found, and no row carries a
reason outside the vocabulary. This cannot drift when prose is reorganised —
it is a partition property, not a threshold — and it is exactly what would have
caught each of the four silencers on the day it was introduced rather than one
at a time by being bitten.

**Reporting.** Criterion 6 asks for the number actually validated rather than
assumed. `census()` returns the bucket counts, the control test prints one line
of them, and `.github/scripts/run-tests.sh` does not pass `-b`, so that line
lands in `unittest-output.log` on every run. Today the module's own report of
its coverage is the absence of a failure.

### Criterion 1: the two questions inside one `continue`

`is_inside_repo`, now split and gone under that name
(`source:tests/test_doc_citations.py::is_under_repo`), returned
`resolved.is_file() and resolved.is_relative_to(REPO_ROOT.resolve())`. The
second conjunct is the security refusal the PRD defends and it must stay
exactly as it is. The first is a staleness test wearing the refusal's clothes.

They separate into `is_under_repo(target)` — containment only, **keeping the
`resolve()`**, and the sole
subject of `test_a_citation_cannot_send_this_test_outside_the_checkout` (`source:tests/test_doc_citations.py::test_a_citation_cannot_send_this_test_outside_the_checkout`) — and a plain `target.is_file()` at the
call site. A path that is not under the checkout is dropped as
`escapes-checkout`, silently and forever. A path that is under the checkout and
is not a file is `target-missing`, and `target-missing` fails.

Measured blast radius of turning `target-missing` red: **one citation in the
whole live corpus**, and it is criterion 2's:

```
docs/spec/backend/manifest-and-filesystem.md
  `_candidate_refresh_required` -> prepare-release.py:109-160
```

Measured blast radius of the security branch, over the same corpus: **zero**.
No citation anywhere under `docs/` resolves outside the checkout. The branch
has never fired on real content and its only coverage is the three synthetic
fixtures in the test named above. Splitting the predicate is what lets that
stay true and visible rather than being inferred from a silence shared with a
live defect.

### Criterion 2 and question 3: the marker already exists

Before inventing an escape hatch, three were found in the tree.

`bin/sd-docs-lint` carries two. Rule 7's `METAVARIABLE_RE`
(`source:bin/sd-docs-lint::METAVARIABLE_RE`) exempts a reference by its **shape** — a token holding
`YYYY`, `MM`, `DD` or `<` is a pattern and not a path — with the stated reason
that "a new template invents no new exception, and a real path can never
contain one". Rule 6's `LOG_HEADING_RE` (`source:bin/sd-docs-lint::LOG_HEADING_RE`) exempts by
**region**: `item_citations` (`source:bin/sd-docs-lint::item_citations`) stops reading at a `Log`
heading, because "a Log entry is a dated record of what a page said on the day
it was reviewed, so its citations are quotations and not claims". That is
question 3's distinction, already drawn, already implemented, for a different
rule.

The third is the one that fits. `[absent: <reason>]`, written immediately after
a reference on the same line, was specified in 0.71.34 for the retired stack's
`checkDocumentationPathReferences`, with a grammar that is still written down
in `CHANGELOG.md` — the reason is required, `[absent:]` and `[absent: ]` leave
the reference checked, the reason may not span a line terminator, and the
exemption covers only the one reference it follows. It is in live use here: 94
markers across the checkout before this item wrote any, 32 of them outside
`archive/` and 22 of those in `docs/spec/backend/manifest-and-filesystem.md`
alone. **The convention outlived its enforcer.** Criterion 2's citation
already carries one; the gate simply does not read it.

So the design adds no new device. It teaches the gate the marker vocabulary
that this repository already writes, with exactly two verbs:

| marker | claim | gate behaviour | fails when |
|---|---|---|---|
| `[absent: <reason>]` | the target is gone and that is expected | not opened | the target **exists** |
| `[quoted: <reason>]` | this is an example, not a claim | not opened | the reason is empty |

`[absent: ...]` is not a mute button, and the third column is why: it asserts
absence, so it goes red when the file comes back. A citation marked absent
whose target has returned is exactly as wrong as a stale line number, and
today nothing would notice.

`[quoted: <reason>]` is the new verb, and it is the one question 3 wanted. A
document explaining the gate can then show a citation in the shape being
discussed, mark it quoted with the reason, and have the gate count it in the
`quoted` bucket rather than silently fail to parse it. Unlike everything else
in the vocabulary it is unfalsifiable by construction, so three things hold it
down: the reason is required by the same grammar `[absent:]` uses; it appears
in the census on every run, so its population is a number a reader can watch;
and it covers one citation, not a document, a region or a path.

**Rejected, and why.**

**Delivered, and demonstrated here rather than described.** This page can now
show the literal shape it is about. `frontmatter` (`bin/sd:1231`) [quoted: tests/test_doc_citations.py:377]
is a real citation, written with its real line number, carrying a marker that
tells the gate it is an example. It lands in the `quoted` bucket and is
counted; the marker's own reason is a `path:line` and is checked like any
other citation, so the escape hatch is falsifiable too. That this paragraph
survives `make check` is question 3's acceptance test, and no fixture could
have been it.

*A metavariable line number* — `` `bin/sd:NN` `` — reusing rule 7's own device.
It is genuinely the closest precedent and it is what this document was forced
to use before the marker existed. Rejected on two counts. It is silent: a
metavariable citation fails to match and is therefore indistinguishable from
prose, which is the disease this item exists to treat. And it destroys the
example: the point of quoting a shape is to show the literal characters, and a
citation whose line number is not a number is no longer the shape under
discussion.

*Exempting fenced code blocks.* Rejected. It is a region exemption with no
per-citation scope, so it silences citations that are claims — the manifest
spec's citations at lines 928 and 985 sit inside indented blocks — and it is
invisible at the point of use, which is the failure criterion 5 names. Rule 6's
`Log` exemption is a region too, but it is a region whose whole content is
dated quotation by definition; a code fence is not.

*A frontmatter opt-out on the document.* Rejected outright: whole-document
blast radius, and it is `optionalReferencePaths` again — the repository-wide
array 0.71.34 replaced, for precisely this reason.

*Breaking the adjacency deliberately*, by writing prose between the symbol and
the citation. Rejected. It works, it is what the PRD's rewritten draft actually
did, and it makes a silencer load-bearing. It also leaves no trace: a reader
cannot tell a sentence that was phrased that way on purpose from one that
happened to be.

### Criterion 4 and question 4: the comma, measured

The PRD says widening `PAIR` to accept the comma is "cheap and nearly free of
blast radius". Measured on today's tree, the first half is right and the second
half is wrong, and the correction changes the design.

Three punctuation-shaped near misses exist in the live corpus — a citation
whose anchor is a symbol, whose target exists, and where the only thing between
the two halves is a mark. All three are in one item. Their verdicts under a
naively widened `PAIR`:

| separator | verdict | what it actually is |
|---|---|---|
| comma, inside a parenthesis | PASS | a real anchored citation |
| comma, bare | FAIL | a comma-separated **list** of citations |
| semicolon, bare | FAIL | a semicolon-separated list of bugs |

The two failures are not stale citations. They are citations whose anchor is
the token to their **right**, in a list where the punctuation separates items.
A left-scanning regex takes the tail of the previous list item as the anchor
and reports a symbol that was never claimed to be there. That is the
mis-attribution `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` (`source:tests/test_doc_citations.py::test_prose_between_a_symbol_and_a_citation_breaks_the_anchor`) was written to prevent, arriving through
punctuation instead of through prose.

So the widening is narrowed by a discriminator that the same measurement
supplies: **the comma or semicolon is accepted only when the pair is wrapped in
one parenthesis containing nothing else.**

```python
PAREN_PAIR = re.compile(
    r"\(`([^`()]+)`\s*[,;]\s*`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`\)")
```

The anchor class excludes parentheses so that the leading `\(` cannot bind to a
parenthesis inside the anchor. That is a real narrowing — `PAIR`'s own anchor
class admits them, and the assertion does `anchor.rstrip("()")` precisely
because anchors like `frontmatter()` are written — and its measured cost today
is zero: allowing parentheses in the class matches the same 34 places, so no
citation in the checkout is currently excluded by it. Stated rather than
assumed, because a narrowing that costs nothing today is exactly the kind that
starts costing something quietly.

Measured repo-wide, that pattern matches 34 places: 6 in the live corpus, 27
under `archive/`, 1 in `CHANGELOG.md`. Of the 6 live ones, 5 have anchors that
are not symbols and stay declined; **one** is newly compared, and it passes.
Every archived match is declined by the anchor rule or by a missing target, so
the widening does nothing there under either answer to question 1. Of the two
bare list separators, neither matches. One new comparison, one pass, zero new
failures, zero false failures.

Criterion 4 asks for the shape to be asserted directly beside `PAIR`'s existing
self-tests, and the fixture set falls straight out of the table: the
parenthesised comma matches, the parenthesised semicolon matches, the bare
comma does not, the bare semicolon does not, and the prose case keeps failing
to match as it does today.

**Criterion 4 is the one criterion this design closes only in part, and saying
so is the point of the section.** Its words are "a citation written in the comma
shape either validates or fails. It must not skip." A *parenthesised* comma
citation now validates or fails. A *bare* comma citation still does neither: it
is classified `separator-not-adjacent`, counted, and printed — which is not
skipping in the sense the PRD's title uses, but is not validating or failing
either.

The reason it cannot be closed further is measured rather than argued. Two of
the three bare instances in the live corpus are list separators whose anchor is
the token to their right. Making the bare comma fail would report both as stale
when they are correct, and a gate that reports correct citations as stale is
the failure mode the module docstring names in its own words. Making it
*validate* requires deciding which side of the comma the anchor is on, which a
regex cannot do and a reader can. So the honest position is: the shape is
ambiguous, the ambiguity is now visible and counted instead of silent, and the
one unambiguous form of it is checked. If the operator reads criterion 4 as
requiring the bare comma to go red as well, that is a decision to accept two
known-false failures today, and it is not one this design takes on its own.

### Question 4: the shapes beyond the comma, enumerated

`PAIR` has four independent ways to miss, and only the first is the separator.
Every count is live-corpus first, archive second.

**The separator, `` \s*\(? ``.** Punctuation-shaped near misses with a symbol
anchor: comma 2 / 13, semicolon 1 / 1, colon 0 / 4, em dash 0 / 2, double
hyphen 0 / 1, sentence break 0 / 3, bold run 0 / 3, table pipe 0 / 15.
Restricted further to citations whose target exists — the ones a widening would
actually open — the entire live population is the three in the table above and
the entire archived population is two.

**A line break between the halves is not one of these shapes.** The PRD lists
it as a candidate. It cannot be: `anchored_citations` flattens the document
with `.replace("\n", " ")` before matching, so `\s*` absorbs the break and any
indentation after it. The same flattening makes `PAIR`'s own `` [^`\n]+ ``
anchor class carry a dead condition — no newline can reach the regex, so the
`\n` exclusion never fires on any of the 1,089 files.

**A word between the halves is not a near miss and must not become one.** 51
word-separated citations in the live corpus resolve to a real file. Under the
nearest-token rule 41 of them would report stale, and spot-reading says the
bulk of those are mis-attribution rather than staleness — the "anchor" is the
last backticked token of an unrelated sentence. This is the boundary
`test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` already defends
and the design does not move it. Question 4's "a bare *and*" is therefore
answered: no.

**The path, `` [A-Za-z0-9_./-]+ ``.** This is the big one, and the PRD does not
name it. A citation whose path is **elided** — written `` `:391-414` `` because
the previous sentence already named the file — cannot match, because the class
requires at least one character before the colon. There are **162** of them in
the live corpus as it stood at `405a9106`, 166 once this item's own two pages
are counted, and 2,180 under `archive/`. That is 31% of the live corpus's 520
`path:line` tokens, against 2 for the comma. It is the single largest silent
class in the repository by two orders of magnitude. The first draft of this
page put it at 45%, which was 162 over the 358 that `PAIR`'s own path class
finds — a denominator that excludes the thing being measured.

**The line, `` (\d+)(?:-(\d+))? ``.** A citation naming several lines with
commas — `` `bin/sd-docs-lint:113,135` `` — matches **nothing**. The first
draft of this page said it matched the first number and dropped the rest, so
that the claim was half-checked while the report said "checked". That was
recalled, not measured, and it is wrong: `PAIR`'s trailing backtick is
mandatory, so `PAIR.search` returns `None` on the whole shape. The citation is
not half-checked, it is invisible, and it lands in `no-adjacent-anchor` with
everything else the anchor patterns never see. 13 in the live corpus at
`405a9106` and 51 archived; the count was right and the behaviour was not.

**The anchor, via `is_symbol`.** `SYMBOL` (`source:tests/test_doc_citations.py::SYMBOL`)
admits no hyphen, so every kebab-case name in this repository —
`sd-review`, `sd-docs-lint`, `sd-status` — is not a symbol and every citation
anchored to one is declined. 7 declined this way in the live corpus, 110 under
`archive/`.

Of these, the design resolves the separator (criterion 4, parenthesised only)
and leaves the other three **declined by name and counted** rather than
silently dropped. That is deliberate and it is decision D5 below.

### What this breaks in the existing suite

`test_a_citation_cannot_send_this_test_outside_the_checkout` (`source:tests/test_doc_citations.py::test_a_citation_cannot_send_this_test_outside_the_checkout`) asserts
`assertFalse(is_inside_repo(REPO_ROOT / "no-such-file-here.md"))`. Under the
split that predicate becomes `is_under_repo`, which answers **true** for that
path — it is under the checkout, it is merely absent. The assertion inverts.
This is not a regression to be repaired: it is the conflation criterion 1 names,
written down as a test, and the test that replaces it asserts both halves
separately.

`test_the_scan_reaches_the_documents` (`source:tests/test_doc_citations.py::test_the_scan_reaches_the_documents`)
keeps its two non-emptiness assertions and its docstring's reasoning, and gains
the conservation assertion. It does not gain a count, for the reason its own
docstring already gives.

`test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` (`source:tests/test_doc_citations.py::test_prose_between_a_symbol_and_a_citation_breaks_the_anchor`) is untouched. `PAREN_PAIR` is a second
pattern rather than an edit to `PAIR`, so the anchoring rule that test defends
is not weakened, and the two fixtures in it keep meaning what they meant.

The module docstring is rewritten. Its four-bullet list of deliberate skips is
correct as far as it goes and stops before the corpus glob, the corpus census
and the elided path.

Nothing outside `tests/test_doc_citations.py`, `docs/` and `CONTRIBUTING.md`
changes. `CONTRIBUTING.md` is where the convention is written down, which is
also why it joined the checked corpus: the worked example every reader copies
was the one citation nothing resolved. In
particular `bin/sd-docs-lint` is not edited: rule 6's `CITATION_RE`
(`source:bin/sd-docs-lint::CITATION_RE`) reads `.md` targets only, and rule 7 reads
`docs/work/` paths, so neither is the home for a rule about citations into
code.

That citation was written `` (`CITATION_RE`, `bin/sd-docs-lint:351`) `` in the
first draft of this page, and rewriting it is worth recording. In that shape it
is one of the parenthesised comma citations this design proposes to start
checking — so today it is silent, tomorrow it is a claim, and it was correct
either way. The point is that nothing about the page told anyone which. Written
adjacently it is checked now, by the gate as it stands, which is the whole
argument in one line.

## Validation

**Conservation is asserted, coverage is printed, neither is a threshold.** The
partition assertion is `sum(census().values()) == len(tokens_found)` together
with `set(census()) <= REASONS`, where `tokens_found` is the list of `TOKEN`
matches defined above and nothing else. Both hold at any corpus size and neither
changes when prose is reorganised, which is the property
`test_the_scan_reaches_the_documents`'s docstring demands and the reason no
number from this document is pinned in a test.

**The marker grammar is proved by fixture, not by the corpus.** Five cases,
mirroring 0.71.34's specification: a marker with a reason exempts; `[absent:]`
and `[absent: ]` do not; a marker separated from the citation by a non-blank
character does not; a marker on the next line does not; and a marker exempts
only the citation it follows, so a second citation of the same path is still
checked.

**The absent marker's own falsifier.** A fixture citation marked
`[absent: ...]` whose target exists must fail. Without this the marker is a
mute button and the whole vocabulary is worth nothing; with it, the marker is
the only exemption in the design that can itself go stale and say so.

**The mutation set, and where each one dies.**

| mutation | the test that fails |
|---|---|
| a declined reason silently dropped instead of recorded | conservation: the buckets no longer sum to the tokens found |
| `escapes-checkout` and `target-missing` merged back into one branch | the missing-target test, which asserts a named failure for a path under the checkout, and the security test, which asserts silence for one outside it |
| `PAREN_PAIR` relaxed to accept a bare comma | the two negative fixtures drawn from the real list shapes above |
| `[quoted: ]` accepted with an empty reason | the grammar fixture, which is 0.71.34's own rule |
| the census printed but never compared | conservation again; printing is not the assertion and is not relied on |

The first row is why conservation is one assertion over the whole corpus rather
than one test per reason: a reason that is dropped rather than recorded is
invisible to any test that only looks at the reasons that survived.

## The two calls that are not mine

Both are recorded here with the evidence and left open. The design accommodates
either answer to each; where a part changes with the answer, it says so.

### Question 1 — should a stale citation in an archived item fail?

Evidence, measured over the 953 archived markdown files:

- 2,947 `path:line` tokens live under `docs/**/archive/**`.
- 396 of them are shapes `PAIR` matches.
- 286 of those have an anchor that is a symbol.
- **36** of those name a file that still exists in the checkout.
- **17** of those 36 are stale — the symbol is not at the cited line.

Turning the archive on therefore turns **17 red**, not 2,947 and not 21. They
sit in **three** archived items, and the concentration is the interesting part:
`archive/2026-09/2026-09-02-dashboard-ack-and-mutation-count` holds 10 and
`archive/2026-09/2026-08-29-artifacts-as-product` holds 6, leaving one
elsewhere. Six files carry all 17 between them — `bin/sd` 5,
`tests/test_loc_caps.py` 4, `bin/sd-handoff-restore` 3, `dashboard/server.py` 3,
and one each in `dashboard/app.js` and `.github/workflows/tests.yml` — every one
of them a file this rollout has since rewritten. The other 2,911 tokens are
declined for reasons that have nothing to do with the archive: a missing
target, a non-symbol anchor, a shape `PAIR` cannot read.

The PRD's figure of "21 comma-shaped citations sitting there unexamined" is not
reproducible today under any definition tried: comma-separated with a symbol
anchor measures 13, comma-separated overall measures 77, and parenthesised
comma or semicolon pairs measure 27 of which 21 have non-symbol anchors. None
of the three is the population the sentence describes. What *is* reproducible
is the more useful fact: **zero** archived comma-shaped citations name a file
that still exists, so the comma question and the archive question do not
interact at all.

**The options.**

*Keep the exclusion, with the reason written down.* The archive's own bullet in
the module docstring already argues it: an archived record cites the code as it
stood, and "those citations are supposed to be stale; that is what an archive
is". Cost: 17 known-wrong citations stay unmarked, and the number is now known
rather than assumed.

*Narrow it: archived citations are compared, and a stale one is reported rather
than failed.* Costs one more reason in the vocabulary (`archived-stale`) and a
census line. Nothing goes red. This is the option that makes "we decided not to"
different from "we never look", which is the distinction the question is about.

*Drop it: archived citations fail like any other.* 17 red on the first run, each
fixable by an `[absent: ...]`-style marker or by correcting the line. It is 17
edits to six archived documents in three items — records of what was, which is
the objection.

**Decided by the operator, 2026-09-07: narrow it.** Archived citations are
compared, and a stale one is reported rather than failed — the second option.
It costs one vocabulary entry (`archived-stale`) and a census line, and nothing
goes red.

The reasoning is the operator's ruling of the same day, given on a different
question and general in form: *"whatever does not reduce existing
functionality. We gotta get out of the proposal to remove functionality to
maintain a cap. I will never agree to that. If functionality requires more
code, then it requires more code."* Of the three options, keeping the exclusion
is the only one that leaves the gate unable to see something it could see; 17
known-wrong citations stay unmarked and the gate stays blind by construction.
Dropping the exclusion sees them but pays for it by editing six archived
documents in three items — rewriting records of what was, to satisfy a check
written afterwards. Narrowing takes the coverage and refuses the rewrite.

It is also the option this section already identified as the one the question
is actually about: it "makes 'we decided not to' different from 'we never
look'".

**What changes with the answer.** Only the corpus filter and one vocabulary
entry. The classification, the marker vocabulary, the conservation assertion and
`PAREN_PAIR` are identical under all three, and the archive filter is one
`continue` that becomes a reason string. Nothing in this design is built on the
archive staying out.

### Question 2 — should the corpus include `CHANGELOG.md`?

Evidence:

- `CHANGELOG.md` holds **8** `path:line` tokens, not one. Six name paths that
  do not exist in this checkout — including `internal/review/rules.go`,
  `review.py`, `prepare-release.py` and two into `docs/FLEET_ROLLOUT.md`. Two
  name `.gitignore:66`, which does exist.
- **Zero** of the 8 are in a shape `PAIR` matches. Not one has an adjacent
  backticked symbol before it.
- `internal/review/rules.go` has never existed in this repository:
  `git rev-list --all --count -- internal/review/rules.go` returns 0, and no
  commit on any ref has ever added a file under `internal/`. It is a citation
  into the retired upstream stack, correct where it was written and
  unresolvable here on purpose.
- The corpus glob drops 112 tracked markdown files, and all 8 of those tokens
  are in `CHANGELOG.md`. Every other file outside `docs/` — `README.md`,
  `AGENTS.md`, `skills/**/SKILL.md`, `agents/*.md` — carries none.

So the glob's measured cost today is eight tokens in one file, none of which
the gate would check even if the file were in scope. Including `CHANGELOG.md`
changes nothing this week; the question is what it should do next year.

**The options.**

*Keep the glob as it is.* Cheapest, and defensible on the same ground rule 7
already states in its docstring: "the changelog names paths as they were at the
time, which is the one place a reference that no longer resolves is still
correct". Writing that reason into the gate makes it a decision rather than an
accident of a glob string.

*Widen the corpus to every tracked markdown file and exclude `CHANGELOG.md` by
name, with rule 7's reason.* This is the shape rule 7 already has
(`bin/sd-docs-lint:465`), so the two rules would agree on what the corpus is
instead of disagreeing by accident. Cost: 112 more files scanned, 8 more tokens
classified, 0 new comparisons, and the exclusion is stated where a reader will
find it.

*Widen it and include `CHANGELOG.md` too.* Six of its eight tokens are
deliberately unresolvable historical references and would each need an
`[absent: ...]` marker — which is what that marker is for, and two of the six
already sit next to a `[absent: <reason>]` example in the 0.71.34 entry that
specified the grammar.

**Decided by the operator, 2026-09-07: widen the corpus and exclude
`CHANGELOG.md` by name, with rule 7's reason.** The second option.

Same ruling, same reading. Option 1 leaves 112 tracked markdown files outside
the gate's sight because of a glob string nobody argued for, which is coverage
lost to an accident. Option 3 takes the coverage but pays by writing
`[absent: ...]` markers into six historical `CHANGELOG.md` entries — the same
rewrite-the-record cost that question 1 refused, and against rule 7's own
stated reason that the changelog "names paths as they were at the time, which
is the one place a reference that no longer resolves is still correct". Option
2 scans everything and states the one exclusion where a reader will find it,
so the gate and rule 7 agree on what the corpus is instead of disagreeing by
accident.

**And the budget consequence is accepted rather than avoided.** This section
says plainly that options 2 and 3 cost a re-derivation option 1 does not: the
corpus must be asked of git rather than walked from the filesystem, which is a
subprocess where there is none today, and `implement.md` prices the seam at
zero on the strength of there being no boundary to cross. That price is now
wrong and the seam is real. Under the ruling, that is a cost to pay and record,
not a reason to choose the cheaper answer — the item lands in `tests/`, which
answers to no ceiling, so what changes is the derivation's honesty rather than
any cap. `implement.md`'s budget section carries the correction.

**What changes with the answer, and the one place it is not free.** Option 1 is
one comment. Options 2 and 3 change the glob, add one exclusion with a comment
— and raise a question the glob currently hides: what *is* "every markdown file
in the repository"? `anchored_citations` walks the filesystem
(`REPO_ROOT.glob`), which under `docs/` is harmless and outside it is not — a
filesystem walk of the whole checkout picks up untracked files and anything a
`.venv` or a vendored tree happens to contain, while the git index does not.
Rule 7 already answers this by asking git (`bin/sd-docs-lint:465`), and
answering it the same way in the gate means a subprocess where there is none
today. That is a seam, and `implement.md`'s budget prices the seam at zero on
the strength of there being no boundary to cross. **So options 2 and 3 cost a
re-derivation of the budget that option 1 does not.** It is small — the
transport is `sd_lib.git_output` and is built — but it is not nothing, and a
plan that said "one glob" without saying this would be understating the answer
the operator is being asked for.

## What the PRD got wrong the second time

The PRD records what its first draft got wrong. This is the same courtesy paid
forward, and criterion 3 asked for it in as many words. Measured on `405a9106`
on 2026-09-07, three days after the PRD's table.

**The punctuation-alone row went from 0 to 3, and the PRD predicted the drift
but not its direction.** It says the row "is zero *today* and that is not
reassuring, because it was 1 an hour ago". It is now three — two commas and a
semicolon, all in one item that did not exist when the PRD was written. What
the PRD did not anticipate is that two of the three are not citations of the
shape it was worried about: they are list separators, and a widening would
report them stale when they are not.

**The archive row's 21 is not reproducible.** Three definitions were tried and
none of them yields it: comma-separated with a symbol anchor measures 13,
comma-separated overall measures 77, and the parenthesised comma-or-semicolon
shape measures 27 of which 21 have anchors that are not symbols. The last is
close enough to be the likely origin and far enough from the sentence's meaning
to be worth not guessing at. The number that matters is one the PRD did not
take: **zero** archived comma-shaped citations name a file that still exists,
so the comma question and the archive question never touched.

**The `CHANGELOG.md` row is right about the comma and understates the file.**
One comma-shaped citation is correct. `CHANGELOG.md` holds eight `path:line`
tokens in total, six of them naming paths that do not exist here, and not one
of the eight is in a shape `PAIR` matches.

**"Widening `PAIR` would have newly checked one citation, and that one passed"
survives, by a different route than the one it was argued from.** Under the
parenthesised widening this design proposes it is still exactly one, and it
still passes. Under the naive widening the PRD had in mind it is three, of
which two fail wrongly. The conclusion was right and the reasoning had not been
run — which is the thing the PRD's own confession is about.

**"A line break landing between the halves" is not a shape.** Question 4 lists
it as a candidate. `anchored_citations` flattens each document with
`.replace("\n", " ")` before matching, so `\s*` absorbs the break and every
indentation after it. No citation in the checkout is silenced this way and none
can be.

**The four shapes question 4 names are together two orders of magnitude smaller
than the one it does not.** Comma, em dash, semicolon and a bare *and* account
for 3 near misses in the live corpus. The elided path accounts for 162.

**The PRD's own citations of the gate were each one line early, and this item
has already corrected them** — at `405a9106` the PRD carried `:79-101` for a
function spanning 80 to 102, `:116-130` for one spanning 117 to 131, `:132-143`
for one spanning 133 to 144, and `:145-154` for one spanning 146 to 155;
`d3c26286` moved all four. A reviewer read this paragraph against `HEAD`, found
the corrected values there, and concluded the defect never existed and the
paragraph should be deleted. It existed: `git show 405a9106:.../prd.md | grep
-n 'test_doc_citations.py:'` prints the four early values, and the paragraph is
kept in the past tense because criterion 3 asks for the correction to be
recorded rather than merely made. All four passed, because `WINDOW` (`source:tests/test_doc_citations.py::WINDOW`) is 2 and forgives an offset of one. They are
corrected in `prd.md` as part of this plan, and the fact that a gate against
stale line numbers tolerates every one of them is worth leaving on the record
next to `WINDOW`'s comment, which argues for exactly that tolerance.

## Decisions

**D1 — the filter chain becomes a classification, and that is the item.**
Considered: fix the four silencers individually and leave the enumeration as
it is. Rejected. The PRD's own history is the argument — four silencers found
one at a time by being bitten, over four review rounds for one of them — and a
fifth was found by this measurement that the PRD did not know about. Patching
the known four leaves the next one exactly as invisible.

**D2 — `PAIR` is not edited; `PAREN_PAIR` is added beside it.** Considered:
widen `PAIR`'s separator to `` \s*[,;]?\s*\(? ``. Rejected on measurement: it
turns two comma- and semicolon-separated *lists* into false stale reports, and
a gate whose failures need interpreting teaches people to interpret failures
away — the module docstring's own sentence. A second pattern with a
parenthesis on both ends is narrower than the shape a reader would guess at,
and the fixtures say exactly what it does.

**D3 — the marker vocabulary is adopted, not invented.** `[absent: <reason>]`
already exists with a written grammar and 29 live uses, 91 across `docs/`;
`[quoted: <reason>]` is
one new verb in the same grammar. Considered: a new syntax that reads better in
prose. Rejected — the repository would then hold two markers meaning nearly the
same thing, and the older one would keep being written by people copying the
spec pages.

**D4 — `[absent: ...]` fails when the target exists.** This is what separates
the design's markers from an exemption list. Considered: treat a marker as an
unconditional skip, matching what 0.71.34 did. Rejected: 0.71.34's rule checked
whether a *path* resolved, so a marker on a resolvable path was merely
redundant. Here the marker is a claim about the state of the tree, and an
unfalsifiable claim in a gate about unfalsifiable claims is the wrong shape.

**D4a — `[quoted: ]` names a source, so it is falsifiable too.** The first
draft took a free-text reason, which made `quoted` the one marker in the design
that could never be wrong — the exact shape D4 rejects one paragraph above, and
a reviewer was right to say the principle was stated and not applied. The form
is `[quoted: <path:line>]`, and the gate asserts that the quoted citation's own
text appears at that line of that file. A page quoting `` `is_symbol` (`source:tests/test_doc_citations.py::is_symbol`) `` as an example of the shape writes
`[quoted: tests/test_doc_citations.py:377]` after it, and if the example is
moved or the line changes, the quotation fails like any other claim. This costs
nothing over the free-text form — it is the same grammar, the same
`marker_after()`, and the same one-citation scope — and it removes the only
unfalsifiable exemption on the page. Considered and rejected: a bare
`[quoted]`, which is the mute button D4 already rejected under another name.

**D5 — the elided path, the multi-line citation and the kebab anchor are named
and counted, not resolved.** They are 162, 13 and 7 in the live corpus against
the comma's 2, so this is not a judgement about size. Resolving the elided path
means carrying a "current file" across a document and deciding what resets it,
which is a parser with its own failure modes and its own item; resolving the
kebab anchor means widening `SYMBOL`, which changes what counts as a claim
everywhere at once. Both are real, both are now measured, and both are visible
in the census from the first run — which is the difference between a backlog
item and a silencer.

**D6 — nothing lands under `bin/`.** The gate is a test and stays one. Rule 6
reads `.md` targets and rule 7 reads `docs/work/` paths; neither is a rule
about citations into code, and moving this there would mean a third citation
reader in a third file. The budget consequence is in `implement.md`: `BIN_CAP`
does not move and its 784 lines of headroom are untouched.

## Risks

**This document is inside its own corpus, and it discusses citation shapes.**
The PRD's first draft failed `make check` on exactly this. Every real citation
above is a claim, verified against this worktree; every illustrative shape is
written with a metavariable line number so it cannot match, and that workaround
is question 3's finding rather than a solution — after `[quoted: <reason>]`
exists, these pages are the first place it should be used, and rewriting them
to use it is step 7 of `implement.md`.

**The live corpus's near-miss population is one item deep.** All three
punctuation-shaped near misses, and 49 of the 51 word-separated ones, are in
`docs/work/2026-09-05-the-pack-runs-a-team-process-for-one-person/`, which is
active and being edited. Those three counts will not survive the week. The
design does not depend on them — `PAREN_PAIR`'s fixtures are literals, not
corpus reads — but any re-run of the numbers in this document must be a re-run
and not a quotation. That is criterion 3, and this document is now the thing it
applies to.

**Turning `target-missing` red depends on a marker landing first.** The one
live instance already carries `[absent: ...]`, so the order is: teach the gate
the marker, then turn the reason red. Reversed, `make check` is broken between
two commits of the same item. `implement.md` sequences it.

**The census is printed, and printing is not free of drift either.** A line in
`unittest-output.log` that nobody reads is a weaker instrument than a failing
test, and the design deliberately does not pin its numbers. What holds it up is
conservation: the census can drift, but it cannot lose a citation without the
partition assertion failing. If that turns out to be too weak in practice, the
next step is a recorded baseline in the manner of rule 6's `.citations.tsv`,
and that is a decision for after the first month of the census, not before it.

**Rule 6 has the same disease and this item does not treat it.** `check_citations`
(`source:bin/sd-docs-lint::check_citations`) checks only items that carry a `.citations.tsv`, and
its note reads "checked 25 citation(s) across 5 recorded item(s)" over a tree
of 497 items. Four of those five manifests are empty, so all 25 rows come from
one item, and a citation added after the recording is not checked by anything.
Named here because it is the same failure in a neighbouring rule, and left
alone because it is a second item.

## The adversarial review, and what it moved

`.claude/rules/sd-planning-adversarial-review.md` puts this item at
**Development / prd and design**, cap **5**. Five passes ran: two by the author
against these pages, and three by two independent readers. The cap is spent, so
no further pass starts on its own, and what follows is the record the rule asks
for rather than a claim of approval.

Rounds 1 and 2 were arithmetic and vocabulary: a missing `declared-absent`
bucket that would have broken the conservation assertion the page sells, a
bare comma mis-filed under `no-adjacent-anchor`, a rule 7 figure this item's own
pages had already moved, and a criterion 4 that read as closed when it is closed
only in part. Commit `3feca986` carries them.

Rounds 3 to 5 were the ones worth having, because they found a class of defect
rather than a set of typos: **a number or a behaviour written into a page from
recollection, and then cited by a later step as if it had been measured.** Six
instances, each confirmed against the source and repaired above:

1. `tokens_found` was never defined, so conservation was a tautology. `TOKEN`
   is now written out, and defining it revealed that the enumerator actually
   used to produce the first draft's census **excluded the elided path** — so
   "162 of the 273 are elided" was not merely imprecise, it was false, and the
   "45% of the corpus" figure divided by a denominator that omitted its own
   numerator.
2. An anchor can itself be a `path:line` token, and 4 of the 7 live
   `PAREN_PAIR` matches are. One match, two tokens, no partition rule; the rule
   is now one row per token, keyed by offset.
3. `is_under_repo` was described as "containment only", which read literally
   drops `resolve()` and turns the security refusal into a traversal.
   `(REPO_ROOT / ".." / ".." / "etc" / "passwd").is_relative_to(REPO_ROOT)` is
   `True`.
4. `separator-not-adjacent` had two incompatible glosses and its 33 reproduced
   under neither. It is now `SEPARATED_PAIR`, a named regex, and 20.
5. `PAIR` was said to truncate a multi-comma citation. It matches nothing at
   all; the trailing backtick is mandatory.
6. Step 8 asked for 21 markers to be confirmed by a mechanism that can see two
   of them.

Three findings were **rebutted with evidence** rather than accepted. A reader
reported that the PRD's four off-by-one citations never existed; they existed at
`405a9106` and `d3c26286` corrected them, which is what
`git show 405a9106:.../prd.md` prints. A reader reported that the reason
vocabulary had no `[absent: ...]` bucket; it gained one in round 2, at
`3feca986`, before that pass ran. And a reader reported that "same line" is
unimplementable against the flattening; the flatten is a one-for-one character
substitution, so offsets survive it and the rule is implementable, which is now
stated on the page rather than assumed.

**What is open at the cap.** No blocking finding survives: each is repaired
above or rebutted with a command whose output is quoted. Two things remain open
and neither is a review finding — questions 1 and 2 were the operator's calls,
recorded under "The two calls that are not mine" with their options and
consequences. **Both were answered on 2026-09-07** and the decisions are
recorded there. The item is **not** `blocked` and is no longer waiting.

One correction while this paragraph is being touched: it previously said "step
0 of `implement.md` says the item does not start until they are answered",
which overstated the gate. `implement.md` says steps 1 to 8 could be built and
landed before either answer, and that only step 9's closure and criterion 5's
claim depended on them. The narrower statement was the true one.
