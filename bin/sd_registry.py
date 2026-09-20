"""Read the provider registry; WORKFLOW.md defines its format and role rules.

With sd_db installed, its registry reader merges provider and bill rows so
runtime controls remain authoritative. Fresh checkouts, CI, and the installer
can instead read the file without a database. Criterion 32 requires both
readers to resolve the same ordered providers from the same providers.yaml.

The standalone reader validates transport exclusivity, role references,
author/reviewer separation, and the refusal of capped start entries. It does
not duplicate database row merging, seeding, or the full YAML parser. Registry
validation does not meter actual provider usage or enforce monetary caps;
usage accounting and provider-charge enforcement remain separate work.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import pwd
import re
import shlex
import sqlite3
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

#: Beside the database, in `~/.local/share/sd/`. The same path `sd_db` uses;
#: stated here rather than imported, because this module answers before the
#: library exists.
REGISTRY_NAME = "providers.yaml"
REGISTRY_RELATIVE = Path(".local/share/sd") / REGISTRY_NAME

#: The two role lists. A third is added to the file and to this tuple, and to
#: nothing else.
ROLES = ("author", "reviewer")

# A provider receives its declared variables and only this execution base.
# This limits accidental credential inheritance; it is not a filesystem sandbox.
BASE_ENV = ("PATH", "HOME", "LANG", "TERM", "TMPDIR", "USER")


def provider_environment(provider: Provider, parent: Mapping[str, str]) -> dict[str, str]:
    """Build the environment passed to one provider, without unrelated keys."""
    allowed = set(BASE_ENV) | set(provider.env)
    result = {name: value for name, value in parent.items() if name in allowed}
    # Native macOS keychain lookup needs the actual login identity, not a key.
    try:
        result["USER"] = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        # A numeric container uid must not inherit a spoofed login identity.
        result.pop("USER", None)
    return result

#: A bill with one of these bases has a spend limit something enforces, so
#: every provider on it must be callable by the library rather than spawned.
CAPPED_BASES = ("company", "plan", "prepaid")

#: What the one client assumes about every `url` entry, and the registry does
#: not say: no field names an endpoint path, an auth scheme or a deadline.
#: OpenAI-compatible is the shape the design pins for all of them, so an
#: endpoint wanting another path or another scheme is a different client, not a
#: different entry.
CHAT_COMPLETIONS = "/chat/completions"
AUTH_SCHEME = "Bearer"
MAX_RESPONSE_BYTES = 2_000_000

_CONSTANTS = {"true": True, "false": False, "null": None, "~": None}


class RegistryError(Exception):
    """A registry that cannot mean anything, refused at read time."""


@dataclass(frozen=True)
class Bill:
    name: str
    cost_basis: str
    cap_usd_month: float | None = None
    meter: str | None = None
    meter_env: str | None = None  # the variable holding the meter's key (sd:788)

    @property
    def capped(self) -> bool:
        return self.cap_usd_month is not None or self.cost_basis in CAPPED_BASES


@dataclass(frozen=True)
class Provider:
    """One entry. `ranks` is its position in each role list it appears on."""

    name: str
    vendor: str
    bill: str
    start: str | None = None
    url: str | None = None
    model: str | None = None
    reader: str | None = None
    max_tokens: int | None = None
    thinking: str | None = None
    reasoning_effort: str | None = None
    price: dict[str, float] = field(default_factory=dict)
    env: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    enabled: bool = True
    reason: str | None = None
    ranks: dict[str, int] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "url" if self.url else "start"


@dataclass(frozen=True)
class Registry:
    path: Path
    bills: dict[str, Bill]
    providers: dict[str, Provider]

    def order(self, role: str) -> list[Provider]:
        """The enabled providers holding `role`, best first.

        Only ranked entries resolve automatically.
        An enabled, unranked reviewer remains available through an explicit pick.
        """
        if role not in ROLES:
            raise RegistryError(f"no role {role!r}; the roles are {', '.join(ROLES)}")
        holders = [
            provider
            for provider in self.providers.values()
            if role in provider.ranks and provider.enabled
        ]
        return sorted(holders, key=lambda provider: provider.ranks[role])

    def resolve(self, role: str) -> Provider:
        """The provider a role gets. A disabled entry never resolves."""
        order = self.order(role)
        if not order:
            raise RegistryError(
                f"no enabled provider holds the {role!r} role in {self.path}"
            )
        return order[0]


def registry_path(
    home: Path | str | None = None, environ: dict[str, str] | None = None
) -> Path:
    """`~/.local/share/sd/providers.yaml`, honouring an explicit home."""
    if home is not None:
        base = Path(home)
    else:
        source = os.environ if environ is None else environ
        base = Path(source.get("HOME", "~")).expanduser()
    return base / REGISTRY_RELATIVE


def shipped_path(checkout: Path | str) -> Path:
    """The copy in the pack checkout, which the installer seeds a home from."""
    return Path(checkout) / REGISTRY_NAME


def library():
    """`sd_db.registry`, or `None` when the library is not installed here."""
    try:
        import sd_lib  # noqa: PLC0415 - its helper also tries the provisioned copy (sd:746)
        sd_lib.import_sd_db()  # a `None` module leaves the import below to fail, as before
        from sd_db import registry as module  # noqa: PLC0415 - optional at runtime
    except ImportError:
        return None
    return module


def read(
    path: Path | str | None = None,
    *,
    home: Path | str | None = None,
    connection: Any = None,
    prefer_library: bool = True,
) -> Registry:
    """The registry, through the library when there is one and the file when
    there is not.

    `connection` is passed through to `sd_db` so the rows win on state; with
    no library it is refused rather than ignored, because a caller that has a
    connection and gets file-only answers would be reading a registry the
    dashboard has already changed.
    """
    target = Path(path) if path is not None else registry_path(home)
    module = library() if prefer_library else None
    if module is None:
        if connection is not None:
            raise RegistryError(
                "a connection was given but sd_db is not installed in this "
                "virtualenv, so the provider and bill rows cannot be read. "
                "Provision the library (`sd-install --provision-library`) or "
                "read the file alone by passing no connection."
            )
        return read_file(target)
    try:
        registry = module.read(target, connection=connection)
        if any(not hasattr(provider, key) for provider in registry.providers.values() for key in ("thinking", "reasoning_effort")):
            if any(provider.thinking or provider.reasoning_effort for provider in read_file(target).providers.values()):
                raise RegistryError("installed sd_db cannot preserve reasoning controls; provision the updated library")
        # `meter_env` is the file's alone: no row carries it, and a library
        # whose `Bill` does not name it drops the key, so the meter step would
        # cap every metered bill for a field the operator wrote (sd:788).
        meter_envs = None
        if any(bill.meter is not None and not hasattr(bill, "meter_env") for bill in registry.bills.values()):
            meter_envs = _file_meter_envs(target)
        return _adapt(registry, meter_envs)
    except module.RegistryError as error:  # one refusal vocabulary, not two
        raise RegistryError(str(error)) from None


def read_or_report(
    path: Path | str | None = None,
    *,
    home: Path | str | None = None,
    connection: Any = None,
    with_database: bool = False,
    database_path: Path | str | None = None,
) -> tuple[Registry, str]:
    """Return the registry, or an empty registry and its refusal reason.

    Bare-checkout --explain must report missing configuration without crashing;
    a real review must refuse it. Never substitute shipped pins for the
    operator's missing registry. Callers requiring a registry check the reason;
    read() retains the raising interface.
    """
    target = Path(path) if path is not None else registry_path(home)
    try:
        return (read_runtime(target, home=home, database_path=database_path) if with_database else read(target, connection=connection)), ""
    except RegistryError as error:
        return Registry(target, {}, {}), str(error)


def read_runtime(target: Path, *, home: Path | str | None = None, database_path: Path | str | None = None) -> Registry:
    """Read provider state without writing; a missing database uses the file."""
    try:
        import sd_lib  # noqa: PLC0415 - so "unavailable" below means both tries failed (sd:746)
        sd_lib.import_sd_db()
        from sd_db import database  # noqa: PLC0415 - optional at runtime
        from sd_db.errors import SdDbError  # noqa: PLC0415
    except ImportError:
        if database_path is not None or registry_path(home).with_name("sd.db").exists():
            raise RegistryError("provider state exists but sd_db is unavailable; provision the library") from None
        return read_file(target)
    explicit = database_path is not None
    database_path = Path(database_path) if database_path is not None else database.default_path(home)
    if not database_path.exists():
        if explicit:
            raise RegistryError(f"configured provider database is missing: {database_path}")
        return read(target)
    try:
        with closing(database.connect(database_path, write=False)) as connection:
            return read(target, connection=connection)
    except (OSError, sqlite3.Error, SdDbError) as error:
        raise RegistryError(f"cannot read provider state at {database_path}: {error}") from None


def _adapt(registry: Any, meter_envs: Mapping[str, str | None] | None = None) -> Registry:
    """`sd_db`'s registry in this module's shapes.

    The two carry the same fields by construction; converting rather than
    re-exporting means one caller-visible type, so a caller cannot come to
    depend on whichever one the machine happened to produce. `meter_envs`
    is the file's `meter_env` per bill, handed in by `read` when the
    library's `Bill` does not carry the field.
    """
    # The rows can carry a cap the file does not (`sd_db.registry.merge`), so
    # the bound's inputs are checked here as well as in `_provider`: a `url`
    # entry the dashboard capped is refused the same way on the merged read.
    for provider in registry.providers.values():
        bill = registry.bills.get(provider.bill)
        if provider.url and bill is not None and bill.capped:
            refuse_unbounded(provider.name, provider.bill, provider.max_tokens, dict(provider.price), Path(registry.path))
    return Registry(
        path=Path(registry.path),
        bills={
            name: Bill(
                name=bill.name,
                cost_basis=bill.cost_basis,
                cap_usd_month=bill.cap_usd_month,
                meter=bill.meter,
                meter_env=getattr(bill, "meter_env", None) if meter_envs is None else meter_envs.get(name),
            )
            for name, bill in registry.bills.items()
        },
        providers={
            name: Provider(
                name=provider.name,
                vendor=provider.vendor,
                bill=provider.bill,
                start=provider.start,
                url=provider.url,
                model=provider.model,
                reader=provider.reader,
                max_tokens=provider.max_tokens,
                thinking=getattr(provider, "thinking", None),
                reasoning_effort=getattr(provider, "reasoning_effort", None),
                price=dict(provider.price),
                env=tuple(provider.env),
                roles=tuple(provider.roles),
                enabled=provider.enabled,
                reason=provider.reason,
                ranks=dict(provider.ranks),
            )
            for name, provider in registry.providers.items()
        },
    )


def _file_meter_envs(target: Path) -> dict[str, str | None]:
    """`meter_env` per bill, from the file's bills section alone.

    Not `read_file`: that runs every provider check of this reader over a
    file the library has already accepted, and the two readers do not refuse
    the same things. The field is typed here as `parse` types it.
    """
    try:
        bills = _document(target.read_text(encoding="utf-8"), target).get("bills", {})
    except (OSError, RegistryError):
        return {}
    found: dict[str, str | None] = {}
    for name, body in bills.items():
        value = body.get("meter_env") if isinstance(body, dict) else None
        if value is not None:
            _typed(value, str, f"'meter_env' of bill {name!r}", "a variable name", target)
        found[name] = value
    return found


def read_file(path: Path | str) -> Registry:
    """The file alone, for a checkout with no database."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        raise RegistryError(f"no provider registry at {target}") from None
    return parse(text, target)


