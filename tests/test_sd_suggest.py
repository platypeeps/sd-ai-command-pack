"""Criterion 28: a suggestion is a row first, and an issue only when asked.

The criterion's own test is `TheCriterion` below: a proposal row written in
each of `sd_lib.MODES` with `gh` never asked about an issue, a `publish` that
refuses with no destination, a `publish` that files exactly one after the
dedup read the skill requires, and a `sd shadow sync` that writes the
tracker's open work as rows without closing anything.

`gh` here is a recorder on `PATH` rather than `sd_db.testing`'s
`GitHubDouble`: the double routes `/repos`, `/branches`, `/collaborators` and
`/pulls`, and this criterion is about issues, which it does not serve. The
recorder logs one argv per line, so "the fixture saw no close call" and "it
filed exactly one" are both assertions about a list rather than about a mock's
call count.

Two clauses of the criterion are not claimed here, and the omission is
deliberate rather than an oversight: `commands.yaml` belongs to item B, and
the writing manifest belongs to another repository.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A `gh` that records every argv and answers the four routes this criterion
#: reaches. It never leaves the machine, and it exits 0 for `auth status` so
#: `available()` and `gh_authenticated` both see a usable credential.
GH_RECORDER = """#!/usr/bin/env python3
import json, os, sys

argv = sys.argv[1:]
with open(os.environ["GH_CALLS"], "a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")
if argv[:1] == ["auth"]:
    sys.exit(int(os.environ.get("GH_AUTH_CODE", "0")))
if "graphql" in argv:
    print(os.environ.get("GH_SEARCH", "{}"))
    sys.exit(0)
if "--method" in argv:
    print(json.dumps({"html_url": "https://github.com/o/r/issues/9"}))
    sys.exit(0)
code = int(os.environ.get("GH_LIST_CODE", "0"))
if code:
    sys.stderr.write("the list call failed\\n")
    sys.exit(code)
print(os.environ.get("GH_OPEN_ISSUES", "[]"))
"""

#: Two open issues, in the shape `sd_db.shadow_sync.QUERY` asks for. The same
#: page answers all four buckets, so the union by url is what makes the row
#: count two rather than eight -- which is the collector's contract, restated
#: here only because a fixture that returned different nodes per bucket would
#: have tested the fixture instead.
TWO_OPEN_ISSUES = {
    "data": {
        "search": {
            "issueCount": 2,
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "__typename": "Issue",
                    "number": 11,
                    "title": "the installer leaves a stale lock",
                    "url": "https://github.com/o/r/issues/11",
                    "state": "OPEN",
                    "updatedAt": "2026-09-06T10:00:00Z",
                    "author": {"login": "sven"},
                    "repository": {"nameWithOwner": "o/r"},
                },
                {
                    "__typename": "Issue",
                    "number": 12,
                    "title": "the dashboard counts a retired item",
                    "url": "https://github.com/o/r/issues/12",
                    "state": "OPEN",
                    "updatedAt": "2026-09-06T11:00:00Z",
                    "author": {"login": "sven"},
                    "repository": {"nameWithOwner": "o/r"},
                },
            ],
        }
    }
}


def load(name: str, filename: str | None = None):
    """Import a `bin/` module by path -- `bin/` is not a package."""
    path = str(REPO_ROOT / "bin" / (filename or f"{name}.py"))
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

sd_lib = load("sd_lib")
sd_handoff_rows = load("sd_handoff_rows")
sd_suggest = load("sd_suggest")
sd_shadow = load("sd_shadow")

import sd_db  # noqa: E402 - after the path juggling above


class Args:
    """A namespace the verbs read, built per call rather than parsed."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


