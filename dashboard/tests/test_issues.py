"""Your issues (sd:4628): each repo's Jira and GitHub issues assigned to or filed by the operator.

sd:5645 moved the section off Tasks to Today's Issues view, and Tasks keeps no copy. sd:5781 moved it, and Issue intake,
to the GitHub page's Your issues and Intake tabs, read from `/api/github/issues` instead of Today's `/api/now`.

The rows come from `sd_db.repos.mine_issues` (pack sd:4636), which filters `shadow` on its `reason` column. The pin in
`.sd-pack-rev` predates both, so these stub the read: what is under test is the page's half, the document, its failure
sentences and the drawn table. The pack's own suite tests the filter.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from pathlib import Path
from unittest import mock

from sd_dashboard import issues, now_screen, tasks_screen, v2
from sd_dashboard.v2.pages import Read
from sd_db import progress, repos, upsert_shadow, workflow, writes
from support import NOW, ScreenCase
from test_now_screen import JobsBackend, fleet_document
from test_v2_tasks import ASIDE_JS, MARKUP_JS, SHELL, STAND_IN
from test_v2_today import OSASCRIPT, run_js
from test_workflow_actions import BrowserSession

V2 = Path(v2.__file__).resolve().parent
ISSUES_JS = (V2 / "static" / "issues.js").read_text(encoding="utf-8") if (V2 / "static" / "issues.js").exists() else ""

FOUND = {
    "/home/example/repos/acme/anvil": [
        {"tracker": "jira", "url": "https://example.test/browse/EXAMPLE-8", "number": None, "title": "Fix the <b>widget</b>",
         "state": "open", "reason": "filed", "last_seen": "2026-09-06T08:00:00+00:00"},
        {"tracker": "github", "url": "https://github.com/example/project/issues/12", "number": 12, "title": "Crash on start",
         "state": "open", "reason": "assigned", "last_seen": "2026-09-05T08:00:00+00:00"},
    ],
    "/home/example/repos/other/kiln": [
        {"tracker": "github", "url": "javascript:alert(1)", "number": 3, "title": "Odd link", "state": "open",
         "reason": "assigned", "last_seen": "2026-09-04T08:00:00+00:00"},
    ],
}


class NoJobs:
    """An operations backend with no job installed, as on a machine without the sync job: no launchctl call is made."""

    cron_root = None

    def inspect(self, name):
        raise workflow.WorkflowError("job is not supported: trusted regular files are required")


def github_issues(connection, jobs=None):
    """What the GitHub page's Your issues and Intake tabs read: /api/github/issues."""
    _, route = v2.api("/api/github/issues")
    return route.read(Read(connection=connection, now=NOW, path="/api/github/issues", jobs=jobs or NoJobs()))


def stub(**kwargs):
    return mock.patch.object(repos, "mine_issues", create=True, **kwargs)


class TheDocument(ScreenCase):
    def test_each_issue_names_its_repo_tracker_reference_reason_and_a_web_link_only(self):
        with stub(return_value=FOUND) as read:
            document = issues.document(self.connection)
        read.assert_called_once_with(self.connection)
        self.assertEqual(document["issues_error"], "")
        self.assertEqual([(row["repo"], row["tracker"], row["ref"], row["reason"], row["url"]) for row in document["issues"]], [
            ("anvil", "Jira", "EXAMPLE-8", "filed", "https://example.test/browse/EXAMPLE-8"),
            ("anvil", "GitHub", "#12", "assigned", "https://github.com/example/project/issues/12"),
            ("kiln", "GitHub", "#3", "assigned", None),
        ])

    def test_a_pack_without_the_read_is_said_with_its_remedy(self):
        with mock.patch.object(repos, "mine_issues", None, create=True):
            document = issues.document(self.connection)
        self.assertEqual(document, {"issues": [], "issues_error":
                                    "this sd_db has no repos.mine_issues; update the command pack"})

    def test_a_database_without_the_reason_column_is_said_with_its_remedy(self):
        with stub(side_effect=sqlite3.OperationalError("no such column: reason")):
            document = issues.document(self.connection)
        self.assertEqual(document, {"issues": [], "issues_error": "no such column: reason; run sd-db migrate"})

    def test_another_failed_read_is_said_not_empty(self):
        with stub(side_effect=sqlite3.OperationalError("database is locked")):
            document = issues.document(self.connection)
        self.assertEqual(document, {"issues": [], "issues_error": "database is locked"})


class TheDetails(ScreenCase):
    """sd:5877: each row carries what its Details show, from the `shadow` row sd shadow sync stored; no tracker is called."""

    def shadow(self, **row):
        row = {"kind": "issue", "state": "open", "first_seen": "2026-09-01T08:00:00+00:00",
               "last_seen": "2026-09-06T08:00:00+00:00", **row}
        self.connection.execute(f"INSERT INTO shadow ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})", list(row.values()))

    def test_each_row_carries_the_stored_facts_and_the_item_filed_under_its_ref(self):
        self.shadow(tracker="github", repo="example/project", url="https://github.com/example/project/issues/12", number=12,
                    title="Crash on start", author="octocat", assignee="example-user", updated_at="2026-09-05T09:00:00Z",
                    created_at="2026-09-01T09:00:00Z")
        self.shadow(tracker="jira", repo="EXAMPLE", url="https://example.test/browse/EXAMPLE-8", title="Fix",
                    author="Reporter Example", status="In Progress")
        filed, jira = self.item("the crash"), self.item("the widget")
        writes.set_item_fields(self.connection, filed, source="task-ref", external_id="github:example/project#12")
        writes.set_item_fields(self.connection, jira, source="task-ref", external_id="jira:EXAMPLE-8")
        with stub(return_value=FOUND):
            rows = {row["ref"]: row for row in issues.document(self.connection)["issues"]}
        crash = rows["#12"]
        self.assertEqual({name: crash[name] for name in ("key", "slug", "state", "assignee", "reporter", "updated_at", "item", "unread")},
                         {"key": "github:example/project#12", "slug": "example/project", "state": "open", "assignee": "example-user",
                          "reporter": "octocat", "updated_at": "2026-09-05T09:00:00Z", "item": filed, "unread": ""})
        self.assertEqual((rows["EXAMPLE-8"]["key"], rows["EXAMPLE-8"]["status"], rows["EXAMPLE-8"]["item"]),
                         ("jira:EXAMPLE-8", "In Progress", jira))
        # A row the store does not hold says nothing it did not record: every fact None, no item; never its url as key.
        self.assertEqual((rows["#3"]["key"], rows["#3"]["assignee"], rows["#3"]["item"]),
                         ("github:/home/example/repos/other/kiln#3", None, None))

    def test_intake_rows_carry_their_facts_and_a_failed_read_is_unread_not_empty(self):
        self.shadow(tracker="github", repo="example/project", url="https://github.com/example/project/issues/21", number=21,
                    title="Docs", author="octocat", updated_at="2026-09-06T07:00:00Z")
        with stub_intake(return_value=INTAKE):
            row = issues.intake(self.connection)["intake"][0]
        self.assertEqual((row["key"], row["reporter"], row["updated_at"], row["item"]),
                         ("github:example/project#21", "octocat", "2026-09-06T07:00:00Z", None))
        self.connection.execute("DROP TABLE shadow")
        with stub(return_value=FOUND):
            rows = issues.document(self.connection)["issues"]
        self.assertEqual({row["unread"] for row in rows}, {"no such table: shadow"})
        self.assertEqual({row["assignee"] for row in rows}, {None})


class ThePages(ScreenCase):
    def test_github_carries_the_issues_and_today_and_tasks_do_not(self):
        with stub(return_value=FOUND) as read:
            found = github_issues(self.connection)
            calls = read.call_count
            today = now_screen.document(self.connection, now=NOW, jobs=JobsBackend(self.tmp.name),
                                        fleet=lambda area: fleet_document(area))
            tasks = tasks_screen.document(self.connection, now=NOW)
        self.assertEqual(([row["ref"] for row in found["issues"]], found["issues_error"]), (["EXAMPLE-8", "#12", "#3"], ""))
        self.assertEqual(read.call_count, calls)  # sd:5645, sd:5781: neither Tasks nor Today reads them
        for other in (today, tasks):
            self.assertNotIn("issues", other)
            self.assertNotIn("issues_error", other)

    def test_your_issues_add_the_operators_other_github_issues_once_and_their_closed_ones(self):
        # sd:5899: the GitHub issues the Pull requests view listed join Your issues; one an issue source lists is not repeated.
        def issue(repo, number, **columns):
            upsert_shadow(self.connection, tracker="github", url=f"https://github.com/{repo}/issues/{number}", repo=repo,
                          number=number, kind="issue", title=f"{repo} {number}", **columns)
        issue("example/project", 12, state="open", reason="assigned")
        issue("upstream/tool", 5, state="open", reason="filed", filed=True, author="me")
        issue("upstream/tool", 6, state="closed", reason="filed", filed=True, author="me", closed_at="2026-09-05T10:00:00Z")
        issue("upstream/tool", 7, state="open", reason="watched", author="carol")
        self.connection.commit()
        with stub(return_value=FOUND):
            found = github_issues(self.connection)
        self.assertEqual(found["github_error"], "")
        self.assertEqual([(row["tracker"], row["ref"], row["repo"], row["state"], row["reason"]) for row in found["issues"]], [
            ("Jira", "EXAMPLE-8", "anvil", None, "filed"), ("GitHub", "#12", "anvil", "open", "assigned"),
            ("GitHub", "#3", "kiln", None, "assigned"), ("GitHub", "#5", "upstream/tool", "open", "upstream"),
            ("GitHub", "#6", "upstream/tool", "closed", "upstream")])
        self.assertEqual(found["issues"][3]["key"], "github:upstream/tool#5")
        with stub(return_value=FOUND), mock.patch.object(progress, "tracker_items", side_effect=sqlite3.OperationalError("database is locked")):
            failed = github_issues(self.connection)
        self.assertEqual((failed["github_error"], len(failed["issues"])), ("database is locked", 3))

    def test_each_issue_names_the_pull_requests_that_close_it_open_first(self):
        # pack sd:7841: the pull requests GitHub's search says close an issue, from the same read; none is [].
        def pull(number, **columns):
            upsert_shadow(self.connection, tracker="github", url=f"https://github.com/example/project/pull/{number}",
                          repo="example/project", number=number, kind="pull", title=f"Fix {number}", reason="filed",
                          filed=True, author="me", **columns)
        pull(41, state="merged", merged_at="2026-09-05T10:00:00Z", linked_issues=["https://github.com/example/project/issues/12"])
        # Another spelling of the same address: GitHub's two reads do not always agree on case.
        pull(40, state="open", updated_at="2026-09-06T09:00:00Z", linked_issues=["https://github.com/Example/Project/issues/12/"])
        pull(42, state="open", updated_at="2026-09-06T10:00:00Z", linked_issues=[])
        self.connection.commit()
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE):
            found = github_issues(self.connection)
        pulls = {row["url"] or row["ref"]: row["pulls"] for row in (*found["issues"], *found["intake"])}
        self.assertEqual(pulls.pop("https://github.com/example/project/issues/12"), [
            {"url": "https://github.com/example/project/pull/40", "ref": "example/project#40", "number": 40,
             "state": "open", "title": "Fix 40"},
            {"url": "https://github.com/example/project/pull/41", "ref": "example/project#41", "number": 41,
             "state": "merged", "title": "Fix 41"}])
        self.assertEqual(pulls, dict.fromkeys(pulls, []))
        self.assertEqual(len(pulls), 4)

    def test_a_failed_issue_read_leaves_the_intake(self):
        with stub(side_effect=sqlite3.OperationalError("database is locked")), stub_intake(return_value=INTAKE):
            found = github_issues(self.connection)
        self.assertEqual((found["issues_error"], [row["ref"] for row in found["intake"]]), ("database is locked", ["#21", "#22"]))

    def test_issues_draws_the_section_and_loads_its_script_before_the_shell(self):
        # pack sd:7682: the Issues page holds Your issues, GitHub's view until then.
        html = (V2 / "issues.html").read_text(encoding="utf-8")
        self.assertIn('<tbody id="issues">', html)
        self.assertIn('id="issues-tally"', html)
        self.assertIn('<link rel="stylesheet" href="/ui/issues.css">', html)
        scripts = re.findall(r'<script src="/ui/([a-z-]+\.js)"></script>', html)
        self.assertLess(scripts.index("github.js"), scripts.index("issues.js"))
        self.assertLess(scripts.index("issues.js"), scripts.index("shell.js"))
        self.assertIn("issues:read", (V2 / "static" / "github.js").read_text(encoding="utf-8"))
        self.assertNotIn("issues:read", (V2 / "static" / "today.js").read_text(encoding="utf-8"))

    def test_tasks_keeps_no_copy_of_the_section(self):
        # sd:5645: the section moved to Today; Tasks draws none, loads neither its script nor its sheet, and reads none.
        html = (V2 / "tasks.html").read_text(encoding="utf-8")
        for gone in ('id="issues-h"', '<tbody id="issues">', 'id="issues-tally"', "/ui/issues.js", "/ui/issues.css",
                     "Your issues"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, html)
        self.assertNotIn("issues:read", (V2 / "static" / "tasks.js").read_text(encoding="utf-8"))


