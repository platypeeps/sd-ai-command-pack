"""A realm place's Overview tiles (sd:6162, sd:6164): an app or a staging site, its link and the commands that run it.

The tiles name folders, hosts and commands on the operator's machines, and this repository is public, so they live in
the config folder, never in a request or a setting row the page writes: `<config>/project-dashboard/place-tiles.conf`
(`CONFIG`; `place-tiles.conf.example` is the template), one line each, as `documents.conf` does:

    tile|<realm>|<tile>|<label>|<folder>|<url or ->[|<host>]   a tile on the realm's Overview, in file order
    act|<tile>|<label>|<command>[|<help>]                      a button on that tile, in file order

`document` answers `GET /api/place/<realm>/overview`. Each tile says whether its folder is on this machine (`here`,
else `why`: an app that runs on another machine shows the tile and the reason, never a button that seems to work),
and probes its URL once, bounded by `PROBE_SECONDS`, the name lookup too (sd:6396): any HTTP answer is
`answers: true` with its status, a refused connection `false`, anything else `null`, unknown. Each action carries its
`help`, the plain words its button's hover shows ("" when the line has none, pack sd:7536), and its last run (`last`).
The line splits on every `|`, so a command never holds one: a pipe makes too many fields, or leaves a quote open.

Pack sd:7665: a tile gets Update (`git pull --ff-only`, no restart) when its folder is a checkout of its own and no line
names Update, and Refresh (Stop, Update, Start) when it has those three and no line names Refresh
(`_update_and_refresh`). `parse` adds them, so a run and a host's follow job see the same actions.

`run` answers `POST /api/place/tiles {realm, tile, action}`. It reads the file again and runs only a command a line
names, split by `shlex` with no shell, in the tile's folder, through `sweep.spawn`: one lock per action
(`<state>/<realm>/<tile>/<action>/lock`), so Stop runs while Start's server holds Start's lock, and a second Deploy
while one runs is a 409. The start is 202 at once; `WRAP` writes `exit` (`<code> <UTC time>`) when the command ends,
and `start.log` holds its output. A refused start (no such line, folder not here) is a 400 and runs nothing.

Last run, from those files: `running` while the lock is held; `done` with the exit code once `exit` is there (the
start clears it first, so an `exit` is always the newest run's); `unknown` when the log is there and neither is
(the run was stopped before it could write `exit`); `none` before the first run.

A tile whose line names a `<host>` other than this machine (`this_host`) runs its actions there (sd:6387), the way
Refresh satellites does (system `local-repo-sync/satellite_refresh.py`, sd:5108): `run` writes the setting row
`place_tiles.request.<host>.<realm>.<tile>.<action>` (`key`), `{id, at, host, realm, tile, action}`, and runs nothing
here. That host's `repo-sync.sh follow`, every five minutes, answers it with system `local-repo-sync/satellite_tiles.py`:
it runs the act line of ITS OWN place-tiles.conf through `run`, never a command from the row, and writes
`place_tiles.result.<...>`, `{host, realm, tile, action, request, attempt, state, started, ended, exit, output, cut,
reason, written}`. Its `state` is `starting`, `running`, `done`, `unknown` (as here) or `refused` (nothing ran,
`reason` says why). `document` reads both rows: a request the result does not answer yet is `pending`. The two
repositories each spell the key rule; a change to it changes both.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .documents import _config_dir, pipe_lines

__all__ = ["CONFIG", "EXAMPLE", "PROBE_SECONDS", "REQUEST", "RESULT", "STEP_SECONDS", "STOP_WAIT", "WRAP", "document", "key", "parse",
           "refresh", "run", "state_dir", "this_host"]

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
#: Seconds Refresh's Stop and Update may each take before Refresh ends them, their children too, and stops (sd:7665).
STEP_SECONDS = 600.0
#: Seconds Refresh waits after Stop for Start's lock to clear, the server it stopped letting go, before Update.
STOP_WAIT = 30.0
#: The Refresh runner: a fresh interpreter, `-I` so the tile's folder shadows no module, given the dashboard and the
#: pack library as its path, then `refresh(realm, tile, config)`.
BOOT = ("import sys; sys.path[:0] = sys.argv[1:3]; from sd_dashboard.place_tiles import refresh; "
        "sys.exit(refresh(*sys.argv[4:]))")
#: The setting rows of a hosted tile's action (sd:6387): the hub's request and that host's result.
REQUEST, RESULT = "place_tiles.request", "place_tiles.result"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def state_dir() -> Path:
    """`st_state_dir place-tiles`: each action's lock, output and exit record."""
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "system" / "place-tiles"


