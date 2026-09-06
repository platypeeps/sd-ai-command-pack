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

import hashlib
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

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


def read_or_report(
    path: Path | str | None = None,
    *,
    home: Path | str | None = None,
    connection: Any = None,
) -> tuple[Registry, str]:
    """The registry, or an empty one and the reason it is empty.

    A machine with no registry is a fact to report, not a crash. `sd-review
    --explain` prints the plan and asks nobody, so it has to answer on a bare
    CI runner that has never run the installer -- and a real review with no
    registry has to say "nobody could be reached" rather than exiting before it
    can say anything at all.

    Falling back to the copy in the pack checkout was the other option and is
    worse: it would review with the shipped pins while reporting them as the
    operator's, and the whole point of seeding the file into the home is that
    what is there afterwards is theirs.

    A caller that must have a real registry -- one resolving a named entry, say
    -- checks the second value and refuses. `RegistryError` still comes out of
    `read` for callers that want it.
    """
    target = Path(path) if path is not None else registry_path(home)
    try:
        return read(target, connection=connection), ""
    except RegistryError as error:
        return Registry(target, {}, {}), str(error)


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
            ("cap_usd_month", (int, float), "an amount"),
        ):
            if body.get(key) is not None:
                _typed(body[key], kind, f"{key!r} of bill {name!r}", form, path)
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


def _typed(
    value: Any, kind: type | tuple[type, ...], what: str, form: str, path: Path
) -> Any:
    """`value`, or a refusal naming what it should have been.

    Every field below is read straight into a `Provider`, so a value of the
    wrong shape does not fail here -- it fails somewhere later, or worse, does
    not fail at all. `env: OPENAI_API_KEY` in place of a one-item list walked
    the string and produced fourteen single-character variable names, which
    the fingerprint then covered and the environment check then looked for.
    """
    if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
        raise RegistryError(f"{path}: {what} is {value!r}, which is not {form}")
    return value


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


# --------------------------------------------------------------------------
# Consent
# --------------------------------------------------------------------------
#
# The registry says who *can* review. `CLAUDE.local.md`'s `reviewers` line says
# who may receive *this repository's* diff, and nothing derives it: the
# installer asks once, the operator answers, and a repository that was skipped
# refuses its first review naming the key.
#
# The line names entries, because the entry is the recipient. Each pair carries
# that recipient beside the name -- the host of a `url` entry, the executable of
# a `start` entry with a fingerprint over its command line and the variables it
# receives -- so an entry repointed at another host, or given another argument,
# is refused until the line is rewritten. Consent to send a diff somewhere is
# consent to send it *there*, and an entry is a name for a destination rather
# than the destination itself.


#: `<entry>@<recipient>`, and for a `start` entry `<entry>@<executable>+<hash>`.
CONSENT_SEPARATOR = "@"
FINGERPRINT_JOIN = "+"
FINGERPRINT_LENGTH = 8


class ConsentRefusal(RegistryError):
    """This repository has not allowed this entry to receive its diff."""


@dataclass(frozen=True)
class Allowance:
    """One pair off the `reviewers` line."""

    entry: str
    recipient: str
    fingerprint: str | None = None

    def __str__(self) -> str:
        """The pair as it is written on the line, and readable back off it.

        A recipient holding a space or a comma is quoted, because that is what
        `consent_parts` needs to see one word where the operator meant one. A
        pair that renders unquoted here and cannot be parsed there would put
        the two halves of consent out of step in the direction that matters:
        a line the installer wrote, refused by the reader.
        """
        tail = f"{FINGERPRINT_JOIN}{self.fingerprint}" if self.fingerprint else ""
        recipient = self.recipient
        if any(character in recipient for character in ' \t,"\''):
            recipient = shlex.quote(recipient)
        return f"{self.entry}{CONSENT_SEPARATOR}{recipient}{tail}"


