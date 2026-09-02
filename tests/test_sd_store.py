"""`sd store`: the vault is the source, and it is read at the moment of asking.

The load-bearing case is `FreshnessTests.test_a_note_written_directly_into_the
_vault_is_visible_to_the_next_query`. It is step 8's own acceptance criterion,
and it is written as a *direct* write on purpose: the note is created by this
test with `write_text`, never by `sd`, and then a query has to see it. Anything
that caches -- an index consulted instead of the vault, a manifest snapshot, a
directory listing held between invocations -- fails it.

That is the property the replaced stack could not offer and the reason R5-D1
keeps the vault as system-of-record with SQLite demoted to an index. A test
that wrote through `sd` and read back through `sd` would pass against a
purely in-memory store and prove nothing about the vault at all.

Every case runs `bin/sd` as a subprocess with `XDG_CONFIG_HOME` and
`OBSIDIAN_VAULT` pointed into a temporary directory, so neither the
developer's machine config nor the developer's vault is ever touched.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import itertools
import json
import os
import pathlib
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

try:                          # a probe, not a dependency; see the test that uses it
    import yaml
except ImportError:           # pragma: no cover - depends on the developer's venv
    yaml = None               # type: ignore[assignment]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = REPO_ROOT / "bin" / "sd"

_SD_MODULE = None


def sd_module():
    """`bin/sd` imported as a module, for the one case that cannot afford a subprocess.

    Every other case in this file runs the real command, which is the point of
    them. The brute-force check renders tens of thousands of values, and a
    subprocess each would make it minutes rather than seconds.
    """

    global _SD_MODULE
    if _SD_MODULE is None:
        loader = importlib.machinery.SourceFileLoader("sd_under_test", str(SD))
        spec = importlib.util.spec_from_file_location("sd_under_test", str(SD), loader=loader)
        assert spec is not None
        _SD_MODULE = importlib.util.module_from_spec(spec)
        loader.exec_module(_SD_MODULE)
    return _SD_MODULE


TIP_KIND: dict[str, object] = {
    "fields": ["status", "score"],
    "initial-status": "inbox",
    "transitions": {"inbox": ["approved", "declined"]},
}

# The shape the `store` block takes, in one place, so a case can break exactly
# one part of it.
STORE: dict[str, object] = {
    "driver": "vault",
    "root": "$OBSIDIAN_VAULT",
    "bases": {"tip": "System/Databases/Tips"},
}


class StoreFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name).resolve()
        self.config_home = self.tmp / "config"
        self.vault = self.tmp / "vault"
        self.tips = self.vault / "System" / "Databases" / "Tips"
        self.tips.mkdir(parents=True)

    def run_sd(self, *args: str, vault: str | None = "") -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.tmp / "home"),
            "XDG_CONFIG_HOME": str(self.config_home),
        }
        # `vault=None` is "the knob is unset", which is a case with its own
        # test; the default is the fixture's own vault.
        if vault is not None:
            env["OBSIDIAN_VAULT"] = vault or str(self.vault)
        return subprocess.run(
            [sys.executable, str(SD), *args], capture_output=True, text=True, env=env)

    def plugin(self, *, kinds: object = None, store: object = STORE,
               register: bool = True) -> pathlib.Path:
        """A registered plugin that keeps `tip` notes in the fixture's vault."""

        root = self.tmp / "pack"
        root.mkdir(parents=True, exist_ok=True)
        body: dict[str, object] = {"prefix": "pp", "interface": 1}
        body["kinds"] = {"tip": dict(TIP_KIND)} if kinds is None else kinds
        if store is not None:
            body["store"] = store
        (root / "sd-plugin.json").write_text(json.dumps(body), encoding="utf-8")
        if register:
            done = self.run_sd("plugin", "add", str(root))
            self.assertEqual(done.returncode, 0, done.stderr)
        return root

    def note(self, title: str, *, status: str = "inbox", score: str = "7",
             body: str = "The body.\n", extra: str = "") -> pathlib.Path:
        path = self.tips / f"{title}.md"
        path.write_text(
            f"---\nstatus: {status}\nscore: {score}\n{extra}---\n\n{body}", encoding="utf-8")
        return path


