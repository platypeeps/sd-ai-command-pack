"""A repository's publish channels: the closed vocabulary of `repo.channels`.

The setting says which outward channels a repository uses and the folder each
one writes to (sd:3462, design sd:3471). It is a JSON object on the `repo`
row, written by `repos.set_channels` and read by `repos.repo_channels`; both
pass it through `validate`, so a value this module refuses is never written
and never read as a setting.

    {"obsidian": {"folder": "Briefs/example"}, "notion": {"folder": "Example"}, "drive": {}}

A channel named with `{}` writes to its default folder; a channel left out is
off. NULL is no setting, which is not the same as `{}`: clearing writes NULL.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .repos import RepoRefusal

#: The channels a repository may name, in the order a refusal lists them.
CHANNELS = ("obsidian", "notion", "drive")

#: The one key a channel's object may hold.
FOLDER = "folder"

#: A Notion page id, compact or hyphenated: an id the drain resolves, never a folder name.
PAGE_ID = re.compile(r"[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


class ChannelRefusal(RepoRefusal):
    """A channels value outside the vocabulary, naming the key that is wrong."""


def _folder(channel: str, folder: Any) -> str:
    """A folder is names, never an id, a URL or a path out of its container.

    Obsidian and Drive take a relative path; Notion takes one page name, since
    a mirror request carries one `subfolder`.
    """
    if not isinstance(folder, str) or not folder:
        raise ChannelRefusal(f"{channel}: folder must be a non-empty name; leave it out for the default folder")
    if any(unicodedata.category(character).startswith("C") for character in folder):
        raise ChannelRefusal(f"{channel}: folder {folder!r} holds a control or format character")
    if "://" in folder:
        raise ChannelRefusal(f"{channel}: folder {folder!r} is a URL; name the folder, not its link")
    if folder.startswith("/"):
        raise ChannelRefusal(f"{channel}: folder {folder!r} has a leading /; name it relative to its container")
    for segment in folder.split("/"):
        if not segment.strip():
            raise ChannelRefusal(f"{channel}: folder {folder!r} has an empty or blank segment")
        if segment in (".", ".."):
            raise ChannelRefusal(f"{channel}: folder {folder!r} has a {segment!r} segment")
        if PAGE_ID.fullmatch(segment):
            raise ChannelRefusal(f"{channel}: folder {folder!r} holds an id; name the folder, and keep ids "
                                 f"per machine or per document")
    if channel == "notion" and "/" in folder:
        raise ChannelRefusal(f"notion: folder {folder!r} must be one page name under the scope folder, with no /")
    return folder


def validate(value: Any) -> dict[str, dict[str, str]]:
    """`value` as a setting, or `ChannelRefusal` naming what is wrong.

    Returns a new dict holding the same keys, so a caller never stores the
    object it was handed.
    """
    if not isinstance(value, dict):
        raise ChannelRefusal(f"channels must be an object of obsidian, notion or drive, not {type(value).__name__}")
    if not value:
        raise ChannelRefusal("channels {} names no channel; clear the setting with `none` instead")
    out: dict[str, dict[str, str]] = {}
    for channel, entry in value.items():
        if channel not in CHANNELS:
            raise ChannelRefusal(f"{channel!r} is not a channel; expected {', '.join(CHANNELS[:-1])} or {CHANNELS[-1]}")
        if not isinstance(entry, dict):
            raise ChannelRefusal(f"{channel}: expected an object holding folder or nothing, not {entry!r}")
        extra = sorted(set(entry) - {FOLDER})
        if extra:
            raise ChannelRefusal(f"{channel}: {extra[0]!r} is not a channel key; a channel holds folder or nothing")
        out[channel] = {FOLDER: _folder(channel, entry[FOLDER])} if FOLDER in entry else {}
    return out


def dumps(value: dict[str, dict[str, str]] | None) -> str:
    """The canonical text: sorted, compact JSON, or `none` for no setting.

    What the column stores and what the verb prints and compares as `before`.
    """
    return "none" if value is None else json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonical(text: str | None) -> str:
    """Stored or given text in the canonical spelling, for a `before` compare.

    NULL and `none` both read `none`. JSON is re-spelled whether or not it
    validates, so a value written by hand still compares; text that is not
    JSON compares as itself.
    """
    if text is None or text == "none":
        return "none"
    try:
        return json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"))
    except ValueError:
        return text
