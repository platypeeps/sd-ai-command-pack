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

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import unittest.mock
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
import sd_lib  # noqa: E402 - on the path once `load` ran

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
        self.dashboard = self.root / "config" / "project-dashboard"
        self.dashboard.mkdir(parents=True)
        self.conf = self.dashboard / "documents.conf"
        self.conf.write_text(HEADER, encoding="utf-8")
        self.repo = self.root / "my-research"
        (self.repo / "build").mkdir(parents=True)

        self.vault = self.root / "vault"
        original = (PUBLISH.DASHBOARD_CONFIG, PUBLISH.QUEUE, PUBLISH.VAULT,
                    PUBLISH.LEGACY_QUEUE, getattr(PUBLISH, "DATABASE_HOME", None))
        PUBLISH.DASHBOARD_CONFIG = self.dashboard
        PUBLISH.QUEUE = self.root / "queue"
        PUBLISH.VAULT = str(self.vault)
        # A home with no database until a test makes one, so no test records
        # a URL on the items of the machine running it.
        self.home = self.root / "home"
        PUBLISH.DATABASE_HOME = self.home
        # Pointed inside the fixture even when a test does not use it, so no
        # test can read or empty the queue of the machine running it.
        self.legacy = self.root / "legacy-queue"
        PUBLISH.LEGACY_QUEUE = self.legacy

        def restore() -> None:
            (PUBLISH.DASHBOARD_CONFIG, PUBLISH.QUEUE, PUBLISH.VAULT,
             PUBLISH.LEGACY_QUEUE, PUBLISH.DATABASE_HOME) = original

        self.addCleanup(restore)

    def briefs(self) -> Path:
        return self.vault / "Briefs" / "my-research"

    def database(self, *titles: str) -> list[int]:
        """A workflow database under the fixture's home, holding one item per title."""
        sd_db = sd_lib.import_sd_db().module
        from sd_db.writes import create_item  # noqa: PLC0415 - after the path is set
        path = sd_db.database.local_path(self.home)
        sd_db.initialise(path)
        connection = sd_db.connect(path)
        self.addCleanup(connection.close)
        self.connection = connection
        return [create_item(connection, kind="task", title=title) for title in titles]

    def published(self, item: int) -> dict | None:
        row = self.connection.execute("SELECT fields FROM item WHERE id = ?", (item,)).fetchone()
        return json.loads(row["fields"] or "{}").get("published")

    def comments(self, item: int) -> list[str]:
        return [row["body"] for row in self.connection.execute(
            "SELECT body FROM note WHERE item = ? AND kind = 'comment' ORDER BY id", (item,))]

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
    def test_the_default_directory_writes_no_row(self) -> None:
        """The dashboard finds `docs/dashboard/` and names it from the database
        (sd:3986); it reads no `label|` line, so writing one is clutter (sd:4631).
        """
        before = self.conf.read_text(encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("finds my-research by itself", said)
        self.assertEqual(self.rows(), [])
        self.assertNotIn("label|my-research", self.conf.read_text(encoding="utf-8"))
        self.assertEqual(self.conf.read_text(encoding="utf-8"), before)
        self.assertEqual(len(self.roots()), 1, "no root| row, so no path to go stale")

    def test_a_second_run_of_the_default_writes_nothing(self) -> None:
        PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        said = PUBLISH.register_root(self.repo, "YOURS", self.repo / "docs" / "dashboard")
        self.assertIn("finds my-research by itself", said)
        self.assertEqual(self.rows(), [])

    def test_the_default_directory_needs_no_dashboard_config(self) -> None:
        PUBLISH.DASHBOARD_CONFIG = self.root / "absent"
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("finds my-research by itself", said)
        self.assertFalse((self.root / "absent").exists(), "nothing created either")

    def test_a_label_row_already_in_the_file_is_left_alone(self) -> None:
        """The page names a stale `label|` line and Rename replaces it; a
        render neither rewrites nor deletes the operator's file."""
        self.conf.write_text(HEADER + "label|my-research|OLD\n", encoding="utf-8")
        PUBLISH.register_root(self.repo, "NEW", self.repo / "docs" / "dashboard")
        self.assertEqual(self.rows(), ["label|my-research|OLD"])

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
        # sd:3515: the refusal names the next step and the file it is in.
        self.assertIn("rename", said)
        self.assertIn(str(self.conf), said)

    def test_no_dashboard_is_reported_not_raised(self) -> None:
        PUBLISH.DASHBOARD_CONFIG = self.root / "absent"
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("not registered", said)
        # sd:3515: the refusal names the next step.
        self.assertIn("SYSTEM_TOOLS_CONFIG", said)


class DashboardConfigTests(unittest.TestCase):
    """`documents.conf` is where the dashboard reads it (sd:2010).

    Since system 350553a the dashboard reads `<config>/project-dashboard/
    documents.conf`, `<config>` being `$SYSTEM_TOOLS_CONFIG` or
    `~/.config/system`. The renderer kept looking in the dashboard checkout,
    found nothing there, and printed "not registered" on every render of a
    repository the dashboard already listed.

    Each case loads the module afresh under a patched environment, because
    the path is read when the module loads -- the way a render reads it.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "my-research"
        (self.repo / "docs" / "dashboard").mkdir(parents=True)

    def loaded(self, **env: str):
        """The module as a render with `env` in its environment loads it."""
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("SYSTEM_TOOLS_CONFIG", "XDG_CONFIG_HOME")}
        with unittest.mock.patch.dict(os.environ, dict(clean, **env), clear=True):
            return load()

    def test_system_tools_config_names_the_file_the_dashboard_reads(self) -> None:
        conf = self.root / "config" / "project-dashboard" / "documents.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text(HEADER, encoding="utf-8")
        module = self.loaded(SYSTEM_TOOLS_CONFIG=str(self.root / "config"))

        said = module.register_root(self.repo, "MINE", self.repo / "build")
        self.assertNotIn("not registered", said)
        self.assertIn("registered my-research", said)
        self.assertIn("root|my-research|MINE|", conf.read_text(encoding="utf-8"))

        said = module.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("already registered", said)

    def test_no_file_at_the_config_path_is_reported_not_raised(self) -> None:
        module = self.loaded(SYSTEM_TOOLS_CONFIG=str(self.root / "empty"))
        said = module.register_root(self.repo, "MINE", self.repo / "build")
        self.assertIn("not registered", said)
        self.assertIn(str(self.root / "empty" / "project-dashboard" / "documents.conf"), said)

    def test_the_directory_follows_the_system_repositorys_rule(self) -> None:
        """`lib/system_tools_config.py` in the system repository, case by case."""
        cases = (
            ({"SYSTEM_TOOLS_CONFIG": "/cfg", "XDG_CONFIG_HOME": "/xdg", "HOME": "/h"},
             Path("/cfg/project-dashboard")),
            ({"SYSTEM_TOOLS_CONFIG": "", "XDG_CONFIG_HOME": "/xdg", "HOME": "/h"},
             Path("/xdg/system/project-dashboard")),
            ({"HOME": "/h"}, Path("/h/.config/system/project-dashboard")),
            ({"SYSTEM_TOOLS_CONFIG": "~/cfg"},
             Path.home() / "cfg" / "project-dashboard"),
        )
        for environ, expected in cases:
            with self.subTest(environ):
                self.assertEqual(PUBLISH.dashboard_config(environ), expected)


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

    def test_a_rewritten_folder_url_still_carries_the_id(self) -> None:
        """The container is the folder, not how it was spelled. A page URL
        replaced by its bare id names one `space_id`, so the recorded page is
        still the right page and dropping it would create a second."""
        url = "https://notion.so/Research-%s" % PRIVATE_FOLDER
        PUBLISH.enqueue(
            self.repo, [dict(out="a", title="A", notion=dict(space=url))])
        path = self.drained("my-research.a.notion.json", page="page-id")

        PUBLISH.enqueue(self.repo, [dict(
            out="a", title="A", notion=dict(space=PRIVATE_FOLDER))])
        self.assertEqual(json.loads(path.read_text())["page"], "page-id")

    def test_another_repo_of_the_same_name_carries_nothing(self) -> None:
        """The queue key is the repo's basename, so two checkouts called
        `research` share a request path and a default container. Adopting
        across that would hand one repo's brief the other's page."""
        doc = [dict(out="report", title="Report", notion=dict())]
        mine = self.root / "mine" / "research"
        theirs = self.root / "theirs" / "research"
        PUBLISH.enqueue(mine, doc)
        path = self.drained("research.report.notion.json", page="mine")

        PUBLISH.enqueue(theirs, doc)
        wrote = json.loads(path.read_text())
        self.assertEqual(wrote["page"], "")
        self.assertEqual(wrote["repo"], str(theirs))

    def test_another_document_of_the_same_name_carries_nothing(self) -> None:
        """`document` is compared for the same reason `repo` is: neither is
        implied by a request path that a rename or a collision can reuse."""
        PUBLISH.enqueue(self.repo, [dict(out="a", title="A", notion=dict())])
        path = self.drained("my-research.a.notion.json",
                            page="a-page", document="was-something-else")

        PUBLISH.enqueue(self.repo, [dict(out="a", title="A", notion=dict())])
        self.assertEqual(json.loads(path.read_text())["page"], "")

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

    def test_a_same_named_checkout_does_not_overwrite_the_vault_copy(self) -> None:
        """sd:3513: the vault folder is keyed on the checkout's name, so a
        second checkout with that name replaced the first one's copy and no
        report said so. It is reported and the first copy stays."""
        PUBLISH.write_obsidian(self.repo, self.docs())
        kept = (self.briefs() / "a.md").read_text(encoding="utf-8")
        other = self.root / "elsewhere" / "my-research"
        (other / "10-x").mkdir(parents=True)
        (other / "10-x" / "a.md").write_text("# Other\n", encoding="utf-8")
        said = PUBLISH.write_obsidian(other, [dict(src="10-x/a.md", out="a", title="A")])
        self.assertEqual((self.briefs() / "a.md").read_text(encoding="utf-8"), kept)
        self.assertTrue(any("a.md" in line and str(self.repo) in line for line in said), said)

    def test_a_copy_written_before_the_checkout_was_recorded_is_replaced(self) -> None:
        """A vault copy an earlier version wrote names no checkout, so the
        next render takes it over rather than refusing every document."""
        self.briefs().mkdir(parents=True)
        (self.briefs() / "a.md").write_text(
            "---\nsource_repo: my-research\nsource_path: 10-x/a.md\n---\n\nold\n", encoding="utf-8")
        PUBLISH.write_obsidian(self.repo, self.docs())
        self.assertIn("# A", (self.briefs() / "a.md").read_text(encoding="utf-8"))

    def test_a_copy_that_cannot_be_read_is_left_alone(self) -> None:
        """Whose copy it is stays unknown, and unknown is not ours."""
        self.briefs().mkdir(parents=True)
        (self.briefs() / "a.md").write_bytes(b"\xff\xfe not text")
        said = PUBLISH.write_obsidian(self.repo, self.docs())
        self.assertEqual((self.briefs() / "a.md").read_bytes(), b"\xff\xfe not text")
        self.assertTrue(any("cannot read" in line for line in said), said)

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
        self.assertIn("retired", said)
        self.assertEqual(self.rows(), [], "retired: the dashboard finds docs/dashboard itself")

    def test_a_row_naming_another_repo_is_still_left_alone(self) -> None:
        """Moving a row is this repository reclaiming its own; a key that names
        somebody else's directory is still a collision to report."""
        self.conf.write_text(
            HEADER + "root|my-research|MINE|%s\n" % (self.root / "elsewhere" / "build"),
            encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("left alone", said)


class RootRowUpgradeTests(Fixture):
    """The rows this renderer wrote before the dashboard found its own root."""

    def test_a_root_row_for_the_default_location_is_retired(self) -> None:
        """Every rendered repo may carry one of these: a re-render retires it
        rather than leave the stale path standing, and writes no `label|`."""
        self.conf.write_text(
            HEADER + "root|my-research|MINE|%s\n" % (self.repo / "docs" / "dashboard"),
            encoding="utf-8")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("retired", said)
        self.assertEqual(self.rows(), [])
        self.assertIn("root|hoa|", self.conf.read_text(encoding="utf-8"), "other rows stay")

    def test_a_root_row_for_a_genuinely_other_path_survives_untouched(self) -> None:
        """`hoa` publishes into `reports`, and the fixture header carries it.

        It is the one row that genuinely needs a path, so nothing here may
        take it, rewrite it or drop its directory.
        """
        row = "root|hoa|Stage Run HOA|~/repos/hoa/reports"
        self.assertEqual(self.rows("hoa"), [row], "the fixture starts with it")
        said = PUBLISH.register_root(self.repo, "MINE", self.repo / "docs" / "dashboard")
        self.assertIn("finds my-research by itself", said)
        self.assertEqual(self.rows("hoa"), [row])
        self.assertEqual(self.rows(), [])

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


#: The entrypoint the hook tests drive, so `init-hook` runs with the fixture
#: repository as its working directory the way it does for a user.
KIT = BIN / "sd-research-kit"

#: A committer for fixture repositories: git refuses a commit without one, and
#: the machine's own identity must not be what a test depends on.
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    merged = dict(os.environ, **GIT_ENV)
    # The machine's hooks path, if it names one, would silence every hook a
    # test installs; the fixture's repository is the only config that applies.
    # And the machine's `SD_SKIP_RENDER`, if set, would silence the hook.
    merged["GIT_CONFIG_GLOBAL"] = os.devnull
    merged.pop("SD_SKIP_RENDER", None)
    merged.update(env or {})
    return subprocess.run(
        ["git", *args], cwd=cwd, env=merged, capture_output=True, text=True,
        check=True, timeout=60,
    ).stdout.strip()


def research_repo(root: Path, name: str = "my-research") -> Path:
    """A committed research repo with one designated document."""
    repo = root / name
    (repo / "10-x").mkdir(parents=True)
    (repo / "research.conf.py").write_text(
        "PROJECT = 'MINE'\n"
        "DOCS = [dict(src='10-x/a.md', out='a', title='A', notion=dict())]\n",
        encoding="utf-8")
    (repo / "10-x" / "a.md").write_text("# A\n\nfirst\n", encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "first")
    return repo


class ReceiptFixture(Fixture):
    """One designated document, its source on disk, and a drain to call."""

    def doc(self, title: str = "A") -> list[dict]:
        return [dict(src="10-x/a.md", out="a", title=title, notion=dict())]

    def source(self, text: str) -> None:
        path = self.repo / "10-x" / "a.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def drain(self, name: str = "my-research.a.notion.json") -> str:
        """What a drain does at its end: acknowledge the generation it read."""
        fingerprint = json.loads((PUBLISH.QUEUE / name).read_text())["fingerprint"]
        return PUBLISH.mirror_delivered(name, fingerprint)[1]


class ReceiptTests(ReceiptFixture):
    """A render that changes nothing queues nothing.

    `enqueue` used to compare nothing, so every render re-queued every
    designated document: eight requests per commit in one repo, and the drain
    then re-wrote eight mirrors that had not changed. The receipt beside the
    queue records what was last queued, and an unchanged document is skipped
    whether its request is still pending or has already been drained.
    """

    def test_a_second_run_over_an_unchanged_tree_queues_once(self) -> None:
        self.source("first\n")
        first = PUBLISH.enqueue(self.repo, self.doc())
        path = PUBLISH.QUEUE / "my-research.a.notion.json"
        before = path.stat().st_mtime_ns
        second = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue(any("queued a" in line for line in first), first)
        self.assertFalse(any("queued a" in line for line in second), second)
        self.assertTrue(any("already queued" in line for line in second), second)
        self.assertEqual(path.stat().st_mtime_ns, before, "the request was rewritten")

    def test_a_delivered_request_is_not_queued_again_while_the_source_stands(self) -> None:
        """The drain records what it delivered and removes the request. Without
        that record the next render cannot tell a delivered mirror from one
        never queued, and re-queues it."""
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.assertIn("request removed", self.drain())
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertEqual(list(PUBLISH.QUEUE.glob("*.json")), [])
        self.assertTrue(any("unchanged" in line for line in said), said)

    def test_a_changed_source_is_queued_again(self) -> None:
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        self.source("second\n")
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue((PUBLISH.QUEUE / "my-research.a.notion.json").is_file())
        self.assertTrue(any("queued a" in line for line in said), said)

    def test_a_changed_title_is_queued_again(self) -> None:
        """The title is what the mirror is called, so a rename is a change
        the destination has to see even when the body did not move."""
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        PUBLISH.enqueue(self.repo, self.doc(title="A renamed"))
        self.assertTrue((PUBLISH.QUEUE / "my-research.a.notion.json").is_file())

    def test_a_changed_container_is_queued_again(self) -> None:
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        PUBLISH.enqueue(self.repo, [dict(
            src="10-x/a.md", out="a", title="A", notion=dict(team=True))])
        self.assertTrue((PUBLISH.QUEUE / "my-research.a.notion.json").is_file())

    def test_the_receipt_lives_beside_the_queue_and_not_in_it(self) -> None:
        """`sd-status` globs `*.json` in the queue, so a receipt inside it
        would read as one more pending mirror."""
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.assertEqual(
            sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
            ["my-research.a.notion.json"])
        receipts = PUBLISH.receipts()
        self.assertNotEqual(receipts, PUBLISH.QUEUE)
        self.assertTrue(receipts.is_relative_to(self.root), receipts)
        self.assertTrue(any(receipts.iterdir()), "no receipt written")

    def test_requeue_forces_a_write_of_an_unchanged_document(self) -> None:
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_MIRROR_REQUEUE="1")
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue((PUBLISH.QUEUE / "my-research.a.notion.json").is_file())
        self.assertTrue(any("queued a" in line for line in said), said)


class PublishedUrlTests(ReceiptFixture):
    """sd:3514: where a mirror landed reaches the receipt, with its item.

    A request carried page and file ids and never an item, and `delivered`
    took no URL, so nothing said where an item's brief was published.
    """

    NAME = "my-research.a.notion.json"
    URL = "https://www.notion.so/example-3c9f52b1578281a7a466fb0e2df4d928"

    def fingerprint(self) -> str:
        return json.loads((PUBLISH.QUEUE / self.NAME).read_text())["fingerprint"]

    def receipt(self) -> dict:
        return json.loads((PUBLISH.receipts() / self.NAME).read_text())

    def test_the_request_carries_the_item_the_designation_names(self) -> None:
        self.source("first\n")
        PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item=3465)])
        self.assertEqual(json.loads((PUBLISH.QUEUE / self.NAME).read_text())["item"], 3465)

    def test_delivered_records_the_url_and_the_item(self) -> None:
        self.database("one", "two")
        self.source("first\n")
        PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item=2)])
        status = PUBLISH.delivered_main([self.NAME, self.fingerprint(), "--url", self.URL])
        self.assertEqual(status, 0)
        self.assertEqual(self.receipt()["url"], self.URL)
        self.assertEqual(self.receipt()["item"], 2)

    def test_a_url_that_is_not_a_web_address_is_refused(self) -> None:
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        status = PUBLISH.delivered_main([self.NAME, self.fingerprint(), "--url", "file:///tmp/a"])
        self.assertEqual(status, 2)
        self.assertNotIn("delivered", self.receipt())
        self.assertTrue((PUBLISH.QUEUE / self.NAME).is_file())

    def test_an_item_that_is_not_a_number_is_reported_and_not_carried(self) -> None:
        self.source("first\n")
        said = PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item="sd:3465")])
        self.assertTrue(any("item=" in line for line in said), said)
        self.assertNotIn("item", json.loads((PUBLISH.QUEUE / self.NAME).read_text()))

    def test_naming_an_item_queues_a_delivered_document_once(self) -> None:
        """sd:3979: the item joins the fingerprint, so the next drain's
        `delivered` records the URL on it; a request without one hashes as before."""
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        said = PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item=3465)])
        self.assertTrue(any("queued a" in line for line in said), said)
        self.assertEqual(json.loads((PUBLISH.QUEUE / self.NAME).read_text())["item"], 3465)
        again = PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item=3465)])
        self.assertTrue(any("already queued" in line for line in again), again)

    def test_changing_the_item_queues_once_more(self) -> None:
        self.source("first\n")
        PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item=3465)])
        first = self.fingerprint()
        said = PUBLISH.enqueue(self.repo, [dict(self.doc()[0], item=3466)])
        self.assertTrue(any("queued a" in line for line in said), said)
        self.assertNotEqual(self.fingerprint(), first)


