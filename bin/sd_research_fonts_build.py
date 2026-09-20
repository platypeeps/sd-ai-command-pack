#!/usr/bin/env python3
"""Vendor the research renderer's Latin woff2 faces and write the CSS module.

    make fonts

The dashboard serves documents under `default-src 'none'`, so a linked Google
Fonts stylesheet does not load and a served page falls back to system fonts.
The faces therefore ship inside the page as data: URIs, which also makes a
rendered page identical over `file://` with no network at read time.

This is the only thing that writes `bin/sd_research_fonts.py`. The module is
generated and committed: `render` must work on a machine with no network, so
resolving fonts at render time is not an option, and a 246 KB generated file in
git is the cost of that.

Only the `/* latin */` subset is kept. The other Google subsets -- cyrillic,
greek, vietnamese, latin-ext -- are a further 1.5 MB for glyphs no research
document has used, and a subset that is absent falls back rather than failing.

Vendored files are renamed on the way in. Google serves them under a hashed
name that says nothing about what it holds, and a directory of those cannot be
reviewed: `ibm-plex-mono-500.woff2` can.
"""

from __future__ import annotations

import base64
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
MODULE = HERE / "sd_research_fonts.py"

#: The families the renderer's tokens name, as a css2 `family=` spec each.
#: Changing this list is the only edit this file expects; rerun `make fonts`.
FAMILIES = [
    "Archivo:wght@400..700",
    "IBM+Plex+Mono:wght@400;500;600",
    "Source+Serif+4:wght@400..600",
]

#: Google serves woff2 only to a browser it recognises. Without this it returns
#: a TrueType stylesheet, which is four times the bytes and renders worse.
AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

BLOCK = re.compile(r"/\* (?P<subset>[\w-]+) \*/\s*@font-face \{(?P<body>.*?)\}", re.S)
FIELD = {
    "family": re.compile(r"font-family:\s*'([^']+)'"),
    "style": re.compile(r"font-style:\s*([\w-]+)"),
    "weight": re.compile(r"font-weight:\s*([\d ]+)"),
    "url": re.compile(r"src:\s*url\(([^)]+)\)"),
}


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - https, fixed host
        return response.read()


def face_slug(family: str, weight: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")
    return "%s-%s" % (stem, weight.replace(" ", "-"))


def latin_faces() -> list[dict[str, str]]:
    """One record per Latin face, in the order the families are declared."""
    faces: list[dict[str, str]] = []
    for spec in FAMILIES:
        url = "https://fonts.googleapis.com/css2?family=%s&display=swap" % spec
        css = fetch_url(url).decode("utf-8")
        found = 0
        for match in BLOCK.finditer(css):
            if match.group("subset") != "latin":
                continue
            body = match.group("body")
            record = {}
            for name, pattern in FIELD.items():
                hit = pattern.search(body)
                if hit is None:
                    sys.exit("%s: a latin face has no %s" % (spec, name))
                record[name] = hit.group(1).strip()
            faces.append(record)
            found += 1
        if not found:
            sys.exit("%s: no latin face in the served CSS" % spec)
    return faces


def build_fonts() -> int:
    faces = latin_faces()
    FONTS.mkdir(exist_ok=True)

    # One @font-face per unique file. A variable font is served once for its
    # whole weight range, so emitting a face per requested weight would embed
    # the same 120 KB three times.
    kept: dict[str, str] = {}
    rules: list[str] = []
    for face in faces:
        name = face_slug(face["family"], face["weight"]) + ".woff2"
        if face["url"] in kept:
            continue
        data = fetch_url(face["url"])
        (FONTS / name).write_bytes(data)
        kept[face["url"]] = name
        rules.append(
            "@font-face{font-family:'%s';font-style:%s;font-weight:%s;"
            "font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2')}"
            % (
                face["family"],
                face["style"],
                face["weight"],
                base64.b64encode(data).decode("ascii"),
            )
        )

    stale = [p for p in FONTS.glob("*.woff2") if p.name not in set(kept.values())]
    for path in stale:
        path.unlink()

    MODULE.write_text(
        '"""Vendored Latin woff2 faces as data: URIs. Generated -- do not edit.\n'
        "\n"
        "Written by `bin/sd_research_fonts_build.py`; regenerate with `make fonts`\n"
        "after changing its family list. The faces are embedded rather than linked\n"
        "because the dashboard serves documents under `default-src 'none'`, which\n"
        "blocks an external stylesheet: a linked page falls back to system fonts.\n"
        "\n"
        "One @font-face per unique file. Archivo and Source Serif 4 are variable, so\n"
        "their weight ranges collapse into a single face instead of one copy each.\n"
        '"""\n'
        "\n"
        'FONTS_CSS = """%s"""\n' % "".join(rules),
        encoding="utf-8",
    )

    print("%d faces -> %s (%d bytes)" % (len(rules), MODULE.name, MODULE.stat().st_size))
    for name in sorted(kept.values()):
        print("  %s  %d bytes" % (name, (FONTS / name).stat().st_size))
    for path in stale:
        print("  removed %s" % path.name)
    return 0


if __name__ == "__main__":
    sys.exit(build_fonts())
