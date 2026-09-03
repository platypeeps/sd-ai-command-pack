"""What Now shows, and in what order.

Now is the view that outranks its own tabs, so the two things worth pinning
are that nothing it should carry gets dropped and that the order does not
move under the operator between polls.
"""

from __future__ import annotations

import random
import re
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


class PullRequestRows(unittest.TestCase):
    def payload(self, *prs: dict) -> dict:
        return {"available": True, "needsYou": list(prs), "other": []}

    def pr(self, number: int, updated: str) -> dict:
        return {"repo": "o/r", "number": number, "title": "t",
                "updated_at": updated}

    def test_a_pull_request_nobody_has_touched_ranks_above_a_dirty_tree(self) -> None:
        """Staleness, not age -- and the swap was forced by the index.

        The view this replaces ranked on how long ago a PR was opened, and
        there is no `created_at` column to answer that. The question changed
        to the better one rather than the cache being migrated for the worse
        one: a three-week PR still being pushed to is working as intended.
        """
        rows = now.pr_rows(self.payload(self.pr(1, "2026-08-01")), "2026-08-31")
        self.assertEqual(rows[0]["rank"], now.STALE)
        self.assertLess(rows[0]["rank"], now.DIRTY)
        self.assertIn("quiet 30d", rows[0]["what"])

    def test_a_pull_request_touched_today_is_a_reminder_and_not_an_alarm(self) -> None:
        rows = now.pr_rows(self.payload(self.pr(2, "2026-08-31")), "2026-08-31")
        self.assertEqual(rows[0]["rank"], now.FRESH)
        self.assertNotIn("quiet", rows[0]["what"])

    def test_the_id_does_not_carry_the_age(self) -> None:
        """An ack has to survive the clock.

        Keyed with the day count, a dismissed PR would un-dismiss itself every
        morning -- the one row guaranteed to come back forever.
        """
        one = now.pr_rows(self.payload(self.pr(3, "2026-08-01")), "2026-08-31")
        two = now.pr_rows(self.payload(self.pr(3, "2026-08-01")), "2026-09-30")
        self.assertEqual(one[0]["id"], two[0]["id"])

    def test_an_unusable_stamp_still_renders_and_is_not_called_quiet(self) -> None:
        """The index stores what the tracker returned, and Now has to work
        when nothing else does. A row it cannot rank is still a row."""
        rows = now.pr_rows(self.payload(self.pr(4, "not-a-date")), "2026-08-31")
        self.assertEqual(rows[0]["rank"], now.FRESH)
        self.assertNotIn("quiet", rows[0]["what"])

    def test_no_index_is_no_rows_rather_than_an_exception(self) -> None:
        """`available: False` is what an uncollected index answers, and Now
        must not be the view that goes blank because of it."""
        self.assertEqual(now.pr_rows({"available": False}), [])

    def test_only_the_group_that_needs_you_contributes(self) -> None:
        """Reverses `test_both_groups_contribute`, which asserted the opposite.

        That test was right about the split being a rendering concern and
        wrong about which way Now should resolve it. `other` is
        `author:@me` and `mentions:@me` -- on this account the larger of the
        two groups -- so Now was ranking pull requests the operator had merely
        opened against the ones somebody was blocked on, and the second kind
        went below the fold. A row here is a claim that something wants an
        answer, which is what `needs_you` already decides.
        """
        payload = {"available": True,
                   "needsYou": [self.pr(1, "2026-08-31")],
                   "other": [self.pr(2, "2026-08-31")]}
        rows = now.pr_rows(payload, "2026-08-31")
        self.assertEqual([row["id"] for row in rows], ["pr:o/r#1"])


def gone(count: int, live: int = 0) -> list[dict]:
    """Registrations as `fleet_worktrees` returns them: abandoned first."""
    return ([{"repo": "o", "name": f"x{n}", "live": False} for n in range(count)]
            + [{"repo": "o", "name": f"y{n}", "live": True} for n in range(live)])


class SessionRows(unittest.TestCase):
    def test_abandoned_worktrees_are_one_row_and_not_one_each(self) -> None:
        """Eight of them is one piece of housekeeping. Eight rows would push
        the fleet's real problems off the top of the view to say so eight
        times."""
        rows = now.session_rows(gone(8))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["what"], "8 abandoned worktrees")
        self.assertEqual(rows[0]["source"], "sessions")

    def test_none_abandoned_is_no_row_at_all(self) -> None:
        """Now reports what needs doing, not what does not."""
        self.assertEqual(now.session_rows(gone(0)), [])

    def test_the_id_carries_the_count(self) -> None:
        """Like the repository rows: the ack covers the eight that were
        dismissed, not whatever number this grows to next week."""
        self.assertNotEqual(now.session_rows(gone(8))[0]["id"],
                            now.session_rows(gone(9))[0]["id"])

    def test_a_live_worktree_is_not_counted_as_abandoned(self) -> None:
        """Now takes the registrations rather than a precomputed count, so
        the counting rule has to hold here as well as in the collector."""
        self.assertEqual(now.session_rows(gone(2, live=5))[0]["what"],
                         "2 abandoned worktrees")

    def test_one_of_them_is_not_plural(self) -> None:
        self.assertEqual(now.session_rows(gone(1))[0]["what"],
                         "1 abandoned worktree")


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


