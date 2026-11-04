"""Operations under Fleet (pack sd:7266): the rail's Operations section, its areas the shell's views.

What this slice promises: the rail's Fleet group holds Operations, which opens `/operations`; the screen declares
Usage, Resources and Trackers as `window.PAGE_VIEWS`, the shell's sub-entries, in `operations_screen.AREAS` order;
and an old `/operations?area=<key>` address opens that view. The server draws only the area the address names, so a
view the reader shows that is not drawn loads its own address. The area link bar and the palette's Services, Trackers
and Sessions entries are gone, and pack sd:7517 sent an old Services or Sessions view address to Management.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_dashboard import operations_screen, v2
from support import ScreenCase
from test_v2_today import MARKUP_JS, OSASCRIPT
from test_v2_today import STAND_IN as MARKUP_STAND_IN

STATIC = Path(v2.__file__).resolve().parent / "static"
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")
ICONS_JS = (STATIC / "icons.js").read_text(encoding="utf-8")
GROUPS = re.search(r"^  const GROUPS = \[\n(.*?)^  \];$", SHELL_JS, re.S | re.M).group(1)
AREAS = [key for key, _ in operations_screen.AREAS]


class TheRail(unittest.TestCase):
    def test_fleet_holds_operations_which_opens_the_screen(self):
        fleet = re.search(r"\['Fleet', +\[(.*)\]\],", GROUPS).group(1)
        entry = re.search(r"\['Operations', '([a-z0-9-]+)', '([a-z])'\]", fleet)
        self.assertIsNotNone(entry, "the Fleet group has no Operations entry")
        icon, key = entry.groups()
        self.assertIn(f'<symbol id="i-{icon}"', ICONS_JS)
        keys = re.findall(r"\['[A-Za-z ]+', '[a-z0-9-]+', '([a-z])'\]", GROUPS)
        self.assertEqual(keys.count(key), 1, f"g {key} is another section's key")
        self.assertEqual(v2.CLASSIC.get("Operations") or v2.SECTIONS.get("Operations"), "/operations")

    def test_the_operations_entry_is_drawn_as_a_standard_section(self):
        """The operator asked for the standard setup: no "classic" tag, and its g u hint shows, on every page."""
        maps = "\n".join(re.findall(r"^  const (?:hrefOf|classic) = .*;$", SHELL_JS, re.M))
        item = re.search(r"\$\{items\.map\((\(\[name, icon, key\]\) => \{\n.*?\n      \})\)\}</ul>", SHELL_JS, re.S)
        self.assertIsNotNone(item, "shell.js has no rail item template")
        script = (MARKUP_STAND_IN + MARKUP_JS + """
const { html } = window.markup;
const ICON = n => html`<svg class="i"><use href="#i-${n}"/></svg>`, badge = () => html``, counts = {};
const PAGES = {}, CLASSIC = { Operations: '/operations' }, page = 'Today';
""" + maps + "\nconst draw = " + item.group(1) + ";\nJSON.stringify(String(draw(['Operations', 'gauge', 'u'])))")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=60,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        drawn = json.loads(result.stdout)
        self.assertIn('<a href="/operations" data-section="Operations">', drawn)
        self.assertIn("<kbd>g u</kbd>", drawn)
        self.assertNotIn("classic", drawn)
        self.assertNotIn("[data-classic]", (STATIC / "shell.css").read_text(encoding="utf-8"))

    def test_the_palette_no_longer_lists_the_areas_on_their_own(self):
        self.assertEqual([href for href in v2.SCREENS.values() if href.startswith("/operations")], [])


class TheScreen(ScreenCase):
    def setUp(self):
        super().setUp()
        patcher = patch("sd_dashboard.reports_screen.collect", lambda area: "")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_area_draws_into_its_view_panel_under_operations(self):
        for area in AREAS:
            with self.subTest(area=area):
                body = self.render("/operations", {"area": [area]})
                self.assertIn('<body data-page="Operations" data-scope="operations">', body)
                panels = re.findall(r'<div id="view-([a-z]+)"( hidden)?>', body)
                self.assertEqual([key for key, _ in panels], AREAS)
                self.assertEqual([key for key, hidden in panels if not hidden], [area])
                for key, label in operations_screen.AREAS:
                    if key != area:
                        self.assertIn(f'<div id="view-{key}" hidden><p class="hint">Opening {label}…</p></div>', body)
                self.assertNotIn("Operations areas", body)
                self.assertRegex(body, r'<script src="/ui/operations\.js\?v=[0-9a-f]{16}"></script>'
                                       r'<script src="/ui/shell\.js\?v=[0-9a-f]{16}"></script>')

    def test_the_views_are_the_areas(self):
        script = (STATIC / "operations.js").read_text(encoding="utf-8")
        block = re.search(r"window\.PAGE_VIEWS = \[(.*?)\];", script, re.S).group(1)
        declared = re.findall(r"\{ id: '([a-z]+)', label: '([A-Za-z]+)'", block)
        self.assertEqual(declared, list(operations_screen.AREAS))


#: The view switch's world, cut down: the panels the server draws, an address, and what replace and replaceState did.
STAND_IN = r"""
var window = globalThis, OUT = { events: [], replaced: [], opened: [], error: null };
var WIN = {}, DOC = {};
function addEventListener(t, f) { (WIN[t] = WIN[t] || []).push(f); }
function El(tag) { const e = { tagName: tag, id: '', attrs: {}, hidden: false, children: [], listeners: {}, textContent: '', className: '',
  setAttribute(k, v) { e.attrs[k] = String(v); }, getAttribute(k) { return k in e.attrs ? e.attrs[k] : null; },
  removeAttribute(k) { delete e.attrs[k]; }, append(...cs) { e.children.push(...cs); },
  addEventListener(t, f) { (e.listeners[t] = e.listeners[t] || []).push(f); }, closest() { return null; } };
  return e; }
