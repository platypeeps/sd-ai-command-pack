"""A `path:line` citation still points at the thing the prose says it does.

A line number is invalidated by any insertion above its target, and nothing
watched them. Step 8-iv demonstrated the failure inside a single branch:
growing `bin/sd` from 1,553 lines to 2,006 moved `frontmatter()` from 1231 to
1248, the reader's `.strip('"')` from 1252 to 1276, and `status_filter` from
1350 to 1378. All three were correct on `main`, all three were wrong on the
branch that changed the file, and the branch that broke them was also the
branch editing the document that carried them.

The planning-adversarial-review contract already asks for this sweep, and it
did catch those three. But it only runs at a planning convergence boundary. A
pure code change that edits no `prd.md`, `design.md` or `implement.md` breaks
citations with nothing to notice; 8-iv was swept only because it happened to
edit `design.md` as well. This runs on every change instead.

**The rule is adjacency.** A citation that directly follows a backticked
symbol -- `` `status_filter` (`bin/sd:1378`) `` -- is a claim *about that
symbol*, and the symbol must appear at the cited line. A citation with prose
between it and the nearest backticked token is making some other claim, and is
skipped rather than guessed at: an earlier draft took the nearest symbol within
90 characters and mis-attributed `bin/sd-status:501-506`, which is an accurate
citation to a docstring that does not happen to repeat the key name. A gate
whose failures need interpreting teaches people to interpret failures away.

Skipped deliberately, each because the check would be wrong rather than
inconvenient:

* **Anything under `archive/`.** An archived record cites the code as it stood.
  `docs/work/archive/` cites `install.py` and `installer/*`, deleted at step 3e.
  Those citations are supposed to be stale; that is what an archive is.
* **A target that no longer exists.** Same reason, for live documents that
  reference sibling repositories (`sd-writing-pack/scripts/pack.py`) or files
  this rollout deleted.
* **An anchor that is a path rather than a symbol.** `` `tests/test_verb_inventory.py` ``
  before a citation says nothing checkable about a particular line.
* **A citation with no adjacent symbol at all**, such as the `bin/sd:323`
  pointer inside a dated, already-addressed incident record whose subject is a
  line that was then changed.
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# A backticked token, then only whitespace or an opening paren, then the
# citation. Anything else between them and this is not a claim about the token.
PAIR = re.compile(r"`([^`\n]+)`\s*\(?`([A-Za-z0-9_./-]+):(\d+)(?:-(\d+))?`")
SYMBOL = re.compile(r"^\.?[A-Za-z_][A-Za-z0-9_.]*(\(.*\))?$")
EXTENSION = re.compile(r"\.(md|py|js|json|sh|ya?ml|toml|txt|lock)$")

# The cited line is where the symbol is *introduced*; prose cites a `def` line
# and the reader looks at the lines under it. Wide enough to survive a
# signature wrapped across lines, narrow enough that a symbol used a hundred
# lines away cannot satisfy it.
WINDOW = 2


def is_symbol(token: str) -> bool:
    """A name a line can be checked against, as opposed to a path or a phrase."""

    return bool(SYMBOL.match(token)) and "/" not in token and not EXTENSION.search(token)


def anchored_citations() -> list[tuple[pathlib.Path, str, pathlib.Path, int, int]]:
    """Every symbol-anchored citation in a live document, enumerated from disk."""

    found = []
    for doc in sorted(REPO_ROOT.glob("docs/**/*.md")):
        if "archive" in doc.parts:
            continue
        # Newlines flattened: a citation routinely wraps away from its symbol.
        flat = doc.read_text(encoding="utf-8").replace("\n", " ")
        for match in PAIR.finditer(flat):
            anchor, path, start = match.group(1), match.group(2), int(match.group(3))
            end = int(match.group(4) or match.group(3))
            target = REPO_ROOT / path
            if not is_symbol(anchor) or not target.is_file():
                continue
            found.append((doc, anchor, target, start, end))
    return found


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

    def test_the_check_finds_citations_to_check(self) -> None:
        """The control.

        A `PAIR` that matched nothing -- a tightened regex, a moved document
        tree -- would make the test above pass over any number of stale
        citations without comparing a single one.
        """

        found = anchored_citations()
        self.assertGreater(len(found), 4, f"only {len(found)} anchored citations found")

    def test_prose_between_a_symbol_and_a_citation_breaks_the_anchor(self) -> None:
        """The rule is adjacency, and adjacency has to actually be required.

        Without this, a `PAIR` that tolerated arbitrary text between the two
        would reintroduce the mis-attribution the docstring describes, and the
        gate would start reporting accurate citations as stale.
        """

        self.assertTrue(PAIR.search("`status_filter` (`bin/sd:1378`)"))
        self.assertIsNone(PAIR.search("`status_filter` is reported by `bin/sd:1378`"))


if __name__ == "__main__":
    unittest.main()
