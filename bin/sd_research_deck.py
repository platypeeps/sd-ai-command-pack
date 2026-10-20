#!/usr/bin/env python3
"""Build an experiment's status deck, and the roundup of several, from `deck.json`.

`deck.json` sits beside the status brief, `30-brief/deck.json`, and holds the
slides the brief's status sections condense to. The agent that updates the
brief updates it; this file only lays it out. The standard is
`skills/sd-research-repo/references/conventions.md`, section **Status brief**.

    sd-research-kit deck                          # this repo: docs/dashboard/deck.pptx
    sd-research-kit roundup <out.pptx> <deck.json> ...

`roundup` gives each experiment a title page ("Experiment 1 of 4"), then its
slides, and keeps one call to action, on the last slide. Both write PowerPoint
through python-pptx; nothing here uploads, imports or sends. A Slides import is
the drain's or the operator's step, not this one.

The look is the theme: `THEME` below, overridden key by key by the deck's own
`theme` object. A roundup takes the first deck's theme. A `logo` is a PNG path,
relative to the deck.json that names it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

DECK = Path("30-brief") / "deck.json"
OUT = Path("docs") / "dashboard" / "deck.pptx"
ROUNDUP = Path("docs") / "dashboard" / "roundup.pptx"

#: The deck's own slides: a status deck is short, and a roundup repeats it per experiment.
SLIDES = 3
CARDS = 6
#: With a track, the cards share the slide with it and fit one row.
TRACK_CARDS = 3
STAGES = (2, 5)
TEXT = 240
TITLE = 90
STATES = ("done", "now", "next")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
URL = re.compile(r"https?://[^\s<>\"']+")

THEME: dict[str, Any] = {
    "font": "Onest",
    "ink": "#0A090C",
    "accent": "#7651B1",
    "muted": "#5B5B5B",
    "rule": "#B7B7B7",
    "paper": "#F4F4F4",
    "card": "#FFFFFF",
    "tones": {
        "done": ["#E8E4F1", "#503A82"],
        "now": ["#7651B1", "#FFFFFF"],
        "planned": ["#E6E6E5", "#444444"],
        "owner": ["#FCE4AE", "#0A090C"],
    },
    "logo": None,
    "cta": None,
}
COLOUR = re.compile(r"#[0-9A-Fa-f]{6}")

#: The 16:9 page, in points.
PAGE = (720, 405)
MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


class Invalid(ValueError):
    """A deck.json this builder refuses, with the path of the bad value."""


def _text(value: Any, where: str, cap: int = TEXT, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{where}: a non-empty string is required")
    if len(value) > cap:
        raise Invalid(f"{where}: {len(value)} characters; at most {cap}")
    if "—" in value:
        raise Invalid(f"{where}: an em dash; use a comma, a colon or two sentences")
    return value


def _keys(obj: Any, where: str, allowed: set[str], required: frozenset[str] | set[str] = frozenset()) -> dict:
    if not isinstance(obj, dict):
        raise Invalid(f"{where}: an object is required")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise Invalid(f"{where}: unknown key {', '.join(unknown)}")
    missing = sorted(required - set(obj))
    if missing:
        raise Invalid(f"{where}: missing {', '.join(missing)}")
    return obj


def _link(obj: Any, where: str) -> dict:
    _keys(obj, where, {"text", "url"}, {"text", "url"})
    _text(obj["text"], f"{where}.text")
    if not isinstance(obj["url"], str) or not URL.fullmatch(obj["url"]):
        raise Invalid(f"{where}.url: an http or https URL is required")
    return obj


def theme(override: Any, where: str = "theme") -> dict:
    """`THEME` with the deck's overrides; every colour checked, tones merged by name."""
    merged = json.loads(json.dumps(THEME))
    if override is None:
        return merged
    _keys(override, where, set(THEME))
    for key, value in override.items():
        if key == "tones":
            _keys(value, f"{where}.tones", set(THEME["tones"]))
            for tone, pair in value.items():
                if (not isinstance(pair, list) or len(pair) != 2
                        or not all(isinstance(c, str) and COLOUR.fullmatch(c) for c in pair)):
                    raise Invalid(f"{where}.tones.{tone}: two #RRGGBB colours, fill then ink")
                merged["tones"][tone] = pair
        elif key == "font":
            merged[key] = _text(value, f"{where}.font", 60)
        elif key == "logo":
            merged[key] = _text(value, f"{where}.logo", 400)
        elif key == "cta":
            merged[key] = _link(value, f"{where}.cta")
        elif not isinstance(value, str) or not COLOUR.fullmatch(value):
            raise Invalid(f"{where}.{key}: a #RRGGBB colour is required")
        else:
            merged[key] = value
    return merged


