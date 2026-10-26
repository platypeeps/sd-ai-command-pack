"""Books: the rows behind the Documents page's Books view (sd:6260).

The page is `v2/documents.html`; it holds no rows. The view reads one JSON document, `/api/documents/books`,
built here from the vault's learning base rows (`records.list_rows(connection, "learning")`,
the `sdw.learning` kind). Nothing here writes: a row's stage and kind stay as the store holds them.

**Which rows.** Books are the rows whose `content-type` is `book` or `article`. Other learning rows (courses, videos) are not books.

**What one row says.** A book: its title, its author or source (the `author` list, else the `publisher`, else the
URL's host), its URL and its read state. The state is the row's stage in the page's words (`READ`); a stage the map does not name is shown as it is. A URL that is not
`http` or `https` is no link: `url` is empty and `url_text` keeps what the row holds, so the page shows it as text.

A store that does not read raises, so the route answers 500 with the cause and the page says the rows were not read.
"""

from __future__ import annotations

import urllib.parse

__all__ = ["READ", "books"]

#: The learning stages in a book's words: to read, reading, done.
READ = {"queued": "to read", "in-progress": "reading", "done": "done", "dropped": "dropped"}


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
