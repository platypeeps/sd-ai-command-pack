"""The provider registry, as the pack reads it.

`providers.yaml` is the only list of providers anywhere: what a provider is,
whose money pays for it, and which of the two roles -- `author`, `reviewer` --
it may hold. Skills name roles; nothing in `skills/` names a vendor. The file's
format is documented in `WORKFLOW.md`, which is where its rules live.

**Two readers, one answer.** With `sd_db` installed this module delegates to
`sd_db.registry`, which merges the file with the `provider` and `bill` rows so
that a provider disabled from the dashboard is disabled here too. Without it --
a fresh checkout, a CI runner, the installer itself, any machine where
`make setup` has not run -- it reads the file alone. Criterion 32 is the test
that keeps the two honest: both must return the same reviewer order from the
same file. That test is the whole reason a second reader is allowed to exist.

The fallback is deliberately the smaller of the two. It reads what resolution
needs and carries the refusals a caller would otherwise trip over later:

* a provider with both `start` and `url`, or with neither;
* a `start` entry on a capped bill, whose cap would be a number nothing
  enforces -- the library refuses a `url` call before it is sent and cannot
  refuse a spawned command's;
* a name that does not resolve, in either direction;
* `author` and `reviewer` resolving to the same provider, which is a review
  by the author.

It does not reimplement the row merge, the seed, or the parser's full YAML
subset, because a checkout with no database has no rows and this file is the
one document either reader parses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Beside the database, in `~/.local/share/sd/`. The same path `sd_db` uses;
#: stated here rather than imported, because this module answers before the
#: library exists.
REGISTRY_NAME = "providers.yaml"
REGISTRY_RELATIVE = Path(".local/share/sd") / REGISTRY_NAME

#: The two role lists. A third is added to the file and to this tuple, and to
#: nothing else.
ROLES = ("author", "reviewer")

#: A bill with one of these bases has a spend limit something enforces, so
#: every provider on it must be callable by the library rather than spawned.
CAPPED_BASES = ("company", "plan", "prepaid")

_CONSTANTS = {"true": True, "false": False, "null": None, "~": None}


class RegistryError(Exception):
    """A registry that cannot mean anything, refused at read time."""


@dataclass(frozen=True)
class Bill:
    name: str
    cost_basis: str
    cap_usd_month: float | None = None
    meter: str | None = None

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

        Only what a role list ranks resolves. An entry that declares the role
        and appears on no list is capable and never chosen, which is what a
        shipped-disabled entry looks like from here.
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
        return _adapt(module.read(target, connection=connection))
    except module.RegistryError as error:  # one refusal vocabulary, not two
        raise RegistryError(str(error)) from None


def _adapt(registry: Any) -> Registry:
    """`sd_db`'s registry in this module's shapes.

    The two carry the same fields by construction; converting rather than
    re-exporting means one caller-visible type, so a caller cannot come to
    depend on whichever one the machine happened to produce.
    """
    return Registry(
        path=Path(registry.path),
        bills={
            name: Bill(
                name=bill.name,
                cost_basis=bill.cost_basis,
                cap_usd_month=bill.cap_usd_month,
                meter=bill.meter,
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


def read_file(path: Path | str) -> Registry:
    """The file alone, for a checkout with no database."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        raise RegistryError(f"no provider registry at {target}") from None
    return parse(text, target)


# --------------------------------------------------------------------------
# The file
# --------------------------------------------------------------------------


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
        bills[name] = Bill(
            name=name,
            cost_basis=str(body["cost"]),
            cap_usd_month=body.get("cap_usd_month"),
            meter=body.get("meter"),
        )

    role_lists: dict[str, list[str]] = {}
    for role, names in document["roles"].items():
        if role not in ROLES:
            raise RegistryError(f"{path}: no role {role!r}")
        if not isinstance(names, list):
            raise RegistryError(f"{path}: role {role!r} is not a list")
        role_lists[role] = [str(name) for name in names]

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


def _provider(
    name: str,
    body: dict[str, Any],
    bills: dict[str, Bill],
    role_lists: dict[str, list[str]],
    path: Path,
) -> Provider:
    start, url = body.get("start"), body.get("url")
    if bool(start) == bool(url):
        raise RegistryError(
            f"{path}: provider {name!r} needs exactly one of 'start' or 'url'; "
            f"it has " + ("both" if start else "neither")
        )
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
    if "vendor" not in body:
        raise RegistryError(f"{path}: provider {name!r} has no 'vendor'")

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
        vendor=str(body["vendor"]),
        bill=bill_name,
        start=start or None,
        url=url or None,
        model=body.get("model"),
        reader=body.get("reader"),
        max_tokens=body.get("max_tokens"),
        price=dict(body.get("price") or {}),
        env=tuple(str(variable) for variable in (body.get("env") or ())),
        roles=roles,
        enabled=bool(body.get("enabled", True)),
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
