"""`sd attribute` -- the write side of the trailer the review lane reads.

The read side (`sd_lib.attribution`, `_in_range`, `author_vendors`) decides who
may review a change. This verb writes what it reads, so the tests that matter
here are not the happy path: they are the ones where a plausible input would
write a line that reads back as a *different* vendor, or as no vendor at all.
The second is the dangerous one. `attribution` drops an `Attributes:` line that
does not split into exactly two fields, and `author_vendors` leaves a commit
with no claim out of the author set entirely -- so a vendor that is dropped on
the way in does not block itself from reviewing its own work. It reviews it.

Every assertion below therefore goes through the reader rather than through the
string this module wrote. A test that checked the trailer text would pass on a
line the reader silently ignores, which is exactly the failure it exists to
catch: `author_vendors` already had to learn to strip a vendor after one
unstripped pair failed the author-exclusion check open.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402
import sd_registry  # noqa: E402


def registry(**vendors: str) -> sd_registry.Registry:
    """A registry holding `name=vendor` and nothing else.

    Built here rather than parsed from a fixture file, because what these
    tests vary is one field -- the vendor's exact bytes -- and a YAML round
    trip would normalise some of the values under test before the code saw
    them, which would be the tests grading their own fixture.
    """

    return sd_registry.Registry(
        pathlib.Path("/fixture/providers.yaml"),
        {},
        {
            name: sd_registry.Provider(name=name, vendor=vendor, bill="b", start="x")
            for name, vendor in vendors.items()
        },
    )


class AttributeFixture(unittest.TestCase):
    """A repository with a base commit and a branch, as a branch review sees it."""

    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(self._remove)
        self.git("init", "--quiet", "--initial-branch", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.base = self.commit("chore: base\n\nAuthored-with: human")
        self.git("checkout", "--quiet", "-b", "topic")

    def _remove(self) -> None:
        subprocess.run(["rm", "-rf", str(self.root)], check=False)

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=str(self.root), check=True,
            capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, message: str, name: str | None = None) -> str:
        target = self.root / (name or f"f{len(list(self.root.iterdir()))}.py")
        target.write_text(f"x = {len(message)}\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def head_message(self) -> str:
        return subprocess.run(
            ["git", "log", "-1", "--format=%B"], cwd=str(self.root), check=True,
            capture_output=True, text=True,
        ).stdout

    def vendors(self) -> tuple[str, ...]:
        return sd_lib.author_vendors(self.root, self.base, "HEAD")

    def said(self) -> dict[str, str]:
        return sd_lib.attribution(self.root, self.base, "HEAD")


class TheRoundTripTests(AttributeFixture):
    """What the verb writes reads back as what was meant, or does not write."""

    def test_an_untagged_commit_reads_back_as_the_entry_and_its_vendor(self) -> None:
        silent = self.commit("feat: something")
        with self.assertRaises(sd_lib.TrailerError):
            self.vendors()  # the state the verb exists to repair
        sha, value, covered = sd_lib.attribute(
            self.root, silent, "claude", registry(claude="anthropic"))
        self.assertEqual(value, "claude/anthropic")
        self.assertEqual(covered, [silent])
        self.assertEqual(self.said()[silent], "claude/anthropic")
        self.assertEqual(self.vendors(), ("anthropic",))
        # The repair does not need repairing (C-40): it says who made it, and
        # the scan that refuses a silent commit accepts this one.
        self.assertEqual(self.said()[sha], sd_lib.HUMAN_AUTHOR)

    def test_the_attributes_line_carries_the_whole_sha(self) -> None:
        """`_in_range` wants seven characters and a unique prefix; give it forty.

        A shortened sha is a prefix that is unique today. The next commit is
        free to collide with it, and a colliding prefix resolves to nothing at
        all -- the claim is dropped and the vendor leaves the author set.
        """

        silent = self.commit("feat: something")
        sd_lib.attribute(self.root, silent[:8], "claude", registry(claude="anthropic"))
        line = [text for text in self.head_message().splitlines()
                if text.startswith(sd_lib.ATTRIBUTES_TRAILER)][0]
        self.assertEqual(line.split(), [sd_lib.ATTRIBUTES_TRAILER, silent, "claude/anthropic"])
        self.assertEqual(len(silent), 40)

    def test_a_vendor_with_surrounding_whitespace_still_reads_back_as_itself(self) -> None:
        """The failure this whole module is shaped around, at the point of writing.

        An unstripped vendor once reached the author-exclusion check as
        `" anthropic"`, matched no registry entry, and left the author's own
        vendor on the reviewer chain. `author_vendors` strips on the way in
        now; this asserts nothing needs it to, because the line written holds
        three fields and not four.
        """

        silent = self.commit("feat: something")
        sd_lib.attribute(self.root, silent, "claude", registry(claude="  anthropic  "))
        line = [text for text in self.head_message().splitlines()
                if text.startswith(sd_lib.ATTRIBUTES_TRAILER)][0]
        self.assertEqual(len(line.split()), 3, line)
        self.assertEqual(self.said()[silent], "claude/anthropic")
        self.assertEqual(self.vendors(), ("anthropic",))

    def test_two_vendors_differing_only_in_case_are_one_vendor(self) -> None:
        """`author_vendors` folds case, so the trailer is written folded.

        Otherwise `git log` shows `Anthropic` while the check compares
        `anthropic`, and the operator reading the commit to find out who may
        review it reads a different string from the one that decides.
        """

        first = self.commit("feat: one")
        sd_lib.attribute(self.root, first, "claude", registry(claude="Anthropic"))
        second = self.commit("feat: two")
        sd_lib.attribute(self.root, second, "clyde", registry(clyde="ANTHROPIC"))
        self.assertEqual(self.said()[first], "claude/anthropic")
        self.assertEqual(self.said()[second], "clyde/anthropic")
        self.assertEqual(self.vendors(), ("anthropic",))

    def test_human_writes_the_bare_word_and_contributes_no_vendor(self) -> None:
        """A range that is the operator's alone is reviewed by the first entry."""

        silent = self.commit("feat: something")
        _, value, _ = sd_lib.attribute(
            self.root, silent, "human", registry(claude="anthropic"))
        self.assertEqual(value, sd_lib.HUMAN_AUTHOR)
        self.assertEqual(self.said()[silent], sd_lib.HUMAN_AUTHOR)
        self.assertEqual(self.vendors(), ())

    def test_the_trailers_are_the_last_paragraph_and_unindented(self) -> None:
        """Git's rule, and `attribution`'s: anything else is not a trailer.

        Both halves are asserted against the message the verb produced rather
        than against a description of it, because a body paragraph appended
        after the block, or a single leading space, turns every line here into
        prose that the reader steps over without a word.
        """

        first = self.commit("feat: one")
        second = self.commit("feat: two")
        sd_lib.attribute(
            self.root, f"{self.base}..HEAD", "claude", registry(claude="anthropic"))
        paragraphs = self.head_message().strip().split("\n\n")
        block = paragraphs[-1].splitlines()
        self.assertEqual(len(block), 3, self.head_message())
        for line in block:
            self.assertEqual(line, line.lstrip(), "an indented trailer is not a trailer")
        for earlier in paragraphs[:-1]:
            self.assertNotIn(sd_lib.ATTRIBUTES_TRAILER, earlier)
        self.assertEqual(self.said()[first], "claude/anthropic")
        self.assertEqual(self.said()[second], "claude/anthropic")

    def test_a_block_that_is_not_the_last_paragraph_is_read_by_nobody(self) -> None:
        """The control for the test above, so it is measuring something.

        Written by hand, since the verb will not produce it: were the writer to
        grow a signature paragraph after its trailers, this is the behaviour
        that would greet it -- silence, and a vendor missing from the set.
        """

        silent = self.commit("feat: something")
        self.commit(
            f"chore: attribute\n\n{sd_lib.ATTRIBUTES_TRAILER} {silent} claude/anthropic\n"
            f"{sd_lib.AUTHORED_TRAILER} {sd_lib.HUMAN_AUTHOR}\n\nA closing thought.",
            name="later.py")
        self.assertNotIn(silent, self.said())

    def test_an_indented_block_is_read_by_nobody_either(self) -> None:
        """The other control. Git does not read one, so neither does the pack."""

        silent = self.commit("feat: something")
        self.commit(
            f"chore: attribute\n\n    {sd_lib.ATTRIBUTES_TRAILER} {silent} claude/anthropic\n"
            f"    {sd_lib.AUTHORED_TRAILER} {sd_lib.HUMAN_AUTHOR}",
            name="later.py")
        self.assertNotIn(silent, self.said())


