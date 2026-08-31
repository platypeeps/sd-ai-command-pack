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

    def plugin(
        self, prefix: str, tile: str | None = None, tabs: list[str] | None = None
    ) -> pathlib.Path:
        root = self.tmp / f"plugin-{prefix}"
        root.mkdir(parents=True, exist_ok=True)
        manifest: dict = {"prefix": prefix, "interface": 1}
        if tile is not None:
            manifest["dashboard"] = {"tile": tile, "tabs": tabs or ["one"]}
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

    def only_tab(self, loaded: dict) -> dict:
        """The one tab of the one registered plugin, whether it reported or not.

        Deliberately not `loaded["tabs"]`, which carries only the tabs that
        succeeded: a refused tab has to stay inspectable, or these tests could
        not tell one apart from a plugin that declared no tabs at all.
        """
        plugin = self.only(loaded)
        self.assertEqual(len(plugin["tabs"]), 1)
        return plugin["tabs"][0]

    # -- the empty machine -------------------------------------------------

    def test_a_machine_with_no_plugins_loads_nothing_and_reports_no_error(self) -> None:
        loaded = plugins.load()
        self.assertEqual(loaded["plugins"], [])
        self.assertEqual(loaded["tabs"], [])
        self.assertEqual(loaded["rows"], [])
        # The distinction the whole `catalog` return type exists for: no
        # plugins is a working machine, not a broken loader.
        self.assertEqual(loaded["registryError"], "")

    def test_a_registry_that_cannot_be_read_is_a_rank_zero_row(self) -> None:
        """The outermost refusal, and the one with no plugin to blame.

        Every other failure path here has a registered plugin to name. This one
        does not: if `sd plugin list` cannot run, the loader knows nothing about
        any plugin, and reporting that as an empty fleet is precisely the quiet
        the module exists to refuse.
        """
        original = plugins.SD
        plugins.SD = pathlib.Path("/nonexistent/sd")
        self.addCleanup(lambda: setattr(plugins, "SD", original))
        loaded = plugins.load()
        self.assertTrue(loaded["registryError"])
        rows = self.rows_of("plugin-registry", loaded)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rank"], 0)
        # And it is distinguishable from the machine that simply has none.
        self.assertNotEqual(loaded["rows"], [])

    def test_a_registry_larger_than_a_tile_is_allowed_still_reads(self) -> None:
        """The registry answers to its own budget, not to a plugin's.

        Found in review. `catalog` read `sd plugin list --json` under
        `TILE_BYTES`, so the size a registry was allowed to be was a function
        of how much output one plugin may print. A machine with enough plugins
        to pass 64KB of listing would have reported a broken registry on every
        load, permanently, with nothing wrong with it.
        """
        config = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "sd-ai-command-pack"
        config.mkdir(parents=True, exist_ok=True)
        # Unregistered roots still list, each with its path and its reason, so
        # a listing far past the tile ceiling needs no plugins on disk.
        roots = [str(self.tmp / ("absent-" + "x" * 200 + f"-{index}")) for index in range(500)]
        (config / "config.json").write_text(
            json.dumps({"plugins": roots}), encoding="utf-8"
        )
        raw, error = plugins.catalog()
        self.assertEqual(error, "")
        self.assertEqual(len(raw), len(roots))
        self.assertGreater(
            len(json.dumps(raw)), plugins.TILE_BYTES, "fixture no longer exceeds a tile"
        )

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
                    print(json.dumps({
                        "title": "toolbox",
                        "html": "<p>ok</p>",
                        "rows": [{"rank": 0, "kind": "cron-exit", "id": "com.sven.x",
                                  "what": "job failed", "detail": "rc=2", "href": "#toolbox"}],
                    }))
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
        self.assertEqual(row["source"], "bb/one")

    def test_rows_arrive_sorted_by_rank_across_plugins(self) -> None:
        for prefix, rank in (("cc", 3), ("dd", 1)):
            self.register(
                self.plugin(
                    prefix,
                    tile_script(
                        f"""
                        import json
                        print(json.dumps({{"rows": [
                          {{"rank": {rank}, "kind": "k", "id": "i", "what": "w"}}]}}))
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
        tab = self.only_tab(loaded)
        self.assertFalse(tab["ok"])
        self.assertIn("more than", tab["reason"])
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
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertIn("within", self.only_tab(loaded)["reason"])
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
        self.assertFalse(self.only_tab(loaded)["ok"])
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
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertIn("exited 3", self.only_tab(loaded)["reason"])

    def test_a_tile_that_emits_output_and_then_fails_is_refused(self) -> None:
        """Closing stdout is not exiting, and the exit status still counts.

        The loader kills the tile's process group on its way out. If that kill
        also ran on the success path, the recorded status would be -SIGKILL for
        every tile that had not quite exited, and a loader that reads its own
        kill as a clean exit accepts the output of every tile that dies after
        writing. The JSON here is perfectly good; the run is not.
        """
        self.register(
            self.plugin(
                "qq",
                tile_script(
                    """
                    import json, os, sys
                    print(json.dumps({"title": "t"}))
                    sys.stdout.flush()
                    os.close(1)
                    os._exit(3)
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertIn("exited 3", self.only_tab(loaded)["reason"])
        self.assertEqual(loaded["tabs"], [])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_tile_that_writes_then_hangs_is_refused_rather_than_accepted(self) -> None:
        """Output in hand is not a finished run while the deadline is unmet."""
        original = plugins.TILE_SECONDS
        plugins.TILE_SECONDS = 0.4
        self.addCleanup(lambda: setattr(plugins, "TILE_SECONDS", original))
        self.register(
            self.plugin(
                "pp",
                tile_script(
                    """
                    import json, os, sys, time
                    print(json.dumps({"title": "t"}))
                    sys.stdout.flush()
                    os.close(1)
                    time.sleep(30)
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertIn("did not exit", self.only_tab(loaded)["reason"])

    def test_a_tile_that_stalls_mid_write_says_so_rather_than_no_output(self) -> None:
        """Two failures share the deadline, and they are not the same failure.

        Found in review. A tile that never spoke and one that wrote and then
        stopped both hit the same timeout, and reporting the second as "no
        output" sends whoever reads the row looking for a tile that never
        started. Stdout stays open here -- that is what separates this path
        from the one the hang test takes.
        """
        original = plugins.TILE_SECONDS
        plugins.TILE_SECONDS = 0.4
        self.addCleanup(lambda: setattr(plugins, "TILE_SECONDS", original))
        self.register(
            self.plugin(
                "ss",
                tile_script(
                    """
                    import sys, time
                    sys.stdout.write('{"title": "t"')
                    sys.stdout.flush()
                    time.sleep(30)
                    """
                ),
            )
        )
        reason = self.only_tab(plugins.load())["reason"]
        self.assertIn("stopped writing", reason)
        self.assertNotIn("no output", reason)

    def test_a_tile_that_prints_nothing_is_refused_rather_than_empty(self) -> None:
        """Printing `{}` and printing nothing are different events.

        Found in review. An empty payload is `{}`, and a tile with nothing to
        show prints it. Silence was being read as that payload, which handed
        the view a successful tab that was silent about its own failure -- the
        exact shape R11-D12 exists to refuse, one level down.
        """
        self.register(self.plugin("tt", tile_script("pass")))
        loaded = plugins.load()
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertIn("printed nothing", self.only_tab(loaded)["reason"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_registry_that_prints_nothing_is_refused_rather_than_empty(self) -> None:
        """The same rule at the level that has no plugin to blame."""
        quiet = self.tmp / "quiet-sd"
        quiet.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        quiet.chmod(0o755)
        original = plugins.SD
        plugins.SD = quiet
        self.addCleanup(lambda: setattr(plugins, "SD", original))
        loaded = plugins.load()
        self.assertIn("printed nothing", loaded["registryError"])
        self.assertEqual(len(self.rows_of("plugin-registry", loaded)), 1)

    def test_a_tile_that_does_not_emit_json_is_refused(self) -> None:
        self.register(self.plugin("ii", tile_script('print("not json")')))
        loaded = plugins.load()
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertIn("not JSON", self.only_tab(loaded)["reason"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_tile_command_that_does_not_exist_is_refused(self) -> None:
        self.register(self.plugin("jj", "/nonexistent/tile --json"))
        loaded = plugins.load()
        self.assertFalse(self.only_tab(loaded)["ok"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_a_manifest_deleted_after_registration_reports_rather_than_raises(self) -> None:
        root = self.plugin("kk", tile_script("print('{}')"))
        self.register(root)
        (root / "sd-plugin.json").unlink()
        loaded = plugins.load()
        # `sd plugin list` reports the root as unreadable; the loader turns
        # that into a row rather than dropping a registered plugin silently.
        # Plugin-level and not tab-level: with no manifest there are no tabs.
        self.assertFalse(self.only(loaded)["ok"])
        self.assertEqual(len(self.rows_of("plugin-dark", loaded)), 1)

    def test_two_unreadable_plugins_are_two_distinguishable_rows(self) -> None:
        """A plugin with no readable manifest has no prefix to be named by.

        Found in review. Naming it "?" made every dark plugin the same row --
        same source, same id, same text -- so an operator with two broken
        plugins could not tell which, or that there were two. The loader has
        the root, so it says the root.
        """
        for prefix in ("kk", "ll"):
            root = self.plugin(prefix, tile_script("print('{}')"))
            self.register(root)
            (root / "sd-plugin.json").unlink()
        rows = self.rows_of("plugin-dark", plugins.load())
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            sorted(row["source"] for row in rows),
            sorted(str(self.tmp / f"plugin-{prefix}") for prefix in ("kk", "ll")),
        )

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
                    print(json.dumps({{"title": "t",
                        "html": "<p>tab still renders</p>",
                        "rows": [json.loads({row_json!r})]}}))
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

    def test_a_negative_rank_is_refused(self) -> None:
        """Rank 0 is the top, and it is where a dark plugin gets reported.

        A row above it would let a plugin sort the notice of its own failure
        underneath its own rows.
        """
        self.assert_refused(
            '{"rank": -1, "kind": "k", "id": "i", "what": "w"}', "top of the view"
        )

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
                    print(json.dumps({"rows": [
                        {"rank": 2, "kind": "good", "id": "i", "what": "w"},
                        {"rank": 2, "kind": "bad", "id": "i", "what": "w",
                         "href": "https://evil.example"},
                    ]}))
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
                    print(json.dumps({"html": "<p>ok</p>", "rows": "nope"}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertTrue(self.only(loaded)["ok"])
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)

    # -- the tab contract --------------------------------------------------

    def test_the_tile_is_invoked_once_per_declared_tab(self) -> None:
        """The measurement that forced this shape, as a test.

        The five system collectors each fit a 5s budget and total 6.66s
        together, so a single invocation serving every tab would be killed on
        every load, permanently. Each declared tab is its own call, its own
        budget and its own failure.
        """
        self.register(
            self.plugin(
                "vv",
                tile_script(
                    """
                    import json, sys
                    name = sys.argv[1]
                    print(json.dumps({"title": name.upper(),
                                      "html": "<p>" + name + "</p>",
                                      "rows": [{"rank": 1, "kind": name,
                                                "id": "i", "what": "w"}]}))
                    """
                ),
                tabs=["toolbox", "vault", "briefs"],
            )
        )
        loaded = plugins.load()
        self.assertEqual([tab["name"] for tab in loaded["tabs"]],
                         ["toolbox", "vault", "briefs"])
        self.assertEqual([tab["title"] for tab in loaded["tabs"]],
                         ["TOOLBOX", "VAULT", "BRIEFS"])
        # Rows carry the tab they came from, not just the plugin: several tabs
        # behind one prefix would otherwise be one undifferentiated source.
        self.assertEqual(sorted(row["source"] for row in loaded["rows"]),
                         ["vv/briefs", "vv/toolbox", "vv/vault"])

    def test_one_failing_tab_does_not_silence_its_siblings(self) -> None:
        """The whole reason for per-tab invocation, asserted directly."""
        original = plugins.TILE_SECONDS
        plugins.TILE_SECONDS = 0.6
        self.addCleanup(lambda: setattr(plugins, "TILE_SECONDS", original))
        self.register(
            self.plugin(
                "uu",
                tile_script(
                    """
                    import json, sys, time
                    name = sys.argv[1]
                    if name == "slow":
                        time.sleep(30)
                    print(json.dumps({"rows": [{"rank": 1, "kind": name,
                                                "id": "i", "what": "w"}]}))
                    """
                ),
                tabs=["slow", "fast"],
            )
        )
        loaded = plugins.load()
        self.assertEqual([tab["name"] for tab in loaded["tabs"]], ["fast"])
        # The lost tab is a rank-0 row naming exactly which tab went dark.
        self.assertEqual([row["id"] for row in self.rows_of("plugin-dark", loaded)],
                         ["uu/slow"])
        # And the surviving tab's own row is still there.
        self.assertEqual(len(self.rows_of("fast", loaded)), 1)

    def test_a_title_the_tile_omits_falls_back_to_the_declared_name(self) -> None:
        self.register(self.plugin("tt", tile_script("print('{}')"), tabs=["ports"]))
        self.assertEqual(plugins.load()["tabs"][0]["title"], "ports")

    def test_a_non_string_title_is_named_and_the_declared_name_stands(self) -> None:
        self.register(
            self.plugin(
                "ss",
                tile_script('import json; print(json.dumps({"title": 7}))'),
                tabs=["ports"],
            )
        )
        loaded = plugins.load()
        self.assertEqual(loaded["tabs"][0]["title"], "ports")
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)

    def test_a_non_string_html_is_named_rather_than_coerced(self) -> None:
        """An empty tab that says nothing is the silence the module refuses.

        The tab survives, because its rows may be perfectly good; what must not
        happen is the markup vanishing without a word.
        """
        self.register(
            self.plugin(
                "oo",
                tile_script(
                    """
                    import json
                    print(json.dumps({"html": 42,
                        "rows": [{"rank": 1, "kind": "kept", "id": "i", "what": "w"}]}))
                    """
                ),
            )
        )
        loaded = plugins.load()
        self.assertEqual(loaded["tabs"][0]["html"], "")
        self.assertEqual(len(self.rows_of("kept", loaded)), 1)
        self.assertEqual(len(self.rows_of("plugin-refused", loaded)), 1)

    def test_the_byte_ceiling_is_applied_before_the_read_not_after(self) -> None:
        """`bounded_run` must not be handed more than one byte past its limit.

        Asserted on the returned length rather than on the refusal, because the
        refusal happens either way -- what this pins is that a small limit is
        not quietly rounded up to a full chunk before being consulted.
        """
        with self.assertRaises(plugins.Bounded):
            plugins.bounded_run(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100000)"],
                None,
                seconds=5.0,
                limit=32,
            )
        # The same command inside the limit returns exactly what it wrote.
        out = plugins.bounded_run(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 32)"],
            None,
            seconds=5.0,
            limit=32,
        )
        self.assertEqual(len(out), 32)

if __name__ == "__main__":
    unittest.main()