class SuggestCase(unittest.TestCase):
    """A scratch home with a real database, a checkout, and a recording `gh`."""

    def setUp(self) -> None:
        self._scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self._scratch.cleanup)
        self.home = Path(self._scratch.name).resolve()
        sd_db.initialise(home=self.home)

        self.root = self.home / "checkout"
        item_dir = self.root / sd_lib.WORK_DIR / "an-item"
        item_dir.mkdir(parents=True)
        (item_dir / "prd.md").write_text("# an item\n", encoding="utf-8")
        for args in (["init", "-q"], ["config", "user.email", "t@example.invalid"],
                     ["config", "user.name", "Test"], ["add", "-A"],
                     ["commit", "-qm", "first"]):
            subprocess.run(["git", "-C", str(self.root), *args], check=True,
                           capture_output=True)
        self.root = self.root.resolve()
        self.item_dir = self.root / sd_lib.WORK_DIR / "an-item"

        self.connection = sd_db.connect(sd_db.default_path(self.home), write=True)
        self.addCleanup(self.connection.close)
        sd_db.writes.upsert_repo(self.connection, str(self.root))
        self.item = sd_db.writes.create_item(
            self.connection,
            kind="work",
            title="an item",
            status="in_progress",
            repo=str(self.root),
            source=sd_lib.ITEM_ROW_SOURCE,
            external_id=sd_lib.external_id(self.root, self.item_dir),
        )

        self.calls = self.home / "gh-calls"
        fake_bin = self.home / "fake-bin"
        fake_bin.mkdir()
        gh = fake_bin / "gh"
        gh.write_text(GH_RECORDER, encoding="utf-8")
        gh.chmod(0o755)
        self.environment(
            HOME=str(self.home),
            GH_CALLS=str(self.calls),
            PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        )
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

    def environment(self, **values: str) -> None:
        """Set env vars for this test and put back what was there."""
        for key, value in values.items():
            was = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, v=was: os.environ.__setitem__(k, v) if v
                            else os.environ.pop(k, None))

    def local_block(self, *lines: str) -> None:
        (self.root / sd_lib.LOCAL_FILE_NAME).write_text(
            f"{sd_lib.LOCAL_BLOCK_START}\n" + "\n".join(lines) + f"\n{sd_lib.LOCAL_BLOCK_END}\n",
            encoding="utf-8",
        )

    def run_verb(self, handler, **fields) -> tuple[int, str]:
        """One verb, with its printed lines captured."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = handler(Args(**fields))
        return code, buffer.getvalue()

    def gh_calls(self) -> list[list[str]]:
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def issue_calls(self) -> list[list[str]]:
        """Every recorded call that names an issues endpoint."""
        return [call for call in self.gh_calls()
                if any("issues" in part for part in call)]

    def proposals(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT body FROM note WHERE kind = ? ORDER BY id", (sd_suggest.PROPOSAL,)
        )
        return [row["body"] for row in rows]

    def note_id(self, body: str = "the installer leaves a stale lock") -> int:
        """One recorded proposal, written the way the verb writes it."""
        return sd_db.add_note(self.connection, self.item, sd_suggest.PROPOSAL, body)

    def shadow_rows(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT url, kind, state, title, repo FROM shadow ORDER BY url")
        return [dict(row) for row in rows]


class TheCriterion(SuggestCase):
    """The four clauses, each as one assertion about what actually happened."""

    def test_the_row_is_written_in_every_mode_and_reaches_no_tracker(self):
        """`add` writes locally in `full`, `minimal` and `guest` alike.

        `full` is the checkout with no origin: `remote_permits_full` answers
        yes for a repository there is nobody to expose anything to, so the
        case needs no remote and asks `gh` nothing. The other two are written
        into the local block, which detection may lower but never raise.
        """
        seen = []
        for expected in sd_lib.MODES:
            if expected == "full":
                (self.root / sd_lib.LOCAL_FILE_NAME).unlink(missing_ok=True)
            else:
                self.local_block(f"mode: {expected}")
            code, out = self.run_verb(
                sd_suggest.suggest_add, item="an-item", body=f"friction in {expected}")
            self.assertEqual(0, code)
            self.assertIn(f"in {expected} mode; filed nowhere", out)
            seen.append(expected)

        self.assertEqual(list(sd_lib.MODES), seen)
        self.assertEqual(
            [f"[{mode}] friction in {mode}" for mode in sd_lib.MODES], self.proposals())
        self.assertEqual([], self.issue_calls())

    def test_publish_refuses_without_a_destination(self):
        """No `--to`, no filing -- and the refusal names the reason, not a default."""
        note = self.note_id()
        with self.assertRaises(sd_handoff_rows.RowsRefusal) as raised:
            self.run_verb(sd_suggest.suggest_publish, note=note, to="")
        self.assertIn("--to owner/repo", str(raised.exception))
        self.assertEqual([], self.gh_calls())

    def test_publish_files_exactly_one_issue_after_the_dedup_read(self):
        """One list call, then one POST, in that order and no more of either."""
        note = self.note_id()
        code, out = self.run_verb(sd_suggest.suggest_publish, note=note, to="o/r")

        self.assertEqual(0, code)
        self.assertIn("https://github.com/o/r/issues/9", out)
        calls = self.issue_calls()
        self.assertEqual(2, len(calls), calls)
        self.assertEqual(["api", "repos/o/r/issues?state=open&per_page=100"], calls[0])
        self.assertEqual("--method", calls[1][1])
        self.assertEqual("POST", calls[1][2])
        self.assertEqual(1, sum(1 for call in calls if "--method" in call))

    def test_shadow_sync_writes_the_open_issues_and_closes_nothing(self):
        """Two open issues in, two rows out, and no call that would close one."""
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        code, out = self.run_verb(sd_shadow.shadow_sync, strict=True)

        self.assertEqual(0, code)
        self.assertIn("wrote 2 shadow row(s)", out)
        self.assertEqual(
            ["https://github.com/o/r/issues/11", "https://github.com/o/r/issues/12"],
            [row["url"] for row in self.shadow_rows()])
        self.assertEqual(["open", "open"], [row["state"] for row in self.shadow_rows()])
        # The clause, as a fact about the argv list rather than about a mock:
        # nothing was asked to write, at all, anywhere.
        for call in self.gh_calls():
            self.assertNotIn("--method", call, call)
            self.assertNotIn("close", call, call)

    def test_the_proposal_template_is_gone_from_the_contributed_skill(self):
        """`contrib/sd-propose-skills/` no longer writes a vault note.

        The criterion asks for the note kind to be absent, and the check is
        the whole directory rather than `SKILL.md`: a template moved into a
        sibling file would satisfy a check that read one file and would still
        be the writing path the row replaced.
        """
        directory = REPO_ROOT / "contrib" / "sd-propose-skills"
        found = [path.relative_to(REPO_ROOT).as_posix()
                 for path in sorted(directory.rglob("*"))
                 if path.is_file() and "skill-proposal" in path.read_text(encoding="utf-8")]
        self.assertEqual([], found)


class WhatTheRowRecords(SuggestCase):
    """The body, the mode and the item the row is keyed to."""

    def test_the_mode_is_recorded_on_the_row_and_not_consulted_for_permission(self):
        """`guest` writes the row too; the mode is a fact, not a gate."""
        self.local_block("mode: guest")
        self.run_verb(sd_suggest.suggest_add, item="an-item", body="a thing")
        self.assertEqual(["[guest] a thing"], self.proposals())

    def test_the_row_hangs_off_the_item_the_flag_names(self):
        self.run_verb(sd_suggest.suggest_add, item="an-item", body="a thing")
        row = self.connection.execute(
            "SELECT item FROM note WHERE kind = ?", (sd_suggest.PROPOSAL,)).fetchone()
        self.assertEqual(self.item, row["item"])

    def test_the_write_prints_the_publish_line_that_would_file_it(self):
        """The id is only useful if the run that made it says how to use it."""
        _, out = self.run_verb(sd_suggest.suggest_add, item="an-item", body="a thing")
        note = self.connection.execute(
            "SELECT id FROM note WHERE kind = ?", (sd_suggest.PROPOSAL,)).fetchone()["id"]
        self.assertIn(f"--note {note}", out)


class WhatItRefuses(SuggestCase):
    """The states where writing or filing would be worse than stopping."""

    def test_add_refuses_an_item_directory_that_is_not_there(self):
        with self.assertRaises(sd_handoff_rows.RowsRefusal) as raised:
            self.run_verb(sd_suggest.suggest_add, item="no-such-item", body="a thing")
        self.assertIn("no work item at", str(raised.exception))
        self.assertEqual([], self.proposals())

    def test_add_refuses_an_item_the_database_has_never_seen(self):
        """Missing import refuses capture; running a read-only report cannot repair it."""
        (self.root / sd_lib.WORK_DIR / "unseen").mkdir()
        items_before = list(self.connection.execute("SELECT id FROM item"))
        with self.assertRaises(sd_handoff_rows.RowsRefusal) as raised:
            self.run_verb(sd_suggest.suggest_add, item="unseen", body="a thing")
        self.assertIn("Import the work item before recording a proposal", str(raised.exception))
        self.assertIn("`sd-status` only reports", str(raised.exception))
        self.assertEqual(items_before, list(self.connection.execute("SELECT id FROM item")))
        self.assertEqual([], self.proposals())
        self.assertEqual([], self.issue_calls())

    def test_publish_refuses_a_note_id_that_is_not_a_proposal(self):
        """A followup id is not a suggestion, and filing one would be a surprise."""
        followup = sd_db.add_note(self.connection, self.item, "followup", "not a proposal")
        with self.assertRaises(sd_handoff_rows.RowsRefusal) as raised:
            self.run_verb(sd_suggest.suggest_publish, note=followup, to="o/r")
        self.assertIn(f"no proposal note with id {followup}", str(raised.exception))
        self.assertEqual([], self.issue_calls())


class TheDedupRead(SuggestCase):
    """`skills/sd-suggest/SKILL.md:36` asks for the list call, actually made."""

    def test_a_title_already_open_files_nothing_and_says_where_it_is(self):
        note = self.note_id("the installer leaves a stale lock")
        self.environment(GH_OPEN_ISSUES=json.dumps([
            {"title": "the installer leaves a stale lock",
             "html_url": "https://github.com/o/r/issues/4"}]))

        code, out = self.run_verb(sd_suggest.suggest_publish, note=note, to="o/r")

        self.assertEqual(0, code)
        self.assertIn("already open at https://github.com/o/r/issues/4", out)
        self.assertEqual([], [call for call in self.gh_calls() if "--method" in call])

    def test_the_match_ignores_case_and_surrounding_space(self):
        """Two people naming the same friction do not type the same capitals."""
        note = self.note_id("The Installer Leaves A Stale Lock")
        self.environment(GH_OPEN_ISSUES=json.dumps([
            {"title": "  the installer leaves a stale lock  ",
             "html_url": "https://github.com/o/r/issues/4"}]))
        code, out = self.run_verb(sd_suggest.suggest_publish, note=note, to="o/r")
        self.assertEqual(0, code)
        self.assertIn("already open at", out)

    def test_a_read_that_fails_refuses_rather_than_filing_blind(self):
        """The read exists to prevent a duplicate, so its failure cannot be a
        fall-through: filing anyway is the outcome the read is there to stop."""
        note = self.note_id()
        self.environment(GH_LIST_CODE="1")
        with self.assertRaises(sd_handoff_rows.RowsRefusal) as raised:
            self.run_verb(sd_suggest.suggest_publish, note=note, to="o/r")
        self.assertIn("filing blind", str(raised.exception))
        self.assertEqual([], [call for call in self.gh_calls() if "--method" in call])

    def test_the_title_is_the_first_line_of_the_body(self):
        """A body is a paragraph; an issue title is one line, and a bounded one."""
        note = self.note_id("a short first line\nand a second paragraph")
        self.run_verb(sd_suggest.suggest_publish, note=note, to="o/r")
        posted = [call for call in self.gh_calls() if "--method" in call][0]
        self.assertIn("title=a short first line", posted)
        self.assertIn("body=a short first line\nand a second paragraph", posted)


class TheShadowSync(SuggestCase):
    """The verb over `sd_db.sync_shadow`: what it reports and what it returns."""

    def test_a_held_cursor_is_reported_and_the_rows_are_still_written(self):
        """The collector writes rows on a partial collect; the verb says both."""
        self.environment(GH_AUTH_CODE="1")
        code, out = self.run_verb(sd_shadow.shadow_sync, strict=False)
        self.assertEqual(0, code)
        self.assertIn("cursor held", out)
        self.assertNotIn("cursor moved", out)

    def test_strict_turns_a_held_cursor_into_a_non_zero_exit(self):
        """The same run, for a caller that schedules it and wants to be told."""
        self.environment(GH_AUTH_CODE="1")
        code, _ = self.run_verb(sd_shadow.shadow_sync, strict=True)
        self.assertEqual(1, code)

    def test_a_successful_collect_moves_the_cursor_and_says_from_where(self):
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        _, out = self.run_verb(sd_shadow.shadow_sync, strict=True)
        self.assertIn("cursor moved to cover from", out)

    def test_the_four_buckets_are_all_asked_and_the_union_is_by_url(self):
        """Four searches, one page each, two rows: the union is the collector's."""
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        self.run_verb(sd_shadow.shadow_sync, strict=True)
        searches = [call for call in self.gh_calls() if "graphql" in call]
        self.assertEqual(4, len(searches))
        self.assertEqual(2, len(self.shadow_rows()))

    def test_a_second_run_updates_the_rows_rather_than_duplicating_them(self):
        """`shadow` is keyed by url, and a mirror that grew every run is a log."""
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        self.run_verb(sd_shadow.shadow_sync, strict=True)
        self.run_verb(sd_shadow.shadow_sync, strict=True)
        self.assertEqual(2, len(self.shadow_rows()))


