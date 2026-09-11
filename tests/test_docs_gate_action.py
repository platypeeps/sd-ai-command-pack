"""The docs-gate action's own shell: what it refuses, and what it still runs."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ACTION = Path(__file__).resolve().parents[1] / "actions/docs-gate/action.yml"

# The action is a composite step, so there is no entry point to import. The
# script is lifted out of the YAML the same way `actions/review-route` is
# tested, and run under the shell the runner would give it.
SCRIPT = textwrap.dedent(ACTION.read_text(encoding="utf-8").split("      run: |\n", 1)[1])

# A stand-in for `bin/sd-research-kit`. The gate's job is deciding which verbs
# reach the kit and what it does with their exit codes, so the real kit would
# only add its own repository-walking failures to every assertion here.
FAKE_KIT = """\
import os, sys
with open(os.environ["SD_FAKE_KIT_LOG"], "a", encoding="utf-8") as log:
    log.write(sys.argv[1] + "\\n")
sys.exit(1 if sys.argv[1] in os.environ.get("SD_FAKE_KIT_FAILS", "").split() else 0)
"""


class DocsGateActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)], check=True))
        self.action_path = self.tmp / "pack/actions/docs-gate"
        self.action_path.mkdir(parents=True)
        self.kit = self.tmp / "pack/bin/sd-research-kit"
        self.kit.parent.mkdir(parents=True)
        self.kit.write_text(FAKE_KIT, encoding="utf-8")
        self.log = self.tmp / "verbs.log"
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()

    def gate(self, verbs, fails=""):
        environment = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "GITHUB_ACTION_PATH": str(self.action_path),
            "SD_DOCS_GATE_VERBS": verbs,
            "SD_FAKE_KIT_LOG": str(self.log),
            "SD_FAKE_KIT_FAILS": fails,
        }
        return subprocess.run(["/bin/bash", "-c", SCRIPT], cwd=self.workspace, env=environment,
                              capture_output=True, text=True, timeout=30)

    def ran(self):
        return self.log.read_text(encoding="utf-8").split() if self.log.exists() else []

    def test_an_unknown_verb_stops_the_gate_before_anything_runs(self):
        result = self.gate("review nonsense")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("refusing unknown or writing verb 'nonsense'", result.stderr)
        self.assertEqual(self.ran(), [], "the allow-list let a verb through before refusing")

    def test_the_writing_verb_is_refused_because_the_action_promises_not_to_write(self):
        result = self.gate("render")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("'render'", result.stderr)
        self.assertEqual(self.ran(), [])

    def test_naming_no_verb_is_refused_rather_than_reported_as_a_pass(self):
        for verbs in ("", "   ", "\t\n"):
            with self.subTest(verbs=repr(verbs)):
                result = self.gate(verbs)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("names no check", result.stderr)
                self.assertEqual(self.ran(), [])

    def test_every_verb_runs_even_after_an_earlier_one_fails(self):
        result = self.gate("review checklinks pins", fails="review")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.ran(), ["review", "checklinks", "pins"],
                         "a failing verb stopped the ones after it")

    def test_the_gate_passes_only_when_every_verb_passes(self):
        result = self.gate("review checklinks pins conventions")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ran(), ["review", "checklinks", "pins", "conventions"])

    def test_a_missing_kit_stops_the_gate_instead_of_passing_on_nothing(self):
        self.kit.unlink()
        result = self.gate("review")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("no sd-research-kit beside this action", result.stderr)

    def test_the_declared_default_names_only_verbs_the_allow_list_accepts(self):
        default = re.search(r"^    default: (.+)$", ACTION.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(default, "the action no longer declares a default for `verbs`")
        assert default is not None
        result = self.gate(default.group(1))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ran(), default.group(1).split())


if __name__ == "__main__":
    unittest.main()
