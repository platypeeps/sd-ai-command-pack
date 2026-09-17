"""The pack's two text reports read an upstream issue as one row, not as debris.

This module imports no `sd_db` on purpose, and that is the point of it rather
than a convenience. The library half of this work -- the `issue_url` field, the
three draft fields, the `closed` lane -- lives in `platypeeps/system` and landed
there at `f18295d` (#308). What this file tests is the other half: this pack's
two renderers, which take plain dictionaries and never call the library. A stub
row hands them exactly what a projection hands them, so a failure here is a
renderer's and nothing else's, and the module needs no library to run. Most of
this suite does not either: 54 of its 86 test modules never name `sd_db`, and
this one names it in prose alone.

This paragraph used to justify the stubs differently, and wrongly: it said the
CI pin was behind `f18295d` and carried `940c045a`, "where `contributions.FIELDS`
has no `issue_url` and `contributions.LANES` has no `closed`". Both halves are
true of `940c045a`, which really was the pin -- until #886 moved it to
`758dfb48` on 2026-09-12, the move made so that CI would carry this very
work's library half. This file arrived after that move, in #888, so the reason
was already one move out of date the day it was written.
By sd:809, `.github/workflows/tests.yml` had pinned nine commits:
`89dcd866`, `4c9ebff4`, `3c4c723a` and `940c045a` have neither symbol;
`758dfb48`, `fb57ae56`, `fd07ea9c`, `dc03956e` and `09260ad4`, the pin sd:809
set, have both, `f18295d` (#308) being an ancestor of each. Every pin since
descends from `09260ad4`. So no pin this file has ever run against lacked
them. The reason was wrong; the design it defends is not
(sd:809).

What the stubs still cannot prove is that the library projects these keys. That
is the system item's evidence, in the system repository's own tests, and no pin
move makes it this file's.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import unittest
from pathlib import Path

from tests.test_sd_status import status

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import sd_work  # noqa: E402

#: Every key the library's `_projection_row` adds for an issue, filed or drafted.
#: Named here once so a renderer that shows four of the five still fails.
ISSUE_KEYS = ("issue_url", "target_repo", "draft_title", "draft_path", "draft_verified")

FILED = {
    "key": "issue:https://github.com/example/project/issues/7",
    "lane": "awaiting_you",
    "title": "Upstream bug",
    "url": "https://github.com/example/project/issues/7",
    "issue_url": "https://github.com/example/project/issues/7",
    "target_repo": "example/project",
    "local_status": "planning",
    "external_state": "open",
    "draft_title": "Crash on empty input",
    "draft_path": {"path": "/drafts/crash.md", "sha256": "e" * 64},
    "draft_verified": True,
    # Sorts before every issue key alphabetically, and that is the whole point
    # of it: the sorted tail is alphabetical, so a sentinel named `zzz_...`
    # would sit after `draft_path` and `issue_url` whether or not the display
    # order names them, and a control built on one proves nothing. This one
    # can only precede them if they were not named.
    "aaa_key_no_display_order_names": "tail",
}


def _status_text(row: dict) -> str:
    output = io.StringIO()
    status._render_contributions({"available": True, "rows": [row]}, output.write)
    return output.getvalue()


def _work_text(row: dict) -> str:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        sd_work._emit_contributions([row], machine=False)
    return output.getvalue()


class IssueRowsAreShownInBothTextReports(unittest.TestCase):
    """Not `--json`: neither JSON path reaches a display-order tuple.

    `sd_work._emit_contributions` returns before its tuple when `machine` is
    set, and `bin/sd-status` serialises the whole result object while the tuple
    lives in `_render_contributions`. A check written against `--json` passes
    before and after any change here and establishes nothing.
    """

    def test_status_shows_every_issue_key(self) -> None:
        text = _status_text(FILED)
        for key in ISSUE_KEYS:
            self.assertIn(f"    {key}: ", text)

    def test_contribution_list_shows_every_issue_key(self) -> None:
        text = _work_text(FILED)
        for key in ISSUE_KEYS:
            self.assertIn(f"  {key}: ", text)

    def test_an_unverified_draft_says_so_in_both_reports(self) -> None:
        """sd:360. `draft_verified: false` is an answer, not an absence.

        `FILED` carries `draft_verified: True`, so the two tests above print
        the key whichever predicate a renderer uses. They were blind to the
        case that matters: a draft whose body no longer matches its digest.
        `sd task contribution list` used to skip every falsy value and so said
        nothing at all about it, while `sd-status` printed `false`.
        """
        unverified = {**FILED, "draft_verified": False}
        for text in (_status_text(unverified), _work_text(unverified)):
            self.assertIn("draft_verified: false", text)

    def test_the_issue_keys_are_named_rather_than_left_in_the_sorted_tail(self) -> None:
        """The control. Membership already came from the row; order did not.

        Without this, both tests above pass with the tuples untouched: the keys
        appear, alphabetically, after `attention_sources` and after anything
        else the library ever adds. A reader would meet `draft_path` between
        `blocking_labels` and `event_ids`.
        """
        for text in (_status_text(FILED), _work_text(FILED)):
            tail = text.index("aaa_key_no_display_order_names")
            for key in ISSUE_KEYS:
                if f"{key}: " not in text:
                    continue
                self.assertLess(text.index(f"{key}: "), tail, key)

    def test_a_draft_that_was_never_filed_still_reads_as_a_row(self) -> None:
        """An unfiled draft has no URL and no branch, so `url` is absent."""
        draft = {"key": "item:244", "lane": "awaiting_you", "title": "Report the crash",
                 "target_repo": "example/project", "draft_title": "Crash on empty input",
                 "draft_path": {"path": "/drafts/crash.md", "sha256": "e" * 64},
                 "reasons": ["Issue draft has not been filed"]}
        for text in (_status_text(draft), _work_text(draft)):
            self.assertIn("target_repo: ", text)
            self.assertIn("draft_title: ", text)
            self.assertIn("draft_path: ", text)
            self.assertNotIn("url: ", text)


class BothReportsAgreeWhatEmptyMeans(unittest.TestCase):
    """sd:360, owner decision 2026-09-13: skip only `None`, `[]` and `""`.

    `False` and `0` are values. `needs_you: false` and a count of zero are
    what the row says, and a report that hides them reads the same as one
    whose producer never set the key.
    """

    #: Invented tail keys as well as named ones: the sorted tail is where a
    #: field the library adds later lands, and it must obey the same rule.
    SHOWN = {"needs_you": False, "draft_verified": False, "aaa_count": 0,
             "aaa_ratio": 0.0, "aaa_mapping": {}}
    SKIPPED = {"blocked_on": None, "reasons": [], "local_branch": ""}

    def _row(self, fields: dict) -> dict:
        return {"key": "item:360", "lane": "awaiting_them", "title": "Upstream", **fields}

    def test_false_and_zero_are_shown_in_both_reports(self) -> None:
        row = self._row(self.SHOWN)
        for text in (_status_text(row), _work_text(row)):
            self.assertIn("needs_you: false", text)
            self.assertIn("draft_verified: false", text)
            self.assertIn("aaa_count: 0", text)
            self.assertIn("aaa_ratio: 0.0", text)
            self.assertIn("aaa_mapping: {}", text)

    def test_none_an_empty_list_and_an_empty_string_are_still_skipped(self) -> None:
        """The control. Without it, printing every key passes the test above."""
        row = self._row(self.SKIPPED)
        for text in (_status_text(row), _work_text(row)):
            for key in self.SKIPPED:
                self.assertNotIn(f"{key}:", text)

    def test_the_two_reports_give_one_answer_for_every_value(self) -> None:
        for value in (*self.SHOWN.values(), *self.SKIPPED.values()):
            row = self._row({"aaa_probe": value})
            with self.subTest(value=value):
                self.assertEqual(
                    "aaa_probe:" in _status_text(row), "aaa_probe:" in _work_text(row))


class TheClosedLaneNeedsNoRendererChange(unittest.TestCase):
    """Stated as a control, because it is the reason no lane list is edited.

    The `closed` lane is the library's, and the sort is the library's. Neither
    renderer recites lane names, so a fifth lane arrives without a pack change.
    A test is still worth its lines: it is what would fail if a reader ever
    grew a lane whitelist, which is how the field lists went wrong.
    """

    def test_both_reports_render_a_lane_they_have_never_seen(self) -> None:
        row = {"key": "issue:https://github.com/example/project/issues/7",
               "lane": "closed", "title": "Upstream bug", "external_state": "closed"}
        self.assertIn("[closed]", _status_text(row))
        self.assertIn("closed", _work_text(row))


class TheKeyHelpNamesEveryFormTheLibraryAccepts(unittest.TestCase):
    def test_show_and_ack_name_all_three_key_forms(self) -> None:
        """Recited, because the parser is built before the library is known.

        `sd --help` answers in guest mode, so this string cannot be derived
        from the library that refuses the same three names. Reciting it is a
        cost; leaving `issue:` out of it is a reader being told the form does
        not exist.
        """
        for form in ("item:ID", "/pull/NUMBER", "issue:", "/issues/NUMBER"):
            self.assertIn(form, sd_work.CONTRIBUTION_KEY_HELP)

    def test_the_parser_hands_the_reader_the_recited_help(self):
        """Read off the BUILT parser, not off the constant.

        The test above pins what the string says. It cannot see whether the
        string ever reaches a reader: rewire `add_argument` back to a literal
        and the constant is still correct, still tested, and `sd task
        contribution show --help` still omits `issue:`. So this walks the
        parser the verb actually builds and asks the `key` action for its
        help, which is the text a reader gets.

        Both actions that take a key are checked. `show` and `ack` are
        registered by one loop today; a future edit that splits them could
        leave one behind, and a test naming only `show` would not notice.
        """
        parser = argparse.ArgumentParser()
        verbs = parser.add_subparsers(dest="noun", required=True)
        sd_work._register_contributions(verbs)
        contribution = verbs.choices["contribution"]
        actions = next(
            action for action in contribution._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        seen = {}
        for name in ("show", "ack"):
            key = next(
                action for action in actions.choices[name]._actions
                if action.dest == "key"
            )
            seen[name] = key.help
        self.assertEqual(
            seen, {"show": sd_work.CONTRIBUTION_KEY_HELP, "ack": sd_work.CONTRIBUTION_KEY_HELP})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
