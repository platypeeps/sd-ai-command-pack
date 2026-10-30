"""A repository's policy (sd:6715): the reader, the session-start line and the commit step's convention check."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import sd_lib  # noqa: E402
import sd_repo_policy  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