# The file


def _uncomment(text: str) -> str:
    """Drop a `#` comment, ignoring one inside a quoted scalar."""
    quote = ""
    for index, character in enumerate(text):
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
            continue
        if character == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index]
    return text


def _depth(text: str) -> int:
    """How far a line leaves a flow value open, brackets outside quotes."""
    quote, open_count = "", 0
    for character in text:
        if quote:
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
        elif character in "{[":
            open_count += 1
        elif character in "}]":
            open_count -= 1
    return open_count


def _scalar(text: str) -> Any:
    """A bare word, a quoted string, a constant, or a number."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.lower() in _CONSTANTS:
        return _CONSTANTS[text.lower()]
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _split(text: str, line: int) -> list[str]:
    """Split on commas that are not inside a nested flow or a quote."""
    parts, depth, quote, current = [], 0, "", ""
    for character in text:
        if quote:
            current += character
            if character == quote:
                quote = ""
            continue
        if character in "\"'":
            quote = character
        elif character in "{[":
            depth += 1
        elif character in "}]":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += character
    if quote:
        raise RegistryError(f"line {line}: a quote is never closed")
    if current.strip():
        parts.append(current)
    return [part for part in parts if part.strip()]


def _value(text: str, line: int) -> Any:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        body: dict[str, Any] = {}
        for part in _split(text[1:-1], line):
            key, _, rest = part.partition(":")
            if not _:
                raise RegistryError(f"line {line}: {part.strip()!r} has no ':'")
            if key.strip() in body:
                raise RegistryError(
                    f"line {line}: {key.strip()!r} twice in one mapping"
                )
            body[key.strip()] = _value(rest, line)
        return body
    if text.startswith("[") and text.endswith("]"):
        return [_value(part, line) for part in _split(text[1:-1], line)]
    if text.startswith(("{", "[")):
        raise RegistryError(f"line {line}: a flow value is never closed")
    return _scalar(text)


def _document(text: str, path: Path) -> dict[str, dict[str, Any]]:
    """The three sections, each a mapping of name to flow value.

    Block sequences, deeper nesting and every other YAML feature are refused
    rather than guessed at: a registry that needs one has outgrown this file,
    and saying so is more use than a silent misparse.
    """
    sections: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    pending, start = "", 0
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            raise RegistryError(f"{path}: line {number}: a tab, which YAML refuses")
        line = _uncomment(raw).rstrip()
        if not line.strip():
            continue
        if pending:
            pending += " " + line.strip()
            if _depth(pending) > 0:
                continue
            line, number = pending, start
            pending = ""
        elif _depth(line) > 0:
            pending, start = line, number
            continue
        indented = line[:1] in (" ",)
        key, separator, rest = line.strip().partition(":")
        if not separator:
            raise RegistryError(f"{path}: line {number}: {line.strip()!r} has no ':'")
        if not indented:
            if key.strip() in sections:
                raise RegistryError(
                    f"{path}: line {number}: a second {key.strip()!r} section. "
                    f"The later one would silently replace the first."
                )
            current = {}
            sections[key.strip()] = current
            if rest.strip():
                raise RegistryError(
                    f"{path}: line {number}: {key.strip()!r} is a section and "
                    f"carries a value"
                )
            continue
        if current is None:
            raise RegistryError(f"{path}: line {number}: an entry before any section")
        if key.strip() in current:
            raise RegistryError(
                f"{path}: line {number}: a second {key.strip()!r} entry. The "
                f"later one would silently replace the first, so the file "
                f"would not say what it appears to say."
            )
        current[key.strip()] = _value(rest, number)
    if pending:
        raise RegistryError(f"{path}: line {start}: a flow value is never closed")
    return sections


def parse(text: str, path: Path | str = REGISTRY_NAME) -> Registry:
    """Read the file. Every refusal happens here, before any caller."""
    path = Path(path)
    document = _document(text, path)
    for section in ("bills", "providers", "roles"):
        if section not in document:
            raise RegistryError(f"{path}: no {section!r} section")

    bills: dict[str, Bill] = {}
    for name, body in document["bills"].items():
        if not isinstance(body, dict) or "cost" not in body:
            raise RegistryError(f"{path}: bill {name!r} has no 'cost'")
        for key, kind, form in (
            ("cost", str, "a cost basis"),
            ("meter", str, "a meter name"),
            ("meter_env", str, "a variable name"),
            ("cap_usd_month", (int, float), "an amount"),
        ):
            if body.get(key) is not None:
                _typed(body[key], kind, f"{key!r} of bill {name!r}", form, path)
        # `meter:` without `meter_env:` reads: the meter step caps the bill
        # naming the missing field (owner decision, sd:788 note 2694), since a
        # reinstall never rewrites the operator's file and a read-time refusal
        # would refuse every review after an upgrade until it was hand-edited.
        bills[name] = Bill(
            name=name,
            cost_basis=str(body["cost"]),
            cap_usd_month=body.get("cap_usd_month"),
            meter=body.get("meter"),
            meter_env=body.get("meter_env"),
        )

    role_lists: dict[str, list[str]] = {}
    for role in ROLES:
        if role not in document["roles"]:
            raise RegistryError(
                f"{path}: the 'roles' section has no {role!r} list. The list "
                f"is the order, so without one no entry holds the role however "
                f"many declare it. Write `{role}: []` to mean nobody."
            )
    for role, names in document["roles"].items():
        if role not in ROLES:
            raise RegistryError(f"{path}: no role {role!r}")
        if not isinstance(names, list):
            raise RegistryError(f"{path}: role {role!r} is not a list")
        ordered = [str(name) for name in names]
        repeated = sorted({name for name in ordered if ordered.count(name) > 1})
        if repeated:
            raise RegistryError(
                f"{path}: the {role!r} list names {repeated} more than once. "
                f"The list is an order, and a name cannot be in two places in "
                f"one."
            )
        role_lists[role] = ordered

    providers: dict[str, Provider] = {}
    for name, body in document["providers"].items():
        if not isinstance(body, dict):
            raise RegistryError(f"{path}: provider {name!r} is not a mapping")
        providers[name] = _provider(name, body, bills, role_lists, path)

    for role, names in role_lists.items():
        unknown = [name for name in names if name not in providers]
        if unknown:
            raise RegistryError(
                f"{path}: the {role!r} list names {unknown}, which the "
                f"'providers' section does not"
            )
        without = [name for name in names if role not in providers[name].roles]
        if without:
            raise RegistryError(
                f"{path}: the {role!r} list names {without}, whose entries do "
                f"not declare that role. A list may be a subset of the "
                f"providers holding a role; it may not add one."
            )

    registry = Registry(path=path, bills=bills, providers=providers)
    _refuse_author_reviewing(registry)
    return registry


def _typed(
    value: Any, kind: type | tuple[type, ...], what: str, form: str, path: Path
) -> Any:
    """Return a correctly typed value or name the required shape.

    Validate before constructing Provider: an env scalar once became individual
    variable names, corrupting both fingerprint and credential lookup.
    """
    if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
        raise RegistryError(f"{path}: {what} is {value!r}, which is not {form}")
    return value


def reasoning_controls(body: dict[str, Any], path: Path, name: str) -> dict[str, Any]:
    """Explicit URL controls; omitted fields leave the endpoint default intact."""
    controls = {}
    for key, values in (("thinking", ("disabled", "adaptive")),
                        ("reasoning_effort", ("none", "low", "high", "max"))):
        value = body.get(key)
        if value is not None:
            if not isinstance(value, str) or value not in values or not body.get("url"):
                raise RegistryError(f"{path}: provider {name!r} needs a URL and {key} in {values}")
            controls[key] = value
    if len(controls) > 1:
        raise RegistryError(f"{path}: provider {name!r} must choose one reasoning control")
    return controls


def refuse_unbounded(name: str, bill: str, max_tokens: Any, price: Mapping[str, Any], path: Path) -> None:
    """A `url` entry on a capped bill whose bound the ledger could not hold.

    The cap is held by reserving the call's bound before the request, the
    prompt's estimated tokens at `price.in` plus `max_tokens` at `price.out`
    (sd:788, `design.md`, the bound). The predicate is `sd_db.calls`'s, which
    refuses the same entry again at the call and treats what it cannot use
    as missing: a price is a finite non-negative number, `max_tokens` a
    whole number above zero. Refused here at read, naming the entry, the key
    and the value, the way a `start` entry on a capped bill is: a registry
    the cap cannot hold is refused before a call is planned, and the message
    is this reader's own rather than the library's.
    """
    faults = {"max_tokens": max_tokens} if type(max_tokens) is not int or max_tokens <= 0 else {}
    for side in ("in", "out"):
        value = price.get(side)
        try:
            usable = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 and abs(float(value)) < float("inf")
        except OverflowError:  # an int too large for a float, which the library cannot price either
            usable = False
        if not usable:
            faults[f"price.{side}"] = value
    if faults:
        named = ", ".join(f"{key} is {value!r}" for key, value in faults.items())
        raise RegistryError(
            f"{path}: provider {name!r} is a 'url' entry on the capped bill "
            f"{bill!r} and {named}. A cap is held by reserving the call's bound "
            f"before it is sent, which needs price.in and price.out as finite "
            f"non-negative numbers per million tokens and max_tokens as a "
            f"whole number above zero. Give the entry those, or move it to an "
            f"uncapped bill."
        )


def _provider(
    name: str,
    body: dict[str, Any],
    bills: dict[str, Bill],
    role_lists: dict[str, list[str]],
    path: Path,
) -> Provider:
    where = f"provider {name!r}"
    for key, kind, form in (
        ("start", str, "a command line"),
        ("url", str, "a url"),
        ("vendor", str, "a name"),
        ("bill", str, "the name of a bill"),
        ("model", str, "a model name"),
        ("reader", str, "the name of a reader"),
        ("reason", str, "a sentence"),
        ("max_tokens", int, "a whole number"),
        ("env", list, "a list of variable names"),
        ("price", dict, "a mapping"),
        ("roles", list, "a list of role names"),
    ):
        if body.get(key) is not None:
            _typed(body[key], kind, f"{key!r} of {where}", form, path)

    start, url = body.get("start"), body.get("url")
    if bool(start) == bool(url):
        raise RegistryError(
            f"{path}: provider {name!r} needs exactly one of 'start' or 'url'; "
            f"it has " + ("both" if start else "neither")
        )
    if url and not urlsplit(str(url)).netloc:
        raise RegistryError(
            f"{path}: provider {name!r} has url {url!r}, which names no host. "
            f"A url entry's recipient is its host, and consent is granted to "
            f"that host, so an entry without one could never be consented to."
        )
    # A cleartext scheme is refused by `refuse_allowance`, not here. It is a
    # consent question rather than a shape question, and the two readers must
    # answer it identically: `_adapt` builds providers from `sd_db`'s rows
    # without ever passing through this function, so a check here would fire
    # only on the machines with no database.
    if "bill" not in body:
        raise RegistryError(f"{path}: provider {name!r} has no 'bill'")
    bill_name = str(body["bill"])
    if bill_name not in bills:
        raise RegistryError(
            f"{path}: provider {name!r} is billed to {bill_name!r}, which the "
            f"'bills' section does not name"
        )
    if bills[bill_name].capped and start:
        raise RegistryError(
            f"{path}: provider {name!r} is a 'start' entry on the capped bill "
            f"{bill_name!r}. A cap is enforced by refusing a call before it is "
            f"sent, which nothing can do for a spawned command, so the cap "
            f"would be a number nothing enforces. Give it a 'url', or move it "
            f"to an uncapped bill."
        )
    if url and bills[bill_name].capped:
        refuse_unbounded(name, bill_name, body.get("max_tokens"), body.get("price") or {}, path)
    if start and str(start).strip():
        first = executable(str(start))
        if not first:
            raise RegistryError(
                f"{path}: provider {name!r} has start {start!r}, which names "
                f"no program to run."
            )
        if first.startswith("-"):
            raise RegistryError(
                f"{path}: provider {name!r} has start {start!r}, whose first "
                f"word {first!r} is a flag. The runner takes the first word as "
                f"the program, so this entry would try to execute a flag."
            )
    if start and not body.get("reader"):
        raise RegistryError(
            f"{path}: provider {name!r} is a 'start' entry with no 'reader'. "
            f"Running one means parsing what the command prints, so an entry "
            f"that does not say how could be selected and never read."
        )
    if "vendor" not in body:
        raise RegistryError(f"{path}: provider {name!r} has no 'vendor'")
    vendor = str(body["vendor"])
    if vendor != vendor.strip().lower():
        raise RegistryError(
            f"{path}: provider {name!r} has vendor {vendor!r}. A vendor is "
            f"compared against a commit trailer by exact match, so one with "
            f"padding or a capital could never match, and the entry would "
            f"review work its own vendor wrote. Write it lower case."
        )

    enabled = body.get("enabled", True)
    if not isinstance(enabled, bool):
        raise RegistryError(
            f"{path}: provider {name!r} has enabled={enabled!r}, which is not "
            f"true or false. 'no', 'off' and a quoted 'false' are strings "
            f"here, and every non-empty string is true, so the entry would "
            f"stay on. Write true or false, unquoted."
        )

    declared = body.get("roles")
    if declared is None:
        roles = tuple(role for role in ROLES if name in role_lists.get(role, []))
    else:
        claimed = {str(role) for role in declared}
        if claimed - set(ROLES):
            raise RegistryError(
                f"{path}: provider {name!r} claims role(s) "
                f"{sorted(claimed - set(ROLES))}"
            )
        roles = tuple(role for role in ROLES if role in claimed)
    return Provider(
        name=name,
        vendor=vendor,
        bill=bill_name,
        start=start or None,
        url=url or None,
        model=body.get("model"),
        reader=body.get("reader"),
        max_tokens=body.get("max_tokens"),
        **reasoning_controls(body, path, name),
        price=dict(body.get("price") or {}),
        env=tuple(str(variable) for variable in (body.get("env") or ())),
        roles=roles,
        enabled=enabled,
        reason=body.get("reason"),
        ranks={
            role: role_lists[role].index(name)
            for role in roles
            if name in role_lists.get(role, [])
        },
    )


def _refuse_author_reviewing(registry: Registry) -> None:
    """Checked on what resolves, not on the whole lists.

    The lists overlap on purpose -- an entry may hold both roles, and two do --
    as long as the one at the top of each is not the same one.
    """
    resolved = {}
    for role in ROLES:
        order = registry.order(role)
        if order:
            resolved[role] = order[0].name
    if len(resolved) == len(ROLES) and len(set(resolved.values())) == 1:
        name = next(iter(resolved.values()))
        raise RegistryError(
            f"{registry.path}: {name!r} is first in both the 'author' and the "
            f"'reviewer' list, so a review would be by the author. Reorder one "
            f"list, or disable the entry for one role."
        )


# Capability comes from the registry; permission comes from operator policy.
# Local pairs restrict destinations to a host or executable/command fingerprint.
# Standing configured-provider consent follows current registry entries instead.


#: `<entry>@<recipient>`, and for a `start` entry `<entry>@<executable>+<hash>`.
CONSENT_SEPARATOR = "@"
FINGERPRINT_JOIN = "+"
FINGERPRINT_LENGTH = 8

#: What ends a pair on the line. One definition, read by the lexer in
#: `consent_parts` and by the quoting in `Allowance.__str__`: the two held
#: separate lists once, and the writer's list was missing the comma the
#: reader's list split on.
CONSENT_WHITESPACE = " \t\n\r,"

_HEX = re.compile(r"[0-9a-f]+")


class ConsentRefusal(RegistryError):
    """This repository has not allowed this entry to receive its diff."""


def _one_word(recipient: str) -> str:
    """Quote a recipient so consent_parts reads exactly one word.

    shlex.quote alone leaves commas unquoted, but consent_parts splits them.
    Quote our separators explicitly; retain shlex handling of quotes and #.
    Otherwise one recipient can become an unintended host and another entry.
    """
    if any(character in recipient for character in CONSENT_WHITESPACE):
        return "'" + recipient.replace("'", "'\"'\"'") + "'"
    return shlex.quote(recipient)


def _split_fingerprint(tail: str) -> tuple[str, str]:
    """`<recipient>+<hash>` as its two halves, or the whole of it as one.

    From the right, and only for a hash shaped like one: `partition` took the
    *first* `+`, so a recipient holding one -- `g++`, a versioned path -- lost
    everything after it and consented to a program with a different name.
    """
    head, join, digest = tail.rpartition(FINGERPRINT_JOIN)
    if join and len(digest) == FINGERPRINT_LENGTH and _HEX.fullmatch(digest):
        return head, digest
    return tail, ""


@dataclass(frozen=True)
class Allowance:
    """One pair off the `reviewers` line."""

    entry: str
    recipient: str
    fingerprint: str | None = None

    def __str__(self) -> str:
        """Render one allowance that parse_consent reads back unchanged.

        TheRoundTrip tests this boundary: splitting a pair can authorize another host.
        """
        tail = f"{FINGERPRINT_JOIN}{self.fingerprint}" if self.fingerprint else ""
        return f"{self.entry}{CONSENT_SEPARATOR}{_one_word(self.recipient)}{tail}"


def resolve_consent(registry: Registry, line: str | None, policy: str | None) -> tuple[dict[str, Allowance], str]:
    """Explicit local restrictions override standing configured-provider consent."""
    if policy not in (None, "configured", "deny"):
        raise ConsentRefusal("invalid external review authorization")
    if policy == "deny":
        return {}, "machine-deny"
    if line is not None:
        return parse_consent(line), "repository"
    if policy == "configured":
        # Consent permits transmission; role ranks control automatic selection.
        return {
            entry.name: recipient(entry)
            for entry in registry.providers.values()
            if entry.enabled and "reviewer" in entry.roles
        }, "machine-configured"
    return parse_consent(None), "none"


def parse_consent(line: str | None) -> dict[str, Allowance]:
    """Parse a local allowance list. Empty denies; absence needs standing policy."""
    if line is None:
        raise ConsentRefusal(
            "no standing authorization or repository 'reviewers' line in CLAUDE.local.md; "
            "no reviewer resolves. Set sd.external_reviews only with operator consent, "
            "or use the installer with --reviewers for a local restriction."
        )
    allowances: dict[str, Allowance] = {}
    for part in consent_parts(line):
        if CONSENT_SEPARATOR not in part:
            raise ConsentRefusal(
                f"{part!r} on the 'reviewers' line is a bare name. Each entry "
                f"names its recipient too -- "
                f"`entry{CONSENT_SEPARATOR}host` for a url entry, "
                f"`entry{CONSENT_SEPARATOR}executable{FINGERPRINT_JOIN}fingerprint` "
                f"for a start entry -- because consent is to a destination and "
                f"not to a name that could be repointed at one."
            )
        # The first separator splits, and only the first: a url entry's
        # recipient is its netloc, which carries any userinfo the url had, so
        # `p@user:pw@host` is one well-defined pair and not an ambiguous one.
        entry, _, recipient = part.partition(CONSENT_SEPARATOR)
        recipient, fingerprint = _split_fingerprint(recipient)
        if not entry or not recipient:
            raise ConsentRefusal(
                f"{part!r} on the 'reviewers' line has an empty "
                + ("entry" if not entry else "recipient")
                + ". Consent is one named entry reaching one named "
                "destination, and half a pair names neither."
            )
        if entry in allowances:
            raise ConsentRefusal(
                f"the 'reviewers' line names {entry!r} twice, as "
                f"{allowances[entry].recipient!r} and {recipient!r}. The later "
                f"one silently won, so the line granted a destination the "
                f"person reading it had no reason to expect."
            )
        allowances[entry] = Allowance(entry, recipient, fingerprint or None)
    return allowances


def consent_parts(line: str) -> list[str]:
    """Split reviewer pairs on unquoted commas and whitespace.

    Use the start-line quoting rules so an executable containing spaces can
    round-trip through consent; plain str.split makes that consent unreadable.
    """
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace = CONSENT_WHITESPACE
    lexer.whitespace_split = True
    # `shlex` treats `#` as a comment by default, which quietly truncated a
    # recipient that held one: `codex@codex#x` consented to `codex`. Nothing
    # on this line is a comment.
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as error:
        raise ConsentRefusal(
            f"the 'reviewers' line cannot be read: {error}. A recipient with a "
            f"space in it is quoted, the way it is on a 'start' line."
        ) from error


def fingerprint(provider: Provider) -> str:
    """Digest a start entry's command line and environment variable names.

    Never hash secret values into a public consent record. Changed arguments
    or declared variables invalidate a local pair, even for the same executable.
    """
    material = "\n".join([provider.start or "", *sorted(provider.env)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


def executable(start: str) -> str:
    """The program a `start` line runs, split the way the runner splits it.

    `shlex`, not `str.split`. `bin/sd-review` builds its argv with `shlex`, so
    a quoted path with a space in it -- `"/opt/my tools/codex" exec` -- would
    otherwise be consented to as `"/opt/my` and run as `/opt/my tools/codex`:
    consent to a string nobody executes, and an executable nobody consented to.
    """
    try:
        words = shlex.split(start)
    except ValueError:
        # An unbalanced quote is not a program name. Raising here would refuse
        # at read time for every caller, including the ones only listing the
        # registry; an empty name fails the consent comparison instead, which
        # is the same answer at the point where it matters.
        return ""
    return words[0] if words else ""


def recipient(provider: Provider) -> Allowance:
    """What the `reviewers` line must name for this entry, as it stands now."""
    if provider.url:
        return Allowance(provider.name, urlsplit(provider.url).netloc)
    return Allowance(provider.name, executable(provider.start or ""), fingerprint(provider))


def refuse_allowance(provider: Provider, allowed: Allowance | None) -> str | None:
    """Why this entry may not receive the diff, or `None` when it may.

    Returns rather than raises: the chain reports every entry it passed over
    and why, and an exception would let it report only the first.
    """
    cleartext = refuse_cleartext(provider)
    if cleartext is not None:
        # First, and here rather than at the run: this is a consent question --
        # the line names a host and cannot name a scheme -- so the chain, the
        # dry run and the run have to give the same answer, and an entry the
        # chain refuses never reaches the code that could send to it.
        return cleartext
    if allowed is None:
        return (
            f"{provider.name} is not allowed by the effective review authorization. "
            f"Check machine sd.external_reviews and the local 'reviewers' restriction."
        )
    current = recipient(provider)
    if allowed.recipient != current.recipient:
        kind = "host" if provider.url else "executable"
        return (
            f"{provider.name} is allowed to reach the {kind} "
            f"{allowed.recipient!r} and the registry now points it at "
            f"{current.recipient!r}. Rewrite the 'reviewers' line if that is "
            f"where this repository's diff should go."
        )
    # Checked when the line carries one, and not required. The installer writes
    # the fingerprint for every `start` entry it offers, so a line without one
    # is a line written by hand, and that is allowed to be the weaker
    # statement it looks like: this executable, whatever it is asked to do.
    # Requiring it would make the shorter form -- which `WORKFLOW.md` and the
    # criteria both use in prose -- refuse every entry it names.
    if allowed.fingerprint and allowed.fingerprint != current.fingerprint:
        return (
            f"{provider.name} is allowed as {allowed} and its start line or "
            f"'env' list now fingerprints as {current.fingerprint}. The "
            f"executable is the same one; what it is asked to do is not."
        )
    return None


def refuse_reader(provider: Provider, readers: tuple[str, ...]) -> str | None:
    """Return this build's reader refusal, or None.

    The chain, dry run, and execution share this decision and wording.
    Only process entries name readers; URL entries spawn no process.
    """
    if not readers:
        return None
    if provider.url:
        # Nothing to check, so nothing to refuse: a `url` entry names no reader
        # because one client and one reader serve all of them, and `readers`
        # lists what parses a spawned command's output. Falling through instead
        # would test `None not in readers` and refuse every one of them.
        return None
    if provider.reader not in readers:
        return (
            f"{provider.name} reads back as {provider.reader!r}, and this "
            f"build implements no such reader."
        )
    return None


def refuse_environment(provider: Provider, environ: Mapping[str, str]) -> str | None:
    """Refuse URL-valued variables passed to a spawned session.

    A declared key grants credentials, not an additional destination absent
    from repository consent. Report the variable name without its value.
    URL entries are exempt because no process inherits their environment.
    """
    if provider.url:
        return None
    for name in provider.env:
        value = environ.get(name, "")
        if value.startswith(("http://", "https://")):
            return (
                f"{provider.name} would receive {name}, whose value in this "
                f"environment is a URL. A start entry's recipient is the one the "
                f"'reviewers' line names; a variable carrying another is a second "
                f"destination nobody consented to. No session was started."
            )
    return None


def loopback_url(url: str) -> bool:
    """Whether this URL's host is the machine the pack runs on."""
    # `hostname` has already stripped the brackets from `[::1]` and
    # lowercased, so a literal address arrives here ready to parse.
    host = (urlsplit(url).hostname or "").lower()
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def loopback(provider: Provider) -> bool:
    """Whether a url entry's recipient is this machine.

    Use ipaddress or exact localhost, never a 127. prefix: 127.evil.com and
    127.0.0.1.evil.com are public DNS names. Refuse abbreviated 127.1 too;
    curl accepts it, but adding a second address parser weakens this boundary.

    One parse, read by both rules that care where a url entry points: the
    cleartext rule below, and the credential rule in `chat_completion`. Two
    copies of an address test are two chances to disagree about what counts
    as this machine, and the pair that disagrees is the pair that sends a
    diff somewhere unintended.

    `sd_db.calls` carries the same pair for the ledger's own call path,
    which is the one a run with a database takes; `chat_completion` here is
    the seam a run without one falls back to. Both had to learn this, and a
    fix to one alone leaves `--preflight` refusing.
    """
    return loopback_url(provider.url) if provider.url else False


