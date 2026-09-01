"""The write path: every mutation is a named command, and the list is closed.

**`RUN_ALLOWLIST` is the whole security model of writing.** The server does not
take a command from the page, build one from a parameter, or interpolate
anything a caller sends into one. A POST names an **id**; it resolves to an
argv written down here or declared in a registered manifest; an id that
resolves to nothing is a 404. There is no path from request text to a shell --
`bounded_run` takes a list and never a string, and nothing here joins one.

**A plugin may declare actions, and that is the point of the mechanism**
(R11-D21, which has the reasoning). A manifest names actions beside its tile,
the backbone renders the control, and the command stays in the plugin's own
repository with the data it writes.

**Declared is not the same as trusted, and the ids say so.** A plugin's action
id is namespaced with its prefix, exactly as its rows and tabs are, so it
cannot claim `index` or shadow another plugin's id. The argv runs with the
plugin's root as its working directory -- the same treatment its tile gets,
because it is the same trust boundary and not a wider one.

**What is NOT here, deliberately: no GET has a side effect.** The dashboard
this replaces started a rebuild on `GET /api/state?refresh=1` behind the Host
check alone while its POST twin required the token
(`local-project-dashboard/dashboard.py:1714` against `:1788` in
`platypeeps/system`, as that file stood at its last commit before
platypeeps/system#190 deleted it at 6b-9 -- a citation into that repository's
history, not into any working tree; nothing on disk answers to the path any
more). `tests/test_dashboard_actions.py` pins that this does not inherit the
habit, which outlives the file it was learned from.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .plugins import Bounded, bounded_run

# Long enough for a collect that talks to GitHub and Jira, short enough that a
# wedged command is a failed button rather than a held thread.
ACTION_SECONDS = 300.0
ACTION_BYTES = 64 * 1024

# Resolved from this file, not looked up on `PATH`, for the same reason
# `plugins.SD` is: the server may be a LaunchAgent whose `PATH` is launchd's,
# and a button that works in a terminal and 502s under the agent is the
# failure this constant exists to make impossible. Found by pressing it.
SD_DASHBOARD = Path(__file__).resolve().parent.parent / "bin" / "sd-dashboard"

# The backbone's own. One entry, and it is the one the Issues and PRs tabs
# already ask for by printing how stale they are.
RUN_ALLOWLIST: dict[str, dict] = {
    "index": {
        "label": "collect issues and pull requests",
        "argv": [str(SD_DASHBOARD), "index"],
        "cwd": None,
    },
}


def declared(entries: list[dict]) -> dict[str, dict]:
    """Actions from registered manifests, namespaced by their plugin's prefix.

    A manifest that declares nothing contributes nothing; a declaration that
    will not parse is dropped rather than refused, because an unrunnable
    button is a smaller failure than a loader that stops serving tabs over it.
    """
    out: dict[str, dict] = {}
    for entry in entries:
        prefix, root = entry.get("prefix"), entry.get("root")
        if not isinstance(prefix, str) or not isinstance(root, str) or not root:
            continue
        for action in entry.get("actions") or []:
            if not isinstance(action, dict):
                continue
            name, label, run = action.get("id"), action.get("label"), action.get("run")
            if not isinstance(name, str) or not isinstance(run, str):
                continue
            try:
                argv = shlex.split(run)
            except ValueError:
                continue
            if not argv:
                continue
            # Namespaced like every other thing a plugin contributes, so a
            # plugin cannot claim `index` or shadow another plugin's id.
            out[f"{prefix}/{name}"] = {
                "label": str(label or name),
                "argv": argv,
                "cwd": root,
            }
    return out


def resolve(entries: list[dict]) -> dict[str, dict]:
    """Every action that exists right now: the backbone's, then the plugins'."""
    return {**RUN_ALLOWLIST, **declared(entries)}


def catalog(entries: list[dict]) -> list[dict]:
    """What the page may offer: id and label only, never the argv.

    The command is not sent to the browser. Nothing there needs it, and a page
    that has never seen an argv cannot be talked into echoing a different one
    back.

    Declaration order, not sorted: R11-D23 chose a list over an object keyed
    by id to keep it. Found in review, against this repository's own record.
    """
    return [{"id": name, "label": spec["label"]}
            for name, spec in resolve(entries).items()]


def run(action_id: object, entries: list[dict]) -> tuple[dict, int]:
    """Run one allow-listed action. `(body, status)`.

    Resolved, never constructed: an unknown id is a 404, not an attempt.
    """
    if not isinstance(action_id, str) or not action_id:
        return {"ok": False, "error": "no action named"}, 400
    spec = resolve(entries).get(action_id)
    if spec is None:
        return {"ok": False, "error": f"no such action: {action_id}"}, 404
    try:
        out = bounded_run(
            spec["argv"],
            cwd=Path(spec["cwd"]) if spec["cwd"] else None,
            seconds=ACTION_SECONDS,
            limit=ACTION_BYTES,
        )
    except Bounded as error:
        # The operator pressed a button and something did not happen. Saying
        # which is the difference between a dashboard and a light switch with
        # no bulb behind it.
        return {"ok": False, "error": str(error), "id": action_id}, 502
    text = out.decode("utf-8", "replace").strip()
    return {"ok": True, "id": action_id, "output": text[-2000:]}, 200
