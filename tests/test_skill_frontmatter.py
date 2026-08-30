"""The frontmatter contract for `skills/sd-*/SKILL.md`, asserted as it is written.

The design's taxonomy (design.md, "Taxonomy (r6 §1)") is a *behavioural* claim:
a COMMAND pre-authorizes side effects, so its invocation must be deliberate and
it sets `disable-model-invocation`; a SKILL is knowledge loaded when relevant and
carries no standing authority, so it must not; an AGENT is a bounded worker and
declares `tools:`. Rendered, that difference is three frontmatter keys, and
nothing in this repository checked them before this file existed.

The contract is grounded rather than invented. Measured across the 60 skills
installed on this machine: `name` and `description` appear in all 60,
`disable-model-invocation` in 16, `model`/`effort` in 54. The marker is a real
mechanism in use, not a design aspiration. The exception has a measured
precedent too: `se-help`, this surface's predecessor and still installed at
`~/.claude/skills/se-help`, carries no marker. It is named here as evidence for
the rule, not as a surface this suite asserts -- everything below is `sd-*`,
where `sd-help` is the one skill among eleven commands.

These run without an installer. That is the point: step 3e builds the renderer
that consumes this tree, so without these assertions the twelve surfaces would
sit unverified until then, and a missing marker would surface as a command that
silently invokes itself.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"

# The eleven commands. With `sd-help` in SKILL_KIND below they are the twelve
# surfaces the design names -- the split is the taxonomy's, which makes catalog
# surfaces skills rather than commands. Pinned deliberately: standing rule 2
# makes the verb inventory a CI-tested invariant, so a thirteenth surface fails
# here until the design record grows to justify it.
COMMANDS = frozenset({
    "sd-plan", "sd-check", "sd-review", "sd-ship", "sd-spec", "sd-status",
    "sd-deps", "sd-suggest", "sd-skill-adopt", "sd-map", "sd-handoff",
})
# The stated exception: help/catalog surfaces are skills, so no marker.
SKILL_KIND = frozenset({"sd-help"})
EXPECTED = COMMANDS | SKILL_KIND

MARKER = "disable-model-invocation"


def frontmatter(text: str) -> dict[str, str] | None:
    """The leading `---` block as flat key/value pairs, or None if absent.

    Deliberately the same 20-line flat-scalar subset the rest of the pack parses
    (D-C1): no YAML dependency, no nested structures, and a file that needs more
    than this is a file that has outgrown the contract.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, str] = {}
    for line in lines[1:21]:
        if line.strip() == "---":
            return fields
        key, separator, value = line.partition(":")
        if separator and not key.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
    return None  # unterminated block within the bound