class TheTable(ScreenCase):
    """issues.js under JavaScriptCore: it draws what the page's read hands it, escaped, and says a failure."""

    PAGE = """
var location = { search: '' };
function URLSearchParams(q) { var m = new Map(String(q || '').replace(/^[?]/, '').split('&').filter(Boolean).map(p => p.split('=')));
  this.get = k => m.has(k) ? m.get(k) : null; this.set = (k, v) => m.set(k, v); this.delete = k => m.delete(k); }
var els = {}, listeners = {};
document.getElementById = id => (els[id] = els[id] || { id, replaceChildren(f) { sunk.push([id, f.parsed]); } });
document.addEventListener = (t, f) => { listeners[t] = f; };
window.shell = { aside: (() => { const { html } = window.markup;
""" + ASIDE_JS + """
    return aside; })() };
"""

    def drawn(self, detail, search=""):
        script = (self.PAGE + f"location.search = '{search}';" + ISSUES_JS
                  + f"listeners['issues:read']({{ detail: {json.dumps(detail)} }}); JSON.stringify(sunk)")
        return dict(run_js(self, script))

    def test_rows_link_the_reference_escape_the_title_and_name_the_reason(self):
        with stub(return_value=FOUND):
            document = issues.document(self.connection)
        drawn = self.drawn({"issues": document["issues"], "error": ""})
        self.assertIn('<a href="https://example.test/browse/EXAMPLE-8">Jira EXAMPLE-8</a>', drawn["issues"])
        self.assertIn("Fix the &lt;b&gt;widget&lt;/b&gt;", drawn["issues"])
        self.assertIn(">assigned<", drawn["issues"])
        self.assertNotIn("javascript:", drawn["issues"])
        # pack sd:7753: GitHub #3 sits in its repo's group, closed while anvil's is open.
        self.assertIn('data-cat-open="repo:kiln"', drawn["issues"])
        self.assertIn("3 open", drawn["issues-tally"])

    def test_each_row_says_when_it_was_last_updated(self):
        # pack sd:7464: an Updated column, the stored updated_at as a relative time; none stored says so.
        rows = [{"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-8", "key": "jira:EXAMPLE-8", "title": "Fix", "reason": "filed",
                 "url": None, "state": None, "updated_at": "2026-11-01T10:00:00Z"},
                {"repo": "anvil", "tracker": "GitHub", "ref": "#3", "key": "github:anvil#3", "title": "Crash", "reason": "assigned",
                 "url": None, "state": None}]
        drawn = self.drawn({"issues": rows, "error": ""})["issues"]
        self.assertIn('<td class="when"><time class="rel" datetime="2026-11-01T10:00:00Z"></time></td>', drawn)
        self.assertIn('<td class="when"><span class="ph">not stored</span></td>', drawn)
        self.assertIn("<th>Updated</th>", (V2 / "issues.html").read_text(encoding="utf-8"))

    def test_a_closed_row_shows_with_closed_only_and_a_failed_github_read_is_said(self):
        # sd:5899: Your issues holds the operator's closed GitHub issues of the window; State open hides them.
        rows = [{"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-8", "key": "jira:EXAMPLE-8", "title": "Fix", "reason": "filed",
                 "url": None, "state": None},
                {"repo": "upstream/tool", "tracker": "GitHub", "ref": "#6", "key": "github:upstream/tool#6", "title": "Old crash",
                 "reason": "upstream", "url": None, "state": "closed"}]
        hidden = self.drawn({"issues": rows, "error": ""})
        shown = self.drawn({"issues": rows, "error": ""}, search="?iss=closed")
        self.assertNotIn("Old crash", hidden["issues"])
        self.assertIn("<span>1 open</span>", hidden["issues-tally"])
        self.assertIn("closed · upstream", shown["issues"])
        self.assertIn("1 closed in 7 d", shown["issues-tally"])
        failed = self.drawn({"issues": rows, "error": "", "github": "database is locked"})
        self.assertIn("Your GitHub issues outside the repos' issue sources were not read: database is locked", failed["issues"])
        self.assertIn("Jira EXAMPLE-8", failed["issues"])

    def test_your_issues_says_open_once_and_one_chip_adds_the_closed_ones(self):
        """Pack sd:7084: Open | Hidden already says open; the State group is one with closed chip, no second open."""
        rows = [{"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-8", "key": "jira:EXAMPLE-8", "title": "Fix", "reason": "filed",
                 "url": None, "state": None},
                {"repo": "upstream/tool", "tracker": "GitHub", "ref": "#6", "key": "github:upstream/tool#6", "title": "Old crash",
                 "reason": "upstream", "url": None, "state": "closed"}]
        # A list stand-in that writes each State item as the page passed it, beside the real set-aside group.
        lists = ("window.shell.list = { fbar: x => x, fseg: (k, n, items) => window.markup.html`${items.map(i =>"
                 " window.markup.html`<i data-f=\"${k}\" data-v=\"${i.v}\" data-p=\"${String(!!i.pressed)}\">${i.label}</i>`)}` };")
        chip = r'data-f="iss" data-v="(\w+)" data-p="(\w+)">([^<]+)<span class="n">(\d+)</span>'
        for search, want in (("", [("closed", "false", "with closed ", "1")]), ("?iss=closed", [("open", "true", "with closed ", "1")])):
            script = (self.PAGE + lists + f"location.search = '{search}';" + ISSUES_JS
                      + f"listeners['issues:read']({{ detail: {json.dumps({'issues': rows, 'error': ''})} }}); JSON.stringify(sunk)")
            bar = dict(run_js(self, script))["issues-filters"]
            self.assertEqual(re.findall(chip, bar), want, search)
            self.assertEqual(bar.count(">Open <"), 1, search)

    def test_a_failure_is_a_row_naming_it_and_none_is_said(self):
        failed = self.drawn({"issues": [], "error": "database is locked"})
        self.assertIn("Issues could not be read: database is locked. Read again tries again.", failed["issues"])
        self.assertNotIn("open", failed["issues-tally"])
        empty = self.drawn({"issues": [], "error": ""})
        self.assertIn("No open issue is assigned to you or filed by you", empty["issues"])


