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

    def write_paths(self, checkout: Path, *names: str) -> Path:
        """The paths file a real checkout has, for a checkout a test built.

        The installer renders what a path names, so a fixture checkout without
        this file is not a smaller version of the real one -- it is a checkout
        the installer is right to refuse. Three paths because criterion 24 says
        three; the two empty ones are as legitimate as the full one.
        """
        path = checkout / "skills" / sd_install.PATHS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "paths": {
                        "research": {"summary": "sources to brief", "skills": list(names)},
                        "development": {"summary": "plan to ship", "skills": []},
                        "act": {"summary": "brief to send", "skills": []},
                    }
                }
            ),
            encoding="utf-8",
        )
        return path

    def committed_checkout(self, name: str = "serving") -> Path:
        """A real git checkout in the scratch home, at a known clean commit.

        The installer asks git about the *serving* checkout in two places: the
        `--status` report, and the `commit`, `branch` and `dirty` fields it
        writes into the receipt. A test that installs from this repository
        therefore records whatever the developer's working tree happens to be.
        That is not a test, it is a reading of the room: locally the tree was
        dirty and the branch was covered, on a clean CI checkout it was not,
        and the 100% gate failed with `bin/sd_install.py 519 1 196 1 99% 824`.
        Anything that asserts on those fields -- including the receipt byte
        comparison, where an unrelated edit landing between two installs used
        to flip `dirty` and fail it -- owns its checkout instead.
        """
        checkout = self.home / name
        folder = checkout / "skills" / "sd-probe"
        folder.mkdir(parents=True)
        (folder / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-probe\n---\n\nprobe\n", encoding="utf-8"
        )
        self.write_paths(checkout, "sd-probe")
        for argv in (
            ("init", "-q"),
            ("config", "user.email", "t@example.invalid"),
            ("config", "user.name", "t"),
            ("add", "-A"),
            ("commit", "-q", "-m", "probe"),
        ):
            subprocess.run(
                ["git", "-C", str(checkout), *argv], check=True, capture_output=True
            )
        return checkout

    def checkout_with_commands(self, *names: str) -> Path:
        """`committed_checkout()` given executables in `bin/`, the way the pack has them."""
        checkout = self.committed_checkout()
        (checkout / "bin").mkdir()
        for name in names:
            target = checkout / "bin" / name
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(0o755)
        return checkout

    def context_for(self, checkout: Path) -> "sd_install.Context":
        return sd_install.Context(
            checkout=checkout, home=self.home, environ=dict(os.environ)
        )

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
    def test_every_surface_preserves_body_and_invocation_policy(self):
        """Only Codex invocation metadata differs; all other bytes stay intact."""
        rc, _ = self.install()
        self.assertEqual(rc, 0)
        surfaces = sd_install.discover_surfaces(REPO_ROOT)
        self.assertTrue(surfaces, "no sd-* surfaces found in the checkout")
        homes = sd_install.platform_homes(self.home, dict(os.environ))
        for surface in surfaces:
            for home in homes:
                source = surface.skill.read_bytes()
                expected = source
                if home.key == "codex":
                    expected = source.replace(b"disable-model-invocation: true\n", b"")
                target = home.target_for(surface.name)
                self.assertTrue(target.exists(), f"{target} was not rendered")
                self.assertEqual(
                    target.read_bytes(),
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
        """Every row of the table, not just the first one.

        Two rows share `bin/sd-skill-use`, so a second run that keyed on the
        command rather than on the command-and-event pair would find the file
        already present and skip a registration it had never made.
        """
        self.install()
        self.install()
        hooks = self.settings["hooks"]
        for command, event, matchers in sd_install.HOOK_SPECS:
            groups = {group["matcher"]: group["hooks"] for group in hooks[event]}
            self.assertLessEqual(set(matchers), set(groups), event)
            for matcher in matchers:
                ours = [
                    entry
                    for entry in groups[matcher]
                    if entry["command"].endswith(command)
                ]
                self.assertEqual(
                    len(ours), 1, f"{event}/{matcher} has {len(ours)} of {command}"
                )

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

    def test_the_hook_table_is_exactly_these_three_registrations(self):
        """R10-D3 names the two SessionStart omissions as design.

        `compact` would consume the packet into the dying session and the
        `/clear` that follows -- the entire gesture -- would find nothing.

        The other two rows are one file on two events, and that is also
        design: `PreToolUse` sees a skill invoked or its `SKILL.md` read,
        `UserPromptSubmit` sees the bare slash form, which reaches no tool
        call at all. Pinned whole, because what the pack registers in
        somebody else's settings file is not a detail to drift.
        """
        self.assertEqual(
            sd_install.HOOK_SPECS,
            (
                ("bin/sd-handoff-restore", "SessionStart", ("startup", "clear")),
                ("bin/sd-skill-use", "PreToolUse", ("Skill|Read",)),
                ("bin/sd-skill-use", "UserPromptSubmit", ("",)),
            ),
        )


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
        self.write_paths(checkout, *names)
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
        # Retiring a skill is two edits now, not one: the directory goes and
        # the path stops naming it. A path naming a directory that is not
        # there is its own refusal, which is what criterion 24's second half
        # is for, so the test performs the whole retirement.
        self.write_paths(checkout, "sd-kept")
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
        # Retiring a skill is two edits now, not one: the directory goes and
        # the path stops naming it. A path naming a directory that is not
        # there is its own refusal, which is what criterion 24's second half
        # is for, so the test performs the whole retirement.
        self.write_paths(checkout, "sd-kept")
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
        # Retiring a skill is two edits now, not one: the directory goes and
        # the path stops naming it. A path naming a directory that is not
        # there is its own refusal, which is what criterion 24's second half
        # is for, so the test performs the whole retirement.
        self.write_paths(checkout, "sd-kept")
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


class TheSeamToTheReader(InstallerHarness):
    """The installer writes the block; `sd_lib` reads it. Cross the seam.

    This is the test whose absence let the two drift. The installer wrote
    `<!-- sd-ai-command-pack:begin -->` and `sd_lib.parse_local_block` looks
    for `<!-- SD-AI-COMMAND-PACK:LOCAL:START -->`, so it took the `start == -1`
    branch and returned `{}` for every block the installer had ever written --
    `mode`, `check`, `test`, `lint` and `reviewers` all unread. Nothing caught
    it because `mode`'s unread value and its fallback are both `full`, and
    because the reader's own tests (`tests/test_sd_review.py:140`, `:850`)
    hand-write the reader's markers rather than producing a block with the
    installer. Neither side was wrong on its own; only the seam was.
    """

    def make_repo(self, name: str = "seam") -> Path:
        repo = self.home / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        return repo

    def read_back(self, repo: Path) -> dict:
        sys.path.insert(0, str(REPO_ROOT / "bin"))
        import sd_lib

        return sd_lib.local_block(repo)

    def test_the_reader_reads_the_keys_the_installer_wrote(self):
        repo = self.make_repo()
        sd_install.write_local_block(repo, consent="codex@codex")
        block = self.read_back(repo)
        self.assertNotEqual(block, {}, "the reader found no block the installer wrote")
        self.assertEqual(block.get(sd_install.CONSENT_KEY), "codex@codex")

    def test_a_grant_is_the_only_key_the_block_sets(self):
        """The block carries the answer this run was given and nothing else.

        `--repo` wrote `mode: full` and three `<placeholder>` values into every
        repository it touched. Each of those keys resolves for itself when it
        is absent -- `mode` from the remote, the check names from the
        repository's own build file -- so a written copy is a default that
        drifts, and the fleet review found the file missing from fourteen of
        sixteen repositories with nothing broken by its absence.
        """
        repo = self.make_repo("granted")
        sd_install.write_local_block(repo, consent="codex@codex")
        self.assertEqual(self.read_back(repo), {sd_install.CONSENT_KEY: "codex@codex"})

    def test_without_a_grant_the_block_sets_nothing_at_all(self):
        repo = self.make_repo("ungranted")
        sd_install.write_local_block(repo)
        self.assertEqual(self.read_back(repo), {})

    def test_the_menu_of_keys_is_still_there_to_uncomment(self):
        """Commented out, not deleted: the block is where an operator finds
        the keys, and `WORKFLOW.md` is checked against this same template."""
        repo = self.make_repo("menu")
        sd_install.write_local_block(repo)
        text = (repo / sd_install.LOCAL_BLOCK_FILE).read_text(encoding="utf-8")
        for key in ("mode", "check", "test", "lint", sd_install.CONSENT_KEY):
            with self.subTest(key=key):
                self.assertIn(f"# {key}:", text)
                self.assertNotIn(f"\n    {key}:", text)

    def test_an_uncommented_answer_survives_the_refresh(self):
        """An operator's `mode: guest` is an answer, and a refresh keeps it.

        Until sd:1340 the refresh carried one key across, `reviewers`, read
        by `standing_consent` and handed back in as `consent`, and rewrote
        every other line from the template: the line the operator had
        uncommented went out commented again, silently, on every `--repo`
        run. The text after the colon comes across as written, inline
        comment included, so a refresh never rewrites a line it did not
        write.
        """
        repo = self.make_repo("answered")
        sd_install.write_local_block(repo, consent="codex@codex")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        text = target.read_text(encoding="utf-8")
        self.assertIn("    # mode: full\n", text)
        target.write_text(text.replace("    # mode: full\n", "    mode: guest  # a fork\n"),
                          encoding="utf-8")
        self.assertEqual(sd_install.write_local_block(repo, consent="codex@codex"),
                         "refreshed")
        refreshed = target.read_text(encoding="utf-8")
        self.assertIn("    mode: guest  # a fork\n", refreshed,
                      "the operator's line did not survive the refresh")
        self.assertEqual(self.read_back(repo),
                         {"mode": "guest", sd_install.CONSENT_KEY: "codex@codex"})

    def test_a_line_that_only_repeats_the_template_is_still_retired(self):
        """`mode: full` and a `<placeholder>` value are the copies `--repo`
        once wrote, not answers; a refresh still puts them back commented."""
        repo = self.make_repo("copied")
        sd_install.write_local_block(repo)
        target = repo / sd_install.LOCAL_BLOCK_FILE
        text = target.read_text(encoding="utf-8")
        target.write_text(text.replace("    # mode: full\n", "    mode: full\n")
                          .replace("    # check:", "    check:"), encoding="utf-8")
        self.assertEqual(sd_install.write_local_block(repo), "refreshed")
        self.assertEqual(self.read_back(repo), {})

    def test_a_repeated_key_carries_what_the_reader_reads(self):
        """The reader takes the last occurrence; so does the carry.

        Filtering line by line skipped a final `mode: full` as a template
        copy and carried the `mode: guest` above it, so a refresh resurrected
        a setting the reader had already retired (codex review of sd:1340).
        """
        sys.path.insert(0, str(REPO_ROOT / "bin"))
        import sd_lib

        for body, expected in (
            ("    mode: guest\n    mode: full\n", {}),
            ("    mode: full\n    mode: guest\n", {"mode": "guest"}),
        ):
            with self.subTest(body=body):
                repo = self.make_repo(f"repeated-{len(expected)}")
                target = repo / sd_install.LOCAL_BLOCK_FILE
                target.write_text(f"{sd_install.BLOCK_BEGIN}\n{body}{sd_install.BLOCK_END}\n",
                                  encoding="utf-8")
                before = sd_lib.local_block(repo).get("mode")
                self.assertEqual(sd_install.write_local_block(repo), "refreshed")
                self.assertEqual(self.read_back(repo), expected)
                self.assertEqual(self.read_back(repo).get("mode"),
                                 None if before == "full" else before)

    def test_the_standing_grant_survives_a_refresh_given_no_answer(self):
        """No consent in hand means inherit, not revoke: the grant already on
        the line is an uncommented key like any other."""
        repo = self.make_repo("standing")
        sd_install.write_local_block(repo, consent="codex@codex")
        self.assertEqual(sd_install.write_local_block(repo), "refreshed")
        self.assertEqual(self.read_back(repo), {sd_install.CONSENT_KEY: "codex@codex"})

    def test_an_empty_grant_is_written_and_denies(self):
        """Empty is an answer -- consent withheld -- and not the same as
        unset, which inherits the machine's standing authorization."""
        repo = self.make_repo("denied")
        sd_install.write_local_block(repo, consent="")
        self.assertEqual(self.read_back(repo), {sd_install.CONSENT_KEY: ""})
        self.assertEqual(sd_install.standing_consent(repo), "")

    def test_a_block_written_under_the_old_markers_is_migrated_in_place(self):
        """Not appended beside. The operator's answers are in the old one.

        There is no machine-scope migration that could do this instead:
        `--adopt-legacy` enumerates the old fleet installer's renders from its
        own receipt, and no receipt anywhere lists the repositories that carry
        a block. The next `--repo` run inside the repository is the only
        moment the correction can happen.
        """
        repo = self.make_repo("old")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        old_begin, old_end = (old for old, _ in sd_install.LEGACY_BLOCK_MARKERS)
        target.write_text(
            f"# notes\n\n{old_begin}\nbody\n\n    mode: guest\n"
            f"    {sd_install.CONSENT_KEY}: codex@codex\n{old_end}\n",
            encoding="utf-8",
        )
        self.assertEqual(sd_install.write_local_block(repo, consent="codex@codex"),
                         "refreshed")
        text = target.read_text(encoding="utf-8")
        self.assertNotIn(old_begin, text, "the unreadable markers survived")
        self.assertEqual(text.count(sd_install.BLOCK_BEGIN), 1, "a second block")
        self.assertIn("# notes", text)
        self.assertEqual(self.read_back(repo).get(sd_install.CONSENT_KEY), "codex@codex")

    def test_only_the_markers_changing_is_still_written(self):
        """The one way a migration silently does nothing.

        The refresh compares against what was read; had it compared against
        the migrated copy, a file whose sole difference is the marker pair
        would be byte-identical to it, no write would happen, and the
        repository would stay on the markers nothing reads.
        """
        repo = self.make_repo("same")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        sd_install.write_local_block(repo)
        current = target.read_text(encoding="utf-8")
        for old, new in sd_install.LEGACY_BLOCK_MARKERS:
            current = current.replace(new, old)
        target.write_text(current, encoding="utf-8")
        sd_install.write_local_block(repo)
        self.assertIn(sd_install.BLOCK_BEGIN, target.read_text(encoding="utf-8"))


REGISTRY_FIXTURE = """\
bills:
  anthropic: { cost: subscription }
  local:     { cost: local }

providers:
  claude:   { start: "claude -p", vendor: anthropic, bill: anthropic,
              roles: [author], reader: claude-json, env: [] }
  plain:    { url: "https://inference.baseten.co/v1", model: m, vendor: v1,
              bill: local, roles: [reviewer], env: [] }
  spaced:   { start: "'/opt/my tools/codex' exec", vendor: v2, bill: local,
              roles: [reviewer], reader: codex-json, env: [] }
  hashed:   { start: "/opt/x#y/tool run", vendor: v4, bill: local,
              roles: [reviewer], reader: codex-json, env: [] }
  userinfo: { url: "https://p:pw@host.example/v1", model: m, vendor: v5,
              bill: local, roles: [reviewer], env: [] }
  commaed:  { start: "/opt/a,b/tool run", vendor: v3, bill: local,
              roles: [reviewer], reader: codex-json, env: [] }
  residue:  { url: "https://host.example+abcdef12/v1", model: m, vendor: v6,
              bill: local, roles: [reviewer], env: [] }

roles:
  author:   [claude]
  reviewer: [plain, spaced, hashed, userinfo, commaed, residue]
"""


class ConsentPromptTests(InstallerHarness):
    """`--repo` asks once who may receive this repository's diff.

    Capability is the registry; permission is the `reviewers` line. The
    installer offers the enabled reviewer entries with the recipients they
    reach and writes the pairs for the ones it is told, taking none as an
    answer and filling in no default.
    """

    def make_repo(self, name: str = "consented") -> Path:
        repo = self.home / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        return repo

    def seed_registry(self, text: str = REGISTRY_FIXTURE) -> None:
        path = self.home / sd_install.REGISTRY_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def registry(self):
        sys.path.insert(0, str(REPO_ROOT / "bin"))
        import sd_registry

        return sd_registry

    def consent_line(self, repo: Path) -> str | None:
        sys.path.insert(0, str(REPO_ROOT / "bin"))
        import sd_lib

        return sd_lib.local_block(repo).get(sd_install.CONSENT_KEY)

    # -- the round trip, end to end ------------------------------------

    def test_every_recipient_shape_survives_write_then_read_then_parse(self):
        """The requirement: what is written parses back as what was offered.

        Four shapes the parser is explicitly built for -- a plain host, an
        executable holding a space, one holding a `#` (not a comment on this
        line), and a url whose netloc carries userinfo (`p:pw@host`, split on
        the *first* `@` only). The path is the real one: the installer writes
        the block, `sd_lib` reads the key out of it, `parse_consent` reads the
        pairs out of the value. A recipient that came back different would be
        this repository's diff going somewhere nobody agreed to.
        """
        self.seed_registry()
        repo = self.make_repo()
        names = "plain spaced hashed userinfo"
        rc, output = self.run_cli("--repo", str(repo), "--reviewers", names)
        self.assertEqual(rc, 0, output)

        sd_registry = self.registry()
        offered = {
            entry.name: sd_registry.recipient(entry)
            for entry in sd_registry.read_file(
                self.home / sd_install.REGISTRY_RELATIVE
            ).order("reviewer")
        }
        parsed = sd_registry.parse_consent(self.consent_line(repo))
        self.assertEqual(parsed, {name: offered[name] for name in names.split()})
        self.assertEqual(
            [parsed[n].recipient for n in ("plain", "spaced", "hashed", "userinfo")],
            ["inference.baseten.co", "/opt/my tools/codex", "/opt/x#y/tool",
             "p:pw@host.example"],
        )

    def test_a_comma_in_a_recipient_now_reads_back_and_is_written(self):
        """The comma defect is fixed at its source, so the guard steps aside.

        `Allowance.__str__` used to quote through `shlex.quote` alone, whose
        safe set includes the comma `consent_parts` splits on: `commaed`'s
        executable holds one, so its pair rendered bare and came back as a
        different recipient beside a fabricated second grant. The installer
        could not fix that where it lives and refused to write it instead.
        `sd_registry._one_word` now quotes on this module's own rule, so the
        pair round-trips and there is nothing left to refuse. Asserted as the
        round trip rather than as the absence of a warning, so a regression in
        the quoting fails here and not merely in the registry's own suite.
        """
        self.seed_registry()
        repo = self.make_repo("comma")
        rc, output = self.run_cli("--repo", str(repo), "--reviewers", "commaed")
        self.assertEqual(rc, 0, output)
        self.assertNotIn("does not read back", output)

        sd_registry = self.registry()
        offered = {
            entry.name: sd_registry.recipient(entry)
            for entry in sd_registry.read_file(
                self.home / sd_install.REGISTRY_RELATIVE
            ).order("reviewer")
        }
        parsed = sd_registry.parse_consent(self.consent_line(repo))
        self.assertEqual(list(parsed), ["commaed"])
        self.assertEqual(parsed["commaed"].recipient, offered["commaed"].recipient)
        self.assertIn(",", parsed["commaed"].recipient)

    def test_a_pair_that_does_not_read_back_is_never_written(self):
        """The guard, on the one shape quoting cannot separate.

        A recipient ending in `+` and exactly `FINGERPRINT_LENGTH` hex
        characters is spelled identically to recipient-plus-fingerprint, and
        no quoting distinguishes them: the split happens after the quotes are
        gone. Only a `url` entry reaches it -- a `start` entry always has a
        real fingerprint appended after, so it round-trips. `residue`'s netloc
        is `host.example+abcdef12`, which reads back as the bare
        `host.example`: a well-formed pair naming a host nobody consented to.
        The installer cannot fix that where it lives; it can refuse to write
        it, which is what this asserts.
        """
        self.seed_registry()
        repo = self.make_repo("residue")
        rc, output = self.run_cli("--repo", str(repo), "--reviewers", "residue")
        self.assertEqual(rc, 2)
        self.assertIn("does not read back", output)
        self.assertIsNone(self.consent_line(repo))

    def test_a_line_that_cannot_be_read_at_all_refuses_by_the_other_arm(self):
        """`reads_back`'s second arm: the read raises instead of differing.

        `residue` reaches the comparison -- the block parses, the pairs come
        back, and they are not the pairs offered. A recipient holding a
        newline never gets that far: the block is line-based, so its second
        line is not `key: value` and `parse_local_block` raises. Both arms
        have to refuse, because a writer that let an unreadable line through
        would be trusting a check that never ran.

        Called directly rather than through the CLI. A newline cannot reach a
        recipient from the registry -- YAML resolves the escape and `shlex`
        then drops the backslash, so `"/opt/a\\nb/tool"` arrives as
        `/opt/anb/tool` -- and building a fixture that pretends otherwise
        would assert something the parser cannot produce. The arm is real
        regardless of which caller reaches it: it is what stands between a
        line the reader chokes on and that line being written anyway.
        """
        sd_registry = self.registry()
        pair = sd_registry.Allowance("entry", "host.example\nrogue: evil")
        self.assertFalse(sd_install.reads_back(str(pair), [pair]))

    # -- refusals grant nothing ----------------------------------------

    def test_a_name_nobody_offered_writes_no_line_and_says_so(self):
        self.seed_registry()
        repo = self.make_repo("unknown")
        rc, output = self.run_cli("--repo", str(repo), "--reviewers", "plain nosuch")
        self.assertEqual(rc, 2)
        self.assertIn("no entry named nosuch", output)
        self.assertIsNone(self.consent_line(repo), "a partial answer granted something")

    def test_an_empty_answer_writes_explicit_denial(self):
        self.seed_registry()
        repo = self.make_repo("nobody")
        rc, output = self.run_cli("--repo", str(repo), "--reviewers", "")
        self.assertEqual(rc, 0)
        self.assertIn("consents to nobody", output)
        self.assertEqual(self.consent_line(repo), "")

    def test_empty_line_denies_the_first_review(self):
        """What "grants nothing" means at the other end of the seam."""
        self.seed_registry()
        repo = self.make_repo("refused")
        self.run_cli("--repo", str(repo), "--reviewers", "")
        self.assertEqual(self.registry().parse_consent(self.consent_line(repo)), {})

    def test_a_registry_with_nothing_enabled_offers_nothing(self):
        repo = self.make_repo("bare")
        rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 0)
        self.assertIn("no enabled reviewer entry", output)
        self.assertIsNone(self.consent_line(repo))

    # -- asked once, kept ever after -----------------------------------

    def test_a_rerun_keeps_the_answer_and_asks_nothing(self):
        self.seed_registry()
        repo = self.make_repo("kept")
        self.run_cli("--repo", str(repo), "--reviewers", "plain")
        first = self.consent_line(repo)
        rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 0)
        self.assertIn("already answered", output)
        self.assertNotIn("which of these", output, "a rerun re-asked")
        self.assertEqual(self.consent_line(repo), first)

    def test_the_shipped_placeholder_is_not_an_answer(self):
        """A line nobody wrote grants nothing, so the prompt still runs."""
        self.seed_registry()
        repo = self.make_repo("placeholder")
        (repo / sd_install.LOCAL_BLOCK_FILE).write_text(
            f"{sd_install.BLOCK_BEGIN}\n{sd_install.DEFAULT_BLOCK_BODY}"
            f"{sd_install.BLOCK_END}\n",
            encoding="utf-8",
        )
        self.assertIsNone(sd_install.standing_consent(repo))
        rc, output = self.run_cli("--repo", str(repo), "--reviewers", "plain")
        self.assertEqual(rc, 0)
        self.assertEqual(self.consent_line(repo), "plain@inference.baseten.co")

    def test_a_file_with_no_block_at_all_has_no_standing_answer(self):
        repo = self.make_repo("noblock")
        (repo / sd_install.LOCAL_BLOCK_FILE).write_text(
            f"    {sd_install.CONSENT_KEY}: plain@elsewhere\n", encoding="utf-8"
        )
        self.assertIsNone(
            sd_install.standing_consent(repo),
            "a line outside the block was read as consent",
        )

    def test_a_block_with_the_key_deleted_has_no_standing_answer(self):
        repo = self.make_repo("nokey")
        sd_install.write_local_block(repo)
        self.assertIsNone(sd_install.standing_consent(repo))

    # -- interactive and not -------------------------------------------

    def test_a_terminal_is_offered_the_entries_and_its_answer_is_written(self):
        self.seed_registry()
        repo = self.make_repo("tty")
        stdin = unittest.mock.Mock()
        stdin.isatty.return_value = True
        stdin.readline.return_value = "plain, userinfo\n"
        with unittest.mock.patch.object(sys, "stdin", stdin):
            rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 0)
        self.assertIn("which of these may receive", output)
        self.assertIn("plain@inference.baseten.co", output)
        self.assertEqual(
            self.consent_line(repo),
            "plain@inference.baseten.co, userinfo@p:pw@host.example",
        )

    def test_a_non_interactive_run_without_the_flag_writes_no_line(self):
        """The plan's clause: `--reviewers` or nothing. Never a default."""
        self.seed_registry()
        repo = self.make_repo("piped")
        stdin = unittest.mock.Mock()
        stdin.isatty.return_value = False
        with unittest.mock.patch.object(sys, "stdin", stdin):
            rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 0)
        self.assertIn("consents to nobody", output)
        self.assertIsNone(self.consent_line(repo))
        stdin.readline.assert_not_called()

    def test_the_flag_needs_a_value(self):
        """`main` directly: `run_cli` appends `--home`, which the flag would
        swallow as its value, and the refusal under test would never fire."""
        out = io.StringIO()
        rc = sd_install.main(["--repo", "--reviewers"], out=out)
        self.assertEqual(rc, 2)
        self.assertIn("needs the entry names", out.getvalue())


