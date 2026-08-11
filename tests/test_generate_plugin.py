"""Claude Code plugin generation from the machine-claude partition slice.

Four concerns, matching the four ways `.github/scripts/generate-plugin.py`
can go wrong:

* Mapping: the slice lands in the plugin layout (skills keep their tree,
  commands flatten under the `sd` plugin name, scripts become `bin/`
  executables), consumer-config rows never travel, and Markdown invocations
  lose their repository-root prefix.
* Self-containment: the bundled `installer/**`, the `machine-payload/**` tree
  it installs, and the `bin/` bootstrap that connects them are present, are
  siblings the way the engine resolves them, and actually run from the emitted
  tree with no pack checkout on `sys.path`.
* Fail-closed conditions: each of the eight documented conditions is exercised
  against a synthetic root, so a silently skipped row is impossible.
* Freshness and allowlist hygiene against the committed tree: `--check` is the
  CI gate, and both allowlists must stay in step with the payload they excuse.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from installer import machinepayload, machinescope, machinestage, references

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

try:
    import test_script_sibling_resolution as _sibling
except ModuleNotFoundError as exc:  # pragma: no cover - import shim
    if exc.name != "test_script_sibling_resolution":
        raise
    from . import test_script_sibling_resolution as _sibling

PACK_ROOT = _support.PACK_ROOT
InstallTestCase = _support.InstallTestCase

GENERATE_SCRIPT = PACK_ROOT / ".github/scripts/generate-plugin.py"
PLUGIN_ROOT = PACK_ROOT / "plugins/sd"
PARTITION_ARTIFACT = PACK_ROOT / "docs/fleet/surface-partition.json"

MACHINE_CLAUDE = "machine-claude"
MACHINE_OTHER = "machine-other"
CONSUMER_CONFIG = "consumer-config"

# The fixture's platforms, all machine-scope and none provisional: what a row
# is allowed to do is the partition's decision, and these tests are about the
# generator, so the gate is held open and exercised where it belongs
# (tests/test_machine_stage.py).
FIXTURE_PLATFORMS = {
    name: {"scope": "machine", "provisional": False}
    for name in ("claude", "shared", "gemini")
}

# A skill body carrying both rewrite forms: the `-f scripts/...` probe arm of
# the layout-neutral existence test, and a `node scripts/...` invocation.
# `bash` keeps its runner prefix (bash PATH-searches a slash-free operand).
SKILL_BODY = """# Thing

