"""The tracked allowlist is derived from this repo's inventories, not typed.

Review found the same defect three times in one pull request, each time a rule
naming something nobody invokes: `python3 scripts/:*` for a directory that does
not exist; `python3 bin/sd-status:*` alone, when the script is executable and
carries a `python3` shebang, so the form the documents actually use is
`bin/sd-status`; and `bin/sd-dashboard:*`, whose `install` verb writes a plist
into `~/Library/LaunchAgents` for a command no document tells anyone to run by
hand. Every one came from writing a rule out of an assumption about the
workflow rather than reading what the workflow runs, and narrowing the list by
hand found them one at a time while reintroducing the shape twice.

Hand-narrowing was the wrong instrument. The repository already states what it
runs, in three places that are maintained for other reasons:

* the Makefile's public `.PHONY` targets,
* README's `bin/sd_install.py` table, one row per mode, with the mode's effect
  written in the row,
* the `mcp__github__*` tools a shipped skill names.

So the list is derived from those at run time and compared against the file. A
rule with no source fails; a source with no rule fails. Adding a `make` target
and forgetting the allowlist is a test failure rather than a prompt somebody
works around six months later.

**What this can and cannot catch.** The comparison is only as good as the
filters below, and it cannot audit its own judgment: writing the file from this
derivation makes the two agree by construction. Its job is to keep them
agreeing as the inventories move. The two checks that are *not* circular are
the ones after it -- every path a rule names must exist, and a target that is
executable with a shebang must carry both invocation forms -- and those two are
what would have failed on each of the three defects above.

`skills/` names six `bin/` commands that do not exist (`sd-ship`, `sd-plan`,
`sd-map`, `sd-help`, `sd-deps`, `sd-suggest`, whose own SKILL.md says "There is
no `bin/sd-suggest` yet"). That is why every derivation here filters on the
filesystem rather than trusting a name it read in a document.
"""

from __future__ import annotations

import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

# A README row reads `| `bin/sd_install.py --flag` | What it does |`. The mode
# is allowlisted unless the row itself says not to, so both filters below read
# the document rather than a list of flags somebody kept in their head.
INSTALL_ROW = re.compile(r"^\|\s*`bin/sd_install\.py ([^`]+)`\s*\|\s*([^|]+?)\s*\|$", re.M)

# A placeholder in the mode means it takes a path, and a path argument is the
# thing that turns a repo-scoped grant into an arbitrary-path write:
# `--repo PATH` writes `PATH/CLAUDE.local.md`, `--home DIR` moves the install
# root. Path-scoping the script is not the test; what the script does with a
# path argument is.
TAKES_A_PATH = re.compile(r"\b[A-Z]{3,}\b")

# The row's own first word. A tracked allowlist that a second contributor
# inherits should not carry a grant whose documented effect is deletion, and
# the README already says which those are.
DESTRUCTIVE = ("Remove", "Delete", "Uninstall", "Drop")

# README's surface table marks exactly one command "Read-only:". A read-only
# surface is the only kind whose whole flag space is safe behind one wildcard,
# so that adjective -- maintained for readers, not for this test -- is what
# decides which `bin/` commands appear at all.
READ_ONLY_SURFACE = re.compile(r"^\|\s*`(sd-[a-z-]+)`\s*\|\s*Read-only:", re.M)

MCP_TOOL = re.compile(r"mcp__github__[a-z_]+")

BASH_RULE = re.compile(r"^Bash\((.*)\)$")


def settings_allow() -> list[str]:
    """What the tracked file actually grants."""

    return json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["allow"]


def public_make_targets() -> list[str]:
    """The Makefile's own public target list.

    The first `.PHONY` line names what a person runs; the second names the two
    path-printing helpers a recipe calls (`lint-ruff-paths`, `lint-mypy-paths`),
    which are not commands anybody types.
    """

    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    first = re.search(r"^\.PHONY:(.*)$", text, re.M)
    assert first, "Makefile has no .PHONY line"
    return first.group(1).split()


def readme_install_modes() -> list[tuple[str, str]]:
    """Every `sd_install.py` mode README documents, as (mode, what it does)."""

    return INSTALL_ROW.findall((REPO_ROOT / "README.md").read_text(encoding="utf-8"))


def grantable_install_modes() -> list[str]:
    """The documented modes that take no path and destroy nothing."""

    return [mode for mode, effect in readme_install_modes()
            if not TAKES_A_PATH.search(mode) and not effect.startswith(DESTRUCTIVE)]


