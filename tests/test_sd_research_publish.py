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

#: One test operator's two Notion folders. Written here and nowhere in `bin/`:
#: a page id belongs to one Notion account, so an id in the source would mirror
#: another operator's brief into a page they do not own.
PRIVATE_FOLDER = "3c9f52b1-5782-81a7-a466-fb0e2df4d928"
TEAM_FOLDER = "3cff52b1-5782-806a-acb0-ca0c8f41524b"


class Configured(unittest.TestCase):
    """A test operator whose environment names both Notion folders.

    `PUBLISH.ENVIRON` is replaced outright, so no test reads the configuration
    of the machine running it and none of them leaks a folder to the next.
    """

    def setUp(self) -> None:
        super().setUp()
        original = PUBLISH.ENVIRON
        self.addCleanup(setattr, PUBLISH, "ENVIRON", original)
        self.configure(private=PRIVATE_FOLDER, team=TEAM_FOLDER)

    def configure(self, **folders: str) -> None:
        """Set these `SD_NOTION_<SCOPE>_FOLDER` variables, and only these."""
        PUBLISH.ENVIRON = {
            "SD_NOTION_%s_FOLDER" % scope.upper(): value
            for scope, value in folders.items()
            if value
        }


class Fixture(Configured):
    def setUp(self) -> None:
        super().setUp()
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
        original = (PUBLISH.DASHBOARD_HOME, PUBLISH.QUEUE, PUBLISH.VAULT,
                    PUBLISH.LEGACY_QUEUE)
        PUBLISH.DASHBOARD_HOME = self.dashboard
        PUBLISH.QUEUE = self.root / "queue"
        PUBLISH.VAULT = str(self.vault)
        # Pointed inside the fixture even when a test does not use it, so no
        # test can read or empty the queue of the machine running it.
        self.legacy = self.root / "legacy-queue"
        PUBLISH.LEGACY_QUEUE = self.legacy

        def restore() -> None:
            (PUBLISH.DASHBOARD_HOME, PUBLISH.QUEUE, PUBLISH.VAULT,
             PUBLISH.LEGACY_QUEUE) = original

        self.addCleanup(restore)

    def briefs(self) -> Path:
        return self.vault / "Briefs" / "my-research"

    def roots(self) -> list[str]:
        return [
            line
            for line in self.conf.read_text(encoding="utf-8").splitlines()
            if line.startswith("root|")
        ]

    def rows(self, key: str = "my-research") -> list[str]:
        """Every row for one key, whichever form it takes."""
        return [
            line
            for line in self.conf.read_text(encoding="utf-8").splitlines()
            if line.split("|")[1:2] == [key]
        ]


class RegisterTests(Fixture):
    def test_the_default_directory_is_registered_without_a_path(self) -> None:
        """The dashboard finds `docs/dashboard/`. A path here is drift."""
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("registered my-research", said)
        self.assertEqual(self.rows(), ["label|my-research|MINE"])
        self.assertEqual(len(self.roots()), 1, "no root| row, so no path to go stale")

    def test_a_second_run_of_the_default_adds_nothing(self) -> None:
        PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("already registered", said)
        self.assertEqual(self.rows(), ["label|my-research|MINE"])

    def test_a_new_label_rewrites_the_row_rather_than_adding_one(self) -> None:
        PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        said = PUBLISH.register_root(self.repo, "YOURS", self.repo / "docs" / "dashboard")
        self.assertIn("relabelled", said)
        self.assertEqual(self.rows(), ["label|my-research|YOURS"])

    def test_a_directory_the_dashboard_cannot_find_still_gets_a_path(self) -> None:
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


