"""Fleet-wide settings as `setting` rows, and a Documents root's label (sd:3989, sd:3987, sd:3986).

The design is the system repository's `docs/work/2026-10-13-config-to-db/design.md`, slice P1.
Row wins: once the database holds a row for a key, `config.json` is not read for it, and a
cleared row is a row. A read that fails is unknown: a `ConfigError`, never the file's value.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from sd_db import connect, set_view, views
from sd_db.errors import SdDbError
from sd_db import schema as schema_module
from sd_db.migrate import initialise, migrate
from sd_db.writes import SettingStale, read_settings, set_setting

from . import support

REPO = Path(support.LIB).parent
sys.path.insert(0, str(REPO / "bin"))
import sd_lib  # type: ignore[import-not-found]  # noqa: E402 - bin/ is not a package

SD = REPO / "bin" / "sd"


class SettingCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sd.db"
        initialise(self.path)
        self.connection = connect(self.path)
        self.addCleanup(self.connection.close)


class TheSettingRow(SettingCase):
    """`set_setting` writes one `setting` row per call; `settings` reads the latest per key."""

    def test_a_key_never_held_is_absent_and_a_cleared_key_reads_none(self):
        self.assertEqual(read_settings(self.connection, ["sd.copilot_review"]), {})
        self.assertIsNone(set_setting(self.connection, "sd.copilot_review", "never"))
        self.assertEqual(set_setting(self.connection, "sd.copilot_review", None), "never")
        self.assertEqual(read_settings(self.connection, ["sd.copilot_review", "sd.fleet_owners"]),
                         {"sd.copilot_review": None})
        rows = self.connection.execute("SELECT kind, key, body FROM state ORDER BY id").fetchall()
        self.assertEqual([tuple(row) for row in rows],
                         [("setting", "sd.copilot_review", '{"value": "never"}'),
                          ("setting", "sd.copilot_review", '{"value": null}')])

    def test_a_stale_before_refuses_and_writes_nothing(self):
        set_setting(self.connection, "dashboard.home_tiles", "headline|Home")
        with self.assertRaises(SettingStale):
            set_setting(self.connection, "dashboard.home_tiles", "headline|Other", before="headline|Old")
        self.assertEqual(read_settings(self.connection, ["dashboard.home_tiles"]), {"dashboard.home_tiles": "headline|Home"})
        set_setting(self.connection, "dashboard.home_tiles", "headline|New", before="headline|Home")
        self.assertEqual(read_settings(self.connection, ["dashboard.home_tiles"]), {"dashboard.home_tiles": "headline|New"})

    def test_a_bad_key_or_value_is_refused_and_writes_nothing(self):
        keys: list[Any] = ["", "copilot_review", "SD.x", "sd.", "sd x.y", None, "sd." + "x" * 130]
        for key in keys:
            with self.subTest(key=key), self.assertRaises(SdDbError):
                set_setting(self.connection, key, "never")
        values: list[Any] = ["", 7, "x" * 16385]
        for value in values:
            with self.subTest(value=value), self.assertRaises(SdDbError):
                set_setting(self.connection, "sd.copilot_review", value)
        self.assertEqual(self.connection.execute("SELECT count(*) FROM state").fetchone()[0], 0)

    def test_a_row_the_reader_cannot_parse_is_unknown_not_unset(self):
        for body in ("not json", '["never"]', '{"other": 1}', '{"value": 7}'):
            with self.subTest(body=body):
                self.connection.execute(
                    "INSERT INTO state (kind, key, timestamp, body) VALUES ('setting', 'sd.copilot_review', 't', ?)",
                    (body,))
                with self.assertRaises(SdDbError):
                    read_settings(self.connection, ["sd.copilot_review"])


class TheRootLabel(SettingCase):
    """A Documents root key (no `/`) takes a label beside hidden (sd:3986)."""

    def test_a_label_only_root_row_is_listed_and_a_cleared_label_drops_it(self):
        self.assertEqual(set_view(self.connection, "system", label=" System tools "),
                         {"pinned": False, "hidden": False, "tags": [], "label": "System tools"})
        self.assertEqual(views(self.connection), {"system": {"pinned": False, "hidden": False, "tags": [],
                                                             "label": "System tools"}})
        self.assertEqual(set_view(self.connection, "system", label=""), {"pinned": False, "hidden": False, "tags": []})
        self.assertEqual(views(self.connection), {})

    def test_hide_before_rename_keeps_both_and_hide_alone_keeps_the_label(self):
        set_view(self.connection, "pack", hidden=True)
        self.assertEqual(set_view(self.connection, "pack", label="Pack"),
                         {"pinned": False, "hidden": True, "tags": [], "label": "Pack"})
        self.assertEqual(set_view(self.connection, "pack", hidden=False),
                         {"pinned": False, "hidden": False, "tags": [], "label": "Pack"})
        self.assertEqual(views(self.connection)["pack"]["label"], "Pack")

    def test_a_file_key_or_a_long_label_is_refused_and_writes_nothing(self):
        with self.assertRaises(SdDbError):
            set_view(self.connection, "system/index.html", label="Index")
        with self.assertRaises(SdDbError):
            set_view(self.connection, "system", label="x" * 61)
        with self.assertRaises(SdDbError):
            set_view(self.connection, "system", label=cast(Any, 7))
        self.assertEqual(self.connection.execute("SELECT count(*) FROM state").fetchone()[0], 0)


class FleetCase(unittest.TestCase):
    """A home and an XDG config folder, each a temp folder; the database is made on request."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.home = root / "home"
        self.home.mkdir()
        self.config_home = root / "config"
        self.config_path = self.config_home / "sd-ai-command-pack" / "config.json"
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config_home),
                    "PYTHONPATH": os.environ.get("PYTHONPATH", "")}

    def database(self):
        path = self.home / ".local/share/sd/sd.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        initialise(path)
        return path

    def write_file(self, **keys):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps({"config": {"sd": keys}}), encoding="utf-8")

    def file_keys(self):
        return json.loads(self.config_path.read_text(encoding="utf-8")).get("config", {}).get("sd", {})

    def run_sd(self, *args):
        return subprocess.run([sys.executable, str(SD), *args], capture_output=True, text=True, env=self.env,
                              timeout=120)