#: `DEFAULT_BLOCK_BODY` as `bin/sd_install.py` spelled it at 43170716
#: (2026-08-30, "machine-scope installer replaces the render payload"), the
#: body every `--repo` run wrote for the week that followed. Verbatim, not
#: paraphrased: the second line is what the reader raises on.
OLD_BODY_43170716 = """\
sd-ai-command-pack, machine-scope. Work items live under `docs/work/`; nothing
else in this repo belongs to the framework.

    mode: full
    check: <the command that verifies this repo, e.g. `make check`>
"""

#: The same at d48d7a19, the last commit before 26501c3e switched the markers
#: on 2026-09-06: ffb86115 had grown the prose to three lines and the menu to
#: five keys that same morning. Also verbatim.
OLD_BODY_D48D7A19 = """\
sd-ai-command-pack, machine-scope. Work items live under `docs/work/`; nothing
else in this repo belongs to the framework. The workflow these keys override is
`WORKFLOW.md` in the pack checkout; it is the one page that states the policy.

    mode: full
    check: <the command that verifies this repo, e.g. `make check`>
    test: <optional, when this repo spells its tests separately>
    lint: <optional, same>
    reviewers: <registry entries allowed to receive this repo's diff>
"""

OLD_BODIES = {"43170716": OLD_BODY_43170716, "d48d7a19": OLD_BODY_D48D7A19}


