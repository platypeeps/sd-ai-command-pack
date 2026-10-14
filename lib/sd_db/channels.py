"""A repository's publish channels: the closed vocabulary of `repo.channels`.

The setting says which outward channels a repository uses and the folder each
one writes to (sd:3462, design sd:3471). It is a JSON object on the `repo`
row, written by `repos.set_channels` and read by `repos.repo_channels`; both
pass it through `validate`, so a value this module refuses is never written
and never read as a setting.

    {"obsidian": {"folder": "Briefs/example"}, "notion": {"folder": "Example"}, "drive": {}}

A channel named with `{}` writes to its default folder; a channel left out is
off. NULL is no setting, which is not the same as `{}`: clearing writes NULL.

`feed` is inbound (sd:3980): the repo's one RSS/Atom subscription,
`{"feed": {"url": "https://example.test/feed.xml"}}`, which `sd-watchlist`
reads. It is not a publish channel: `outbound` drops it before a publisher
reads the setting, so a feed alone leaves publishing as no setting does.

`jira` and `github` are inbound too (sd:3461): the repo's issue sources,
`{"jira": {"project": "EXAMPLE"}, "github": {"repo": "example/project"}}`.
Each names the `repo` value its tracker's `shadow` rows carry, and
`repos.issue_sources` reads them for Today and Tasks.

`record_url` puts where a document was published on the item that owns it
(sd:3979): the item row holds the URL, and the dashboard reads the row.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from . import paths
from .database import transaction
from .errors import SdDbError
from .repos import RepoRefusal

#: The channels a repository may name, in the order a refusal lists them.
CHANNELS = ("obsidian", "notion", "drive")

#: The inbound sources a repository may name beside its channels (sd:3980).
INBOUND = ("feed", "jira", "github")

#: The one key a channel's object may hold.
FOLDER = "folder"

#: The one key the feed's object holds.
URL = "url"

#: The one key each issue source's object holds, and the spelling of its value:
#: a Jira project key, a GitHub `owner/name` (sd:3461).
ISSUE_KEYS = {"jira": "project", "github": "repo"}
ISSUE_SPELLING = {"jira": re.compile(r"[A-Z][A-Z0-9_]+"),
                  "github": re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/(?!\.\.?$)[A-Za-z0-9._-]+")}

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


def _feed(entry: dict) -> dict[str, str]:
    """The feed's object: one http or https URL with a host, no credentials and no space."""
    from urllib.parse import urlsplit

    extra = sorted(set(entry) - {URL})
    url = entry.get(URL)
    if extra or not isinstance(url, str) or not url:
        raise ChannelRefusal("feed: expected {\"url\": URL} and nothing else; `feed=URL` sets it")
    if any(character.isspace() or unicodedata.category(character).startswith("C") for character in url):
        raise ChannelRefusal(f"feed: url {url!r} holds a space, a control or a format character")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ChannelRefusal(f"feed: url {url!r} must be an http or https URL with a host")
    if parts.username is not None or parts.password is not None:
        raise ChannelRefusal(f"feed: url {url!r} holds credentials; the setting holds none")
    return {URL: url}


def _issue_source(source: str, entry: dict) -> dict[str, str]:
    """An issue source's object: its one key, in its tracker's spelling."""
    key = ISSUE_KEYS[source]
    value = entry.get(key)
    if set(entry) != {key} or not isinstance(value, str) or not ISSUE_SPELLING[source].fullmatch(value):
        example = "EXAMPLE" if source == "jira" else "owner/name"
        raise ChannelRefusal(f"{source}: expected {{\"{key}\": \"{example}\"}} and nothing else, not {entry!r}; "
                             f"`{source}={example}` sets it")
    return {key: value}


def outbound(setting: dict[str, dict[str, str]] | None) -> dict[str, dict[str, str]] | None:
    """The publish channels of a setting, or None when it names none (sd:3980).

    A setting naming only inbound sources says nothing about publishing, so
    it publishes as no setting does; beside an outbound channel, a channel
    left out is still off.
    """
    channels = {name: entry for name, entry in (setting or {}).items() if name in CHANNELS}
    return channels or None


