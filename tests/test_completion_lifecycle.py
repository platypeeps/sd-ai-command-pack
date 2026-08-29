"""Contract tests for the completion-versus-housekeeping lifecycle boundary.

Owner task: 07-28-clarify-completion-housekeeping-obligations.

These assert that the shared reference defines one named post-archive handoff and
that every lifecycle skill agrees on the same pre-archive/post-archive ownership
boundary, so stale guidance can never present post-archive mutations as unchecked
pre-archive acceptance criteria.
"""

from __future__ import annotations

import re
import unittest

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

from installer import registry

install = _support.install

BOUNDARY_SKILLS = (
    "sd-finish-work",
    "sd-housekeeping",
    "sd-review-pr",
    "sd-ship",
)

REFERENCE_RELATIVE = "references/completion-lifecycle.md"
REFERENCE_LINK = "../sd-help/references/completion-lifecycle.md"
BEFORE_ARCHIVE = "before Trellis archives the task"
CANONICAL_SENTENCE = (
    "Merge, branch deletion, default-branch synchronization, superseded-PR "
    "closure, and post-merge fleet checks are the **Post-archive handoff**, "
    "never left as unchecked acceptance criteria."
)

# Verbs that only make sense after archive; an unchecked acceptance-criteria
# checkbox must never name one of them.
POST_ARCHIVE_VERBS = (
    "merge",
    "branch deletion",
    "delete the branch",
    "delete the merged",
    "superseded",
    "fleet",
)
UNCHECKED_CRITERION = re.compile(r"^\s*[-*]\s*\[ \]\s*(?P<text>.+)$")


def _template_skill(name: str) -> str:
    path = install.ROOT / f"templates/.agents/skills/{name}/SKILL.md"
    return path.read_text(encoding="utf-8")


def _reference_text(root: str) -> str:
    path = install.ROOT / root / "skills/sd-help" / REFERENCE_RELATIVE
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class CompletionLifecycleReferenceTests(unittest.TestCase):
    def test_reference_is_registered_as_shared(self) -> None:
        self.assertIn(
            REFERENCE_RELATIVE,
            registry.SHARED_SKILL_REFERENCES["sd-help"],
            "completion-lifecycle reference must fan out with sd-help",
        )

    def test_reference_defines_one_named_post_archive_place(self) -> None:
        text = _reference_text("templates/.agents")
        self.assertIn("## Post-archive handoff", text)
        # The named place is prose handoff: no post-archive verb may appear as an
        # unchecked acceptance criterion anywhere in the reference, including the
        # authoring examples.
        for line in text.splitlines():
            match = UNCHECKED_CRITERION.match(line)
            if not match:
                continue
            lowered = match.group("text").casefold()
            offenders = [v for v in POST_ARCHIVE_VERBS if v in lowered]
            self.assertFalse(
                offenders,
                f"reference criterion names post-archive work {offenders}: "
                f"{line!r}",
            )

    def test_reference_covers_the_three_required_examples(self) -> None:
        text = _reference_text("templates/.agents")
        for heading in (
            "### Normal implementation task",
            "### Planning-only finalization",
            "### Task with post-archive fleet or cleanup follow-through",
        ):
            self.assertIn(heading, text, f"missing example: {heading}")

    def test_reference_forbids_a_second_merge_authority(self) -> None:
        normalized = _normalize(_reference_text("templates/.agents"))
        self.assertIn("sole merge", normalized)
        self.assertIn("second merge authority", normalized)

    def test_reference_applies_prospectively(self) -> None:
        text = _reference_text("templates/.agents")
        self.assertIn("prospectively", text)
        self.assertNotIn("rewrite historical", text.lower())


class CompletionLifecycleSkillContractTests(unittest.TestCase):
    def test_every_boundary_skill_links_the_shared_reference(self) -> None:
        for name in BOUNDARY_SKILLS:
            with self.subTest(skill=name):
                skill = _template_skill(name)
                self.assertIn("## Completion boundary", skill)
                self.assertIn(REFERENCE_LINK, skill)

    def test_every_boundary_skill_states_the_same_boundary(self) -> None:
        for name in BOUNDARY_SKILLS:
            with self.subTest(skill=name):
                normalized = _normalize(_template_skill(name))
                self.assertIn(_normalize(BEFORE_ARCHIVE), normalized)
                self.assertIn(
                    _normalize(CANONICAL_SENTENCE),
                    normalized,
                    f"{name}: missing the canonical post-archive-handoff sentence",
                )

    def test_no_boundary_skill_presents_post_archive_as_criterion(self) -> None:
        """Reject stale guidance: no unchecked acceptance-criteria checkbox in a
        lifecycle skill may name a post-archive mutation."""

        for name in BOUNDARY_SKILLS:
            with self.subTest(skill=name):
                for line in _template_skill(name).splitlines():
                    match = UNCHECKED_CRITERION.match(line)
                    if not match:
                        continue
                    lowered = match.group("text").casefold()
                    offenders = [v for v in POST_ARCHIVE_VERBS if v in lowered]
                    self.assertFalse(
                        offenders,
                        f"{name}: unchecked acceptance criterion names "
                        f"post-archive work {offenders}: {line!r}",
                    )


if __name__ == "__main__":
    unittest.main()
