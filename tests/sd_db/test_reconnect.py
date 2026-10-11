"""sd:3336. A session dropped while it held nothing is opened again for the next unit.

`sd-ship prepare` holds one hub session across its review and gate, 15 to
40 minutes in which it sends nothing. The hub keeps an idle session outside a
transaction open for as long as the socket lives (`serve.Session.handle`), so
the drops a satellite saw came from below it: a hub restart after an install,
or the transport. The first call after the gate then failed `hub_unavailable`,
and the review it was recording was lost.

`IdleDrop` stands in for that hub: a relay in front of a real server that
closes both sides of any session silent for `idle` seconds. Each case counts
rows on the hub's file, so a call repeated where it must not be shows as a
second row.
"""

from __future__ import annotations

import socket
import sqlite3
import threading
import time

from sd_db import remote, ship
from sd_db.database import transaction

from .test_outcome import OutcomeCase, count

#: How long the double lets a session sit silent, and how long a test waits past it.
IDLE = 0.2
PAST_IDLE = 0.6


class IdleDrop:
    """A relay that closes any session silent for `idle` seconds, as a restarted hub does.

    `refusing` closes each new session at once: a hub that is still down.
    `dropped` counts the sessions it closed.
    """

    def __init__(self, port: int, idle: float = IDLE) -> None:
        self.target = port
        self.idle = idle
        self.refusing = False
        self.dropped = 0
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.sockets: list[socket.socket] = [self.listener]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            if self.refusing:
                client.close()
                continue
            self.sockets.append(client)
            threading.Thread(target=self._pump, args=(client,), daemon=True).start()

    def _pump(self, client: socket.socket) -> None:
        hub = socket.create_connection(("127.0.0.1", self.target))
        self.sockets.append(hub)
        try:
            while True:
                client.settimeout(self.idle)
                try:
                    frame = remote.read_frame(client)
                except TimeoutError:
                    self.dropped += 1
                    return
                client.settimeout(None)
                remote.send_frame(hub, frame)
                remote.send_frame(client, remote.read_frame(hub))
        except (OSError, EOFError):
            pass
        finally:
            client.close()
            hub.close()

    def stop(self) -> None:
        for each in self.sockets:
            try:
                each.close()
            except OSError:
                pass


class ADroppedIdleSession(OutcomeCase):
    def through_drop(self, **options) -> tuple[IdleDrop, remote.Connection]:
        relay = IdleDrop(self.hub.port)
        self.addCleanup(relay.stop)
        client = self.connect(relay.port, **options)
        return relay, client

    def idle_past(self, relay: IdleDrop) -> None:
        time.sleep(PAST_IDLE)
        self.assertGreaterEqual(relay.dropped, 1, "the double did not drop the idle session")

    def test_the_receipt_save_after_the_gate_lands_on_a_fresh_session(self):
        """The call `record_review` makes after the gate: `ship.save`, a compare-and-set. One row."""
        relay, client = self.through_drop()
        revision = ship.save(client, "ship:example", 0, {"phase": "reviewing"})
        self.idle_past(relay)
        later = ship.save(client, "ship:example", revision, {"phase": "reviewed"})
        self.assertGreater(later, revision)
        self.assertEqual(ship.read(client, "ship:example"), (later, {"phase": "reviewed", "protocol": 1}))
        self.assertEqual(count(self.path, "state"), 2)

    def test_a_write_transaction_opened_after_a_drop_commits_once(self):
        relay, client = self.through_drop()
        self.idle_past(relay)
        with transaction(client):
            client.execute("INSERT INTO probe (name) VALUES ('a')")
        self.assertEqual(count(self.path), 1)

    def test_a_read_after_a_drop_answers(self):
        relay, client = self.through_drop(write=False)
        self.idle_past(relay)
        self.assertEqual(client.execute("SELECT count(*) FROM probe").fetchone()[0], 0)
        self.assertEqual(client.execute("PRAGMA query_only").fetchone()[0], 1,
                         "the new session must open as the old one did")

    def test_a_trace_callback_survives_the_new_session(self):
        relay, client = self.through_drop()
        seen: list[str] = []
        client.set_trace_callback(seen.append)
        self.idle_past(relay)
        client.execute("SELECT 1").fetchone()
        self.assertIn("SELECT 1", seen)

    def test_a_write_outside_a_transaction_is_not_repeated(self):
        """An autocommit write is settled by asking the hub for its id, never sent again."""
        relay, client = self.through_drop()
        self.idle_past(relay)
        with self.assertRaises(remote.TransactionLost):
            client.execute("INSERT INTO probe (name) VALUES ('a')")
        self.assertEqual(count(self.path), 0)

    def test_a_statement_inside_a_transaction_is_not_repeated(self):
        """A drop inside a transaction rolled it back on the hub; the rest of it must not land alone."""
        relay, client = self.through_drop()
        with self.assertRaises(remote.HubUnreachable):
            with transaction(client):
                client.execute("INSERT INTO probe (name) VALUES ('a')")
                self.idle_past(relay)
                client.execute("INSERT INTO probe (name) VALUES ('b')")
        self.assertEqual(count(self.path), 0)
        self.assertFalse(client.in_transaction)

    def test_a_hub_still_down_fails_by_name(self):
        relay, client = self.through_drop()
        self.idle_past(relay)
        relay.refusing = True
        with self.assertRaises(remote.HubUnreachable):
            client.execute("SELECT 1")
        self.assertEqual(count(self.path), 0)

    def test_a_closed_connection_is_not_reopened(self):
        """`close` is the caller's word; only a drop opens a new session."""
        relay, client = self.through_drop()
        client.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            client.execute("SELECT 1")


if __name__ == "__main__":
    import unittest

    unittest.main()
