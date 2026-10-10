"""Seed the row that owns a work item's status (sd:3015).

Every status is the row's, so a test whose subject reads a status writes the
row, in a database under a scratch `HOME`; the operator's is never opened.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_db  # noqa: E402 - `make setup` provisions it
import sd_lib  # noqa: E402


def seed_row(home: pathlib.Path, repo: pathlib.Path, item: pathlib.Path, status: str,
             *, branch: str | None = None) -> None:
    """The row for `item` under `repo`, in the database at `home`."""
    repo = repo.resolve()
    item = item.resolve()
    if not sd_db.default_path(home).exists():
        sd_db.initialise(home=home)
    connection = sd_db.connect(home=home)
    try:
        sd_db.upsert_repo(connection, str(repo), managed=1)
        sd_db.upsert_item(
            connection, source=sd_lib.ITEM_ROW_SOURCE,
            external_id=sd_lib.external_id(repo, item),
            kind="work", title=item.name, status=status, who="test",
            repo=str(repo), branch=branch,
        )
    finally:
        connection.close()

