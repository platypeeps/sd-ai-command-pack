"""What Now shows, and in what order.

Now is the view that outranks its own tabs, so the two things worth pinning
are that nothing it should carry gets dropped and that the order does not
move under the operator between polls.
"""

from __future__ import annotations

import random
import unittest

from dashboard import now


def repo(name: str, *, ahead: int = 0, dirty: int = 0, branch: str = "main",
         last: str = "") -> dict:
    return {"name": name, "branch": branch, "ahead": ahead, "dirty": dirty,
            "last": last}


class BackboneRows(unittest.TestCase):
    def test_a_clean_repo_says_nothing(self) -> None:
        """Twelve quiet repositories are not twelve rows."""
        self.assertEqual(now.backbone_rows([repo("a")]), [])

    def test_ahead_and_dirty_is_one_row_at_the_ahead_rank(self) -> None:
        """One repository with one thing wrong with it, not two.

        Splitting them put the same name on two lines at two ranks, which
        reads as two problems and doubles the list on a fleet mid-work.
        """
        rows = now.backbone_rows([repo("a", ahead=2, dirty=5)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rank"], now.AHEAD)
        self.assertIn("5 dirty files", rows[0]["detail"])

    def test_a_dirty_tree_alone_ranks_below_unpushed_work(self) -> None:
        rows = now.backbone_rows([repo("a", dirty=1)])
        self.assertEqual(rows[0]["rank"], now.DIRTY)
        self.assertEqual(rows[0]["what"], "a has 1 uncommitted file")

    def test_the_id_carries_the_count_so_an_ack_does_not_outlive_it(self) -> None:
        """An id is an ack key (R11-D20), and it identifies one alert.

        Keyed on the name alone, acking "2 unpushed" would silently cover
        "9 unpushed" tomorrow -- the operator would have dismissed a fact
        that had not happened yet.
        """
        two = now.backbone_rows([repo("a", ahead=2)])[0]["id"]
        nine = now.backbone_rows([repo("a", ahead=9)])[0]["id"]
        self.assertNotEqual(two, nine)

    def test_one_of_a_thing_is_not_plural(self) -> None:
        rows = now.backbone_rows([repo("a", ahead=1)])
        self.assertEqual(rows[0]["what"], "a has 1 unpushed commit")

    def test_a_repo_that_reported_nothing_does_not_crash_the_view(self) -> None:
        """`git_facts` returns None fields for a checkout with no upstream.

        Now is the view that has to work when nothing else does, so a missing
        branch is a "?" and not an exception that empties the table.
        """
        rows = now.backbone_rows([{"name": "a", "ahead": None, "dirty": 2}])
        self.assertEqual(rows[0]["detail"], "? · last commit ?")

    def test_every_row_names_a_source(self) -> None:
        """The page resolves a row's destination from `source` and nothing else."""
        rows = now.backbone_rows([repo("a", ahead=1), repo("b", dirty=1)])
        self.assertEqual({row["source"] for row in rows}, {"repos"})


class Merge(unittest.TestCase):
    def test_a_plugin_rank_zero_outranks_every_backbone_row(self) -> None:
        """The rank-0 and rank-1 rows all come from plugin-bound sources.

        This is the whole reason plugin rows reach Now at all: a merge that
        put the backbone first would bury a dark plugin under a dirty tree.
        """
        backbone = now.backbone_rows([repo("a", ahead=1)])
        plugin = [{"rank": 0, "id": "z", "source": "sys/toolbox",
                   "what": "cron exited 1", "detail": ""}]
        self.assertEqual(now.merge(backbone, plugin)[0]["source"], "sys/toolbox")

    def test_the_order_does_not_move_between_polls(self) -> None:
        """Rank ties are the common case, not the exception.

        A fleet of twelve contributes a dozen rows at one rank, and the git
        fan-out is a thread pool, so collection order is not stable. Sorting
        on rank alone would reshuffle the list under the operator every ten
        seconds while they were reading it.
        """
        rows = now.backbone_rows(
            [repo(name, dirty=1) for name in "abcdefghijkl"])
        first = [row["id"] for row in now.merge(rows, [])]
        for _ in range(5):
            shuffled = rows[:]
            random.shuffle(shuffled)
            self.assertEqual([row["id"] for row in now.merge(shuffled, [])], first)

    def test_a_row_with_no_rank_sinks_rather_than_raising(self) -> None:
        """Plugin rows are validated by the loader, and Now is not the place
        to discover that something got past it."""
        got = now.merge([], [{"id": "x", "source": "p"}, {"rank": 2, "id": "y"}])
        self.assertEqual([row["id"] for row in got], ["y", "x"])


if __name__ == "__main__":
    unittest.main()