class OldBlockRefreshTests(InstallerHarness):
    """`--repo` refreshes the block it wrote before 2026-09-06 (sd:928).

    `cmd_repo` reads the standing consent before it writes, through
    `migrated` and then the reader. `migrated` rewrites only the markers; the
    old body opens with unmarked prose, which is not `key: value`, so the
    reader raised `ConfigError` on line 2, `cmd_repo` printed `error:` and
    returned 2, and `write_local_block` -- the one place that could replace
    the body -- was never reached. The refresh failed on exactly the block it
    exists to correct, on every machine set up before then. The migration
    test beside this one never saw it: it calls `write_local_block` directly
    with a consent in hand, and so never crosses the read.
    """

    OLD_BEGIN, OLD_END = (old for old, _ in sd_install.LEGACY_BLOCK_MARKERS)
    GRANT = "plain@inference.baseten.co"
    PLACEHOLDER = "    reviewers: <registry entries allowed to receive this repo's diff>\n"

    def make_repo(self, name: str) -> Path:
        repo = self.home / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        return repo

    def seed_registry(self) -> None:
        path = self.home / sd_install.REGISTRY_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(REGISTRY_FIXTURE, encoding="utf-8")

    def read_back(self, repo: Path) -> dict:
        sys.path.insert(0, str(REPO_ROOT / "bin"))
        import sd_lib

        return sd_lib.local_block(repo)

    def old_file(self, body: str, *, grant: str | None = None) -> str:
        """The operator's notes, then the old block as the installer left it.

        A grant is what an operator would have written by hand into that
        block: the placeholder line replaced (d48d7a19) or a line added under
        the two keys the template had (43170716), on its own line either way.
        """
        if grant is not None:
            body = body.replace(self.PLACEHOLDER, "") + f"    {sd_install.CONSENT_KEY}: {grant}\n"
        return f"# notes\n\n{self.OLD_BEGIN}\n{body}{self.OLD_END}\n"

    def assert_refreshed(self, repo: Path, text: str) -> None:
        self.assertNotIn(self.OLD_BEGIN, text, "the unreadable markers survived")
        self.assertNotIn(self.OLD_END, text, "the unreadable markers survived")
        self.assertEqual(text.count(sd_install.BLOCK_BEGIN), 1, "a second block")
        self.assertEqual(text.count(sd_install.BLOCK_END), 1, "a second block")
        self.assertTrue(text.startswith("# notes\n"), "the operator's notes moved")
        # The new body says the same thing behind `#`; the unmarked line is
        # the one the reader raised on.
        self.assertNotIn("\nsd-ai-command-pack, machine-scope", text, "the unmarked prose survived")

    def test_an_old_block_with_a_grant_is_refreshed_and_the_grant_kept(self):
        """rc 0, the reader's markers, a body the reader parses, the grant.

        The grant is the one thing an operator could have written into the
        old body and the one key with no fallback, so it must come through
        the refresh: read on its own line when the body as a whole raises.
        """
        for commit, body in OLD_BODIES.items():
            with self.subTest(commit=commit):
                self.seed_registry()
                repo = self.make_repo(f"granted-{commit}")
                target = repo / sd_install.LOCAL_BLOCK_FILE
                target.write_text(self.old_file(body, grant=self.GRANT), encoding="utf-8")
                self.assertEqual(sd_install.standing_consent(repo), self.GRANT)
                rc, output = self.run_cli("--repo", str(repo))
                self.assertEqual(rc, 0, output)
                self.assertIn("already answered here", output)
                self.assertIn("refreshed the sd block", output)
                text = target.read_text(encoding="utf-8")
                self.assert_refreshed(repo, text)
                self.assertEqual(self.read_back(repo), {sd_install.CONSENT_KEY: self.GRANT})

    def test_an_old_block_without_a_grant_is_refreshed_and_asked(self):
        """No grant in the old body is no standing answer: the prompt runs,
        `--reviewers` answers it, and the placeholder is still not an answer."""
        for commit, body in OLD_BODIES.items():
            with self.subTest(commit=commit):
                self.seed_registry()
                repo = self.make_repo(f"asked-{commit}")
                target = repo / sd_install.LOCAL_BLOCK_FILE
                target.write_text(self.old_file(body), encoding="utf-8")
                self.assertIsNone(sd_install.standing_consent(repo))
                rc, output = self.run_cli("--repo", str(repo), "--reviewers", "plain")
                self.assertEqual(rc, 0, output)
                self.assertNotIn("already answered", output)
                self.assert_refreshed(repo, target.read_text(encoding="utf-8"))
                self.assertEqual(self.read_back(repo), {sd_install.CONSENT_KEY: self.GRANT})

    def test_the_prose_the_refresh_reads_past_is_the_prose_the_installer_wrote(self):
        """Two spellings of the old prose, one here and one in the installer,
        and the fixture is the one copied out of git: every unmarked line of
        both old bodies is in `LEGACY_BLOCK_PROSE`, and nothing else is."""
        unmarked = {
            line.strip()
            for body in OLD_BODIES.values()
            for line in body.split("\n")
            if line.strip() and ":" not in line
        }
        self.assertEqual(unmarked, set(sd_install.LEGACY_BLOCK_PROSE))

    def test_a_malformed_grant_in_an_old_block_still_refuses(self):
        """Reading past our prose is not reading loosely: what the grant line
        says still goes through `parse_consent`, and a bare name consents to
        nobody."""
        repo = self.make_repo("bare-name")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        before = self.old_file(OLD_BODY_D48D7A19, grant="plain")
        target.write_text(before, encoding="utf-8")
        rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 2)
        self.assertIn("bare name", output)
        self.assertEqual(target.read_text(encoding="utf-8"), before, "a refused run wrote")

    def test_an_operators_own_unreadable_line_in_an_old_block_still_refuses(self):
        """Only our lines come out. `reviewers ""` is a denial with the colon
        missing; read past it, the refresh would write a block with no
        `reviewers` line and the repository would inherit the machine's
        policy -- consent widened by a typo. So it is refused, as
        `test_malformed_local_syntax_and_unreadable_file_refuse_without_overwrite`
        requires of a current block, with the file left as it was."""
        repo = self.make_repo("typo")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        before = self.old_file(OLD_BODY_43170716.replace("    mode: full\n", '    reviewers ""\n'))
        target.write_text(before, encoding="utf-8")
        rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 2, output)
        self.assertIn("'reviewers \"\"' is not `key: value`", output)
        self.assertEqual(target.read_text(encoding="utf-8"), before, "a refused run wrote")

    def test_an_old_block_with_a_half_open_pair_is_still_refused(self):
        """The body is ours; the markers are the operator's. An old block
        missing its end marker is refused before its body is read at all,
        and the file is left exactly as it was."""
        repo = self.make_repo("half-open")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        before = f"# notes\n\n{self.OLD_BEGIN}\n{OLD_BODY_D48D7A19}"
        target.write_text(before, encoding="utf-8")
        rc, output = self.run_cli("--repo", str(repo))
        self.assertEqual(rc, 2)
        self.assertIn("start marker with no end marker", output)
        self.assertEqual(target.read_text(encoding="utf-8"), before, "a refused run wrote")

    def test_an_old_block_in_a_tracked_file_is_still_refused(self):
        """P6 holds for the old block too: tracked is tracked."""
        repo = self.make_repo("tracked")
        target = repo / sd_install.LOCAL_BLOCK_FILE
        before = self.old_file(OLD_BODY_43170716)
        target.write_text(before, encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "add", "-f", sd_install.LOCAL_BLOCK_FILE],
            check=True,
        )
        ctx = sd_install.Context(checkout=REPO_ROOT, home=self.home, environ={})
        with self.assertRaises(SystemExit) as caught:
            sd_install.cmd_repo(ctx, repo, io.StringIO())
        self.assertIn("refusing to edit a tracked file", str(caught.exception))
        self.assertEqual(target.read_text(encoding="utf-8"), before, "a refused run wrote")


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

    def legacy_receipt_file(self) -> Path:
        return (
            self.home
            / ".local"
            / "state"
            / "sd-ai-command-pack"
            / "machine"
            / "machine-receipt.json"
        )

    def seed(self, family: str, rel: str, body: bytes) -> dict:
        roots = {
            "agents-skills": self.home / ".agents" / "skills",
            "opencode-commands": self.home / ".config" / "opencode" / "commands",
        }
        path = roots[family] / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return {"family": family, "path": rel, "digest": sd_install.digest(body)}

    def test_the_removal_count_is_measured_before_the_removal(self):
        """The count is the only output, so a count read after the fact lies.

        `present` used to be computed from the disk *after* pruning, which made
        a run that deleted every recorded file report the survivors instead --
        on this machine, "removed 5" for a 112-file removal. The number a
        migration step prints is the number its operator checks.
        """
        rows = [
            self.seed("agents-skills", f"sd-gone-{n}/SKILL.md", b"legacy %d\n" % n)
            for n in range(4)
        ]
        self.write_legacy_receipt(rows)
        rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertIn("4 recorded, 4 still present, removed 4", output)

    def test_a_colliding_name_is_kept_and_not_counted_as_removed(self):
        """`--user` overwrites collisions; adoption must not claim them."""
        kept = self.seed("opencode-commands", "sd-check.md", b"old sd-check\n")
        gone = self.seed("agents-skills", "sd-retired/SKILL.md", b"no successor\n")
        self.write_legacy_receipt([kept, gone])
        rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertIn("2 recorded, 2 still present, removed 1", output)
        self.assertIn("1 kept for --user to overwrite", output)
        self.assertTrue(
            (self.home / ".config" / "opencode" / "commands" / "sd-check.md").exists()
        )

    def test_adoption_retires_the_receipt_and_stops_the_status_advice(self):
        """The ratchet has to latch, or --status advises a done migration forever."""
        self.write_legacy_receipt(
            [self.seed("opencode-commands", "sd-check.md", b"old sd-check\n")]
        )
        rc, _ = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertFalse(self.legacy_receipt_file().exists())
        self.install()
        rc, output = self.run_cli("--status")
        self.assertEqual(rc, 0)
        self.assertNotIn("legacy:", output)

    def test_an_unremovable_receipt_is_reported_not_swallowed(self):
        """--status keeps advising the migration, so silence would strand it."""
        self.write_legacy_receipt(
            [self.seed("opencode-commands", "sd-check.md", b"old sd-check\n")]
        )
        with unittest.mock.patch.object(
            Path, "unlink", side_effect=OSError(13, "Permission denied")
        ):
            rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertIn("could not retire the legacy receipt", output)
        self.assertIn("Permission denied", output)

    def test_a_skipped_file_keeps_the_receipt_for_a_second_attempt(self):
        edited = self.seed("agents-skills", "sd-edited/SKILL.md", b"changed\n")
        edited["digest"] = sd_install.digest(b"what was installed\n")
        self.write_legacy_receipt([edited])
        rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertIn("modified since it was installed", output)
        self.assertTrue(self.legacy_receipt_file().exists())

    def test_status_does_not_call_its_own_renders_legacy(self):
        """A recorded name the current render owns is ours, not a leftover."""
        self.install()
        self.write_legacy_receipt(
            [{"family": "opencode-commands", "path": "sd-check.md", "digest": "stale"}]
        )
        rc, output = self.run_cli("--status")
        self.assertEqual(rc, 0)
        self.assertIn("0 missing, 0 modified", output)
        self.assertNotIn("legacy:", output)

    def test_adopt_legacy_is_a_clean_no_op_without_a_receipt(self):
        rc, output = self.run_cli("--adopt-legacy")
        self.assertEqual(rc, 0)
        self.assertIn("no legacy receipt", output)