def check_deck(deck: Any, where: str = "deck") -> dict:
    """The deck as given, or `Invalid` naming the first value it refuses."""
    _keys(deck, where, {"name", "tagline", "date", "theme", "slides"}, {"name", "tagline", "date", "slides"})
    _text(deck["name"], f"{where}.name", 60)
    _text(deck["tagline"], f"{where}.tagline", 60)
    if not isinstance(deck["date"], str) or not DATE.fullmatch(deck["date"]):
        raise Invalid(f"{where}.date: YYYY-MM-DD is required")
    theme(deck.get("theme"), f"{where}.theme")
    slides = deck["slides"]
    if not isinstance(slides, list) or not 1 <= len(slides) <= SLIDES:
        raise Invalid(f"{where}.slides: 1 to {SLIDES} slides")
    for n, slide in enumerate(slides):
        _slide(slide, f"{where}.slides[{n}]")
    return deck


def _slide(slide: Any, at: str) -> None:
    _keys(slide, at, {"eyebrow", "title", "accent", "track", "cards", "foot", "foot_label", "link"},
          {"eyebrow", "title"})
    _text(slide["eyebrow"], f"{at}.eyebrow", 80)
    _text(slide["title"], f"{at}.title", TITLE)
    _text(slide.get("accent"), f"{at}.accent", TITLE, required=False)
    _text(slide.get("foot"), f"{at}.foot", required=False)
    _text(slide.get("foot_label"), f"{at}.foot_label", 20, required=False)
    if "foot_label" in slide and "foot" not in slide:
        raise Invalid(f"{at}.foot_label: needs a foot")
    if "link" in slide:
        _link(slide["link"], f"{at}.link")
    track = slide.get("track")
    if track is not None:
        _track(track, f"{at}.track")
    cards = slide.get("cards", [])
    cap = TRACK_CARDS if track else CARDS
    if not isinstance(cards, list) or len(cards) > cap:
        raise Invalid(f"{at}.cards: at most {cap} cards{' beside a track' if track else ''}")
    for k, card in enumerate(cards):
        _card(card, f"{at}.cards[{k}]")


def _track(track: Any, at: str) -> None:
    if not isinstance(track, list) or not STAGES[0] <= len(track) <= STAGES[1]:
        raise Invalid(f"{at}: {STAGES[0]} to {STAGES[1]} stages")
    for k, stage in enumerate(track):
        _keys(stage, f"{at}[{k}]", {"label", "note", "state"}, {"label", "state"})
        _text(stage["label"], f"{at}[{k}].label", 24)
        _text(stage.get("note"), f"{at}[{k}].note", 32, required=False)
        if stage["state"] not in STATES:
            raise Invalid(f"{at}[{k}].state: one of {', '.join(STATES)}")


def _card(card: Any, at: str) -> None:
    _keys(card, at, {"big", "head", "text", "pill", "tone"}, {"text"})
    _text(card.get("big"), f"{at}.big", 8, required=False)
    _text(card.get("head"), f"{at}.head", 40, required=False)
    _text(card["text"], f"{at}.text", 120)
    _text(card.get("pill"), f"{at}.pill", 32, required=False)
    if "tone" in card and card["tone"] not in THEME["tones"]:
        raise Invalid(f"{at}.tone: one of {', '.join(THEME['tones'])}")
    if "tone" in card and "pill" not in card:
        raise Invalid(f"{at}.tone: needs a pill")


def load_deck(path: Path) -> dict:
    try:
        deck = json.loads(path.read_text(encoding="utf-8"))
    except OSError as problem:
        raise Invalid(f"{path}: cannot be read: {problem}") from None
    except ValueError as problem:
        raise Invalid(f"{path}: not JSON: {problem}") from None
    check_deck(deck, str(path))
    logo = (deck.get("theme") or {}).get("logo")
    if logo:
        deck["theme"]["logo"] = str((path.parent / logo).resolve())
    return deck


def spoken(date: str) -> str:
    """`2026-10-20` as `OCTOBER 20, 2026`, for an eyebrow."""
    y, m, d = (int(p) for p in date.split("-"))
    return f"{MONTHS[m - 1].upper()} {d}, {y}"


