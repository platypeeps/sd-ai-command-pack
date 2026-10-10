"""`sd writing import` names the operator to the library that records it."""

import argparse
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import sd_db
import sd_db.writing as writing

ROOT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(ROOT / "bin"), *sys.path]):
    cli = importlib.import_module("sd_writing")


class WritingImport(unittest.TestCase):
    """`writing.import_pieces` takes `who` with no default (sd:749).

    The library call is an autospec mock, so leaving `who` out is the
    library's own TypeError rather than a mock that accepts anything.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve()
        (self.repo / "content").mkdir()
        self.parser = argparse.ArgumentParser()
        cli.register(self.parser.add_subparsers(required=True))
        self.connection = Mock()
        self.connect = Mock(return_value=self.connection)
        for patcher in (
            patch.object(cli.sd_handoff_rows, "library", return_value=sd_db),
            patch.object(cli.sd_handoff_rows, "connect", self.connect),
            patch.object(cli.sd_lib, "repo_root", return_value=self.repo),
            patch.object(cli.getpass, "getuser", return_value="operator"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.imported = self.autospec("import_pieces", {"items": [], "warnings": []})
        self.preview = self.autospec("cutover_preview", {"pieces": []})

    def autospec(self, name, result):
        patcher = patch.object(writing, name, autospec=True, return_value=result)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def call(self, *argv):
        arguments = self.parser.parse_args(["writing", "import", "--json", *argv])
        with redirect_stdout(io.StringIO()) as output:
            code = arguments.handler(arguments)
        self.assertEqual(code, 0)
        return json.loads(output.getvalue())

    def test_applied_import_names_the_operator(self):
        self.assertEqual(self.call("--apply"), {"items": [], "warnings": []})
        self.imported.assert_called_once_with(self.connection, str(self.repo), who="operator")
        self.connect.assert_called_once_with(sd_db, write=True)
        self.preview.assert_not_called()
        self.connection.close.assert_called_once()

    def test_preview_writes_nothing_and_names_no_operator(self):
        self.assertEqual(self.call(), {"pieces": []})
        self.preview.assert_called_once_with(self.connection, str(self.repo))
        self.connect.assert_called_once_with(sd_db, write=False)
        self.imported.assert_not_called()


class WritingPromote(unittest.TestCase):
    """`sd writing promote` hands an idea row to the library that registers it (sd:1994).

    The library call is an autospec mock, so a keyword the library lacks is
    its own TypeError rather than a mock that accepts anything.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve()
        self.parser = argparse.ArgumentParser()
        cli.register(self.parser.add_subparsers(required=True))
        self.connection = Mock()
        self.connect = Mock(return_value=self.connection)
        for patcher in (
            patch.object(cli.sd_handoff_rows, "library", return_value=sd_db),
            patch.object(cli.sd_handoff_rows, "connect", self.connect),
            patch.object(cli.sd_lib, "repo_root", return_value=self.repo),
            patch.object(cli.sd_lib, "stored_repo", side_effect=str),
            patch.object(cli.getpass, "getuser", return_value="operator"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(writing, "promote", autospec=True, return_value={"item": {"piece": "2026/a"}})
        self.promoted = patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, *argv):
        arguments = self.parser.parse_args(["writing", "promote", *argv, "--json"])
        with redirect_stdout(io.StringIO()) as output:
            code = arguments.handler(arguments)
        return code, json.loads(output.getvalue())

    def test_a_writing_checkout_is_the_target(self):
        """The current checkout names the repository, never a flag (R10-D6)."""
        (self.repo / "content").mkdir()
        self.assertEqual((0, {"item": {"piece": "2026/a"}}), self.call("12"))
        self.promoted.assert_called_once_with(self.connection, 12, slug=None, repo=str(self.repo),
                                              who="operator", expected_revision=None)
        self.connect.assert_called_once_with(sd_db, write=True)
        self.connection.close.assert_called_once()

    def test_another_checkout_lets_the_library_pick_the_target(self):
        """With no pieces here, the library picks the one repository that registers them."""
        self.assertEqual(0, self.call("12")[0])
        self.promoted.assert_called_once_with(self.connection, 12, slug=None, repo=None, who="operator",
                                              expected_revision=None)

    def test_promote_passes_slug_and_revision(self):
        (self.repo / "content-parked").mkdir()
        self.call("12", "--slug", "a", "--if-revision", "r1")
        self.promoted.assert_called_once_with(self.connection, 12, slug="a", repo=str(self.repo),
                                              who="operator", expected_revision="r1")

    def test_promote_takes_no_repository_flag(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parser.parse_args(["writing", "promote", "12", "--repo", "~/repos/writing"])

    def test_a_library_refusal_is_a_work_refusal(self):
        self.promoted.side_effect = sd_db.SdDbError("several repositories register pieces; name the target repository")
        with self.assertRaisesRegex(cli.WorkRefusal, "name the target repository; run sd writing promote "
                                                     "from that repository's checkout"):
            self.call("12")
        self.connection.close.assert_called_once()

    def test_a_refusal_in_a_writing_checkout_names_no_other_checkout(self):
        (self.repo / "content").mkdir()
        self.promoted.side_effect = sd_db.SdDbError("item 12 is not an idea")
        with self.assertRaisesRegex(cli.WorkRefusal, r"^item 12 is not an idea$"):
            self.call("12")

    def test_an_older_library_refuses_by_name(self):
        with patch.object(writing, "promote", None):
            with self.assertRaisesRegex(cli.WorkRefusal, "current system/local-sd-db build to promote"):
                self.call("12")
        self.connect.assert_not_called()


class WritingVerifyCheckout(unittest.TestCase):
    """`sd writing verify` refuses where there is nothing to verify (sd:1660)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve()
        self.parser = argparse.ArgumentParser()
        cli.register(self.parser.add_subparsers(required=True))
        self.connection = Mock()
        self.connect = Mock(return_value=self.connection)
        self.root = patch.object(cli.sd_lib, "repo_root", return_value=self.repo)
        for patcher in (
            patch.object(cli.sd_handoff_rows, "library", return_value=sd_db),
            patch.object(cli.sd_handoff_rows, "connect", self.connect),
            self.root,
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(writing, "verify_pieces", autospec=True, return_value={
            "ok": True, "owner": "row", "files": 1, "rows": 1, "differences": []})
        self.verified = patcher.start()
        self.addCleanup(patcher.stop)

    def run_verify(self):
        arguments = self.parser.parse_args(["writing", "verify", "--json"])
        with redirect_stdout(io.StringIO()) as output:
            code = arguments.handler(arguments)
        return code, output.getvalue()

    def test_outside_any_checkout_refuses(self):
        self.root.stop()
        with patch.object(cli.sd_lib, "repo_root", return_value=None):
            with self.assertRaisesRegex(cli.WorkRefusal, "writing Git checkout"):
                self.run_verify()
        self.root.start()
        self.connect.assert_not_called()

    def test_checkout_without_content_refuses(self):
        with self.assertRaisesRegex(cli.WorkRefusal, "no content/ folder.*writing Git checkout"):
            self.run_verify()
        self.connect.assert_not_called()
        self.verified.assert_not_called()

    def test_writing_checkout_verifies(self):
        (self.repo / "content").mkdir()
        code, output = self.run_verify()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["files"], 1)
        self.verified.assert_called_once_with(self.connection, str(self.repo))


class WritingContentCheckout(unittest.TestCase):
    """`list` and `import` refuse where there are no pieces, as `verify` does (sd:1803).

    In a checkout with no content/ folder they printed empty results and
    exited 0, which reads as "this repository has no pieces" rather than
    "you are in the wrong checkout".
    """

    VERBS = (("list", "list_pieces", []), ("import", "cutover_preview", {"pieces": []}),
             ("import --apply", "import_pieces", {"items": [], "warnings": []}))

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name).resolve()
        self.parser = argparse.ArgumentParser()
        cli.register(self.parser.add_subparsers(required=True))
        self.connection = Mock()
        self.connect = Mock(return_value=self.connection)
        for patcher in (
            patch.object(cli.sd_handoff_rows, "library", return_value=sd_db),
            patch.object(cli.sd_handoff_rows, "connect", self.connect),
            patch.object(cli.sd_lib, "repo_root", return_value=self.repo),
            *(patch.object(writing, name, autospec=True, return_value=result)
              for _verb, name, result in self.VERBS),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_verb(self, verb):
        arguments = self.parser.parse_args(["writing", *verb.split(), "--json"])
        with redirect_stdout(io.StringIO()) as output:
            code = arguments.handler(arguments)
        return code, output.getvalue()

    def test_checkout_without_content_refuses_each_verb(self):
        for verb, name, _result in self.VERBS:
            with self.subTest(verb=verb):
                action = verb.split()[0]
                with self.assertRaisesRegex(
                        cli.WorkRefusal, f"no content/ folder, so there is nothing to {action}; "
                                         f"run sd writing {action} from the writing Git checkout"):
                    self.run_verb(verb)
                getattr(writing, name).assert_not_called()
        self.connect.assert_not_called()

    def test_writing_checkout_answers_each_verb(self):
        (self.repo / "content").mkdir()
        for verb, name, result in self.VERBS:
            with self.subTest(verb=verb):
                code, output = self.run_verb(verb)
                self.assertEqual((0, result), (code, json.loads(output)))
                getattr(writing, name).assert_called_once()

    def test_a_parked_only_checkout_still_answers(self):
        """`content-parked` alone counts, as it does for `verify`."""
        (self.repo / "content-parked").mkdir()
        self.assertEqual(0, self.run_verb("list")[0])


class WritingFromWorktree(unittest.TestCase):
    """A linked worktree keys rows to the main checkout and reads its own files (sd:2024)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.main = Path(tmp.name).resolve() / "main"
        self.main.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
        for command in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "seed"],
                        ["worktree", "add", "-q", "-b", "gate", "../linked"]):
            subprocess.run(["git", *command], cwd=self.main, env=env, check=True, capture_output=True)
        self.linked = self.main.parent / "linked"
        self.parser = argparse.ArgumentParser()
        cli.register(self.parser.add_subparsers(required=True))
        self.connection = Mock()
        self.connect = Mock(return_value=self.connection)
        self.checkout = Mock(return_value=nullcontext())
        for patcher in (
            patch.object(cli.sd_handoff_rows, "library", return_value=sd_db),
            patch.object(cli.sd_handoff_rows, "connect", self.connect),
            patch.object(cli.sd_lib, "stored_repo", side_effect=str),
            patch.object(writing, "checkout", self.checkout, create=True),
            patch.object(writing, "piece_for_key", return_value={"id": 7}),
            patch.object(writing, "readiness", return_value={"ok": True}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_in(self, root, *argv):
        arguments = self.parser.parse_args(["writing", *argv, "--json"])
        with patch.object(cli.sd_lib, "repo_root", return_value=root), redirect_stdout(io.StringIO()):
            return arguments.handler(arguments)

    def test_worktree_reads_under_the_main_checkout_row(self):
        self.assertEqual(self.run_in(self.linked, "readiness", "--piece", "2026/a"), 0)
        writing.piece_for_key.assert_called_once_with(self.connection, str(self.main), "2026/a")
        self.checkout.assert_called_once_with(str(self.main), self.linked)

    def test_main_checkout_enters_no_override(self):
        self.assertEqual(self.run_in(self.main, "readiness", "--piece", "2026/a"), 0)
        writing.piece_for_key.assert_called_once_with(self.connection, str(self.main), "2026/a")
        self.checkout.assert_not_called()

    def test_publication_and_cutover_refuse_a_worktree(self):
        for argv in (["publication-render", "--piece", "2026/a"], ["import"], ["recover"],
                     ["register", "--piece", "2026/a"]):
            with self.subTest(argv=argv[0]):
                with self.assertRaisesRegex(cli.WorkRefusal, "only in the main checkout"):
                    self.run_in(self.linked, *argv)
        self.connect.assert_not_called()

    def test_promote_scaffolds_in_the_worktree(self):
        """Promote writes the new piece file, so a worktree's own copy takes it (sd:1994, sd:2024)."""
        (self.linked / "content").mkdir()
        with patch.object(writing, "promote", return_value={"ok": True}) as promoted:
            self.assertEqual(self.run_in(self.linked, "promote", "12"), 0)
        self.assertEqual(promoted.call_args.kwargs["repo"], str(self.main))
        self.checkout.assert_called_once_with(str(self.main), self.linked)

    def test_an_older_library_refuses_a_worktree_by_name(self):
        with patch.object(writing, "checkout", None, create=True):
            with self.assertRaisesRegex(cli.WorkRefusal, "current system/local-sd-db"):
                self.run_in(self.linked, "readiness", "--piece", "2026/a")


if __name__ == "__main__":
    unittest.main()
