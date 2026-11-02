"""`sd-research-kit highlight`: mark what changed in a Google Doc update (sd:7252).

Every Google Doc update the framework makes marks the paragraphs that changed
since the copy the reader last saw, so the reader rereads only those. The
baseline is that copy: the Doc's current text, read back with workspace-mcp
`get_doc_as_markdown` (`comment_mode: none`) just before the update, so a
reviewer's own edits count as already seen.

    sd-research-kit highlight --previous <baseline.md> [--since <time>] [--skip-header] <in> <out.html>

`<in>` is the HTML about to be uploaded, or Markdown (`.md`), which is laid out
as HTML first, as a mirror's `content` is. Each unit whose text is not in the
baseline gets `background-color:#fff2a8`: a paragraph, list item, heading, table
cell or code block, and any text outside those, such as a list item's tail after
its nested list. One note, highlighted the same way, says "Changed since
<time>": the count, how many earlier units no longer appear (reworded or
removed), and the sections of both. With neither it says "No changes since".

Everything is compared unless the caller passes `--skip-header`: then what
comes before the first `<hr` of the page, and before the first rule of the
baseline, is a header block (a review copy's title, repository and push time,
which changes every push), and the note goes at its end. A page with no `<hr` is
refused under that flag. Otherwise the note opens the body.

A unit is unchanged when its text, tags stripped and whitespace collapsed,
equals an unmatched unit of the baseline with Markdown syntax taken away: links
keep their text, images go, bold and italic marks go, and heading, quote and
list markers go, with the `[ ]` checkbox Drive adds to an imported list. Code
spans, code blocks and escaped characters keep their characters literally.
Each baseline unit matches once, so a duplicated paragraph is new. Formatting,
a link's target and an image are not compared, by the ruling: Drive rewrites
image URLs and may rewrite links.

An empty baseline is a first push, which has nothing to compare: the verb
refuses it and writes nothing, so a failed read-back never marks a whole
document. Exit codes: 0 written (changed or not); 2 bad arguments, an unreadable
file or an empty baseline.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

MARK = "background-color:#fff2a8"
USAGE = "usage: sd-research-kit highlight --previous <baseline.md> [--since <time>] [--skip-header] <in> <out.html>"
#: Tags that hold a unit's text; a changed one gets the mark on its opening tag.
UNIT = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "pre", "dt", "dd", "caption",
        "figcaption", "blockquote", "div"}
#: Every block tag: a unit's text runs from one of these to the next. Inline tags (a, code, br) do not cut it.
BLOCK = UNIT | {"ul", "ol", "hr", "table", "thead", "tbody", "tfoot", "tr", "dl", "figure", "body", "html",
                "section", "article", "main", "header", "footer"}
#: A tag's attributes, quote-aware: a `>` inside a quoted value does not end the tag.
ATTRS = r"""(?:"[^"]*"|'[^']*'|[^'">])*"""
#: A comment (no name) or a tag `(closing slash, name)`; every tag read in this file goes through it.
TAG = re.compile(rf"<!--.*?-->|<(/?)([a-zA-Z][a-zA-Z0-9]*)\b{ATTRS}>", re.S)
#: One attribute inside a tag: `(name, value as written, quotes kept)`.
ATTR = re.compile(r"""([^\s"'>/=]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?""")
LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\((?:[^()\s]|\([^)]*\))*(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\((?:[^()]|\([^)]*\))*\)")
LEAD = re.compile(r"^\s*(?:#{1,6}\s+|>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?(?:\[[ xX]\]\s+)?")
HEADING = re.compile(r"^\s*#{1,6}\s")
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
ROW = re.compile(r"^\s*\|.*\|\s*$")
RULE = re.compile(r"^\s*(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
#: The note's own text, read back from the previous push: never a paragraph of the document.
NOTE = re.compile(r"^(Changed since|No changes since) ")
#: Markdown's emphasis pairs, strong first: each keeps its text.
EMPHASIS = (re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1"), re.compile(r"\*(?=\S)(.+?)(?<=\S)\*"),
            re.compile(r"(?<![\w\\])_(?=\S)(.+?)(?<=\S)_(?!\w)"))


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _name(tag: re.Match[str]) -> str:
    """A tag's lower-case name; empty for a comment."""

    return (tag.group(2) or "").lower()


def _strip(fragment: str) -> str:
    """`fragment` with tags and comments taken out and `<br>` a space; entities still escaped."""

    return TAG.sub(lambda tag: " " if _name(tag) == "br" else "", fragment)


def html_text(fragment: str) -> str:
    """A fragment's text: tags stripped, `<br>` a space, entities read. Literal characters stay."""

    return _collapse(html.unescape(_strip(fragment)))


def markdown_text(line: str) -> str:
    """One Markdown line or block as the text its HTML would hold.

    Code spans and backslash escapes are set aside first, so their characters stay literal:
    `` `__init__` `` reads `__init__`, while `__init__` outside code is bold `init`.
    """

    kept: list[str] = []

    def keep(text: str) -> str:
        kept.append(text)
        return f"\x00{len(kept) - 1}\x00"

    text = re.sub(r"(`+)(.+?)\1", lambda m: keep(m.group(2).strip() if m.group(2).strip() else m.group(2)), line)
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~<])", lambda m: keep(m.group(1)), text)
    text = IMAGE.sub("", text)
    text = LINK.sub(r"\1", text)
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)
    text = "\n".join(LEAD.sub("", row) for row in text.split("\n"))
    for pattern in EMPHASIS:
        while True:
            text, count = pattern.subn(lambda m: m.group(m.lastindex or 1), text)
            if not count:
                break
    text = html.unescape(_strip(text))
    text = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)
    return _collapse(text)


