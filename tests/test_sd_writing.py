"""`sd writing import` names the operator to the library that records it."""

import argparse
import importlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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


if __name__ == "__main__":
    unittest.main()
