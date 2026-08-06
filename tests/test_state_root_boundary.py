"""A-046 boundary gate: user-local state-root resolution lives in the shared lib.

Two static (AST) checks over the shipped ``scripts/*.py`` surface, plus the
behavioral guarantees the consolidation had to preserve:

* AC2 — exactly one ``def resolve_state_root`` and one
  ``def ensure_private_directory`` across ``scripts/*.py``, both in the shared
  library. Callers keep their module-level names bound by assignment, so the
  gate catches a re-forked definition without forbidding the wrappers.
* AC1 — all four state-owning modules honor ``SD_AI_COMMAND_PACK_STATE_HOME``.
* PRD R3 — no call site changes its observable error type, including the two
  recorded exceptions: recovery-artifacts now raises ``RecoveryError`` where a
  raw ``OSError`` used to escape (R2), and a relative ``XDG_STATE_HOME`` still
  raises ``FleetControllerError``.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
LIB_NAME = "sd_ai_command_pack_lib.py"
CONSOLIDATED = ("resolve_state_root", "ensure_private_directory")
STATE_HOME_ENV = "SD_AI_COMMAND_PACK_STATE_HOME"

# The four modules that own user-local state and previously forked the ladder.
STATE_MODULES = (
    "sd-ai-command-pack-work-loop.py",
    "sd-ai-command-pack-recovery-artifacts.py",
    "sd-ai-command-pack-fleet-timing.py",
    "sd-ai-command-pack-fleet-controller.py",
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _top_level_defs(tree: ast.Module, names: tuple[str, ...]) -> list[tuple[str, int]]:
    """Module-level ``def``s whose name is one of ``names``."""

    return [
        (node.name, node.lineno)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]


def _load(name: str, filename: str) -> Any:
    """Import a shipped script by path, with ``scripts/`` importable for the lib."""

    path = SCRIPTS_DIR / filename
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class StateRootBoundaryTest(unittest.TestCase):
    def test_single_definition_of_each_helper(self) -> None:
        """AC2: only the shared lib defines the two consolidated functions."""

        offenders: dict[str, list[tuple[str, int]]] = {}
        for path in sorted(SCRIPTS_DIR.glob("*.py")):
            if path.name == LIB_NAME:
                continue
            hits = _top_level_defs(_tree(path), CONSOLIDATED)
            if hits:
                offenders[path.name] = hits
        self.assertEqual(
            offenders,
            {},
            f"{CONSOLIDATED} must be defined only in {LIB_NAME}; callers bind a "
            "private wrapper to the module-level name by assignment instead. "
            f"Offenders: {offenders}",
        )

    def test_lib_defines_both_helpers_exactly_once(self) -> None:
        """The gate is only meaningful if the lib actually owns both names."""

        defs = _top_level_defs(_tree(SCRIPTS_DIR / LIB_NAME), CONSOLIDATED)
        self.assertEqual(sorted(name for name, _ in defs), sorted(CONSOLIDATED))

    def test_every_state_module_exposes_the_bound_name(self) -> None:
        """Existing call sites keep working: the module-level names still resolve."""

        for filename in STATE_MODULES:
            source = (SCRIPTS_DIR / filename).read_text(encoding="utf-8")
            with self.subTest(module=filename):
                if filename == "sd-ai-command-pack-fleet-controller.py":
                    # The controller has no ensure/resolve call sites of its own;
                    # CampaignStore consumes the lib resolver directly.
                    self.assertIn("_lib_resolve_state_root", source)
                    self.assertNotIn("def default_state_home", source)
                else:
                    self.assertIn("resolve_state_root = _state_root", source)
                    self.assertIn("ensure_private_directory = _ensure", source)


class StateRootBehaviorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (STATE_HOME_ENV, "XDG_STATE_HOME", "LOCALAPPDATA")
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_all_four_modules_honor_the_pack_state_home(self) -> None:
        """AC1: one variable moves every module's root, including the fleet pair."""

        os.environ[STATE_HOME_ENV] = "/tmp/a046-state"
        work_loop = _load("a046_work_loop", "sd-ai-command-pack-work-loop.py")
        recovery = _load("a046_recovery", "sd-ai-command-pack-recovery-artifacts.py")
        timing = _load("a046_timing", "sd-ai-command-pack-fleet-timing.py")
        controller = _load("a046_controller", "sd-ai-command-pack-fleet-controller.py")

        expected = Path("/tmp/a046-state")
        self.assertEqual(work_loop.resolve_state_root(), expected)
        self.assertEqual(recovery.resolve_state_root(), expected)
        self.assertEqual(timing.resolve_state_root(), expected)
        store = controller.CampaignStore(ROOT, "a046-probe")
        self.assertEqual(store.directory.parent, expected / "fleet-campaigns")

    def test_campaign_default_gains_exactly_one_fleet_campaigns_segment(self) -> None:
        os.environ["XDG_STATE_HOME"] = "/tmp/a046-xdg"
        controller = _load("a046_controller_xdg", "sd-ai-command-pack-fleet-controller.py")
        root = controller.CampaignStore(ROOT, "a046-probe").directory.parent
        self.assertEqual(root, Path("/tmp/a046-xdg/sd-ai-command-pack/fleet-campaigns"))
        self.assertEqual(str(root).count("fleet-campaigns"), 1)

    def test_injected_campaign_state_home_is_unchanged(self) -> None:
        controller = _load("a046_controller_inj", "sd-ai-command-pack-fleet-controller.py")
        store = controller.CampaignStore(ROOT, "a046-probe", Path("/tmp/a046-injected"))
        self.assertEqual(
            store.directory, Path("/tmp/a046-injected") / store.repository_digest
        )

    def test_relative_xdg_state_home_still_raises_fleet_controller_error(self) -> None:
        """PRD R3 exception (b): the shared ladder would silently fall through."""

        os.environ["XDG_STATE_HOME"] = "relative/not/absolute"
        controller = _load("a046_controller_rel", "sd-ai-command-pack-fleet-controller.py")
        with self.assertRaisesRegex(
            controller.FleetControllerError, "state home must be an absolute path"
        ):
            controller.CampaignStore(ROOT, "a046-probe")

    def test_relative_pack_state_home_keeps_each_module_error_type(self) -> None:
        """PRD R3: the override rejection is restated in each module's type."""

        os.environ[STATE_HOME_ENV] = "relative/not/absolute"
        work_loop = _load("a046_work_loop_rel", "sd-ai-command-pack-work-loop.py")
        recovery = _load("a046_recovery_rel", "sd-ai-command-pack-recovery-artifacts.py")
        timing = _load("a046_timing_rel", "sd-ai-command-pack-fleet-timing.py")
        for module, error in (
            (work_loop, work_loop.WorkLoopError),
            (recovery, recovery.RecoveryError),
            (timing, timing.FleetTimingError),
        ):
            with self.subTest(module=module.__name__):
                with self.assertRaisesRegex(error, f"{STATE_HOME_ENV} must be"):
                    module.resolve_state_root()

    def test_windows_branch_resolves_through_the_shared_ladder(self) -> None:
        """The lib owns the Windows branch the fleet pair now inherits."""

        lib = _load("a046_lib", LIB_NAME)
        resolved = lib.resolve_state_root(
            environ={"LOCALAPPDATA": r"C:\Users\example\AppData\Local"},
            os_name="nt",
        )
        # ``as_posix()``, not ``str()``: on Windows ``Path`` stringifies with
        # backslashes, and the canonical normalization is the point of the branch.
        self.assertEqual(
            resolved.as_posix(), "C:/Users/example/AppData/Local/sd-ai-command-pack/state"
        )

    def test_symlink_state_directory_keeps_each_module_error_type(self) -> None:
        import tempfile

        work_loop = _load("a046_work_loop_link", "sd-ai-command-pack-work-loop.py")
        recovery = _load("a046_recovery_link", "sd-ai-command-pack-recovery-artifacts.py")
        timing = _load("a046_timing_link", "sd-ai-command-pack-fleet-timing.py")
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            (base / "real").mkdir()
            link = base / "link"
            link.symlink_to(base / "real")
            for module, error in (
                (work_loop, work_loop.WorkLoopError),
                (recovery, recovery.RecoveryError),
                (timing, timing.FleetTimingError),
            ):
                with self.subTest(module=module.__name__):
                    with self.assertRaisesRegex(error, "must not be a symlink"):
                        module.ensure_private_directory(link)

    def test_each_module_keeps_its_own_path_redaction_posture(self) -> None:
        """The lib never picks a path rendering; the caller's `reference` does.

        recovery-artifacts never puts a host absolute path in a user-facing
        diagnostic, and fleet-timing names no path at all. Delegation must not
        quietly widen either.
        """

        import tempfile

        work_loop = _load("a046_work_loop_redact", "sd-ai-command-pack-work-loop.py")
        recovery = _load("a046_recovery_redact", "sd-ai-command-pack-recovery-artifacts.py")
        timing = _load("a046_timing_redact", "sd-ai-command-pack-fleet-timing.py")
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            (base / "real").mkdir()
            link = base / "link"
            link.symlink_to(base / "real")

            with self.assertRaises(work_loop.WorkLoopError) as full:
                work_loop.ensure_private_directory(link)
            self.assertEqual(
                str(full.exception), f"state directory must not be a symlink: {link}"
            )

            with self.assertRaises(recovery.RecoveryError) as redacted:
                recovery.ensure_private_directory(link)
            self.assertEqual(
                str(redacted.exception), "state directory must not be a symlink: link"
            )
            self.assertNotIn(str(base), str(redacted.exception))

            with self.assertRaises(timing.FleetTimingError) as bare:
                timing.ensure_private_directory(link)
            self.assertEqual(
                str(bare.exception), "timing state directory must not be a symlink"
            )

            # A blocked mkdir must not leak the target either: str(OSError)
            # embeds it, so only strerror reaches the message.
            base.chmod(0o500)
            try:
                with self.assertRaises(recovery.RecoveryError) as blocked:
                    recovery.ensure_private_directory(base / "denied")
                self.assertNotIn(str(base), str(blocked.exception))
                self.assertEqual(
                    str(blocked.exception), "cannot create state directory: Permission denied"
                )
            finally:
                base.chmod(0o700)

    def test_unwritable_parent_keeps_structured_work_loop_evidence(self) -> None:
        """The ``environment_blocked`` fragment survives delegation unchanged."""

        import tempfile

        work_loop = _load("a046_work_loop_blocked", "sd-ai-command-pack-work-loop.py")
        recovery = _load("a046_recovery_blocked", "sd-ai-command-pack-recovery-artifacts.py")
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            base.chmod(0o500)
            try:
                with self.assertRaises(work_loop.StatePersistenceError) as captured:
                    work_loop.ensure_private_directory(base / "denied")
                self.assertIsInstance(captured.exception, OSError)
                evidence = captured.exception.evidence
                self.assertEqual(evidence["boundary"], "user-state")
                self.assertEqual(evidence["checkpoint"], "state-directory")
                self.assertEqual(evidence["mutationState"], "none")
                # PRD R2/R3 exception (a): a raw OSError used to escape here.
                with self.assertRaises(recovery.RecoveryError):
                    recovery.ensure_private_directory(base / "denied")
            finally:
                base.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