class TheRefusalTests(AttributeFixture):
    """A malformed input is refused loudly rather than written quietly."""

    def refuses(self, target: str, name: str, **vendors: str) -> str:
        before = self.git("rev-parse", "HEAD")
        with self.assertRaises(sd_lib.TrailerError) as caught:
            sd_lib.attribute(self.root, target, name, registry(**vendors))
        # Nothing was written. A refusal that had already committed would
        # leave the repository holding a claim the operator was told failed.
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        return str(caught.exception)

    def test_an_entry_the_registry_does_not_have_is_refused_by_name(self) -> None:
        silent = self.commit("feat: something")
        message = self.refuses(silent, "nosuch", claude="anthropic")
        self.assertIn("nosuch", message)
        self.assertIn("providers.yaml", message)
        self.assertIn("claude", message)

    def test_an_entry_differing_only_in_case_is_a_different_entry(self) -> None:
        """The registry is keyed exactly, so `CLAUDE` is not `claude`.

        Guessing would be worse than refusing: two entries whose names differ
        only in case are two entries, and a case-insensitive match would pick
        one of them for the operator without saying which.
        """

        silent = self.commit("feat: something")
        self.assertIn("CLAUDE", self.refuses(silent, "CLAUDE", claude="anthropic"))

    def test_a_vendor_with_a_space_inside_it_is_refused(self) -> None:
        """It would write four fields where the reader wants three, and the
        reader drops such a line -- leaving the vendor out of the author set."""

        silent = self.commit("feat: something")
        self.assertIn("unreadable", self.refuses(silent, "claude", claude="anthro pic"))

    def test_a_vendor_carrying_a_slash_is_refused(self) -> None:
        """`partition('/')` takes the first one, so the rest becomes the vendor."""

        silent = self.commit("feat: something")
        self.assertIn("slash", self.refuses(silent, "claude", claude="anthropic/eu"))

    def test_an_empty_vendor_is_refused(self) -> None:
        silent = self.commit("feat: something")
        self.assertIn("pair", self.refuses(silent, "claude", claude="   "))

    def test_a_registry_entry_may_not_be_called_human(self) -> None:
        """Otherwise its trailer reads as the operator and hides its vendor.

        The one input that turns a real vendor into no vendor without a single
        malformed character in the line: a registry naming an entry `human`
        would have `sd attribute <sha> human` write the bare word, which
        `author_vendors` skips by design.
        """

        silent = self.commit("feat: something")
        message = self.refuses(silent, "human", human="anthropic")
        self.assertIn("human", message)
        self.assertIn("hide its vendor", message)

    def test_a_merge_named_directly_is_refused(self) -> None:
        """It wrote nothing, and the review skips it, so the claim would be lost."""

        self.commit("feat: on the branch")
        self.git("checkout", "--quiet", "main")
        self.commit("feat: elsewhere", name="other.py")
        self.git("checkout", "--quiet", "topic")
        self.git("merge", "--quiet", "--no-ff", "-m", "Merge main", "main")
        merge = self.git("rev-parse", "HEAD")
        self.assertIn("merge", self.refuses(merge, "claude", claude="anthropic"))

    def test_a_range_whose_only_commit_is_a_merge_is_refused(self) -> None:
        """`commit_messages` passes `--no-merges`, so the range comes back empty.

        Writing an empty attributing commit here would report success having
        recorded nothing, which is the shape of failure this file is about.

        The range is built from the merge's *second* parent, which is the only
        way to get one: a merge always brings its side's commits into a range
        that excludes only the first parent, and they answer for themselves.
        """

        self.git("checkout", "--quiet", "main")
        elsewhere = self.commit("feat: elsewhere\n\nAuthored-with: human", name="other.py")
        self.git("checkout", "--quiet", "topic")
        self.git("merge", "--quiet", "--no-ff", "-m", "Merge main", "main")
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", "HEAD").split()), 3)
        message = self.refuses(f"{elsewhere}..HEAD", "claude", claude="anthropic")
        self.assertIn("carries work to attribute", message)

    def test_a_commit_that_already_says_is_refused_rather_than_overwritten(self) -> None:
        """`Attributes:` never outranks `Authored-with:`, which is the point.

        A later claim that could relabel an anthropic commit as an openai one
        would buy it an anthropic reviewer. So the writer will not produce a
        line the reader is built to ignore.
        """

        tagged = self.commit("feat: something\n\nAuthored-with: codex/openai")
        message = self.refuses(tagged, "claude", claude="anthropic")
        self.assertIn("outranks", message)
        self.assertEqual(self.vendors(), ("openai",))

    def test_a_commit_that_is_not_on_this_branch_is_refused(self) -> None:
        """The attributing commit lands here, so a claim about elsewhere is inert."""

        self.git("checkout", "--quiet", "main")
        elsewhere = self.commit("feat: elsewhere", name="other.py")
        self.git("checkout", "--quiet", "topic")
        self.assertIn("reachable", self.refuses(elsewhere, "claude", claude="anthropic"))

    def test_a_nonexistent_commit_is_refused(self) -> None:
        self.commit("feat: something")
        self.assertIn("reachable", self.refuses("0" * 40, "claude", claude="anthropic"))

    def test_a_malformed_range_is_refused(self) -> None:
        self.commit("feat: something")
        self.assertIn("range", self.refuses("..HEAD", "claude", claude="anthropic"))


