"""The write fence on a returning hub's own database (system sd:5986, slice 1).

A returning old hub keeps its `sd.db` and has no `hub.json`, so a session,
a job or the dashboard on it would write its stale record. Every write
through the library to this machine's own database asks the fence before it
runs and again at its commit: `elsewhere` refuses with `hub.Fenced`, naming
the holder and the two demotion steps, `hub.json` first. `holder`, `off`
and `unknown` write (#31093). Reads stay allowed. `sd-db restore` writes
before the promoted machine takes the hub's name, and passes.

`tailscale` is the harness stub on PATH; no test reaches the real daemon.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

from sd_db import create_item, database, hub, initialise, writes
from sd_db.backup import restore
from sd_db.backup import run as backup

from . import support
from .test_fence import HUB_NAME, StubCase

OLD_HUB = "old-hub.example.test."


class FenceCase(StubCase):
    """`StubCase` with this home's own database: the default path the fence guards."""

    def setUp(self):
        super().setUp()
        self.home = self.root / "home"
        self.enterContext(mock.patch.dict(os.environ, {"HOME": str(self.home)}))
        self.enterContext(mock.patch.dict(hub._answers, clear=True))
        self.path = database.local_path()
        self.path.parent.mkdir(parents=True)
        initialise(self.path)

    def name_hub(self, value: str | None) -> None:
        super().name_hub(value)
        self.later()

    def later(self):
        """Past `FENCE_SECONDS`, so the next write asks the fence again."""
        hub._answers.clear()

    def open(self) -> sqlite3.Connection:
        connection = database.connect()
        self.addCleanup(connection.close)
        return connection

    def items(self) -> int:
        connection = database.connect(write=False)
        try:
            return connection.execute("SELECT count(*) FROM item").fetchone()[0]
        finally:
            connection.close()


