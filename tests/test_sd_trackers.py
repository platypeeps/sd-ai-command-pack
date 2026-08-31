"""Behaviour tests for `sd-trackers ref`, the resolution path behind `--from`.

Every call is injected. The GitHub half takes the `runner` seam the collector
already uses -- a callable over the argv -- and the Jira half takes the
`transport` seam, so nothing here opens a socket or needs a configured machine.

The properties worth pinning are the ones that would be wrong in a way nobody
notices: that the link is the one the tracker returned rather than one this
code assembled, that a failure prints nothing on stdout (a stray
citation pasted into a work item outlives the session that invented it), that the
Jira half names environment variables and never their values, and that the
three exit codes stay distinct -- 1 means the tracker was asked and the
reference did not resolve (no such issue, or an answer this could not read), 2
means it could not be asked at all, and pasting the difference away would make a
mistyped reference indistinguishable from an unconfigured tracker.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dashboard import github, jira  # noqa: E402 - after the path insert


def load_cli():
    path = REPO_ROOT / "bin" / "sd-trackers"
    loader = importlib.machinery.SourceFileLoader("sd_trackers", str(path))
    spec = importlib.util.spec_from_file_location("sd_trackers", str(path), loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_trackers = load_cli()

ISSUE_PAYLOAD = {
    "number": 7,
    "title": "Retry storm on token refresh",
    "state": "open",
    "html_url": "https://github.com/o/r/issues/7",
    "updated_at": "2026-08-30T11:22:33Z",
    "user": {"login": "someone"},
}

PULL_PAYLOAD = {
    "number": 8,
    "title": "Fix the retry storm",
    "state": "closed",
    # Deliberately a different path segment from the issue above: this is the
    # fact that makes assembling the URL from the reference wrong.
    "html_url": "https://github.com/o/r/pull/8",
    "updated_at": "2026-08-31T09:00:00Z",
    "user": {"login": "someone"},
    "pull_request": {"merged_at": "2026-08-31T09:00:00Z"},
}

JIRA_PAYLOAD = {
    "key": "ABC-45",
    "fields": {
        "summary": "Broker drops the last ack",
        "status": {"statusCategory": {"name": "In Progress"}},
        "updated": "2026-08-28T07:15:00.000+0000",
        "reporter": {"displayName": "A Reporter"},
        "project": {"key": "ABC"},
    },
}

JIRA_ENV = {
    "JIRA_BASE_URL": "https://example.atlassian.net",
    "JIRA_EMAIL": "someone@example.com",
    "JIRA_API_TOKEN": "s3cret-token-value",
}


def gh_runner(payload: dict | None, code: int = 0, err: str = "", auth: int = 0):
    """A `gh` seam: `auth status` answers `auth`, the API call answers the rest."""

    def runner(argv: list[str]) -> tuple[int, str, str]:
        if argv[:3] == ["gh", "auth", "status"]:
            return auth, "", ""
        if payload is None:
            return code, "", err
        return code, json.dumps(payload), err

    return runner


def jira_transport(payload: dict | None, error: str = ""):
    def transport(url: str, headers: dict, body: dict | None):
        return payload, error

    return transport


def run(argv: list[str], **seams) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = sd_trackers.main(argv, out=out, err=err, **seams)
    return code, out.getvalue(), err.getvalue()


class ReferenceParsingTests(unittest.TestCase):
    def test_an_unreadable_reference_names_both_spellings(self) -> None:
        code, out, err = run(["ref", "nonsense"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("gh:owner/repo#123", err)
        self.assertIn("jira:KEY-123", err)

    def test_half_matching_references_are_refused(self) -> None:
        """Anchored patterns: a reference that nearly parses must not part-parse.

        `gh:o/r` with no number and `gh:o/r#12x` both used to be one unanchored
        regex away from resolving issue 12 of a repository nobody named.
        """

        for reference in ("gh:o/r", "gh:o#7", "gh:o/r#", "gh:o/r#12x", "jira:45", "jira:-4"):
            with self.subTest(reference=reference):
                code, out, _ = run(["ref", reference])
                self.assertEqual(code, 2)
                self.assertEqual(out, "")

    def test_a_lowercase_jira_key_is_accepted_and_upper_cased(self) -> None:
        seen: list[str] = []

        def transport(url: str, headers: dict, body: dict | None):
            seen.append(url)
            return JIRA_PAYLOAD, ""

        code, _, _ = run(["ref", "jira:abc-45"], transport=transport, environ=dict(JIRA_ENV))
        self.assertEqual(code, 0)
        self.assertIn("/rest/api/3/issue/ABC-45", seen[0])


class GitHubReferenceTests(unittest.TestCase):
    def test_an_issue_renders_the_citation_block(self) -> None:
        code, out, err = run(["ref", "gh:o/r#7"], runner=gh_runner(ISSUE_PAYLOAD))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            out.splitlines(),
            [
                "- [o/r#7](https://github.com/o/r/issues/7) — Retry storm on token "
                "refresh (open issue, updated 2026-08-30)"
            ],
        )

    def test_the_link_is_the_one_github_returned(self) -> None:
        """The reference says `#8`; the answer says `/pull/8`. The answer wins.

        Assembling `/issues/8` from the reference would produce a link that
        redirects today and is simply wrong the moment GitHub stops redirecting.
        """

        _, out, _ = run(["ref", "gh:o/r#8"], runner=gh_runner(PULL_PAYLOAD))
        self.assertIn("https://github.com/o/r/pull/8", out)
        self.assertNotIn("/issues/8", out)

    def test_a_merged_pull_request_is_not_reported_as_closed(self) -> None:
        _, out, _ = run(["ref", "gh:o/r#8"], runner=gh_runner(PULL_PAYLOAD))
        self.assertIn("(merged pull request, updated 2026-08-31)", out)

    def test_a_closed_pull_request_that_never_merged_stays_closed(self) -> None:
        """`merged_at: null` is the shape GitHub returns for an abandoned PR.

        Reading the presence of `pull_request` as "merged" would report every
        closed pull request as landed -- the same misreading in reverse.
        """

        payload = dict(
            PULL_PAYLOAD,
            pull_request={"merged_at": None, "url": "https://api.github.com/repos/o/r/pulls/8"},
        )
        _, out, _ = run(["ref", "gh:o/r#8"], runner=gh_runner(payload))
        self.assertIn("(closed pull request, updated 2026-08-31)", out)

    def test_an_absent_reference_exits_one_and_prints_nothing(self) -> None:
        runner = gh_runner(None, code=1, err="gh: Not Found (HTTP 404)")
        code, out, err = run(["ref", "gh:o/r#404"], runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("Not Found", err)

    def test_an_unauthenticated_gh_exits_two(self) -> None:
        code, out, err = run(["ref", "gh:o/r#7"], runner=gh_runner(ISSUE_PAYLOAD, auth=1))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(err.strip(), f"gh:o/r#7: {github.NO_AUTH}")

    def test_a_non_json_answer_is_an_error_not_an_empty_citation(self) -> None:
        def runner(argv: list[str]) -> tuple[int, str, str]:
            if argv[:3] == ["gh", "auth", "status"]:
                return 0, "", ""
            return 0, "<html>proxy error</html>", ""

        code, out, err = run(["ref", "gh:o/r#7"], runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("did not return JSON", err)

    def test_an_answer_without_a_link_is_refused(self) -> None:
        payload = {key: value for key, value in ISSUE_PAYLOAD.items() if key != "html_url"}
        code, out, err = run(["ref", "gh:o/r#7"], runner=gh_runner(payload))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("html_url", err)


class JiraReferenceTests(unittest.TestCase):
    def test_a_jira_issue_renders_the_citation_block(self) -> None:
        code, out, err = run(
            ["ref", "jira:ABC-45"],
            transport=jira_transport(JIRA_PAYLOAD),
            environ=dict(JIRA_ENV),
        )
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            out.splitlines(),
            [
                "- [ABC-45](https://example.atlassian.net/browse/ABC-45) — Broker drops "
                "the last ack (open issue, updated 2026-08-28)"
            ],
        )

    def test_a_done_issue_reads_closed(self) -> None:
        payload = json.loads(json.dumps(JIRA_PAYLOAD))
        payload["fields"]["status"]["statusCategory"]["name"] = "Done"
        _, out, _ = run(
            ["ref", "jira:ABC-45"],
            transport=jira_transport(payload),
            environ=dict(JIRA_ENV),
        )
        self.assertIn("(closed issue,", out)

    def test_an_unconfigured_tracker_names_the_variables_and_never_their_values(self) -> None:
        environ = {"JIRA_API_TOKEN": JIRA_ENV["JIRA_API_TOKEN"]}
        code, out, err = run(["ref", "jira:ABC-45"], environ=environ)
        self.assertEqual((code, out), (2, ""))
        self.assertIn(jira.ENV_BASE, err)
        self.assertIn(jira.ENV_EMAIL, err)
        self.assertNotIn(JIRA_ENV["JIRA_API_TOKEN"], err)
        # The one that *is* set must not be named as missing either.
        self.assertNotIn(jira.ENV_TOKEN, err)

    def test_a_tracker_error_exits_one_and_prints_nothing(self) -> None:
        code, out, err = run(
            ["ref", "jira:ABC-45"],
            transport=jira_transport(None, "Jira returned 404 Not Found"),
            environ=dict(JIRA_ENV),
        )
        self.assertEqual((code, out), (1, ""))
        self.assertIn("404", err)

    def test_an_answer_without_a_key_is_refused(self) -> None:
        code, out, err = run(
            ["ref", "jira:ABC-45"],
            transport=jira_transport({"fields": {}}),
            environ=dict(JIRA_ENV),
        )
        self.assertEqual((code, out), (1, ""))
        self.assertIn("without an issue key", err)


class TemplateFitTests(unittest.TestCase):
    def test_the_output_is_the_bullet_and_not_the_heading(self) -> None:
        """The PRD template ships `## References`; printing it again duplicates it."""

        _, out, _ = run(["ref", "gh:o/r#7"], runner=gh_runner(ISSUE_PAYLOAD))
        self.assertNotIn("## References", out)
        template = (REPO_ROOT / "skills/sd-plan/templates/prd.md").read_text(encoding="utf-8")
        self.assertIn("## References", template)
        self.assertTrue(out.startswith("- ["), out)


class SharedStateRuleTests(unittest.TestCase):
    def test_both_jira_readers_use_one_definition_of_closed(self) -> None:
        """`normalize` and `fetch_issue` must not drift on what closed means."""

        fields = {"status": {"statusCategory": {"name": "Done"}}}
        self.assertEqual(jira.state_of(fields), "closed")
        row = jira.normalize(
            {"key": "ABC-1", "fields": dict(fields, summary="x")},
            {"base": "https://example.atlassian.net", "email": "a@b.c"},
            "me",
        )
        self.assertEqual(row["state"], "closed")


if __name__ == "__main__":
    unittest.main()
