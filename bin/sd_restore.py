"""`sd restore` — what a restored database owes before it may be used again.

A restored database is a record, not a permission. The snapshot is a moment
in the past: work was dispatched after it, money was spent after it, and a
process that simply picked the rows up would dispatch that work twice and
spend against a cap that has already been paid. So the restore lands as an
unresolved `restore` row, and while it is unresolved the runner dispatches
nothing and the palette runs nothing, with Today saying so first.

Two verbs clear it:

* **`sd restore reimport <repository>`** — for a repository whose source
  authority the snapshot cannot prove. A repository migrates its statuses
  from files to rows in a sitting, and the sitting writes a `verified` row
  recording the hash it found equal before it snapshots. A nightly snapshot
  taken *before* that sitting holds rehearsal rows, and the checkout's marker
  proves only that the checkout migrated, not that this snapshot holds its
  data. Such a repository stays `retiring`, every writer refuses, and
  `reimport` is what puts it right.
* **`sd restore resume`** — the operator's word that the reconciliation is
  done. It names what was blocked and what was frozen, resolves the row, and
  dispatch resumes.

`sd_db` is imported inside the handlers, not at module import. The library
reaches this virtualenv through the pack's installer, which is item A's
criterion 13 and lands after this; until then `sd` must keep working for
every other verb and refuse this one with the reason.
"""

from __future__ import annotations

import argparse

#: Why the two verbs cannot run yet, when they cannot.
NOT_INSTALLED = (
    "sd_db is not installed in this virtualenv. `sd restore` reads the "
    "database directly; install the library with the pack's installer "
    "(`sd-install`), which provisions it from the `system` checkout at its "
    "tag, then run this again."
)

#: The two columns a repository's source authority is held in, and the word
#: each carries while its sitting is incomplete.
AUTHORITY = ("status_source", "pieces_source")
RETIRING = "retiring"


class RestoreRefusal(Exception):
    """Something the operator must settle before dispatch resumes."""


def _library():
    """Import `sd_db`, or refuse with the remedy rather than a traceback."""
    try:
        # Not resolvable at type-check time by design: `sd_db` is installed
        # into this virtualenv by the pack's installer, from the `system`
        # checkout at its tag, and this repository does not vendor it. The
        # ImportError below is the supported state, not an edge case.
        import sd_db  # type: ignore[import-not-found]
    except ImportError:
        raise RestoreRefusal(NOT_INSTALLED) from None
    return sd_db


def _open(sd_db):
    try:
        return sd_db.connect()
    except FileNotFoundError as error:
        raise RestoreRefusal(str(error)) from None


def open_restore(sd_db, connection):
    """The unresolved `restore` row, or a refusal saying there is none."""
    rows = sd_db.unresolved_state(connection, "restore")
    if not rows:
        raise RestoreRefusal(
            "no unresolved restore. Nothing is held back, and there is "
            "nothing for this command to clear."
        )
    if len(rows) > 1:
        # Two restores with the first unreconciled means a snapshot was put
        # back on top of one that was never settled. Which is authoritative
        # is not this command's call.
        raise RestoreRefusal(
            f"{len(rows)} unresolved restores, from "
            + ", ".join(str(row["key"]) for row in rows)
            + ". Resolve them in order, oldest first, or restore once more "
            "from the snapshot you mean to keep."
        )
    return rows[0]


def unproven_repositories(connection, restore_row) -> list[tuple[str, str]]:
    """Repositories the snapshot cannot prove it holds the rows for.

    A repository is proven for a kind when the snapshot carries a `verified`
    row for that repository and kind written *before* the snapshot. Without
    one the column stays `retiring` and every writer refuses.
    """
    verified = {
        (row["key"] or "").split("\t", 1)[0]: row["timestamp"]
        for row in connection.execute(
            "SELECT key, timestamp FROM state WHERE kind = 'verified'"
        )
    }
    unproven = []
    for row in connection.execute("SELECT path, status_source, pieces_source FROM repo"):
        for column in AUTHORITY:
            if row[column] != RETIRING:
                continue
            marker = f"{row['path']}:{column}"
            if marker not in verified and row["path"] not in verified:
                unproven.append((row["path"], column))
    del restore_row
    return unproven