def this_host() -> str:
    """This machine's `hostname -s`, lower-cased: the name a tile line's `<host>` and the cron jobs use."""
    return socket.gethostname().split(".")[0].lower()


def parse(text: str) -> tuple[list[dict], list[str]]:
    """The tiles a text names, each with its actions, and the lines it could not read, each with its number."""
    tiles, problems = {}, []
    for number, _line, fields in pipe_lines(text):
        kind = fields[0]
        if (kind == "tile" and len(fields) in (6, 7) and ID.fullmatch(fields[1]) and ID.fullmatch(fields[2]) and fields[3]
                and fields[4] and (len(fields) == 6 or ID.fullmatch(fields[6]))):
            _, realm, tile, label, folder, url, *host = fields
            if tile in tiles:
                problems.append(f"line {number}: tile {tile} is named twice")
                continue
            tiles[tile] = {"realm": realm, "id": tile, "label": label, "folder": str(Path(folder).expanduser()),
                           "url": "" if url == "-" else url, "host": "".join(host), "actions": []}
        elif kind == "act" and len(fields) in (4, 5) and all(fields):
            _, tile, label, command, *help_ = fields
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
                tiles[tile]["actions"].append({"label": label, "command": command, "argv": argv, "help": "".join(help_)})
        else:
            problems.append(f"line {number}: expected tile|<realm>|<tile>|<label>|<folder>|<url or ->[|<host>] "
                            "or act|<tile>|<label>|<command>[|<help>]")
    for tile in tiles.values():
        _update_and_refresh(tile)
    return list(tiles.values()), problems


def _update_and_refresh(tile: dict) -> None:
    """Pack sd:7665: append Update and Refresh to a tile whose lines name neither, after its own actions.

    Update pulls the latest code and restarts nothing; a tile gets it when its folder is a checkout of its own (`.git`
    there). A folder inside another checkout (a tool of a pinned checkout) gets none: a pull there moves the whole
    checkout, which its lane or repo-sync owns. A hosted tile gets none either (sd:7704): its host adds Update only for
    a checkout there and answers no action its own file lacks, so a line names Update on both. Refresh runs the
    tile's own Stop and Update, then starts Start as its button does, under Start's own lock (`refresh`); a tile
    without Start and Stop runs no process to restart, so it gets none. Refresh starts nothing after a failed update,
    as a hand-written one did. Its `argv` is empty: `run` builds the runner, which needs the file's path.
    """
    by = {_slug(a["label"]): a for a in tile["actions"]}
    if "update" not in by and not _hosted(tile) and (Path(tile["folder"]) / ".git").exists():
        by["update"] = {"label": "Update", "command": "git pull --ff-only", "argv": ["git", "pull", "--ff-only"],
                        "help": "Pulls the latest code into this folder; restarts nothing, and refuses local changes."}
        tile["actions"].append(by["update"])
    if "refresh" not in by and all(step in by for step in ("stop", "update", "start")):
        stop, update, start = (shlex.join(by[step]["argv"]) for step in ("stop", "update", "start"))
        help_ = (f"Asks {tile['host']} to stop {tile['label']}, run its Update, then start it again; the Start button "
                 "here does not show that start." if _hosted(tile)
                 else f"Stops {tile['label']}, runs its Update, then starts it again.")
        tile["actions"].append({"label": "Refresh", "command": f"{stop}; {update} && Start: {start}", "argv": [],
                                "refresh": True, "help": help_})


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


def _probes(urls: list[str]) -> list[dict | None]:
    """Each URL's probe, None for no URL, all within `PROBE_SECONDS` (sd:6396).

    The socket timeout bounds connect and read, not the name lookup before them, so one slow resolver held the whole
    read. A probe still out at the bound is unknown; its thread is left to end on its own, never waited for. Each runs
    in a daemon thread, not an executor's worker, which interpreter exit joins: Refresh's probe after a failed Stop
    runs in its own process, and a stalled lookup held it, its lock and its exit record open (sd:7704).
    """
    found: dict[int, dict] = {}

    def probe(index: int, url: str) -> None:
        try:
            found[index] = _probe(url)
        except Exception as error:  # noqa: BLE001 - a failed probe is unknown, never a down app
            found[index] = {"answers": None, "status": f"not known: {error.__class__.__name__}"}

    threads = [threading.Thread(target=probe, args=(index, url), daemon=True) for index, url in enumerate(urls) if url]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + PROBE_SECONDS
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    return [None if not url else found.get(index, {"answers": None,
                                                   "status": f"not known: no answer within {PROBE_SECONDS:g} s"})
            for index, url in enumerate(urls)]


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "action"