class PageAndClientAgree(unittest.TestCase):
    """Every element the client reaches for is one the page declares.

    There is no JavaScript harness here and adding one to cover a two-line
    render change would cost more than the change. This is the part of that
    coverage a Python test can actually hold, and it is the part that broke:
    the tables and their `getElementById` handles live in two files, so
    deleting a `<tbody>` and leaving the lookup -- or the reverse -- produces
    a page that loads, draws most of itself, and silently stops filling one
    table. `document.getElementById` returns null rather than raising, which
    is why nothing else would have said so.

    Ids the page mints at run time are excluded by construction: this reads
    the literal `id="..."` attributes `PAGE` ships with, so a plugin table
    built in JavaScript is out of scope, as it should be -- those are exactly
    the ids `sanitise` strips (`test_an_id_is_dropped_so_a_plugin_cannot_
    claim_a_backbone_element`).
    """

    def handles(self) -> set[str]:
        from dashboard import server
        return set(re.findall(r"""getElementById\(["']([^"']+)["']\)""",
                              server.script_source()))

    def declared(self) -> set[str]:
        from dashboard import server
        return set(re.findall(r"""\bid=["']([^"']+)["']""", server.PAGE))

    def test_the_client_reaches_for_nothing_the_page_does_not_declare(self) -> None:
        orphans = sorted(self.handles() - self.declared())
        self.assertEqual(orphans, [], f"app.js looks up ids PAGE never emits: {orphans}")

    def test_the_check_can_fail(self) -> None:
        """The control. Both sides are regexes over prose-sized documents,
        and a regex that stops matching would make the assertion above pass
        over an empty set forever."""
        self.assertIn("pr-needs", self.handles())
        self.assertIn("pr-needs", self.declared())
        self.assertIn("pr-more", self.declared())
        self.assertNotIn("pr-other", self.declared())

    def calls(self) -> list[str]:
        """`fillIssues` call sites, arguments only.

        Matched to the closing `);` rather than the first `)`, because
        stopping at the first one reads `fillIssues(into, pick(a),
        payload.other)` as `into, pick(a` and finds nothing to complain
        about -- the argument that decides the filter is exactly the one a
        nested call would hide. `(?<!function )` keeps the declaration out:
        it has no `);` of its own, so it would otherwise swallow its way into
        the body and match on whatever came first.
        """
        from dashboard import server
        return re.findall(r"(?<!function )fillIssues\((.*?)\);",
                          server.script_source(), re.S)

    def test_the_main_table_is_never_drawn_from_the_withheld_group(self) -> None:
        """`other` fills the disclosure and never the table above it.

        A source-level assertion, and worth saying why rather than pretending
        it is more: `fillIssues` is the only thing that puts rows in a tracker
        table, so which group each call site is handed *is* the filter, and
        there is no JavaScript runtime here to observe it any other way.

        Only the calls that fill `into` are constrained. `other` reaching
        `more.tbody` is the point of the disclosure -- suppressing a bucket
        from the queue is a ranking decision, but making it unreachable is a
        different and worse one, and `other` carries Jira's `filed`,
        `watching` and `matched` as well as GitHub's two.
        """
        calls = self.calls()
        self.assertNotEqual(calls, [], "fillIssues call sites not parsed")
        main = [call for call in calls if call.lstrip().startswith("into")]
        self.assertNotEqual(main, [], "no call fills the main table")
        drawn = [call for call in main if "other" in call]
        self.assertEqual(drawn, [], f"the main table is filled from `other`: {drawn}")

    def test_the_withheld_group_is_drawn_somewhere(self) -> None:
        """The other half of the same rule, and the one that fails silently.

        A change that simply stopped passing `other` anywhere would satisfy
        the assertion above forever while quietly restoring the defect the
        disclosure exists to prevent: indexed work reduced to a count.
        """
        self.assertNotEqual(
            [call for call in self.calls() if "other" in call], [],
            "no call site draws the withheld rows; they are unreachable again")


if __name__ == "__main__":
    unittest.main()