class TheScriptTests(AttributeFixture):
    """`Authored-with: script`: a deterministic job wrote it, no model and no person (sd:1637).

    A peer of `human`: reserved, no vendor, so any provider may review it. It
    is not `human`, so an unattended job's commits stop counting as the
    operator's own.
    """

    refuses = TheRefusalTests.refuses

    def test_a_script_trailer_reads_back_and_contributes_no_vendor(self) -> None:
        landed = self.commit("chore: data\n\nAuthored-with: script")
        self.assertEqual(self.said()[landed], sd_lib.SCRIPT_AUTHOR)
        self.assertEqual(self.vendors(), ())

    def test_sd_attribute_writes_script_bare(self) -> None:
        silent = self.commit("chore: data")
        _, value, _ = sd_lib.attribute(self.root, silent, "script", registry(claude="anthropic"))
        self.assertEqual((value, self.said()[silent]), ("script", "script"))
        self.assertEqual(self.vendors(), ())

    def test_a_registry_entry_may_not_be_called_script(self) -> None:
        silent = self.commit("chore: data")
        self.assertIn("hide its vendor", self.refuses(silent, "script", script="anthropic"))

    def test_a_squash_body_may_carry_script(self) -> None:
        import sd_ship_body
        self.assertTrue(sd_ship_body.known_author("script", []))