def _segment(name: str) -> str:
    """A setting key segment is `[a-z][a-z0-9_]*`: `-` becomes `_`, and one that starts with a digit gets an `x`."""
    segment = re.sub(r"[^a-z0-9_]", "_", name.lower())
    return segment if re.match(r"[a-z]", segment) else "x" + segment


def key(kind: str, tile: dict, label: str) -> str:
    """`<kind>.<host>.<realm>.<tile>.<action>`: the row of `kind` (`REQUEST` or `RESULT`) for one hosted action.

    Two names can map to one segment (`1a` and `x1a`), so each row also holds its names, and a reader checks them
    (`_mine`). System `local-repo-sync/satellite_tiles.py` spells the same rule.
    """
    return ".".join([kind, *(_segment(name) for name in (tile["host"], tile["realm"], tile["id"], _slug(label)))])


def _hosted(tile: dict) -> bool:
    """A tile whose actions run on another machine, its `<host>`; a line that names this machine is a local tile."""
    return bool(tile["host"]) and tile["host"] != this_host()


def _mine(name: str, value, tile: dict, label: str) -> dict | None:
    """Row `name`'s object, None when unset; `ValueError` when it does not read or names another action."""
    if value is None:
        return None
    row = json.loads(value)
    if not isinstance(row, dict):
        raise ValueError(f"{name} holds no object")
    names = {"host": tile["host"], "realm": tile["realm"], "tile": tile["id"], "action": label}
    if any(row.get(field) != want for field, want in names.items()):
        raise ValueError(f"{name} holds another action's row: {row.get('tile')} {row.get('action')} on {row.get('host')}")
    return row


def _remote_last(tile: dict, label: str, held: dict) -> dict:
    """A hosted action's last run, from its request and result rows (`held`, by key)."""
    try:
        asked = _mine(key(REQUEST, tile, label), held.get(key(REQUEST, tile, label)), tile, label)
        result = _mine(key(RESULT, tile, label), held.get(key(RESULT, tile, label)), tile, label)
    except ValueError as error:
        return {"state": "unknown", "host": tile["host"], "reason": str(error)}
    if asked is not None and (result is None or result.get("request") != asked.get("id")):
        return {"state": "pending", "host": tile["host"], "requested": asked.get("at")}
    if result is None:
        return {"state": "none", "host": tile["host"]}
    last = {field: result.get(field) for field in ("state", "started", "ended", "exit", "output", "cut", "reason",
                                                   "attempt", "written")}
    if last["state"] not in ("starting", "running", "done", "unknown", "refused"):
        last = {**last, "state": "unknown", "reason": f"its result reads state {result.get('state')!r}"}
    return {**{k: v for k, v in last.items() if v is not None}, "host": tile["host"]}


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


def document(realm: str, *, now: str, config: Path | None = None, connection=None) -> dict:
    """`GET /api/place/<realm>/overview`: the realm's tiles as `rows`, each probed and with its actions' last runs.

    A hosted tile's last runs come from its rows in `connection`'s database; none, or a read that fails, is unknown."""
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
    probes = _probes([tile["url"] for tile in tiles])
    held, unread = _held_rows(connection, [(t, a["label"]) for t in tiles if _hosted(t) for a in t["actions"]])
    rows = []
    for tile, probe in zip(tiles, probes, strict=True):
        hosted = _hosted(tile)
        here = not hosted and Path(tile["folder"]).is_dir()
        lasts = [({"state": "unknown", "host": tile["host"], "reason": unread} if unread else _remote_last(tile, a["label"], held))
                 if hosted else _last(_state(tile, a["label"])) for a in tile["actions"]]
        rows.append({"id": tile["id"], "label": tile["label"], "url": tile["url"], "probe": probe, "here": here,
                     "host": tile["host"] if hosted else "",
                     "why": "" if here or hosted else f"{tile['folder']} is not on this machine, so its actions run elsewhere",
                     "actions": [{"label": a["label"], "command": a["command"], "help": a["help"], "last": last}
                                 for a, last in zip(tile["actions"], lasts, strict=True)]})
    reason = "; ".join(problems) if problems else "" if rows else f"{source} names no tile for {realm}."
    return {**base, "state": "read", "rows": rows, "problems": problems, "reason": reason}