def surfaces() -> list[pathlib.Path]:
    """Every `skills/*/SKILL.md` on disk."""

    if not SKILLS.is_dir():
        return []
    return sorted(p / "SKILL.md" for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


class InventoryTests(unittest.TestCase):
    def test_the_tree_holds_exactly_the_surfaces_the_design_names(self) -> None:
        found = {p.parent.name for p in surfaces()}
        self.assertEqual(found, set(EXPECTED), "skills/ drifted from the design's 12")

    def test_every_directory_holds_a_skill_file(self) -> None:
        if not SKILLS.is_dir():
            self.skipTest("skills/ does not exist yet")
        for entry in sorted(SKILLS.iterdir()):
            if entry.is_dir():
                with self.subTest(surface=entry.name):
                    self.assertTrue((entry / "SKILL.md").is_file(), "no SKILL.md")


class FrontmatterTests(unittest.TestCase):
    def test_every_surface_parses(self) -> None:
        for path in surfaces():
            with self.subTest(surface=path.parent.name):
                self.assertIsNotNone(frontmatter(path.read_text(encoding="utf-8")))

    def test_name_matches_the_directory(self) -> None:
        for path in surfaces():
            fields = frontmatter(path.read_text(encoding="utf-8")) or {}
            with self.subTest(surface=path.parent.name):
                self.assertEqual(fields.get("name"), path.parent.name)

    def test_description_is_present_and_one_line(self) -> None:
        for path in surfaces():
            fields = frontmatter(path.read_text(encoding="utf-8")) or {}
            description = fields.get("description", "")
            with self.subTest(surface=path.parent.name):
                self.assertTrue(description.strip(), "empty description")
                self.assertNotIn("\n", description)


class KindMarkerTests(unittest.TestCase):
    """The taxonomy, which is the whole reason this file exists."""

    def test_commands_disable_model_invocation(self) -> None:
        for path in surfaces():
            if path.parent.name not in COMMANDS:
                continue
            fields = frontmatter(path.read_text(encoding="utf-8")) or {}
            with self.subTest(command=path.parent.name):
                self.assertEqual(
                    fields.get(MARKER),
                    "true",
                    f"a command whose invocation is not deliberate: {MARKER} must be true",
                )

    def test_skills_do_not(self) -> None:
        for path in surfaces():
            if path.parent.name not in SKILL_KIND:
                continue
            fields = frontmatter(path.read_text(encoding="utf-8")) or {}
            with self.subTest(skill=path.parent.name):
                self.assertNotIn(MARKER, fields, "a skill carrying a command's marker")

    def test_no_surface_here_declares_tools(self) -> None:
        """`tools:` marks an agent, and agents live in `agents/`, not here."""

        for path in surfaces():
            fields = frontmatter(path.read_text(encoding="utf-8")) or {}
            with self.subTest(surface=path.parent.name):
                self.assertNotIn("tools", fields, "an agent in the skills tree")


class DocumentedFlagTests(unittest.TestCase):
    """A skill must not document a flag its tool does not have.

    The frontmatter checks above cannot see this: a skill can be perfectly
    shaped and still describe an option that was removed. That is exactly what
    happened -- `sd-check`'s skill documented `--repo` hours after #605 deleted
    it, because the author branched before the fix landed, and every structural
    test still passed.

    Scoped to the surfaces with a real implementation in `bin/`. For the eight
    that have no tool yet the design's table is the only source, and asserting
    against it would pin prose to prose.
    """

    def implemented(self) -> list[tuple[str, pathlib.Path, pathlib.Path]]:
        found = []
        for path in surfaces():
            tool = REPO_ROOT / "bin" / path.parent.name
            if tool.is_file():
                found.append((path.parent.name, path, tool))
        return found

    def tool_source(self, tool: pathlib.Path) -> str:
        """The tool's text, plus that of every `bin/` module it imports.

        A surface is not always one file. `sd-review` dispatches `setup-github`
        into `bin/sd_setup_github.py`, and that module owns four of the flags
        the skill documents; reading only the entry point would have reported
        them as undocumented-in-the-tool. The imports are enumerated from the
        source rather than listed here, so a second split needs no edit.
        """

        text = tool.read_text(encoding="utf-8", errors="replace")
        parts = [text]
        for node in ast.walk(ast.parse(text)):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                module = REPO_ROOT / "bin" / f"{name}.py"
                if module.is_file():
                    parts.append(module.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(parts)

    def test_there_are_implemented_surfaces_to_check(self) -> None:
        # Guards the loop below from passing by finding nothing.
        self.assertGreaterEqual(len(self.implemented()), 4)

    # Phrases that mark a flag as documented-but-absent on purpose. A skill is
    # allowed -- encouraged -- to say "the design has --push, the code does not",
    # and the sentence carrying that disclaimer is often the section heading
    # rather than the line naming the flag. So the window is the flag's line plus
    # the heading it sits under, which is where a skill states this truthfully.
    DISCLAIMERS = (
        "not implemented",
        "does not exist",
        "not exist",
        "no `",
        "will not be",
        "when it exists",
        "yet",
    )

    def disclaimed(self, body: str, option: str) -> bool:
        heading = ""
        for line in body.splitlines():
            if line.startswith("#"):
                heading = line
            if option in line:
                window = f"{heading}\n{line}".lower()
                if any(phrase in window for phrase in self.DISCLAIMERS):
                    return True
        return False

    def test_every_documented_flag_exists_in_the_tool(self) -> None:
        import re

        flag = re.compile(r"`(--[a-z][a-z-]+)")
        for name, skill, tool in self.implemented():
            source = self.tool_source(tool)
            body = skill.read_text(encoding="utf-8")
            for option in sorted(set(flag.findall(body))):
                # A skill may say a flag does NOT exist; that sentence names it.
                present = f'"{option}"' in source or f"'{option}'" in source
                disclaimed = self.disclaimed(body, option)
                with self.subTest(surface=name, flag=option):
                    if present and disclaimed:
                        # The skill says the flag is gone and the tool still has
                        # it. Copilot caught exactly this on #607: the branch
                        # predated the PR that deleted `--repo`, so the skill's
                        # "there is no --repo" was false in its own tree. The
                        # disclaimer path used to `continue` here, which made a
                        # confident denial the one claim this test never read.
                        self.fail(
                            f"{name} says {option} does not exist, but "
                            f"bin/{name} still accepts it"
                        )
                    if not present and not disclaimed:
                        self.fail(
                            f"{name} documents {option}, which bin/{name} "
                            f"does not accept"
                        )


class UnbuiltSurfaceTests(unittest.TestCase):
    """A skill for a tool that does not exist must say so.

    Eight of the twelve surfaces have no `bin/` implementation yet. Their skills
    are written from the design, and a reader -- human or model -- who takes one
    at face value will try to run a command that is not there. Saying "not built
    yet" once is the whole requirement; this test only checks it is said.
    """

    DISCLOSURES = (
        "not implemented",
        "does not exist yet",
        "not built",
        "when it exists",
        "no `bin/",
        "lands in a later",
        "lands in a separate",
    )

    def unbuilt(self) -> list[pathlib.Path]:
        return [
            path
            for path in surfaces()
            if not (REPO_ROOT / "bin" / path.parent.name).is_file()
        ]

    def test_there_are_unbuilt_surfaces_to_check(self) -> None:
        # If every surface gets built this guard fires and the test is deleted,
        # rather than passing forever over an empty list.
        self.assertGreater(len(self.unbuilt()), 0)

    def test_unbuilt_surfaces_disclose_it(self) -> None:
        for path in self.unbuilt():
            body = path.read_text(encoding="utf-8").lower()
            with self.subTest(surface=path.parent.name):
                self.assertTrue(
                    any(phrase in body for phrase in self.DISCLOSURES),
                    f"{path.parent.name} documents a tool that does not exist in "
                    f"bin/ without saying so anywhere in the skill",
                )


if __name__ == "__main__":
    unittest.main()
