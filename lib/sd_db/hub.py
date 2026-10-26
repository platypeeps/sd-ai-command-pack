"""The satellite's selector: `~/.config/sd/hub.json` (step 4).

Step 4 of `docs/work/2026-09-22-run-the-framework-from-a-second-machine/`.
A machine whose home holds this file is a satellite: `sd_db.connect` sends
every open of the default database to the hub the file names, and
`sd_db.default_path` answers with a `HubPath`, whose `exists()` asks the hub.

    {"hub": "hub.example.test", "port": 8769}

The selector is a file and not an environment variable. Cron and launchd
read no shell profile, and a satellite must refuse the same way from every
caller.

Three rules, each one a test in `tests/test_hub.py`:

* No file: `connect` opens the local database, as it always did.
* The file and no reachable hub: `HubUnreachable`, naming the hub. Nothing
  is created on this machine: no database, no folder for one.
* The file beside a local database: `HubConflict`. A machine is a hub or a
  satellite, not both, and the refusal is what keeps the satellite free of
  a second writer.

An explicit path other than the default is opened locally, as before: the
Jev meter's own file, a backup target and a test's fixture are not the
record, and the hub does not hold them.

`token_file` is for loopback only: `sd-db serve --loopback` refuses a
session without the token it wrote beside its database. A hub on the
tailnet carries no token; it admits the session by its peer's Tailscale
identity (step 7), so a satellite's `hub.json` names no `token_file`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import remote, tailnet
from .errors import SchemaTooNew, SdDbError

#: Beside `runner.json` and `dashboard.json`, under the same home as the
#: database path it replaces.
CONFIG_RELATIVE = Path(".config/sd/hub.json")
#: The port the design names for `sd-db serve`.
DEFAULT_PORT = 8769
#: Seconds to wait for the hub to answer a connect. A satellite with
#: Tailscale down must fail by name in seconds, not hang for a TCP timeout.
CONNECT_TIMEOUT = 5.0
#: Seconds a satellite waits on a silent hub, per read of an answer, past
#: the session's own wait for the write lock (`busy_timeout`) (sd:3359). A
#: hub that took the session and stopped answering held its caller, and a
#: lane runner's lock with it, for as long as the socket lived.
ANSWER_TIMEOUT = 120.0


#: What `Hub.open` calls with a `BuildMismatch` before raising it (sd:4748):
#: `follow.attempt` in an entrypoint that may run again from its start, which
#: `bin/sd` installs through `sd_lib.import_sd_db`. `None` here and in every
#: other process: a server, a lane runner or a ship sees the refusal. A hook
#: that returns leaves the refusal to be raised; one that replaces the process
#: does not return.
on_mismatch: Callable[[remote.BuildMismatch], None] | None = None


class HubConfigError(remote.RemoteError):
    """`hub.json` exists and cannot be read as a hub. Never a local fallback."""


class HubConflict(remote.RemoteError):
    """This machine has both `hub.json` and a local database."""

    def __init__(self, config: Path, local: Path, host: str) -> None:
        self.config = str(config)
        self.local = str(local)
        self.host = host
        super().__init__(
            f"this machine has both {config}, which names the sd hub {host}, and a "
            f"local database at {local}; a machine is a hub or a satellite, not both. "
            f"On a satellite, move the local database away; on the hub, remove {config}"
        )


def _base(home: Path | str | None) -> Path:
    # As `database.local_path` reads it: `$HOME` at call time.
    return Path(home) if home is not None else Path(os.environ.get("HOME", "~")).expanduser()


def config_path(home: Path | str | None = None) -> Path:
    return _base(home) / CONFIG_RELATIVE


def configured(home: Path | str | None = None) -> bool:
    """Whether this home names a hub. Cheap: one `stat`, no parse."""
    return config_path(home).exists()


@dataclass(frozen=True)
class Hub:
    """The hub one `hub.json` names."""

    host: str
    port: int
    config: Path
    token_file: Path | None = None

    def token(self) -> str:
        """The loopback server's token, read when the socket is up."""
        if self.token_file is None:
            return ""
        try:
            return self.token_file.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise HubConfigError(
                f"cannot read the token file {self.token_file} that {self.config} names: "
                f"{error.strerror or error}"
            ) from error

    def open(self, local: Path, *, write: bool, create: bool, busy_timeout: int) -> remote.Connection:
        """A session on the hub's own database, in place of `local`."""
        if local.exists():
            raise HubConflict(self.config, local, self.host)
        if create:
            # `init` and `migrate` are hub verbs, and a satellite holds no
            # database to create (R4).
            raise remote.HubOnly("init and migrate", f"{self.host}:{self.port}")
        try:
            return remote.connect(self.host, self.port, None, token=self.token, write=write,
                                  busy_timeout=busy_timeout, timeout=CONNECT_TIMEOUT,
                                  answer_timeout=ANSWER_TIMEOUT + busy_timeout / 1000)
        except remote.HubUnreachable as error:
            raise remote.HubUnreachable(
                self.host, self.port, f"{error.reason} (named in {self.config})"
            ) from error
        except remote.BuildMismatch as mismatch:
            if on_mismatch is not None:
                on_mismatch(mismatch)
            raise