def refuse_cleartext(provider: Provider) -> str | None:
    """Refuse cleartext outside loopback; never silently upgrade the URL.

    Host consent excludes the scheme, so changing https to http can otherwise
    expose the diff without changing its recipient. The configured scheme
    must remain explicit. A local socket is the loopback exception.
    """
    if not provider.url:
        return None
    parts = urlsplit(provider.url)
    if parts.scheme == "https" or loopback(provider):
        return None
    return (
        f"{provider.name} points at {provider.url!r}, which reaches "
        f"{parts.netloc!r} in the clear. Consent names a host and not a "
        f"scheme, so this edit would pass the 'reviewers' line and send this "
        f"repository's diff unencrypted. Give it 'https', or a loopback host."
    )


# The one client for `url` entries, and the one reader for their answers

#: The second seam `bin/sd-review` injects, beside its runner. A test hands in
#: a recorder and asserts on what left -- including, for a refused entry, that
#: nothing did.
ClientResult = tuple[int, str, str, bool] | tuple[int, str, str, bool, int | None]
Client = Callable[[Provider, str, Mapping[str, str], int], ClientResult]


def endpoint(provider: Provider) -> str:
    """Where `chat_completion` will POST. One definition, so a dry run cannot
    print an endpoint the client does not use."""
    return f"{str(provider.url).rstrip('/')}{CHAT_COMPLETIONS}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is a second recipient the `reviewers` line never named, and
    urllib follows one by default, carrying `Authorization` to whichever host
    the answer points at. `None` turns the 3xx into a reported `HTTPError`."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)

