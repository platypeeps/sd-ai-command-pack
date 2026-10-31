"""A repository's policy (sd:6715): the reader, the session-start line and the commit step's convention check."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import io  # noqa: E402
import json  # noqa: E402
import urllib.error  # noqa: E402

import sd_lib  # noqa: E402
import sd_repo_policy  # noqa: E402
import sd_ship_jenkins  # noqa: E402

ORG = {"mode": "org", "issues": "read", "review": {"human": 1},
       "commit_convention": {"types": ["feat", "fix", "doc", "chore"], "aliases": {"docs": "doc"},
                             "body": "required", "footer": r"^Ref: LOG-\d+$"}}


class Policy(unittest.TestCase):

    def test_policy_is_a_declaration_kind_its_reader_checks(self):
        self.assertIn("policy", sd_lib.DECLARATION_KINDS)
        self.assertEqual(sd_lib.declaration_problems("policy", ORG), [])
        self.assertEqual(sd_lib.declaration_problems("policy", {"mode": "org", "push": "auto"}),
                         ["the policy declaration: push is ask in a org repository; auto is for managed ones only "
                          "(note #34749)"])

    def test_no_policy_reads_as_todays_managed_defaults(self):
        self.assertEqual(sd_repo_policy.effective(None), sd_repo_policy.DEFAULTS)
        self.assertEqual(sd_repo_policy.summary(None), "")

    def test_an_org_repository_asks_for_every_act_it_leaves_out(self):
        held = sd_repo_policy.effective({"mode": "org"})
        self.assertEqual([held[act] for act in sd_repo_policy.ACTS], ["ask", "ask", "ask"])
        self.assertEqual(held["commit_convention"]["line_max"], 72)

    def test_the_session_start_line_names_what_an_agent_may_do(self):
        self.assertEqual(sd_repo_policy.summary(ORG),
                         "Repository policy (sd-db repo declare . policy): mode=org, commit=ask, push=ask, pr=ask, "
                         r"merge=squash, issues=read, review=human(1), types=feat|fix|doc|chore, aliases=docs->doc, "
                         r"body=required, footer=^Ref: LOG-\d+$, title<=63, lines<=72")

    def test_an_alias_is_rewritten_before_the_commit(self):
        message = "docs: say how\n\nThe body.\n\nRef: LOG-12\n"
        self.assertEqual(sd_repo_policy.check_message(message, ORG["commit_convention"]),
                         "doc: say how\n\nThe body.\n\nRef: LOG-12\n")

    def test_alias_rewrite_then_footer_missing_refuses_before_commit(self):
        """Design § Failure table: the rewrite yields a message the org's hook still refuses."""
        with self.assertRaises(sd_repo_policy.ConventionRefused) as refused:
            sd_repo_policy.check_message("docs: say how\n\nThe body.\n", ORG["commit_convention"])
        self.assertEqual(str(refused.exception), r"no footer line matches ^Ref: LOG-\d+$")

    def test_each_broken_rule_is_named(self):
        convention = ORG["commit_convention"]
        cases = {"docs say how": "is not a Conventional Commit",
                 "build: x\n\nbody\n\nRef: LOG-1": "type 'build' is not one of",
                 "fix: x\n\nRef: LOG-1": "the convention requires a body",
                 "fix: " + "x" * 70 + "\n\nbody\n\nRef: LOG-1": "over 63",
                 "fix: x\n\n" + "y" * 80 + "\n\nRef: LOG-1": "line 3 is 80 characters, over 72"}
        for message, rule in cases.items():
            with self.subTest(message=message[:30]):
                with self.assertRaises(sd_repo_policy.ConventionRefused) as refused:
                    sd_repo_policy.check_message(message, convention)
                self.assertIn(rule, str(refused.exception))
        fenced = "fix: x\n\nbody\n```\n" + "z" * 90 + "\n```\nhttps://example.com/" + "p" * 80 + "\n\nRef: LOG-1"
        self.assertTrue(sd_repo_policy.check_message(fenced, convention).startswith("fix: x"))

    def test_a_fenced_footer_example_stays_in_its_fence(self):
        """Review advisory note #36094: a fenced `Ref: LOG-1` is an example, not the footer."""
        body = "The body.\n\n```\nRef: LOG-1\n```\n\nCloses: sd:1\n"
        self.assertEqual(sd_repo_policy.footer_last(body, r"^Ref: LOG-\d+$"), body)
        with self.assertRaises(sd_repo_policy.ConventionRefused):
            sd_repo_policy.check_message("fix: x\n\n" + body.replace("\n\nCloses: sd:1", ""), ORG["commit_convention"])

    def test_an_approval_counts_only_from_a_human_on_the_head(self):
        head = "a" * 40
        reviews = [None, {}, {"user": None}, {"user": {"login": 3}, "state": "APPROVED", "commit_id": head},
                   {"user": {"login": "bot[bot]"}, "state": "APPROVED", "commit_id": head},
                   {"user": {"login": "old"}, "state": "APPROVED", "commit_id": "b" * 40},
                   {"user": {"login": "x"}, "state": "APPROVED", "commit_id": head},
                   {"user": {"login": "x"}, "state": "COMMENTED", "commit_id": head},
                   {"user": {"login": "y"}, "state": "APPROVED", "commit_id": head},
                   {"user": {"login": "y"}, "state": "CHANGES_REQUESTED", "commit_id": head}]
        self.assertEqual(sd_repo_policy.approvals(reviews, head), ["x"])

    def test_extreme_values_are_refused_not_raised(self):
        for value in ([], "x", None, 1, {"review": []}, {"review": {"human": True}}, {"review": {"human": 10 ** 30}},
                      {"commit_convention": {"footer": "("}}, {"commit_convention": {"line_max": float("inf")}},
                      {"commit_convention": {"title_max": 0}}, {"links": "x"}, {"ci": []},
                      {"commit_convention": {"aliases": {"a": 1}}}, {"review": {"reviewers": [""]}}):
            with self.subTest(value=value):
                self.assertTrue(sd_repo_policy.problems(value))