class TheFleetRead(FleetCase):
    """`sd_lib.core_setting` for a key in `FLEET_KEYS`."""

    def test_a_machine_with_no_database_reads_the_file(self):
        self.write_file(copilot_review="never")
        self.assertEqual(sd_lib.fleet_setting("copilot_review", self.env), ("never", "file"))
        self.assertEqual(sd_lib.fleet_setting("fleet_owners", self.env), (None, "default"))

    def test_the_row_wins_over_the_file_and_a_cleared_row_hides_it(self):
        self.write_file(copilot_review="never")
        path = self.database()
        self.assertEqual(sd_lib.fleet_setting("copilot_review", self.env), ("never", "file"))
        connection = connect(path)
        set_setting(connection, "sd.copilot_review", "always")
        self.assertEqual(sd_lib.core_setting("copilot_review", self.env), "always")
        set_setting(connection, "sd.copilot_review", None)
        connection.close()
        self.assertEqual(sd_lib.fleet_setting("copilot_review", self.env), (None, "database"))

    def test_a_refused_open_raises_and_never_answers_with_the_file(self):
        self.write_file(copilot_review="never")
        self.database()
        with mock.patch("sd_db.connect", side_effect=OSError("hub refused the session")):
            with self.assertRaises(sd_lib.ConfigError) as raised:
                sd_lib.core_setting("copilot_review", self.env)
        self.assertIn("hub refused the session", str(raised.exception))

    def test_a_satellite_whose_hub_does_not_answer_raises(self):
        self.write_file(fleet_owners="example")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        hub = self.home / ".config/sd/hub.json"
        hub.parent.mkdir(parents=True)
        hub.write_text(json.dumps({"hub": "127.0.0.1", "port": port}), encoding="utf-8")
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.core_setting("fleet_owners", self.env)

    def test_a_row_outside_the_pattern_raises(self):
        connection = connect(self.database())
        set_setting(connection, "sd.copilot_review", "sometimes")
        connection.close()
        with self.assertRaises(sd_lib.ConfigError):
            sd_lib.core_setting("copilot_review", self.env)

    def test_external_reviews_stays_in_the_file(self):
        """Its machines' values are not known to match, so it is not a fleet key yet."""
        self.assertNotIn("external_reviews", sd_lib.FLEET_KEYS)
        self.write_file(external_reviews="deny")
        connection = connect(self.database())
        set_setting(connection, "sd.external_reviews", "configured")
        connection.close()
        self.assertEqual(sd_lib.core_setting("external_reviews", self.env), "deny")


