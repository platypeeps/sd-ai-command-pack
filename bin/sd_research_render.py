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
    figs     optional   [(number, "pass|fail|warn|flat", label, sub), ...];
                        a state carries its glyph: pass ●, warn ▲, fail ■
    legend   optional   caption under the figures
    footer   optional   footer HTML
    skip     optional   ["Section title", ...] dropped from the rendered page
    links    optional   [(label, href), ...] shown in the rail
    sibling  optional   raw HTML for a "Companions" rail block
    notion   optional   dict(space="...", page="...") — the Notion mirror this
                        document is designated for. The default folder is the
                        page id the `sd.notion_private_folder` (or
                        `sd.notion_team_folder`) setting holds, with the repo's own
                        page under it; `space=` overrides that, by id or page
                        URL where one is known
    drive    optional   dict(folder="...", file="...") — the Google Drive mirror
                        this document is designated for. With neither key, the
                        document publishes to the dashboard and nowhere else;
                        with both, it has two mirrors rather than a choice.

Writes one file per doc, then one manifest:

    docs/dashboard/<out>.html   standalone — opens with file://, and is what the
                                dashboard's Documents tab lists and serves
    docs/dashboard/research.json
                                PROJECT, the sha256 of the research.conf.py
                                executed, each doc's string fields, and
                                a true or false per destination it
                                designates (`notion`, `drive`): the
                                dashboard reads a config it cannot read
                                without running it from here

`docs/dashboard/` is gitignored: it is regenerated on every commit, and the
dashboard serves whatever it finds there.

Rendering ends by writing each document's Markdown into the Obsidian vault,
registering `docs/dashboard/` with the dashboard, and queueing a sync for every
document that designates an outward destination. See `sd_research_publish` and
`skills/_shared/references/publication-contract.md`.

