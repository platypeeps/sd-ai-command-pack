#!/usr/bin/env python3
"""Render a research repo's markdown into standalone + publishable HTML.

Usage
-----
    pip install markdown
    research-kit render [repo_dir]        # or: python3 ~/repos/system/local-research-kit/render.py [repo_dir]

Reads `<repo>/research.conf.py`, which must define:

    PROJECT = "MCP"                 # rail badge
    DOCS = [ {...}, {...} ]         # one dict per rendered page

Each DOCS entry:

    src      required   path to the markdown, relative to the repo root
    out      required   basename of the output, no extension
    title    required   <title> — also the artifact/gallery name
    h1       optional   page headline (defaults to title)
    eyebrow  optional   small uppercase line above the h1
    stand    optional   one-sentence standfirst
    meta     optional   provenance line (HTML allowed)
    vtitle   optional   heading for the verdict strip
    figs     optional   [(number, "pass|fail|warn|flat", label, sub), ...]
    legend   optional   caption under the figures
    footer   optional   footer HTML
    skip     optional   ["Section title", ...] dropped from the rendered page
    links    optional   [(label, href), ...] shown in the rail
    sibling  optional   raw HTML for a "Companions" rail block

Writes two files per doc:

    build/<out>.html            standalone — opens with file://, the local reading form
    build/artifact/<out>.html   content-only — legacy; nothing consumes it now that
                                research is published to Notion, not as artifacts

Never hand-wrap HTML for publishing; that mismatch is what this exists to prevent.
"""

import html
import os
import re
import subprocess
import sys
from typing import Any

try:
    import markdown
except ImportError:
    sys.exit("needs python-markdown:  pip install markdown")

from sd_research_tokens import TOKENS_CSS

CSS = TOKENS_CSS

LIST_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s)")


def loosen_lists(md):
    """python-markdown renders a list glued to the line above as run-on prose.
    Insert the blank line it needs, never inside a fence."""
    out: list[str] = []
    fence = False
    for line in md.split("\n"):
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and LIST_RE.match(line) and out:
            prev = out[-1]
            if prev.strip() and not LIST_RE.match(prev) and not prev.lstrip().startswith((">", "|", "#")):
                out.append("")
        out.append(line)
    return "\n".join(out)


def drop_sections(md, titles):
    for t in titles:
        md = re.sub(r"(?ms)^## [^\n]*" + re.escape(t) + r"[^\n]*\n.*?(?=^## |\Z)", "", md)
    return md


def doc_version(repo, src):
    """Created date, version, updated date — from git history of the file.
    v1.0 is the first commit. Falls back to mtime where there is no git."""
    try:
        out = subprocess.run(
            ["git", "log", "--follow", "--date=format-local:%Y-%m-%d", "--format=%ad", "--", src],
            capture_output=True, text=True, check=True, cwd=repo).stdout.split()
        if out:
            return out[-1], "v1.%d" % (len(out) - 1), out[0]
    except Exception:
        pass
    import datetime
    d = datetime.date.fromtimestamp(os.path.getmtime(os.path.join(repo, src))).isoformat()
    return d, "v1.0", d


