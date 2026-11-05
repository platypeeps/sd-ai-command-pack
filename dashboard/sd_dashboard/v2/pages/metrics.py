"""Metrics (sd:2119): spend against budget, the week, providers, the month's usage and age in status, from
the reads the retired Usage and Progress areas made. Its Cap and Configure post /api/bills/<bill>/cap and
/api/providers/configure (sd:3387). It reads the current month, `?month=YYYY-MM` any other, the picker Operations
Usage had (pack sd:7524), and with `?range=6mo` the last six months by bill (pack sd:7208)."""

from __future__ import annotations

import re

from . import Api, Page


def _read(read):
    from ... import metrics_screen

    asked = read.parameters
    span, month = asked.get("range", ["7d"]), asked.get("month", [None])
    if (set(asked) - {"range", "month"} or len(span) != 1 or span[0] not in metrics_screen.RANGES or len(month) != 1
            or (month[0] is not None and not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month[0]))):
        return 400, {"error": f"Metrics takes a range, {' or '.join(metrics_screen.RANGES)}, and a month, YYYY-MM."}
    return metrics_screen.document(read.connection, now=read.now, kept=read.metrics, span=span[0], month=month[0])


PAGE = Page(
    section="Metrics",
    routes=("/metrics",),
    html="metrics.html",
    item="sd:2119",
    api=(Api("/api/metrics", _read, query=True),),
    count="/api/metrics",
)
