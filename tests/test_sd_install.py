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
import unittest.mock
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
    """A retired surface must actually disappear; an edited one must not.

    These run against a synthetic checkout rather than the real one. An earlier
    version created a probe surface under the repository's own `skills/` and
    removed it afterwards, which raced `test_sd_check`'s purity assertion under
    the parallel runner -- that suite checks the working tree is clean, and for
    a few seconds it was not. A test that dirties the repository to prove
    something about the installer is testing the wrong thing anyway: the
    installer takes a checkout as input, so the input should be a fixture.
    """

    def make_checkout(self, *names: str) -> Path:
        checkout = self.home / "checkout"
        for name in names:
            folder = checkout / "skills" / name
            folder.mkdir(parents=True)
            (folder / sd_install.SKILL_FILE).write_text(
                f"---\nname: {name}\n---\n\nprobe surface\n", encoding="utf-8"
            )
        return checkout

    def context(self, checkout: Path) -> "sd_install.Context":
        return sd_install.Context(
            checkout=checkout,
            home=self.home,
            environ={
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
        )

    def install(self, checkout: Path) -> str:
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 0)
        return out.getvalue()

    def rendered(self, name: str) -> list[Path]:
        return [
            home.target_for(name)
            for home in sd_install.platform_homes(self.home, dict(os.environ))
        ]

    def test_a_retired_surface_is_removed_from_every_platform(self):
        checkout = self.make_checkout("sd-kept", "sd-retired")
        self.install(checkout)
        targets = self.rendered("sd-retired")
        for target in targets:
            self.assertTrue(target.exists())

        subprocess.run(
            ["rm", "-rf", str(checkout / "skills" / "sd-retired")], check=True
        )
        self.install(checkout)
        for target in targets:
            self.assertFalse(target.exists(), f"{target} survived the removal")
        self.assertTrue(self.rendered("sd-kept")[0].exists())

    def test_a_hand_edited_render_is_kept_and_reported(self):
        checkout = self.make_checkout("sd-kept", "sd-retired")
        self.install(checkout)
        edited = self.rendered("sd-retired")[0]
        edited.write_text("someone edited this\n", encoding="utf-8")

        subprocess.run(
            ["rm", "-rf", str(checkout / "skills" / "sd-retired")], check=True
        )
        output = self.install(checkout)
        self.assertTrue(edited.exists(), "an edited file was deleted")
        self.assertIn("modified since it was installed", output)

    def test_a_corrupt_receipt_deletes_nothing(self):
        """The receipt is the delete authority, so an unreadable one grants none."""
        checkout = self.make_checkout("sd-kept", "sd-retired")
        self.install(checkout)
        orphan = self.rendered("sd-retired")[0]

        receipt = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        )
        receipt.write_text("{ truncated", encoding="utf-8")
        subprocess.run(
            ["rm", "-rf", str(checkout / "skills" / "sd-retired")], check=True
        )
        self.install(checkout)
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

    def test_any_home_but_the_real_one_is_sandboxed(self):
        """Derived, not passed -- a Context cannot forget to be contained."""
        ctx = sd_install.Context(
            checkout=REPO_ROOT, home=self.home, environ={}
        )
        self.assertTrue(ctx.sandboxed)
        real = sd_install.Context(
            checkout=REPO_ROOT,
            home=Path(os.path.expanduser("~")),
            environ={},
        )
        self.assertFalse(real.sandboxed)

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
        # -f because the machine running these tests may well have the pack
        # installed, and the one line the installer adds to the global excludes
        # is exactly this filename. Git refusing to add it is the doctrine
        # working; the test needs it tracked anyway to prove the refusal.
        subprocess.run(
            ["git", "-C", str(repo), "add", "-f", sd_install.LOCAL_BLOCK_FILE],
            check=True,
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


class GitContextTests(InstallerHarness):
    """`git_context` describes the serving checkout, and must not raise.

    Every field it reports is diagnostic, so a git that is absent, broken, or
    pointed at a non-repository has to degrade to empty strings rather than
    take the whole command down with it.
    """

    def test_a_non_repository_reports_empty_fields(self):
        context = sd_install.git_context(self.home)
        self.assertEqual(context["commit"], "")
        self.assertEqual(context["branch"], "")
        self.assertFalse(context["dirty"])

    def test_a_missing_git_binary_is_not_fatal(self):
        with unittest.mock.patch(
            "subprocess.run", side_effect=OSError("no git here")
        ):
            context = sd_install.git_context(REPO_ROOT)
        self.assertEqual(context, {"commit": "", "branch": "", "dirty": False})

    def test_a_dirty_checkout_is_reported(self):
        repo = self.home / "dirty"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        (repo / "file.txt").write_text("untracked\n", encoding="utf-8")
        self.assertTrue(sd_install.git_context(repo)["dirty"])


class ExcludesTests(InstallerHarness):
    """The unsandboxed path, which the machine's real install takes."""

    def test_a_configured_excludes_file_is_honoured(self):
        """Writing our line into git's default while `core.excludesFile` names
        somewhere else would leave it configured and ignored."""
        configured = self.home / "somewhere" / "else"
        completed = subprocess.CompletedProcess([], 0, stdout=f"{configured}\n", stderr="")
        with unittest.mock.patch("subprocess.run", return_value=completed):
            resolved = sd_install.excludes_file(self.home, {})
        self.assertEqual(resolved, configured)

    def test_an_unconfigured_excludes_file_falls_back_to_the_xdg_default(self):
        completed = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with unittest.mock.patch("subprocess.run", return_value=completed):
            resolved = sd_install.excludes_file(
                self.home, {"XDG_CONFIG_HOME": str(self.home / "cfg")}
            )
        self.assertEqual(resolved, self.home / "cfg" / "git" / "ignore")

    def test_a_missing_git_binary_falls_back_rather_than_raising(self):
        with unittest.mock.patch("subprocess.run", side_effect=OSError("no git")):
            resolved = sd_install.excludes_file(self.home, {})
        self.assertEqual(resolved, self.home / ".config" / "git" / "ignore")

    def test_the_line_is_appended_to_a_file_with_no_trailing_newline(self):
        target = self.home / "ignore"
        target.write_text("*.log", encoding="utf-8")
        self.assertTrue(sd_install.ensure_excludes_line(target))
        self.assertEqual(
            target.read_text(encoding="utf-8"),
            f"*.log\n{sd_install.EXCLUDES_LINE}\n",
        )

    def test_a_dry_run_reports_the_change_without_making_it(self):
        target = self.home / "ignore"
        self.assertTrue(sd_install.ensure_excludes_line(target, dry_run=True))
        self.assertFalse(target.exists())

    def test_the_config_is_only_set_when_nothing_is_configured(self):
        calls = []

        def record(args, **kwargs):
            calls.append(args)
            if "--get" in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with unittest.mock.patch("subprocess.run", side_effect=record):
            sd_install.set_excludes_config(self.home / "ignore")
        self.assertEqual(len(calls), 2, "the config was not written")
        self.assertIn("core.excludesFile", calls[1])

    def test_an_existing_config_is_left_alone(self):
        completed = subprocess.CompletedProcess([], 0, stdout="/somewhere\n", stderr="")
        with unittest.mock.patch(
            "subprocess.run", return_value=completed
        ) as run:
            sd_install.set_excludes_config(self.home / "ignore")
        self.assertEqual(run.call_count, 1, "an existing core.excludesFile was rewritten")

    def test_a_dry_run_does_not_write_the_config(self):
        completed = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        with unittest.mock.patch("subprocess.run", return_value=completed) as run:
            sd_install.set_excludes_config(self.home / "ignore", dry_run=True)
        self.assertEqual(run.call_count, 1)

    def test_a_missing_git_binary_is_survivable(self):
        with unittest.mock.patch("subprocess.run", side_effect=OSError("no git")):
            sd_install.set_excludes_config(self.home / "ignore")


class ReceiptTests(InstallerHarness):
    def test_a_missing_or_unreadable_receipt_reads_as_empty(self):
        self.assertEqual(sd_install.read_receipt(self.home / "absent.json"), {})
        broken = self.home / "broken.json"
        broken.write_text("{ nope", encoding="utf-8")
        self.assertEqual(sd_install.read_receipt(broken), {})

    def test_a_receipt_that_is_not_an_object_reads_as_empty(self):
        listy = self.home / "list.json"
        listy.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(sd_install.read_receipt(listy), {})

    def test_malformed_owned_entries_are_ignored(self):
        self.assertEqual(sd_install.owned_entries({"owned": "not a list"}), [])
        self.assertEqual(
            sd_install.owned_entries({"owned": ["a string", {"no": "path"}]}), []
        )

    def test_the_receipt_is_replaced_atomically(self):
        target = self.home / "state" / "installed.json"
        sd_install.write_receipt(target, {"schema": 1})
        sd_install.write_receipt(target, {"schema": 2})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["schema"], 2)
        self.assertEqual(
            sorted(p.name for p in target.parent.iterdir()),
            ["installed.json"],
            "a scratch file was left behind",
        )