var PANELS = {};
AREAS.forEach(id => { const p = El('div'); p.id = 'view-' + id; PANELS[p.id] = p; });
var document = { readyState: 'loading',
  getElementById: id => PANELS[id] || null, createElement: tag => El(tag), querySelector: () => null,
  addEventListener(t, f) { (DOC[t] = DOC[t] || []).push(f); },
  dispatchEvent(e) { if (e.type === 'shell:view') OUT.events.push(e.detail.id); (DOC[e.type] || []).forEach(f => f(e)); } };
function CustomEvent(type, o) { this.type = type; this.detail = o && o.detail; }
// JXA has no URLSearchParams: the first value of a key, as the browser's get returns.
function URLSearchParams(q) { const m = String(q || '').replace(/^[?]/, '').split('&').filter(Boolean).map(p => p.split('='));
  this.get = k => { const f = m.find(p => p[0] === k); return f ? decodeURIComponent(f[1] || '') : null; }; }
var location = { hash: HASH, pathname: '/operations', search: SEARCH, replace(u) { OUT.opened.push(u); } };
var history = { state: null, pushState(s, t, u) { location.hash = u.slice(u.indexOf('#')); },
  replaceState(s, t, u) { OUT.replaced.push(u); location.hash = u.slice(u.indexOf('#')); } };
var STORE = KEPT, localStorage = { getItem: k => k in STORE ? STORE[k] : null, setItem: (k, v) => { STORE[k] = String(v); } };
var LI = El('li'), LINK = El('a');
LINK.closest = sel => sel === 'li' ? LI : null;
var rail = { querySelector: sel => sel === '[data-section="Operations"]' ? LINK : null };
var page = 'Operations', hrefOf = name => name === 'Operations' ? '/operations' : undefined;
"""


class TheViews(unittest.TestCase):
    """operations.js ahead of the shell's view switch (shell.js, view:start), as the page loads them."""

    def run_page(self, body, search="", hash="", kept=None):
        block = re.search(r"^  // view:start\n(.*?)^  // view:end$", SHELL_JS, re.S | re.M).group(1)
        stand_in = (STAND_IN.replace("AREAS", json.dumps(AREAS)).replace("HASH", json.dumps(hash))
                    .replace("SEARCH", json.dumps(search)).replace("KEPT", json.dumps(kept or {})))
        script = (stand_in + (STATIC / "operations.js").read_text(encoding="utf-8") + "\n" + block + r"""
var R = {};
const shown = () => Object.values(PANELS).filter(p => !p.hidden).map(p => p.id);
try {
(DOC.DOMContentLoaded || []).forEach(f => f({ type: 'DOMContentLoaded' }));
R.views = window.PAGE_VIEWS.map(v => [v.id, v.label]); R.cur = view.current(); R.shown = shown();
R.links = LI.children.length ? LI.children[0].children.map(li => li.children[0].getAttribute('href')) : [];
""" + body + """
} catch (e) { OUT.error = String(e) + ' ' + e.stack; }
function run() { OUT.R = R; return JSON.stringify(OUT); }
""")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=60,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out

    def test_an_area_address_opens_its_view_and_the_rail_lists_every_area(self):
        out = self.run_page("", search="?area=trackers", kept={"sd.view./operations": "resources"})
        self.assertEqual(out["R"]["views"], [list(area) for area in operations_screen.AREAS])
        self.assertEqual((out["R"]["cur"], out["R"]["shown"]), ("trackers", ["view-trackers"]))
        self.assertEqual(out["R"]["links"], [f"/operations#view={key}" for key in AREAS])
        self.assertEqual((out["replaced"], out["events"], out["opened"]), (["#view=trackers"], ["trackers"], []))

    def test_the_bare_address_opens_usage(self):
        out = self.run_page("")
        self.assertEqual((out["R"]["cur"], out["replaced"], out["opened"]), ("usage", ["#view=usage"], []))

    def test_showing_a_view_that_is_not_drawn_loads_its_area(self):
        out = self.run_page("view.show('resources');", search="?area=trackers")
        self.assertEqual(out["opened"], ["/operations?area=resources#view=resources"])

    def test_a_view_address_for_another_area_loads_that_area(self):
        # A rail sub-entry opened in a new tab is /operations#view=<id>: the server drew Usage.
        out = self.run_page("", hash="#view=resources")
        self.assertEqual((out["replaced"], out["opened"]), ([], ["/operations?area=resources#view=resources"]))
        out = self.run_page("", search="?area=resources", hash="#view=resources")
        self.assertEqual((out["replaced"], out["opened"]), ([], []))

    def test_a_moved_view_address_opens_its_management_view(self):
        """pack sd:7517: an old rail sub-entry, /operations#view=services or #view=sessions, lands on Management."""
        for was, target in (("services", "/management#view=deploys"), ("sessions", "/management#view=sessions")):
            with self.subTest(was=was):
                out = self.run_page("", hash=f"#view={was}")
                self.assertEqual(out["opened"], [target])

    def test_each_view_has_its_own_key(self):
        out = self.run_page("R.keys = window.PAGE_KEYS;")
        keys = out["R"]["keys"][-1][0].split(" / ")
        self.assertEqual(len(keys), len(set(keys)), keys)


if __name__ == "__main__":
    unittest.main()
