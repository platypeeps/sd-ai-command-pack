"""Dashboard registration and the Notion sync queue.

`.coveragerc` keeps the non-installer `bin/` tools out of the 100% gate and
covers them with focused tests instead. This is that file for
`bin/sd_research_publish.py`.

What is worth pinning is the part that would fail silently. Registration writes
into a config file this repository does not own, so the cases that matter are
the second run (no duplicate line) and the key that already names something else
(left alone, not overwritten). Enqueueing decides what reaches Notion, so the
case that matters is the document with no `notion` key: the contract says it
publishes locally and nowhere else, and a queue entry appearing for it would be
an outward push nobody asked for.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "bin"


def load():
    if str(BIN) not in sys.path:
        sys.path.insert(0, str(BIN))
    spec = importlib.util.spec_from_file_location(
        "sd_research_publish", BIN / "sd_research_publish.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PUBLISH = load()

HEADER = "# Generated documents the dashboard lists and serves.\n#\n#   root|<key>|<label>|<directory>\n\nroot|hoa|Stage Run HOA|~/repos/hoa/reports\n"


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dashboard = self.root / "dashboard"
        self.dashboard.mkdir()
        self.conf = self.dashboard / "documents.conf"
        self.conf.write_text(HEADER, encoding="utf-8")
        self.repo = self.root / "my-research"
        (self.repo / "build").mkdir(parents=True)

        original_home, original_queue = PUBLISH.DASHBOARD_HOME, PUBLISH.QUEUE
        PUBLISH.DASHBOARD_HOME = self.dashboard
        PUBLISH.QUEUE = self.root / "queue"

        def restore() -> None:
            PUBLISH.DASHBOARD_HOME, PUBLISH.QUEUE = original_home, original_queue

        self.addCleanup(restore)

    def roots(self) -> list[str]:
        return [
            line
            for line in self.conf.read_text(encoding="utf-8").splitlines()
            if line.startswith("root|")
        ]


class RegisterTests(Fixture):
    def test_a_new_repo_gains_one_line(self) -> None:
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("registered my-research", said)
        self.assertEqual(len(self.roots()), 2)
        self.assertIn("root|my-research|MINE|", self.roots()[1])

    def test_a_second_run_adds_nothing(self) -> None:
        PUBLISH.register_root(self.repo, "MINE", self.repo / "build")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("already registered", said)
        self.assertEqual(len(self.roots()), 2)

    def test_a_key_naming_another_directory_is_left_alone(self) -> None:
        with self.conf.open("a", encoding="utf-8") as handle:
            handle.write("root|my-research|Someone Else|~/elsewhere\n")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("left alone", said)
        self.assertEqual(len(self.roots()), 2)
        self.assertIn("~/elsewhere", self.roots()[1])

    def test_no_dashboard_is_reported_not_raised(self) -> None:
        PUBLISH.DASHBOARD_HOME = self.root / "absent"
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("not registered", said)


class NotionTargetTests(unittest.TestCase):
    def test_absent_means_local_only(self) -> None:
        self.assertIsNone(PUBLISH.notion_target({"out": "doc"}))

    def test_a_space_is_required(self) -> None:
        with self.assertRaises(ValueError):
            PUBLISH.notion_target({"out": "doc", "notion": {"page": "x"}})

    def test_a_non_dict_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            PUBLISH.notion_target({"out": "doc", "notion": "Research"})


class EnqueueTests(Fixture):
    def docs(self) -> list[dict]:
        return [
            dict(
                src="10-x/a.md",
                out="a",
                title="A",
                notion=dict(space="Research", page="https://notion.so/a"),
            ),
            dict(src="10-x/b.md", out="b", title="B"),
        ]

    def test_only_the_designated_document_is_queued(self) -> None:
        PUBLISH.enqueue(self.repo, self.docs())
        written = sorted(p.name for p in PUBLISH.QUEUE.iterdir())
        self.assertEqual(written, ["my-research.a.json"])

    def test_the_request_names_the_space_and_the_page(self) -> None:
        PUBLISH.enqueue(self.repo, self.docs())
        request = json.loads((PUBLISH.QUEUE / "my-research.a.json").read_text())
        self.assertEqual(request["space"], "Research")
        self.assertEqual(request["page"], "https://notion.so/a")
        self.assertEqual(request["document"], "a")

    def test_a_re_render_replaces_rather_than_queues_twice(self) -> None:
        PUBLISH.enqueue(self.repo, self.docs())
        PUBLISH.enqueue(self.repo, self.docs())
        self.assertEqual(len(list(PUBLISH.QUEUE.iterdir())), 1)

    def test_nothing_designated_writes_no_queue_at_all(self) -> None:
        PUBLISH.enqueue(self.repo, [dict(src="x.md", out="b", title="B")])
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_a_malformed_target_is_reported_and_skipped(self) -> None:
        said = PUBLISH.enqueue(self.repo, [dict(out="c", notion={"page": "x"})])
        self.assertTrue(any("needs a space" in line for line in said))
        self.assertFalse(PUBLISH.QUEUE.exists())


class RepoKeyTests(unittest.TestCase):
    def test_the_key_is_usable_in_a_url(self) -> None:
        for name in ("Traces-Research", "my repo", "a.b_c"):
            key = PUBLISH.repo_key(Path("/tmp") / name)
            self.assertRegex(key, r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z", name)


if __name__ == "__main__":
    unittest.main()