class DeliveredItemTests(ReceiptFixture):
    """sd:3979: `delivered` records the URL on the item, for the drained generation only.

    Before, the URL and the pending request's `item` went on the receipt
    whatever generation was pending, and nothing reached the item row. Every
    step that did not finish printed its reason and exited 0.
    """

    NAME = "my-research.a.notion.json"
    URL = "https://example.test/p"

    def setUp(self) -> None:
        super().setUp()
        self.item, self.other = self.database("Publish A", "Publish B")
        self.source("first\n")
        PUBLISH.enqueue(self.repo, self.doc(self.item))

    def doc(self, item: int | None = None, title: str = "A") -> list[dict]:  # type: ignore[override]
        entry = dict(src="10-x/a.md", out="a", title=title, notion=dict())
        return [dict(entry, item=item)] if item else [entry]

    def request(self) -> bytes:
        return (PUBLISH.QUEUE / self.NAME).read_bytes()

    def receipt(self) -> dict:
        return PUBLISH.load_record(PUBLISH.receipts() / self.NAME)

    def fingerprint(self) -> str:
        return json.loads(self.request())["fingerprint"]

    def deliver(self, *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            status = PUBLISH.delivered_main([self.NAME, self.fingerprint(), *extra])
        return status, out.getvalue()

    def key(self) -> str:
        return "%s::a" % self.repo

    def test_the_url_reaches_the_item_with_one_note(self) -> None:
        status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 0, said)
        self.assertEqual(self.published(self.item), {self.key(): {"title": "A", "notion": self.URL}})
        self.assertEqual(self.comments(self.item), ["Published notion a: %s" % self.URL])
        self.assertFalse((PUBLISH.QUEUE / self.NAME).exists())
        self.assertEqual(self.receipt()["item"], self.item)

    def test_an_item_without_a_url_exits_2_and_writes_nothing(self) -> None:
        before, receipt = self.request(), self.receipt()
        status, said = self.deliver()
        self.assertEqual(status, 2, said)
        self.assertIn("--url", said)
        self.assertEqual(self.request(), before)
        self.assertEqual(self.receipt(), receipt)
        self.assertIsNone(self.published(self.item))

    def test_a_refused_record_leaves_request_and_receipt_unchanged(self) -> None:
        from sd_db.writes import record_state  # noqa: PLC0415
        record_state(self.connection, "restore", key="example", body={})
        before, receipt = self.request(), self.receipt()
        status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 1, said)
        self.assertIn("restore", said)
        self.assertEqual(self.request(), before)
        self.assertEqual(self.receipt(), receipt)
        self.assertNotIn("delivered", self.receipt())

    def test_no_database_leaves_the_request_and_exits_1(self) -> None:
        self.connection.close()
        PUBLISH.DATABASE_HOME = self.root / "no-home"
        before = self.request()
        status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 1, said)
        self.assertEqual(self.request(), before)

    def test_a_newer_generation_with_another_item_records_on_neither(self) -> None:
        drained = self.fingerprint()
        self.source("second\n")
        PUBLISH.enqueue(self.repo, self.doc(self.other))
        newer = self.request()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = PUBLISH.delivered_main([self.NAME, drained, "--url", self.URL])
        self.assertEqual(status, 0, out.getvalue())
        self.assertIsNone(self.published(self.item))
        self.assertIsNone(self.published(self.other))
        self.assertEqual(self.request(), newer)
        self.assertEqual(self.receipt()["delivered"], drained)
        self.assertNotIn("item", self.receipt())

    def test_a_stop_after_the_record_reruns_to_one_note(self) -> None:
        """The record lands, the receipt write fails: exit 1, the request
        stays, and the rerun completes with `unchanged` and no second note."""
        receipt = PUBLISH.receipts() / self.NAME
        held = receipt.read_text()
        receipt.unlink()
        receipt.mkdir()
        status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 1, said)
        self.assertIn("cannot write receipt", said)
        self.assertTrue((PUBLISH.QUEUE / self.NAME).exists())
        self.assertEqual(self.comments(self.item), ["Published notion a: %s" % self.URL])
        receipt.rmdir()
        receipt.write_text(held)
        status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 0, said)
        self.assertFalse((PUBLISH.QUEUE / self.NAME).exists())
        self.assertEqual(self.comments(self.item), ["Published notion a: %s" % self.URL])

    def test_an_unlink_error_exits_1(self) -> None:
        with unittest.mock.patch.object(PUBLISH.Path, "unlink", side_effect=OSError("denied")):
            status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 1, said)
        self.assertIn("cannot remove the request", said)
        self.assertEqual(self.receipt()["delivered"], self.fingerprint())

    def test_no_readable_request_exits_1(self) -> None:
        fingerprint = self.fingerprint()
        (PUBLISH.QUEUE / self.NAME).unlink()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = PUBLISH.delivered_main([self.NAME, fingerprint, "--url", self.URL])
        self.assertEqual(status, 1, out.getvalue())

    def test_a_request_without_an_item_touches_no_database(self) -> None:
        self.connection.close()
        PUBLISH.DATABASE_HOME = self.root / "no-home"
        PUBLISH.enqueue(self.repo, self.doc())
        status, said = self.deliver("--url", self.URL)
        self.assertEqual(status, 0, said)
        self.assertEqual(self.receipt()["url"], self.URL)
        self.assertNotIn("item", self.receipt())