Never hand-wrap HTML for publishing; that mismatch is what this exists to prevent.
"""

import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("needs python-markdown:  pip install markdown")

from sd_lib import GIT_TIMEOUT_SECONDS
from sd_research_fonts import FONTS_CSS
from sd_research_publish import (
    CONF_DIGEST,
    DESTINATIONS,
    execute_conf,
    exit_status,
    project_label,
    publish,
)
from sd_research_tokens import THEME_JS, TOKENS_CSS

CSS = TOKENS_CSS

#: The foundation's state grammar: a glyph beside every state colour, with its
#: name for a screen reader. `flat` and `inert` are counts, not states.
GLYPHS = {
    "pass": ("●", "Normal"),
    "warn": ("▲", "Caution"),
    "caution": ("▲", "Caution"),
    "fail": ("■", "Warning"),
}

#: The foundation's theme control. theme.js marks the chosen button with
#: `aria-pressed`; a page where it cannot run hides the control (PAGE_CSS).
THEME_CONTROL = ('<div class="theme" role="group" aria-label="Theme">'
                 + "".join('<button type="button" data-theme-choice="%s">%s</button>' % (c, c.title())
                           for c in ("dark", "light", "system"))
                 + "</div>")

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


#: The class an embedded Archify diagram's rules are scoped to (pack sd:5918).
ARCHIFY = "archify-diagram"
ARCHIFY_SVG_RE = re.compile(r"<svg\b[^>]*archify-diagram-title[^>]*>.*?</svg>", re.S)
#: The page's theme when the reader picked none: "system", or no theme.js.
PAGE_UNPICKED = ':root:not([data-theme="dark"]):not([data-theme="light"])'
#: A comment, a string or a brace: the tokens css_blocks matches blocks by.
CSS_TOKEN_RE = re.compile(r"""/\*.*?(?:\*/|\Z)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{}]""", re.S)


def css_blocks(css):
    """Each top-level `prelude { body }` of `css`, braces matched (pack sd:5944).

    A brace in a comment or a string counts for nothing, and a comment
    leaves the prelude: `/* Font */ svg` is the selector `svg`.
    """
    depth, at, start, prelude = 0, 0, 0, ""
    for token in CSS_TOKEN_RE.finditer(css):
        kind = token.group(0)
        if kind == "{":
            if not depth:
                prelude, start = prelude + css[at:token.start()], token.end()
            depth += 1
        elif kind == "}" and depth:
            depth -= 1
            if not depth:
                yield prelude.strip(), css[start:token.start()]
                prelude, at = "", token.end()
        elif kind.startswith("/*") and not depth:
            prelude, at = prelude + css[at:token.start()], token.end()
    if depth:
        yield prelude.strip(), css[start:]


def scope_selector(prelude, scope):
    """`prelude` under `scope`, or None for a rule meant for the host page (`:root`, `[data-…]`)."""
    parts, depth, last = [], 0, 0
    for index, char in enumerate(prelude + ","):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(char, 0)
        if char == "," and not depth:
            parts.append(prelude[last:index].strip())
            last = index + 1
    scoped = []
    for part in parts:
        if part in (":root", "svg"):
            scoped.append(scope)
        elif re.match(r"svg(?![\w-])", part):
            scoped.append(scope + part[3:])
        elif part.startswith((":root", "[data-")):
            return None
        else:
            scoped.append(scope + " " + part)
    return ", ".join(dict.fromkeys(scoped))  # `:root, svg` is the one element


def scope_rules(css, scope):
    """Archify's rules, every selector under `scope` and each theme following the page's."""
    rules = []
    for prelude, body in css_blocks(css):
        if prelude.startswith(("@keyframes", "@font-face")):
            rules.append("%s {%s}" % (prelude, body))
            continue
        if prelude.startswith("@media"):
            light = prelude.startswith("@media (prefers-color-scheme: light)")
            inner = scope_rules(body, "%s %s" % (PAGE_UNPICKED, scope) if light else scope)
            if inner:
                rules.append("%s {%s}" % (prelude, inner))
            continue
        theme = re.fullmatch(r'svg\[data-theme="(\w+)"\]', prelude)
        selector = '[data-theme="%s"] %s' % (theme.group(1), scope) if theme else scope_selector(prelude, scope)
        if selector:
            rules.append("%s {%s}" % (selector, body))
    return "\n".join(rules)


def scope_archify(text):
    """Scope each Archify SVG export in `text` to its own element (pack sd:5918).

    Archify's export styles `:root`, `svg` and `[data-theme]` for the whole
    page, so a pasted one would restyle the research page. Its rules move
    under `.archify-diagram`, its light and dark sets follow the page's theme
    control, and its trailing whitespace and blank lines go: its `@keyframes`
    lines end in a space. An SVG that carries the class already is left alone.
    """
    def scope_one(match):
        svg = match.group(0)
        tag = svg[:svg.index(">") + 1]
        styled = re.search(r"<style>(.*?)</style>", svg, re.S)
        if re.search(r'\sclass="[^"]*\b%s\b' % ARCHIFY, tag) or not styled:
            return svg
        selector = "." + ARCHIFY
        css = scope_rules(styled.group(1).replace("&gt;", ">"), selector)
        css += "\n%s {max-width:100%%;height:auto;display:block;margin:0 auto}" % selector
        svg = svg[:styled.start()] + "<style>" + css.replace(">", "&gt;") + "</style>" + svg[styled.end():]
        svg = svg.replace("<svg ", '<svg class="%s" ' % ARCHIFY, 1)
        svg = re.sub(r'\s(?:tabindex|data-theme)="[^"]*"|\sstyle=""', "", svg)
        return "\n".join(line.rstrip() for line in svg.splitlines() if line.strip())

    return ARCHIFY_SVG_RE.sub(scope_one, text)


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
    body_md = drop_sections(loosen_lists(scope_archify(body_md)), cfg.get("skip", []))

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
        nav.append('<a href="#%s" title="%s"><em>%s</em><span>%s</span></a>'
                   % (item["id"], html.escape(label), html.escape(num), html.escape(label, quote=False)))

    def glyph(state):
        if state not in GLYPHS:
            return ""
        mark, name = GLYPHS[state]
        return '<span class="g" role="img" aria-label="%s">%s</span>' % (name, mark)

    figs = "".join(
        '<div class="fig"><span class="n is-%s">%s%s</span><span class="l">%s</span><span class="s">%s</span></div>'
        % (t, glyph(t), html.escape(str(n)), label, html.escape(s))
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
             # In <head> and not deferred, so the stored theme applies before
             # first paint. The one script a page carries: the dashboard runs
             # it only once its policy pins this script's digest.
             "<script>%s</script>" % THEME_JS,
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
             "  " + THEME_CONTROL,
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


#: The string fields of a DOCS entry the manifest carries; `links` is the one list.
MANIFEST_FIELDS = ("src", "out", "title", "eyebrow", "stand")


def write_manifest(repo, project, docs, digest):
    """Write docs/dashboard/research.json atomically: the dashboard reads it
    instead of executing research.conf.py, and a reader never sees half a file.

    Strings only: a field that is not a string, and a link that is not a pair
    of strings, is left out rather than coerced. Then one flag per
    destination in `DESTINATIONS`: whether the document designates it, read
    as `publish` reads it (True or a dict), so a designation a config sets
    in a loop reaches the dashboard too (pack sd:5936).
    """
    entries = []
    for cfg in docs:
        entry = {key: cfg[key] for key in MANIFEST_FIELDS if isinstance(cfg.get(key), str)}
        entry["links"] = [[label, href] for label, href in
                          (link for link in cfg.get("links", []) if isinstance(link, (list, tuple)) and len(link) == 2)
                          if isinstance(label, str) and isinstance(href, str)]
        entry.update({dest.name: cfg.get(dest.name) is True or isinstance(cfg.get(dest.name), dict)
                      for dest in DESTINATIONS})
        entries.append(entry)
    manifest = {"version": 1, "project": project, "conf_sha256": digest, "docs": entries}
    path = os.path.join(repo, "docs", "dashboard", "research.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    partial = path + ".partial"
    with open(partial, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    os.replace(partial, path)
    return path


def main() -> int:
    # R10-D6: the repository is the one the caller is standing in. The kit took
    # `render [repo_dir]` before it moved here, which is the shape that lets a
    # session act on a checkout nobody pointed it at.
    repo = os.getcwd()
    ns = execute_conf(Path(repo), "render")
    if ns is None:
        sys.exit("no research.conf.py in %s" % repo)
    # `publish()` takes PROJECT as written and owns the fallback, so the
    # badge and the dashboard label are one value (sd:3513).
    project = ns.get("PROJECT")
    badge = project_label(Path(repo), project)
    print("%s  ->  docs/dashboard/" % os.path.basename(repo))
    for cfg in ns["DOCS"]:
        build_one(repo, cfg, badge)
    # After the pages: a render stopped between them leaves the last manifest,
    # whose digest the dashboard shows as an older render.
    write_manifest(repo, badge, ns["DOCS"], ns[CONF_DIGEST])

    # Publication is the default, not a step the user asks for: a document
    # nobody can find was not delivered. Registration is idempotent and
    # enqueueing skips what is unchanged, so re-rendering costs nothing and
    # leaves no duplicates.
    reports = publish(Path(repo), project, ns["DOCS"])
    for line in reports:
        print("  %s" % line)
    return exit_status(reports)


if __name__ == "__main__":
    sys.exit(main())
