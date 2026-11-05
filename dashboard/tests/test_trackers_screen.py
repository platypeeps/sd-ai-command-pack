"""GitHub > Tracked (pack sd:7525): every open row `sd shadow sync` keeps, Operations > Trackers until then.

The rows are the cache `sd shadow sync` keeps in `shadow`, of every tracker: GitHub's watched and other-repository rows
and Jira's issues, which the other GitHub views leave out. `trackers_screen.document` reads them through
`progress.tracker_items` and each tracker's health through `progress.tracker_freshness`; `/api/github/tracked` serves
it, and `tracked.js` draws one table on the GitHub page. A failed read is the table's one row naming it, never an empty
list. Nothing here opens a database of its own; the criterion 2 grep in `tests/test_markup.py` is the check.
"""

import http.client
import json
import re
import subprocess
import unittest
from pathlib import Path

from sd_dashboard import trackers_screen, v2
from sd_db import upsert_shadow
from sd_db.shadow_sync import write_watermark
from sd_db.writes import record_state
from support import NOW, ScreenCase
from test_v2_tasks import MARKUP_JS, SHELL, STAND_IN
from test_v2_today import OSASCRIPT
from test_workflow_actions import BrowserSession

PULL = "https://github.com/acme/widgets/pull/4321"
JIRA = "https://example.atlassian.net/browse/LOG-1234"
V2 = Path(v2.__file__).resolve().parent
SCRIPT = V2 / "static" / "tracked.js"
PAGE_JS = SCRIPT.read_text(encoding="utf-8") if SCRIPT.exists() else ""


def shadow(connection):
    upsert_shadow(connection, tracker="github", repo="acme/widgets", url=PULL,
                  number=4321, kind="pull", title="Widen the widget", state="open", author="pat")
    upsert_shadow(connection, tracker="jira", repo="LOG", url=JIRA,
                  kind="issue", title="Log lines arrive twice", state="open", author="Pat Example")


class TheDocument(ScreenCase):

    def setUp(self):
        super().setUp()
        shadow(self.connection)

    def read(self):
        return trackers_screen.document(self.connection, now=NOW)

    def refs(self):
        return sorted(row["ref"] for row in self.read()["rows"])

    def test_a_github_row_shows_its_number_and_a_jira_row_its_ticket_not_its_project(self):
        # The key is the URL's last path segment, never the `repo` column, which for Jira is the project.
        rows = {row["ref"]: row for row in self.read()["rows"]}
        self.assertEqual(sorted(rows), ["LOG-1234", "acme/widgets#4321"])
        self.assertEqual({k: rows["LOG-1234"][k] for k in ("tracker", "kind", "repo", "url", "author")},
                         {"tracker": "jira", "kind": "issue", "repo": "LOG", "url": JIRA, "author": "Pat Example"})
        self.assertEqual((rows["acme/widgets#4321"]["kind"], rows["acme/widgets#4321"]["url"]), ("pull", PULL))

    def test_only_open_pull_requests_and_issues_are_listed_from_every_tracker(self):
        upsert_shadow(self.connection, tracker="github", repo="acme/widgets",
                      url="https://github.com/acme/widgets/issues/7", number=7, kind="issue",
                      title="Widget wobbles", state="open", author="pat")
        upsert_shadow(self.connection, tracker="github", repo="acme/widgets",
                      url="https://github.com/acme/widgets/pull/9", number=9, kind="pull",
                      title="Merged already", state="merged", author="pat")
        self.assertEqual(self.refs(), ["LOG-1234", "acme/widgets#4321", "acme/widgets#7"])

    def test_each_tracker_reports_its_sync_health(self):
        health = {t["tracker"]: t for t in self.read()["trackers"]}
        self.assertEqual((health["github"]["state"], health["jira"]["state"]), ("never", "never"))
        write_watermark(self.connection, "jira", "2026-09-01T11:00:00+00:00", "2026-08-31T11:00:00+00:00")
        jira = {t["tracker"]: t for t in self.read()["trackers"]}["jira"]
        self.assertEqual((jira["state"], jira["last_success_at"]), ("stale", "2026-09-01T11:00:00+00:00"))
        record_state(self.connection, "heartbeat", key="tracker-sync:jira", timestamp="2026-09-06T11:30:00+00:00",
                     body={"ok": False, "reason": "Jira answered 503"})
        jira = {t["tracker"]: t for t in self.read()["trackers"]}["jira"]
        self.assertEqual((jira["state"], jira["reason"]), ("degraded", "Jira answered 503"))

    def test_an_unsafe_url_is_no_link(self):
        upsert_shadow(self.connection, tracker="jira", repo="LOG", url="javascript:alert(1)/<b>x",
                      kind="issue", title="odd", state="open")
        # An authority with no host: `netloc` is `@`, `hostname` is None.
        upsert_shadow(self.connection, tracker="jira", repo="LOG", url="https://@/browse/LOG-1",
                      kind="issue", title="hostless", state="open")
        rows = {row["ref"]: row for row in self.read()["rows"]}
        self.assertEqual((rows["<b>x"]["url"], rows["LOG-1"]["url"]), (None, None))

    def test_a_failed_read_is_an_error_not_an_empty_list(self):
        self.connection.execute("DROP TABLE shadow")
        found = self.read()
        self.assertTrue(found["error"])
        self.assertEqual(found["rows"], [])