class TheDetailsPane(ScreenCase):
    """sd:5877 under JavaScriptCore: a row of Your issues or Intake opens its Details, as a pull request row does."""

    PAGE = """
var location = { search: '' };
function URLSearchParams(q) { var m = new Map(String(q || '').replace(/^[?]/, '').split('&').filter(Boolean).map(p => p.split('=')));
  this.get = k => m.has(k) ? m.get(k) : null; this.set = (k, v) => m.set(k, v); this.delete = k => m.delete(k); }
var els = {}, listeners = {}, opened = [], selected = [], panes = [], registered = [], objects = {};
document.getElementById = id => (els[id] = els[id] || { id, replaceChildren(f) { sunk.push([id, f.parsed]); } });
document.addEventListener = (t, f) => { (listeners[t] = listeners[t] || []).push(f); };
document.querySelectorAll = () => [];
const fire = (t, detail) => (listeners[t] || []).forEach(f => f({ detail }));
window.open = (u, t) => opened.push([u, t]);
window.shell = { itemHref: n => `/tasks?item=${n}`, openItem: n => `#${n} opens in Tasks`, shq: v => `'${v}'`, row: () => null,
  openPane: tab => panes.push(tab), post: () => new Promise(() => {}),
  commands: { put: o => { objects[o.id] = o; }, get: id => objects[id], register: (...c) => registered.push(...c),
    select: id => selected.push(id), bar: id => window.markup.html`<div class="bar">${id}</div>` },
  aside: (() => { const { html } = window.markup;
""" + ASIDE_JS + """
    return aside; })() };
"""

    shadow = TheDetails.shadow

    def run_page(self, then):
        self.shadow(tracker="github", repo="example/project", url="https://github.com/example/project/issues/12", number=12,
                    title="Crash on start", author="octocat", assignee="example-user", updated_at="2026-09-05T09:00:00Z")
        filed = self.item("the crash")
        writes.set_item_fields(self.connection, filed, source="task-ref", external_id="github:example/project#12")
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE):
            found = github_issues(self.connection)
        script = (self.PAGE + COMMANDS_JS + ISSUES_JS + "fire('DOMContentLoaded');"
                  + f"fire('issues:read', {{ issues: {json.dumps(found['issues'])}, error: '' }});"
                  + f"fire('intake:read', {{ intake: {json.dumps(found['intake'])}, error: '' }});" + then
                  + "JSON.stringify({ sunk, opened, selected, panes, ids: registered.map(c => c.id), types: Object.values(objects).map(o => o.type) })")
        return filed, run_js(self, script)

    def test_a_row_opens_its_details_with_the_stored_facts_and_its_actions(self):
        filed, out = self.run_page("window.issues.details('iss:github:example/project#12');")
        drawn = dict(out["sunk"])
        self.assertIn('data-id="iss:github:example/project#12"', drawn["issues"])
        self.assertIn('data-iss-open="iss:jira:EXAMPLE-8"', drawn["issues"])
        self.assertIn('data-iss-open="iss:github:example/project#21"', drawn["intake"])
        self.assertIn(">File as item<", drawn["intake"])
        details = drawn["details"]
        for shown in ("GitHub issue · open", "<h2>Crash on start</h2>", "example/project", "example-user", "octocat",
                      'datetime="2026-09-05T09:00:00Z"', f'<a href="/tasks?item={filed}">sd:{filed}</a>',
                      '<div class="bar">iss:github:example/project#12</div>'):
            self.assertIn(shown, details)
        # pack sd:7718: the Act bar's Open on GitHub opens the issue, so Details carry no text link to it.
        self.assertNotIn("https://github.com/example/project/issues/12", details)
        self.assertNotIn("Open #12 on GitHub", details)
        self.assertIn("<dt>Labels</dt><dd><span class=\"ph\">not stored</span>", details)
        self.assertIn("<dt>Priority</dt>", details)
        self.assertIn("sd shadow sync keeps no labels, priority or description", details)
        self.assertEqual((out["selected"], out["panes"]), (["iss:github:example/project#12"], ["tab-details"]))
        self.assertEqual(out["ids"], ["jira issue.open", "jira issue.item", "jira issue.hide", "jira issue.unhide",
                                      "github issue.open", "github issue.item", "github issue.hide", "github issue.unhide",
                                      # pack sd:7787: File as item, in Details and the bulk bar.
                                      "github issue.file",
                                      # pack sd:7841: Open PR, the pull request that closes the issue.
                                      "github issue.pr",
                                      # pack sd:7708: Set category, then the category list's commands.
                                      "jira issue.category", "issue categories.add", "issue category.rename", "issue category.remove"])
        self.assertEqual(sorted(set(out["types"])), ["github issue", "issue categories", "jira issue"])

    def test_a_row_a_pull_request_closes_has_its_icon_and_open_pr_and_the_others_neither(self):
        # pack sd:7841: the row's icon and Details' Open PR open the open pull request in a new tab; a row none
        # closes draws neither, and Open PR is off on it with the reason.
        for number, state, linked in ((40, "open", ["https://github.com/example/project/issues/12"]),
                                      (39, "merged", ["https://github.com/example/project/issues/12"])):
            upsert_shadow(self.connection, tracker="github", url=f"https://github.com/example/project/pull/{number}",
                          repo="example/project", number=number, kind="pull", title=f"Fix {number}", state=state,
                          reason="filed", filed=True, author="me", linked_issues=linked,
                          merged_at="2026-09-05T10:00:00Z" if state == "merged" else None)
        self.connection.commit()
        _, out = self.run_page(
            "window.issues.details('iss:github:example/project#12');"
            "const pr = registered.find(c => c.id === 'github issue.pr'), o = objects['iss:github:example/project#12'];"
            "const none = objects['iss:github:example/project#21'];"
            "if (pr) sunk.push(['ran', pr.run(o)], ['cli', pr.cli(o)], ['off', String(pr.when(none))], ['on', String(pr.when(o))]);")
        drawn = dict(out["sunk"])
        row = re.search(r'<tr data-id="iss:github:example/project#12".*?</tr>', drawn["issues"], re.S)[0]
        self.assertIn('<a class="icon-btn" href="https://github.com/example/project/pull/40" target="_blank" '
                      'rel="noopener noreferrer" aria-label="Open pull request example/project#40 on GitHub"', row)
        self.assertIn('<use href="#i-git-pull-request"/>', row)
        self.assertIn("1 more pull request", row)
        self.assertNotIn("i-git-pull-request", drawn["intake"])
        other = re.search(r'<tr data-id="iss:github:/home/example/repos/other/kiln#3".*?</tr>', drawn["issues"], re.S)
        self.assertNotIn("i-git-pull-request", other[0] if other else "")
        self.assertIn('<dt>Pull requests</dt><dd>example/project#40 · open, <a href="https://github.com/example/project/pull/39" '
                      'target="_blank" rel="noopener noreferrer">example/project#39</a> · merged</dd>', drawn["details"])
        self.assertEqual(out["opened"], [["https://github.com/example/project/pull/40", "_blank"]])
        self.assertEqual((drawn["ran"], drawn["cli"], drawn["on"], drawn["off"]), (
            "Opened on GitHub in a new tab", "gh pr view 40 --repo example/project --web", "true",
            "no pull request closes this issue"))

    def test_a_jira_row_opens_in_jira_by_its_command_and_a_fact_not_stored_says_so(self):
        _, out = self.run_page("window.issues.details('iss:jira:EXAMPLE-8');"
                               "const o = objects['iss:jira:EXAMPLE-8']; R = registered.find(c => c.id === 'jira issue.open').run(o);")
        details = dict(out["sunk"])["details"]
        self.assertNotIn("Open EXAMPLE-8 in Jira", details)  # pack sd:7718: the command below opens it
        self.assertIn("<dt>Assignee</dt><dd><span class=\"ph\">not stored</span>", details)
        self.assertIn("none filed under this issue", details)
        self.assertEqual(out["opened"], [["https://example.test/browse/EXAMPLE-8", "_blank"]])


INTAKE = {
    "/home/example/repos/acme/anvil": [
        {"tracker": "github", "repo": "example/project", "url": "https://github.com/example/project/issues/21",
         "number": 21, "title": "Docs <i>typo</i>", "state": "open", "reason": "watched", "author": "octocat",
         "last_seen": "2026-09-06T08:00:00+00:00"},
        {"tracker": "github", "repo": "example/project", "url": "javascript:alert(1)", "number": 22, "title": "Odd",
         "state": "open", "reason": None, "author": None, "last_seen": "2026-09-05T08:00:00+00:00"},
    ],
}


def stub_intake(**kwargs):
    return mock.patch.object(repos, "intake_issues", create=True, **kwargs)


class TheIntake(ScreenCase):
    """Issue intake on Today (sd:4840): each `github_issues` repo's open third-party issues that no sd item carries,
    from `sd_db.repos.intake_issues` (pack sd:4880). Stubbed here as Your issues is: the pack's suite tests the read."""

    def test_each_row_names_its_repo_reference_author_and_the_ref_an_item_files_it_under(self):
        with stub_intake(return_value=INTAKE) as read:
            document = issues.intake(self.connection)
        read.assert_called_once_with(self.connection)
        self.assertEqual(document["intake_error"], "")
        self.assertEqual([(row["repo"], row["repo_path"], row["ref"], row["key"], row["author"], row["url"])
                          for row in document["intake"]], [
            ("anvil", "/home/example/repos/acme/anvil", "#21", "github:example/project#21", "octocat",
             "https://github.com/example/project/issues/21"),
            ("anvil", "/home/example/repos/acme/anvil", "#22", "github:example/project#22", "", None),
        ])

    def test_a_pack_without_the_read_or_a_failed_read_is_said_not_empty(self):
        with mock.patch.object(repos, "intake_issues", None, create=True):
            self.assertEqual(issues.intake(self.connection), {"intake": [], "intake_error":
                             "this sd_db has no repos.intake_issues; update the command pack"})
        with stub_intake(side_effect=sqlite3.OperationalError("no such column: declarations")):
            self.assertEqual(issues.intake(self.connection), {"intake": [], "intake_error":
                             "no such column: declarations"})
        with stub_intake(side_effect=sqlite3.OperationalError("database is locked")):
            self.assertEqual(issues.intake(self.connection), {"intake": [], "intake_error": "database is locked"})

    def test_github_carries_the_intake_and_a_failure_leaves_the_rest(self):
        with stub_intake(return_value=INTAKE), stub(return_value=FOUND):
            found = github_issues(self.connection)
        self.assertEqual([row["ref"] for row in found["intake"]], ["#21", "#22"])
        with stub_intake(side_effect=sqlite3.OperationalError("database is locked")), stub(return_value=FOUND):
            found = github_issues(self.connection)
        self.assertEqual((found["intake_error"], len(found["issues"])), ("database is locked", 3))

    def test_issues_draws_the_section_and_hands_the_rows_over(self):
        html = (V2 / "issues.html").read_text(encoding="utf-8")
        self.assertIn('<tbody id="intake">', html)
        self.assertIn('id="intake-tally"', html)
        self.assertIn("intake:read", (V2 / "static" / "github.js").read_text(encoding="utf-8"))


class TheIntakeTable(ScreenCase):
    """issues.js draws the intake rows, each with File as item, which posts the item under the issue's ref."""

    PAGE = TheTable.PAGE + """
var posted = [];
window.shell = { aside: window.shell.aside, post: (path, body) => { posted.push([path, body]); return new Promise(() => {}); } };
"""

    def drawn(self, detail, then=""):
        script = (self.PAGE + ISSUES_JS + f"listeners['intake:read']({{ detail: {json.dumps(detail)} }});" + then
                  + "JSON.stringify({ sunk, posted })")
        return run_js(self, script)

    def test_rows_escape_link_only_https_and_carry_a_file_control(self):
        with stub_intake(return_value=INTAKE):
            document = issues.intake(self.connection)
        out = self.drawn({"intake": document["intake"], "error": ""})
        drawn = dict(out["sunk"])
        self.assertIn('<a href="https://github.com/example/project/issues/21">GitHub #21</a>', drawn["intake"])
        self.assertIn("Docs &lt;i&gt;typo&lt;/i&gt;", drawn["intake"])
        self.assertNotIn("javascript:", drawn["intake"])
        self.assertIn(">octocat<", drawn["intake"])
        self.assertEqual(drawn["intake"].count(">File as item<"), 2)
        self.assertIn('data-key="github:example/project#21"', drawn["intake"])
        self.assertIn("2 waiting", drawn["intake-tally"])

    def test_file_posts_a_task_under_the_issue_s_ref_in_its_repo_and_marks_the_row_busy(self):
        with stub_intake(return_value=INTAKE):
            document = issues.intake(self.connection)
        out = self.drawn({"intake": document["intake"], "error": ""}, "window.issues.file('github:example/project#21');")
        self.assertEqual(out["posted"], [["/api/items", {"title": "Docs <i>typo</i>", "repo": "/home/example/repos/acme/anvil",
                                                         "ref": "github:example/project#21"}]])
        self.assertIn('aria-busy="true"', out["sunk"][-2][1])

    def test_a_failure_is_a_row_naming_it_and_none_is_said(self):
        failed = dict(self.drawn({"intake": [], "error": "database is locked"})["sunk"])
        self.assertIn("Issue intake could not be read: database is locked. Read again tries again.", failed["intake"])
        empty = dict(self.drawn({"intake": [], "error": ""})["sunk"])
        self.assertIn("No third-party issue waits for an item", empty["intake"])


class TheHideState(ScreenCase):
    """sd:6175: each Your issues and Intake row carries `hidden`, the view state Contributions' and Designs' Hide write,
    keyed `issue:<row key>`; a view store that does not read hides nothing and says why Hide is off."""

    def test_a_hidden_row_carries_hidden_and_the_rest_do_not(self):
        writes.set_view(self.connection, issues.view_key("jira:EXAMPLE-8"), hidden=True)
        writes.set_view(self.connection, issues.view_key("github:example/project#21"), hidden=True)
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE):
            found = github_issues(self.connection)
        self.assertEqual([(row["ref"], row["hidden"]) for row in found["issues"]], [("EXAMPLE-8", True), ("#12", False), ("#3", False)])
        self.assertEqual([(row["key"], row["hidden"]) for row in found["intake"]],
                         [("github:example/project#21", True), ("github:example/project#22", False)])
        self.assertEqual(found["store"], {"available": True, "reason": ""})

    def test_the_key_ignores_case_so_a_renamed_slug_stays_hidden(self):
        self.assertEqual(issues.view_key("github:Example/Project#21"), issues.view_key("github:example/project#21"))
        self.assertTrue(issues.view_key("jira:EXAMPLE-8").startswith("issue:"))

    def test_a_view_store_that_does_not_read_hides_nothing_and_says_why(self):
        writes.set_view(self.connection, issues.view_key("jira:EXAMPLE-8"), hidden=True)
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE), \
                mock.patch.object(writes, "views", side_effect=sqlite3.OperationalError("database is locked")):
            found = github_issues(self.connection)
        self.assertEqual({row["hidden"] for row in found["issues"] + found["intake"]}, {False})
        self.assertEqual(found["store"], {"available": False, "reason": "the view store was not read: database is locked"})


