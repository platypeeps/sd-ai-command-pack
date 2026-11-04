"""Operations under Fleet (pack sd:7266), and where its areas went (pack sd:7517).

The rail's Fleet group holds Operations, which opens `/operations`. Every area moved, Trackers last (pack sd:7525), so
the bare address lists each area's new home, and `operations.js` follows the one an old `#view=<area>` names: only the
browser sees it. The palette lists no area on its own.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from sd_dashboard import operations_screen, server, v2
from support import ScreenCase
from test_v2_today import MARKUP_JS, OSASCRIPT
from test_v2_today import STAND_IN as MARKUP_STAND_IN

STATIC = Path(v2.__file__).resolve().parent / "static"
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")
ICONS_JS = (STATIC / "icons.js").read_text(encoding="utf-8")
GROUPS = re.search(r"^  const GROUPS = \[\n(.*?)^  \];$", SHELL_JS, re.S | re.M).group(1)


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


class TheMovedPage(ScreenCase):
    """pack sd:7525: Trackers, the last area, moved to GitHub; the bare address lists where every area went."""

    def test_the_bare_address_links_each_area_to_its_new_home(self):
        body = self.render("/operations")
        links = re.findall(r'<a href="([^"]+)" data-view="([a-z]+)">', body)
        self.assertEqual({view: href for href, view in links}, {area: href for area, (href, _) in operations_screen.MOVED.items()})
        self.assertEqual(links[-1], ("/github#view=tracked", "trackers"))
        self.assertIn("<h1>Operations moved</h1>", body)
        self.assertNotIn('id="view-', body)
        self.assertRegex(body, r'<script src="/ui/operations\.js\?v=[0-9a-f]{16}"></script>'
                               r'<script src="/ui/shell\.js\?v=[0-9a-f]{16}"></script>')

    def test_an_area_that_never_moved_is_a_404(self):
        with self.assertRaises(server.NotFound):
            self.render("/operations", {"area": ["jobs"]})


#: The moved page's world, cut down: its links, an address, and what replace did.
STAND_IN = r"""
var window = globalThis, OUT = { opened: [], error: null };
var LINKS = MOVED;
var document = { querySelector: sel => { const m = /^a\[data-view="([a-z0-9-]+)"\]$/.exec(sel);
  return m && m[1] in LINKS ? { getAttribute: k => k === 'href' ? LINKS[m[1]] : null } : null; } };
var location = { hash: HASH, pathname: '/operations', search: '', replace(u) { OUT.opened.push(u); } };
"""


class TheScript(unittest.TestCase):
    """operations.js on the moved page: an old #view= address follows the link that names its area."""

    def run_page(self, hash=""):
        moved = {area: href for area, (href, _) in operations_screen.MOVED.items()}
        script = (STAND_IN.replace("MOVED", json.dumps(moved)).replace("HASH", json.dumps(hash))
                  + "try {\n" + (STATIC / "operations.js").read_text(encoding="utf-8")
                  + "\n} catch (e) { OUT.error = String(e) + ' ' + e.stack; }\nfunction run() { return JSON.stringify(OUT); }\n")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=60,
                                check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out["opened"]

    def test_an_old_view_address_opens_the_view_that_holds_it_now(self):
        for was, target in (("services", "/management#view=deploys"), ("sessions", "/management#view=sessions"),
                            ("usage", "/metrics#view=spend"), ("resources", "/management#view=machine"),
                            ("trackers", "/github#view=tracked")):
            with self.subTest(was=was):
                self.assertEqual(self.run_page(f"#view={was}"), [target])

    def test_the_bare_address_opens_trackers_and_an_unknown_view_stays(self):
        self.assertEqual(self.run_page(""), ["/github#view=tracked"])
        self.assertEqual(self.run_page("#view=jobs"), [])
        self.assertEqual(self.run_page("#view=\"]x"), ["/github#view=tracked"])


if __name__ == "__main__":
    unittest.main()
