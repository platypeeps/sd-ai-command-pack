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

import functools
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from sd_db import create_item, database, hub, initialise, writes
from sd_db.backup import restore
from sd_db.backup import run as backup
from sd_db.errors import SdDbError

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

    def test_the_refusal_names_the_raw_fix_for_a_mistyped_hub_name(self):
        """Decision on #31345: no exception for `sd.hub_name`; the refusal names the fix, and the fix works."""
        typo = "hub-typo.example.test"
        self.name_hub(typo)
        self.node()
        connection = self.open()
        with self.assertRaises(hub.Fenced) as caught:
            create_item(connection, kind="work", title="locked out")
        text = str(caught.exception)
        self.assertIn(f"If this machine is the hub and sd.hub_name is mistyped, no sd command can fix it: "
                      f"run sqlite3 {self.path} \"", text)
        self.assertIn(f"or rename this node in Tailscale to {typo}", text)
        fix = text.split(f"run sqlite3 {self.path} \"", 1)[1].split("\"", 1)[0]
        raw = sqlite3.connect(self.path)
        raw.execute(fix.replace("<this node>", HUB_NAME))
        raw.commit()
        raw.close()
        self.later()
        create_item(connection, kind="work", title="fixed")
        self.assertEqual(self.items(), 1)

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
            "executescript": lambda: connection.executescript(
                "BEGIN IMMEDIATE; CREATE TABLE stale (id INTEGER); COMMIT;"),
            "cursor": lambda: connection.cursor().execute(insert, ("c",)),
            "execute's cursor": lambda: connection.execute("SELECT 1").execute(insert, ("e",)),
            "inside BEGIN": lambda: (connection.execute("BEGIN IMMEDIATE"), connection.execute(insert, ("d",))),
        }
        for name, write in paths.items():
            with self.subTest(path=name), self.assertRaises(hub.Fenced):
                write()
            self.assertFalse(connection.in_transaction)
        self.assertEqual(connection.execute("SELECT count(*) FROM state WHERE kind = 'x'").fetchone()[0], 0)

    def test_no_cursor_or_authorizer_leaves_the_fence(self):
        """Every cursor the connection hands out is fenced; nothing replaces the fence's authorizer."""
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        handed = {
            "cursor": connection.cursor(),
            "execute": connection.execute("SELECT 1"),
            "executemany": connection.executemany("DELETE FROM state WHERE id = ?", []),
            "executescript": connection.executescript("SELECT 1"),
        }
        for name, cursor in handed.items():
            with self.subTest(method=name):
                self.assertIsInstance(cursor, hub._FencedCursor)
        with self.assertRaises(SdDbError):
            connection.cursor(sqlite3.Cursor)
        for authorizer in (None, lambda *args: sqlite3.SQLITE_OK):
            with self.subTest(authorizer=authorizer), self.assertRaises(SdDbError):
                connection.set_authorizer(authorizer)

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
                "BEGIN; INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'd', '{}', '2026'); COMMIT;"),
        }
        for name, write in writes_.items():
            with self.subTest(path=name), self.assertRaises(hub.Fenced):
                write()
        self.assertEqual(self.rows(), 1, "only the write before the rename")

    def test_an_autocommit_batch_spanning_the_rename_persists_nothing(self):
        """Lead review of f349b44ce: SQLite authorizes `executemany` once, then commits each set."""
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', ?, '{}', '2026')"

        def sets():
            yield ("a",)
            self.node(OLD_HUB)
            yield ("b",)

        batches = {
            "connection": lambda connection: connection.executemany(insert, sets()),
            "cursor": lambda connection: connection.cursor().executemany(insert, sets()),
            # Lead review of 731a41b3f: the cursor each convenience method returns, reused.
            "execute's cursor": lambda connection: connection.execute("SELECT 1").executemany(insert, sets()),
            "executemany's cursor": lambda connection: connection.executemany(insert, []).executemany(insert, sets()),
            "executescript's cursor": lambda connection: connection.executescript("SELECT 1").executemany(
                insert, sets()),
        }
        for name, batch in batches.items():
            with self.subTest(wrapper=name):
                hub._answers.clear()
                self.node()
                self.name_hub(HUB_NAME)
                connection = self.open()
                with self.assertRaises(hub.Fenced):
                    batch(connection)
                self.assertFalse(connection.in_transaction)
                self.assertEqual(self.rows(), 0)

    def test_an_autocommit_batch_on_the_live_hub_writes_every_set(self):
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', ?, '{}', '2026')"
        connection.executemany(insert, [("a",), ("b",)])
        connection.cursor().executemany(insert, [("c",)])
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.rows(), 3)

    def test_a_batch_inside_a_transaction_commits_with_it(self):
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', ?, '{}', '2026')"
        connection.execute("BEGIN IMMEDIATE")
        connection.executemany(insert, [("a",), ("b",)])
        self.assertTrue(connection.in_transaction)
        connection.execute("ROLLBACK")
        self.assertEqual(self.rows(), 0)

    def test_a_script_write_outside_a_transaction_refuses(self):
        """sqlite3 commits an open transaction before a script, so nothing outside can hold its writes."""
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        script = "".join(f"INSERT INTO state (kind, key, body, timestamp) VALUES ('x', '{key}', '{{}}', '2026');"
                         for key in ("a", "b"))
        with self.assertRaises(SdDbError) as refused:
            connection.executescript(script)
        self.assertIn("BEGIN IMMEDIATE ... COMMIT inside the script", str(refused.exception))
        self.assertEqual(self.rows(), 0)
        connection.executescript(f"BEGIN IMMEDIATE; {script} COMMIT;")
        self.assertEqual(self.rows(), 2)

    def test_a_rename_between_prepare_and_commit_persists_nothing(self):
        """Lane review of 7953e175d: the role flips while the write runs, after its prepare asked."""
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', flip(), '{}', '2026')"
        writes_ = {
            "execute": lambda connection: connection.execute(insert),
            "cursor": lambda connection: connection.cursor().execute(insert),
            "executemany": lambda connection: connection.executemany(insert, [()]),
            "executescript": lambda connection: connection.executescript(f"BEGIN; {insert}; COMMIT;"),
        }

        def flip() -> str:
            self.node(OLD_HUB)
            return "flipped"

        for name, write in writes_.items():
            with self.subTest(path=name):
                hub._answers.clear()
                self.node()
                self.name_hub(HUB_NAME)
                connection = self.open()
                connection.create_function("flip", 0, flip)
                with self.assertRaises(hub.Fenced):
                    write(connection)
                self.assertFalse(connection.in_transaction)
                self.assertEqual(self.rows(), 0)

    def test_a_writable_blob_outside_a_transaction_refuses(self):
        """A blob write passes no authorizer and commits on each write, so it needs a transaction."""
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        connection.execute("INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'b', 'abcd', '2026')")
        row = connection.execute("SELECT max(id) FROM state").fetchone()[0]
        with self.assertRaises(SdDbError):
            connection.blobopen("state", "body", row)
        with connection.blobopen("state", "body", row, readonly=True) as blob:
            self.assertEqual(blob.read(), b"abcd")

    def test_a_blob_write_commits_only_after_a_fresh_ask(self):
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        connection.execute("INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'b', 'abcd', '2026')")
        row = connection.execute("SELECT max(id) FROM state").fetchone()[0]
        connection.execute("BEGIN IMMEDIATE")
        with connection.blobopen("state", "body", row) as blob:
            blob.write(b"wxyz")
        self.node(OLD_HUB)
        with self.assertRaises(hub.Fenced):
            connection.execute("COMMIT")
        reader = database.connect(write=False)
        self.addCleanup(reader.close)
        self.assertEqual(reader.execute("SELECT body FROM state WHERE id = ?", (row,)).fetchone()[0], "abcd")

    def test_a_failed_nested_begin_keeps_the_commit_asking(self):
        """Lead review of f716079a9: a BEGIN that SQLite refuses inside a transaction ends nothing."""
        endings = {
            "COMMIT": ("BEGIN IMMEDIATE", "COMMIT"),
            "outer RELEASE": ("SAVEPOINT outer", "RELEASE outer"),
        }
        for name, (opening, end) in endings.items():
            with self.subTest(end=name):
                hub._answers.clear()
                connection = self.begun(opening)
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("BEGIN")
                self.assertTrue(connection.in_transaction)
                with self.assertRaises(hub.Fenced):
                    connection.execute(end)
                self.assertFalse(connection.in_transaction)
                self.assertEqual(self.rows(), 0)

    def test_a_read_only_transaction_on_a_fenced_node_commits_with_no_probe(self):
        """Lead ruling on f716079a9: reads on an old hub keep working, and cost no probe."""
        self.node()
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        before = len(self.asked())
        reads = {
            "COMMIT": ("BEGIN", "COMMIT"),
            "outer RELEASE": ("SAVEPOINT outer", "RELEASE outer"),
        }
        for name, (opening, end) in reads.items():
            with self.subTest(end=name):
                connection.execute(opening)
                self.assertEqual(connection.execute("SELECT count(*) FROM item").fetchone()[0], 0)
                connection.execute(end)
                self.assertFalse(connection.in_transaction)
        with database.transaction(connection):
            connection.execute("SELECT count(*) FROM state").fetchone()
        self.assertEqual(len(self.asked()), before)

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