def read(home: Path | str | None = None) -> Hub | None:
    """The hub this home names, or `None` when it names none.

    A file that exists and does not parse is refused by name. Falling back
    to a local open would put a second database on a satellite.
    """
    path = config_path(home)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise HubConfigError(f"cannot read {path}: {error.strerror or error}") from error
    expected = f'expected {{"hub": "<host>", "port": {DEFAULT_PORT}}}'
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        host = data["hub"]
        if not isinstance(host, str) or not host.strip():
            raise ValueError('"hub" is not a host name')
        port = data.get("port", DEFAULT_PORT)
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError(f'"port" {port!r} is not a TCP port')
        token_file = data.get("token_file")
        if token_file is not None and (not isinstance(token_file, str) or not token_file):
            raise ValueError('"token_file" is not a path')
    except KeyError as missing:
        raise HubConfigError(f"{path} names no {missing.args[0]!r}; {expected}") from None
    except ValueError as problem:
        raise HubConfigError(f"{path} is not a hub config: {problem}; {expected}") from None
    return Hub(host=host.strip(), port=port, config=path,
               token_file=Path(token_file).expanduser() if token_file else None)


class HubPath(type(Path())):
    """`default_path()` on a satellite: the same path, with `exists()` asked of the hub.

    Gap x1 of the design. Pack verbs test `sd_db.default_path().exists()`
    before they connect, or pass the path to `connect`. On a satellite the
    local file does not exist, so a plain path would read "no database". This
    one compares, prints and hashes as the plain path does. `connect` treats
    it, and any path equal to it, as the default. Paths derived from it
    (`parent`, `with_name`, `/`) are plain paths.
    """

    def __init__(self, *segments, home: Path | str | None = None) -> None:
        super().__init__(*segments)
        self.sd_home = None if home is None else Path(home)

    def with_segments(self, *segments) -> Path:
        return Path(*segments)

    def exists(self, *, follow_symlinks: bool = True) -> bool:
        """Whether the hub has its database. Raises `HubUnreachable`, never guesses.

        A read session proves it. A hub whose file is newer than this
        library still has one, so `SchemaTooNew` answers `True` here and
        refuses at `connect`, where it belongs.
        """
        from .database import connect

        try:
            connection = connect(self, write=False, home=self.sd_home)
        except FileNotFoundError:
            return False
        except SchemaTooNew:
            return True
        connection.close()
        return True


# ---------------------------------------------------------------- the fence

#: The fleet setting that names the hub by its tailnet name (hub failover, D5).
HUB_NAME = "sd.hub_name"
#: Seconds a failed read of this node's name stands: `lane run` asks once per
#: repository, and a stalled daemon must not cost each one its timeout.
#: A name is never held: a rename must refuse the next check (sd:4044).
NAME_SECONDS = 30.0

_name_failed: tuple[float, Exception] | None = None


@dataclass(frozen=True)
class Role:
    """Whether this machine holds the hub role: `holder`, `off`, `elsewhere` or `unknown`.

    `holder` is the name `sd.hub_name` holds, `None` when unset; `reason`
    is one line a refusal can quote. Callers that act off this machine refuse
    on `elsewhere` and `unknown`; a write to its own database refuses on
    `elsewhere` alone (`write_role`).
    """

    state: str
    holder: str | None
    reason: str

    @property
    def refuses(self) -> bool:
        return self.state not in ("holder", "off")


def _this_name() -> str:
    """`tailnet.this_name`, except that a failure refuses again for `NAME_SECONDS` without asking."""
    global _name_failed
    if _name_failed is not None and time.monotonic() - _name_failed[0] <= NAME_SECONDS:
        raise _name_failed[1]
    try:
        return tailnet.this_name()
    except tailnet.TailnetError as error:
        _name_failed = (time.monotonic(), error)
        raise


