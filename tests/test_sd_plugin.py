"""Fixtures for `sd plugin`: real manifests, real config files, real exits.

Every case runs `bin/sd` as a subprocess with `XDG_CONFIG_HOME` pointed at a
temporary directory, so the machine config under test is never the developer's
own and the exit code asserted is the exit code a caller sees.

The load-bearing case is `test_an_unrelated_config_key_survives_registration`.
`sd plugin add` is the first thing in this pack that *writes* the machine
config -- until now `sd_lib.machine_config` only read it -- and that file
already holds settings this command knows nothing about. A registration that
dropped them would be the framework damaging state it does not own.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = REPO_ROOT / "bin" / "sd"


class PluginFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.config_home = self.tmp / "config"
        self.config_path = self.config_home / "sd-ai-command-pack" / "config.json"

    def run_sd(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SD), *args],
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(self.tmp / "home"),
                "XDG_CONFIG_HOME": str(self.config_home),
            },
        )

    def plugin(self, name: str = "pack", **manifest: object) -> pathlib.Path:
        """A plugin checkout whose manifest is `manifest`, defaults filled in."""

        root = self.tmp / name
        root.mkdir(parents=True, exist_ok=True)
        body: dict[str, object] = {"prefix": "pp", "interface": 1}
        body.update(manifest)
        (root / "sd-plugin.json").write_text(json.dumps(body), encoding="utf-8")
        return root

    def write_config(self, payload: dict[str, object]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(payload), encoding="utf-8")

    def config(self) -> dict[str, object]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))


class AddTests(PluginFixture):
    def test_a_registration_round_trips_through_list(self) -> None:
        added = self.run_sd("plugin", "add", str(self.plugin()))
        self.assertEqual(added.returncode, 0, added.stderr)
        listed = self.run_sd("plugin", "list", "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(sorted(json.loads(listed.stdout)), ["pp"])

    def test_an_unrelated_config_key_survives_registration(self) -> None:
        self.write_config({"google": {"accounts": {"personal": {"roles": ["mail_send"]}}}})
        result = self.run_sd("plugin", "add", str(self.plugin()))
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.config()
        self.assertEqual(config["google"], {"accounts": {"personal": {"roles": ["mail_send"]}}})
        self.assertIn("pp", config["plugins"])

    def test_the_manifest_may_be_named_directly(self) -> None:
        manifest = self.plugin() / "sd-plugin.json"
        self.assertEqual(self.run_sd("plugin", "add", str(manifest)).returncode, 0)

    def test_the_tile_command_is_recorded_when_declared(self) -> None:
        root = self.plugin(dashboard={"tile": "./bin/tile"})
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        self.assertEqual(self.config()["plugins"]["pp"]["tile"], "./bin/tile")

    def test_keys_this_slice_does_not_enforce_are_still_carried(self) -> None:
        """`kinds` is stored verbatim, so step 8 inherits data, not a re-read."""

        kinds = {"tip": {"floor": 3, "sections": ["Body"], "nonsense": True}}
        root = self.plugin(kinds=kinds, issues={"repo": "o/r"}, vendor={"pin": "abc"})
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        entry = self.config()["plugins"]["pp"]
        self.assertEqual(entry["kinds"], kinds)
        self.assertEqual(entry["issues"], {"repo": "o/r"})
        self.assertEqual(entry["vendor"], {"pin": "abc"})


class RefusalTests(PluginFixture):
    def assert_refused(self, *args: str, because: str) -> None:
        result = self.run_sd(*args)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(because, result.stderr)

    def test_a_missing_manifest_refuses(self) -> None:
        self.assert_refused(
            "plugin", "add", str(self.tmp / "absent"), because="no sd-plugin.json"
        )

    def test_malformed_json_refuses(self) -> None:
        root = self.tmp / "broken"
        root.mkdir()
        (root / "sd-plugin.json").write_text("{", encoding="utf-8")
        self.assert_refused("plugin", "add", str(root), because="not valid JSON")

    def test_a_manifest_that_is_not_an_object_refuses(self) -> None:
        root = self.tmp / "list"
        root.mkdir()
        (root / "sd-plugin.json").write_text("[]", encoding="utf-8")
        self.assert_refused("plugin", "add", str(root), because="not a JSON object")

    def test_a_missing_prefix_refuses(self) -> None:
        root = self.tmp / "np"
        root.mkdir()
        (root / "sd-plugin.json").write_text('{"interface": 1}', encoding="utf-8")
        self.assert_refused("plugin", "add", str(root), because="declares no `prefix`")

    def test_a_malformed_prefix_refuses(self) -> None:
        self.assert_refused(
            "plugin", "add", str(self.plugin(prefix="Toolong")),
            because="not two to five lowercase letters",
        )

    def test_a_reserved_prefix_refuses(self) -> None:
        for reserved in ("sd", "se"):
            with self.subTest(prefix=reserved):
                self.assert_refused(
                    "plugin", "add", str(self.plugin(name=reserved, prefix=reserved)),
                    because="reserved by the backbone",
                )

    def test_a_second_registration_of_one_prefix_refuses(self) -> None:
        self.assertEqual(self.run_sd("plugin", "add", str(self.plugin("one"))).returncode, 0)
        self.assert_refused(
            "plugin", "add", str(self.plugin("two")), because="already registered"
        )

    def test_a_tile_that_is_not_a_command_refuses(self) -> None:
        self.assert_refused(
            "plugin", "add", str(self.plugin(dashboard={"tile": ""})),
            because="not a non-empty command string",
        )

    def test_a_malformed_machine_config_refuses(self) -> None:
        self.write_config({"plugins": ["pp"]})
        self.assert_refused(
            "plugin", "add", str(self.plugin()), because="`plugins` is not an object"
        )


class ListTests(PluginFixture):
    def test_listing_nothing_is_not_a_failure(self) -> None:
        result = self.run_sd("plugin", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no plugins registered", result.stdout)

    def test_a_bad_invocation_exits_two(self) -> None:
        for args in (("plugin",), ("plugin", "sync"), ("nonesuch",)):
            with self.subTest(args=args):
                self.assertEqual(self.run_sd(*args).returncode, 2)


if __name__ == "__main__":
    unittest.main()
