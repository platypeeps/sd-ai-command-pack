"""Behaviour tests for the machine-scope installer.

Every test here drives the real CLI against a scratch `--home`, because the
properties worth pinning are the ones that only appear when files actually land
on disk: that a second run does not double-register the hook, that a retired
surface is removed, that a hand-edited one is not, and that nothing reaches
outside the directory the run was told to use.

The scratch home is what makes that safe, and it is itself one of the assertions
(`SandboxContainmentTests`): an installer that consults the real user's git
config while installing into a temporary directory would append to the machine's
actual global excludes, and the test that noticed that is the reason the
`sandboxed` flag exists.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_module():
    """Import `bin/sd_install.py` by path -- `bin/` is not a package.

    Registered in `sys.modules` before execution because `@dataclass` resolves
    annotations through `sys.modules[cls.__module__]`, and a module that is not
    there yet resolves to None.
    """
    spec = importlib.util.spec_from_file_location(
        "sd_install", REPO_ROOT / "bin" / "sd_install.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sd_install = load_module()


class InstallerHarness(unittest.TestCase):
    """A scratch home plus a `run()` that returns (rc, output)."""

    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self._scratch.cleanup)
        # Resolved, because `--home` resolves what it is given and macOS hands
        # out `/var/...` symlinks to `/private/var/...`; an unresolved scratch
        # path would make the containment assertion compare two spellings of
        # the same directory and fail.
        self.home = Path(self._scratch.name).resolve()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        rc = sd_install.main([*args, "--home", str(self.home)], out=out)
        return rc, out.getvalue()

    def install(self) -> tuple[int, str]:
        return self.run_cli("--user")

    @property
    def receipt(self) -> dict:
        path = self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @property
    def settings(self) -> dict:
        path = self.home / ".claude" / "settings.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))


class RendererParityTests(InstallerHarness):
    def test_every_surface_is_byte_identical_across_platforms(self):
        """Verbatim rendering is the design, so parity is digest equality.

        Asserting the *bytes* match rather than "each platform has N files" is
        the whole point: a renderer that rewrote frontmatter per platform could
        pass a count check while shipping three subtly different skills.
        """
        rc, _ = self.install()
        self.assertEqual(rc, 0)
        surfaces = sd_install.discover_surfaces(REPO_ROOT)
        self.assertTrue(surfaces, "no sd-* surfaces found in the checkout")
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        for surface in surfaces:
            expected = sd_install.digest(surface.skill.read_bytes())
            for home in homes:
                target = home.target_for(surface.name)
                self.assertTrue(target.exists(), f"{target} was not rendered")
                self.assertEqual(
                    sd_install.digest(target.read_bytes()),
                    expected,
                    f"{home.key} render of {surface.name} differs from the source",
                )

    def test_antigravity_is_not_rendered_at_all(self):
        """R9b-D1: zero or all, never partial, and P1 has not passed.

        Rendering into a candidate root that `agy` does not load would produce
        surfaces that look installed and never load -- worse than absent, since
        nothing would report them missing.
        """
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        self.assertEqual(
            {home.key for home in homes},
            {"claude", "codex", "opencode"},
        )
        self.install()
        for candidate in (".gemini/skills", ".gemini/config", ".gemini/antigravity-cli"):
            root = self.home / candidate
            found = sorted(p.name for p in root.glob("sd-*")) if root.is_dir() else []
            self.assertEqual(found, [], f"sd-* residue under {candidate}")

    def test_flat_platforms_get_no_template_files(self):
        """OpenCode's loader reads every file in the directory as a command.

        A template rendered beside a skill there would appear as an extra
        command whose name is a template filename.
        """
        self.install()
        commands = self.home / ".config" / "opencode" / "commands"
        names = sorted(p.name for p in commands.iterdir())
        self.assertTrue(names)
        for name in names:
            self.assertTrue(name.startswith("sd-"), f"{name} is not an sd-* command")
        self.assertFalse((commands / "templates").exists())


class IdempotencyTests(InstallerHarness):
    def test_second_run_does_not_double_register_the_hook(self):
        self.install()
        self.install()
        groups = self.settings["hooks"]["SessionStart"]
        matchers = {group["matcher"]: group["hooks"] for group in groups}
        self.assertEqual(set(matchers), set(sd_install.HOOK_MATCHERS))
        for matcher, entries in matchers.items():
            self.assertEqual(len(entries), 1, f"{matcher} registered {len(entries)}x")

    def test_second_run_does_not_duplicate_the_excludes_line(self):
        self.install()
        self.install()
        excludes = self.home / ".config" / "git" / "ignore"
        lines = [
            line
            for line in excludes.read_text(encoding="utf-8").splitlines()
            if line.strip() == sd_install.EXCLUDES_LINE
        ]
        self.assertEqual(lines, [sd_install.EXCLUDES_LINE])

    def test_the_hook_matchers_are_exactly_startup_and_clear(self):
        """R10-D3 names the two omissions as design, so they are pinned here.

        `compact` would consume the packet into the dying session and the
        `/clear` that follows -- the entire gesture -- would find nothing.
        """
        self.assertEqual(sd_install.HOOK_MATCHERS, ("startup", "clear"))


class OtherPeoplesFilesTests(InstallerHarness):
    def test_another_installers_hook_survives_install_and_uninstall(self):
        """`~/.claude/settings.json` holds hooks this pack did not write.

        The machine really does carry other SessionStart hooks, so a settings
        edit that rewrote the stanza wholesale would silently unregister them.
        """
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        foreign = {"type": "command", "command": "~/.claude/hooks/somebody-else"}
        settings.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {
                        "SessionStart": [{"matcher": "startup", "hooks": [foreign]}]
                    },
                }
            ),
            encoding="utf-8",
        )
        self.install()
        groups = self.settings["hooks"]["SessionStart"]
        startup = next(g for g in groups if g["matcher"] == "startup")
        self.assertIn(foreign, startup["hooks"])
        self.assertEqual(len(startup["hooks"]), 2)

        self.run_cli("--uninstall")
        after = self.settings
        self.assertEqual(after["model"], "opus", "unrelated settings were lost")
        startup = next(
            g for g in after["hooks"]["SessionStart"] if g["matcher"] == "startup"
        )
        self.assertEqual(startup["hooks"], [foreign])

    def test_unparseable_settings_are_refused_rather_than_overwritten(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text("{not json", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            self.install()
        self.assertIn("not readable JSON", str(caught.exception))
        self.assertEqual(settings.read_text(encoding="utf-8"), "{not json")


class ReconciliationTests(InstallerHarness):
    """A retired surface must actually disappear; an edited one must not."""

    def add_surface(self, name: str = "sd-zzz-probe") -> Path:
        folder = REPO_ROOT / "skills" / name
        folder.mkdir(parents=True)
        self.addCleanup(
            lambda: subprocess.run(["rm", "-rf", str(folder)], check=False)
        )
        (folder / "SKILL.md").write_text(
            f"---\nname: {name}\n---\n\nprobe surface\n", encoding="utf-8"
        )
        return folder

    def test_a_retired_surface_is_removed_from_every_platform(self):
        folder = self.add_surface()
        self.install()
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        rendered = [home.target_for(folder.name) for home in homes]
        for target in rendered:
            self.assertTrue(target.exists())

        subprocess.run(["rm", "-rf", str(folder)], check=True)
        self.install()
        for target in rendered:
            self.assertFalse(target.exists(), f"{target} survived the surface removal")

    def test_a_hand_edited_render_is_kept_and_reported(self):
        folder = self.add_surface()
        self.install()
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        edited = homes[0].target_for(folder.name)
        edited.write_text("someone edited this\n", encoding="utf-8")

        subprocess.run(["rm", "-rf", str(folder)], check=True)
        rc, output = self.install()
        self.assertEqual(rc, 0)
        self.assertTrue(edited.exists(), "an edited file was deleted")
        self.assertIn("modified since it was installed", output)

    def test_a_corrupt_receipt_deletes_nothing(self):
        """The receipt is the delete authority, so an unreadable one grants none."""
        folder = self.add_surface()
        self.install()
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        orphan = homes[0].target_for(folder.name)

        receipt = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        )
        receipt.write_text("{ truncated", encoding="utf-8")
        subprocess.run(["rm", "-rf", str(folder)], check=True)
        rc, _ = self.install()
        self.assertEqual(rc, 0)
        self.assertTrue(
            orphan.exists(),
            "a file was deleted on the authority of a receipt that would not parse",
        )


class UninstallTests(InstallerHarness):
    def test_uninstall_leaves_no_residue_of_its_own(self):
        self.install()
        rc, _ = self.run_cli("--uninstall")
        self.assertEqual(rc, 0)
        for home in sd_install.platform_homes(self.home, dict(os.environ)):
            leftovers = sorted(home.root.glob("sd-*")) if home.root.is_dir() else []
            self.assertEqual(leftovers, [], f"{home.key} still holds renders")
        self.assertNotIn("hooks", self.settings)

    def test_uninstall_without_a_receipt_removes_nothing(self):
        rc, output = self.run_cli("--uninstall")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to remove", output)


class SandboxContainmentTests(InstallerHarness):
    def test_a_scratch_install_never_resolves_the_real_global_excludes(self):
        """`--home` must mean the run stays inside that home.

        Git's global config is per-user, not per-`$HOME`-argument, so the
        unsandboxed lookup resolves to the machine's real excludes file. This
        caught exactly that during development.
        """
        resolved = sd_install.excludes_file(
            self.home,
            {"XDG_CONFIG_HOME": str(self.home / ".config")},
            sandboxed=True,
        )
        self.assertEqual(resolved, self.home / ".config" / "git" / "ignore")

    def test_every_written_path_is_under_the_given_home(self):
        self.install()
        for entry in self.receipt["owned"]:
            path = Path(entry["path"])
            self.assertTrue(
                str(path).startswith(str(self.home)),
                f"{path} was written outside the scratch home",
            )


class LocalBlockTests(InstallerHarness):
    def make_repo(self) -> Path:
        repo = self.home / "scratch-repo"
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        return repo

    def test_the_block_is_added_then_refreshed_in_place(self):
        repo = self.make_repo()
        target = repo / sd_install.LOCAL_BLOCK_FILE
        target.write_text("# my notes\n\nkeep me\n", encoding="utf-8")

        self.assertEqual(sd_install.write_local_block(repo), "added")
        first = target.read_text(encoding="utf-8")
        self.assertIn("keep me", first)
        self.assertEqual(first.count(sd_install.BLOCK_BEGIN), 1)

        self.assertEqual(sd_install.write_local_block(repo), "refreshed")
        second = target.read_text(encoding="utf-8")
        self.assertIn("keep me", second)
        self.assertEqual(second.count(sd_install.BLOCK_BEGIN), 1)
        self.assertEqual(second, first, "a refresh changed content it should not")

    def test_a_tracked_local_file_is_refused(self):
        """P6: the framework never edits a tracked repo file, no exceptions."""
        repo = self.make_repo()
        target = repo / sd_install.LOCAL_BLOCK_FILE
        target.write_text("committed by mistake\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "add", sd_install.LOCAL_BLOCK_FILE], check=True
        )
        with self.assertRaises(SystemExit) as caught:
            sd_install.write_local_block(repo)
        self.assertIn("refusing to edit a tracked file", str(caught.exception))
        self.assertEqual(
            target.read_text(encoding="utf-8"), "committed by mistake\n"
        )

    def test_a_half_open_block_is_refused(self):
        repo = self.make_repo()
        (repo / sd_install.LOCAL_BLOCK_FILE).write_text(
            f"{sd_install.BLOCK_BEGIN}\nsomeone deleted the end marker\n",
            encoding="utf-8",
        )
        with self.assertRaises(SystemExit) as caught:
            sd_install.write_local_block(repo)
        self.assertIn("half-open", str(caught.exception))


class LegacyReceiptTests(InstallerHarness):
    def write_legacy_receipt(self, rows: list[dict]) -> None:
        path = (
            self.home
            / ".local"
            / "state"
            / "sd-ai-command-pack"
            / "machine"
            / "machine-receipt.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"files": rows}), encoding="utf-8")

    def environ(self) -> dict[str, str]:
        return {
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
        }

    def test_families_resolve_to_the_old_installers_roots(self):
        self.write_legacy_receipt(
            [
                {
                    "family": "agents-skills",
                    "path": "sd-audit-repo/SKILL.md",
                    "digest": "sha256:abc",
                },
                {"family": "gemini-commands", "path": "sd/check.toml", "digest": "def"},
                {"family": "opencode-commands", "path": "sd-check.md", "digest": "ghi"},
            ]
        )
        found = dict(sd_install.legacy_targets(self.home, self.environ()))
        self.assertIn(
            self.home / ".agents" / "skills" / "sd-audit-repo" / "SKILL.md", found
        )
        self.assertIn(self.home / ".gemini" / "commands" / "sd" / "check.toml", found)
        self.assertIn(
            self.home / ".config" / "opencode" / "commands" / "sd-check.md", found
        )
        self.assertEqual(
            found[self.home / ".agents" / "skills" / "sd-audit-repo" / "SKILL.md"],
            "abc",
            "the sha256: prefix was not stripped",
        )

    def test_an_unknown_family_is_skipped_rather_than_guessed(self):
        self.write_legacy_receipt(
            [{"family": "some-future-family", "path": "x.md", "digest": "abc"}]
        )
        self.assertEqual(sd_install.legacy_targets(self.home, self.environ()), [])

    def test_adopt_legacy_deletes_only_successor_less_renders(self):
        survivor = self.home / ".agents" / "skills" / "sd-kept" / "SKILL.md"
        survivor.parent.mkdir(parents=True)
        survivor.write_bytes(b"legacy body\n")
        edited = self.home / ".agents" / "skills" / "sd-edited" / "SKILL.md"
        edited.parent.mkdir(parents=True)
        edited.write_bytes(b"changed since install\n")
        self.write_legacy_receipt(
            [
                {
                    "family": "agents-skills",
                    "path": "sd-kept/SKILL.md",
                    "digest": sd_install.digest(b"legacy body\n"),
                },
                {
                    "family": "agents-skills",
                    "path": "sd-edited/SKILL.md",
                    "digest": sd_install.digest(b"what was installed\n"),
                },
            ]
        )
        rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertFalse(survivor.exists(), "a successor-less render survived")
        self.assertTrue(edited.exists(), "an edited legacy file was deleted")
        self.assertIn("modified since it was installed", output)

    def test_adopt_legacy_is_a_clean_no_op_without_a_receipt(self):
        rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertIn("no legacy receipt", output)


class PullTests(InstallerHarness):
    def test_pull_refuses_off_main(self):
        """The serving checkout is what every render points at.

        Fast-forwarding a branch someone is working on would change what is
        installed on the machine as a side effect of an update.
        """
        out = io.StringIO()
        ctx = sd_install.Context(
            checkout=REPO_ROOT, home=self.home, environ=dict(os.environ)
        )
        branch = sd_install.git_context(REPO_ROOT)["branch"]
        if branch == "main":
            self.skipTest("this checkout is on main; the refusal cannot be observed")
        self.assertEqual(sd_install.cmd_pull(ctx, out), 1)
        self.assertIn("not main", out.getvalue())


class CommandLineTests(InstallerHarness):
    def test_no_mode_prints_usage_and_fails(self):
        out = io.StringIO()
        self.assertEqual(sd_install.main([], out=out), 2)
        self.assertIn("usage:", out.getvalue())

    def test_two_modes_are_refused(self):
        out = io.StringIO()
        self.assertEqual(sd_install.main(["--user", "--status"], out=out), 2)
        self.assertIn("mutually exclusive", out.getvalue())

    def test_an_unknown_flag_is_refused(self):
        out = io.StringIO()
        self.assertEqual(sd_install.main(["--nope"], out=out), 2)
        self.assertIn("unknown argument", out.getvalue())

    def test_dry_run_writes_nothing(self):
        rc, output = self.run_cli("--user", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("would render", output)
        self.assertEqual(
            sorted(p.name for p in self.home.iterdir()),
            [],
            "a dry run created files",
        )


if __name__ == "__main__":
    unittest.main()