def _matches(mine: str, holder: str) -> bool:
    """The full MagicDNS name, or its first label when `sd.hub_name` is a bare machine name."""
    holder = holder.strip().rstrip(".").lower()
    return mine == holder if "." in holder else mine.split(".")[0] == holder


def role(connection, name=None) -> Role:
    """The fence: a machine holds the hub role only while its tailnet name is `sd.hub_name`.

    `connection` is this machine's own database; `name` reads this node's
    tailnet name (`tailnet.this_name`; a failure stands for `NAME_SECONDS`). The setting
    is read first, so a machine that never set it asks Tailscale nothing.

    Unset is `off`: a fleet that never named its hub runs as before, and
    `promote` refuses to move the role until the setting exists, so a
    returning old hub always finds the name in its own database.
    An unreadable setting, or a Tailscale that does not answer, is `unknown`.
    """
    from . import writes

    try:
        # A database older than the `state` table can hold no setting: never set, not unreadable.
        held = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'state'").fetchone()
        holder = writes.read_settings(connection, [HUB_NAME]).get(HUB_NAME) if held else None
    except (SdDbError, sqlite3.Error, OSError) as error:
        return Role("unknown", None, f"{HUB_NAME} does not read: {error}")
    if not holder:
        return Role("off", None, f"{HUB_NAME} is unset, so the fence is off; "
                                 f"on the hub run `sd config set {HUB_NAME} <its tailnet name>`")
    try:
        mine = (name or _this_name)()
    except tailnet.TailnetError as error:
        return Role("unknown", holder, f"Tailscale does not name this node, so it cannot match {holder}: {error}")
    if _matches(mine, holder):
        return Role("holder", holder, f"this node is {mine}, the hub {HUB_NAME} names")
    return Role("elsewhere", holder, f"{HUB_NAME} names {holder}, and this node is {mine}")


def role_at(path: Path, name=None) -> Role:
    """`role` on a fresh read-only connection to `path`; a database that does not open is `unknown`."""
    from .database import connect

    try:
        connection = connect(path, write=False)
    except Exception as error:  # noqa: BLE001 -- no answer is unknown, named
        return Role("unknown", None, f"the database at {path} did not open: {type(error).__name__}: {error}")
    try:
        return role(connection, name)
    finally:
        connection.close()


# ------------------------------------------------------- the write fence

#: Seconds a write inside a transaction trusts the last fence answer for one
#: database, as a tailnet frame does (`serve.FENCE_SECONDS`). A commit
#: never trusts it: it asks afresh, as the listener's commit does. A wall
#: clock that moved `CLOCK_SLACK` more than the monotonic one, which does
#: not count a sleep, asks again.
FENCE_SECONDS = 5.0
CLOCK_SLACK = 1.0
#: SQLite's action codes for a statement that writes a database file. A
#: pragma is left out: migrate's DDL asks, and a pragma alone moves no row.
_WRITES = frozenset({
    sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ANALYZE, sqlite3.SQLITE_REINDEX, sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_VIEW, sqlite3.SQLITE_CREATE_VTABLE,
    sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_TRIGGER, sqlite3.SQLITE_DROP_VIEW,
    sqlite3.SQLITE_DROP_VTABLE,
})

_answers: dict[str, tuple[float, float, Role]] = {}
_answers_guard = threading.Lock()


class Fenced(remote.RemoteError):
    """This machine no longer holds the hub role (hub failover, D5).

    On the tailnet the session closes and rolls back. On a returning hub's
    own database the write refuses and its transaction rolls back (system
    sd:5986).
    """


def write_role(path: Path, *, fresh: bool = False) -> Role:
    """`role` of the database at `path`, read from that file and held `FENCE_SECONDS`.

    The file itself, never through `hub.json`: during demotion `hub.json`
    sits beside the database, and a `HubConflict` read as `unknown` would let
    a writer that is already open go on. `fresh` asks again whatever is
    held, as a commit does: a held `holder` may predate the rename.
    """
    from .database import open_local

    key = str(path)
    with _answers_guard:
        ticks, wall = time.monotonic(), time.time()
        held = _answers.get(key)
        if held is not None and not fresh:
            since, at, found = held
            if ticks - since < FENCE_SECONDS and abs((wall - at) - (ticks - since)) <= CLOCK_SLACK:
                return found
        try:
            connection = open_local(Path(path), write=False, create=False)
        except Exception as error:  # noqa: BLE001 -- no answer is unknown, named
            found = Role("unknown", None, f"the database at {path} did not open: {type(error).__name__}: {error}")
        else:
            try:
                found = role(connection)
            finally:
                connection.close()
        _answers[key] = (ticks, wall, found)
        return found