class ObsidianItemTests(Fixture):
    """sd:3979: the render records the vault copy's link on the item it names.

    Only a copy the render wrote, and only where it would queue a mirror. A
    refused record never fails the render, and the next render records it.
    """

    def setUp(self) -> None:
        super().setUp()
        (self.repo / "build").rmdir()
        self.repo.rmdir()
        self.repo = research_repo(self.root)
        (self.item,) = self.database("Publish A")
        self.link = "obsidian://open?vault=vault&file=Briefs%2Fmy-research%2Fa"

    def docs(self, **extra: object) -> list[dict]:
        return [dict(src="10-x/a.md", out="a", title="A", item=self.item, **extra)]

    def publish(self, docs: list[dict] | None = None) -> list[str]:
        return PUBLISH.publish(self.repo, "MINE", self.docs() if docs is None else docs)

    def test_a_written_copy_records_its_link(self) -> None:
        said = self.publish()
        self.assertEqual(self.published(self.item), {"%s::a" % self.repo: {"title": "A", "obsidian": self.link}})
        self.assertEqual(self.comments(self.item), ["Published obsidian a: %s" % self.link])
        self.assertTrue(any("item: obsidian link for sd:%d recorded" % self.item in line for line in said), said)
        self.publish()
        self.assertEqual(len(self.comments(self.item)), 1)

    def test_a_refused_record_keeps_the_copy_and_records_on_the_next_render(self) -> None:
        """Refused for an item not yet in the database. An open restore
        refuses it too, but holds the whole render first (sd:3462)."""
        from sd_db.writes import create_item  # noqa: PLC0415
        later = self.item + 1
        said = self.publish([dict(src="10-x/a.md", out="a", title="A", item=later)])
        self.assertTrue((self.briefs() / "a.md").is_file())
        self.assertTrue(any("item: obsidian link for sd:%d not recorded (" % later in line
                            for line in said), said)
        self.assertEqual(create_item(self.connection, kind="task", title="Later"), later)
        self.publish([dict(src="10-x/a.md", out="a", title="A", item=later)])
        self.assertEqual(self.published(later)["%s::a" % self.repo]["obsidian"], self.link)

    def test_no_database_reports_and_the_render_goes_on(self) -> None:
        self.connection.close()
        PUBLISH.DATABASE_HOME = self.root / "no-home"
        said = self.publish()
        self.assertTrue((self.briefs() / "a.md").is_file())
        self.assertTrue(any("not recorded (" in line for line in said), said)
        self.assertTrue(any("finds my-research by itself" in line for line in said), said)

    def test_a_document_without_an_item_records_nothing(self) -> None:
        said = self.publish([dict(src="10-x/a.md", out="a", title="A")])
        self.assertFalse(any(line.startswith("item:") for line in said), said)

    def assert_nothing_recorded(self, said: list[str]) -> None:
        self.assertIsNone(self.published(self.item))
        self.assertEqual(self.comments(self.item), [])
        self.assertFalse(any("recorded" in line and "not recorded" not in line for line in said), said)

    def test_no_vault_records_nothing(self) -> None:
        PUBLISH.VAULT = ""
        self.assert_nothing_recorded(self.publish())

    def test_an_unreadable_source_records_nothing(self) -> None:
        self.assert_nothing_recorded(self.publish([dict(src="10-x/missing.md", out="a", title="A",
                                                        item=self.item)]))

    def test_another_checkouts_copy_records_nothing(self) -> None:
        self.briefs().mkdir(parents=True)
        (self.briefs() / "a.md").write_text("---\nsource_checkout: ~/elsewhere/my-research\n---\n")
        self.assert_nothing_recorded(self.publish())

    def test_a_write_error_records_nothing(self) -> None:
        self.briefs().parent.mkdir(parents=True)
        self.briefs().write_text("a file where the folder goes")
        self.assert_nothing_recorded(self.publish())

    def test_a_held_mirror_records_nothing(self) -> None:
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_SKIP_MIRROR="testing")
        said = self.publish()
        self.assertTrue((self.briefs() / "a.md").is_file())
        self.assert_nothing_recorded(said)

    def test_a_branch_off_the_default_records_nothing(self) -> None:
        git(self.repo, "checkout", "-q", "-b", "topic")
        said = self.publish()
        self.assertTrue((self.briefs() / "a.md").is_file())
        self.assert_nothing_recorded(said)


class MirrorDryRunTests(ReceiptFixture):
    """sd:3515: `SD_MIRROR_DRY_RUN=1` says what a render would queue and
    writes neither the request nor its receipt."""

    def setUp(self) -> None:
        super().setUp()
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_MIRROR_DRY_RUN="1")

    def test_a_dry_run_reports_the_request_and_writes_nothing(self) -> None:
        self.source("first\n")
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue(any("would queue a" in line for line in said), said)
        self.assertFalse((PUBLISH.QUEUE / "my-research.a.notion.json").exists())
        self.assertFalse((PUBLISH.receipts() / "my-research.a.notion.json").exists())

    def test_a_dry_run_leaves_a_pending_request_as_it_was(self) -> None:
        self.source("first\n")
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_MIRROR_DRY_RUN="")
        PUBLISH.enqueue(self.repo, self.doc())
        path = PUBLISH.QUEUE / "my-research.a.notion.json"
        before = path.read_bytes()
        self.source("second\n")
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_MIRROR_DRY_RUN="1")
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue(any("would queue a" in line for line in said), said)
        self.assertEqual(path.read_bytes(), before)


class MirrorHoldTests(ReceiptFixture):
    """A render told to hold its mirrors queues nothing, and says why.

    sd:1991: a branch switch onto a `main` behind its upstream rendered the
    stale tree, and the render queued that text for the shared mirror a
    moment before the pull brought the current one. The hook now renders
    such a checkout with `SD_SKIP_MIRROR` set to its reason, so the dashboard
    stays current and the queue is left alone.
    """

    NAME = "my-research.a.notion.json"
    REASON = "post-checkout: HEAD is 1 commit behind its upstream"

    def test_a_held_render_queues_nothing_and_says_why(self) -> None:
        self.source("stale\n")
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_SKIP_MIRROR=self.REASON)
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertEqual(list(PUBLISH.QUEUE.glob("*.json")), [], said)
        self.assertTrue(any(self.REASON in line for line in said), said)

    def test_a_held_render_leaves_a_pending_request_as_it_was(self) -> None:
        self.source("current\n")
        PUBLISH.enqueue(self.repo, self.doc())
        before = (PUBLISH.QUEUE / self.NAME).read_text()
        self.source("stale\n")
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_SKIP_MIRROR=self.REASON)
        PUBLISH.enqueue(self.repo, self.doc())
        self.assertEqual((PUBLISH.QUEUE / self.NAME).read_text(), before)


