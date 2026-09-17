"""No literal count restating something enumerable, unless it is a measurement.

sd:431's prose rule 2, R13-D2. "The pack ships 16 tools" in a skill is a claim
that rots: the day a seventeenth lands nothing fails, and the sentence goes on
being read as current. The same number reported against a commit is a
measurement -- `bin/` carries 768 `def` lines on `e6c2cb20` -- and it stays
true forever, because it says when it was true. So the rule is on
present-tense counts, and a line that carries its own commit, pull request
number or date is exempt; the design records that the first page the rule
would otherwise redden is the one that proposed it.

**Why a test module and not a `bin/sd-docs-lint` rule.** The backbone item
assumed the linter "already walks the corpus". Measured on `ef7c0c7b`: its
tree rules read `docs/work` only, and rule 7 opens every tracked markdown file
to resolve `docs/work/` references and reads it for nothing else. None of the
pages this rule is about -- the skills, `README.md`, `AGENTS.md`, the spec
pages, the rules under `.claude/` -- is read for its prose by any rule there,
so a rule added to the linter would have had to bring its own walk anyway,
and a test over the tree is the shape every other registry checker has.

**The predicate is narrow on purpose, and its false negatives are accepted.**
`<number> <noun>` with the noun drawn from `ENUMERABLE` on one line: a count
written as a word, a noun not in the set, or a number and its noun split
across a line break are all invisible here. It is a ratchet on new claims,
not an audit of old ones, and a ratchet with false negatives still moves one
way. Widening the noun set is a change to the rule and re-measures the
baseline; the set was read off the corpus on `ef7c0c7b`, where the wider
candidates -- `lines`, `rows`, `scripts` -- named thresholds and measurements
and no enumerable thing.
"""

from __future__ import annotations

import collections
import pathlib
import re
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The live prose an author writes as current fact, as `git ls-files`
#: pathspecs. The skills as leg b reads them -- every markdown file under
#: `skills/`, templates included, because a template is installed as prose --
#: and the pages above `docs/` that describe the pack as it is. `docs/work` is
#: out: a planning page is a record, and the design says its counts are
#: measurements once they carry a commit, which its convention requires.
CORPUS = ("skills/*.md", "skills/**/*.md", "README.md", "AGENTS.md",
          "docs/spec/**", ".claude/rules/**")

#: The nouns a count restates something enumerable with.
ENUMERABLE = ("tools", "commands", "skills", "tests", "rules", "files", "verbs",
              "checkers", "surfaces", "agents", "platforms")

#: `16 tools`, `2,998 files`: a number, then one of the nouns, on one line.
#: The lookbehind keeps a number out of a path, a time, a version and a
#: decimal, where it is not a count of anything.
COUNT = re.compile(
    r"(?<![\w.,:/-])(\d[\d,]*)\s+(" + "|".join(ENUMERABLE) + r")\b")

#: The marks that turn a claim into a measurement: a commit of seven or more
#: hex digits, a `#<n>` pull request or note number, a `YYYY-MM-DD` date.
MEASURED_AGAINST = re.compile(
    r"\b[0-9a-f]{7,40}\b|(?<!\w)#\d+\b|\b\d{4}-\d{2}-\d{2}\b")

FENCE = re.compile(r"^\s*(?:```|~~~)")
CODE_SPAN = re.compile(r"`[^`\n]*`")

#: Present-tense count claims per document, measured on `ef7c0c7b` by
#: `present_tense_counts` below. A ratchet on violations: each entry may fall
#: and may not rise, and an entry at zero is deleted. Both lines held here
#: are the predicate's own edges rather than claims about the pack -- one
#: describes a test's coverage points, the other reads `surfaces` as a verb --
#: and they stay because exempting them would need a parser the design
#: declined. Per document, so a new claim in one page cannot be netted off
#: against a cleanup in another.
PRESENT_TENSE_COUNTS = {
    "docs/spec/backend/quality-guidelines.md": 1,
    "skills/sd-status/SKILL.md": 1,
}


def tracked(root: pathlib.Path = REPO_ROOT) -> list[pathlib.Path]:
    """Every tracked markdown file the corpus names, as the index reports it."""

    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--deduplicate", "--", *CORPUS],
        capture_output=True, text=True, check=True).stdout.split("\0")
    return [root / name for name in listed if name.endswith(".md")]


