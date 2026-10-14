"""Fleet-wide settings as `setting` rows (sd:3989, sd:3987).

The design is the system repository's `docs/work/2026-10-13-config-to-db/design.md`, slice P1.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from sd_db import connect
from sd_db.errors import SdDbError
from sd_db.migrate import initialise
from sd_db.writes import SettingStale, read_settings, set_setting

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


if __name__ == "__main__":
    unittest.main()
