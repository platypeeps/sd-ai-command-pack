"""The pull-request body `sd-ship` publishes, read against the lines it owns (sd:1870).

`sd-ship` writes `Work:` into the body it publishes, and `Item:`, `Delivers:`
and the authorship lines into the squash message. A supplied body that says
the same thing is not a conflict, so such a line is stripped and named in the
result. A line that says something else -- another item, a delivery nobody
claimed, an author no registry knows, a pre-squash sha -- is refused by line
number, with the value `sd-ship` would have written.

The fixpoint is the point: `normalize` of a body `sd-ship` published returns
the body it published before appending `Work:`, so the live pull-request body
fed back as `--body-file` prepares again without a refusal. Before this, the
body `sd-ship` itself wrote was refused as input (#1236, #1238).

A body with no item owns nothing: every owned line refuses there, indented
or not, and nothing is stripped. With an item, only a line at column zero is
read, because that is the only form git or rule 5 reads; an indented line is
prose about a trailer, and the body keeps it.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re

import sd_lib
from sd_ship_remote import Refusal

#: The canonical spelling of each owned key, by its case-folded name.
_CANONICAL = {key.rstrip(":").lower(): key for key in sd_lib.OWNED_TRAILERS}
_OWNED_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>" + "|".join(re.escape(key.rstrip(":")) for key in sd_lib.OWNED_TRAILERS)
    + r")[ \t]*:(?P<value>.*)$",
    re.IGNORECASE,
)


@dataclasses.dataclass(frozen=True)
class OwnedLine:
    """One owned trailer line: its 1-based number, text, canonical key and value."""

    number: int
    text: str
    key: str
    value: str
    indented: bool


def owned_lines(body: str) -> list[OwnedLine]:
    """Every line of `body` that starts with an owned key, indented or not."""
    found = []
    for number, line in enumerate(body.split("\n"), start=1):
        match = _OWNED_RE.match(line.rstrip("\r"))
        if match is not None:
            found.append(OwnedLine(number, line.rstrip("\r"), _CANONICAL[match["key"].lower()],
                                   match["value"].strip(), bool(match["indent"])))
    return found


def registries() -> list:
    """The operator's registry and the pack's own `providers.yaml`, each that reads."""
    import sd_registry  # noqa: PLC0415 - only a body naming an author needs it
    found = []
    home, reason = sd_registry.read_or_report()
    if not reason:
        found.append(home)
    try:
        found.append(sd_registry.read_file(sd_registry.shipped_path(pathlib.Path(__file__).resolve().parent.parent)))
    except sd_registry.RegistryError:
        pass
    return found


def known_author(value: str, readers: list) -> bool:
    """Whether `value` is `human` or the `<entry>/<vendor>` a registry resolves."""
    if value == sd_lib.HUMAN_AUTHOR:
        return True
    entry, separator, _vendor = value.partition("/")
    for registry in readers:
        try:
            if separator and sd_lib.attribution_value(entry, registry) == value:
                return True
        except sd_lib.TrailerError:
            continue
    return False


def problem(line: OwnedLine, item: int, deliver: bool, readers: list | None) -> str | None:
    """Why `line` cannot be stripped from an item's body, or None when it can."""
    expected = f"sd:{item}"
    if line.key in (sd_lib.ITEM_TRAILER, sd_lib.WORK_TRAILER):
        return None if line.value == expected else f"expected `{line.key} {expected}`"
    if line.key == sd_lib.DELIVERS_TRAILER:
        if not deliver:
            return "expected no line: delivery is claimed with --deliver, never by the body"
        return None if line.value == expected else f"expected `{line.key} {expected}`"
    if line.key == sd_lib.AUTHORED_TRAILER:
        if known_author(line.value, registries() if readers is None else readers):
            return None
        return (f"expected `{line.key} {sd_lib.HUMAN_AUTHOR}` or an `<entry>/<vendor>` the provider "
                f"registry resolves; the commits decide authorship")
    if line.key == sd_lib.ATTRIBUTES_TRAILER:
        return "expected no line: it names a pre-squash sha, and the squash carries authorship from the commits"
    return f"expected no line: `{line.key}` rides a later merge or an empty commit, never this body"


def normalize(body: str, item: int | None, *, deliver: bool = False,
              readers: list | None = None) -> tuple[str, tuple[str, ...]]:
    """`body` without the owned lines that agree with `sd-ship`, and those lines.

    Refuses, naming every offending line, when any owned line disagrees. With
    no item, every owned line disagrees and `body` is returned unchanged.
    With an item, the result carries no trailing whitespace, which is what
    makes `normalize(published)` equal the body before `Work:` was appended.
    """
    found = owned_lines(body)
    if item is None:
        if found:
            raise Refusal("no-item publication cannot carry item or caller-supplied authorship trailers: "
                          + "; ".join(f"line {line.number}: `{line.text.strip()}`" for line in found))
        return body, ()
    read = [line for line in found if not line.indented]
    problems = [(line, reason) for line in read
                if (reason := problem(line, item, deliver, readers)) is not None]
    if problems:
        raise Refusal("the ship adapter owns association and delivery trailers: "
                      + "; ".join(f"line {line.number}: `{line.text}`; {reason}" for line, reason in problems),
                      code="body_trailer_refused", boundary="input", state="operator_decision",
                      next_action="Remove or correct the named lines; sd-ship writes them itself.")
    stripped = {line.number for line in read}
    lines = body.split("\n")
    kept: list[str] = []
    for number, text in enumerate(lines, start=1):
        # A stripped line between two blank ones leaves one gap, not two.
        if number in stripped or (number - 1 in stripped and not text.strip()
                                  and kept and not kept[-1].strip()):
            continue
        kept.append(text)
    return "\n".join(kept).rstrip(), tuple(line.text for line in read)


def published(body: str, item: int) -> str:
    """The body as `sd-ship` publishes it: normalized, then one `Work:` line."""
    return f"{body}\n\n{sd_lib.WORK_TRAILER} sd:{item}\n"
