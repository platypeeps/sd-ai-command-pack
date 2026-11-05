"""`/api/usage`: the month as `sd usage --json` prints it, as the same bytes.

Requirement 6 says the four numbers, the item screen and `sd usage` cannot disagree, so this serves
`usage.json_text` of `usage.read`, the read `sd usage` prints, and nothing it computes itself. The one difference is
the sweep: the dashboard's GET connection is read-only (`sd_db.connect` with `write=False`: `mode=ro`, `query_only`),
so the API shows the read as it stands, a dead owner's `reserved` or `sending` row still held until the next
reservation or `sd usage` sweeps it, after which the two are the same bytes. The Usage area that drew this month
moved to Metrics' Spend view in pack sd:7524.
"""

from __future__ import annotations

import sqlite3

from sd_db import usage

__all__ = ["document"]


def document(connection: sqlite3.Connection, *, now: str, month: str | None) -> str:
    """`/api/usage`: the read as `sd usage --json` prints it, without the verb's sweep (the module docstring)."""
    return usage.json_text(usage.read(connection, month=month, now=now))