class DrainRaceTests(ReceiptFixture):
    """A render that queues during a drain is not acknowledged by that drain.

    Vacuity, against 476c85db: the receipt recorded what was *queued*, and
    read the request's absence as "delivered". A drain that read A, then a
    render that queued B, then the drain deleting the shared file, left B's
    receipt standing with no request -- so every later render skipped B
    while the destination held A (`remote=A, source=B, queue absent`). On
    that revision `PUBLISH.delivered` does not exist, and the first test
    below fails at the call; the second fails on its `queued a` assertion,
    because the old rule made the deleted slot read as delivered.
    """

    NAME = "my-research.a.notion.json"

    def test_a_request_queued_during_a_drain_survives_the_drains_delete(self) -> None:
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        read = json.loads((PUBLISH.QUEUE / self.NAME).read_text())  # drain step 1
        self.source("B\n")
        PUBLISH.enqueue(self.repo, self.doc())  # a render during the drain
        said = PUBLISH.mirror_delivered(self.NAME, read["fingerprint"])[1]  # drain step 6
        self.assertIn("newer request is pending and stays", said)
        self.assertTrue((PUBLISH.QUEUE / self.NAME).is_file(), "B's request was deleted")
        pending = json.loads((PUBLISH.QUEUE / self.NAME).read_text())
        self.assertNotEqual(pending["fingerprint"], read["fingerprint"])
        # The next render sees B pending, not delivered, and leaves it for the
        # next drain; the drain then acknowledges B and only B is gone.
        again = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue(any("already queued" in line for line in again), again)
        self.assertIn("request removed", self.drain())
        after = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue(any("unchanged" in line for line in after), after)
        self.assertEqual(list(PUBLISH.QUEUE.glob("*.json")), [])

    def test_a_request_removed_without_a_delivery_record_is_queued_again(self) -> None:
        """Absence says nothing. A file deleted by hand, or by a drain that
        recorded nothing, is not evidence the destination holds this."""
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        (PUBLISH.QUEUE / self.NAME).unlink()
        said = PUBLISH.enqueue(self.repo, self.doc())
        self.assertTrue(any("queued a" in line for line in said), said)
        self.assertTrue((PUBLISH.QUEUE / self.NAME).is_file())

    def test_the_verb_records_and_removes_through_the_kit(self) -> None:
        """The drain is an agent session; the step it runs is this command."""
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        fingerprint = json.loads((PUBLISH.QUEUE / self.NAME).read_text())["fingerprint"]
        env = dict(os.environ, SD_MIRROR_QUEUE=str(PUBLISH.QUEUE))
        result = subprocess.run(
            [sys.executable, str(KIT), "delivered", self.NAME, fingerprint],
            env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("request removed", result.stdout)
        self.assertFalse((PUBLISH.QUEUE / self.NAME).exists())
        self.assertEqual(
            json.loads((PUBLISH.receipts() / self.NAME).read_text())["delivered"],
            fingerprint)
        self.assertIn("delivered", subprocess.run(
            [sys.executable, str(KIT), "--help"], capture_output=True, text=True).stdout)

    def test_the_verb_refuses_anything_but_a_name_and_a_fingerprint(self) -> None:
        for argv in ([], ["only-a-name"], ["a", "b", "c"]):
            result = subprocess.run(
                [sys.executable, str(KIT), "delivered", *argv],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 2, argv)


class AcknowledgementRaceTests(ReceiptFixture):
    """A render cannot land between the acknowledgement's read and its unlink.

    The reviewer's reproduction against bdb6774f, `ACK_RACE: remote=A,
    source=B, queue=False`: `mirror_delivered` read the request, wrote the
    receipt, compared the record it had read *before* those writes, and
    unlinked -- and a render that wrote B between the read and the unlink
    had B removed with A's fingerprint on the receipt. Nothing serialised
    the two writers. Now both take the queue lock, so the render lands
    wholly before the read (and the comparison keeps it) or wholly after the
    unlink (and nothing is left to remove).

    Deterministic, with no sleep and no join timeout. The acknowledgement
    runs in the main thread with its request read hooked; the hook starts
    the render in a thread and waits for it to *report progress*: a render
    that reaches the lock reports before it can hold it, and a render that
    finds no lock to wait on reports when it has finished. Either way the
    hook returns with the render's write either impossible until the
    acknowledgement is done, or already done. Against bdb6774f there is no
    lock, so the render finishes inside the window and the unlink takes B.
    """

    NAME = "my-research.a.notion.json"

    def test_a_render_during_the_acknowledgement_keeps_its_request(self) -> None:
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        read = json.loads((PUBLISH.QUEUE / self.NAME).read_text())  # drain step 1
        self.source("B\n")  # what the render during the drain will queue

        progress = threading.Event()
        failures: list[BaseException] = []

        def render() -> None:
            try:
                PUBLISH.enqueue(self.repo, self.doc())
            except BaseException as problem:  # noqa: BLE001 - re-raised below
                failures.append(problem)
            finally:
                progress.set()

        thread = threading.Thread(target=render, name="render")
        real_lock = getattr(PUBLISH, "queue_locked", None)
        if real_lock is not None:
            @contextlib.contextmanager
            def announced():
                if threading.current_thread() is thread:
                    progress.set()  # at the lock, and so not yet past it
                with real_lock():
                    yield
            PUBLISH.queue_locked = announced
            self.addCleanup(setattr, PUBLISH, "queue_locked", real_lock)

        real_load = PUBLISH.load_record
        started = threading.Event()

        def hooked(path: Path) -> dict:
            record = real_load(path)
            if (path == PUBLISH.QUEUE / self.NAME
                    and threading.current_thread() is threading.main_thread()
                    and not started.is_set()):
                started.set()
                thread.start()
                progress.wait()
            return record

        PUBLISH.load_record = hooked
        self.addCleanup(setattr, PUBLISH, "load_record", real_load)

        said = PUBLISH.mirror_delivered(self.NAME, read["fingerprint"])[1]  # drain step 6
        thread.join()
        if failures:
            raise failures[0]
        self.assertTrue(started.is_set(), "the acknowledgement never read the request")
        self.assertIn("request removed", said)
        queued = (PUBLISH.QUEUE / self.NAME).is_file()
        self.assertTrue(queued, "ACK_RACE: remote=A, source=B, queue=%s" % queued)
        pending = json.loads((PUBLISH.QUEUE / self.NAME).read_text())
        self.assertNotEqual(pending["fingerprint"], read["fingerprint"], "B was not queued")
        receipt = json.loads((PUBLISH.receipts() / self.NAME).read_text())
        self.assertEqual(receipt["delivered"], read["fingerprint"])
        self.assertEqual(receipt["queued"], pending["fingerprint"])

    def test_the_lock_sits_beside_the_queue_and_survives_the_drain(self) -> None:
        """Not in the queue, where `sd-status` would list it; not removed,
        because a removed lock file is two inodes and two winners."""
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        lock = PUBLISH.queue_lock_path()
        self.assertTrue(lock.is_file(), lock)
        self.assertNotEqual(lock.parent, PUBLISH.QUEUE)
        self.assertTrue(lock.is_relative_to(self.root), lock)
        self.drain()
        self.assertTrue(lock.is_file(), "the drain removed the lock")


class RevertTests(ReceiptFixture):
    """A pending request is reconciled before a delivered receipt is trusted.

    The reviewer's reproduction against bdb6774f, `REVERT: desired_title=A,
    pending_title=B`: `already_queued` consulted the receipt first, so a
    document delivered as A, then queued as B, then reverted to A before any
    drain, read as delivered -- and B stayed in the queue for the next drain
    to rename the page with. The queue is now read first: a request asking
    for a different generation is overwritten whatever the receipt says,
    carrying the id a drain may have recorded in it.
    """

    NAME = "my-research.a.notion.json"

    def test_a_reverted_designation_overwrites_the_pending_request(self) -> None:
        self.source("body\n")
        PUBLISH.enqueue(self.repo, self.doc(title="A"))
        self.assertIn("request removed", self.drain())  # A delivered
        PUBLISH.enqueue(self.repo, self.doc(title="B"))  # the rename, queued
        path = PUBLISH.QUEUE / self.NAME
        queued = json.loads(path.read_text())
        queued["page"] = "page-a-drain-recorded"  # an interrupted drain's step 4
        path.write_text(json.dumps(queued), encoding="utf-8")
        said = PUBLISH.enqueue(self.repo, self.doc(title="A"))  # the revert
        pending = json.loads(path.read_text())
        self.assertEqual(
            pending["title"], "A",
            "REVERT: desired_title=A, pending_title=%s" % pending["title"])
        self.assertTrue(any("queued a" in line for line in said), said)
        self.assertEqual(pending["page"], "page-a-drain-recorded", "the recorded id was dropped")
        # The next drain writes A, and only then is A read as delivered again.
        self.assertIn("request removed", self.drain())
        after = PUBLISH.enqueue(self.repo, self.doc(title="A"))
        self.assertTrue(any("unchanged" in line for line in after), after)

    def test_a_delivered_document_with_nothing_pending_is_still_skipped(self) -> None:
        self.source("body\n")
        PUBLISH.enqueue(self.repo, self.doc(title="A"))
        self.drain()
        said = PUBLISH.enqueue(self.repo, self.doc(title="A"))
        self.assertTrue(any("unchanged" in line for line in said), said)
        self.assertEqual(list(PUBLISH.QUEUE.glob("*.json")), [])

    def test_a_return_to_the_delivered_text_says_so(self) -> None:
        """sd:1991's second render: the stale checkout queued old text, and the
        pull's render asked for exactly what the receipt says was delivered.
        The request is rewritten to it, and the report says why a request for
        content the destination already holds is standing."""
        self.source("current\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        self.source("stale\n")
        PUBLISH.enqueue(self.repo, self.doc())  # the checkout of a stale main
        self.source("current\n")
        said = PUBLISH.enqueue(self.repo, self.doc())  # the pull
        self.assertTrue(any("back to the delivered version" in line for line in said), said)
        delivered = json.loads((PUBLISH.receipts() / self.NAME).read_text())["delivered"]
        pending = json.loads((PUBLISH.QUEUE / self.NAME).read_text())
        self.assertEqual((pending["content"], pending["fingerprint"]), ("current\n", delivered))

    def test_a_drain_holding_the_replaced_request_is_undone_by_the_next(self) -> None:
        """Why the return to the delivered text rewrites and does not withdraw.

        A drain reads its request outside the queue lock. One that read the
        stale request and wrote it has only its acknowledgement left; were the
        request withdrawn, that acknowledgement found nothing, recorded
        nothing, and every later render read the receipt's old `delivered` and
        left the stale text on the destination for good.
        """
        self.source("current\n")
        PUBLISH.enqueue(self.repo, self.doc())
        self.drain()
        self.source("stale\n")
        PUBLISH.enqueue(self.repo, self.doc())
        read = json.loads((PUBLISH.QUEUE / self.NAME).read_text())  # drain step 1
        self.source("current\n")
        PUBLISH.enqueue(self.repo, self.doc())  # the pull, while the drain writes
        said = PUBLISH.mirror_delivered(self.NAME, read["fingerprint"])[1]  # drain step 6
        self.assertIn("newer request is pending and stays", said)
        pending = json.loads((PUBLISH.QUEUE / self.NAME).read_text())
        self.assertEqual(pending["content"], "current\n", "STALE: remote=stale, queue empty")


class MutableSourceTests(ReceiptFixture):
    """A request carries the Markdown it was queued with, and the fingerprint
    describes that text and not the path.

    The reviewer's reproduction against bdb6774f, `MUTABLE_SOURCE: remote=B,
    source=A, queue=False`: the request named a mutable `source` path and the
    fingerprint hashed the file's bytes at enqueue. Queue A, edit the file to
    B without rendering, and the drain read the path, published B and
    acknowledged A's fingerprint; restoring A then read as delivered, so A
    was never published again. The request now carries `content`, read once
    at enqueue, and the drain mirrors that; the fingerprint hashes the stored
    text, so the two cannot disagree.
    """

    NAME = "my-research.a.notion.json"

    def published(self, request: dict) -> str:
        """What a drain mirrors: the request's `content`. A request without
        one -- every request before this -- sent the drain to the path."""
        if "content" in request:
            return request["content"]
        return Path(request["source"]).read_text(encoding="utf-8")

    def test_the_drain_publishes_the_content_the_request_carries(self) -> None:
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        request = json.loads((PUBLISH.QUEUE / self.NAME).read_text())  # drain step 1
        self.source("B\n")  # edited under the queued request, with no render
        remote = self.published(request).strip()  # drain step 3
        PUBLISH.mirror_delivered(self.NAME, request["fingerprint"])[1]  # drain step 6
        self.source("A\n")  # the edit reverted
        PUBLISH.enqueue(self.repo, self.doc())
        queued = (PUBLISH.QUEUE / self.NAME).is_file()
        self.assertEqual(
            (remote, queued), ("A", False),
            "MUTABLE_SOURCE: remote=%s, source=A, queue=%s" % (remote, queued))

    def test_the_fingerprint_hashes_the_stored_text_and_not_the_path(self) -> None:
        self.source("A\n")
        PUBLISH.enqueue(self.repo, self.doc())
        request = json.loads((PUBLISH.QUEUE / self.NAME).read_text())
        self.assertEqual(request["content"], "A\n")
        targets, problems = PUBLISH.mirror_targets(self.doc()[0], self.repo)
        self.assertEqual(problems, [])
        what = PUBLISH.BY_NAME["notion"].what
        self.source("B\n")
        self.assertEqual(
            PUBLISH.mirror_fingerprint(request, targets[0], what), request["fingerprint"],
            "the fingerprint followed the path")
        self.assertNotEqual(
            PUBLISH.mirror_fingerprint(dict(request, content="B\n"), targets[0], what),
            request["fingerprint"], "the fingerprint ignores the content")


class SourceUrlTests(Fixture):
    """A request carries the GitHub URL of its source, read from `origin`.

    The request named only a local path, so the drain composed the pointer
    line's URL itself, and the owner drifted: after a repository moved to
    a new owner, its Notion pages still pointed at the old owner for six
    days (sd:1999). The render reads the owner from `origin`, and a repository
    whose origin is missing or not on github.com carries `None` rather than
    a guessed URL.
    """

    NAME = "my-research.a.notion.json"
    DOC = [dict(src="10-x/a.md", out="a", title="A", notion=dict())]
    URL = "https://github.com/example-org/research-repo/blob/HEAD/10-x/a.md"

    def setUp(self) -> None:
        super().setUp()
        (self.repo / "build").rmdir()
        self.repo.rmdir()
        self.repo = research_repo(self.root)

    def origin(self, url: str) -> None:
        if git(self.repo, "remote"):
            git(self.repo, "remote", "remove", "origin")
        git(self.repo, "remote", "add", "origin", url)
        # As a fetch leaves it: with an origin, only origin's refs name the
        # default branch the mirror publishes from (sd:2019).
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    def queued(self, docs: list[dict] | None = None, name: str = NAME) -> dict:
        with unittest.mock.patch.dict(PUBLISH.ENVIRON, SD_MIRROR_REQUEUE="1"):
            PUBLISH.enqueue(self.repo, docs or self.DOC)
        return json.loads((PUBLISH.QUEUE / name).read_text())

    def test_ssh_and_https_origins_give_one_https_url(self) -> None:
        for url in ("git@github.com:example-org/research-repo.git",
                    "ssh://git@github.com/example-org/research-repo.git",
                    "https://github.com/example-org/research-repo.git",
                    "https://github.com/example-org/research-repo"):
            with self.subTest(origin=url):
                self.origin(url)
                self.assertEqual(self.queued()["source_url"], self.URL)

    def test_no_origin_carries_no_url(self) -> None:
        self.assertIsNone(self.queued()["source_url"])

    def test_an_origin_not_on_github_carries_no_url(self) -> None:
        for url in ("https://gitlab.com/example-org/research-repo.git",
                    "https://token@github.com/example-org/research-repo.git",
                    "/srv/git/research-repo.git"):
            with self.subTest(origin=url):
                self.origin(url)
                request = self.queued()
                self.assertIsNone(request["source_url"])
                self.assertNotIn("token", json.dumps(request))

    def test_the_path_is_repo_relative_and_quoted(self) -> None:
        (self.repo / "10-x" / "a b.md").write_text("# B\n", encoding="utf-8")
        self.origin("git@github.com:example-org/research-repo.git")
        request = self.queued([dict(src="10-x/a b.md", out="b", title="B", notion=dict())],
                              "my-research.b.notion.json")
        self.assertEqual(request["source_url"],
                         "https://github.com/example-org/research-repo/blob/HEAD/10-x/a%20b.md")

    def test_a_moved_origin_queues_the_delivered_document_again(self) -> None:
        """The pointer line is part of the mirror, so a new owner is a new
        generation: a delivered page naming the old owner is written again."""
        self.origin("git@github.com:old-owner/research-repo.git")
        PUBLISH.enqueue(self.repo, self.DOC)
        fingerprint = json.loads((PUBLISH.QUEUE / self.NAME).read_text())["fingerprint"]
        self.assertIn("request removed", PUBLISH.mirror_delivered(self.NAME, fingerprint)[1])
        self.origin("git@github.com:example-org/research-repo.git")
        said = PUBLISH.enqueue(self.repo, self.DOC)
        self.assertTrue(any("queued a" in line for line in said), said)
        request = json.loads((PUBLISH.QUEUE / self.NAME).read_text())
        self.assertEqual(request["source_url"], self.URL)
        self.assertNotEqual(request["fingerprint"], fingerprint)

    def test_a_request_without_a_url_keeps_its_fingerprint(self) -> None:
        """No origin on GitHub adds nothing to the digest, so upgrading the
        pack re-queues no delivered document of such a repository."""
        request = self.queued()
        targets, _ = PUBLISH.mirror_targets(self.DOC[0], self.repo)
        what = PUBLISH.BY_NAME["notion"].what
        without = {k: v for k, v in request.items() if k != "source_url"}
        self.assertEqual(PUBLISH.mirror_fingerprint(without, targets[0], what),
                         request["fingerprint"])


class WorktreeIdentityTests(Fixture):
    """A render from a linked worktree names the repository, not the worktree.

    The key, the vault folder and the default containers were all derived
    from `Path.cwd().name`, so a render from a worktree called `tc-pins`
    wrote `label|tc-pins|TRACE-CLASSIFIER` into the dashboard's tracked
    `documents.conf` and a `Briefs/tc-pins/` folder into the vault.
    """

    def setUp(self) -> None:
        super().setUp()
        (self.repo / "build").rmdir()
        self.repo.rmdir()
        self.primary = research_repo(self.root)
        self.wt = self.root / "wt-x"
        git(self.primary, "worktree", "add", "-q", str(self.wt), "-b", "x")

    def test_the_dashboard_row_carries_the_primary_checkouts_key(self) -> None:
        said = PUBLISH.register_root(self.wt, "MINE", self.wt / "docs" / "dashboard")
        self.assertIn("finds my-research by itself", said)
        self.assertEqual(self.rows("wt-x"), [])
        self.assertEqual(self.rows(), [])

    def test_a_worktree_and_the_primary_write_no_row(self) -> None:
        PUBLISH.register_root(self.primary, "MINE", self.primary / "docs" / "dashboard")
        said = PUBLISH.register_root(self.wt, "MINE", self.wt / "docs" / "dashboard")
        self.assertIn("finds my-research by itself", said)
        self.assertEqual(self.rows(), [])

    def test_the_vault_folder_is_the_primary_checkouts(self) -> None:
        self.assertEqual(PUBLISH.vault_folder(self.wt), self.briefs())

    DOC = [dict(src="10-x/a.md", out="a", title="A", notion=dict())]

    def test_a_worktree_render_queues_nothing_and_claims_no_page_id(self) -> None:
        """Publication is the main checkout's. A worktree render must neither
        replace its pending request nor inherit the page id a drain recorded
        for it: that is branch content becoming the canonical mirror.

        Vacuity, against 476c85db: the worktree's enqueue overwrote the
        request under the repository's name, carried the recorded page id
        into it, and pointed `source` at the worktree -- the assertion on
        `source` below is the one that failed there, with the page id
        adopted.
        """
        PUBLISH.enqueue(self.primary, self.DOC)
        path = PUBLISH.QUEUE / "my-research.a.notion.json"
        request = json.loads(path.read_text())
        request["page"] = "canonical-page"  # drain step 4
        path.write_text(json.dumps(request) + "\n", encoding="utf-8")
        (self.wt / "10-x" / "a.md").write_text("branch content\n", encoding="utf-8")

        said = PUBLISH.enqueue(self.wt, self.DOC)
        self.assertEqual(sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
                         ["my-research.a.notion.json"])
        after = json.loads(path.read_text())
        self.assertEqual(Path(after["source"]).resolve(),
                         (self.primary / "10-x" / "a.md").resolve())
        self.assertEqual(after["page"], "canonical-page")
        self.assertEqual(len(said), 1, said)
        self.assertIn(str(self.primary.resolve()), said[0])
        self.assertIn("SD_PUBLISH_FROM_WORKTREE", said[0])

    def test_a_worktree_render_writes_no_vault_copy(self) -> None:
        said = PUBLISH.write_obsidian(self.wt, self.DOC)
        self.assertFalse(self.briefs().exists())
        self.assertEqual(len(said), 1, said)
        self.assertIn("SD_PUBLISH_FROM_WORKTREE", said[0])

    def test_with_the_opt_in_a_worktree_publishes_under_the_repositorys_name(self) -> None:
        """`SD_PUBLISH_FROM_WORKTREE=1` is the operator saying, on the
        invocation, that this branch's content is the canonical copy."""
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_PUBLISH_FROM_WORKTREE="1")
        PUBLISH.enqueue(self.wt, self.DOC)
        self.assertEqual(
            sorted(p.name for p in PUBLISH.QUEUE.iterdir()),
            ["my-research.a.notion.json"])
        request = json.loads(
            (PUBLISH.QUEUE / "my-research.a.notion.json").read_text())
        self.assertEqual(Path(request["repo"]).resolve(), self.primary.resolve())
        self.assertEqual(request["subfolder"], "my-research")
        # The files to read are the worktree's: that is what was rendered.
        self.assertEqual(Path(request["source"]).resolve(),
                         (self.wt / "10-x" / "a.md").resolve())
        PUBLISH.write_obsidian(self.wt, self.DOC)
        self.assertTrue((self.briefs() / "a.md").is_file())

    def test_a_primary_checkout_is_its_own_home(self) -> None:
        self.assertEqual(PUBLISH.repo_home(self.primary).resolve(),
                         self.primary.resolve())

    def test_a_directory_outside_git_is_its_own_home(self) -> None:
        plain = self.root / "plain"
        plain.mkdir()
        self.assertEqual(PUBLISH.repo_home(plain), plain)


class BranchCheckoutTests(Fixture):
    """The main checkout queues a mirror from its default branch only (sd:2019).

    The init-hook render fires on post-checkout, so a branch switch in the
    main checkout rewrote the pending request with that branch's text: a
    drain in that window published unmerged content as the canonical mirror.
    """

    NAME = "my-research.a.notion.json"
    DOC = [dict(src="10-x/a.md", out="a", title="A", notion=dict())]

    def setUp(self) -> None:
        super().setUp()
        (self.repo / "build").rmdir()
        self.repo.rmdir()
        self.repo = research_repo(self.root)
        PUBLISH.enqueue(self.repo, self.DOC)
        self.pending = (PUBLISH.QUEUE / self.NAME).read_text()

    def switch(self, *args: str) -> None:
        git(self.repo, "checkout", "-q", *args)
        (self.repo / "10-x" / "a.md").write_text("# A\n\nbranch text\n", encoding="utf-8")

    def test_a_feature_branch_switch_queues_nothing(self) -> None:
        self.switch("-b", "feature")
        said = PUBLISH.enqueue(self.repo, self.DOC)
        self.assertFalse(any("queued" in line and "not queued" not in line for line in said), said)
        self.assertEqual((PUBLISH.QUEUE / self.NAME).read_text(), self.pending)
        self.assertEqual(len(said), 1, said)
        self.assertIn("feature", said[0])
        self.assertIn("SD_PUBLISH_FROM_WORKTREE", said[0])

    def test_a_detached_head_queues_nothing(self) -> None:
        self.switch("--detach")
        said = PUBLISH.enqueue(self.repo, self.DOC)
        self.assertEqual((PUBLISH.QUEUE / self.NAME).read_text(), self.pending)
        self.assertIn("SD_PUBLISH_FROM_WORKTREE", said[0])

    def test_with_the_opt_in_a_feature_branch_queues(self) -> None:
        self.switch("-b", "feature")
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_PUBLISH_FROM_WORKTREE="1")
        said = PUBLISH.enqueue(self.repo, self.DOC)
        self.assertTrue(any("queued a" in line for line in said), said)
        self.assertNotEqual((PUBLISH.QUEUE / self.NAME).read_text(), self.pending)

    def test_the_vault_copy_is_still_written_on_a_branch(self) -> None:
        """Only the mirror is held: the vault copy is local and the next render replaces it."""
        self.switch("-b", "feature")
        self.assertEqual(PUBLISH.publish_refusal(self.repo, "obsidian"), "")

    def fork(self, origin_head: bool) -> None:
        """`feature` tracks a fork whose default branch is `feature`.

        No network: the remotes' refs are written as a fetch would leave them.
        """
        for name, url in (("origin", "https://example.test/canon.git"),
                          ("fork", "https://example.test/fork.git")):
            git(self.repo, "remote", "add", name, url)
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        if origin_head:
            git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.switch("-b", "feature")
        git(self.repo, "update-ref", "refs/remotes/fork/feature", "HEAD")
        git(self.repo, "symbolic-ref", "refs/remotes/fork/HEAD", "refs/remotes/fork/feature")
        git(self.repo, "config", "branch.feature.remote", "fork")
        git(self.repo, "config", "branch.feature.merge", "refs/heads/feature")

    def test_a_branch_tracking_a_fork_is_held(self) -> None:
        """The default branch is origin's, not the one HEAD's tracking remote publishes."""
        self.fork(origin_head=True)
        said = PUBLISH.enqueue(self.repo, self.DOC)
        self.assertEqual((PUBLISH.QUEUE / self.NAME).read_text(), self.pending)
        self.assertIn("queues from main only", said[0])

    def test_without_origin_head_a_fork_branch_is_still_held(self) -> None:
        """No `origin/HEAD`: nothing names the default, so the fork's branch is held."""
        self.fork(origin_head=False)
        refusal = PUBLISH.publish_refusal(self.repo, "mirror")
        self.assertIn("not queued from branch feature", refusal)
        self.assertIn("git remote set-head origin --auto", refusal)

    def test_without_origin_head_an_origin_main_does_not_name_the_default(self) -> None:
        """origin's default is `trunk`; an `origin/main` it also has is not proof of it."""
        git(self.repo, "remote", "add", "origin", "https://example.test/canon.git")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        self.assertEqual(git(self.repo, "branch", "--show-current").strip(), "main")
        self.assertIsNone(PUBLISH.canonical_branch(self.repo))
        self.assertIn("git remote set-head origin --auto",
                      PUBLISH.publish_refusal(self.repo, "mirror"))

    def test_with_an_origin_a_local_main_does_not_name_the_default(self) -> None:
        """origin's default is `trunk`, with no `origin/HEAD`: a local `main` is a feature branch."""
        git(self.repo, "remote", "add", "origin", "https://example.test/canon.git")
        git(self.repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        self.assertEqual(git(self.repo, "branch", "--show-current").strip(), "main")
        (self.repo / "10-x" / "a.md").write_text("# A\n\nbranch text\n", encoding="utf-8")
        self.assertIsNone(PUBLISH.canonical_branch(self.repo))
        self.assertNotEqual(PUBLISH.publish_refusal(self.repo, "mirror"), "")


class HookTests(unittest.TestCase):
    """`init-hook` installs one script under three names, and git runs it.

    The post-commit hook alone missed every pulled change: a `git pull`
    fast-forwards without committing, so the page went stale while looking
    current, and the review then demanded a render nobody was told to run.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = research_repo(self.root)
        self.hooks = self.repo / ".git" / "hooks"
        # The merge and checkout arms render only a config a render recorded
        # (sd:1376), and the stand-in below records nothing. The config this
        # repository started with has been rendered once, by hand.
        PUBLISH.trust_conf(self.repo, (self.repo / "research.conf.py").read_bytes())
        # A stand-in kit on PATH that records where and how it was called.
        self.log = self.root / "calls.log"
        bindir = self.root / "bin"
        bindir.mkdir()
        fake = bindir / "sd-research-kit"
        fake.write_text(
            "#!%s\nimport os, sys\n"
            "open(%r, 'a').write(os.getcwd() + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            % (sys.executable, str(self.log)), encoding="utf-8")
        fake.chmod(0o755)
        self.env = {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}

    def init_hook(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(KIT), "init-hook"], cwd=self.repo,
            capture_output=True, text=True, timeout=60)

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.is_file() else []

    def rendered_and_checked(self) -> list[str]:
        """One render, then the link check that follows it (sd:1840)."""
        return ["%s %s" % (self.repo.resolve(), verb) for verb in ("render", "checklinks")]

    def git(self, *args: str, env: dict[str, str] | None = None) -> str:
        merged = dict(self.env)
        merged.update(env or {})
        return git(self.repo, *args, env=merged)

    def feature_commit(self, text: str = "second\n") -> None:
        """A branch `feature`, one commit ahead of `main`, changing the document."""
        self.git("checkout", "-q", "-b", "feature")
        (self.repo / "10-x" / "a.md").write_text(text, encoding="utf-8")
        self.git("commit", "-q", "-am", "edit", env={"SD_SKIP_RENDER": "1"})
        self.git("checkout", "-q", "main", env={"SD_SKIP_RENDER": "1"})

    def test_three_hooks_are_installed_from_one_text(self) -> None:
        result = self.init_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("post-commit", "post-merge", "post-checkout"):
            path = self.hooks / name
            self.assertTrue(path.is_file(), name)
            self.assertTrue(os.access(path, os.X_OK), name)
            self.assertEqual(path.read_text(encoding="utf-8"), PUBLISH.HOOK, name)

    def test_a_second_install_changes_nothing_and_says_so(self) -> None:
        self.init_hook()
        stamps = {n: (self.hooks / n).stat().st_mtime_ns
                  for n in ("post-commit", "post-merge", "post-checkout")}
        result = self.init_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        # One line naming every target, not one line per target: the merge
        # took sd:1353's installer, which reports the set it left alone.
        self.assertIn("already installed", result.stdout)
        for name in ("post-commit", "post-merge", "post-checkout"):
            self.assertIn(name, result.stdout)
        for name, stamp in stamps.items():
            self.assertEqual((self.hooks / name).stat().st_mtime_ns, stamp, name)

    def test_a_hook_this_kit_wrote_earlier_is_upgraded(self) -> None:
        """A released body, byte for byte, is what says the file is ours.

        This branch proposed a marker line -- any file carrying
        `Installed by ...init-hook` is ours to rewrite --
        and the merge with sd:1353 took that branch's stricter test instead,
        `SUPERSEDED_HOOKS`, because a marker also claims a copy of our hook
        that somebody has edited. So the file installed here is a body this
        pack actually released rather than a hand-written stand-in, which is
        the case the weaker test could not tell apart from the stronger one.
        """
        self.hooks.mkdir(exist_ok=True)
        old = PUBLISH.SUPERSEDED_HOOKS[0]
        (self.hooks / "post-commit").write_text(old, encoding="utf-8")
        result = self.init_hook()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("upgraded", result.stdout)
        self.assertEqual((self.hooks / "post-commit").read_text(encoding="utf-8"), PUBLISH.HOOK)
        self.assertTrue((self.hooks / "post-merge").is_file())

    def test_a_hook_somebody_else_wrote_is_refused_and_kept(self) -> None:
        self.hooks.mkdir(exist_ok=True)
        theirs = "#!/bin/sh\necho theirs\n"
        (self.hooks / "post-merge").write_text(theirs, encoding="utf-8")
        result = self.init_hook()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("post-merge", result.stderr)
        self.assertEqual((self.hooks / "post-merge").read_text(encoding="utf-8"), theirs)

    def test_a_fast_forward_merge_renders(self) -> None:
        self.feature_commit()
        self.assertEqual(self.init_hook().returncode, 0)
        self.git("merge", "-q", "--ff-only", "feature")
        self.assertEqual(self.calls(), self.rendered_and_checked())

    def test_a_branch_checkout_that_changes_a_document_renders(self) -> None:
        self.feature_commit()
        self.assertEqual(self.init_hook().returncode, 0)
        self.git("checkout", "-q", "feature")
        self.assertEqual(self.calls(), self.rendered_and_checked())

    def test_a_checkout_that_moved_no_branch_renders(self) -> None:
        """Reversed by the merge with sd:1353, deliberately.

        This branch stayed quiet here, on the ground that nothing moved. That
        reads the tree against `HEAD`, and what a mirror needs to know is
        whether the tree differs from what was *published*. The two agree only
        while the published copy tracks `HEAD`, which `git checkout <rev> --
        doc.md` is exactly what stops: revert a page, publish the older text,
        restore `HEAD`, and a diff-shaped guard sees a clean tree and freezes
        the reverted text in the mirror for good. `git checkout -b` falls in
        the same arm and renders for the same reason -- a branch that did not
        move is no more a statement about the published copy than a clean tree
        is. A render that finds nothing changed is cheap; a mirror holding text
        nobody can see is not.
        """
        self.assertEqual(self.init_hook().returncode, 0)
        self.git("checkout", "-q", "-b", "same-commit")
        self.assertEqual(self.calls(), self.rendered_and_checked())

    def test_a_commit_renders_and_the_skip_variable_still_skips(self) -> None:
        self.assertEqual(self.init_hook().returncode, 0)
        (self.repo / "10-x" / "a.md").write_text("edited\n", encoding="utf-8")
        self.git("commit", "-q", "-am", "edit", env={"SD_SKIP_RENDER": "1"})
        self.assertEqual(self.calls(), [])
        (self.repo / "10-x" / "a.md").write_text("edited again\n", encoding="utf-8")
        self.git("commit", "-q", "-am", "edit again")
        self.assertEqual(self.calls(), self.rendered_and_checked())

    def test_a_worktree_add_does_not_render(self) -> None:
        """`git worktree add` runs post-checkout with no previous HEAD. A
        render there would publish a checkout nobody has committed to yet.

        This test is older than the guard it now covers. It passed under the
        merge commit too, by a different route: `git diff 0000000 <new>`
        failed and the hook's error arm returned 0. Same answer, but that arm
        returns 0 for any failure of that command, so the day something else
        throws in it a fresh clone stops rendering and this goes on passing.
        `diff_argv` says it now.
        """
        self.assertEqual(self.init_hook().returncode, 0)
        self.git("worktree", "add", "-q", str(self.root / "wt-y"), "-b", "y")
        self.assertEqual(self.calls(), [])



#: The requests, receipts, vault copies and report lines the `origin/main`
#: publisher wrote for `ChannelsTests.SCENARIO` with no setting, the fixture
#: root spelled `{root}` (sd:3462). Captured once from `origin/main` at
#: a3cd16bd8; a repo with no setting must still match it byte for byte.
NO_SETTING = Path(__file__).resolve().parent / "fixtures" / "research_publish_no_setting.json"

#: The fields `mirror_targets` puts on a request, per destination: the target
#: a fingerprint is computed over, read back out of a written request.
TARGET_FIELDS = {
    "notion": ("destination", "scope", "space_id", "resolve", "space", "subfolder", "page", "target"),
    "drive": ("destination", "folder", "file", "target"),
}


class ChannelsTests(Fixture):
    """sd:3462: the render reads the repo's `channels` setting once.

    No setting publishes as before; a setting moves each channel's folder and
    turns an omitted channel off; a setting that cannot be read holds the
    vault copy and the queue for that render.
    """

    #: Every shape of designation, so the no-setting fixture pins each one.
    SCENARIO = [
        dict(src="10-x/a.md", out="a", title="A", notion=dict()),
        dict(src="10-x/b.md", out="b", title="B", notion=dict(team=True), drive=dict()),
        dict(src="10-x/c.md", out="c", title="C", notion=dict(space="Research"),
             drive=dict(folder="Deliverables", file="1AbCdEf")),
        dict(src="10-x/d.md", out="d", title="D"),
        dict(src="10-x/e.md", out="e", title="E", notion=dict(page="https://notion.so/e")),
    ]

    def setUp(self) -> None:
        super().setUp()
        for doc in self.SCENARIO:
            path = self.repo / doc["src"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# %s\n\nbody of %s\n" % (doc["title"], doc["out"]), encoding="utf-8")

    def publish(self, docs: list[dict] | None = None) -> list[str]:
        return PUBLISH.publish(self.repo, "MINE", self.SCENARIO if docs is None else docs)

    def row(self, channels: object = None) -> None:
        """This repo's row in a fixture database, holding `channels` as JSON."""
        sd_db = sd_lib.import_sd_db().module
        from sd_db.writes import upsert_repo  # noqa: PLC0415 - after the path is set
        if not hasattr(self, "connection"):
            self.database()
        key = sd_db.paths.key(str(self.repo.resolve()))
        upsert_repo(self.connection, key)
        self.connection.execute("UPDATE repo SET channels = ? WHERE path = ?",
                                (None if channels is None else json.dumps(channels), key))
        self.connection.commit()

    def norm(self, text: str) -> str:
        for root in sorted({str(self.root.resolve()), str(self.root)}, key=len, reverse=True):
            text = text.replace(root, "{root}")
        return text

    def queued(self) -> dict[str, dict]:
        return {path.name: json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(PUBLISH.QUEUE.glob("*.json"))}

    def queue_bytes(self) -> dict[str, bytes]:
        return {path.name: path.read_bytes() for path in sorted(PUBLISH.QUEUE.glob("*.json"))}

    @staticmethod
    def fingerprint(request: dict) -> str:
        """The fingerprint `enqueue` computes, from a written request alone."""
        destination = request["destination"]
        target = {field: request[field] for field in TARGET_FIELDS[destination]}
        return PUBLISH.mirror_fingerprint(request, target, PUBLISH.BY_NAME[destination].what)

    def snapshot(self, said: list[str]) -> dict:
        """Everything a render left, the root spelled `{root}`.

        A fingerprint hashes the repo's path, so each is read at `{root}`:
        recomputed over the normalised request, and checked here to be the
        one `enqueue` wrote over the real one.
        """
        requests, fingerprints = {}, {}
        for name, request in self.queued().items():
            written = request.pop("fingerprint")
            self.assertEqual(written, self.fingerprint(request), name)
            requests[name] = json.loads(self.norm(json.dumps(request)))
            fingerprints[name] = self.fingerprint(requests[name])
        receipts = {}
        for path in sorted(PUBLISH.receipts().glob("*.json")):
            receipt = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(receipt.pop("queued"), self.queued()[path.name]["fingerprint"], path.name)
            receipts[path.name] = json.loads(self.norm(json.dumps(receipt)))
        vault = {path.relative_to(self.vault).as_posix(): self.norm(path.read_text(encoding="utf-8"))
                 for path in sorted(self.vault.rglob("*.md"))}
        return dict(requests=requests, fingerprints=fingerprints, receipts=receipts, vault=vault,
                    said=[self.norm(line) for line in said])

    def assert_origin_main(self) -> None:
        self.assertEqual(self.snapshot(self.publish()),
                         json.loads(NO_SETTING.read_text(encoding="utf-8")))

    # No setting: today's publisher, byte for byte.

    def test_a_machine_with_no_database_matches_the_origin_main_fixture(self) -> None:
        self.assertFalse(self.home.exists())
        self.assert_origin_main()

    def test_a_repo_with_no_row_matches_the_origin_main_fixture(self) -> None:
        self.database()
        self.assert_origin_main()

    def test_a_null_setting_matches_the_origin_main_fixture(self) -> None:
        self.row(None)
        self.assert_origin_main()

    def test_a_setting_naming_only_a_feed_matches_the_origin_main_fixture(self) -> None:
        """sd:3980: the inbound feed is not a publish channel, so it leaves
        no outbound channel off."""
        self.row({"feed": {"url": "https://example.test/feed.xml"}})
        self.assert_origin_main()

    def test_a_setting_naming_only_issue_sources_matches_the_origin_main_fixture(self) -> None:
        """sd:3461: the Jira and GitHub issue sources are inbound too."""
        self.row({"jira": {"project": "EXAMPLE"}, "github": {"repo": "example/project"}})
        self.assert_origin_main()

    # Folders.

    def test_a_notion_folder_replaces_the_repo_subfolder(self) -> None:
        self.row({"notion": {"folder": "Example"}})
        said = self.publish([self.SCENARIO[0]])
        request = self.queued()["my-research.a.notion.json"]
        self.assertEqual(request["subfolder"], "Example")
        self.assertEqual(request["space_id"], PRIVATE_FOLDER)
        self.assertIn("under Example", request["target"])
        self.assertTrue(any("queued a" in line for line in said), said)

    def test_a_drive_folder_replaces_briefs(self) -> None:
        self.row({"drive": {"folder": "Research/Example"}})
        self.publish([dict(src="10-x/b.md", out="b", title="B", drive=dict())])
        self.assertEqual(self.queued()["my-research.b.drive.json"]["folder"], "Research/Example")

    def test_an_empty_channel_keeps_the_default_folder(self) -> None:
        self.row({"obsidian": {}, "notion": {}, "drive": {}})
        self.publish([self.SCENARIO[1]])
        queued = self.queued()
        self.assertEqual(queued["my-research.b.notion.json"]["subfolder"], "my-research")
        self.assertEqual(queued["my-research.b.drive.json"]["folder"], "Briefs/my-research")
        self.assertTrue((self.briefs() / "b.md").is_file())

    def test_an_obsidian_folder_moves_the_vault_copy_and_the_request(self) -> None:
        self.row({"obsidian": {"folder": "Notes/example"}, "notion": {}})
        said = self.publish([self.SCENARIO[0]])
        moved = self.vault / "Notes" / "example" / "a.md"
        self.assertTrue(moved.is_file(), said)
        self.assertFalse((self.briefs() / "a.md").exists())
        self.assertEqual(self.queued()["my-research.a.notion.json"]["markdown"], str(moved))

    def test_a_setting_folder_never_overwrites_a_note_this_tool_did_not_write(self) -> None:
        """Review of b96428745: a folder the setting names is the operator's,
        not ours, so a note there that names no checkout is theirs. It is
        left alone and named; once it is gone the copy is written, and the
        next render replaces its own copy."""
        self.row({"obsidian": {"folder": "Notes"}})
        hand = self.vault / "Notes" / "d.md"
        hand.parent.mkdir(parents=True)
        hand.write_text("# My own note\n", encoding="utf-8")
        said = self.publish([self.SCENARIO[3]])
        self.assertEqual(hand.read_text(encoding="utf-8"), "# My own note\n")
        self.assertTrue(any(str(hand) in line and "left alone" in line for line in said), said)
        hand.unlink()
        self.publish([self.SCENARIO[3]])
        self.assertIn("source_checkout: ", hand.read_text(encoding="utf-8"))
        (self.repo / "10-x" / "d.md").write_text("# D\n\nedited\n", encoding="utf-8")
        self.publish([self.SCENARIO[3]])
        self.assertIn("edited", hand.read_text(encoding="utf-8"))

    def test_a_setting_naming_the_default_folder_still_never_overwrites_a_hand_note(self) -> None:
        """Self-review of b91fa6c6f: a folder the setting names is the
        operator's even when it spells the default, so the takeover of an
        earlier version's copy is for no setting alone."""
        self.row({"obsidian": {"folder": "Briefs/my-research"}})
        hand = self.briefs() / "d.md"
        hand.parent.mkdir(parents=True, exist_ok=True)
        hand.write_text("# My own note\n", encoding="utf-8")
        said = self.publish([self.SCENARIO[3]])
        self.assertEqual(hand.read_text(encoding="utf-8"), "# My own note\n")
        self.assertTrue(any(str(hand) in line and "left alone" in line for line in said), said)

    def test_a_document_key_wins_over_the_setting(self) -> None:
        self.row({"notion": {"folder": "Example"}, "drive": {"folder": "Research/Example"}})
        self.publish([self.SCENARIO[2]])
        queued = self.queued()
        self.assertEqual(queued["my-research.c.notion.json"]["space"], "Research")
        self.assertEqual(queued["my-research.c.notion.json"]["subfolder"], "")
        self.assertEqual(queued["my-research.c.drive.json"]["folder"], "Deliverables")

    def test_a_pin_wins_over_both_and_is_reported(self) -> None:
        self.row({"notion": {"folder": "Example"}, "drive": {"folder": "Research/Example"}})
        said = self.publish([self.SCENARIO[4],
                             dict(src="10-x/b.md", out="b", title="B", drive=dict(file="1AbCdEf"))])
        queued = self.queued()
        self.assertEqual(queued["my-research.e.notion.json"]["page"], "https://notion.so/e")
        self.assertEqual(queued["my-research.b.drive.json"]["file"], "1AbCdEf")
        for out, key in (("e", "page="), ("b", "file=")):
            self.assertTrue(any(line.startswith("mirror: ") and key in line and "delete" in line
                                and line.endswith(" in %s" % out) for line in said), said)

    def test_no_pin_is_reported_without_a_setting_folder(self) -> None:
        self.row({"notion": {}})
        said = self.publish([self.SCENARIO[4]])
        self.assertFalse(any("page=" in line for line in said), said)

    # An omitted channel.

    def test_an_omitted_channel_refuses_and_leaves_its_pending_request(self) -> None:
        self.publish([self.SCENARIO[1]])
        drive = PUBLISH.QUEUE / "my-research.b.drive.json"
        before = drive.read_bytes()
        (PUBLISH.QUEUE / "my-research.b.notion.json").unlink()
        self.row({"notion": {}})
        said = self.publish([self.SCENARIO[1]])
        self.assertEqual(drive.read_bytes(), before)
        self.assertTrue(any("drive: not a channel of this repo" in line for line in said), said)
        self.assertTrue(any(str(drive) in line for line in said), said)
        self.assertIn("my-research.b.notion.json", self.queued())
        # Named again on the next render: refused, never deleted.
        said = self.publish([self.SCENARIO[1]])
        self.assertTrue(any(str(drive) in line for line in said), said)
        self.assertEqual(drive.read_bytes(), before)

    def test_an_omitted_obsidian_writes_no_vault_copy_and_says_so(self) -> None:
        self.row({"notion": {}})
        said = self.publish([self.SCENARIO[0]])
        self.assertFalse(self.vault.exists())
        self.assertTrue(any(line.startswith("obsidian: not a channel of this repo") for line in said), said)
        self.assertEqual(self.queued()["my-research.a.notion.json"]["markdown"], "")
        self.assertTrue((self.root / "config").exists())

    def test_requeue_after_re_enabling_a_channel(self) -> None:
        """A drain may have written the page before the channel was left
        out, so its receipt reads delivered: re-enabling takes one render
        with `SD_MIRROR_REQUEUE=1`."""
        name = "my-research.b.drive.json"
        doc = [dict(src="10-x/b.md", out="b", title="B", drive=dict())]
        self.publish(doc)
        status, _ = PUBLISH.mirror_delivered(name, self.queued()[name]["fingerprint"])
        self.assertEqual(status, 0)
        self.row({"notion": {}})
        self.publish(doc)
        self.row({"notion": {}, "drive": {}})
        said = self.publish(doc)
        self.assertNotIn(name, self.queued())
        self.assertTrue(any("unchanged since it was last mirrored" in line for line in said), said)
        PUBLISH.ENVIRON = dict(PUBLISH.ENVIRON, SD_MIRROR_REQUEUE="1")
        self.publish(doc)
        self.assertIn(name, self.queued())

    def test_a_hold_leaves_the_legacy_queue(self) -> None:
        """The legacy queue moves into the queue; a hold moves nothing."""
        self.legacy.mkdir()
        (self.legacy / "other.a.notion.json").write_text('{"repo": "/elsewhere"}\n', encoding="utf-8")
        self.hold("unreadable file")
        said = self.publish([self.SCENARIO[0]])
        self.assertTrue(said[0].startswith(PUBLISH.HELD), said)
        self.assertTrue((self.legacy / "other.a.notion.json").is_file())
        self.assertFalse(PUBLISH.QUEUE.exists())

    # A folder change.

    def test_a_folder_change_reports_the_old_vault_copies(self) -> None:
        self.publish([self.SCENARIO[0]])
        old = self.briefs() / "a.md"
        kept = old.read_text(encoding="utf-8")
        (self.briefs() / "z.md").write_text("---\nsource_checkout: ~/elsewhere/my-research\n---\n")
        self.row({"obsidian": {"folder": "Notes/example"}, "notion": {}})
        said = self.publish([self.SCENARIO[0]])
        self.assertEqual(old.read_text(encoding="utf-8"), kept)
        self.assertTrue(any(str(old) in line for line in said), said)
        self.assertFalse(any("z.md" in line for line in said), said)

    def test_a_render_after_a_folder_change_queues_the_new_container_once(self) -> None:
        doc = [self.SCENARIO[0]]
        self.publish(doc)
        path = PUBLISH.QUEUE / "my-research.a.notion.json"
        request = json.loads(path.read_text(encoding="utf-8"))
        request["page"] = "3e1f52b1-5782-8145-9c00-e9779a77804f"
        path.write_text(json.dumps(request) + "\n", encoding="utf-8")
        self.row({"notion": {"folder": "Example"}})
        said = self.publish(doc)
        moved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(moved["subfolder"], "Example")
        self.assertEqual(moved["page"], "", "a page id belongs to the old folder")
        self.assertTrue(any("queued a" in line for line in said), said)
        said = self.publish(doc)
        self.assertTrue(any("already queued" in line for line in said), said)

    def test_a_rollback_fixture_is_rewritten_and_reported(self) -> None:
        """What the `origin/main` publisher left (the no-setting fixture
        proves it is the same), rendered again under a setting: a moved
        folder's request is rewritten under its own name, an omitted
        channel's request is reported and left, and the old vault copies
        are named."""
        self.publish()
        drive = PUBLISH.QUEUE / "my-research.b.drive.json"
        before = drive.read_bytes()
        self.row({"obsidian": {"folder": "Notes/example"}, "notion": {"folder": "Example"}})
        said = self.publish()
        queued = self.queued()
        self.assertEqual(queued["my-research.a.notion.json"]["subfolder"], "Example")
        self.assertEqual(queued["my-research.b.notion.json"]["subfolder"], "Example")
        self.assertEqual(drive.read_bytes(), before)
        for name in ("my-research.b.drive.json", "my-research.c.drive.json"):
            self.assertTrue(any(str(PUBLISH.QUEUE / name) in line for line in said), said)
        for out in "abcde":
            self.assertTrue((self.vault / "Notes" / "example" / (out + ".md")).is_file())
            self.assertTrue(any(str(self.briefs() / (out + ".md")) in line for line in said), said)

    # Unknown is not "no setting".

    def hold(self, cause: str) -> None:
        """Make the setting unreadable for `cause`."""
        sd_db = sd_lib.import_sd_db().module
        if cause == "restore":
            from sd_db.writes import record_state  # noqa: PLC0415
            self.row({"notion": {}})
            record_state(self.connection, "restore", key="example", body={})
        elif cause == "refused value":
            self.row({"notion": {}})
            self.connection.execute("UPDATE repo SET channels = ?", ('{"bogus": {}}',))
            self.connection.commit()
        elif cause == "schema too old":
            self.row(None)
            self.connection.executescript(
                "ALTER TABLE repo DROP COLUMN channels; PRAGMA user_version = 28;")
        elif cause == "unreadable file":
            path = sd_db.database.local_path(self.home)
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not a database")
        elif cause == "hub unreachable":
            path = sd_db.hub.config_path(self.home)
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"hub": "127.0.0.1", "port": 1}), encoding="utf-8")
        else:
            raise AssertionError(cause)

    def test_each_unknown_cause_holds_the_vault_copy_and_the_queue(self) -> None:
        for cause in ("restore", "refused value", "schema too old", "unreadable file",
                      "hub unreachable"):
            with self.subTest(cause=cause):
                self.setUp()
                self.__dict__.pop("connection", None)
                self.publish([self.SCENARIO[0]])
                queue = self.queue_bytes()
                self.assertTrue(queue)
                (self.briefs() / "a.md").unlink()
                (self.repo / "10-x" / "a.md").write_text("# A\n\nedited\n", encoding="utf-8")
                self.hold(cause)
                said = self.publish([self.SCENARIO[0]])
                self.assertEqual(self.queue_bytes(), queue)
                self.assertFalse((self.briefs() / "a.md").exists())
                self.assertTrue(said[0].startswith(PUBLISH.HELD), said)
                self.assertTrue(any("finds my-research by itself" in line for line in said), said)
                self.assertEqual(PUBLISH.exit_status(said), 1)

    def test_a_hold_exits_1_by_hand_and_0_from_the_hook(self) -> None:
        held = [PUBLISH.HELD + ": example"]
        clean = {k: v for k, v in os.environ.items() if k not in ("SD_RESEARCH_TRIGGER", "GIT_EXEC_PATH")}
        with unittest.mock.patch.dict(os.environ, clean, clear=True):
            self.assertEqual(PUBLISH.exit_status(held), 1)
            self.assertEqual(PUBLISH.exit_status(["mirror: queued a"]), 0)
        with unittest.mock.patch.dict(os.environ, dict(clean, SD_RESEARCH_TRIGGER="post-commit"), clear=True):
            self.assertEqual(PUBLISH.exit_status(held), 0)

    def test_the_publish_verb_exits_1_on_a_hold(self) -> None:
        repo = research_repo(self.root, "held-research")
        self.hold("unreadable file")
        clean = {k: v for k, v in os.environ.items() if k not in ("SD_RESEARCH_TRIGGER", "GIT_EXEC_PATH")}
        here = os.getcwd()
        os.chdir(repo)
        self.addCleanup(os.chdir, here)
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ, clean, clear=True), contextlib.redirect_stdout(out):
            status = PUBLISH.publish_main()
        self.assertEqual(status, 1, out.getvalue())
        self.assertIn(PUBLISH.HELD, out.getvalue())
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_the_render_exits_1_on_a_hold_by_hand(self) -> None:
        repo = research_repo(self.root, "held-research")
        (repo / "research.conf.py").write_text("PROJECT = 'MINE'\nDOCS = []\n", encoding="utf-8")
        self.hold("unreadable file")
        spec = importlib.util.spec_from_file_location("sd_research_render", BIN / "sd_research_render.py")
        assert spec and spec.loader
        render = importlib.util.module_from_spec(spec)
        # This module's publisher, so the render reads the fixture's home and
        # never the machine's database; and no python-markdown is needed for
        # a config that names no document.
        with unittest.mock.patch.dict(sys.modules, {"sd_research_publish": PUBLISH,
                                                    "markdown": types.ModuleType("markdown")}):
            spec.loader.exec_module(render)
        clean = {k: v for k, v in os.environ.items() if k not in ("SD_RESEARCH_TRIGGER", "GIT_EXEC_PATH")}
        here = os.getcwd()
        os.chdir(repo)
        self.addCleanup(os.chdir, here)
        for env, status in ((clean, 1), (dict(clean, SD_RESEARCH_TRIGGER="post-commit"), 0)):
            out = io.StringIO()
            with unittest.mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
                self.assertEqual(render.main(), status, out.getvalue())
            self.assertIn(PUBLISH.HELD, out.getvalue())

    def test_another_repos_setting_does_not_apply(self) -> None:
        """The row read is this checkout's: a setting on another path, and a
        request another checkout of the same name queued, are not this
        repo's."""
        sd_db = sd_lib.import_sd_db().module
        from sd_db.writes import upsert_repo  # noqa: PLC0415
        self.database()
        other = self.root / "elsewhere" / "my-research"
        key = sd_db.paths.key(str(other))
        upsert_repo(self.connection, key)
        self.connection.execute("UPDATE repo SET channels = ? WHERE path = ?",
                                (json.dumps({"notion": {"folder": "Other"}}), key))
        self.connection.commit()
        PUBLISH.enqueue(other, [dict(out="z", title="Z", drive=dict())])
        self.publish([self.SCENARIO[0]])
        self.assertEqual(self.queued()["my-research.a.notion.json"]["subfolder"], "my-research")
        self.row({"notion": {}})
        said = self.publish([self.SCENARIO[0]])
        self.assertFalse(any("my-research.z.drive.json" in line for line in said), said)

    def test_a_worktree_render_reads_no_setting(self) -> None:
        """A linked worktree publishes nothing, so nothing is held for it."""
        with unittest.mock.patch.object(PUBLISH, "publish_refusal", return_value="refused"):
            self.hold("unreadable file")
            said = self.publish()
        self.assertFalse(any(line.startswith(PUBLISH.HELD) for line in said), said)