class TheShadowRecoveryArguments(unittest.TestCase):
    """Bad recovery bounds must stop before the library or database is opened."""

    @classmethod
    def setUpClass(cls):
        cls.command = load("sd_shadow_command", "sd")

    def refuse_before_database(self, *options):
        error = io.StringIO()
        with patch.object(sd_handoff_rows, "library") as library, \
                patch.object(sd_handoff_rows, "connect") as connect, \
                contextlib.redirect_stderr(error):
            code = self.command.main(["shadow", "sync", *options])
        self.assertNotEqual(0, code, options)
        self.assertNotIn("Traceback", error.getvalue())
        library.assert_not_called()
        connect.assert_not_called()
        return error.getvalue()

    def test_invalid_or_naive_timestamps_refuse_before_database_access(self):
        for flag in ("--since", "--until"):
            for value in ("2026-09-06", "2026-09-06T10:00:00", "2026-09-06 10:00:00Z",
                          "2026-02-30T10:00:00Z", "2026-09-06T25:00:00Z",
                          "2026-09-06T10:00:00+01:60", "2026-09-06T10:00:00+25:00",
                          "not-a-time"):
                with self.subTest(flag=flag, value=value):
                    self.assertIn("timestamp", self.refuse_before_database(flag, value))

    def test_invalid_limits_refuse_before_database_access(self):
        cases = {
            "--max-requests": ("0", "-1", "1.5", "nan", "inf", "bad"),
            "--max-seconds": ("0", "-1", "nan", "inf", "-inf", "1e999", "bad"),
        }
        for flag, values in cases.items():
            for value in values:
                with self.subTest(flag=flag, value=value):
                    self.assertIn("positive", self.refuse_before_database(f"{flag}={value}"))

    def test_reversed_and_future_windows_refuse_before_database_access(self):
        for options in (
            ("--since", "2026-09-07T00:00:00Z", "--until", "2026-09-06T00:00:00Z"),
            ("--since", "9999-01-01T00:00:00Z"),
            ("--until", "9999-01-01T00:00:00Z"),
        ):
            with self.subTest(options=options):
                self.refuse_before_database(*options)


