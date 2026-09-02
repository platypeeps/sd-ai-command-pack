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

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = REPO_ROOT / "bin" / "sd"

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

    def test_a_value_holding_a_backslash_survives_the_round_trip(self) -> None:
        """Written, then read back through `sd get --json`. An actual round trip."""

        self.plugin(kinds={"tip": {"fields": ["status", "note"], "initial-status": "inbox"}})
        self.note("Ship it", extra="note: old\n")
        value = "a \\ slash: yes"
        self.assertEqual(
            self.run_sd("store", "set", "pp.tip", "Ship it", "note", value).returncode, 0)
        done = self.run_sd("store", "get", "pp.tip", "Ship it", "--json")
        self.assertEqual(json.loads(done.stdout)["fields"]["note"], value)

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