class TheAutocommitWindow(FenceCase):
    """Lane reviews of 0bff04f7d and 7953e175d: no write commits where the authorizer cannot see it.

    A write outside a transaction runs inside BEGIN IMMEDIATE ... COMMIT, so
    it has committed when its call returns, through a COMMIT that asked.
    """

    def test_an_autocommit_write_has_committed_when_its_call_returns(self):
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        reader = database.connect(write=False)
        self.addCleanup(reader.close)
        insert = "INSERT INTO state (kind, key, body, timestamp) VALUES ('x', ?, '{}', '2026')"
        writes_ = {
            "execute": lambda: connection.execute(insert, ("a",)),
            "cursor": lambda: connection.cursor().execute(insert, ("b",)),
            "executemany": lambda: connection.executemany(insert, [("c",), ("d",)]),
            "executescript": lambda: connection.executescript(
                "BEGIN; INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'e', '{}', '2026'); COMMIT;"),
        }
        seen = 0
        for name, write in writes_.items():
            with self.subTest(path=name):
                write()
                count = reader.execute("SELECT count(*) FROM state WHERE kind = 'x'").fetchone()[0]
                self.assertGreater(count, seen, "committed before the call returned")
                seen = count

    def test_an_autocommit_returning_write_fails_closed(self):
        """A RETURNING write holds its statement open, so its wrapping COMMIT cannot run: nothing persists."""
        self.node()
        self.name_hub(HUB_NAME)
        connection = self.open()
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("INSERT INTO state (kind, key, body, timestamp) VALUES ('x', 'r', '{}', '2026') "
                               "RETURNING id")
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.rows(), 0)

    def rows(self) -> int:
        reader = database.connect(write=False)
        try:
            return reader.execute("SELECT count(*) FROM state WHERE kind = 'x'").fetchone()[0]
        finally:
            reader.close()