def parse_consent(line: str | None) -> dict[str, Allowance]:
    """The `reviewers` line as a mapping of entry name to what it may reach.

    An absent line and an empty one are the same answer and both mean no
    reviewer resolves; the caller distinguishes them because the installer
    writes no line for an empty answer.
    """
    if line is None:
        raise ConsentRefusal(
            "this repository has no 'reviewers' line in CLAUDE.local.md, so no "
            "entry may receive its diff and no reviewer resolves. The installer "
            "asks for it once per repository; add the key, or re-run the "
            "installer with --reviewers."
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
        recipient, _, fingerprint = recipient.partition(FINGERPRINT_JOIN)
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
    """The pairs on a `reviewers` line, split the way a start line is split.

    Commas and whitespace separate, and a quoted recipient survives both. A
    plain `str.split` could not name a `start` entry whose executable holds a
    space -- the very case `executable()` is shlex-aware to support -- so the
    one line that could consent to it was unparseable, and refused as a bare
    name. The two halves of the same consent have to agree on where a word
    ends.
    """
    lexer = shlex.shlex(line, posix=True)
    lexer.whitespace = " \t\n\r,"
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
    """A short digest over a `start` entry's command line and its `env` names.

    The names and not the values: the digest goes in a file the operator reads
    and a diff someone else may see, and a value is a key. An argument added to
    the start line, or a variable added to the list, changes it, which is the
    point -- a spawned command that gained `--upload` is a different recipient
    wearing the same executable.
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
    if allowed is None:
        return (
            f"{provider.name} is not on the repository's 'reviewers' line. A "
            f"registry entry is capability; the line is consent, and a new entry "
            f"resolves nowhere until the line names it."
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


def refuse_environment(provider: Provider, environ: Mapping[str, str]) -> str | None:
    """A variable whose value is a URL, which a spawned session may not receive.

    A key is a secret and the operator has consented to that; a URL in the
    environment is a destination the `reviewers` line never named, and a session
    that inherits one can send the diff somewhere this repository did not agree
    to. Named without its value, because printing it would put the destination
    in the log that reports the refusal.
    """
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


# --------------------------------------------------------------------------
# The chain
# --------------------------------------------------------------------------


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


def reviewer_chain(
    registry: Registry,
    *,
    consent: dict[str, Allowance],
    author_vendors: tuple[str, ...] = (),
    capped_bills: tuple[str, ...] = (),
    readers: tuple[str, ...] = (),
) -> list[Candidate]:
    """Every enabled entry holding `reviewer`, in order, each marked.

    Marked rather than filtered, because the run has to say which providers it
    passed over and why. A chain that returned only the survivors would report
    "codex reviewed" where the interesting sentence is "codex reviewed;
    claude was skipped as the author's vendor and minimax's bill is at its cap".

    Preflight is not decided here. Whether a binary answers is a fact about the
    machine at this second, and this function is a decision about the registry,
    the repository's consent and the branch's trailers -- all three of which are
    the same for a dry run as for a real one.
    """
    candidates: list[Candidate] = []
    for provider in registry.order("reviewer"):
        refusal = None
        if readers and provider.reader not in readers:
            # A reader this build does not implement is decided here and not at
            # the run, because a tier's depth is a count of entries taken off
            # this list: an entry that cannot run would occupy a slot and the
            # change would be read by fewer providers than its tier asked for,
            # while still reporting clean. That is a fact about the build, not
            # about the machine at this second, so it belongs in the chain.
            # Two different situations, and one message for both said the
            # wrong thing about the commoner one. Four of the five entries on
            # the shipped chain are `url` entries, which declare no reader at
            # all because a reader parses a spawned command's output; what
            # they wait on is a client for `url`. Reporting them as naming a
            # reader called `None` described a typo nobody made.
            refusal = (
                f"{provider.name} is a 'url' entry, and this build has no "
                f"client for one yet; it runs 'start' entries."
                if provider.url
                else f"{provider.name} reads back as {provider.reader!r}, and "
                f"this build implements no such reader."
            )
        if refusal is None:
            refusal = refuse_allowance(provider, consent.get(provider.name))
        if refusal is None and provider.vendor in author_vendors:
            refusal = (
                f"{provider.name} is an entry of vendor {provider.vendor}, and "
                f"this branch carries {provider.vendor} authorship. The reviewer "
                f"is a different vendor from the author, always."
            )
        if refusal is None and provider.bill in capped_bills:
            refusal = (
                f"{provider.name} is billed to {provider.bill}, which is at its "
                f"cap for the month."
            )
        candidates.append(Candidate(provider, refusal is None, refusal or ""))
    return candidates


def pick(
    registry: Registry,
    name: str,
    *,
    consent: dict[str, Allowance],
    author_vendors: tuple[str, ...] = (),
    capped_bills: tuple[str, ...] = (),
) -> Provider:
    """`--provider <name>`: one entry for one run, or a refusal that says why.

    A direct pick is refused for the same reasons a fallthrough skips, and
    reaches entries a fallthrough never sees -- a disabled one is not on the
    chain at all, and picking it by name should answer with the reason it ships
    disabled rather than with 'no such provider'.
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
    for candidate in reviewer_chain(
        registry,
        consent=consent,
        author_vendors=author_vendors,
        capped_bills=capped_bills,
    ):
        if candidate.provider.name != name:
            continue
        if candidate.eligible:
            return candidate.provider
        raise ConsentRefusal(candidate.reason)
    raise RegistryError(
        f"{name!r} holds the 'reviewer' role but is on no reviewer list in "
        f"{registry.path}, so nothing ranks it. Add it to the list, or pick an "
        f"entry the list names."
    )