class TheSyncJob(ScreenCase):
    """sd:6175: the issue read carries Refresh from GitHub's job, shadow-sync-nightly, as the jobs inventory reads it: the revision
    the retry route checks and the retry capability that turns Refresh from GitHub off."""

    def test_the_read_carries_the_jobs_state_revision_and_retry_capability(self):
        backend = JobsBackend(self.tmp.name, jobs=[("shadow-sync-nightly", "idle", 0, None)])
        with stub(return_value={}), stub_intake(return_value={}):
            sync = github_issues(self.connection, jobs=backend)["sync"]
        self.assertEqual((sync["name"], sync["service"], sync["state"]), ("shadow-sync-nightly", "fixture/shadow-sync-nightly", "idle"))
        self.assertRegex(sync["revision"], r"^[0-9a-f]{64}$")
        self.assertEqual(sync["capabilities"]["retry"]["allowed"], True)
        running = JobsBackend(self.tmp.name, jobs=[("shadow-sync-nightly", "running", None, None)])
        with stub(return_value={}), stub_intake(return_value={}):
            sync = github_issues(self.connection, jobs=running)["sync"]
        self.assertEqual((sync["state"], sync["capabilities"]["retry"]["reason"]), ("running", "the job is already running"))

    def test_a_job_that_is_not_installed_is_said_with_the_line_that_installs_it(self):
        with stub(return_value={}), stub_intake(return_value={}):
            sync = github_issues(self.connection)["sync"]
        self.assertEqual(sync, {"name": "shadow-sync-nightly", "error": "shadow-sync-nightly is not an installed job (job is not "
                                "supported: trusted regular files are required); local-cron-jobs/cron-jobs.sh install "
                                "shadow-sync-nightly installs it"})

    def test_a_job_read_that_fails_is_said_not_a_job_that_is_off(self):
        class Broken(NoJobs):
            def inspect(self, name):
                raise OSError("launchctl: no answer")
        with stub(return_value={}), stub_intake(return_value={}):
            sync = github_issues(self.connection, jobs=Broken())["sync"]
        self.assertEqual(sync, {"name": "shadow-sync-nightly", "error": "shadow-sync-nightly was not read: launchctl: no answer"})


GITHUB_JS = (V2 / "static" / "github.js").read_text(encoding="utf-8")
COMMANDS_JS = (V2 / "static" / "commands.js").read_text(encoding="utf-8")
JOB = {"name": "shadow-sync-nightly", "service": "gui/501/local.sd.shadow-sync-nightly", "state": "idle", "last_exit": 0,
       "revision": "r1", "capabilities": {"retry": {"allowed": True, "reason": "", "label": "Run now"}}, "last_request": None}


class TheGitHubPage(ScreenCase):
    """github.js and issues.js on the stand-in page with the shared commands: Hide, Open | Hidden and Refresh from
    GitHub (sd:6175, sd:6701, pack sd:6702).
    The stand-in server keeps the hidden keys a view POST writes and answers each read with them."""

    def run_page(self, body, *, issues_rows=None, intake_rows=None, sync=None, states=("idle",), store=None, synced=None,
                 categories=(), refuse=None):
        doc = {"issues": issues_rows if issues_rows is not None else [
                   {"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-8", "key": "jira:EXAMPLE-8", "title": "Fix the widget",
                    "reason": "filed", "url": None, "state": None, "hidden": False},
                   {"repo": "anvil", "tracker": "GitHub", "ref": "#12", "key": "github:example/project#12", "title": "Crash on start",
                    "reason": "assigned", "url": None, "state": "open", "hidden": False}],
               "issues_error": "", "github_error": "",
               "intake": intake_rows if intake_rows is not None else [
                   {"repo": "anvil", "repo_path": "/home/example/repos/acme/anvil", "ref": "#21", "key": "github:example/project#21",
                    "title": "Docs typo", "author": "octocat", "url": None, "hidden": False}],
               "intake_error": "", "store": store or {"available": True, "reason": ""}, "sync": sync or JOB, "synced": synced,
               "categories": list(categories)}
        # pack sd:7708: the stand-in keeps each row's category and the category list as the view store does.
        # pack sd:7787: /api/items files sd:9NN for issue #NN, or refuses a ref `refuse` names with its reason (400, as the
        # server answers a ref an item already carries); the next read leaves a filed issue out of intake.
        # A row the doc hands over hidden starts in HID, so an Unhide shows it on the next read (pack sd:7787).
        answer = """(() => { const DOC = %s, STATES = %s, CAT = {}, REFUSE = %s, FILED = new Set(); let reads = 0;
  const HID = new Set([...DOC.issues, ...DOC.intake].filter(r => r.hidden).map(r => r.key));
  return (path, body) => {
    if (path === '/api/items') { if (REFUSE[body.ref]) return [400, { error: REFUSE[body.ref] }];
      FILED.add(body.ref); return [201, { item: { id: 900 + Number(body.ref.split('#')[1]) } }]; }
    if (path === '/api/github/issues/view' && 'category' in body) { CAT[body.key] = body.category; return [200, { key: body.key, category: body.category }]; }
    if (path === '/api/github/issues/categories') {
      DOC.categories = body.rename ? DOC.categories.map(n => n === body.rename ? body.to : n) : body.categories.map(n => n.trim());
      if (body.rename) DOC.issues.forEach(r => { if ((r.key in CAT ? CAT[r.key] : r.category) === body.rename) CAT[r.key] = body.to; });
      return [200, { categories: DOC.categories, moved: 0 }]; }
    if (path === '/api/github/issues/view') { if (body.hidden) HID.add(body.key); else HID.delete(body.key); return [200, { key: body.key, hidden: body.hidden }]; }
    if (path.startsWith('/api/jobs/')) return [200, { request: { status: 'accepted', message: 'kickstarted' } }];
    const state = STATES[Math.min(reads++, STATES.length - 1)];
    const mark = r => ({ ...r, hidden: HID.has(r.key), ...(r.key in CAT ? { category: CAT[r.key] } : {}) });
    return [200, { ...DOC, issues: DOC.issues.map(mark), intake: DOC.intake.filter(r => !FILED.has(r.key)).map(mark), sync: DOC.sync.error ? DOC.sync : { ...DOC.sync, state } }];
  }; })()""" % (json.dumps(doc), json.dumps(list(states)), json.dumps(refuse or {}))
        script = (STAND_IN + MARKUP_JS + "\nconst mk = window.markup.html;\n" + SHELL + COMMANDS_JS
                  + "\nANSWER = " + answer + ";\n"
                  + "window.shell.row = () => null; window.shell.url = q => { location.search = q ? '?' + q : ''; };\n"
                  + GITHUB_JS + ISSUES_JS
                  + "\nvar R = {};\nconst show = id => document.dispatchEvent(new CustomEvent('shell:view', { detail: { id } }));\n"
                  # sd:6701: click('hidden', v) presses Open | Hidden's v, Hidden by default.
                  + "const click = (f, v = 'aside') => (DOC_LISTENERS.click || []).forEach(h => h({ target: { closest: s => s.includes(`[data-f=\"${f}\"]`)"
                    " ? { dataset: { f, v: '1' } } : f === 'hidden' && s.includes('[data-aside=\"hidden\"]') ? { dataset: { aside: f, v } } : null } }));\n"
                  + "const act = (id, obj) => C.run(cmd(id), C.get(obj));\n"
                  + "(async () => { try {\n(DOC_LISTENERS.DOMContentLoaded || []).forEach(f => f());\nawait flush();\n"
                  + body + "\n} catch (e) { OUT.error = String(e) + ' ' + e.stack; } })();\n"
                  + "function run() { OUT.R = R; return JSON.stringify(OUT); }\n")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out

    def test_hide_removes_the_row_and_its_count_and_undo_restores_it(self):
        # pack sd:7753: the Jira row's group opens by a press; with it gone, the repo group opens.
        out = self.run_page(TheCategoryGroups.PRESS + "show('issues'); await flush(); press('none'); await flush();"
                            " R.before = ELS.issues.html; R.n0 = OUT.counts.issues;"
                            " act('jira issue.hide', 'iss:jira:EXAMPLE-8'); await flush(); R.after = ELS.issues.html; R.n1 = OUT.counts.issues;"
                            " R.tally = ELS['issues-tally'].html; R.bar = ELS['issues-filters'].html; R.toast = lastToast().msg;"
                            " lastUndo().undo(); await flush(); press('none'); await flush(); R.back = ELS.issues.html; R.n2 = OUT.counts.issues;")
        r = out["R"]
        self.assertIn("Fix the widget", r["before"])
        self.assertNotIn("Fix the widget", r["after"])
        self.assertIn("Crash on start", r["after"])
        self.assertEqual((r["n0"], r["n1"], r["n2"]), (2, 1, 2))
        self.assertIn("<span>1 open</span>", r["tally"])
        self.assertIn('data-aside="hidden" data-v="aside" aria-pressed="false">Hidden <span class="n">1</span>', r["bar"])
        self.assertIn("Hidden · Jira EXAMPLE-8", r["toast"])
        self.assertIn("Fix the widget", r["back"])
        self.assertEqual([p[:2] for p in out["posts"]], [["/api/github/issues/view", {"key": "jira:EXAMPLE-8", "hidden": True}],
                                                         ["/api/github/issues/view", {"key": "jira:EXAMPLE-8", "hidden": False}]])

    def test_show_hidden_lists_only_the_hidden_rows_with_unhide_and_keeps_it_in_the_url(self):
        out = self.run_page("show('issues'); await flush(); act('jira issue.hide', 'iss:jira:EXAMPLE-8'); await flush();"
                            " click('hidden'); await flush(); R.shown = ELS.issues.html; R.search = location.search;"
                            " R.unhide = C.offWhy(cmd('jira issue.unhide'), C.get('iss:jira:EXAMPLE-8'));"
                            " R.hide = C.offWhy(cmd('jira issue.hide'), C.get('iss:jira:EXAMPLE-8'));"
                            " act('jira issue.unhide', 'iss:jira:EXAMPLE-8'); await flush(); R.after = ELS.issues.html;")
        r = out["R"]
        self.assertIn("Fix the widget", r["shown"])
        self.assertNotIn("Crash on start", r["shown"])
        self.assertEqual(r["search"], "?hidden=1")
        self.assertEqual((r["unhide"], r["hide"]), ("", "already hidden"))
        self.assertNotIn("Fix the widget", r["after"])

    def test_each_bar_is_open_and_hidden_and_an_older_hidden_all_link_lands_on_open(self):
        # Pack sd:7263 (operator 2026-11-02): Your issues and Intake drop All; ?hidden=all, which All kept, lands on Open.
        out = self.run_page("location.search = '?hidden=all'; show('issues'); await flush();"
                            " act('jira issue.hide', 'iss:jira:EXAMPLE-8'); await flush(); act('github issue.hide', 'iss:github:example/project#21');"
                            " await flush(); R.rows = ELS.issues.html; R.bar = ELS['issues-filters'].html;"
                            " show('intake'); await flush(); R.intake = ELS.intake.html; R.ibar = ELS['intake-filters'].html;")
        r, seg = out["R"], r'data-aside="hidden" data-v="(\w+)" aria-pressed="(\w+)">(\w+) <span class="n">(\d+)</span>'
        self.assertNotIn("Fix the widget", r["rows"])
        self.assertIn("Crash on start", r["rows"])
        self.assertNotIn("Docs typo", r["intake"])
        self.assertEqual(re.findall(seg, r["bar"]), [("open", "true", "Open", "1"), ("aside", "false", "Hidden", "1")])
        self.assertEqual(re.findall(seg, r["ibar"]), [("open", "true", "Open", "0"), ("aside", "false", "Hidden", "1")])

    def test_a_page_opened_with_hidden_1_shows_the_hidden_rows(self):
        rows = [{"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-8", "key": "jira:EXAMPLE-8", "title": "Fix the widget",
                 "reason": "filed", "url": None, "state": None, "hidden": True}]
        out = self.run_page("location.search = '?hidden=1'; show('issues'); await flush(); R.shown = ELS.issues.html; R.n = OUT.counts.issues;",
                            issues_rows=rows)
        self.assertIn("Fix the widget", out["R"]["shown"])
        self.assertEqual(out["R"]["n"], 0)

    def test_an_intake_row_hides_and_leaves_the_waiting_count(self):
        out = self.run_page("show('intake'); await flush(); R.n0 = OUT.counts.intake;"
                            " act('github issue.hide', 'iss:github:example/project#21'); await flush();"
                            " R.after = ELS.intake.html; R.n1 = OUT.counts.intake; R.bar = ELS['intake-filters'].html;"
                            " click('hidden'); await flush(); R.shown = ELS.intake.html;")
        r = out["R"]
        self.assertEqual((r["n0"], r["n1"]), (1, 0))
        self.assertNotIn("Docs typo", r["after"])
        self.assertIn('data-aside="hidden" data-v="aside" aria-pressed="false">Hidden <span class="n">1</span>', r["bar"])
        self.assertIn("Docs typo", r["shown"])

    def test_an_unread_view_store_turns_hide_off_with_the_reason(self):
        out = self.run_page("show('issues'); await flush(); R.off = C.offWhy(cmd('jira issue.hide'), C.get('iss:jira:EXAMPLE-8'));"
                            " R.rows = ELS.issues.html;", store={"available": False, "reason": "the view store was not read: locked"})
        self.assertEqual(out["R"]["off"], "Hide is off: the view store was not read: locked")
        self.assertIn("Fix the widget", out["R"]["rows"])

    def test_sync_now_appears_and_runs_the_jobs_retry_command_then_reads_again_when_the_run_ends(self):
        out = self.run_page("show('issues'); await flush(); R.line = (ELS['issues-sync'].html + ELS['issues-said'].html); R.intake = (ELS['intake-sync'].html + ELS['intake-said'].html);"
                            " R.label = cmd('jobs.retry').label; R.cli = cmd('jobs.retry').cli(C.get('job:shadow-sync-nightly'));"
                            " act('jobs.retry', 'job:shadow-sync-nightly'); await flush(); R.toast = lastToast().msg;",
                            states=("idle", "running", "idle"))
        r = out["R"]
        self.assertIn('data-cmd="jobs.retry" data-obj="job:shadow-sync-nightly"', r["line"])
        self.assertIn("<span>Refresh from GitHub</span>", r["line"])
        self.assertIn("runs in the background", r["line"])
        self.assertEqual(r["intake"], r["line"])
        self.assertEqual((r["label"], r["cli"]), ("Refresh from GitHub", "sd jobs retry shadow-sync-nightly"))
        self.assertEqual([p[:2] for p in out["posts"]], [["/api/jobs/shadow-sync-nightly/retry", {"revision": "r1"}]])
        # The first read, then one while the run is going, then the one after it ends; then no more.
        self.assertEqual(out["gets"], ["/api/github/issues"] * 3)
        self.assertIn("Refresh from GitHub started in the background", r["toast"])

    def test_sync_now_is_off_with_the_reason_while_the_job_runs_or_is_not_installed(self):
        # The stand-in's timers run at once; a run that never ends would read forever, so this one holds its poll.
        out = self.run_page("setTimeout = f => 1; show('issues'); await flush(); R.line = (ELS['issues-sync'].html + ELS['issues-said'].html);"
                            " R.off = C.offWhy(cmd('jobs.retry'), C.get('job:shadow-sync-nightly'));",
                            sync={**JOB, "state": "running", "capabilities": {"retry": {"allowed": False, "reason": "the job is already running"}}},
                            states=("running",))
        self.assertEqual(out["R"]["off"], "the job is already running")
        self.assertIn("disabled", out["R"]["line"])
        # pack sd:7675: the button says it runs and turns its icon while the job runs.
        self.assertIn('disabled aria-busy="true"', out["R"]["line"])
        self.assertIn("<span>Refreshing from GitHub</span>", out["R"]["line"])
        self.assertIn("running in the background", out["R"]["line"])
        missing = {"name": "shadow-sync-nightly", "error": "shadow-sync-nightly is not an installed job (x); local-cron-jobs/cron-jobs.sh install shadow-sync-nightly installs it"}
        out = self.run_page("show('issues'); await flush(); R.line = (ELS['issues-sync'].html + ELS['issues-said'].html);"
                            " R.off = C.offWhy(cmd('jobs.retry'), C.get('job:shadow-sync-nightly'));", sync=missing)
        self.assertEqual(out["R"]["off"], missing["error"])
        self.assertIn("Refresh from GitHub is off: shadow-sync-nightly is not an installed job", out["R"]["line"])

    def test_pull_requests_has_refresh_from_github_and_reads_again_when_the_run_ends(self):
        """pack sd:6702: Pull requests shows the same Refresh from GitHub with when GitHub was last read, and the read
        after the run ends reads Pull requests again too."""
        out = self.run_page("OUT.again = 0; window.githubPulls = { again: () => { OUT.again++; } };"
                            " show('pulls'); await flush(); R.line = (ELS['pulls-sync'].html + ELS['pulls-said'].html); R.issues = (ELS['issues-sync'].html + ELS['issues-said'].html);"
                            " act('jobs.retry', 'job:shadow-sync-nightly'); await flush();",
                            states=("idle", "running", "idle"), synced={"last_success_at": "2026-10-19T15:30:00Z"})
        r = out["R"]
        self.assertIn('data-cmd="jobs.retry" data-obj="job:shadow-sync-nightly"', r["line"])
        self.assertIn("<span>Refresh from GitHub</span>", r["line"])
        self.assertIn('GitHub read <time class="rel" datetime="2026-10-19T15:30:00Z">', r["line"])
        self.assertEqual(r["issues"], r["line"])
        self.assertEqual([p[0] for p in out["posts"]], ["/api/jobs/shadow-sync-nightly/retry"])
        self.assertEqual(out["again"], 1)

    def test_github_puts_refresh_in_each_section_heads_tools_and_its_line_under_it(self):
        """Pack sd:7084: a view's actions sit in its section head's tools; the line under the head says what it did. Pack
        sd:7214: the tally is the head's own item, beside .tools, so Refresh ends the row."""
        # pack sd:7682: Your issues and Issue Intake are on the Issues page, which keeps Refresh from GitHub too.
        for page, view, tally in (("github", "pulls", "github-tally"), ("issues", "issues", "issues-tally"), ("issues", "intake", "intake-tally")):
            html = (V2 / f"{page}.html").read_text(encoding="utf-8")
            cats = '<span id="issues-cats"></span>' if view == "issues" else ""
            self.assertIn(f'<p class="tally" id="{tally}"></p>\n          <div class="tools">{cats}<span id="{view}-sync"></span></div>', html)
            self.assertIn(f'<p class="why" id="{view}-said"></p>', html)
        self.assertIn('id="intake-filters"', (V2 / "issues.html").read_text(encoding="utf-8"))