JENKINS = {"provider": "jenkins", "url": "http://127.0.0.1:10168", "job": "team/repo/PR-{pr}"}
HEAD = "a" * 40


def answering(*bodies):
    """A urlopen double that answers each poll with the next body; an exception body is raised."""
    calls = []

    def opener(address, timeout):
        calls.append(address)
        body = bodies[min(len(calls), len(bodies)) - 1]
        if isinstance(body, Exception):
            raise body
        return io.BytesIO(json.dumps(body).encode())
    opener.calls = calls
    return opener


def build(result, sha=HEAD, building=False):
    return {"number": 7, "result": result, "building": building, "url": "http://jenkins/7/",
            "actions": [{}, {"lastBuiltRevision": {"SHA1": sha}}]}


class JenkinsWait(unittest.TestCase):
    """sd:6880. `sd-ship merge` waits on the Jenkins job the policy names, bound to the head SHA."""

    def test_the_ci_key_takes_jenkins_with_its_url_and_job(self):
        self.assertEqual(sd_repo_policy.problems({"mode": "org", "ci": JENKINS}), [])
        for ci in ({"provider": "circle", "url": "http://x", "job": "j"}, {"provider": "jenkins", "job": "j"},
                   {"provider": "jenkins", "url": "ftp://x", "job": "j"}, {**JENKINS, "token": "x"}):
            with self.subTest(ci=ci):
                self.assertTrue(sd_repo_policy.problems({"ci": ci}))
        self.assertIn("ci=jenkins", sd_repo_policy.summary({"mode": "org", "ci": JENKINS}))

    def test_the_test_key_takes_a_recipe(self):
        """sd:6882. `test` is setup and teardown commands and the env names the checks need."""
        self.assertEqual(sd_repo_policy.problems({"test": {"setup": "make db", "env": ["DB_URL"], "teardown": "x"}}), [])
        for test in ({"setup": ""}, {"setup": 1}, {"env": "DB_URL"}, {"env": ["1X"]}, {"env": ["A B"]},
                     {"before": "x"}, []):
            with self.subTest(test=test):
                self.assertTrue(sd_repo_policy.problems({"test": test}))

    def test_the_job_path_names_each_folder_and_the_pull_request(self):
        self.assertEqual(sd_ship_jenkins.job_url(JENKINS, 12),
                         "http://127.0.0.1:10168/job/team/job/repo/job/PR-12")

    def test_unreachable_jenkins_is_not_green(self):
        for error in (urllib.error.URLError("Connection refused"), urllib.error.HTTPError("u", 403, "x", {}, None),
                      ValueError("not JSON")):
            with self.subTest(error=error):
                with self.assertRaises(sd_ship_jenkins.Refusal) as caught:
                    sd_ship_jenkins.wait_green(JENKINS, 1, HEAD, wait_seconds=0, opener=answering(error))
                self.assertEqual(caught.exception.workflow["blocker"]["code"], "ci_unreachable")
                self.assertIn("sdm-login", str(caught.exception.workflow))

    def test_a_green_build_counts_only_for_the_head_it_built(self):
        other = {"builds": [build("SUCCESS", sha="b" * 40)]}
        with self.assertRaises(sd_ship_jenkins.Refusal) as caught:
            sd_ship_jenkins.wait_green(JENKINS, 1, HEAD, wait_seconds=0, opener=answering(other))
        self.assertEqual(caught.exception.workflow["blocker"]["code"], "ci_pending")
        green = {"builds": [build("SUCCESS", sha="b" * 40), build("SUCCESS")]}
        self.assertEqual(sd_ship_jenkins.wait_green(JENKINS, 1, HEAD, wait_seconds=0, opener=answering(green))["number"], 7)

    def test_a_sha_that_only_contains_the_head_is_not_the_head(self):
        """Review of build 317: a substring match accepted SHA1 'b' + head + 'c' and any field echoing the head."""
        padded = build("SUCCESS", sha="b" + HEAD + "c")
        echoed = {**build("SUCCESS", sha="c" * 40), "actions": [{"causes": [{"shortDescription": HEAD}]}]}
        pulled = {**build("SUCCESS", sha="c" * 40), "actions": [{"revision": {"hash": "d" * 40, "pullHash": HEAD}}]}
        for builds, found in (([padded], None), ([echoed], None), ([pulled], 7)):
            with self.subTest(builds=builds):
                self.assertEqual((sd_ship_jenkins.head_build(JENKINS, 1, HEAD, answering({"builds": builds}))
                                  or {}).get("number"), found)

    def test_a_running_build_is_polled_until_it_ends(self):
        opener, slept = answering({"builds": [build(None, building=True)]}, {"builds": [build("FAILURE")]}), []
        with self.assertRaises(sd_ship_jenkins.Refusal) as caught:
            sd_ship_jenkins.wait_green(JENKINS, 1, HEAD, wait_seconds=600, opener=opener, sleep=slept.append)
        self.assertEqual(caught.exception.workflow["blocker"]["code"], "ci_not_passing")
        self.assertEqual((len(opener.calls), slept), (2, [sd_ship_jenkins.POLL_SECONDS]))

    def test_a_job_not_indexed_yet_is_pending_not_unreachable(self):
        with self.assertRaises(sd_ship_jenkins.Refusal) as caught:
            sd_ship_jenkins.wait_green(JENKINS, 1, HEAD, wait_seconds=0,
                                       opener=answering(urllib.error.HTTPError("u", 404, "x", {}, None)))
        self.assertEqual(caught.exception.workflow["blocker"]["code"], "ci_pending")


if __name__ == "__main__":
    unittest.main()
