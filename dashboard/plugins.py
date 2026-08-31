"""Plugin tabs, loaded from the registry rather than found on disk.

Three of the six sources the Needs-you view alerts on -- `toolbox`, `ports`,
`areas` -- are system-owned and arrive through this module (R11-D12). Two
properties follow from that, and both are load-bearing.

**One plugin, many tabs.** A repository has one manifest and therefore one
`dashboard.tile`, but `~/repos/system` owns five of the views being folded in.
So a tile returns a *list* of tabs rather than a single one, and a pack
contributing one tab writes a list of length one. The uniform shape is worth
the small ceremony: the alternative is two payload shapes and a rule about
which applies.

**The registry is asked, never scanned.** The tile contract says registration
happens only through `sd plugin add`; a loader that globbed a directory would
run whatever landed in it. So this module does not read manifests at all. It
shells out to `sd plugin list --json` -- the CLI is the plugin service surface
by design (r5), and calling it is what keeps a second manifest parser from
existing. The pack has already paid four times over for the same file in four
places; a reader is a file like any other.

**A plugin that goes dark says so.** The view this feeds owns every rank-0 and
rank-1 alert the dashboard can emit: a cron job that exited non-zero, a vault
collector that errored. The failure that matters is not a plugin crashing, it
is a plugin crashing quietly and leaving Now looking calm. So every way a tile
can fail -- absent, non-zero, timed out, oversized, unparseable, or emitting a
row the contract rejects -- becomes a rank-0 row in the same view, written by
this module. Silence is the one outcome that is not available.

The budget is per tile and covers both halves of what it returns: five seconds
and 64 KB for the markup and the rows together. Both are enforced while
reading, not checked afterwards, because a check that runs after the read has
already let an unbounded plugin decide how much memory the dashboard uses.
"""

from __future__ import annotations

import json
import os
import re
import select
import shlex
import signal
import subprocess
import time
from pathlib import Path

SD = Path(__file__).resolve().parent.parent / "bin" / "sd"

TILE_SECONDS = 5.0
TILE_BYTES = 64 * 1024
CATALOG_SECONDS = 10.0
READ_CHUNK = 65536

# An `href` may point within the page and nowhere else. A plugin row lands in
# the backbone's most prominent view, and the difference between rendering
# there and being able to navigate the operator somewhere is the whole of the
# trust boundary R11-D12 drew.
ANCHOR = re.compile(r"^#[A-Za-z0-9_:.-]{1,64}$")

REQUIRED_ROW = ("rank", "kind", "id", "what")
OPTIONAL_ROW = ("detail", "href")

# Rank 0 is the top of the view. A tab that failed is reported there rather
# than at the bottom, because the rows it did not emit were rank 0 too.
FAILURE_RANK = 0


class Bounded(Exception):
    """A tile exceeded its budget. The message names which half."""