class TheShadowRecoveryWindow(SuggestCase):
    """The real collector receives explicit controls and preserves its cursor contract."""

    @classmethod
    def setUpClass(cls):
        cls.command = load("sd_shadow_window_command", "sd")

    def command_sync(self, *options):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = self.command.main(["shadow", "sync", *options])
        return code, output.getvalue()

    def test_ordinary_sync_keeps_the_library_defaults(self):
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        with patch.object(sd_db, "sync_shadow", wraps=sd_db.sync_shadow) as sync:
            code, _ = self.command_sync("--strict")
        self.assertEqual(0, code)
        self.assertEqual({}, sync.call_args.kwargs)
        self.assertEqual(2, len(self.shadow_rows()))

    def test_explicit_bounds_and_limits_reach_the_real_library(self):
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        with patch.object(sd_db, "sync_shadow", wraps=sd_db.sync_shadow) as sync:
            code, _ = self.command_sync(
                "--strict", "--since", "2026-09-06T12:00:00.750+02:00",
                "--until", "2026-09-06T11:00:00.250Z",
                "--max-requests", "4", "--max-seconds", "15.5")
        self.assertEqual(0, code)
        self.assertEqual({
            "since": datetime(2026, 9, 6, 10, tzinfo=timezone.utc),
            "now": datetime(2026, 9, 6, 11, tzinfo=timezone.utc),
            "max_requests": 4, "max_seconds": 15.5,
        }, sync.call_args.kwargs)
        self.assertEqual(2, len(self.shadow_rows()))

    def test_one_optional_limit_does_not_override_other_defaults(self):
        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        with patch.object(sd_db, "sync_shadow", wraps=sd_db.sync_shadow) as sync:
            code, _ = self.command_sync("--strict", "--max-requests", "4")
        self.assertEqual(0, code)
        self.assertEqual({"max_requests": 4}, sync.call_args.kwargs)

    def test_saturated_single_second_window_fails_strict_and_holds_cursor(self):
        from sd_db.shadow_sync import read_watermark

        page = json.loads(json.dumps(TWO_OPEN_ISSUES))
        page["data"]["search"]["issueCount"] = 1001
        for node in page["data"]["search"]["nodes"]:
            node["updatedAt"] = "2026-09-06T10:00:00Z"
        self.environment(GH_SEARCH=json.dumps(page))
        code, output = self.command_sync(
            "--strict", "--since", "2026-09-06T10:00:00Z",
            "--until", "2026-09-06T10:00:00Z")
        self.assertEqual(1, code, output)
        self.assertIn("coverage is incomplete", output)
        self.assertIn("cursor held", output)
        self.assertIsNone(read_watermark(self.connection))
        self.assertEqual(2, len(self.shadow_rows()))

    def test_request_exhaustion_fails_strict_and_keeps_partial_rows(self):
        from sd_db.shadow_sync import read_watermark

        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        code, output = self.command_sync("--strict", "--max-requests", "1")
        self.assertEqual(1, code, output)
        self.assertIn("cursor held", output)
        self.assertIsNone(read_watermark(self.connection))
        self.assertEqual(2, len(self.shadow_rows()))
        self.assertEqual(1, len([call for call in self.gh_calls() if "graphql" in call]))

    def test_time_exhaustion_fails_strict_without_moving_cursor(self):
        from sd_db.shadow_sync import read_watermark

        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        code, output = self.command_sync("--strict", "--max-seconds", "0.000000001")
        self.assertEqual(1, code, output)
        self.assertIn("cursor held", output)
        self.assertIsNone(read_watermark(self.connection))
        self.assertEqual([], [call for call in self.gh_calls() if "graphql" in call])

    def test_complete_historical_window_retains_the_later_cursor(self):
        from sd_db.shadow_sync import read_watermark

        self.environment(GH_SEARCH=json.dumps(TWO_OPEN_ISSUES))
        code, _ = self.command_sync("--strict")
        self.assertEqual(0, code)
        previous = read_watermark(self.connection)
        code, output = self.command_sync(
            "--strict", "--since", "2026-09-06T10:00:00Z",
            "--until", "2026-09-06T11:00:00Z")
        self.assertEqual(0, code, output)
        self.assertIn("coverage completed", output)
        self.assertIn("existing cursor retained", output)
        self.assertNotIn("cursor moved", output)
        self.assertEqual(previous, read_watermark(self.connection))

    def test_complete_later_window_does_not_skip_an_uncovered_gap(self):
        from sd_db.shadow_sync import read_watermark

        page = json.loads(json.dumps(TWO_OPEN_ISSUES))
        for node in page["data"]["search"]["nodes"]:
            node["updatedAt"] = "2026-09-06T10:00:00Z"
        self.environment(GH_SEARCH=json.dumps(page))
        code, _ = self.command_sync(
            "--strict", "--since", "2026-09-06T10:00:00Z",
            "--until", "2026-09-06T10:00:00Z")
        self.assertEqual(0, code)
        previous = read_watermark(self.connection)
        for node in page["data"]["search"]["nodes"]:
            node["updatedAt"] = "2026-09-06T11:00:00Z"
        self.environment(GH_SEARCH=json.dumps(page))
        code, output = self.command_sync(
            "--strict", "--since", "2026-09-06T11:00:00Z",
            "--until", "2026-09-06T11:00:00Z")
        self.assertEqual(0, code, output)
        self.assertIn("existing cursor retained", output)
        self.assertEqual(previous, read_watermark(self.connection))