class TheRoute(BrowserSession):
    def raw(self, path):
        """`(status, Location)` without following a redirect."""
        host, port = self.listening.server_address[:2]
        connection = http.client.HTTPConnection(host, port, timeout=10)
        try:
            connection.request("GET", path, headers={"Cookie": self.cookie})
            answer = connection.getresponse()
            answer.read()
        finally:
            connection.close()
        return answer.status, answer.headers["Location"]

    def test_the_github_page_serves_the_tracked_view_and_its_read_needs_a_session(self):
        shadow(self.connection)
        self.connection.commit()
        status, _, answer = self.request("/api/github/tracked", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200, answer)
        self.assertEqual(sorted(row["ref"] for row in json.loads(answer)["rows"]), ["LOG-1234", "acme/widgets#4321"])
        self.assertNotEqual(self.request("/api/github/tracked")[0], 200)
        status, _, page = self.request("/github", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200)
        self.assertIn('id="view-tracked"', page)
        scripts = re.findall(r'<script src="/ui/([^"?]+)', page)
        self.assertLess(scripts.index("github.js"), scripts.index("tracked.js"))
        self.assertLess(scripts.index("tracked.js"), scripts.index("shell.js"))
        self.assertEqual(self.request("/ui/tracked.js")[0], 200)

    def test_an_old_trackers_address_answers_301_to_the_tracked_view(self):
        for query in ("?area=trackers", "?area=trackers&view=issues&q=widget"):
            self.assertEqual(self.raw(f"/operations{query}"), (301, "/github#view=tracked"), query)


class TheScript(unittest.TestCase):
    """tracked.js against the stand-in page: it reads when the view shows and draws one escaped table."""

    def run_page(self, body, answer):
        script = (STAND_IN + MARKUP_JS + "\nconst mk = window.markup.html;\n" + SHELL
                  + "\nANSWER = " + answer + ";\n" + PAGE_JS
                  + "\nvar R = {};\nconst show = () => document.dispatchEvent(new CustomEvent('shell:view', { detail: { id: 'tracked', first: true } }));\n"
                  + "(async () => { try {\n(DOC_LISTENERS.DOMContentLoaded || []).forEach(f => f());\nawait flush();\n"
                  + body + "\n} catch (e) { OUT.error = String(e) + ' ' + e.stack; } })();\n"
                  + "function run() { OUT.R = R; return JSON.stringify(OUT); }\n")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script],
                                capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out

    def doc(self):
        return {"rows": [
            {"key": PULL, "tracker": "github", "kind": "pull", "ref": "acme/widgets#4321", "title": "<b>Widen</b>",
             "repo": "acme/widgets", "author": "pat", "state": "open", "last_seen": "2026-09-06T11:00:00Z", "url": PULL},
            {"key": JIRA, "tracker": "jira", "kind": "issue", "ref": "LOG-1234", "title": "Log lines arrive twice",
             "repo": "LOG", "author": "Pat Example", "state": "open", "last_seen": None, "url": None}],
            "trackers": [{"tracker": "github", "state": "fresh", "last_success_at": "2026-09-06T11:00:00Z", "reason": ""},
                         {"tracker": "jira", "state": "degraded", "last_success_at": None, "reason": "Jira answered 503"}],
            "error": ""}

    def test_the_view_reads_once_shown_and_draws_each_row_escaped(self):
        out = self.run_page("R.before = OUT.gets.length; show(); await flush(); R.rows = ELS['tracked'].html;"
                            " R.health = ELS['tracked-health'].html; R.tally = ELS['tracked-tally'].html;",
                            f"(path, body) => [200, {json.dumps(self.doc())}]")
        self.assertEqual((out["R"]["before"], out["gets"]), (0, ["/api/github/tracked"]))
        rows = out["R"]["rows"]
        self.assertIn(f'<a href="{PULL}" target="_blank" rel="noopener noreferrer">acme/widgets#4321</a>', rows)
        self.assertIn("&lt;b&gt;Widen&lt;/b&gt;", rows)
        self.assertNotIn("<b>Widen</b>", rows)
        self.assertIn('<td class="why">Jira issue</td>', rows)
        self.assertIn('<td class="why">GitHub pull request</td>', rows)
        self.assertIn('<td class="ref">LOG-1234</td>', rows)
        self.assertIn("github: fresh", out["R"]["health"])
        self.assertIn("jira: degraded · Jira answered 503", out["R"]["health"])
        self.assertEqual(out["R"]["tally"], "2 open rows")
        self.assertEqual(out["counts"], {"tracked": 2})

    def test_a_failed_read_is_a_row_naming_it_never_an_empty_list(self):
        out = self.run_page("show(); await flush(); R.rows = ELS['tracked'].html;",
                            "(path, body) => [500, { error: 'database is locked' }]")
        self.assertIn("The tracked rows were not read: ", out["R"]["rows"])
        self.assertEqual(out["counts"], {"tracked": None})


if __name__ == "__main__":
    unittest.main()
