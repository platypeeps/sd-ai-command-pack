"""Behavioral tests for ``scripts/sd-ai-command-pack-pr-body-scope.py``.

Focus: the automated-author exemption (added so wiring the check into CI does
not fail Dependabot/Renovate PRs and block their auto-merge). The script is
otherwise exercised end-to-end by consumer repos; these tests pin the
pack-owned behavior that must hold everywhere the script ships.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PACK_ROOT / "scripts" / "sd-ai-command-pack-pr-body-scope.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("_pr_body_scope_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Registered in sys.modules so the module-level @dataclass can resolve its
    # own module during class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ActorExemptionUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_script()

    def test_bot_logins_are_exempt(self) -> None:
        for login in ("dependabot[bot]", "github-actions[bot]", "renovate[bot]"):
            self.assertTrue(self.mod._actor_is_exempt(login), login)

    def test_human_and_empty_are_not_exempt(self) -> None:
        self.assertFalse(self.mod._actor_is_exempt("sventhegrinch"))
        self.assertFalse(self.mod._actor_is_exempt(""))
        # A non-suffix substring must not match — only the trailing [bot].
        self.assertFalse(self.mod._actor_is_exempt("bot-fan"))

    def test_resolve_actor_flag_beats_env_and_trims(self) -> None:
        self.assertEqual(self.mod._resolve_actor("  dependabot[bot]  "), "dependabot[bot]")

    def test_resolve_actor_env_fallback(self) -> None:
        var = self.mod.ACTOR_ENV_VARS[0]
        with mock.patch.dict("os.environ", {var: "renovate[bot]"}):
            self.assertEqual(self.mod._resolve_actor(None), "renovate[bot]")

    def test_resolve_actor_empty_when_unset(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.mod._resolve_actor(None), "")


class ActorExemptionEndToEndTests(unittest.TestCase):
    """Drive ``check()`` with a change that requires a scope section and a body
    that omits it — the exact shape a Dependabot PR presents."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_script()

    def _fixture_root(self, tmp: Path) -> Path:
        # A change under .sd-ai-command-pack/** triggers the default
        # "Tooling/generated scope" rule; an empty installed-targets file keeps
        # _load_installed_target_patterns happy.
        (tmp / ".sd-ai-command-pack").mkdir(parents=True)
        (tmp / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
            "", encoding="utf-8"
        )
        (tmp / "changed.txt").write_text(
            ".sd-ai-command-pack/foo.txt\n", encoding="utf-8"
        )
        (tmp / "body.txt").write_text(
            "Just a dependency bump. No scope heading here.\n", encoding="utf-8"
        )
        return tmp

    def _check(self, root: Path, actor):
        return self.mod.check(
            root,
            body_file=root / "body.txt",
            changed_files_path=root / "changed.txt",
            actor=actor,
        )

    def test_human_author_with_missing_section_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = self._fixture_root(Path(raw))
            status, messages = self._check(root, actor="sventhegrinch")
            self.assertEqual(status, 1, messages)
            self.assertTrue(any("missing Tooling/generated scope" in m for m in messages))

    def test_bot_author_with_missing_section_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = self._fixture_root(Path(raw))
            status, messages = self._check(root, actor="dependabot[bot]")
            self.assertEqual(status, 0, messages)
            self.assertTrue(any("skipped for automated actor" in m for m in messages))

    def test_bot_author_via_env_var_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = self._fixture_root(Path(raw))
            var = self.mod.ACTOR_ENV_VARS[0]
            with mock.patch.dict("os.environ", {var: "dependabot[bot]"}):
                status, messages = self._check(root, actor=None)
            self.assertEqual(status, 0, messages)

    def test_no_actor_preserves_strict_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = self._fixture_root(Path(raw))
            with mock.patch.dict("os.environ", {}, clear=True):
                status, _messages = self._check(root, actor=None)
            self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
