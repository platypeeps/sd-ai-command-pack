"""Plugin tabs, loaded from the registry rather than found on disk.

Three of the six sources the Needs-you view alerts on -- `toolbox`, `ports`,
`areas` -- are system-owned and arrive through this module (R11-D12). Two
properties follow from that, and both are load-bearing.

**One plugin, many tabs, one invocation each.** A repository has one manifest
and therefore one `dashboard.tile`, but `~/repos/system` owns five of the views
being folded in. The manifest names them in `dashboard.tabs`, and the loader
runs the tile once per name, passing the name as its argument.

That is not a shape preference, it is what the budget requires. Measured on
this machine, the five system collectors take 3.78s, 2.84s, 0.03s, 0.01s and
0.00s. Every one fits a 5s budget; run in sequence behind a single command they
total 6.66s and the tile is killed on every load, permanently. Per-tab
invocation keeps the 5s meaning the same thing however many tabs a plugin
grows, and gives each tab its own failure: the 3.78s collector can no longer
starve the four that cost nothing. Tabs run concurrently, so the wall clock is
the slowest tab rather than their sum.

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

import concurrent.futures
import json
import os
import re
import select
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path

SD = Path(__file__).resolve().parent.parent / "bin" / "sd"

TILE_SECONDS = 5.0
TILE_BYTES = 64 * 1024
# The registry is the pack's own CLI rather than a plugin, so it answers to its
# own budget. Borrowing the per-tile ceiling made the registry's size a function
# of what one plugin is allowed to print, and a machine registering enough
# plugins to pass 64KB of listing would have read as a broken registry forever.
CATALOG_SECONDS = 10.0
CATALOG_BYTES = 1024 * 1024
READ_CHUNK = 65536
# A plugin's tabs wait on each other only for the machine. Bounded because a
# plugin declaring thirty tabs should not decide how many processes the
# dashboard starts at once.
#
# This is a per-plugin pool, and the machine-wide ceiling is the same number
# only because plugins are read one at a time -- `load` iterates them serially,
# and `cached_load`'s lock means one load runs at a time. Raised in review as
# `TAB_WORKERS * plugins`, which is what it would become the day plugin reading
# is parallelised. Whoever does that owes this constant a semaphore; until
# then, adding one would be machinery for a code path that does not exist.
TAB_WORKERS = 4
# One fan-out at a time, and not repeated for callers arriving together.
LOAD_SECONDS = 5.0
_LOAD_LOCK = threading.Lock()
_LOADED: dict | None = None
_LOADED_AT = 0.0
# The registry validates tab names when a plugin registers; this is the loader
# declining to trust what reaches it anyway, because a name arrives as a
# command-line argument and `--anything` would arrive as a flag.
TAB_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

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
    """A subprocess did not deliver a usable answer inside its bounds.

    Raised for every way `bounded_run` can decline: the deadline passing, the
    byte ceiling being crossed, the command failing to start, the process
    outliving its own output, and a non-zero exit. The message says which. It
    covers the registry read as well as tiles, since both go through the same
    bounded call.
    """


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
        # The cwd belongs in the message: "no such file or directory" for a
        # tile that exists says nothing until you know which directory it was
        # looked for in. Found in review.
        where = f" in {cwd}" if cwd is not None else ""
        raise Bounded(f"cannot run {argv[0]}{where}: {error}") from None

    chunks: list[bytes] = []
    size = 0
    stop = time.monotonic() + seconds
    assert proc.stdout is not None
    try:
        fd = proc.stdout.fileno()
        while True:
            left = stop - time.monotonic()
            # Two different failures share this deadline and are not the same
            # thing to whoever reads the row: a tile that never spoke, and one
            # that wrote and then stopped. Reporting the second as "no output"
            # sends the operator looking for a tile that never started.
            stalled = (
                f"no output within {seconds:g}s"
                if not size
                else f"stopped writing within {seconds:g}s, after {size} bytes"
            )
            if left <= 0:
                raise Bounded(stalled)
            if not select.select([fd], [], [], left)[0]:
                raise Bounded(stalled)
            # One byte past the ceiling is enough to know the tile crossed
            # it. Asking for a fixed 64KB and measuring afterwards would let a
            # caller with a small limit still be handed -- and made to
            # allocate -- a full chunk before the limit was consulted, which
            # is the opposite of enforcing it while reading.
            chunk = os.read(fd, min(READ_CHUNK, limit - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise Bounded(f"wrote more than {limit} bytes")
            chunks.append(chunk)
        # Closing stdout is not exiting, and the exit status is part of what
        # the budget covers: a tile that prints its JSON and then fails has
        # failed. Killing it on the way past would record -SIGKILL, and a
        # loader that reads its own kill as a clean exit accepts the output of
        # every tile that dies after writing.
        try:
            proc.wait(timeout=max(stop - time.monotonic(), 0.0))
        except subprocess.TimeoutExpired:
            raise Bounded(f"did not exit within {seconds:g}s") from None
        if proc.returncode != 0:
            raise Bounded(f"exited {proc.returncode}")
    finally:
        # Only on the way out of a refusal. A tile that exited on its own has
        # nothing left to kill, and `poll()` is what tells the two apart.
        if proc.poll() is None:
            _terminate(proc)
        proc.stdout.close()
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
            limit=CATALOG_BYTES,
        )
    except Bounded as error:
        return [], f"cannot read the plugin registry: {error}"
    except Exception as error:  # noqa: BLE001 - the alternative is no dashboard
        # `select` and `os.read` raise `OSError` and `InterruptedError` on
        # their own account, and this is the one read with no plugin above it
        # to catch the failure: uncaught, the whole view is gone rather than
        # one tab. Same rule as the per-tab net, at the level that has no tab.
        return [], f"the loader failed reading the plugin registry: {error!r}"
    # `sd plugin list --json` prints a JSON array on every path, an empty
    # registry included. Nothing at all is the CLI misbehaving, and treating it
    # as an empty registry makes a broken loader look like a machine with no
    # plugins -- this module's own complaint, at the one level that has no
    # plugin to blame.
    if not raw.strip():
        return [], "plugin registry printed nothing"
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as error:
        return [], f"plugin registry is not JSON: {error}"
    except UnicodeDecodeError as error:
        return [], f"plugin registry is not UTF-8: {error}"
    if not isinstance(loaded, list):
        return [], "plugin registry is not a list"
    entries = [entry for entry in loaded if isinstance(entry, dict)]
    # Dropping what it cannot read and reporting success is the quiet this
    # module refuses everywhere else: a corrupt registry would lose plugins
    # with nothing said. The readable entries are still returned, because
    # losing the rest of the fleet to one bad element is the same mistake.
    dropped = len(loaded) - len(entries)
    if dropped:
        return entries, f"plugin registry has {dropped} entr{'y' if dropped == 1 else 'ies'} that are not objects"
    return entries, ""


def validate_rows(payload: object, source: str) -> tuple[list[dict], list[str]]:
    """The rows a tile emitted, and a complaint for each one refused.

    A rejected row is dropped and named rather than silently repaired. Both
    halves are returned because the caller turns the complaints into rows of
    their own: a plugin whose alert was malformed has still lost an alert, and
    that loss is exactly what must not be quiet.
    """
    # `null` is absent, here and for `title` and `html` alike. The contract
    # marks these keys optional, and a tile that spells "nothing to show" as
    # `null` rather than by omission has lost nothing -- complaining about one
    # spelling while accepting the other is a rule about JSON style rather than
    # about what reached the operator. Raised in review; kept, and now stated.
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
        # Rank 0 is the top of the view and is where this module writes the
        # row saying a plugin has gone dark. A negative rank would sort above
        # that, so a plugin could push the notice of its own failure below its
        # own rows -- the exact outcome the failure row exists to prevent.
        if row["rank"] < FAILURE_RANK:
            complaints.append(
                f"{source}: row {index} has a rank above {FAILURE_RANK}, "
                f"which is the top of the view"
            )
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
    """One registered plugin's tabs, each collected under its own budget."""
    # Read, not coerced: `str(7)` is a non-empty string that passes the check
    # below and leaves `Path("7")` as a relative working directory the plugin
    # never named. The check is for the type the contract says, not for
    # something that can be spelled as text. Found in review.
    raw_root = entry.get("root")
    raw_prefix = entry.get("prefix")
    root = raw_root if isinstance(raw_root, str) else ""
    prefix = raw_prefix if isinstance(raw_prefix, str) else ""
    # A plugin whose manifest will not read has no prefix to be named by, and
    # "?" for every one of them makes two dark plugins one indistinguishable
    # row. The root is what the loader has, so the root is what it says.
    base: dict = {"prefix": prefix, "root": root, "label": prefix or root or "?", "tabs": []}

    def refuse(reason: str) -> dict:
        return {**base, "ok": False, "declared": True, "reason": reason}

    # `is not True` rather than falsiness: a registry spelling it `"false"` is
    # a string, which is truthy, and the loader would have run a tile for a
    # manifest that never read. Found in review.
    if entry.get("readable") is not True:
        return refuse(str(entry.get("why") or "manifest unreadable"))
    # An entry the loader cannot identify is not an entry it may run. An empty
    # root would resolve to `Path("")`, which is the dashboard's own working
    # directory, so a tile would run somewhere its plugin never asked for; and
    # an empty prefix stamps every row of every tab as `/<name>`. Refusing is
    # the same answer the rest of this module gives to a payload it cannot
    # trust. Found in review.
    if not root or not prefix:
        return refuse("registry entry has no root or no prefix")
    # `sd plugin list` validates the dashboard block and says when it no
    # longer parses -- a tab that stopped appearing, rather than a plugin that
    # never declared one.
    broken = entry.get("dashboardError")
    if broken:
        return refuse(str(broken))

    tile = entry.get("tile")
    names = entry.get("tabs")
    if tile is None:
        # Not a failure. A plugin may register for its `kinds` or its issues
        # repo and never declare a tile, and reporting that as broken would
        # put a rank-0 row in Now for a machine that is working correctly.
        # Absent is the only spelling of that -- an empty or non-string tile is
        # a declared tile that is wrong, and falls through to a refusal.
        return {**base, "ok": True, "declared": False, "reason": ""}
    if not isinstance(tile, str) or not tile:
        return refuse("`dashboard.tile` is not a command")
    if not isinstance(names, list) or not names:
        return refuse("`dashboard.tabs` names no tabs to serve")
    try:
        argv = shlex.split(tile)
    except ValueError as error:
        return refuse(f"unparseable tile command: {error}")
    if not argv:
        return refuse("`dashboard.tile` is empty")

    wanted: list[str] = []
    refused: list[dict] = []
    for name in names:
        text = str(name)
        if not TAB_NAME.fullmatch(text):
            refused.append(_refused_tab(prefix, text, "is not a tab name"))
        elif text in wanted:
            refused.append(_refused_tab(prefix, text, "is declared twice"))
        else:
            wanted.append(text)
    with concurrent.futures.ThreadPoolExecutor(max_workers=TAB_WORKERS) as pool:
        tabs = list(pool.map(lambda name: _tab(argv, root, prefix, name), wanted))
    return {**base, "tabs": tabs + refused, "ok": True, "declared": True, "reason": ""}