class TheFleetVerbs(FleetCase):
    """`sd config set|unset|get|list` on a fleet key, with a database."""

    def test_set_writes_the_row_and_not_the_file(self):
        self.write_file(copilot_review="never")
        path = self.database()
        done = self.run_sd("config", "set", "sd.copilot_review", "always")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("never -> always (workflow database)", done.stdout)
        self.assertEqual(self.file_keys(), {"copilot_review": "never"})
        connection = connect(path)
        self.addCleanup(connection.close)
        self.assertEqual(read_settings(connection, ["sd.copilot_review"]), {"sd.copilot_review": "always"})
        got = self.run_sd("config", "get", "sd.copilot_review")
        self.assertEqual((got.returncode, got.stdout), (0, "always\n"))
        self.assertIn("is not read: the workflow database holds it", got.stderr)

    def test_unset_with_a_file_key_present_reads_unset(self):
        self.write_file(copilot_review="never")
        self.database()
        done = self.run_sd("config", "unset", "sd.copilot_review")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.file_keys(), {"copilot_review": "never"})
        got = self.run_sd("config", "get", "sd.copilot_review")
        self.assertNotEqual(got.returncode, 0)
        self.assertIn("sd.copilot_review is not set", got.stderr)
        self.assertNotEqual(self.run_sd("config", "unset", "sd.copilot_review").returncode, 0)

    def test_a_failed_write_exits_non_zero_and_the_old_answer_stands(self):
        self.write_file(copilot_review="never")
        path = self.database()
        connection = connect(path)
        set_setting(connection, "sd.copilot_review", "deep")
        connection.close()
        # A write the database refuses: the file made read-only, so the write's open fails.
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        done = self.run_sd("config", "set", "sd.copilot_review", "always")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("sd.copilot_review", done.stderr)
        path.chmod(0o644)
        self.assertEqual(sd_lib.fleet_setting("copilot_review", self.env), ("deep", "database"))

    def test_list_names_every_moved_key_with_its_source(self):
        self.write_file(fleet_owners="example", external_reviews="deny")
        connection = connect(self.database())
        set_setting(connection, "sd.copilot_review", "never")
        connection.close()
        done = self.run_sd("config", "list", "sd", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        listed = json.loads(done.stdout)
        self.assertEqual({key: (listed[key]["value"], listed[key]["source"]) for key in sd_lib.FLEET_KEYS},
                         {"copilot_review": ("never", "database"), "fleet_owners": ("example", "file")})
        self.assertEqual((listed["external_reviews"]["value"], listed["external_reviews"]["source"]), ("deny", "file"))
        self.assertEqual((listed["gate_slots"]["value"], listed["gate_slots"]["source"]), (None, "default"))
        text = self.run_sd("config", "list", "sd")
        self.assertEqual(text.returncode, 0, text.stderr)
        self.assertIn("never  [database]", text.stdout)

    def test_a_database_still_at_twenty_nine_reads_the_file_and_refuses_a_set_by_name(self):
        """Older state: the hub not yet migrated. No `setting` row can exist, so the file answers; a write names why."""
        self.write_file(copilot_review="never")
        path = self.home / ".local/share/sd/sd.db"
        path.parent.mkdir(parents=True)
        through = [m for m in schema_module.migrations() if m[0] <= 29]
        with mock.patch("sd_db.migrate.migrations", return_value=through):
            migrate(path)
        self.assertEqual(sd_lib.fleet_setting("copilot_review", self.env), ("never", "file"))
        done = self.run_sd("config", "set", "sd.copilot_review", "always")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("SchemaTooOld", done.stderr)
        self.assertEqual(self.file_keys(), {"copilot_review": "never"})

    def test_a_machine_with_no_database_keeps_the_file(self):
        done = self.run_sd("config", "set", "sd.copilot_review", "never")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.file_keys(), {"copilot_review": "never"})
        self.assertFalse((self.home / ".local/share/sd/sd.db").exists())


if __name__ == "__main__":
    unittest.main()