class ReceiptCanonicalTests(InstallerHarness):
    """The receipt is an artifact others diff, so its bytes have to mean something."""

    def test_owned_is_sorted_by_path(self):
        self.install()
        paths = [row["path"] for row in self.receipt["owned"]]
        self.assertEqual(paths, sorted(paths))

    def test_two_runs_of_the_same_checkout_write_identical_bytes(self):
        """Byte equality, against a checkout whose git state cannot move.

        The receipt records the serving checkout's commit, branch and dirty
        flag, and the CLI's default checkout is this repository. Installing
        twice from it compared two readings of the developer's working tree,
        so any edit landing between them flipped `dirty` false to true and
        failed a test about the installer's own determinism. The fixture is a
        real repository at a known clean commit, which is what makes "the same
        checkout" in the test's name true. Every field stays in the
        comparison, and the three git ones are asserted to be the values the
        fixture pins so the equality is not passing on empty strings.
        """
        checkout = self.committed_checkout()
        ctx = self.context_for(checkout)
        path = (
            self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        )
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        first = path.read_bytes()
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        self.assertEqual(first, path.read_bytes())

        recorded = json.loads(first)
        self.assertFalse(recorded["dirty"])
        self.assertTrue(recorded["commit"])
        self.assertTrue(recorded["branch"])

    def test_the_hook_row_takes_its_sorted_position(self):
        """It is appended after the renders, so sorting has to come after that.

        Asserted by position rather than by "it is not last", which would only
        hold for a home whose settings path happens not to sort last.
        """
        self.install()
        owned = self.receipt["owned"]
        hook = next(row for row in owned if row.get("kind") == "hook")
        self.assertEqual(
            owned.index(hook),
            sorted(row["path"] for row in owned).index(hook["path"]),
        )


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

    def test_a_git_that_will_not_finish_does_not_fail_the_install(self):
        """The bound added with the timeout has to have somewhere to land.

        `configured_excludes` already answers an unusable git with `None` and
        the caller returns; the write has the same standing, so a `git` that
        hangs past the bound leaves the convenience unwritten and nothing
        else. Without the guard this raises out of `install`.
        """
        calls = []

        def record(args, **kwargs):
            calls.append(args)
            if "--get" in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])

        with unittest.mock.patch("subprocess.run", side_effect=record):
            sd_install.set_excludes_config(self.home / "ignore")
        self.assertEqual(len(calls), 2, "the write was never attempted")
        self.assertIn("core.excludesFile", calls[1])

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
    # A real `HOOK_SPECS` command, carrying the checkout prefix a real run
    # gives it. `remove_hook` matches the receipt's held commands against the
    # table by suffix, so a made-up name matches no row, clears nothing, and
    # every removal test below would pass by removing nothing at all.
    RESTORE = "/x/bin/sd-handoff-restore"

    def spec(self, command=RESTORE, event="SessionStart",
             matchers=("startup", "clear")):
        """One row shaped like `hook_specs` output."""
        return [(command, event, matchers)]

    def settings_path(self) -> Path:
        path = self.home / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_a_non_object_settings_file_is_refused(self):
        path = self.settings_path()
        path.write_text("[]", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, self.spec())
        self.assertIn("not a JSON object", str(caught.exception))

    def test_a_non_object_hooks_key_is_refused(self):
        path = self.settings_path()
        path.write_text(json.dumps({"hooks": []}), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, self.spec())
        self.assertIn("non-object 'hooks'", str(caught.exception))

    def test_a_non_list_session_start_is_refused(self):
        path = self.settings_path()
        path.write_text(json.dumps({"hooks": {"SessionStart": {}}}), encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sd_install.install_hook(path, self.spec())
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
            sd_install.install_hook(path, self.spec())
        self.assertIn("non-list 'hooks'", str(caught.exception))

    def test_a_dry_run_registers_nothing(self):
        path = self.settings_path()
        self.assertTrue(sd_install.install_hook(path, self.spec(), dry_run=True))
        self.assertFalse(path.exists())

    def test_removing_from_a_file_that_never_had_the_hook_changes_nothing(self):
        path = self.settings_path()
        self.assertFalse(sd_install.remove_hook(path, [self.RESTORE]))
        path.write_text("{ broken", encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, [self.RESTORE]))
        path.write_text("[]", encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, [self.RESTORE]))
        path.write_text(json.dumps({"hooks": []}), encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, [self.RESTORE]))
        path.write_text(json.dumps({"hooks": {"SessionStart": {}}}), encoding="utf-8")
        self.assertFalse(sd_install.remove_hook(path, [self.RESTORE]))
        path.write_text(
            json.dumps({"hooks": {"SessionStart": [{"matcher": "startup"}]}}),
            encoding="utf-8",
        )
        self.assertFalse(sd_install.remove_hook(path, [self.RESTORE]))

    def test_groups_for_other_matchers_are_left_untouched(self):
        path = self.settings_path()
        other = {"matcher": "resume", "hooks": [{"command": self.RESTORE}]}
        path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            other,
                            {"matcher": "startup", "hooks": [{"command": self.RESTORE}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(sd_install.remove_hook(path, [self.RESTORE]))
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
                            {"matcher": "clear", "hooks": [{"command": self.RESTORE}]},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(sd_install.remove_hook(path, [self.RESTORE]))
        groups = json.loads(path.read_text(encoding="utf-8"))["hooks"]["SessionStart"]
        self.assertEqual(groups, [{"matcher": "startup", "hooks": []}])

    def test_a_dry_run_removal_writes_nothing(self):
        path = self.settings_path()
        original = json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"matcher": "clear", "hooks": [{"command": self.RESTORE}]}
                    ]
                }
            }
        )
        path.write_text(original, encoding="utf-8")
        self.assertTrue(
            sd_install.remove_hook(path, [self.RESTORE], dry_run=True)
        )
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
        # Named by a path and still not a surface: the path says install it,
        # the directory has no SKILL.md to install. `missing_skills` is what
        # reports that; the renderer simply has nothing to render.
        self.write_paths(self.home, "sd-empty")
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

    def test_metadata_refusal_reports_unknown_comparisons_without_cleanup_advice(self):
        checkout = self.committed_checkout()
        ctx = self.context_for(checkout)
        source = checkout / "skills" / "sd-probe" / "SKILL.md"
        original = b"---\nname: sd-probe\ndisable-model-invocation: true\n---\n\nBody.\n"
        source.write_bytes(original)
        with unittest.mock.patch.object(sd_install, "open_library", return_value=(None, "synthetic no database")):
            self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        current = self.home / ".config" / "opencode" / "commands" / "sd-probe.md"
        retired = self.home / ".gemini" / "commands" / "sd-retired.toml"
        retired.parent.mkdir(parents=True)
        retired.write_bytes(b"retired\n")
        sd_install.write_receipt(sd_install.legacy_receipt_path(self.home, ctx.environ), {"files": [
            {"family": "opencode-commands", "path": current.name, "digest": sd_install.digest(current.read_bytes())},
            {"family": "gemini-commands", "path": retired.name, "digest": sd_install.digest(retired.read_bytes())},
        ]})
        (self.home / ".claude" / "skills" / "sd-probe" / "SKILL.md").unlink()
        (self.home / ".codex" / "skills" / "sd-probe" / "SKILL.md").write_bytes(b"modified render\n")
        baseline = io.StringIO()
        self.assertEqual(sd_install.cmd_status(ctx, baseline), 0)
        self.assertIn("4 rendered files, 1 missing, 1 modified", baseline.getvalue())
        self.assertIn("legacy: 1 file(s)", baseline.getvalue())
        command_report = sd_install.command_report(checkout, ctx.environ)
        for bad in (original.replace(b"name:", b'"name":'), original.replace(b"true", b"invalid")):
            with self.subTest(source=bad):
                source.write_bytes(bad)
                before = {path: path.read_bytes() for path in self.home.rglob("*") if path.is_file()}
                output = io.StringIO()
                with unittest.mock.patch.object(sd_install, "legacy_targets", side_effect=AssertionError("classification needs expected paths")):
                    self.assertEqual(sd_install.cmd_status(ctx, output), 0)
                report = output.getvalue()
                self.assertIn("metadata cannot render", report)
                self.assertIn("1 in checkout; rendered comparison unavailable", report)
                self.assertIn("legacy: classification unavailable", report)
                self.assertIn(f"checkout: {checkout}", report)
                self.assertIn(command_report, report)
                self.assertNotIn("rendered files", report)
                self.assertNotIn("0 missing", report)
                self.assertNotIn("0 modified", report)
                self.assertNotIn("--adopt-legacy", report)
                self.assertNotIn("file(s) from the old fleet installer", report)
                self.assertEqual(sd_install.verify_rendered(ctx, self.receipt)[0]["code"], "source_payload_invalid")
                self.assertEqual(before, {path: path.read_bytes() for path in self.home.rglob("*") if path.is_file()})

    def _status_of(self, checkout: Path) -> str:
        ctx = self.context_for(checkout)
        installed = io.StringIO()
        self.assertEqual(sd_install.cmd_user(ctx, installed), 0)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_status(ctx, out), 0)
        return out.getvalue()

    def test_a_clean_serving_checkout_is_not_reported_dirty(self):
        self.assertNotIn("checkout is dirty", self._status_of(self.committed_checkout()))

    def test_a_dirty_serving_checkout_is_reported(self):
        checkout = self.committed_checkout()
        (checkout / "skills" / "sd-probe" / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-probe\n---\n\nedited\n", encoding="utf-8"
        )
        self.assertIn("checkout is dirty", self._status_of(checkout))

    def _bin_with(self, *names: str) -> Path:
        """A checkout whose `bin/` holds the named executables and nothing else."""
        checkout = self.home / "probe-checkout"
        (checkout / "bin").mkdir(parents=True, exist_ok=True)
        for name in names:
            target = checkout / "bin" / name
            target.write_text("#!/bin/sh\n", encoding="utf-8")
            target.chmod(0o755)
        return checkout

    def test_command_report_says_how_to_invoke_when_bin_is_not_on_path(self):
        checkout = self._bin_with("sd-handoff", "sd-review")
        report = sd_install.command_report(checkout, {"PATH": ""})
        self.assertIn("2 in bin/", report)
        self.assertIn("not on PATH", report)
        self.assertIn("bin/sd-handoff", report)

    def test_command_report_notices_bin_on_path(self):
        checkout = self._bin_with("sd-handoff")
        report = sd_install.command_report(
            checkout, {"PATH": str(checkout / "bin")}
        )
        self.assertIn("on PATH from this checkout", report)
        self.assertNotIn("not on PATH", report)

    def test_command_report_names_a_command_shadowed_by_another_install(self):
        checkout = self._bin_with("sd-handoff")
        other = self.home / "other" / "bin"
        other.mkdir(parents=True)
        stale = other / "sd-handoff"
        stale.write_text("#!/bin/sh\n", encoding="utf-8")
        stale.chmod(0o755)
        report = sd_install.command_report(checkout, {"PATH": str(other)})
        self.assertIn("not on PATH", report)
        self.assertIn("shadowed by another install", report)
        self.assertIn("sd-handoff", report)

    def test_command_report_does_not_call_a_symlink_home_a_shadow(self):
        """A link in another `bin` pointing back here is this checkout's command.

        `~/bin/common/sd-handoff -> <checkout>/bin/sd-handoff` is how a hand-made
        install reaches these commands. Resolving the directory rather than the
        executable reports that as a competing install, which it is not.
        """
        checkout = self._bin_with("sd-handoff")
        other = self.home / "common"
        other.mkdir(parents=True)
        (other / "sd-handoff").symlink_to(checkout / "bin" / "sd-handoff")
        report = sd_install.command_report(checkout, {"PATH": str(other)})
        self.assertNotIn("shadowed", report)

    def test_command_report_counts_the_dispatcher_and_not_the_modules(self):
        checkout = self._bin_with("sd", "sd-handoff")
        module = checkout / "bin" / "sd_lib.py"
        module.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
        module.chmod(0o755)
        report = sd_install.command_report(checkout, {"PATH": ""})
        self.assertIn("2 in bin/", report)
        self.assertIn("invoke by path (bin/sd)", report)

    def test_command_report_does_not_call_a_linked_command_its_own_shadow(self):
        """A command that is itself a link inside `bin/` resolves past its name."""
        checkout = self._bin_with("sd_handoff_impl.py")
        (checkout / "bin" / "sd-handoff").symlink_to("sd_handoff_impl.py")
        report = sd_install.command_report(
            checkout, {"PATH": str(checkout / "bin")}
        )
        self.assertIn("on PATH from this checkout", report)
        self.assertNotIn("shadowed", report)

    def test_command_report_counts_per_command_links(self):
        """Rule 2: the count is per command, so a linked set is seen as installed.

        `~/.local/bin/sd-* -> <checkout>/bin/sd-*` is what `--user` makes, and
        a directory test never saw it: no PATH entry resolves to `bin/`. Two
        links of three name the missing one; three are the whole set; a foreign
        file on PATH keeps its shadow warning.
        """
        checkout = self._bin_with("sd", "sd-handoff", "sd-review")
        common = self.home / "common"
        common.mkdir()
        environ = {"PATH": str(common)}
        for name in ("sd", "sd-handoff"):
            (common / name).symlink_to(checkout / "bin" / name)
        report = sd_install.command_report(checkout, environ)
        self.assertIn("3 in bin/, 2 of 3 resolve on PATH from this checkout", report)
        self.assertIn("(missing: sd-review)", report)
        self.assertNotIn("shadowed", report)

        (common / "sd-review").symlink_to(checkout / "bin" / "sd-review")
        report = sd_install.command_report(checkout, environ)
        self.assertIn("3 in bin/, 3 resolve on PATH from this checkout", report)
        self.assertNotIn("missing", report)

        (common / "sd-review").unlink()
        (common / "sd-handoff").unlink()
        foreign = common / "sd-review"
        foreign.write_text("#!/bin/sh\n", encoding="utf-8")
        foreign.chmod(0o755)
        report = sd_install.command_report(checkout, environ)
        self.assertIn("1 of 3 resolve on PATH from this checkout", report)
        self.assertIn("(missing: sd-handoff)", report)
        self.assertIn("[1 shadowed by another install: sd-review]", report)

    def test_command_report_on_a_checkout_with_no_commands(self):
        checkout = self.home / "empty-checkout"
        (checkout / "bin").mkdir(parents=True)
        self.assertEqual(
            sd_install.command_report(checkout, {"PATH": ""}),
            "commands: none in bin/",
        )

    def test_status_reports_the_calling_convention(self):
        self.install()
        _, output = self.run_cli("--status")
        self.assertIn("commands:", output)

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
        """Against a repository this test creates, never the ambient one.

        A duplicate of this test used to run against `REPO_ROOT` and skip when
        that checkout happened to be on `main`. On a branch it passed; merged
        to `main` it skipped, and CI fails any run that skips a test -- so the
        first red `main` of this rollout was caused by a test asking where it
        was running instead of building what it needed.
        """
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

    def test_a_pull_that_will_not_finish_is_reported_and_not_raised(self):
        """`PULL_TIMEOUT` bounds a fetch, so it can expire on a slow network.

        A fetch that never returns used to hang the command; it now ends as
        the failure it is, with the reason named, and the exit code is the
        one a failed pull already had.
        """
        repo = self.make_main_checkout()
        real = subprocess.run

        def fake(args, **kwargs):
            if "pull" in args:
                raise subprocess.TimeoutExpired(args, kwargs["timeout"])
            return real(args, **kwargs)

        out = io.StringIO()
        with unittest.mock.patch("subprocess.run", side_effect=fake):
            rc = sd_install.cmd_pull(self.context(repo), out)
        self.assertEqual(rc, 1)
        self.assertIn("could not finish", out.getvalue())

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

    def test_a_git_that_will_not_answer_stops_the_write(self):
        """The bound must not turn "cannot say" into "not tracked".

        `write_local_block` writes unless the check says tracked, so a
        timeout answered `False` would overwrite a tracked `CLAUDE.local.md`
        -- the one edit the check exists to prevent. A missing binary is the
        other case and stays `False`, which the test above holds.
        """
        repo = self.home / "checkout"
        repo.mkdir()
        expired = subprocess.TimeoutExpired(["git"], sd_install.GIT_TIMEOUT)
        with unittest.mock.patch("subprocess.run", side_effect=expired):
            with self.assertRaises(SystemExit) as caught:
                sd_install.write_local_block(repo)
        self.assertIn("could not say whether", str(caught.exception))
        self.assertFalse((repo / sd_install.LOCAL_BLOCK_FILE).exists())


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
                            {
                                "matcher": "clear",
                                "hooks": [
                                    {"command": "/x/bin/sd-handoff-restore"}
                                ],
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            sd_install.remove_hook(path, ["/x/bin/sd-handoff-restore"])
        )
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


class PathsTests(InstallerHarness):
    """Criterion 24: a path names what installs, and nothing else does.

    The two directions are separate tests on purpose. "On disk and on no
    path" is the drift a new skill directory creates; "named and not on
    disk" is the drift a deletion creates. A check that asked only one of
    them would pass while the other was true.
    """

    def context(self, checkout: Path) -> "sd_install.Context":
        return sd_install.Context(
            checkout=checkout,
            home=self.home,
            environ={
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                # No system checkout, so the library is absent and the trials
                # are unavailable. That is the machine most of these tests are
                # describing, and the installer still has to render the paths.
                sd_install.SYSTEM_CHECKOUT_ENV: str(self.home / "absent"),
            },
        )

    def make_checkout(self, *names: str) -> Path:
        checkout = self.home / "checkout"
        for name in names:
            folder = checkout / "skills" / name
            folder.mkdir(parents=True)
            (folder / sd_install.SKILL_FILE).write_text(
                f"---\nname: {name}\n---\n\nprobe surface\n", encoding="utf-8"
            )
        self.write_paths(checkout, *names)
        return checkout

    def test_the_real_checkout_has_three_paths_covering_every_directory(self):
        """The assertion criterion 24 makes about this repository, not a fixture."""
        self.assertEqual(len(sd_install.read_paths(REPO_ROOT)), 3)
        self.assertEqual(sd_install.unnamed_directories(REPO_ROOT), [])
        self.assertEqual(sd_install.missing_skills(REPO_ROOT), [])

    def test_an_unlisted_skill_directory_refuses_the_install(self):
        """Criterion 24's own test: add a directory no path names, see it fail."""
        checkout = self.make_checkout("sd-kept")
        stray = checkout / "skills" / "sd-stray"
        stray.mkdir()
        (stray / sd_install.SKILL_FILE).write_text("---\nname: sd-stray\n---\n", "utf-8")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 1)
        self.assertIn("sd-stray", out.getvalue())
        self.assertIn("on no path", out.getvalue())

    def test_a_path_naming_a_directory_that_is_gone_refuses_the_install(self):
        checkout = self.make_checkout("sd-kept")
        self.write_paths(checkout, "sd-kept", "sd-ghost")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 1)
        self.assertIn("sd-ghost", out.getvalue())

    def test_a_missing_paths_file_refuses_rather_than_falling_back_to_disk(self):
        checkout = self.make_checkout("sd-kept")
        sd_install.paths_path(checkout).unlink()
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 1)
        self.assertIn("requirement 10", out.getvalue())

    def test_a_file_that_is_not_json_is_refused_with_the_parser_error(self):
        """Truncated, half-merged, or edited by hand and left broken.

        The refusal names the file and quotes what the parser said, because
        "requirement 10 says a path names what installs" is the right message
        for an absent file and the wrong one for a file that is right there
        with a comma missing.
        """
        checkout = self.make_checkout("sd-kept")
        sd_install.paths_path(checkout).write_text('{"paths": {', encoding="utf-8")
        with self.assertRaises(sd_install.PathsRefused) as caught:
            sd_install.read_paths(checkout)
        self.assertIn("is not readable JSON", str(caught.exception))
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 1)

    def test_a_file_naming_two_paths_is_refused_naming_the_count(self):
        checkout = self.make_checkout("sd-kept")
        sd_install.paths_path(checkout).write_text(
            json.dumps({"paths": {"research": {"skills": []}, "act": {"skills": []}}}),
            encoding="utf-8",
        )
        with self.assertRaises(sd_install.PathsRefused) as caught:
            sd_install.read_paths(checkout)
        self.assertIn("names 2 paths", str(caught.exception))

    def test_contrib_is_not_rendered_without_a_trial_row(self):
        """Criterion 24's last clause, both halves in one test."""
        checkout = self.make_checkout("sd-kept")
        contrib = checkout / sd_install.CONTRIB_DIR / "sd-trialled"
        contrib.mkdir(parents=True)
        (contrib / sd_install.SKILL_FILE).write_text(
            "---\nname: sd-trialled\n---\n", encoding="utf-8"
        )
        without = [s.name for s in sd_install.discover_surfaces(checkout)]
        self.assertEqual(without, ["sd-kept"])
        withal = [s.name for s in sd_install.discover_surfaces(checkout, ["sd-trialled"])]
        self.assertEqual(withal, ["sd-kept", "sd-trialled"])

    def test_a_skill_in_both_places_renders_from_skills(self):
        """A stale trial row must not keep rendering a promoted skill's old copy."""
        checkout = self.make_checkout("sd-kept")
        contrib = checkout / sd_install.CONTRIB_DIR / "sd-kept"
        contrib.mkdir(parents=True)
        (contrib / sd_install.SKILL_FILE).write_text("stale copy\n", encoding="utf-8")
        surfaces = sd_install.discover_surfaces(checkout, ["sd-kept"])
        self.assertEqual(len(surfaces), 1)
        self.assertEqual(surfaces[0].skill.parent.parent.name, "skills")