class TheRangeTests(AttributeFixture):
    """The form the rebase repair needs: a mixture, repaired in one commit."""

    def test_a_range_attributes_only_the_commits_that_said_nothing(self) -> None:
        tagged = self.commit("feat: one\n\nAuthored-with: codex/openai")
        silent = self.commit("feat: two")
        _, _, covered = sd_lib.attribute(
            self.root, f"{self.base}..HEAD", "claude", registry(claude="anthropic"))
        self.assertEqual(covered, [silent])
        self.assertEqual(self.said()[tagged], "codex/openai")
        self.assertEqual(self.said()[silent], "claude/anthropic")
        self.assertEqual(sorted(self.vendors()), ["anthropic", "openai"])

    def test_a_range_where_every_commit_already_says_is_refused(self) -> None:
        self.commit("feat: one\n\nAuthored-with: codex/openai")
        with self.assertRaises(sd_lib.TrailerError) as caught:
            sd_lib.attribute(
                self.root, f"{self.base}..HEAD", "claude", registry(claude="anthropic"))
        self.assertIn("already names its author", str(caught.exception))

    def test_a_rebase_loses_the_claim_and_one_range_attribution_restores_it(self) -> None:
        """The case the plan calls deliberate and rare (C-41).

        The `Attributes:` line names a hash. A rebase makes a new one, the
        claim names a commit that is no longer in the range, `_in_range` drops
        it, and the review refuses again -- which is the behaviour, not a bug:
        a trailer that followed content across rewrites would have to match by
        patch id, and a conflict resolution changes that.
        """

        silent = self.commit("feat: something")
        sd_lib.attribute(self.root, silent, "claude", registry(claude="anthropic"))
        self.assertEqual(self.vendors(), ("anthropic",))
        self.git("checkout", "--quiet", "main")
        self.commit("feat: moving the base\n\nAuthored-with: human", name="moved.py")
        self.git("checkout", "--quiet", "topic")
        self.git("rebase", "--quiet", "main")
        moved = self.git("rev-parse", "main")
        with self.assertRaises(sd_lib.TrailerError) as caught:
            sd_lib.author_vendors(self.root, moved, "HEAD")
        self.assertIn("carry no", str(caught.exception))
        sd_lib.attribute(self.root, f"{moved}..HEAD", "claude", registry(claude="anthropic"))
        self.assertEqual(sd_lib.author_vendors(self.root, moved, "HEAD"), ("anthropic",))