def read_only_surfaces() -> list[str]:
    """The `bin/` commands README describes as read-only, that exist."""

    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return [name for name in READ_ONLY_SURFACE.findall(text)
            if (REPO_ROOT / "bin" / name).is_file()]


def skill_mcp_tools() -> set[str]:
    """The GitHub tools a shipped skill tells a reader to call."""

    found: set[str] = set()
    for skill in REPO_ROOT.glob("skills/**/*.md"):
        found.update(MCP_TOOL.findall(skill.read_text(encoding="utf-8")))
    return found


def runs_under_python3(name: str) -> bool:
    """A `bin/` file that is executable and says how to run itself."""

    target = REPO_ROOT / "bin" / name
    if not target.is_file():
        return False
    first = target.read_text(encoding="utf-8").splitlines()[:1]
    return bool(first) and first[0].startswith("#!") and "python3" in first[0]


def derived_allow() -> set[str]:
    """The whole tracked allowlist, from the three inventories above."""

    rules = {f"Bash(make {target})" for target in public_make_targets()}
    rules |= {f"Bash(python3 bin/sd_install.py {mode})" for mode in grantable_install_modes()}
    for name in read_only_surfaces():
        rules.add(f"Bash(bin/{name}:*)")
        if runs_under_python3(name):
            # Executable with a shebang, so both spellings are real and a rule
            # matching one does not match the other.
            rules.add(f"Bash(python3 bin/{name}:*)")
    return rules | skill_mcp_tools()


class PermissionAllowlistTests(unittest.TestCase):
    def test_the_tracked_allowlist_is_exactly_what_the_inventories_yield(self) -> None:
        actual = set(settings_allow())
        derived = derived_allow()
        self.assertEqual(
            actual, derived,
            f"\n  granted with no source: {sorted(actual - derived)}"
            f"\n  documented with no rule: {sorted(derived - actual)}")

    def test_every_path_a_rule_names_exists(self) -> None:
        """The defect that arrived three times, checked without a derivation.

        `python3 scripts/:*` named a directory this repository does not have.
        A rule pointing at nothing is not harmless -- it reads as coverage, so
        the prompt it was supposed to stop keeps arriving and the next person
        widens something real to fix it.
        """

        missing = []
        for rule in settings_allow():
            match = BASH_RULE.match(rule)
            if not match:
                continue
            for token in match.group(1).removesuffix(":*").split():
                if "/" not in token:
                    continue
                if not (REPO_ROOT / token).exists():
                    missing.append(f"{rule} names {token}, which does not exist")
        self.assertEqual(missing, [], "\n".join(missing))

    def test_an_executable_target_carries_both_invocation_forms(self) -> None:
        """`bin/sd-status --json` and `python3 bin/sd-status --json` both happen.

        A rule matching one does not match the other, so granting only the
        `python3` spelling covers the form this repository's own documents
        never use. Found in review after the rule had already shipped once.
        """

        gaps = []
        for rule in settings_allow():
            match = BASH_RULE.match(rule)
            if not match or not match.group(1).startswith("bin/"):
                continue
            name = match.group(1).removesuffix(":*").split("/")[-1].split()[0]
            if runs_under_python3(name) and f"Bash(python3 {match.group(1)})" not in settings_allow():
                gaps.append(f"{rule} has no `python3 bin/{name}` counterpart")
        self.assertEqual(gaps, [], "\n".join(gaps))

    def test_the_inventories_were_actually_read(self) -> None:
        """The control. A regex that silently stops matching would empty the
        derived set and make the comparison above pass over anything."""

        self.assertNotEqual(public_make_targets(), [], "Makefile .PHONY not parsed")
        self.assertNotEqual(readme_install_modes(), [], "README install table not parsed")
        self.assertNotEqual(read_only_surfaces(), [], "README surface table not parsed")
        self.assertNotEqual(skill_mcp_tools(), set(), "no skill named an mcp__github__ tool")

    def test_a_destructive_or_path_taking_mode_is_never_granted(self) -> None:
        """Both filters, against the README rows they read.

        Without this, widening `TAKES_A_PATH` or emptying `DESTRUCTIVE` would
        quietly add `--repo [PATH]` and `--uninstall` to the derived set, and
        the comparison would then demand they be granted.
        """

        documented = dict(readme_install_modes())
        self.assertIn("--repo [PATH]", documented, "README no longer documents --repo")
        self.assertIn("--uninstall", documented, "README no longer documents --uninstall")
        granted = grantable_install_modes()
        self.assertNotIn("--repo [PATH]", granted)
        self.assertNotIn("--uninstall", granted)
        self.assertIn("--status", granted)


if __name__ == "__main__":
    unittest.main()
