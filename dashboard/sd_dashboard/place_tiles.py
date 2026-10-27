"""A realm place's Overview tiles (sd:6162, sd:6164): an app or a staging site, its link and the commands that run it.

The tiles name folders, hosts and commands on the operator's machines, and this repository is public, so they live in
the config folder, never in a request or a setting row the page writes: `<config>/project-dashboard/place-tiles.conf`
(`CONFIG`; `place-tiles.conf.example` is the template), one line each, as `documents.conf` does:

    tile|<realm>|<tile>|<label>|<folder>|<url or ->     a tile on the realm's Overview, in file order
    act|<tile>|<label>|<command>                        a button on that tile, in file order

`document` answers `GET /api/place/<realm>/overview`. Each tile says whether its folder is on this machine (`here`,
else `why`: an app that runs on another machine shows the tile and the reason, never a button that seems to work),
and probes its URL once, bounded by `PROBE_SECONDS`: any HTTP answer is `answers: true` with its status, a refused
connection `false`, anything else `null`, unknown. Each action carries its last run (`last`).

`run` answers `POST /api/place/tiles {realm, tile, action}`. It reads the file again and runs only a command a line
names, split by `shlex` with no shell, in the tile's folder, through `sweep.spawn`: one lock per action
(`<state>/<realm>/<tile>/<action>/lock`), so Stop runs while Start's server holds Start's lock, and a second Deploy
while one runs is a 409. The start is 202 at once; `WRAP` writes `exit` (`<code> <UTC time>`) when the command ends,
and `start.log` holds its output. A refused start (no such line, folder not here) is a 400 and runs nothing.

Last run, from those files: `running` while the lock is held; `done` with the exit code once `exit` is there (the
start clears it first, so an `exit` is always the newest run's); `unknown` when the log is there and neither is
(the run was stopped before it could write `exit`); `none` before the first run.
"""

from __future__ import annotations

import concurrent.futures
import http.client
import os
import re
import shlex
import socket
import urllib.error
import urllib.request
from pathlib import Path

from .documents import _config_dir, pipe_lines

__all__ = ["CONFIG", "EXAMPLE", "PROBE_SECONDS", "WRAP", "document", "parse", "run", "state_dir"]

#: In this machine's config directory, never supplied by a request.
CONFIG = _config_dir() / "place-tiles.conf"
EXAMPLE = Path(__file__).resolve().parents[1] / "place-tiles.conf.example"
#: Seconds one URL probe may take; the probes run together, so the read waits about this long at most.
PROBE_SECONDS = 2.0
#: The bytes of `start.log` a run shows: its tail. The read seeks there, so a long-lived server's log costs no more.
TAIL = 4000
#: Runs the command, then records its exit code and end time in the file `$1`.
WRAP = 'f=$1; shift; "$@"; c=$?; printf "%s %s\\n" "$c" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$f"; exit "$c"'
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def state_dir() -> Path:
    """`st_state_dir place-tiles`: each action's lock, output and exit record."""
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "system" / "place-tiles"


def parse(text: str) -> tuple[list[dict], list[str]]:
    """The tiles a text names, each with its actions, and the lines it could not read, each with its number."""
    tiles, problems = {}, []
    for number, _line, fields in pipe_lines(text):
        kind = fields[0]
        if kind == "tile" and len(fields) == 6 and ID.fullmatch(fields[1]) and ID.fullmatch(fields[2]) and fields[3] and fields[4]:
            _, realm, tile, label, folder, url = fields
            if tile in tiles:
                problems.append(f"line {number}: tile {tile} is named twice")
                continue
            tiles[tile] = {"realm": realm, "id": tile, "label": label, "folder": str(Path(folder).expanduser()),
                           "url": "" if url == "-" else url, "actions": []}
        elif kind == "act" and len(fields) == 4 and all(fields):
            _, tile, label, command = fields
            try:
                argv = shlex.split(command)
            except ValueError as error:
                problems.append(f"line {number}: the command does not split: {error}")
                continue
            if tile not in tiles:
                problems.append(f"line {number}: act names tile {tile}, which no tile line above names")
            elif any(_slug(a["label"]) == _slug(label) for a in tiles[tile]["actions"]):
                problems.append(f"line {number}: {tile} has two actions labelled {label}")
            else:
                tiles[tile]["actions"].append({"label": label, "command": command, "argv": argv})
        else:
            problems.append(f"line {number}: expected tile|<realm>|<tile>|<label>|<folder>|<url or -> "
                            "or act|<tile>|<label>|<command>")
    return list(tiles.values()), problems


def _read(config: Path) -> tuple[list[dict], list[str]]:
    return parse(config.read_text(encoding="utf-8"))