class ProviderRegistrySeedTests(InstallerHarness):
    """The registry lands in the home once, and is the operator's after that.

    The two helpers are taken from `PathsTests` rather than inherited from it:
    subclassing would re-run that class's whole suite under a second name, and
    copying them would give this file two fixture checkouts that could drift
    apart. The registry is written into the checkout per test, because "the
    checkout has no registry" is one of the cases.
    """

    context = PathsTests.context
    make_checkout = PathsTests.make_checkout

    REGISTRY = (
        "bills:\n"
        "  free: { cost: local }\n"
        "providers:\n"
        '  one: { url: "http://localhost:1/v1", vendor: alpha, bill: free, roles: [author] }\n'
        '  two: { url: "http://localhost:2/v1", vendor: beta, bill: free, roles: [reviewer] }\n'
        "roles:\n"
        "  author: [one]\n"
        "  reviewer: [two]\n"
    )

    def with_registry(self, checkout: Path) -> Path:
        source = checkout / sd_install.REGISTRY_NAME
        source.write_text(self.REGISTRY, encoding="utf-8")
        return source

    @property
    def target(self) -> Path:
        return self.home / sd_install.REGISTRY_RELATIVE

    def test_the_constants_agree_with_the_reader_that_reads_the_file(self):
        """Restated in two files, so the restatement is asserted.

        `bin/sd_registry.py` reads this file and the installer places it. The
        installer may not import a sibling -- it runs before anything else in
        `bin/` is importable -- so the names are stated twice and pinned here.
        """
        spec = importlib.util.spec_from_file_location(
            "sd_registry_for_install_tests", REPO_ROOT / "bin" / "sd_registry.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(sd_install.REGISTRY_NAME, module.REGISTRY_NAME)
        self.assertEqual(sd_install.REGISTRY_RELATIVE, module.REGISTRY_RELATIVE)

    def test_it_is_copied_when_the_home_has_none(self):
        checkout = self.make_checkout("sd-kept")
        self.with_registry(checkout)
        seeded, report = sd_install.seed_registry(self.context(checkout))
        self.assertTrue(seeded)
        self.assertIn("seeded", report)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.REGISTRY)

    def test_a_registry_already_there_is_left_exactly_as_it_is(self):
        """A pin changed this morning survives a reinstall this afternoon."""
        checkout = self.make_checkout("sd-kept")
        self.with_registry(checkout)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("bills: {}\n", encoding="utf-8")
        seeded, report = sd_install.seed_registry(self.context(checkout))
        self.assertFalse(seeded)
        self.assertIn("left as it is", report)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "bills: {}\n")

    def test_a_checkout_with_no_registry_says_so_and_installs_anyway(self):
        checkout = self.make_checkout("sd-kept")
        seeded, report = sd_install.seed_registry(self.context(checkout))
        self.assertFalse(seeded)
        self.assertIn("no reviewer resolves", report)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 0)

    def test_a_dry_run_writes_nothing(self):
        checkout = self.make_checkout("sd-kept")
        self.with_registry(checkout)
        context = sd_install.Context(
            checkout=checkout,
            home=self.home,
            environ=self.context(checkout).environ,
            dry_run=True,
        )
        seeded, report = sd_install.seed_registry(context)
        self.assertTrue(seeded)
        self.assertIn("would seed", report)
        self.assertFalse(self.target.exists())

    def test_the_install_says_it_seeded_nothing_when_there_was_nothing(self):
        """Copilot found this. `seed_registry` promises its report "says which
        -- an install that quietly did nothing is the same output as one that
        quietly overwrote", and the caller printed it only when it had seeded.
        So the outcome that costs most -- no registry, so no reviewer resolves
        -- was the one that printed nothing at all."""
        checkout = self.make_checkout("sd-kept")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 0)
        self.assertIn("no reviewer resolves", out.getvalue())

    def test_the_install_says_it_left_an_existing_registry_alone(self):
        checkout = self.make_checkout("sd-kept")
        self.with_registry(checkout)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text("bills: {}\n", encoding="utf-8")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 0)
        self.assertIn("left as it is", out.getvalue())

    def test_the_install_reports_the_seed_and_the_file_is_readable(self):
        checkout = self.make_checkout("sd-kept")
        self.with_registry(checkout)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context(checkout), out), 0)
        self.assertIn("provider registry seeded", out.getvalue())
        self.assertTrue(self.target.is_file())

    def test_it_is_not_recorded_as_a_file_the_installer_owns(self):
        """Owned files are removed on uninstall. This one is the operator's."""
        checkout = self.make_checkout("sd-kept")
        self.with_registry(checkout)
        out = io.StringIO()
        sd_install.cmd_user(self.context(checkout), out)
        owned = {row["path"] for row in self.receipt["owned"]}
        self.assertNotIn(str(self.target), owned)


class StandingPolicyInstallerTests(InstallerHarness):
    make_repo = ConsentPromptTests.make_repo
    consent_line = ConsentPromptTests.consent_line
    def test_explicit_empty_is_a_durable_denial_even_without_registry(self):
        repo = self.make_repo()
        code, output = self.run_cli("--repo", str(repo), "--reviewers", "")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.consent_line(repo), "")
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 0, output)
        self.assertIn("already answered", output)
        self.assertEqual(self.consent_line(repo), "")

    def test_interactive_empty_answer_is_preserved_as_local_denial(self):
        ConsentPromptTests.seed_registry(self)
        repo = self.make_repo()
        stdin = unittest.mock.Mock()
        stdin.isatty.return_value = True
        stdin.readline.return_value = "\n"
        with unittest.mock.patch.object(sys, "stdin", stdin):
            code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.consent_line(repo), "")

    def test_machine_authorization_is_inherited_without_copying_a_recipient_list(self):
        path = self.home / ".config/sd-ai-command-pack/config.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        repo = self.make_repo()
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 0, output)
        self.assertIn("inherits", output)
        self.assertNotIn("which of these", output)
        self.assertIsNone(self.consent_line(repo))
        self.assertEqual(json.loads(path.read_text())["config"]["sd"]["external_reviews"], "configured")

    def test_dangling_local_link_cannot_be_repaired_into_inherited_authorization(self):
        policy = self.home / ".config/sd-ai-command-pack/config.json"
        policy.parent.mkdir(parents=True)
        policy.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        repo = self.make_repo()
        target = repo / "missing-config"
        local = repo / sd_install.LOCAL_BLOCK_FILE
        local.symlink_to(target)
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 2, output)
        self.assertTrue(local.is_symlink())
        self.assertFalse(target.exists())

    def test_linked_repo_installer_writes_and_protects_the_canonical_main_config(self):
        repo = self.make_repo()
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-qm", "seed"], check=True)
        linked = self.home / "linked"
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "--detach", str(linked), "HEAD"], check=True, capture_output=True)
        code, output = self.run_cli("--repo", str(linked), "--reviewers", "")
        self.assertEqual(code, 0, output)
        self.assertEqual(self.consent_line(repo), "")
        self.assertFalse((linked / sd_install.LOCAL_BLOCK_FILE).exists())
        self.assertIn(str(repo / sd_install.LOCAL_BLOCK_FILE), output)
        local = repo / sd_install.LOCAL_BLOCK_FILE
        before = local.read_bytes()
        subprocess.run(["git", "-C", str(repo), "add", "-f", sd_install.LOCAL_BLOCK_FILE], check=True)
        with self.assertRaisesRegex(SystemExit, "tracked"):
            self.run_cli("--repo", str(linked), "--reviewers", "")
        self.assertEqual(local.read_bytes(), before)

    def test_only_exact_shipped_placeholder_can_inherit_machine_authorization(self):
        policy = self.home / ".config/sd-ai-command-pack/config.json"
        policy.parent.mkdir(parents=True)
        policy.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        repo = self.make_repo()
        local = repo / sd_install.LOCAL_BLOCK_FILE
        before = f'{sd_install.BLOCK_BEGIN}\nreviewers: <broken\n{sd_install.BLOCK_END}\n'
        local.write_text(before)
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 2, output)
        self.assertEqual(local.read_text(), before)
        local.write_text(f'{sd_install.BLOCK_BEGIN}\n{sd_install.DEFAULT_BLOCK_BODY}{sd_install.BLOCK_END}\n')
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 0, output)
        self.assertIn("inherits", output)
        self.assertIsNone(self.consent_line(repo))

    def test_malformed_local_block_cannot_be_rewritten_into_inherited_authorization(self):
        policy = self.home / ".config/sd-ai-command-pack/config.json"
        policy.parent.mkdir(parents=True)
        policy.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        repo = self.make_repo()
        local = repo / sd_install.LOCAL_BLOCK_FILE
        before = f'{sd_install.BLOCK_BEGIN}\nreviewers: "unterminated\n{sd_install.BLOCK_END}\n'
        local.write_text(before)
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 2, output)
        self.assertIn("error:", output)
        self.assertEqual(local.read_text(), before)

    def test_unknown_explicit_answer_cannot_fall_through_to_machine_authorization(self):
        ConsentPromptTests.seed_registry(self)
        policy = self.home / ".config/sd-ai-command-pack/config.json"
        policy.parent.mkdir(parents=True)
        policy.write_text('{"config":{"sd":{"external_reviews":"configured"}}}')
        repo = self.make_repo()
        code, output = self.run_cli("--repo", str(repo), "--reviewers", "plain nosuch")
        self.assertEqual(code, 2, output)
        self.assertFalse((repo / sd_install.LOCAL_BLOCK_FILE).exists())

    def test_malformed_local_syntax_and_unreadable_file_refuse_without_overwrite(self):
        repo = self.make_repo()
        local = repo / sd_install.LOCAL_BLOCK_FILE
        before = f'{sd_install.BLOCK_BEGIN}\nreviewers ""\n{sd_install.BLOCK_END}\n'
        local.write_text(before)
        code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 2, output)
        self.assertEqual(local.read_text(), before)
        with unittest.mock.patch.object(Path, "read_text", side_effect=PermissionError("read denied")):
            code, output = self.run_cli("--repo", str(repo))
        self.assertEqual(code, 2, output)
        self.assertEqual(local.read_text(), before)

    def test_explicit_unknown_with_no_registry_refuses_without_write(self):
        repo = self.make_repo()
        code, output = self.run_cli("--repo", str(repo), "--reviewers", "unknown")
        self.assertEqual(code, 2, output)
        self.assertFalse((repo / sd_install.LOCAL_BLOCK_FILE).exists())


