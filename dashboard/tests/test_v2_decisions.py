"""Today's Decisions section (sd:3012): a pending decision with one button per option.

What this slice promises: a decision is a `question` note with one `Option: <text>`
line per choice; `/api/decisions` lists each unresolved one, with the item's
revision; a click posts `/api/decisions/answer` with the item and note, which writes a `decision`
note through `workflow.add_item_note` and resolves the question through
`workflow.resolve_item_note`, in one transaction under the revision the page
read, so a stale page writes nothing (409). The ruling reads back from
`workflow.item_state`, the document `sd task show` prints. An old prose
"Decision needed" comment and a resolved question list nothing. A question
with fewer than two options (sd:5064) lists with a text box, and its words
are the ruling, as `sd task note N ... --kind decision --answers <note>` writes.

`decisions.js` runs under JavaScriptCore (osascript), as `test_v2_tasks` runs
`tasks.js`, against the same stand-in page and shell. The browser half -- the
look at 375 px, focus order -- is a manual check recorded on the pull request.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from sd_db import workflow
from sd_dashboard import decisions, v2

from support import NOW, ScreenCase, before_5648
from test_v2_tasks import MARKUP_JS, SHELL, STAND_IN
from test_v2_today import OSASCRIPT
from test_workflow_actions import BrowserSession

V2 = Path(v2.__file__).resolve().parent
PAGE_JS = (V2 / "static" / "decisions.js").read_text(encoding="utf-8") if (V2 / "static" / "decisions.js").exists() else ""

ASKED = "Which store holds quick notes?\nThe page keeps them for the visit today.\nOption: A pack store kind\nOption: Workflow database rows"


def seed(case):
    """One item with a decision, a resolved one, a one-option question and an old prose comment; one done item."""
    item = case.item("Notes quick capture", repo=case.repo())
    ids = {"item": item,
           "asked": case.note(item, ASKED, kind="question"),
           "settled": case.note(item, "Pick a colour\nOption: Red\nOption: Blue", kind="question"),
           "single": case.note(item, "Approve it?\nOption: Approve", kind="question"),
           "free": case.note(item, "Which name fits the quick notes page?", kind="question"),
           "prose": case.note(item, "Decision needed: (a) a store kind, or (b) database rows?", kind="comment")}
    case.connection.execute("UPDATE note SET resolved_at = ? WHERE id = ?", ("2026-09-06T11:00:00Z", ids["settled"]))
    case.connection.commit()
    closed = case.item("Closed work", status="done")
    ids["closed"] = case.note(closed, "Ship it?\nOption: Yes\nOption: No", kind="question")
    return ids


class TheFormat(unittest.TestCase):
    def test_option_lines_are_the_choices_and_the_rest_is_the_question(self):
        self.assertEqual(decisions.parse(ASKED), ("Which store holds quick notes?\nThe page keeps them for the visit today.",
                                                  ["A pack store kind", "Workflow database rows"]))

    def test_only_a_line_that_starts_with_option_counts_and_a_repeat_counts_once(self):
        body = "Keep it?\n  Option:   Keep  \nOption: Drop\nOption: Keep\nOption:\nThe Option: inline is prose\noption: lower"
        self.assertEqual(decisions.parse(body), ("Keep it?\nThe Option: inline is prose\noption: lower", ["Keep", "Drop"]))

    def test_prose_options_are_not_parsed(self):
        self.assertEqual(decisions.parse("Decision needed: (a) one, or (b) the other?")[1], [])


class TheRecommendation(ScreenCase):
    """sd:5306: `recommended` is the index of the option a note recommends, in the three forms live notes use."""

    def recommended(self, body):
        item = self.item("Recommends", repo=self.repo())
        self.note(item, body, kind="question")
        return decisions.document(self.connection)["decisions"][0]["recommended"]

    def test_an_option_that_ends_recommended(self):
        self.assertEqual(self.recommended("Which?\nOption: Leave it\nOption: Map it to its report (Recommended)"), 1)

    def test_an_option_that_starts_recommended(self):
        self.assertEqual(self.recommended("Which?\nOption: Leave it\nOption: Recommended: map it\nOption: Drop it"), 1)
        self.assertEqual(decisions.recommended("", ["(Recommended) Keep it", "Drop it"]), 0)

    def test_a_recommendation_line_that_names_an_option(self):
        self.assertEqual(self.recommended("Which?\nRecommendation: Rows and a cache, as the read is hot.\n"
                                          "Option: Rows\nOption: Rows and a cache"), 1)
        self.assertIsNone(decisions.recommended("Recommendation: something else", ["Rows", "Cache"]))

    def test_a_conditional_two_marks_or_none_recommend_nothing(self):
        for body, options in (("", ["Key on the seed (Recommended only if seed variation is wanted)", "Keep it"]),
                              ("", ["A (Recommended)", "B (Recommended)"]),
                              ("", ["A", "B"]),
                              ("Recommendation: Notes", [])):
            with self.subTest(options=options):
                self.assertIsNone(decisions.recommended(body, options))
        self.assertIsNone(self.recommended("Which?\nOption: A (Recommended only if it is cheap)\nOption: B"))


class TheDocument(ScreenCase):
    def test_every_unresolved_question_on_an_open_item_is_listed_free_text_ones_too(self):
        ids = seed(self)
        doc = decisions.document(self.connection)
        self.assertEqual([row["note"] for row in doc["decisions"]], [ids["asked"], ids["single"], ids["free"]])
        self.assertEqual([row["options"] for row in doc["decisions"][1:]], [["Approve"], []])
        self.assertEqual(doc["decisions"][2]["question"], "Which name fits the quick notes page?")
        row = doc["decisions"][0]
        self.assertEqual((row["item"], row["title"], row["repo"]), (ids["item"], "Notes quick capture", "/repos/system"))
        self.assertEqual(row["question"], "Which store holds quick notes?\nThe page keeps them for the visit today.")
        self.assertEqual(row["options"], ["A pack store kind", "Workflow database rows"])
        self.assertEqual(row["revision"], workflow.item_state(self.connection, ids["item"])["revision"])
        self.assertTrue(row["asked"])

    def test_a_scheduled_occurrence_asks_nothing_until_it_opens(self):
        """sd:5670: Decisions lists questions on the items Tasks lists, so a scheduled occurrence (pack sd:5648) waits
        until it opens. A pack before sd:5648 lists its questions as before."""
        ids = seed(self)
        self.schedule(ids["item"], "2026-09-09")
        self.assertEqual(decisions.document(self.connection, now=NOW)["decisions"], [])
        with before_5648():
            self.assertEqual(len(decisions.document(self.connection, now=NOW)["decisions"]), 3)

    def test_no_decisions_is_an_empty_list(self):
        self.assertEqual(decisions.document(self.connection)["decisions"], [])


class TheAnswer(ScreenCase):
    def setUp(self):
        super().setUp()
        self.ids = seed(self)
        self.revision = workflow.item_state(self.connection, self.ids["item"])["revision"]

    def notes(self):
        return {note["id"]: note for note in workflow.item_state(self.connection, self.ids["item"])["notes"]}

    def test_a_choice_writes_a_decision_note_and_resolves_the_question(self):
        state = decisions.answer(self.connection, self.ids["item"], self.ids["asked"], "Workflow database rows",
                                 expected_revision=self.revision, who="dashboard")
        ruling = state["ruling"]
        self.assertEqual((ruling["kind"], ruling["body"], ruling["session"]),
                         ("decision", f"Ruling on note #{self.ids['asked']}: Workflow database rows", "dashboard"))
        notes = self.notes()
        self.assertIsNotNone(notes[self.ids["asked"]]["resolved_at"])
        self.assertEqual(notes[ruling["id"]]["body"], ruling["body"])
        self.assertEqual(state["revision"], workflow.item_state(self.connection, self.ids["item"])["revision"])
        self.assertEqual([row["note"] for row in decisions.document(self.connection)["decisions"]], [self.ids["single"], self.ids["free"]])

    def test_the_ruling_reads_back_as_sd_task_show_prints_it(self):
        decisions.answer(self.connection, self.ids["item"], self.ids["asked"], "A pack store kind", expected_revision=self.revision, who="dashboard")
        # The pack's `sd task show` prints each note of `item_state` as `note #<id> · <kind>[ (resolved)]: <body>`.
        lines = [f"note #{n['id']} · {n['kind']}: {n['body']}" for n in self.notes().values() if n["kind"] == "decision"]
        self.assertEqual(lines, [f"note #{max(self.notes())} · decision: Ruling on note #{self.ids['asked']}: A pack store kind"])

    def test_a_stale_revision_writes_nothing(self):
        workflow.add_item_note(self.connection, self.ids["item"], body="a later comment", who="cli")
        before = tuple(self.connection.iterdump())
        with self.assertRaises(workflow.StaleItem):
            decisions.answer(self.connection, self.ids["item"], self.ids["asked"], "A pack store kind", expected_revision=self.revision, who="dashboard")
        self.assertEqual(tuple(self.connection.iterdump()), before)

    def test_a_choice_the_note_does_not_offer_and_a_note_that_is_no_decision_are_refused(self):
        before = tuple(self.connection.iterdump())
        for note, option in ((self.ids["asked"], "Something else"), (self.ids["settled"], "Red"),
                             (self.ids["prose"], "(a) a store kind")):
            with self.subTest(note=note), self.assertRaises(workflow.WorkflowError) as refused:
                decisions.answer(self.connection, self.ids["item"], note, option, expected_revision=self.revision, who="dashboard")
            self.assertNotIsInstance(refused.exception, workflow.StaleItem)
        for note in (999999, self.ids["closed"]):
            with self.subTest(note=note), self.assertRaises(workflow.MissingNote):
                decisions.answer(self.connection, self.ids["item"], note, "Yes", expected_revision=self.revision, who="dashboard")
        self.assertEqual(tuple(self.connection.iterdump()), before)


    def test_a_free_text_question_takes_its_words_as_the_ruling_and_resolves(self):
        # sd:5064: decisions.py:66 dropped a question with fewer than two Option: lines and answer() refused it.
        for note, words in ((self.ids["free"], "  Call it Notes  "), (self.ids["single"], "Approve, with a dry run first")):
            with self.subTest(note=note):
                revision = workflow.item_state(self.connection, self.ids["item"])["revision"]
                state = decisions.answer(self.connection, self.ids["item"], note, words, expected_revision=revision, who="dashboard")
                self.assertEqual((state["ruling"]["kind"], state["ruling"]["body"]), ("decision", f"Ruling on note #{note}: {words.strip()}"))
                self.assertIsNotNone(self.notes()[note]["resolved_at"])
        self.assertEqual([row["note"] for row in decisions.document(self.connection)["decisions"]], [self.ids["asked"]])


class TheRulings(ScreenCase):
    """Pack sd:6015: the last week's rulings, one group per session, each with its item, state and question; Reverse
    reopens the question a ruling answered (operator ruling, grill Q36)."""

    def setUp(self):
        super().setUp()
        self.ids = seed(self)

    def rule(self, note, option, session):
        revision = workflow.item_state(self.connection, self.ids["item"])["revision"]
        return decisions.answer(self.connection, self.ids["item"], note, option, expected_revision=revision,
                                who=session)["ruling"]["id"]

    def test_rulings_group_by_session_with_item_state_and_question(self):
        first = self.rule(self.ids["asked"], "A pack store kind", "grill-session")
        second = self.rule(self.ids["free"], "Notes", "grill-session")
        other = self.rule(self.ids["single"], "Approve", "other-session")
        bare = self.note(self.ids["item"], "Operator ruling (grill Q36).", kind="decision", session="grill-session")
        groups = decisions.document(self.connection)["rulings"]
        self.assertEqual({group["session"]: [r["note"] for r in group["rulings"]] for group in groups},
                         {"grill-session": [first, second, bare], "other-session": [other]})
        ruling = next(group for group in groups if group["session"] == "grill-session")["rulings"][0]
        self.assertEqual((ruling["item"], ruling["title"], ruling["state"], ruling["ruling"], ruling["answers"]),
                         (self.ids["item"], "Notes quick capture", "planning", "A pack store kind", self.ids["asked"]))
        self.assertEqual(ruling["question"], "Which store holds quick notes?\nThe page keeps them for the visit today.")
        self.assertEqual(ruling["revision"], workflow.item_state(self.connection, self.ids["item"])["revision"])
        unlinked = next(group for group in groups if group["session"] == "grill-session")["rulings"][2]
        self.assertEqual((unlinked["ruling"], unlinked["answers"], unlinked["question"]),
                         ("Operator ruling (grill Q36).", None, None))

    def test_reverse_notes_the_reversal_and_the_question_waits_again(self):
        ruling = self.rule(self.ids["asked"], "A pack store kind", "grill-session")
        revision = workflow.item_state(self.connection, self.ids["item"])["revision"]
        state = decisions.reverse(self.connection, self.ids["item"], ruling, expected_revision=revision, who="dashboard")
        self.assertEqual(state["reversal"]["body"], f"Reversed ruling #{ruling}: question #{self.ids['asked']} asks again.")
        doc = decisions.document(self.connection)
        self.assertIn(self.ids["asked"], [row["note"] for row in doc["decisions"]])
        [group] = [group for group in doc["rulings"] if group["session"] == "grill-session"]
        self.assertEqual([(r["note"], r["reversed"]) for r in group["rulings"]], [(ruling, True)])

    def test_reverse_refuses_a_stale_page_a_ruling_with_no_question_and_an_open_question(self):
        ruling = self.rule(self.ids["asked"], "A pack store kind", "grill-session")
        bare = self.note(self.ids["item"], "Operator ruling (grill Q36).", kind="decision")
        old = workflow.item_state(self.connection, self.ids["item"])["revision"]
        workflow.add_item_note(self.connection, self.ids["item"], body="a later comment", who="cli")
        before = tuple(self.connection.iterdump())
        with self.assertRaises(workflow.StaleItem):
            decisions.reverse(self.connection, self.ids["item"], ruling, expected_revision=old, who="dashboard")
        revision = workflow.item_state(self.connection, self.ids["item"])["revision"]
        with self.assertRaises(workflow.WorkflowError) as refused:
            decisions.reverse(self.connection, self.ids["item"], bare, expected_revision=revision, who="dashboard")
        self.assertIn("answered no question", str(refused.exception))
        self.connection.execute("UPDATE note SET resolved_at = NULL WHERE id = ?", (self.ids["asked"],))
        self.connection.commit()
        before = tuple(self.connection.iterdump())
        revision = workflow.item_state(self.connection, self.ids["item"])["revision"]
        with self.assertRaises(workflow.WorkflowError) as refused:
            decisions.reverse(self.connection, self.ids["item"], ruling, expected_revision=revision, who="dashboard")
        self.assertIn("is open already", str(refused.exception))
        self.assertEqual(tuple(self.connection.iterdump()), before)


class TheRoutes(BrowserSession):
    def test_reverse_goes_through_the_server_and_a_second_tap_is_stale(self):
        """Pack sd:6015: /api/decisions/reverse with the item revision the page read."""
        ids = seed(self)
        revision = workflow.item_state(self.connection, ids["item"])["revision"]
        ruling = decisions.answer(self.connection, ids["item"], ids["asked"], "A pack store kind",
                                  expected_revision=revision, who="cli")["ruling"]["id"]
        self.connection.commit()
        status, _, body = self.request("/api/decisions", headers={"Cookie": self.cookie})
        row = json.loads(body)["rulings"][0]["rulings"][0]
        payload = {"item": ids["item"], "note": ruling, "revision": row["revision"]}
        status, _, state = self.post("/api/decisions/reverse", payload)
        self.assertEqual(status, 200, state)
        self.assertEqual(self.post("/api/decisions/reverse", payload)[0], 409)
        for bad in ({**payload, "revision": "x"}, {k: v for k, v in payload.items() if k != "note"}, {**payload, "who": 1}):
            with self.subTest(payload=bad):
                self.assertEqual(self.post("/api/decisions/reverse", bad)[0], 400)


    def test_the_list_and_the_answer_go_through_the_server_and_a_second_click_is_stale(self):
        ids = seed(self)
        status, _, body = self.request("/api/decisions", headers={"Cookie": self.cookie})
        self.assertEqual(status, 200)
        row = json.loads(body)["decisions"][0]
        payload = {"item": ids["item"], "note": ids["asked"], "revision": row["revision"], "option": row["options"][1]}
        status, _, state = self.post("/api/decisions/answer", payload)
        self.assertEqual(status, 200, state)
        self.assertEqual(state["ruling"]["body"], f"Ruling on note #{ids['asked']}: Workflow database rows")
        status, _, refused = self.post("/api/decisions/answer", payload)
        self.assertEqual(status, 409)
        self.assertTrue(refused["reload"])

    def test_a_body_without_a_revision_or_option_is_refused_before_the_database_opens(self):
        ids = seed(self)
        good = {"item": ids["item"], "note": ids["asked"], "revision": "a" * 64, "option": "Red"}
        for payload in ({k: v for k, v in good.items() if k != "item"}, {k: v for k, v in good.items() if k != "revision"},
                        {**good, "revision": "x"}, {**good, "option": ""}, {**good, "note": str(ids["asked"])},
                        {**good, "item": 0}, {**good, "note": 2 ** 63}, {**good, "who": "me"},
                        {**good, "option": "x" * (decisions.ANSWER_MAX + 1)}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post("/api/decisions/answer", payload)[0], 400)


def decision_row(**changes):
    return {"note": 7, "item": 3012, "title": "Dashboard v2", "repo": "/repos/system", "asked": "2026-10-08T21:00:00Z",
            "question": "Which shape?\n<b>not markup</b>", "options": ["Option lines", "Free text <i>"],
            "revision": "a" * 64, **changes}


class TheScript(unittest.TestCase):
    """decisions.js against a stand-in page: the rows it draws and the posts a click makes."""

    def run_page(self, body, answer, prefix=""):
        script = (STAND_IN + MARKUP_JS + "\nconst mk = window.markup.html;\n" + SHELL
                  + "\nANSWER = " + answer + ";\n" + prefix + PAGE_JS
                  + "\nvar R = {};\nconst click = (note, i) => ELS.decisions.listeners.click[0]({ target: { closest: s => s === 'button[data-option]'"
                    " ? { dataset: { note: String(note), option: String(i) }, closest: () => null } : null } });\n"
                  + "(async () => { try {\n(DOC_LISTENERS.DOMContentLoaded || []).forEach(f => f());\nawait flush();\n"
                  + body + "\n} catch (e) { OUT.error = String(e) + ' ' + e.stack; } })();\n"
                  + "function run() { OUT.R = R; return JSON.stringify(OUT); }\n")
        result = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", script],
                                capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertIsNone(out["error"])
        return out

    def test_each_decision_is_a_row_with_one_button_per_option_and_values_stay_text(self):
        doc = json.dumps({"decisions": [decision_row()]})
        out = self.run_page("R.rows = ELS.decisions.html; R.tally = ELS['decisions-tally'].html;",
                            f"(path, body) => [200, {doc}]")
        self.assertEqual(out["gets"], ["/api/decisions"])
        rows = out["R"]["rows"]
        self.assertEqual(rows.count('data-option="'), 2)
        self.assertIn('data-note="7" data-option="0"', rows)
        self.assertIn('data-note="7" data-option="1"', rows)
        self.assertIn("Free text &lt;i&gt;", rows)
        self.assertIn("&lt;b&gt;not markup&lt;/b&gt;", rows)
        self.assertIn('href="/tasks?row=3012"', rows)
        self.assertIn("1 waiting", out["R"]["tally"])

    def test_the_recommendation_is_a_line_and_a_filled_button_that_posts_the_option_as_written(self):
        # sd:5306: the server names the recommended option; the page says it under the question and picks it in one press.
        doc = json.dumps({"decisions": [decision_row(options=["Leave as is", "Map it to its report (Recommended)"],
                                                     recommended=1)]})
        out = self.run_page("R.rows = ELS.decisions.html; click(7, 1); await flush();",
                            f"""(path, body) => path === '/api/decisions' ? [200, {doc}]
                                : [200, {{ revision: '{"b" * 64}', ruling: {{ id: 99, kind: 'decision', body: 'x' }} }}]""")
        rows = out["R"]["rows"]
        self.assertIn('<span class="advice">Recommended: Map it to its report</span>', rows)
        self.assertIn('class="btn sm" data-note="7" data-option="1" title="Map it to its report (Recommended)"><span>Choose recommended</span>', rows)
        self.assertLess(rows.index("Choose recommended"), rows.index('class="btn quiet sm" data-note="7" data-option="0"'))
        self.assertIn('class="btn quiet sm" data-note="7" data-option="1"', rows)
        self.assertNotIn('class="tag"', rows)
        self.assertNotIn("(Recommended)</span>", rows)
        self.assertEqual(out["posts"][0][1]["option"], "Map it to its report (Recommended)")

    def test_no_recommendation_says_so_and_draws_no_button(self):
        doc = json.dumps({"decisions": [decision_row(recommended=None)]})
        rows = self.run_page("R.rows = ELS.decisions.html;", f"(path, body) => [200, {doc}]")["R"]["rows"]
        self.assertIn('<span class="advice none">No recommendation</span>', rows)
        self.assertNotIn("Choose recommended", rows)
        self.assertEqual(rows.count('data-option="'), 2)

    def test_review_batch_questions_are_one_line_that_opens_scoring(self):
        # sd:3709: a review batch's questions are counted, not listed; a failed read draws no count.
        doc = json.dumps({"decisions": [decision_row()], "review": 292})
        out = self.run_page("R.line = ELS['decisions-review'].html; R.hidden = ELS['decisions-review'].hidden; R.rows = ELS.decisions.html;",
                            f"(path, body) => [200, {doc}]")
        self.assertIn('<a href="#view=scoring">292 questions wait on Scoring</a>', out["R"]["line"])
        self.assertFalse(out["R"]["hidden"])
        self.assertEqual(out["R"]["rows"].count("<tr data-item="), 1)
        none = self.run_page("R.hidden = ELS['decisions-review'].hidden;", "(path, body) => [200, { decisions: [] }]")
        self.assertTrue(none["R"]["hidden"])
        failed = self.run_page("R.hidden = ELS['decisions-review'].hidden;", "(path, body) => [500, { error: 'locked' }]")
        self.assertTrue(failed["R"]["hidden"])

    def test_no_decisions_says_so_and_a_failed_read_says_why(self):
        empty = self.run_page("R.rows = ELS.decisions.html;", "(path, body) => [200, { decisions: [] }]")
        self.assertIn("No decision waits on you", empty["R"]["rows"])
        failed = self.run_page("R.rows = ELS.decisions.html;", "(path, body) => [500, { error: 'database is locked' }]")
        self.assertIn("Decisions could not be read: database is locked", failed["R"]["rows"])

    def test_a_click_posts_the_option_and_revision_and_the_row_says_what_was_ruled(self):
        doc = json.dumps({"decisions": [decision_row(), decision_row(note=8, options=["Yes", "No"])]})
        out = self.run_page("click(7, 1); await flush(); R.rows = ELS.decisions.html;",
                            f"""(path, body) => path === '/api/decisions' ? [200, {doc}]
                                : [200, {{ revision: '{"b" * 64}', ruling: {{ id: 99, kind: 'decision', body: 'Ruling on note #7: Free text <i>' }} }}]""")
        self.assertEqual(out["posts"], [["/api/decisions/answer", {"item": 3012, "note": 7, "revision": "a" * 64, "option": "Free text <i>"}, 64]])
        rows = out["R"]["rows"]
        self.assertIn("Ruled: Free text &lt;i&gt;", rows)
        self.assertIn("note #99", rows)
        # The other decision on the same item now carries the revision the answer returned, so its click is not stale.
        out = self.run_page("click(7, 1); await flush(); click(8, 0); await flush();",
                            f"""(path, body) => path === '/api/decisions' ? [200, {doc}]
                                : [200, {{ revision: '{"b" * 64}', ruling: {{ id: 99, kind: 'decision', body: 'x' }} }}]""")
        self.assertEqual(out["posts"][1], ["/api/decisions/answer", {"item": 3012, "note": 8, "revision": "b" * 64, "option": "Yes"}, 64])

    def test_a_free_text_question_is_a_text_box_whose_words_post_as_the_option(self):
        # sd:5064: a question with fewer than two Option: lines had no row; now it has a box and an Answer button.
        doc = json.dumps({"decisions": [decision_row(options=[]), decision_row(note=8, options=["Approve"])]})
        submit = ("const submit = (note, value) => ELS.decisions.listeners.submit[0]({ preventDefault() {}, target: { closest: s => s === 'form.answer'"
                  " ? { dataset: { note: String(note) }, elements: { answer: { value } } } : null } });\n")
        out = self.run_page(submit + "R.rows = ELS.decisions.html; submit(7, '  '); await flush(); submit(7, ' Keep both <b> '); await flush(); R.after = ELS.decisions.html;",
                            f"""(path, body) => path === '/api/decisions' ? [200, {doc}]
                                : [200, {{ revision: '{"b" * 64}', ruling: {{ id: 99, kind: 'decision', body: 'x' }} }}]""")
        rows = out["R"]["rows"]
        self.assertEqual(rows.count('<form class="answer" data-note="'), 2)
        self.assertNotIn("data-option=", rows)
        self.assertIn('placeholder="Approve"', rows)
        self.assertIn('<button type="submit" class="btn sm">Answer</button>', rows)
        self.assertEqual(out["posts"], [["/api/decisions/answer", {"item": 3012, "note": 7, "revision": "a" * 64, "option": "Keep both <b>"}, 64]])
        self.assertIn("Ruled: Keep both &lt;b&gt;", out["R"]["after"])

    def test_a_stale_answer_reads_the_list_again_and_says_why(self):
        doc = json.dumps({"decisions": [decision_row()]})
        out = self.run_page("click(7, 0); await flush(); R.note = ELS['decisions-note'].textContent; R.hidden = ELS['decisions-note'].hidden;",
                            f"""(path, body) => path === '/api/decisions' ? [200, {doc}]
                                : [409, {{ error: 'item 3012 changed; reload it before applying this change', reload: true }}]""")
        self.assertEqual(out["gets"], ["/api/decisions", "/api/decisions"])
        self.assertIn("Not recorded: item 3012 changed", out["R"]["note"])
        self.assertFalse(out["R"]["hidden"])

    def test_a_refused_answer_stays_in_its_row(self):
        doc = json.dumps({"decisions": [decision_row()]})
        out = self.run_page("click(7, 0); await flush(); R.rows = ELS.decisions.html;",
                            f"""(path, body) => path === '/api/decisions' ? [200, {doc}]
                                : [400, {{ error: 'note 7 offers no option Option lines' }}]""")
        self.assertEqual(out["gets"], ["/api/decisions"])
        self.assertIn("Not recorded: note 7 offers no option Option lines", out["R"]["rows"])
        self.assertEqual(out["R"]["rows"].count('data-option="'), 2)


def ruling_group(**changes):
    return {"session": "6668b6c0-2dbb-4a22-a0f7-9975ed7dba82", "at": "2026-10-24T21:00:00+00:00", "rulings": [
        {"note": 41, "item": 6015, "title": "Decisions groups <rulings>", "repo": "/repos/pack", "state": "ready",
         "at": "2026-10-24T20:00:00+00:00", "ruling": "Group by session", "answers": 40, "question": "Group how?",
         "reversed": False, "revision": "a" * 64},
        {"note": 43, "item": 6017, "title": "Phone layout", "repo": "/repos/pack", "state": "in_progress",
         "at": "2026-10-24T21:00:00+00:00", "ruling": "Operator ruling (grill Q38).", "answers": None,
         "question": None, "reversed": False, "revision": "b" * 64}], **changes}


class TheRulingsScript(TheScript):
    """Pack sd:6015: each session's rulings as one group under Decisions; Reverse posts in one tap."""

    def test_a_session_is_one_group_with_ruling_item_and_state(self):
        doc = json.dumps({"decisions": [], "rulings": [ruling_group()]})
        out = self.run_page("R.rulings = ELS.rulings.html;", f"(path, body) => [200, {doc}]")
        rulings = out["R"]["rulings"]
        self.assertIn("Session 6668b6c0 · 2 rulings", rulings)
        self.assertIn('aria-label="Rulings of session 6668b6c0"', rulings)
        self.assertIn("Decisions groups &lt;rulings&gt;", rulings)
        self.assertIn("Group how? → <b>Group by session</b>", rulings)
        self.assertIn("in_progress", rulings)
        self.assertEqual(rulings.count('data-reverse="'), 1)
        self.assertIn('data-reverse="41"', rulings)
        self.assertIn("answered no question", rulings)

    def test_reverse_posts_the_ruling_and_reads_again(self):
        doc = json.dumps({"decisions": [], "rulings": [ruling_group()]})
        out = self.run_page(
            "ELS.rulings.listeners.click[0]({ target: { closest: s => s === 'button[data-reverse]'"
            " ? { dataset: { reverse: '41' }, disabled: false } : null } }); await flush(); await flush();",
            f"(path, body) => path === '/api/decisions' ? [200, {doc}] : [200, {{ revision: 'c', reversal: {{ id: 50 }} }}]")
        self.assertEqual([post[:2] for post in out["posts"]],
                         [["/api/decisions/reverse", {"item": 6015, "note": 41, "revision": "a" * 64}]])
        self.assertEqual(out["gets"], ["/api/decisions", "/api/decisions"])


if __name__ == "__main__":
    unittest.main()
