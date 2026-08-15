"""Tests for the pack-owned layout resolver.

The cases that matter are the ones a plausible-but-wrong implementation
passes: resolving the state root by expanding `~` (passes every test that sets
SD_AI_COMMAND_PACK_STATE_HOME), returning `scripts/<name>` in both modes
(passes the fat resolve test), and reporting an all-`authored` classification
when no pack is installed (passes every classification test).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sd-ai-command-pack-review-layout.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))


def run_script(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None):
    environment = dict(os.environ)
    # A live install on the developer's machine would otherwise resolve every
    # "thin" fixture to the real receipt.
    environment.pop("SD_AI_COMMAND_PACK_STATE_HOME", None)
    environment.pop("SD_AI_COMMAND_PACK_TARGETS_FILE", None)
    environment.pop("XDG_STATE_HOME", None)
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=environment,
        cwd=str(cwd) if cwd else None,
        check=False,
    )


class LayoutResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        self.root.mkdir()
        # A home with no pack, so an unresolved fixture stays unresolved even on
        # a machine that has one installed.
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def write_fat_receipt(self, *targets: str) -> Path:
        receipt = self.root / ".sd-ai-command-pack" / "installed-targets.txt"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("\n".join(targets) + "\n", encoding="utf-8")
        return receipt

    def write_machine_receipt(self, state_root: Path, *names: str) -> Path:
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "files": [
                        {"family": "agents-bin", "path": name, "executable": True}
                        for name in names
                    ],
                }
            ),
            encoding="utf-8",
        )
        return receipt

    def test_vendored_receipt_resolves_fat(self) -> None:
        self.write_fat_receipt("scripts/sd-ai-command-pack-full-check.sh")
        result = run_script("--root", str(self.root), env={"HOME": str(self.home)})
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["mode"], "fat")
        self.assertEqual(
            document["receipt"], ".sd-ai-command-pack/installed-targets.txt"
        )

    def test_machine_receipt_resolves_thin_through_the_state_home_override(
        self,
    ) -> None:
        state_root = Path(self.tmp.name) / "state"
        self.write_machine_receipt(state_root, "sd-ai-command-pack-full-check.sh")
        result = run_script(
            "--root",
            str(self.root),
            env={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "thin")

    def test_xdg_state_home_is_honored_without_the_pack_override(self) -> None:
        """The rung a `~/.local/state` expansion skips.

        Every other thin test sets SD_AI_COMMAND_PACK_STATE_HOME, which a
        hardcoded home expansion could still satisfy by accident if it checked
        the override first. This one does not, so only a real call to
        `resolve_state_root` passes it.
        """

        xdg = Path(self.tmp.name) / "xdg-state"
        self.write_machine_receipt(
            xdg / "sd-ai-command-pack", "sd-ai-command-pack-full-check.sh"
        )
        result = run_script(
            "--root",
            str(self.root),
            env={"XDG_STATE_HOME": str(xdg), "HOME": str(self.home)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "thin")

    def test_targets_file_override_wins_over_both(self) -> None:
        elsewhere = Path(self.tmp.name) / "elsewhere-targets.txt"
        elsewhere.write_text(
            "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )
        state_root = Path(self.tmp.name) / "state"
        self.write_machine_receipt(state_root, "sd-ai-command-pack-full-check.sh")
        result = run_script(
            "--root",
            str(self.root),
            env={
                "SD_AI_COMMAND_PACK_TARGETS_FILE": str(elsewhere),
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "fat")

    def test_no_installation_is_unresolved_and_emits_no_classification(self) -> None:
        """Failing loud, not open.

        An all-`authored` array here would be indistinguishable from a healthy
        run on a consumer that changed no pack files, so the breakage would
        never surface. Absence of the key is the signal.
        """

        state_root = Path(self.tmp.name) / "empty-state"
        state_root.mkdir()
        result = run_script(
            "--root",
            str(self.root),
            "--path",
            "scripts/sd-ai-command-pack-full-check.sh",
            env={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        self.assertEqual(result.returncode, 1)
        document = json.loads(result.stdout)
        self.assertEqual(document["mode"], "unresolved")
        self.assertNotIn("paths", document)
        self.assertIn("reason", document)


class ClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        (self.root / ".sd-ai-command-pack").mkdir(parents=True)
        (self.root / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
            "\n".join(
                [
                    "scripts/sd-ai-command-pack-full-check.sh",
                    ".agents/skills/sd-review-pr/SKILL.md",
                    ".claude/commands/sd/review-pr.md",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def classify(self, *paths: str) -> dict[str, str]:
        args = ["--root", str(self.root)]
        for path in paths:
            args += ["--path", path]
        result = run_script(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return {
            row["path"]: row["category"] for row in json.loads(result.stdout)["paths"]
        }

    def test_receipt_membership_decides_payload_versus_authored(self) -> None:
        rows = self.classify("scripts/sd-ai-command-pack-full-check.sh", "src/app.ts")
        self.assertEqual(
            rows["scripts/sd-ai-command-pack-full-check.sh"], "pack-payload"
        )
        self.assertEqual(rows["src/app.ts"], "authored")

    def test_pack_metadata_is_payload_even_when_the_receipt_predates_it(self) -> None:
        """A newer pack version ships metadata an older receipt cannot list."""

        rows = self.classify(".sd-ai-command-pack/some-future-file.json")
        self.assertEqual(
            rows[".sd-ai-command-pack/some-future-file.json"], "pack-payload"
        )

    def test_command_surface_is_enumerated_from_the_receipt(self) -> None:
        result = run_script("--root", str(self.root))
        commands = json.loads(result.stdout)["surface"]["commands"]
        names = {entry["name"] for entry in commands}
        self.assertIn("review-pr", names)
        # Not an existence check: this fixture writes the receipt without the
        # files it lists, and the query's contract is "what the receipt says is
        # installed", which `install-audit` -- not this -- compares to disk.
        receipt = set(
            (self.root / ".sd-ai-command-pack" / "installed-targets.txt")
            .read_text(encoding="utf-8")
            .split()
        )
        for entry in commands:
            self.assertTrue(entry["paths"], entry["name"])
            for path in entry["paths"]:
                self.assertIn(path, receipt)
                self.assertIn(entry["name"], path)

    def test_no_literal_command_list_is_embedded_in_the_script(self) -> None:
        """A hardcoded table passes every behavioral test on this pack.

        Only reading the source catches it, so this assertion is a grep rather
        than a call.
        """

        source = SCRIPT.read_text(encoding="utf-8")
        for literal in (
            '"review-pr"',
            "'review-pr'",
            '"housekeeping"',
            "'housekeeping'",
        ):
            self.assertNotIn(literal, source)


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir(parents=True)
        (self.root / ".sd-ai-command-pack").mkdir(parents=True)
        (self.root / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
            "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )
        self.state_root = Path(self.tmp.name) / "state"
        receipt = self.state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "files": [
                        {
                            "family": "agents-bin",
                            "path": "sd-ai-command-pack-full-check.sh",
                            "executable": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_fat_resolves_into_the_consumer_scripts_directory(self) -> None:
        result = run_script(
            "--root",
            str(self.root),
            "--resolve",
            "sd-ai-command-pack-full-check.sh",
            env={"HOME": str(self.home)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["mode"], "fat")
        self.assertTrue(
            document["path"].endswith("scripts/sd-ai-command-pack-full-check.sh")
        )

    def test_thin_resolves_somewhere_other_than_the_consumer(self) -> None:
        """Asserting the two answers *differ* is the point.

        A resolver that returned `scripts/<name>` in both modes passes the fat
        test and is useless, which is the whole defect being fixed.
        """

        empty = Path(self.tmp.name) / "thin-consumer"
        empty.mkdir()
        result = run_script(
            "--root",
            str(empty),
            "--resolve",
            "sd-ai-command-pack-full-check.sh",
            env={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(self.state_root),
                "HOME": str(self.home),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        self.assertEqual(document["mode"], "thin")
        self.assertEqual(
            document["path"],
            str(self.home / ".agents" / "bin" / "sd-ai-command-pack-full-check.sh"),
        )
        self.assertNotIn(str(empty), document["path"])

    def test_an_unlisted_name_errors_without_offering_a_path(self) -> None:
        result = run_script(
            "--root",
            str(self.root),
            "--resolve",
            "not-a-pack-script.sh",
            env={"HOME": str(self.home)},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("not-a-pack-script.sh", result.stderr)
        self.assertNotIn("scripts/not-a-pack-script.sh", result.stdout)
        self.assertEqual(result.stdout.strip(), "")


class MirroredConstantTests(unittest.TestCase):
    """The shipped copies must still equal the `installer/` originals.

    `installer/` ships zero files, so the guard cannot import it; the copies are
    deliberate. Unchecked duplication is what drifts, so this is the check that
    makes the duplication safe rather than merely intentional.
    """

    def test_receipt_constants_match_installer(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("review_layout", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        from installer import machinescope, registry

        self.assertEqual(
            module.INSTALLED_TARGETS_RELATIVE, str(registry.INSTALLED_TARGETS_FILE)
        )
        self.assertEqual(module.MACHINE_STATE_DIR, machinescope.MACHINE_STATE_DIR)
        self.assertEqual(module.MACHINE_RECEIPT_FILE, machinescope.RECEIPT_FILE)

    def test_family_roots_match_installer(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("review_layout", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        from installer import machinepayload

        home = Path("/tmp/fake-home")
        for environ in ({}, {"XDG_CONFIG_HOME": "/tmp/xdg-config"}):
            self.assertEqual(
                module.family_roots(home, environ),
                machinepayload.family_roots(home=home, environ=environ),
            )

    def test_carried_state_root_ladder_matches_library(self) -> None:
        """Every rung, against the library this script may not import.

        The carried copy exists because a `consumer-config` install of this
        file has no `sd_ai_command_pack_lib` beside it (see the module note).
        A copy nobody compares is how the two quietly stop agreeing, so this
        walks all five rungs plus the three absolute-path refusals rather than
        spot-checking the one rung the other tests happen to exercise.
        """

        import importlib.util

        spec = importlib.util.spec_from_file_location("review_layout", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        from sd_ai_command_pack_lib import CommandError as LibraryCommandError
        from sd_ai_command_pack_lib import resolve_state_root as library

        self.assertIsNot(module.resolve_state_root, library)
        self.assertEqual(module.STATE_HOME_ENV, "SD_AI_COMMAND_PACK_STATE_HOME")

        home = Path("/tmp/fake-home")
        cases: tuple[dict[str, object], ...] = (
            # 1. explicit state_home wins over everything in the environment.
            {
                "state_home": Path("/tmp/explicit-state"),
                "environ": {"SD_AI_COMMAND_PACK_STATE_HOME": "/tmp/ignored"},
                "home": home,
            },
            # 2. the pack's own override.
            {"environ": {"SD_AI_COMMAND_PACK_STATE_HOME": "/tmp/override"}, "home": home},
            # 3. XDG, absolute and (ignored) relative.
            {"environ": {"XDG_STATE_HOME": "/tmp/xdg"}, "home": home},
            {"environ": {"XDG_STATE_HOME": "relative/xdg"}, "home": home},
            # 4. Windows local-app-data, only under nt.
            {
                "environ": {"LOCALAPPDATA": "C:\\Users\\x\\AppData\\Local"},
                "home": home,
                "os_name": "nt",
            },
            {
                "environ": {"LOCALAPPDATA": "C:\\Users\\x\\AppData\\Local"},
                "home": home,
                "os_name": "posix",
            },
            {"environ": {"LOCALAPPDATA": "relative"}, "home": home, "os_name": "nt"},
            # Windows with no LOCALAPPDATA at all: falls through to the home
            # rung rather than to an error, which is the branch a reader is
            # most likely to assume goes the other way.
            {"environ": {}, "home": home, "os_name": "nt"},
            # 5. the home fallback, and an empty environment reaching it.
            {"environ": {}, "home": home},
            {"environ": {"SD_AI_COMMAND_PACK_STATE_HOME": "  "}, "home": home},
        )
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(module.resolve_state_root(**case), library(**case))

        refusals: tuple[dict[str, object], ...] = (
            {"state_home": Path("relative/state")},
            {"environ": {"SD_AI_COMMAND_PACK_STATE_HOME": "relative/override"}},
            {"environ": {}, "home": Path("relative/home")},
        )
        for case in refusals:
            with self.subTest(refusal=case):
                with self.assertRaises(module.CommandError):
                    module.resolve_state_root(**case)
                # Same refusal, not merely some failure: the carried class is a
                # distinct type from the library's, so the pair is checked by
                # each raising its own rather than by a shared base.
                with self.assertRaises(LibraryCommandError):
                    library(**case)
        self.assertIsNot(module.CommandError, LibraryCommandError)

    def test_the_module_imports_without_the_library(self) -> None:
        """The whole point of carrying the ladder, asserted rather than assumed.

        Under thin this file installs to `.sd-ai-command-pack/bin/`, which
        conversion keeps, while `sd_ai_command_pack_lib.py` is `machine-claude`
        and goes away. Blocking the name in `sys.modules` makes any import of
        it raise, so a reintroduced module-level import fails here instead of
        in the consumers that have no other way to locate the pack.
        """

        import importlib.util

        blocked = dict(sys.modules)
        blocked_name = "sd_ai_command_pack_lib"
        original = sys.modules.get(blocked_name, ...)
        sys.modules[blocked_name] = None  # type: ignore[assignment]
        try:
            spec = importlib.util.spec_from_file_location("review_layout_solo", SCRIPT)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        finally:
            if original is ...:
                sys.modules.pop(blocked_name, None)
            else:
                sys.modules[blocked_name] = original
        self.assertEqual(blocked.keys() - sys.modules.keys(), set())

        # It imported; now prove it still answers, so the test cannot pass by
        # importing a module that does nothing useful without its library.
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp) / "state"
            (state_root / "machine").mkdir(parents=True)
            (state_root / "machine" / "machine-receipt.json").write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "family": "agents-bin",
                                "path": "sd-ai-command-pack-review-local.py",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            layout = module.resolve_layout(
                Path(tmp),
                environ={
                    "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                    "HOME": tmp,
                },
            )
        self.assertEqual(layout.mode, "thin")


class BindingAgreementTests(unittest.TestCase):
    """One implementation, three callers -- proven, not asserted in a comment.

    Bindings that each re-derive the answer is the original defect reproduced
    inside the pack, so the three must agree on identical input.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        (self.root / ".sd-ai-command-pack").mkdir(parents=True)
        (self.root / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
            "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )
        (self.root / "scripts").mkdir()

    def test_the_shell_binding_agrees_with_the_script(self) -> None:
        """The third caller the class docstring claims, actually exercised.

        `review-scope.sh --json` delegates to the resolver rather than
        restating it, so the two must not be able to disagree. Worth its own
        case now that the resolver also installs to a `consumer-config` path:
        the shell binding is the caller most likely to be rewritten by a
        conversion cohort, and a silent divergence here would look like a
        classification bug in the consumer.
        """

        # The receipt is supplied rather than discovered. Both callers land on
        # `REPO_ROOT` (see below), and `.sd-ai-command-pack/installed-targets.txt`
        # there is install-time output that `.gitignore:25` excludes -- so a
        # developer who has installed the pack into its own checkout resolves
        # `fat` and a clean CI checkout resolves `unresolved` and exits 1. That
        # difference is about whose machine ran the test, not about whether the
        # binding delegates. Pinning the receipt makes both sides read the same
        # fixture in either environment.
        environment = dict(os.environ)
        for name in ("SD_AI_COMMAND_PACK_STATE_HOME", "XDG_STATE_HOME"):
            environment.pop(name, None)
        environment["SD_AI_COMMAND_PACK_TARGETS_FILE"] = str(
            self.root / ".sd-ai-command-pack" / "installed-targets.txt"
        )

        arguments = [
            "--path",
            "scripts/sd-ai-command-pack-full-check.sh",
            "--path",
            "src/app.py",
        ]
        # Both sides get the same root, because the binding chooses one for
        # itself: `review-scope.sh:6` sets `REPO_ROOT="$SCRIPT_DIR/.."`, the
        # checkout hosting the script rather than the caller's repository. What
        # is under test is that the binding delegates instead of restating the
        # matcher; passing the fixture root to one side and letting the other
        # derive its own would test root resolution and call it agreement.
        direct = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(REPO_ROOT), *arguments],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        self.assertEqual(direct.returncode, 0, direct.stderr)

        shell = subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "scripts" / "sd-ai-command-pack-review-scope.sh"),
                "--json",
                *arguments,
            ],
            capture_output=True,
            text=True,
            cwd=self.root,
            env=environment,
            check=False,
        )
        self.assertEqual(shell.returncode, 0, shell.stderr)
        self.assertEqual(json.loads(shell.stdout), json.loads(direct.stdout))
        # Not vacuous: the two paths must actually be classified, and
        # differently, or an `unresolved` report would satisfy the equality
        # above while proving nothing about the matcher. Asserted rather than
        # guarded now that the pinned receipt makes the mode deterministic.
        document = json.loads(direct.stdout)
        self.assertEqual(document["mode"], "fat")
        categories = [entry["category"] for entry in document["paths"]]
        self.assertEqual(categories, ["pack-payload", "authored"])

    def test_python_and_node_bindings_agree(self) -> None:
        node = subprocess.run(["node", "--version"], capture_output=True, check=False)
        if node.returncode != 0:
            self.skipTest("node is unavailable")

        paths = ["scripts/sd-ai-command-pack-full-check.sh", "src/app.ts"]
        args = ["--root", str(self.root)]
        for path in paths:
            args += ["--path", path]
        direct = json.loads(run_script(*args).stdout)

        script = (
            "import { resolvePackLayout } from "
            f"'{REPO_ROOT / 'scripts' / 'sd-ai-command-pack-review-preflight.mjs'}';\n"
            f"const out = resolvePackLayout({{ root: {json.dumps(str(self.root))}, "
            f"paths: {json.dumps(paths)} }});\n"
            "process.stdout.write(JSON.stringify(out));\n"
        )
        module = Path(self.tmp.name) / "binding.mjs"
        module.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["node", str(module)], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), direct)