class PruneTests(InstallerHarness):
    def test_an_entry_with_no_path_or_an_absent_file_is_skipped_silently(self):
        skipped = sd_install.prune_stale(
            [
                {"path": 42, "sha256": "x"},
                {"path": str(self.home / "gone"), "sha256": "x"},
                {"path": str(self.home / "s"), "kind": "hook"},
            ],
            set(),
        )
        self.assertEqual(skipped, [])

    def test_an_unreadable_file_is_reported_rather_than_deleted(self):
        target = self.home / "unreadable"
        target.write_text("body\n", encoding="utf-8")
        entry = {"path": str(target), "sha256": "whatever"}
        with unittest.mock.patch.object(
            Path, "read_bytes", side_effect=OSError(13, "Permission denied")
        ):
            skipped = sd_install.prune_stale([entry], set())
        self.assertEqual(len(skipped), 1)
        self.assertIn("unreadable", skipped[0][1])
        self.assertTrue(target.exists())

    def test_a_failed_removal_is_reported_rather_than_swallowed(self):
        target = self.home / "stuck"
        body = b"body\n"
        target.write_bytes(body)
        entry = {"path": str(target), "sha256": sd_install.digest(body)}
        with unittest.mock.patch.object(
            Path, "unlink", side_effect=OSError(1, "Operation not permitted")
        ):
            skipped = sd_install.prune_stale([entry], set())
        self.assertEqual(len(skipped), 1)
        self.assertIn("could not remove", skipped[0][1])

    def test_a_dry_run_deletes_nothing(self):
        target = self.home / "kept"
        body = b"body\n"
        target.write_bytes(body)
        sd_install.prune_stale(
            [{"path": str(target), "sha256": sd_install.digest(body)}],
            set(),
            dry_run=True,
        )
        self.assertTrue(target.exists())

    def test_directory_pruning_stops_at_the_first_non_empty_parent(self):
        nest = self.home / "a" / "b" / "c"
        nest.mkdir(parents=True)
        (self.home / "a" / "keep.txt").write_text("x", encoding="utf-8")
        sd_install.prune_empty_dirs(nest)
        self.assertFalse((self.home / "a" / "b").exists())
        self.assertTrue((self.home / "a").exists(), "a populated parent was removed")


