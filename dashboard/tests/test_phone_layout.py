"""Today, Decisions and the Build controls on a phone (pack sd:6017): one column, no clipped words, touch-sized controls.

Operator ruling (grill Q38): Today, Decisions and the Build controls get a first-class phone layout over the tailnet; the
other pages stay desktop-first. A probe in headless Chrome at 320, 375 and 414 px wide, as an iPhone, found what these
tests pin: a folded pane kept the rail as a 216 px column beside the page on a narrow iPad, a long word in a title ran
past the screen edge, and Today's band folds were 23 px tall. A second probe, on a fixture store with open builds, found
the Build controls' faults: the Tasks board's lanes were 2 px wide, the Build dialog cut each item number to "#", a
builder run's ETA sentence squeezed its title to one word a line on Today, and Queue's ended-builds fold was 19 px tall.
The auto-pickup control is not built yet (system design step 7), so it has no layout to pin.
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
TASKS_CSS = (STATIC / "tasks.css").read_text(encoding="utf-8")
QUEUE_CSS = (STATIC / "queue.css").read_text(encoding="utf-8")


def blocks(css: str, query: str, at: str = "@media") -> str:
    """The text of every top-level `<at> <query>` block in `css`, comments removed."""
    css, out = re.sub(r"/\*.*?\*/", "", css, flags=re.S), []
    for found in re.finditer(re.escape(at) + " " + re.escape(query) + r"\s*\{", css):
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


def selectors(css: str, prop: str) -> set[str]:
    """Every selector in `css` whose rule sets `prop`."""
    return {sel for sels, body in rules(css) for sel in sels if re.search(rf"(^|;|\s){re.escape(prop)}:", body)}


class TheBuildControls(unittest.TestCase):
    def test_every_board_form_is_a_snap_carousel_on_a_phone(self):
        # The container rule's [data-nodone] forms outrank a bare .board; the phone block left them at three 2 px columns.
        wide = selectors(blocks(TASKS_CSS, "(max-width: 65.5rem)", "@container"), "grid-template-columns")
        phone = selectors(blocks(TASKS_CSS, "(max-width: 719px)"), "grid-auto-columns")
        self.assertTrue(wide)
        self.assertEqual(sorted(wide - phone), [])
        narrow = selectors(blocks(TASKS_CSS, "(max-width: 380px)"), "grid-auto-columns")
        self.assertEqual(sorted(wide - narrow), [])

    def test_the_build_dialog_keeps_each_item_number_whole(self):
        # `.palette li code` ellipsizes; in a wrapping title row it left "#" and hid which item the Build is for.
        bodies = [body for sels, body in rules(TASKS_CSS) if ".palette .start-list li code" in sels]
        self.assertEqual(len(bodies), 1)
        self.assertIn("flex: none", bodies[0])
        self.assertIn("overflow: visible", bodies[0])

    def test_a_builder_run_puts_its_eta_sentence_under_the_title(self):
        phone = blocks(TODAY_CSS, "(max-width: 899px)")
        row = [body for sels, body in rules(phone) if ".builds tbody tr" in sels]
        self.assertEqual(len(row), 1)
        self.assertIn('". num num"', row[0])
        self.assertIn('"g what what"', row[0])
        num = [body for sels, body in rules(phone) if ".ledger.builds .num" in sels]
        self.assertEqual(len(num), 1)
        self.assertIn("white-space: normal", num[0])

    def test_the_eta_sentence_wrap_wins_the_cascade_on_a_phone(self):
        # `.ledger.active .num` (three classes) kept it nowrap over the phone's
        # two-class `.builds .num`, so the sentence still overran (pack sd:6398).
        # The cell: `td.num` in `table.ledger.active.builds`, at phone width.
        table = {"ledger", "active", "builds"}
        found = []
        for order, (sels, body) in enumerate(rules(TODAY_CSS)):
            value = re.search(r"(?:^|;|\s)white-space:\s*([a-z-]+)", body)
            for sel in sels:
                parts = re.fullmatch(r"((?:\.[\w-]+)+) \.num", sel)
                if value and parts and set(parts[1].split(".")[1:]) <= table:
                    found.append((parts[1].count("."), order, sel, value[1]))
        self.assertTrue(found)
        self.assertEqual(max(found)[3], "normal", max(found)[2])

    def test_the_no_sessions_row_is_one_block_on_a_phone(self):
        # Its single cell fell into the 2rem first grid column, so the sentence ran one word a line.
        phone = blocks(TODAY_CSS, "(max-width: 899px)")
        row = [body for sels, body in rules(phone) if ".active tbody tr.empty" in sels]
        self.assertEqual(len(row), 1)
        self.assertIn("display: block", row[0])

    def test_each_build_control_link_and_fold_is_touch_sized(self):
        for name, css, selector in (("today.css", TODAY_CSS, "#active-tally a"), ("today.css", TODAY_CSS, ".digest .lines a"),
                                    ("today.css", TODAY_CSS, ".active .what a"),
                                    ("queue.css", QUEUE_CSS, "#builds details.ended summary")):
            with self.subTest(selector):
                touch = [body for sels, body in rules(blocks(css, "(pointer: coarse)")) if selector in sels]
                self.assertTrue(any("min-height: var(--row-touch)" in body for body in touch), f"{selector} in {name}")


class TheRowIcons(unittest.TestCase):
    def test_the_row_actions_sit_on_the_published_marks_middle(self):
        # pack sd:6704: .pub sat on the middle and .rowact on the baseline, so Read
        # drew 4 px above the marks in a Briefs or Documents act cell (headless Chrome).
        for selector in (".pub", ".pub + .rowact"):
            with self.subTest(selector):
                found = [body for sels, body in rules(SHELL_CSS) if selector in sels]
                self.assertTrue(any("vertical-align: middle" in body for body in found), selector)


if __name__ == "__main__":
    unittest.main()