def _held_rows(connection, actions: list[tuple[dict, str]]) -> tuple[dict, str]:
    """The request and result rows of `actions`, by key, and why they were not read ("" when they were)."""
    if not actions:
        return {}, ""
    if connection is None:
        return {}, "no database answered this read, so the host's rows were not read"
    from sd_db import writes

    try:
        return writes.read_settings(connection, [key(kind, tile, label) for tile, label in actions
                                                 for kind in (REQUEST, RESULT)]), ""
    except Exception as error:  # noqa: BLE001 - any failed read is unknown, never "not run yet"
        return {}, f"the host's rows were not read: {error.__class__.__name__}: {error}"


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
    if _hosted(tile):
        return lambda connection: _ask(connection, tile, action)
    folder = Path(tile["folder"])
    if not folder.is_dir():
        raise ValueError(f"Nothing ran: {folder} is not on this machine, so {tile['label']} runs elsewhere.")
    state = _state(tile, action["label"])
    argv = _refresher(tile, config) if action.get("refresh") else action["argv"]

    def start(connection):
        return spawn(state, folder, ["/bin/sh", "-c", WRAP, "sh", str(state / "exit"), *argv], action["command"],
                     f"{tile['label']} {action['label']}", prepare=lambda: (state / "exit").unlink(missing_ok=True))

    return start


def _ask(connection, tile: dict, action: dict):
    """A hosted action's start: its request row, which that host's follow job answers; nothing runs here."""
    from sd_db import writes

    asked = {"id": secrets.token_hex(8), "at": writes.now(), "host": tile["host"], "realm": tile["realm"],
             "tile": tile["id"], "action": action["label"]}
    writes.set_setting(connection, key(REQUEST, tile, action["label"]), json.dumps(asked))
    return 202, {"requested": asked["id"], "at": asked["at"], "host": tile["host"], "command": action["command"]}


def _refresher(tile: dict, config: Path) -> list[str]:
    """The argv of a tile's Refresh: `refresh` in a fresh interpreter, which the WRAP and Refresh's lock hold."""
    from . import pack_library

    return [sys.executable, "-I", "-c", BOOT, str(Path(__file__).resolve().parents[1]), str(pack_library()), "refresh",
            tile["realm"], tile["id"], str(config)]


class _Ended(Exception):
    """TERM or INT reached Refresh: its running step is ended and reaped before Refresh lets go of its lock."""

    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


def _end_refresh(signum, _frame):
    # One signal is enough: the rest are ignored, so ending the step is not cut short in turn.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, signal.SIG_IGN)
    raise _Ended(signum)


