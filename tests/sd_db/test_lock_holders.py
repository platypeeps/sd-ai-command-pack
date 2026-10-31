"""Pack sd:6948. A write a held lock refuses past its retries names the processes that hold the file."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest import mock

from sd_db import database
from sd_db.database import Patient, connect, transaction
from sd_db.migrate import initialise

#: A writer that opens a write transaction, says so, and holds it until its stdin closes.
HOLDER = """
import sqlite3, sys
connection = sqlite3.connect(sys.argv[1], isolation_level=None)
connection.execute("BEGIN IMMEDIATE")
print("held", flush=True)
sys.stdin.read()
"""


class LockHolders(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "sd.db"
        initialise(self.path)
        self.holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(self.path)], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, text=True)
        assert self.holder.stdin is not None and self.holder.stdout is not None
        self.addCleanup(self.holder.wait, 10)
        self.addCleanup(self.holder.stdin.close)
        self.assertEqual(self.holder.stdout.readline().strip(), "held")
        self.connection = connect(self.path, busy_timeout=10)
        self.addCleanup(self.connection.close)

    def test_a_write_past_its_retries_names_the_holder(self):
        with mock.patch.object(database, "LOCK_WAITS", (0.01,)), \
                self.assertRaises(database.sqlite3.OperationalError) as caught:
            Patient(self.connection).execute("CREATE TABLE fixture (x)")
        self.assertIn("database is locked", str(caught.exception))
        self.assertIn(f"holders (pid, elapsed, command): {self.holder.pid} ", str(caught.exception))

    def test_a_transaction_the_lock_refuses_names_the_holder(self):
        with self.assertRaises(database.sqlite3.OperationalError) as caught, transaction(self.connection):
            pass
        self.assertIn(f"{self.holder.pid} ", str(caught.exception))
        self.assertEqual(str(caught.exception).count("holders"), 1)
        self.assertEqual(caught.exception.sqlite_errorname, "SQLITE_BUSY", "the code survives the report")

    def test_a_patient_transaction_names_the_holder_once(self):
        with mock.patch.object(database, "LOCK_WAITS", (0.01,)), \
                self.assertRaises(database.sqlite3.OperationalError) as caught, \
                transaction(cast(Any, Patient(self.connection))):
            pass
        self.assertEqual(str(caught.exception).count("holders"), 1)


if __name__ == "__main__":
    unittest.main()