def _terminate(proc: subprocess.Popen) -> None:
    """Kill the tile's whole process group, not just the command it named.

    A tile that backgrounds work would otherwise outlive its own timeout and go
    on holding the pipe, so the deadline would bound this module and nothing
    else.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def bounded_run(argv: list[str], cwd: Path | None, *, seconds: float, limit: int) -> bytes:
    """`argv`'s stdout, refusing past `seconds` or `limit` bytes.

    Both bounds are applied to the stream as it arrives. Reading everything and
    measuring afterwards would make the limit advisory: the process has already
    handed us the bytes by the time the number is known.
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as error:
        raise Bounded(f"cannot run {argv[0]}: {error}") from None

    chunks: list[bytes] = []
    size = 0
    stop = time.monotonic() + seconds
    assert proc.stdout is not None
    try:
        fd = proc.stdout.fileno()
        while True:
            left = stop - time.monotonic()
            if left <= 0:
                raise Bounded(f"no output within {seconds:g}s")
            if not select.select([fd], [], [], left)[0]:
                raise Bounded(f"no output within {seconds:g}s")
            chunk = os.read(fd, READ_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise Bounded(f"wrote more than {limit} bytes")
            chunks.append(chunk)
    finally:
        _terminate(proc)
        proc.stdout.close()

    if proc.returncode not in (0, -signal.SIGKILL):
        raise Bounded(f"exited {proc.returncode}")
    return b"".join(chunks)


def catalog() -> tuple[list[dict], str]:
    """Registered plugins, as `sd plugin list --json` reports them.

    An empty registry and an `sd` that cannot run are different answers and are
    returned as such: the first is a machine with no plugins, which is normal,
    and the second is the loader being broken, which is not.
    """
    try:
        raw = bounded_run(
            [str(SD), "plugin", "list", "--json"],
            cwd=None,
            seconds=CATALOG_SECONDS,
            limit=TILE_BYTES,
        )
    except Bounded as error:
        return [], f"cannot read the plugin registry: {error}"
    try:
        loaded = json.loads(raw or b"[]")
    except json.JSONDecodeError as error:
        return [], f"plugin registry is not JSON: {error}"
    if not isinstance(loaded, list):
        return [], "plugin registry is not a list"
    return [entry for entry in loaded if isinstance(entry, dict)], ""


def validate_rows(payload: object, source: str) -> tuple[list[dict], list[str]]:
    """The rows a tile emitted, and a complaint for each one refused.

    A rejected row is dropped and named rather than silently repaired. Both
    halves are returned because the caller turns the complaints into rows of
    their own: a plugin whose alert was malformed has still lost an alert, and
    that loss is exactly what must not be quiet.
    """
    if payload is None:
        return [], []
    if not isinstance(payload, list):
        return [], [f"{source}: `rows` is not a list"]
    rows: list[dict] = []
    complaints: list[str] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            complaints.append(f"{source}: row {index} is not an object")
            continue
        missing = [key for key in REQUIRED_ROW if key not in row]
        if missing:
            complaints.append(f"{source}: row {index} lacks {', '.join(missing)}")
            continue
        # `rank` orders the whole merged view, so a string that sorts as a
        # string would put a plugin's row anywhere. bool is excluded because it
        # is an int in Python and `rank: true` is not an ordering.
        if isinstance(row["rank"], bool) or not isinstance(row["rank"], int):
            complaints.append(f"{source}: row {index} has a non-integer rank")
            continue
        text = {key: row[key] for key in REQUIRED_ROW if key != "rank"}
        if not all(isinstance(value, str) for value in text.values()):
            complaints.append(f"{source}: row {index} has a non-string kind, id or what")
            continue
        clean = {"source": source, "rank": row["rank"], **text}
        detail = row.get("detail")
        if detail is not None and not isinstance(detail, str):
            complaints.append(f"{source}: row {index} has a non-string detail")
            continue
        clean["detail"] = detail or ""
        href = row.get("href")
        if href is not None:
            if not isinstance(href, str) or not ANCHOR.fullmatch(href):
                complaints.append(f"{source}: row {index} has an href that is not an in-page anchor")
                continue
            clean["href"] = href
        rows.append(clean)
    return rows, complaints


def read_plugin(entry: dict) -> dict:
    """One registered plugin's tabs, or the reason there are none."""
    root = str(entry.get("root") or "")
    prefix = str(entry.get("prefix") or "?")
    base: dict = {"prefix": prefix, "root": root, "tabs": [], "complaints": []}

    def refuse(reason: str) -> dict:
        return {**base, "ok": False, "declared": True, "reason": reason}

    if not entry.get("readable", False):
        return {**base, "ok": False, "declared": True,
                "reason": str(entry.get("why") or "manifest unreadable")}
    tile = entry.get("tile")
    if not tile:
        # Not a failure. A plugin may register for its `kinds` or its issues
        # repo and never declare a tile, and reporting that as broken would
        # put a rank-0 row in Now for a machine that is working correctly.
        return {**base, "ok": True, "declared": False, "reason": ""}
    if not isinstance(tile, str):
        return refuse("`dashboard.tile` is not a command string")
    try:
        argv = shlex.split(tile)
    except ValueError as error:
        return refuse(f"unparseable tile command: {error}")
    if not argv:
        return refuse("`dashboard.tile` is empty")

    try:
        raw = bounded_run(argv, Path(root), seconds=TILE_SECONDS, limit=TILE_BYTES)
    except Bounded as error:
        return refuse(str(error))
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError as error:
        return refuse(f"tile output is not JSON: {error}")
    if not isinstance(payload, dict):
        return refuse("tile output is not a JSON object")
    declared = payload.get("tabs")
    if declared is None:
        return refuse("tile output declares no `tabs`")
    if not isinstance(declared, list):
        return refuse("`tabs` is not a list")

    tabs, complaints = validate_tabs(declared, prefix)
    return {**base, "tabs": tabs, "complaints": complaints,
            "ok": True, "declared": True, "reason": ""}


def validate_tabs(declared: list, prefix: str) -> tuple[list[dict], list[str]]:
    """The tabs a tile emitted, and a complaint for each one refused.

    A refused tab is dropped and named rather than repaired, on the same
    reasoning as a refused row: the plugin believes it published a view, and
    the gap between what it published and what renders is the thing that must
    not be quiet.
    """
    tabs: list[dict] = []
    complaints: list[str] = []
    seen: set[str] = set()
    for index, tab in enumerate(declared):
        where = f"{prefix}: tab {index}"
        if not isinstance(tab, dict):
            complaints.append(f"{where} is not an object")
            continue
        title = tab.get("title")
        # Required rather than defaulted to the prefix. A default is a
        # convenience at one tab and a collision at five, and the title is
        # what the operator clicks.
        if not isinstance(title, str) or not title.strip():
            complaints.append(f"{where} has no title")
            continue
        title = title.strip()
        if title in seen:
            # Two tabs under one name is a tab that cannot be reached, which
            # renders as a working dashboard missing a view.
            complaints.append(f"{where} repeats the title {title!r}")
            continue
        seen.add(title)
        html = tab.get("html")
        rows, row_complaints = validate_rows(tab.get("rows"), f"{prefix}/{title}")
        complaints.extend(row_complaints)
        tabs.append(
            {
                "prefix": prefix,
                "title": title,
                # Markup by contract: a tile renders itself into its own tab,
                # and that was true before rows existed. Rows are data and are
                # rendered as text; the two are not the same trust and the
                # split is deliberate.
                "html": html if isinstance(html, str) else "",
                "rows": rows,
            }
        )
    return tabs, complaints


def load() -> dict:
    """Every plugin tab, plus the alert rows they contribute to Now."""
    entries, failure = catalog()
    found = [read_plugin(entry) for entry in entries]
    return {
        "plugins": found,
        "tabs": [tab for plugin in found for tab in plugin["tabs"]],
        "rows": alert_rows(found, failure),
        "registryError": failure,
    }


def alert_rows(found: list[dict], failure: str = "") -> list[dict]:
    """Plugin rows for Now, with every loss represented as a row of its own.

    Sorted by rank so the merge with the backbone's own rows is a concatenation
    the caller sorts once, and stable within a rank so a plugin cannot reorder
    another plugin's alerts by renaming its own.
    """
    rows: list[dict] = []
    if failure:
        rows.append(
            {
                "source": "dashboard",
                "rank": FAILURE_RANK,
                "kind": "plugin-registry",
                "id": "registry",
                "what": "plugin registry unreadable",
                "detail": failure,
            }
        )
    for plugin in found:
        prefix = plugin["prefix"]
        if not plugin["ok"]:
            rows.append(
                {
                    "source": prefix,
                    "rank": FAILURE_RANK,
                    "kind": "plugin-dark",
                    "id": prefix,
                    "what": f"plugin tab {prefix} is not reporting",
                    "detail": plugin["reason"],
                }
            )
            continue
        for tab in plugin["tabs"]:
            rows.extend(tab["rows"])
        for complaint in plugin["complaints"]:
            rows.append(
                {
                    "source": prefix,
                    "rank": FAILURE_RANK,
                    "kind": "plugin-refused",
                    "id": prefix,
                    "what": f"plugin {prefix} emitted something the contract refused",
                    "detail": complaint,
                }
            )
    rows.sort(key=lambda row: row["rank"])
    return rows