class TheWriteFence(FenceCase):
    def test_a_local_write_on_a_fenced_hub_refuses(self):
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        with self.assertRaises(hub.Fenced) as caught:
            create_item(connection, kind="work", title="stale")
        text = str(caught.exception)
        self.assertIn(f"this machine is not the hub, so it writes nothing to {self.path}", text)
        self.assertIn(f"sd.hub_name names {HUB_NAME}, and this node is old-hub.example.test", text)
        self.assertIn(f"sd commands then reach the hub, {HUB_NAME}", text)
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.items(), 0)
        self.assertEqual(connection.execute("SELECT count(*) FROM item").fetchone()[0], 0, "reads still work")

    def test_the_refusal_names_hub_json_first(self):
        """Demote 2 in the design's failure table: the old order left no `hub.json` and no database."""
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        with self.assertRaises(hub.Fenced) as caught:
            self.open().execute("INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'y', '{}', '2026')")
        text = str(caught.exception)
        first = text.index("1. copy ~/.config/sd/hub.json from any satellite")
        second = text.index(f"2. move {self.path} aside as sd.db.demoted-<date>")
        self.assertLess(first, second)

    def test_the_live_hub_writes_as_today(self):
        self.name_hub(HUB_NAME)
        self.node()
        create_item(self.open(), kind="work", title="live")
        self.assertEqual(self.items(), 1)

    def test_an_unknown_fence_writes_locally(self):
        """#31093: a Tailscale outage does not stop a healthy hub, and a returning one writes only here."""
        self.name_hub(HUB_NAME)
        for state in ({"backend": "Stopped"}, {"online": False}, {"dnsname": ""}):
            with self.subTest(state=state):
                hub._name_failed = None
                self.later()
                self.node(**state)
                self.assertEqual(hub.write_role(self.path).state, "unknown")
                create_item(self.open(), kind="work", title="outage")
        self.assertEqual(self.items(), 3)

    def test_an_unset_hub_name_writes_and_asks_tailscale_nothing(self):
        self.node(OLD_HUB)
        create_item(self.open(), kind="work", title="unfenced")
        self.assertEqual(self.items(), 1)
        self.assertEqual(self.asked(), [])

    def test_a_write_open_across_the_rename_rolls_back(self):
        """The commit asks again, so a transaction open when the console renames the node writes nothing."""
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        with self.assertRaises(hub.Fenced):
            with database.transaction(connection):
                create_item(connection, kind="work", title="open across the rename")
                self.node(OLD_HUB)
                self.later()
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.items(), 0)

    def test_a_raw_commit_across_the_rename_rolls_back(self):
        """`COMMIT` by hand, `commit()`, `with connection:` and the outer savepoint's RELEASE each ask."""
        self.name_hub(HUB_NAME)
        endings = {
            "COMMIT": lambda connection: connection.execute("COMMIT"),
            "commit()": lambda connection: connection.commit(),
            "with": lambda connection: connection.__exit__(None, None, None),
            "RELEASE": lambda connection: connection.execute("RELEASE outer"),
        }
        for name, end in endings.items():
            with self.subTest(end=name):
                self.later()
                self.node()
                connection = self.open()
                connection.execute("SAVEPOINT outer" if name == "RELEASE" else "BEGIN IMMEDIATE")
                create_item(connection, kind="work", title=name)
                self.node(OLD_HUB)
                self.later()
                with self.assertRaises(hub.Fenced):
                    end(connection)
                self.assertFalse(connection.in_transaction)
                self.assertEqual(self.items(), 0)

    def test_every_statement_path_refuses(self):
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', ?, '{}', '2026')"
        paths = {
            "execute": lambda: connection.execute(insert, ("a",)),
            "executemany": lambda: connection.executemany(insert, [("b",)]),
            "executescript": lambda: connection.executescript("CREATE TABLE stale (id INTEGER)"),
            "cursor": lambda: connection.cursor().execute(insert, ("c",)),
            "inside BEGIN": lambda: (connection.execute("BEGIN IMMEDIATE"), connection.execute(insert, ("d",))),
        }
        for name, write in paths.items():
            with self.subTest(path=name), self.assertRaises(hub.Fenced):
                write()
            self.assertFalse(connection.in_transaction)
        self.assertEqual(connection.execute("SELECT count(*) FROM state WHERE kind = 'x'").fetchone()[0], 0)

    def test_reads_and_temp_tables_stay_allowed(self):
        """The old hub's dashboard still shows its stale records; a read transaction commits."""
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        with database.transaction(connection):
            connection.execute("SELECT count(*) FROM item").fetchone()
        connection.execute("CREATE TEMP TABLE scratch (id INTEGER)")
        connection.execute("INSERT INTO scratch VALUES (1)")
        self.assertEqual(connection.execute("SELECT count(*) FROM scratch").fetchone()[0], 1)

    def test_another_database_is_not_the_record(self):
        """A fixture, the Jev meter's file or a backup target holds no hub role."""
        other = self.root / "other.db"
        initialise(other)
        connection = database.connect(other)
        self.addCleanup(connection.close)
        writes.set_setting(connection, hub.HUB_NAME, HUB_NAME)
        self.node(OLD_HUB)
        create_item(connection, kind="work", title="not the record")
        self.assertEqual(self.asked(), [])

    def test_writes_inside_a_transaction_share_one_probe_and_its_commit_asks_again(self):
        """The cost bound: statements inside one transaction share the held answer; the commit asks afresh."""
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        with database.transaction(connection):
            for title in ("one", "two", "three"):
                create_item(connection, kind="work", title=title)
        self.assertEqual(len(self.asked()), 2, "one for the writes, one for the commit")
        self.assertEqual(hub.FENCE_SECONDS, 5.0)

    def test_hub_json_beside_the_database_still_refuses_an_open_writer(self):
        """Demote 1 cut short: the fence reads the file itself, so `HubConflict` does not read as unknown."""
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        config = hub.config_path()
        config.parent.mkdir(parents=True)
        config.write_text('{"hub": "hub.example.test", "port": 8769}', encoding="utf-8")
        with self.assertRaises(hub.Fenced):
            create_item(connection, kind="work", title="stale")
        with self.assertRaises(hub.HubConflict):
            database.connect()


