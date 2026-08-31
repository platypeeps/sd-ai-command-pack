"""The `agents/` tree and how the installer renders it.

Agents are the taxonomy's third kind: a bounded worker with context isolation
and a declared tool set. The declaration is the whole governance mechanism --
an agent whose prose says "read-only" and whose frontmatter says nothing is an
agent the platform will hand every tool it has -- so the contract is asserted
here rather than trusted.

The fold that brought these five in is exactly where that could have been lost.
Their upstream templates carried no `tools:` at all for two of the five; the
governed versions existed only as files somebody had edited in place under
`~/.claude/agents`, which the next install from upstream would have overwritten.
These tests are what makes that a red check instead of a quiet regression.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS = REPO_ROOT / "agents"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "sd_install_agents", REPO_ROOT / "bin" / "sd_install.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_install = load_module()

# Tools that can change the working tree. An agent describing itself as
# read-only must not hold one; `Bash` is deliberately not in this set, because
# it is how a reviewer runs `cargo check` and excluding it would either fail a
# correct agent or push the check into prose.
WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})


def frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    """The leading `---` block as scalars plus the `tools:` list.

    The same flat-scalar subset the rest of the pack parses (D-C1), with one
    addition: `tools:` is the one list-valued key an agent carries, so it is
    read as a list here rather than pretending the file is flat.
    """

    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "no frontmatter"
    fields: dict[str, str] = {}
    tools: list[str] = []
    in_tools = False
    for line in lines[1:]:
        if line.strip() == "---":
            return fields, tools
        if in_tools and line.lstrip().startswith("- "):
            tools.append(line.split("- ", 1)[1].strip())
            continue
        in_tools = False
        key, separator, value = line.partition(":")
        if separator and not key.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
            in_tools = key.strip() == "tools"
    raise AssertionError("unterminated frontmatter")


def agent_files() -> list[Path]:
    return sorted(AGENTS.glob("sd-*.md")) if AGENTS.is_dir() else []


class ContractTests(unittest.TestCase):
    def test_there_are_agents_to_check(self) -> None:
        # Without this every assertion below passes over an empty list.
        self.assertGreater(len(agent_files()), 1, "agents/ enumerated to almost nothing")

    def test_the_name_matches_the_file(self) -> None:
        for path in agent_files():
            with self.subTest(agent=path.name):
                fields, _ = frontmatter(path.read_text(encoding="utf-8"))
                self.assertEqual(fields.get("name"), path.stem)

    def test_every_agent_declares_tools(self) -> None:
        """The taxonomy's marker for this kind, and the reason for the fold's care."""

        for path in agent_files():
            with self.subTest(agent=path.name):
                _, tools = frontmatter(path.read_text(encoding="utf-8"))
                self.assertTrue(tools, f"{path.name} declares no tools")

    def test_a_read_only_agent_holds_no_write_tool(self) -> None:
        """Prose and frontmatter must agree about authority.

        Scoped to agents that say "read-only" about themselves, so it checks a
        claim the file makes rather than imposing one it never made.
        """

        checked = 0
        for path in agent_files():
            text = path.read_text(encoding="utf-8")
            fields, tools = frontmatter(text)
            if "read-only" not in fields.get("description", "").lower():
                continue
            checked += 1
            with self.subTest(agent=path.name):
                self.assertEqual(
                    sorted(WRITE_TOOLS & set(tools)),
                    [],
                    f"{path.name} calls itself read-only and can write",
                )
        self.assertGreater(checked, 0, "no read-only agent found to check")

    def test_no_agent_carries_the_command_marker(self) -> None:
        """`disable-model-invocation` is a command's key; an agent is dispatched."""

        for path in agent_files():
            with self.subTest(agent=path.name):
                fields, _ = frontmatter(path.read_text(encoding="utf-8"))
                self.assertNotIn("disable-model-invocation", fields)

    def test_no_agent_still_names_the_retired_framework(self) -> None:
        for path in agent_files():
            with self.subTest(agent=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("Trellis", text)
                self.assertNotIn("se-", text)


class RenderTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()

    def install(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        rc = sd_install.main([*args, "--home", str(self.home)], out=out)
        return rc, out.getvalue()

    @property
    def receipt(self) -> dict:
        path = self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_agents_land_verbatim_in_the_claude_agents_home(self) -> None:
        rc, _ = self.install("--user")
        self.assertEqual(rc, 0)
        for source in agent_files():
            target = self.home / ".claude" / "agents" / source.name
            with self.subTest(agent=source.name):
                self.assertTrue(target.is_file(), f"{target} missing")
                self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_the_receipt_records_them_as_agents_not_skills(self) -> None:
        """Kind is what `--uninstall` and the drift check read; conflating the
        two would make an agent look like a skill that lost its home."""

        self.install("--user")
        kinds = {
            row["kind"]
            for row in self.receipt["owned"]
            if row["path"].endswith(tuple(f"agents/{p.name}" for p in agent_files()))
        }
        self.assertEqual(kinds, {"agent:claude"})

    def test_agents_are_not_rendered_to_codex_or_opencode(self) -> None:
        """The stated limit, pinned so it cannot erode into a half-render.

        Codex agents are TOML with the instructions embedded; producing that is
        a translation this renderer deliberately does not do.
        """

        self.install("--user")
        codex_agents = self.home / ".codex" / "agents"
        # By stem and any extension, not by filename: Codex's native agent
        # format is `.toml`, so a check for `sd-rust-fill.md` would pass over
        # exactly the render this limit exists to forbid.
        landed = sorted(
            path.name
            for path in (codex_agents.glob("*") if codex_agents.is_dir() else [])
        )
        self.assertEqual(landed, [], f"agents rendered to {codex_agents}")
        for source in agent_files():
            with self.subTest(agent=source.name):
                self.assertEqual(sorted((self.home / ".codex" / "skills").glob(
                    f"{source.stem}.*")), [])
                self.assertEqual(sorted(
                    (self.home / ".config" / "opencode" / "commands").glob(
                        f"{source.stem}.*")), [])

    def test_uninstall_takes_them_with_it(self) -> None:
        self.install("--user")
        rc, _ = self.install("--uninstall")
        self.assertEqual(rc, 0)
        for name in (p.name for p in agent_files()):
            with self.subTest(agent=name):
                self.assertFalse((self.home / ".claude" / "agents" / name).exists())

    def test_a_checkout_without_agents_still_installs(self) -> None:
        """Discovery returns nothing rather than failing on an absent directory.

        The skills half of the install is what the command exists for, and a
        checkout predating `agents/` -- or a future one that retires it -- must
        converge instead of erroring.
        """

        checkout = self.home / "checkout"
        folder = checkout / "skills" / "sd-probe"
        folder.mkdir(parents=True)
        (folder / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-probe\n---\n\nprobe surface\n", encoding="utf-8"
        )
        self.assertEqual(sd_install.discover_agents(checkout), [])
        context = sd_install.Context(
            checkout=checkout,
            home=self.home,
            environ={
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
        )
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(context, out), 0)
        self.assertNotIn("agents", out.getvalue())


if __name__ == "__main__":
    unittest.main()
