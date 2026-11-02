"""Metrics (sd:2119): spend against budget, the week, providers, the month's usage and age in status, from
the reads the classic Usage area and the retired Progress area make. Its Cap and Configure post the routes the classic
Usage area's forms post (sd:3387). That area stays in the palette: its month picker reads any past month; this page
reads the current month, and with `?range=6mo` the last six months by bill (pack sd:7208)."""

from __future__ import annotations

from . import Api, Page


def _read(read):
    from ... import metrics_screen

    asked = read.parameters
    span = asked.get("range", ["7d"])
    if set(asked) - {"range"} or len(span) != 1 or span[0] not in metrics_screen.RANGES:
        return 400, {"error": f"Metrics takes one query parameter, range: {' or '.join(metrics_screen.RANGES)}."}
    return metrics_screen.document(read.connection, now=read.now, kept=read.metrics, span=span[0])


PAGE = Page(
    section="Metrics",
    routes=("/metrics",),
    html="metrics.html",
    item="sd:2119",
    api=(Api("/api/metrics", _read, query=True),),
    count="/api/metrics",
    classic={"Usage (classic)": "/operations?area=usage"},
)