def load_module():
    """Import the shipped script as a module.

    The subprocess tests above prove the CLI contract, which is what consumers
    actually invoke; these in-process tests reach the branches a subprocess
    hides from coverage. Both are needed: dropping the subprocess cases would
    stop testing argument parsing and exit codes, and dropping these would
    leave most of the file unmeasured.
    """

    import importlib.util

    spec = importlib.util.spec_from_file_location("review_layout_inproc", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InProcessLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        self.root.mkdir()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def fat(self, *targets: str) -> None:
        receipt = self.root / ".sd-ai-command-pack" / "installed-targets.txt"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text("\n".join(targets) + "\n", encoding="utf-8")

    def test_comments_and_blank_lines_are_not_receipt_entries(self) -> None:
        self.fat("# a comment", "", "scripts/sd-ai-command-pack-full-check.sh")
        layout = self.module.resolve_layout(self.root, environ={"HOME": str(self.home)})
        self.assertEqual(
            layout.targets, frozenset({"scripts/sd-ai-command-pack-full-check.sh"})
        )

    def test_leading_dot_slash_is_stripped_without_eating_the_dotfile(self) -> None:
        """`lstrip('./')` takes a character set, not a prefix.

        The obvious one-liner turns `.sd-ai-command-pack/x` into
        `sd-ai-command-pack/x` and classifies every pack metadata path as
        authored. This is the case that catches it.
        """

        self.fat("scripts/sd-ai-command-pack-full-check.sh")
        layout = self.module.resolve_layout(self.root, environ={"HOME": str(self.home)})
        self.assertEqual(
            self.module.classify(layout, "./scripts/sd-ai-command-pack-full-check.sh"),
            "pack-payload",
        )
        self.assertEqual(
            self.module.classify(layout, ".sd-ai-command-pack/manifest.json"),
            "pack-payload",
        )

    def test_trellis_runtime_paths_are_payload(self) -> None:
        self.fat("scripts/sd-ai-command-pack-full-check.sh")
        layout = self.module.resolve_layout(self.root, environ={"HOME": str(self.home)})
        for path in (".trellis/scripts/task.py", ".trellis/agents/trellis-check.md"):
            self.assertEqual(self.module.classify(layout, path), "pack-payload", path)
        # A task record is the consumer's own work, not copied payload.
        self.assertEqual(
            self.module.classify(layout, ".trellis/tasks/08-01-x/prd.md"), "authored"
        )

    def test_command_name_derivation_covers_both_namespace_shapes(self) -> None:
        self.fat(
            ".claude/commands/sd/review-pr.md",
            ".opencode/commands/sd-review-pr.md",
            ".agents/skills/sd-housekeeping/SKILL.md",
            ".claude/commands/other/thing.md",
            "src/app.ts",
        )
        layout = self.module.resolve_layout(self.root, environ={"HOME": str(self.home)})
        surface = {
            entry["name"]: entry["paths"]
            for entry in self.module.command_surface(layout)
        }
        self.assertEqual(sorted(surface), ["housekeeping", "review-pr"])
        self.assertEqual(len(surface["review-pr"]), 2)

    def test_override_naming_a_missing_file_is_an_error_not_a_fallback(self) -> None:
        """Falling through to the vendored receipt would be the friendly bug.

        An operator who set the override and mistyped it would silently get a
        different repository's classification and never learn.
        """

        self.fat("scripts/sd-ai-command-pack-full-check.sh")
        with self.assertRaises(self.module.LayoutError):
            self.module.resolve_layout(
                self.root,
                environ={
                    "SD_AI_COMMAND_PACK_TARGETS_FILE": str(self.root / "nope.txt"),
                    "HOME": str(self.home),
                },
            )

    def test_a_converted_consumer_classifies_a_removed_script_as_authored(
        self,
    ) -> None:
        """The documented bound on `--path`, pinned so a change to it is loud.

        `classify` consults the receipt before `COPIED_PREFIXES`, and
        conversion rewrites the receipt down to the residual slice. So in a
        converted consumer a `scripts/sd-ai-command-pack-*.py` path matches
        neither test and comes back `authored` -- the wrong answer about what
        that path *is*, and the right answer to the question the query asks,
        which is about the current install rather than about history.

        Unreachable in ordinary use, because in a converted consumer that path
        does not exist and no changed-file set contains it. Reachable now that
        the resolver installs somewhere conversion keeps, which is why the
        behaviour is written down (design D5b, ledger C-4) instead of left to
        be rediscovered by a cohort.
        """

        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(
            json.dumps({"files": [{"family": "agents-bin", "path": "x.sh"}]}),
            encoding="utf-8",
        )
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        self.assertEqual(layout.mode, "thin")
        self.assertEqual(
            self.module.classify(layout, "scripts/sd-ai-command-pack-review-layout.py"),
            self.module.CATEGORY_AUTHORED,
        )
        # The copy that survives conversion is covered by COPIED_PREFIXES, so
        # the answer about the path a converted consumer actually holds stays
        # correct. Without this half the test would read as "classification is
        # broken under thin", which is not what is being pinned.
        self.assertEqual(
            self.module.classify(
                layout, ".sd-ai-command-pack/bin/sd-ai-command-pack-review-layout.py"
            ),
            self.module.CATEGORY_PAYLOAD,
        )

    def test_malformed_machine_receipt_is_reported_not_ignored(self) -> None:
        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text("{not json", encoding="utf-8")
        with self.assertRaises(self.module.LayoutError):
            self.module.resolve_layout(
                self.root,
                environ={
                    "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                    "HOME": str(self.home),
                },
            )

    def test_machine_receipt_without_a_files_array_is_reported(self) -> None:
        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({"schemaVersion": 1}), encoding="utf-8")
        with self.assertRaises(self.module.LayoutError):
            self.module.resolve_layout(
                self.root,
                environ={
                    "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                    "HOME": str(self.home),
                },
            )

    def test_unknown_destination_family_refuses_rather_than_guessing(self) -> None:
        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(
            json.dumps({"files": [{"family": "not-a-family", "path": "x.sh"}]}),
            encoding="utf-8",
        )
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        with self.assertRaises(self.module.LayoutError):
            self.module.resolve_script(layout, "x.sh", root=self.root, environ={})

    def test_resolving_against_an_unresolved_layout_reports_the_reason(self) -> None:
        state_root = Path(self.tmp.name) / "empty"
        state_root.mkdir()
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        with self.assertRaises(self.module.LayoutError) as caught:
            self.module.resolve_script(
                layout, "anything.sh", root=self.root, environ={}
            )
        self.assertIn("no pack installation found", str(caught.exception))

    def test_receipt_outside_the_repository_is_rendered_absolute(self) -> None:
        elsewhere = Path(self.tmp.name) / "targets.txt"
        elsewhere.write_text(
            "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_TARGETS_FILE": str(elsewhere),
                "HOME": str(self.home),
            },
        )
        report = self.module.build_report(layout, [], root=self.root)
        self.assertEqual(report["receipt"], str(elsewhere))

    def test_xdg_config_home_moves_only_the_opencode_family(self) -> None:
        home = Path("/tmp/fake-home")
        plain = self.module.family_roots(home, {})
        moved = self.module.family_roots(home, {"XDG_CONFIG_HOME": "/tmp/xdg"})
        self.assertNotEqual(plain["opencode-commands"], moved["opencode-commands"])
        for family in ("agents-skills", "agents-bin", "agents-docs", "gemini-commands"):
            self.assertEqual(plain[family], moved[family])

    def test_an_unreadable_receipt_names_the_file_it_could_not_read(self) -> None:
        """`is_file()` gates both readers, so this is the post-check race.

        The window is real -- a reinstall can replace the receipt between the
        check and the read -- and the reader must say which file failed rather
        than surfacing a bare OSError.
        """

        directory = self.root / "receipt-shaped-directory"
        directory.mkdir()
        for reader in (self.module._read_targets, self.module._read_machine_receipt):
            with self.assertRaises(self.module.LayoutError) as caught:
                reader(directory)
            self.assertIn(str(directory), str(caught.exception))

    def test_an_unresolvable_state_root_is_unresolved_not_an_exception(self) -> None:
        """A machine with no usable state home still gets a usable answer.

        The consumer's guard should report `unresolved` and its reason, not
        propagate the library's error out of a classification call.
        """

        def refuse(**_kwargs: object) -> str:
            raise self.module.CommandError("no state home")

        original = self.module.resolve_state_root
        self.module.resolve_state_root = refuse
        self.addCleanup(setattr, self.module, "resolve_state_root", original)

        layout = self.module.resolve_layout(self.root, environ={"HOME": str(self.home)})
        self.assertEqual(layout.mode, "unresolved")
        self.assertIn("cannot resolve state root", layout.reason or "")

    def test_a_bare_sd_namespace_directory_names_no_command(self) -> None:
        self.fat(".claude/commands/sd")
        layout = self.module.resolve_layout(self.root, environ={"HOME": str(self.home)})
        self.assertEqual(self.module.command_surface(layout), [])

    def test_thin_resolution_skips_entries_for_other_scripts(self) -> None:
        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(
            json.dumps(
                {
                    "files": [
                        "not-a-dict",
                        {"family": "agents-bin", "path": "other.sh"},
                        {"family": "agents-bin", "path": "wanted.sh"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        self.assertEqual(len(layout.machine_files), 2)
        resolved = self.module.resolve_script(
            layout, "wanted.sh", root=self.root, environ={}
        )
        self.assertEqual(resolved.name, "wanted.sh")
        self.assertEqual(resolved.parent.name, "bin")

    def test_an_unresolved_report_carries_a_reason_and_no_paths(self) -> None:
        empty_state = Path(self.tmp.name) / "no-install"
        empty_state.mkdir()
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(empty_state),
                "HOME": str(self.home),
            },
        )
        report = self.module.build_report(layout, ["src/app.ts"], root=self.root)
        self.assertNotIn("paths", report)
        self.assertNotIn("surface", report)
        self.assertTrue(report["reason"])

    def test_thin_resolution_honors_the_home_in_environ(self) -> None:
        """`Path.home()` would read the process environment instead.

        That makes `environ` decorative: a caller embedding this with its own
        HOME would silently resolve against the running user's home. Asserting
        the returned path sits under the *passed* home is what catches it.
        """

        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(
            json.dumps({"files": [{"family": "agents-bin", "path": "wanted.sh"}]}),
            encoding="utf-8",
        )
        environ = {
            "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
            "HOME": str(self.home),
        }
        layout = self.module.resolve_layout(self.root, environ=environ)
        resolved = self.module.resolve_script(
            layout, "wanted.sh", root=self.root, environ=environ
        )
        self.assertEqual(resolved, self.home / ".agents" / "bin" / "wanted.sh")
        self.assertNotEqual(self.home, Path.home())

    def test_a_relative_home_in_environ_falls_back_to_the_process_home(self) -> None:
        """Windows has no HOME; an unusable one must not become an error."""

        self.assertEqual(self.module.home_from({"HOME": "relative/path"}), Path.home())
        self.assertEqual(self.module.home_from({}), Path.home())

    def test_a_thin_install_missing_the_script_says_so(self) -> None:
        state_root = Path(self.tmp.name) / "state"
        receipt = state_root / "machine" / "machine-receipt.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({"files": []}), encoding="utf-8")
        layout = self.module.resolve_layout(
            self.root,
            environ={
                "SD_AI_COMMAND_PACK_STATE_HOME": str(state_root),
                "HOME": str(self.home),
            },
        )
        with self.assertRaises(self.module.LayoutError) as caught:
            self.module.resolve_script(layout, "absent.sh", root=self.root, environ={})
        self.assertIn("not listed", str(caught.exception))

    def test_a_path_outside_any_command_namespace_names_no_command(self) -> None:
        self.assertIsNone(self.module._command_name("src/app.ts"))

    def test_a_layout_with_no_receipt_renders_none(self) -> None:
        self.assertIsNone(self.module._render_receipt(None, self.root))

    def test_a_relative_xdg_config_home_is_ignored(self) -> None:
        home = Path("/tmp/fake-home")
        self.assertEqual(
            self.module.family_roots(home, {"XDG_CONFIG_HOME": "relative/path"}),
            self.module.family_roots(home, {}),
        )


class MainEntryPointTests(unittest.TestCase):
    """`main` owns argument handling and exit codes; cover it in process."""

    def setUp(self) -> None:
        self.module = load_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "consumer"
        (self.root / ".sd-ai-command-pack").mkdir(parents=True)
        (self.root / ".sd-ai-command-pack" / "installed-targets.txt").write_text(
            "scripts/sd-ai-command-pack-full-check.sh\n", encoding="utf-8"
        )
        for name in (
            "SD_AI_COMMAND_PACK_TARGETS_FILE",
            "SD_AI_COMMAND_PACK_STATE_HOME",
        ):
            if name in os.environ:
                value = os.environ.pop(name)
                self.addCleanup(os.environ.__setitem__, name, value)

    def capture(self, *argv: str) -> tuple[int, str, str]:
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.module.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_classification_exits_zero_and_prints_a_document(self) -> None:
        code, out, _ = self.capture(
            "--root",
            str(self.root),
            "--path",
            "scripts/sd-ai-command-pack-full-check.sh",
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["paths"][0]["category"], "pack-payload")

    def test_resolve_exits_zero_and_names_the_script(self) -> None:
        code, out, _ = self.capture(
            "--root", str(self.root), "--resolve", "sd-ai-command-pack-full-check.sh"
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["name"], "sd-ai-command-pack-full-check.sh")

    def test_a_layout_error_exits_one_and_writes_only_to_stderr(self) -> None:
        code, out, err = self.capture(
            "--root", str(self.root), "--resolve", "not-shipped.sh"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "")
        self.assertIn("not-shipped.sh", err)


if __name__ == "__main__":
    unittest.main()