def frozen_bills(connection) -> list[str]:
    """Bills a cap or a plan freezes until this month's spend is entered.

    Frozen because the ledger under the snapshot predates it: the cap may
    already have been paid against, and a cap reopened by an old snapshot is
    a cap that does not hold.
    """
    return [
        row["name"]
        for row in connection.execute(
            "SELECT name, cost_basis, cap_usd_month FROM bill "
            "WHERE cap_usd_month IS NOT NULL OR cost_basis IN ('plan', 'prepaid') "
            "ORDER BY name"
        )
    ]


def blocked_assignments(connection) -> list[tuple[int, str]]:
    """What the restore stopped, so `resume` can name it rather than count it."""
    return [
        (row["id"], row["role"])
        for row in connection.execute(
            "SELECT id, role FROM assignment WHERE status = 'blocked' "
            "ORDER BY id"
        )
    ]


def reimport(args: argparse.Namespace) -> int:
    """Reconcile one repository's source authority against its checkout.

    This is the verb group item C's own pull request builds the
    piece-specific half of. What lands here is the shape and the refusals:
    which repository, whether the snapshot can prove it, and what it means
    when it cannot. Importing a kind's lines from each row's `source_commit`
    belongs to the migration that wrote those rows, and arrives with it.
    """
    sd_db = _library()
    connection = _open(sd_db)
    try:
        restore_row = open_restore(sd_db, connection)
        row = connection.execute(
            "SELECT path, status_source, pieces_source FROM repo WHERE path = ?",
            (args.repository,),
        ).fetchone()
        if row is None:
            known = [entry["path"] for entry in connection.execute("SELECT path FROM repo")]
            raise RestoreRefusal(
                f"{args.repository} is not a registered repository. "
                + (f"Registered: {', '.join(known)}." if known else "None are registered.")
            )
        retiring = [column for column in AUTHORITY if row[column] == RETIRING]
        if not retiring:
            raise RestoreRefusal(
                f"{args.repository} is not awaiting a reimport: its "
                f"status_source is {row['status_source']!r} and its "
                f"pieces_source is {row['pieces_source']!r}. Nothing here is "
                f"held back by the restore of {restore_row['key']}."
            )
        print(
            f"sd: {args.repository} is {RETIRING} for "
            f"{', '.join(retiring)} after the restore of {restore_row['key']}."
        )
        print(
            "sd: the snapshot predates the sitting's verify, so its rows are "
            "rehearsal rows and every writer refuses."
        )
        print(
            "sd: reimporting a kind's lines from each row's source_commit is "
            "the migration's half and is not installed here yet; until it is, "
            "rerun the sitting for this repository."
        )
        return 1
    finally:
        connection.close()


def resume(args: argparse.Namespace) -> int:
    """Mark the restore reconciled. Names what was held before it does."""
    del args
    sd_db = _library()
    connection = _open(sd_db)
    try:
        restore_row = open_restore(sd_db, connection)
        unproven = unproven_repositories(connection, restore_row)
        if unproven:
            detail = ", ".join(f"{path} ({column})" for path, column in unproven)
            raise RestoreRefusal(
                f"{len(unproven)} repository authority/authorities are still "
                f"{RETIRING}: {detail}. Run `sd restore reimport <repository>` "
                f"for each, or rerun its sitting. Dispatch stays stopped until "
                f"they are settled."
            )

        blocked = blocked_assignments(connection)
        frozen = frozen_bills(connection)
        print(f"sd: restore of {restore_row['key']}, taken {restore_row['timestamp']}.")
        if blocked:
            print(f"sd: {len(blocked)} assignment(s) stay blocked and are not requeued:")
            for identifier, role in blocked:
                print(f"sd:   assignment {identifier} ({role})")
        else:
            print("sd: no assignment was blocked by the restore.")
        if frozen:
            print(
                "sd: these bills stay frozen until this month's spend is "
                "entered on the Providers screen: " + ", ".join(frozen)
            )
        sd_db.resolve_state(connection, restore_row["id"])
        print("sd: the restore is reconciled. Dispatch resumes.")
        return 0
    finally:
        connection.close()
