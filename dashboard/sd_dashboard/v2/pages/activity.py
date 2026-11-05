"""Activity (sd:2111): the 24-hour timeline, from the records the library already keeps. `?range=7d` reads 7 days,
for Today's Timeline (pack sd:7681)."""

from __future__ import annotations

from . import Api, Page


def _read(read):
    from ... import activity_screen

    asked = read.parameters
    span = asked.get("range", ["24h"])
    if set(asked) - {"range"} or len(span) != 1 or span[0] not in activity_screen.RANGES:
        return 400, {"error": f"Activity takes a range, {' or '.join(activity_screen.RANGES)}."}
    return activity_screen.document(read.connection, now=read.now, jobs_backend=read.jobs,
                                    window=activity_screen.RANGES[span[0]])


PAGE = Page(
    section="Activity",
    routes=("/activity",),
    html="activity.html",
    item="sd:2111",
    api=(Api("/api/activity", _read, query=True),),
    count="/api/activity",
)
