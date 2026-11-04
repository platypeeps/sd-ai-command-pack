"""Operations: the classic areas whose data no v2 page shows yet, and the helpers other screens import.

Trackers keeps the tracker issues. The Jobs, Ports, Progress, Reports,
Repos and Commands areas were retired in sd:3402, once Management, Health, Metrics, Reports and Activity carried
their controls; an address naming one is a 404. Services and Sessions moved to Management in pack sd:7517 and Usage to
Metrics in pack sd:7524, and Resources' four views to Management, Notes and Tasks in pack sd:7527 (`MOVED`,
`MOVED_RESOURCES`): an address naming one answers 301 to the view that holds it. Every area draws
inside the v2 shell (sd:3586), under Fleet's Operations rail section, as one of its views (pack sd:7266):
`/ui/operations.js` declares them, and the server draws only the area `?area=` names.
"""

import contextlib
import re
import signal

from sd_db import operations

from .controls import form
from .markup import join, tag
from .pages import shell_page

AREAS = (("trackers", "Trackers"),)
#: The retired areas and the view that holds each now (pack sd:7517); `server` answers 301 there (`moved_to`) and
#: `/ui/operations.js` sends an old `#view=` address there too.
MOVED = {"services": "/management#view=deploys", "sessions": "/management#view=sessions", "usage": "/metrics#view=spend",
         "resources": "/management#view=machine"}
#: Resources' views and the page that holds each now (pack sd:7527): `?area=resources&resource=<view>` answers 301
#: there, and a bare or unknown one to Toolbox's, the view Resources opened on.
MOVED_RESOURCES = {"toolbox": "/management#view=machine", "research": "/management?research=yes#view=repos",
                   "vault": "/notes", "queues": "/tasks?queues=open"}
#: Each area's Details note.
NOTES = {
    "trackers": "Trackers lists the open pull requests and issues that sd shadow sync last saw.",
}


def _views(area, content):
    """One `view-<key>` panel per area, the shell's views (pack sd:7266); only `area`'s holds its content.

    The shell shows one panel and hides the rest; `/ui/operations.js` loads the address of a view that is not drawn.
    """
    return join(tag("div", content if key == area else tag("p", f"Opening {label}…", class_="hint"),
                    id=f"view-{key}", hidden=key != area) for key, label in AREAS)


def assignment_cancel(connection, identity: int):
    """`sd assignments cancel` as a form, where `operations.cancel_assignment` takes it; else nothing.

    The runner's cancel went with the runner (sd:3041); this one ends a queued row with no process to stop.
    """
    state = operations.assignment_state(connection, identity)
    if not state["capabilities"]["cancel"]["allowed"]:
        return ""
    return form(f"/api/assignments/{identity}/cancel", label="Cancel assignment",
                command=f"sd assignments cancel {identity}", revision=state["revision"], compact=True)


def _signal_name(number):
    """`SIGTERM (15)` when Python knows the number, the bare number otherwise."""
    try:
        return f"{signal.Signals(number).name} ({number})"
    except ValueError:
        return str(number)


@contextlib.contextmanager
def _one_snapshot(connection):
    """One deferred read transaction around a page's reads, so they compare one snapshot of the store.

    Tasks, Places, HOA and Reports read through it. Deferred: the connection is read-only and `isolation_level=None`,
    and WAL keeps a reader's snapshot from its first read to its COMMIT. Inside a caller's transaction it adds none.
    """
    if connection.in_transaction:
        yield
        return
    connection.execute("BEGIN")
    try:
        yield
    finally:
        connection.execute("COMMIT")


def moved_to(parameters):
    """The address a retired area's bookmark answers 301 to, or None for an area still here.

    Usage's month rides along when it is one (pack sd:7524): Metrics reads `?month=YYYY-MM`.
    """
    area = (parameters.get("area") or [""])[0]
    if area == "resources":
        return MOVED_RESOURCES.get((parameters.get("resource") or [""])[0], MOVED["resources"])
    target = MOVED.get(area)
    month = (parameters.get("month") or [""])[0]
    if target and area == "usage" and re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        return target.replace("#", f"?month={month}#")
    return target


def operations_page(connection, *, parameters, now):
    """The area `?area=` names, the first by default; None for an area that is not one, so the server answers 404."""
    area = (parameters.get("area") or [AREAS[0][0]])[0]
    if area not in dict(AREAS):
        return None
    from .trackers_screen import trackers_panel

    content = trackers_panel(connection, parameters, now=now)
    return shell_page("Operations", "Operations", _views(area, content), subtitle=_subtitle(), screen="operations",
                      note=NOTES[area], script="operations.js")


def _subtitle():
    """The areas, from `AREAS`, so the summary names every view the rail lists."""
    words = [label.lower() for _, label in AREAS]
    words[0] = words[0].capitalize()
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]