INTAKE_ROWS = [
    {"repo": "anvil", "repo_path": "/home/example/repos/acme/anvil", "ref": f"#{n}", "key": f"github:example/project#{n}",
     "title": title, "author": "octocat", "url": None, "hidden": hidden}
    for n, title, hidden in ((21, "Docs typo", False), (22, "Odd link", True), (23, "Crash in CLI", False))]
REFUSED_23 = "sd:5 (ready) already carries --ref github:example/project#23"


class TheIntakeBulk(ScreenCase):
    """pack sd:7787 on the stand-in page: a checkbox on each Issue Intake row and one in its head for the rows shown, the
    shell's picked set and bulk bar, File as item, Hide and Unhide on the picked rows, and File as item in Details."""

    run_page = TheGitHubPage.run_page

    # The shell's picked set (shell.js commands.pick): a toggle that tells the page with shell:picked. change(target)
    # is the page's change listener seeing a checkbox; shared() lists the bulk commands the bar offers for the picks.
    PICK = ("const PICKED = new Set(); C.pick = id => { PICKED.has(id) ? PICKED.delete(id) : PICKED.add(id);"
            " document.dispatchEvent(new CustomEvent('shell:picked', { detail: [...PICKED] })); };\n"
            "const change = target => (DOC_LISTENERS.change || []).forEach(h => h({ target: { closest: () => null, dataset: {}, ...target } }));\n"
            "const all = on => change({ id: 'intake-all', checked: on });\n"
            "const shared = () => REG.filter(c => c.on === 'github issue' && c.bulk && [...PICKED].every(id => !C.offWhy(c, C.get(id)))).map(c => c.id);\n"
            "const bulk = id => C.runBulk(cmd(id), [...PICKED].map(i => C.get(i)));\n")
    ID = "iss:github:example/project#{}"

    def page(self, body, **kwargs):
        return self.run_page(self.PICK + body, intake_rows=INTAKE_ROWS, **kwargs)

    def test_each_row_has_a_checkbox_that_picks_it_and_opens_no_details(self):
        out = self.page("show('intake'); await flush(); R.rows = ELS.intake.html;"
                        " change({ dataset: { intakePick: 'iss:github:example/project#21' } }); await flush();"
                        " R.one = [...PICKED]; R.drawn = ELS.intake.html; R.head = [ELS['intake-all'].checked, ELS['intake-all'].indeterminate];"
                        " R.details = (ELS.details || {}).html;"
                        " (DOC_LISTENERS.click || []).forEach(h => h({ target: { closest: s => s.includes('label') ? {}"
                        " : s.includes('#intake tr[data-id]') ? { dataset: { id: 'iss:github:example/project#21' } } : null } }));"
                        " R.after = (ELS.details || {}).html;"
                        " change({ dataset: { intakePick: 'iss:github:example/project#21' } }); await flush(); R.none = [...PICKED];")
        r = out["R"]
        for n in (21, 23):
            self.assertIn(f'<td class="sel"><label class="pick"><input type="checkbox" data-intake-pick="{self.ID.format(n)}"'
                          f' aria-label="Select GitHub #{n}"><span></span></label></td>', r["rows"])
        self.assertNotIn(self.ID.format(22), r["rows"])
        self.assertEqual(r["one"], [self.ID.format(21)])
        self.assertIn(f'data-intake-pick="{self.ID.format(21)}" aria-label="Select GitHub #21" checked', r["drawn"])
        self.assertIn(f'<tr data-id="{self.ID.format(21)}" aria-selected="false" data-picked>', r["drawn"])
        self.assertEqual(r["head"], [False, True])
        # A press on the box picks; it opens no Details.
        self.assertEqual((r.get("details"), r.get("after")), (None, None))
        self.assertEqual(r["none"], [])

    def test_the_head_checkbox_picks_the_rows_shown_and_only_those(self):
        out = self.page("show('intake'); await flush(); all(true); await flush(); R.open = [...PICKED];"
                        " R.head = [ELS['intake-all'].checked, ELS['intake-all'].indeterminate, ELS['intake-all'].disabled];"
                        " click('hidden'); await flush(); R.left = [...PICKED]; all(true); await flush(); R.hidden = [...PICKED];"
                        " all(false); await flush(); R.none = [...PICKED];"
                        # A row the table's column filter hides (data-tout) is not shown, so the head box leaves it.
                        " click('hidden', 'open'); await flush();"
                        " document.querySelectorAll = s => s === '#intake tr[data-tout]' ? [{ dataset: { id: 'iss:github:example/project#23' } }] : [];"
                        " all(true); await flush(); R.filtered = [...PICKED];")
        r = out["R"]
        self.assertEqual(r["open"], [self.ID.format(21), self.ID.format(23)])
        self.assertEqual(r["head"], [True, False, False])
        # The Hidden filter shows other rows: a pick no longer shown is dropped, and the head box picks the hidden row alone.
        self.assertEqual(r["left"], [])
        self.assertEqual(r["hidden"], [self.ID.format(22)])
        self.assertEqual(r["none"], [])
        self.assertEqual(r["filtered"], [self.ID.format(21)])
        html = (V2 / "issues.html").read_text(encoding="utf-8")
        self.assertIn('<th class="sel"><label class="pick"><input type="checkbox" id="intake-all" aria-label="Select every intake issue shown">', html)
        self.assertIn('<tbody id="intake"><tr class="empty"><td colspan="6">', html)

    def test_file_as_item_on_the_picked_rows_files_each_and_names_the_one_refused(self):
        out = self.page("show('intake'); await flush(); all(true); await flush(); R.bar = shared();"
                        " bulk('github issue.file'); await flush(); R.toast = lastToast().msg; R.rows = ELS.intake.html;"
                        " R.n = OUT.counts.intake;", refuse={"github:example/project#23": REFUSED_23})
        r = out["R"]
        self.assertEqual(r["bar"], ["github issue.hide", "github issue.file"])
        self.assertEqual([p[:2] for p in out["posts"]], [
            ["/api/items", {"title": "Docs typo", "repo": "/home/example/repos/acme/anvil", "ref": "github:example/project#21"}],
            ["/api/items", {"title": "Crash in CLI", "repo": "/home/example/repos/acme/anvil", "ref": "github:example/project#23"}]])
        # Never a partial batch said as success: the toast counts what landed and names the refusal with its reason.
        self.assertIn("File as item · 1 github issue", r["toast"])
        self.assertIn(f"1 of 2 not changed: GitHub #23 Crash in CLI ({REFUSED_23})", r["toast"])
        self.assertNotIn("Docs typo", r["rows"])
        self.assertIn("Crash in CLI", r["rows"])
        self.assertIn(f"Not filed: {REFUSED_23}", r["rows"])
        self.assertEqual(r["n"], 1)

    def test_a_filing_with_no_answer_is_said_not_known_and_reads_again(self):
        out = self.page("show('intake'); await flush(); R.gets = OUT.gets.length; const was = ANSWER;"
                        " ANSWER = (p, b) => { if (p === '/api/items') throw new TypeError('Load failed'); return was(p, b); };"
                        " act('github issue.file', 'iss:github:example/project#21'); await flush(); R.toast = lastToast().msg;"
                        " R.gets = OUT.gets.length - R.gets;")
        r = out["R"]
        self.assertIn("not known if it filed: Load failed; Read again shows whether an item carries it", r["toast"])
        self.assertEqual(r["gets"], 1)

    def test_hide_on_the_picked_rows_hides_each_and_reads_again_once(self):
        out = self.page("show('intake'); await flush(); all(true); await flush(); R.gets = OUT.gets.length;"
                        " bulk('github issue.hide'); await flush(); R.gets = OUT.gets.length - R.gets;"
                        " R.toast = lastToast().msg; R.rows = ELS.intake.html; R.left = [...PICKED]; R.n = OUT.counts.intake;")
        r = out["R"]
        self.assertIn("Hide · 2 github issues", r["toast"])
        self.assertNotIn("Docs typo", r["rows"])
        self.assertNotIn("Crash in CLI", r["rows"])
        self.assertEqual((r["left"], r["n"]), ([], 0))
        # Two writes, one read after the last of them.
        self.assertEqual(r["gets"], 1)
        self.assertEqual([p[1] for p in out["posts"]], [{"key": "github:example/project#21", "hidden": True},
                                                        {"key": "github:example/project#23", "hidden": True}])

    def test_unhide_on_the_picked_rows_under_hidden_shows_each_again(self):
        out = self.page("show('intake'); await flush(); click('hidden'); await flush();"
                        " all(true); await flush(); R.bar = shared(); R.picked = [...PICKED];"
                        " bulk('github issue.unhide'); await flush(); R.toast = lastToast().msg; R.after = ELS.intake.html;"
                        " click('hidden', 'open'); await flush(); R.open = ELS.intake.html;")
        r = out["R"]
        self.assertEqual(r["bar"], ["github issue.unhide", "github issue.file"])
        self.assertEqual(r["picked"], [self.ID.format(22)])
        self.assertIn("Unhide · 1 github issue", r["toast"])
        self.assertEqual([p[1] for p in out["posts"]], [{"key": "github:example/project#22", "hidden": False}])
        self.assertIn("No intake issue is hidden.", r["after"])
        self.assertIn("Odd link", r["open"])

    def test_details_and_the_row_button_file_through_one_command(self):
        rows = [*INTAKE_ROWS, {"repo": "anvil", "tracker": "GitHub", "ref": "#12", "key": "github:example/project#12",
                               "title": "Crash on start", "reason": "assigned", "url": None, "state": "open", "hidden": False}]
        out = self.run_page(
            self.PICK + "show('intake'); await flush(); const f = cmd('github issue.file');"
            " R.on = C.offWhy(f, C.get('iss:github:example/project#21')); R.mine = C.offWhy(f, C.get('iss:github:example/project#12'));"
            " R.cli = f.cli(C.get('iss:github:example/project#21')); R.inBar = f.bar !== false;"
            " act('github issue.file', 'iss:github:example/project#21'); await flush(); R.toast = lastToast().msg; R.rows = ELS.intake.html;"
            " R.filed = C.offWhy(f, C.get('iss:github:example/project#21'));"
            " (DOC_LISTENERS.click || []).forEach(h => h({ target: { closest: s => s === '#intake button[data-key]'"
            " ? { dataset: { key: 'github:example/project#23' } } : null } })); await flush(); R.refused = lastToast().msg; R.after = ELS.intake.html;",
            intake_rows=INTAKE_ROWS, issues_rows=rows[3:], refuse={"github:example/project#23": REFUSED_23})
        r = out["R"]
        self.assertEqual((r["on"], r["inBar"]), ("", True))
        self.assertEqual(r["mine"], "only an Issue Intake row files an item here")
        self.assertEqual(r["cli"], "cd '/home/example/repos/acme/anvil' && sd task add --ref 'github:example/project#21' 'Docs typo'")
        self.assertEqual(r["toast"], "Filed sd:921 · GitHub #21 Docs typo")
        self.assertNotIn("Docs typo", r["rows"])
        self.assertEqual(r["filed"], "filed as sd:921")
        self.assertEqual(r["refused"], f"GitHub #23 Crash in CLI not changed: {REFUSED_23}")
        self.assertIn(f"Not filed: {REFUSED_23}", r["after"])
        self.assertEqual([p[1]["ref"] for p in out["posts"] if p[0] == "/api/items"],
                         ["github:example/project#21", "github:example/project#23"])

    def test_a_pick_keeps_keyboard_focus_on_its_box_after_the_redraw(self):
        """pack sd:7794: the redraw read document.activeElement after it replaced the rows, when the browser had already
        moved focus to the body, so Space on a box lost focus and the next Tab started from the top of the page."""
        out = self.page(
            "show('intake'); await flush(); R.focused = null;"
            " document.activeElement = { dataset: { intakePick: 'iss:github:example/project#21' } };"
            # As a browser does: replacing the rows drops the focus of the box that held it.
            " const rc = ELS.intake.replaceChildren; ELS.intake.replaceChildren = f => { rc(f); document.activeElement = document.body; };"
            " ELS.intake.querySelectorAll = s => s === '[data-intake-pick]' ? [21, 23].map(n => ({ dataset:"
            " { intakePick: `iss:github:example/project#${n}` }, focus() { R.focused = this.dataset.intakePick; } })) : [];"
            " change({ dataset: { intakePick: 'iss:github:example/project#21' } }); await flush();")
        self.assertEqual(out["R"]["focused"], self.ID.format(21))

    def test_read_again_drops_the_pick_of_a_row_it_no_longer_lists(self):
        """pack sd:7794: a picked Your issues row that Read again no longer listed stayed picked as a 'not listed'
        object, so the bulk bar's Hide ran on it; the reader retires such a pick first, as read.js does."""
        gone = "github:example/project#12"
        out = self.page(
            f"show('issues'); await flush(); C.pick('iss:{gone}'); R.before = [...PICKED];"
            " const was = ANSWER; ANSWER = (p, b) => { const a = was(p, b); if (p !== '/api/github/issues') return a;"
            f" return [a[0], {{ ...a[1], issues: a[1].issues.filter(r => r.key !== '{gone}') }}]; }};"
            f" await window.PAGE_AGAIN.run(); await flush(); R.after = [...PICKED]; R.type = C.get('iss:{gone}').type;")
        r = out["R"]
        self.assertEqual(r["before"], [f"iss:{gone}"])
        self.assertEqual((r["after"], r["type"]), ([], "not listed"))

    def test_a_filed_row_stays_out_only_of_reads_begun_before_its_filing_landed(self):
        """pack sd:7794: a filed row stayed out of every read that still listed it, for as long as the page was open; a
        read begun after the filing landed is the server's answer, so a row it still lists shows again and files again."""
        listed = json.dumps(INTAKE_ROWS)
        out = self.page(
            "show('intake'); await flush(); act('github issue.file', 'iss:github:example/project#21'); await flush();"
            " R.gone = ELS.intake.html;"
            # The page's first read, begun before the filing landed, answers late and still lists the row.
            f" document.dispatchEvent(new CustomEvent('intake:read', {{ detail: {{ intake: {listed}, error: '',"
            " store: { available: true }, read: 1 } })); R.early = ELS.intake.html;"
            " const was = ANSWER; ANSWER = (p, b) => { const a = was(p, b); if (p !== '/api/github/issues') return a;"
            f" return [a[0], {{ ...a[1], intake: {listed} }}]; }};"
            " await window.githubIssues.again(); await flush(); R.late = ELS.intake.html;"
            " R.off = C.offWhy(cmd('github issue.file'), C.get('iss:github:example/project#21'));")
        r = out["R"]
        self.assertNotIn("Docs typo", r["gone"])
        self.assertNotIn("Docs typo", r["early"])
        self.assertIn("Docs typo", r["late"])
        self.assertEqual(r["off"], "")

