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
mechanism in use, not a design aspiration, and `se-help` already ships without
it -- which matches the design's one stated exception, that help and catalog
surfaces are skills rather than commands.

These run without an installer. That is the point: step 3e builds the renderer
that consumes this tree, so without these assertions the twelve surfaces would
sit unverified until then, and a missing marker would surface as a command that
silently invokes itself.
"""

from __future__ import annotations

import pathlib
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = REPO_ROOT / "skills"

# The 12 the design names. Pinned deliberately: standing rule 2 makes the verb
# inventory a CI-tested invariant, so a thirteenth surface fails here until the
# design record grows to justify it.
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


if __name__ == "__main__":
    unittest.main()
