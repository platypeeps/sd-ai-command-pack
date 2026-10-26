"""Today and Decisions on a phone (pack sd:6017): one column, no clipped words, touch-sized folds.

Operator ruling (grill Q38): Today, Decisions and the Build controls get a first-class phone layout over the tailnet; the
other pages stay desktop-first. A probe in headless Chrome at 320, 375 and 414 px wide, as an iPhone, found what these
tests pin: a folded pane kept the rail as a 216 px column beside the page on a narrow iPad, a long word in a title ran
past the screen edge, and Today's band folds were 23 px tall.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from sd_dashboard import v2

STATIC = Path(v2.__file__).resolve().parent / "static"
SHELL_CSS = (STATIC / "shell.css").read_text(encoding="utf-8")
TODAY_CSS = (STATIC / "today.css").read_text(encoding="utf-8")
DECISIONS_CSS = (STATIC / "decisions.css").read_text(encoding="utf-8")


def blocks(css: str, query: str) -> str:
    """The text of every top-level `@media <query>` block in `css`, comments removed."""
    css, out = re.sub(r"/\*.*?\*/", "", css, flags=re.S), []
    for found in re.finditer(r"@media " + re.escape(query) + r"\s*\{", css):
        depth, end = 1, found.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        out.append(css[found.end():end - 1])
    return "\n".join(out)


def rules(css: str) -> list[tuple[list[str], str]]:
    """Each plain rule in `css` as its selectors and its body."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [([s.strip() for s in sel.split(",")], body) for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)]


class TheShell(unittest.TestCase):
    def test_every_shell_column_rule_is_one_column_on_a_phone(self):
        # A wider rule with more specificity (body[data-pane="min"] .shell) outranked the phone's plain `.shell`.
        setting = {sel for sels, body in rules(SHELL_CSS) for sel in sels
                   if sel.endswith(".shell") and "grid-template-columns" in body}
        phone = {sel for sels, body in rules(blocks(SHELL_CSS, "(max-width: 899px)")) for sel in sels
                 if sel.endswith(".shell") and re.search(r"grid-template-columns:\s*minmax\(0, 1fr\);", body)}
        self.assertTrue(setting)
        self.assertEqual(sorted(setting - phone), [])

    def test_a_band_fold_in_a_header_cell_is_styled_and_touch_sized(self):
        # Today's bands are <th> cells; the fold rules named <td> alone, so its folds kept browser chrome, 23 px tall.
        self.assertIn(":is(td, th) > .tfold { all: unset;", SHELL_CSS)
        self.assertRegex(blocks(SHELL_CSS, "(pointer: coarse)"), r":is\(td, th\) > \.tfold \{ min-height: var\(--row-touch\); \}")


class TheWords(unittest.TestCase):
    def test_a_long_word_in_a_title_wraps_inside_the_screen(self):
        for name, css, selector in (("decisions.css", DECISIONS_CSS, ".decisions .what"),
                                    ("today.css", TODAY_CSS, ".track-table .what")):
            with self.subTest(name):
                bodies = [body for sels, body in rules(css) if selector in sels]
                self.assertTrue(any("overflow-wrap: anywhere" in body for body in bodies), f"{selector} in {name}")


if __name__ == "__main__":
    unittest.main()
