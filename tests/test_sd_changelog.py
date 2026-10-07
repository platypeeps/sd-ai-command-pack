"""`bin/sd_changelog.py`: the `## Changelog` parser, privacy check, row store (step 1) and `sd changelog` (step 2).

A real workflow database in a temporary folder holds the rows, and a fixture
git repository holds the squash history; the privacy patterns are synthetic,
never the operator's file (sd:2783).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
        self.assertEqual(self.refusal("Item: sd:7\nDelivers: sd:7\n"), "changelog_missing")
        self.assertEqual(self.refusal("### Changelog\n\nnone\n"), "changelog_missing")

    def test_a_section_inside_a_code_fence_is_an_example(self):
        self.assertEqual(self.refusal("## Summary\n\n```markdown\n## Changelog\n\nnone\n```\n"), "changelog_missing")

    def test_a_fence_closes_only_on_its_own_character_and_length(self):
        for body in ("````markdown\n```\n## Changelog\n\nnone\n````\n",
                     "~~~markdown\n```\n## Changelog\n\nnone\n~~~\n",
                     "```markdown\n``` not a close\n## Changelog\n\nnone\n```\n"):
            with self.subTest(body=body):
                self.assertEqual(self.refusal(body), "changelog_missing")

    def test_a_heading_inside_an_html_comment_neither_ends_nor_opens_a_section(self):
        body = "## Changelog\n\n### Fixed\n\n- Real fix.\n<!--\n## Notes\nhidden guidance\n-->\n- Second fix.\n"
        self.assertEqual([entry["text"] for entry in sd_changelog.parse_section(body)], ["Real fix.", "Second fix."])
        self.assertEqual(sd_changelog.parse_section("<!--\n## Changelog\n-->\n## Changelog\n\nnone\n"), [])

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

    def test_a_comment_inside_a_code_span_or_fence_is_entry_text(self):
        body = ("## Changelog\n\n### Fixed\n\n- Render keeps `<!-- sd-changelog:begin -->` as written.\n"
                "  ```markdown\n  <!-- a fenced comment -->\n  ```\n<!-- a real comment -->\n")
        self.assertEqual(sd_changelog.parse_section(body), [{
            "section": "Fixed", "text": "Render keeps `<!-- sd-changelog:begin -->` as written.\n"
                                        "```markdown\n<!-- a fenced comment -->\n```"}])

    def test_a_fenced_subsection_heading_stays_inside_its_entry(self):
        body = "## Changelog\n\n### Added\n\n- A template:\n```markdown\n### Fixed\n\n- an example\n```\n\n- Second.\n"
        self.assertEqual(sd_changelog.parse_section(body), [
            {"section": "Added", "text": "A template:\n```markdown\n### Fixed\n\n- an example\n```"},
            {"section": "Added", "text": "Second."}])

    def test_a_fence_before_any_bullet_is_text_outside_a_bullet(self):
        self.assertEqual(self.refusal("## Changelog\n\n### Added\n\n```\n- not a bullet\n```\n"), "changelog_invalid")

    def test_trailer_paragraphs_at_the_end_of_a_squash_message_are_not_entry_text(self):
        message = ("Title (#12)\n\n## Changelog\n\n### Fixed\n\n- A fix.\n\nWork: sd:7\n\n"
                   "Item: sd:7\nDelivers: sd:7\nCo-Authored-By: A <a@example.test>\n  folded\n")
        self.assertEqual(sd_changelog.parse_section(message), [{"section": "Fixed", "text": "A fix."}])
        self.assertEqual(sd_changelog.section_digest(message),
                         sd_changelog.section_digest("## Changelog\n\n### Fixed\n\n- A fix.\n"))

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


CHANGELOG = """\
# Changelog

## Unreleased

<!-- sd-changelog:begin -->
<!-- sd-changelog:end -->

### Added

- A hand-written entry stays byte for byte.

## 1.0.0 - 2026-09-01
"""

#: `(pull request, subject, changelog section)`, oldest first, all after the tag.
MERGES = (
    (11, "Add a verb", "### Added\n\n- A verb.\n"),
    (12, "Fix a bug", "### Fixed\n\n- A fix that\n  wraps.\n"),
    (13, "Docs only", "none\n"),
    (14, "Add another verb", "### Added\n\n- Another verb, for example:\n\n  ```markdown\n  ### Fixed\n\n"
                             "  - an example\n  ```\n\n### Fixed\n\n- A second fix.\n"),
)

RENDERED = """\
<!-- sd-changelog:begin -->

### Added