class FreshnessTests(StoreFixture):
    def test_a_note_written_directly_into_the_vault_is_visible_to_the_next_query(self) -> None:
        """Step 8's acceptance criterion, written as a direct write.

        Three reads, none of them preceded by a write through `sd`: an empty
        vault reports empty, a note dropped in by hand is listed, and an edit
        made in place is reflected. A cache anywhere in the path fails the
        second or the third.
        """

        self.plugin()
        first = self.run_sd("store", "list", "pp.tip", "--json")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout), [])

        self.note("Ship it", score="7")
        second = self.run_sd("store", "list", "pp.tip", "--json")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            json.loads(second.stdout),
            [{"title": "Ship it", "status": "inbox", "score": "7"}])

        self.note("Ship it", status="approved", score="9")
        third = self.run_sd("store", "get", "pp.tip", "Ship it", "--json")
        self.assertEqual(third.returncode, 0, third.stderr)
        payload = json.loads(third.stdout)
        self.assertEqual(payload["fields"]["status"], "approved")
        self.assertEqual(payload["fields"]["score"], "9")

    def test_a_manifest_edit_reaches_the_store_without_re_registering(self) -> None:
        """The registry holds a path, so the base is read from disk every time."""

        root = self.plugin()
        self.note("Ship it")
        moved = self.vault / "System" / "Databases" / "Elsewhere"
        moved.mkdir(parents=True)
        (moved / "Moved.md").write_text("---\nstatus: inbox\nscore: 8\n---\n\nx\n",
                                        encoding="utf-8")
        manifest = json.loads((root / "sd-plugin.json").read_text(encoding="utf-8"))
        manifest["store"]["bases"]["tip"] = "System/Databases/Elsewhere"
        (root / "sd-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        listed = self.run_sd("store", "list", "pp.tip", "--json")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual([row["title"] for row in json.loads(listed.stdout)], ["Moved"])


class ReadTests(StoreFixture):
    def test_get_reports_a_field_the_manifest_never_declared(self) -> None:
        """`interface = 1` promises fields and the whole body, not the declared subset.

        A note that grew a field ahead of its manifest is the case a caller
        most needs to see; filtering to `kinds.tip.fields` would hide it while
        looking complete.
        """

        self.plugin()
        self.note("Ship it", extra="my-rating: 4\n", body="# Ship it\n\nProse.\n")
        done = self.run_sd("store", "get", "pp.tip", "Ship it", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual(payload["fields"]["my-rating"], "4")
        self.assertIn("Prose.", payload["body"])

    def test_the_body_is_everything_after_the_frontmatter(self) -> None:
        self.plugin()
        self.note("Ship it", body="one\n---\ntwo\n")
        done = self.run_sd("store", "get", "pp.tip", "Ship it", "--json")
        self.assertEqual(json.loads(done.stdout)["body"], "\none\n---\ntwo\n")

    def test_a_note_whose_first_line_is_a_rule_keeps_its_whole_body(self) -> None:
        """An unterminated `---` block is not frontmatter, so nothing is dropped."""

        self.plugin()
        (self.tips / "Rule.md").write_text("---\nnot closed\n", encoding="utf-8")
        done = self.run_sd("store", "get", "pp.tip", "Rule", "--json")
        self.assertEqual(json.loads(done.stdout)["body"], "---\nnot closed\n")

    def test_status_selects_and_reports_a_count(self) -> None:
        self.plugin()
        self.note("Kept", status="inbox")
        self.note("Gone", status="declined")
        done = self.run_sd("store", "list", "pp.tip", "--status", "inbox")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "inbox\t7\tKept\n")
        self.assertIn("# 1 note(s)", done.stderr)

    def test_the_column_order_is_the_manifest_order_not_alphabetical(self) -> None:
        """The plugin says which field matters most; sorting would overrule it.

        `fields` is declared `status, score`, and alphabetical is the reverse.
        `pack.py` printed status first for three databases and no other key in
        the vocabulary carries this information, so registration keeps the
        order it was given.
        """

        self.plugin()
        self.note("Ship it", status="approved", score="9")
        done = self.run_sd("store", "list", "pp.tip")
        self.assertEqual(done.stdout, "approved\t9\tShip it\n")

    def test_a_field_the_note_does_not_carry_prints_as_a_question_mark(self) -> None:
        """Empty and absent are the same answer here, and it is not a blank column."""

        self.plugin()
        (self.tips / "Bare.md").write_text("---\nstatus: inbox\n---\n\nx\n", encoding="utf-8")
        done = self.run_sd("store", "list", "pp.tip")
        self.assertEqual(done.stdout, "inbox\t?\tBare\n")

    def test_status_on_a_kind_without_one_refuses_instead_of_matching_nothing(self) -> None:
        """The vacuous-filter case: silence would read as "none in that status"."""

        self.plugin(kinds={"tip": {"fields": ["score"], "initial-status": "inbox"}})
        self.note("Ship it")
        done = self.run_sd("store", "list", "pp.tip", "--status", "inbox")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("declares no `status` field", done.stderr)

    def test_a_missing_note_and_a_missing_base_refuse_differently(self) -> None:
        self.plugin()
        absent = self.run_sd("store", "get", "pp.tip", "Nothing")
        self.assertEqual(absent.returncode, 1, absent.stdout)
        self.assertIn("no note titled", absent.stderr)
        for child in self.tips.iterdir():
            child.unlink()
        self.tips.rmdir()
        gone = self.run_sd("store", "list", "pp.tip")
        self.assertEqual(gone.returncode, 1, gone.stdout)
        self.assertIn("does not exist", gone.stderr)

    def test_one_strange_entry_does_not_take_out_the_whole_listing(self) -> None:
        """A directory and a dangling link both end in `.md` and are not notes.

        Without the `is_file()` filter the directory raises `IsADirectoryError`
        on read and refuses the entire query, so one odd entry in a vault makes
        every note of that kind unreachable. Found in review.
        """

        self.plugin()
        self.note("Real")
        (self.tips / "Folder.md").mkdir()
        (self.tips / "Dangling.md").symlink_to(self.tmp / "absent.md")
        done = self.run_sd("store", "list", "pp.tip", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([row["title"] for row in json.loads(done.stdout)], ["Real"])

    def test_a_symlink_to_a_real_note_is_read(self) -> None:
        """Declined half of a review finding, pinned so the decision is visible.

        The vault is the user's own data and its owner is the manifest's
        author; refusing a symlinked note would reject a legitimate layout to
        guard a boundary that does not exist here. `digest()` refuses symlinks
        for a different job -- a lock must pin content that is where it says.
        """

        self.plugin()
        elsewhere = self.tmp / "elsewhere.md"
        elsewhere.write_text("---\nstatus: inbox\nscore: 3\n---\n\nLinked.\n",
                             encoding="utf-8")
        (self.tips / "Linked.md").symlink_to(elsewhere)
        done = self.run_sd("store", "get", "pp.tip", "Linked", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Linked.", json.loads(done.stdout)["body"])

    def test_a_title_holding_a_path_separator_is_a_usage_error(self) -> None:
        self.plugin()
        for title in ("../secret", "a/b", ".."):
            with self.subTest(title=title):
                done = self.run_sd("store", "get", "pp.tip", title)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("is not a note title", done.stderr)


class ResolutionTests(StoreFixture):
    def test_an_unset_knob_names_the_knob(self) -> None:
        self.plugin()
        done = self.run_sd("store", "list", "pp.tip", vault=None)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("OBSIDIAN_VAULT is not set", done.stderr)

    def test_a_vault_that_is_not_there_says_so_rather_than_reporting_empty(self) -> None:
        self.plugin()
        done = self.run_sd("store", "list", "pp.tip", vault=str(self.tmp / "absent"))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("vault path does not exist", done.stderr)

    @unittest.skipIf(os.geteuid() == 0, "root reads a directory with no permissions")
    def test_an_unreadable_vault_says_permission_denied_and_not_macos(self) -> None:
        """Each probe answer gets its own sentence, and only one mentions macOS.

        Found in review. The first draft folded the timeout and the denial
        together, so a directory with the read bit off reported "on macOS this
        is Documents access" and sent somebody to System Settings for a
        `chmod`. **A hang is the TCC signature; a refusal is not.**
        """

        self.plugin()
        closed = self.tmp / "closed"
        closed.mkdir()
        closed.chmod(0o000)
        self.addCleanup(closed.chmod, 0o755)
        done = self.run_sd("store", "list", "pp.tip", vault=str(closed))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("permission denied", done.stderr)
        self.assertNotIn("Full Disk Access", done.stderr)

    def test_a_vault_that_is_a_file_says_so(self) -> None:
        self.plugin()
        flat = self.tmp / "flat"
        flat.write_text("not a vault\n", encoding="utf-8")
        done = self.run_sd("store", "list", "pp.tip", vault=str(flat))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("is not a directory", done.stderr)

    def test_a_relative_vault_root_refuses(self) -> None:
        """The same command must not answer differently from two directories."""

        self.plugin()
        done = self.run_sd("store", "list", "pp.tip", vault="vault")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("must be an absolute path", done.stderr)

    def test_an_unknown_prefix_and_an_unknown_kind_refuse_differently(self) -> None:
        self.plugin()
        for reference, expected in (("zz.tip", "no registered plugin has prefix"),
                                    ("pp.absent", "declares no kind")):
            with self.subTest(reference=reference):
                done = self.run_sd("store", "list", reference)
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn(expected, done.stderr)

    def test_a_reference_that_is_not_prefix_dot_kind_is_a_usage_error(self) -> None:
        self.plugin()
        for reference in ("tip", "pp.tip.extra"):
            with self.subTest(reference=reference):
                done = self.run_sd("store", "list", reference)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("<prefix>.<kind>", done.stderr)

    def test_a_plugin_with_kinds_and_no_store_refuses_at_use_time(self) -> None:
        """Absent stays absent: `sys` declares no `store` and registers fine."""

        self.plugin(store=None)
        done = self.run_sd("store", "list", "pp.tip")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("declares no `store`", done.stderr)


class ManifestTests(StoreFixture):
    def refused(self, store: object, *, kinds: object = None) -> str:
        root = self.plugin(store=store, kinds=kinds, register=False)
        done = self.run_sd("plugin", "add", str(root))
        self.assertEqual(done.returncode, 1, done.stdout)
        return done.stderr

    def test_a_root_that_is_a_literal_path_refuses(self) -> None:
        """The `pack.py:146` defect, refused where it would be committed.

        A vault path written into a manifest is portable to one machine, and
        the manifest is the file most likely to be copied to another.
        """

        for root in ("/Users/someone/Documents/Vault", "~/Documents/Vault", "$lowercase"):
            with self.subTest(root=root):
                self.assertIn(
                    "environment variable reference",
                    self.refused({**STORE, "root": root}))

    def test_an_unknown_driver_refuses_by_name(self) -> None:
        self.assertIn("the driver(s) are vault", self.refused({**STORE, "driver": "vualt"}))

    def test_every_key_of_the_block_is_required(self) -> None:
        for key in sorted(STORE):
            with self.subTest(key=key):
                self.assertIn(
                    f"declares no {key!r}",
                    self.refused({k: v for k, v in STORE.items() if k != key}))

    def test_an_unknown_key_refuses(self) -> None:
        self.assertIn("unknown key(s): cache", self.refused({**STORE, "cache": True}))

    def test_coverage_is_checked_in_both_directions(self) -> None:
        """A base with no kind is dead; a kind with no base is a store verb that cannot run."""

        self.assertIn(
            "'topic', which is not a declared kind",
            self.refused({**STORE, "bases": {"tip": "a", "topic": "b"}}))
        self.assertIn(
            "kind 'topic' has no `store.bases` entry",
            self.refused(
                STORE,
                kinds={"tip": dict(TIP_KIND), "topic": dict(TIP_KIND)}))

    def test_a_base_that_leaves_the_vault_refuses(self) -> None:
        for base in ("/etc", "../../etc", ""):
            with self.subTest(base=base):
                self.refused({**STORE, "bases": {"tip": base}})

    def test_a_windows_style_base_stays_inside_the_vault(self) -> None:
        """Declined half of a review finding, proved rather than argued.

        Review asked for a root-escape guard against Windows-style paths, on
        this pull request and the one before it. On POSIX a backslash is a
        filename character and not a separator, so `..\\..\\etc` names one
        strangely-spelled directory *inside* the vault; `C:\\vault` likewise.
        The pack's CI gates bash 3.2 and `/usr/bin/python3`, so there is no
        Windows path to protect -- but the last thing declined on reasoning
        alone turned out to be real on an interpreter the reasoning never ran,
        so this one is a test: the base registers, and the path the driver then
        fails to find is under the vault root.
        """

        root = self.plugin()
        for base in ("..\\..\\etc", "C:\\vault"):
            with self.subTest(base=base):
                manifest = json.loads((root / "sd-plugin.json").read_text(encoding="utf-8"))
                manifest["store"]["bases"]["tip"] = base
                (root / "sd-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
                done = self.run_sd("store", "list", "pp.tip")
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("does not exist", done.stderr)
                self.assertIn(str(self.vault), done.stderr)

    def test_a_store_with_no_kinds_refuses(self) -> None:
        root = self.tmp / "pack"
        root.mkdir(parents=True, exist_ok=True)
        (root / "sd-plugin.json").write_text(
            json.dumps({"prefix": "pp", "interface": 1, "store": STORE}), encoding="utf-8")
        done = self.run_sd("plugin", "add", str(root))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("declares no `kinds` to keep", done.stderr)

    def test_a_registered_store_is_reported_by_plugin_list(self) -> None:
        self.plugin()
        done = self.run_sd("plugin", "list")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("store: vault at $OBSIDIAN_VAULT", done.stdout)


class WriteTests(StoreFixture):
    """8-iv's acceptance criterion, inverted from 8-iii's on purpose.

    8-iii writes with `write_text` and reads through `sd`, so a store that
    cached could not pass. These write through `sd` and read the **bytes** back
    with `read_text`, so a store that answered from memory could not pass
    either. The load-bearing case is
    `test_a_set_leaves_every_line_it_did_not_edit_byte_identical`: a
    write-through-`sd`, read-through-`sd` test cannot see the failure R11-D27
    exists to prevent, because `sd`'s own reader is the thing that is blind.
    """

    #: A note in the shape the real corpus is in: list values under `tags` and
    #: `contexts`, and a quoted scalar holding a colon and a wikilink. Every
    #: one of these is invisible to `frontmatter()` and destroyed by a
    #: parse-and-rewrite.
    LOSSY = (
        "---\n"
        "status: inbox\n"
        "score: 7\n"
        "aliases:\n"
        '  - "A tip: with a colon"\n'
        "contexts:\n"
        "  - Personal\n"
        'source-brief: "[[2026-08-15 - Daily Intel Brief]]"\n'
        "tags:\n"
        "  - tip\n"
        "  - ai-generated\n"
        "---\n"
        "\n"
        "The body, which also stays.\n"
    )

    def template(self, root: pathlib.Path, text: str = "\n## Why\n\n## What\n") -> None:
        (root / "tip.md").write_text(text, encoding="utf-8")

    def kind_with_template(self, **over: object) -> dict[str, object]:
        kind: dict[str, object] = dict(TIP_KIND)
        kind["sections"] = {"order": ["Why", "What"], "template": "tip.md"}
        kind.update(over)
        return kind

    # -- add ---------------------------------------------------------------

    def test_add_writes_a_note_the_filesystem_can_read_without_sd(self) -> None:
        """Written through `sd`, asserted as bytes on disk. Never read back through `sd`."""

        root = self.plugin(kinds={"tip": self.kind_with_template()}, register=False)
        self.template(root)
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)

        done = self.run_sd("store", "add", "pp.tip", "Ship it", "--field", "score=9")
        self.assertEqual(done.returncode, 0, done.stderr)

        text = (self.tips / "Ship it.md").read_text(encoding="utf-8")
        self.assertEqual(text, "---\nstatus: inbox\nscore: 9\n---\n\n## Why\n\n## What\n")

    def test_add_supplies_the_initial_status_without_being_asked(self) -> None:
        root = self.plugin(kinds={"tip": self.kind_with_template()}, register=False)
        self.template(root)
        self.run_sd("plugin", "add", str(root))
        self.run_sd("store", "add", "pp.tip", "Ship it")
        self.assertIn("status: inbox", (self.tips / "Ship it.md").read_text(encoding="utf-8"))

    def test_add_refuses_to_overwrite_an_existing_note(self) -> None:
        root = self.plugin(kinds={"tip": self.kind_with_template()}, register=False)
        self.template(root)
        self.run_sd("plugin", "add", str(root))
        kept = self.note("Ship it", body="Do not lose me.\n")
        done = self.run_sd("store", "add", "pp.tip", "Ship it")
        self.assertEqual(done.returncode, 1)
        self.assertIn("already exists", done.stderr)
        self.assertIn("Do not lose me.", kept.read_text(encoding="utf-8"))

    def test_a_template_that_does_not_render_the_declared_order_refuses(self) -> None:
        """`sections.order` gets a consequence for the first time.

        `validate_sections` never opens the template, so before 8-iv an order
        naming headings the template does not produce registered clean.
        """

        root = self.plugin(kinds={"tip": self.kind_with_template()}, register=False)
        self.template(root, "\n## What\n\n## Why\n")   # declared order is Why, What
        self.run_sd("plugin", "add", str(root))
        done = self.run_sd("store", "add", "pp.tip", "Ship it")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("sections.order", done.stderr)
        self.assertFalse((self.tips / "Ship it.md").exists())

    def test_add_refuses_a_duplicate_unique_field(self) -> None:
        root = self.plugin(
            kinds={"tip": self.kind_with_template(**{"unique-fields": ["score"]})},
            register=False)
        self.template(root)
        self.run_sd("plugin", "add", str(root))
        self.note("Taken", score="9")
        done = self.run_sd("store", "add", "pp.tip", "Ship it", "--field", "score=9")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("unique-fields", done.stderr)

    # -- set, and the thing it must never do -------------------------------

    def test_a_set_leaves_every_line_it_did_not_edit_byte_identical(self) -> None:
        """The whole reason 8-iv is a line edit (R11-D27).

        A parse-and-rewrite passes a write-through-`sd`, read-through-`sd`
        test and fails this one, because `sd`'s own reader cannot see the
        lines it destroyed.
        """

        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text(self.LOSSY, encoding="utf-8")

        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")
        self.assertEqual(done.returncode, 0, done.stderr)

        after = path.read_text(encoding="utf-8")
        self.assertEqual(after, self.LOSSY.replace("status: inbox", "status: approved"))

    def test_a_set_preserves_every_list_item_and_quoted_scalar(self) -> None:
        """Stated as its own case so a failure names what was lost."""

        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text(self.LOSSY, encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")

        # Without these two lines the case is vacuous: every survivor string is
        # already in the file before the write, so a `set` that refused and
        # changed nothing would pass every assertion below. Proven by
        # sabotaging `store_set` to raise -- this test still passed, and the
        # byte-identical sibling above correctly failed.
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("status: approved", after)

        for survivor in (
                "aliases:", '  - "A tip: with a colon"', "contexts:", "  - Personal",
                'source-brief: "[[2026-08-15 - Daily Intel Brief]]"',
                "tags:", "  - tip", "  - ai-generated", "The body, which also stays."):
            self.assertIn(survivor, after, f"a set destroyed {survivor!r}")

    def test_a_field_the_note_does_not_carry_is_added_before_the_fence(self) -> None:
        self.plugin(kinds={"tip": {"fields": ["status", "score"], "initial-status": "inbox"}})
        path = self.tips / "Ship it.md"
        path.write_text("---\nstatus: inbox\n---\n\nBody.\n", encoding="utf-8")
        self.run_sd("store", "set", "pp.tip", "Ship it", "score", "9")
        self.assertEqual(
            path.read_text(encoding="utf-8"), "---\nstatus: inbox\nscore: 9\n---\n\nBody.\n")

    def test_a_duplicate_key_is_refused_rather_than_half_edited(self) -> None:
        self.plugin()
        path = self.tips / "Ship it.md"
        original = "---\nstatus: inbox\nscore: 7\nstatus: approved\n---\n\nBody.\n"
        path.write_text(original, encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "declined")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("2 lines", done.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_a_note_with_no_frontmatter_block_refuses(self) -> None:
        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text("Just a body.\n", encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("frontmatter", done.stderr)

    def test_a_value_needing_quotes_gets_them(self) -> None:
        """A bare `[[wikilink]]` or sentence colon is malformed YAML, not lossy YAML."""

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        self.note("Ship it", extra="note: old\n")
        self.run_sd("store", "set", "pp.tip", "Ship it", "note", "[[A link]] and a: colon")
        self.assertIn(
            'note: "[[A link]] and a: colon"',
            (self.tips / "Ship it.md").read_text(encoding="utf-8"))

    # -- the six keys, refusing -------------------------------------------

    def test_a_protected_field_refuses(self) -> None:
        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox",
            "protected-fields": ["score"]}})
        path = self.note("Ship it")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "9")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("protected-fields", done.stderr)
        self.assertIn("score: 7", path.read_text(encoding="utf-8"))

    def test_a_transition_no_edge_allows_refuses(self) -> None:
        self.plugin()
        self.note("Ship it", status="approved")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "inbox")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("transitions", done.stderr)

    def test_a_value_under_the_floor_refuses(self) -> None:
        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox", "floor": {"score": 6}}})
        self.note("Ship it")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "3")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("floor", done.stderr)

    def test_a_human_only_status_refuses_and_offers_no_force(self) -> None:
        """There is deliberately no flag that lifts this (R11-D27)."""

        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox",
            "transitions": {"inbox": ["published"]},
            "human-only": {"publish": "published"}}})
        self.note("Ship it")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "published")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("human-only", done.stderr)

        forced = self.run_sd(
            "store", "set", "pp.tip", "Ship it", "status", "published", "--force")
        self.assertEqual(forced.returncode, 2, "--force must not be a flag this verb accepts")

    def test_a_field_the_kind_never_declared_refuses(self) -> None:
        self.plugin()
        self.note("Ship it")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "invented", "x")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("declares no field", done.stderr)


    # -- the positive controls, without which a refusal proves nothing ------

    def test_a_value_at_or_above_the_floor_is_written(self) -> None:
        """The control for the floor case.

        Without it, a `refuse_below_floor` that refused every write to a
        floored field -- never comparing anything -- would pass the whole
        suite. The boundary is included because `<` and `<=` are the usual
        place this goes wrong.
        """

        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox", "floor": {"score": 6}}})
        path = self.note("Ship it")
        for value in ("6", "9"):
            done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", value)
            self.assertEqual(done.returncode, 0, f"{value} is not under the floor: {done.stderr}")
            self.assertIn(f"score: {value}", path.read_text(encoding="utf-8"))

    def test_add_cannot_slip_under_a_floor_by_omitting_the_field(self) -> None:
        """The floor is a property of the note, not of the arguments.

        `store_add` used to iterate the fields it was *given*, so leaving the
        floored field off the command line created a note the floor would have
        refused had it been named. The check iterates the kind's floored
        fields instead, so silence is not a way past it.
        """

        root = self.plugin(
            kinds={"tip": self.kind_with_template(floor={"score": 6})}, register=False)
        self.template(root)
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)

        done = self.run_sd("store", "add", "pp.tip", "Quiet one")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("floor", done.stderr)
        self.assertFalse(
            list(self.vault.rglob("Quiet one.md")), "the refused note must not be on disk")

        allowed = self.run_sd("store", "add", "pp.tip", "Loud one", "--field", "score=7")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_a_closing_fence_with_trailing_spaces_still_ends_the_block(self) -> None:
        """The last of the three fence sites to disagree with the other two.

        `frontmatter_span` compared with `.rstrip("\\r\\n")` while `frontmatter`
        and `note_body` used `.rstrip()`, so `---   ` closed the block for the
        readers and not for the writer. The writer then scanned past it and
        would insert a key below the block, in the body, leaving the real one
        above -- the same failure an indented `---` caused, arriving from the
        opposite direction. No note in the live bases spells a fence that way;
        the point is that the three agree, not that the corpus needs it.
        """

        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text("---\nstatus: inbox\n---   \n\nThe body.\n", encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "---\nstatus: approved\n---   \n\nThe body.\n")

    def test_an_opening_fence_with_trailing_spaces_is_still_frontmatter(self) -> None:
        """The fourth fence site, and the one the previous round left behind.

        Fixing `frontmatter_span`'s *closing* comparison last round did not
        touch its *opening* one, which still used `.rstrip("\\r\\n")`. So a note
        whose first line is `---   ` had frontmatter according to both readers
        and none according to the writer, which refuses a note it cannot find
        a block in -- a `set` failing on a note whose fields `sd store get`
        will happily print.
        """

        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text("---   \nstatus: inbox\n---\n\nThe body.\n", encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            "---   \nstatus: approved\n---\n\nThe body.\n")

    def test_the_first_add_into_a_new_kind_creates_its_directory(self) -> None:
        """`unique-fields` used to stop this, and the message named the vault.

        `refuse_duplicate_unique` scans the kind directory and `note_paths`
        refuses a missing one, so the first `add` into a kind whose directory
        did not exist yet failed a *uniqueness* check -- while `store_add`
        creates that directory a few lines further down. Nothing collides with
        notes that are not there.
        """

        self.check_missing_base(["score"])

    def test_the_first_add_works_without_unique_fields_too(self) -> None:
        """The control: this path never went through the uniqueness scan."""

        self.check_missing_base([])

    def check_missing_base(self, unique: list[str]) -> None:
        kind = self.kind_with_template()
        if unique:
            kind["unique-fields"] = unique
        root = self.plugin(kinds={"tip": kind}, register=False)
        self.template(root)
        done = self.run_sd("plugin", "add", str(root))
        self.assertEqual(done.returncode, 0, done.stderr)
        shutil.rmtree(self.tips)

        done = self.run_sd("store", "add", "pp.tip", "First", "--field", "score=7")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.tips / "First.md").is_file(), "the note was not written")

        # And the scan it skipped still works once there is something to scan.
        clash = self.run_sd("store", "add", "pp.tip", "Second", "--field", "score=7")
        if unique:
            self.assertEqual(clash.returncode, 1, clash.stdout)
            self.assertIn("unique", clash.stderr)
        else:
            self.assertEqual(clash.returncode, 0, clash.stderr)

    def test_a_hash_anywhere_in_a_value_gets_quoted_not_only_at_the_start(self) -> None:
        """YAML starts a comment at ` #`, not only at the first column.

        `NEEDS_QUOTING` tested `#` in the first-character class, so
        `released in v2 # not really` was emitted bare and a real parser read
        it as `released in v2`. Same shape as the backslash case: this
        repository's reader takes the whole line and never sees the loss, so
        the note is wrong only for everything else that opens the vault.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        self.note("Ship it", extra="note: old\n")
        value = "released in v2 # not really"
        self.assertEqual(
            self.run_sd("store", "set", "pp.tip", "Ship it", "note", value).returncode, 0)
        self.assertIn(
            f'note: "{value}"\n', (self.tips / "Ship it.md").read_text(encoding="utf-8"))

    def test_an_edit_does_not_change_who_may_read_the_note(self) -> None:
        """`os.replace` carries the temporary file's mode onto the target.

        `NamedTemporaryFile` creates at 0600, so editing one field of a
        world-readable note silently made it owner-only -- a permission change
        nobody asked for, from a command whose contract is that it changes one
        line.
        """

        self.plugin()
        path = self.note("Ship it")
        path.chmod(0o644)
        self.assertEqual(
            self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved").returncode, 0)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)

    def test_a_value_opening_with_a_yaml_indicator_is_quoted(self) -> None:
        """Five shapes that made the note unparseable, found by enumeration.

        Eight review rounds each surfaced one more value this reader accepted
        and a real parser did not, so the class was enumerated instead of
        waited on: every value in the case list below was rendered and handed
        to PyYAML. `- item`, `? key`, `, comma`, `]close` and `}close` were
        hard parse errors -- a note `sd store set` writes and nothing can
        read.

        `-3` and `?x` stay bare deliberately. Only `- ` and `? ` are
        indicators; quoting a leading dash outright would turn every negative
        number in the vault into a string.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        path = self.note("Ship it", extra="note: old\n")
        for value in ("- item", "? key", ", comma", "]close", "}close",
                      "'quote", "trailing:", "-", "?", "=", "a\tb"):
            self.assertEqual(
                self.run_sd("store", "set", "pp.tip", "Ship it", "note", value).returncode, 0)
            self.assertIn(f'note: "{value}"\n', path.read_text(encoding="utf-8"))
        for value in ("-3", "?x", "3-4", "a,b"):
            self.assertEqual(
                self.run_sd("store", "set", "pp.tip", "Ship it", "note", value).returncode, 0)
            self.assertIn(f"note: {value}\n", path.read_text(encoding="utf-8"))

    @unittest.skipUnless(yaml is not None, "PyYAML absent; the concrete case above still runs")
    def test_a_real_yaml_reader_can_parse_every_note_this_writer_leaves(self) -> None:
        """The general form, against a parser that is not this repository's.

        PyYAML is deliberately not a dependency of `sd` -- R11-D27 rejected
        taking one for the write path -- so this reinforces the case above
        where it is installed rather than replacing it. What it pins is the
        property that case can only sample: the note `sd store set` leaves on
        disk is readable by Obsidian, and by anything else pointed at the
        vault, not only by `frontmatter()`.

        Eight review rounds each found one more value that got past this
        writer and not past a real parser. The list below is the enumeration
        that ended that: every value is written through the real command and
        read back through a real parser.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        path = self.note("Ship it", extra="note: old\n")
        for value in ["plain", "a: b", "mid # hash", "[x]", "{y}", "#tag", "|pipe", ">fold",
                      "&anchor", "*alias", "!tag", "%directive", "@at", "`tick", "- item",
                      "? key", ", comma", "]close", "}close", "-3", "?x", "a,b", "3-4",
                      "true", "1", "2026-09-01", "12:30", "0755", "~",
                      "'quote", "trailing:", "-", "?", "=", "a\tb", "'a'"]:
            with self.subTest(value=value):
                done = self.run_sd("store", "set", "pp.tip", "Ship it", "note", value)
                self.assertEqual(done.returncode, 0, done.stderr)
                yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])

    @unittest.skipUnless(yaml is not None, "PyYAML absent; the concrete cases above still run")
    def test_no_short_value_over_the_yaml_indicators_breaks_a_real_parser(self) -> None:
        """The rule `NEEDS_QUOTING` encodes, derived rather than recalled.

        Two hand-written enumerations of the indicator set were each
        incomplete. The first missed the five values that open `- `, `? `,
        `,`, `]` and `}`. The second, written *after* that lesson and believed
        to be the whole class, still missed a leading `'` -- which opens a
        single-quoted scalar and swallows the rest of the block -- along with a
        trailing `:` (`note: See also:` is an unterminated mapping key) and an
        embedded tab, which `render_value` lets past its control-character
        check on purpose.

        So this does not check a list. It renders every string up to length
        three over the alphabet of YAML indicators, plus a random sample of
        longer ones, and requires that a real parser reads back what was
        written. A future edit to `NEEDS_QUOTING` that reopens any hole fails
        here without anyone having to have thought of the case.

        `render_value` is called in process rather than through `sd store set`
        because the subprocess cost is per value and there are tens of
        thousands of them; the end-to-end path is covered by the two cases
        above.
        """

        alphabet = list("-?:,[]{}>|&*!%@`#'\"= \tab1.~")
        values = ["".join(p) for n in (1, 2, 3) for p in itertools.product(alphabet, repeat=n)]
        rng = random.Random(11)
        values += ["".join(rng.choice(alphabet) for _ in range(rng.randint(4, 9)))
                   for _ in range(4000)]
        broken = []
        for value in values:
            try:
                rendered = sd_module().render_value(value)
            except Exception:
                continue          # refused outright, which is a valid answer
            try:
                read_back = yaml.safe_load(f"k: {rendered}\n")["k"]
            except Exception as error:
                broken.append((value, rendered, type(error).__name__))
                continue
            if isinstance(read_back, str) and read_back != value:
                broken.append((value, rendered, f"read back as {read_back!r}"))
        self.assertEqual(broken[:10], [], f"{len(broken)} of {len(values)} values do not survive")

    @unittest.skipUnless(yaml is not None, "PyYAML absent")
    def test_the_types_a_real_reader_infers_are_left_to_the_corpus_convention(self) -> None:
        """An inventory of what this writer deliberately does *not* quote.

        Every value below is written bare and a real parser gives it a type
        other than string. That is left alone, and this test exists so that
        leaving it alone stays a decision rather than becoming an oversight.

        Quoting them was considered and rejected. `sd store set` takes its
        value from `argv`, so every value arrives as a string and the writer
        has no declared type to consult -- quoting would mean guessing. The
        cost of guessing is concrete: a hand-written note in the vault holds
        bare `true`, so a quoted `"true"` from `sd` would read as a different
        type than the note beside it. Numbers are the case that matters most
        and they are unaffected either way (`1` and `-3` both survive), so
        `floor` keeps comparing numbers whatever is decided here.

        `0755` reading back as 493 and `12:30` as 750 are YAML 1.1 warts, and
        they are the two entries here worth revisiting -- but Obsidian applies
        the same warts to a note written by hand, and `sd` diverging from that
        would be its own defect.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        path = self.note("Ship it", extra="note: old\n")
        for value, expected in [("true", True), ("no", False), ("on", True),
                                ("~", None), ("0755", 493), ("12:30", 750)]:
            with self.subTest(value=value):
                self.assertEqual(
                    self.run_sd("store", "set", "pp.tip", "Ship it", "note", value).returncode, 0)
                self.assertIn(f"note: {value}\n", path.read_text(encoding="utf-8"))
                loaded = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
                self.assertEqual(loaded["note"], expected)

    def test_a_floor_is_not_stepped_over_by_spelling_a_value_nan(self) -> None:
        """`float("nan") < 6` is False, so an unguarded floor lets it through.

        The floor refused 5 and accepted `nan`, which is a bound any value can
        clear by spelling itself strangely. `inf` is included because it is the
        same class of input even though it clears a floor honestly.
        """

        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox", "floor": {"score": 6}}})
        path = self.note("Ship it", score="7")
        for value in ("nan", "NaN", "inf", "Infinity"):
            done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", value)
            self.assertEqual(done.returncode, 1, f"{value} was accepted: {done.stdout}")
            self.assertIn("finite", done.stderr)

        # `-inf` never reaches the floor: argparse reads a leading dash as an
        # option and rejects it first. Asserted as refused rather than as
        # refused *here*, because pinning the exit code would pin argparse's
        # behaviour rather than this check's.
        minus = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "-inf")
        self.assertNotEqual(minus.returncode, 0, "-inf was accepted")

        self.assertIn("score: 7", path.read_text(encoding="utf-8"))

    def test_a_title_cannot_walk_out_of_the_kind_directory(self) -> None:
        """Both verbs, because `store get` kept its own weaker copy of this.

        Containment does the work rather than a forbidden-character list: with
        the resolve check removed, `a/b` and `../escaped` are both accepted.
        A backslash is *not* asserted here -- it is an ordinary filename
        character on this platform, and refusing it would be a rule about
        Windows enforced against a legal title.
        """

        root = self.plugin(kinds={"tip": self.kind_with_template()}, register=False)
        self.template(root)
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)
        for title in ("../escaped", "..", ".", "", "a/b", "sub/../../out"):
            for verb in (("store", "set", "pp.tip", title, "status", "inbox"),
                         ("store", "get", "pp.tip", title)):
                done = self.run_sd(*verb)
                self.assertEqual(
                    done.returncode, 2, f"{title!r} accepted by {verb[1]}: {done.stdout}")

    def test_an_indented_rule_does_not_move_where_the_body_starts(self) -> None:
        """The third fence site, which the other two fixes left behind.

        `note_body` kept `.strip()` after `frontmatter` and `frontmatter_span`
        moved to column zero, so the three disagreed about where the block
        ends. `read_note` reaches it, which makes `sd store get --json` the
        place it shows: the fields are read to the real fence and the body is
        cut at the indented one, so the note comes back reporting a body that
        starts in the middle of its own frontmatter.
        """

        self.plugin()
        (self.tips / "Ship it.md").write_text(
            "---\nstatus: inbox\nnote: |\n  one\n  ---\n  two\n---\n\n## Why\n",
            encoding="utf-8")
        done = self.run_sd("store", "get", "pp.tip", "Ship it", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        body = json.loads(done.stdout)["body"]
        self.assertEqual(body, "\n## Why\n", f"body was cut at the indented rule: {body!r}")

    def test_a_floored_field_given_something_that_is_not_a_number(self) -> None:
        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox", "floor": {"score": 6}}})
        self.note("Ship it")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "high")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("must be a number", done.stderr)

    def test_setting_a_unique_field_to_its_own_current_value_is_not_a_collision(self) -> None:
        """`skip=path`: a note must not collide with itself."""

        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox",
            "unique-fields": ["score"]}})
        self.note("Ship it", score="7")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "7")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_setting_a_unique_field_to_a_value_another_note_holds_refuses(self) -> None:
        self.plugin(kinds={"tip": {
            "fields": ["status", "score"], "initial-status": "inbox",
            "unique-fields": ["score"]}})
        self.note("Ship it", score="7")
        self.note("Taken", score="9")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "9")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("unique-fields", done.stderr)

    def test_add_enforces_the_same_keys_set_does(self) -> None:
        """`add`'s enforcement calls were reachable only through `set` before this."""

        root = self.plugin(kinds={"tip": self.kind_with_template(**{
            "protected-fields": ["score"], "floor": {"score": 6}})}, register=False)
        self.template(root)
        self.run_sd("plugin", "add", str(root))

        protected = self.run_sd("store", "add", "pp.tip", "A", "--field", "score=9")
        self.assertEqual(protected.returncode, 1, protected.stdout)
        self.assertIn("protected-fields", protected.stderr)
        self.assertFalse((self.tips / "A.md").exists())

    def test_add_refuses_a_status_no_transition_reaches(self) -> None:
        root = self.plugin(kinds={"tip": self.kind_with_template()}, register=False)
        self.template(root)
        self.run_sd("plugin", "add", str(root))
        done = self.run_sd("store", "add", "pp.tip", "A", "--field", "status=published")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("transitions", done.stderr)
        self.assertFalse((self.tips / "A.md").exists())

    def test_setting_a_field_to_the_value_it_already_holds_writes_nothing(self) -> None:
        self.plugin()
        path = self.note("Ship it")
        before = path.read_text(encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "score", "7")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("already holds", done.stdout)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_an_unterminated_frontmatter_block_refuses(self) -> None:
        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text("---\nstatus: inbox\nscore: 7\n", encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("never closed", done.stderr)

    def test_a_value_the_reader_could_not_read_back_is_refused(self) -> None:
        """A double quote, refused rather than encoded.

        The quoted form is `\\"` and `frontmatter()` strips quotes without
        unescaping anything, so the value would come back carrying a
        backslash. Writing something the store cannot read back is worse than
        refusing it, and the corpus quotes plenty of scalars without nesting a
        quote inside one.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        path = self.note("Ship it", extra="note: old\n")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "note", 'a "quote"')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("read back unchanged", done.stderr)
        self.assertIn("note: old", path.read_text(encoding="utf-8"))

    def test_a_value_holding_a_newline_is_refused_not_split_across_lines(self) -> None:
        """The one-line invariant, defended at the value.

        Without this, `edit_field` writes the newline straight through and the
        single line it replaced becomes two -- a physical line silently
        inserted into the block, which is the property this design exists to
        hold.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        path = self.note("Ship it", extra="note: old\n")
        before = path.read_text(encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "Ship it", "note", "line1\nline2")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("control character", done.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_a_backslash_is_written_bare_and_refused_where_it_would_be_quoted(self) -> None:
        """This test used to assert the opposite, and was wrong to.

        It wrote `a \\ slash: yes`, which needs quoting for the colon, and
        asserted the value came back through `sd store get`. It did -- because
        this reader ends `.strip('"')` and unescapes nothing. A real YAML
        parser reads `"a \\ slash: yes"` as an invalid escape and fails, so the
        note round-tripped here while being unreadable to Obsidian and to
        every other tool pointed at the same vault. That is the malformed-YAML
        failure R11-D27 exists to prevent, written by the code meant to
        prevent it.

        A plain scalar takes a backslash literally, so an unquoted value keeps
        one. A value that needs quoting for some other reason is refused.
        """

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        self.note("Ship it", extra="note: old\n")

        bare = "a \\ slash"
        self.assertEqual(
            self.run_sd("store", "set", "pp.tip", "Ship it", "note", bare).returncode, 0)
        self.assertIn("note: a \\ slash\n", (self.tips / "Ship it.md").read_text(encoding="utf-8"))
        done = self.run_sd("store", "get", "pp.tip", "Ship it", "--json")
        self.assertEqual(json.loads(done.stdout)["fields"]["note"], bare)

        quoted = self.run_sd("store", "set", "pp.tip", "Ship it", "note", "a \\ slash: yes")
        self.assertEqual(quoted.returncode, 1, quoted.stdout)
        self.assertIn("backslash", quoted.stderr)

    def test_an_indented_rule_inside_a_value_is_not_the_closing_fence(self) -> None:
        """A block scalar holding its own `---` line.

        `frontmatter_span` matched on `.strip()`, so an **indented** `---`
        inside a value closed the block at the wrong line. `set` then reported
        the real field as absent and inserted a fresh `key: value` into the
        middle of the note's prose, leaving the original in place -- a
        corrupted note carrying a duplicate key. YAML always indents a block
        scalar's body, so the fence is the one at column zero.
        """

        self.plugin()
        path = self.tips / "Ship it.md"
        path.write_text(
            "---\n"
            "description: |\n"
            "  some prose\n"
            "  ---\n"
            "  more prose\n"
            "status: inbox\n"
            "score: 7\n"
            "---\n"
            "\nBody\n", encoding="utf-8")

        done = self.run_sd("store", "set", "pp.tip", "Ship it", "status", "approved")
        self.assertEqual(done.returncode, 0, done.stderr)

        after = path.read_text(encoding="utf-8")
        self.assertEqual(after.count("status:"), 1, f"a duplicate key was inserted:\n{after}")
        self.assertIn("  ---\n  more prose\n", after)
        self.assertIn("status: approved\n", after)

class AddListsAndSectionsTests(StoreFixture):
    """8-vi: what `add` needs before a routine can stop calling `pack.py`.

    A tip note carries two list-valued frontmatter keys and three sections of
    generated prose. Until this, `add` wrote flat `field: value` and a static
    template, so `sd store add` could not produce one.
    """

    def setUp(self) -> None:
        super().setUp()
        self.kind: dict[str, object] = {
            "fields": ["status", "score", "contexts"],
            "initial-status": "inbox",
            "transitions": {"inbox": ["approved", "declined"]},
            "sections": {"order": ["Tip", "Score"], "template": "tip.md"},
        }

    def build(self, template: str = "\n## Tip\n\n## Score\n") -> None:
        root = self.plugin(kinds={"tip": self.kind}, register=False)
        (root / "tip.md").write_text(template, encoding="utf-8")
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)

    def test_a_repeated_field_builds_a_block_sequence(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--field", "contexts+=Personal", "--field", "contexts+=Work")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(
            "contexts:\n  - Personal\n  - Work\n",
            (self.tips / "T.md").read_text(encoding="utf-8"))

    @unittest.skipUnless(yaml is not None, "PyYAML is not installed")
    def test_a_real_yaml_reader_sees_the_sequence_as_a_list(self) -> None:
        """The corpus rule, applied to the shape this adds. A block sequence
        that a real reader folds into a string would be worse than no list."""

        self.build()
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--field", "contexts+=Personal", "--field", "contexts+=Work").returncode, 0)
        text = (self.tips / "T.md").read_text(encoding="utf-8")
        block = text.split("---\n")[1]
        assert yaml is not None
        self.assertEqual(yaml.safe_load(block)["contexts"], ["Personal", "Work"])

    def test_a_field_given_twice_with_plain_equals_is_still_a_mistake(self) -> None:
        """`+=` exists so this stays an error. Folding every duplicate into a
        list would make `--field score=7 --field score=8` a two-item list."""

        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=7", "--field", "score=8")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("given twice", done.stderr)
        self.assertFalse((self.tips / "T.md").exists())

    def test_mixing_the_two_spellings_on_one_field_is_refused(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "contexts=Personal",
            "--field", "contexts+=Work")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("given twice", done.stderr)

    def test_a_value_holding_the_separator_is_not_split_on_it(self) -> None:
        self.build()
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--field", "contexts=a+=b").returncode, 0)
        self.assertIn("contexts: a+=b", (self.tips / "T.md").read_text(encoding="utf-8"))

    def test_a_list_is_refused_on_a_field_something_compares_as_one_value(self) -> None:
        """`status`, `floor` and `unique-fields` all read a field as a scalar.
        Without this the list reached them where a string was expected."""

        self.kind["floor"] = {"score": 6}
        self.build()
        for field in ("status", "score"):
            with self.subTest(field=field):
                # `score` is given once, as a list. Adding a scalar `score=9`
                # alongside would trip the duplicate guard first and the case
                # would pass without ever reaching what it is about.
                extra = [] if field == "score" else ["--field", "score=9"]
                done = self.run_sd(
                    "store", "add", "pp.tip", f"T-{field}",
                    *extra, "--field", f"{field}+=x")
                self.assertNotEqual(done.returncode, 0)
                self.assertIn("single value", done.stderr)

    def test_section_text_lands_under_its_heading(self) -> None:
        self.build()
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Tip=Use a narrow grant.",
            "--section", "Score=Rated 9 for blast radius.").returncode, 0)
        body = (self.tips / "T.md").read_text(encoding="utf-8").split("---\n")[2]
        self.assertEqual(
            body, "\n## Tip\n\nUse a narrow grant.\n\n## Score\n\nRated 9 for blast radius.\n")

    def test_the_templates_own_content_survives_the_fill(self) -> None:
        """Text goes under the heading, above the boilerplate. Replacing the
        section would make `--section` a silent template override."""

        self.build(template="\n## Tip\n\nboilerplate\n\n## Score\n")
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Tip=Real text.").returncode, 0)
        body = (self.tips / "T.md").read_text(encoding="utf-8")
        self.assertIn("## Tip\n\nReal text.\n\nboilerplate\n", body)

    def test_a_section_the_template_does_not_render_is_refused(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Provenance=Nowhere to go.")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("renders no `## Provenance`", done.stderr)
        self.assertFalse((self.tips / "T.md").exists())

    def test_section_text_carrying_its_own_heading_is_refused(self) -> None:
        """Otherwise the note is written with a heading outside
        `sections.order`, which the order check has just approved."""

        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Tip=text\n## Score\nsmuggled")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("its own `## ` heading", done.stderr)


LIST_KIND: dict[str, object] = {
    "fields": ["status", "score", "contexts"],
    "initial-status": "inbox",
    "transitions": {"inbox": ["approved", "declined"]},
}


class ListValuedFieldTests(StoreFixture):
    """R11-D27's hazard reached from the write side.

    `edit_field` replaces the one line that declares a key. For `contexts:`
    with `  - Personal` under it, that line is only the header, and replacing
    it leaves the items behind as orphans that the next reader attaches to
    whatever key follows. The note still parses, which is what makes it worth
    a test rather than a comment.
    """

    def test_a_field_holding_a_list_is_refused_rather_than_edited(self) -> None:
        self.plugin(kinds={"tip": dict(LIST_KIND)})
        path = self.note("T", extra="contexts:\n  - Personal\n  - Work\n")
        before = path.read_bytes()
        done = self.run_sd("store", "set", "pp.tip", "T", "contexts", "Shared")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("holds a list", done.stderr)
        # The refusal has to leave the file alone, not merely report. A guard
        # that refuses after writing is the failure it exists to prevent.
        self.assertEqual(path.read_bytes(), before)

    def test_a_blank_line_between_the_key_and_its_items_does_not_hide_them(self) -> None:
        """The scan skips blanks. Stopping at the first one would step over
        the continuation and hand the note back to `edit_field`."""

        self.plugin(kinds={"tip": dict(LIST_KIND)})
        path = self.note("T", extra="contexts:\n\n  - Personal\n")
        before = path.read_bytes()
        done = self.run_sd("store", "set", "pp.tip", "T", "contexts", "Shared")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_an_inline_value_is_still_edited(self) -> None:
        """The other half. A guard that refused every field would pass the
        test above while breaking `set` entirely."""

        self.plugin(kinds={"tip": dict(LIST_KIND)})
        path = self.note("T", extra="contexts: Personal\n")
        done = self.run_sd("store", "set", "pp.tip", "T", "contexts", "Shared")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("contexts: Shared", path.read_text(encoding="utf-8"))

    def test_a_following_key_is_not_read_as_a_continuation(self) -> None:
        """`score: 7` after an empty `contexts:` is a sibling key, not an item.
        Matching any indented line, or any line at all, would refuse it."""

        self.plugin(kinds={"tip": dict(LIST_KIND)})
        path = self.note("T", extra="contexts:\n")
        done = self.run_sd("store", "set", "pp.tip", "T", "contexts", "Shared")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("contexts: Shared", path.read_text(encoding="utf-8"))


class DeclarationTests(StoreFixture):
    """The 8-i gap 8-iv closes: a key that governs nothing registers clean."""

    def test_transitions_without_a_status_field_refuses_at_registration(self) -> None:
        root = self.plugin(
            kinds={"tip": {"fields": ["score"], "initial-status": "inbox",
                           "transitions": {"inbox": ["approved"]}}},
            register=False)
        done = self.run_sd("plugin", "add", str(root))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("transitions", done.stderr)

    def test_human_only_without_a_status_field_refuses_at_registration(self) -> None:
        root = self.plugin(
            kinds={"tip": {"fields": ["score"], "initial-status": "inbox",
                           "human-only": {"publish": "published"}}},
            register=False)
        done = self.run_sd("plugin", "add", str(root))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("human-only", done.stderr)

    def test_a_statusless_kind_is_still_registerable(self) -> None:
        """`initial-status` is deliberately not part of the tightening.

        It is required of every kind, so requiring a `status` field for it
        would make a statusless kind unregisterable and `status_filter`'s
        refusal unreachable -- the case
        `test_status_on_a_kind_without_one_refuses_instead_of_matching_nothing`
        exists to cover.
        """

        root = self.plugin(
            kinds={"tip": {"fields": ["score"], "initial-status": "inbox"}}, register=False)
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
