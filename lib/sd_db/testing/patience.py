"""How long a test waits on wall-clock time, given the machine's load (sd:6158).

A test that waits a fixed number of seconds -- an HTTP timeout, a settle
deadline, a join, a double's idle window -- passes on a quiet machine and fails
under a gate that shares the CPUs with two other gates: at load 49 to 99 on 16
cores the dashboard tests failed on waits of 0.2 to 5 seconds, and each passed
by hand. The budget is a test's own choice; this scales it, once, for every
caller, by how many runnable processes each core holds now.
"""

from __future__ import annotations

import os

#: The most a budget grows. Load 99 on 16 cores is about 6; a wait that needs
#: more than this is a hang, and a failing test should still end.
MOST = 8.0


def factor() -> float:
    """The one-minute load per core, at least 1 and at most `MOST`.

    A load that cannot be read is not a quiet machine: it gives `MOST`, so the
    wait errs long. Only a failing test, or a timed sleep, pays for it.
    """

    try:
        load = os.getloadavg()[0]
    except OSError:
        return MOST
    return min(MOST, max(1.0, load / (os.cpu_count() or 1)))


def patience(seconds: float) -> float:
    """`seconds` scaled by `factor()`, read at the call: the load moves during a run."""

    return seconds * factor()