class HookEdgeCaseTests(InstallerHarness):
    def settings_path(self) -> Path:
        path = self.home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_a_non_object_settings_file_is_refused(self):
        path = self.settings_path()
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, "cmd")
        self.assertIn("not a JSON object", str(caught.exception))

    def test_a_non_object_hooks_key_is_refused(self):
        path = self.settings_path()
        path.write_text(json.dumps({"hooks": []}), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, "cmd")
        self.assertIn("non-object 'hooks'", str(caught.exception))

    def test_a_non_list_session_start_is_refused(self):
        path = self.settings_path()
        path.write_text(json.dumps({"hooks": {"SessionStart": {}}}), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, "cmd")
        self.assertIn("non-list", str(caught.exception))

    def test_a_matcher_group_with_a_non_list_hooks_key_is_refused(self):
        path = self.settings_path()
        path.write_text(
            json.dumps(
                {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": {}}]}}
            ),
            encoding="utf-8",
        )
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, "cmd")
        self.assertIn("non-list 'hooks'", str(caught.exception))

    def test_a_dry_run_registers_nothing(self):
        path = self.settings_path()
        self.assertTrue(sd_install.install_hook(path, "cmd", dry_run=True))
        self.assertFalse(path.exists())

    def test_removing_from_a_file_that_never_had_the_hook_changes_nothing(self):
        path = self.settings_path()
        self.assertFalse(sd_install.remove_hook(path, "cmd"))
        path.write_text("{ broken", encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, "cmd"))
        path.write_text("[]", encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, "cmd"))
        path.write_text(json.dumps({"hooks": []}), encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, "cmd"))
        path.write_text(json.dumps({"hooks": {"SessionStart": {}}}), encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, "cmd"))
        path.write_text(
            json.dumps({"hooks": {"SessionStart": [{"matcher": "startup"}]}}),
            encoding="utf-8",
        )
        self.assertFalse(sd_install.remove_hook(path, "cmd"))

    def test_groups_for_other_matchers_are_left_untouched(self):
        path = self.settings_path()
        other = {"matcher": "resume", "hooks": [{"command": "cmd"}]}
        path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            other,
                            {"matcher": "startup", "hooks": [{"command": "cmd"}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(sd_install.remove_hook(path, "cmd"))
        groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        self.assertEqual(groups, [other], "a matcher we never register on was changed")

    def test_an_already_empty_group_is_preserved_rather_than_swept_up(self):
        """We remove groups *we* emptied, not ones that arrived empty."""
        path = self.settings_path()
        path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {"matcher": "startup", "hooks": []},
                            {"matcher": "clear", "hooks": [{"command": "cmd"}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(sd_install.remove_hook(path, "cmd"))
        groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        self.assertEqual(groups, [{"matcher": "startup", "hooks": []}])

    def test_a_dry_run_removal_writes_nothing(self):
        path = self.settings_path()
        original = json.dumps(
            {"hooks": {"SessionStart": [{"matcher": "clear", "hooks": [{"command": "c"}]}]}}
        )
        path.write_text(original, encoding="utf-8")
        self.assertTrue(sd_install.remove_hook(path, "c", dry_run=True))
        self.assertEqual(path.read_text(encoding="utf-8"), original)


class DiscoveryTests(InstallerHarness):
    def test_a_checkout_with_no_skills_directory_finds_nothing(self):
        self.assertEqual(sd_install.discover_surfaces(self.home), [])

    def test_a_directory_without_a_skill_file_is_not_a_surface(self):
        skills = self.home / "skills"
        (skills / "sd-empty").mkdir(parents=True)
        (skills / "not-sd").mkdir()
        (skills / "not-sd" / sd_install.SKILL_FILE).write_text("x", encoding="utf-8")
        (skills / "loose.md").write_text("x", encoding="utf-8")
        self.assertEqual(sd_install.discover_surfaces(self.home), [])

    def test_user_refuses_a_checkout_with_no_surfaces(self):
        out = io.StringIO()
        ctx = sd_install.Context(
            checkout=self.home, home=self.home, environ=dict(os.environ)
        )
        self.assertEqual(sd_install.cmd_user(ctx, out), 1)
        self.assertIn("is this the pack checkout?", out.getvalue())


class StatusTests(InstallerHarness):
    def test_status_before_any_install_says_so(self):
        rc, output = self.run_cli("--status")
        self.assertEqual(rc, 0)
        self.assertIn("not installed", output)

    def test_status_after_install_reports_the_recorded_commit(self):
        self.install()
        rc, output = self.run_cli("--status")
        self.assertEqual(rc, 0)
        self.assertIn("checkout:", output)
        self.assertIn("0 missing, 0 modified", output)

    def test_status_counts_a_missing_render(self):
        self.install()
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        target = next(homes[0].root.glob("sd-*/SKILL.md"))
        target.unlink()
        _, output = self.run_cli("--status")
        self.assertIn("1 missing", output)

    def _committed_checkout(self) -> Path:
        """A real git checkout in the scratch home, at a known clean commit.

        `--status` reports dirtiness by asking git about the *serving* checkout,
        so a test that installs from this repository reports whatever the
        developer's working tree happens to be. That is not a test, it is a
        reading of the room: locally the tree was dirty and the branch was
        covered, on a clean CI checkout it was not, and the 100% gate failed
        with `bin/sd_install.py 519 1 196 1 99% 824`. Both sides of the branch
        are pinned here against a checkout this test owns.
        """
        checkout = self.home / "serving"
        folder = checkout / "skills" / "sd-probe"
        folder.mkdir(parents=True)
        (folder / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-probe\n---\n\nprobe\n", encoding="utf-8"
        )
        for argv in (
            ("init", "-q"),
            ("config", "user.email", "t@example.invalid"),
            ("config", "user.name", "t"),
            ("add", "-A"),
            ("commit", "-q", "-m", "probe"),
        ):
            subprocess.run(
                ["git", *argv], cwd=checkout, check=True, capture_output=True
            )
        return checkout

    def _status_of(self, checkout: Path) -> str:
        ctx = sd_install.Context(
            checkout=checkout, home=self.home, environ=dict(os.environ)
        )
        installed = io.StringIO()
        self.assertEqual(sd_install.cmd_user(ctx, installed), 0)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_status(ctx, out), 0)
        return out.getvalue()

    def test_a_clean_serving_checkout_is_not_reported_dirty(self):
        self.assertNotIn("checkout is dirty", self._status_of(self._committed_checkout()))

    def test_a_dirty_serving_checkout_is_reported(self):
        checkout = self._committed_checkout()
        (checkout / "skills" / "sd-probe" / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-probe\n---\n\nedited\n", encoding="utf-8"
        )
        self.assertIn("checkout is dirty", self._status_of(checkout))

    def test_status_names_legacy_residue(self):
        legacy = self.home / ".agents" / "skills" / "sd-old" / "SKILL.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("old\n", encoding="utf-8")
        receipt = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "machine"
            / "machine-receipt.json"
        )
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {"files": [{"family": "agents-skills", "path": "sd-old/SKILL.md"}]}
            ),
            encoding="utf-8",
        )
        _, output = self.run_cli("--status")
        self.assertIn("old fleet installer", output)

    def test_a_receipt_with_no_files_key_enumerates_nothing(self):
        receipt = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "machine"
            / "machine-receipt.json"
        )
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"schemaVersion": 1}), encoding="utf-8")
        self.assertEqual(
            sd_install.legacy_targets(
                self.home,
                {"XDG_STATE_HOME": str(self.home / ".local" / "state")},
            ),
            [],
        )

    def test_malformed_legacy_rows_are_skipped(self):
        receipt = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "machine"
            / "machine-receipt.json"
        )
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "files": [
                        "a string",
                        {"family": "agents-bin"},
                        {"family": 7, "path": "x"},
                        {"family": "agents-bin", "path": "tool", "digest": 9},
                    ]
                }
            ),
            encoding="utf-8",
        )
        found = sd_install.legacy_targets(
            self.home, {"XDG_STATE_HOME": str(self.home / ".local" / "state")}
        )
        self.assertEqual(found, [(self.home / ".agents" / "bin" / "tool", "")])