def _refused_tab(prefix: str, name: str, why: str) -> dict:
    """A declared tab that is never invoked, and says so rather than vanishing."""
    return {"prefix": prefix, "name": name, "title": name, "html": "", "rows": [],
            "complaints": [], "ok": False, "reason": f"`{name}` {why}"}


def _tab(argv: list[str], root: str, prefix: str, name: str) -> dict:
    """`read_tab`, with a tab's failure kept inside that tab.

    Refusal is per item at every level in this module, and an exception nobody
    predicted is the one path that was not: raised in a worker it surfaces when
    the results are collected and takes every other plugin's tabs down with it.
    A row naming the tab is not masking the error -- it is the error, reported
    where an operator will see it.
    """
    try:
        return read_tab(argv, root, prefix, name)
    except Exception as error:  # noqa: BLE001 - the alternative is losing every tab
        return {"prefix": prefix, "name": name, "title": name, "html": "",
                "rows": [], "complaints": [], "ok": False,
                "reason": f"the loader failed reading this tab: {error!r}"}


def read_tab(argv: list[str], root: str, prefix: str, name: str) -> dict:
    """One tab, from one invocation of the tile under one budget."""
    tab: dict = {"prefix": prefix, "name": name, "title": name,
                 "html": "", "rows": [], "complaints": []}

    def refuse(reason: str) -> dict:
        return {**tab, "ok": False, "reason": reason}

    try:
        raw = bounded_run(
            [*argv, name], Path(root), seconds=TILE_SECONDS, limit=TILE_BYTES
        )
    except Bounded as error:
        return refuse(str(error))
    # An empty payload is `{}` and a tile that has nothing to show prints it.
    # Printing nothing is a different event, and accepting it hands the view a
    # successful tab that is silent about its own failure.
    if not raw.strip():
        return refuse("tile printed nothing")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        return refuse(f"tile output is not JSON: {error}")
    except UnicodeDecodeError as error:
        # `json.loads` decodes bytes before it parses them, so bytes that are
        # not UTF-8 raise past every JSON guard. Left uncaught it escapes the
        # worker and takes the whole load with it: one plugin's bad bytes, and
        # no plugin reports at all.
        return refuse(f"tile output is not UTF-8: {error}")
    if not isinstance(payload, dict):
        return refuse("tile output is not a JSON object")

    complaints: list[str] = []
    where = f"{prefix}/{name}"
    # The declared name is both the identity and the fallback; `title` only
    # renames what the operator sees. A plugin that omits it is not in error,
    # which is why this field differs from every other one here.
    title = payload.get("title")
    if title is not None and (not isinstance(title, str) or not title.strip()):
        complaints.append(f"{where} has a title that is not a non-empty string")
        title = None
    html = payload.get("html")
    if html is not None and not isinstance(html, str):
        # Coercing it to "" would render an empty tab and say nothing, which
        # is the silence this module exists to refuse. The tab is kept -- its
        # rows may still be good -- and the loss is named.
        complaints.append(f"{where} has a non-string html")
        html = None
    rows, row_complaints = validate_rows(payload.get("rows"), where)
    complaints.extend(row_complaints)
    return {
        **tab,
        "title": title.strip() if isinstance(title, str) else name,
        # Markup by contract: a tile renders itself into its own tab, and that
        # was true before rows existed. Rows are data and are rendered as
        # text; the two are not the same trust and the split is deliberate.
        "html": html if isinstance(html, str) else "",
        "rows": rows,
        "complaints": complaints,
        "ok": True,
        "reason": "",
    }


