"""What the Work tab reports, and what it refuses to hide.

Every fixture here is shaped after something the real fleet contains: the
compound `blocked | phase: ...` status, the `archive` directory that matches
the same glob as an item, and the three items whose directory holds no
`prd.md` at all.
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from dashboard import work


def make_repo(root: pathlib.Path, name: str) -> pathlib.Path:
    repo = root / name
    (repo / ".git").mkdir(parents=True)
    (repo / "docs" / "work").mkdir(parents=True)
    return repo


def make_item(repo: pathlib.Path, name: str, status: str | None, **fields) -> None:
    item = repo / "docs" / "work" / name
    item.mkdir(parents=True)
    if status is None:
        return
    lines = ["---"]
    if status:
        lines.append(f"status: {status}")
    lines += [f"{key}: {value}" for key, value in fields.items()]
    lines += ["---", "", "# body"]
    (item / "prd.md").write_text("\n".join(lines), encoding="utf-8")


class WorkCollection(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_settled_item_is_counted_and_not_listed(self) -> None:
        """300 of 310 read `planning`; listing them is not a view."""
        repo = make_repo(self.root, "one")
        for n in range(5):
            make_item(repo, f"2026-01-0{n}-thing", "planning")
        make_item(repo, "2026-02-01-moving", "in_progress")
        got = work.collect_work(self.root)
        self.assertEqual([row["name"] for row in got["moving"]], ["2026-02-01-moving"])
        self.assertEqual(got["counts"]["planning"], 5)
        self.assertEqual(got["active"], 6)

    def test_a_status_this_module_has_never_seen_is_shown_not_dropped(self) -> None:
        """Moving is defined by exclusion, so a new word surfaces itself.

        An allow-list of interesting statuses would need editing every time
        the templates grow one, and until someone noticed, the item would be
        silently absent from the only view that would have shown it.
        """
        repo = make_repo(self.root, "one")
        make_item(repo, "2026-01-01-odd", "marinating")
        got = work.collect_work(self.root)
        self.assertEqual([row["status"] for row in got["moving"]], ["marinating"])

    def test_a_compound_status_keeps_the_reason_attached(self) -> None:
        """`blocked | phase: check | diagnostic: ...` is a real fleet line."""
        repo = make_repo(self.root, "one")
        make_item(repo, "2026-01-01-stuck",
                  "blocked | phase: check | diagnostic: typed sd-check did not pass")
        row = work.collect_work(self.root)["moving"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(
            row["detail"], "phase: check | diagnostic: typed sd-check did not pass")

    def test_the_archive_directory_is_not_an_item(self) -> None:
        """It matches the same glob and holds no prd.md.

        Without this it reports once per repository as an item whose state
        cannot be read -- which is exactly the row that is supposed to mean
        something.
        """
        repo = make_repo(self.root, "one")
        month = repo / "docs" / "work" / "archive" / "2026-07"
        (month / "2026-07-01-old").mkdir(parents=True)
        (month / "2026-07-02-older").mkdir(parents=True)
        got = work.collect_work(self.root)
        self.assertEqual(got["unstated"], [])
        self.assertEqual(got["moving"], [])
        self.assertEqual(got["archived"], 2)
        self.assertEqual(got["active"], 0)

    def test_a_file_in_an_archive_month_is_not_a_shipped_item(self) -> None:
        """A README beside the archived items would inflate the count."""
        repo = make_repo(self.root, "one")
        month = repo / "docs" / "work" / "archive" / "2026-07"
        (month / "2026-07-01-old").mkdir(parents=True)
        (month / "README.md").write_text("what is in here", encoding="utf-8")
        (repo / "docs" / "work" / "archive" / "stray.md").write_text("x", encoding="utf-8")
        self.assertEqual(work.collect_work(self.root)["archived"], 1)

    def test_an_item_that_cannot_say_what_it_is_gets_its_own_list(self) -> None:
        """Not a blank status column: a blank cell is how it stays unnoticed."""
        repo = make_repo(self.root, "one")
        make_item(repo, "2026-01-01-no-prd", None)
        make_item(repo, "2026-01-02-no-status", "")
        got = work.collect_work(self.root)
        self.assertEqual(
            [(row["name"], row["hasPrd"]) for row in got["unstated"]],
            [("2026-01-01-no-prd", False), ("2026-01-02-no-status", True)],
        )
        self.assertEqual(got["moving"], [])
        self.assertEqual(got["active"], 2)

    def test_the_breakdown_covers_the_moving_items_too(self) -> None:
        """`counts` is the whole active set, not the part the table omits.

        The summary line prints it beside `active`, so a breakdown missing the
        moving items would not add up and the page would quietly disagree with
        itself.
        """
        repo = make_repo(self.root, "one")
        make_item(repo, "2026-01-01-a", "planning")
        make_item(repo, "2026-01-02-b", "in_progress")
        make_item(repo, "2026-01-03-c", "blocked | why")
        make_item(repo, "2026-01-04-d", None)
        got = work.collect_work(self.root)
        self.assertEqual(got["counts"], {"planning": 1, "in_progress": 1, "blocked": 1})
        self.assertEqual(sum(got["counts"].values()) + len(got["unstated"]), got["active"])

    def test_a_repo_without_docs_work_is_not_counted_as_one_with_none(self) -> None:
        """`repos` names the denominator of the summary line."""
        make_repo(self.root, "has")
        bare = self.root / "bare"
        (bare / ".git").mkdir(parents=True)
        make_item(self.root / "has", "2026-01-01-x", "planning")
        got = work.collect_work(self.root)
        self.assertEqual(got["repos"], 1)

    def test_items_carry_the_repository_they_came_from(self) -> None:
        """Six moving items across four repos: the name alone does not place one."""
        first = make_repo(self.root, "alpha")
        second = make_repo(self.root, "beta")
        make_item(first, "2026-01-01-same-name", "in_progress")
        make_item(second, "2026-01-01-same-name", "in_progress")
        got = work.collect_work(self.root)
        self.assertEqual([row["repo"] for row in got["moving"]], ["alpha", "beta"])

    def test_a_grouped_checkout_reports_group_and_name(self) -> None:
        """The fleet is two levels deep -- `platypeeps/loadsmith`, not `loadsmith`."""
        group = self.root / "platypeeps"
        repo = make_repo(group, "loadsmith")
        make_item(repo, "2026-01-01-x", "in_progress")
        got = work.collect_work(self.root)
        self.assertEqual(got["moving"][0]["repo"], "platypeeps/loadsmith")


class Frontmatter(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, text: str) -> pathlib.Path:
        path = self.root / "prd.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_file_that_does_not_open_with_a_fence_has_no_frontmatter(self) -> None:
        """A `status:` in the prose is prose, not state."""
        got = work.frontmatter(self.write("# PRD\n\nstatus: in_progress\n"))
        self.assertEqual(got, {})

    def test_reading_stops_at_the_closing_fence(self) -> None:
        got = work.frontmatter(
            self.write("---\nstatus: planning\n---\n\nbranch: not-a-field\n"))
        self.assertEqual(got, {"status": "planning"})

    def test_an_unterminated_fence_does_not_read_the_whole_document(self) -> None:
        """These are whole PRDs, and there are hundreds of them.

        The fixture size is a literal and does not scale with the constant
        under test. Two earlier versions of this test proved nothing: the
        first repeated one key, so the dict stayed small whether the cap held
        or not; the second sized its input as `FRONTMATTER_LINES + 5`, so
        raising the cap raised the fixture with it and the assertion moved out
        of the way. Both survived a mutation that removed the cap entirely.
        """
        body = "---\nstatus: planning\n" + "".join(
            f"filler{n}: x\n" for n in range(5000))
        got = work.frontmatter(self.write(body))
        self.assertIn("status", got)
        self.assertIn("filler0", got)
        # Bounded well under the fixture but well over any plausible cap, so
        # it fails only for a reader that consumed the document.
        self.assertLess(len(got), 500)
        self.assertNotIn("filler4999", got)

    def test_a_missing_file_is_not_an_error(self) -> None:
        self.assertEqual(work.frontmatter(self.root / "absent.md"), {})


if __name__ == "__main__":
    unittest.main()
