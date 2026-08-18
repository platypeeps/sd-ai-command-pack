"""The repository runs the pack on itself, out of its own `.agents/skills/`.

Most of that tree is written by `install.py`, so `make sync` repairs any drift.
`sd-fleet-refresh` is source-only -- absent from `manifest.json`, never written
by the installer -- and the helper-resolution gate scans authored trees only.
Between them, an edit to `templates/.agents/skills/` could leave the copy the
`/sd:fleet-refresh` command actually reads a release behind, which is how the
working-directory-relative helper invocations survived the change that removed
them everywhere else.

This compares the whole authored tree against the mirror rather than that one
skill, so a second source-only skill is covered the day it is added.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORED = REPO_ROOT / "templates/.agents/skills"
MIRROR = REPO_ROOT / ".agents/skills"

MODEL_PIN_RE = re.compile(r"^model:\s*\S+\s*$\n?", re.MULTILINE)

# Mirrors that intentionally drop the authored `model:` frontmatter pin, named
# one by one. The pin selects the model a skill dispatches under, so a blanket
# exception would hide a real difference in behaviour everywhere; every other
# mirror is compared byte for byte.
DROPS_MODEL_PIN = frozenset({"sd-fleet-refresh/SKILL.md"})


class SkillMirrorParityTests(unittest.TestCase):
    def test_every_authored_skill_file_has_a_current_mirror(self) -> None:
        authored = sorted(
            path for path in AUTHORED.rglob("*") if path.is_file()
        )
        self.assertNotEqual(authored, [], f"no authored skills under {AUTHORED}")

        for path in authored:
            relative = path.relative_to(AUTHORED)
            with self.subTest(skill=str(relative)):
                mirror = MIRROR / relative
                self.assertTrue(
                    mirror.is_file(),
                    f".agents/skills/{relative} is missing; the repository "
                    "runs the pack from this tree",
                )
                expected = path.read_text(encoding="utf-8")
                if relative.as_posix() in DROPS_MODEL_PIN:
                    expected = MODEL_PIN_RE.sub("", expected, count=1)
                self.assertEqual(
                    mirror.read_text(encoding="utf-8"),
                    expected,
                    f".agents/skills/{relative} drifts from its authored "
                    "source; `make sync` repairs an installed skill, and a "
                    "source-only skill is copied by hand",
                )

    def test_every_declared_model_pin_drop_is_still_real(self) -> None:
        """A stale allowance is an exception nobody is checking any more."""

        for relative in sorted(DROPS_MODEL_PIN):
            with self.subTest(skill=relative):
                authored = (AUTHORED / relative).read_text(encoding="utf-8")
                mirror = (MIRROR / relative).read_text(encoding="utf-8")
                self.assertRegex(
                    authored,
                    MODEL_PIN_RE,
                    f"templates/.agents/skills/{relative} has no model pin to "
                    "drop; remove the allowance",
                )
                self.assertNotRegex(
                    mirror,
                    MODEL_PIN_RE,
                    f".agents/skills/{relative} carries a model pin; remove "
                    "the allowance and compare it byte for byte",
                )


if __name__ == "__main__":
    unittest.main()