def cached_load(now: float | None = None) -> dict:
    """`load`, shared between overlapping requests rather than repeated.

    The server is threaded, so a page refreshing quickly -- or two of them --
    had every request starting its own fan-out of tile subprocesses. The lock
    makes concurrent callers wait for one load instead of each spawning their
    own, and the short window keeps a refresh loop from re-running tiles that
    answered a moment ago. Deliberately not the state cache's twenty seconds: a
    plugin row is what an operator is watching change. Found in review.
    """
    stamp = time.monotonic() if now is None else now
    with _LOAD_LOCK:
        global _LOADED, _LOADED_AT
        if _LOADED is None or stamp - _LOADED_AT >= LOAD_SECONDS:
            _LOADED = load()
            _LOADED_AT = stamp
        return _LOADED


def load() -> dict:
    """Every plugin tab, plus the alert rows they contribute to Now."""
    entries, failure = catalog()
    found = [read_plugin(entry) for entry in entries]
    return {
        "plugins": found,
        "tabs": [tab for plugin in found for tab in plugin["tabs"] if tab["ok"]],
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
                # Not "unreadable": since the registry also reports entries it
                # had to drop, a readable registry can fail here too, and a row
                # that names the wrong failure is a row that misdirects.
                "what": "plugin registry did not load cleanly",
                "detail": failure,
            }
        )
    def dark(where: str, what: str, detail: str) -> dict:
        return {"source": where, "rank": FAILURE_RANK, "kind": "plugin-dark",
                "id": where, "what": what, "detail": detail}

    for plugin in found:
        label = plugin["label"]
        if not plugin["ok"]:
            rows.append(dark(label, f"plugin {label} is not reporting", plugin["reason"]))
            continue
        for tab in plugin["tabs"]:
            where = f"{plugin['prefix']}/{tab['name']}"
            if not tab["ok"]:
                # Per tab, not per plugin: the whole reason the tile is invoked
                # once per tab is that one of them failing must not be the
                # others going quiet.
                rows.append(dark(where, f"plugin tab {where} is not reporting", tab["reason"]))
                continue
            rows.extend(tab["rows"])
            for complaint in tab["complaints"]:
                rows.append(
                    {
                        "source": where,
                        "rank": FAILURE_RANK,
                        "kind": "plugin-refused",
                        "id": where,
                        "what": f"plugin tab {where} emitted something the contract refused",
                        "detail": complaint,
                    }
                )
    rows.sort(key=lambda row: row["rank"])
    return rows
