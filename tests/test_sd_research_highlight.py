"""`sd-research-kit highlight`: what changed since a Google Doc's read-back copy (sd:7252).

The fixtures are trimmed from a real review copy and the copy pushed before it.
`baseline.md` is shaped as `get_doc_as_markdown` returns a Doc: links as
`[text](url)`, bold and italic as `**` and `*`, headings as `##`, and every
list item behind the `- [ ]` checkbox Drive adds to an imported list.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import re
import subprocess
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

from tests.clean_env import clean_environment

REPO_ROOT = Path(__file__).resolve().parents[1]
KIT = REPO_ROOT / "bin" / "sd-research-kit"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "highlight"
MARK = "background-color:#fff2a8"


def load_highlight():
    spec = importlib.util.spec_from_file_location("sd_research_highlight", REPO_ROOT / "bin" / "sd_research_highlight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_kit():
    loader = importlib.machinery.SourceFileLoader("sd_research_kit_highlight", str(KIT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def run_kit(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KIT), "highlight", *args], capture_output=True, text=True,
                          env=clean_environment(), timeout=60, check=False)


def marked_units(page: str) -> list[str]:
    """The text of every highlighted `<p>`/`<li>` but the note, in order."""

    found = re.findall(r"<(p|li)\b[^>]*" + re.escape(MARK) + r"[^>]*>(.*?)(?=<(?:/?(?:p|li|ul|ol|h\d|hr)\b))", page, re.S)
    texts = [re.sub(r"<[^>]+>", "", body).strip() for _, body in found]
    return [text for text in texts if not text.startswith(("Changed since", "No changes since"))]


class HighlightFixtureTests(unittest.TestCase):
    """The real pair: three units changed, the rest carried Markdown syntax across."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / "out.html"
        self.done = run_kit("--previous", str(FIXTURES / "baseline.md"), "--since", "2026-11-02 12:04 MST", "--skip-header",
                            str(FIXTURES / "new.html"), str(self.out))
        self.assertEqual(self.done.returncode, 0, self.done.stderr)
        self.page = self.out.read_text(encoding="utf-8")

    def test_unchanged_text_with_links_bold_italic_and_checkboxes_stays_unmarked(self) -> None:
        marked = " | ".join(marked_units(self.page))
        for unchanged in ("The push comes from the whole industry", "The shift I expect",
                          "The tiers only work", "Detection costs something"):
            with self.subTest(unchanged=unchanged):
                self.assertNotIn(unchanged, marked)

    def test_a_changed_paragraph_is_marked_and_its_section_listed(self) -> None:
        marked = marked_units(self.page)
        self.assertTrue(any(text.startswith("So both camps have a point:") for text in marked), marked)
        self.assertTrue(any(text.startswith('"Just vibe code it"') for text in marked), marked)
        self.assertIn("sections: Opening; Where the pressure comes from; Risks and open questions", self.done.stdout)

    def test_a_new_list_item_is_marked(self) -> None:
        self.assertTrue(any(text.startswith("Would AI review have caught") for text in marked_units(self.page)))

    def test_the_count_is_printed_and_the_header_block_is_never_compared(self) -> None:
        self.assertIn("changed: 3 since 2026-11-02 12:04 MST", self.done.stdout)
        self.assertEqual(len(marked_units(self.page)), 3)
        header = self.page.split("<hr")[0]
        self.assertNotIn(MARK, header.split(f'<p style="{MARK}"><strong>Changed since')[0])

    def test_the_header_note_appears_exactly_once_before_the_rule(self) -> None:
        self.assertEqual(self.page.count("Changed since"), 1)
        note = re.search(r'<p style="' + re.escape(MARK) + r'"><strong>Changed since 2026-11-02 12:04 MST</strong>: '
                         r"3 paragraphs, highlighted below; 2 earlier paragraphs no longer appear, reworded or removed\. "
                         r"Sections: Opening; Where the pressure comes from; "
                         r"Risks and open questions\.</p>\n<hr />", self.page)
        self.assertIsNotNone(note, self.page[:1200])

    def test_only_opening_tags_change(self) -> None:
        source = (FIXTURES / "new.html").read_text(encoding="utf-8")
        stripped = re.sub(r"<p style=\"" + re.escape(MARK) + r"\">.*?</p>\n", "", self.page, count=1)
        self.assertEqual(stripped.replace(";" + MARK, ""), source)


class HighlightEdgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.highlight = load_highlight()

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_an_empty_baseline_is_a_first_push_and_is_refused(self) -> None:
        for empty in ("", "\n  \n"):
            with self.subTest(baseline=repr(empty)):
                out = self.tmp / "out.html"
                done = run_kit("--previous", str(self.write("empty.md", empty)), str(FIXTURES / "new.html"), str(out))
                self.assertEqual(done.returncode, 2)
                self.assertIn("a first push has nothing to compare", done.stderr)
                self.assertFalse(out.exists())

    def test_nothing_changed_writes_the_page_unmarked_with_a_no_changes_note(self) -> None:
        page = "<html><body>\n<h2>One</h2>\n<p>Same <a href=\"https://example.test\">text</a>.</p>\n</body></html>\n"
        out = self.tmp / "out.html"
        done = run_kit("--previous", str(self.write("b.md", "## One\n\nSame [text](https://example.test).\n")),
                       "--since", "09:00 MST", str(self.write("in.html", page)), str(out))
        self.assertEqual((done.returncode, done.stdout), (0, "changed: 0 since 09:00 MST\n"))
        written = out.read_text(encoding="utf-8")
        self.assertEqual(written.count(MARK), 1)
        self.assertIn(f'<body><p style="{MARK}"><strong>No changes since 09:00 MST</strong>.</p>\n\n<h2>', written)

    def test_an_existing_style_keeps_its_rules_and_gains_the_mark(self) -> None:
        seen = self.highlight.Baseline("- Old.\n", header=False)
        page, _, _, _ = self.highlight.highlight('<p style="margin:0;">New.</p><li>Old.</li>', seen, "t", header=False)
        self.assertIn(f'<p style="margin:0;{MARK}">New.</p>', page)
        self.assertIn("<li>Old.</li>", page)

    def test_markdown_syntax_normalises_to_the_html_text(self) -> None:
        pairs = (
            ("- [ ] An **item** with a [link](https://example.test/a_(b)).", "An <strong>item</strong> with a <a>link</a>."),
            ("1. *Italic* and `code` and snake_case.", "<em>Italic</em> and <code>code</code> and snake_case."),
            ("> Quoted \\*star\\* &amp; more", "Quoted *star* &amp; more"),
            ("Text ![alt](https://example.test/i.png) after", "Text <img src=\"x\" alt=\"alt\"> after"),
            ("Line one\nline two", "Line one<br />line two"),
        )
        for markdown, fragment in pairs:
            with self.subTest(markdown=markdown):
                self.assertEqual(self.highlight.markdown_text(markdown), self.highlight.html_text(fragment))

    def test_a_nested_list_item_is_its_own_unit(self) -> None:
        page = "<ul><li>Outer<ul><li>Inner new</li></ul></li></ul>"
        marked, changed, _, _ = self.highlight.highlight(page, self.highlight.Baseline("- Outer\n", header=False), "t",
                                                         header=False)
        self.assertEqual(changed, 1)
        self.assertIn(f'<li style="{MARK}">Inner new', marked)

    def test_a_markdown_input_is_laid_out_and_has_no_header_block(self) -> None:
        fake = types.ModuleType("markdown")
        fake.markdown = lambda text, extensions: "<h2>Plan</h2>\n<hr />\n<p>New step.</p>\n<p>Old step.</p>"
        out = self.tmp / "out.html"
        with unittest.mock.patch.dict(sys.modules, {"markdown": fake}), contextlib.redirect_stdout(io.StringIO()) as said:
            code = self.highlight.highlight_main(["--previous", str(self.write("b.md", "## Plan\n\nOld step.\n")),
                                        str(self.write("in.md", "ignored")), str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(said.getvalue(), "changed: 1 since the last push\nsections: Plan\n")
        self.assertTrue(out.read_text(encoding="utf-8").startswith(f'<p style="{MARK}"><strong>Changed since'))

    def test_bad_arguments_exit_2(self) -> None:
        for args in ((), ("in.html", "out.html"), ("--previous", "b.md", "in.html"), ("--previous", "b.md", "--x", "a", "b")):
            with self.subTest(args=args):
                self.assertEqual(run_kit(*args).returncode, 2)

    def test_the_kit_resolves_markdown_only_for_a_markdown_input(self) -> None:
        kit = load_kit()
        calls = []
        kit.reexec_with = lambda *args: calls.append(args) or (_ for _ in ()).throw(SystemExit(0))
        base = str(self.write("b.md", "Old.\n"))
        with unittest.mock.patch.object(kit.importlib.util, "find_spec", return_value=None):
            with self.assertRaises(SystemExit):
                kit.main(["sd-research-kit", "highlight", "--previous", base, str(self.write("in.md", "x")), "o.html"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(kit.main(["sd-research-kit", "highlight", "--previous", base,
                                           str(self.write("in.html", "<p>Old.</p>")), str(self.tmp / "o.html")]), 0)
        self.assertEqual(calls, [("markdown", "markdown", ["highlight", "--previous", base, str(self.tmp / "in.md"), "o.html"])])


class ChangesTheComparisonMustSee(unittest.TestCase):
    """Round 1's class: a real change the comparison cannot see gives a false or short note.

    One test per row of the failure table in the PR body.
    """

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.highlight = load_highlight()

    def check(self, baseline: str, page: str) -> tuple[str, str]:
        (self.tmp / "b.md").write_text(baseline, encoding="utf-8")
        (self.tmp / "in.html").write_text(page, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = self.highlight.highlight_main(["--previous", str(self.tmp / "b.md"), "--since", "T",
                                                  str(self.tmp / "in.html"), str(self.tmp / "out.html")])
        self.assertEqual(code, 0)
        return said.getvalue(), (self.tmp / "out.html").read_text(encoding="utf-8")

    def test_a_heading_edit_is_marked(self) -> None:
        said, page = self.check("## Old title\n\nSame.\n", "<h2>New title</h2>\n<p>Same.</p>\n")
        self.assertIn("changed: 1 since T", said)
        self.assertIn(f'<h2 style="{MARK}">New title</h2>', page)

    def test_a_table_cell_edit_is_marked(self) -> None:
        said, page = self.check("| Key | Value |\n| --- | --- |\n| exit | 0 |\n",
                                "<table><tr><th>Key</th><th>Value</th></tr><tr><td>exit</td><td>1</td></tr></table>")
        self.assertIn("changed: 1 since T", said)
        self.assertIn(f'<td style="{MARK}">1</td>', page)

    def test_a_fenced_code_edit_is_marked(self) -> None:
        said, page = self.check("```\nset -e\nexit 0\n```\n", "<pre><code>set -e\nexit 1\n</code></pre>")
        self.assertIn("changed: 1 since T", said)
        self.assertIn(f'<pre style="{MARK}">', page)

    def test_an_unchanged_fenced_block_stays_unmarked(self) -> None:
        said, _ = self.check("```\nset -e\nexit 0\n```\n", "<pre><code>set -e\nexit 0\n</code></pre>")
        self.assertIn("changed: 0 since T", said)

    def test_literal_markdown_characters_count(self) -> None:
        said, _ = self.check("Call `init` now.\n", "<p>Call <code>__init__</code> now.</p>")
        self.assertIn("changed: 1 since T", said)
        said, _ = self.check("Call `__init__` and \\*args now.\n", "<p>Call <code>__init__</code> and *args now.</p>")
        self.assertIn("changed: 0 since T", said)

    def test_a_deletion_alone_is_reported_not_called_no_change(self) -> None:
        said, page = self.check("## Plan\n\nOne.\n\nTwo.\n", "<h2>Plan</h2>\n<p>One.</p>\n")
        self.assertIn("gone: 1", said)
        self.assertNotIn("No changes since", page)
        self.assertIn("1 earlier paragraph no longer appears, reworded or removed. Sections: Plan.", page)

    def test_an_added_duplicate_is_marked(self) -> None:
        said, _ = self.check("Yes.\n", "<p>Yes.</p>\n<p>Yes.</p>\n")
        self.assertIn("changed: 1 since T", said)

    def test_text_outside_any_paragraph_is_compared(self) -> None:
        said, page = self.check("- [ ] Outer\n- [ ] Inner\n",
                                "<ul><li>Outer<ul><li>Inner</li></ul>Tail added</li></ul>")
        self.assertIn("changed: 1 since T", said)
        self.assertIn(f'<span style="{MARK}">Tail added</span>', page)

    def test_a_line_match_leaves_the_rest_of_its_paragraph_unmatched(self) -> None:
        """Round 2: a line of a single-newline run matched, and the deleted line beside it vanished."""
        said, page = self.check("One.\nTwo.\n", "<p>One.</p>\n")
        self.assertEqual(said, "changed: 0 since T\ngone: 1\nsections: Opening\n")
        self.assertNotIn("No changes since", page)

    def test_a_whole_match_uses_up_its_lines(self) -> None:
        """Round 2: the run matched whole, then one of its lines matched again, hiding a duplicate."""
        said, _ = self.check("One.\nTwo.\n", "<p>One. Two.</p>\n<p>One.</p>\n")
        self.assertIn("changed: 1 since T", said)
        self.assertNotIn("gone:", said)

    def test_matching_does_not_depend_on_order(self) -> None:
        said, page = self.check("One.\nTwo.\n", "<p>One.</p>\n<p>One. Two.</p>\n")
        self.assertIn("changed: 1 since T", said)
        self.assertNotIn("gone:", said)
        self.assertIn(f'<p style="{MARK}">One.</p>\n<p>One. Two.</p>', page)

    def test_the_previous_note_read_back_is_not_a_gone_paragraph(self) -> None:
        said, page = self.check("**Changed since T0**: 1 paragraph, highlighted below. Sections: Opening.\n\nSame.\n",
                                "<p>Same.</p>\n")
        self.assertEqual(said, "changed: 0 since T\n")
        self.assertIn("No changes since T", page)

    def test_text_before_an_ordinary_rule_is_compared(self) -> None:
        """Lane round 2: a guessed header block hid an edited opening above a plain `---`."""
        said, page = self.check("Old opening.\n\n---\n\nSame.\n", "<p>New opening.</p>\n<hr />\n<p>Same.</p>\n")
        self.assertEqual(said, "changed: 1 since T\ngone: 1\nsections: Opening\n")
        self.assertIn(f'<p style="{MARK}">New opening.</p>', page)

    def test_skip_header_leaves_what_precedes_the_first_rule_uncompared(self) -> None:
        (self.tmp / "b.md").write_text("Pushed 09:00.\n\n---\n\nSame.\n", encoding="utf-8")
        (self.tmp / "in.html").write_text("<p>Pushed 10:00.</p>\n<hr />\n<p>Same.</p>\n", encoding="utf-8")
        done = run_kit("--previous", str(self.tmp / "b.md"), "--since", "T", "--skip-header",
                       str(self.tmp / "in.html"), str(self.tmp / "out.html"))
        self.assertEqual((done.returncode, done.stdout), (0, "changed: 0 since T\n"))
        page = (self.tmp / "out.html").read_text(encoding="utf-8")
        self.assertIn(f'<p>Pushed 10:00.</p>\n<p style="{MARK}"><strong>No changes since T</strong>.</p>\n<hr />', page)

    def test_skip_header_without_a_rule_is_refused(self) -> None:
        (self.tmp / "b.md").write_text("Same.\n", encoding="utf-8")
        (self.tmp / "in.html").write_text("<p>Same.</p>\n", encoding="utf-8")
        out = self.tmp / "out.html"
        done = run_kit("--previous", str(self.tmp / "b.md"), "--skip-header", str(self.tmp / "in.html"), str(out))
        self.assertEqual(done.returncode, 2)
        self.assertIn("--skip-header: no <hr", done.stderr)
        self.assertFalse(out.exists())

    def test_a_rule_after_a_heading_is_not_a_header_block(self) -> None:
        said, _ = self.check("## Plan\n\nOriginal.\n\n---\n\nSame.\n",
                             "<h2>Plan</h2>\n<p>Edited.</p>\n<hr />\n<p>Same.</p>\n")
        self.assertIn("changed: 1 since T", said)


if __name__ == "__main__":
    unittest.main()
