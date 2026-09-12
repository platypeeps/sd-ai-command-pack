"""A `path:line` citation still points at the thing the prose says it does.

A line number is invalidated by any insertion above its target, and nothing
watched them. Step 8-iv demonstrated the failure inside a single branch:
growing `bin/sd` from 1,553 lines to 2,006 moved `frontmatter()` from 1231 to
1248, the reader's `.strip('"')` from 1252 to 1276, and `status_filter` from
1350 to 1378. All three were correct on `main`, all three were wrong on the
branch that changed the file, and the branch that broke them was also the
branch editing the document that carried them.

The planning review rule -- `.claude/rules/sd-planning-adversarial-review.md`,
and the contract it points at -- already asks for this sweep, and it did catch
those three. But it only runs at a planning convergence boundary. A pure code
change that edits no `prd.md`, `design.md` or `implement.md` breaks citations
with nothing to notice; 8-iv was swept only because it happened to edit
`design.md` as well. This runs on every change instead.

**The rule is adjacency.** A citation that directly follows a backticked
symbol -- `` `status_filter` (`bin/sd:1378`) `` -- is a claim *about that
symbol*, and the symbol must appear at the cited line. A citation with prose
between it and the nearest backticked token is making some other claim, and is
skipped rather than guessed at: an earlier draft took the nearest symbol within
90 characters and mis-attributed `bin/sd-status:501-506`, which is an accurate
citation to a docstring that does not happen to repeat the key name. A gate
whose failures need interpreting teaches people to interpret failures away.

**Nothing is skipped silently any more.** The predecessor filtered: four
`continue`s in a row, each dropping a population and none of them naming it.
Whichever ran first hid everything the later ones would have said, so the
order of the chain decided the report, and nobody had written the order down.
Removing the last of them moved the compared population from 44 to 1 and every
test in this module stayed green -- which is the argument for classifying
rather than filtering, and it is not an argument about tidiness.

`classify()` now returns one row per `path:line` token in the corpus, each
carrying a reason from `REASONS`, and `census()` counts them. Conservation is
asserted: the buckets sum to the tokens found and no row carries a reason from
outside the vocabulary. That is a partition property rather than a threshold,
so it does not drift when prose is reorganised, and it is what would have
caught each of these on the day it was introduced rather than one at a time by
being bitten.

Measured over the corpus at the time of writing -- 1,096 tracked markdown
files, 5,699 tokens -- and re-measurable by running the module, which prints
the census on every run:

===========================  ======  ======  ======
reason                         live  archiv   total
===========================  ======  ======  ======
`compared`                       39      15      54
`no-adjacent-anchor`            322   2,410   2,732
`elided-path`                   176   2,180   2,356
`archived-stale`                  0     277     277
`anchor-not-a-symbol`            13     131     144
`separator-not-adjacent`         20     114     134
`declared-absent`                 1       0       1
`absent-but-present`              0       0       0
`target-missing`                  0       0       0
`escapes-checkout`                0       0       0
`quoted`                          1       0       1
===========================  ======  ======  ======

Each reason, with why it exists:

* **`compared`** -- the anchor was checked against the cited line. The only
  bucket that can fail, together with `target-missing`.
* **`no-adjacent-anchor`** and **`elided-path`** -- the token matched no
  anchoring shape, or names a line and no file because the prose named the
  file already. Both are tokens, neither is anchorable, and between them they
  are 89% of the corpus. Counted rather than dropped so that a regex tightened
  by accident shows up as a bucket moving.
* **`archived-stale`** -- an archived document citing a line that has moved,
  or a file since deleted. Reported, never failed: the ruling was to take the
  coverage and not buy it by editing the historical record. Archives are *in*
  the corpus now; the predecessor never opened them and said nothing about it.
* **`anchor-not-a-symbol`** -- the token before the citation is a path or a
  phrase, so there is nothing to check a line against.
* **`separator-not-adjacent`** -- a bare comma or semicolon between the two
  halves. Question 4's subject, and its own bucket on purpose: folded into
  `no-adjacent-anchor` the comma population is uncountable, which is how it
  stayed at "0" for three days.
* **`target-missing`** -- a path inside the checkout with no file at it. This
  is a stale citation and it is **red**. Empty today.
* **`declared-absent`** -- the same, but the citation carries
  `[absent: <reason>]`. Not a failure and not the same bucket, because the
  marker is a claim that can itself go stale.
* **`absent-but-present`** -- that claim, gone stale: an `[absent: ...]` whose
  target exists. **Red**, and empty today. Stated as a contract in an earlier
  draft of this docstring with nothing enforcing it, which is the silencer
  shape this module is about; `test_the_red_buckets_are_empty` enforces it now.
* **`escapes-checkout`** -- the path resolved outside the tree. Silent by
  design and the only one of these that is a security refusal. It has never
  fired on real content, and it is its own bucket so that the silence stays
  visible instead of being inferred from one it used to share with a live
  defect.
* **`quoted`** -- the citation carries `[quoted: <reason>]`. See below.

**The corpus is every tracked markdown file, asked of git**, with
`CHANGELOG.md` excluded by name carrying rule 7's reason: the changelog names
paths as they were at the time, the one place a reference that no longer
resolves is still correct. The predecessor globbed `docs/**/*.md`, which held
the gate off `AGENTS.md`, `README.md`, `CONTRIBUTING.md` and every
`skills/**/SKILL.md` without ever saying so.

**The two markers.** `[absent: <reason>]` says a cited file is gone on
purpose. `[quoted: <path:line>]` says a citation is an example rather than a
claim -- the answer to "can a document explain this gate without tripping it",
found by being caught, when this item's own PRD reproduced a self-test
verbatim and `make check` failed on that file. Both require a reason: an
exemption nobody has to justify is a silencer with better manners. The reason
on `[quoted: ]` is itself a `path:line`, so the escape hatch is falsifiable
too.

Three shapes are named and counted rather than resolved, and saying so is more
honest than a number that implies they were handled: the bare comma and
semicolon (134), the elided path (2,356), and the token with no anchoring
shape at all (2,732).
"""

from __future__ import annotations

import collections
import os
import pathlib
import re
import subprocess
import tempfile
import typing
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# A backticked token, then only whitespace or an opening paren, then the
# citation. Anything else between them and this is not a claim about the token.
PAIR = re.compile(r"`([^`\n]+)`\s*\(?`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`")

#: The parenthesised comma and semicolon, accepted; the bare ones, not.
#:
#: Measured before it was written: of the three punctuation-shaped near misses
#: in the corpus, the parenthesised comma is a real anchored citation and the
#: two bare ones are *list separators*, where the anchor of each citation is
#: the token to its right. A left-scanning regex widened to the bare comma
#: takes the tail of the previous list item as the anchor and reports a symbol
#: nobody claimed was there -- the mis-attribution
#: `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` exists to
#: prevent, arriving through punctuation instead of prose. So the wrapping
#: parenthesis is the discriminator, and the anchor class excludes parentheses
#: so the leading `\(` cannot bind to one inside the anchor.
PAREN_PAIR = re.compile(
    r"\(`([^`()\n]+)`\s*[,;]\s*`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`\)")