class CommandFixture(AttributeFixture):
    """`sd attribute` end to end, through the parser and the real registry read."""

    def setUp(self) -> None:
        super().setUp()
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(subprocess.run, ["rm", "-rf", str(self.home)], check=False)
        seeded = self.home / sd_registry.REGISTRY_RELATIVE
        seeded.parent.mkdir(parents=True)
        # Two entries, because a registry whose first author is also its first
        # reviewer is refused at read time -- correctly, and it would refuse
        # this fixture before the verb under test was reached.
        seeded.write_text(
            "bills:\n  anthropic: { cost: subscription }\n  openai: { cost: subscription }\n"
            "providers:\n"
            "  claude: { start: 'claude -p', vendor: anthropic, bill: anthropic,\n"
            "            roles: [author, reviewer], env: [] }\n"
            "  codex:  { start: 'codex exec', vendor: openai, bill: openai,\n"
            "            roles: [author, reviewer], env: [] }\n"
            "roles:\n  author: [claude, codex]\n  reviewer: [codex, claude]\n",
            encoding="utf-8")

    def run_sd(self, *argv: str) -> tuple[int, str, str]:
        """`bin/sd` in-process, with `HOME` and the cwd pointed at the fixture.

        In-process rather than as a subprocess so a traceback lands in the
        failure instead of in a captured stderr nobody reads, and because the
        registry is resolved from `HOME` at call time, which is exactly what
        this has to vary.
        """

        spec = importlib.util.spec_from_loader(
            "sd_cli_for_attribute", importlib.machinery.SourceFileLoader(
                "sd_cli_for_attribute", str(REPO_ROOT / "bin" / "sd")))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        environment, cwd = dict(os.environ), os.getcwd()
        os.environ["HOME"] = str(self.home)
        os.chdir(self.root)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = module.main(list(argv))
        finally:
            os.chdir(cwd)
            os.environ.clear()
            os.environ.update(environment)
        return code, out.getvalue(), err.getvalue()


class TheCommandTests(CommandFixture):
    """The verb's own answers: what it writes, what it refuses, the range form."""

    def test_the_verb_writes_a_commit_the_reader_agrees_with(self) -> None:
        silent = self.commit("feat: something")
        code, out, err = self.run_sd("attribute", silent, "claude")
        self.assertEqual(code, 0, err)
        self.assertIn("claude/anthropic", out)
        self.assertIn(silent[:12], out)
        self.assertEqual(self.vendors(), ("anthropic",))

    def test_an_unknown_entry_exits_one_and_writes_nothing(self) -> None:
        silent = self.commit("feat: something")
        before = self.git("rev-parse", "HEAD")
        code, _, err = self.run_sd("attribute", silent, "nosuch")
        self.assertEqual(code, 1)
        self.assertIn("nosuch", err)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_the_trailer_value_names_its_entry(self) -> None:
        """`claude/anthropic` is what every commit carries; refusing it pushed agents to `human` (sd:2689)."""
        silent = self.commit("feat: something")
        code, out, err = self.run_sd("attribute", silent, "claude/anthropic")
        self.assertEqual(code, 0, err)
        self.assertIn("claude/anthropic", out)
        self.assertEqual(self.said()[silent], "claude/anthropic")

    def test_a_vendor_the_registry_does_not_give_refuses_naming_both_forms(self) -> None:
        silent = self.commit("feat: something")
        before = self.git("rev-parse", "HEAD")
        code, _, err = self.run_sd("attribute", silent, "claude/openai")
        self.assertEqual(code, 1)
        self.assertIn("'claude' or 'claude/anthropic'", err)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

    def test_the_range_form_reaches_the_library(self) -> None:
        first = self.commit("feat: one")
        second = self.commit("feat: two")
        code, out, err = self.run_sd("attribute", f"{self.base}..HEAD", "claude")
        self.assertEqual(code, 0, err)
        self.assertIn("2 commit(s)", out)
        self.assertEqual(self.said()[first], "claude/anthropic")
        self.assertEqual(self.said()[second], "claude/anthropic")


