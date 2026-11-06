"""GitHub's Dependabot view (pack sd:7515): each managed repository's open Dependabot alerts, grouped by repository.

What this slice promises: `/api/github/dependabot` (`health_screen.dependabot_document`) reads only what `sd shadow sync`
stored in `repo_protection` -- the counts Health reads and, since pack sd:7515, each alert's summary -- and calls no
GitHub API. A group per repository with open alerts, worst severity first, its alerts critical first; a count past the
first page reads "100+"; a row stored before the summaries says so instead of listing nothing. Repositories with alerts
off, not read or archived are names and counts, never groups. `dependabot.js` reads once the view shows and draws one
ledger: a band per repository (the shell's table grammar folds a band, `data-band` keys it) naming the repo, its count
and worst severity, with Health's Fix beside the fold, and a row per alert with its severity glyph and Open, the alert's
page on GitHub. Fix is the one shared declaration (`commands.dependabotFix`): it files or reuses the repo's
`dependabot:<owner>/<repo>` item, then posts its fix route. It runs under JavaScriptCore against the stand-in page, as
`test_v2_today_github` runs `today-github.js`.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from sd_dashboard import health_screen, v2
from sd_db import upsert_repo
from test_v2_tasks import MARKUP_JS, SHELL, STAND_IN
from test_v2_today import OSASCRIPT
from test_workflow_actions import BrowserSession

V2 = Path(v2.__file__).resolve().parent
SCRIPT = V2 / "static" / "dependabot.js"
COMMANDS_JS = (V2 / "static" / "commands.js").read_text(encoding="utf-8")
PAGE_JS = SCRIPT.read_text(encoding="utf-8") if SCRIPT.exists() else ""
HUB = "https://github.com"


def stored(number, severity, package="widgetlib", **changes):
    """One alert summary as `protection._alert_summary` stores it."""
    return {"number": number, "severity": severity, "package": package, "ecosystem": "pip",
            "manifest": "requirements.txt", "summary": f"{package} advisory {number}", "ghsa": f"GHSA-{number}",
            "cve": None, "patched": "2.0.1", "url": f"{HUB}/example/anvil/security/dependabot/{number}",
            "created_at": "2026-09-01T08:00:00Z", **changes}


def repo(name, dependabot, **changes):
    return {"repo": f"/checkouts/{name}", "slug": f"example/{name}", "status": "protected",
            "observed_at": "2026-09-05T08:00:00Z", "reason": None, "managed": True,
            "alerts": {"dependabot": dependabot, "secret_scanning": {"visibility": "private"}}, **changes}


FOUND = [
    repo("anvil", {"open": 3, "more": False, "severity": {"low": 1, "high": 1, "medium": 1},
                   "summaries": [stored(1, "low"), stored(2, "high", "<b>odd</b>"), stored(3, "medium")]}),
    repo("bellows", {"open": 100, "more": True, "severity": {"critical": 2, "low": 98},
                     "summaries": [stored(10, "low"), stored(11, "critical"), stored(12, "critical")]}),
    # Stored before pack sd:7515: counts only.
    repo("chisel", {"open": 1, "more": False, "severity": {"medium": 1}}),
    repo("dolly", {"open": 0, "more": False, "severity": {}, "summaries": []}),
    repo("easel", {"setting": "disabled"}),
    repo("forge", {"reason": "API HTTP 403; retry on a later collection"}),
    repo("gauge", {"archived": True}),
    repo("hammer", {"open": 5, "more": False, "severity": {"critical": 5}}, managed=False),
]


class TheDocument(unittest.TestCase):
    def test_a_group_per_repo_with_open_alerts_worst_first_and_the_rest_as_notes(self):
        doc = health_screen.dependabot_document(FOUND)
        self.assertEqual([(g["name"], g["worst"], g["shown"]) for g in doc["groups"]],
                         [("example/bellows", "critical", "100+"), ("example/anvil", "high", "3"),
                          ("example/chisel", "medium", "1")])
        bellows, anvil, chisel = doc["groups"]
        self.assertEqual([(a["number"], a["severity"]) for a in bellows["alerts"]],
                         [(12, "critical"), (11, "critical"), (10, "low")])
        self.assertEqual([a["severity"] for a in anvil["alerts"]], ["high", "medium", "low"])
        self.assertIsNone(chisel["alerts"], "a row stored before the summaries listed no alert as if none were open")
        # What Health's Fix reads, so the one shared Fix serves both pages.
        self.assertEqual({k: bellows[k] for k in ("id", "type", "slug", "repo_path", "grave", "facts", "more")},
                         {"id": "dep:/checkouts/bellows", "type": "dependabot alerts", "slug": "example/bellows",
                          "repo_path": "/checkouts/bellows", "grave": 2, "more": True,
                          "facts": {"Repository": "/checkouts/bellows", "Shown": "100+"}})
        self.assertEqual(list(bellows["severity"]), ["critical", "low"])
        self.assertEqual((doc["off"], doc["clean"], doc["archived"], doc["managed"]), (["example/easel"], 1, 1, 7))
        self.assertEqual(doc["unread"], ["example/forge: API HTTP 403; retry on a later collection"])

    def test_an_sd_db_without_the_managed_flag_is_an_error_not_an_empty_list(self):
        doc = health_screen.dependabot_document([{"repo": "/checkouts/anvil", "status": "protected"}])
        self.assertIn("no managed flag", doc["error"])
        self.assertEqual(doc["groups"], [])


class TheRoute(BrowserSession):
    def test_the_view_reads_what_the_sync_stored_and_needs_a_session(self):
        upsert_repo(self.connection, "/checkouts/anvil", remote="git@github.com:example/anvil.git")
        self.connection.execute("UPDATE repo SET managed = 1")
        body = {"alerts": {"dependabot": {"open": 1, "more": False, "severity": {"high": 1},
                                          "summaries": [stored(7, "high")]}}}
        self.connection.execute("INSERT INTO repo_protection (repo, observed_at, status, default_branch, body) "
                                "VALUES ('/checkouts/anvil', '2026-09-05T02:20:00Z', 'protected', 'main', ?)",
                                (json.dumps(body),))
        self.connection.commit()
        status, _, answer = self.request("/api/github/dependabot", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200, answer)
        (group,) = json.loads(answer)["groups"]
        self.assertEqual((group["slug"], [a["number"] for a in group["alerts"]]), ("example/anvil", [7]))
        self.assertNotEqual(self.request("/api/github/dependabot")[0], 200)
        status, _, page = self.request("/github", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200)
        self.assertIn('id="view-dependabot"', page)
        scripts = re.findall(r'<script src="/ui/([^"?]+)', page)
        self.assertLess(scripts.index("commands.js"), scripts.index("dependabot.js"))
        self.assertEqual(self.request("/ui/dependabot.js")[0], 200)


class TheScript(unittest.TestCase):
    """dependabot.js against the stand-in page: what it reads and what it draws."""

    def run_page(self, body, answer):
        script = (STAND_IN + MARKUP_JS + "\nconst mk = window.markup.html;\n" + SHELL + COMMANDS_JS
                  + "\nANSWER = " + answer + ";\n" + PAGE_JS
                  + "\nvar R = {};\nconst show = () => document.dispatchEvent(new CustomEvent('shell:view', { detail: { id: 'dependabot', first: true } }));\n"
                  + "(async () => { try {\n(DOC_LISTENERS.DOMContentLoaded || []).forEach(f => f());\nawait flush();\n"
                  + body + "\n} catch (e) { OUT.error = String(e) + ' ' + e.stack; } })();\n"
                  + "function run() { OUT.R = R; OUT.toasts = OUT.toasts.map(t => t.msg); return JSON.stringify(OUT); }\n")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script],
                                capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out

    def test_each_repo_is_a_band_the_shell_folds_with_fix_and_each_alert_a_row_with_severity_and_open(self):
        doc = health_screen.dependabot_document(FOUND)
        out = self.run_page("R.before = OUT.gets.length; show(); await flush(); R.rows = ELS['dependabot'].html;"
                            " R.notes = ELS['dependabot-notes'].html; R.tally = ELS['dependabot-tally'].html;",
                            f"(path, body) => [200, {json.dumps(doc)}]")
        self.assertEqual((out["R"]["before"], out["gets"]), (0, ["/api/github/dependabot"]))
        rows = out["R"]["rows"]
        # A band is one cell spanning the table, keyed by data-band: the shell's table grammar makes it a fold.
        bands = re.findall(r'<tr class="band" data-band="([^"]+)"><td colspan="5">', rows)
        self.assertEqual(bands, ["dep:/checkouts/bellows", "dep:/checkouts/anvil", "dep:/checkouts/chisel"])
        self.assertIn("example/bellows<span class=\"n\">100+ open · worst critical · 2 critical · 98 low · first page only</span>",
                      rows)
        self.assertIn('<button class="btn quiet sm" type="button" data-tkeep="" data-cmd="dependabot alerts.fix"'
                      ' data-obj="dep:/checkouts/anvil">Fix</button>', rows)
        bellows = rows[rows.index('data-band="dep:/checkouts/bellows"'):rows.index('data-band="dep:/checkouts/anvil"')]
        self.assertEqual(re.findall(r'data-alert="example/bellows#(\d+)"', bellows), ["12", "11", "10"])
        self.assertIn('<td class="sev" data-sort-value="0"><span class="g-warning" aria-hidden="true">■</span> critical</td>',
                      bellows)
        self.assertIn(f'<a class="btn quiet sm" href="{HUB}/example/anvil/security/dependabot/12" target="_blank"'
                      ' rel="noopener" aria-label="Open example/bellows alert 12 on GitHub">Open</a>', bellows)
        self.assertIn("&lt;b&gt;odd&lt;/b&gt;", rows)
        self.assertNotIn("<b>odd</b>", rows)
        self.assertIn("The alerts' details are not stored yet", rows)
        self.assertIn("Alerts off in 1 repo: example/easel.", out["R"]["notes"])
        self.assertIn("Not read in 1 repo: example/forge: API HTTP 403", out["R"]["notes"])
        self.assertEqual(out["R"]["tally"], "104+ open in 3 repos")
        self.assertEqual(out["counts"], {"dependabot": 104})

    def test_fix_on_a_group_files_the_repos_item_then_posts_its_fix_route(self):
        doc = health_screen.dependabot_document(FOUND)
        answer = (f"(path, body) => path === '/api/github/dependabot' ? [200, {json.dumps(doc)}]"
                  " : path === '/api/items' ? [201, { item: { id: 77 }, revision: 'a'.repeat(64) }]"
                  " : path === '/api/items/77/fix' ? [200, { fix: { session: 'builder', pane: 'p1' } }] : [404, { error: 'no answer' }]")
        out = self.run_page("show(); await flush(); const c = cmd('dependabot alerts.fix'), o = C.get('dep:/checkouts/bellows');"
                            " R.ask = !!c.askFirst; R.on = c.when(o); shellRun(c, o); await flush();", answer)
        self.assertEqual((out["R"]["ask"], out["R"]["on"]), (True, True))
        posts = [post[:2] for post in out["posts"]]
        self.assertEqual({k: posts[0][1][k] for k in ("title", "repo", "ref")},
                         {"title": "Dependabot: 100+ open alerts in example/bellows", "repo": "/checkouts/bellows",
                          "ref": "dependabot:example/bellows"})
        self.assertIn("2 critical or high", posts[0][1]["body"])
        self.assertEqual(posts[1], ["/api/items/77/fix", {"revision": "a" * 64}])
        self.assertEqual(out["toasts"][-1], "Fix started · #77 · builder session in herdr pane p1")

    def test_a_failed_launch_after_filing_names_the_filed_item_and_its_note(self):
        """pack sd:7756: the item is filed and the launch answers 503; the toast said "not changed" and the cause alone,
        so nothing named sd:77, the item filed for the repo, whose note now keeps the cause (fix_session._noted)."""
        doc = health_screen.dependabot_document(FOUND)
        error = ("Fix failed: herdr.sh launch: session sd is not running and did not start: herdr --session sd server"
                 " exited 1. A note on sd:77 keeps the cause.")
        answer = (f"(path, body) => path === '/api/github/dependabot' ? [200, {json.dumps(doc)}]"
                  " : path === '/api/items' ? [201, { item: { id: 77 }, revision: 'a'.repeat(64) }]"
                  f" : path === '/api/items/77/fix' ? [503, {{ error: {json.dumps(error)} }}] : [404, {{ error: 'no answer' }}]")
        out = self.run_page("show(); await flush(); const c = cmd('dependabot alerts.fix'), o = C.get('dep:/checkouts/bellows');"
                            " shellRun(c, o); await flush();", answer)
        self.assertEqual([post[0] for post in out["posts"]], ["/api/items", "/api/items/77/fix"])
        self.assertEqual(out["toasts"][-1], f"example/bellows not changed: filed sd:77, but {error}")

    def test_a_failed_read_is_a_row_naming_it_never_an_empty_list(self):
        out = self.run_page("show(); await flush(); R.rows = ELS['dependabot'].html;",
                            "(path, body) => [500, { error: 'database is locked' }]")
        self.assertIn("The alerts were not read: ", out["R"]["rows"])
        self.assertEqual(out["counts"], {"dependabot": None})


if __name__ == "__main__":
    unittest.main()