CATEGORY_ROWS = [
    {"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-8", "key": "jira:EXAMPLE-8", "title": "Fix the widget", "reason": "filed",
     "url": None, "state": None, "hidden": False, "category": "Alerts", "updated_at": "2026-11-01T10:00:00Z"},
    {"repo": "anvil", "tracker": "Jira", "ref": "EXAMPLE-9", "key": "jira:EXAMPLE-9", "title": "Tune the alarm", "reason": "assigned",
     "url": None, "state": None, "hidden": False, "category": None},
    {"repo": "anvil", "tracker": "GitHub", "ref": "#12", "key": "github:example/project#12", "title": "Crash on start",
     "reason": "assigned", "url": None, "state": "open", "hidden": False}]


class TheCategoryGroups(ScreenCase):
    """pack sd:7708 on the stand-in page: Your issues groups its Jira rows by local category, one group open at a time,
    Uncategorized last; Set category, the Details select and the list's commands post, each with Undo."""

    run_page = TheGitHubPage.run_page

    def page(self, body, **kwargs):
        return self.run_page(body, issues_rows=CATEGORY_ROWS, categories=kwargs.pop("categories", ("Alerts", "Ingest")), **kwargs)

    # A press on a group's name, as the page's click listener sees it.
    PRESS = ("const press = key => (DOC_LISTENERS.click || []).forEach(h => h({ target: { closest: s => s === '[data-cat-open]'"
             " ? { dataset: { catOpen: key } } : null } }));\n")
    GROUPS = r'data-cat="([^"]+)" aria-expanded="(\w+)"'

    def test_jira_rows_group_by_category_one_open_at_a_time_and_uncategorized_is_last(self):
        out = self.page(self.PRESS + "show('issues'); await flush(); R.first = ELS.issues.html;"
                        " press('none'); await flush(); R.none = ELS.issues.html; press('none'); await flush(); R.shut = ELS.issues.html;")
        r = out["R"]
        # pack sd:7753: the GitHub row's repo group comes first and opens first.
        self.assertEqual(re.findall(self.GROUPS, r["first"]),
                         [("repo:anvil", "true"), ("cat:Alerts", "false"), ("cat:Ingest", "false"), ("none", "false")])
        self.assertLess(r["first"].index("Crash on start"), r["first"].index('data-cat="cat:Alerts"'))
        self.assertNotIn("Fix the widget", r["first"])
        self.assertNotIn("Tune the alarm", r["first"])
        self.assertEqual(re.findall(self.GROUPS, r["none"]),
                         [("repo:anvil", "false"), ("cat:Alerts", "false"), ("cat:Ingest", "false"), ("none", "true")])
        self.assertIn("Tune the alarm", r["none"])
        self.assertNotIn("Fix the widget", r["none"])
        self.assertNotIn("Crash on start", r["none"])
        self.assertEqual(re.findall(self.GROUPS, r["shut"]),
                         [("repo:anvil", "false"), ("cat:Alerts", "false"), ("cat:Ingest", "false"), ("none", "false")])
        self.assertNotIn("Tune the alarm", r["shut"])
        self.assertNotIn("Crash on start", r["shut"])
        self.assertIn(">1 issue<", r["first"])
        self.assertIn(">0 issues<", r["first"])

    def test_set_category_posts_and_the_row_sits_in_its_group_and_undo_takes_it_out(self):
        out = self.page("show('issues'); await flush(); FIELD_VALUES.category = 'Ingest';"
                        " act('jira issue.category', 'iss:jira:EXAMPLE-9'); await flush(); R.after = ELS.issues.html; R.toast = lastToast().msg;"
                        " lastUndo().undo(); await flush(); R.back = ELS.issues.html;"
                        " R.github = REG.filter(c => c.on === 'github issue').map(c => c.id);")
        r = out["R"]
        self.assertEqual([p[:2] for p in out["posts"]], [["/api/github/issues/view", {"key": "jira:EXAMPLE-9", "category": "Ingest"}],
                                                         ["/api/github/issues/view", {"key": "jira:EXAMPLE-9", "category": None}]])
        self.assertIn(("cat:Ingest", "true"), re.findall(self.GROUPS, r["after"]))
        self.assertIn("Tune the alarm", r["after"])
        self.assertIn("Category Ingest · Jira EXAMPLE-9", r["toast"])
        self.assertIn(("none", "true"), re.findall(self.GROUPS, r["back"]))
        self.assertIn("Tune the alarm", r["back"])
        self.assertNotIn("github issue.category", r["github"])

    def test_the_details_select_picks_or_clears_the_category_with_undo(self):
        change = ("const change = (id, value) => (DOC_LISTENERS.change || []).forEach(h => h({ target: { closest: s => s === '[data-iss-cat]'"
                  " ? { dataset: { issCat: id }, value } : null } }));\n")
        out = self.page(change + "show('issues'); await flush(); window.issues.details('iss:jira:EXAMPLE-8'); R.details = ELS.details.html;"
                        " change('iss:jira:EXAMPLE-8', ''); await flush(); R.toast = lastToast().msg; R.after = ELS.issues.html;"
                        " lastUndo().undo(); await flush(); R.back = ELS.issues.html;")
        r = out["R"]
        self.assertIn('<select class="cap-in" data-iss-cat="iss:jira:EXAMPLE-8" aria-label="Category">', r["details"])
        self.assertIn('<option value="Alerts" selected>Alerts</option>', r["details"])
        self.assertIn('<option value="">None (Uncategorized)</option>', r["details"])
        self.assertEqual([p[:2] for p in out["posts"]], [["/api/github/issues/view", {"key": "jira:EXAMPLE-8", "category": None}],
                                                         ["/api/github/issues/view", {"key": "jira:EXAMPLE-8", "category": "Alerts"}]])
        self.assertIn("Category cleared · Jira EXAMPLE-8", r["toast"])
        self.assertIn(("none", "true"), re.findall(self.GROUPS, r["after"]))
        self.assertIn(("cat:Alerts", "true"), re.findall(self.GROUPS, r["back"]))

    def test_the_category_pickers_list_by_name_ignoring_case_and_none_last(self):
        """pack sd:7752: the Details select and Set category's options sort by name; the groups keep the stored order."""
        out = self.page("show('issues'); await flush(); window.issues.details('iss:jira:EXAMPLE-9'); R.details = ELS.details.html;"
                        " R.rows = ELS.issues.html;"
                        " R.fields = cmd('jira issue.category').fields(C.get('iss:jira:EXAMPLE-9'))[0];",
                        categories=("beta", "Alpha", "gamma"))
        r = out["R"]
        self.assertEqual(re.findall(r'<option value="[^"]*"(?: selected)?>([^<]+)</option>', r["details"]),
                         ["Alpha", "beta", "gamma", "None (Uncategorized)"])
        self.assertEqual([o["label"] for o in r["fields"]["options"]], ["Alpha", "beta", "gamma", "None (Uncategorized)"])
        self.assertEqual(r["fields"]["value"], "Alpha")
        self.assertEqual([g for g, _ in re.findall(self.GROUPS, r["rows"])], ["repo:anvil", "cat:beta", "cat:Alpha", "cat:gamma", "none"])

    def test_github_rows_group_by_repo_first_and_share_the_one_open_group(self):
        """pack sd:7753: one group per repo, by name ignoring case, before the categories; one group open at a time."""
        github = [{"repo": repo, "tracker": "GitHub", "ref": ref, "key": f"github:example/{repo}{ref}", "title": title,
                   "reason": "assigned", "url": None, "state": "open", "hidden": False}
                  for repo, ref, title in (("zinc", "#3", "Zinc breaks"), ("Brass", "#4", "Brass bends"))]
        out = self.run_page(self.PRESS + "show('issues'); await flush(); R.first = ELS.issues.html;"
                            " press('repo:zinc'); await flush(); R.second = ELS.issues.html;",
                            issues_rows=CATEGORY_ROWS[:2] + github, categories=("Alerts",))
        r = out["R"]
        self.assertEqual(re.findall(self.GROUPS, r["first"]),
                         [("repo:Brass", "true"), ("repo:zinc", "false"), ("cat:Alerts", "false"), ("none", "false")])
        self.assertIn("Brass bends", r["first"])
        self.assertNotIn("Zinc breaks", r["first"])
        self.assertNotIn("Fix the widget", r["first"])
        self.assertEqual(re.findall(self.GROUPS, r["second"]),
                         [("repo:Brass", "false"), ("repo:zinc", "true"), ("cat:Alerts", "false"), ("none", "false")])
        self.assertIn("Zinc breaks", r["second"])
        self.assertNotIn("Brass bends", r["second"])
        # A repo group carries no Rename or Remove: its Actions cell is empty.
        self.assertRegex(r["first"], r'data-cat="repo:Brass"[^\n]*(?:\n[^\n]*){0,4}<td class="act"></td></tr>')

    def test_one_repos_rows_from_both_sources_share_one_group_named_by_its_checkout(self):
        """pack sd:7754: a registered checkout's row has its short label as `repo` and the GitHub name as `slug`; a row
        `with_github` adds has owner/name as both. Both rows key on the GitHub name, case ignored, so one repo is one
        group, and the group shows the checkout's short label."""
        rows = [{"repo": "anvil", "repo_path": "/srv/example/anvil", "slug": "Example/Anvil", "tracker": "GitHub",
                 "ref": "#12", "key": "github:example/anvil#12", "title": "Crash on start", "reason": "assigned",
                 "url": None, "state": "open", "hidden": False},
                {"repo": "example/anvil", "repo_path": None, "slug": "example/anvil", "tracker": "GitHub", "ref": "#13",
                 "key": "github:example/anvil#13", "title": "Slow on load", "reason": "assigned", "url": None,
                 "state": "open", "hidden": False}]
        out = self.run_page("show('issues'); await flush(); R.first = ELS.issues.html;", issues_rows=rows, categories=())
        first = out["R"]["first"]
        self.assertEqual(re.findall(self.GROUPS, first), [("repo:example/anvil", "true")])
        self.assertIn('data-cat-open="repo:example/anvil">anvil</button>', first)
        self.assertIn("Crash on start", first)
        self.assertIn("Slow on load", first)

    def test_remove_asks_nothing_leaves_its_issues_uncategorized_and_undo_restores_the_list(self):
        # The repo group stays open; a press opens Uncategorized, which now holds both Jira issues.
        out = self.page(self.PRESS + "show('issues'); await flush(); act('issue category.remove', 'isscat:Alerts'); await flush();"
                        " R.after = ELS.issues.html; R.toast = lastToast().msg; press('none'); await flush(); R.none = ELS.issues.html;"
                        " lastUndo().undo(); await flush(); R.back = ELS.issues.html;")
        r = out["R"]
        self.assertEqual(out["confirms"], [])
        self.assertEqual([p[:2] for p in out["posts"]], [
            ["/api/github/issues/categories", {"categories": ["Ingest"], "before": ["Alerts", "Ingest"]}],
            ["/api/github/issues/categories", {"categories": ["Alerts", "Ingest"], "before": ["Ingest"]}]])
        self.assertEqual(re.findall(self.GROUPS, r["after"]), [("repo:anvil", "true"), ("cat:Ingest", "false"), ("none", "false")])
        self.assertIn("Fix the widget", r["none"])
        self.assertIn("Tune the alarm", r["none"])
        self.assertIn("Category Alerts removed · its issues are uncategorized", r["toast"])
        self.assertEqual([g for g, _ in re.findall(self.GROUPS, r["back"])], ["repo:anvil", "cat:Alerts", "cat:Ingest", "none"])

    def test_new_category_and_rename_post_the_list_the_page_read(self):
        out = self.page("show('issues'); await flush(); R.button = ELS['issues-cats'].html; FIELD_VALUES.name = 'Pages';"
                        " act('issue categories.add', 'isscats'); await flush(); R.added = ELS.issues.html; R.addToast = lastToast().msg;"
                        " FIELD_VALUES.to = 'Paging'; act('issue category.rename', 'isscat:Pages'); await flush(); R.renamed = ELS.issues.html;"
                        " lastUndo().undo(); await flush(); R.back = ELS.issues.html;")
        r = out["R"]
        self.assertIn('data-cmd="issue categories.add" data-obj="isscats"', r["button"])
        self.assertEqual([p[:2] for p in out["posts"]], [
            ["/api/github/issues/categories", {"categories": ["Alerts", "Ingest", "Pages"], "before": ["Alerts", "Ingest"]}],
            ["/api/github/issues/categories", {"rename": "Pages", "to": "Paging", "before": ["Alerts", "Ingest", "Pages"]}],
            ["/api/github/issues/categories", {"rename": "Paging", "to": "Pages", "before": ["Alerts", "Ingest", "Paging"]}]])
        self.assertIn("Category Pages added", r["addToast"])
        self.assertIn('data-cat="cat:Paging"', r["renamed"])
        self.assertIn('data-cat="cat:Pages"', r["back"])

    def test_an_unread_store_says_why_and_groups_nothing(self):
        out = self.page("show('issues'); await flush(); R.rows = ELS.issues.html; R.button = ELS['issues-cats'].html;"
                        " R.off = C.offWhy(cmd('jira issue.category'), C.get('iss:jira:EXAMPLE-8'));",
                        store={"available": False, "reason": "the view store was not read: locked"})
        r = out["R"]
        self.assertIn("Categories were not read: the view store was not read: locked. The Jira issues below are not grouped.", r["rows"])
        self.assertNotIn('data-cat="cat:', r["rows"])
        self.assertNotIn('data-cat="none"', r["rows"])
        self.assertIn("Fix the widget", r["rows"])
        self.assertIn("Tune the alarm", r["rows"])
        self.assertIn("disabled", r["button"])
        self.assertEqual(r["off"], "Categories are off: the view store was not read: locked")


