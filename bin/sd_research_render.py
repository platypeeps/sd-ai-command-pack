#!/usr/bin/env python3
"""Render a research repo's markdown into standalone + publishable HTML.

Usage
-----
    sd-research-kit render        # from inside the research repo

`render` takes no argument: every verb acts on the current working directory
(`bin/sd-research-kit:133` rejects one). The entrypoint bootstraps `markdown`
itself, so there is nothing to install first.

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
    notion   optional   dict(space="...", page="...") — the Notion mirror this
                        document is designated for. The default folder is the
                        page id `$SD_NOTION_PRIVATE_FOLDER` (or
                        `$SD_NOTION_TEAM_FOLDER`) holds, with the repo's own
                        page under it; `space=` overrides that, by id or page
                        URL where one is known
    drive    optional   dict(folder="...", file="...") — the Google Drive mirror
                        this document is designated for. With neither key, the
                        document publishes to the dashboard and nowhere else;
                        with both, it has two mirrors rather than a choice.

Writes one file per doc:

    docs/dashboard/<out>.html   standalone — opens with file://, and is what the
                                dashboard's Documents tab lists and serves

`docs/dashboard/` is gitignored: it is regenerated on every commit, and the
dashboard serves whatever it finds there.

Rendering ends by writing each document's Markdown into the Obsidian vault,
registering `docs/dashboard/` with the dashboard, and queueing a sync for every
document that designates an outward destination. See `sd_research_publish` and
`skills/_shared/references/publication-contract.md`.

Never hand-wrap HTML for publishing; that mismatch is what this exists to prevent.
"""

import html
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import markdown
except ImportError:
    sys.exit("needs python-markdown:  pip install markdown")

from sd_lib import GIT_TIMEOUT_SECONDS
from sd_research_fonts import FONTS_CSS
from sd_research_publish import publish, repo_home, trust_conf
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
            capture_output=True, text=True, check=True, cwd=repo,
            timeout=GIT_TIMEOUT_SECONDS).stdout.split()
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
             # Fonts are embedded, not linked. The dashboard serves documents under
             # `default-src 'none'`, which blocks an external stylesheet: a linked
             # Google Fonts page falls back to system fonts. See sd_research_fonts.
             "<style>%s</style>" % FONTS_CSS,
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

    out_dir = os.path.join(repo, "docs", "dashboard")
    os.makedirs(out_dir, exist_ok=True)

    # One form, not two. The content-only `artifact/` copy was documented as
    # legacy with nothing consuming it, and the dashboard folder's contract is
    # that everything in it is published -- so carrying dead output into it
    # would publish a file no reader was ever meant to open.

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
    # nosec B102 - research.conf.py is a file in the repo being rendered, at the
    # same trust level as this script, and the format needs execution: at least
    # one live config builds its DOCS list with a loop.
    with open(conf, "rb") as handle:
        source = handle.read()
    exec(compile(source, conf, "exec"), ns)  # nosec B102
    # The hook renders after a pull or checkout only a config a render has
    # executed before (sd:1376). This is that record.
    trust_conf(Path(repo), source)
    # The fallback badge comes from the repository's name, not the checkout's:
    # a worktree is called after its branch, and its name is nobody's project.
    project = ns.get("PROJECT", repo_home(Path(repo)).name.split("-")[0].upper())
    print("%s  ->  docs/dashboard/" % os.path.basename(repo))
    for cfg in ns["DOCS"]:
        build_one(repo, cfg, project)

    # Publication is the default, not a step the user asks for: a document
    # nobody can find was not delivered. Registration is idempotent and
    # enqueueing skips what is unchanged, so re-rendering costs nothing and
    # leaves no duplicates.
    for line in publish(Path(repo), project, ns["DOCS"]):
        print("  %s" % line)


if __name__ == "__main__":
    main()