class Baseline:
    """The previous copy's units, each matched at most once.

    A unit is a heading, a list item, a table cell, a fenced block, or a run of plain lines (one
    paragraph, however Drive wrapped it). Drive may also end a paragraph at a single newline, so a
    run's lines can match one by one. Each unit is one multiset of lines: a whole match takes every
    line and needs all of them left, and a line match takes that line alone, so what no match took
    stays unmatched and counts as gone.
    """

    def __init__(self, markdown: str, header: bool) -> None:
        self.units: list[tuple[str, str]] = []  # (text, section)
        self.left: list[list[str]] = []  # each unit's lines no match has taken
        self.full: list[int] = []  # how many lines each unit started with
        self.whole: dict[str, list[int]] = {}
        self.lines: dict[str, list[int]] = {}
        rows = markdown.splitlines()
        if header:
            rows = self._after_header(rows)
        section, fence = "Opening", None
        run: list[str] = []
        code: list[str] = []
        for row in rows + [""]:
            if fence is not None:
                if row.strip().startswith(fence):
                    self._add(_collapse("\n".join(code)), section, [])
                    fence, code = None, []
                else:
                    code.append(row)
                continue
            opened = FENCE.match(row)
            structural = opened or not row.strip() or HEADING.match(row) or ITEM.match(row) or ROW.match(row)
            if structural and run:
                self._add(markdown_text("\n".join(run)), section, [markdown_text(line) for line in run])
                run = []
            if opened:
                fence = opened.group(1)
            elif structural:
                section = self._structural(row, section)
            elif not RULE.match(row):
                run.append(row)

    def _structural(self, row: str, section: str) -> str:
        """Add a heading, list item or table row's units; the section that follows."""

        if HEADING.match(row):
            section = markdown_text(row) or section
            self._add(section, section, [])
        elif ITEM.match(row):
            self._add(markdown_text(row), section, [])
        elif ROW.match(row):
            for cell in re.split(r"(?<!\\)\|", row.strip().strip("|")):
                if not re.fullmatch(r"\s*:?-+:?\s*", cell):
                    self._add(markdown_text(cell), section, [])
        return section

    @staticmethod
    def _after_header(rows: list[str]) -> list[str]:
        """The rows after the first rule: what `--skip-header` leaves out of the baseline."""

        for index, row in enumerate(rows):
            if RULE.match(row):
                return rows[index + 1:]
        return rows

    def _add(self, text: str, section: str, lines: list[str]) -> None:
        if not text or NOTE.match(text):
            return
        index = len(self.units)
        parts = [line for line in lines if line] if len(lines) > 1 else [text]
        self.units.append((text, section))
        self.left.append(parts)
        self.full.append(len(parts))
        self.whole.setdefault(text, []).append(index)
        for line in set(parts) - {text}:
            self.lines.setdefault(line, []).append(index)

    def __bool__(self) -> bool:
        return bool(self.units)

    def match_whole(self, text: str) -> bool:
        """Take a unit whose whole text is `text` and that no match has touched."""

        for index in self.whole.get(text, []):
            if self.left[index] and self.full[index] == len(self.left[index]):
                self.left[index] = []
                return True
        return False

    def match_line(self, text: str) -> bool:
        """Take one line `text` from a run that still holds it."""

        for index in self.lines.get(text, []):
            if text in self.left[index]:
                self.left[index].remove(text)
                return True
        return False

    def unmatched(self) -> list[tuple[str, str]]:
        """What no match took, reworded or removed: an untouched unit once, else each line left."""

        gone = []
        for index, (text, section) in enumerate(self.units):
            left = self.left[index]
            if left and len(left) == self.full[index]:
                gone.append((text, section))
            else:
                gone += [(line, section) for line in left]
        return gone