class ThePragmaWrites(FenceCase):
    """pack sd:6328: a PRAGMA that changes the file is a write; one that reads or sets this connection is not.

    SQLite authorizes a pragma as SQLITE_PRAGMA, its value as `arg2`.
    """

    def header(self) -> tuple:
        reader = database.connect(write=False)
        try:
            return tuple(reader.execute(f"PRAGMA {name}").fetchone()[0]
                         for name in ("user_version", "application_id", "journal_mode"))
        finally:
            reader.close()

    def test_a_pragma_write_on_a_fenced_hub_refuses(self):
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        before = self.header()
        writes_ = ("PRAGMA user_version = 7", "PRAGMA main.application_id = 7", "pragma JOURNAL_MODE = delete",
                   "PRAGMA wal_checkpoint(TRUNCATE)", "PRAGMA wal_checkpoint", "PRAGMA incremental_vacuum")
        paths: dict[str, Callable[[], object]] = {
            statement: functools.partial(connection.execute, statement) for statement in writes_}
        paths["executescript"] = lambda: connection.executescript("PRAGMA user_version = 8;")
        paths["inside BEGIN"] = lambda: (connection.execute("BEGIN IMMEDIATE"),
                                         connection.execute("PRAGMA user_version = 9"))
        for name, write in paths.items():
            with self.subTest(path=name), self.assertRaises(hub.Fenced):
                write()
            self.assertFalse(connection.in_transaction)
        self.assertEqual(self.header(), before)

    def test_a_pragma_write_in_a_transaction_across_the_rename_rolls_back(self):
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA application_id = 7")
        self.node(OLD_HUB)
        self.later()
        with self.assertRaises(hub.Fenced):
            connection.execute("COMMIT")
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.header()[1], 0)

    def test_pragma_reads_and_connection_settings_stay_allowed_with_no_probe(self):
        self.name_hub(HUB_NAME)
        self.node(OLD_HUB)
        connection = self.open()
        before = len(self.asked())
        reads = ("PRAGMA user_version", "PRAGMA journal_mode", "PRAGMA table_info(item)", "PRAGMA index_list(item)",
                 "PRAGMA foreign_key_check(item)", "PRAGMA integrity_check(1)", "PRAGMA busy_timeout = 100",
                 "PRAGMA foreign_keys = ON", "PRAGMA temp.user_version = 3")
        for statement in reads:
            with self.subTest(statement=statement):
                connection.execute(statement).fetchall()
        self.assertEqual(len(self.asked()), before)

    def test_a_pragma_write_on_the_live_hub_runs_outside_a_transaction(self):
        """`journal_mode` and `wal_checkpoint` cannot run inside one, so the fence asks at prepare instead."""
        self.name_hub(HUB_NAME)
        self.node()
        connection = self.open()
        connection.execute("PRAGMA application_id = 7")
        self.assertEqual(connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0], "delete")
        self.assertEqual(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0], "wal")
        self.assertEqual(connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0], 0)
        self.assertFalse(connection.in_transaction)
        self.assertEqual(self.header()[1:], (7, "wal"))


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
