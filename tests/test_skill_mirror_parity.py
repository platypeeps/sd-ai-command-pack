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


def _without_model_pin(text: str) -> str:
    """The one difference the mirror is allowed to carry.

    A skill may pin the model it dispatches under; `sd-fleet-refresh`'s mirror
    has dropped that pin since the file was introduced, so requiring byte
    identity would fail on a difference nobody intends to remove.
    """

    return MODEL_PIN_RE.sub("", text, count=1)


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
                self.assertEqual(
                    _without_model_pin(mirror.read_text(encoding="utf-8")),
                    _without_model_pin(path.read_text(encoding="utf-8")),
                    f".agents/skills/{relative} drifts from its authored "
                    "source; `make sync` repairs an installed skill, and a "
                    "source-only skill is copied by hand",
                )


if __name__ == "__main__":
    unittest.main()
