"""The dashboard's icon (pack sd:6322): a tab icon and an iOS home-screen icon, each a file served from 'self'.

The policy (`default-src 'self'`) refuses a data: icon, so the shell's drawn icon never showed and /favicon.ico
answered 204: a tab showed the browser's blank page and Add to Home Screen a page snapshot.
"""

from __future__ import annotations

import json
import re
import struct
import subprocess
import unittest
import urllib.request

from sd_dashboard import v2
from test_v2_tasks import SHELL_JS
from test_v2_today import OSASCRIPT
from test_workflow_actions import BrowserSession

HEAD = ('<link rel="icon" href="/static/icon-32.png" type="image/png" sizes="32x32">',
        '<link rel="icon" href="/static/icon.svg" type="image/svg+xml">',
        '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">',
        '<meta name="apple-mobile-web-app-title" content="sd">')


def png_size(body: bytes) -> tuple[int, int, int]:
    """Width, height and colour type of a PNG, from its IHDR chunk."""
    assert body[:8] == b"\x89PNG\r\n\x1a\n", body[:8]
    width, height, _, colour = struct.unpack(">IIBB", body[16:26])
    return width, height, colour


class TheIcon(BrowserSession):
    def fetch(self, path: str) -> tuple[int, str, bytes]:
        with urllib.request.urlopen(self.base + path, timeout=30) as answer:
            return answer.status, answer.headers.get_content_type(), answer.read()

    def test_each_icon_answers_200_with_its_type(self):
        for path, kind in (("/favicon.ico", "image/x-icon"), ("/static/icon.svg", "image/svg+xml"),
                           ("/static/icon-warning.svg", "image/svg+xml"), ("/static/icon-32.png", "image/png"),
                           ("/static/apple-touch-icon.png", "image/png")):
            with self.subTest(path=path):
                status, served, body = self.fetch(path)
                self.assertEqual((status, served), (200, kind))
                self.assertTrue(body)
        self.assertEqual(self.fetch("/favicon.ico")[2][:4], b"\x00\x00\x01\x00")  # an ICO header, not a renamed PNG
        self.assertEqual(png_size(self.fetch("/static/icon-32.png")[2])[:2], (32, 32))

    def test_the_home_screen_icon_is_180_px_and_opaque(self):
        # iOS fills a transparent pixel with black; colour type 2 is RGB with no alpha channel.
        self.assertEqual(png_size(self.fetch("/static/apple-touch-icon.png")[2]), (180, 180, 2))

    def test_every_shell_page_head_links_the_icons(self):
        for path in v2.PAGES:
            with self.subTest(path=path):
                head = v2.page(path).split("</head>", 1)[0]
                for line in HEAD:
                    self.assertEqual(head.count(line), 1, line)
        status, _, body = self.request("/tasks")
        self.assertEqual(status, 200)
        for line in HEAD:
            self.assertIn(line, body.split("</head>", 1)[0])

    def test_the_icon_svg_has_no_script_and_no_outside_reference(self):
        for name in ("icon.svg", "icon-warning.svg"):
            text = self.fetch(f"/static/{name}")[2].decode("utf-8")
            self.assertNotRegex(text, r"(?i)<script|href=|url\(|on\w+=")


class TheWarningMark(unittest.TestCase):
    """Under the policy the count cannot be drawn; a warning swaps in the static warning mark, and none puts it back."""

    def test_a_warning_count_swaps_the_mark_and_none_restores_it(self):
        found = re.search(r"  function titleCount\(n\) \{\n.*?\n  \}\n", SHELL_JS, re.S)
        self.assertIsNotNone(found, "shell.js has no titleCount")
        script = """
const OUT = [];
const svg = { dataset: {}, attrs: { href: '/static/icon.svg' },
  getAttribute(k) { return this.attrs[k]; }, setAttribute(k, v) { OUT.push(v); this.attrs[k] = v; } };
const document = { title: 'Today · system', head: { append() { OUT.push('appended'); } },
  createElement() { throw new Error('drew a canvas'); },
  querySelector: s => s === 'link[rel="icon"][type="image/svg+xml"]' ? svg : null };
const window = { SHELL_PAGES: {} };
const baseTitle = 'Today · system';
""" + found.group(0) + """
function run() {
  titleCount(0); const quiet = document.title;
  titleCount(3); const lit = [document.title, svg.attrs.href];
  titleCount(4); titleCount(0);
  return JSON.stringify({ quiet, lit, back: [document.title, svg.attrs.href], writes: OUT });
}
"""
        out = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script], capture_output=True, text=True,
                             timeout=60, check=False)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout), {
            "quiet": "Today · system", "lit": ["(3) Today · system", "/static/icon-warning.svg"],
            "back": ["Today · system", "/static/icon.svg"],
            # A count of 0 leaves the static mark alone, and a second warning does not reload it.
            "writes": ["/static/icon-warning.svg", "/static/icon.svg"]})
