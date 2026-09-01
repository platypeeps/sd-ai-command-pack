"""Fixtures for `sd plugin`: real manifests, real config files, real exits.

Every case runs `bin/sd` as a subprocess with `XDG_CONFIG_HOME` pointed at a
temporary directory, so the machine config under test is never the developer's
own and the exit code asserted is the exit code a caller sees.

Two cases are load-bearing.

`test_an_unrelated_config_key_survives_registration`: `sd plugin add` is the
first thing in this pack that *writes* the machine config -- until now
`sd_lib.machine_config` only read it -- and that file already holds settings
this command knows nothing about. A registration that dropped them would be
the framework damaging state it does not own.

`test_a_manifest_edit_is_seen_without_re-registering`: the registry stores a
path, and everything else is read from the manifest at use time. If that ever
regresses to caching the manifest's contents, this is the test that fails --
and the failure it catches is a plugin editing its manifest while every reader
goes on seeing the values captured at registration.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = REPO_ROOT / "bin" / "sd"

# The eight keys, written here as a literal on purpose. Standing rule 2 fixes
# the plugin-kind vocabulary at eight and makes a change to it a decision
# record; a test that read the set out of `bin/sd` would agree with whatever
# the source said and pin nothing. This is the assertion that a ninth key
# cannot arrive quietly -- `RefusalTests.test_every_key_in_the_vocabulary_is_
# validated` is the one that reads the source, and it enumerates from there so
# a key added without a validator fails rather than passes.
THE_EIGHT_KEYS = {
    "fields", "initial-status", "protected-fields", "transitions",
    "human-only", "unique-fields", "floor", "sections",
}

# A kind that satisfies every check, so a case can break exactly one thing.
WELL_FORMED_KIND: dict[str, object] = {
    "fields": ["status", "score", "my-rating"],
    "initial-status": "inbox",
    "protected-fields": ["my-rating"],
    "transitions": {"inbox": ["approved", "declined"], "approved": ["published"]},
    "human-only": {"approve": "approved", "decline": "declined"},
    "unique-fields": ["status"],
    "floor": {"score": 6},
    "sections": {"order": ["Body", "Provenance"], "template": "templates/tip.md"},
}


def load_sd():
    """`bin/sd` as a module. It has no suffix, so import needs the long way."""

    spec = importlib.util.spec_from_loader(
        "sd_cli", importlib.machinery.SourceFileLoader("sd_cli", str(SD)))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PluginFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        # `sd plugin add` stores the canonical path, so one checkout cannot
        # register twice under two spellings. On macOS that resolves
        # /var -> /private/var, so the fixture resolves too or every path
        # comparison here fails on the symlink rather than on behaviour.
        self.tmp = pathlib.Path(self._tmp.name).resolve()
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

    def kinded(self, name: str = "pack", *, kind: dict[str, object] | None = None,
               **manifest: object) -> pathlib.Path:
        """A plugin whose `kinds.tip` is well formed, with its files on disk.

        The template and the vendored directory are written for real because
        the reader checks that both exist. A manifest naming a template that
        is not there is exactly the failure registration is the cheapest place
        to catch, and a fixture that faked the file would test the opposite.
        """

        root = self.tmp / name
        (root / "templates").mkdir(parents=True, exist_ok=True)
        (root / "templates" / "tip.md").write_text("# {title}\n", encoding="utf-8")
        (root / "vendor").mkdir(parents=True, exist_ok=True)
        (root / "vendor" / "upstream.py").write_text("print('hi')\n", encoding="utf-8")
        body = dict(WELL_FORMED_KIND) if kind is None else kind
        return self.plugin(name, kinds={"tip": body}, **manifest)

    def write_config(self, payload: dict[str, object]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(payload), encoding="utf-8")

    def config(self) -> dict[str, object]:
        return json.loads(self.config_path.read_text(encoding="utf-8"))


class AddTests(PluginFixture):
    def listed(self) -> list[dict[str, object]]:
        result = self.run_sd("plugin", "list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return list(json.loads(result.stdout))

    def test_a_registration_round_trips_through_list(self) -> None:
        added = self.run_sd("plugin", "add", str(self.plugin()))
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertEqual([e["prefix"] for e in self.listed()], ["pp"])

    def test_the_registry_stores_a_path_and_not_the_manifest(self) -> None:
        self.assertEqual(self.run_sd("plugin", "add", str(self.plugin())).returncode, 0)
        self.assertEqual(self.config()["plugins"], [str(self.tmp / "pack")])

    def test_a_manifest_edit_is_seen_without_re_registering(self) -> None:
        root = self.plugin()
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        self.assertIsNone(self.listed()[0].get("tile"))
        (root / "sd-plugin.json").write_text(
            json.dumps({"prefix": "pp", "dashboard": {"tile": "./bin/tile",
                        "tabs": ["one"]}}), encoding="utf-8"
        )
        self.assertEqual(self.listed()[0]["tile"], "./bin/tile")
        self.assertEqual(self.listed()[0]["tabs"], ["one"])

    def test_an_unreadable_root_is_reported_rather_than_hidden(self) -> None:
        root = self.plugin()
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        (root / "sd-plugin.json").unlink()
        entry = self.listed()[0]
        self.assertFalse(entry["readable"])
        result = self.run_sd("plugin", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UNREADABLE", result.stdout)

    def test_an_unreadable_root_does_not_block_another_registration(self) -> None:
        broken = self.plugin("broken")
        self.assertEqual(self.run_sd("plugin", "add", str(broken)).returncode, 0)
        (broken / "sd-plugin.json").unlink()
        other = self.plugin("other", prefix="qq")
        self.assertEqual(self.run_sd("plugin", "add", str(other)).returncode, 0)

    def test_an_unrelated_config_key_survives_registration(self) -> None:
        self.write_config({"google": {"accounts": {"personal": {"roles": ["mail_send"]}}}})
        result = self.run_sd("plugin", "add", str(self.plugin()))
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.config()
        self.assertEqual(config["google"], {"accounts": {"personal": {"roles": ["mail_send"]}}})
        self.assertEqual(config["plugins"], [str(self.tmp / "pack")])

    def test_the_manifest_may_be_named_directly(self) -> None:
        manifest = self.plugin() / "sd-plugin.json"
        self.assertEqual(self.run_sd("plugin", "add", str(manifest)).returncode, 0)

    def test_the_tile_command_is_reported_when_declared(self) -> None:
        root = self.plugin(dashboard={"tile": "./bin/tile", "tabs": ["one", "two"]})
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        self.assertEqual(self.listed()[0]["tile"], "./bin/tile")
        self.assertEqual(self.listed()[0]["tabs"], ["one", "two"])

    def test_a_manifest_declaring_every_block_registers(self) -> None:
        """The inverse of what 6b-1 asserted, and the point of step 8-i.

        Until this step the case here was
        `test_keys_this_slice_does_not_enforce_are_left_alone`, which
        registered `{"tip": {"floor": 3, "sections": ["Body"], "nonsense":
        True}}` and asserted it was accepted -- `kinds` was read and carried,
        never enforced (R11-D13). All three of those values now refuse: the
        vocabulary is closed, `floor` names the field it bounds, and
        `sections` carries the template that renders it. The old test is not
        edited to pass; it is replaced by its opposite, and
        `RefusalTests.test_the_shape_6b_accepted_is_now_refused` keeps the
        superseded manifest around as the record of what changed.
        """

        root = self.kinded(issues={"repo": "o/r"},
                           vendor={"up": {"source": "o/up", "path": "vendor"}})
        added = self.run_sd("plugin", "add", str(root))
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertEqual(self.config()["plugins"], [str(root)])
        entry = self.listed()[0]
        self.assertEqual(entry["kinds"], ["tip"])
        self.assertEqual(entry["issues"], "o/r")
        self.assertEqual(entry["vendor"], ["up"])


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

    def test_a_tile_without_tabs_refuses(self) -> None:
        """The loader invokes the tile once per tab, so it must be told which.

        A tile with nothing to serve is a registration that would silently
        contribute no view, which is worth catching at the registry rather
        than discovering as an empty dashboard.
        """
        done = self.run_sd(
            "plugin", "add", str(self.plugin(dashboard={"tile": "./bin/tile"}))
        )
        self.assertEqual(done.returncode, 1)
        self.assertIn("no `dashboard.tabs`", done.stderr)

    def test_a_tab_name_shaped_like_a_flag_refuses(self) -> None:
        """A name reaches the tile as an argument and must not read as one."""
        done = self.run_sd(
            "plugin",
            "add",
            str(self.plugin(dashboard={"tile": "./bin/tile", "tabs": ["--help"]})),
        )
        self.assertEqual(done.returncode, 1)
        self.assertIn("tab name", done.stderr)

    def test_a_repeated_tab_name_refuses(self) -> None:
        done = self.run_sd(
            "plugin",
            "add",
            str(self.plugin(dashboard={"tile": "./bin/tile", "tabs": ["a", "a"]})),
        )
        self.assertEqual(done.returncode, 1)
        self.assertIn("declared twice", done.stderr)

    def test_a_tile_that_is_not_a_command_refuses(self) -> None:
        self.assert_refused(
            "plugin", "add", str(self.plugin(dashboard={"tile": ""})),
            because="not a non-empty command string",
        )

    def test_a_malformed_machine_config_refuses(self) -> None:
        self.write_config({"plugins": {"pp": {"root": "/somewhere"}}})
        self.assert_refused(
            "plugin", "add", str(self.plugin()), because="`plugins` is not a list of paths"
        )

    def test_the_shape_6b_accepted_is_now_refused(self) -> None:
        """The exact manifest 6b-1's test registered, kept as the record.

        `{"tip": {"floor": 3, "sections": ["Body"], "nonsense": True}}` was a
        passing case one step ago, because `kinds` was read and carried and
        never enforced. It is three refusals now, and keeping the literal here
        is what makes the change legible: a reader comparing the two steps
        sees the manifest, not a sentence about it.
        """

        root = self.plugin(kinds={"tip": {"floor": 3, "sections": ["Body"], "nonsense": True}})
        self.assert_refused("plugin", "add", str(root),
                            because="outside the closed vocabulary")

    def test_registering_one_root_twice_refuses(self) -> None:
        root = self.plugin()
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        self.assert_refused("plugin", "add", str(root), because="already registered")


class KindTests(PluginFixture):
    """The closed vocabulary, and the consistency checks inside one kind."""

    def add_kind(self, **changes: object) -> subprocess.CompletedProcess[str]:
        kind = dict(WELL_FORMED_KIND)
        for key, value in changes.items():
            spelled = key.replace("_", "-")
            if value is None:
                kind.pop(spelled, None)
            else:
                kind[spelled] = value
        return self.run_sd("plugin", "add", str(self.kinded(kind=kind)))

    def assert_kind_refused(self, because: str, **changes: object) -> None:
        result = self.add_kind(**changes)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(because, result.stderr)

    def test_the_vocabulary_is_eight_keys(self) -> None:
        """Standing rule 2, as an assertion rather than a sentence.

        The count and the names both, because the rule fixes both: a rename
        that kept the count at eight would still be a vocabulary change, and
        this is the test that makes somebody write the decision record.
        """

        self.assertEqual(set(load_sd().KIND_KEYS), THE_EIGHT_KEYS)
        self.assertEqual(len(THE_EIGHT_KEYS), 8)

    def test_a_ninth_key_refuses(self) -> None:
        result = self.add_kind(nonsense=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("outside the closed vocabulary", result.stderr)
        self.assertIn("nonsense", result.stderr)

    def test_every_key_in_the_vocabulary_is_validated(self) -> None:
        """Enumerated from `bin/sd`, so an unvalidated ninth key fails here.

        Each key is handed a value of the wrong type and the registration must
        refuse. A key added to `KIND_KEYS` with no validator behind it accepts
        the junk, and this is what says so -- the alternative, a list of cases
        written by hand, tests only the keys somebody remembered.
        """

        for key in sorted(load_sd().KIND_KEYS):
            with self.subTest(key=key):
                kind = dict(WELL_FORMED_KIND)
                kind[key] = 12345
                result = self.run_sd("plugin", "add", str(self.kinded(kind=kind)))
                self.assertEqual(result.returncode, 1,
                                 f"{key} accepted an integer: {result.stdout}")

    def test_both_required_keys_are_required(self) -> None:
        for key in ("fields", "initial-status"):
            with self.subTest(key=key):
                self.assert_kind_refused("declares no", **{key.replace("-", "_"): None})

    def test_the_six_optional_keys_are_optional(self) -> None:
        """A kind with only `fields` and `initial-status` is a kind.

        The verb that needs `sections` refuses when it is asked to render, and
        that refusal belongs to the verb: registration validating what a
        plugin's own commands never call would reject well-formed manifests
        for a capability they do not want.
        """

        kind = {"fields": ["status"], "initial-status": "inbox"}
        result = self.run_sd("plugin", "add", str(self.kinded(kind=kind)))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_protected_field_the_kind_does_not_have_refuses(self) -> None:
        """The vacuous-check failure, caught at the one place it is cheap.

        `protected-fields: ["my_rating"]` against a kind whose field is
        `my-rating` protects nothing and reads in review as though it protects
        something. This rollout has already shipped three gates that certified
        nothing for exactly this reason.
        """

        self.assert_kind_refused("not one of the kind's `fields`",
                                 protected_fields=["my_rating"])

    def test_a_unique_field_the_kind_does_not_have_refuses(self) -> None:
        self.assert_kind_refused("not one of the kind's `fields`", unique_fields=["absent"])

    def test_a_floor_on_a_field_the_kind_does_not_have_refuses(self) -> None:
        self.assert_kind_refused("not one of the kind's `fields`", floor={"absent": 6})

    def test_a_boolean_floor_refuses(self) -> None:
        """`isinstance(True, int)` is true, so this needs its own exclusion.

        Without it `"floor": {"score": true}` registers as a minimum of 1 --
        a floor that is on, reads as configured, and stops nothing.
        """

        self.assert_kind_refused("not a number", floor={"score": True})

    def test_an_initial_status_no_transition_mentions_refuses(self) -> None:
        self.assert_kind_refused("no transition mentions", initial_status="nowhere")

    def test_a_human_only_target_no_transition_mentions_refuses(self) -> None:
        self.assert_kind_refused("no transition mentions",
                                 human_only={"approve": "nowhere"})

    def test_a_self_transition_refuses(self) -> None:
        self.assert_kind_refused("transitions to itself",
                                 transitions={"inbox": ["inbox"]},
                                 initial_status="inbox",
                                 human_only={"approve": "inbox"})

    def test_sections_without_a_template_refuses(self) -> None:
        self.assert_kind_refused("declares no `template`", sections={"order": ["Body"]})

    def test_a_template_that_is_not_there_refuses(self) -> None:
        self.assert_kind_refused(
            "does not exist",
            sections={"order": ["Body"], "template": "templates/absent.md"})

    def test_a_directory_where_the_template_should_be_refuses(self) -> None:
        """Existence is not the check. Found by review on #678.

        A directory at `templates/tip.md` satisfies "it is there" and fails
        the moment somebody renders a note -- the deferral registration is
        supposed to prevent. `vendor.*.path` keeps taking either, because a
        vendored tree is the ordinary case there.
        """

        root = self.kinded()
        (root / "templates" / "tip.md").unlink()
        (root / "templates" / "tip.md").mkdir()
        result = self.run_sd("plugin", "add", str(root))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("is not a regular file", result.stderr)

    def test_a_vendored_path_may_be_a_directory_or_a_file(self) -> None:
        for path in ("vendor", "vendor/upstream.py"):
            with self.subTest(path=path):
                root = self.kinded(f"v-{path.replace('/', '-')}",
                                   vendor={"up": {"source": "o/up", "path": path}})
                result = self.run_sd("plugin", "add", str(root))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.run_sd("plugin", "lock", str(root)).returncode, 0)
                self.write_config({})

    def test_a_template_outside_the_checkout_refuses(self) -> None:
        for escape in ("../../etc/passwd", "/etc/passwd"):
            with self.subTest(path=escape):
                result = self.add_kind(sections={"order": ["Body"], "template": escape})
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("inside the plugin", result.stderr)

    def test_a_template_symlinked_out_of_the_checkout_refuses(self) -> None:
        """The escape a `..` check cannot see.

        `templates/tip.md` may be a relative path with no `..` in it and still
        be a link to somewhere else on the machine, so the check resolves
        before it compares.
        """

        outside = self.tmp / "elsewhere.md"
        outside.write_text("# elsewhere\n", encoding="utf-8")
        root = self.kinded()
        link = root / "templates" / "linked.md"
        link.symlink_to(outside)
        kind = dict(WELL_FORMED_KIND)
        kind["sections"] = {"order": ["Body"], "template": "templates/linked.md"}
        (root / "sd-plugin.json").write_text(
            json.dumps({"prefix": "pp", "kinds": {"tip": kind}}), encoding="utf-8")
        result = self.run_sd("plugin", "add", str(root))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("outside the plugin checkout", result.stderr)

    def test_a_path_the_filesystem_cannot_express_refuses_instead_of_crashing(self) -> None:
        """A NUL byte in a declared path is a refusal, not a traceback.

        One of two faults `resolve()` cannot answer for. This one JSON can
        write and no filesystem can hold, and it raises `ValueError` on 3.9
        and 3.14 alike. Its sibling below is the symlink loop.
        """

        result = self.add_kind(sections={"order": ["Body"], "template": "templates/a\u0000b.md"})
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not a usable path", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_symlink_loop_refuses_on_every_interpreter_rather_than_crashing(self) -> None:
        """The fault whose *class* changes with the interpreter.

        `resolve()` raises `RuntimeError("Symlink loop from ...")` on
        3.10-3.12 and returns the link itself on 3.9 and 3.13+, where the
        refusal then comes from `exists()` instead. So the assertion is the
        refusal and the absence of a traceback, not one particular sentence:
        pinning the 3.13 wording would turn a version difference into a red
        build, and pinning neither is how this shipped crashing on the one
        interpreter CI was already running.
        """

        root = self.kinded()
        first, second = root / "templates" / "one.md", root / "templates" / "two.md"
        first.symlink_to(second)
        second.symlink_to(first)
        kind = dict(WELL_FORMED_KIND)
        kind["sections"] = {"order": ["Body"], "template": "templates/one.md"}
        (root / "sd-plugin.json").write_text(
            json.dumps({"prefix": "pp", "kinds": {"tip": kind}}), encoding="utf-8")
        result = self.run_sd("plugin", "add", str(root))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("sections.template", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_an_empty_kinds_block_refuses(self) -> None:
        result = self.run_sd("plugin", "add", str(self.plugin(kinds={})))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not a non-empty object", result.stderr)

    def test_a_manifest_with_no_kinds_is_untouched(self) -> None:
        """Absent is not an error. The `sys` plugin declares no kinds today."""

        self.assertEqual(self.run_sd("plugin", "add", str(self.plugin())).returncode, 0)

    def test_a_kind_that_goes_bad_after_registration_is_reported(self) -> None:
        root = self.kinded()
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        (root / "templates" / "tip.md").unlink()
        listed = self.run_sd("plugin", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("manifest:", listed.stdout)
        self.assertIn("does not exist", listed.stdout)


class IssuesAndVendorTests(PluginFixture):
    def assert_refused(self, root: pathlib.Path, because: str) -> None:
        result = self.run_sd("plugin", "add", str(root))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(because, result.stderr)

    def test_a_repo_that_is_not_owner_slash_name_refuses(self) -> None:
        for bad in ("justname", "o/r/extra", "o /r"):
            with self.subTest(repo=bad):
                self.assert_refused(self.plugin(issues={"repo": bad}), "not owner/name")

    def test_an_issues_block_with_no_repo_refuses(self) -> None:
        self.assert_refused(self.plugin(issues={"tracker": "jira"}), "declares no `repo`")

    def test_a_vendor_entry_needs_a_source_and_a_path(self) -> None:
        root = self.kinded("v1", vendor={"up": {"path": "vendor"}})
        self.assert_refused(root, "declares no `source`")
        root = self.kinded("v2", vendor={"up": {"source": "o/up"}})
        self.assert_refused(root, "is not a non-empty path")

    def test_a_vendored_path_outside_the_checkout_refuses(self) -> None:
        root = self.kinded("v3", vendor={"up": {"source": "o/up", "path": "../elsewhere"}})
        self.assert_refused(root, "inside the plugin")


class LockTests(PluginFixture):
    def test_lock_writes_a_pin_for_the_manifest_and_each_vendor_entry(self) -> None:
        root = self.kinded(vendor={"up": {"source": "o/up", "path": "vendor"}})
        done = self.run_sd("plugin", "lock", str(root))
        self.assertEqual(done.returncode, 0, done.stderr)
        lock = json.loads((root / "sd-plugin.lock").read_text(encoding="utf-8"))
        self.assertTrue(lock["manifest"].startswith("sha256:"))
        self.assertTrue(lock["vendor"]["up"]["hash"].startswith("sha256:"))
        self.assertEqual(lock["vendor"]["up"]["source"], "o/up")

    def test_check_passes_on_an_unchanged_checkout(self) -> None:
        root = self.kinded(vendor={"up": {"source": "o/up", "path": "vendor"}})
        self.assertEqual(self.run_sd("plugin", "lock", str(root)).returncode, 0)
        done = self.run_sd("plugin", "lock", str(root), "--check")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("matches its sd-plugin.lock", done.stdout)

    def test_a_changed_manifest_is_named_by_check(self) -> None:
        """The gap 6b-6 recorded: a registration whose manifest moved under it.

        Actions and tabs are fixed in the manifest and never sent by the page,
        which is what "pinned" meant then. This is the other half -- the
        manifest itself no longer changes unnoticed.
        """

        root = self.kinded()
        self.assertEqual(self.run_sd("plugin", "lock", str(root)).returncode, 0)
        manifest = json.loads((root / "sd-plugin.json").read_text(encoding="utf-8"))
        manifest["dashboard"] = {"tile": "./tile", "tabs": ["new"]}
        (root / "sd-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        done = self.run_sd("plugin", "lock", str(root), "--check")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("sd-plugin.json changed", done.stderr)

    def test_changed_vendored_content_is_named_by_check(self) -> None:
        root = self.kinded(vendor={"up": {"source": "o/up", "path": "vendor"}})
        self.assertEqual(self.run_sd("plugin", "lock", str(root)).returncode, 0)
        (root / "vendor" / "upstream.py").write_text("print('changed')\n", encoding="utf-8")
        done = self.run_sd("plugin", "lock", str(root), "--check")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("vendor.up changed", done.stderr)

    def test_a_renamed_file_inside_a_vendored_tree_is_drift(self) -> None:
        """Path and content are both hashed, so a pure rename is not free."""

        root = self.kinded(vendor={"up": {"source": "o/up", "path": "vendor"}})
        self.assertEqual(self.run_sd("plugin", "lock", str(root)).returncode, 0)
        (root / "vendor" / "upstream.py").rename(root / "vendor" / "renamed.py")
        self.assertEqual(self.run_sd("plugin", "lock", str(root), "--check").returncode, 1)

    def test_a_symlink_in_a_vendored_tree_refuses(self) -> None:
        root = self.kinded(vendor={"up": {"source": "o/up", "path": "vendor"}})
        (root / "vendor" / "link.py").symlink_to(self.tmp / "absent.py")
        done = self.run_sd("plugin", "lock", str(root))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("symlink", done.stderr)

    def test_check_without_a_lock_refuses_rather_than_passing(self) -> None:
        """A missing lock is not a clean one, and this is the difference.

        `--check` is what a plugin's CI runs. Exiting 0 because nothing was
        ever pinned is the shape of gate this rollout has now removed three
        of.
        """

        root = self.kinded()
        done = self.run_sd("plugin", "lock", str(root), "--check")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("run `sd plugin lock` first", done.stderr)

    def test_reordering_the_manifests_keys_is_drift(self) -> None:
        """Bytes, not the parsed object.

        A lock over `json.loads(...)` goes on matching after a key is
        reordered -- a diff the reviewer sees and the lock does not.
        """

        root = self.kinded()
        self.assertEqual(self.run_sd("plugin", "lock", str(root)).returncode, 0)
        manifest = json.loads((root / "sd-plugin.json").read_text(encoding="utf-8"))
        (root / "sd-plugin.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        self.assertEqual(self.run_sd("plugin", "lock", str(root), "--check").returncode, 1)


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
