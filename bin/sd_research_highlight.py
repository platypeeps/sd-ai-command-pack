"""`sd-research-kit highlight`: mark what changed in a Google Doc update (sd:7252).

Every Google Doc update the framework makes marks the paragraphs that changed
since the copy the reader last saw, so the reader rereads only those. The
baseline is that copy: the Doc's current text, read back with workspace-mcp
`get_doc_as_markdown` (`comment_mode: none`) just before the update, so a
reviewer's own edits count as already seen.

    sd-research-kit highlight --previous <baseline.md> [--since <time>] <in> <out.html>

`<in>` is the HTML about to be uploaded, or Markdown (`.md`), which is laid out
as HTML first, as a mirror's `content` is. Each `<p>` and `<li>` whose text is
not in the baseline gets `background-color:#fff2a8`, and one note, highlighted
the same way, says "Changed since <time>": the count and the changed sections.
In HTML input, what comes before the first `<hr` is the review copy's header
block (title, repository, push time): it is never compared, since its push time
changes every push, and the note goes at its end. Otherwise the note opens the
body.

A paragraph is unchanged when its text, tags stripped and whitespace collapsed,
equals the text of a line or a blank-line block of the baseline, with Markdown
syntax taken away: links keep their text, images go, bold, italic and code
marks go, and heading, quote and list markers go, with the `[ ]` checkbox Drive
adds to an imported list.

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
USAGE = "usage: sd-research-kit highlight --previous <baseline.md> [--since <time>] <in> <out.html>"
#: Every tag the scan stops at: a unit's text runs from its opening tag to the next of these.
TAG = re.compile(r"<(/?)(p|li|h[1-6]|ul|ol|hr|div|table|blockquote|pre)\b([^>]*)>", re.I)
STYLE = re.compile(r"""\bstyle=(["'])(.*?)\1""", re.I | re.S)
LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\((?:[^()\s]|\([^)]*\))*(?:\s+\"[^\"]*\")?\)")
IMAGE = re.compile(r"!\[[^\]]*\]\((?:[^()]|\([^)]*\))*\)")
LEAD = re.compile(r"^\s*(?:#{1,6}\s+|>\s*)*(?:(?:[-*+]|\d+[.)])\s+)?(?:\[[ xX]\]\s+)?")


def _flat(text: str) -> str:
    """Both sides' last step: entities, emphasis and code marks, whitespace."""

    text = html.unescape(text)
    text = text.replace("`", "").replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)[*_]+|[*_]+(?!\w)", "", text)
    return " ".join(text.split())


def html_text(fragment: str) -> str:
    return _flat(re.sub(r"<[^>]+>", "", re.sub(r"<br\b[^>]*>", " ", fragment, flags=re.I)))


def markdown_text(line: str) -> str:
    """One Markdown line or block as the text its HTML would hold."""

    text = IMAGE.sub("", line)
    text = LINK.sub(r"\1", text)
    text = re.sub(r"<(https?://[^>\s]+)>", r"\1", text)
    text = "\n".join(LEAD.sub("", row) for row in text.split("\n"))
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>~<])", r"\1", text)
    return _flat(re.sub(r"<[^>]+>", "", text))


def baseline(markdown: str) -> set[str]:
    """Every line and every blank-line block, as text: Drive may break a paragraph either way."""

    seen = {markdown_text(line) for line in markdown.splitlines()}
    seen |= {markdown_text(block) for block in re.split(r"\n\s*\n", markdown)}
    seen.discard("")
    return seen


def _marked(tag: str) -> str:
    """The opening tag `tag` with the highlight added to its style."""

    found = STYLE.search(tag)
    if not found:
        return tag[:-1].rstrip("/ ") + f' style="{MARK}">'
    style = found.group(2).rstrip().rstrip(";")
    style = f"{style};{MARK}" if style else MARK
    return tag[: found.start()] + f"style={found.group(1)}{style}{found.group(1)}" + tag[found.end():]


def highlight(page: str, seen: set[str], since: str, header: bool) -> tuple[str, int, list[str]]:
    """`page` with each unseen `<p>`/`<li>` marked and the note placed; the count and the sections."""

    start = 0
    if header:
        rule = re.search(r"<hr\b", page, re.I)
        start = rule.start() if rule else 0
    if not start:
        body = re.search(r"<body\b[^>]*>", page, re.I)
        start = body.end() if body else 0
    tags = list(TAG.finditer(page, start))
    out, at, section, changed, sections = [], start, "Opening", 0, []
    for index, tag in enumerate(tags):
        closing, name = tag.group(1), tag.group(2).lower()
        heading = re.fullmatch(r"h[1-6]", name) is not None
        if closing or name not in ("p", "li") and not heading:
            continue
        end = tags[index + 1].start() if index + 1 < len(tags) else len(page)
        text = html_text(page[tag.end():end])
        if heading:
            section = text or section
            continue
        if not text or text in seen:
            continue
        out.append(page[at:tag.start()])
        out.append(_marked(tag.group(0)))
        at = tag.end()
        changed += 1
        if section not in sections:
            sections.append(section)
    out.append(page[at:])
    if changed:
        noun = "paragraph" if changed == 1 else "paragraphs"
        note = (f"<strong>Changed since {html.escape(since)}</strong>: {changed} {noun}, highlighted below. "
                f"Sections: {html.escape('; '.join(sections))}.")
    else:
        note = f"<strong>No changes since {html.escape(since)}</strong>."
    lead = page[:start] + f'<p style="{MARK}">{note}</p>\n'
    return lead + "".join(out), changed, sections


def _layout(markdown: str) -> str:
    """Markdown as the HTML a Drive import reads, with the renderer's extensions."""

    import markdown as md  # resolved by `sd-research-kit` before this module loads

    return md.markdown(markdown, extensions=["tables", "fenced_code", "sane_lists"])


def highlight_args(argv: list[str]) -> tuple[str, str, Path, Path] | None:
    """`(previous, since, in, out)`, or None after printing the usage."""

    previous: str | None = None
    since, rest = "the last push", list(argv)
    paths: list[str] = []
    while rest:
        word = rest.pop(0)
        if word in ("--previous", "--since") and rest:
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
    return previous, since, Path(paths[0]), Path(paths[1])


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in (".md", ".markdown")


def highlight_main(argv: list[str]) -> int:
    parsed = highlight_args(argv)
    if parsed is None:
        return 2
    previous, since, source, target = parsed
    try:
        before = Path(previous).read_text(encoding="utf-8")
        page = source.read_text(encoding="utf-8")
    except OSError as error:
        print(f"sd-research-kit highlight: {error}", file=sys.stderr)
        return 2
    seen = baseline(before)
    if not seen:
        print(f"sd-research-kit highlight: {previous} is empty: a first push has nothing to compare; "
              "upload without highlight", file=sys.stderr)
        return 2
    markdown_in = is_markdown(source)
    page = _layout(page) if markdown_in else page
    marked, changed, sections = highlight(page, seen, since, header=not markdown_in)
    try:
        target.write_text(marked, encoding="utf-8")
    except OSError as error:
        print(f"sd-research-kit highlight: {error}", file=sys.stderr)
        return 2
    if changed:
        print(f"changed: {changed} since {since}")
        print(f"sections: {'; '.join(sections)}")
    else:
        print(f"changed: 0 since {since}")
    return 0


if __name__ == "__main__":  # pragma: no cover - run through sd-research-kit
    sys.exit(highlight_main(sys.argv[1:]))