#: For a recipient on this machine. `build_opener` installs a `ProxyHandler`
#: that reads `HTTP_PROXY` at import, and urllib's bypass list does not
#: special-case loopback: on a box where `HTTP_PROXY` is set and `NO_PROXY`
#: omits `localhost`, a loopback request is forwarded to the proxy and the
#: diff leaves the machine. An empty mapping installs no proxy at all -- and
#: `build_opener` drops it rather than registering an inert one -- so the
#: socket goes where the URL says. A public host keeps `_OPENER`, because a
#: proxy is how it is reachable at all on such a box.
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def _opener(url: str):
    """The opener for this URL: proxy-free for this machine, default beyond."""
    return _DIRECT_OPENER if loopback_url(url) else _OPENER


def chat_completion(
    provider: Provider,
    prompt: str,
    environ: Mapping[str, str],
    timeout: int,
) -> tuple[int, str, str, bool, int | None]:
    """POST one review through the injected OpenAI-compatible transport.

    Return Completed-compatible fields without importing sd-review: raw body
    in stdout, status-only HTTP errors in stderr, observed HTTP status last.
    A missing response sets
    launched=False; an HTTP429 response remains distinct from connection failure.
    """
    refusal = refuse_cleartext(provider)
    if refusal is not None:
        return (1, "", refusal, False, None)
    name = provider.env[0] if provider.env else ""
    key = environ.get(name, "")
    # A locally hosted server reached over loopback is already restricted to
    # processes running as this user, so a key adds nothing the socket did
    # not require. Demanding one kept every such entry unreachable: the
    # registry has no way to spell "this recipient authenticates nobody", and
    # a placeholder variable exported to satisfy the check would be a secret
    # in name only. An entry that does declare a variable still has to supply
    # its value, loopback or not, because a server that was configured to
    # check a key must not be called without one.
    if not key and not (loopback(provider) and not provider.env):
        return (1, "", f"{provider.name} has no value for {name or 'any key'}", False, None)
    request_body: dict[str, Any] = {"model": provider.model, "max_tokens": provider.max_tokens,
                            "messages": [{"role": "user", "content": prompt}]}
    if provider.thinking is not None:
        request_body["thinking"] = {"type": provider.thinking}
    if provider.reasoning_effort is not None:
        request_body["reasoning_effort"] = provider.reasoning_effort
    payload = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        endpoint(provider),
        data=payload,
        headers={**({"Authorization": f"{AUTH_SCHEME} {key}"} if key else {}),
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _opener(request.full_url).open(request, timeout=timeout) as answer:
            status = getattr(answer, "status", None)
            status = status if type(status) is int and 100 <= status <= 599 else None
            body = answer.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return (1, body.decode("utf-8", "replace"), "response exceeds the declared byte limit", True, status)
            return (0, body.decode("utf-8", "replace"), "", True, status)
    except urllib.error.HTTPError as error:
        with error:
            body = error.read(MAX_RESPONSE_BYTES + 1).decode("utf-8", "replace")
        return (error.code, body, f"HTTP {error.code} from {provider.name}", True, error.code)
    except OSError as error:
        # `URLError` and a timeout are both `OSError`; neither is an answer, so
        # neither may read as a quota stop however the message is worded.
        return (1, "", f"{provider.name}: {error}", False, None)


# The meter: one pinned GET per metered bill at review start (sd:788 slice 4)

#: The one destination a `meter:` may name: scheme, host, port and path. The
#: value is a shipped string a live GET would send the bill's key to, so an
#: edited registry pointing it elsewhere is refused before any request. The
#: key is named on the bill (`Bill.meter_env`) and not on an entry: several
#: entries can share one bill, and a credential chosen by registry order is
#: chosen by accident.
METER_PIN = ("https", "www.minimax.io", None, "/v1/token_plan/remains")
#: The `model_remains` entry the text model draws from, and the two fields
#: read off it: each a remaining percent, and the row stores the share used.
METER_PLAN = "general"
METER_FIELDS = ("current_interval_remaining_percent", "current_weekly_remaining_percent")

#: The third seam `bin/sd-review` injects: the reader of the meter, handed a
#: bill and answering as `chat_completion` does, so a test records what left.
Meter = Callable[[Bill, Mapping[str, str], int], ClientResult]


def refuse_meter(bill: Bill) -> str | None:
    """A `meter:` that is not the pin, naming the value and the pinned four.

    Compared part by part rather than as one string, so the same-host
    `http://` value is refused the way `refuse_cleartext` refuses a `url`
    entry, and a port or a path edit is named as what it is.
    """
    if bill.meter is None:
        return None
    parts = urlsplit(bill.meter)
    try:
        port = parts.port
    except ValueError:
        port = -1
    # A query or a fragment rides on the path: the pin names none.
    tail = (f"?{parts.query}" if parts.query else "") + (f"#{parts.fragment}" if parts.fragment else "")
    found = (parts.scheme.lower(), (parts.hostname or "").lower(), port, parts.path + tail)
    if found == METER_PIN:
        return None
    what = ("scheme", "host", "port", "path")[[a != b for a, b in zip(found, METER_PIN, strict=True)].index(True)]
    return (
        f"bill {bill.name!r} names meter {bill.meter!r}, whose {what} is not "
        f"the pinned meter's: scheme 'https', host 'www.minimax.io', no explicit "
        f"port, path '/v1/token_plan/remains'. No request was sent."
    )


def meter_reading(bill: Bill, environ: Mapping[str, str], timeout: int) -> tuple[int, str, str, bool, int | None]:
    """GET the pinned meter with the bill's key, in `chat_completion`'s shape.

    Refused before any request when the value is not the pin or no key is
    named or set. An `OSError` is not an answer: `launched` is False and the
    caller classifies on the rows it already holds.
    """
    refusal = refuse_meter(bill)
    if refusal is None and not bill.meter_env:
        refusal = f"bill {bill.name!r} carries meter: and no meter_env:, so no variable names the key the reading sends"
    if refusal is not None:
        return (1, "", refusal, False, None)
    key = environ.get(str(bill.meter_env), "")
    if not key:
        return (1, "", f"bill {bill.name!r} has no value for {bill.meter_env}", False, None)
    request = urllib.request.Request(str(bill.meter), headers={"Authorization": f"{AUTH_SCHEME} {key}"}, method="GET")
    try:
        with _opener(request.full_url).open(request, timeout=timeout) as answer:
            status = getattr(answer, "status", None)
            status = status if type(status) is int and 100 <= status <= 599 else None
            body = answer.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return (1, body.decode("utf-8", "replace"), "response exceeds the declared byte limit", True, status)
            return (0, body.decode("utf-8", "replace"), "", True, status)
    except urllib.error.HTTPError as error:
        with error:
            body = error.read(MAX_RESPONSE_BYTES + 1).decode("utf-8", "replace")
        return (error.code, body, f"HTTP {error.code} from the meter of bill {bill.name!r}", True, error.code)
    except OSError as error:
        return (1, "", f"the meter of bill {bill.name!r}: {error}", False, None)


def meter_percents(body: str) -> tuple[float, float] | str:
    """The two remaining percents of the one `general` entry, or the sentence
    that says why the answer is not one. Fails closed on the count and on
    each field: missing, a string, a boolean, NaN, an infinity or outside
    0 to 100 is named with its value, and the caller writes no row.
    """
    try:
        answer = json.loads(body)
    except ValueError:
        return "the answer is not JSON"
    remains = answer.get("model_remains") if isinstance(answer, dict) else None
    if not isinstance(remains, list):
        return "the answer carries no model_remains list"
    plans = [entry for entry in remains if isinstance(entry, dict) and entry.get("model_name") == METER_PLAN]
    if len(plans) != 1:
        return f"model_remains carries {len(plans)} {METER_PLAN!r} entries, not one"
    percents = []
    for name in METER_FIELDS:
        if name not in plans[0]:
            return f"{name} is missing"
        value = plans[0][name]
        # `0 <= nan` is False, so NaN falls with the infinities and the range.
        if type(value) not in (int, float) or not 0 <= value <= 100:
            return f"{name} is {value!r}, not a number from 0 to 100"
        percents.append(float(value))
    return (percents[0], percents[1])


# Inline thinking: strip every block, case-insensitively, allowing opening
# attributes. Nested blocks are unsupported and remain nonpassing. An unclosed
# block consumes the remainder because truncated reasoning is not an answer.
# Empty or whitespace-only final content also remains nonpassing. Separate
# reasoning never becomes final JSON; see url_response and response tests.
_THINK = re.compile(r"<think\b[^>]*>.*?(?:</think\s*>|\Z)", re.DOTALL | re.IGNORECASE)


def response_value(value: Any) -> dict[str, Any]:
    """Preserve response shape and identity without arbitrary provider text."""
    if isinstance(value, str):
        encoded = value.encode("utf-8", "surrogatepass")
        return {"type": "string", "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest()}
    return {"type": "null" if value is None else "boolean" if type(value) is bool else
            "number" if type(value) in (int, float) else "array" if isinstance(value, list) else
            "object" if isinstance(value, dict) else "other"}


def url_response(body: str) -> tuple[str, dict[str, Any]]:
    """Read bounded response structure; diagnostics never contain model text."""
    encoded = body.encode("utf-8")
    diagnostic: dict[str, Any] = {
        "response_text_bytes": len(encoded),
        "response_text_sha256": hashlib.sha256(encoded).hexdigest(),
        "category": "invalid_envelope",
        "sanitized_response": {"body": response_value(body)},
    }
    if len(encoded) > MAX_RESPONSE_BYTES:
        diagnostic["category"] = "response_limit"
        diagnostic["hash_scope"] = "captured_text_only"
        return "", diagnostic
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        diagnostic["category"] = "invalid_json"
        return "", diagnostic
    if not isinstance(payload, dict):
        return "", diagnostic
    safe = diagnostic["sanitized_response"]
    safe["model"] = response_value(payload.get("model"))
    usage = payload.get("usage")
    safe["usage"] = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                     if isinstance(usage, dict) and type(usage.get(key)) is int and 0 <= usage[key] <= 10**12}
    if payload.get("error") is not None:
        diagnostic["category"] = "api_error"
        error = payload["error"]
        diagnostic["error_fields"] = [key for key in ("code", "type", "message") if isinstance(error, dict) and key in error]
        safe["error"] = {key: response_value(error[key]) for key in diagnostic["error_fields"]}
        return "", diagnostic
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", diagnostic
    safe["choices"] = len(choices)
    first = choices[0]
    reason = first.get("finish_reason")
    diagnostic["finish_reason"] = reason if reason in (None, "stop", "length", "content_filter", "tool_calls", "function_call") else "other"
    message = first.get("message")
    if not isinstance(message, dict):
        return "", diagnostic
    content, reasoning = message.get("content"), message.get("reasoning_content")
    safe["message"] = {"content": response_value(content), "reasoning_content": response_value(reasoning)}
    diagnostic["content_bytes"] = safe["message"]["content"].get("bytes", 0)
    diagnostic["reasoning_bytes"] = safe["message"]["reasoning_content"].get("bytes", 0)
    text = _THINK.sub("", content).strip() if isinstance(content, str) else ""
    diagnostic["content_format"] = "fenced" if text.startswith("```") else "text"
    if reason == "length":
        diagnostic["category"] = "truncated"
    elif reason not in (None, "stop"):
        diagnostic["category"] = "incomplete_finish"
    elif not text:
        diagnostic["category"] = "reasoning_only" if diagnostic["reasoning_bytes"] or isinstance(content, str) and "<think" in content else "empty_content"
    else:
        diagnostic["category"] = "content"
    return text, diagnostic


def url_answer(body: str) -> str:
    """Return final answer text, or an empty string for unreadable output.

    Empty text must fail parsing, never become a clean empty finding list.
    Separate reasoning_content contributes diagnostic lengths only; never
    concatenate it with final JSON. Inline thinking is stripped by url_response.
    """
    return url_response(body)[0]


# The chain


@dataclass(frozen=True)
class Candidate:
    """One entry on the reviewer list, and whether this run may use it."""

    provider: Provider
    eligible: bool
    reason: str = ""

    @property
    def row(self) -> dict[str, Any]:
        """What a report shows: who, on whose money, and whether they may.

        Shaped here rather than at each caller, because a chain that is
        reported differently by the review, the dashboard and the doctor is
        three answers to one question.
        """
        return {
            "provider": self.provider.name,
            "vendor": self.provider.vendor,
            "bill": self.provider.bill,
            "eligible": self.eligible,
            "reason": self.reason,
        }


def _reviewer_candidate(
    provider: Provider,
    *,
    consent: dict[str, Allowance],
    author_vendors: tuple[str, ...],
    capped_bills: Mapping[str, str] | None,
    readers: tuple[str, ...],
) -> Candidate:
    """Apply the same eligibility guards to automatic and explicit selection."""
    refusal = refuse_reader(provider, readers)
    if refusal is None:
        refusal = refuse_allowance(provider, consent.get(provider.name))
    if refusal is None and provider.vendor in author_vendors:
        refusal = (
            f"{provider.name} is an entry of vendor {provider.vendor}, and "
            f"this branch carries {provider.vendor} authorship. The reviewer "
            f"is a different vendor from the author, always."
        )
    if refusal is None and provider.bill in (capped_bills or {}):
        refusal = f"{provider.name} is billed to {provider.bill}: {(capped_bills or {})[provider.bill]}"
    return Candidate(provider, refusal is None, refusal or "")


def reviewer_chain(
    registry: Registry,
    *,
    consent: dict[str, Allowance],
    author_vendors: tuple[str, ...] = (),
    # Bill name to the line the refusal renders, supplied by `review` in
    # `bin/sd-review` (sd:788 slice 3). A cap is spend against
    # `cap_usd_month`, which the ledger sums from `cost` rows, so the
    # file-only reader cannot know it and the caller that holds a connection
    # says which bills are at theirs, with the month's total in the line, or
    # names the fault that kept it from finding out. The registry refuses a
    # `start` entry on a capped bill outright, so the only entries a cap can
    # reach are `url` entries.
    capped_bills: Mapping[str, str] | None = None,
    readers: tuple[str, ...] = (),
) -> list[Candidate]:
    """Return enabled reviewers in order, including eligibility and reasons.

    Mark rather than filter so receipts preserve skipped providers and why.
    This evaluates registry, consent, authorship, and declared caps consistently
    for planning and execution; runtime availability preflight happens later.
    """
    return [
        _reviewer_candidate(
            provider,
            consent=consent,
            author_vendors=author_vendors,
            capped_bills=capped_bills,
            readers=readers,
        )
        for provider in registry.order("reviewer")
    ]


def pick(
    registry: Registry,
    name: str,
    *,
    consent: dict[str, Allowance],
    author_vendors: tuple[str, ...] = (),
    capped_bills: Mapping[str, str] | None = None,
    readers: tuple[str, ...] = (),
) -> Provider:
    """`--provider <name>`: one entry for one run, or a refusal that says why.

    Direct picks can reach enabled reviewers outside the automatic order.
    They retain the same consent, independence, reader, transport, and spending guards.
    Disabled entries remain refused with their recorded reason.
    """
    provider = registry.providers.get(name)
    if provider is None:
        raise RegistryError(
            f"no provider {name!r} in {registry.path}. The registry is the only "
            f"list of providers; add an entry to it rather than a flag here."
        )
    if "reviewer" not in provider.roles:
        raise RegistryError(
            f"{name!r} does not hold the 'reviewer' role, so it cannot review."
        )
    if not provider.enabled:
        raise RegistryError(
            f"{name!r} is disabled: {provider.reason or 'no reason recorded'}"
        )
    candidate = _reviewer_candidate(
        provider,
        consent=consent,
        author_vendors=author_vendors,
        capped_bills=capped_bills,
        readers=readers,
    )
    if not candidate.eligible:
        raise ConsentRefusal(candidate.reason)
    return provider


def select_reviewers(
    registry: Registry,
    name: str | None = None,
    *,
    consent: dict[str, Allowance],
    author_vendors: tuple[str, ...] = (),
    capped_bills: Mapping[str, str] | None = None,
    readers: tuple[str, ...] = (),
) -> list[Provider]:
    """Select one explicit reviewer or the eligible automatic fallback chain."""
    if name is not None:
        return [pick(
            registry, name, consent=consent, author_vendors=author_vendors,
            capped_bills=capped_bills, readers=readers,
        )]
    return [
        candidate.provider
        for candidate in reviewer_chain(
            registry, consent=consent, author_vendors=author_vendors,
            capped_bills=capped_bills, readers=readers,
        )
        if candidate.eligible
    ]
