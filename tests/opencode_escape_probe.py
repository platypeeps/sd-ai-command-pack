"""Opt-in, live: the opencode confinement asserted against the installed binary.

Run ``python3 -m unittest tests.opencode_escape_probe`` by hand after an
opencode upgrade, outside the unit-test suite. `make test` runs only
`tests/test_*.py`, so the gate never depends on which opencode the machine has:
a missing binary or a new major used to fail every pack gate through the skip
check (sd:3486). The reader refuses any major but `SUPPORTED_MAJOR` before a
review runs, and `tests/test_sd_review_opencode.py` covers that refusal
offline; this probe is what re-measures a new major before that number moves.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_opencode  # noqa: E402

from tests.test_sd_review import sd_review  # noqa: E402


def _opencode_major() -> int | None:
    if not shutil.which("opencode"):
        return None
    done = subprocess.run(["opencode", "--version"], capture_output=True, text=True, timeout=30,
                          stdin=subprocess.DEVNULL, check=False)
    return sd_opencode.major_version(done.stdout)


@unittest.skipUnless(shutil.which("opencode"), "the opencode binary is not on PATH")
class TheEscapeIsClosedLive(unittest.TestCase):
    """The confinement asserted against opencode itself, not only against the
    generated config. A hostile checkout is built from
    `tests/fixtures/opencode_escape`. The marker that opencode loaded the
    checkout's config is the checkout's own MCP server starting: the inert
    mutator writes `server-started` to `MUTATOR_EVIDENCE` during bootstrap,
    before any model call. Measured on 2.0.20; another major is refused by
    the reader before any of this runs, so it skips here."""

    FIXTURE = REPO_ROOT / "tests" / "fixtures" / "opencode_escape"

    def setUp(self) -> None:
        major = _opencode_major()
        if major != sd_opencode.SUPPORTED_MAJOR:
            self.skipTest(f"opencode major {major} is refused by the reader, not measured here")
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tmp = pathlib.Path(self.dir.name).resolve()
        self.checkout = self.build_checkout(self.tmp)
        self.neutral = self.tmp / "neutral"
        self.neutral.mkdir()
        for launch in (self.checkout, self.neutral):
            (launch / "review-subject.md").write_text("Reply with {\"findings\": []}\n", encoding="utf-8")
        sd_opencode.assert_isolated_launch(self.neutral, self.checkout)

    def build_checkout(self, tmp: pathlib.Path) -> pathlib.Path:
        checkout = tmp / "checkout"
        (checkout / "tools").mkdir(parents=True)
        (checkout / "opencode.json").write_text((self.FIXTURE / "checkout_opencode.json").read_text(encoding="utf-8"), encoding="utf-8")
        (checkout / "AGENTS.md").write_text((self.FIXTURE / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")
        (checkout / "tools" / "mutator_mcp.py").write_text((self.FIXTURE / "mutator_mcp.py").read_text(encoding="utf-8"), encoding="utf-8")
        (checkout / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        return checkout

    def reader_env(self, name: str, **parent: str) -> dict[str, str]:
        """The environment the reader hands opencode, from this process's own
        plus `parent`, with a fresh empty config dir."""
        config_dir = self.tmp / f"config-{name}"
        config_dir.mkdir()
        return sd_opencode.opencode_environment({**os.environ, **parent}, config_dir)

    def server_started(self, cwd: pathlib.Path, env: dict[str, str], name: str) -> bool:
        evidence = self.tmp / f"{name}.log"
        argv = sd_opencode.opencode_argv(cwd, "opencode run", "openai/gpt-5.5")
        try:
            subprocess.run(argv, cwd=str(cwd), env={**env, "MUTATOR_EVIDENCE": str(evidence)},
                           capture_output=True, text=True, timeout=45, stdin=subprocess.DEVNULL, check=False)
        except subprocess.TimeoutExpired:
            pass
        return evidence.exists() and "server-started" in evidence.read_text(encoding="utf-8")

    def test_the_checkout_mcp_server_starts_from_inside_but_never_under_the_reader(self) -> None:
        # A shell standing in the checkout, with project config on.
        open_env = {key: value for key, value in self.reader_env("control").items()
                    if key not in ("OPENCODE_CONFIG_PROJECT_DISABLE", "OPENCODE_DISABLE_PROJECT_CONFIG")}
        open_env["PWD"] = str(self.checkout)
        self.assertTrue(self.server_started(self.checkout, open_env, "control"),
                        "control arm: inside the checkout with project config on, opencode starts its server")
        # The reader's launch, from a parent that stood in the checkout: the
        # inherited `PWD` alone started the server from a neutral cwd on 2.0.20.
        self.assertFalse(self.server_started(self.neutral, self.reader_env("reader", PWD=str(self.checkout)), "reader"),
                         "the checkout's MCP server must not start under the reader's launch")
        # The second layer on its own: even launched inside, project config is off.
        self.assertFalse(self.server_started(self.checkout, self.reader_env("layer"), "layer"),
                         "project config must stay off even inside the checkout")
        self.assertFalse((self.checkout / "PWNED-1375.txt").exists(), "no mutation may reach the checkout")

    def report(self, cwd: pathlib.Path, env: dict[str, str]) -> dict[str, Any]:
        result = sd_review.subprocess_runner(sd_opencode.probe_argv("opencode run", 40), env, cwd, 45)
        report = sd_opencode.probe_report(result.stdout) if result.exit_code == 0 else None
        self.assertIsNotNone(report, result.stderr)
        return report or {}

    def breach(self, cwd: pathlib.Path, env: dict[str, str]) -> str | None:
        return sd_opencode.confinement_breach(sd_review.subprocess_runner, "opencode run", env, cwd, 45)

    def test_opencode_resolves_the_map_and_the_probe_refuses_a_widening(self) -> None:
        """Measured through opencode, not the loader. The reader's launch
        resolves the exact map with no plugin of its own, from the neutral dir
        and from inside the checkout alike. With project config on, the
        hostile rules are contributed but land before our deny: 2.x merges
        the inline config last. A rule after the deny, and a plugin in the
        config dir, refuse; `XDG_CONFIG_HOME` no longer reaches the run."""
        self.assertIsNone(self.breach(self.neutral, self.reader_env("neutral")))
        inside = self.report(self.checkout, self.reader_env("inside"))
        self.assertNotIn("mutator_mutate", json.dumps(inside["agent"]), "project config is off")
        self.assertIsNone(self.breach(self.checkout, self.reader_env("inside2")))

        open_env = {key: value for key, value in self.reader_env("open").items()
                    if key not in ("OPENCODE_CONFIG_PROJECT_DISABLE", "OPENCODE_DISABLE_PROJECT_CONFIG")}
        rules = sd_opencode.resolved_rules(self.report(self.checkout, open_env)) or []
        hostile = {"action": "mutator_mutate", "resource": "*", "effect": "allow"}
        self.assertIn(hostile, rules, "the probe reads opencode's merge, not our config")
        self.assertLess(rules.index(hostile), rules.index(sd_opencode.PERMISSION[0]))
        self.assertIsNone(self.breach(self.checkout, open_env))

        widened = self.reader_env("widened")
        config = json.loads(widened["OPENCODE_CONFIG_CONTENT"])
        config["agents"][sd_opencode.AGENT]["permissions"].append({"action": "shell", "resource": "*", "effect": "allow"})
        self.assertIn('"shell"', self.breach(self.neutral, {**widened, "OPENCODE_CONFIG_CONTENT": json.dumps(config)}) or "")

        xdg = self.tmp / "xdg" / "opencode" / "plugins"
        xdg.mkdir(parents=True)
        (xdg / "plugin_local.js").write_text((self.FIXTURE / "plugin_local.js").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertIsNone(self.breach(self.neutral, self.reader_env("xdg", XDG_CONFIG_HOME=str(self.tmp / "xdg"))))
        planted = self.reader_env("planted")
        (pathlib.Path(planted["OPENCODE_CONFIG_DIR"]) / "plugins").mkdir()
        (pathlib.Path(planted["OPENCODE_CONFIG_DIR"]) / "plugins" / "plugin_local.js").write_text(
            (self.FIXTURE / "plugin_local.js").read_text(encoding="utf-8"), encoding="utf-8")
        self.assertIn("sd-fixture-local", self.breach(self.neutral, planted) or "")


if __name__ == "__main__":
    unittest.main()