def refresh(realm: str, tile_id: str, config: str) -> int:
    """`_refresh`, with TERM and INT ending its running step before it returns; the old handlers come back after."""
    handlers = {sig: signal.signal(sig, _end_refresh) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        return _refresh(realm, tile_id, config)
    except _Ended as ended:
        print(f"Refresh was ended by signal {ended.signum}; its running step was ended first.", flush=True)
        return 128 + ended.signum
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def _refresh(realm: str, tile_id: str, config: str) -> int:
    """A tile's Refresh (sd:7665): its Stop, then its Update, then a start of Start through `run`, as its button does.

    Start runs under its own lock, so a foreground server is Start's: Start's button reads it running and refuses a
    second server, and Refresh ends once Start is started. Each step moves state, so a step that fails stops Refresh
    before the next one (the PR's failure table, review round 2):

    - Stop exits non-zero: the server may still run, so Update does not run, unless the service reads stopped: Start's
      lock is free and the tile's link refuses. With no link, or one that does not refuse, it is not known to be
      stopped, and not known is not stopped.
    - Stop exits 0 and Start's lock is still held `STOP_WAIT` seconds later: the server still runs; no Update.
    - Stop or Update runs past `STEP_SECONDS` (a pull waiting on a credential): Refresh ends it and its children, and
      stops with 124. Git is told not to prompt, so a pull fails at once where it can.
    - Update fails: nothing starts; the service stays stopped, and the output says to press Update, then Start.
    - Start is refused (a press of Start got there first: 409) or no longer named (400): named, exit 1 or 2.

    A Refresh cut short frees its lock only once no step of it runs (review round 3): TERM or INT ends and reaps the
    running step first, and each step holds Refresh's lock too (`SD_RUN_LOCK_FD`), so after a KILL the step left
    behind keeps Refresh running, and the next Refresh a 409, until it ends. Its exit record names the cut, and the
    next Refresh runs every step again. The probe after a failed Stop is bounded by `PROBE_SECONDS`, as the Overview's
    are; past it the service is not known to be stopped. On a hosted tile the host runs this, writes no row for Start, and the hub's Start button reads
    its own last request, not this start: a limit Refresh's hover says on the hub. The output goes to Refresh's
    `start.log`.
    """
    from .sweep import _held

    config_path = Path(config)
    try:
        tiles, _ = _read(config_path)
    except (OSError, UnicodeDecodeError) as error:
        print(f"Nothing ran: {config_path.name} was not read: {error.__class__.__name__}.")
        return 2
    tile = next((t for t in tiles if (t["realm"], t["id"]) == (realm, tile_id)), None)
    by = {_slug(a["label"]): a for a in tile["actions"]} if tile else {}
    if tile is None or _hosted(tile) or not all(step in by for step in ("stop", "update", "start")):
        print(f"Nothing ran: {config_path.name} no longer gives {tile_id} of {realm} a Start, Stop and Update here.")
        return 2
    start_state = _state(tile, by["start"]["label"])
    code = _step(by["stop"], tile["folder"])
    if code is None:
        print(f"Stop ran past {STEP_SECONDS:g} s and was ended; whether {tile['label']} runs is not known, so Update "
              "did not run.", flush=True)
        return 124
    if code and not (_held(start_state) is None and tile["url"] and _probes([tile["url"]])[0]["answers"] is False):
        print(f"Stop exited {code} and {tile['label']} is not known to be stopped, so Update did not run.", flush=True)
        return code
    deadline = time.monotonic() + STOP_WAIT
    while _held(start_state) is not None:
        if time.monotonic() >= deadline:
            print(f"Start's server still runs {STOP_WAIT:g} s after Stop, so Update did not run.", flush=True)
            return 1
        time.sleep(0.2)
    code = _step(by["update"], tile["folder"])
    if code is None or code:
        why = f"ran past {STEP_SECONDS:g} s and was ended" if code is None else f"exited {code}"
        print(f"Update {why}, so Start was not pressed: {tile['label']} stays stopped. Press Update, then Start.",
              flush=True)
        return 124 if code is None else code
    try:
        status, body = run({"realm": realm, "tile": tile_id, "action": by["start"]["label"]}, config_path)(None)
    except ValueError as error:
        print(f"Start was not started: {error}", flush=True)
        return 2
    if status == 202:
        print(f"Start started at {body['started']}, under its own lock: its button shows how it runs.", flush=True)
        return 0
    print(f"Start was not started: {body.get('error', status)}", flush=True)
    return 1


def _step(action: dict, folder: str) -> int | None:
    """Refresh's Stop or Update, in its own session and holding Refresh's lock too; its exit code, or None when it ran
    past `STEP_SECONDS` and it and its children were ended. `_Ended` ends it the same way, then goes on up."""
    print(f"$ {action['command']}", flush=True)
    lock = os.environ.get("SD_RUN_LOCK_FD", "")
    fds = (int(lock),) if lock.isdigit() and _open(int(lock)) else ()
    child = subprocess.Popen(action["argv"], cwd=folder, stdin=subprocess.DEVNULL, start_new_session=True,
                             pass_fds=fds, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    try:
        code = child.wait(timeout=STEP_SECONDS)
    except subprocess.TimeoutExpired:
        _end(child)
        return None
    except _Ended:
        _end(child)
        raise
    # Popen gives a step a signal ended as minus the signal; a shell's 128+signum is what Refresh exits (sd:7704).
    return 128 - code if code < 0 else code


def _open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def _end(child: subprocess.Popen) -> None:
    """TERM, then KILL whatever of the step's group outlived TERM, and reap it; the group is gone once killpg finds
    no member. macOS answers EPERM now and then for a group whose last members are exiting (sd:7704): the step itself
    is then KILLed alone, so the reap below cannot wait on it."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            break
        except PermissionError:
            child.kill()
            break
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    child.wait()