class TheWriterTests(CommandFixture):
    """sd:2009 gap 1: the repair commit names who ran `sd attribute`, not `human` always.

    The operator's ruling of 2026-09-30: an agent's repair says the agent's
    entry. `SD_AUTHOR` names it, as it does to the commit-msg hook (sd:1295);
    unset, the repair says `human`, as before.
    """

    def run_as(self, author: str | None, *argv: str, marker: str | None = None) -> tuple[int, str, str]:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SD_AUTHOR", None)
            os.environ.pop("CLAUDECODE", None)  # the suite itself may run in a Claude Code shell
            if author is not None:
                os.environ["SD_AUTHOR"] = author
            if marker is not None:
                os.environ["CLAUDECODE"] = marker
            return self.run_sd(*argv)

    def own(self) -> str:
        return self.git("log", "-1", "--format=%(trailers:key=Authored-with,valueonly)")

    def test_an_agent_repair_says_the_agents_entry(self) -> None:
        silent = self.commit("feat: something")
        code, _, err = self.run_as("claude", "attribute", silent, "claude")
        self.assertEqual((code, self.own()), (0, "claude/anthropic"), err)
        self.assertEqual(self.vendors(), ("anthropic",))

    def test_without_sd_author_the_repair_says_human(self) -> None:
        silent = self.commit("feat: something")
        code, _, err = self.run_as(None, "attribute", silent, "codex")
        self.assertEqual((code, self.own()), (0, "human"), err)

    def test_a_claude_code_shell_without_sd_author_says_claude(self) -> None:
        """Claude Code sets `CLAUDECODE=1` and not `SD_AUTHOR`; its repair was `human` (sd:2689)."""
        silent = self.commit("feat: something")
        code, _, err = self.run_as(None, "attribute", silent, "codex", marker="1")
        self.assertEqual((code, self.own()), (0, "claude/anthropic"), err)

    def test_the_marker_needs_the_registry_to_give_claude_its_vendor(self) -> None:
        """An entry name is the operator's: a `claude` of another vendor is not Claude Code's."""
        seeded = self.home / sd_registry.REGISTRY_RELATIVE
        seeded.write_text(seeded.read_text(encoding="utf-8").replace(
            "vendor: anthropic", "vendor: openai"), encoding="utf-8")
        silent = self.commit("feat: something")
        code, _, err = self.run_as(None, "attribute", silent, "codex", marker="1")
        self.assertEqual((code, self.own()), (0, "human"), err)

    def test_an_explicit_sd_author_outranks_the_marker(self) -> None:
        silent = self.commit("feat: something")
        code, _, err = self.run_as("codex", "attribute", silent, "claude", marker="1")
        self.assertEqual((code, self.own()), (0, "codex/openai"), err)

    def test_a_marker_with_another_value_is_no_marker(self) -> None:
        silent = self.commit("feat: something")
        code, _, err = self.run_as(None, "attribute", silent, "codex", marker="0")
        self.assertEqual((code, self.own()), (0, "human"), err)

    def test_sd_author_may_name_the_value_itself(self) -> None:
        silent = self.commit("feat: something")
        code, _, err = self.run_as("claude/anthropic", "attribute", silent, "codex")
        self.assertEqual((code, self.own()), (0, "claude/anthropic"), err)

    def test_an_sd_author_nothing_resolves_writes_nothing(self) -> None:
        silent = self.commit("feat: something")
        before = self.git("rev-parse", "HEAD")
        code, _, err = self.run_as("nosuch", "attribute", silent, "claude")
        self.assertEqual(code, 1)
        self.assertIn("SD_AUTHOR='nosuch'", err)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)