class PullBehaviourTests(InstallerHarness):
    def context(self, checkout: Path, **kwargs) -> "sd_install.Context":
        return sd_install.Context(
            checkout=checkout,
            home=self.home,
            environ={
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
            },
            **kwargs,
        )

    def make_main_checkout(self) -> Path:
        repo = self.home / "serving"
        repo.mkdir()
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", "-C", str(repo), *a], check=True, capture_output=True
        )
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "Test")
        (repo / "file.txt").write_text("body\n", encoding="utf-8")
        run("add", "file.txt")
        run("commit", "-qm", "initial")
        return repo

    def test_pull_refuses_a_dirty_checkout(self):
        repo = self.make_main_checkout()
        (repo / "file.txt").write_text("changed\n", encoding="utf-8")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_pull(self.context(repo), out), 1)
        self.assertIn("uncommitted changes", out.getvalue())

    def test_pull_refuses_off_main(self):
        repo = self.make_main_checkout()
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "-q", "-b", "sidebranch"],
            check=True,
            capture_output=True,
        )
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_pull(self.context(repo), out), 1)
        self.assertIn("not main", out.getvalue())

    def test_a_dry_run_pull_does_not_touch_git(self):
        repo = self.make_main_checkout()
        out = io.StringIO()
        rc = sd_install.cmd_pull(self.context(repo, dry_run=True), out)
        self.assertEqual(rc, 0)
        self.assertIn("would fast-forward", out.getvalue())

    def test_a_failed_fast_forward_is_reported_with_git_stderr(self):
        repo = self.make_main_checkout()
        out = io.StringIO()
        rc = sd_install.cmd_pull(self.context(repo), out)
        self.assertEqual(rc, 1, "a repo with no remote should fail to pull")
        self.assertIn("git pull --ff-only failed", out.getvalue())

    def test_a_successful_pull_re_renders(self):
        completed = subprocess.CompletedProcess([], 0, stdout="Already up to date.\n", stderr="")
        real = subprocess.run

        def fake(args, **kwargs):
            if "pull" in args:
                return completed
            return real(args, **kwargs)

        ctx = self.context(REPO_ROOT)
        out = io.StringIO()
        with unittest.mock.patch("subprocess.run", side_effect=fake):
            with unittest.mock.patch.object(
                sd_install, "git_context", return_value={"branch": "main", "commit": "a", "dirty": False}
            ):
                rc = sd_install.cmd_pull(ctx, out)
        self.assertEqual(rc, 0)
        self.assertIn("rendered", out.getvalue())


