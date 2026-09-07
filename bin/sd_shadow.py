"""`sd shadow sync` — the verb over the collector the library already ships.

`sd_db.shadow_sync`'s own docstring settles the split in as many words: "This
module is the collector, not the command. `sd shadow sync` is a verb and verbs
live in the pack." So nothing here collects. It opens the connection, calls
`sd_db.sync_shadow`, and turns the `Synced` it gets back into a line an
operator can act on.

The one thing worth stating twice is the order the collector guarantees and
this verb must not obscure: rows are written whether or not the collect
succeeded, because a partial answer is still true, and the watermark moves only
on the collect's own success. A run that reports "wrote 4, cursor held" is
therefore not a contradiction -- it is the design -- and the report says both
numbers rather than one summary word that would have to pick.

Nothing here closes anything. `sync` calls `collect`, `store` and
`write_watermark` and no fourth thing, which is why criterion 28's "the fixture
saw no close call" is a fact about the library rather than a rule this verb has
to keep.
"""

from __future__ import annotations


def _rows():
    """`bin/sd_handoff_rows.py`, which owns the library frame and its refusal."""
    import sd_handoff_rows  # noqa: PLC0415 - deferred, as the module docstring says

    return sd_handoff_rows


def shadow_sync(args) -> int:
    """Run one sync and report what moved. Writes rows; never closes anything."""
    rows = _rows()
    sd_db = rows.library()
    connection = rows.connect(sd_db, write=True)
    try:
        result = sd_db.sync_shadow(connection)
    finally:
        connection.close()

    print(f"wrote {result.written} shadow row(s)")
    if result.truncated:
        # Named, because a truncated page means the next run starts from the
        # same watermark and there is more behind it than this run saw.
        print("the tracker returned a truncated page; run again to reach the rest")
    if result.ok:
        print(f"cursor moved to cover from {result.window_start}")
        return 0
    # The rows above are still written and still true. Only the cursor held,
    # so the next run re-reads the same window rather than skipping it.
    print(f"cursor held: {result.reason or 'the collect did not succeed'}")
    return 1 if args.strict else 0