class TheContentGateTests(AttributeFixture):
    """The gate runs on content, and the attributing commit has none.

    `hooks/pre-commit` runs two whole-tree test passes on every commit. On the
    empty commit `attribute` makes there is nothing for them to read, and on a
    loaded machine they spend the whole `GIT_TIMEOUT_SECONDS` bound and lose
    the attribution to `subprocess.TimeoutExpired`. Reproduced on 2026-09-20 in
    a fresh worktree, which is where every agent in this repository works.

    The hook installed below is that hook's shape and not that hook: it reads
    the same variable, and it records that it ran and then sleeps past the
    bound, so a gate that runs on nothing is a failure and not a slow pass.
    """

    def install_hook(self, sleep_seconds: float) -> pathlib.Path:
        """A pre-commit hook that marks the run, sleeps, and honours the skip."""
        marker = self.root / "hook-ran"
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        hook = hooks / "pre-commit"
        hook.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, time\n"
            f"if os.environ.get({sd_lib.SKIP_HOOKS_VARIABLE!r}) == '1':\n"
            "    raise SystemExit(0)\n"
            f"pathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
            f"time.sleep({sleep_seconds!r})\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        return marker

    def test_a_slow_gate_does_not_cost_the_attribution(self) -> None:
        silent = self.commit("feat: something")
        marker = self.install_hook(sd_lib.GIT_TIMEOUT_SECONDS + 5)
        sha, value, covered = sd_lib.attribute(
            self.root, silent, "claude", registry(claude="anthropic"))
        self.assertEqual(covered, [silent])
        self.assertEqual(value, "claude/anthropic")
        self.assertFalse(
            marker.exists(),
            "a content gate ran on a commit that carries no content",
        )
        self.assertEqual(self.said()[silent], "claude/anthropic")
        self.assertEqual(self.said()[sha], sd_lib.HUMAN_AUTHOR)

    def test_a_staged_index_still_goes_through_the_gate(self) -> None:
        """Staged content rides into this commit, so the gate that reads it runs."""
        silent = self.commit("feat: something")
        marker = self.install_hook(0)
        (self.root / "staged.py").write_text("y = 1\n", encoding="utf-8")
        self.git("add", "staged.py")
        sd_lib.attribute(self.root, silent, "claude", registry(claude="anthropic"))
        self.assertTrue(
            marker.exists(),
            "staged content went in without the gate that reads content",
        )


#: What GitHub records on a Dependabot commit, read off pack PR #1257 on
#: 2026-09-29: the bot as author, GitHub's web-flow identity as committer.
DEPENDABOT = ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com")
WEB_FLOW = ("GitHub", "noreply@github.com")


