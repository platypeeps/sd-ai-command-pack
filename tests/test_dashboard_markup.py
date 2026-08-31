"""The allow-list, tested against what it is for rather than against its list.

Every case here is a way markup runs code or reaches the network without a
`<script>` tag, because `innerHTML` refusing to run `<script>` is the reason
this filter looks unnecessary and none of these care about it. The rest assert
the other half of the bargain: a plugin that loses markup is told, and a tile
that draws an ordinary table gets it back byte for byte.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dashboard.markup import sanitize  # noqa: E402


class MarkupFilterTest(unittest.TestCase):
    def clean(self, html: str) -> str:
        return sanitize(html, "sys/toolbox")[0]

    def complaints(self, html: str) -> list[str]:
        return sanitize(html, "sys/toolbox")[1]

    # -- what runs without a script tag ------------------------------------

    def test_an_inline_handler_does_not_survive(self) -> None:
        self.assertEqual(self.clean('<div onclick="steal()">x</div>'), "<div>x</div>")

    def test_an_image_that_cannot_load_does_not_survive(self) -> None:
        """`<img src=x onerror=...>` is the payload that needs no script tag."""
        self.assertEqual(self.clean('<img src="x" onerror="steal()">after'), "after")

    def test_a_javascript_href_loses_the_attribute_and_keeps_the_text(self) -> None:
        # The anchor stays: the text was the content, and deleting it would
        # lose a label to protect against a link nobody can now follow.
        self.assertEqual(
            self.clean('<a href="javascript:steal()">click</a>'), "<a>click</a>"
        )

    def test_a_relative_href_is_dropped_too(self) -> None:
        """It would resolve against this server's own routes, not the plugin's."""
        self.assertEqual(self.clean('<a href="/api/state">x</a>'), "<a>x</a>")

    def test_an_external_link_is_kept(self) -> None:
        self.assertEqual(
            self.clean('<a href="https://example.com">x</a>'),
            '<a href="https://example.com">x</a>',
        )

    def test_a_frame_takes_its_contents_with_it(self) -> None:
        self.assertEqual(self.clean('<iframe src="//x"><p>in</p></iframe>ok'), "ok")

    def test_a_script_takes_its_contents_with_it(self) -> None:
        self.assertEqual(self.clean("<script>steal()</script>visible"), "visible")

    def test_a_script_inside_svg_is_erased_with_the_svg(self) -> None:
        """`svg` parses its children by its own rules; none of them are a view."""
        self.assertEqual(self.clean("<svg><script>steal()</script></svg>ok"), "ok")

    def test_a_self_closed_script_opens_no_erasure_region(self) -> None:
        """`<script/>` has no end tag, and skipping until one would eat the tab."""
        self.assertEqual(self.clean("<script/>tail"), "tail")

    def test_an_id_is_dropped_so_a_plugin_cannot_claim_a_backbone_element(self) -> None:
        self.assertEqual(self.clean('<p id="rows">x</p>'), "<p>x</p>")

    def test_style_is_dropped(self) -> None:
        self.assertEqual(self.clean('<div style="position:fixed;inset:0">x</div>'),
                         "<div>x</div>")

    # -- what a tile is actually for ---------------------------------------

    def test_a_declared_table_survives_unchanged(self) -> None:
        table = (
            '<table data-sd-sort data-sd-search="filter jobs">'
            '<thead><tr><th data-sort="text">job</th>'
            '<th data-sort="num" class="n">age</th></tr></thead>'
            "<tbody><tr><td>com.sven.x</td><td>12</td></tr></tbody></table>"
        )
        self.assertEqual(self.clean(table), table)
        self.assertEqual(self.complaints(table), [])

    def test_an_unknown_tag_loses_the_box_and_keeps_the_text(self) -> None:
        self.assertEqual(self.clean("<marquee>text</marquee>tail"), "texttail")

    def test_text_is_escaped_rather_than_passed_through(self) -> None:
        self.assertEqual(self.clean("<p>a & b < c</p>"), "<p>a &amp; b &lt; c</p>")

    def test_an_unclosed_element_is_closed_rather_than_left_open(self) -> None:
        """An open `<table>` would otherwise swallow the panel that follows it."""
        self.assertEqual(
            self.clean("<table><tr><td>open"), "<table><tr><td>open</td></tr></table>"
        )

    def test_an_end_tag_for_nothing_open_emits_nothing(self) -> None:
        self.assertEqual(self.clean("<td>x</td></div>ok"), "<td>x</td>ok")

    # -- the loss is reported ----------------------------------------------

    def test_every_kind_of_loss_is_named(self) -> None:
        said = self.complaints('<script>x</script><div onclick="y" id="z">t</div>')
        self.assertEqual(len(said), 2)
        self.assertIn("script", said[0])
        self.assertIn("onclick", said[1])
        self.assertIn("id", said[1])
        # Named to the tab, so a complaint that reaches Now says whose it was.
        self.assertTrue(all(line.startswith("sys/toolbox: ") for line in said))

    def test_markup_that_loses_nothing_says_nothing(self) -> None:
        self.assertEqual(self.complaints("<p>plain</p>"), [])

    def test_an_unclosed_erasure_is_reported_rather_than_swallowed(self) -> None:
        """Everything after an unclosed `<script>` is gone; that has to be said."""
        clean, said = sanitize("<script>x<p>rest</p>", "sys/toolbox")
        self.assertEqual(clean, "")
        self.assertTrue(any("never closed" in line for line in said))


if __name__ == "__main__":
    unittest.main()
