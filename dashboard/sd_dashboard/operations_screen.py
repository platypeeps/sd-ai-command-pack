"""Operations: the classic areas whose data no v2 page shows yet, and the helpers other screens import.

Resources keeps Toolbox, Vault and Queues, and Trackers keeps the tracker issues. The Jobs, Ports, Progress, Reports,
Repos and Commands areas were retired in sd:3402, once Management, Health, Metrics, Reports and Activity carried
their controls; an address naming one is a 404. Services and Sessions moved to Management in pack sd:7517 and Usage to
Metrics in pack sd:7524 (`MOVED`): an address naming one answers 301 to the view that holds it. Every area draws
inside the v2 shell (sd:3586), under Fleet's Operations rail section, as one of its views (pack sd:7266):
`/ui/operations.js` declares them, and the server draws only the area `?area=` names.
"""

import re
import signal

from sd_db import operations

from .controls import form
from .markup import join, tag
from .pages import shell_page

AREAS = (("resources", "Resources"), ("trackers", "Trackers"))
#: The retired areas and the view that holds each now (pack sd:7517); `server` answers 301 there (`moved_to`) and
#: `/ui/operations.js` sends an old `#view=` address there too.
MOVED = {"services": "/management#view=deploys", "sessions": "/management#view=sessions", "usage": "/metrics#view=spend"}
#: Resources' views that moved to a page of their own (pack sd:7527): `?area=resources&resource=<view>` answers 301 there.
MOVED_RESOURCES = {"toolbox": "/management#view=machine"}
#: Each area's Details note.
NOTES = {
    "resources": "Resources shows what the local collectors read: Toolbox, Vault, Research and Queues.",
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


def moved_to(parameters):
    """The address a retired area's bookmark answers 301 to, or None for an area still here.

    Usage's month rides along when it is one (pack sd:7524): Metrics reads `?month=YYYY-MM`.
    """
    area = (parameters.get("area") or [""])[0]
    if area == "resources":
        return MOVED_RESOURCES.get((parameters.get("resource") or [""])[0])
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
    if area == "resources":
        from .reports_screen import resources

        content = resources(parameters)
    else:
        from .trackers_screen import trackers_panel

        content = trackers_panel(connection, parameters, now=now)
    return shell_page("Operations", "Operations", _views(area, content), subtitle=_subtitle(), screen="operations",
                      note=NOTES[area], script="operations.js")


def _subtitle():
    """The areas, from `AREAS`, so the summary names every view the rail lists."""
    words = [label.lower() for _, label in AREAS]
    words[0] = words[0].capitalize()
    return ", ".join(words[:-1]) + " and " + words[-1]