def build_one(repo, cfg, project):
    src = os.path.join(repo, cfg["src"])
    raw = open(src).read()

    # drop the H1 + provenance block above the first '---'; the page has a masthead.
    # Without that block, drop just the leading H1 so it does not duplicate the masthead.
    if "\n---\n" in raw.split("\n## ")[0]:
        body_md = raw.split("\n---\n", 1)[1]
    else:
        body_md = re.sub(r"\A\s*#\s[^\n]*\n", "", raw)
    body_md = drop_sections(loosen_lists(body_md), cfg.get("skip", []))

    mdx = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"])
    body = mdx.convert(body_md)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")

    def flatten(tokens):
        for t in tokens:
            yield t
            yield from flatten(t.get("children", []))

    nav = []
    for item in flatten(mdx.toc_tokens):
        if item["level"] != 2:
            continue
        text = html.unescape(re.sub(r"<[^>]+>", "", item["name"]))
        m = re.match(r"^(\d+[a-z]?)[.)]\s*(.+)$", text)
        num, label = (m.group(1), m.group(2)) if m else ("", text)
        label = label.split(" — ")[0].split(": ")[0].split(" (")[0]
        nav.append('<a href="#%s"><em>%s</em><span>%s</span></a>'
                   % (item["id"], html.escape(num), html.escape(label, quote=False)))

    figs = "".join(
        '<div class="fig"><span class="n is-%s">%s</span><span class="l">%s</span><span class="s">%s</span></div>'
        % (t, html.escape(str(n)), label, html.escape(s))
        for n, t, label, s in cfg.get("figs", []))

    verdict = ""
    if figs:
        verdict = ('<section class="verdict"><h2>%s</h2><div class="figs">%s</div>%s</section>'
                   % (cfg.get("vtitle", "At a glance"), figs,
                      '<div class="legend">%s</div>' % cfg["legend"] if cfg.get("legend") else ""))

    links = "".join(
        '<a href="%s">%s</a><br>' % (h, html.escape(label)) for label, h in cfg.get("links", [])
    )
    sibling = cfg.get("sibling", "")
    created, ver, updated = doc_version(repo, cfg["src"])

    parts = ["<title>%s</title>" % html.escape(cfg["title"]),
             '<link rel="preconnect" href="https://fonts.googleapis.com">',
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&'
             'family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">',
             "<style>%s</style>" % CSS,
             '<div class="wrap">',
             '<aside class="rail">',
             '  <div class="badge"><b>%s</b><span>research</span></div>' % html.escape(project),
             "  <nav>%s</nav>" % "".join(nav),
             ('  <div class="railnote"><strong>Companions</strong>%s</div>' % sibling) if sibling else "",
             ('  <div class="railnote"><strong>Also here</strong>%s</div>' % links) if links else "",
             '  <div class="railnote"><strong>Source</strong><code>%s</code></div>' % html.escape(cfg["src"]),
             "</aside>",
             "<main>",
             ('  <p class="eyebrow">%s</p>' % cfg["eyebrow"]) if cfg.get("eyebrow") else "",
             "  <h1>%s</h1>" % html.escape(cfg.get("h1", cfg["title"])),
             '  <p class="subtitle">Created <b>%s</b> · Updated <b>%s</b> · <b>%s</b></p>' % (created, updated, ver),
             ('  <p class="standfirst">%s</p>' % cfg["stand"]) if cfg.get("stand") else "",
             ('  <div class="meta">%s</div>' % cfg["meta"]) if cfg.get("meta") else "",
             verdict,
             '  <article class="doc">%s</article>' % body,
             ('  <footer>%s</footer>' % cfg["footer"]) if cfg.get("footer") else "",
             "</main>", "</div>"]
    content = "\n".join(p for p in parts if p)

    out_dir = os.path.join(repo, "build")
    os.makedirs(os.path.join(out_dir, "artifact"), exist_ok=True)

    # artifact form: content only — the Artifact tool supplies the skeleton
    art = os.path.join(out_dir, "artifact", cfg["out"] + ".html")
    open(art, "w").write(content + "\n")

    # standalone form: openable with file://
    standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                  '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
                  + content.split('<div class="wrap">')[0]
                  + '</head>\n<body>\n<div class="wrap">'
                  + content.split('<div class="wrap">', 1)[1]
                  + "\n</body>\n</html>\n")
    page = os.path.join(out_dir, cfg["out"] + ".html")
    open(page, "w").write(standalone)

    print("  %-28s %5d KB  %2d sections  %s" % (cfg["out"] + ".html", len(standalone) // 1024, len(nav), ver))
    return page


def main():
    # R10-D6: the repository is the one the caller is standing in. The kit took
    # `render [repo_dir]` before it moved here, which is the shape that lets a
    # session act on a checkout nobody pointed it at.
    repo = os.getcwd()
    conf = os.path.join(repo, "research.conf.py")
    if not os.path.exists(conf):
        sys.exit("no research.conf.py in %s" % repo)
    ns: dict[str, Any] = {}
    exec(compile(open(conf).read(), conf, "exec"), ns)
    project = ns.get("PROJECT", os.path.basename(repo).split("-")[0].upper())
    print("%s  ->  build/" % os.path.basename(repo))
    for cfg in ns["DOCS"]:
        build_one(repo, cfg, project)


if __name__ == "__main__":
    main()