class MirrorTargetTests(Configured):
    def test_no_key_means_local_only(self) -> None:
        self.assertEqual(PUBLISH.mirror_targets({"out": "doc"}, REPO), ([], []))

    def test_no_destination_needs_a_container_named(self) -> None:
        """Every destination has a default, so a bare designation is valid
        everywhere once Notion's folders are configured. A folder nobody has to
        name is a folder nobody can misspell."""
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
        self.assertEqual(private["space_id"], PRIVATE_FOLDER)
        (team,), _ = PUBLISH.mirror_targets({"notion": dict(team=True)}, REPO)
        self.assertEqual(team["scope"], "team")
        self.assertEqual(team["space_id"], TEAM_FOLDER)

    def test_naming_a_folder_does_not_change_the_space(self) -> None:
        """`space=` says where inside a space, never which space."""
        (target,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="Archive")}, REPO)
        self.assertEqual(target["scope"], "private")
        self.assertEqual(target["space"], "Archive")
        (target,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="Archive", team=True)}, REPO)
        self.assertEqual(target["scope"], "team")

    def test_a_notion_default_is_the_operator_s_configured_page_id(self) -> None:
        """The folder is a page id this operator configured, resolved as one.

        A name lookup that finds nothing returns an empty result rather than an
        error, so a rename would move every default mirror to nowhere and say
        so to nobody."""
        for flag, folder in ((False, PRIVATE_FOLDER), (True, TEAM_FOLDER)):
            with self.subTest(team=flag):
                (target,), _ = PUBLISH.mirror_targets(
                    {"notion": dict(team=flag)}, REPO)
                self.assertEqual(target["space_id"], folder)
                self.assertEqual(target["resolve"], "id")

    def test_an_unconfigured_notion_default_refuses_and_names_the_setting(
            self) -> None:
        """No id ships in `bin/`, because a page id belongs to one account.

        So an unconfigured operator gets a refusal naming the variable to set,
        not a request bound for a page somebody else owns."""
        for flag, setting in ((False, "SD_NOTION_PRIVATE_FOLDER"),
                              (True, "SD_NOTION_TEAM_FOLDER")):
            with self.subTest(team=flag):
                self.configure()
                targets, problems = PUBLISH.mirror_targets(
                    {"notion": dict(team=flag)}, REPO)
                self.assertEqual(targets, [])
                self.assertEqual(len(problems), 1)
                self.assertIn(setting, problems[0])

    def test_a_folder_name_in_the_setting_is_not_configuration(self) -> None:
        """A name is what the defect was. An operator who pasted one has not
        named a folder this can reach, so it refuses rather than passing the
        name along for the drain to look up."""
        self.configure(private="Briefs")
        targets, problems = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(targets, [])
        self.assertIn("SD_NOTION_PRIVATE_FOLDER", problems[0])

    def test_one_scope_configured_does_not_serve_the_other(self) -> None:
        """A configured private folder is not a team folder. Reusing it would
        put a brief in the space the operator did not name."""
        self.configure(private=PRIVATE_FOLDER)
        (private,), _ = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(private["space_id"], PRIVATE_FOLDER)
        targets, problems = PUBLISH.mirror_targets(
            {"notion": dict(team=True)}, REPO)
        self.assertEqual(targets, [])
        self.assertIn("SD_NOTION_TEAM_FOLDER", problems[0])

    def test_a_notion_default_names_the_repo_the_way_drive_does(self) -> None:
        """The vault uses `Briefs/<repo>`, and the configured folder already
        holds one page per repo. A default that stopped at the folder dropped
        every repository's briefs in beside those pages."""
        (drive,), _ = PUBLISH.mirror_targets({"drive": {}}, REPO)
        self.assertEqual(drive["folder"], "Briefs/my-research")
        (notion,), _ = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(notion["subfolder"], "my-research")
        self.assertIn("my-research", notion["target"])

    def test_naming_a_container_replaces_it_rather_than_nesting_under_it(
            self) -> None:
        """`space=` says where the document goes. Appending the repo to what
        the user named would put it somewhere they did not ask for."""
        (target,), _ = PUBLISH.mirror_targets(
            {"notion": dict(space="Archive")}, REPO)
        self.assertEqual(target["subfolder"], "")

    def test_no_folder_name_is_written_down_for_a_rename_to_invalidate(
            self) -> None:
        """Nothing in the table is a folder name, so a rename reaches nothing.

        The scopes name a config key and word a report; a default request
        carries the id and no name at all."""
        for scope in PUBLISH.NOTION_SCOPES.values():
            with self.subTest(scope.scope):
                self.assertTrue(scope.setting.startswith("SD_NOTION_"))
                self.assertNotIn("Briefs", scope.phrase)
        (private,), _ = PUBLISH.mirror_targets({"notion": {}}, REPO)
        self.assertEqual(private["space"], "")

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

    def test_a_query_string_or_fragment_does_not_defeat_id_resolution(
            self) -> None:
        """A copied Notion link carries `?pvs=` and `#<block id>`.

        The id is read off the URL path, so both are gone before it is looked
        for. Matching the whole link found no id, which read as a folder name
        and sent the drain looking for a folder called `https://...`."""
        base = ("https://www.notion.so/Briefs-"
                "3cff52b15782806aacb0ca0c8f41524b")
        for suffix in ("", "?pvs=4", "#3c9f52b15782817aa466fb0e2df4d928",
                       "?pvs=4#3c9f52b15782817aa466fb0e2df4d928", "/"):
            with self.subTest(suffix or "bare"):
                (target,), _ = PUBLISH.mirror_targets(
                    {"notion": dict(space=base + suffix)}, REPO)
                self.assertEqual(target["resolve"], "id")
                self.assertEqual(
                    target["space_id"], "3cff52b15782806aacb0ca0c8f41524b")

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
        self.assertEqual(
            notion["target"],
            "your private Notion briefs folder, under my-research")
        (team,), _ = PUBLISH.mirror_targets({"notion": dict(team=True)}, REPO)
        self.assertEqual(
            team["target"],
            "your team Notion briefs folder, under my-research")
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

    def test_a_default_notion_request_carries_the_folder_id_and_the_repo(
            self) -> None:
        """The drain reads `space_id` and `subfolder`, so both reach the file."""
        PUBLISH.enqueue(self.repo, [dict(
            src="10-x/a.md", out="a", title="A", notion=dict(team=True))])
        request = json.loads(
            (PUBLISH.QUEUE / "my-research.a.notion.json").read_text())
        self.assertEqual(request["space_id"], TEAM_FOLDER)
        self.assertEqual(request["resolve"], "id")
        self.assertEqual(request["subfolder"], "my-research")

    def test_an_unconfigured_default_queues_nothing_and_reports_it(self) -> None:
        """A refusal is reported and no request is written. A request bound for
        an unresolved folder would sit in the queue claiming work is owed."""
        self.configure()
        reports = PUBLISH.enqueue(self.repo, [dict(
            src="10-x/a.md", out="a", title="A", notion=dict())])
        self.assertEqual(list(PUBLISH.QUEUE.glob("*.json")), [])
        self.assertTrue(
            any("SD_NOTION_PRIVATE_FOLDER" in line for line in reports),
            reports)

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

    def drained(self, name: str, **fields: str) -> Path:
        """One queued request amended the way a drain's step 4 amends it."""
        path = PUBLISH.QUEUE / name
        request = json.loads(path.read_text(encoding="utf-8"))
        request.update(fields)
        path.write_text(json.dumps(request) + "\n", encoding="utf-8")
        return path

    def test_a_re_render_keeps_an_id_the_drain_recorded(self) -> None:
        """The request is the durable record, so a render must not erase it.

        A drain that writes the id into the request and stops before amending
        `research.conf.py` leaves the only record of the created page in the
        queue. The post-commit hook renders on the next commit, and a render
        that overwrote the request there would drop the id -- after which the
        next drain creates a second page carrying the same title.
        """
        doc = dict(src="10-x/a.md", out="a", title="A", notion=dict())
        PUBLISH.enqueue(self.repo, [doc])
        path = self.drained("my-research.a.notion.json",
                            page="3e1f52b1-5782-8145-9c00-e9779a77804f")

        PUBLISH.enqueue(self.repo, [doc])
        self.assertEqual(
            json.loads(path.read_text())["page"],
            "3e1f52b1-5782-8145-9c00-e9779a77804f",
        )

    def test_a_re_render_keeps_a_drive_file_the_drain_recorded(self) -> None:
        """Both destinations carry the id in the field their table names, so
        neither depends on the other having been thought about."""
        doc = dict(src="10-x/a.md", out="a", title="A", drive=dict())
        PUBLISH.enqueue(self.repo, [doc])
        path = self.drained("my-research.a.drive.json", file="1AbCdEf")

        PUBLISH.enqueue(self.repo, [doc])
        self.assertEqual(json.loads(path.read_text())["file"], "1AbCdEf")

    def test_a_carried_id_survives_a_renamed_document(self) -> None:
        """The title is what an undesignated drain adopts by, so a rename is
        exactly when the recorded id is the only thing that finds the page."""
        PUBLISH.enqueue(self.repo, [dict(out="a", title="A", notion=dict())])
        path = self.drained("my-research.a.notion.json", page="page-id")

        PUBLISH.enqueue(
            self.repo, [dict(out="a", title="A renamed", notion=dict())])
        wrote = json.loads(path.read_text())
        self.assertEqual(wrote["page"], "page-id")
        self.assertEqual(wrote["title"], "A renamed")

    def test_the_designation_wins_over_a_carried_id(self) -> None:
        """A `page=` the user wrote is the answer. The queue is a record of
        what a drain did, never an override of what the document says."""
        PUBLISH.enqueue(self.repo, [dict(out="a", title="A", notion=dict())])
        path = self.drained("my-research.a.notion.json", page="stale")

        PUBLISH.enqueue(
            self.repo, [dict(out="a", title="A", notion=dict(page="named"))])
        self.assertEqual(json.loads(path.read_text())["page"], "named")

    def test_a_carried_id_is_dropped_when_the_container_changes(self) -> None:
        """A page id belongs to the container it was created under. Moving the
        designation to the team folder makes the recorded page the wrong one,
        so the request names none and the drain resolves it afresh."""
        PUBLISH.enqueue(self.repo, [dict(out="a", title="A", notion=dict())])
        path = self.drained("my-research.a.notion.json", page="private-page")

        PUBLISH.enqueue(
            self.repo, [dict(out="a", title="A", notion=dict(team=True))])
        wrote = json.loads(path.read_text())
        self.assertEqual(wrote["page"], "")
        self.assertEqual(wrote["space_id"], TEAM_FOLDER)

    def test_an_unreadable_pending_request_carries_nothing(self) -> None:
        """A truncated or hand-edited request records nothing. It is replaced
        and reported as queued, and the drain adopts by title instead."""
        PUBLISH.enqueue(self.repo, [dict(out="a", title="A", notion=dict())])
        path = PUBLISH.QUEUE / "my-research.a.notion.json"
        path.write_text("{not json", encoding="utf-8")

        said = PUBLISH.enqueue(
            self.repo, [dict(out="a", title="A", notion=dict())])
        self.assertEqual(json.loads(path.read_text())["page"], "")
        self.assertTrue(any("queued a" in line for line in said), said)

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