#: The bare separator, matched in order to be *counted* rather than compared.
#: Question 4's whole subject. It needs its own bucket: folded into
#: `no-adjacent-anchor` the comma population is uncountable, which is how it
#: stayed at "0" for three days. A named regex rather than a character
#: distance on purpose -- sweeping a distance bound from one character to ten
#: moved the bucket from 0 to 132 with no principled stopping point, which is
#: not a classification, it is a dial.
SEPARATED_PAIR = re.compile(
    r"`([^`\n]+)`\s*[,;]\s*`([A-Za-z0-9_./-]*):(\d+)(?:-(\d+))?`")

#: Every `path:line` token, including the elided form that names no file.
#: `PAIR`'s path class with `+` relaxed to `*`. The relaxation is what admits
#: a non-citation, so it was measured rather than assumed: across the live
#: corpus it adds only the elided form and introduces no match whose path is
#: neither a file name nor empty. A backticked ISO timestamp does not match --
#: `2026-09-06T19:11:39Z` puts a colon where the pattern needs a closing
#: backtick -- and one written to minute precision would surface as a
#: `no-adjacent-anchor` row rather than as a silent drop, which is the point
#: of counting rather than filtering.
TOKEN = re.compile(r"`([A-Za-z0-9_./-]*):(\d+)(?:-(\d+))?`")

SYMBOL = re.compile(r"^\.?[A-Za-z_][A-Za-z0-9_.]*(\(.*\))?$")
EXTENSION = re.compile(r"\.(md|py|js|json|sh|ya?ml|toml|txt|lock)$")

#: The two markers, and their grammar, taken from 0.71.34. The reason is
#: required, the marker follows its citation on the same line with nothing
#: non-blank between them, and it covers exactly one citation.
#: Every line terminator the grammar names, not just `\n`. 0.71.34 is explicit
#: -- "Reasons may not span a line terminator, `\r` and U+2028/U+2029
#: included" -- and a reason class excluding only `\n` would let
#: `[absent: x\u2028y]` through, which is a marker spanning a line
#: suppressing a missing-target failure. A guard that fails open on an exotic
#: separator is worth less than no guard, because it reads as covered.
TERMINATORS = "\n\r\u2028\u2029"

MARKER = re.compile(r"\[(quoted|absent):[ \t]*([^\]" + TERMINATORS + r"]*?)[ \t]*\]")

# The cited line is where the symbol is *introduced*; prose cites a `def` line
# and the reader looks at the lines under it. Wide enough to survive a
# signature wrapped across lines, narrow enough that a symbol used a hundred
# lines away cannot satisfy it.
WINDOW = 2

#: The closed vocabulary. Conservation is asserted against it: every token in
#: the corpus lands in exactly one of these, the buckets sum to the tokens
#: found, and no row carries a reason from outside. That is a partition
#: property rather than a threshold, so it cannot drift when prose is
#: reorganised -- and it is what would have caught each of the four silencers
#: this module used to carry on the day it was introduced, rather than one at
#: a time by being bitten.
REASONS = frozenset({
    "compared",
    "archived-stale",
    "escapes-checkout",
    "target-missing",
    "declared-absent",
    "absent-but-present",
    "anchor-not-a-symbol",
    "elided-path",
    "separator-not-adjacent",
    "no-adjacent-anchor",
    "quoted",
})


class Citation(typing.NamedTuple):
    """One `path:line` token in one document, with why it was or was not checked."""

    doc: pathlib.Path
    anchor: str
    path: str
    target: pathlib.Path | None
    start: int
    end: int
    reason: str


#: `CHANGELOG.md` is excluded by name, carrying rule 7's stated reason: the
#: changelog names paths as they were at the time, which is the one place a
#: reference that no longer resolves is still correct. It holds 9 tokens, 6 of
#: them naming paths that do not exist; every one of those is correct.
CHANGELOG = "CHANGELOG.md"


def is_symbol(token: str) -> bool:
    """A name a line can be checked against, as opposed to a path or a phrase."""

    return bool(SYMBOL.match(token)) and "/" not in token and not EXTENSION.search(token)


def is_under_repo(target: pathlib.Path) -> bool:
    """Containment only: does this path resolve inside the checkout?

    **The `resolve()` is load-bearing and is not an implementation detail.**
    `Path.is_relative_to` is lexical, so
    `(REPO_ROOT / ".." / ".." / "etc" / "passwd").is_relative_to(REPO_ROOT)`
    is `True` without it and `False` with it. Reading this predicate's name as
    "containment" and dropping the resolve would turn the security refusal
    into an invitation.

    It no longer answers "and does a file exist there". That second question
    is a *stale citation* -- the thing this module was built to catch -- and
    it used to be discarded through the same `continue` as the refusal.
    """

    try:
        resolved = target.resolve()
    except OSError:
        return False
    return resolved.is_relative_to(REPO_ROOT.resolve())