class LinkTests(InstallerHarness):
    """`--user` links the `bin/` commands onto PATH, and the receipt names them.

    Three commands stand in for the seventeen: the count is enumerated from
    `bin/` at run time, so a fixture of three exercises every branch the real
    checkout would.
    """

    def test_user_links_the_commands_and_the_receipt_names_them(self):
        """Rule 1: every command is linked, and a link already pointing here is kept.

        One hand-made link is absolute and one is relative, because the hand
        loop that preceded this made absolute ones and a relative one is what
        `ln -s` from inside the directory makes; both point here, so both are
        ours and keep their inodes rather than being rewritten.
        """
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        absolute = bin_dir / "sd"
        absolute.symlink_to(checkout / "bin" / "sd")
        relative = bin_dir / "sd-handoff"
        relative.symlink_to(
            os.path.relpath(checkout / "bin" / "sd-handoff", bin_dir)
        )
        inodes = {absolute.lstat().st_ino, relative.lstat().st_ino}

        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(self.context_for(checkout), out), 0)

        for name in ("sd", "sd-handoff", "sd-review"):
            link = bin_dir / name
            self.assertTrue(link.is_symlink(), f"{link} is not a symlink")
            self.assertEqual(link.resolve(), (checkout / "bin" / name).resolve())
        self.assertEqual(
            {absolute.lstat().st_ino, relative.lstat().st_ino}, inodes,
            "a link that already pointed here was rewritten",
        )
        links = [row for row in self.receipt["owned"] if row.get("kind") == "link"]
        self.assertEqual(
            links,
            [
                {
                    "path": str(bin_dir / name),
                    "kind": "link",
                    "target": str(checkout / "bin" / name),
                }
                for name in ("sd", "sd-handoff", "sd-review")
            ],
        )
        self.assertIn(f"linked 3 commands into {bin_dir}", out.getvalue())
        # C-35, both ways: this shell's PATH lacks the scratch directory; a
        # PATH that holds it gets no warning.
        self.assertIn(f"warning: {bin_dir} is not on PATH in this shell", out.getvalue())
        again = io.StringIO()
        on_path = sd_install.Context(
            checkout=checkout,
            home=self.home,
            environ={**os.environ, "PATH": f"/usr/bin{os.pathsep}{bin_dir}"},
        )
        self.assertEqual(sd_install.cmd_user(on_path, again), 0)
        self.assertNotIn("not on PATH", again.getvalue())

    def test_user_refuses_a_foreign_file_at_a_target(self):
        """Rule 1: a foreign entry at one target refuses the run before it writes.

        Four foreign shapes, each in its own scratch home: a regular file, a
        dangling link, a link into a second checkout's copy, and a directory. The pre-flight
        runs before the library is opened, and the expired trial in the
        library is the witness: `expire_trials` would have ended it.
        """
        sd_db = sd_install.sibling("sd_lib").import_sd_db().module
        self.assertIsNotNone(sd_db, "the pack's virtualenv carries sd_db")

        def regular_file(path: Path, checkout: Path) -> None:
            path.write_text("#!/bin/sh\n", encoding="utf-8")

        def dangling_link(path: Path, checkout: Path) -> None:
            path.symlink_to(self.home / "gone" / "sd-handoff")

        def other_checkout(path: Path, checkout: Path) -> None:
            other = self.home / "other" / "bin"
            other.mkdir(parents=True)
            (other / "sd-handoff").write_text("#!/bin/sh\n", encoding="utf-8")
            path.symlink_to(other / "sd-handoff")

        def directory(path: Path, checkout: Path) -> None:
            # C-28: `os.symlink` over a directory raises after the renders.
            path.mkdir()

        for shape in (regular_file, dangling_link, other_checkout, directory):
            with self.subTest(shape=shape.__name__):
                self.setUp()
                checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
                sd_db.initialise(home=self.home)
                connection = sd_db.connect(sd_db.default_path(self.home))
                self.addCleanup(connection.close)
                sd_db.start_trial(connection, "sd-probe", "2001-01-01T00:00:00Z")
                foreign = self.home / ".local" / "bin" / "sd-handoff"
                foreign.parent.mkdir(parents=True)
                shape(foreign, checkout)
                before = foreign.lstat()

                out = io.StringIO()
                rc = sd_install.cmd_user(self.context_for(checkout), out)

                self.assertEqual(rc, 1)
                self.assertIn(str(foreign), out.getvalue())
                self.assertIn("not a link to", out.getvalue())
                for home in sd_install.platform_homes(self.home, dict(os.environ)):
                    self.assertEqual(
                        sorted(home.root.glob("sd-*")) if home.root.is_dir() else [],
                        [], f"{home.key} holds a render after a refusal",
                    )
                self.assertFalse(
                    (self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json").exists(),
                    "a receipt was written after a refusal",
                )
                self.assertFalse((self.home / ".local" / "bin" / "sd").exists())
                after = foreign.lstat()
                self.assertEqual((before.st_ino, before.st_mode), (after.st_ino, after.st_mode))
                self.assertEqual(
                    [row["skill"] for row in sd_db.trials(connection)], ["sd-probe"],
                    "the expired trial was ended before the refusal",
                )

    def test_uninstall_removes_the_links_and_nothing_else(self):
        """Rule 1: `--uninstall` removes the links the receipt names, if still ours.

        A link the receipt does not name is never a candidate; a recorded link
        that now points elsewhere, or a regular file at a recorded path, is
        left and reported, the way a hand-edited render is.
        """
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        ctx = self.context_for(checkout)
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        # C-34: the relative link is the one that gets removed, so a link kept
        # at install is recognised at uninstall.
        relative = bin_dir / "sd-handoff"
        relative.symlink_to(os.path.relpath(checkout / "bin" / "sd-handoff", bin_dir))
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        scratch = self.home / "scratch"
        scratch.write_text("#!/bin/sh\n", encoding="utf-8")
        unrecorded = bin_dir / "sd-other"
        unrecorded.symlink_to(scratch)
        retargeted = bin_dir / "sd"
        retargeted.unlink()
        retargeted.symlink_to(scratch)
        regular = bin_dir / "sd-review"
        regular.unlink()
        regular.write_text("#!/bin/sh\n", encoding="utf-8")
        # C-33: a link row without a target is reported, not an abort.
        receipt_path = self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["owned"].append({"path": str(bin_dir / "sd-ghost"), "kind": "link"})
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        out = io.StringIO()
        self.assertEqual(sd_install.cmd_uninstall(ctx, out), 0)

        self.assertFalse(relative.is_symlink(), "our relative link was left")
        self.assertTrue(retargeted.is_symlink() and retargeted.resolve() == scratch)
        self.assertTrue(regular.is_file() and not regular.is_symlink())
        self.assertTrue(unrecorded.is_symlink(), "an unrecorded link was removed")
        self.assertTrue(bin_dir.is_dir(), "the link directory was removed")
        self.assertIn(f"left in place (not our link): {retargeted}", out.getvalue())
        self.assertIn(f"left in place (not our link): {regular}", out.getvalue())
        self.assertIn(f"left in place (malformed link row): {bin_dir / 'sd-ghost'}", out.getvalue())
        # Three renders (one skill, three platforms) and one link.
        self.assertIn("removed 4 file(s)", out.getvalue())

    def test_the_link_rule_is_stated_where_the_no_link_rule_was(self):
        """Rule 3: the three documents that said "links no executable" say the new rule.

        Whitespace is folded before the search because `AGENTS.md` wraps the
        phrase across a line, and a test that read it as absent for that
        reason would pass on the very text it exists to retire.
        """
        documents = {
            "README.md": (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
            "AGENTS.md": (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
            "command_report docstring": sd_install.command_report.__doc__,
        }
        for name, text in documents.items():
            folded = " ".join(text.split())
            with self.subTest(document=name):
                self.assertFalse(
                    "links no executable" in folded, f"{name} still says it links no executable"
                )
                self.assertTrue("~/.local/bin" in folded, f"{name} does not name the link directory")


class LinkEdgeCaseTests(InstallerHarness):
    """Rule 4: every branch the link step adds has a test, for the 100% gate."""

    def test_a_sandboxed_bin_dir_outside_the_home_is_refused_before_any_mode_runs(self):
        """`--pull` fast-forwards before it links, so the check is in `main`.

        `subprocess.run` is patched to fail the test if a pull is attempted,
        and the serving checkout's commit is read before and after, so a
        refusal that came one step too late would show twice.
        """
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(outside.rmdir)
        before = sd_install.git_context(REPO_ROOT)["commit"]
        real = subprocess.run

        def guard(args, **kwargs):
            self.assertNotIn("pull", args, "the checkout was pulled before the refusal")
            return real(args, **kwargs)

        for mode in ("--user", "--pull"):
            with self.subTest(mode=mode):
                with unittest.mock.patch("subprocess.run", side_effect=guard):
                    rc, output = self.run_cli(mode, "--bin-dir", str(outside))
                self.assertEqual(rc, 2)
                self.assertIn(f"--bin-dir {outside} is outside --home {self.home}", output)
                self.assertEqual(sorted(outside.iterdir()), [])
                self.assertFalse(
                    (self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json").exists()
                )
        self.assertEqual(sd_install.git_context(REPO_ROOT)["commit"], before)

    def test_a_bin_dir_under_a_symlinked_parent_that_resolves_outside_is_refused(self):
        """Containment is on the resolved path: `<home>/alias/bin` can write outside."""
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(outside.rmdir)
        (self.home / "alias").symlink_to(outside)
        rc, output = self.run_cli("--user", "--bin-dir", str(self.home / "alias" / "bin"))
        self.assertEqual(rc, 2)
        self.assertIn("is outside --home", output)
        self.assertEqual(sorted(outside.iterdir()), [])

    def test_a_bin_dir_inside_the_home_takes_the_links(self):
        """`--bin-dir ~/bin/common` is what a machine whose PATH lacks `~/.local/bin` passes."""
        common = self.home / "bin" / "common"
        rc, output = self.run_cli("--user", "--bin-dir", str(common))
        self.assertEqual(rc, 0)
        names = sd_install.bin_commands(REPO_ROOT)
        self.assertIn(f"linked {len(names)} commands into {common}", output)
        self.assertIn(f"warning: {common} is not on PATH in this shell", output)
        for name in names:
            self.assertEqual((common / name).resolve(), (REPO_ROOT / "bin" / name).resolve())
        self.assertFalse((self.home / ".local" / "bin").exists())
        links = [row for row in self.receipt["owned"] if row.get("kind") == "link"]
        self.assertEqual({Path(row["path"]).parent for row in links}, {common})

    def test_bin_dir_without_a_directory_is_an_error(self):
        """Through `main` directly: `run_cli` would append `--home`, and that
        would be read as the directory."""
        out = io.StringIO()
        self.assertEqual(sd_install.main(["--user", "--bin-dir"], out=out), 2)
        self.assertIn("--bin-dir needs a directory", out.getvalue())

    def test_a_flagless_run_reuses_the_recorded_bin_dir_and_a_new_flag_relocates(self):
        """C-30: the receipt carries `binDir`; without the flag the next run links there."""
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        first = self.home / "first"
        second = self.home / "second"
        ctx = sd_install.Context(
            checkout=checkout, home=self.home, environ=dict(os.environ), bin_dir=first
        )
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        self.assertEqual(self.receipt["binDir"], str(first))

        plain = self.context_for(checkout)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(plain, out), 0)
        self.assertIn(f"linked 3 commands into {first} (3 already linked)", out.getvalue())
        self.assertFalse((self.home / ".local" / "bin").exists())
        self.assertEqual(self.receipt["binDir"], str(first))

        moved = sd_install.Context(
            checkout=checkout, home=self.home, environ=dict(os.environ), bin_dir=second
        )
        self.assertEqual(sd_install.cmd_user(moved, io.StringIO()), 0)
        self.assertEqual(sorted(first.iterdir()), [])
        self.assertEqual(
            sorted(entry.name for entry in second.iterdir()), ["sd", "sd-handoff", "sd-review"]
        )
        links = [row["path"] for row in self.receipt["owned"] if row.get("kind") == "link"]
        self.assertEqual({Path(path).parent for path in links}, {second})
        self.assertEqual(self.receipt["binDir"], str(second))

    def test_an_unwritable_link_directory_is_the_same_error_as_a_failed_link(self):
        """C-31: the `mkdir -p` sits inside the `OSError` handling."""
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        bin_dir = self.home / ".local" / "bin"
        real = Path.mkdir

        def refuse(self, *args, **kwargs):
            if self == bin_dir:
                raise OSError(13, "Permission denied")
            return real(self, *args, **kwargs)

        out = io.StringIO()
        with unittest.mock.patch.object(Path, "mkdir", refuse):
            rc = sd_install.cmd_user(self.context_for(checkout), out)
        self.assertEqual(rc, 1)
        self.assertIn(f"error: could not link {bin_dir / 'sd'} (Permission denied)", out.getvalue())
        self.assertFalse(bin_dir.exists())
        self.assertFalse(
            (self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json").exists()
        )

    def test_a_dry_run_would_link_and_writes_no_link(self):
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        ctx = self.context_for(checkout)
        ctx.dry_run = True
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(ctx, out), 0)
        self.assertIn(f"would link 3 commands into {self.home / '.local' / 'bin'}", out.getvalue())
        self.assertFalse((self.home / ".local" / "bin").exists())

    def test_a_second_user_run_keeps_the_links_and_says_so(self):
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        ctx = self.context_for(checkout)
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(ctx, out), 0)
        self.assertIn("linked 3 commands into", out.getvalue())
        self.assertIn("(3 already linked)", out.getvalue())

    def test_a_retired_command_loses_its_link_on_the_next_user(self):
        """What `--pull` does to links: it re-runs this, so a gone command's link goes."""
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        ctx = self.context_for(checkout)
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        (checkout / "bin" / "sd-review").unlink()
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        bin_dir = self.home / ".local" / "bin"
        self.assertFalse((bin_dir / "sd-review").is_symlink())
        self.assertTrue((bin_dir / "sd-handoff").is_symlink())
        links = [row["path"] for row in self.receipt["owned"] if row.get("kind") == "link"]
        self.assertEqual(links, [str(bin_dir / "sd"), str(bin_dir / "sd-handoff")])

    def test_a_recorded_link_already_gone_is_not_an_error(self):
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        ctx = self.context_for(checkout)
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        (self.home / ".local" / "bin" / "sd-review").unlink()
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_uninstall(ctx, out), 0)
        self.assertNotIn("left in place", out.getvalue())

    def test_a_partial_link_failure_rolls_back_and_writes_no_receipt(self):
        checkout = self.checkout_with_commands("sd", "sd-handoff", "sd-review")
        (checkout / "skills" / "sd-probe" / "SKILL.md").write_text("---\nname: sd-probe\ndisable-model-invocation: true\n---\n")
        real = os.symlink
        calls = []

        def second_fails(target, path, *args, **kwargs):
            calls.append(path)
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            return real(target, path, *args, **kwargs)

        out = io.StringIO()
        with unittest.mock.patch("os.symlink", side_effect=second_fails):
            rc = sd_install.cmd_user(self.context_for(checkout), out)
        self.assertEqual(rc, 1)
        bin_dir = self.home / ".local" / "bin"
        self.assertIn(f"error: could not link {bin_dir / 'sd-handoff'} (No space left on device)", out.getvalue())
        self.assertFalse((bin_dir / "sd").is_symlink(), "the first link was not rolled back")
        self.assertEqual(sorted(bin_dir.iterdir()), [])
        self.assertFalse(
            (self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json").exists()
        )
        # C-29: the next clean run records every render and every link.
        self.assertEqual(sd_install.cmd_user(self.context_for(checkout), io.StringIO()), 0)
        owned = self.receipt["owned"]
        self.assertEqual(
            sorted(row["path"] for row in owned if row.get("kind") == "link"),
            [str(bin_dir / name) for name in ("sd", "sd-handoff", "sd-review")],
        )
        for home in sd_install.platform_homes(self.home, dict(os.environ)):
            self.assertIn(str(home.target_for("sd-probe")), {row["path"] for row in owned})

    def test_prune_links_reports_a_malformed_row(self):
        """C-33: a link row whose path or target is not a string is reported, never removed."""
        skipped = sd_install.prune_links(
            [
                {"path": 7, "kind": "link", "target": "x"},
                {"path": "/y", "kind": "link", "target": 3},
                {"kind": "link", "target": "/z"},
                {"path": "/x", "kind": "hook"},
            ],
            set(),
        )
        self.assertEqual(
            skipped,
            [
                ("7", "malformed link row"),
                ("/y", "malformed link row"),
                ('{"kind": "link", "target": "/z"}', "malformed link row"),
            ],
        )

    def test_command_report_ignores_a_command_in_the_working_directory(self):
        """`PATH=":"` is two empty components and `PATH="."` a relative one;
        `which` reads both as the working directory (C-19, C-32)."""
        checkout = self.checkout_with_commands("sd-handoff")
        cwd = self.home / "cwd"
        cwd.mkdir()
        stray = cwd / "sd-handoff"
        stray.write_text("#!/bin/sh\n", encoding="utf-8")
        stray.chmod(0o755)
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(cwd)
        for path in (os.pathsep, ".", f".{os.pathsep}{os.pathsep}", f"{os.pathsep}."):
            with self.subTest(PATH=path):
                report = sd_install.command_report(checkout, {"PATH": path})
                self.assertIn("not on PATH", report)
                self.assertNotIn("shadowed", report)

    def test_a_receipt_bin_dir_outside_the_home_is_refused_like_the_flag(self):
        """A flagless run links where the receipt's `binDir` says (C-30), and
        `main` checks only the flag: a receipt naming a directory outside
        `--home` was written to. Review finding 2: the receipt value gets the
        flag's containment test, refused by name with rc 2 before a render
        or a pull, and the receipt is left as it was.
        """
        outside = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(outside.rmdir)
        receipt_path = self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(
            json.dumps({"schema": 1, "binDir": str(outside), "owned": []}), encoding="utf-8"
        )
        recorded = receipt_path.read_bytes()
        before = sd_install.git_context(REPO_ROOT)["commit"]
        real = subprocess.run

        def guard(args, **kwargs):
            self.assertNotIn("pull", args, "the checkout was pulled before the refusal")
            return real(args, **kwargs)

        for mode in ("--user", "--pull"):
            with self.subTest(mode=mode):
                with unittest.mock.patch("subprocess.run", side_effect=guard):
                    rc, output = self.run_cli(mode)
                self.assertEqual(rc, 2, output)
                self.assertIn(
                    f"the receipt's binDir {outside} is outside --home {self.home}", output
                )
                self.assertIn("pass --bin-dir", output)
                self.assertEqual(sorted(outside.iterdir()), [])
                self.assertEqual(receipt_path.read_bytes(), recorded)
                self.assertEqual([entry.name for entry in self.home.iterdir()], [".local"])
                self.assertEqual([entry.name for entry in (self.home / ".local").iterdir()], ["state"])
        self.assertEqual(sd_install.git_context(REPO_ROOT)["commit"], before)
        # The flag still wins over the receipt, and inside the home it links.
        rc, output = self.run_cli("--user", "--bin-dir", str(self.home / "bin"))
        self.assertEqual(rc, 0, output)
        self.assertEqual(self.receipt["binDir"], str(self.home / "bin"))

    def test_a_link_row_without_a_path_is_reported_and_left(self):
        """Review finding 4: a `kind: link` row with no `path` is a malformed
        row, reported under `--uninstall` like one whose path is not a string
        (C-33), not dropped on the floor by `owned_entries`.
        """
        checkout = self.checkout_with_commands("sd", "sd-handoff")
        ctx = self.context_for(checkout)
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        receipt_path = self.home / ".local" / "state" / "sd-ai-command-pack" / "installed.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        row = {"kind": "link", "target": str(checkout / "bin" / "sd")}
        receipt["owned"].append(row)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        out = io.StringIO()
        self.assertEqual(sd_install.cmd_uninstall(ctx, out), 0)
        self.assertIn(
            f"left in place (malformed link row): {json.dumps(row, sort_keys=True)}",
            out.getvalue(),
        )
        # Three renders and the two links; the malformed row is not counted.
        self.assertIn("removed 5 file(s)", out.getvalue())
        self.assertTrue((checkout / "bin" / "sd").is_file())
        self.assertFalse((self.home / ".local" / "bin" / "sd").is_symlink())

    def test_a_symlink_loop_at_a_target_is_foreign_and_a_recorded_one_is_left(self):
        """Review finding 3, measured rather than guarded: on the interpreter
        the pack requires (`requires-python = ">=3.13"`), `Path.exists` on
        `a -> a` is False and non-strict `Path.resolve` returns the loop
        itself, so `_resolves_to` is False without an exception. `link_plan`
        calls the loop foreign and `prune_links` leaves it; neither is a
        traceback. This test pins that so an interpreter change surfaces here.
        """
        checkout = self.checkout_with_commands("sd", "sd-loop")
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        loop = bin_dir / "sd-loop"
        loop.symlink_to("sd-loop")
        ctx = self.context_for(checkout)

        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(ctx, out), 1)
        self.assertIn(f"error: {loop} exists and is not a link to", out.getvalue())
        self.assertFalse((bin_dir / "sd").is_symlink(), "a link was made before the refusal")

        loop.unlink()
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        loop.unlink()
        loop.symlink_to("sd-loop")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_uninstall(ctx, out), 0)
        self.assertTrue(loop.is_symlink(), "the loop was removed")
        self.assertIn(f"left in place (not our link): {loop}", out.getvalue())
        self.assertFalse((bin_dir / "sd").is_symlink(), "our link was left")


