"""Files that ship beside a skill: its own, and the ones many skills cite.

Two mechanisms, one reason. A skill directory's contents render at the paths
they already have, so a skill that grows `references/` or `scripts/` ships it
without the installer learning the word. And a companion cited by many skills is
stored once under `skills/_shared/references/` and copied into each citing skill
at render time -- because the alternative, a copy per skill in the checkout, is
the same paragraph committed fifty-four times, which is the shape this rebuild
exists to delete.

The fan-out is driven by the citation, never by a list: the file lands in a
skill because that skill's text says `references/<name>.md`, so a skill that
stops citing one stops shipping it, with nothing to remember.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_module():
    spec = importlib.util.spec_from_file_location(
        "sd_install_companions", REPO_ROOT / "bin" / "sd_install.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_install = load_module()


class FixtureHarness(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name).resolve()
        self.checkout = self.home / "checkout"

    def write(self, relative: str, text: str) -> Path:
        path = self.checkout / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def skill(self, name: str, body: str = "probe surface") -> Path:
        return self.write(
            f"skills/{name}/{sd_install.SKILL_FILE}",
            f"---\nname: {name}\n---\n\n{body}\n",
        )

    def surfaces(self) -> dict[str, "sd_install.Surface"]:
        return {s.name: s for s in sd_install.discover_surfaces(self.checkout)}

    def install(self) -> str:
        context = sd_install.Context(
            checkout=self.checkout,
            home=self.home,
            environ={
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
        )
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(context, out), 0)
        return out.getvalue()

    @property
    def claude(self) -> Path:
        return self.home / ".claude" / "skills"

    @property
    def opencode(self) -> Path:
        return self.home / ".config" / "opencode" / "commands"


class LocalCompanionTests(FixtureHarness):
    def test_a_skills_own_files_render_at_their_own_paths(self) -> None:
        self.skill("sd-probe")
        self.write("skills/sd-probe/references/local.md", "local\n")
        self.write("skills/sd-probe/scripts/tool.py", "print('hi')\n")
        self.write("skills/sd-probe/templates/thing.md", "template\n")
        self.install()
        for relative in ("references/local.md", "scripts/tool.py", "templates/thing.md"):
            with self.subTest(file=relative):
                target = self.claude / "sd-probe" / relative
                self.assertTrue(target.is_file(), f"{target} missing")
                self.assertEqual(
                    target.read_bytes(),
                    (self.checkout / "skills" / "sd-probe" / relative).read_bytes(),
                )

    def test_companions_do_not_reach_the_flat_home(self) -> None:
        """OpenCode's loader reads every file in that directory as a command."""

        self.skill("sd-probe")
        self.write("skills/sd-probe/references/local.md", "local\n")
        self.install()
        self.assertTrue((self.opencode / "sd-probe.md").is_file())
        self.assertEqual(sorted(p.name for p in self.opencode.iterdir()), ["sd-probe.md"])


class SharedReferenceTests(FixtureHarness):
    def setUp(self) -> None:
        super().setUp()
        self.shared = self.write(
            "skills/_shared/references/source-standards.md", "one copy\n"
        )

    def test_one_stored_copy_reaches_every_citing_skill(self) -> None:
        self.skill("sd-one", "Read `references/source-standards.md` first.")
        self.skill("sd-two", "See references/source-standards.md for the bar.")
        self.install()
        for name in ("sd-one", "sd-two"):
            with self.subTest(skill=name):
                target = self.claude / name / "references" / "source-standards.md"
                self.assertEqual(target.read_bytes(), self.shared.read_bytes())

    def test_a_skill_that_does_not_cite_it_does_not_ship_it(self) -> None:
        """Citation-driven, not copy-everything -- otherwise every skill grows
        every companion and the fan-out stops meaning anything."""

        self.skill("sd-quiet")
        self.install()
        self.assertFalse((self.claude / "sd-quiet" / "references").exists())

    def test_a_local_file_wins_over_the_shared_one(self) -> None:
        self.skill("sd-own", "Read `references/source-standards.md`.")
        local = self.write(
            "skills/sd-own/references/source-standards.md", "this skill's own\n"
        )
        self.install()
        target = self.claude / "sd-own" / "references" / "source-standards.md"
        self.assertEqual(target.read_bytes(), local.read_bytes())

    def test_the_shared_directory_is_not_itself_a_skill(self) -> None:
        self.skill("sd-probe")
        self.install()
        self.assertNotIn("_shared", [p.name for p in self.claude.iterdir()])

    def test_a_path_that_merely_ends_in_references_is_not_a_citation(self) -> None:
        """`docs/references/x.md` names a file in a repository, not a companion.

        Without the boundary the installer would hunt for a shared reference
        every time a skill mentioned somebody else's directory.
        """

        self.skill("sd-doc", "The design lives at docs/references/source-standards.md.")
        self.assertEqual(self.surfaces()["sd-doc"].extras, [])


class MissingCitationTests(FixtureHarness):
    def test_an_unshipped_citation_is_reported_and_does_not_stop_the_install(self) -> None:
        self.skill("sd-broken", "Read `references/absent.md` before starting.")
        self.skill("sd-fine")
        output = self.install()
        self.assertIn("sd-broken: references/absent.md is cited but not shipped", output)
        # The other skill still installed: reporting a gap is not refusing to work.
        self.assertTrue((self.claude / "sd-fine" / sd_install.SKILL_FILE).is_file())
        self.assertTrue((self.claude / "sd-broken" / sd_install.SKILL_FILE).is_file())

    def test_a_resolved_citation_is_not_reported(self) -> None:
        self.write("skills/_shared/references/present.md", "here\n")
        self.skill("sd-ok", "Read `references/present.md`.")
        self.assertEqual(sd_install.missing_citations(
            sd_install.discover_surfaces(self.checkout)), [])


class ReceiptTests(FixtureHarness):
    def test_companions_are_recorded_as_companions(self) -> None:
        """Not as `template`: these are references and scripts too now."""

        import json

        self.skill("sd-probe")
        self.write("skills/sd-probe/references/local.md", "local\n")
        self.install()
        receipt = json.loads(
            (self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json")
            .read_text(encoding="utf-8")
        )
        kinds = {
            row["kind"] for row in receipt["owned"] if row["path"].endswith("local.md")
        }
        self.assertEqual(kinds, {"companion:claude", "companion:codex"})


class RepositoryInvariantTests(unittest.TestCase):
    def test_no_skill_in_this_checkout_cites_a_file_it_does_not_ship(self) -> None:
        """The CI half of the installer's warning.

        A skill telling the model to read a file that was never shipped fails
        silently: the read fails and the run continues on whatever the model
        remembered instead. Here it is a red check.
        """

        surfaces = sd_install.discover_surfaces(REPO_ROOT)
        self.assertGreater(len(surfaces), 0, "no surfaces discovered")
        self.assertEqual(sd_install.missing_citations(surfaces), [])


if __name__ == "__main__":
    unittest.main()