def _marked(tag: str) -> str:
    """The opening tag `tag` with the highlight added to its style."""

    named = re.match(r"<[a-zA-Z0-9]+", tag)
    for attr in ATTR.finditer(tag, named.end() if named else 1, len(tag) - 1):
        if attr.group(1).lower() != "style":
            continue
        if attr.group(2) is None:  # a bare `style`
            return tag[: attr.start()] + f'style="{MARK}"' + tag[attr.end():]
        value = attr.group(2)
        quote = value[0] if value[0] in "\"'" else '"'
        style = value.strip(quote).rstrip().rstrip(";") if value[0] == quote else value.rstrip(";")
        style = f"{style};{MARK}" if style else MARK
        return tag[: attr.start(2)] + f"{quote}{style}{quote}" + tag[attr.end(2):]
    return tag[:-1].rstrip("/ ") + f' style="{MARK}">'


def _first(page: str, name: str) -> re.Match[str] | None:
    """The page's first opening `<name>` tag, outside comments and other tags' attributes."""

    return next((tag for tag in TAG.finditer(page) if _name(tag) == name and not tag.group(1)), None)


def _header_end(page: str) -> int | None:
    """Where `--skip-header`'s header block ends: the page's first `<hr`, or None without one."""

    rule = _first(page, "hr")
    return rule.start() if rule else None


def _note(changed: int, gone: int, sections: list[str], since: str) -> str:
    """The header note's inner HTML."""

    parts = []
    if changed:
        parts.append(f"{changed} {'paragraph' if changed == 1 else 'paragraphs'}, highlighted below")
    if gone:
        parts.append(f"{gone} earlier {'paragraph no longer appears' if gone == 1 else 'paragraphs no longer appear'}"
                     ", reworded or removed")
    if parts:
        note = (f"<strong>Changed since {html.escape(since)}</strong>: {'; '.join(parts)}. "
                f"Sections: {html.escape('; '.join(sections))}.")
    else:
        note = f"<strong>No changes since {html.escape(since)}</strong>."
    return note


def _units(page: str, start: int, tags: list[re.Match[str]]) -> list[tuple[int, int, re.Match[str] | None, str, str]]:
    """Each text segment between block tags: `(begin, end, unit tag or None, section, text)`."""

    units: list[tuple[int, int, re.Match[str] | None, str, str]] = []
    section = "Opening"
    bounds = [(start, None)] + [(tag.end(), tag) for tag in tags]
    for index, (begin, tag) in enumerate(bounds):
        end = tags[index].start() if index < len(tags) else len(page)
        text = html_text(page[begin:end])
        if not text:
            continue
        name = _name(tag) if tag is not None and not tag.group(1) else ""
        if re.fullmatch(r"h[1-6]", name):
            section = text
        units.append((begin, end, tag if name in UNIT else None, section, text))
    return units


