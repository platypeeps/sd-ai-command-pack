"""Watches (sd:6264): the company and product watches, the store's market rows, and the market-watch job that refreshes
them. Refresh all posts /api/jobs/market-watch/retry; Refresh and Add watch post /api/actions/run (watch.refresh,
watch.add)."""

from __future__ import annotations

from . import Api, Page


def _read(read):
    from ... import watches_screen

    return watches_screen.document(read.connection, now=read.now, jobs=read.jobs)


PAGE = Page(
    section="Watches",
    routes=("/watches",),
    html="watches.html",
    item="sd:6264",
    api=(Api("/api/watches", _read),),
)