def demotion(path: Path, found: Role) -> str:
    """The `Fenced` text for a local write: the holder, then the two demotion steps, `hub.json` first."""
    return (f"refused: this machine is not the hub, so it writes nothing to {path}: {found.reason}. "
            f"Reads still work. Demote it in this order: "
            f"1. copy ~/{CONFIG_RELATIVE} from any satellite into this home "
            f"(until step 2, every sd command refuses with HubConflict); "
            f"2. move {path} aside as {Path(path).name}.demoted-<date>; "
            f"sd commands then reach the hub, {found.holder}")


class _WriteFence:
    """SQLite's authorizer on this machine's own write connection (system sd:5986).

    Write unless fenced (#31093): only `elsewhere` refuses. `holder`, `off`
    and `unknown` write, so a Tailscale outage does not stop a healthy hub.
    Each boundary that makes a write persist asks afresh: COMMIT, the RELEASE
    of a savepoint opened outside a transaction, and a write outside one,
    which commits when it ends (`executescript` runs each statement so).
    A write inside a transaction asks the held answer, to stop early; its
    commit decides. So a transaction open across the console rename rolls back.
    The connection caches no statement: Python does not authorize a cached one again.
    It holds its connection weakly, so the pair makes no cycle.
    """

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self.connection = weakref.ref(connection)
        #: This transaction, or an autocommit write since the last BEGIN, prepared a write.
        self.wrote = False
        #: The savepoint opened outside a transaction: its RELEASE commits.
        self.outer: str | None = None
        #: Why the last statement was denied, for the `Fenced` the connection raises.
        self.refusal: str | None = None

    def _open(self) -> bool:
        """Whether a transaction is open before the statement being prepared."""
        connection = self.connection()
        return connection is not None and connection.in_transaction

    def __call__(self, action: int, arg1, arg2, database, trigger) -> int:
        if action == sqlite3.SQLITE_TRANSACTION:
            if arg1 == "COMMIT":
                return self._ask(fresh=True) if self.wrote else sqlite3.SQLITE_OK
            self.wrote, self.outer = False, None
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_SAVEPOINT:
            name = (arg2 or "").lower()
            if arg1 == "BEGIN" and not self._open():
                self.wrote, self.outer = False, name
            if arg1 == "RELEASE" and name == self.outer and self.wrote:
                return self._ask(fresh=True)
            return sqlite3.SQLITE_OK
        if action in _WRITES and database != "temp":
            self.wrote = True
            return self._ask(fresh=not self._open())
        return sqlite3.SQLITE_OK

    def _ask(self, *, fresh: bool) -> int:
        found = write_role(self.path, fresh=fresh)
        if found.state != "elsewhere":
            return sqlite3.SQLITE_OK
        self.refusal = demotion(self.path, found)
        return sqlite3.SQLITE_DENY


def _fenced(connection: sqlite3.Connection, run, *args):
    """`run(*args)`, with a fence denial raised as `Fenced` after its transaction rolls back."""
    fence: _WriteFence | None = getattr(connection, "fence", None)
    if fence is not None:
        fence.refusal = None
    try:
        return run(*args)
    except sqlite3.DatabaseError as error:
        if fence is None or fence.refusal is None:
            raise
        refusal, fence.refusal = fence.refusal, None
        if connection.in_transaction:
            # Nothing a fenced transaction wrote may commit.
            sqlite3.Connection.execute(connection, "ROLLBACK")
        raise Fenced(refusal) from error


class _FencedCursor(sqlite3.Cursor):
    def execute(self, *args):
        return _fenced(self.connection, super().execute, *args)

    def executemany(self, *args):
        return _fenced(self.connection, super().executemany, *args)

    def executescript(self, *args):
        return _fenced(self.connection, super().executescript, *args)


class FencedConnection(sqlite3.Connection):
    """This machine's own write connection to its default database (`database.open_local`)."""

    fence: _WriteFence | None = None

    def arm(self, path: Path) -> None:
        self.fence = _WriteFence(Path(path), self)
        self.set_authorizer(self.fence)

    def cursor(self, factory=_FencedCursor):
        return super().cursor(factory)

    def execute(self, *args):
        return _fenced(self, super().execute, *args)

    def executemany(self, *args):
        return _fenced(self, super().executemany, *args)

    def executescript(self, *args):
        return _fenced(self, super().executescript, *args)

    def commit(self):
        return _fenced(self, super().commit)

    def __exit__(self, *args):
        return _fenced(self, super().__exit__, *args)
