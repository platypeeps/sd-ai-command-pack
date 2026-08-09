"""Claude Code plugin generation from the machine-claude partition slice.

Three concerns, matching the three ways `.github/scripts/generate-plugin.py`
can go wrong:

* Mapping: the slice lands in the plugin layout (skills keep their tree,
  commands flatten under the `sd` plugin name, scripts become `bin/`
  executables), consumer-config rows never travel, and Markdown invocations
  lose their repository-root prefix.
* Fail-closed conditions: each of the six documented conditions is exercised
  against a synthetic root, so a silently skipped row is impossible.
* Freshness and allowlist hygiene against the committed tree: `--check` is the
  CI gate, and both allowlists must stay in step with the payload they excuse.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
CONSUMER_CONFIG = "consumer-config"

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
            if kind == "command" and row.get("commandSource", True):
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
                    {"schemaVersion": 1, "manifestVersion": version, "files": partition_rows},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return root

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
            sorted(files),
            [
                ".claude-plugin/plugin.json",
                "bin/sd-ai-command-pack-probe.mjs",
                "bin/sd-ai-command-pack-probe.sh",
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

        with mock.patch.object(self.generator, "BIN_LITERAL_ALLOWLIST", allowlist):
            files = self.generator.build_files(root)

        self.assertIn("bin/sd-ai-command-pack-probe.sh", files)

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
            found = sorted(
                {
                    match.rstrip(".")
                    for match in self.generator.RESIDUE_RE.findall(
                        path.read_text(encoding="utf-8")
                    )
                }
            )
            if found:
                offenders[path.relative_to(PLUGIN_ROOT).as_posix()] = found

        self.assertEqual(offenders, {})


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
                for match in self.generator.RESIDUE_RE.findall(
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