def corpus(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every tracked markdown file, asked of git, `CHANGELOG.md` excluded.

    Asked of git rather than globbed so that the corpus is the repository's
    own answer to what it tracks. The predecessor globbed `docs/**/*.md`,
    which silently held the gate off every markdown file above `docs/` --
    `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, every `skills/**/SKILL.md` --
    and said nothing about it.

    Archived documents are *in* the corpus and are compared. A stale citation
    in an archive is reported as `archived-stale` and fails nothing: the
    ruling was to take the coverage and not buy it by editing the historical
    record.
    """

    # Not resolved: `contained` does the containment test against a resolved
    # base of its own, and a caller that passed `/var/...` needs the documents
    # back under `/var/...` rather than under the `/private/var/...` the
    # platform resolves it to.
    root = root or REPO_ROOT
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "*.md"],
            capture_output=True, text=True, check=True).stdout.split("\0")
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - no git
        listed = [str(p.relative_to(root)) for p in sorted(root.rglob("*.md"))]
    return contained(root, [root / name for name in listed
                            if name and name != CHANGELOG])


def marker_after(flat: str, raw: str, end: int) -> tuple[str, str] | None:
    """The marker covering the citation that ends at `end`, or `None`.

    0.71.34's grammar: the reason is required, the marker follows the citation
    on the same line with nothing non-blank between them, and it covers one
    citation.

    **"Nothing non-blank" admits one closing parenthesis**, because the
    commonest citation shape in this repository wraps itself in one --
    ``frontmatter() (`bin/sd:1231`)`` -- and the marker has to be able to
    follow it. Taking the grammar's words literally would leave the
    parenthesised form, which is most of the corpus, unable to carry a marker
    at all. One, not any number: a run of them is prose.

    The line rule survives the flattening because the flattening is
    offset-preserving -- one space per newline, one character for one -- so an
    offset in `flat` is the same offset in `raw`. The match is taken on `flat`
    and the line test is then made against `raw`.
    """

    cursor = end
    seen_paren = False
    while cursor < len(flat):
        if flat[cursor] in " \t":
            cursor += 1
        elif flat[cursor] == ")" and not seen_paren:
            seen_paren = True
            cursor += 1
        else:
            break
    match = MARKER.match(flat, cursor)
    if match is None:
        return None
    if any(mark in raw[end:match.end()] for mark in TERMINATORS):
        return None
    kind, reason = match.group(1), match.group(2).strip()
    if not reason:
        return None
    return kind, reason


def anchor_for(flat: str, span: tuple[int, int]) -> tuple[str, bool] | None:
    """The backticked token this citation is a claim about, and whether it is adjacent.

    Returns `(anchor, True)` for the two adjacent shapes, `(anchor, False)` for
    a bare comma or semicolon -- counted rather than compared -- and `None`
    when no anchoring shape reaches the token at all.

    Each candidate is accepted only when its *citation half* covers exactly the
    token being classified, span for span. An approximate test was written
    first and it mis-filed a real parenthesised pair as a bare separator, which
    is the kind of error a census hides rather than reports: the token still
    lands in a bucket, just the wrong one, and conservation stays green.
    """

    for pattern, trailing in ((PAIR, 0), (PAREN_PAIR, 1), (SEPARATED_PAIR, 0)):
        for match in pattern.finditer(flat, max(0, span[0] - 400), span[1] + 2):
            if (match.start(2) - 1, match.end() - trailing) == span:
                return match.group(1), pattern is not SEPARATED_PAIR
    return None


def classify(docs: list[pathlib.Path] | None = None) -> list[Citation]:
    """One row per `path:line` token in the corpus, each with why it was kept or not.

    **The chain stopped being a chain.** The predecessor filtered: four
    `continue`s in a row, each dropping a population and none of them naming
    it. Whichever ran first hid everything the later ones would have said, so
    the order of the chain decided the report and nobody had written the order
    down. A classification cannot do that -- every token gets a row, the
    reasons are a closed set, and the buckets are asserted to partition the
    corpus.

    **Iteration is over tokens, not over anchor-citation pairs.** A citation's
    anchor can itself be a `path:line` token, so one `PAREN_PAIR` match can
    contain two `TOKEN` matches. The subject token is compared, the anchor
    token gets its own row on its own terms, and no token is consumed by being
    another token's anchor. Without that rule the buckets under-count against
    the corpus and conservation fails on the real tree rather than on a
    fixture.

    **The corpus is a parameter and that is not a convenience.**
    `escapes-checkout` has no live instance and never has had one, and
    `quoted` has as many as this item's own pages carry. A function that
    fetches its own input can only be tested against whatever it fetches, so
    without this the two branches that matter most would be unreachable in a
    test and conservation would be proved only on the shapes that happen to
    exist today.
    """

    rows: list[Citation] = []
    for doc in (corpus() if docs is None else docs):
        raw = doc.read_text(encoding="utf-8", errors="replace")
        # Newlines flattened: a citation routinely wraps away from its symbol.
        # One character for one, so offsets carry over to `raw` unchanged.
        flat = raw.replace("\n", " ")
        archived = "archive" in doc.parts
        for match in TOKEN.finditer(flat):
            path, start = match.group(1), int(match.group(2))
            end = int(match.group(3) or match.group(2))
            marker = marker_after(flat, raw, match.end())
            if marker and marker[0] == "quoted":
                rows.append(Citation(doc, "", path, None, start, end, "quoted"))
                continue
            if not path:
                rows.append(Citation(doc, "", path, None, start, end, "elided-path"))
                continue
            found = anchor_for(flat, match.span())
            if found is None:
                rows.append(
                    Citation(doc, "", path, None, start, end, "no-adjacent-anchor"))
                continue
            anchor, adjacent = found
            if not adjacent:
                rows.append(
                    Citation(doc, anchor, path, None, start, end,
                             "separator-not-adjacent"))
                continue
            if not is_symbol(anchor):
                rows.append(
                    Citation(doc, anchor, path, None, start, end,
                             "anchor-not-a-symbol"))
                continue
            target = REPO_ROOT / path
            if not is_under_repo(target):
                rows.append(
                    Citation(doc, anchor, path, None, start, end,
                             "escapes-checkout"))
                continue
            if not target.is_file():
                # An archive naming a file that has since been deleted is a
                # record, not a defect: `archived-stale` reports it and fails
                # nothing. Live, the same shape is the stale citation this
                # module exists to catch, and `target-missing` is red.
                if archived:
                    reason = "archived-stale"
                elif marker and marker[0] == "absent":
                    reason = "declared-absent"
                else:
                    reason = "target-missing"
                rows.append(Citation(doc, anchor, path, target, start, end, reason))
                continue
            reason = "compared"
            if marker and marker[0] == "absent":
                # The marker claims the target is gone and it is not. The claim
                # is the thing that went stale, so it is its own bucket and it
                # is red -- an absence marker nobody rechecks is a silencer
                # that outlives its reason.
                reason = "absent-but-present"
            elif archived and not names_its_symbol(anchor, target, start, end):
                reason = "archived-stale"
            rows.append(Citation(doc, anchor, path, target, start, end, reason))
    return rows


def names_its_symbol(anchor: str, target: pathlib.Path, start: int, end: int) -> bool:
    """Does the cited window carry the anchor? The one comparison this gate makes."""

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    window = "\n".join(lines[max(0, start - 1 - WINDOW):end + WINDOW])
    return anchor.rstrip("()") in window


def census(docs: list[pathlib.Path] | None = None) -> collections.Counter:
    """How many tokens landed in each bucket. Criterion 6's report."""

    return collections.Counter(row.reason for row in classify(docs))


def contained(root: pathlib.Path, documents) -> list[pathlib.Path]:
    """The documents this test will open: real files inside `root`.

    `is_under_repo` guards the file a citation *names*. This guards the file
    the citation is *in*, which nothing was watching. `glob` returns a symlink
    as readily as a regular file and `read_text` follows it, so a tracked
    `docs/current.md -> /etc/passwd` would have CI read a file of the
    document tree's choosing -- the same hole, entered from the other side.

    Resolved before the containment test, because an unresolved path compares
    as relative to the root while pointing anywhere at all.
    """
    base = root.resolve()
    kept = []
    for doc in documents:
        try:
            resolved = doc.resolve()
        except OSError:
            continue
        if resolved.is_file() and resolved.is_relative_to(base):
            kept.append(doc)
    return kept


def anchored_citations() -> list[tuple[pathlib.Path, str, pathlib.Path, int, int]]:
    """The `compared` bucket, in the shape the staleness test has always read."""

    return [(row.doc, row.anchor, row.target, row.start, row.end)
            for row in classify() if row.reason == "compared"]



class DocCitationTests(unittest.TestCase):
    def test_every_anchored_citation_names_its_symbol_at_the_cited_line(self) -> None:
        stale = []
        for doc, anchor, target, start, end in anchored_citations():
            lines = target.read_text(encoding="utf-8").splitlines()
            window = "\n".join(lines[max(0, start - 1 - WINDOW):end + WINDOW])
            if anchor.rstrip("()") not in window:
                stale.append(
                    f"{doc.relative_to(REPO_ROOT)}: `{anchor}` is not at"
                    f" {target.relative_to(REPO_ROOT)}:{start}")
        self.assertEqual(stale, [], "\n".join(stale))

    def test_the_scan_reaches_the_documents(self) -> None:
        """The control, and deliberately not a threshold on what it found.

        A `PAIR` that matched nothing -- a tightened regex, a moved document
        tree -- would make the test above pass over any number of stale
        citations without comparing a single one. But asserting *how many*
        citations exist makes the control fail whenever the prose is
        reorganised, while the invariant still holds. So this asserts the tree
        was reached and at least one citation was compared; that `PAIR` itself
        works is proved by fixture in the test below rather than by counting.
        """

        self.assertNotEqual(corpus(), [], "the document tree was not reached at all")
        self.assertTrue(anchored_citations() or stable_source_citations(REPO_ROOT), "no citation was compared")

        # Conservation, which is the assertion the two above cannot make. Every
        # token lands in exactly one bucket and no bucket is invented, so a new
        # silencer cannot be added without either naming itself in `REASONS` or
        # breaking this line. A threshold drifts when prose is reorganised; a
        # partition does not.
        counts = census()
        tokens_found = sum(len(TOKEN.findall(
            doc.read_text(encoding="utf-8", errors="replace").replace("\n", " ")))
            for doc in corpus())
        self.assertEqual(sum(counts.values()), tokens_found,
                         "a token was dropped between the scan and the census")
        self.assertLessEqual(set(counts), REASONS,
                             f"reasons outside the vocabulary: {set(counts) - REASONS}")

        # Criterion 6: what was actually validated, rather than assumed.
        # `.github/scripts/run-tests.sh` runs each module as
        # `python -m unittest <module> > <shard>.log 2>&1` with no `-b`, so
        # this lands in `unittest-output.log` on every run.
        # Over `REASONS`, not over `counts`: a bucket that fell to zero is a
        # result, and iterating the counter would delete it from the report.
        print("citation census: " + ", ".join(
            f"{reason}={counts[reason]}" for reason in sorted(REASONS)))

    def test_the_red_buckets_are_empty(self) -> None:
        """The docstring calls two buckets red. Until this, nothing made them so.

        `anchored_citations()` filters to `compared`, so the stale-symbol test
        never sees `target-missing` or `absent-but-present`: a live citation to
        a deleted file, or an `[absent: ...]` on a file that came back, landed
        in its bucket, was counted, and left the suite green. Counting a defect
        is not catching it. The reasons named here are the ones the module
        documents as failures, and this is the assertion that spends them.
        """

        rows = classify()
        for reason in ("target-missing", "absent-but-present"):
            offenders = [
                f"{row.doc.relative_to(REPO_ROOT)}: `{row.path}:{row.start}`"
                for row in rows if row.reason == reason
            ]
            self.assertEqual(offenders, [], f"{reason}:\n" + "\n".join(offenders))

    def test_a_citation_cannot_send_this_test_outside_the_checkout(self) -> None:
        """A citation is a string in a document, and this test opens what it names.

        `REPO_ROOT / path` returns the absolute path when `path` is absolute
        and follows `..` out of the tree, so without this an edit to any
        document under `docs/` could make CI read a file of its choosing.
        """

        self.assertFalse(is_under_repo(pathlib.Path("/etc/passwd")))
        self.assertFalse(is_under_repo(REPO_ROOT / ".." / ".." / "etc" / "passwd"))
        self.assertTrue(is_under_repo(REPO_ROOT / "bin" / "sd"))

    def test_containment_is_not_lexical_and_the_resolve_is_what_makes_it_so(self) -> None:
        """The mutation this predicate invites, named so it cannot be made quietly.

        `Path.is_relative_to` is lexical. Read the predicate's name as
        "containment" and drop the `resolve()` -- which is how a reviewer
        reading the phrase literally would implement it -- and the escape
        below starts answering `True`. The control beside it is what makes
        this test mean anything: the same path is `True` under the lexical
        comparison, so it is the resolve that refuses, not the shape.
        """

        escape = REPO_ROOT / ".." / ".." / "etc" / "passwd"
        self.assertTrue(escape.is_relative_to(REPO_ROOT))
        self.assertFalse(is_under_repo(escape))

    def test_a_missing_target_inside_the_checkout_is_a_stale_citation(self) -> None:
        """The second question that used to share the refusal's `continue`.

        "This path escapes the checkout" is a security refusal and is silent
        forever. "This path is inside the checkout and there is no file
        there" is a stale citation -- precisely what this module was built to
        catch -- and it was discarded through the same branch. Split, the
        first is `escapes-checkout` and the second is `target-missing`, which
        fails.
        """

        missing = REPO_ROOT / "no-such-file-here.md"
        self.assertTrue(is_under_repo(missing), "the path is inside the checkout")
        self.assertFalse(missing.is_file(), "and there is no file at it")

    def test_prose_between_a_symbol_and_a_citation_breaks_the_anchor(self) -> None:
        """The rule is adjacency, and adjacency has to actually be required.

        Without this, a `PAIR` that tolerated arbitrary text between the two
        would reintroduce the mis-attribution the docstring describes, and the
        gate would start reporting accurate citations as stale.
        """

        self.assertTrue(PAIR.search("`status_filter` (`bin/sd:1378`)"))
        self.assertIsNone(PAIR.search("`status_filter` is reported by `bin/sd:1378`"))


class TheMarkerGrammar(unittest.TestCase):
    """0.71.34's grammar, and the four ways of not writing a marker.

    `[quoted: <reason>]` is the answer to "can a document quote a citation
    without making it a claim". It was found by being caught: this item's own
    PRD reproduced the module's self-test verbatim and `make check` failed on
    *that file*, because quoting the example asserted something false about
    this repository. A gate that cannot be shown an example cannot be
    documented.

    The negatives carry the weight. A marker with no reason is the mute button
    -- `[quoted]` under another name -- and is rejected for the same reason
    `until` is required of an accepted protection gap: an exemption nobody has
    to justify is a silencer with better manners.
    """

    def reason_for(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "doc.md").write_text(text + "\n", encoding="utf-8")
            rows = classify([root / "doc.md"])
            self.assertEqual(len(rows), 1, f"{len(rows)} tokens in {text!r}")
            return rows[0].reason

    def test_a_marker_with_a_reason_exempts_the_citation_it_follows(self) -> None:
        self.assertEqual(
            self.reason_for("`f` (`bin/x.py:1`) [quoted: bin/sd:1]"), "quoted")

    def test_a_marker_with_no_reason_does_not_exempt(self) -> None:
        self.assertNotEqual(self.reason_for("`f` (`bin/x.py:1`) [quoted:]"), "quoted")

    def test_a_marker_whose_reason_is_blank_does_not_exempt(self) -> None:
        self.assertNotEqual(self.reason_for("`f` (`bin/x.py:1`) [quoted: ]"), "quoted")

    def test_anything_non_blank_between_the_two_breaks_the_marker(self) -> None:
        self.assertNotEqual(
            self.reason_for("`f` (`bin/x.py:1`) see [quoted: bin/sd:1]"), "quoted")

    def test_a_marker_on_the_next_line_does_not_exempt(self) -> None:
        """Testable only because the flattening is offset-preserving.

        `classify` flattens with one space per newline, so an offset in the
        flattened text is the same offset in the raw text and the line rule
        can still be asked. Under a genuinely lossy flatten this case could
        not fail, and the grammar's line clause would be decoration.
        """

        self.assertNotEqual(
            self.reason_for("`f` (`bin/x.py:1`)\n[quoted: bin/sd:1]"), "quoted")

    def test_no_line_terminator_the_grammar_names_can_be_spanned(self) -> None:
        """All four, because the first version of this checked only `\n`.

        0.71.34 is explicit: "Reasons may not span a line terminator, `\r`
        and U+2028/U+2029 included". A reason class excluding only `\n` lets
        `[absent: x\u2028y]` through, and that marker suppresses a
        missing-target failure -- a guard failing open on an exotic separator,
        which is worth less than no guard because it reads as covered. Each
        terminator is asserted separately so a partial fix cannot pass.
        """

        for name, mark in (("newline", "\n"), ("carriage return", "\r"),
                           ("line separator", "\u2028"),
                           ("paragraph separator", "\u2029")):
            with self.subTest(terminator=name):
                self.assertNotEqual(
                    self.reason_for(f"`f` (`bin/x.py:1`) [quoted: bin/sd{mark}:1]"),
                    "quoted", f"a reason spanning a {name} exempted the citation")

    def test_a_marker_covers_one_citation_and_not_the_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "doc.md").write_text(
                "`f` (`bin/x.py:1`) [quoted: bin/sd:1] and `g` (`bin/x.py:2`)\n",
                encoding="utf-8")
            reasons = [row.reason for row in classify([root / "doc.md"])]
        self.assertEqual(reasons.count("quoted"), 1, reasons)


class TheSeparatorIsNarrowedByAParenthesis(unittest.TestCase):
    """Criterion 4: the comma shape, and why it is not simply admitted.

    Measured before it was decided. Of the punctuation-shaped near misses in
    the corpus, the parenthesised comma is a real anchored citation and the
    bare ones are **list separators** whose citations are anchored by the
    token to their *right*. Widening `PAIR` to the bare comma makes a
    left-scanning regex take the tail of the previous list item as the anchor
    and report a symbol nobody claimed -- the mis-attribution
    `test_prose_between_a_symbol_and_a_citation_breaks_the_anchor` was written
    to prevent, arriving through punctuation rather than prose.

    The last two fixtures are the point. A synthetic negative proves the regex
    is narrow; only the shapes taken verbatim from the corpus prove it is
    narrow enough for this corpus.
    """

    def test_a_parenthesised_comma_is_an_anchored_citation(self) -> None:
        self.assertTrue(PAREN_PAIR.search("(`status_filter`, `bin/sd:1378`)"))

    def test_a_parenthesised_semicolon_is_too(self) -> None:
        self.assertTrue(PAREN_PAIR.search("(`status_filter`; `bin/sd:1378`)"))

    def test_a_bare_comma_is_not(self) -> None:
        self.assertIsNone(PAREN_PAIR.search("`status_filter`, `bin/sd:1378`"))

    def test_a_bare_semicolon_is_not(self) -> None:
        self.assertIsNone(PAREN_PAIR.search("`status_filter`; `bin/sd:1378`"))

    def test_a_real_comma_separated_list_is_not(self) -> None:
        """Verbatim from `docs/work/.../implement.md`: three files, listed."""

        self.assertIsNone(PAREN_PAIR.search(
            "returns three files: `AGENTS.md:14`, `skills/sd-plan/SKILL.md:40` and"))

    def test_a_real_list_inside_a_parenthesis_anchors_on_no_symbol(self) -> None:
        """Verbatim from `design.md`. `PAREN_PAIR` matches it; the anchor rule declines it.

        This is the shape that made the first, approximate `anchor_for` wrong:
        it filed the pair as a bare separator. Matching it and then declining
        it on the anchor is the correct path, and the two are different
        buckets, so the census can tell them apart.
        """

        text = "(`bin/sd-review:514`, `skills/sd-review/SKILL.md:39`)"
        self.assertTrue(PAREN_PAIR.search(text))
        self.assertFalse(is_symbol("bin/sd-review:514"))


class TheReasonsThatHaveNoLiveInstance(unittest.TestCase):
    """`escapes-checkout` and `quoted`, reachable only because the corpus is a parameter.

    `escapes-checkout` has never fired on real content -- measured over the
    whole corpus, no citation anywhere resolves outside the checkout -- and a
    function that fetches its own input can only be tested against whatever it
    fetches. Splitting the predicate is what lets that silence stay visible
    rather than being inferred from a silence it used to share with a live
    defect.
    """

    def classify_one(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "doc.md").write_text(text + "\n", encoding="utf-8")
            rows = classify([root / "doc.md"])
            self.assertEqual(len(rows), 1, f"{len(rows)} tokens in {text!r}")
            return rows[0].reason

    def test_a_citation_escaping_the_checkout_is_named_and_not_merged(self) -> None:
        self.assertEqual(
            self.classify_one("`frontmatter` (`../../etc/passwd:1`)"),
            "escapes-checkout")

    def test_a_missing_target_inside_the_checkout_is_a_different_bucket(self) -> None:
        self.assertEqual(
            self.classify_one("`frontmatter` (`bin/no-such-file:1`)"),
            "target-missing")

    def test_an_absent_marker_moves_it_out_of_the_failing_bucket(self) -> None:
        self.assertEqual(
            self.classify_one(
                "`frontmatter` (`bin/no-such-file:1`) [absent: deleted in 0.72.0]"),
            "declared-absent")

    def test_an_absent_marker_on_a_file_that_exists_is_the_claim_going_stale(self) -> None:
        """The pair to the test above, and the one that makes the marker honest.

        `[absent: ...]` is the only marker that asserts something about the
        world rather than about the prose, so it is the only one that can be
        contradicted by the world. A file that comes back -- restored, renamed
        back, un-deleted -- leaves the marker behind saying it is gone. Without
        this the marker is a permanent exemption bought once and never re-read,
        which is the thing this module exists to stop.
        """

        self.assertEqual(
            self.classify_one(
                "`is_symbol` (`tests/test_doc_citations.py:232`) [absent: never was]"),
            "absent-but-present")

    def test_the_elided_form_names_no_file_and_is_counted(self) -> None:
        self.assertEqual(self.classify_one("as written at `:1378`"), "elided-path")


# An explicit declaration locator carries no line claim. Keep the existing
# path:line rule above strict; only this spelling survives line movement.
STABLE_SOURCE = re.compile(r"`source:([A-Za-z0-9_./-]+)::([A-Za-z_][A-Za-z0-9_]*)`")


#: Living documents that sit above `docs/`. `CONTRIBUTING.md` is where the
#: convention itself is written down, example included, so a corpus that skips
#: it would let the one citation every reader copies rot first and unnoticed.
ROOT_DOCUMENTS = ("CONTRIBUTING.md",)


def stable_source_citations(root: pathlib.Path) -> list[tuple[pathlib.Path, str, str]]:
    """Explicit source:path::symbol locators; existing pytest node IDs are untouched."""
    # The archive rule is this reader's own, stated here rather than inherited
    # from `contained`. `classify` deliberately *does* read archives -- it
    # reports a stale archived citation instead of failing it -- so a shared
    # filter would have made one rule's corpus an accident of the other's.
    documents = [d for d in sorted(root.glob("docs/**/*.md"))
                 if "archive" not in d.parts]
    documents += [root / name for name in ROOT_DOCUMENTS if (root / name).is_file()]
    found = []
    for doc in contained(root, documents):
        found.extend((doc, path, symbol) for path, symbol in
                     STABLE_SOURCE.findall(doc.read_text(encoding="utf-8")))
    return found


def source_declaration_error(root: pathlib.Path, path: str, symbol: str) -> str | None:
    """Resolve a Python top-level declaration without reading outside the checkout.

    Functions, classes and assigned names are declarations; comments, strings
    and call sites cannot keep a deleted definition's citation passing. This
    also handles extensionless Python entrypoints such as bin/sd-docs-lint.
    """
    import ast

    try:
        target = (root / path).resolve()
        if not target.is_relative_to(root.resolve()):
            return None  # Preserve the line rule's containment exclusion.
        if not target.is_file():
            return f"{path}: target is missing"
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=path)
    except (OSError, UnicodeError, SyntaxError) as error:
        return f"{path}: cannot read a Python source declaration: {error}"

    # Module level, then one level into each class. A test method is a
    # declaration a document cites by name as readily as a function is, and
    # `TestCase` puts every one of them inside a class. Not deeper: a name
    # defined inside a function body is a local, and a citation to one is a
    # claim about an implementation detail that has no stable identity.
    bodies = [tree.body]
    bodies += [node.body for node in tree.body if isinstance(node, ast.ClassDef)]
    declarations = 0
    for body in bodies:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                declarations += node.name == symbol
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                declarations += sum(
                    isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store)
                    and name.id == symbol
                    for target in targets for name in ast.walk(target)
                )
    if declarations != 1:
        return (f"{path}::{symbol}: expected one declaration at module or class "
                f"level, found {declarations}")
    return None


class StableSourceCitationTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.target = self.root / "bin" / "tool"
        self.target.parent.mkdir()
        self.target.write_text("def render():\n    pass\n", encoding="utf-8")

    def test_inserted_lines_do_not_break_a_declaration_locator(self) -> None:
        self.assertIsNone(source_declaration_error(self.root, "bin/tool", "render"))
        self.target.write_text("# inserted\n" * 100 + self.target.read_text(), encoding="utf-8")
        self.assertIsNone(source_declaration_error(self.root, "bin/tool", "render"))

    def test_deleted_renamed_or_comment_only_symbols_fail(self) -> None:
        for source in (
            "", "def renamed():\n    pass\n", "# def render():\ntext = 'render'\n", "render()\n"
        ):
            with self.subTest(source=source):
                self.target.write_text(source, encoding="utf-8")
                self.assertIn(
                    "found 0", source_declaration_error(self.root, "bin/tool", "render") or ""
                )

    def test_duplicate_declarations_fail_as_ambiguous(self) -> None:
        self.target.write_text(self.target.read_text() * 2, encoding="utf-8")
        self.assertIn(
            "found 2", source_declaration_error(self.root, "bin/tool", "render") or ""
        )

    def test_constants_and_classes_are_declarations(self) -> None:
        self.target.write_text("LIMIT = 2\nLABEL: str = 'name'\nclass Reader:\n    pass\n")
        for symbol in ("LIMIT", "LABEL", "Reader"):
            with self.subTest(symbol=symbol):
                self.assertIsNone(source_declaration_error(self.root, "bin/tool", symbol))

    def test_missing_inside_target_fails(self) -> None:
        self.assertIn(
            "target is missing",
            source_declaration_error(self.root, "bin/missing", "render") or "",
        )

    def test_outside_targets_are_never_opened(self) -> None:
        from unittest import mock

        link = self.root / "escape"
        link.symlink_to(self.root.parent / "outside.py")
        with mock.patch.object(pathlib.Path, "read_text", side_effect=AssertionError("opened")):
            for path in (str(self.root.parent / "outside.py"), "../outside.py", "escape"):
                with self.subTest(path=path):
                    self.assertIsNone(source_declaration_error(self.root, path, "render"))

    def test_only_explicit_locators_are_scanned_and_archives_stay_excluded(self) -> None:
        docs = self.root / "docs"
        archive = docs / "archive"
        archive.mkdir(parents=True)
        (docs / "current.md").write_text(
            "`render` (`source:bin/tool::render`) and `gh` (`GH_RECORDER`)\n"
            "`render` (`bin/tool:1`) and `tests/missing.py::test_historical`\n", encoding="utf-8"
        )
        (archive / "old.md").write_text("`source:bin/missing::gone`\n", encoding="utf-8")
        self.assertEqual(
            stable_source_citations(self.root), [(docs / "current.md", "bin/tool", "render")]
        )

    def test_root_documents_are_scanned_beside_the_docs_tree(self) -> None:
        """`CONTRIBUTING.md` states the convention, so its own example must resolve.

        Scoping the corpus to `docs/**` would leave the citation every reader
        copies as the only one nothing checks.
        """

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "current.md").write_text("`source:bin/tool::render`\n", encoding="utf-8")
        contributing = self.root / "CONTRIBUTING.md"
        contributing.write_text("prefer `source:bin/tool::render`\n", encoding="utf-8")
        self.assertIn(
            (contributing, "bin/tool", "render"), stable_source_citations(self.root)
        )
        contributing.write_text("prefer `source:bin/tool::deleted`\n", encoding="utf-8")
        self.assertIn(
            "found 0",
            source_declaration_error(self.root, "bin/tool", "deleted") or "",
        )

    def test_a_symlinked_document_is_never_read(self) -> None:
        """The document is an input too, not only the file its citation names.

        `glob` returns a symlink as readily as a file and `read_text` follows
        it, so without this a tracked `docs/current.md` could point anywhere
        and have CI read it. Asserted on both walks, because both glob the
        same tree.
        """

        docs = self.root / "docs"
        docs.mkdir()
        outside = self.root.parent / f"outside-{os.getpid()}.md"
        outside.write_text(
            "`source:bin/tool::render` and `render` (`bin/tool:1`)\n", encoding="utf-8"
        )
        self.addCleanup(outside.unlink)
        (docs / "escape.md").symlink_to(outside)
        (docs / "real.md").write_text("`source:bin/tool::render`\n", encoding="utf-8")

        collected = stable_source_citations(self.root)
        self.assertEqual([doc for doc, _, _ in collected], [docs / "real.md"])
        self.assertEqual(contained(self.root, [docs / "escape.md"]), [])

        with mock.patch.dict(globals(), {"REPO_ROOT": self.root}):
            self.assertEqual(anchored_citations(), [])

    def test_existing_line_citations_still_reject_line_movement(self) -> None:
        from unittest import mock

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "current.md").write_text("`render` (`bin/tool:1`)\n", encoding="utf-8")
        self.target.write_text("# inserted\n" * 100 + self.target.read_text(), encoding="utf-8")
        with mock.patch.dict(globals(), {"REPO_ROOT": self.root}):
            with self.assertRaisesRegex(AssertionError, "is not at"):
                DocCitationTests().test_every_anchored_citation_names_its_symbol_at_the_cited_line()

    def test_scan_control_accepts_a_corpus_using_only_stable_locators(self) -> None:
        from unittest import mock

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "current.md").write_text("`source:bin/tool::render`\n", encoding="utf-8")
        with mock.patch.dict(globals(), {"REPO_ROOT": self.root}):
            self.assertEqual(anchored_citations(), [])
            DocCitationTests().test_the_scan_reaches_the_documents()

    def test_every_explicit_source_locator_resolves_in_the_live_corpus(self) -> None:
        citations = stable_source_citations(REPO_ROOT)
        failures = []
        for doc, path, symbol in citations:
            problem = source_declaration_error(REPO_ROOT, path, symbol)
            if problem:
                failures.append(f"{doc.relative_to(REPO_ROOT)}: {problem}")
        self.assertEqual(failures, [], "\n".join(failures))


#: **Which skills must qualify the citation: all of them, and none is named.**
#:
#: The rule has no exception list because the reason is structural rather than
#: per-skill. A skill is installed to the platform home and read with the
#: reader's cwd in whatever checkout encloses it (R10-D6); nothing makes that
#: checkout this one. `sd-research-repo` is read from a research repo,
#: `sd-plan`/`sd-review`/`sd-ship` from whatever repository is being developed.
#: So a rule path any of them cites resolves against a checkout that need not
#: have the file. No skill is exempt, so no skill has to be remembered, and
#: both ends of this scan are walked from the filesystem: the documents from
#: `skills/`, the paths that matter from `.claude/rules/`.
#:
#: The predecessor hardcoded `FOREIGN_SKILL = "skills/sd-research-repo"`, which
#: was narrower than the defect it was written for -- four skills carried the
#: citation and one was watched.
SKILLS_DIR = "skills"

#: **Which paths are in scope: the pack's authored rules, enumerated.**
#:
#: Not "every path that happens to resolve in this checkout", which was the
#: predecessor's test and is wrong the moment it leaves one skill. Run broadly
#: it flags `.github/sd-review.json`, `.github/workflows/sd-review-route.yml`
#: and `.github/sd-status.json` -- per-repository configuration that the
#: *reader's* checkout is supposed to carry, which `bin/sd_setup_github.py`
#: writes there. Those are correct unqualified, and rewriting them to name the
#: pack would be the worse bug.
#:
#: What makes `.claude/rules/` different is that it is the one surface the pack
#: authors, tells the reader to go and *read* for authoritative content, and
#: cannot put in the reader's checkout:
#:
#:   * it is not installed -- `bin/sd_install.py` carries zero `.claude/rules`
#:     references, so it cannot be fanned out;
#:   * it cannot be shipped as a copy either -- the caps table is allowed
#:     exactly two copies and `tests/test_workflow_policy.py::ReviewTable`
#:     enforces that, so a third beside a skill fails the gate;
#:   * and resolving it against the wrong checkout is silent. The reader finds
#:     no file, reads no cap, and the review pass proceeds as if it had one.
#:     Confirmed absent in all seven research repos on this machine.
#:
#: So the invariant is the only one left: the prose names the checkout that
#: holds it. The rule files themselves are globbed, not listed, so a rule added
#: next to this one is covered on the day it is written.
RULES_DIR = ".claude/rules"

#: A backticked path with a directory separator. Only those make a claim about
#: some checkout's layout; a bare `CLAUDE.md` or `research.conf.py` is a name
#: the research-repo standard defines and not a pointer into this repository.
#: The leading `\.?` is load-bearing and was missing in the first draft: every
#: path this check exists for begins `.claude/`, so without it the scan matched
#: nothing and the live test passed over the defect it was written to catch.
BACKTICKED_PATH = re.compile(r"`(\.?[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:md|py|json|toml|ya?ml|sh))`")
#: Word-bounded, and that is the whole point. An unbounded `pack` is satisfied
#: by "the package documentation", "the packaging notes" or "unpack the brief",
#: so an unqualified citation with any of those within the window read as
#: qualified and the scan passed it -- verified against all three before this
#: was tightened. A guard with a false negative is worse than no guard, because
#: the class then looks clean. The boundary still matches what the prose
#: actually says: `pack`, `pack's`, and the `pack` in `sd-ai-command-pack`,
#: whose preceding `-` is a non-word character.
QUALIFIER = re.compile(r"\bpack\b", re.IGNORECASE)

#: Enough to reach back over "live in the sd-ai-command-pack checkout's" and a
#: line wrap, and short enough that the word has to be about this citation.
#:
#: Read on *both* sides of the citation, which the first version did not.
#: English puts the qualification either way round -- "the cap is in the
#: sd-ai-command-pack checkout's `<path>`" and "`<path>` ... that file lives
#: only in the sd-ai-command-pack checkout" are the same statement -- and a
#: guard that accepts one word order and not the other enforces a house style
#: instead of the invariant. Both forms are live in `skills/` today.
QUALIFIER_WINDOW = 100


def skill_documents(root: pathlib.Path) -> list[pathlib.Path]:
    """Every authored `*.md` under `skills/`, walked from the filesystem.

    Enumeration, not a roster. A skill that acquires a pack-path citation next
    month is covered the day it is written, with nobody updating anything --
    which is the property the hardcoded predecessor did not have.
    """

    return contained(root, sorted((root / SKILLS_DIR).rglob("*.md")))


def pack_rule_paths(root: pathlib.Path) -> set[str]:
    """The pack's authored rule files, as the paths a skill would cite them by.

    Globbed, so the scope grows with the directory rather than with anyone's
    memory of what is in it.
    """

    rules = root / RULES_DIR
    return {
        str(rule.relative_to(root))
        for rule in contained(root, sorted(rules.rglob("*.md")))
    }


def rule_path_citations(root: pathlib.Path) -> list[tuple[pathlib.Path, str, bool]]:
    """Every citation of a pack rule file from any skill, and whether the prose
    beside it names the checkout that holds it.

    Enumerated from disk on both axes: the documents come from walking
    `skills/`, and what counts as a rule path comes from walking
    `.claude/rules/`. Neither is a list anybody maintains.
    """

    rule_paths = pack_rule_paths(root)
    found: list[tuple[pathlib.Path, str, bool]] = []
    for doc in skill_documents(root):
        # Newlines flattened: the qualifier routinely wraps away from the path.
        flat = doc.read_text(encoding="utf-8").replace("\n", " ")
        for match in BACKTICKED_PATH.finditer(flat):
            cited = match.group(1)
            if cited not in rule_paths:
                continue
            # The citation itself is excluded from the window on purpose: a
            # cited path with `pack` as a segment would otherwise qualify
            # itself, which is a citation vouching for its own resolution.
            before = flat[max(0, match.start() - QUALIFIER_WINDOW):match.start()]
            after = flat[match.end():match.end() + QUALIFIER_WINDOW]
            found.append((doc, cited, bool(QUALIFIER.search(before) or QUALIFIER.search(after))))
    return found


def unqualified_rule_paths(root: pathlib.Path) -> list[str]:
    """The failures, as `<document>: <path>` lines."""

    return [
        f"{doc.relative_to(root)}: `{cited}` lives only in this pack, cited to a reader"
        " standing in some other checkout without naming the pack"
        for doc, cited, qualified in rule_path_citations(root)
        if not qualified
    ]


class ForeignCheckoutCitationTests(unittest.TestCase):
    def test_no_rule_path_is_cited_as_if_the_reader_s_checkout_had_it(self) -> None:
        problems = unqualified_rule_paths(REPO_ROOT)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_scan_reaches_the_skills(self) -> None:
        """The control, and it is not a formality.

        The first draft's regex rejected a leading dot, so it matched none of
        the `.claude/...` paths this check exists for and the test above passed
        on the unfixed tree. Asserting that the skills were globbed is not
        enough; both ends of the walk have to have produced something and a
        citation has to have been classified.
        """

        self.assertNotEqual(skill_documents(REPO_ROOT), [], "no skill document was walked")
        self.assertNotEqual(pack_rule_paths(REPO_ROOT), set(), "no rule file was walked")
        self.assertNotEqual(rule_path_citations(REPO_ROOT), [], "no rule citation was classified")

    def test_the_walk_covers_every_skill_and_not_a_named_one(self) -> None:
        """The generalisation, asserted rather than assumed.

        The predecessor hardcoded `skills/sd-research-repo` and so watched one
        skill while four carried the citation. Two things are checked. Every
        directory holding a `SKILL.md` is reached by the walk -- computed from
        disk on both sides, so adding a skill cannot quietly fall outside it.
        And the citations actually classified come from more than one skill,
        which a walk that had silently collapsed back to a single directory
        could not satisfy.
        """

        authored = {
            skill.parent for skill in (REPO_ROOT / SKILLS_DIR).rglob("SKILL.md")
        }
        self.assertGreater(len(authored), 1, "the skills tree did not enumerate")
        walked = {doc.parent for doc in skill_documents(REPO_ROOT)}
        self.assertEqual(authored - walked, set(), "a skill directory was not walked")

        cited_by = {doc.relative_to(REPO_ROOT).parts[1] for doc, _, _ in rule_path_citations(REPO_ROOT)}
        self.assertGreater(len(cited_by), 1, f"only one skill was scanned: {sorted(cited_by)}")

    def fixture(self) -> pathlib.Path:
        """A checkout with the cap file and an empty `skills/` tree."""

        import tempfile

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = pathlib.Path(temporary.name)
        (root / SKILLS_DIR).mkdir()
        (root / ".claude" / "rules").mkdir(parents=True)
        (root / ".claude" / "rules" / "caps.md").write_text("| Cap |\n", encoding="utf-8")
        return root

    def test_an_unqualified_pack_path_is_caught_and_a_qualified_one_is_not(self) -> None:
        """The guard against the guard: the defect this class exists for.

        Both halves matter. Without the first the check can never fail; without
        the second it fails on every correctly-written citation and gets
        deleted the next time someone needs the build green.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        (skill / "references").mkdir(parents=True)

        document = skill / "SKILL.md"
        document.write_text("its cap is in\n`.claude/rules/caps.md`.\n", encoding="utf-8")
        self.assertEqual(len(unqualified_rule_paths(root)), 1)

        document.write_text(
            "its cap is in the pack's\n`.claude/rules/caps.md`.\n", encoding="utf-8")
        self.assertEqual(unqualified_rule_paths(root), [])

    def test_any_skill_is_watched_and_the_failure_names_the_one_at_fault(self) -> None:
        """The generalisation, at fixture scale.

        Three skills, none of them the one the predecessor hardcoded, and only
        the middle one unqualified. A guard scoped to a named skill reports
        nothing here; this one reports exactly the offender, by name. The two
        well-written neighbours are the other direction -- a guard that fires
        on correct prose is worse than the bug, because it gets deleted.
        """

        root = self.fixture()
        for name, prose in (
            ("sd-alpha", "its cap is in the sd-ai-command-pack checkout's"),
            ("sd-beta", "its cap is in"),
            ("sd-gamma", "read the caps in the pack's"),
        ):
            skill = root / SKILLS_DIR / name
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                f"{prose}\n`.claude/rules/caps.md`.\n", encoding="utf-8")

        problems = unqualified_rule_paths(root)
        self.assertEqual(len(problems), 1, "\n".join(problems))
        self.assertIn(f"{SKILLS_DIR}/sd-beta/SKILL.md", problems[0])

    def test_the_qualifier_counts_on_either_side_of_the_citation(self) -> None:
        """The word order is prose, not the invariant.

        "the pack's `<path>`" and "`<path>` ... that file lives only in the
        sd-ai-command-pack checkout" say the same thing, and both are live in
        `skills/` today. A window that reads only backwards passes the first
        and fails the second, which makes the guard a style rule. The third
        case is the one that must still fail: a mention far enough away to be
        about something else does not qualify anything.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        skill.mkdir()
        document = skill / "SKILL.md"

        document.write_text(
            "the cap is on that row in\n`.claude/rules/caps.md`.\nThat file lives only in"
            " the sd-ai-command-pack checkout.\n", encoding="utf-8")
        self.assertEqual(unqualified_rule_paths(root), [])

        document.write_text(
            "the cap is on that row in\n`.claude/rules/caps.md`.\n"
            f"{'Read it before promoting the item. ' * 6}It ships with the pack.\n",
            encoding="utf-8")
        self.assertEqual(len(unqualified_rule_paths(root)), 1)

    def test_a_word_containing_pack_does_not_qualify_a_citation(self) -> None:
        """The false negative from the other side, and the reason for `\\b`.

        The first version matched `pack` as a bare substring, so "the package
        documentation", "the packaging notes" and "unpack the brief" all read
        as naming this pack and let an unqualified citation through. Each of
        the three was confirmed to slip through before the boundary was added.
        A guard that cannot fail is worse than no guard: the class it watches
        then looks clean.

        The second half is the one that matters as much -- the boundary must
        still accept what the prose really says, or the guard fires on every
        correct citation and gets deleted the next time the build is red.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        skill.mkdir()
        document = skill / "SKILL.md"

        for decoy in (
            "the package documentation says the cap is in",
            "see the packaging notes; the cap is in",
            "unpack the brief first. The cap is in",
            "the cap is in",
        ):
            with self.subTest(lead=decoy):
                document.write_text(f"{decoy}\n`.claude/rules/caps.md`.\n", encoding="utf-8")
                self.assertEqual(len(unqualified_rule_paths(root)), 1)

        for real in (
            "the cap is in the sd-ai-command-pack checkout's",
            "the caps live in the pack's",
            "read it in the pack at",
        ):
            with self.subTest(lead=real):
                document.write_text(f"{real}\n`.claude/rules/caps.md`.\n", encoding="utf-8")
                self.assertEqual(unqualified_rule_paths(root), [])

    def test_paths_that_are_not_pack_rules_are_left_alone(self) -> None:
        """The scope, and why it is the rules directory rather than everything.

        Each of these is correct *because* it resolves against the reader's
        checkout, and rewriting it to name the pack would be the worse bug this
        test exists to prevent:

        * `references/x.md` ships beside the installed skill.
        * `.github/sd-review.json` and `.github/workflows/sd-review-route.yml`
          are per-repository configuration written into the reader's checkout
          by `bin/sd_setup_github.py`; the reader's copy is the one that
          governs. A draft of this class that flagged every path resolving in
          this checkout reported all three, plus `.github/sd-status.json`.
        * a path this checkout does not have is naming another repository,
          which is what the prose beside it says.
        """

        root = self.fixture()
        skill = root / SKILLS_DIR / "sd-example"
        skill.mkdir()
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "sd-review.json").write_text("{}\n", encoding="utf-8")
        (root / ".github" / "workflows" / "route.yml").write_text("on: push\n", encoding="utf-8")
        (skill / "SKILL.md").write_text(
            "read `references/conventions.md`, the repository's `.github/sd-review.json`,"
            " the route in `.github/workflows/route.yml`, and"
            " `local-adversarial-gate/core.md`\n",
            encoding="utf-8")
        self.assertEqual(unqualified_rule_paths(root), [])


if __name__ == "__main__":
    unittest.main()
