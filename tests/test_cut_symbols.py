"""Criterion 31 of sd:10: the symbols requirement 13 cuts are gone, by grep.

One test per symbol, each a `git grep` over the governed tree -- what runs or
governs, criterion 4's list -- rather than a list of the files the cut was
known to touch. A hand-kept file list proves the cut reached those files; the
grep proves it reached every file, including the one nobody thought carried
the name.

31(a) is `sd_sweep`, the age sweep cut under criterion 21. 31(b1), the
prose symbols and flags, is `ProseSymbolsAndFlags` below: one grep per
symbol, and a bounded set of the symbols the lane could not cut because the
code behind them is live and load-bearing. 31(b2), the `authors` policy key,
is cut and its symbol is in `PROSE_SYMBOLS` with the rest; 31(c), the bug
regressions, lands in its own pull request and adds its symbols here.

31(b2)'s key was declared in four places and read by none. Its schema said a
CI lane hard-failed the logins it listed; no workflow, no action under
`actions/` and no code in `bin/` ever read the list, and `setup-github`'s own
line said as much -- "(none listed; rule 5 hard-fails for nobody)". It is a
`RETIRED_POLICY_KEYS` row now, so a repository whose `.github/sd-review.json`
still carries it is refused by name with a remedy rather than by "unknown
key". The grep is bounded to let that row and the assertion proving it name
the key; `TheAuthorsBoundStillFindsAKey` is the control on the bound.

31(a) also names `parked` and `archived`, scoped to the `sd_lib` item field
and its readers. That cut is deferred to a later lane (team-lead decision
2026-09-16, reversible by the owner): every reader is in `bin/sd-status`,
which sd:431 slice D edits next, and a second writer on that file would
collide. Until that lane, `ParkedAndArchivedReaders` freezes the reader set
by file and text so it cannot grow while the cut waits.

Two things the tree carries by name and this file leaves alone. `docs/work/`
and `CHANGELOG.md` are history, excluded by the criterion's own definition of
the governed tree. `tests/fixtures/*-round.json` are captured review rounds --
`tests/test_sd_review_ack.py` says of the first one, "not an invented
fixture", twelve pull requests read from the GitHub API "as they stand" -- and
a Copilot body in one of them summarises a change to `bin/sd_sweep.py`.
Editing a capture to satisfy a grep would falsify the record the capture is
kept for, so the captures are excluded here by name, as history, and the
exclusion is stated rather than buried in a pattern.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "bin") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "bin"))

import sd_lib  # noqa: E402
import sd_rules  # noqa: E402

#: What runs or governs. `docs/work/` and `CHANGELOG.md` are history.
GOVERNED = (
    "bin",
    "skills",
    "agents",
    "tests",
    ".claude",
    ".github",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "docs/spec",
)

#: Excluded from every grep below. This file quotes each symbol it searches
#: for, and the review captures are history, see the module docstring.
EXCLUDED = ("tests/test_cut_symbols.py", "tests/fixtures/*-round.json")


def governed_grep(pattern: str) -> list[str]:
    """`git grep` over the governed tree, returning `path:line:text` rows.

    The pattern follows `-e`, so a pattern that starts with a dash -- the
    flags of 31(b1) -- is a pattern and not an option `git grep` refuses."""
    result = subprocess.run(
        ["git", "grep", "-nIE", "-e", pattern, "--", *GOVERNED,
         *(f":(exclude){path}" for path in EXCLUDED)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line]


def _matches(pattern: str, line: str) -> bool:
    r"""One line against a `git grep -E` pattern, for bound controls.

    `[:space:]` is POSIX and `re` does not know it, so it is translated
    rather than the pattern being written twice in two dialects. The one
    replacement covers both shapes the pattern uses it in: `[[:space:]]*`
    becomes `[\s]*`, and the negated `[^"[:space:]]` becomes `[^"\s]`.
    """
    return re.search(pattern.replace("[:space:]", r"\s"), line) is not None


class TheGrepMeasuresSomething(unittest.TestCase):
    """The control: a grep that could not find a name that is there proves
    nothing about a name that is not."""

    def test_a_symbol_the_tree_does_carry_is_found(self) -> None:
        rows = governed_grep(r"def work_items\(")
        self.assertTrue(rows, "the governed grep found nothing for work_items")


class SweepCut(unittest.TestCase):
    """31(a): `sd_sweep`, the 45-day age sweep, cut under criterion 21."""

    def test_no_governed_file_names_sd_sweep(self) -> None:
        rows = governed_grep(r"sd_sweep")
        self.assertEqual(rows, [], "sd_sweep is still named: " + "; ".join(rows))

    def test_the_module_and_its_suite_are_gone(self) -> None:
        for path in ("bin/sd_sweep.py", "tests/test_sd_sweep.py"):
            self.assertFalse((REPO_ROOT / path).exists(), f"{path} still exists")

    def test_sd_has_no_sweep_verb(self) -> None:
        """The verb, not only the module: a `sweep` group left registered
        against some other handler would still be a sweep code path."""
        sd = sd_lib.sibling("sd_under_cut_symbols", "sd")
        parser = sd.build_parser()
        groups = [action for action in parser._actions
                  if hasattr(action, "choices") and action.choices]
        self.assertEqual(len(groups), 1, "expected one group of top-level verbs")
        verbs = set(groups[0].choices)
        self.assertIn("store", verbs, "the verb enumeration missed a verb that exists")
        self.assertNotIn("sweep", verbs)

    def test_the_aging_basis_survived_the_cut_in_the_library(self) -> None:
        """The aging basis now lives in `sd_lib`: the threshold, the two
        functions `sd-status`'s `idle-planning` read off the sweep, and the
        sweep's own date parser (`sd-status` keeps its local `_item_date`).
        The cut removed a verb, not the one definition of idle."""
        self.assertEqual(sd_lib.DEFAULT_DAYS, 45)
        for name in ("item_date", "last_active", "touched"):
            self.assertTrue(callable(getattr(sd_lib, name, None)), f"sd_lib.{name} is missing")


#: The pack dashboard, cut at sd:719 step 7, and what went before it. The
#: package `dashboard/` and its CLI `bin/sd-dashboard` left the tree in one
#: commit with the ceilings on them; the tracker index and its clients went at
#: step 4, and their test modules with them. Directories are pathspecs here,
#: so a file restored anywhere under `dashboard/` surfaces, not only one the
#: list happens to name. Asserted from the index and the filesystem, never
#: from a string the author already knew: a file restored on its own is red.
RETIRED_DASHBOARD = (
    "dashboard",
    "bin/sd-dashboard",
    "bin/sd-trackers",
    "tests/test_sd_dashboard.py",
    "tests/test_sd_trackers.py",
    "tests/test_sd_dashboard_index.py",
    "tests/test_dashboard_sessions.py",
    "tests/test_dashboard_skills.py",
    "tests/test_dashboard_now.py",
    "tests/test_dashboard_work.py",
    "tests/test_dashboard_deliver.py",
    "tests/test_dashboard_actions.py",
)


class DashboardCut(unittest.TestCase):
    """sd:719 step 7: `dashboard/` and `bin/sd-dashboard` are not in the tree.

    The census `tests/test_sd_dashboard.py` kept until step 7 asserted each
    retired module by name while the package still stood; with the package
    gone the pathspec is the directory, and the CLI and the test modules are
    listed beside it. An importer of the package needs no row here: mypy over
    `bin/` reports `import-not-found` for a module that is not there, and a
    test module importing it fails at collection.
    """

    def test_the_dashboard_and_its_cli_are_not_in_the_tree(self) -> None:
        listed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--deduplicate", "--", *RETIRED_DASHBOARD],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual(listed, [], f"still tracked: {listed}")
        present = [path for path in RETIRED_DASHBOARD if (REPO_ROOT / path).exists()]
        self.assertEqual(present, [], f"still on disk: {present}")


#: Every site under `bin` that reads the `archived` field, as `path` and the
#: line's text. `bin/sd_lib.py` builds the item; everything else is
#: `bin/sd-status`, where three filters ask whether an item is live.
#:
#: The set used to freeze `parked` too and carried thirteen rows. 31(a) cut
#: the `parked` half on 2026-09-19 -- the field, the `--parked` flag, the
#: parked section and every read -- leaving six. Two of the six are the same
#: filters with the `or entry["parked"]` clause removed, so their text
#: changed; the other eleven rows went. The dashboard row that read the
#: archived count left the set when sd:719 step 6 retired the client script,
#: and the grep stopped naming the directory when step 7 deleted it.
#:
#: `archived` is kept, and this set is its ceiling: a reader added anywhere
#: under `bin` is a row this set does not carry, and the test below fails it.
FROZEN_FIELD_READERS = frozenset({
    ("bin/sd_lib.py", "archived=report.archived,"),
    ("bin/sd-status", '"archived": item.archived,'),
    ("bin/sd-status", 'active = [entry for entry in listed if not entry["archived"]]'),
    ("bin/sd-status", 'if entry["archived"]:'),
    ("bin/sd-status", 'if entry["archived"] or entry["status"] == "done":'),
    ("bin/sd-status", 'live = [entry for entry in work["items"] if not entry["archived"]]'),
})

#: An attribute or key read of either field. `git grep -E` on this platform
#: has no `\b`, so the attribute form is bounded by hand. `parked` stays in
#: the pattern after its cut: the pattern is what proves the cut held, and a
#: read of the gone field anywhere under `bin` must fail rather than pass
#: silently because the grep stopped looking for it.
FIELD_READ = r'\.(parked|archived)([^A-Za-z_]|$)|\["(parked|archived)"\]'


def field_readers() -> list[tuple[str, str]]:
    """The `(path, text)` of every field read under `bin`."""
    result = subprocess.run(
        ["git", "grep", "-nIE", FIELD_READ, "--", "bin"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(result.stderr.strip())
    sites = []
    for line in result.stdout.splitlines():
        path, _, text = line.split(":", 2)
        sites.append((path, text.strip()))
    return sites


class ParkedAndArchivedReaders(unittest.TestCase):
    """31(a)'s two fields: `parked` is cut, `archived` is frozen.

    The split is the owner's call of 2026-09-19. `parked` went because
    nothing wrote it -- the 45-day age sweep that set it was retired under
    criterion 21, and `sd-handoff`'s Lane B `--park` was never built -- and
    because every item carrying the field was also archived, so the
    `archived` half of each filter already excluded it. `archived` stays: it
    is derived from where the item lives, every scan produces it, and the
    three filters are what keep closed work out of an active view.

    The assertion is that the set has not grown, not that the grep is empty,
    the same shape criterion 21 gives the deletion verbs. A reader added
    anywhere under `bin` is a row the set does not carry.
    """

    def test_no_reader_of_the_cut_parked_field_remains(self) -> None:
        """31(a)'s `parked` half, stated as the criterion states a cut.

        The frozen set above would catch a `parked` read as an unexpected
        row, but only as one row among any others, and its message would say
        a reader appeared rather than that the cut came undone. This says it
        directly, and it is the check that goes red first if the field is
        put back.
        """
        back = [site for site in field_readers() if "parked" in site[1]]
        self.assertEqual(back, [], "the cut `parked` field has a reader again")

    def test_the_readers_are_the_frozen_set_and_no_more(self) -> None:
        unexpected = [site for site in field_readers() if site not in FROZEN_FIELD_READERS]
        self.assertEqual(unexpected, [], "a new reader of parked/archived appeared")

    def test_the_grep_reaches_the_sites_it_freezes(self) -> None:
        """The control: a frozen site the grep no longer finds is either cut,
        which is the later lane's row to remove, or reworded past the
        pattern, which would let the check above pass on nothing."""
        found = set(field_readers())
        missing = sorted(FROZEN_FIELD_READERS - found)
        self.assertEqual(missing, [], "frozen reader sites the grep did not reach")


#: 31(b1): the criterion's prose symbols and flags, each as the `git grep -E`
#: pattern its grep runs. Two patterns are wider or narrower than the literal
#: on purpose. `Standing rule` is matched in either case: the rule the phrase
#: cites is defined nowhere, and `standing rule 2` in a comment cites it just
#: as `Standing rule 2` in a docstring does. `--park` is bounded so that it
#: does not match `--parked`; the criterion's `--park` is the Lane B flag of
#: `sd-handoff`, which was never built. 31(a) has since cut `--parked` as
#: well, so the bound now separates the pattern from a flag that is gone
#: rather than from a live one -- which is why the control below keeps
#: asserting it: an unbounded `--park` would match the old spelling wherever
#: history still writes it, and report the wrong flag as uncut.
PROSE_SYMBOLS = (
    ("record_load", r"record_load"),
    ("carrier_branches", r"carrier_branches"),
    ("--stash-ref", r"--stash-ref"),
    ("--push", r"--push"),
    ("--park", r"--park([^a-z]|$)"),
    ("argument-vocabulary", r"argument-vocabulary"),
    ("Standing rule", r"[Ss]tanding rule"),
    ("five gates", r"five gates"),
    ("cron-jobs.sh", r"cron-jobs\.sh"),
    ("Active item:", r"Active item:"),
    ("sd-deps", r"sd-deps"),
    # 31(b2). Bounded away from the one place the key may still be named:
    # its `RETIRED_POLICY_KEYS` row, where the value is a remedy string, so
    # `"authors": "` is the one form that does not match. Every other shape
    # the key took is here -- the mapping entry before a list or an object,
    # the `_STRING_LIST_KEYS` tuple member, and a subscript read.
    # `TheAuthorsBoundStillFindsAKey` is the control on that bound.
    ("authors policy key",
     r'"authors"[^:]|"authors":[[:space:]]*[^"[:space:]]'),
)

#: The 31(b1) symbols that are **kept**, each with the files that may carry
#: it. Both are live functions of `bin/sd-status`'s protection section:
#: `load_acknowledgements` reads the accepted gaps of
#: `.github/sd-status.json`, a tracked record that today holds the
#: `unprotected` acceptance of 2026-09-12, and `_protection_gaps` is what
#: those acceptances are applied to.
#:
#: This was a hold, waiting on the owner to rewrite the section into one
#: `protected: yes/no` line. On 2026-09-19 the owner rescinded that cut and
#: criterion 31 stopped listing the two symbols. The reason is in the item's
#: Log: the accepted gap is not a boolean. It carries a dated reason, what
#: protection was costing, what is genuinely lost, the human standing in for
#: the lost backstop, and an `until` condition. One word says none of it, and
#: this is the one repository whose answer is deliberately "no".
#:
#: Nothing about the enforcement changes -- a keep is bounded exactly as a
#: hold was, which is the point: the symbol may not spread. A file outside
#: its set fails below, and a symbol added here that `HELD_SYMBOLS_BOUND`
#: does not name fails too. What changed is why the rows are here, so a later
#: reader does not go looking for the lane that was going to remove them.
HELD_SYMBOLS = {
    "_protection_gaps": frozenset({"bin/sd-status", "tests/test_sd_status.py"}),
    "load_acknowledgements": frozenset({"bin/sd-status", "tests/test_sd_status.py"}),
}

#: The frozen ceiling on `HELD_SYMBOLS`: it may lose an entry, never gain
#: one, and no entry may gain a file. The ceiling outlives the rescind: a
#: keep that may only shrink is still the check that catches the symbol
#: spreading to a third file.
HELD_SYMBOLS_BOUND = {
    "_protection_gaps": frozenset({"bin/sd-status", "tests/test_sd_status.py"}),
    "load_acknowledgements": frozenset({"bin/sd-status", "tests/test_sd_status.py"}),
}


class ProseSymbolsAndFlags(unittest.TestCase):
    """31(b1): each prose symbol and flag returns nothing from the governed
    grep, and the symbols the lane held are bounded rather than exempted."""

    def test_no_governed_file_names_a_cut_symbol(self) -> None:
        for symbol, pattern in PROSE_SYMBOLS:
            with self.subTest(symbol=symbol):
                rows = governed_grep(pattern)
                self.assertEqual(
                    rows, [],
                    f"{symbol} is still named in {len(rows)} line(s): " + "; ".join(rows),
                )

    def test_the_bounded_pattern_still_finds_the_bare_flag(self) -> None:
        """The control for `--park`: a pattern narrowed past `--parked` must
        still match the flag it is for, or the assertion above is over
        nothing. `--parked` is itself cut now, but `CHANGELOG.md` and the
        archived items still write it, so the bound is still load-bearing."""
        pattern = dict(PROSE_SYMBOLS)["--park"]
        self.assertIsNotNone(re.search(pattern, "the design has `--park`"))
        self.assertIsNotNone(re.search(pattern, "sd-handoff --park"))
        self.assertIsNone(re.search(pattern, "sd-status --parked"))

    def test_a_held_symbol_stays_in_the_files_that_hold_it(self) -> None:
        for symbol, files in HELD_SYMBOLS.items():
            with self.subTest(symbol=symbol):
                found = {row.split(":", 1)[0] for row in governed_grep(symbol)}
                self.assertTrue(found, f"{symbol} is gone: remove its row from HELD_SYMBOLS")
                self.assertLessEqual(found, files, f"{symbol} spread to {sorted(found - files)}")

    def test_the_authors_bound_still_finds_a_key(self) -> None:
        """The control on 31(b2)'s bound: it excludes one shape, not the key.

        The pattern lets `"authors": "` through so the `RETIRED_POLICY_KEYS`
        row and the assertion proving the retirement can name the key they
        retire. A bound that had swallowed the key itself would make the grep
        above pass over a policy file that still declares it, which is the
        failure the whole gate exists to catch.
        """
        pattern = dict(PROSE_SYMBOLS)["authors policy key"]
        live = (
            '    "authors": [],',
            '_STRING_LIST_KEYS = ("docs_skip", "sensitive", "authors")',
            '        "authors": list(policy["authors"]),',
            '    authors = ", ".join(result["authors"])',
            '    "authors": {',
            '  "authors": ["sdelmas"],',
            '        self.assertIn("authors", policy)',
            '    for key in ("authors", "sensitive"):',
        )
        for line in live:
            with self.subTest(line=line):
                self.assertTrue(_matches(pattern, line), "the bound lost a live key shape")
        retired = (
            '    "authors": "nothing ever read it. Delete the key",',
            '        self.assert_rejects({"authors": "x"}, "authors is retired")',
        )
        for line in retired:
            with self.subTest(line=line):
                self.assertFalse(_matches(pattern, line), "the bound caught its own exception")

    def test_the_held_set_is_bounded_and_shrinking(self) -> None:
        self.assertLessEqual(set(HELD_SYMBOLS), set(HELD_SYMBOLS_BOUND))
        for symbol, files in HELD_SYMBOLS.items():
            with self.subTest(symbol=symbol):
                self.assertLessEqual(files, HELD_SYMBOLS_BOUND[symbol])
        held = {symbol for symbol, _ in PROSE_SYMBOLS} & set(HELD_SYMBOLS)
        self.assertEqual(held, set(), "a symbol is both cut and held")


#: The repealed row `R10-D2` of `bin/sd_rules.py` teaches from a section of
#: `skills/sd-handoff/SKILL.md` whose heading carried both Lane B flags. The
#: sweep renames the heading and the row's `teaches` together; leg a of
#: `tests/test_rule_registry.py` reads live rows only, so this is the check
#: that the repealed row still lands on a real section that cites it.
REPEALED_TEACHING = ("R10-D2", "skills/sd-handoff/SKILL.md", "Lane B is not implemented")


class TheRepealedRowStillTeaches(unittest.TestCase):
    def test_r10_d2_teaches_from_a_section_that_cites_it(self) -> None:
        rule_id, path, heading = REPEALED_TEACHING
        rows = [rule for rule in sd_rules.RULES if rule.id == rule_id]
        self.assertEqual(len(rows), 1, f"{rule_id} is not one row")
        self.assertEqual(rows[0].teaches, f"{path}#{heading}")
        lines = (REPO_ROOT / path).read_text(encoding="utf-8").splitlines()
        starts = [i for i, line in enumerate(lines) if line.strip() == f"## {heading}"]
        self.assertEqual(len(starts), 1, f"{path} carries {len(starts)} headings {heading!r}")
        body = []
        for line in lines[starts[0] + 1:]:
            if line.startswith("## "):
                break
            body.append(line)
        self.assertIn(rule_id, "\n".join(body), f"the section {heading!r} does not cite {rule_id}")


#: 31(c)'s one-definition greps: `(what, pattern, the one file that may
#: define it)`.
#:
#: The criterion named four -- the provider list, the git wrapper, the
#: status vocabulary and the ACTIVE set. One is here, and the owner settled
#: the other three on 2026-09-19 (decision note 3006) as not being
#: duplicates at all, so no row is coming for them.
#:
#: The status vocabulary needed no choice. `bin/sd-docs-lint` already
#: imported `sd_lib` and carried a byte-identical copy of the tuple beside
#: the import, so there was nothing to decide and nothing to weigh: the
#: copy became the import it was sitting next to.
#:
#: The git wrapper is not a name to grep for. The second wrapper this rule
#: looked for was a name-only forwarder, and the real defect was a `git`
#: call with no timeout at seven sites no name-grep reached.
#: `tests/test_git_policy.py` holds that policy with an AST walk of `bin/`
#: instead, and records every exception by path and reason.
#:
#: The provider list and the ACTIVE set are several on purpose. Three
#: active-status sets answer three questions -- display order, planning
#: eligibility, the row vocabulary -- and `providers.yaml` carries provider
#: identity while the `provider` rows carry state. Collapsing either pair
#: would lose a distinction, not a duplicate. The item's `prd.md` Log for
#: that date is the record.
ONE_DEFINITION = (
    (
        "the status vocabulary",
        r'\("planning", *"ready", *"in_progress", *"done"\)',
        "bin/sd_lib.py",
    ),
)


class OneDefinitionEach(unittest.TestCase):
    """31(c): a grep of the governed tree finds no second definition.

    Two tests, because one of them alone proves nothing. The first fails
    when a second definition appears; the second fails when the pattern
    stops reaching the first, which is how a gate quietly becomes a gate
    over an empty set.
    """

    def test_each_name_has_exactly_one_definition(self) -> None:
        for what, pattern, owner in ONE_DEFINITION:
            with self.subTest(what=what):
                found = sorted({row.split(":", 1)[0] for row in governed_grep(pattern)})
                self.assertEqual(
                    found, [owner],
                    f"{what} is defined in {len(found)} file(s), not only {owner}",
                )

    def test_the_grep_reaches_the_definition_it_names(self) -> None:
        for what, pattern, owner in ONE_DEFINITION:
            with self.subTest(what=what):
                rows = [row for row in governed_grep(pattern)
                        if row.startswith(f"{owner}:")]
                self.assertEqual(
                    len(rows), 1,
                    f"the {what} pattern matches {len(rows)} line(s) of {owner}",
                )

    def test_the_status_vocabulary_pattern_matches_the_live_tuple(self) -> None:
        """The pattern is tied to the value, not to a remembered spelling.

        Without this, reordering `ITEM_STATUSES` would leave a pattern that
        matches nothing, and a grep that finds one definition and a grep
        that finds none both read as a pass on the first test above.
        """
        _, pattern, owner = ONE_DEFINITION[0]
        live = "(" + ", ".join(f'"{status}"' for status in sd_lib.ITEM_STATUSES) + ")"
        self.assertTrue(
            _matches(pattern, f"ITEM_STATUSES = {live}"),
            f"the pattern no longer matches sd_lib.ITEM_STATUSES == {live}",
        )
        self.assertIn(
            f"ITEM_STATUSES = {live}",
            (REPO_ROOT / owner).read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
