"""Queue (sd:2585): each repository's ship lane, one row per item as merging, next, building, blocked, cancelled or
landed, read by `queue_screen`. Up, down, top, hold, release and cancel, a blocked row's retry and approve, a cancelled
row's Re-queue and a running row's Release post /api/queue/move, which runs `sd-ship lane move|hold|release|cancel|retry` and nothing else.
The Builds panel (pack sd:6095) reads /api/queue/builds (`builds.panel`); a blocked run's Retry posts
/api/queue/builds/retry, and a running build's Cancel posts the assignment cancel route that exists."""

from __future__ import annotations

from . import Api, Page


def _read(read):
    from ... import queue_screen

    return queue_screen.document(read.connection, now=read.now)


def _builds(read):
    from ... import builds

    return builds.panel(read.connection, now=read.now)


def _retry(payload, principal):
    from ... import builds

    if (set(payload) != {"assignment", "revision"} or type(payload["assignment"]) is not int
            or not 1 <= payload["assignment"] <= 9223372036854775807 or not isinstance(payload["revision"], str)):
        raise ValueError("Retry takes the lead assignment and the revision the panel read.")

    def write(connection):
        out = builds.retry(connection, payload["assignment"], expected_revision=payload["revision"], who="dashboard")
        return {**out, "kickstart": builds.kickstart()}

    return write


def _move(payload, principal):
    from ... import queue_screen

    return queue_screen.move(payload)


PAGE = Page(
    section="Queue",
    routes=("/queue",),
    html="queue.html",
    item="sd:2585",
    api=(Api("/api/queue", _read), Api("/api/queue/move", write=_move), Api("/api/queue/builds", _builds),
         Api("/api/queue/builds/retry", write=_retry)),
    # No rail badge (sd:5921): a blocked entry is a broken row of Today's Needs you, which counts it there.
)
