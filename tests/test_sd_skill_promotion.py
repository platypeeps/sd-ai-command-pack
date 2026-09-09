"""Skill CLI queues isolated changes; the operator checkout is never mutated."""

import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sd_db import connect, initialise, upsert_repo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import sd_skill  # noqa: E402 - bin is not a package


class SkillRequests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "pack"
        (self.repo / "contrib/sd-candidate").mkdir(parents=True)
        (self.repo / "skills/sd-kept").mkdir(parents=True)
        for path in (
            self.repo / "contrib/sd-candidate/SKILL.md",
            self.repo / "skills/sd-kept/SKILL.md",
        ):
            path.write_text(
                "---\ndescription: Use this fixture.\n---\nA bounded fixture.\n"
            )
        (self.repo / "skills/paths.json").write_text(
            json.dumps({"paths": {"development": {"skills": ["sd-kept"]}}})
        )
        self.git("init", "-b", "main")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("add", ".")
        self.git("commit", "-m", "Fixture\n\nAuthored-with: codex/openai")
        self.dbpath = self.root / "sd.db"
        initialise(self.dbpath)
        self.db = connect(self.dbpath)
        self.addCleanup(self.db.close)
        upsert_repo(self.db, str(self.repo), remote="https://example.invalid/pack.git")
        for replacement in (
            patch.object(sd_skill, "checkout", return_value=self.repo),
            patch.object(
                sd_skill.sd_handoff_rows,
                "connect",
                side_effect=lambda lib, write: connect(self.dbpath, write=write),
            ),
        ):
            replacement.start()
            self.addCleanup(replacement.stop)

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def request(self, verb, name, path=None):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            rc = sd_skill.run(
                argparse.Namespace(
                    verb=verb, name=name, path=path, if_revision=None, json=True
                )
            )
        self.assertEqual(rc, 0)
        return json.loads(output.getvalue())

    def test_promotion_and_demotion_queue_code_review_without_git_writes(self):
        (self.repo / "unrelated.md").write_text("Operator work")
        original = self.git("status", "--porcelain")
        head = self.git("rev-parse", "HEAD")
        promoted = self.request("promote", "sd-candidate", "development")
        demoted = self.request("demote", "sd-kept")
        for value in (promoted, demoted):
            self.assertEqual(len(value["assignments"]), 1)
            self.assertEqual(value["assignments"][0]["scope"], "skill-apply")
            self.assertIn("sd-ship skill", value["item"]["body"])
            self.assertEqual(value["item"]["source_commit"], head)
        self.assertEqual(original, self.git("status", "--porcelain"))
        self.assertEqual(self.git("branch", "--format=%(refname:short)"), "main")
        self.assertTrue((self.repo / "contrib/sd-candidate/SKILL.md").exists())
        self.assertTrue((self.repo / "skills/sd-kept/SKILL.md").exists())

    def test_repeating_same_intent_has_one_assignment(self):
        first = self.request("promote", "sd-candidate", "development")
        second = self.request("promote", "sd-candidate", "development")
        self.assertEqual(first["item"]["id"], second["item"]["id"])
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM assignment").fetchone()[0], 1
        )

    def test_invalid_path_and_changed_source_do_not_queue(self):
        with self.assertRaises(sd_skill.SkillRefusal):
            self.request("promote", "sd-candidate", "absent")
        (self.repo / "contrib/sd-candidate/SKILL.md").write_text("Uncommitted edit")
        with self.assertRaisesRegex(sd_skill.SkillRefusal, "commit"):
            self.request("promote", "sd-candidate", "development")
        self.assertEqual(
            self.db.execute("SELECT count(*) FROM assignment").fetchone()[0], 0
        )

    def test_gateway_contains_no_git_or_github_mutation(self):
        source = (ROOT / "bin/sd_skill.py").read_text()
        for needle in (
            "subprocess",
            "git push",
            "pr create",
            "--method",
            "shutil.move",
        ):
            self.assertNotIn(needle, source)


if __name__ == "__main__":
    unittest.main()