class CodexMetadataTests(InstallerHarness):
    def make_surface(self, marker="true", companion=None, newline="\n"):
        root = self.home / "checkout" / "skills" / "sd-probe"
        root.mkdir(parents=True, exist_ok=True)
        source = root / "SKILL.md"
        front = "---\nname: sd-probe\ndescription: Test the metadata adapter.\n"
        if marker is not None:
            front += f"disable-model-invocation: {marker}\n"
        source.write_bytes((front + "metadata:\n  note: untouched\n---\n\nBody ä.\n").replace("\n", newline).encode())
        extras = []
        if companion is not None:
            path = root / "agents" / "openai.yaml"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(companion)
            extras.append(sd_install.Extra("agents/openai.yaml", path))
        self.write_paths(self.home / "checkout", "sd-probe")
        return sd_install.Surface("sd-probe", source, extras)

    def test_all_real_commands_and_trials_preserve_policy_and_other_bytes(self):
        import yaml

        trials = [path.parent.name for path in (REPO_ROOT / "contrib").glob("*/SKILL.md")]
        surfaces = sd_install.discover_surfaces(REPO_ROOT, trials)
        sd_install.render(surfaces, sd_install.platform_homes(self.home, {}))
        commands = []
        for surface in surfaces:
            original = surface.skill.read_bytes()
            target = self.home / ".codex" / "skills" / surface.name
            actual = (target / "SKILL.md").read_bytes()
            metadata = yaml.safe_load(original.split(b"---", 2)[1])
            marker = metadata.get("disable-model-invocation")
            if marker is not None:
                commands.append(surface.name)
                policy = yaml.safe_load((target / "agents" / "openai.yaml").read_text())
                self.assertIs(policy["policy"]["allow_implicit_invocation"], not marker)
                self.assertEqual(actual, original.replace(f"disable-model-invocation: {str(marker).lower()}\n".encode(), b""))
            else:
                self.assertEqual(actual, original)
            self.assertEqual((self.home / ".claude" / "skills" / surface.name / "SKILL.md").read_bytes(), original)
        self.assertTrue(commands)
        self.assertTrue(any(name in trials for name in commands))

    def test_false_crlf_and_compatible_existing_metadata(self):
        metadata = b'interface:\n  display_name: "Probe"\ndependencies:\n  tools:\n    - type: "mcp"\n'
        surface = self.make_surface("false", metadata, "\r\n")
        body, extras, adapted = sd_install.codex_payload(surface)
        self.assertTrue(adapted)
        self.assertEqual(body, surface.skill.read_bytes().replace(b"disable-model-invocation: false\r\n", b""))
        self.assertTrue(extras["agents/openai.yaml"].startswith(metadata))
        self.assertIn(b"allow_implicit_invocation: true", extras["agents/openai.yaml"])
        same = b"policy:\n  allow_implicit_invocation: true\ninterface:\n  display_name: Probe\n"
        self.assertEqual(sd_install.codex_policy(same, True), same)
        inserted = b"policy: # preserved\n  products:\n    - CODEX\ninterface:\n  display_name: Probe\n"
        actual = sd_install.codex_policy(inserted, False)
        self.assertEqual(actual.replace(b"  allow_implicit_invocation: false\n", b""), inserted)
        self.assertEqual(sd_install.codex_policy(b"interface:\n  display_name: Probe", True), b"interface:\n  display_name: Probe\npolicy:\n  allow_implicit_invocation: true\n")
        self.assertEqual(sd_install.codex_policy(b"policy:", True), b"policy:\n  allow_implicit_invocation: true\n")

    def test_absent_marker_and_agents_are_unchanged(self):
        surface = self.make_surface(None, b"policy:\n  allow_implicit_invocation: false\n")
        self.assertFalse(sd_install.codex_payload(surface)[2])
        self.assertEqual(sd_install.codex_policy(b"interface:\n  display_name: Probe\n", None), b"interface:\n  display_name: Probe\n")
        self.assertEqual(sd_install.codex_policy(b"policy:\n  products:\n    - CODEX\n", None), b"policy:\n  products:\n    - CODEX\n")
        surface.skill.write_bytes(b"No frontmatter.\n")
        self.assertEqual(sd_install.codex_payload(surface)[0], b"No frontmatter.\n")
        surface = self.make_surface("nonsense")
        homes = [sd_install.PlatformHome("codex", self.home / "agent", "flat")]
        sd_install.render([surface], homes, kind="agent")
        self.assertEqual(homes[0].target_for(surface.name).read_bytes(), surface.skill.read_bytes())

    def test_malformed_fields_refuse_before_any_render(self):
        surface = self.make_surface()
        cases = [
            b"---\nname: x\ndisable-model-invocation: true\n",
            b"---\nname: x\ndisable-model-invocation: 'true'\n---\n",
            b"---\nname: x\ndisable-model-invocation: true\ndisable-model-invocation: false\n---\n",
            b"---\n'disable-model-invocation': true\n---\n",
            b"---\nname: \xff\n---\n",
            b"---\n\tdisable-model-invocation: true\n---\n",
        ]
        homes = sd_install.platform_homes(self.home, {})
        for data in cases:
            with self.subTest(data=data):
                surface.skill.write_bytes(data)
                with self.assertRaises(sd_install.MetadataRefused):
                    sd_install.render([surface], homes)
                self.assertFalse(homes[0].root.exists())

    def test_invocation_scalar_continuations_refuse_before_render(self):
        import yaml

        surface = self.make_surface("true\n  continued scalar")
        original = surface.skill.read_bytes()
        parsed = yaml.safe_load(original.split(b"---", 2)[1])
        self.assertEqual(parsed["disable-model-invocation"], "true continued scalar")
        homes = sd_install.platform_homes(self.home, {})
        with self.assertRaisesRegex(sd_install.MetadataRefused, "scalar continuation"):
            sd_install.render([surface], homes)
        self.assertEqual(surface.skill.read_bytes(), original)
        self.assertTrue(all(not home.root.exists() for home in homes))
        for marker in (None, "true"):
            with self.subTest(marker=marker):
                surface = self.make_surface(marker, b"policy:\n  allow_implicit_invocation: false\n    continued scalar\n")
                with self.assertRaisesRegex(sd_install.MetadataRefused, "scalar continuation"):
                    sd_install.render([surface], homes)
                self.assertTrue(all(not home.root.exists() for home in homes))

    def test_unrelated_continuations_and_control_comments_preserve_bytes(self):
        companion = b"interface:\n  display_name: Original\n    continued scalar\npolicy:\n  allow_implicit_invocation: false\n    # comment stays\n"
        surface = self.make_surface("true\n  # comment stays", companion)
        original = surface.skill.read_bytes().replace(b"adapter.\n", b"adapter.\n  continued description\n")
        surface.skill.write_bytes(original)
        body, extras, _ = sd_install.codex_payload(surface)
        self.assertEqual(body, original.replace(b"disable-model-invocation: true\n", b""))
        self.assertEqual(extras["agents/openai.yaml"], companion)

    def test_unsupported_or_conflicting_policy_refuses(self):
        self.assertTrue(sd_install.invocation_bool("true # comment", "probe"))
        with self.assertRaises(sd_install.MetadataRefused):
            sd_install.invocation_bool("true#not-a-comment", "probe")
        for data in (b"policy: {}\n", b"policy: *alias\n", b"policy:\n allow_implicit_invocation: false\n", b"policy:\n  allow_implicit_invocation: true\n", b"policy:\n  allow_implicit_invocation: false\n  allow_implicit_invocation: false\n", b"policy:\n  allow_implicit_invocation: null\n"):
            with self.subTest(data=data), self.assertRaises(sd_install.MetadataRefused):
                sd_install.codex_policy(data, False)
        self.assertEqual(sd_install.codex_policy(b"# note\n\n", False), b"# note\n\npolicy:\n  allow_implicit_invocation: false\n")
        with self.assertRaises(sd_install.MetadataRefused):
            sd_install.codex_policy(b"policy:\n    allow_implicit_invocation: true\n", False)

    def test_install_collision_drift_removal_and_dry_run(self):
        surface = self.make_surface()
        ctx = self.context_for(self.home / "checkout")
        target = self.home / ".codex" / "skills" / "sd-probe" / "agents" / "openai.yaml"
        target.parent.mkdir(parents=True)
        target.write_text("foreign\n")
        for dry_run in (False, True):
            ctx.dry_run = dry_run
            self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 1)
            self.assertFalse(ctx.receipt.exists())
            self.assertFalse((self.home / ".claude" / "skills").exists())
        target.unlink()
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        self.assertFalse(target.exists())
        ctx.dry_run = False
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        original = target.read_bytes()
        row = next(row for row in self.receipt["owned"] if row["path"] == str(target))
        self.assertEqual(row["sha256"], sd_install.digest(original))
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        target.write_bytes(original + b"# changed\n")
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 1)
        surface.skill.write_bytes(surface.skill.read_bytes().replace(b"disable-model-invocation: true\n", b""))
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_user(ctx, out), 0)
        self.assertIn("modified since it was installed", out.getvalue())
        self.assertTrue(target.exists())
        target.unlink()
        surface = self.make_surface()
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        surface.skill.write_bytes(surface.skill.read_bytes().replace(b"disable-model-invocation: true\n", b""))
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        self.assertFalse(target.exists())
        self.make_surface()
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
        self.assertEqual(sd_install.cmd_uninstall(ctx, io.StringIO()), 0)
        self.assertFalse(target.exists())

    def test_policy_symlink_directory_and_invalid_install_are_refused(self):
        surface = self.make_surface()
        target = self.home / "target"
        target.mkdir()
        planned = [(target, b"data", "invocation-policy:codex")]
        with self.assertRaises(sd_install.MetadataRefused):
            sd_install.policy_collisions(planned, [])
        target.rmdir()
        target.symlink_to(self.home / "missing")
        with self.assertRaises(sd_install.MetadataRefused):
            sd_install.policy_collisions(planned, [])
        surface.skill.write_bytes(b"---\ndisable-model-invocation: invalid\n---\n")
        self.assertEqual(sd_install.cmd_user(self.context_for(self.home / "checkout"), io.StringIO()), 1)

    def test_policy_initial_and_upgrade_failures_restore_retry_state(self):
        for installed in (False, True):
            for stage in ("write_render_plan", "install_hook", "seed_registry", "write_receipt"):
                with self.subTest(installed=installed, stage=stage):
                    surface = self.make_surface()
                    ctx = self.context_for(self.home / "checkout")
                    ctx.home = self.home / f"failure-{installed}-{stage}"
                    if installed:
                        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
                        surface.skill.write_bytes(surface.skill.read_bytes().replace(b"invocation: true", b"invocation: false"))
                    target = ctx.home / ".codex" / "skills" / "sd-probe" / "agents" / "openai.yaml"
                    before = target.read_bytes() if installed else None
                    receipt_before = ctx.receipt.read_bytes() if installed else None
                    real = sd_install.write_render_plan

                    def fail_after_render(*args, render=real, **kwargs):
                        render(*args, **kwargs)
                        raise OSError("synthetic render failure")

                    failure = fail_after_render if stage == "write_render_plan" else SystemExit("synthetic failure")
                    with unittest.mock.patch.object(sd_install, stage, side_effect=failure), self.assertRaises((OSError, SystemExit)):
                        sd_install.cmd_user(ctx, io.StringIO())
                    self.assertEqual(target.read_bytes() if target.exists() else None, before)
                    self.assertEqual(ctx.receipt.read_bytes() if ctx.receipt.exists() else None, receipt_before)
                    self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)

    def test_policy_failure_preserves_concurrent_changes(self):
        self.make_surface()
        ctx = self.context_for(self.home / "checkout")
        target = self.home / ".codex" / "skills" / "sd-probe" / "agents" / "openai.yaml"

        def changed(*args, **kwargs):
            target.write_bytes(b"concurrent change\n")
            raise SystemExit("synthetic failure")

        out = io.StringIO()
        with unittest.mock.patch.object(sd_install, "install_hook", side_effect=changed), self.assertRaises(SystemExit):
            sd_install.cmd_user(ctx, out)
        self.assertEqual(target.read_bytes(), b"concurrent change\n")
        self.assertIn("left in place", out.getvalue())
        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 1)

    def test_partial_policy_write_and_replace_failure_remain_retryable(self):
        for installed in (False, True):
            for failure in ("write", "replace"):
                with self.subTest(installed=installed, failure=failure):
                    surface = self.make_surface()
                    ctx = self.context_for(self.home / "checkout")
                    ctx.home = self.home / f"atomic-{installed}-{failure}"
                    target = ctx.home / ".codex" / "skills" / "sd-probe" / "agents" / "openai.yaml"
                    if installed:
                        self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
                        target.chmod(0o600)
                        surface.skill.write_bytes(surface.skill.read_bytes().replace(b"invocation: true", b"invocation: false"))
                    before = target.read_bytes() if installed else None
                    real_write, real_replace = Path.write_bytes, os.replace

                    def partial(path, data, write=real_write, destination=target, stage=failure):
                        if stage == "write" and path.name == "openai.yaml" and destination.parent in path.parents:
                            write(path, data[:8])
                            raise OSError("synthetic partial write")
                        return write(path, data)

                    def replace(source, destination, real=real_replace, expected=target, stage=failure):
                        if stage == "replace" and Path(destination) == expected:
                            raise OSError("synthetic replace failure")
                        return real(source, destination)

                    with unittest.mock.patch.object(Path, "write_bytes", partial), unittest.mock.patch.object(os, "replace", replace), self.assertRaises(OSError):
                        sd_install.cmd_user(ctx, io.StringIO())
                    self.assertEqual(target.read_bytes() if target.exists() else None, before)
                    self.assertEqual(list(target.parent.iterdir()), [target] if installed else [])
                    self.assertEqual(sd_install.cmd_user(ctx, io.StringIO()), 0)
                    if installed:
                        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_policy_recovery_preserves_missing_directories_and_symlinks(self):
        missing = self.home / "missing"
        directory = self.home / "directory"
        directory.mkdir()
        original = self.home / "original"
        original.write_bytes(b"expected")
        link = self.home / "link"
        link.symlink_to(original)
        out = io.StringIO()
        sd_install.restore_policies([(path, b"expected", None) for path in (missing, directory, link)], out)
        self.assertFalse(missing.exists())
        self.assertTrue(directory.is_dir())
        self.assertTrue(link.is_symlink())
        self.assertEqual(original.read_bytes(), b"expected")
        self.assertEqual(out.getvalue().count("left in place"), 2)
        with unittest.mock.patch.object(Path, "unlink", side_effect=OSError("synthetic recovery failure")):
            sd_install.restore_policies([(original, b"expected", None)], out)
        self.assertIn("policy recovery failed", out.getvalue())
        self.assertEqual(original.read_bytes(), b"expected")

    def test_dry_run_reports_expired_trials_without_writing(self):
        import sd_db

        rows = [{"skill": "sd-expired", "started": "2000", "expires": "2001"}]
        with unittest.mock.patch.object(sd_db, "trials", return_value=rows), unittest.mock.patch.object(sd_db, "skill_use_since", return_value=False), unittest.mock.patch.object(sd_db, "end_trial") as end:
            out = io.StringIO()
            self.assertEqual(sd_install.expire_trials(None, out, dry_run=True), ["sd-expired"])
            self.assertIn("would remove sd-expired", out.getvalue())
            end.assert_not_called()

    def test_expired_trial_cannot_remove_a_promoted_default_skill(self):
        import sd_db

        self.make_surface()
        with unittest.mock.patch.object(sd_install, "open_library", return_value=(object(), "")), unittest.mock.patch.object(sd_db, "active_trials", return_value=[]), unittest.mock.patch.object(sd_install, "expire_trials", return_value=["sd-probe"]):
            self.assertEqual(sd_install.cmd_user(self.context_for(self.home / "checkout"), io.StringIO()), 0)
        self.assertTrue((self.home / ".codex" / "skills" / "sd-probe" / "SKILL.md").is_file())


