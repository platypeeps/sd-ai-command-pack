"""Skill CLI queues isolated changes; the operator checkout is never mutated."""

import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import re
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

#: Vocabulary that would make `sd skill promote` or `sd skill demote` sound
#: like it writes something. Neither verb touches git or a forge: each queues
#: one assignment and returns. The help and the parser comment are read
#: against this whole family rather than against one phrase, because the
#: regression these guards exist for was never "the words `pull request`
#: appeared" -- it was "the text promised work that nothing does". A phrase
#: guard waved through a comment offering "a merge request against `main`",
#: a help string offering to "merge the move onto a path", and
#: "pull-request" spelled with a hyphen.
_FORGE_CLAIMS = (
    r"pull\s*requests?",
    r"merge\s*requests?",
    r"\bprs?\b",
    r"\bmrs?\b",
    r"\bbranch(?:es)?\b",
    r"\bcommit(?:s|ted|ting)?\b",
    r"\bpush(?:es|ed|ing)?\b",
    r"\bmerg(?:e|es|ed|ing)\b",
    r"\bgit\b",
    r"\bopen(?:s|ed|ing)?\b",
    r"\bfork(?:s|ed|ing)?\b",
    r"\brebas(?:e|es|ed|ing)\b",
    r"\bcherry\s*pick(?:s|ed|ing)?\b",
)

#: What turns a mention of that vocabulary into a denial. "no branch" and
#: "open nothing themselves" are true statements the comment exists to make,
#: so the check reads clause by clause and skips any clause that denies.
_NEGATORS = r"\b(?:no|not|never|nothing|none|neither|nor|without)\b"

#: Clause boundaries. `and` and `but` split as well as punctuation, so a
#: promise cannot shelter under a denial standing next to it.
_CLAUSES = r"[.,;:()]|\band\b|\bbut\b|\bwhile\b"

#: Counting words the help might use, so "queue five code review tasks" is
#: measured against the one assignment a real run produces instead of being
#: read as prose.
_COUNT_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
                "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10}

#: Where a help string says the directory ends up. The key is the directory a
#: real run of the verb names in the brief it queues, so a help string that
#: advertises the other verb's effect does not match its own verb.
_ENDPOINTS = {
    "contrib": r"\b(?:back\s+)?(?:in|on)?to\s+(?:the\s+)?contrib\b",
    "path": r"\b(?:in|on)?to\s+(?:a|an|the|one|its)\s+path\b",
}


def _normalised(text: str) -> str:
    """One lower-case line, so a line break or a hyphen cannot hide a claim."""

    return " ".join(re.sub(r"[-_]+", " ", text).split()).lower()


def _promised(text: str) -> list[str]:
    """Forge vocabulary used as a promise, ignoring clauses that deny it."""

    promises: list[str] = []
    for clause in re.split(_CLAUSES, _normalised(text)):
        if re.search(_NEGATORS, clause):
            continue
        promises.extend(
            pattern for pattern in _FORGE_CLAIMS if re.search(pattern, clause))
    return promises


def _stated_count(text: str) -> int | None:
    """How many things the text says it queues, or None if it names no number."""

    match = re.search(r"\bqueues?\s+(\w+)", _normalised(text))
    if match is None:
        return None
    word = match.group(1)
    return int(word) if word.isdigit() else _COUNT_WORDS.get(word)


def _stated_endpoint(text: str) -> str | None:
    """Where the text says the directory ends up, or None if it is unclear."""

    named = [name for name, pattern in _ENDPOINTS.items()
             if re.search(pattern, _normalised(text))]
    return named[0] if len(named) == 1 else None


class SkillFixture(unittest.TestCase):
    """A pack checkout, a database, and the two skills the verbs act on."""

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


class SkillRequests(SkillFixture):
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


class SkillHelpText(SkillFixture):
    """What `sd skill --help` promises for `promote` and `demote`.

    The queue design landed without its documentation: the command stopped
    opening a pull request and the help text went on offering one, so an
    operator reading `--help` was told to expect a branch that nothing was
    going to write. Correcting the words left the guards pinned to the words,
    and a reviewer's mutation survey found eight restatements of the same
    promise that a `"pull request" not in text` guard waved through: a
    comment offering "a merge request against `main`", a help string offering
    to "merge the move onto a path", a comment claiming a `git mv` and a
    commit in this checkout, "queue five code review tasks", the two help
    strings swapped so each verb advertised the other's effect,
    "pull-request" hyphenated, and deleting the comment outright.

    So these guards pin the claim rather than the phrase. Each verb's help is
    measured against a real run of that verb -- how many assignments it
    queues, and which directory the queued brief says the skill ends up in --
    and both the help and the comment are read for any promise of forge or
    git work, in whatever wording, with denials of that work allowed.
    """

    def skill_verbs(self) -> dict[str, str]:
        """The one-line help argparse prints for each `sd skill` verb."""
        loader = importlib.machinery.SourceFileLoader(
            "sd_cli_under_test", str(ROOT / "bin/sd")
        )
        spec = importlib.util.spec_from_file_location(
            "sd_cli_under_test", str(ROOT / "bin/sd"), loader=loader
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["sd_cli_under_test"] = module
        loader.exec_module(module)
        for action in module.build_parser()._subparsers._group_actions:
            for name, parser in action.choices.items():
                if name != "skill":
                    continue
                verbs = parser._subparsers._group_actions[0]
                return {
                    choice.dest: choice.help or ""
                    for choice in verbs._choices_actions
                }
        raise AssertionError("sd has no `skill` group")

    def queued_move(self, verb: str, name: str, path: str | None = None):
        """What one real run of `verb` queues: how many, and to where."""

        result = self.request(verb, name, path)
        move = re.search(
            r"move (contrib|skills)/\S+ to (contrib|skills)/",
            result["item"]["body"].lower(),
        )
        self.assertIsNotNone(move, "the queued brief no longer names the move")
        assert move is not None
        endpoint = "contrib" if move.group(2) == "contrib" else "path"
        return len(result["assignments"]), endpoint

    def parser_comment(self) -> str:
        """The comment lines inside `bin/sd`'s `sd skill` parser block."""

        source = (ROOT / "bin/sd").read_text()
        start = source.index("trying = skill.add_subparsers")
        end = source.index("sd_skill.register_extra(trying)")
        self.assertLess(start, end, "the `sd skill` block's anchors inverted")
        return " ".join(
            line.strip().lstrip("#").strip()
            for line in source[start:end].splitlines()
            if line.strip().startswith("#")
        )

    def test_help_matches_what_each_verb_really_queues(self) -> None:
        observed = {
            "promote": self.queued_move("promote", "sd-candidate", "development"),
            "demote": self.queued_move("demote", "sd-kept"),
        }
        verbs = self.skill_verbs()
        for verb, (count, endpoint) in observed.items():
            with self.subTest(verb=verb):
                text = _normalised(verbs[verb])
                self.assertIn("queue", text)
                self.assertEqual([], _promised(text))
                self.assertEqual(count, _stated_count(text))
                self.assertEqual(endpoint, _stated_endpoint(text))
                self.assertNotRegex(
                    text, r"\b(?:tasks|assignments|reviews|items)\b")

    def test_the_parser_comment_states_the_queue_and_no_local_write(self) -> None:
        comment = self.parser_comment()
        self.assertTrue(
            comment, "the `sd skill` block has to say what promote and demote do")
        text = _normalised(comment)
        self.assertEqual([], _promised(text))
        self.assertIn("queue", text)
        self.assertIn("checkout", text)
        self.assertRegex(text, _NEGATORS)


if __name__ == "__main__":
    unittest.main()
