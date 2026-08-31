"""The plugin loader's budget, its contract, and its refusal to go quiet.

Two properties carry the weight here and both are tested against a real
subprocess rather than a stubbed one, because both are about what a plugin can
do to the process that loads it -- outlast its deadline, outgrow its buffer --
and neither survives being mocked.

The third is the one R11-D12 exists for: three plugin tabs own every rank-0 and
rank-1 alert the dashboard emits, so a plugin that fails must produce a row
saying it failed. Every refusal path below is asserted to leave a row behind,
which is the assertion that would catch the view going calm while the machine
is on fire.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dashboard import plugins  # noqa: E402


def tile_script(body: str) -> str:
    """A tile command: this interpreter running an inline program."""
    return f"{shlex_quote(sys.executable)} -c {shlex_quote(textwrap.dedent(body))}"


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)


class PluginLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        # Resolved because macOS spells its temporary directory both `/var` and
        # `/private/var`, and `sd plugin add` records the canonical path.
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self._env = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._env)))
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "config")

    def plugin(self, prefix: str, tile: str | None = None) -> pathlib.Path:
        root = self.tmp / f"plugin-{prefix}"
        root.mkdir(parents=True, exist_ok=True)
        manifest: dict = {"prefix": prefix, "interface": 1}
        if tile is not None:
            manifest["dashboard"] = {"tile": tile}
        (root / "sd-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def register(self, root: pathlib.Path) -> None:
        done = subprocess.run(
            [sys.executable, str(REPO_ROOT / "bin" / "sd"), "plugin", "add", str(root)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)

    def rows_of(self, kind: str, loaded: dict) -> list[dict]:
        return [row for row in loaded["rows"] if row["kind"] == kind]

    def only(self, loaded: dict) -> dict:
        self.assertEqual(len(loaded["plugins"]), 1)
        return loaded["plugins"][0]

    # -- the empty machine -------------------------------------------------

    def test_a_machine_with_no_plugins_loads_nothing_and_reports_no_error(self) -> None:
        loaded = plugins.load()
        self.assertEqual(loaded["plugins"], [])
        self.assertEqual(loaded["tabs"], [])
        self.assertEqual(loaded["rows"], [])
        # The distinction the whole `catalog` return type exists for: no
        # plugins is a working machine, not a broken loader.
        self.assertEqual(loaded["registryError"], "")

    def test_a_plugin_without_a_tile_is_not_a_failure(self) -> None:
        self.register(self.plugin("aa"))
        loaded = plugins.load()
        self.assertTrue(self.only(loaded)["ok"])
        self.assertFalse(self.only(loaded)["declared"])
        self.assertEqual(loaded["tabs"], [])
        self.assertEqual(loaded["rows"], [])

    # -- the happy path ----------------------------------------------------

    def test_a_tile_contributes_its_markup_and_its_rows(self) -> None:
        self.register(
            self.plugin(
                "bb",
                tile_script(
                    """
                    import json
                    print(json.dumps({"tabs": [{
                        "title": "toolbox",
                        "html": "<p>ok</p>",
                        "rows": [{"rank": 0, "kind": "cron-exit", "id": "com.sven.x",
                                  "what": "job failed", "detail": "rc=2", "href": "#toolbox"}],
                    }]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertEqual(len(loaded["tabs"]), 1)
        tab = loaded["tabs"][0]
        self.assertEqual(tab["title"], "toolbox")
        self.assertEqual(tab["html"], "<p>ok</p>")
        self.assertEqual(len(loaded["rows"]), 1)
        row = loaded["rows"][0]
        self.assertEqual(row["kind"], "cron-exit")
        self.assertEqual(row["href"], "#toolbox")
        # Stamped by the loader, not by the plugin: a row has to be traceable
        # to the tab that emitted it even when the plugin would rather it were
        # not. Tab and not just plugin, because one prefix now carries several.
        self.assertEqual(row["source"], "bb/toolbox")

    def test_rows_arrive_sorted_by_rank_across_plugins(self) -> None:
        for prefix, rank in (("cc", 3), ("dd", 1)):
            self.register(
                self.plugin(
                    prefix,
                    tile_script(
                        f"""
                        import json
                        print(json.dumps({{"tabs": [{{"title": "t", "rows": [
                          {{"rank": {rank}, "kind": "k", "id": "i", "what": "w"}}]}}]}}))
                        """
                    ),
                )
            )
        loaded = plugins.load()
        self.assertEqual([row["rank"] for row in loaded["rows"]], [1, 3])

    # -- the budget --------------------------------------------------------

    def test_a_tile_larger_than_its_byte_budget_is_refused_and_reported(self) -> None:
        self.register(
            self.plugin(
                "ee",
                tile_script(
                    """
                    import sys
                    sys.stdout.write("x" * (200 * 1024))
                    """
                ),
            )
        )
        loaded = plugins.load()
        plugin = self.only(loaded)
        self.assertFalse(plugin["ok"])
        self.assertIn("more than", plugin["reason"])
        # The whole point: the oversized markup is gone and a row took its
        # place. An empty tab with no row is the failure this asserts against.
        self.assertEqual(loaded["tabs"], [])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)
        self.assertEqual(loaded["rows"][0]["rank"], 0)

    def test_a_tile_that_outlasts_its_deadline_is_killed_and_reported(self) -> None:
        original = plugins.TILE_SECONDS
        plugins.TILE_SECONDS = 0.4
        self.addCleanup(lambda: setattr(plugins, "TILE_SECONDS", original))
        self.register(
            self.plugin(
                "ff",
                tile_script(
                    """
                    import time
                    time.sleep(30)
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertFalse(self.only(loaded)["ok"])
        self.assertIn("within", self.only(loaded)["reason"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_tile_that_backgrounds_work_does_not_outlive_the_deadline(self) -> None:
        """The kill targets the process group, not the command that was named.

        A tile whose child holds the pipe open would otherwise keep the read
        blocked past the deadline, which would bound this module and nothing
        else.
        """
        original = plugins.TILE_SECONDS
        plugins.TILE_SECONDS = 0.4
        self.addCleanup(lambda: setattr(plugins, "TILE_SECONDS", original))
        marker = self.tmp / "child-finished"
        self.register(
            self.plugin(
                "gg",
                tile_script(
                    f"""
                    import subprocess, sys, time
                    subprocess.Popen([sys.executable, "-c",
                      "import time,pathlib; time.sleep(6);"
                      "pathlib.Path({str(marker)!r}).write_text('x')"])
                    time.sleep(30)
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertFalse(self.only(loaded)["ok"])
        import time as _time

        _time.sleep(1.5)
        self.assertFalse(
            marker.exists(),
            "the tile's child survived the group kill and kept running",
        )

    def test_a_tile_that_exits_non_zero_is_refused(self) -> None:
        self.register(
            self.plugin(
                "hh",
                tile_script(
                    """
                    import sys
                    sys.exit(3)
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertFalse(self.only(loaded)["ok"])
        self.assertIn("exited 3", self.only(loaded)["reason"])

    def test_a_tile_that_does_not_emit_json_is_refused(self) -> None:
        self.register(self.plugin("ii", tile_script('print("not json")')))
        loaded = plugins.load()
        self.assertFalse(self.only(loaded)["ok"])
        self.assertIn("not JSON", self.only(loaded)["reason"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_tile_command_that_does_not_exist_is_refused(self) -> None:
        self.register(self.plugin("jj", "/nonexistent/tile --json"))
        loaded = plugins.load()
        self.assertFalse(self.only(loaded)["ok"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_manifest_deleted_after_registration_reports_rather_than_raises(self) -> None:
        root = self.plugin("kk", tile_script("print('{\"tabs\": []}')"))
        self.register(root)
        (root / "sd-plugin.json").unlink()
        loaded = plugins.load()
        # `sd plugin list` reports the root as unreadable; the loader turns
        # that into a row rather than dropping a registered plugin silently.
        self.assertFalse(self.only(loaded)["ok"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    # -- the row contract --------------------------------------------------

    def refused_row(self, row_json: str) -> dict:
        """A tile emitting exactly one row, given as JSON rather than as Python.

        The distinction is not cosmetic: `{"rank": true}` is JSON and not a
        Python expression, so embedding these as literals would make the
        boolean case exercise a crashed interpreter instead of the validator.
        """
        self.register(
            self.plugin(
                "zz",
                tile_script(
                    f"""
                    import json
                    print(json.dumps({{"tabs": [{{"title": "t",
                        "html": "<p>tab still renders</p>",
                        "rows": [json.loads({row_json!r})]}}]}}))
                    """
                ),
            )
        )
        return plugins.load()

    def assert_refused(self, row_json: str, because: str) -> None:
        loaded = self.refused_row(row_json)
        # The tab is fine; one row was not. Refusing the whole tile over a bad
        # row would take the plugin's good alerts down with the bad one.
        self.assertTrue(self.only(loaded)["ok"])
        tab = loaded["tabs"][0]
        self.assertEqual(tab["html"], "<p>tab still renders</p>")
        self.assertEqual(tab["rows"], [])
        refusals = self.rows_of("plugin-refused", loaded)
        self.assertEqual(len(refusals), 1)
        self.assertEqual(refusals[0]["rank"], 0)
        self.assertIn(because, refusals[0]["detail"])

    def test_an_off_page_href_is_refused(self) -> None:
        self.assert_refused(
            '{"rank": 1, "kind": "k", "id": "i", "what": "w", "href": "https://evil.example"}',
            "in-page anchor",
        )

    def test_a_javascript_href_is_refused(self) -> None:
        self.assert_refused(
            '{"rank": 1, "kind": "k", "id": "i", "what": "w", "href": "javascript:alert(1)"}',
            "in-page anchor",
        )

    def test_a_non_integer_rank_is_refused(self) -> None:
        self.assert_refused('{"rank": "0", "kind": "k", "id": "i", "what": "w"}', "rank")

    def test_a_boolean_rank_is_refused(self) -> None:
        """`True` is an `int` in Python, and `rank: true` is not an ordering."""
        self.assert_refused('{"rank": true, "kind": "k", "id": "i", "what": "w"}', "rank")

    def test_a_row_missing_a_required_field_is_refused(self) -> None:
        self.assert_refused('{"rank": 1, "kind": "k", "id": "i"}', "what")

    def test_a_row_that_is_not_an_object_is_refused(self) -> None:
        self.assert_refused('"just a string"', "not an object")

    def test_a_good_row_survives_beside_a_refused_one(self) -> None:
        self.register(
            self.plugin(
                "yy",
                tile_script(
                    """
                    import json
                    print(json.dumps({"tabs": [{"title": "t", "rows": [
                        {"rank": 2, "kind": "good", "id": "i", "what": "w"},
                        {"rank": 2, "kind": "bad", "id": "i", "what": "w",
                         "href": "https://evil.example"},
                    ]}]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertEqual(len(self.rows_of("good", loaded)), 1)
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)
        self.assertEqual(len(self.rows_of("bad", loaded)), 0)

    def test_rows_that_are_not_a_list_are_refused_without_taking_the_tab(self) -> None:
        self.register(
            self.plugin(
                "xx",
                tile_script(
                    """
                    import json
                    print(json.dumps({"tabs": [
                        {"title": "t", "html": "<p>ok</p>", "rows": "nope"}]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertTrue(self.only(loaded)["ok"])
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)

    # -- the tab contract --------------------------------------------------

    def test_one_tile_may_carry_several_tabs(self) -> None:
        """`~/repos/system` is one repository, one manifest, and five views.

        A payload that could hold only one tab could not express the tabs the
        swap exists to move, which is what makes the list the contract rather
        than a convenience.
        """
        self.register(
            self.plugin(
                "vv",
                tile_script(
                    """
                    import json
                    print(json.dumps({"tabs": [
                        {"title": "toolbox", "html": "<p>a</p>",
                         "rows": [{"rank": 1, "kind": "k", "id": "i", "what": "w"}]},
                        {"title": "vault", "html": "<p>b</p>",
                         "rows": [{"rank": 0, "kind": "j", "id": "i", "what": "w"}]},
                        {"title": "briefs", "html": "<p>c</p>"},
                    ]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertEqual([t["title"] for t in loaded["tabs"]], ["toolbox", "vault", "briefs"])
        self.assertEqual([r["rank"] for r in loaded["rows"]], [0, 1])
        # Rows carry the tab they came from, not just the plugin: five tabs
        # behind one prefix would otherwise be one undifferentiated source.
        self.assertEqual(sorted(r["source"] for r in loaded["rows"]),
                         ["vv/toolbox", "vv/vault"])

    def test_a_tab_without_a_title_is_refused_without_taking_its_siblings(self) -> None:
        self.register(
            self.plugin(
                "uu",
                tile_script(
                    """
                    import json
                    print(json.dumps({"tabs": [
                        {"html": "<p>nameless</p>"},
                        {"title": "kept", "html": "<p>b</p>"},
                    ]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertEqual([t["title"] for t in loaded["tabs"]], ["kept"])
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)

    def test_a_repeated_title_is_refused_because_the_tab_is_unreachable(self) -> None:
        self.register(
            self.plugin(
                "tt",
                tile_script(
                    """
                    import json
                    print(json.dumps({"tabs": [
                        {"title": "same", "html": "<p>first</p>"},
                        {"title": "same", "html": "<p>second</p>"},
                    ]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertEqual(len(loaded["tabs"]), 1)
        self.assertEqual(loaded["tabs"][0]["html"], "<p>first</p>")
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)

    def test_a_tile_that_declares_no_tabs_key_is_refused(self) -> None:
        """Distinct from an empty list, which is a plugin with nothing to show."""
        self.register(self.plugin("ss", tile_script('print(\'{"html": "<p>x</p>"}\')')))
        loaded = plugins.load()
        self.assertFalse(self.only(loaded)["ok"])
        self.assertIn("no `tabs`", self.only(loaded)["reason"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_an_empty_tabs_list_is_a_working_plugin(self) -> None:
        self.register(self.plugin("rr", tile_script('print(\'{"tabs": []}\')')))
        loaded = plugins.load()
        self.assertTrue(self.only(loaded)["ok"])
        self.assertEqual(loaded["tabs"], [])
        self.assertEqual(loaded["rows"], [])


if __name__ == "__main__":
    unittest.main()
