"""The issue index: what it keeps, what it refuses to lose, and when it moves.

Three properties carry the weight here, and each has a test that fails loudly
if it stops holding:

1. **Closed rows are kept.** The index is a cache of what the trackers said, so
   an issue that closes is updated in place and an issue that stops matching is
   left alone. Deleting either would make "what happened to that PR" answerable
   only by asking GitHub again.
2. **The watermark moves only on a successful collect.** A partial collect that
   advanced it would step the window past the buckets that failed, and those
   issues would never be collected by any later run -- the one way a windowed
   collector loses data permanently rather than temporarily.
3. **A page ceiling is reported, never swallowed.** A capped collect that
   rendered as a complete one is worse than a failed one, because it looks
   right.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dashboard import collect, store, trackers  # noqa: E402 - after the path insert

NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def node(number: int, why_url: str = "", *, kind: str = "Issue", state: str = "OPEN"):
    """One search result in the shape GraphQL actually returns."""
    return {
        "__typename": kind,
        "number": number,
        "title": f"issue {number}",
        "url": why_url or f"https://github.com/o/r/issues/{number}",
        "state": state,
        "updatedAt": "2026-08-30T00:00:00Z",
        "author": {"login": "sven"},
        "repository": {"nameWithOwner": "o/r"},
    }


def issue_row(url: str, why: list[str], *, state: str = "open", updated: str = "2026-08-30T00:00:00Z"):
    return {
        "tracker": "github",
        "url": url,
        "repo": "o/r",
        "number": 1,
        "kind": "issue",
        "title": "one",
        "state": state,
        "author": "sven",
        "updated_at": updated,
        "why": why,
    }


class FakeGh:
    """A `gh` that answers from a script instead of from the network.

    Keyed on the search qualifier rather than on argv position, because the
    argv is an implementation detail of `_page` and a test that asserts its
    shape breaks on every refactor without ever catching a real defect.
    """

    def __init__(self, pages: dict[str, list[dict]], *, authed: bool = True, fail: set[str] | None = None):
        self.pages = pages
        self.authed = authed
        self.fail = fail or set()
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        self.calls.append(argv)
        if argv[:3] == ["gh", "auth", "status"]:
            return (0, "", "") if self.authed else (1, "", "not logged in")
        query = next(part[2:] for part in argv if part.startswith("q="))
        bucket = query.split(":", 1)[0]
        if bucket in self.fail:
            return 1, "", f"{bucket} exploded"
        cursor = next((part[6:] for part in argv if part.startswith("after=")), "")
        sequence = self.pages.get(bucket, [])
        page = int(cursor) if cursor else 0
        if page >= len(sequence):
            block = {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}
        else:
            block = sequence[page]
        return 0, json.dumps({"data": {"search": block}}), ""


def page(nodes: list[dict], *, next_cursor: str | None = None) -> dict:
    return {
        "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
        "nodes": nodes,
    }


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = store.connect(pathlib.Path(":memory:"))
        self.addCleanup(self.connection.close)

    def test_connect_is_idempotent(self) -> None:
        """Schema application runs on every collect, so it must not be a step."""
        store.connect(pathlib.Path(":memory:")).close()
        names = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("issue", names)
        self.assertIn("tracker_watermark", names)

    def test_first_seen_survives_an_update_and_last_seen_moves(self) -> None:
        url = "https://github.com/o/r/issues/1"
        store.upsert_issues(self.connection, [issue_row(url, ["author"])], "2026-08-01T00:00:00Z")
        inserted, updated = store.upsert_issues(
            self.connection, [issue_row(url, ["author"], state="closed")], "2026-08-31T00:00:00Z"
        )
        self.assertEqual((inserted, updated), (0, 1))
        rows = store.issues(self.connection)
        self.assertEqual(len(rows), 1, "the upsert key is not holding")
        self.assertEqual(rows[0]["first_seen"], "2026-08-01T00:00:00Z")
        self.assertEqual(rows[0]["last_seen"], "2026-08-31T00:00:00Z")

    def test_a_closed_row_is_kept_and_an_unseen_row_is_not_deleted(self) -> None:
        """Property 1. Both halves, because only one of them is obvious."""
        kept = "https://github.com/o/r/issues/1"
        vanished = "https://github.com/o/r/issues/2"
        store.upsert_issues(
            self.connection,
            [issue_row(kept, ["author"]), issue_row(vanished, ["mentioned"])],
            "2026-08-01T00:00:00Z",
        )
        store.upsert_issues(
            self.connection, [issue_row(kept, ["author"], state="closed")], "2026-08-31T00:00:00Z"
        )
        by_url = {row["url"]: row for row in store.issues(self.connection)}
        self.assertEqual(by_url[kept]["state"], "closed")
        self.assertIn(vanished, by_url, "a row absent from a later collect was deleted")
        self.assertEqual(by_url[vanished]["last_seen"], "2026-08-01T00:00:00Z")

    def test_why_is_replaced_not_merged(self) -> None:
        """A reason that stopped being true must stop being displayed."""
        url = "https://github.com/o/r/issues/1"
        store.upsert_issues(self.connection, [issue_row(url, ["review-requested"])], "t1")
        store.upsert_issues(self.connection, [issue_row(url, ["author"])], "t2")
        self.assertEqual(store.issues(self.connection)[0]["why"], ["author"])

    def test_rows_from_two_trackers_do_not_collide(self) -> None:
        row = issue_row("https://example.invalid/x", ["author"])
        other = dict(row, tracker="jira")
        store.upsert_issues(self.connection, [row, other], "t1")
        self.assertEqual(len(store.issues(self.connection)), 2)

    def test_watermark_round_trips(self) -> None:
        self.assertIsNone(store.watermark(self.connection, "github"))
        store.set_watermark(self.connection, "github", "t2", "t1")
        store.set_watermark(self.connection, "github", "t4", "t3")
        self.assertEqual(store.watermark(self.connection, "github"), "t4")

    def test_index_path_honours_the_cache_home(self) -> None:
        path = store.index_path({"XDG_CACHE_HOME": "/tmp/somewhere"})
        self.assertEqual(str(path), "/tmp/somewhere/sd-ai-command-pack/index.sqlite")
        self.assertNotIn(
            ".local/state",
            str(store.index_path({})),
            "the rebuildable cache must not live beside the handoff packets",
        )


class WindowTests(unittest.TestCase):
    def test_no_watermark_opens_the_first_run_window(self) -> None:
        self.assertEqual(trackers.window_start(None, NOW), NOW - trackers.FIRST_RUN_WINDOW)

    def test_a_watermark_is_rewound_by_the_overlap(self) -> None:
        mark = trackers.iso(NOW - timedelta(hours=6))
        self.assertEqual(trackers.window_start(mark, NOW), NOW - timedelta(hours=7))

    def test_an_unparseable_watermark_widens_rather_than_narrows(self) -> None:
        """Garbage must never shrink the window; that stops collection silently."""
        self.assertEqual(trackers.window_start("not-a-date", NOW), NOW - trackers.FIRST_RUN_WINDOW)


class CollectTests(unittest.TestCase):
    def test_buckets_union_by_url_and_accumulate_reasons(self) -> None:
        shared = "https://github.com/o/r/pull/9"
        gh = FakeGh(
            {
                "assignee": [page([node(9, shared, kind="PullRequest")])],
                "mentions": [page([])],
                "review-requested": [page([node(9, shared, kind="PullRequest")])],
                "author": [page([node(9, shared, kind="PullRequest")])],
            }
        )
        result = trackers.collect(None, NOW, gh)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(
            result["issues"][0]["why"], ["assigned", "author", "review-requested"]
        )
        self.assertEqual(result["issues"][0]["kind"], "pull")

    def test_pagination_follows_the_cursor(self) -> None:
        gh = FakeGh(
            {
                "assignee": [page([node(1)], next_cursor="1"), page([node(2)])],
                "mentions": [page([])],
                "review-requested": [page([])],
                "author": [page([])],
            }
        )
        result = trackers.collect(None, NOW, gh)
        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual(result["truncated"], [])

    def test_the_page_ceiling_is_reported(self) -> None:
        """Property 3: a capped walk says so."""
        endless = [page([node(n)], next_cursor=str(n + 1)) for n in range(trackers.MAX_PAGES + 2)]
        gh = FakeGh(
            {
                "assignee": endless,
                "mentions": [page([])],
                "review-requested": [page([])],
                "author": [page([])],
            }
        )
        result = trackers.collect(None, NOW, gh)
        self.assertEqual(result["truncated"], ["assigned"])
        self.assertEqual(len(result["issues"]), trackers.MAX_PAGES)

    def test_a_failing_bucket_keeps_the_rows_and_fails_the_collect(self) -> None:
        gh = FakeGh(
            {"assignee": [page([node(1)])], "mentions": [page([])], "review-requested": [page([])], "author": [page([])]},
            fail={"author"},
        )
        result = trackers.collect(None, NOW, gh)
        self.assertFalse(result["ok"])
        self.assertIn("author", result["reason"])
        self.assertEqual(len(result["issues"]), 1, "real rows were thrown away with the error")

    def test_unauthenticated_is_a_reason_not_a_crash(self) -> None:
        result = trackers.collect(None, NOW, FakeGh({}, authed=False))
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], trackers.NO_AUTH)
        self.assertEqual(result["issues"], [])

    def test_a_node_without_a_url_is_dropped(self) -> None:
        """An empty key would collide every url-less node onto one row."""
        self.assertIsNone(trackers.normalize({"number": 1}, "author"))


class RefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = store.connect(pathlib.Path(":memory:"))
        self.addCleanup(self.connection.close)

    def all_pages(self, nodes: list[dict], fail: set[str] | None = None) -> FakeGh:
        return FakeGh(
            {
                "assignee": [page(nodes)],
                "mentions": [page([])],
                "review-requested": [page([])],
                "author": [page([])],
            },
            fail=fail,
        )

    def test_a_successful_refresh_moves_the_watermark(self) -> None:
        result = collect.refresh_issues(self.connection, NOW, self.all_pages([node(1)]))
        self.assertTrue(result["watermark_moved"])
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(store.watermark(self.connection, "github"), trackers.iso(NOW))

    def test_a_failed_refresh_leaves_the_watermark_where_it_was(self) -> None:
        """Property 2, the one that decides whether a gap is temporary."""
        store.set_watermark(self.connection, "github", "2026-08-01T00:00:00Z", "x")
        result = collect.refresh_issues(
            self.connection, NOW, self.all_pages([node(1)], fail={"author"})
        )
        self.assertFalse(result["watermark_moved"])
        self.assertEqual(result["inserted"], 1, "the rows that did arrive were dropped")
        self.assertEqual(
            store.watermark(self.connection, "github"),
            "2026-08-01T00:00:00Z",
            "a partial collect stepped the window past the bucket that failed",
        )


class DumpTests(unittest.TestCase):
    """`--dump` is the canonical-diff check, so it must stay offline."""

    def test_dump_touches_neither_the_network_nor_the_index(self) -> None:
        import io
        import runpy

        module = runpy.run_path(str(REPO_ROOT / "bin" / "sd-dashboard"))

        def explode(*_args, **_kwargs):
            raise AssertionError("--dump reached the network or the index")

        original_run, original_connect = trackers._run, store.connect
        trackers._run, store.connect = explode, explode
        try:
            buffer = io.StringIO()
            code = module["main"](["index", "--dump"], out=buffer)
        finally:
            trackers._run, store.connect = original_run, original_connect
        self.assertEqual(code, 0)
        self.assertIn('"repos"', buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