def highlight(page: str, seen: Baseline, since: str, header: bool) -> tuple[str, int, int, list[str]]:
    """`page` marked, with its note: the count changed, the count gone, and the sections of both."""

    start = (_header_end(page) or 0) if header else 0
    if not start:
        body = _first(page, "body")
        start = body.end() if body else 0
    tags = [tag for tag in TAG.finditer(page, start) if _name(tag) in BLOCK]
    units = _units(page, start, tags)
    # Whole matches first, then lines: which paragraph comes first must not decide what matches.
    found = [seen.match_whole(text) for _, _, _, _, text in units]
    found = [hit or seen.match_line(text) for hit, (_, _, _, _, text) in zip(found, units, strict=True)]
    out, at, changed, sections = [], start, 0, []
    for hit, (begin, end, tag, section, _) in zip(found, units, strict=True):
        if hit:
            continue
        changed += 1
        if section not in sections:
            sections.append(section)
        if tag is not None:
            out += [page[at:tag.start()], _marked(tag.group(0))]
            at = tag.end()
        else:  # text outside any unit tag, such as a list item's tail after its nested list
            out += [page[at:begin], f'<span style="{MARK}">', page[begin:end], "</span>"]
            at = end
    out.append(page[at:])
    gone = seen.unmatched()
    for _, where in gone:
        if where not in sections:
            sections.append(where)
    note = _note(changed, len(gone), sections, since)
    lead = page[:start] + f'<p style="{MARK}">{note}</p>\n'
    return lead + "".join(out), changed, len(gone), sections


def _layout(markdown: str) -> str:
    """Markdown as the HTML a Drive import reads, with the renderer's extensions."""

    import markdown as md  # resolved by `sd-research-kit` before this module loads

    return md.markdown(markdown, extensions=["tables", "fenced_code", "sane_lists"])


def highlight_args(argv: list[str]) -> tuple[str, str, Path, Path, bool] | None:
    """`(previous, since, in, out, skip_header)`, or None after printing the usage."""

    previous: str | None = None
    since, rest = "the last push", list(argv)
    paths: list[str] = []
    skip_header = False
    while rest:
        word = rest.pop(0)
        if word == "--skip-header":
            skip_header = True
        elif word in ("--previous", "--since") and rest:
            value = rest.pop(0)
            previous, since = (value, since) if word == "--previous" else (previous, value)
        elif word.startswith("-"):
            print(f"sd-research-kit highlight: unknown option {word}", file=sys.stderr)
            paths = []
            break
        else:
            paths.append(word)
    if previous is None or len(paths) != 2:
        print(USAGE, file=sys.stderr)
        return None
    return previous, since, Path(paths[0]), Path(paths[1]), skip_header


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in (".md", ".markdown")


def highlight_main(argv: list[str]) -> int:
    parsed = highlight_args(argv)
    if parsed is None:
        return 2
    previous, since, source, target, skip_header = parsed
    try:
        before = Path(previous).read_text(encoding="utf-8")
        page = source.read_text(encoding="utf-8")
    except OSError as error:
        print(f"sd-research-kit highlight: {error}", file=sys.stderr)
        return 2
    markdown_in = is_markdown(source)
    seen = Baseline(before, header=skip_header)
    if not before.strip():
        print(f"sd-research-kit highlight: {previous} is empty: a first push has nothing to compare; "
              "upload without highlight", file=sys.stderr)
        return 2
    page = _layout(page) if markdown_in else page
    if skip_header and _header_end(page) is None:
        print(f"sd-research-kit highlight: --skip-header: no <hr> in {source} ends a header block", file=sys.stderr)
        return 2
    marked, changed, gone, sections = highlight(page, seen, since, header=skip_header)
    try:
        target.write_text(marked, encoding="utf-8")
    except OSError as error:
        print(f"sd-research-kit highlight: {error}", file=sys.stderr)
        return 2
    print(f"changed: {changed} since {since}")
    if gone:
        print(f"gone: {gone}")
    if sections:
        print(f"sections: {'; '.join(sections)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - run through sd-research-kit
    sys.exit(highlight_main(sys.argv[1:]))