class BriefTests(Fixture):
    """sd:5102: a routine brief is designated on its item, `fields.publish`, and queued like a document.

    A brief is a database row with no `research.conf.py`, so its item holds the designation, with the keys a conf
    entry takes. The request is the same file, fingerprint and receipt; its `content` is the row's text and its
    `source` names the item, since no file holds the brief.
    """

    STEM = "2026-10-18 - Daily Intel Brief"
    TEXT = "---\ntags:\n  - brief\n---\n\n# Daily Intel Brief\n\nThree things.\n"
    URL = "https://www.notion.so/example-page-0123456789abcdef0123456789abcdef"

    def setUp(self) -> None:
        super().setUp()
        self.database()
        from sd_db import routine_briefs  # noqa: PLC0415 - after the path is set
        from sd_db.writes import upsert_repo  # noqa: PLC0415
        sd_db = sd_lib.import_sd_db().module
        self.key = sd_db.paths.key(str(self.repo.resolve()))
        upsert_repo(self.connection, self.key)
        self.brief = routine_briefs.add(self.connection, self.STEM, self.TEXT, repo=str(self.repo.resolve()),
                                        who="test")["item"]

    def fields(self, value: object) -> None:
        self.connection.execute("UPDATE item SET fields = ? WHERE id = ?", (json.dumps(value), self.brief))
        self.connection.commit()

    def request(self, destination: str = "notion") -> dict:
        return json.loads((PUBLISH.QUEUE / ("my-research.%s.%s.json" % (self.STEM, destination))).read_text())

    def designate(self, publish: dict) -> None:
        """Set `fields.publish` alone, keeping what step 6 recorded in `fields.published`."""
        self.connection.execute("UPDATE item SET fields = json_set(fields, '$.publish', json(?)) WHERE id = ?",
                                (json.dumps(publish), self.brief))
        self.connection.commit()

    def deliver(self, destination: str = "notion") -> None:
        """Drain step 6 for the pending request, as `sd-research-kit delivered` runs it."""
        name = "my-research.%s.%s.json" % (self.STEM, destination)
        self.assertEqual(PUBLISH.delivered_main([name, self.request(destination)["fingerprint"], "--url", self.URL]), 0)

    def extend(self, more: str) -> None:
        self.connection.execute("UPDATE item SET body = ? WHERE id = ?", (json.dumps({"text": self.TEXT + more}),
                                                                           self.brief))
        self.connection.commit()

    def test_an_undesignated_brief_queues_nothing(self) -> None:
        self.assertEqual(PUBLISH.enqueue_briefs(self.connection), [])
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_a_designated_brief_queues_its_row_text_naming_its_item(self) -> None:
        self.fields({"publish": {"notion": {}}})
        reports = PUBLISH.enqueue_briefs(self.connection)
        self.assertTrue(any(line.startswith("mirror: queued %s " % self.STEM) for line in reports), reports)
        request = self.request()
        self.assertEqual((request["content"], request["item"], request["source"], request["rendered"]),
                         (self.TEXT, self.brief, "sd:%d" % self.brief, ""))
        self.assertEqual((request["document"], request["title"], request["space_id"]), (self.STEM, self.STEM, PRIVATE_FOLDER))

    def test_the_same_text_again_is_already_queued(self) -> None:
        self.fields({"publish": {"drive": {}}})
        PUBLISH.enqueue_briefs(self.connection)
        again = PUBLISH.enqueue_briefs(self.connection)
        self.assertTrue(any("%s: already queued" % self.STEM in line for line in again), again)

    def test_a_delivered_copy_is_updated_by_the_next_generation_in_its_container(self) -> None:
        # Drain step 6 records the URL and the container it went to; the next generation there updates that copy.
        self.designate({"notion": {}})
        PUBLISH.enqueue_briefs(self.connection)
        self.deliver()
        again = PUBLISH.enqueue_briefs(self.connection)
        self.assertTrue(any("unchanged since it was last mirrored" in line for line in again), again)
        self.extend("Four things.\n")
        PUBLISH.enqueue_briefs(self.connection)
        self.assertEqual(self.request()["page"], self.URL)

    def test_a_delivered_copy_is_not_reused_in_another_container(self) -> None:
        # sd:5122 round 1: a URL belongs to the container it was created under, as a carried id does (contract
        # step 4), so another scope, space or folder publishes afresh there.
        for before, after, destination, what in (
                ({"notion": {}}, {"notion": {"team": True}}, "notion", "page"),
                ({"notion": {}}, {"notion": {"space": "Archive"}}, "notion", "page"),
                ({"drive": {}}, {"drive": {"folder": "Elsewhere"}}, "drive", "file")):
            with self.subTest(after=after):
                self.designate(before)
                PUBLISH.enqueue_briefs(self.connection)
                self.deliver(destination)
                self.designate(after)
                PUBLISH.enqueue_briefs(self.connection)
                self.assertEqual(self.request(destination).get(what, ""), "")

    def test_a_delivery_of_an_older_generation_records_no_container(self) -> None:
        # A newer request was queued after the drain read the older one: the receipt's container is the newer
        # request's, not where this URL went, so nothing is carried from it.
        self.designate({"notion": {}})
        PUBLISH.enqueue_briefs(self.connection)
        drained = self.request()["fingerprint"]
        self.designate({"notion": {"team": True}})
        PUBLISH.enqueue_briefs(self.connection)
        name = "my-research.%s.notion.json" % self.STEM
        self.assertEqual(PUBLISH.delivered_main([name, drained, "--url", self.URL]), 0)
        self.assertNotIn("delivered_to", json.loads((PUBLISH.receipts() / name).read_text()))
        self.extend("Four things.\n")
        PUBLISH.enqueue_briefs(self.connection)
        self.assertEqual(self.request().get("page", ""), "")

    def test_a_receipt_from_before_containers_were_recorded_carries_nothing(self) -> None:
        # Older state: a receipt the previous version wrote names no container, so the drain adopts by title.
        self.designate({"drive": {}})
        PUBLISH.enqueue_briefs(self.connection)
        self.deliver("drive")
        receipt = PUBLISH.receipts() / ("my-research.%s.drive.json" % self.STEM)
        record = json.loads(receipt.read_text())
        record.pop("delivered_to", None)
        receipt.write_text(json.dumps(record))
        self.extend("Four things.\n")
        PUBLISH.enqueue_briefs(self.connection)
        self.assertEqual(self.request("drive").get("file", ""), "")

    def test_a_page_the_designation_names_wins_over_the_delivered_url(self) -> None:
        self.designate({"notion": {}})
        PUBLISH.enqueue_briefs(self.connection)
        self.deliver()
        self.designate({"notion": {"page": "https://notion.so/mine"}})
        PUBLISH.enqueue_briefs(self.connection)
        self.assertEqual(self.request()["page"], "https://notion.so/mine")

    def test_fields_that_are_not_an_object_are_reported_not_queued(self) -> None:
        for value in ([1], {"publish": ["notion"]}):
            with self.subTest(value=value):
                self.fields(value)
                reports = PUBLISH.enqueue_briefs(self.connection)
                self.assertTrue(any("sd:%d" % self.brief in line and "not queued" in line for line in reports), reports)
                self.assertFalse(PUBLISH.QUEUE.exists())

    def test_only_the_named_items_are_queued(self) -> None:
        self.fields({"publish": {"notion": {}}})
        self.assertEqual(PUBLISH.enqueue_briefs(self.connection, items={self.brief + 1}), [])
        self.assertFalse(PUBLISH.QUEUE.exists())

    def test_a_channel_the_repo_leaves_out_is_refused(self) -> None:
        self.connection.execute("UPDATE repo SET channels = ? WHERE path = ?", (json.dumps({"obsidian": {}}), self.key))
        self.connection.commit()
        self.fields({"publish": {"notion": {}}})
        PUBLISH.enqueue_briefs(self.connection)
        self.assertEqual(list(PUBLISH.QUEUE.glob("*.json")) if PUBLISH.QUEUE.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