- Another verb, for example: (#14)

  ```markdown
  ### Fixed

  - an example
  ```

- A verb. (#11)

### Fixed

- A second fix. (#14)

- A fix that (#12)
  wraps.

<!-- sd-changelog:end -->
"""


class Changelog(unittest.TestCase):
    """`sd changelog render|show|import` over a fixture repository whose history GitHub-style squashes made."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = pathlib.Path(tmp.name)
        self.repo = self.home / "repo"
        self.repo.mkdir()
        (self.home / "system").mkdir()
        self.patterns = self.home / "system" / "privacy-patterns"
        self.patterns.write_text("# synthetic\nsecret-[0-9]+\n", encoding="utf-8")
        self.environ = {"PATH": os.environ["PATH"], "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / "xdg"),
                        "SYSTEM_TOOLS_CONFIG": str(self.home / "system"), "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_AUTHOR_DATE": "2026-10-05T12:00:00Z", "GIT_COMMITTER_DATE": "2026-10-05T12:00:00Z"}
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.test")
        self.git("remote", "add", "origin", "https://github.com/Owner/Name.git")
        self.changelog = self.repo / "CHANGELOG.md"
        self.changelog.write_text(CHANGELOG, encoding="utf-8")
        self.git("add", "CHANGELOG.md")
        self.git("commit", "-q", "-m", "Released (#10)\n\n## Changelog\n\n### Added\n\n- Released before the tag.")
        self.released = self.git("rev-parse", "HEAD")
        self.git("tag", "v1.0.0")
        self.merges = {number: self.squash(number, subject, section) for number, subject, section in MERGES}
        self.git("commit", "-q", "--allow-empty", "-m", "Chore (#15)\n\nNo changelog section.")
        self.database = self.home / "sd.db"
        initialise(self.database)

    def git(self, *argv: str) -> str:
        return subprocess.run(["git", "-C", str(self.repo), *argv], check=True, capture_output=True, text=True,
                              env=self.environ, timeout=60).stdout.strip()

    def squash(self, number: int, subject: str, section: str) -> str:
        message = (f"{subject} (#{number})\n\n## Summary\n\nWhat changed.\n\n## Changelog\n\n{section}\n"
                   f"Work: sd:7\n\nItem: sd:7\nDelivers: sd:7\nAuthored-with: claude/anthropic\n")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def message(self, number: int) -> str:
        return self.git("log", "-1", "--format=%B", self.merges[number])

    def store(self, numbers: tuple[int, ...] = (11, 12, 13, 14), commits: dict[int, str] | None = None) -> None:
        """One row per pull request, written in `numbers` order, each `merged_at` later than the last."""
        connection = connect(self.database)
        try:
            for second, number in enumerate(numbers):
                message = self.message(number)
                sd_changelog.write(connection, {
                    "repository": "owner/name", "pull_request": number, "item": "sd:7",
                    "merge_commit": (commits or self.merges)[number], "merged_at": f"2026-10-06T00:00:{second:02d}Z",
                    "entries": sd_changelog.parse_section(message), "body_digest": sd_changelog.section_digest(message)})
        finally:
            connection.close()

    def sd(self, *argv: str) -> tuple[int, str, str]:
        parser = argparse.ArgumentParser()
        sd_changelog.register_changelog(parser.add_subparsers(dest="group"))
        database = [] if "--database" in argv else ["--database", str(self.database)]
        args = parser.parse_args(["changelog", *argv, *database])
        out, err = io.StringIO(), io.StringIO()
        with (mock.patch.dict(os.environ, self.environ, clear=True), contextlib.chdir(self.repo),
              contextlib.redirect_stdout(out), contextlib.redirect_stderr(err)):
            code = args.handler(args)
        return code, out.getvalue(), err.getvalue()

    def region(self) -> str:
        text = self.changelog.read_text(encoding="utf-8")
        return text[text.index(sd_changelog.BEGIN):text.index(sd_changelog.END) + len(sd_changelog.END) + 1]

    def test_render_writes_the_region_by_subsection_then_newest_merge_and_nothing_else(self):
        self.store()
        self.assertEqual(self.sd("render")[0], 0)
        self.assertEqual(self.region(), RENDERED)
        text = self.changelog.read_text(encoding="utf-8")
        self.assertEqual(text.replace(RENDERED, sd_changelog.BEGIN + "\n" + sd_changelog.END + "\n"), CHANGELOG)
        self.assertNotIn("Released before the tag", text)

    def test_render_is_the_same_bytes_twice_and_after_the_rows_are_written_in_reverse(self):
        self.store()
        self.sd("render")
        first = self.changelog.read_bytes()
        self.assertEqual(self.sd("render")[0], 0)
        self.assertEqual(self.changelog.read_bytes(), first)
        # Reversed, each row's `merged_at` reverses too: sorting by it would reorder the entries.
        self.database.unlink()
        initialise(self.database)
        self.store((14, 13, 12, 11))
        self.changelog.write_text(CHANGELOG, encoding="utf-8")
        self.assertEqual(self.sd("render")[0], 0)
        self.assertEqual(self.changelog.read_bytes(), first)

    def test_a_merged_entry_without_a_row_refuses_and_names_the_pull_request(self):
        self.store((11, 14))
        code, _, err = self.sd("render")
        self.assertEqual(code, 1)
        self.assertIn("changelog_rows_missing", err)
        self.assertIn("#12", err)
        self.assertNotIn("#13", err)  # `none` needs no row
        self.assertNotIn("#15", err)  # nor does a message with no section
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), CHANGELOG)

    def test_a_row_for_another_commit_does_not_stand_in_for_the_merge(self):
        self.store(commits={**self.merges, 12: self.merges[11]})
        code, _, err = self.sd("render")
        self.assertEqual((code, "#12" in err), (1, True))

    def test_an_unreadable_section_or_a_subject_with_no_number_is_named_too(self):
        self.store()
        self.git("commit", "-q", "--allow-empty", "-m", "Broken (#17)\n\n## Changelog\n\nProse, not bullets.")
        self.git("commit", "-q", "--allow-empty", "-m", "Pushed by hand\n\n## Changelog\n\n### Added\n\n- Direct.")
        code, _, err = self.sd("render")
        self.assertEqual(code, 1)
        self.assertIn(f": {self.git('rev-parse', 'HEAD')[:12]}, #17;", err)  # newest first
        self.assertEqual(self.sd("import", "17")[2].split(":")[1].strip(), "changelog_invalid")

    def test_import_writes_the_missing_row_from_the_squash_message_once(self):
        self.store((11, 13, 14))
        code, out, _ = self.sd("import", "12")
        self.assertEqual(code, 0, out)
        connection = connect(self.database)
        try:
            row = [row for row in sd_changelog.rows(connection, "owner/name") if row["pull_request"] == 12][0]
        finally:
            connection.close()
        self.assertEqual((row["merge_commit"], row["item"], row["merged_at"], row["entries"]),
                         (self.merges[12], "sd:7", "2026-10-05T12:00:00Z",
                          [{"section": "Fixed", "text": "A fix that\nwraps."}]))
        self.assertEqual(row["body_digest"], sd_changelog.section_digest("## Changelog\n\n" + MERGES[1][2]))
        self.assertEqual(self.sd("import", "12")[1].split(" is ")[1], out.split(" is ")[1])
        self.assertEqual(self.sd("render")[0], 0)
        self.assertIn("- A fix that (#12)", self.region())

    def test_import_refuses_a_pull_request_with_no_squash_or_no_section(self):
        for number, code in (("99", "changelog_import"), ("15", "changelog_missing")):
            with self.subTest(number=number):
                result = self.sd("import", number)
                self.assertEqual((result[0], code in result[2]), (1, True), result)

    def test_a_privacy_match_refuses_with_the_line_number_and_never_the_text(self):
        self.store()
        connection = connect(self.database)
        try:
            row = [row for row in sd_changelog.rows(connection, "owner/name") if row["pull_request"] == 12][0]
            sd_changelog.write(connection, {**row, "body_digest": "corrected",
                                            "entries": [{"section": "Fixed", "text": "A fix\nfor secret-42."}]})
        finally:
            connection.close()
        code, _, err = self.sd("render")
        self.assertEqual(code, 1)
        self.assertIn("changelog_private", err)
        self.assertIn("#12 entry line 2", err)
        self.assertNotIn("secret-42", err)
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), CHANGELOG)

    def test_no_pattern_file_refuses_render_and_show(self):
        self.store()
        self.patterns.unlink()
        for verb in ("render", "show"):
            with self.subTest(verb=verb):
                code, _, err = self.sd(verb)
                self.assertEqual(code, 1)
                self.assertIn("changelog_patterns_missing", err)
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), CHANGELOG)

    def test_sd_privacy_patterns_names_the_pattern_file(self):
        self.store()
        other = self.home / "elsewhere"
        other.write_text("verb\n", encoding="utf-8")
        config = self.home / "xdg" / "sd-ai-command-pack" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"config": {"sd": {"privacy_patterns": str(other)}}}), encoding="utf-8")
        code, _, err = self.sd("render")
        self.assertEqual((code, "changelog_private" in err), (1, True), err)

    def test_check_exits_one_on_a_difference_and_writes_nothing(self):
        self.store()
        code, _, err = self.sd("render", "--check")
        self.assertEqual(code, 1)
        self.assertIn("differs", err)
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), CHANGELOG)
        self.sd("render")
        self.assertEqual(self.sd("render", "--check")[0], 0)

    def test_show_prints_the_region_and_writes_nothing(self):
        self.store()
        code, out, _ = self.sd("show")
        self.assertEqual(code, 0)
        self.assertEqual(out, RENDERED.split("\n", 2)[2].rsplit("\n", 3)[0] + "\n")
        self.assertEqual(self.changelog.read_text(encoding="utf-8"), CHANGELOG)
        self.assertEqual(self.sd("show", "--base", "v1.0.0")[:2], (0, ""))  # nothing merged since the tag

    def test_a_row_off_the_base_is_named_and_not_rendered(self):
        self.git("checkout", "-q", "-b", "side", self.merges[13])
        self.git("commit", "-q", "--allow-empty", "-m", "Elsewhere (#16)\n\n## Changelog\n\n### Added\n\n- Off base.")
        elsewhere = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.store()
        connection = connect(self.database)
        try:
            for number, commit in ((16, elsewhere), (10, self.released)):
                sd_changelog.write(connection, {"repository": "owner/name", "pull_request": number, "item": None,
                                                "merge_commit": commit, "merged_at": "2026-10-06T00:00:00Z",
                                                "entries": [{"section": "Added", "text": f"Row {number}."}],
                                                "body_digest": "d"})
        finally:
            connection.close()
        code, _, err = self.sd("render")
        self.assertEqual(code, 0, err)
        self.assertIn(f"skipped #16 (merge commit {elsewhere[:12]} is not on HEAD)", err)
        self.assertNotIn("#10", err)  # released before the tag: on the base, not rendered
        self.assertEqual(self.region(), RENDERED)

    def test_release_puts_the_entries_under_a_dated_heading_and_empties_the_region(self):
        self.store()
        self.assertEqual(self.sd("render", "--release", "1.1.0")[0], 0)
        text = self.changelog.read_text(encoding="utf-8")
        released = RENDERED.replace(sd_changelog.BEGIN + "\n", "").replace(sd_changelog.END + "\n", "")
        self.assertIn(f"{sd_changelog.BEGIN}\n{sd_changelog.END}\n\n## 1.1.0 - 2026-10-05\n{released}### Added\n\n"
                      "- A hand-written entry", text)

    def test_a_file_without_one_ordered_region_refuses(self):
        self.store()
        begin, end = sd_changelog.BEGIN, sd_changelog.END
        for text in (CHANGELOG.replace(begin + "\n", ""), CHANGELOG.replace(end, end + "\n" + end),
                     CHANGELOG.replace(f"{begin}\n{end}", f"{end}\n{begin}")):
            with self.subTest(text=text[:120]):
                self.changelog.write_text(text, encoding="utf-8")
                code, _, err = self.sd("render")
                self.assertEqual((code, "changelog_region" in err), (1, True), err)
                self.assertEqual(self.changelog.read_text(encoding="utf-8"), text)

    def test_each_input_refusal_names_its_code(self):
        self.store()
        self.assertIn("changelog_base", self.sd("render", "--base", "no-such-ref")[2])
        for argv in (["import", "12", "--base", "no-such-ref"], ["show", "--base=--output=x"]):
            with self.subTest(argv=argv):
                self.assertIn("changelog_base", self.sd(*argv)[2])
        self.assertFalse((self.repo / "x").exists())
        real = sd_changelog.sd_lib.git_output
        with mock.patch.object(sd_changelog.sd_lib, "git_output",
                               side_effect=lambda argv, root: None if argv[0] == "rev-list" else real(argv, root)):
            self.assertIn("changelog_git: git could not list the history of HEAD", self.sd("render")[2])
        self.assertIn("changelog_database", self.sd("render", "--database", str(self.home / "absent.db"))[2])
        self.changelog.unlink()
        self.assertIn("changelog_region", self.sd("render")[2])
        self.git("remote", "set-url", "origin", "https://example.test/owner/name.git")
        self.assertIn("changelog_origin", self.sd("show")[2])
        with contextlib.redirect_stderr(io.StringIO()):
            for argv in (["render", "--release", "v1"], ["import", "0"], ["render", "--check", "--release", "1.1.0"]):
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    self.sd(*argv)

    def test_outside_a_repository_refuses(self):
        self.repo = self.home / "system"
        self.assertIn("not inside a Git repository", self.sd("show")[2])

    def test_bin_sd_carries_the_verbs(self):
        self.store()
        done = subprocess.run([sys.executable, str(ROOT / "bin" / "sd"), "changelog", "show", "--database",
                               str(self.database)], cwd=self.repo, env=self.environ, capture_output=True, text=True,
                              timeout=60)
        self.assertEqual((done.returncode, done.stdout.splitlines()[:3]), (0, ["### Added", "", "- Another verb, for example: (#14)"]),
                         done.stderr)


if __name__ == "__main__":
    unittest.main()