class TheRefusalReachesTheOperator(SuggestCase):
    """`bin/sd` had never caught `RowsRefusal`, and these two verbs raise it.

    The handler is nine lines and the rest of the file has no test that would
    notice if it went away: every other `RowsRefusal` reader is
    `bin/sd-handoff-restore`, a hook that swallows everything by design. So
    the verb is run as `bin/sd` actually runs it, in a subprocess, and what is
    asserted is what an operator sees.
    """

    def run_cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "sd"), *argv],
            cwd=self.root, capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})

    def test_a_bad_item_is_one_sentence_and_not_a_traceback(self):
        done = self.run_cli("suggest", "add", "a thing", "--item", "no-such-item")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertTrue(done.stderr.startswith("sd: "), done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_publish_with_no_destination_refuses_through_the_same_handler(self):
        note = self.note_id()
        done = self.run_cli("suggest", "publish", "--note", str(note))
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("--to owner/repo", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_the_row_the_group_writes_is_the_row_the_library_writes(self):
        """The wiring end to end, so the group is not a parser with no verb."""
        done = self.run_cli("suggest", "add", "a thing", "--item", "an-item")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(["[full] a thing"], self.proposals())


class WhatIsNotAPaletteEntry(unittest.TestCase):
    """Criterion 28 says filing must not be an installed entrypoint."""

    def test_there_is_no_sd_suggest_executable_in_bin(self):
        """A verb under `sd` is reachable; a `bin/sd-suggest` is *installed*.

        `bin/sd_suggest.py` is a module the group imports, and the suffix is
        the distinction the installer reads -- so the check is for the
        suffixless name, which is what would appear on a palette.
        """
        self.assertFalse((REPO_ROOT / "bin" / "sd-suggest").exists())
        self.assertTrue((REPO_ROOT / "bin" / "sd_suggest.py").exists())

    def test_the_skill_discloses_no_bin_path_that_is_not_built(self):
        """The skill may not point a reader at a command that is not there.

        `sd-status`'s `undisclosed-tool` class fired on this file: the tooling
        section named `bin/sd-suggest` in the act of saying it did not exist,
        and a reader who skims a backticked path takes it for something they
        can run. The decision was to stop disclosing it rather than build it,
        so the section now names the verbs that do exist.

        Resolved the way `_tool_rows` resolves, and for the same reason its
        `_tool_candidates` refuses to respell `-` as `_`: `bin/sd_suggest.py`
        is a module `bin/sd` imports, and it does not build `bin/sd-suggest`.
        The two candidates are the name itself and the name with `.py`, which
        is what lets the true path `bin/sd_handoff_rows.py` resolve.
        """
        skill = REPO_ROOT / "skills" / "sd-suggest" / "SKILL.md"
        disclosed = sorted(set(re.findall(
            r"bin/([A-Za-z0-9][A-Za-z0-9_-]*)", skill.read_text(encoding="utf-8"))))
        self.assertIn("sd", disclosed, "the section that names the group moved")
        unbuilt = [
            f"bin/{tool}" for tool in disclosed
            if not any((REPO_ROOT / "bin" / name).is_file()
                       for name in (tool, tool + ".py"))
        ]
        self.assertEqual([], unbuilt, f"{skill.name} names {unbuilt}, not built")

    def test_the_two_verbs_are_reachable_only_through_the_group(self):
        """`sd suggest add` and `sd suggest publish`, and nothing else wires them."""
        text = (REPO_ROOT / "bin" / "sd").read_text(encoding="utf-8")
        self.assertIn("sd_suggest.suggest_add", text)
        self.assertIn("sd_suggest.suggest_publish", text)
        self.assertEqual(1, text.count('groups.add_parser(\n        "suggest"'))


if __name__ == "__main__":
    unittest.main()