class TheCategoryStore(ScreenCase):
    """pack sd:7708: a Jira row's category is its view row's tag that names a listed category; the list is one view row."""

    def write(self, request):
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE):
            return request(self.connection)

    def read(self):
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE):
            return github_issues(self.connection)

    def jira(self):
        return next(row for row in self.read()["issues"] if row["key"] == "jira:EXAMPLE-8")

    def test_assigning_stores_the_category_and_the_read_carries_it(self):
        self.write(issues.categories({"categories": ["Alerts", " Ingest "], "before": []}))
        out = self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Ingest"}))
        self.assertEqual((out["category"], out["tags"]), ("Ingest", ["Ingest"]))
        found = self.read()
        self.assertEqual(found["categories"], ["Alerts", "Ingest"])
        self.assertEqual([(row["ref"], row.get("category", "absent")) for row in found["issues"]],
                         [("EXAMPLE-8", "Ingest"), ("#12", "absent"), ("#3", "absent")])
        self.assertEqual(writes.views(self.connection)[issues.view_key("jira:EXAMPLE-8")]["tags"], ["Ingest"])

    def test_clearing_leaves_the_row_uncategorized_and_keeps_hidden(self):
        self.write(issues.categories({"categories": ["Alerts"], "before": []}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "hidden": True}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Alerts"}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": None}))
        self.assertEqual((self.jira()["category"], self.jira()["hidden"]), (None, True))

    def test_removing_a_category_leaves_its_issues_uncategorized_and_listing_it_again_restores_them(self):
        self.write(issues.categories({"categories": ["Alerts", "Ingest"], "before": []}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Alerts"}))
        self.write(issues.categories({"categories": ["Ingest"], "before": ["Alerts", "Ingest"]}))
        self.assertEqual((self.jira()["category"], self.read()["categories"]), (None, ["Ingest"]))
        self.write(issues.categories({"categories": ["Alerts", "Ingest"], "before": ["Ingest"]}))
        self.assertEqual(self.jira()["category"], "Alerts")

    def test_a_removed_name_listed_again_after_another_write_starts_empty(self):
        """pack sd:7735: a removed name's tags stayed on its issues for good, so listing it again later, by New category
        or a rename, silently refilled the group. Undo is the next list write only; after another, the tags go."""
        self.write(issues.categories({"categories": ["Alerts", "Ingest"], "before": []}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Alerts"}))
        self.write(issues.categories({"categories": ["Ingest"], "before": ["Alerts", "Ingest"]}))
        self.write(issues.categories({"categories": ["Ingest", "Paging"], "before": ["Ingest"]}))
        self.assertEqual(writes.views(self.connection).get(issues.view_key("jira:EXAMPLE-8"), {}).get("tags", []), [])
        self.write(issues.categories({"categories": ["Ingest", "Paging", "Alerts"], "before": ["Ingest", "Paging"]}))
        self.assertIsNone(self.jira()["category"])

    def test_renaming_to_a_removed_name_moves_only_the_renamed_issues(self):
        """pack sd:7735: a rename to a name removed earlier took that name's old issues along."""
        self.write(issues.categories({"categories": ["Alerts", "Ingest"], "before": []}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Alerts"}))
        self.write(issues.categories({"categories": ["Ingest"], "before": ["Alerts", "Ingest"]}))
        self.write(issues.categories({"rename": "Ingest", "to": "Alerts", "before": ["Ingest"]}))
        self.assertIsNone(self.jira()["category"])

    def test_rename_moves_the_category_and_its_issues_in_one_write(self):
        self.write(issues.categories({"categories": ["Alerts", "Ingest"], "before": []}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Alerts"}))
        out = self.write(issues.categories({"rename": "Alerts", "to": "Paging", "before": ["Alerts", "Ingest"]}))
        self.assertEqual(out, {"categories": ["Paging", "Ingest"], "moved": 1})
        self.assertEqual((self.jira()["category"], self.read()["categories"]), ("Paging", ["Paging", "Ingest"]))

    def test_a_stale_list_an_unlisted_category_or_a_github_row_writes_nothing(self):
        self.write(issues.categories({"categories": ["Alerts"], "before": []}))
        github = next(row["key"] for row in self.read()["issues"] if row["tracker"] == "GitHub")
        before = writes.views(self.connection)
        for request, refused in ((issues.categories({"categories": ["Ingest"], "before": []}), workflow.StaleItem),
                                 (issues.categories({"rename": "Gone", "to": "X", "before": ["Alerts"]}), workflow.StaleItem),
                                 (issues.view({"key": "jira:EXAMPLE-8", "category": "Ingest"}), workflow.StaleItem),
                                 (issues.view({"key": "jira:EXAMPLE-404", "category": "Alerts"}), workflow.StaleItem),
                                 (issues.view({"key": github, "category": "Alerts"}), ValueError)):
            with self.subTest(refused=refused), self.assertRaises(refused):
                self.write(request)
        self.assertEqual(writes.views(self.connection), before)
        for names in ([""], ["a", "A"], ["uncategorized"], ["x" * 65], [f"c{n}" for n in range(17)], "Alerts"):
            with self.subTest(names=names), self.assertRaises(ValueError):
                issues.categories({"categories": names, "before": []})
        for payload in ({"key": "jira:EXAMPLE-8", "category": ""}, {"key": "jira:EXAMPLE-8", "category": 3},
                        {"categories": [], "before": "x"}, {"rename": "Alerts", "to": "", "before": []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                (issues.categories if "key" not in payload else issues.view)(payload)

    def test_an_unread_store_lists_no_category_and_says_why(self):
        self.write(issues.categories({"categories": ["Alerts"], "before": []}))
        self.write(issues.view({"key": "jira:EXAMPLE-8", "category": "Alerts"}))
        with mock.patch.object(writes, "views", side_effect=sqlite3.OperationalError("database is locked")):
            found = self.read()
        self.assertEqual((found["categories"], self.jira_of(found)["category"]), ([], None))
        self.assertEqual(found["store"], {"available": False, "reason": "the view store was not read: database is locked"})

    @staticmethod
    def jira_of(found):
        return next(row for row in found["issues"] if row["key"] == "jira:EXAMPLE-8")


class TheViewRoute(BrowserSession):
    """sd:6175: POST /api/github/issues/view writes a listed row's view state, as /api/contributions/view does; a key the
    issue read no longer lists writes nothing."""

    def test_hide_writes_the_view_state_the_read_carries_back_and_unhide_clears_it(self):
        job = {"name": "shadow-sync-nightly", "error": "not installed here"}
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE), mock.patch.object(issues, "sync_job", return_value=job):
            def read():
                return json.loads(self.request("/api/github/issues", headers={"Cookie": self.cookie})[2])
            self.assertFalse(read()["issues"][0]["hidden"])
            before = self.snapshot()
            for payload in ({"key": "jira:EXAMPLE-8"}, {"key": "jira:EXAMPLE-8", "hidden": "yes"}, {"key": 3, "hidden": True},
                            {"key": "jira:EXAMPLE-8", "hidden": True, "extra": 1}):
                self.assertEqual(self.post("/api/github/issues/view", payload)[0], 400, payload)
            self.assertEqual(self.post("/api/github/issues/view", {"key": "jira:EXAMPLE-8", "hidden": True}, **{"X-SD-CSRF": "0" * 64})[0], 403)
            status, _, refused = self.post("/api/github/issues/view", {"key": "github:example/gone#9", "hidden": True})
            self.assertEqual((status, refused.get("reload")), (409, True))
            self.assertEqual(self.snapshot(), before)
            status, _, out = self.post("/api/github/issues/view", {"key": "jira:EXAMPLE-8", "hidden": True})
            self.assertEqual((status, out), (200, {"key": "jira:EXAMPLE-8", "pinned": False, "hidden": True, "tags": []}))
            self.assertEqual([row["hidden"] for row in read()["issues"]], [True, False, False])
            self.assertEqual(writes.views(self.connection)["issue:jira:example-8"]["hidden"], True)
            status, _, out = self.post("/api/github/issues/view", {"key": "github:example/project#21", "hidden": True})
            self.assertEqual(status, 200, out)
            self.assertEqual([row["hidden"] for row in read()["intake"]], [True, False])
            self.assertEqual(self.post("/api/github/issues/view", {"key": "jira:EXAMPLE-8", "hidden": False})[0], 200)
            self.assertEqual([row["hidden"] for row in read()["issues"]], [False, False, False])

    def test_the_category_routes_write_the_list_and_a_rows_category(self):
        job = {"name": "shadow-sync-nightly", "error": "not installed here"}
        with stub(return_value=FOUND), stub_intake(return_value=INTAKE), mock.patch.object(issues, "sync_job", return_value=job):
            status, _, out = self.post("/api/github/issues/categories", {"categories": ["Alerts"], "before": []})
            self.assertEqual((status, out), (200, {"categories": ["Alerts"], "moved": 0}))
            status, _, refused = self.post("/api/github/issues/categories", {"categories": [], "before": []})
            self.assertEqual((status, refused.get("reload")), (409, True))
            self.assertEqual(self.post("/api/github/issues/categories", {"categories": ["uncategorized"], "before": ["Alerts"]})[0], 400)
            status, _, out = self.post("/api/github/issues/view", {"key": "jira:EXAMPLE-8", "category": "Alerts"})
            self.assertEqual((status, out["category"]), (200, "Alerts"))
            read = json.loads(self.request("/api/github/issues", headers={"Cookie": self.cookie})[2])
            self.assertEqual((read["categories"], read["issues"][0]["category"]), (["Alerts"], "Alerts"))