def kept(value: dict[str, dict[str, str]], stored: str | None) -> dict[str, dict[str, str]]:
    """`value` with what it leaves out taken from `stored` (sd:3980, sd:3461).

    The outbound channels are one replacement: a value naming none keeps the
    stored ones, and a value naming any replaces them all. Each inbound source
    is its own: a value that leaves one out keeps it, so `feed=URL` never
    deletes the Jira or GitHub source. A stored value that is NULL or that the
    validator refuses keeps nothing: a set replaces it whole.
    """
    try:
        old = validate(json.loads(stored)) if stored else {}
    except (ValueError, ChannelRefusal):
        old = {}
    out = dict(value)
    if not any(key in value for key in CHANNELS):
        out.update({key: old[key] for key in CHANNELS if key in old})
    out.update({key: old[key] for key in INBOUND if key in old and key not in value})
    return out


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
        if channel not in CHANNELS + INBOUND:
            raise ChannelRefusal(f"{channel!r} is not a channel; expected {', '.join(CHANNELS[:-1])} or {CHANNELS[-1]}, "
                                 f"or the inbound {', '.join(INBOUND[:-1])} or {INBOUND[-1]}")
        if not isinstance(entry, dict):
            raise ChannelRefusal(f"{channel}: expected an object holding folder or nothing, not {entry!r}")
        if channel == "feed":
            out[channel] = _feed(entry)
            continue
        if channel in ISSUE_KEYS:
            out[channel] = _issue_source(channel, entry)
            continue
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


class UrlRefusal(SdDbError):
    """A published URL that cannot be recorded on its item; nothing was written."""


def record_url(connection: Any, item: int, repo: str, document: str, title: str, channel: str, url: str,
               who: str) -> str:
    """Record that `document` of `repo` was published to `channel` at `url`, on item `item`.

    One transaction. The URL goes in `fields.published`, keyed
    `<repo>::<document>` with the repository's stored key, so two
    repositories with one basename keep two entries; a `comment` note
    `Published <channel> <document>: <url>` gives the history. Returns
    `unchanged` when the field already holds this URL (no note), else
    `recorded`. Refuses, writing nothing, while a restore is unresolved (the
    row may be older than the receipts) and for an item that is not there.
    """
    from .writes import add_note, now, unresolved_state

    if channel not in CHANNELS:
        raise UrlRefusal(f"{channel!r} is not a channel; expected {', '.join(CHANNELS[:-1])} or {CHANNELS[-1]}")
    if type(item) is not int or item < 1:
        raise UrlRefusal(f"item must be an sd item number, not {item!r}")
    key = f"{paths.key(repo)}::{document}"
    with transaction(connection):
        if unresolved_state(connection, "restore"):
            raise UrlRefusal("a restore is unresolved, so the item rows may be older than the receipts; "
                             "resolve the restore, then run again")
        row = connection.execute("SELECT fields FROM item WHERE id = ?", (item,)).fetchone()
        if row is None:
            raise UrlRefusal(f"sd:{item} is not an item in this database")
        try:
            fields = json.loads(row["fields"]) if row["fields"] else {}
        except ValueError as error:
            raise UrlRefusal(f"sd:{item}'s fields are not JSON ({error}); left as they are") from error
        if not isinstance(fields, dict):
            raise UrlRefusal(f"sd:{item}'s fields are not an object; left as they are")
        published = fields.get("published")
        published = dict(published) if isinstance(published, dict) else {}
        entry = published.get(key)
        entry = dict(entry) if isinstance(entry, dict) else {}
        if entry.get(channel) == url and entry.get("title") == title:
            return "unchanged"
        moved = entry.get(channel) != url
        entry.update({"title": title, channel: url})
        published[key] = entry
        fields["published"] = published
        connection.execute("UPDATE item SET fields = ?, updated_at = ? WHERE id = ?",
                           (json.dumps(fields, sort_keys=True), now(), item))
        if moved:
            add_note(connection, item, "comment", f"Published {channel} {document}: {url}", session=who)
    return "recorded"
