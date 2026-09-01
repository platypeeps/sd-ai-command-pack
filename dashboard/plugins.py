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
import hashlib
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

from . import markup

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
# How much of a failing tile's stderr rides back in the refusal. The tail
# rather than the head: a Python traceback puts the error on its last line, and
# a plugin author reading a row wants the thing that went wrong rather than the
# first frame of the stack that led there. Bounded because stderr is written by
# the plugin too, and an unbounded one would put a plugin in charge of how long
# a row is.
STDERR_TAIL = 512

# What one refusal will read off stderr on its way out, at most. Raised in
# review as a hang: a tile writing stderr in a loop keeps the pipe readable, so
# an unbounded drain would spin there and never reach the kill. Measured, that
# does not happen -- `yes`, `cat /dev/zero`, and three concurrent writers each
# ran the pipe empty in three reads, because a zero-timeout `select` sees the
# gap the instant the reader wins and no writer refills within that quantum.
# The bound stays anyway, on the narrower claim it can actually carry: one
# refusal reads what one pipe buffer can hold, which is everything a tile can
# have written with nobody reading, and it is a fixed amount of work rather
# than an argument about scheduling.
DRAIN_BYTES = 65536
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

# A row names no destination of its own. R11-D19: the only anchor a plugin
# could write is one it cannot know, since the panel id is composed by the
# backbone from `prefix/name` and published nowhere. The destination is
# therefore resolved from the `source` this module stamps below, rather than
# carried in the payload.
#
# `source` is unique per served tab -- `bin/sd` refuses a duplicate prefix and
# `read_plugin` a duplicate tab name -- but the panel id derived from it is
# NOT, because `panelId` normalises with `[^a-z0-9]+ -> -`, which is lossy:
# `a-b` and `a--b` are both valid `TAB_NAME`s and both land on `sys-a-b`, so
# the collision suffix is reachable. Now must therefore read the id from a map
# the renderer builds as it assigns them, keyed on `prefix/name` -- never by
# recomputing the normalisation. Recomputing would send a row to a sibling
# tab's panel, which is worse than not linking it.
#
# Now is not built yet (6b-5b): until it is, nothing links a row anywhere and
# `showAlerts` renders source, what and detail as text. The trust boundary
# R11-D12 drew is kept by the backbone choosing the destination rather than by
# a regex hoping for one.
REQUIRED_ROW = ("rank", "kind", "id", "what")
OPTIONAL_ROW = ("detail",)

# Rank 0 is the top of the view. A tab that failed is reported there rather
# than at the bottom, because the rows it did not emit were rank 0 too.
FAILURE_RANK = 0

# R11-D20. An alert id is an ack key: the operator dismisses a row by its id and
# every row sharing it goes too. So an id identifies one alert, and it is
# namespaced by its source, because a plugin minting `pr:owner/repo#5` would
# otherwise dismiss the backbone's row of that name. Bounded at 300 because the
# ack store refuses anything longer, and a row that cannot be acked is a row
# that cannot be cleared.
ID_MAX = 300


def alert_id(source: str, *parts: str) -> str:
    """One stable, bounded, source-namespaced id for one alert.

    Stable rather than positional: a complaint's ordinal shifts when a
    neighbouring complaint clears, which would silently move an ack from the
    row it was granted to onto a different one. A digest of the text does not
    move, and the text is what the operator read when they dismissed it.
    """
    ident = ":".join((source,) + parts)
    if len(ident) <= ID_MAX:
        return ident
    keep = ID_MAX - 13  # room for "~" plus a 12-character digest
    return ident[:keep] + "~" + hashlib.sha256(ident.encode()).hexdigest()[:12]