class Builder:
    """One presentation, slide by slide, in the theme's tokens."""

    def __init__(self, look: dict):
        from pptx import Presentation
        from pptx.util import Pt

        self.look = look
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Pt(PAGE[0]), Pt(PAGE[1])
        self.blank = self.prs.slide_layouts[6]
        self.slide: Any = None

    def rgb(self, colour: str) -> Any:
        from pptx.dml.color import RGBColor

        return RGBColor.from_string(colour.lstrip("#"))

    def page(self) -> Any:
        self.slide = self.prs.slides.add_slide(self.blank)
        fill = self.slide.background.fill
        fill.solid()
        fill.fore_color.rgb = self.rgb(self.look["paper"])
        if self.look.get("logo"):
            from pptx.util import Pt

            self.slide.shapes.add_picture(self.look["logo"], Pt(620), Pt(26), width=Pt(64))
        return self.slide

    def box(self, kind: str, x: float, y: float, w: float, h: float, fill: str | None = None,
            line: str | None = None, weight: float = 1.0) -> Any:
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Pt

        shape = self.slide.shapes.add_shape(getattr(MSO_SHAPE, kind), Pt(x), Pt(y), Pt(w), Pt(h))
        shape.shadow.inherit = False
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = self.rgb(fill)
        else:
            shape.fill.background()
        if line:
            shape.line.color.rgb = self.rgb(line)
            shape.line.width = Pt(weight)
        else:
            shape.line.fill.background()
        if kind == "ROUNDED_RECTANGLE":
            shape.adjustments[0] = min(0.5, 6 / min(w, h))
        return shape

    def put_text(self, x: float, y: float, w: float, h: float, runs: list[tuple[str, dict]], size: float,
             align: str = "LEFT", middle: bool = False, shape: Any = None) -> Any:
        """A text box (or `shape`'s own frame) holding `runs`: (text, {bold, colour, url})."""
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.util import Pt

        target = shape or self.slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
        frame = target.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE if middle else MSO_ANCHOR.TOP
        lines: list[list[tuple[str, dict]]] = [[]]
        for words, style in runs:
            for i, part in enumerate(words.split("\n")):
                if i:
                    lines.append([])
                if part:
                    lines[-1].append((part, style))
        for n, line in enumerate(lines):
            para = frame.paragraphs[0] if n == 0 else frame.add_paragraph()
            para.alignment = getattr(PP_ALIGN, align)
            for words, style in line:
                run = para.add_run()
                run.text = words
                run.font.name = self.look["font"]
                run.font.size = Pt(size)
                run.font.bold = bool(style.get("bold"))
                run.font.color.rgb = self.rgb(style.get("colour") or self.look["ink"])
                if style.get("url"):
                    run.hyperlink.address = style["url"]
                    run.font.underline = True
        return target

    def head(self, eyebrow: str, title: str, accent: str | None) -> None:
        look = self.look
        self.put_text(40, 24, 560, 20, [(eyebrow.upper(), {"colour": look["muted"]})], 14)
        runs = [(title, {"bold": True})]
        if accent:
            runs.append((" " + accent, {"bold": True, "colour": look["accent"]}))
        self.put_text(40, 46, 580, 40, runs, 26)

    def title_page(self, eyebrow: str, name: str, tagline: str) -> None:
        self.page()
        self.put_text(40, 140, 600, 20, [(eyebrow.upper(), {"colour": self.look["muted"]})], 14)
        self.put_text(40, 162, 640, 56, [(name, {"bold": True})], 44)
        self.put_text(40, 222, 640, 36, [(tagline, {"bold": True, "colour": self.look["accent"]})], 26)

    def track(self, stages: list[dict]) -> None:
        look, x0, x1, yc = self.look, 80.0, 640.0, 116.0
        step = (x1 - x0) / (len(stages) - 1)
        reached = max((i for i, s in enumerate(stages) if s["state"] != "next"), default=0)
        if reached:
            self.box("RECTANGLE", x0, yc - 1.5, step * reached, 3, look["accent"])
        if reached < len(stages) - 1:
            self.box("RECTANGLE", x0 + step * reached, yc - 1, step * (len(stages) - 1 - reached), 2, look["rule"])
        for k, stage in enumerate(stages):
            cx, state = x0 + step * k, stage["state"]
            r = 12 if state == "now" else 9
            if state == "done":
                self.box("OVAL", cx - r, yc - r, 2 * r, 2 * r, look["accent"])
            elif state == "now":
                self.box("OVAL", cx - r, yc - r, 2 * r, 2 * r, look["card"], look["accent"], 3)
            else:
                self.box("OVAL", cx - r, yc - r, 2 * r, 2 * r, look["card"], look["rule"], 1.5)
            colour = look["muted"] if state == "next" else look["ink"]
            runs = [(stage["label"], {"bold": state == "now", "colour": colour})]
            if stage.get("note"):
                runs.append(("\n" + stage["note"], {"colour": look["accent"] if state == "now" else colour}))
            self.put_text(cx - 70, yc + 15, 140, 40, runs, 14, "CENTER")

    def cards(self, cards: list[dict], top: float, height: float) -> None:
        look, width, gap = self.look, 205.0, 12.0
        for k, card in enumerate(cards):
            cx, cy = 40 + (k % 3) * (width + gap), top + (k // 3) * (height + gap)
            self.box("ROUNDED_RECTANGLE", cx, cy, width, height, look["card"], look["rule"], 1)
            y = cy + 10
            if card.get("big"):
                self.put_text(cx + 14, cy + 6, width - 28, 46, [(card["big"], {"bold": True, "colour": look["accent"]})], 36)
                y = cy + 56
            if card.get("head"):
                self.put_text(cx + 14, y, width - 28, 24, [(card["head"], {"bold": True})], 16)
                y += 24
            self.put_text(cx + 14, y, width - 28, cy + height - y - 32, [(card["text"], {})], 14)
            if card.get("pill"):
                fill, ink = look["tones"][card.get("tone") or "planned"]
                pw = min(width - 28, len(card["pill"]) * 7.2 + 18)
                pill = self.box("ROUNDED_RECTANGLE", cx + 14, cy + height - 30, pw, 20, fill)
                self.put_text(0, 0, 0, 0, [(card["pill"], {"colour": ink})], 12, "CENTER", True, shape=pill)

    def status_slide(self, slide: dict, cta: dict | None) -> None:
        self.page()
        self.head(slide["eyebrow"], slide["title"], slide.get("accent"))
        cards = slide.get("cards", [])
        if slide.get("track"):
            self.track(slide["track"])
            self.cards(cards, 178, 132)
            foot_y = 326
        else:
            rows = max(1, (len(cards) + 2) // 3)
            self.cards(cards, 98, 112 if rows > 1 else 124)
            foot_y = 352 if rows > 1 else 240
        if slide.get("foot"):
            runs = [(slide["foot_label"] + " ", {"bold": True})] if slide.get("foot_label") else []
            self.put_text(40, foot_y, 640, 44, runs + [(slide["foot"], {})], 14)
        if slide.get("link"):
            self.put_text(40, 368, 420, 22, [("Details: ", {}), (slide["link"]["text"], {"url": slide["link"]["url"]})], 14)
        if cta:
            self.put_text(500, 368, 180, 22, [(cta["text"], {"bold": True, "url": cta["url"]})], 14, "RIGHT")

    def save_pptx(self, out: Path) -> None:
        """Write beside `out`, then replace it: a reader never sees half a file."""
        out.parent.mkdir(parents=True, exist_ok=True)
        fd, partial = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".partial", dir=out.parent)
        os.close(fd)
        try:
            self.prs.save(partial)
            os.replace(partial, out)
        except BaseException:
            Path(partial).unlink(missing_ok=True)
            raise


def build(decks: list[dict], out: Path, titles: bool) -> int:
    """Lay out `decks` into `out`; `titles` gives each a title page. Returns the slide count."""
    look = theme(decks[0].get("theme"))
    builder = Builder(look)
    for n, deck in enumerate(decks):
        if titles:
            builder.title_page(f"Experiment {n + 1} of {len(decks)}  ·  {spoken(deck['date'])}",
                               deck["name"], deck["tagline"])
        for k, slide in enumerate(deck["slides"]):
            last = n == len(decks) - 1 and k == len(deck["slides"]) - 1
            builder.status_slide(slide, look["cta"] if last else None)
    builder.save_pptx(out)
    return len(builder.prs.slides)


def deck_main() -> int:
    """`sd-research-kit deck`: this repo's `30-brief/deck.json` into `docs/dashboard/deck.pptx`."""
    path = Path.cwd() / DECK
    if not path.is_file():
        print(f"sd-research-kit deck: no {DECK} here; the status brief's deck lives there", file=sys.stderr)
        return 2
    try:
        count = build([load_deck(path)], Path.cwd() / OUT, titles=False)
    except Invalid as problem:
        print(f"sd-research-kit deck: {problem}", file=sys.stderr)
        return 1
    print(f"wrote {OUT}: {count} slides")
    return 0


def fleet_decks(trees: list[Path]) -> list[Path]:
    """Each checkout's own `30-brief/deck.json`, not a symlink, newest `date` first, then by checkout name."""
    found = []
    for tree in trees:
        path = Path(tree) / DECK
        if path.is_file() and not path.is_symlink():
            found.append((load_deck(path), path))
    found.sort(key=lambda pair: pair[1].parent.parent.name)
    found.sort(key=lambda pair: pair[0]["date"], reverse=True)
    return found


def roundup_main(trees: list[Path]) -> int:
    """`sd-research-kit roundup`: every checkout's deck.json into `docs/dashboard/roundup.pptx` here."""
    try:
        found = fleet_decks(trees)
        if not found:
            print(f"sd-research-kit roundup: no checkout beside this one keeps a {DECK}", file=sys.stderr)
            return 2
        count = build([deck for deck, _ in found], Path.cwd() / ROUNDUP, titles=True)
    except Invalid as problem:
        print(f"sd-research-kit roundup: {problem}", file=sys.stderr)
        return 1
    print(f"wrote {ROUNDUP}: {count} slides from {len(found)} decks")
    for _, path in found:
        print(f"  {path}")
    return 0
