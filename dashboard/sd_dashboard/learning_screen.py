"""Books and Videos: the rows behind the Documents page's Books and Videos views (sd:6260, sd:6261).

The page is `v2/documents.html`; it holds no rows. Each view reads one JSON document, `/api/documents/books` and
`/api/documents/videos`, built here from the vault's learning base rows (`records.list_rows(connection, "learning")`,
the `sdw.learning` kind). Nothing here writes: a row's stage and kind stay as the store holds them.

**Which rows.** Books are the rows whose `content-type` is `book` or `article`. Videos are the rows whose
`content-type` is `youtube` or `video`, and any learning row titled `YYYY-MM-DD - YouTube - <channel> - <title>`, the
name the vault's video notes carry. Other learning rows (courses) are in neither.

**What one row says.** A book: its title, its author or source (the `author` list, else the `publisher`, else the
URL's host), its URL and its read state. A video: its title less the dated prefix, its channel (the `channel` field,
else the title's), its date (`published-date`, else the title's), its URL and its watched state. The state is the
row's stage in the page's words (`READ`, `WATCHED`); a stage the map does not name is shown as it is. A URL that is not
`http` or `https` is no link: `url` is empty and `url_text` keeps what the row holds, so the page shows it as text.

A store that does not read raises, so the route answers 500 with the cause and the page says the rows were not read.
"""

from __future__ import annotations

import re
import urllib.parse

__all__ = ["READ", "WATCHED", "books", "videos"]

#: The learning stages in a book's words: to read, reading, done.
READ = {"queued": "to read", "in-progress": "reading", "done": "done", "dropped": "dropped"}
#: The learning stages in a video's words.
WATCHED = {"queued": "to watch", "in-progress": "watching", "done": "watched", "dropped": "dropped"}
#: A video note's title: its date, YouTube, the channel and the video's own title.
VIDEO_TITLE = re.compile(r"^(\d{4}-\d{2}-\d{2}) - YouTube - (.+?) - (.+)$")


def _rows(connection):
    from sd_db import records

    return records.list_rows(connection, "learning")


def _text(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def _url(value) -> tuple[str, str]:
    """The link and its host for an http(s) URL; else no link, so the page draws the text and never a javascript: href."""
    text = _text(value)
    parts = urllib.parse.urlsplit(text)
    return (text, parts.hostname or "") if parts.scheme in ("http", "https") and parts.hostname else ("", "")


def _base(row, words) -> dict:
    fields = row["fields"]
    url, host = _url(fields.get("url"))
    stage = row.get("stage") or ""
    return {"id": row["id"], "title": row["title"], "stage": stage, "state": words.get(stage, stage),
            "url": url, "host": host, "url_text": "" if url else _text(fields.get("url")),
            "description": _text(fields.get("description")), "added": _text(fields.get("dateCreated"))[:10]}


def books(connection, *, now: str) -> dict:
    """`/api/documents/books`: the book and article rows, in the store's order; the page sorts them."""
    out = []
    for row in _rows(connection):
        fields = row["fields"]
        kind = _text(fields.get("content-type")).lower()
        if kind not in ("book", "article"):
            continue
        item = _base(row, READ)
        item.update(kind=kind, by=_text(fields.get("author")) or _text(fields.get("publisher")) or item["host"],
                    subtitle=_text(fields.get("subtitle")), published=_text(fields.get("published-date")),
                    pages=_text(fields.get("total-pages")), isbn=_text(fields.get("isbn")))
        out.append(item)
    return {"read": now, "rows": out}


def videos(connection, *, now: str) -> dict:
    """`/api/documents/videos`: the video rows, in the store's order; the page sorts them."""
    out = []
    for row in _rows(connection):
        fields = row["fields"]
        named = VIDEO_TITLE.match(row["title"] or "")
        if _text(fields.get("content-type")).lower() not in ("youtube", "video") and not named:
            continue
        item = _base(row, WATCHED)
        item.update(title=named.group(3) if named else row["title"],
                    channel=_text(fields.get("channel")) or (named.group(2) if named else ""),
                    date=_text(fields.get("published-date"))[:10] or (named.group(1) if named else ""),
                    duration=_text(fields.get("duration")))
        out.append(item)
    return {"read": now, "rows": out}