class LegacyQueueTests(Fixture):
    """The queue's former name, emptied rather than read for ever.

    `~/.claude/pending-notion-syncs` was the queue from the first render that
    enqueued until one queue carried every destination. A machine that
    rendered in that window holds requests there, and nothing has read that
    path since -- so the rename made them durable and invisible, which is the
    one thing a durable queue must never be.
    """

    def legacy_request(self, name: str = "old.doc.notion.json") -> Path:
        self.legacy.mkdir(parents=True, exist_ok=True)
        path = self.legacy / name
        path.write_text(json.dumps({"repo": str(self.repo), "document": "doc"}),
                        encoding="utf-8")
        return path

    def test_a_stranded_request_moves_into_the_current_queue(self) -> None:
        """With no current directory at all, which is the upgrade's own shape:
        the rename landed before this machine's next render."""
        self.legacy_request()
        reports = PUBLISH.migrate_legacy_queue()
        self.assertEqual(
            sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
            ["old.doc.notion.json"])
        self.assertEqual(list(self.legacy.iterdir()), [])
        self.assertTrue(any("migrated 1 request" in line for line in reports),
                        reports)

    def test_the_request_arrives_with_its_contents_intact(self) -> None:
        """An old request may predate a field a reader now expects. Rewriting
        somebody's queued work to a schema it was not written under is worse
        than handing it over as it stands."""
        written = json.loads(self.legacy_request().read_text())
        PUBLISH.migrate_legacy_queue()
        moved = json.loads(
            (PUBLISH.QUEUE / "old.doc.notion.json").read_text())
        self.assertEqual(moved, written)

    def test_both_queues_present_leaves_one(self) -> None:
        """The two hold different documents, and every one of them survives."""
        PUBLISH.QUEUE.mkdir(parents=True)
        (PUBLISH.QUEUE / "new.doc.drive.json").write_text("{}", encoding="utf-8")
        self.legacy_request()
        PUBLISH.migrate_legacy_queue()
        self.assertEqual(
            sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
            ["new.doc.drive.json", "old.doc.notion.json"])
        self.assertEqual(list(self.legacy.iterdir()), [])

    def test_the_current_queue_wins_a_name_collision(self) -> None:
        """The rename is what stopped the old name being written, so a file in
        the current queue was written after its legacy twin. Keeping the older
        one would replace a current request with a stale revision."""
        PUBLISH.QUEUE.mkdir(parents=True)
        current = PUBLISH.QUEUE / "old.doc.notion.json"
        current.write_text('{"revision": "current"}', encoding="utf-8")
        self.legacy_request()
        PUBLISH.migrate_legacy_queue()
        self.assertEqual(current.read_text(), '{"revision": "current"}')
        self.assertEqual(list(self.legacy.iterdir()), [])

    def test_looking_creates_neither_directory(self) -> None:
        """A migration that provisioned a queue would leave every machine
        holding a directory it never used."""
        self.assertEqual(PUBLISH.migrate_legacy_queue(), [])
        self.assertFalse(self.legacy.exists())
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_an_empty_legacy_directory_makes_no_queue_and_no_report(
            self) -> None:
        self.legacy.mkdir(parents=True)
        self.assertEqual(PUBLISH.migrate_legacy_queue(), [])
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_one_directory_under_both_names_is_left_alone(self) -> None:
        """A machine that pointed the old variable at the new directory has
        one queue. Migrating it into itself would delete the queue."""
        PUBLISH.LEGACY_QUEUE = PUBLISH.QUEUE
        PUBLISH.QUEUE.mkdir(parents=True)
        (PUBLISH.QUEUE / "new.doc.notion.json").write_text(
            "{}", encoding="utf-8")
        self.assertEqual(PUBLISH.migrate_legacy_queue(), [])
        self.assertEqual(
            sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
            ["new.doc.notion.json"])

    def test_a_render_migrates_even_when_it_designates_nothing(self) -> None:
        """The stranded machine need not still designate a document. `publish`
        runs on every render, and `enqueue` returns before touching the
        directory when it has no request of its own to write."""
        self.legacy_request()
        (self.repo / "10-x").mkdir(parents=True)
        (self.repo / "10-x" / "a.md").write_text("# A\n", encoding="utf-8")
        reports = PUBLISH.publish(
            self.repo, "My Research",
            [dict(src="10-x/a.md", out="a", title="A")])
        self.assertTrue(any("migrated 1 request" in line for line in reports),
                        reports)
        self.assertTrue((PUBLISH.QUEUE / "old.doc.notion.json").is_file())


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
        self.assertEqual(self.rows(), ["label|my-research|MINE"], "moved, not duplicated")

    def test_a_row_naming_another_repo_is_still_left_alone(self) -> None:
        """Moving a row is this repository reclaiming its own; a key that names
        somebody else's directory is still a collision to report."""
        self.conf.write_text(
            HEADER + "root|my-research|MINE|%s\n" % (self.root / "elsewhere" / "build"),
            encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("left alone", said)


class RootRowUpgradeTests(Fixture):
    """The rows this renderer wrote before it knew about `label|`."""

    def test_a_root_row_for_the_default_location_becomes_a_label_row(self) -> None:
        """The regression: every rendered repo carries one of these today, and
        a re-render must retire it rather than leave the stale path standing."""
        self.conf.write_text(
            HEADER + "root|my-research|MINE|%s\n" % (self.repo / "docs" / "dashboard"),
            encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("moved", said)
        self.assertEqual(self.rows(), ["label|my-research|MINE"])
        self.assertEqual([r for r in self.roots() if "my-research" in r], [],
                         "the path is gone, not duplicated")

    def test_the_upgrade_keeps_the_label_the_row_carried(self) -> None:
        self.conf.write_text(
            HEADER + "root|my-research|TRACES|%s\n" % (self.repo / "docs" / "dashboard"),
            encoding="utf-8")
        PUBLISH.register_root(self.repo, "TRACES", self.repo / "docs" / "dashboard")
        self.assertEqual(self.rows(), ["label|my-research|TRACES"])

    def test_a_root_row_for_a_genuinely_other_path_survives_untouched(self) -> None:
        """`hoa` publishes into `reports`, and the fixture header carries it.

        It is the one row that genuinely needs a path, so nothing here may
        take it, rewrite it or drop its directory.
        """
        row = "root|hoa|Stage Run HOA|~/repos/hoa/reports"
        self.assertEqual(self.rows("hoa"), [row], "the fixture starts with it")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("registered my-research", said)
        self.assertEqual(self.rows("hoa"), [row])
        self.assertEqual(self.rows(), ["label|my-research|MINE"])

    def test_a_foreign_row_for_this_key_is_still_left_alone(self) -> None:
        self.conf.write_text(
            HEADER + "root|my-research|Someone Else|~/elsewhere\n", encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("left alone", said)
        self.assertEqual(self.rows(), ["root|my-research|Someone Else|~/elsewhere"])


class RepoKeyTests(unittest.TestCase):
    def test_the_key_is_usable_in_a_url(self) -> None:
        for name in ("Traces-Research", "my repo", "a.b_c"):
            key = PUBLISH.repo_key(Path("/tmp") / name)
            self.assertRegex(key, r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z", name)


if __name__ == "__main__":
    unittest.main()
