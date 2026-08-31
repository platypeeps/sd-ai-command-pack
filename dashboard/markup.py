"""What a plugin is allowed to draw into its own tab.

A tile returns markup and the dashboard injects it. `innerHTML` does not run
`<script>`, which is the reassurance that makes people skip this file; it is
also not the attack. Inline handlers -- `onclick`, `onerror` on an `<img>` that
cannot load -- run exactly as written, and an `<iframe>` needs no handler at
all. So the payload is filtered here, once, on the way out of the loader,
rather than trusted at the point of injection.

Filtering server-side rather than in the browser is deliberate: `/api/plugins`
is a public surface of this server, and a sanitiser living in `app.js` would
leave the endpoint itself serving whatever a tile printed. What this module
returns is what every consumer gets.

The rule is an allow-list, because a deny-list of dangerous tags is a list
somebody has to keep current against browsers. Three outcomes, and which one a
tag gets is the whole design:

* **kept** -- structural markup a table-shaped view needs;
* **unwrapped** -- an unknown tag is dropped and its text kept, so a plugin
  using `<marquee>` loses a box, not a sentence;
* **erased** -- a tag whose content is code, a request, or a control (`script`,
  `iframe`, `form`, `svg`) loses its subtree with it.

`<img>` sits in neither list and needs neither: it is simply not allow-listed,
and a void element has no subtree to take with it. The distinction matters only
to a reader of this file -- what reaches the page is the same nothing either
way.

Every drop is reported. A tile whose markup was quietly rewritten looks like a
tile that rendered what it meant to, and the plugin author has no way to find
out otherwise -- so the complaints ride back with the tab and become rows in
the same view that reports a plugin going dark.

Interaction is not markup and is not here: a table declares `data-sd-sort` or
`data-sd-search` and the backbone wires the behaviour (R11-D16). `data-*` is
allow-listed for exactly that reason, and it is why no plugin needs script.
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

KEPT = {
    "p", "div", "span", "section", "article", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "colgroup", "col", "ul", "ol", "li", "dl", "dt", "dd",
    "a", "code", "pre", "em", "strong", "b", "i", "small", "abbr", "time",
    "br", "hr", "details", "summary", "figure", "figcaption", "blockquote",
}
# No end tag ever arrives for these, so erasing one must not open a region.
VOID = {"br", "hr", "col", "wbr", "img", "input", "link", "meta", "base", "source"}
# Content erased with the tag: it is code, a fetch, a control, or a nested
# document, and none of those is a view.
ERASED = {
    "script", "style", "iframe", "object", "embed", "template", "noscript",
    "svg", "math", "form", "button", "select", "textarea", "label",
    "video", "audio", "canvas", "dialog", "slot", "portal",
}
GLOBAL_ATTRS = {"class", "title", "lang", "dir"}
PER_TAG_ATTRS = {
    "a": {"href"},
    "td": {"colspan", "rowspan", "headers"},
    "th": {"colspan", "rowspan", "scope", "headers"},
    "col": {"span"},
    "colgroup": {"span"},
    "ol": {"start", "reversed", "type"},
    "time": {"datetime"},
    "details": {"open"},
    "abbr": {"title"},
}
DATA_ATTR = re.compile(r"^data-[a-z0-9-]+$")
# Absolute and external only. A relative href would resolve against this
# server's own routes, and `javascript:` is the reason this check exists at
# all; an in-page anchor is pointless here because `id` is not allow-listed.
SAFE_HREF = re.compile(r"^(?:https?://|mailto:)", re.IGNORECASE)


class Filter(HTMLParser):
    """Rebuilds the document from the parts that survive the allow-list."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []
        self.erasing = ""
        self.depth = 0
        self.dropped_tags: set[str] = set()
        self.dropped_attrs: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.erasing:
            if tag == self.erasing and tag not in VOID:
                self.depth += 1
            return
        if tag in ERASED:
            self.dropped_tags.add(tag)
            if tag not in VOID:
                self.erasing, self.depth = tag, 1
            return
        if tag not in KEPT:
            # Unwrapped: the text is the content and the box was decoration.
            self.dropped_tags.add(tag)
            return
        rendered = "".join(self._attr(tag, name, value) for name, value in attrs)
        self.out.append(f"<{tag}{rendered}>")
        if tag not in VOID:
            self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """`<br/>`: a start tag that never gets an end tag, whatever it names.

        Routed through `handle_starttag` so one allow-list decides, then any
        element it opened is closed here -- otherwise `<div/>` would leave a
        `<div>` open for the rest of the document.
        """
        before, depth = len(self.open), self.depth
        self.handle_starttag(tag, attrs)
        if len(self.open) > before:
            self.out.append(f"</{self.open.pop()}>")
        if self.erasing == tag:
            # `<script/>` opens no region: either it just started one that ends
            # here, or it nested inside one and closed itself again.
            self.depth = depth
            if not self.depth:
                self.erasing = ""

    def handle_endtag(self, tag: str) -> None:
        if self.erasing:
            if tag == self.erasing:
                self.depth -= 1
                if self.depth <= 0:
                    self.erasing, self.depth = "", 0
            return
        if tag not in self.open:
            # Either it was unwrapped on the way in or it closes nothing. The
            # drop is already recorded; emitting `</article>` here would put
            # back the tag the allow-list just removed.
            return
        # Close what is actually open, innermost first: a tile ending `</div>`
        # while a `<td>` is still open must not emit tags in an order no
        # parser will accept.
        while self.open:
            done = self.open.pop()
            self.out.append(f"</{done}>")
            if done == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.erasing:
            self.out.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        """Dropped without comment, so to speak -- conditional comments are
        markup in some parsers and a comment is never a view."""

    def _attr(self, tag: str, name: str, value: str | None) -> str:
        name = name.lower()
        allowed = name in GLOBAL_ATTRS or name in PER_TAG_ATTRS.get(tag, set())
        if not (allowed or DATA_ATTR.fullmatch(name)):
            # `on*` lands here with everything else. Naming handlers
            # specifically would suggest the rest were judged safe; they are
            # simply not on the list.
            self.dropped_attrs.add(name)
            return ""
        if value is None:
            return f" {name}"
        if name == "href" and not SAFE_HREF.match(value.strip()):
            self.dropped_attrs.add("href")
            return ""
        return f' {name}="{escape(value, quote=True)}"'

    def finish(self) -> str:
        # An unclosed `<table>` would otherwise swallow the tab that follows it
        # in the page.
        while self.open:
            self.out.append(f"</{self.open.pop()}>")
        return "".join(self.out)


def sanitize(html: str, source: str) -> tuple[str, list[str]]:
    """The markup a tile may draw, and one complaint per kind of loss."""
    parser = Filter()
    try:
        parser.feed(html)
        parser.close()
    except Exception as error:  # noqa: BLE001 - a parser fault is not a page fault
        return "", [f"{source}: markup could not be parsed: {error!r}"]
    complaints = []
    if parser.dropped_tags:
        complaints.append(
            f"{source}: dropped markup the contract does not allow: "
            + ", ".join(sorted(parser.dropped_tags))
        )
    if parser.dropped_attrs:
        complaints.append(
            f"{source}: dropped attributes the contract does not allow: "
            + ", ".join(sorted(parser.dropped_attrs))
        )
    if parser.erasing:
        complaints.append(f"{source}: `<{parser.erasing}>` was never closed")
    return parser.finish(), complaints