```bash
if ! command -v sd-ai-command-pack-probe.mjs >/dev/null 2>&1 \\
  && [ ! -f scripts/sd-ai-command-pack-probe.mjs ]; then
  printf '%s\\n' "error: sd-ai-command-pack-probe.mjs is not resolvable" >&2
fi
node scripts/sd-ai-command-pack-probe.mjs
bash scripts/sd-ai-command-pack-probe.sh
```
"""


def load_generator():
    # The generator defines module-scope dataclasses, whose decorator resolves
    # the module by name: sys.modules must hold it before exec_module runs.
    module = sys.modules.get("generate_plugin")
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location("generate_plugin", GENERATE_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin generator from {GENERATE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["generate_plugin"] = module
    spec.loader.exec_module(module)
    return module


def default_source(target: str, kind: str) -> str:
    """Where a manifest row of this kind authors its template."""

    if kind == "skill":
        return "templates/.agents/skills/" + target[len(".claude/skills/") :]
    if kind == "command":
        return "templates/.claude/commands/sd/" + target[len(".claude/commands/sd/") :]
    return "templates/" + target


class PluginFixtureCase(InstallTestCase):
    """Synthetic pack roots, small enough to reason about row by row."""

    def setUp(self) -> None:
        super().setUp()
        self.generator = load_generator()

    def baseline_rows(self) -> list[dict[str, object]]:
        return [
            {
                "target": ".claude/skills/sd-thing/SKILL.md",
                "kind": "skill",
                "content": SKILL_BODY,
            },
            {
                "target": ".claude/skills/sd-thing/references/notes.md",
                "kind": "skill",
                "content": "# Notes\n",
            },
            {
                "target": ".claude/commands/sd/thing.md",
                "kind": "command",
                "content": "Run the thing.\n",
            },
            {
                "target": "scripts/sd-ai-command-pack-probe.sh",
                "kind": "script",
                "content": "#!/usr/bin/env bash\nprintf 'probe\\n'\n",
            },
            {
                "target": "scripts/sd-ai-command-pack-probe.mjs",
                "kind": "script",
                "content": "#!/usr/bin/env node\nconsole.log('probe');\n",
            },
            {
                "target": "scripts/sd_ai_command_pack_lib.py",
                "kind": "script",
                "content": "VALUE = 1\n",
            },
            {
                "target": ".claude/rules/sd-thing.md",
                "kind": "config",
                "category": CONSUMER_CONFIG,
                "content": "# Rules\n",
            },
            # The machine slice: a shared `.agents` skill and one non-Claude
            # command adapter, so the bundled payload has both a rewritten body
            # and a second destination family. It authors its own source rather
            # than sharing the Claude skill's, so a test can remove one without
            # silently removing the other.
            {
                "target": ".agents/skills/sd-machine/SKILL.md",
                "kind": "skill",
                "platform": "shared",
                "category": MACHINE_OTHER,
                "source": "templates/.agents/skills/sd-machine/SKILL.md",
                "content": SKILL_BODY,
            },
            {
                "target": ".gemini/commands/sd/thing.toml",
                "kind": "command",
                "platform": "gemini",
                "category": MACHINE_OTHER,
                "source": "templates/.gemini/commands/sd/thing.toml",
                "content": 'prompt = "Run the thing."\n',
            },
        ]

    def build_root(
        self,
        rows: list[dict[str, object]] | None = None,
        *,
        version: str = "9.9.9",
        partition: bool = True,
    ) -> Path:
        entries = self.baseline_rows() if rows is None else rows
        tempdir = tempfile.TemporaryDirectory(prefix="sd-ai-command-pack-test-")
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        # The generator bundles the installer modules it finds under the root
        # it is pointed at, so a synthetic root carries the real package: the
        # bundled set is then the real import closure rather than a shape
        # invented by the fixture.
        shutil.copytree(
            PACK_ROOT / "installer",
            root / "installer",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

        manifest_rows: list[dict[str, str]] = []
        partition_rows: list[dict[str, object]] = []
        for row in entries:
            target = str(row["target"])
            kind = str(row["kind"])
            category = str(row.get("category", MACHINE_CLAUDE))
            source = str(row.get("source") or default_source(target, kind))
            if row.get("manifest", True):
                manifest_rows.append(
                    {
                        "platform": str(row.get("platform", "claude")),
                        "kind": kind,
                        "source": source,
                        "target": target,
                    }
                )
            partition_rows.append(
                {
                    "target": target,
                    "platform": str(row.get("platform", "claude")),
                    "kind": kind,
                    "category": category,
                    "sharedRuntime": target.startswith("scripts/"),
                }
            )
            if row.get("write", True):
                path = root / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(row.get("content", "# Thing\n")), encoding="utf-8")
            if target.startswith(".claude/commands/sd/") and row.get(
                "commandSource", True
            ):
                short = target[len(".claude/commands/sd/") : -len(".md")]
                authored = root / ".github/command-sources" / f"sd-{short}.md"
                authored.parent.mkdir(parents=True, exist_ok=True)
                authored.write_text(
                    str(row.get("commandSourceText", "---\ndescription: Do the thing.\n---\n\nbody\n")),
                    encoding="utf-8",
                )

        (root / "manifest.json").write_text(
            json.dumps({"version": version, "files": manifest_rows}, indent=2) + "\n",
            encoding="utf-8",
        )
        if partition:
            artifact = root / self.generator.PARTITION_PATH
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "manifestVersion": version,
                        "files": partition_rows,
                        "platforms": FIXTURE_PLATFORMS,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return root

    def patch_bin_allowlist(
        self, allowlist: dict[str, tuple[str, frozenset[str]]]
    ) -> None:
        """One allowlist, two payload builds, two module-level bindings."""

        for module in (self.generator, machinestage):
            # TestCase.enterContext needs Python 3.11+; CI still runs 3.10.
            patcher = mock.patch.object(module, "BIN_LITERAL_ALLOWLIST", allowlist)
            patcher.start()
            self.addCleanup(patcher.stop)

    def row_for(self, rows: list[dict[str, object]], target: str) -> dict[str, object]:
        """The fixture row for a target, so edits name what they change."""

        for row in rows:
            if row["target"] == target:
                return row
        raise AssertionError(f"fixture has no row for {target}")

    def native_paths(self, files: dict[str, object]) -> list[str]:
        """Only what this build maps itself, without the two bundled trees."""

        return sorted(path for path in files if self.generator.plugin_native(path))

    def written_tree(self, root: Path) -> dict[str, tuple[bytes, bool]]:
        """Everything under the written plugin, as content plus exec bit."""

        plugin_root = root / self.generator.PLUGIN_PATH
        found: dict[str, tuple[bytes, bool]] = {}
        for path in sorted(plugin_root.rglob("*")):
            if path.is_file():
                found[path.relative_to(plugin_root).as_posix()] = (
                    path.read_bytes(),
                    bool(path.stat().st_mode & 0o111),
                )
        return found


class PluginLayoutTests(PluginFixtureCase):
    """Slice rows land where the plugin runtime expects them."""

    def test_slice_rows_map_into_the_plugin_layout(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)

        self.assertEqual(
            self.native_paths(files),
            [
                ".claude-plugin/plugin.json",
                "bin/sd-ai-command-pack-probe.mjs",
                "bin/sd-ai-command-pack-probe.sh",
                "bin/sd-machine-install",
                "bin/sd_ai_command_pack_lib.py",
                "commands/thing.md",
                "skills/sd-thing/SKILL.md",
                "skills/sd-thing/references/notes.md",
            ],
        )

    def test_commands_flatten_and_gain_the_authored_description(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)
        command = files["commands/thing.md"].content.decode("utf-8")

        self.assertTrue(command.startswith("---\ndescription: Do the thing.\n---\n\n"))
        self.assertIn("Run the thing.", command)

    def test_executable_bit_separates_commands_from_libraries(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)

        self.assertTrue(files["bin/sd-ai-command-pack-probe.sh"].executable)
        self.assertTrue(files["bin/sd-ai-command-pack-probe.mjs"].executable)
        self.assertFalse(files["bin/sd_ai_command_pack_lib.py"].executable)
        self.assertFalse(files["skills/sd-thing/SKILL.md"].executable)
        self.assertFalse(files["commands/thing.md"].executable)

    def test_script_bytes_travel_unrewritten(self) -> None:
        """Only Markdown is rewritten; bin/ ships the authored payload."""

        root = self.build_root()
        source = root / "templates/scripts/sd-ai-command-pack-probe.sh"

        files = self.generator.build_files(root)

        self.assertEqual(
            files["bin/sd-ai-command-pack-probe.sh"].content, source.read_bytes()
        )

    def test_consumer_config_rows_never_reach_the_plugin(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)

        self.assertFalse([path for path in files if "rules" in path])
        for entry in files.values():
            self.assertNotIn(b"# Rules", entry.content)

    def test_rewrite_drops_the_repo_root_prefix_and_the_node_runner(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)
        skill = files["skills/sd-thing/SKILL.md"].content.decode("utf-8")

        self.assertIn("[ ! -f sd-ai-command-pack-probe.mjs ]", skill)
        self.assertIn("\nsd-ai-command-pack-probe.mjs\n", skill)
        self.assertNotIn("node sd-ai-command-pack-probe.mjs", skill)
        # bash PATH-searches a slash-free operand, so its prefix stays.
        self.assertIn("bash sd-ai-command-pack-probe.sh", skill)
        self.assertNotIn("scripts/", skill)

    def test_plugin_manifest_stamps_the_manifest_version(self) -> None:
        root = self.build_root(version="1.2.3")

        files = self.generator.build_files(root)
        manifest = json.loads(files[".claude-plugin/plugin.json"].content)

        self.assertEqual(manifest["version"], "1.2.3")
        self.assertEqual(manifest["name"], self.generator.PLUGIN_NAME)
        self.assertEqual(manifest["description"], self.generator.PLUGIN_DESCRIPTION)

    def test_build_is_deterministic(self) -> None:
        root = self.build_root()

        first = self.generator.build_files(root)
        second = self.generator.build_files(root)

        self.assertEqual(first, second)
        self.assertEqual(list(first), sorted(first))

    def test_materialized_output_is_byte_identical_across_runs(self) -> None:
        root = self.build_root()

        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        first = self.written_tree(root)
        # A rewrite from scratch, not the unchanged short circuit.
        shutil.rmtree(root / self.generator.PLUGIN_PATH)
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)

        self.assertEqual(self.written_tree(root), first)


class PluginSelfContainmentTests(PluginFixtureCase):
    """A machine with only the plugin still has the machine-scope installer."""

    def test_bundled_installer_is_the_engine_import_closure(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)
        bundled = {
            path[len("installer/") :]
            for path in files
            if path.startswith("installer/")
        }

        self.assertIn("machinescope.py", bundled)
        self.assertIn("__init__.py", bundled)
        # Transitive, through fileops: the walk follows imports, it does not
        # stop at the entry module's own line.
        self.assertIn("registry.py", bundled)
        # Fat-install modules nothing in that graph imports stay behind.
        self.assertNotIn("removal.py", bundled)
        self.assertNotIn("machinestage.py", bundled)

    def test_installer_and_payload_land_where_the_engine_looks(self) -> None:
        """The engine resolves its default payload beside its own package."""

        root = self.build_root()
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        plugin_root = root / self.generator.PLUGIN_PATH

        package = plugin_root / "installer" / "machinescope.py"
        payload = package.parent.parent / machinescope.DEFAULT_PAYLOAD_DIRNAME

        self.assertTrue(package.is_file())
        self.assertTrue((payload / machinepayload.PARTITION_FILE).is_file())

    def test_machine_payload_ships_rewritten_bodies_and_its_own_gate(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)
        skill = files["machine-payload/.agents/skills/sd-machine/SKILL.md"]
        body = skill.content.decode("utf-8")

        self.assertIn("~/.agents/bin/sd-ai-command-pack-probe.mjs", body)
        self.assertNotIn("scripts/", body)
        # The machine profile keeps the runner: it names a path, not a command.
        self.assertIn("node ~/.agents/bin/sd-ai-command-pack-probe.mjs", body)
        self.assertIn("machine-payload/.gemini/commands/sd/thing.toml", files)
        self.assertIn("machine-payload/partition.json", files)

    def test_machine_payload_keeps_the_family_executable_rule(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)

        self.assertTrue(
            files["machine-payload/scripts/sd-ai-command-pack-probe.sh"].executable
        )
        self.assertFalse(
            files["machine-payload/scripts/sd_ai_command_pack_lib.py"].executable
        )
        self.assertFalse(
            files["machine-payload/.agents/skills/sd-machine/SKILL.md"].executable
        )

    def test_bootstrap_is_an_executable_that_calls_the_engine(self) -> None:
        root = self.build_root()

        files = self.generator.build_files(root)
        bootstrap = files["bin/sd-machine-install"]

        self.assertTrue(bootstrap.executable)
        body = bootstrap.content.decode("utf-8")
        self.assertTrue(body.startswith("#!/usr/bin/env python3\n"))
        self.assertIn("from installer.machinescope import main", body)

    def test_bundled_trees_do_not_answer_to_the_plugin_rewrite_profile(self) -> None:
        """Their gates ran in their own profile; this one would misjudge them."""

        self.assertFalse(self.generator.plugin_native("machine-payload/docs/x.md"))
        self.assertFalse(self.generator.plugin_native("installer/machinescope.py"))
        self.assertTrue(self.generator.plugin_native("skills/sd-thing/SKILL.md"))
        self.assertTrue(self.generator.plugin_native("bin/sd-machine-install"))


class PluginFailClosedTests(PluginFixtureCase):
    """Each documented condition stops the build instead of shipping."""

    def test_slice_row_without_a_manifest_source_row_fails(self) -> None:
        rows = self.baseline_rows()
        rows[0]["manifest"] = False
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, "no manifest source row: .claude/skills/sd-thing"
        ):
            self.generator.build_files(root)

    def test_missing_template_source_fails(self) -> None:
        rows = self.baseline_rows()
        rows[0]["write"] = False
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, "cannot read template source"
        ):
            self.generator.build_files(root)

    def test_missing_command_source_fails(self) -> None:
        rows = self.baseline_rows()
        rows[2]["commandSource"] = False
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, "cannot read command source"
        ):
            self.generator.build_files(root)

    def test_command_source_without_a_description_fails(self) -> None:
        rows = self.baseline_rows()
        rows[2]["commandSourceText"] = "---\nname: thing\n---\n\nbody\n"
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, "missing frontmatter description"
        ):
            self.generator.build_files(root)

    def test_unmapped_kind_fails(self) -> None:
        rows = self.baseline_rows()
        rows.append(
            {
                "target": ".claude/agents/sd-thing.md",
                "kind": "agent",
                "source": "templates/.claude/agents/sd-thing.md",
                "content": "# Agent\n",
            }
        )
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, "unmapped machine-claude row: kind 'agent'"
        ):
            self.generator.build_files(root)

    def test_known_kind_under_an_unexpected_prefix_fails(self) -> None:
        rows = self.baseline_rows()
        rows.append(
            {
                "target": ".agents/skills/sd-elsewhere/SKILL.md",
                "kind": "skill",
                "source": "templates/.agents/skills/sd-elsewhere/SKILL.md",
                "content": "# Elsewhere\n",
            }
        )
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, r"unmapped machine-claude row: .*sd-elsewhere"
        ):
            self.generator.build_files(root)

    def test_markdown_residue_fails(self) -> None:
        rows = self.baseline_rows()
        # A glob is not an invocation, so no rewrite rule matches it.
        rows[1]["content"] = "Audit `scripts/sd-ai-command-pack-*.py` before release.\n"
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError,
            r"rewrite residue in skills/sd-thing/references/notes.md",
        ):
            self.generator.build_files(root)

    def test_bin_literal_outside_the_allowlist_fails(self) -> None:
        rows = self.baseline_rows()
        rows[3]["content"] = (
            "#!/usr/bin/env bash\nbash scripts/sd-ai-command-pack-other.sh\n"
        )
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError,
            "repository-root pack paths in bin/sd-ai-command-pack-probe.sh",
        ):
            self.generator.build_files(root)

    def test_bin_literal_on_the_allowlist_passes(self) -> None:
        rows = self.baseline_rows()
        rows[3]["content"] = (
            "#!/usr/bin/env bash\n# audits scripts/sd-ai-command-pack-other.sh\n"
        )
        root = self.build_root(rows)
        allowlist = {
            "sd-ai-command-pack-probe.sh": (
                "consumer-layout data: the probe reports on the repository it "
                "inspects, not on its own siblings",
                frozenset({"scripts/sd-ai-command-pack-other.sh"}),
            )
        }
        # The script ships in both payloads, and each build reads the allowlist
        # through its own module-level name, so an excuse has to reach both.
        self.patch_bin_allowlist(allowlist)

        files = self.generator.build_files(root)

        self.assertIn("bin/sd-ai-command-pack-probe.sh", files)
        self.assertIn("machine-payload/scripts/sd-ai-command-pack-probe.sh", files)

    def test_bin_allowlist_entry_without_a_justification_fails(self) -> None:
        rows = self.baseline_rows()
        rows[3]["content"] = (
            "#!/usr/bin/env bash\n# audits scripts/sd-ai-command-pack-other.sh\n"
        )
        root = self.build_root(rows)
        allowlist = {
            "sd-ai-command-pack-probe.sh": (
                "",
                frozenset({"scripts/sd-ai-command-pack-other.sh"}),
            )
        }

        with mock.patch.object(self.generator, "BIN_LITERAL_ALLOWLIST", allowlist):
            with self.assertRaisesRegex(
                self.generator.PluginError, "has no justification"
            ):
                self.generator.build_files(root)

    def test_markdown_reference_to_an_unshipped_command_fails(self) -> None:
        rows = self.baseline_rows()
        rows[1]["content"] = "Then run sd-ai-command-pack-absent.py to finish.\n"
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError,
            r"references sd-ai-command-pack-absent.py, which the plugin does not",
        ):
            self.generator.build_files(root)

    def test_closure_allowlist_accepts_a_justified_reference(self) -> None:
        rows = self.baseline_rows()
        rows[1]["content"] = "Then run sd-ai-command-pack-absent.py to finish.\n"
        root = self.build_root(rows)
        closure = {
            ("skills/sd-thing/references/notes.md", "sd-ai-command-pack-absent.py"): (
                "fleet-operator path: the script has no manifest row and is "
                "already absent from vendored consumer installs"
            )
        }

        with mock.patch.object(self.generator, "CLOSURE_ALLOWLIST", closure):
            files = self.generator.build_files(root)

        self.assertIn("skills/sd-thing/references/notes.md", files)

    def test_installer_module_without_a_file_fails(self) -> None:
        root = self.build_root()
        (root / "installer/machinescope.py").write_text(
            "from installer.absent import thing\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(
            self.generator.PluginError,
            r"imports installer/absent.py, which the plugin cannot bundle",
        ):
            self.generator.build_files(root)

    def test_installer_package_without_its_marker_fails(self) -> None:
        root = self.build_root()
        (root / "installer/__init__.py").unlink()

        with self.assertRaisesRegex(
            self.generator.PluginError, "the plugin bootstrap imports"
        ):
            self.generator.build_files(root)

    def test_relative_import_inside_the_installer_fails(self) -> None:
        """The bundle loads the package by absolute name, so it must be one."""

        root = self.build_root()
        (root / "installer/machinescope.py").write_text(
            "from . import fileops\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(
            self.generator.PluginError, "imports a sibling relatively"
        ):
            self.generator.build_files(root)

    def test_machine_row_without_a_destination_family_fails(self) -> None:
        rows = self.baseline_rows()
        rows.append(
            {
                "target": ".agents/agents/sd-thing.md",
                "kind": "agent",
                "platform": "shared",
                "category": MACHINE_OTHER,
                "source": "templates/.agents/agents/sd-thing.md",
                "content": "# Agent\n",
            }
        )
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError,
            r"machine payload: machine row has no destination family",
        ):
            self.generator.build_files(root)

    def test_machine_payload_closure_failure_fails_the_plugin_build(self) -> None:
        rows = self.baseline_rows()
        agents = self.row_for(rows, ".agents/skills/sd-machine/SKILL.md")
        agents["content"] = "Then run sd-ai-command-pack-absent.py to finish.\n"
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError,
            r"machine payload: .*references sd-ai-command-pack-absent.py",
        ):
            self.generator.build_files(root)

    def test_machine_payload_residue_fails_the_plugin_build(self) -> None:
        rows = self.baseline_rows()
        agents = self.row_for(rows, ".agents/skills/sd-machine/SKILL.md")
        # A glob is not an invocation, so no rewrite rule relocates it.
        agents["content"] = "Audit `scripts/sd-ai-command-pack-*.py` first.\n"
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, r"machine payload: rewrite residue"
        ):
            self.generator.build_files(root)

    def test_empty_manifest_version_fails(self) -> None:
        root = self.build_root(version="")

        with self.assertRaisesRegex(
            self.generator.PluginError, "has no version; the plugin version"
        ):
            self.generator.build_files(root)

    def test_missing_partition_artifact_fails(self) -> None:
        root = self.build_root(partition=False)

        with self.assertRaisesRegex(
            self.generator.PluginError, "surface partition not found"
        ):
            self.generator.build_files(root)

    def test_partition_without_machine_claude_rows_fails(self) -> None:
        rows = [row for row in self.baseline_rows() if row.get("category")]
        root = self.build_root(rows)

        with self.assertRaisesRegex(
            self.generator.PluginError, "holds no machine-claude rows"
        ):
            self.generator.build_files(root)

    def test_cli_reports_errors_without_raising(self) -> None:
        root = self.build_root(version="")

        self.assertEqual(self.generator.main(["--root", str(root)]), 1)


class PluginWriteTests(PluginFixtureCase):
    """Wholesale replacement, and what `--check` calls drift."""

    def test_write_then_check_is_idempotent(self) -> None:
        root = self.build_root()

        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        self.assertEqual(self.generator.main(["--check", "--root", str(root)]), 0)

    def test_write_removes_files_that_left_the_set(self) -> None:
        root = self.build_root()
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        stale = root / self.generator.PLUGIN_PATH / "skills/sd-gone/SKILL.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("# Gone\n", encoding="utf-8")

        self.assertEqual(self.generator.main(["--root", str(root)]), 0)

        self.assertFalse(stale.exists())
        self.assertFalse(stale.parent.exists())

    def test_check_reports_extraneous_committed_files(self) -> None:
        root = self.build_root()
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        extra = root / self.generator.PLUGIN_PATH / "skills/sd-gone/SKILL.md"
        extra.parent.mkdir(parents=True)
        extra.write_text("# Gone\n", encoding="utf-8")

        self.assertEqual(self.generator.main(["--check", "--root", str(root)]), 1)

    def test_check_reports_content_drift(self) -> None:
        root = self.build_root()
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        edited = root / self.generator.PLUGIN_PATH / "skills/sd-thing/SKILL.md"
        edited.write_text("# Hand edited\n", encoding="utf-8")

        self.assertEqual(self.generator.main(["--check", "--root", str(root)]), 1)

    def test_check_reports_executable_bit_drift(self) -> None:
        root = self.build_root()
        self.assertEqual(self.generator.main(["--root", str(root)]), 0)
        script = (
            root / self.generator.PLUGIN_PATH / "bin/sd-ai-command-pack-probe.sh"
        )
        script.chmod(0o644)

        self.assertEqual(self.generator.main(["--check", "--root", str(root)]), 1)

    def test_check_reports_a_missing_plugin_tree(self) -> None:
        root = self.build_root()

        self.assertEqual(self.generator.main(["--check", "--root", str(root)]), 1)


class CommittedPluginTreeTests(PluginFixtureCase):
    """The committed tree is the artifact CI and consumers actually read."""

    def test_check_mode_is_clean_on_committed_tree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATE_SCRIPT), "--check"],
            cwd=PACK_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            "plugins/sd drifts from the surface partition and templates; run "
            f"`make generate`:\n{result.stdout}{result.stderr}",
        )

    def test_committed_plugin_version_matches_the_manifest(self) -> None:
        manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        plugin = json.loads(
            (PLUGIN_ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
        )

        self.assertEqual(plugin["version"], manifest["version"])

    def test_committed_tree_carries_no_consumer_config_payload(self) -> None:
        """Neither under its own name nor renamed: content is checked too."""

        partition = json.loads(PARTITION_ARTIFACT.read_text(encoding="utf-8"))
        manifest = json.loads((PACK_ROOT / "manifest.json").read_text(encoding="utf-8"))
        sources = {row["target"]: row["source"] for row in manifest["files"]}
        shipped = [path for path in PLUGIN_ROOT.rglob("*") if path.is_file()]
        names = {path.name for path in shipped}
        contents = {path.read_bytes() for path in shipped}

        excluded = [
            entry["target"]
            for entry in partition["files"]
            if entry["category"] == CONSUMER_CONFIG
        ]
        self.assertTrue(any(t.startswith(".claude/rules/") for t in excluded))
        for target in excluded:
            with self.subTest(target=target):
                self.assertNotIn(Path(target).name, names)
                self.assertNotIn(
                    (PACK_ROOT / sources[target]).read_bytes(), contents
                )

    def test_committed_tree_holds_no_markdown_residue(self) -> None:
        offenders: dict[str, list[str]] = {}
        for path in sorted(PLUGIN_ROOT.rglob("*.md")):
            relative = path.relative_to(PLUGIN_ROOT).as_posix()
            if not self.generator.plugin_native(relative):
                continue
            found = sorted(
                {
                    match.rstrip(".")
                    for match in references.RESIDUE_RE.findall(
                        path.read_text(encoding="utf-8")
                    )
                }
            )
            if found:
                offenders[relative] = found

        self.assertEqual(offenders, {})

    def test_committed_machine_payload_holds_only_exempted_residue(self) -> None:
        """The bundled payload answers to the machine profile, so check that."""

        prefix = self.generator.MACHINE_PAYLOAD_PREFIX
        offenders: dict[str, str] = {}
        for path in sorted((PLUGIN_ROOT / "machine-payload").rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".toml"}:
                continue
            target = path.relative_to(PLUGIN_ROOT).as_posix()[len(prefix) :]
            try:
                references.check_text_residue(
                    target,
                    path.read_text(encoding="utf-8"),
                    profile=references.MACHINE_PROFILE,
                )
            except references.ReferenceRewriteError as error:
                offenders[target] = str(error)

        self.assertEqual(offenders, {})

    def bootstrap_report(self, entry: Path) -> dict[str, object]:
        """One dry-run install report, produced by running a bootstrap entry."""

        home = Path(tempfile.mkdtemp(prefix="sd-ai-command-pack-test-"))
        self.addCleanup(shutil.rmtree, home, ignore_errors=True)
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "XDG_CONFIG_HOME", "XDG_STATE_HOME"}
        }

        result = subprocess.run(
            [
                str(entry),
                "install",
                "--home",
                str(home),
                "--state-home",
                str(home / "state"),
                "--dry-run",
                "--json",
            ],
            # Anywhere but the pack: an implicit checkout on sys.path would
            # make a missing bundled module look like a working bootstrap.
            cwd=home,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_bootstrap_installs_the_bundled_payload_from_the_plugin_alone(
        self,
    ) -> None:
        """The self-containment claim, executed: no pack checkout in sight."""

        report = self.bootstrap_report(PLUGIN_ROOT / "bin/sd-machine-install")
        payload_root = PLUGIN_ROOT / "machine-payload"
        partition = json.loads(
            (payload_root / machinepayload.PARTITION_FILE).read_text(encoding="utf-8")
        )
        targets = machinepayload.payload_targets(payload_root)
        self.assertIsInstance(targets, list)
        self.assertTrue(report["dryRun"])
        self.assertEqual(report["packVersion"], partition["manifestVersion"])
        self.assertEqual(
            report["counts"], {str(machinescope.PlanStatus.ABSENT): len(targets)}
        )

    def test_bootstrap_resolves_its_own_root_through_a_symlink(self) -> None:
        """A linked plugin still installs the payload beside the code that ran.

        Plugin roots and their `bin/` entries are both reachable through links.
        The bootstrap derives its root from its own resolved file, so neither
        shape can point the engine at a payload from somewhere else -- and the
        linked-entry shape has no installer package beside it at all, so a
        bootstrap that trusted the link's parent would not even start.
        """

        scratch = Path(tempfile.mkdtemp(prefix="sd-ai-command-pack-test-"))
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        linked_root = scratch / "linked-root"
        linked_root.symlink_to(PLUGIN_ROOT)
        linked_entry = scratch / "sd-machine-install"
        linked_entry.symlink_to(PLUGIN_ROOT / "bin/sd-machine-install")

        direct = self.bootstrap_report(PLUGIN_ROOT / "bin/sd-machine-install")

        for entry in (linked_root / "bin/sd-machine-install", linked_entry):
            with self.subTest(entry=str(entry.relative_to(scratch))):
                report = self.bootstrap_report(entry)

                self.assertEqual(report["payloadDigest"], direct["payloadDigest"])
                self.assertEqual(report["packVersion"], direct["packVersion"])
                self.assertEqual(report["counts"], direct["counts"])


class AllowlistHygieneTests(PluginFixtureCase):
    """Both allowlists must describe the payload as it ships today."""

    def test_bin_allowlist_matches_the_sibling_resolution_allowlist(self) -> None:
        """One decision, recorded twice: the copies may not diverge."""

        self.assertEqual(
            self.generator.BIN_LITERAL_ALLOWLIST, _sibling.ALLOWED_LITERALS
        )

    def test_every_bin_allowlist_literal_still_occurs_in_its_file(self) -> None:
        stale: dict[str, list[str]] = {}
        for name, (_justification, allowed) in (
            self.generator.BIN_LITERAL_ALLOWLIST.items()
        ):
            path = PLUGIN_ROOT / "bin" / name
            self.assertTrue(path.is_file(), f"allowlisted script is missing: {name}")
            found = {
                match.rstrip(".")
                for match in references.RESIDUE_RE.findall(
                    path.read_text(encoding="utf-8")
                )
            }
            unused = sorted(allowed - found)
            if unused:
                stale[name] = unused

        self.assertEqual(
            stale, {}, f"remove converted literals from BIN_LITERAL_ALLOWLIST: {stale}"
        )

    def test_every_closure_allowlist_reference_still_occurs(self) -> None:
        stale: list[str] = []
        for (path, command), justification in (
            self.generator.CLOSURE_ALLOWLIST.items()
        ):
            self.assertGreater(len(justification.split()), 5, path)
            shipped = PLUGIN_ROOT / path
            self.assertTrue(shipped.is_file(), f"allowlisted Markdown is missing: {path}")
            if command not in shipped.read_text(encoding="utf-8"):
                stale.append(f"{path}: {command}")

        self.assertEqual(
            stale, [], f"remove resolved references from CLOSURE_ALLOWLIST: {stale}"
        )


if __name__ == "__main__":
    unittest.main()