def _digest(text: str) -> str:
    """Twelve hex characters of a complaint, used as its stable identity."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]


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

    Stderr is read alongside stdout and its tail is carried into the refusal.
    It used to go to `DEVNULL`, which made every failing tile report as bare
    `exited 1` -- this module refuses to let a plugin go quiet and was
    discarding the plugin's own account of why it had. It is read rather than
    left in a pipe because a pipe nobody drains fills, and a tile blocked
    writing its traceback would hit the deadline and be reported as a timeout
    instead: the fix for a lost message would have been a wrong one.
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
    assert proc.stderr is not None
    said = b""

    def refuse(reason: str) -> Bounded:
        """The refusal, with whatever the tile managed to say about it."""
        drain()
        tail = said.decode("utf-8", "replace").strip()
        return Bounded(f"{reason}: {tail}" if tail else reason)

    def drain() -> None:
        """Whatever is already in the stderr pipe, without waiting for more.

        Called on the way to every refusal because the interesting case is a
        tile that writes its traceback and exits: both pipes close at once, and
        the loop can break on stdout without stderr's last read.

        Never blocks: a zero timeout means no read waits on the tile. Bounded
        by DRAIN_BYTES besides, so one refusal costs a fixed amount of reading
        no matter what the tile is doing -- see that constant for what was and
        was not shown about the loop this bound was proposed to stop.
        """
        nonlocal said
        budget = DRAIN_BYTES
        while err in watch and budget > 0:
            if not select.select([err], [], [], 0)[0]:
                return
            piece = os.read(err, min(READ_CHUNK, budget))
            if not piece:
                watch.remove(err)
                return
            budget -= len(piece)
            said = (said + piece)[-STDERR_TAIL:]

    fd = proc.stdout.fileno()
    err = proc.stderr.fileno()
    watch = [fd, err]
    try:
        while True:
            left = stop - time.monotonic()
            # Two different failures share this deadline and are not the same
            # thing to whoever reads the row: a tile that never spoke, and one
            # that wrote and then stopped. Reporting the second as "no stdout"
            # sends the operator looking for a tile that never started.
            #
            # Both name stdout rather than output, because since R11-D18 the
            # refusal carries the tile's stderr tail: "no output within 5s:
            # Traceback ..." contradicts itself, and the tile that talked only
            # on stderr is exactly the case this message is read in. Found in
            # review.
            stalled = (
                f"no stdout within {seconds:g}s"
                if not size
                else f"stopped writing stdout within {seconds:g}s, after {size} bytes"
            )
            if left <= 0:
                raise refuse(stalled)
            ready = select.select(watch, [], [], left)[0]
            if not ready:
                raise refuse(stalled)
            if err in ready:
                # Kept as a tail, so a tile that writes megabytes of warnings
                # costs a constant amount of memory rather than its own choice
                # of one.
                piece = os.read(err, READ_CHUNK)
                if piece:
                    said = (said + piece)[-STDERR_TAIL:]
                else:
                    # Closed. Left in `watch` it would be ready forever and
                    # spin this loop against the deadline.
                    watch.remove(err)
                continue
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
                raise refuse(f"wrote more than {limit} bytes")
            chunks.append(chunk)
        # Closing stdout is not exiting, and the exit status is part of what
        # the budget covers: a tile that prints its JSON and then fails has
        # failed. Killing it on the way past would record -SIGKILL, and a
        # loader that reads its own kill as a clean exit accepts the output of
        # every tile that dies after writing.
        #
        # The wait drains, for the reason the loop above reads stderr at all.
        # Stdout closing does not close stderr, and a tile that prints its JSON,
        # closes stdout, then writes past the pipe capacity on stderr blocks in
        # that write until someone reads -- so a plain `wait` here would hang on
        # it until the deadline and report `did not exit` for a tile that had
        # already said everything it was asked for. That is the deadlock this
        # function was changed to remove, moved past the break. Found in review.
        while True:
            left = stop - time.monotonic()
            if left <= 0:
                raise refuse(f"did not exit within {seconds:g}s")
            if err in watch:
                # Capped at 50ms so a tile that exits while holding stderr open
                # -- a grandchild inheriting it -- is noticed by the `wait`
                # below rather than waited on until the deadline.
                if select.select([err], [], [], min(left, 0.05))[0]:
                    piece = os.read(err, READ_CHUNK)
                    if piece:
                        said = (said + piece)[-STDERR_TAIL:]
                        continue
                    watch.remove(err)
            try:
                # Once stderr is closed there is nothing left to drain and this
                # blocks for the rest of the budget; while it is open the poll
                # is free and the select above is what does the waiting.
                proc.wait(timeout=left if err not in watch else 0.0)
                break
            except subprocess.TimeoutExpired:
                continue
        if proc.returncode != 0:
            raise refuse(f"exited {proc.returncode}")
    finally:
        # Only on the way out of a refusal. A tile that exited on its own has
        # nothing left to kill, and `poll()` is what tells the two apart.
        if proc.poll() is None:
            _terminate(proc)
        proc.stdout.close()
        proc.stderr.close()
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
        # Namespaced here rather than at render time: an id that is only unique
        # once somebody remembers to prefix it is not unique.
        text["id"] = alert_id(source, text["id"])
        clean = {"source": source, "rank": row["rank"], **text}
        detail = row.get("detail")
        if detail is not None and not isinstance(detail, str):
            complaints.append(f"{source}: row {index} has a non-string detail")
            continue
        clean["detail"] = detail or ""
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
    # Markup by contract: a tile renders itself into its own tab, and that was
    # true before rows existed. Rows are data and are rendered as text; the two
    # are not the same trust and the split is deliberate. The markup half is
    # filtered here rather than at the point of injection, so that what
    # `/api/plugins` serves is already what the contract allows -- see
    # `markup.py` for why `innerHTML` not running `<script>` settles nothing.
    clean, markup_complaints = (
        markup.sanitize(html, where) if isinstance(html, str) else ("", [])
    )
    complaints.extend(markup_complaints)
    return {
        **tab,
        "title": title.strip() if isinstance(title, str) else name,
        "html": clean,
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
                "id": alert_id("dashboard", "registry"),
                # Not "unreadable": since the registry also reports entries it
                # had to drop, a readable registry can fail here too, and a row
                # that names the wrong failure is a row that misdirects.
                "what": "plugin registry did not load cleanly",
                "detail": failure,
            }
        )
    def dark(where: str, what: str, detail: str) -> dict:
        return {"source": where, "rank": FAILURE_RANK, "kind": "plugin-dark",
                "id": alert_id(where, "dark"), "what": what, "detail": detail}

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
                        # Per complaint, not per tab: a tab refusing three rows
                        # is three things the operator lost, and one shared id
                        # would let dismissing the first hide the other two.
                        "id": alert_id(where, "refused", _digest(complaint)),
                        "what": f"plugin tab {where} emitted something the contract refused",
                        "detail": complaint,
                    }
                )
    rows.sort(key=lambda row: row["rank"])
    return rows
