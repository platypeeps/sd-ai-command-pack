"""The fast Git fixture preserves argv, transport scope, and process results."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tests import test_sd_ship as fixture


class GitTransportTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="ship fixture's ")
        self.addCleanup(scratch.cleanup)
        self.root = pathlib.Path(scratch.name)
        self.binary = self.root / "real git's executable"
        self.binary.write_text(
            f"#!{sys.executable}\nimport json, os, sys\n"
            "print(json.dumps(sys.argv[1:]))\n"
            "print('fixture stderr', file=sys.stderr)\n"
            "sys.exit(int(os.environ.get('FIXTURE_EXIT', '0')))\n"
        )
        self.binary.chmod(0o755)
        self.remote = self.root / "remote repo's.git"
        self.url = "https://github.com/fixture/repo.git"
        self.adapter = self.root / "git"
        self.adapter.write_text(fixture.git_transport(str(self.binary), self.remote, self.url))
        self.adapter.chmod(0o755)
        python = self.root / "python3"
        python.write_text("#!/bin/sh\nexit 99\n")
        python.chmod(0o755)

    def invoke(self, *args, exit_code=0):
        return subprocess.run(
            [str(self.adapter), *args], capture_output=True, text=True, timeout=10,
            env={**os.environ, "PATH": str(self.root), "FIXTURE_EXIT": str(exit_code)},
        )

    def test_transport_rewrites_only_network_commands_without_python_on_path(self):
        rewrite = ["-c", f"url.{self.remote}.insteadOf={self.url}"]
        for command in ("fetch", "push", "ls-remote"):
            with self.subTest(command=command):
                args = ["-C", str(self.root), command, self.url, "branch with ' quotes;$x"]
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), rewrite + args)

    def test_local_commands_preserve_literal_arguments_without_rewriting(self):
        args = ["config", "--get", "remote.origin.url", "$(not-a-command)", "", "fetching"]
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), args)

    def test_nonzero_status_and_stderr_survive_exec(self):
        result = self.invoke("status", exit_code=17)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stderr, "fixture stderr\n")
        self.assertEqual(json.loads(result.stdout), ["status"])


if __name__ == "__main__":
    unittest.main()