def _probe(url: str) -> dict:
    try:
        with _OPENER.open(urllib.request.Request(url, method="GET"), timeout=PROBE_SECONDS) as answer:
            return {"answers": True, "status": f"HTTP {answer.status}"}
    except urllib.error.HTTPError as error:
        error.close()
        return {"answers": True, "status": f"HTTP {error.code}"}
    except urllib.error.URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            return {"answers": False, "status": "nothing listens there"}
        return {"answers": None, "status": f"not known: {error.reason.__class__.__name__}"}
    except (OSError, socket.timeout, ValueError, http.client.HTTPException) as error:
        # HTTPException: `InvalidURL` (a space, a bad port) and a malformed answer are this tile's, not the Overview's.
        return {"answers": None, "status": f"not known: {error.__class__.__name__}"}


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "action"


def _state(tile: dict, label: str) -> Path:
    return state_dir() / tile["realm"] / tile["id"] / _slug(label)


def _last(state: Path) -> dict:
    """The action's last run, from its lock, `exit` and `start.log`."""
    from .sweep import _held

    try:
        with (state / "start.log").open("rb") as log:
            head = log.readline(TAIL)
            body = log.tell()
            end = log.seek(0, os.SEEK_END)
            log.seek(max(body, end - TAIL))
            tail = log.read(TAIL)
    except FileNotFoundError:
        return {"state": "none"}
    except OSError as error:
        return {"state": "unknown", "reason": f"start.log was not read: {error.__class__.__name__}"}
    out = {"started": head.decode("utf-8", "replace").split(" ", 1)[0], "output": tail.decode("utf-8", "replace"),
           "cut": end - body > TAIL}
    held = _held(state)
    if held:
        return {**out, "state": "running"}
    try:
        code, ended = (state / "exit").read_text(encoding="utf-8").split()
        return {**out, "state": "done", "exit": int(code), "ended": ended}
    except FileNotFoundError:
        return {**out, "state": "unknown", "reason": "it ended with no exit record: stopped before it could write one"}
    except (OSError, ValueError) as error:
        return {**out, "state": "unknown", "reason": f"its exit record was not read: {error.__class__.__name__}"}


def document(realm: str, *, now: str, config: Path | None = None) -> dict:
    """`GET /api/place/<realm>/overview`: the realm's tiles as `rows`, each probed and with its actions' last runs."""
    config = CONFIG if config is None else config
    source = f"<config>/project-dashboard/{config.name}"
    base = {"read": now, "area": realm, "source": source, "rows": [], "problems": []}
    try:
        tiles, problems = _read(config)
    except FileNotFoundError:
        return {**base, "state": "read", "reason": f"No tile is set: copy {EXAMPLE.name} to {source} and name this realm's tiles."}
    except (OSError, UnicodeDecodeError) as error:
        return {**base, "state": "unknown", "reason": f"{source} was not read: {error.__class__.__name__}"}
    tiles = [tile for tile in tiles if tile["realm"] == realm]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        probes = list(pool.map(lambda t: _probe(t["url"]) if t["url"] else None, tiles))
    rows = []
    for tile, probe in zip(tiles, probes, strict=True):
        here = Path(tile["folder"]).is_dir()
        rows.append({"id": tile["id"], "label": tile["label"], "url": tile["url"], "probe": probe, "here": here,
                     "why": "" if here else f"{tile['folder']} is not on this machine, so its actions run elsewhere",
                     "actions": [{"label": a["label"], "command": a["command"], "last": _last(_state(tile, a["label"]))}
                                 for a in tile["actions"]]})
    reason = "; ".join(problems) if problems else "" if rows else f"{source} names no tile for {realm}."
    return {**base, "state": "read", "rows": rows, "problems": problems, "reason": reason}


def run(payload, config: Path | None = None):
    """`POST /api/place/tiles {realm, tile, action}`: the start `sweep.spawn` makes, or `ValueError` (400, nothing ran)."""
    from .sweep import spawn

    if set(payload) != {"realm", "tile", "action"} or not all(isinstance(v, str) for v in payload.values()):
        raise ValueError("Expected {realm, tile, action}: the names the Overview tile shows.")
    config = CONFIG if config is None else config
    try:
        tiles, _ = _read(config)
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Nothing ran: {config.name} was not read: {error.__class__.__name__}.") from None
    tile = next((t for t in tiles if (t["realm"], t["id"]) == (payload["realm"], payload["tile"])), None)
    action = next((a for a in tile["actions"] if a["label"] == payload["action"]), None) if tile else None
    if action is None:
        raise ValueError(f"Nothing ran: {config.name} names no action {payload['action']!r} on tile {payload['tile']!r} "
                         f"of {payload['realm']!r}. Read the Overview again.")
    folder = Path(tile["folder"])
    if not folder.is_dir():
        raise ValueError(f"Nothing ran: {folder} is not on this machine, so {tile['label']} runs elsewhere.")
    state = _state(tile, action["label"])

    def start(connection):
        return spawn(state, folder, ["/bin/sh", "-c", WRAP, "sh", str(state / "exit"), *action["argv"]], action["command"],
                     f"{tile['label']} {action['label']}", prepare=lambda: (state / "exit").unlink(missing_ok=True))

    return start