def count_claims(text: str) -> list[tuple[int, str]]:
    """Every present-tense count in one document, as `(line, text)`.

    Fenced blocks are skipped whole and a count inside a code span is not
    read, because a command's output pasted into a page is a measurement by
    construction. The mark is read off the whole line, code spans included:
    a commit is written `` `ef7c0c7b` `` in this repository more often than
    bare. The scope is one line, as leg b's is: a count and a date in the same
    paragraph are not one claim about one measurement.
    """

    found = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        if COUNT.search(CODE_SPAN.sub("~", line)) and not MEASURED_AGAINST.search(line):
            found.append((number, line.strip()))
    return found


def present_tense_counts(root: pathlib.Path = REPO_ROOT) -> dict[str, int]:
    """Present-tense count claims, counted per document."""

    counts: collections.Counter = collections.Counter()
    for path in tracked(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for _ in count_claims(text):
            counts[path.relative_to(root).as_posix()] += 1
    return dict(counts)


class TheCountPredicate(unittest.TestCase):
    """What is a claim and what is a measurement, on fixtures."""

    def claims(self, text: str) -> list[int]:
        return [number for number, _ in count_claims(text)]

    def test_a_count_of_an_enumerable_noun_is_a_claim(self) -> None:
        self.assertEqual(self.claims("The pack ships 16 tools.\n"), [1])
        self.assertEqual(self.claims("2,998 files and 3 skills\n"), [1])

    def test_a_commit_a_number_or_a_date_makes_it_a_measurement(self) -> None:
        for measured in ("16 tools on `ef7c0c7b`", "16 tools on ef7c0c7b",
                         "16 tools since #1011", "16 tools as of 2026-09-16"):
            with self.subTest(measured=measured):
                self.assertEqual(self.claims(measured + "\n"), [])

    def test_the_mark_has_to_be_on_the_claims_own_line(self) -> None:
        self.assertEqual(self.claims("Measured on 2026-09-16:\n16 tools.\n"), [2])

    def test_a_noun_outside_the_set_is_not_read(self) -> None:
        self.assertEqual(self.claims("768 lines, 45 commits, 3 people\n"), [])

    def test_a_number_inside_a_path_a_version_or_a_decimal_is_not_a_count(self) -> None:
        self.assertEqual(self.claims("v1.2 tools, 3.5 files, a/7 skills, 10:30 tests\n"),
                         [])

    def test_a_fence_and_a_code_span_are_measurements_by_construction(self) -> None:
        self.assertEqual(self.claims("```\n16 tools\n```\nsays `16 tools` here\n"), [])

    def test_the_word_boundary_keeps_the_noun_whole(self) -> None:
        self.assertEqual(self.claims("3 toolsmiths and 4 testsuites\n"), [])


class ProseCounts(unittest.TestCase):
    """R13-D2 over the live corpus."""

    def test_present_tense_counts_match_their_baseline(self) -> None:
        """The ratchet. Equality, so a cleanup moves the record with it."""

        self.assertEqual(present_tense_counts(), PRESENT_TENSE_COUNTS, """
The present-tense counts in live prose no longer match their baseline.

Above: measured first, baseline second. A count that rose is a new line
stating how many of something the tree has, as if it were current: derive it,
or report it against the commit, pull request number or date it was measured
at, on the same line. A count that fell is a cleanup: lower the entry in
`PRESENT_TENSE_COUNTS` in the same change, and delete it at zero.""")

    def test_the_walk_reaches_the_corpus(self) -> None:
        """The control: a pathspec that matched nothing would pass the ratchet."""

        seen = {path.relative_to(REPO_ROOT).parts[0] for path in tracked()}
        self.assertLessEqual({"skills", "README.md", "AGENTS.md", "docs"}, seen)

    def test_every_baseline_entry_is_a_tracked_page(self) -> None:
        listed = {path.relative_to(REPO_ROOT).as_posix() for path in tracked()}
        self.assertEqual(sorted(set(PRESENT_TENSE_COUNTS) - listed), [],
                         "a baseline entry names a page the corpus does not hold")


if __name__ == "__main__":  # pragma: no cover - the suite runs this by module
    unittest.main()
