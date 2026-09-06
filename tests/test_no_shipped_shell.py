"""The pack ships no shell, and this is what keeps that true.

Step 3e removed the `Shell coverage` CI job and its required status context
(R11-D6). That removal is only defensible because of a fact about the tree
rather than a judgement about the job: the payload it measured -- the shell
under `templates/scripts/` that every consumer received a copy of -- no longer
exists. The installer renders `skills/**/SKILL.md` verbatim and nothing else,
so there is no shipped shell left to cover.

A deleted CI job leaves nothing behind that notices when its premise stops
holding. This test is that notice. If shell reappears on the render surface,
or a script lands outside the repository's own tooling directory, the coverage
lane's removal has quietly become wrong and this fails with the reason.

The two checks are deliberately different in kind. The render-surface check is
absolute: `skills/` is what gets copied onto a machine, and a shell file there
is shipped shell by definition. The location check is an allow-list, because
this repository legitimately runs shell on itself -- `make check` drives three
scripts under `.github/scripts/`, which is also exactly the set the bash 3.2
gate still covers. Adding a fourth there is ordinary work; adding one anywhere
else is the change that needs a decision record.
"""

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Where this repository is allowed to keep shell it runs on itself. Prefixes,
# matched against forward-slash paths as git reports them.
TOOLING_PREFIXES = (".github/scripts/",)

# What the installer copies onto a machine. Anything here reaches a consumer.
RENDER_ROOT = "skills/"

SHELL_SUFFIXES = (".sh", ".bash", ".zsh")


def tracked_files():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def looks_like_shell(path):
    """Extension or shebang. Neither alone is enough.

    `run-tests.sh` announces itself by name; a hook or helper checked in
    without an extension announces itself only on its first line. Enumerating
    from git and testing both is what makes this a sweep rather than a search
    for the spelling already known about.
    """
    if path.endswith(SHELL_SUFFIXES):
        return True
    target = REPO_ROOT / path
    try:
        with target.open("rb") as handle:
            first = handle.readline(128)
    except OSError:
        return False
    if not first.startswith(b"#!"):
        return False
    line = first.decode("utf-8", "replace")
    return "bash" in line or "/sh" in line or " sh" in line


class NoShippedShellTests(unittest.TestCase):
    def test_the_render_surface_is_markdown_only(self):
        """A skill directory is copied verbatim; a script there is shipped.

        The surface is `skills/<name>/...`, not everything under `skills/`.
        Requirement 10 put one file at the root of the tree -- `paths.json`,
        which says *which* directories install -- and the installer reads it
        rather than rendering it: it iterates the named skills, each of which
        is a directory, so a file beside them cannot reach a platform home.
        The test below pins that, so the carve-out here stays one named file
        rather than a hole anything at the root can fall through.
        """
        rendered = [
            p for p in tracked_files()
            if p.startswith(RENDER_ROOT) and "/" in p[len(RENDER_ROOT):]
        ]
        self.assertTrue(rendered, "render surface is empty; the pack ships nothing")

        offenders = [p for p in rendered if not p.endswith(".md")]
        self.assertEqual(
            offenders,
            [],
            "the installer renders this tree verbatim onto every platform home, "
            "so a non-markdown file here is payload. If that is intended, the "
            "renderer, its parity test, and R11-D6's premise all need revisiting",
        )

    def test_the_only_file_at_the_root_of_the_tree_is_the_paths_file(self):
        """The carve-out above, pinned to one name.

        `paths.json` is exempt from the markdown rule because the installer
        reads it instead of rendering it. Nothing else may join it quietly:
        a second root file would be exempt by shape rather than by decision,
        and if it *were* rendered the exemption would have hidden it.
        """
        root_files = [
            p for p in tracked_files()
            if p.startswith(RENDER_ROOT) and "/" not in p[len(RENDER_ROOT):]
        ]
        self.assertEqual(root_files, ["skills/paths.json"])

    def test_shell_lives_only_in_this_repository_s_own_tooling(self):
        offenders = [
            path
            for path in tracked_files()
            if looks_like_shell(path)
            and not path.startswith(TOOLING_PREFIXES)
        ]
        self.assertEqual(
            offenders,
            [],
            "shell outside .github/scripts/ is shell the pack may hand to "
            "someone else. The `Shell coverage` CI job that used to measure "
            "shipped shell was removed at step 3e (R11-D6) on the premise that "
            "none exists. Restore the lane or move the script",
        )

    def test_the_bash_gate_and_the_allow_list_describe_the_same_set(self):
        """Two statements of one fact drift; catch it while it is cheap.

        CONTRIBUTING says the bash 3.2 gate's remaining subject is this
        repository's own scripts. That is true only while the allow-list above
        and the gate's enumeration agree.
        """
        shell = [p for p in tracked_files() if looks_like_shell(p)]
        self.assertTrue(shell, "expected this repository to run some shell on itself")
        for path in shell:
            self.assertTrue(
                path.startswith(TOOLING_PREFIXES),
                f"{path} is shell the bash 3.2 gate does not cover",
            )


if __name__ == "__main__":
    unittest.main()
