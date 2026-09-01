"""What ships here against what the agent will actually find."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from dashboard import skills


class Skills(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.pack = self.root / "pack"
        self.live = self.root / "installed"

    def make(self, where: pathlib.Path, name: str, description: str = "does a thing",
             body: bool = True) -> None:
        skill = where / name
        skill.mkdir(parents=True)
        if body:
            skill.joinpath("SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {description}\n---\n\n# how\n",
                encoding="utf-8")

    def test_the_gap_runs_both_ways_and_is_counted_both_ways(self) -> None:
        """Shipped-and-not-installed is a skill the agent cannot reach;
        installed-and-not-shipped came from somewhere else and is not this
        repository's business. Reporting one number would blur them."""
        self.make(self.pack / "skills", "mine")
        self.make(self.pack / "skills", "adopted")
        self.make(self.live, "adopted")
        self.make(self.live, "theirs")
        got = skills.collect_skills(self.pack, self.live)
        self.assertEqual(got["counts"],
                         {"shipped": 2, "installed": 2, "unadopted": 1, "foreign": 1})

    def test_a_directory_with_no_skill_md_is_not_a_skill(self) -> None:
        """`skills/_shared` is a real directory in this repository and the
        agent cannot invoke it. Counting it would overstate what ships."""
        self.make(self.pack / "skills", "real")
        self.make(self.pack / "skills", "_shared", body=False)
        self.assertEqual(skills.collect_skills(self.pack, self.live)["counts"]["shipped"], 1)

    def test_every_skill_on_either_side_gets_a_row(self) -> None:
        self.make(self.pack / "skills", "a")
        self.make(self.live, "b")
        got = skills.collect_skills(self.pack, self.live)
        self.assertEqual([(r["name"], r["shipped"], r["installed"]) for r in got["skills"]],
                         [("a", True, False), ("b", False, True)])

    def test_a_description_is_read_from_whichever_side_has_the_file(self) -> None:
        """An installed-only skill still has a SKILL.md; reading only the
        pack's copy would leave 62 rows on this machine blank."""
        self.make(self.live, "theirs", description="something else entirely")
        row = skills.collect_skills(self.pack, self.live)["skills"][0]
        self.assertEqual(row["description"], "something else entirely")

    def test_no_installed_directory_is_a_reported_state(self) -> None:
        """Not an empty list: "nothing installed" and "never installed
        anything" are different answers and the page says which."""
        self.make(self.pack / "skills", "a")
        got = skills.collect_skills(self.pack, self.root / "absent")
        self.assertFalse(got["installedExists"])
        self.assertEqual(got["counts"]["unadopted"], 1)

    def test_frontmatter_reading_stops_and_does_not_eat_the_document(self) -> None:
        """These are documents. A missing closing fence must not turn a whole
        skill into a description."""
        skill = self.pack / "skills" / "long"
        skill.mkdir(parents=True)
        skill.joinpath("SKILL.md").write_text(
            "---\ndescription: short\n" + "".join(f"x{n}: y\n" for n in range(500)),
            encoding="utf-8")
        self.assertEqual(skills.described(skill)["description"], "short")

    def test_a_file_that_does_not_open_with_a_fence_has_no_frontmatter(self) -> None:
        skill = self.pack / "skills" / "prose"
        skill.mkdir(parents=True)
        skill.joinpath("SKILL.md").write_text("# heading\ndescription: no\n",
                                              encoding="utf-8")
        self.assertEqual(skills.described(skill), {"name": "", "description": ""})


if __name__ == "__main__":
    unittest.main()
