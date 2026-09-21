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
import json
import re
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

    def write_paths(self) -> None:
        """Name every skill this fixture built, on one of the three paths.

        These tests are about companions, not about which skills install,
        so the paths file follows the fixture rather than the other way
        round. Written afresh on each render so a skill added mid-test is
        named without the test having to say so twice.
        """
        skills = self.checkout / "skills"
        named = sorted(
            entry.name
            for entry in skills.iterdir()
            if entry.is_dir() and entry.name != sd_install.SHARED_DIR
        ) if skills.is_dir() else []
        skills.mkdir(parents=True, exist_ok=True)
        (skills / sd_install.PATHS_FILE).write_text(
            json.dumps({"paths": {
                "research": {"summary": "sources to brief", "skills": named},
                "development": {"summary": "plan to ship", "skills": []},
                "act": {"summary": "brief to send", "skills": []},
            }}),
            encoding="utf-8",
        )

    def surfaces(self) -> dict[str, "sd_install.Surface"]:
        self.write_paths()
        return {s.name: s for s in sd_install.discover_surfaces(self.checkout)}

    def install(self) -> str:
        self.write_paths()
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
        self.assertEqual(sd_install.missing_citations(self.surfaces().values()), [])


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


class PublicationContractDrainTests(unittest.TestCase):
    """The shared drain procedure's step order, pinned where it is stated.

    `skills/_shared/references/publication-contract.md` binds the pack and
    everything installed from it, and nothing read it. The duplicate-page bug
    of #1107 is what an unpinned procedure costs: the research-repo skill grew
    a write-back step, the contract kept the four-step form ending at the
    delete, and an agent that read the contract instead of the skill went on
    creating a second page on every render.

    What is pinned is the order, not the prose: the id is recorded before the
    request is deleted. Reword any step freely; move the delete above a write
    and this fails.
    """

    #: `Draining is <word> steps per request` -- the count the prose claims.
    COUNTS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}

    def setUp(self) -> None:
        self.contract = (
            REPO_ROOT / "skills" / "_shared" / "references"
            / "publication-contract.md"
        ).read_text(encoding="utf-8")
        self.steps = self.drain_steps()

    def drain_steps(self) -> list[str]:
        """The numbered drain steps, each as one string.

        Parsed from the document rather than counted by hand, so a step added
        without a number, or numbered out of order, is a failure here rather
        than a list that silently disagrees with itself.
        """

        head = re.search(r"Draining is (\w+) steps per request", self.contract)
        self.assertIsNotNone(head, "the drain procedure's opening line moved")
        self.claimed = self.COUNTS.get(head.group(1))
        self.assertIsNotNone(self.claimed, f"unknown count {head.group(1)!r}")
        body = self.contract[head.end():]
        # The list ends at the first line that starts flush left and is not a
        # step: an unindented paragraph, a heading, or a table.
        steps: list[str] = []
        current: list[str] = []
        for line in body.splitlines():
            start = re.match(r"^(\d+)\. (.*)$", line)
            if start:
                if current:
                    steps.append("\n".join(current))
                self.assertEqual(
                    int(start.group(1)), len(steps) + 1,
                    f"step {start.group(1)} follows {len(steps)} step(s)")
                current = [start.group(2)]
            elif current and (not line.strip() or line.startswith(" ")):
                current.append(line)
            elif current:
                steps.append("\n".join(current))
                break
        else:  # pragma: no cover - the file always has trailing prose
            if current:
                steps.append("\n".join(current))
        self.assertTrue(steps, "no numbered drain steps found")
        return steps

    def test_the_step_count_matches_the_steps(self) -> None:
        self.assertEqual(len(self.steps), self.claimed)

    def test_the_id_is_recorded_before_the_request_is_deleted(self) -> None:
        """The defect this contract shipped with, as a check.

        A drain that deletes the request before recording the created id has
        thrown away the only durable trace of that page, and the next render
        enqueues another create.
        """

        deletes = [i for i, step in enumerate(self.steps)
                   if re.search(r"[Dd]elete the request file", step)]
        self.assertEqual(len(deletes), 1, "one step deletes the request")
        records = [i for i, step in enumerate(self.steps)
                   if "page=" in step and "file=" in step]
        self.assertTrue(records, "no step records the created id")
        self.assertLess(
            max(records), deletes[0],
            "the drain deletes the request before recording the id it created")

    def test_the_delete_is_the_last_step(self) -> None:
        self.assertRegex(self.steps[-1], r"[Dd]elete the request file")

    def test_the_recording_step_names_both_destinations(self) -> None:
        """A write-back stated for one destination leaves the other duplicating."""

        recording = "\n".join(
            step for step in self.steps if "page=" in step or "file=" in step)
        self.assertIn("page=", recording)
        self.assertIn("file=", recording)

    def test_the_skill_states_the_same_order(self) -> None:
        """The skill is shorter than the contract, never differently ordered."""

        skill = (REPO_ROOT / "skills" / "sd-research-repo" / "SKILL.md").read_text(
            encoding="utf-8")
        records = skill.find("`page=`")
        deletes = skill.lower().find("delete the request only after")
        self.assertNotEqual(records, -1, "the skill states no write-back")
        self.assertNotEqual(deletes, -1, "the skill does not order the delete last")
        self.assertLess(records, deletes)


class WorkflowReferenceTests(unittest.TestCase):
    """Checkout-qualified procedures stay reachable from every rendered layout."""

    def test_workflow_references_resolve_from_each_platform(self) -> None:
        surfaces = sd_install.discover_surfaces(REPO_ROOT)
        selected = [surface for surface in surfaces
                    if surface.name in {"sd-check", "sd-review", "sd-ship"}]
        self.assertEqual({surface.name for surface in selected}, {"sd-check", "sd-review", "sd-ship"})
        with tempfile.TemporaryDirectory() as raw:
            homes = sd_install.platform_homes(Path(raw), {})
            sd_install.render(selected, homes)
            for home in homes:
                for surface in selected:
                    with self.subTest(platform=home.key, skill=surface.name):
                        body = home.target_for(surface.name).read_text(encoding="utf-8")
                        paths = re.findall(r"`(skills/sd-[^`]+/references/[^`]+\.md)`", body)
                        self.assertGreater(len(paths), 0, "conditional procedures disappeared")
                        self.assertIn("sd-ai-command-pack checkout", body)
                        for relative in paths:
                            target = (REPO_ROOT / relative).resolve()
                            self.assertTrue(target.is_relative_to(REPO_ROOT))
                            self.assertTrue(target.is_file(), relative)
                            self.assertGreater(len(target.read_text(encoding="utf-8")), 100)

    def test_every_extracted_procedure_has_an_entrypoint_reference(self) -> None:
        for name in ("sd-check", "sd-review", "sd-ship"):
            directory = REPO_ROOT / "skills" / name
            body = (directory / "SKILL.md").read_text(encoding="utf-8")
            files = sorted((directory / "references").glob("*.md"))
            self.assertGreater(len(files), 0, name)
            for path in files:
                with self.subTest(path=path):
                    self.assertIn(f"`{path.relative_to(REPO_ROOT).as_posix()}`", body)


if __name__ == "__main__":
    unittest.main()
