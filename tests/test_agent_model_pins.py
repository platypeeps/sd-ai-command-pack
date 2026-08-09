"""Guard Trellis-local agent model pins against regeneration clobber.

``.claude/agents/trellis-*.md`` is ``trellis_local_only`` in
``installer/registry.py``: the pack installer never rewrites it, but a
Trellis upgrade or re-init regenerates these files and would silently
drop hand-applied frontmatter. This test fails loudly so the pin is
re-applied instead of dispatches quietly reverting to the session model.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# path -> required frontmatter model value
PINNED_AGENT_MODELS = {
    ".claude/agents/trellis-implement.md": "opus",
}


def _frontmatter(text: str) -> str:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    return match.group(1) if match else ""


class AgentModelPinTest(unittest.TestCase):
    def test_pinned_agents_declare_model(self) -> None:
        for rel_path, expected in PINNED_AGENT_MODELS.items():
            with self.subTest(agent=rel_path):
                path = REPO_ROOT / rel_path
                self.assertTrue(path.is_file(), f"{rel_path} is missing")
                frontmatter = _frontmatter(path.read_text(encoding="utf-8"))
                match = re.search(
                    r"^model:\s*(\S+)\s*$", frontmatter, re.MULTILINE
                )
                self.assertIsNotNone(
                    match,
                    f"{rel_path} lost its 'model:' frontmatter pin — "
                    "re-apply it after the Trellis update",
                )
                assert match is not None
                self.assertEqual(
                    match.group(1),
                    expected,
                    f"{rel_path} model pin changed from '{expected}'",
                )


if __name__ == "__main__":
    unittest.main()