class TheCommitBoundaries(FenceCase):
    """Lead review of 59dbc8cf0: a boundary that makes a write persist never trusts a held answer.

    Each test renames the node inside the `FENCE_SECONDS` window and keeps the held
    `holder` answer; the boundary must ask Tailscale again and refuse.
    """

    def begun(self, opening: str) -> sqlite3.Connection:
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        connection.execute(opening)
        connection.execute("INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'held', '{}', '2026')")
        self.node(OLD_HUB)
        return connection

    def rows(self) -> int:
        connection = database.connect(write=False)
        try:
            return connection.execute("SELECT count(*) FROM state WHERE kind = 'x'").fetchone()[0]
        finally:
            connection.close()

    def test_a_commit_inside_the_window_asks_again(self):
        endings = {
            "COMMIT": ("BEGIN IMMEDIATE", lambda connection: connection.execute("COMMIT")),
            "END": ("BEGIN", lambda connection: connection.execute("END")),
            "commit()": ("BEGIN IMMEDIATE", lambda connection: connection.commit()),
            "with": ("BEGIN IMMEDIATE", lambda connection: connection.__exit__(None, None, None)),
            "outer RELEASE": ("SAVEPOINT outer", lambda connection: connection.execute("RELEASE outer")),
            "executescript COMMIT": ("BEGIN IMMEDIATE", lambda connection: connection.executescript("COMMIT")),
        }
        for name, (opening, end) in endings.items():
            with self.subTest(end=name):
                hub._answers.clear()
                connection = self.begun(opening)
                with self.assertRaises(hub.Fenced):
                    end(connection)
                self.assertFalse(connection.in_transaction)
                self.assertEqual(self.rows(), 0)

    def test_a_library_transaction_inside_the_window_rolls_back(self):
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        with self.assertRaises(hub.Fenced):
            with database.transaction(connection):
                create_item(connection, kind="work", title="held across the rename")
                self.node(OLD_HUB)
        self.assertEqual(self.items(), 0)

    def test_an_autocommit_write_inside_the_window_asks_again(self):
        """A write outside a transaction commits when it ends, so it is a boundary too."""
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', ?, '{}', '2026')"
        connection.execute(insert, ("live",))
        self.node(OLD_HUB)
        writes_ = {
            "execute": lambda: connection.execute(insert, ("a",)),
            "executemany": lambda: connection.executemany(insert, [("b",)]),
            "cursor": lambda: connection.cursor().execute(insert, ("c",)),
            "executescript": lambda: connection.executescript(
                "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'd', '{}', '2026')"),
        }
        for name, write in writes_.items():
            with self.subTest(path=name), self.assertRaises(hub.Fenced):
                write()
        self.assertEqual(self.rows(), 1, "only the write before the rename")

    def test_an_inner_release_does_not_probe(self):
        """A nested savepoint's RELEASE commits nothing, so it costs no probe."""
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        connection.execute("BEGIN IMMEDIATE")
        for title in ("one", "two"):
            create_item(connection, kind="work", title=title)
        self.assertEqual(len(self.asked()), 1)
        connection.execute("COMMIT")
        self.assertEqual(len(self.asked()), 2)
        self.assertEqual(self.items(), 2)


class TheRestore(FenceCase):
    def test_restore_writes_before_the_name_is_taken(self):
        """Promote step 5 restores the old hub's record on a machine that does not hold its name yet."""
        self.name_hub(HUB_NAME)
        self.node()
        create_item(self.open(), kind="work", title="kept")
        snapshot = backup(home=self.home)
        promoted = self.root / "promoted"
        self.node("satellite.example.test.")
        self.later()
        with mock.patch.dict(os.environ, {"HOME": str(promoted)}):
            restore(snapshot.directory, home=promoted)
            connection = database.connect()
            self.addCleanup(connection.close)
            self.assertEqual(connection.execute("SELECT count(*) FROM item").fetchone()[0], 1)
            with self.assertRaises(hub.Fenced):
                create_item(connection, kind="work", title="before the rename")
            self.node()
            self.later()
            create_item(connection, kind="work", title="after the rename")


class TheCommand(FenceCase):
    def test_a_note_on_a_fenced_hub_exits_non_zero_naming_the_demotion(self):
        """The design's first acceptance line: `sd task note 1 x` on a test hub whose fence reads `elsewhere`."""
        create_item(self.open(), kind="work", title="one")
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        environment = {**os.environ, "PYTHONPATH": str(support.LIB), "HOME": str(self.home)}
        done = subprocess.run([sys.executable, str(Path(support.LIB).parent / "bin" / "sd"), "task", "note", "1", "x"],
                              capture_output=True, text=True, env=environment, timeout=120)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("1. copy ~/.config/sd/hub.json from any satellite", done.stderr)
        self.assertIn(f"sd commands then reach the hub, {HUB_NAME}", done.stderr)