class TheDependabotTests(AttributeFixture):
    """sd:2065: a Dependabot commit says who wrote it by GitHub's identity pair.

    Dependabot writes no trailer, and a person cannot add one without
    rewriting the commit. Each case below goes through the reader, and each
    near miss -- a spoofed name, a local rebase -- must stay silent.
    """

    def bot_commit(self, message: str = "build(deps): bump fixture from 1 to 2",
                   author: tuple[str, str] = DEPENDABOT,
                   committer: tuple[str, str] = WEB_FLOW) -> str:
        target = self.root / f"bump{len(list(self.root.iterdir()))}.txt"
        target.write_text("fixture==2\n", encoding="utf-8")
        self.git("add", "-A")
        subprocess.run(
            ["git", "commit", "--quiet", "-m", message], cwd=str(self.root), check=True,
            capture_output=True, text=True,
            env={**os.environ,
                 "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
                 "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1]},
        )
        return self.git("rev-parse", "HEAD")

    def test_a_dependabot_commit_reads_as_dependabot_without_a_trailer(self) -> None:
        bump = self.bot_commit()
        self.assertEqual(self.said()[bump], sd_lib.DEPENDABOT_AUTHOR)
        self.assertEqual(self.vendors(), ("github",))

    def test_a_trailer_in_a_dependabot_commit_still_outranks_the_identity(self) -> None:
        bump = self.bot_commit("build(deps): bump\n\nAuthored-with: codex/openai")
        self.assertEqual(self.said()[bump], "codex/openai")

    def test_the_bot_name_with_another_email_is_not_dependabot(self) -> None:
        """`git commit --author` sets a name in one flag; the pair is the claim."""
        self.bot_commit(author=("dependabot[bot]", "fixture@example.invalid"))
        with self.assertRaises(sd_lib.TrailerError):
            self.vendors()

    def test_a_dependabot_commit_rebased_locally_is_not_dependabot(self) -> None:
        """A local rewrite keeps the author and names this machine as committer.

        What the commit holds is then somebody's rewrite, which may carry
        their changes; it says nothing until they say who they are.
        """
        self.bot_commit(committer=("Fixture", "fixture@example.invalid"))
        with self.assertRaises(sd_lib.TrailerError):
            self.vendors()

    def test_a_mailmap_on_the_branch_does_not_make_anybody_dependabot(self) -> None:
        """`.mailmap` is a file under review; the raw fields ignore it."""
        (self.root / ".mailmap").write_text(
            f"{DEPENDABOT[0]} <{DEPENDABOT[1]}> Fixture <fixture@example.invalid>\n"
            f"{WEB_FLOW[0]} <{WEB_FLOW[1]}> Fixture <committer@example.invalid>\n",
            encoding="utf-8")
        self.bot_commit("chore: map myself", author=("Fixture", "fixture@example.invalid"),
                        committer=("Fixture", "committer@example.invalid"))
        self.git("config", "log.mailmap", "true")
        with self.assertRaises(sd_lib.TrailerError):
            self.vendors()

    def test_a_human_fix_up_on_a_dependabot_branch_still_needs_its_trailer(self) -> None:
        bump = self.bot_commit()
        fix = self.commit("fix: pin the lockfile")
        with self.assertRaises(sd_lib.TrailerError) as caught:
            self.vendors()
        self.assertIn(fix[:12], str(caught.exception))
        self.assertNotIn(bump[:12], str(caught.exception))
        _, _, covered = sd_lib.attribute(
            self.root, f"{self.base}..HEAD", "claude", registry(claude="anthropic"))
        self.assertEqual(covered, [fix], "the Dependabot commit already says")
        self.assertEqual(sorted(self.vendors()), ["anthropic", "github"])

    def test_a_dependabot_commit_is_not_attributed_over(self) -> None:
        bump = self.bot_commit()
        with self.assertRaises(sd_lib.TrailerError) as caught:
            sd_lib.attribute(self.root, bump, "claude", registry(claude="anthropic"))
        self.assertIn("outranks", str(caught.exception))

    def test_sd_attribute_names_dependabot_for_a_rewritten_bump(self) -> None:
        """The operator's word after a local rebase, the way `human` is theirs."""
        rebased = self.bot_commit(committer=("Fixture", "fixture@example.invalid"))
        _, value, covered = sd_lib.attribute(
            self.root, rebased, "dependabot", registry(claude="anthropic"))
        self.assertEqual((value, covered), (sd_lib.DEPENDABOT_AUTHOR, [rebased]))
        self.assertEqual(self.said()[rebased], sd_lib.DEPENDABOT_AUTHOR)

    def test_a_registry_entry_may_not_be_called_dependabot(self) -> None:
        silent = self.commit("feat: something")
        with self.assertRaises(sd_lib.TrailerError) as caught:
            sd_lib.attribute(self.root, silent, "dependabot", registry(dependabot="anthropic"))
        self.assertIn("hide its vendor", str(caught.exception))

    def test_the_squash_body_check_knows_the_value(self) -> None:
        import sd_ship_body  # noqa: PLC0415 - one test reads the body side
        self.assertTrue(sd_ship_body.known_author(sd_lib.DEPENDABOT_AUTHOR, []))
        self.assertFalse(sd_ship_body.known_author("dependabot/anthropic", []))


if __name__ == "__main__":
    unittest.main()
