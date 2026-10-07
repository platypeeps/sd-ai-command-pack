"""`bin/sd_changelog.py`: the `## Changelog` parser, privacy check, row key, writer and reader (sd:2783, step 1).

A real workflow database in a temporary folder holds the rows; the privacy
patterns are synthetic, never the operator's file.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

from sd_db import connect, initialise

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import sd_changelog  # noqa: E402

ENTRY = """\
## Summary

A fix.

## Changelog

### Fixed

- **A catch-up keeps both entries (sd:2174).** The lane
  resolves it.
  - a nested point
    with its own continuation

- Second fix, one line.

### Added

- A new verb.

## Tests

None here.
"""


class ParseSection(unittest.TestCase):
    def refusal(self, body: str) -> str:
        with self.assertRaises(sd_changelog.ChangelogError) as caught:
            sd_changelog.parse_section(body)
        return caught.exception.code

    def test_entries_keep_body_order_and_lose_the_bullet_indent(self):
        self.assertEqual(sd_changelog.parse_section(ENTRY), [
            {"section": "Fixed", "text": "**A catch-up keeps both entries (sd:2174).** The lane\nresolves it.\n"
                                         "- a nested point\n  with its own continuation"},
            {"section": "Fixed", "text": "Second fix, one line."},
            {"section": "Added", "text": "A new verb."},
        ])

    def test_crlf_bodies_parse_like_lf_bodies(self):
        # GitHub returns a body edited in its web form with CRLF endings.
        self.assertEqual(sd_changelog.parse_section(ENTRY.replace("\n", "\r\n")), sd_changelog.parse_section(ENTRY))

    def test_none_is_an_explicit_empty_answer(self):
        self.assertEqual(sd_changelog.parse_section("## Changelog\n\nnone\n"), [])
        self.assertEqual(sd_changelog.parse_section("## Changelog\n<!-- Write `none` for no entry. -->\nnone\n"), [])

    def test_a_missing_section_is_changelog_missing(self):
        self.assertEqual(self.refusal("## Summary\n\nA fix.\n"), "changelog_missing")
        self.assertEqual(self.refusal("### Changelog\n\nnone\n"), "changelog_missing")

    def test_a_section_inside_a_code_fence_is_an_example(self):
        self.assertEqual(self.refusal("## Summary\n\n```markdown\n## Changelog\n\nnone\n```\n"), "changelog_missing")

    def test_each_invalid_shape_is_changelog_invalid(self):
        for body in (
            "## Changelog\n",
            "## Changelog\n<!-- only the template comment -->\n",
            "## Changelog\n\n### Improved\n\n- Something.\n",
            "## Changelog\n\n### Fixed\n\n### Added\n\n- Something.\n",
            "## Changelog\n\n### Fixed\n",
            "## Changelog\n\n- A bullet before any subsection.\n",
            "## Changelog\n\nProse instead of bullets.\n",
            "## Changelog\n\n### Fixed\n\n- A fix.\n\nA stray paragraph.\n",
            "## Changelog\n\nnone\n\n## Changelog\n\nnone\n",
        ):
            with self.subTest(body=body):
                self.assertEqual(self.refusal(body), "changelog_invalid")

    def test_the_section_ends_at_the_next_level_two_heading(self):
        body = "## Changelog\n\n### Added\n\n- A verb.\n\n## Notes\n\nNot an entry.\n"
        self.assertEqual(sd_changelog.parse_section(body), [{"section": "Added", "text": "A verb."}])


class Private(unittest.TestCase):
    def test_matching_line_numbers_only(self):
        text = "first line\nmentions host-17.example.test\nthird\nalso host-9.example.test\n"
        self.assertEqual(sd_changelog.private(text, [r"host-[0-9]+\.example\.test"]), [2, 4])

    def test_patterns_are_extended_regular_expressions_as_grep_reads_them(self):
        # Python's `re` reads `[[:digit:]]` as a character set, not a class, and would miss this.
        self.assertEqual(sd_changelog.private("id 4242\n", ["id [[:digit:]]{4}"]), [1])

    def test_blank_and_comment_pattern_lines_are_skipped(self):
        self.assertEqual(sd_changelog.private("clean text\n", ["# a comment", "", "   ", "secret-[a-z]+"]), [])

    def test_no_usable_pattern_refuses(self):
        for patterns in ([], ["# only a comment", ""]):
            with self.subTest(patterns=patterns), self.assertRaises(sd_changelog.ChangelogError) as caught:
                sd_changelog.private("anything\n", patterns)
            self.assertEqual(caught.exception.code, "changelog_patterns_missing")

    def test_a_pattern_grep_refuses_is_refused(self):
        with self.assertRaises(sd_changelog.ChangelogError) as caught:
            sd_changelog.private("anything\n", ["a{2,1}"])
        self.assertEqual(caught.exception.code, "changelog_patterns_invalid")


class Rows(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        database = pathlib.Path(tmp.name) / "sd.db"
        initialise(database)
        self.connection = connect(database)
        self.addCleanup(self.connection.close)

    def row(self, slug: str, pull_request: int, digest: str = "d1", commit: str = "c1") -> dict:
        return {"repository": slug, "pull_request": pull_request, "item": "sd:2783", "merge_commit": commit,
                "merged_at": "2026-10-06T00:00:00Z", "entries": [{"section": "Added", "text": "A verb."}],
                "body_digest": digest}

    def stored(self) -> int:
        return self.connection.execute("SELECT count(*) FROM state WHERE key LIKE 'sd-changelog:%'").fetchone()[0]

    def test_the_key_names_the_lower_case_slug_and_the_number(self):
        self.assertEqual(sd_changelog.row_key("Platypeeps/SD-AI-Command-Pack", 1377),
                         "sd-changelog:v1:platypeeps/sd-ai-command-pack:1377")
        for number in (0, -1, "12", 1.0, True):
            with self.subTest(number=number), self.assertRaises(ValueError):
                sd_changelog.row_key("owner/name", number)

    def test_a_second_write_adds_no_revision(self):
        first = sd_changelog.write(self.connection, self.row("owner/name", 7))
        self.assertEqual(sd_changelog.write(self.connection, self.row("owner/name", 7)), first)
        self.assertEqual(self.stored(), 1)

    def test_a_changed_digest_appends_a_revision_and_reads_newest(self):
        sd_changelog.write(self.connection, self.row("owner/name", 7))
        sd_changelog.write(self.connection, self.row("owner/name", 7, digest="d2"))
        self.assertEqual(self.stored(), 2)
        self.assertEqual([row["body_digest"] for row in sd_changelog.rows(self.connection, "owner/name")], ["d2"])

    def test_a_row_without_its_evidence_is_refused(self):
        for field in ("merge_commit", "body_digest"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                sd_changelog.write(self.connection, {**self.row("owner/name", 7), field: ""})
        self.assertEqual(self.stored(), 0)

    def test_an_underscore_in_a_slug_is_not_a_wildcard(self):
        # `LIKE 'sd-changelog:v1:owner/a_b:%'` would also read `owner/axb`.
        sd_changelog.write(self.connection, self.row("owner/a_b", 1))
        sd_changelog.write(self.connection, self.row("owner/axb", 2))
        self.assertEqual([row["repository"] for row in sd_changelog.rows(self.connection, "owner/a_b")], ["owner/a_b"])

    def test_a_slug_that_prefixes_another_reads_only_its_own(self):
        sd_changelog.write(self.connection, self.row("owner/name", 1))
        sd_changelog.write(self.connection, self.row("owner/name-2", 2))
        self.assertEqual([row["pull_request"] for row in sd_changelog.rows(self.connection, "owner/name")], [1])

    def test_rows_are_ordered_by_pull_request_number(self):
        for number in (100, 9, 23):
            sd_changelog.write(self.connection, self.row("Owner/Name", number))
        self.assertEqual([row["pull_request"] for row in sd_changelog.rows(self.connection, "owner/name")],
                         [9, 23, 100])


if __name__ == "__main__":
    unittest.main()