class StrictVerificationTests(InstallerHarness):
    def setUp(self):
        super().setUp()
        self.checkout = self.checkout_with_commands("sd", "sd-review", "sd-ship", "sd-hook")
        for command in (self.checkout / "bin").iterdir():
            command.write_text("#!/bin/sh\nexit 0\n")
        subprocess.run(["git", "-C", str(self.checkout), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.checkout), "commit", "-qm", "commands"], check=True, capture_output=True)
        self.ctx = self.context_for(self.checkout)
        self.ctx.environ["PATH"] = str(self.home / ".local" / "bin") + os.pathsep + os.environ["PATH"]
        self.assertEqual(sd_install.cmd_user(self.ctx, io.StringIO()), 0)

    def verify(self):
        out = io.StringIO()
        rc = sd_install.cmd_verify(self.ctx, out, as_json=True)
        return rc, json.loads(out.getvalue())

    def codes(self):
        rc, payload = self.verify()
        self.assertEqual(rc, 1)
        return {check["code"] for check in payload["checks"]}

    def test_pass_runs_only_resolved_safe_help_and_writes_nothing(self):
        before = {path: path.read_bytes() for path in self.home.rglob("*") if path.is_file()}
        with unittest.mock.patch.object(sd_install, "open_library", side_effect=AssertionError("database call")):
            rc, result = self.verify()
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["smoke"]["unsmoked"], ["sd-hook"])
        self.assertEqual({row["name"] for row in result["checks"] if row["component"] == "smoke"}, {"sd", "sd-review", "sd-ship"})
        after = {path: path.read_bytes() for path in self.home.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_verify(self.ctx, out), 0)
        self.assertIn("installation: verified", out.getvalue())

    def test_missing_malformed_foreign_and_duplicate_receipts(self):
        original = self.ctx.receipt.read_bytes()
        for update, expected in (
            ({}, "receipt_missing_or_unreadable"),
            ({"schema": 100}, "receipt_schema_unsupported"),
            ({"schema": True}, "receipt_schema_unsupported"),
            ({"checkout": "/foreign"}, "receipt_foreign_checkout"),
            ({"owned": None}, "receipt_malformed"),
            ({"owned": [None]}, "receipt_malformed"),
            ({"owned": [{"path": "x", "kind": "hook", "command": []}]}, "receipt_malformed"),
        ):
            data = json.loads(original)
            data.update(update)
            if not update:
                data = {}
            self.ctx.receipt.write_text(json.dumps(data))
            self.assertIn(expected, self.codes())
        data = json.loads(original)
        data["owned"].append(data["owned"][0])
        self.ctx.receipt.write_text(json.dumps(data))
        self.assertIn("receipt_duplicate_rows", self.codes())
        self.ctx.receipt.write_bytes(b"invalid")
        self.assertIn("receipt_missing_or_unreadable", self.codes())
        self.ctx.receipt.unlink()
        self.assertIn("receipt_missing_or_unreadable", self.codes())
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_verify(self.ctx, out), 1)
        self.assertIn("receipt_missing_or_unreadable", out.getvalue())

    def test_source_mismatch_dirty_and_unreadable_refuse_smoke(self):
        receipt = self.receipt
        receipt["commit"] = "old"
        self.assertEqual(sd_install.verify_source(self.ctx, receipt)["code"], "source_commit_changed")
        receipt = self.receipt
        receipt["dirty"] = True
        self.assertEqual(sd_install.verify_source(self.ctx, receipt)["code"], "source_not_clean")
        (self.checkout / "untracked").write_text("changed")
        with unittest.mock.patch.object(sd_install, "verify_help", side_effect=AssertionError("smoke on dirty source")):
            self.assertIn("source_not_clean", self.codes())
        for failure in (OSError("git missing"), subprocess.TimeoutExpired("git", 5)):
            with unittest.mock.patch.object(sd_install.subprocess, "run", side_effect=failure):
                self.assertEqual(sd_install.verify_source(self.ctx, receipt)["code"], "source_unreadable")
        with unittest.mock.patch.object(sd_install.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            self.assertEqual(sd_install.verify_source(self.ctx, receipt)["code"], "source_unreadable")

    def test_render_missing_modified_foreign_and_receipt_tampering(self):
        path = self.home / ".codex" / "skills" / "sd-probe" / "SKILL.md"
        original = path.read_bytes()
        path.write_bytes(b"modified")
        self.assertIn("render_modified", self.codes())
        path.unlink()
        self.assertIn("render_missing_or_unreadable", self.codes())
        path.write_bytes(original)
        self.assertEqual(self.verify()[0], 0)
        receipt = self.receipt
        receipt["owned"].append({"path": "/never-read", "kind": "skill:foreign", "sha256": "wrong"})
        next(row for row in receipt["owned"] if row["path"] == str(path))["sha256"] = "wrong"
        self.ctx.receipt.write_text(json.dumps(receipt))
        self.assertIn("render_foreign_receipt_path", self.codes())
        self.assertIn("render_receipt_changed", self.codes())

    def test_missing_source_trial_and_invalid_payload_fail(self):
        receipt = self.receipt
        receipt["owned"].append({"path": str(self.home / ".claude" / "skills" / "sd-trial" / "SKILL.md"), "kind": "skill:claude", "sha256": "x"})
        self.assertEqual(sd_install.verify_rendered(self.ctx, receipt)[0]["code"], "source_payload_invalid")
        (self.checkout / "skills" / "sd-probe" / "SKILL.md").write_text("---\nno end")
        self.assertEqual(sd_install.verify_rendered(self.ctx, self.receipt)[0]["code"], "source_payload_invalid")

    def test_receipt_and_live_hook_drift_are_detected(self):
        receipt = self.receipt
        receipt["owned"] = [row for row in receipt["owned"] if row["kind"] != "hook"]
        self.assertEqual(sd_install.verify_hooks(self.ctx, receipt)["code"], "hook_receipt_changed")
        settings = json.loads(self.ctx.settings.read_text())
        settings["hooks"]["SessionStart"] = []
        self.ctx.settings.write_text(json.dumps(settings))
        self.assertIn("hook_missing_or_modified", self.codes())
        self.ctx.settings.write_text("[]")
        self.assertIn("hook_unreadable", self.codes())

    def test_path_shadow_link_drift_and_missing_path(self):
        before = self.ctx.environ["PATH"]
        other = self.home / "common"
        other.mkdir()
        shadow = other / "sd"
        shadow.write_text("#!/bin/sh\nexit 0\n")
        shadow.chmod(0o755)
        self.ctx.environ["PATH"] = str(other) + os.pathsep + before
        self.assertIn("command_shadowed", self.codes())
        self.ctx.environ["PATH"] = str(self.home / "missing-bin")
        self.assertIn("command_not_on_path", self.codes())
        self.ctx.environ["PATH"] = before
        link = self.home / ".local" / "bin" / "sd"
        link.unlink()
        link.symlink_to(shadow)
        self.assertIn("command_link_changed", self.codes())
        receipt = self.receipt
        receipt["owned"].append({"path": "/foreign-link", "kind": "link", "target": "/foreign"})
        self.ctx.receipt.write_text(json.dumps(receipt))
        self.assertIn("command_foreign_receipt_path", self.codes())

    def test_relative_and_empty_path_command_shadows_refuse_without_smoke(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.checkout)
        absolute = self.ctx.environ["PATH"]
        for component in ("../shadow", ".", ""):
            with self.subTest(component=component):
                directory = self.checkout / component if component else self.checkout
                directory.mkdir(exist_ok=True)
                shadow = directory / "sd"
                shadow.write_text("#!/bin/sh\nexit 0\n")
                shadow.chmod(0o755)
                subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
                subprocess.run(["git", "commit", "--allow-empty", "-qm", "shadow fixture"], check=True, capture_output=True)
                self.assertEqual(sd_install.cmd_user(self.ctx, io.StringIO()), 0)
                self.ctx.environ["PATH"] = component + os.pathsep + absolute
                self.assertEqual(Path(sd_install.shutil.which("sd", path=self.ctx.environ["PATH"])).resolve(), shadow.resolve())
                with unittest.mock.patch.object(sd_install, "verify_help", side_effect=AssertionError("unsafe smoke")):
                    rc, result = self.verify()
                self.assertEqual(rc, 1)
                self.assertIn("path_unsupported_components", {row["code"] for row in result["checks"]})
                self.assertEqual(result["smoke"]["status"], "not_run")
                self.ctx.environ["PATH"] = absolute
        self.assertEqual(self.verify()[0], 0)

    def test_relative_and_empty_path_interpreters_never_execute(self):
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(self.checkout)
        absolute = self.ctx.environ["PATH"]
        trace = self.home / "unexpected-interpreter"
        for command in (self.checkout / "bin").iterdir():
            command.write_text("#!/usr/bin/env sh\nexit 0\n")
        for component in ("../shadow", ".", ""):
            with self.subTest(component=component):
                directory = self.checkout / component if component else self.checkout
                directory.mkdir(exist_ok=True)
                shadow = directory / "sh"
                shadow.write_text(f"#!/bin/sh\nprintf invoked >> '{trace}'\nexit 0\n")
                shadow.chmod(0o755)
                subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
                subprocess.run(["git", "commit", "--allow-empty", "-qm", "interpreter fixture"], check=True, capture_output=True)
                self.assertEqual(sd_install.cmd_user(self.ctx, io.StringIO()), 0)
                self.ctx.environ["PATH"] = component + os.pathsep + absolute
                rc, result = self.verify()
                self.assertEqual(rc, 1)
                self.assertEqual(result["smoke"]["status"], "not_run")
                self.assertFalse(trace.exists())
                self.ctx.environ["PATH"] = absolute
        self.assertEqual(self.verify()[0], 0)

    def test_empty_missing_and_trailing_path_components_refuse(self):
        absolute = self.ctx.environ["PATH"]
        for value in ("", os.pathsep, absolute + os.pathsep, absolute + os.pathsep + "relative"):
            self.ctx.environ["PATH"] = value
            self.assertIn("path_unsupported_components", self.codes())
        del self.ctx.environ["PATH"]
        self.assertIn("path_unsupported_components", self.codes())

    def test_interpreter_validation_covers_every_command_without_execution(self):
        source = self.checkout / "bin" / "sd-hook"
        for text, expected in (
            ("#!/absent/interpreter\n", "interpreter_missing"),
            (f"#!{self.home}\n", "interpreter_missing"),
            ("#!/usr/bin/env absent-interpreter\n", "interpreter_missing"),
            ("#!/usr/bin/env -S python3\n", "interpreter_unsupported"),
            ("not executable format\n", "interpreter_unsupported"),
            ("#!'broken\n", "interpreter_unreadable"),
            ("#!/usr/bin/env python3\n", "ok"),
        ):
            source.write_text(text)
            self.assertEqual(sd_install.verify_interpreter(source, os.environ["PATH"]), expected)
        source.write_text("#!/absent/interpreter\n")
        self.assertIn("interpreter_missing", self.codes())
        source.unlink()
        self.assertEqual(sd_install.verify_interpreter(source, ""), "interpreter_unreadable")

    def test_help_failures_timeout_and_launch_error_are_typed(self):
        for side_effect, code in ((subprocess.TimeoutExpired("help", 5), "help_timeout"), (OSError("broken"), "help_unavailable")):
            with unittest.mock.patch.object(sd_install.subprocess, "run", side_effect=side_effect):
                self.assertEqual(sd_install.verify_help(self.ctx, "sd", "/path")["code"], code)
        with unittest.mock.patch.object(sd_install.subprocess, "run", return_value=subprocess.CompletedProcess([], 3)) as run:
            result = sd_install.verify_help(self.ctx, "sd", str(self.home / ".local" / "bin" / "sd"))
            self.assertEqual(result["code"], "help_failed")
            self.assertEqual(run.call_args.args[0], [str(self.home / ".local" / "bin" / "sd"), "--help"])
            self.assertEqual(run.call_args.kwargs["timeout"], 5)
        with unittest.mock.patch.object(sd_install, "verify_help", return_value=sd_install.verify_result("smoke", "help_failed")):
            self.assertIn("help_failed", self.codes())
        with unittest.mock.patch.object(sd_install, "verify_source", side_effect=[sd_install.verify_result("source"), sd_install.verify_result("source", "source_commit_changed")]) as source:
            self.assertIn("source_commit_changed", self.codes())
            self.assertEqual(source.call_count, 2)

    def test_cli_json_mode_and_legacy_status_exit_are_preserved(self):
        with unittest.mock.patch.object(sd_install, "__file__", str(self.checkout / "bin" / "sd_install.py")):
            out = io.StringIO()
            self.assertEqual(sd_install.main(["--verify", "--json", "--home", str(self.home)], self.ctx.environ, out), 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "verified")
        self.assertEqual(self.run_cli("--status", "--json")[0], 2)
        self.ctx.receipt.write_text("invalid")
        self.assertEqual(sd_install.cmd_status(self.ctx, io.StringIO()), 0)
        (self.checkout / "skills" / "sd-probe" / "SKILL.md").write_text("---\ndisable-model-invocation: invalid\n---\n")
        out = io.StringIO()
        self.assertEqual(sd_install.cmd_status(self.ctx, out), 0)
        self.assertIn("metadata cannot render", out.getvalue())


if __name__ == "__main__":
    unittest.main()
