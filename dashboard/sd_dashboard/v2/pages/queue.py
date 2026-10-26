"""Queue (sd:2585): each repository's ship lane, one row per item as merging, next, building, blocked, cancelled or
landed, read by `queue_screen`. Up, down, top, hold, release and cancel, a blocked row's retry and approve, a cancelled
row's Re-queue and a running row's Release post /api/queue/move, which runs `sd-ship lane move|hold|release|cancel|retry` and nothing else.
The Builds panel (pack sd:6095) reads /api/queue/builds (`builds.panel`); a blocked or cancelled run's Retry posts
/api/queue/builds/retry, and its Send to builder posts the same route with a `finding` (pack sd:6020); a running
build's Cancel posts the assignment cancel route that exists."""

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

    finding = payload.get("finding", "")
    if (set(payload) - {"finding"} != {"assignment", "revision"} or type(payload["assignment"]) is not int
            or not 1 <= payload["assignment"] <= 9223372036854775807 or not isinstance(payload["revision"], str)):
        raise ValueError("Retry takes the lead assignment and the revision the panel read.")
    if "finding" in payload and (not isinstance(finding, str) or not finding.strip()
                                 or len(finding) > builds.FINDING_MAX):
        raise ValueError(f"Send to builder takes a finding of 1 to {builds.FINDING_MAX} characters.")

    def write(connection):
        out = builds.retry(connection, payload["assignment"], expected_revision=payload["revision"], who="dashboard",
                           finding=finding.strip())
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