class RepoCommandTests(InstallerHarness):
    def test_repo_defaults_to_the_working_directory(self):
        repo = self.home / "here"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        cwd = os.getcwd()
        os.chdir(repo)
        try:
            rc, output = self.run_cli("--repo")
        finally:
            os.chdir(cwd)
        self.assertEqual(rc, 0)
        self.assertIn("added the sd block", output)

    def test_a_dry_run_repo_writes_nothing(self):
        repo = self.home / "dry"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        rc, output = self.run_cli("--repo", str(repo), "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("would have added", output)
        self.assertFalse((repo / sd_install.LOCAL_BLOCK_FILE).exists())

    def test_a_path_that_is_not_a_repository_still_gets_a_block(self):
        """`--repo` is about the local config file, not about git.

        A directory that is not a repository has nothing tracked, so the
        tracked-file refusal cannot fire and the block is simply written.
        """
        plain = self.home / "plain"
        plain.mkdir()
        self.assertEqual(sd_install.write_local_block(plain), "added")

    def test_a_missing_git_binary_does_not_report_a_file_as_tracked(self):
        with unittest.mock.patch("subprocess.run", side_effect=OSError("no git")):
            self.assertFalse(sd_install.path_is_tracked(self.home, "anything"))


class UninstallEdgeCaseTests(InstallerHarness):
    def test_a_dry_run_uninstall_removes_nothing(self):
        self.install()
        rc, output = self.run_cli("--uninstall", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("would remove", output)
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        self.assertTrue(any(homes[0].root.glob("sd-*")))

    def test_an_undeletable_receipt_does_not_fail_the_command(self):
        self.install()
        with unittest.mock.patch.object(
            Path, "unlink", side_effect=OSError(1, "nope")
        ):
            rc, _ = self.run_cli("--uninstall")
        self.assertEqual(rc, 0)


class AdoptLegacyEdgeCaseTests(InstallerHarness):
    def test_a_dry_run_removes_nothing(self):
        legacy = self.home / ".agents" / "skills" / "sd-old" / "SKILL.md"
        legacy.parent.mkdir(parents=True)
        body = b"old\n"
        legacy.write_bytes(body)
        receipt = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "machine"
            / "machine-receipt.json"
        )
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "family": "agents-skills",
                            "path": "sd-old/SKILL.md",
                            "digest": sd_install.digest(body),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        rc, output = self.run_cli("--adopt-legacy", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("would remove 1", output)
        self.assertTrue(legacy.exists())


class UsageTests(InstallerHarness):
    def test_help_prints_usage_and_succeeds(self):
        for flag in ("-h", "--help"):
            out = io.StringIO()
            self.assertEqual(sd_install.main([flag], out=out), 0)
            self.assertIn("usage:", out.getvalue())

    def test_home_without_a_directory_is_refused(self):
        out = io.StringIO()
        self.assertEqual(sd_install.main(["--user", "--home"], out=out), 2)
        self.assertIn("--home needs a directory", out.getvalue())


class StateRootTests(unittest.TestCase):
    """`state_home` must agree with the other bin/ tools, byte for byte.

    It is deliberately a copy of `bin/sd-handoff`'s helper rather than an
    import: the handoff tools have to work with no installer present at all,
    and sharing a module would make the installer a dependency of the thing it
    installs. A copy is only safe while it behaves identically, so both
    branches are pinned here -- plus the containment rule, which this one has
    and the handoff helper does not, because only this one takes a `--home`.
    """

    real_home = Path(os.path.expanduser("~"))

    def test_an_absolute_xdg_state_home_is_honoured_for_the_real_home(self):
        self.assertEqual(
            sd_install.state_home(
                self.real_home, {"XDG_STATE_HOME": "/somewhere/state"}
            ),
            Path("/somewhere/state"),
        )

    def test_an_unset_or_relative_value_falls_back_to_local_state(self):
        expected = self.real_home / ".local" / "state"
        self.assertEqual(sd_install.state_home(self.real_home, {}), expected)
        self.assertEqual(
            sd_install.state_home(self.real_home, {"XDG_STATE_HOME": ""}), expected
        )
        self.assertEqual(
            sd_install.state_home(self.real_home, {"XDG_STATE_HOME": "relative/path"}),
            expected,
        )

    def test_the_receipt_hangs_off_the_state_root(self):
        self.assertEqual(
            sd_install.receipt_path(self.real_home, {"XDG_STATE_HOME": "/s"}),
            Path("/s") / sd_install.STATE_DIR / sd_install.RECEIPT_NAME,
        )


class XdgContainmentTests(unittest.TestCase):
    """An XDG override must not carry a sandboxed run out of its home.

    This is the third `--home` escape of this rebuild and the one CI caught
    rather than the developer. The first two were git's global config; this
    one is the environment. All three had the same shape -- a second source of
    truth about where "home" is -- so all three are now answered the same way,
    by deriving the answer from the home that was actually passed.

    The failure is silent in exactly the way that matters: on a machine with
    the XDG variables unset (this developer's) everything agrees and the tests
    pass. On a GitHub runner `XDG_CONFIG_HOME` is set, and it pointed a
    question about a scratch install at `/home/runner/.config`.
    """

    def setUp(self):
        self._scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self._scratch.cleanup)
        self.home = Path(self._scratch.name).resolve()
        self.outside = {
            "XDG_CONFIG_HOME": "/home/runner/.config",
            "XDG_STATE_HOME": "/home/runner/.local/state",
        }

    def test_an_override_outside_a_sandbox_home_is_refused(self):
        self.assertEqual(
            sd_install.config_home(self.home, self.outside), self.home / ".config"
        )
        self.assertEqual(
            sd_install.state_home(self.home, self.outside),
            self.home / ".local" / "state",
        )

    def test_an_override_inside_a_sandbox_home_is_honoured(self):
        """Containment, not blanket refusal: a scratch XDG root is legitimate."""
        inside = {"XDG_CONFIG_HOME": str(self.home / "cfg")}
        self.assertEqual(
            sd_install.config_home(self.home, inside), self.home / "cfg"
        )

    def test_containment_is_by_path_parts_not_string_prefix(self):
        """`/tmp/home-2` is not inside `/tmp/home`, however it reads."""
        sibling = self.home.parent / (self.home.name + "-2")
        self.assertEqual(
            sd_install.config_home(self.home, {"XDG_CONFIG_HOME": str(sibling)}),
            self.home / ".config",
        )

    def test_every_rendered_root_stays_under_a_sandbox_home(self):
        """The assertion the CI failure would have needed to be caught here."""
        for platform in sd_install.platform_homes(self.home, self.outside):
            self.assertTrue(
                sd_install._is_within(platform.root, self.home),
                f"{platform.key} renders to {platform.root}, outside {self.home}",
            )

    def test_the_real_home_still_honours_an_override_outside_it(self):
        """Not a sandbox, so not this helper's business to second-guess."""
        real = Path(os.path.expanduser("~"))
        self.assertEqual(
            sd_install.config_home(real, {"XDG_CONFIG_HOME": "/srv/config"}),
            Path("/srv/config"),
        )


class RemainingBranchTests(InstallerHarness):
    def test_removing_the_hook_keeps_unrelated_hook_events(self):
        """`hooks` is only dropped when SessionStart was the last thing in it."""
        path = self.home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [{"matcher": "Bash", "hooks": []}],
                        "SessionStart": [
                            {"matcher": "clear", "hooks": [{"command": "ours"}]}
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(sd_install.remove_hook(path, "ours"))
        hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(list(hooks), ["PreToolUse"])

    def test_an_empty_configured_excludes_path_falls_through(self):
        """`git config --get` can exit 0 with an empty value."""
        completed = subprocess.CompletedProcess([], 0, stdout="\n", stderr="")
        with unittest.mock.patch("subprocess.run", return_value=completed):
            resolved = sd_install.excludes_file(self.home, {})
        self.assertEqual(resolved, self.home / ".config" / "git" / "ignore")

    def test_status_counts_a_modified_render(self):
        self.install()
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        target = next(homes[0].root.glob("sd-*/SKILL.md"))
        target.write_text("edited by hand\n", encoding="utf-8")
        _, output = self.run_cli("--status")
        self.assertIn("1 modified", output)

    def test_status_on_a_clean_checkout_says_nothing_about_dirtiness(self):
        out = io.StringIO()
        ctx = sd_install.Context(
            checkout=REPO_ROOT,
            home=self.home,
            environ={"XDG_STATE_HOME": str(self.home / ".local" / "state")},
        )
        with unittest.mock.patch.object(
            sd_install,
            "git_context",
            return_value={"commit": "abc", "branch": "main", "dirty": False},
        ):
            sd_install.write_receipt(ctx.receipt, {"checkout": "x", "commit": "abc"})
            sd_install.cmd_status(ctx, out)
        self.assertNotIn("dirty", out.getvalue())

    def test_uninstall_handles_a_receipt_with_no_hook_entry(self):
        body = b"body\n"
        orphan = self.home / "orphan.md"
        orphan.write_bytes(body)
        sd_install.write_receipt(
            self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json",
            {
                "schema": 1,
                "owned": [
                    {"path": str(orphan), "sha256": sd_install.digest(body), "kind": "skill"}
                ],
            },
        )
        rc, output = self.run_cli("--uninstall")
        self.assertEqual(rc, 0)
        self.assertIn("removed 1 file", output)
        self.assertFalse(orphan.exists())

    def test_without_home_the_real_home_is_used(self):
        """Read-only: `--status` never writes, so the real home is safe to probe."""
        out = io.StringIO()
        rc = sd_install.main(["--status"], out=out)
        self.assertEqual(rc, 0)
        self.assertIn("surfaces:", out.getvalue())

    def test_pull_is_reachable_from_the_command_line(self):
        """Dispatch coverage, with git_context stubbed so the outcome does not
        depend on which branch the checkout running the tests happens to be on."""
        out = io.StringIO()
        with unittest.mock.patch.object(
            sd_install,
            "git_context",
            return_value={"commit": "abc", "branch": "sidebranch", "dirty": False},
        ):
            rc = sd_install.main(["--pull", "--home", str(self.home)], out=out)
        self.assertEqual(rc, 1)
        self.assertIn("not main", out.getvalue())
