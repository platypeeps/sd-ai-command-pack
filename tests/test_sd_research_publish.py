"""Dashboard registration and the outward mirror queue.

`.coveragerc` keeps the non-installer `bin/` tools out of the 100% gate and
covers them with focused tests instead. This is that file for
`bin/sd_research_publish.py`.

What is worth pinning is the part that would fail silently. Registration writes
into a config file this repository does not own, so the cases that matter are
the second run (no duplicate line) and the key that already names something else
(left alone, not overwritten). Enqueueing decides what leaves the machine, so
the case that matters is the document designating no destination: the contract
says it publishes locally and nowhere else, and a queue entry appearing for it
would be an outward push nobody asked for. The second is a document designated
twice, which must be two independent requests -- one queue file per destination
-- because either mirror can drain while the other still waits.
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

#: `mirror_targets` resolves a destination's default container from the
#: repo name, so every call needs a repo even when the designation names
#: its container outright.
REPO = Path("/repos/my-research")

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

        self.vault = self.root / "vault"
        original = (PUBLISH.DASHBOARD_HOME, PUBLISH.QUEUE, PUBLISH.VAULT)
        PUBLISH.DASHBOARD_HOME = self.dashboard
        PUBLISH.QUEUE = self.root / "queue"
        PUBLISH.VAULT = str(self.vault)

        def restore() -> None:
            (PUBLISH.DASHBOARD_HOME, PUBLISH.QUEUE, PUBLISH.VAULT) = original

        self.addCleanup(restore)

    def briefs(self) -> Path:
        return self.vault / "Briefs" / "my-research"

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


class MirrorTargetTests(unittest.TestCase):
    def test_no_key_means_local_only(self) -> None:
        self.assertEqual(PUBLISH.mirror_targets({"out": "doc"}, REPO), ([], []))

    def test_no_destination_needs_a_container_named(self) -> None:
        """Every destination has a default, so a bare designation is valid
        everywhere. A folder nobody has to name is a folder nobody can
        misspell."""
        for key in ("notion", "drive"):
            with self.subTest(key):
                targets, problems = PUBLISH.mirror_targets(
                    {"out": "d", key: {}}, REPO)
                self.assertEqual(problems, [])
                self.assertEqual(len(targets), 1)

    def test_a_drive_mirror_defaults_to_briefs_and_the_repo_name(self) -> None:
        """The shape the vault uses, so the copies agree on where a brief
        lives. The drain resolves the path and creates the repo folder when it
        is missing, which is what lets a new repo publish without anyone
        provisioning a folder first."""
        (drive,), _ = PUBLISH.mirror_targets({"drive": {}}, REPO)
        self.assertEqual(drive["folder"], "Briefs/my-research")
        self.assertEqual(drive["target"], "the Briefs/my-research Drive folder")

    def test_naming_a_drive_folder_overrides_the_default(self) -> None:
        (drive,), _ = PUBLISH.mirror_targets(
            {"drive": dict(folder="Deliverables")}, REPO)
        self.assertEqual(drive["folder"], "Deliverables")

    def test_an_empty_notion_dict_is_still_a_designation(self) -> None:
        """`notion=dict()` is falsy, so presence decides, not truth."""
        for written in ({}, True):
            with self.subTest(repr(written)):
                targets, _ = PUBLISH.mirror_targets({"notion": written}, REPO)
                self.assertEqual(len(targets), 1)

    def test_a_designation_turned_off_designates_nothing(self) -> None:
        for written in (None, False):
            with self.subTest(repr(written)):
                self.assertEqual(
                    PUBLISH.mirror_targets({"notion": written}, REPO), ([], []))

    def test_notion_is_private_unless_the_document_asks_for_the_team(self) -> None:
        """The recoverable mistake is the one that happens by accident: a brief
        the team cannot see is repaired by adding `team=True` and draining
        again, and a private brief in a shared space cannot be unseen."""
        (private,), _ = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(private["scope"], "private")
        self.assertEqual(private["space"], "Briefs")
        (team,), _ = PUBLISH.mirror_targets({"notion": dict(team=True)}, REPO)
        self.assertEqual(team["scope"], "team")
        self.assertEqual(team["space"], "R&D Briefs")

    def test_naming_a_folder_does_not_change_the_space(self) -> None:
        """`space=` says where inside a space, never which space."""
        (target,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="Archive")}, REPO)
        self.assertEqual(target["scope"], "private")
        self.assertEqual(target["space"], "Archive")
        (target,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="Archive", team=True)}, REPO)
        self.assertEqual(target["scope"], "team")

    def test_a_notion_default_is_pinned_by_page_id_not_by_folder_name(self) -> None:
        """The folder is resolved by id, and the name is only ever printed.

        A name lookup that finds nothing returns an empty result rather than an
        error, so a rename moved every default mirror to nowhere and said so to
        nobody. Both folders have been renamed once already."""
        (private,), _ = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(
            private["space_id"], "3c9f52b1-5782-81a7-a466-fb0e2df4d928")
        self.assertEqual(private["resolve"], "id")
        (team,), _ = PUBLISH.mirror_targets({"notion": dict(team=True)}, REPO)
        self.assertEqual(
            team["space_id"], "3cff52b1-5782-806a-acb0-ca0c8f41524b")
        self.assertEqual(team["resolve"], "id")

    def test_renaming_the_folder_in_notion_is_cosmetic(self) -> None:
        """After a rename the label changes and the folder does not."""
        before = [PUBLISH.mirror_targets({"notion": dict(team=flag)}, REPO)[0][0]
                  for flag in (False, True)]
        original = PUBLISH.NOTION_SCOPES
        self.addCleanup(setattr, PUBLISH, "NOTION_SCOPES", original)
        PUBLISH.NOTION_SCOPES = {
            flag: scope._replace(label=scope.label + " 2026",
                                 phrase=scope.phrase + " 2026")
            for flag, scope in original.items()
        }
        after = [PUBLISH.mirror_targets({"notion": dict(team=flag)}, REPO)[0][0]
                 for flag in (False, True)]
        for was, now in zip(before, after, strict=True):
            self.assertEqual(was["space_id"], now["space_id"])
            self.assertEqual(now["resolve"], "id")
            self.assertNotEqual(was["space"], now["space"])

    def test_an_override_resolves_by_id_whenever_it_names_one(self) -> None:
        """`space=` may be an id or a page URL, and then it is rename-proof.

        A plain name is not, so the request says `name` rather than implying a
        resolution it did not make."""
        for written in ("3cff52b1-5782-806a-acb0-ca0c8f41524b",
                        "https://www.notion.so/Old-Name-"
                        "3cff52b15782806aacb0ca0c8f41524b"):
            with self.subTest(written):
                (target,), _ = PUBLISH.mirror_targets(
                    {"notion": dict(space=written)}, REPO)
                self.assertEqual(target["resolve"], "id")
                self.assertTrue(target["space_id"].endswith("524b"))
        (named,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="Archive")}, REPO)
        self.assertEqual(named["space_id"], "")
        self.assertEqual(named["resolve"], "name")

    def test_a_non_dict_is_refused(self) -> None:
        for key in ("notion", "drive"):
            with self.subTest(key):
                targets, problems = PUBLISH.mirror_targets(
                    {"out": "d", key: "R"}, REPO)
                self.assertEqual(targets, [])
                self.assertTrue(any("must be a dict" in p for p in problems))

    def test_each_destination_keeps_its_own_field_names(self) -> None:
        """A drain reads the fields its connector needs, not a generic pair."""
        (notion,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="R", page="p")}, REPO)
        self.assertEqual(notion["destination"], "notion")
        self.assertEqual((notion["space"], notion["page"]), ("R", "p"))
        self.assertIn("scope", notion)
        (drive,), _ = PUBLISH.mirror_targets(
            {"drive": dict(folder="F", file="f")}, REPO)
        self.assertEqual(drive["destination"], "drive")
        self.assertEqual((drive["folder"], drive["file"]), ("F", "f"))

    def test_the_target_is_worded_for_whoever_reads_the_request(self) -> None:
        """`sd-status` prints this, so it never carries the destination table."""
        (notion,), _ = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(notion["target"], "the private Briefs folder")
        (team,), _ = PUBLISH.mirror_targets({"notion": dict(team=True)}, REPO)
        self.assertEqual(
            team["target"], "the R&D Briefs folder in the R&D team space")
        (drive,), _ = PUBLISH.mirror_targets(
            {"drive": dict(folder="Deliverables")}, REPO)
        self.assertEqual(drive["target"], "the Deliverables Drive folder")

    def test_two_keys_are_two_mirrors_and_not_a_choice(self) -> None:
        targets, _ = PUBLISH.mirror_targets(
            {"notion": {}, "drive": dict(folder="F")}, REPO)
        self.assertEqual([t["destination"] for t in targets], ["notion", "drive"])

    def test_an_unknown_key_designates_nothing(self) -> None:
        """A destination is a row in the table; anything else is a typo, and a
        typo that queued a mirror would queue it to a place nothing drains."""
        self.assertEqual(
            PUBLISH.mirror_targets({"sharepoint": {"site": "x"}}, REPO),
            ([], []))


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
        self.assertEqual(written, ["my-research.a.notion.json"])

    def test_the_request_names_the_container_and_the_page(self) -> None:
        PUBLISH.enqueue(self.repo, self.docs())
        path = PUBLISH.QUEUE / "my-research.a.notion.json"
        request = json.loads(path.read_text())
        self.assertEqual(request["destination"], "notion")
        self.assertEqual(request["space"], "Research")
        self.assertEqual(request["page"], "https://notion.so/a")
        self.assertEqual(request["document"], "a")

    def test_a_default_notion_request_carries_the_folder_id(self) -> None:
        """The drain reads `space_id`, so the id has to reach the file."""
        PUBLISH.enqueue(self.repo, [dict(
            src="10-x/a.md", out="a", title="A", notion=dict(team=True))])
        request = json.loads(
            (PUBLISH.QUEUE / "my-research.a.notion.json").read_text())
        self.assertEqual(
            request["space_id"], "3cff52b1-5782-806a-acb0-ca0c8f41524b")
        self.assertEqual(request["resolve"], "id")

    def test_a_drive_designation_queues_a_drive_request(self) -> None:
        PUBLISH.enqueue(self.repo, [dict(
            src="10-x/a.md", out="a", title="A",
            drive=dict(folder="Deliverables", file="https://docs.google.com/d/a"),
        )])
        path = PUBLISH.QUEUE / "my-research.a.drive.json"
        request = json.loads(path.read_text())
        self.assertEqual(request["destination"], "drive")
        self.assertEqual(request["folder"], "Deliverables")
        self.assertEqual(request["file"], "https://docs.google.com/d/a")

    def test_a_document_designated_twice_is_two_requests(self) -> None:
        """Either mirror can drain while the other waits, so neither shares a
        file with the other -- deleting one would otherwise cancel both."""
        PUBLISH.enqueue(self.repo, [dict(
            src="10-x/a.md", out="a", title="A",
            notion=dict(space="R"), drive=dict(folder="F"),
        )])
        self.assertEqual(
            sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
            ["my-research.a.drive.json", "my-research.a.notion.json"],
        )

    def test_a_re_render_replaces_rather_than_queues_twice(self) -> None:
        PUBLISH.enqueue(self.repo, self.docs())
        PUBLISH.enqueue(self.repo, self.docs())
        self.assertEqual(len(list(PUBLISH.QUEUE.iterdir())), 1)

    def test_nothing_designated_writes_no_queue_at_all(self) -> None:
        PUBLISH.enqueue(self.repo, [dict(src="x.md", out="b", title="B")])
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_a_malformed_target_is_reported_and_skipped(self) -> None:
        said = PUBLISH.enqueue(self.repo, [dict(out="c", drive="Deliverables")])
        self.assertTrue(any("must be a dict" in line for line in said))
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_a_malformed_designation_does_not_withhold_the_good_one(self) -> None:
        """The dashboard copy is already written; one bad key must not cost the
        other destination its request."""
        said = PUBLISH.enqueue(self.repo, [dict(
            out="c", notion={}, drive="Deliverables",
        )])
        self.assertTrue(any("must be a dict" in line for line in said))
        self.assertEqual([p.name for p in PUBLISH.QUEUE.iterdir()],
                         ["my-research.c.notion.json"])

    def test_a_drive_request_naming_no_folder_carries_the_default(self) -> None:
        """Naming the file to update says nothing about where it lives, so the
        request still has to state a folder for the drain to resolve."""
        PUBLISH.enqueue(self.repo, [dict(out="c", drive={"file": "x"})])
        wrote = json.loads(
            (PUBLISH.QUEUE / "my-research.c.drive.json").read_text())
        self.assertEqual(wrote["folder"], "Briefs/my-research")
        self.assertEqual(wrote["file"], "x")


class ObsidianTests(Fixture):
    """The vault copy: local, written by the render, and the primary one."""

    def docs(self) -> list[dict]:
        (self.repo / "10-x").mkdir(parents=True, exist_ok=True)
        (self.repo / "10-x" / "a.md").write_text("# A\n\nbody\n", encoding="utf-8")
        return [dict(src="10-x/a.md", out="a", title="A")]

    def test_the_markdown_lands_under_briefs_and_the_repo_name(self) -> None:
        PUBLISH.write_obsidian(self.repo, self.docs())
        self.assertTrue((self.briefs() / "a.md").is_file())

    def test_it_carries_the_markdown_and_not_the_rendered_page(self) -> None:
        """The vault's value is that a note is editable and linkable; an HTML
        blob in it is neither."""
        PUBLISH.write_obsidian(self.repo, self.docs())
        written = (self.briefs() / "a.md").read_text(encoding="utf-8")
        self.assertIn("# A", written)
        self.assertNotIn("<html", written)

    def test_provenance_is_frontmatter_so_the_vault_can_query_it(self) -> None:
        PUBLISH.write_obsidian(self.repo, self.docs())
        written = (self.briefs() / "a.md").read_text(encoding="utf-8")
        self.assertTrue(written.startswith("---\n"))
        self.assertIn("source_repo: my-research", written)
        self.assertIn("source_path: 10-x/a.md", written)

    def test_a_re_render_replaces_rather_than_appends(self) -> None:
        PUBLISH.write_obsidian(self.repo, self.docs())
        PUBLISH.write_obsidian(self.repo, self.docs())
        written = (self.briefs() / "a.md").read_text(encoding="utf-8")
        self.assertEqual(written.count("source_repo:"), 1)

    def test_no_vault_is_reported_and_does_not_fail_the_render(self) -> None:
        """A machine with no vault still publishes to the dashboard, the same
        way one with no dashboard checkout still renders."""
        PUBLISH.VAULT = ""
        said = PUBLISH.write_obsidian(self.repo, self.docs())
        self.assertTrue(any("OBSIDIAN_VAULT is not set" in line for line in said))

    def test_an_unreadable_source_is_reported_and_the_rest_continue(self) -> None:
        docs = self.docs() + [dict(src="10-x/missing.md", out="b", title="B")]
        said = PUBLISH.write_obsidian(self.repo, docs)
        self.assertTrue(any("cannot read" in line for line in said))
        self.assertTrue((self.briefs() / "a.md").is_file())


class GitignoreTests(Fixture):
    def test_the_dashboard_folder_is_ignored(self) -> None:
        PUBLISH.ignore_dashboard(self.repo)
        self.assertIn("docs/dashboard/",
                      (self.repo / ".gitignore").read_text(encoding="utf-8"))

    def test_a_second_run_does_not_add_it_twice(self) -> None:
        PUBLISH.ignore_dashboard(self.repo)
        said = PUBLISH.ignore_dashboard(self.repo)
        self.assertIn("already ignored", said)
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(text.count("docs/dashboard"), 1)

    def test_an_existing_gitignore_keeps_what_it_had(self) -> None:
        (self.repo / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
        PUBLISH.ignore_dashboard(self.repo)
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.pyc", text)
        self.assertIn("docs/dashboard/", text)


class BuildMigrationTests(Fixture):
    """`build/` was the published directory before `docs/dashboard/`."""

    def test_this_repos_own_stale_build_row_is_moved(self) -> None:
        self.conf.write_text(
            HEADER + "root|my-research|MINE|%s\n" % (self.repo / "build"),
            encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("moved", said)
        mine = [r for r in self.roots() if "my-research" in r]
        self.assertEqual(len(mine), 1, "moved, not duplicated")
        self.assertTrue(mine[0].endswith("docs/dashboard"))

    def test_a_row_naming_another_repo_is_still_left_alone(self) -> None:
        """Moving a row is this repository reclaiming its own; a key that names
        somebody else's directory is still a collision to report."""
        self.conf.write_text(
            HEADER + "root|my-research|MINE|%s\n" % (self.root / "elsewhere" / "build"),
            encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("left alone", said)


class RepoKeyTests(unittest.TestCase):
    def test_the_key_is_usable_in_a_url(self) -> None:
        for name in ("Traces-Research", "my repo", "a.b_c"):
            key = PUBLISH.repo_key(Path("/tmp") / name)
            self.assertRegex(key, r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z", name)


if __name__ == "__main__":
    unittest.main()
