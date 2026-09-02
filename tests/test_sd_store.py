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

    def test_the_value_starts_immediately_after_the_first_separator(self) -> None:
        """`contexts+==x` is a list holding `=x`, and `contexts==x` is the
        scalar `=x`. Both take everything after the separator verbatim, which
        is the same rule, and a value may legitimately begin with `=`.

        Pinned rather than argued: rejecting `+==` as a typo would special-case
        one spelling while `==` -- which has always been accepted and gives the
        analogous scalar -- kept working, and would refuse a real `=x`.
        """

        self.build()
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "L", "--field", "score=9",
            "--field", "contexts+==Personal").returncode, 0)
        self.assertIn("contexts:\n  - =Personal\n",
                      (self.tips / "L.md").read_text(encoding="utf-8"))
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "S", "--field", "score=9",
            "--field", "contexts==Personal").returncode, 0)
        self.assertIn("contexts: =Personal",
                      (self.tips / "S.md").read_text(encoding="utf-8"))

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

    def test_an_indented_heading_is_refused_too(self) -> None:
        """CommonMark renders a heading indented by up to three spaces, so
        `   ## Score` reaches Obsidian as one while `body_headings`, which reads
        column 0, does not see it."""

        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Tip=text\n   ## Score\nsmuggled")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("its own `## ` heading", done.stderr)

    def test_a_crlf_template_is_normalised_before_it_is_filled(self) -> None:
        """Where the CRLF actually goes, which is not where it looks.

        `read_template` opens the file in text mode, so universal newlines
        turn `\\r\\n` into `\\n` before `fill_sections` is called at all. The
        note is therefore all-LF rather than mixed, and this pins that -- the
        function's own ending handling is checked directly below, because no
        input the CLI can produce reaches it with a `\\r` still attached.
        """

        self.build(template="\r\n## Tip\r\n\r\n## Score\r\n")
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Tip=one\ntwo").returncode, 0)
        body = (self.tips / "T.md").read_bytes().split(b"---\n")[2]
        self.assertNotIn(b"\r", body)
        self.assertIn(b"## Tip\n\none\ntwo\n", body)

    def test_the_template_can_say_the_notes_own_title(self) -> None:
        """The one thing a static template cannot state on its own, and that
        every note in the corpus carries."""

        self.build(template="\n# {{title}}\n\n## Tip\n\n## Score\n")
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "A narrow grant", "--field", "score=9").returncode, 0)
        self.assertIn(
            "# A narrow grant\n",
            (self.tips / "A narrow grant.md").read_text(encoding="utf-8"))

    def test_a_misspelled_placeholder_is_refused_rather_than_shipped(self) -> None:
        """Left in place it would reach every note written from that template
        as literal text, and be noticed by a reader rather than an author."""

        self.build(template="\n# {{titel}}\n\n## Tip\n\n## Score\n")
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("{{titel}}", done.stderr)
        self.assertFalse((self.tips / "T.md").exists())

    def test_a_title_is_not_re_scanned_for_placeholders(self) -> None:
        """A title holding `{{x}}` is a title, not a template instruction.
        Refusing it would make the note's name decide whether it can be
        written; substituting from it would let a title reach the engine."""

        self.build(template="\n# {{title}}\n\n## Tip\n\n## Score\n")
        done = self.run_sd(
            "store", "add", "pp.tip", "About {{x}} syntax", "--field", "score=9")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(
            "# About {{x}} syntax\n",
            (self.tips / "About {{x}} syntax.md").read_text(encoding="utf-8"))

    def test_a_field_with_no_value_is_written_without_a_trailing_space(self) -> None:
        """No note in the corpus carries `key: ` with a trailing space, and
        `pack.py` never wrote one. Writing it would make every note `sd` adds
        distinguishable from every note beside it, on whitespace alone."""

        self.build()
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9").returncode, 0)
        block = (self.tips / "T.md").read_text(encoding="utf-8").split("---\n")[1]
        self.assertIn("contexts:\n", block)
        self.assertNotIn("contexts: \n", block)

    @unittest.skipUnless(yaml is not None, "PyYAML is not installed")
    def test_an_empty_list_renders_bare_and_reads_back_as_none(self) -> None:
        """`key:` and `key: []` are different values, not two spellings of one.

        Called directly: `parse_assignments` appends a value for every `+=`, so
        no CLI input builds an empty list. This pins `render_field`'s contract,
        and the reason the bare form is written anyway -- it is what the corpus
        carries for an unfilled list, as `used-by:` and `my-rating:` show.
        """

        rendered = sd_module().render_field("used-by", [])
        self.assertEqual(rendered, "used-by:\n")
        assert yaml is not None
        self.assertIsNone(yaml.safe_load(rendered)["used-by"])
        self.assertEqual(yaml.safe_load("used-by: []")["used-by"], [])

    def test_fill_sections_takes_the_headings_own_line_ending(self) -> None:
        """Called directly, because `read_template` normalises the only input
        the CLI has. Hardcoding "\\n" here put two endings in one file, and
        would do so again the day a template is read with `newline=""`."""

        filled = sd_module().fill_sections(
            "\r\n## Tip\r\n\r\n## Score\r\n", {"Tip": "one\ntwo"})
        self.assertEqual(filled, "\r\n## Tip\r\n\r\none\r\ntwo\r\n\r\n## Score\r\n")
        self.assertNotIn("\n", filled.replace("\r\n", ""))

    def test_section_text_carrying_its_own_heading_is_refused(self) -> None:
        """Otherwise the note is written with a heading outside
        `sections.order`, which the order check has just approved."""

        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section", "Tip=text\n## Score\nsmuggled")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("its own `## ` heading", done.stderr)


class ValueFromFileTests(StoreFixture):
    """10b-i: the two flags `sdw-tips` cannot move without.

    Step 9 retargeted all six of the vault's `pack.py` invocations and left one
    caller standing outside it: `sdw-tips`, in the plugin repository, which
    passes its tip text as `--tip-file` precisely so a backtick in the prose is
    not run by the shell. `sd store add` had no twin for that flag; these two
    flags are it.

    The load-bearing case is
    `test_a_backtick_survives_the_file_and_would_not_survive_the_shell`: the
    failure being prevented is silent, so a test that only proves the flag
    works would not distinguish it from the flag that loses the words.
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

    def file(self, name: str, text: str) -> str:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_a_backtick_survives_the_file_and_would_not_survive_the_shell(self) -> None:
        """The whole reason the flag exists, asserted against a real shell.

        The same text is put through `sh -c` on the way to the inline flag and
        read from a file on the way to this one. The shell run is not a
        second way of writing the note -- it is the evidence that the words
        this one keeps are the words the other one drops.
        """

        self.build()
        text = "Grant `Bash(sd:*)`, never `Bash(*)`."
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", f"Tip={self.file('tip.txt', text)}").returncode, 0)
        self.assertIn(text, (self.tips / "T.md").read_text(encoding="utf-8"))

        through_a_shell = subprocess.run(
            ["/bin/sh", "-c", f'printf %s "{text}"'], capture_output=True, text=True)
        # The two shells this runs on fail differently and the test may not
        # pick one. `/bin/sh` is bash on macOS, which runs the substitution and
        # hands back the text with the words gone; it is dash on the CI
        # runners, which refuses to parse `Bash(sd:*)` and exits 2 with nothing
        # on stdout. Asserting the bash shape passed locally and failed both
        # matrix legs. What is true of every shell is the claim worth making:
        # none of them hands the text back intact.
        self.assertNotEqual(through_a_shell.stdout, text)
        self.assertNotIn("Bash(sd:*)", through_a_shell.stdout)

    def test_a_field_reads_its_value_from_a_file(self) -> None:
        self.build()
        score = self.file("score.txt", "9\n")
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field-file", f"score={score}").returncode, 0)
        self.assertIn("score: 9\n", (self.tips / "T.md").read_text(encoding="utf-8"))

    def test_the_two_spellings_keep_the_order_they_were_typed_in(self) -> None:
        """A block sequence's order comes from the command line, not from
        which flag supplied each item. `migrate-golden-corpus` compares whole
        notes, so a silent reordering reads as drift with no author."""

        self.build()
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--field", "contexts+=Personal",
            "--field-file", f"contexts+={self.file('c.txt', 'Work')}",
            "--field", "contexts+=Fleet").returncode, 0)
        self.assertIn(
            "contexts:\n  - Personal\n  - Work\n  - Fleet\n",
            (self.tips / "T.md").read_text(encoding="utf-8"))

    def test_file_text_carrying_the_separators_stays_whole(self) -> None:
        """The pair is re-spelled rather than split, so the parsers below
        partition on the first separator and the file's own `=` and `+=`
        are text."""

        self.build()
        text = "score=9 and tags+=x"
        self.assertEqual(self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", f"Tip={self.file('tip.txt', text)}").returncode, 0)
        self.assertIn(text, (self.tips / "T.md").read_text(encoding="utf-8"))

    def test_a_smuggled_heading_is_refused_from_a_file_too(self) -> None:
        """File text goes through the same parser the inline spelling does.
        A second, laxer path to the same write is the thing to avoid."""

        self.build()
        tip = self.file("tip.txt", "text\n## Score\nsmuggled")
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", f"Tip={tip}")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("its own `## ` heading", done.stderr)
        self.assertFalse((self.tips / "T.md").exists())

    def test_a_field_the_kind_does_not_declare_is_refused_from_a_file_too(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T",
            "--field-file", f"nope={self.file('v.txt', 'x')}")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("declares no field", done.stderr)

    def test_a_missing_file_refuses_rather_than_writing_an_empty_value(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", f"Tip={self.tmp / 'absent.txt'}")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("cannot read", done.stderr)
        self.assertFalse((self.tips / "T.md").exists())

    def test_an_empty_file_refuses(self) -> None:
        """`pack.py`'s rule, kept: a note written from an empty file is a note
        nobody meant to write, and it is written silently."""

        self.build()
        tip = self.file("tip.txt", "   \n\n")
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", f"Tip={tip}")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("is empty", done.stderr)

    def test_a_file_that_is_not_utf8_refuses(self) -> None:
        path = self.tmp / "tip.bin"
        path.write_bytes(b"\xff\xfe\x00")
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", f"Tip={path}")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("cannot read", done.stderr)

    def test_a_pair_with_no_separator_is_a_usage_error(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T", "--field", "score=9",
            "--section-file", str(self.file("tip.txt", "text")))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("is not name=path", done.stderr)

    def test_a_pair_with_a_separator_and_no_path_is_a_usage_error(self) -> None:
        """`--field-file score=` is a different mistake from `--field-file
        score`, and says so rather than failing later as an unreadable ''."""

        self.build()
        done = self.run_sd("store", "add", "pp.tip", "T", "--field-file", "score=")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("no path after the separator", done.stderr)

    def test_both_spellings_of_one_field_is_the_error_a_repeat_already_was(self) -> None:
        self.build()
        done = self.run_sd(
            "store", "add", "pp.tip", "T",
            "--field", "score=9",
            "--field-file", f"score={self.file('score.txt', '8')}")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("given twice", done.stderr)

    def test_set_refuses_the_positional_and_the_flag_together(self) -> None:
        """10b-iv gave `set` the file spellings; mixing them is still wrong.

        `--field-file` is on `set` now, because the `pack.py` verbs it replaces
        moved several keys in one write. What is refused is no longer the flag
        but the *mix*: `set k t score --field-file x=y` has one field named
        positionally and another named by flag, and no reading of that is
        obviously right. Exit 2 rather than 1, and it is checked before the
        path is opened -- a wrong invocation should be told so, not told that
        the file it should not have named is missing.
        """

        self.build()
        done = self.run_sd("store", "set", "pp.tip", "T", "score", "--field-file", "x=y")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("not both", done.stderr)


class SetSectionTests(StoreFixture):
    """10b-iii: a `## ` section edited by the line, so `pack.py` can stop.

    Five `pack.py` verbs write a section of a vault note -- `topics
    set-ground-truth`, `topics add-feed`, `topics rm-feed`, `ideas
    set-drive-docs` and `vault set-score` -- and every one of them does it with
    its own `re.sub` over the whole file. Two properties of those are what this
    verb has to keep and what it gets to drop.

    **Kept: the note is never parsed and written back.** R11-D27 is not a
    stylistic preference here. `frontmatter()` reads a block sequence as `""`
    and strips the quotes off a quoted scalar, and all 14 tips in the real
    corpus carry a block sequence while 10 carry a quoted scalar -- so a
    `set-section` that round-tripped the note would destroy every one of them.

    **Dropped: the named anchor.** `topics add-feed` created `## Feeds` by
    substituting ahead of `## Provenance` and died outright when that heading
    was missing (`sd-writing-pack/scripts/pack.py:1082`). The backbone has
    `sections.order`, which already declares where each section sits, so
    position is read from the manifest and a note missing some other section is
    no longer a failure. That is what lets the absent-section read below return
    empty instead of refusing, which in turn collapses `add-feed`'s two
    branches into one read-edit-write.
    """

    ORDER = ["Tip", "Score", "Provenance"]

    def setUp(self) -> None:
        super().setUp()
        self.kind: dict[str, object] = {
            "fields": ["status", "score", "contexts"],
            "initial-status": "inbox",
            "transitions": {"inbox": ["approved", "declined"]},
            "sections": {"order": list(self.ORDER), "template": "tip.md"},
        }

    def build(self, kind: object = None) -> None:
        root = self.plugin(kinds={"tip": kind or self.kind}, register=False)
        (root / "tip.md").write_text(
            "\n## Tip\n\n## Score\n\n## Provenance\n", encoding="utf-8")
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)

    def tip(self, body: str) -> pathlib.Path:
        """A note carrying both shapes `frontmatter()` cannot round-trip."""

        path = self.tips / "T.md"
        path.write_text(
            "---\n"
            "status: inbox\n"
            "score: 7\n"
            'description: "quoted, and the reader strips it"\n'
            "contexts:\n  - Personal\n  - Work\n"
            "---\n\n" + body, encoding="utf-8")
        return path

    def headings(self, path: pathlib.Path) -> list[str]:
        return [line[3:].strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("## ")]

    def file(self, name: str, text: str) -> str:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    # -- the R11-D27 property -------------------------------------------

    def test_the_frontmatter_comes_back_byte_for_byte(self) -> None:
        """The reason this is a line splice and not a parse.

        Proved against the real corpus as well, before this verb was written:
        all 14 tips in `System/Databases/Tips and Tricks` were edited through
        it and not one byte outside the target section changed.
        """

        self.build()
        path = self.tip("## Tip\n\nold tip\n\n## Score\n\nold score\n")
        before = path.read_text(encoding="utf-8").split("\n---\n")[0]
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=new")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(after.split("\n---\n")[0], before)
        self.assertIn("contexts:\n  - Personal\n  - Work\n", after)
        self.assertIn('description: "quoted, and the reader strips it"\n', after)
        self.assertIn("## Score\n\nnew\n", after)
        self.assertIn("old tip", after)

    def test_the_body_outside_the_edited_section_is_untouched(self) -> None:
        self.build()
        path = self.tip("## Tip\n\nkeep me\n\n## Score\n\ngone\n\n## Provenance\n\nkeep me too\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=x")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("## Tip\n\nkeep me\n", after)
        self.assertIn("## Provenance\n\nkeep me too\n", after)
        self.assertNotIn("gone", after)

    # -- fenced code, which a tip is full of ----------------------------

    def test_a_fenced_heading_does_not_end_the_section_it_sits_in(self) -> None:
        """A tip is prose about commands, so a fenced block is the normal case.

        `body_headings` reads column 0 and would take the `## Score` inside
        this fence for a real heading, ending `## Tip` early and leaving the
        rest of somebody's code sample stranded in the section after it.
        """

        self.build()
        path = self.tip(
            "## Tip\n\nRun it:\n\n```markdown\n## Score\nnot a heading\n```\n\n"
            "## Score\n\nreal score\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Tip=replaced")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        # The fenced sample belonged to `## Tip` and went with it...
        self.assertNotIn("not a heading", after)
        # ...and the real `## Score` and its text are still there, once.
        self.assertIn("## Score\n\nreal score\n", after)
        self.assertEqual(after.count("## Score"), 1)

    def test_a_fenced_heading_is_not_the_section_that_gets_edited(self) -> None:
        self.build()
        path = self.tip("## Tip\n\n```markdown\n## Score\nfenced\n```\n\n## Score\n\nreal\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=written")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("```markdown\n## Score\nfenced\n```", after)
        self.assertIn("## Score\n\nwritten\n", after)

    def test_a_tilde_fence_does_not_close_a_backtick_fence(self) -> None:
        """A closing fence has to match the marker that opened it."""

        self.build()
        path = self.tip("## Tip\n\n```\n~~~\n## Score\nstill fenced\n```\n\n## Score\n\nreal\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=written")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("## Score\nstill fenced\n", path.read_text(encoding="utf-8"))

    def test_a_longer_fence_is_not_closed_by_a_shorter_one(self) -> None:
        """The way a tip quotes a fenced block: a ```` fence around a ``` one.

        Treating every run as equivalent closed the outer fence on the inner
        one, and the scanner then read the *fenced* `## Score` as the real
        heading -- so the section ran from inside the code sample to the end of
        the note, and one `set-section` would have deleted the rest of the
        sample, the closing fence, the real heading and its text together.
        CommonMark's rule is that a closing fence matches the character and is
        at least as long, with nothing but whitespace after it.
        """

        self.build()
        path = self.tip(
            "## Tip\n\n````markdown\n```\n## Score\n````\n\n## Score\n\nreal score\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=written")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        # The whole sample, both fences included, is still intact...
        self.assertIn("````markdown\n```\n## Score\n````\n", after)
        # ...and the edit landed on the real section, not the quoted one.
        self.assertIn("## Score\n\nwritten\n", after)
        self.assertNotIn("real score", after)

    def test_an_info_string_holding_a_backtick_does_not_open_a_fence(self) -> None:
        """A backtick fence's info string may not itself carry a backtick."""

        self.build()
        self.tip("## Tip\n\n```` `x` ````\n\n## Score\n\nreal\n")
        got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Score")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout, "real\n")

    # -- indentation, which Obsidian renders and column 0 misses ---------

    def test_an_indented_heading_is_the_section_it_looks_like(self) -> None:
        """CommonMark renders a heading indented by up to three spaces.

        A column-zero scan does not see `   ## Score`, so it would report the
        section absent and *create* a second one below the heading already on
        screen -- two `## Score` blocks in a note whose reader shows one.
        `parse_sections` already refuses this wider shape on the way in.
        """

        self.build()
        path = self.tip("## Tip\n\nt\n\n   ## Score\n\nindented\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=written")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(after.count("## Score"), 1, f"a second heading was created:\n{after}")
        self.assertNotIn("indented", after)
        self.assertIn("written", after)

    def test_an_indented_heading_ends_the_section_above_it(self) -> None:
        self.build()
        path = self.tip("## Tip\n\nmine\n\n  ## Provenance\n\nnot mine\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Tip=replaced")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("not mine", after)
        self.assertNotIn("mine\n\n  ## Provenance", after.replace("not mine", ""))

    def test_an_indented_heading_is_found_by_the_reader_too(self) -> None:
        self.build()
        self.tip("## Tip\n\nt\n\n   ## Score\n\nindented text\n")
        got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Score")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout, "indented text\n")

    def test_json_alongside_section_is_refused_rather_than_ignored(self) -> None:
        """A caller feeds `--section` output straight back to `set-section`.
        Quietly dropping a `--json` it asked for would hand back something it
        could not tell apart from an empty section."""

        self.build()
        self.tip("## Tip\n\nt\n")
        got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Tip", "--json")
        self.assertEqual(got.returncode, 2, got.stderr)
        self.assertIn("--json", got.stderr)

    # -- creation, without pack.py's anchor ------------------------------

    def test_a_declared_section_the_note_lacks_is_created_in_declared_order(self) -> None:
        self.build()
        path = self.tip("## Tip\n\ntip text\n\n## Provenance\n\nwhere from\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=8/10")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.headings(path), ["Tip", "Score", "Provenance"])
        self.assertIn("## Score\n\n8/10\n", path.read_text(encoding="utf-8"))

    def test_a_section_with_no_later_neighbour_is_appended(self) -> None:
        self.build()
        path = self.tip("## Tip\n\ntip text\n")
        done = self.run_sd(
            "store", "set-section", "pp.tip", "T", "--section", "Provenance=a link")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertEqual(self.headings(path), ["Tip", "Provenance"])
        self.assertTrue(after.endswith("## Provenance\n\na link\n"), repr(after[-60:]))

    def test_a_section_is_created_with_no_anchor_heading_present_at_all(self) -> None:
        """The case `pack.py` died on rather than handled."""

        self.build()
        path = self.tip("Just prose, and not one heading.\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=8")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("## Score\n\n8\n", after)
        self.assertIn("Just prose, and not one heading.\n", after)

    def test_an_appended_section_does_not_land_on_an_unterminated_last_line(self) -> None:
        self.build()
        path = self.tips / "T.md"
        path.write_text("---\nstatus: inbox\nscore: 7\n---\n\n## Tip\n\nno trailing newline",
                        encoding="utf-8")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("no trailing newline\n", path.read_text(encoding="utf-8"))
        self.assertEqual(self.headings(path), ["Tip", "Score"])

    def test_a_heading_the_manifest_does_not_declare_is_not_a_position(self) -> None:
        """An undeclared heading cannot be ordered against a declared one, so
        it is stepped over rather than guessed at."""

        self.build()
        path = self.tip("## Tip\n\nt\n\n## Notes\n\nhand-written\n\n## Provenance\n\np\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.headings(path), ["Tip", "Notes", "Score", "Provenance"])

    def test_an_emptied_section_is_a_heading_and_one_blank_line(self) -> None:
        """Not two. The blank after a heading and the blank before the next one
        are the same line when there is nothing between them."""

        self.build()
        path = self.tip("## Tip\n\ngone\n\n## Score\n\ns\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Tip=")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("## Tip\n\n## Score\n", after)
        self.assertNotIn("\n\n\n", after)

    def test_a_created_empty_section_is_the_same_shape(self) -> None:
        self.build()
        path = self.tip("## Tip\n\nt\n\n## Provenance\n\np\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("## Score\n\n## Provenance\n", after)
        self.assertNotIn("\n\n\n", after)

    # -- the read half ---------------------------------------------------

    def test_get_prints_only_the_named_section(self) -> None:
        self.build()
        self.tip("## Tip\n\nthe tip\n\n## Score\n\nthe score\n")
        got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Tip")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout, "the tip\n")

    def test_get_of_a_declared_but_absent_section_is_empty_and_exits_zero(self) -> None:
        """What makes read-edit-write cover creation."""

        self.build()
        self.tip("## Tip\n\nthe tip\n")
        got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Score")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(got.stdout, "")

    def test_get_of_a_section_the_kind_does_not_declare_is_refused(self) -> None:
        self.build()
        self.tip("## Tip\n\nthe tip\n")
        got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Nope")
        self.assertEqual(got.returncode, 1, got.stdout)
        self.assertIn("declares no section", got.stderr)

    def test_read_edit_write_appends_and_creates_the_section_on_first_use(self) -> None:
        """`pack.py topics add-feed`, with its second branch gone.

        That verb had one path to append a line to `## Feeds` and another to
        create the section when it was absent, anchored on a heading that might
        not be there. Here the absent section reads as empty, so appending to
        what came back does both -- and the second pass proves the append is
        an append and not a replace.
        """

        self.build()
        path = self.tip("## Tip\n\ntip text\n\n## Provenance\n\nsrc\n")
        for url in ("https://a.example/feed", "https://b.example/feed"):
            got = self.run_sd("store", "get", "pp.tip", "T", "--section", "Score")
            self.assertEqual(got.returncode, 0, got.stderr)
            kept = [line for line in got.stdout.splitlines() if line.strip()]
            kept.append(f"- {url}")
            done = self.run_sd("store", "set-section", "pp.tip", "T",
                               "--section", "Score=" + "\n".join(kept))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.headings(path), ["Tip", "Score", "Provenance"])
        self.assertIn(
            "## Score\n\n- https://a.example/feed\n- https://b.example/feed\n",
            path.read_text(encoding="utf-8"))

    # -- refusals --------------------------------------------------------

    def test_a_section_the_kind_does_not_declare_is_refused(self) -> None:
        self.build()
        self.tip("## Tip\n\nt\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Nope=x")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("declares no section", done.stderr)

    def test_a_kind_that_declares_no_sections_refuses_the_verb(self) -> None:
        self.build(kind=dict(TIP_KIND))
        self.tip("## Tip\n\nt\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Tip=x")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("declares no sections", done.stderr)

    def test_a_heading_carried_twice_is_refused_rather_than_guessed(self) -> None:
        """The rule `field_lines` applies to a duplicated key, applied to a
        duplicated heading: picking the first of two is a silent choice
        wearing the clothes of a fix."""

        self.build()
        self.tip("## Score\n\nfirst\n\n## Score\n\nsecond\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Score=x")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("refusing to guess which one is meant", done.stderr)

    def test_a_note_with_no_frontmatter_block_is_refused(self) -> None:
        self.build()
        (self.tips / "T.md").write_text("## Tip\n\nno block\n", encoding="utf-8")
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Tip=x")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("frontmatter", done.stderr)

    def test_a_missing_note_is_refused(self) -> None:
        self.build()
        done = self.run_sd("store", "set-section", "pp.tip", "Ghost", "--section", "Tip=x")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("no note titled", done.stderr)

    def test_giving_no_section_at_all_is_a_usage_error(self) -> None:
        """Exit 2, not 1: nothing about the vault is wrong."""

        self.build()
        self.tip("## Tip\n\nt\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T")
        self.assertEqual(done.returncode, 2, done.stdout)

    def test_only_the_file_spelling_still_takes_the_section_flag(self) -> None:
        """`--section-file` alone has to be enough. `required=True` on
        `--section` would have made this the error argparse reports."""

        self.build()
        self.tip("## Tip\n\nt\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T",
                           "--section-file", "Tip=" + self.file("t.txt", "from a file\n"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("## Tip\n\nfrom a file\n", (self.tips / "T.md").read_text(encoding="utf-8"))

    # -- the rest --------------------------------------------------------

    def test_several_sections_are_written_in_one_pass(self) -> None:
        """`pack.py` rewrote the file once per section, so an interrupted run
        left a note with some sections updated and some not."""

        self.build()
        path = self.tip("## Tip\n\na\n\n## Score\n\nb\n\n## Provenance\n\nc\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T",
                           "--section", "Tip=one", "--section", "Provenance=three")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = path.read_text(encoding="utf-8")
        self.assertIn("## Tip\n\none\n", after)
        self.assertIn("## Score\n\nb\n", after)
        self.assertIn("## Provenance\n\nthree\n", after)

    def test_a_backtick_survives_the_file_form_and_not_the_shell(self) -> None:
        """The same trap `--section-file` was added to `add` for: a backtick
        inside a double-quoted shell argument is a command substitution."""

        self.build()
        self.tip("## Tip\n\nold\n")
        text = "Use `sd store set-section` when the text carries a backtick.\n"
        done = self.run_sd("store", "set-section", "pp.tip", "T",
                           "--section-file", "Tip=" + self.file("tip.txt", text))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(text, (self.tips / "T.md").read_text(encoding="utf-8"))

    def test_section_text_carrying_its_own_heading_is_refused(self) -> None:
        self.build()
        self.tip("## Tip\n\nt\n")
        done = self.run_sd("store", "set-section", "pp.tip", "T",
                           "--section", "Tip=fine\n## Smuggled\nnot fine")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("carries its own `## ` heading", done.stderr)

    def test_writing_the_text_the_note_already_holds_changes_nothing(self) -> None:
        self.build()
        path = self.tip("## Tip\n\nthe same\n\n## Score\n\ns\n")
        before = path.read_bytes()
        done = self.run_sd("store", "set-section", "pp.tip", "T", "--section", "Tip=the same")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("already holds that text", done.stdout)
        self.assertEqual(path.read_bytes(), before)

    def test_a_crlf_note_comes_back_all_lf_rather_than_mixed(self) -> None:
        """Where the CRLF actually goes, which is not where it looks.

        `store_set_section` opens the note in text mode, so universal newlines
        turn `\\r\\n` into `\\n` before `edit_section` sees it -- the same thing
        `read_template` does to a template. The note is therefore rewritten
        all-LF rather than mixed, and this pins that; `edit_section`'s own
        ending handling is checked directly below, because no input the CLI can
        produce reaches it with a `\\r` still attached.
        """

        path = self.tips / "T.md"
        self.build()
        path.write_text(
            "---\r\nstatus: inbox\r\nscore: 7\r\n---\r\n\r\n## Tip\r\n\r\nold\r\n",
            encoding="utf-8", newline="")
        done = self.run_sd("store", "set-section", "pp.tip", "T",
                           "--section", "Score=first\nsecond")
        self.assertEqual(done.returncode, 0, done.stderr)
        raw = path.read_bytes()
        self.assertIn(b"## Score\n\nfirst\nsecond\n", raw)
        self.assertNotIn(b"\r", raw)

    def test_edit_section_takes_the_headings_own_line_ending(self) -> None:
        """Called directly, because the CLI normalises the only input it has.

        Hardcoding a newline here is what put two endings in one file when
        `fill_sections` did it, and `edit_field` carries the same rule. This is
        the third site, which is why `line_ending` is a named helper rather
        than a fourth copy of the expression.
        """

        edit_section = sd_module().edit_section
        note = "---\r\nstatus: inbox\r\n---\r\n\r\n## Tip\r\n\r\nold\r\n"
        replaced = edit_section(note, "Tip", "one\ntwo", ["Tip", "Score"])
        self.assertEqual(
            replaced, "---\r\nstatus: inbox\r\n---\r\n\r\n## Tip\r\n\r\none\r\ntwo\r\n")
        self.assertNotIn("\n", replaced.replace("\r\n", ""))

        created = edit_section(note, "Score", "s", ["Tip", "Score"])
        self.assertNotIn("\n", created.replace("\r\n", ""))
        self.assertIn("## Score\r\n\r\ns\r\n", created)



class MultiFieldSetTests(StoreFixture):
    """10b-iv: several fields, and sections beside them, in one atomic write.

    Three `pack.py` verbs move more than one frontmatter key per run -- `tips
    set-published` writes `status`, `url` and `used-by`, `ideas set-published`
    writes `status` and `url`, and `vault set-score` writes `score` alongside
    the `## Score` body. Each does it with one `open(w)`, so a note is never
    seen holding half of the change.

    A migration that spelled those as a sequence of `sd store set` calls would
    have introduced a state `pack.py` could not produce: `status: published`
    on a note with no `url`, because the second call refused or the process
    stopped between the two. That is a regression, not a refactor, which is
    why `set` takes the fields together rather than the callers taking turns.

    The property under test is therefore not "several fields can be given" --
    that much is visible from `--help`. It is that **nothing reaches the disk
    unless every field passes every refusal**, which is what the second case
    below actually measures.
    """

    ORDER = ["Tip", "Score", "Provenance"]

    def setUp(self) -> None:
        super().setUp()
        self.kind: dict[str, object] = {
            "fields": ["status", "score", "url", "used-by"],
            "initial-status": "inbox",
            "transitions": {"inbox": ["approved", "published"]},
            "floor": {"score": 6},
            "sections": {"order": list(self.ORDER), "template": "tip.md"},
        }

    def build(self) -> None:
        root = self.plugin(kinds={"tip": self.kind}, register=False)
        (root / "tip.md").write_text(
            "\n## Tip\n\n## Score\n\n## Provenance\n", encoding="utf-8")
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)

    def tip(self) -> pathlib.Path:
        """A note carrying both shapes `frontmatter()` cannot round-trip."""

        path = self.tips / "T.md"
        path.write_text(
            "---\n"
            "status: inbox\n"
            "score: 7\n"
            'description: "quoted, and the reader strips it"\n'
            "contexts:\n  - Personal\n  - Work\n"
            "---\n\n## Tip\n\nThe tip.\n\n## Score\n\nold breakdown\n\n## Provenance\n\nx\n",
            encoding="utf-8")
        return path

    # -- what the three deleted verbs needed ----------------------------

    def test_three_fields_land_in_one_call(self) -> None:
        """`pack.py tips set-published`, spelled on the backbone.

        `url` and `used-by` are absent from the note, so this also covers the
        insert path twice in a row: the second insert has to re-find the
        closing fence the first one moved.
        """

        self.build()
        path = self.tip()
        done = self.run_sd(
            "store", "set", "pp.tip", "T",
            "--field", "status=published",
            "--field", "url=https://example.com/p",
            "--field", "used-by=2026/slug")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = path.read_text(encoding="utf-8")
        self.assertIn("status: published\n", text)
        self.assertIn("url: https://example.com/p\n", text)
        self.assertIn("used-by: 2026/slug\n", text)
        # R11-D27 still holds across a multi-field write: the two shapes
        # `frontmatter()` cannot round-trip are untouched.
        self.assertIn('description: "quoted, and the reader strips it"\n', text)
        self.assertIn("contexts:\n  - Personal\n  - Work\n", text)

    def test_a_refusal_on_the_second_field_leaves_the_note_untouched(self) -> None:
        """The whole reason the fields travel together.

        `url` is valid and `score` is under the kind's floor. A handler that
        validated and wrote field by field would have written `url` before
        reaching the refusal, leaving the note in a state no single `pack.py`
        run could produce. The note is compared byte-for-byte, not key by key,
        because a partial write is exactly the thing a key-by-key comparison
        would be at risk of stepping over.
        """

        self.build()
        path = self.tip()
        before = path.read_bytes()
        done = self.run_sd(
            "store", "set", "pp.tip", "T",
            "--field", "url=https://example.com/p",
            "--field", "score=3")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_a_refusal_on_a_section_leaves_the_fields_unwritten(self) -> None:
        """The same property across the two kinds of edit.

        Sections are validated before any field is applied, so an undeclared
        section name stops a call whose fields were all fine.
        """

        self.build()
        path = self.tip()
        before = path.read_bytes()
        done = self.run_sd(
            "store", "set", "pp.tip", "T",
            "--field", "status=published",
            "--section", "Nope=text")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("no section 'Nope'", done.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_a_field_and_a_section_are_written_together(self) -> None:
        """`pack.py vault set-score`, which moved `score` and `## Score` at once."""

        self.build()
        path = self.tip()
        done = self.run_sd(
            "store", "set", "pp.tip", "T",
            "--field", "score=9",
            "--section", "Score=8 for reach, 9 for novelty")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = path.read_text(encoding="utf-8")
        self.assertIn("score: 9\n", text)
        self.assertIn("## Score\n\n8 for reach, 9 for novelty\n", text)
        self.assertNotIn("old breakdown", text)

    def test_a_value_from_a_file_reaches_the_same_refusals(self) -> None:
        """`--field-file` is the spelling for text a shell would mangle.

        It goes through `resolve_pair_files` into the same parser the inline
        form uses, so a file-supplied value under the floor is refused for the
        floor rather than accepted down a second path.
        """

        self.build()
        path = self.tip()
        before = path.read_bytes()
        low = self.tmp / "score.txt"
        low.write_text("3", encoding="utf-8")
        done = self.run_sd("store", "set", "pp.tip", "T", "--field-file", f"score={low}")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(path.read_bytes(), before)

    # -- the shorthand, kept ---------------------------------------------

    def test_the_positional_form_still_writes_one_field(self) -> None:
        """Every caller written before 10b-iv types this, and it is unchanged."""

        self.build()
        path = self.tip()
        done = self.run_sd("store", "set", "pp.tip", "T", "status", "approved")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("status: approved\n", path.read_text(encoding="utf-8"))

    def test_a_positional_field_with_no_value_is_a_usage_error(self) -> None:
        """Two `nargs="?"` positionals cannot express "both or neither"."""

        self.build()
        self.tip()
        done = self.run_sd("store", "set", "pp.tip", "T", "status")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("FIELD VALUE", done.stderr)

    # -- refusals ---------------------------------------------------------

    def test_neither_a_field_nor_a_section_is_a_usage_error(self) -> None:
        self.build()
        self.tip()
        done = self.run_sd("store", "set", "pp.tip", "T")
        self.assertEqual(done.returncode, 2, done.stderr)

    def test_the_same_field_twice_is_refused(self) -> None:
        """`parse_assignments` already calls a repeated `=` a typo, and it is."""

        self.build()
        self.tip()
        done = self.run_sd(
            "store", "set", "pp.tip", "T", "--field", "score=7", "--field", "score=8")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("given twice", done.stderr)

    def test_append_cannot_build_a_list_on_set(self) -> None:
        """`add` renders the whole block and can write a sequence; `set` edits
        one line, and one line is not a sequence."""

        self.build()
        path = self.tip()
        before = path.read_bytes()
        done = self.run_sd("store", "set", "pp.tip", "T", "--field", "used-by+=a")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("block sequence", done.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_an_undeclared_field_is_refused_with_the_declared_ones(self) -> None:
        self.build()
        self.tip()
        done = self.run_sd("store", "set", "pp.tip", "T", "--field", "nope=1")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("declares no field 'nope'", done.stderr)

    def test_a_bad_transition_is_judged_against_the_note_on_disk(self) -> None:
        """Not against a value supplied in the same call.

        `status` is read from the note before any edit is applied, so the
        transition is checked against what the note actually holds.
        """

        self.build()
        path = self.tip()
        before = path.read_bytes()
        done = self.run_sd(
            "store", "set", "pp.tip", "T",
            "--field", "status=declined", "--field", "url=https://x")
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(path.read_bytes(), before)


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

    def test_a_comment_between_the_key_and_its_items_does_not_hide_them(self) -> None:
        """A YAML comment is not a value, and returning on one stepped over the
        sequence it precedes -- the guard allowed the edit that orphans it."""

        self.plugin(kinds={"tip": dict(LIST_KIND)})
        path = self.note("T", extra="contexts:\n# where these came from\n  - Personal\n")
        before = path.read_bytes()
        done = self.run_sd("store", "set", "pp.tip", "T", "contexts", "Shared")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("holds a list", done.stderr)
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



class FullListingTests(StoreFixture):
    """`--full`: the whole note set in one call, which step 9 needs.

    `pack.py topics list --status active --full` printed every active topic's
    body, and the research routines read `## Covers`, `## Feeds` and
    `## Ground truth` out of it. Without this, retargeting them at `sd` turned
    one call into a listing plus one `get` per topic -- ten calls for nine
    topics, handed to an unattended run.
    """

    def setUp(self) -> None:
        super().setUp()
        self.plugin()
        self.note("Kept", status="approved", body="## Covers\n\nWhat it covers.\n")
        self.note("Dropped", status="declined", body="## Covers\n\nNot this one.\n")

    def test_full_prints_each_body(self) -> None:
        done = self.run_sd("store", "list", "pp.tip", "--full")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("What it covers.", done.stdout)
        self.assertIn("Not this one.", done.stdout)

    def test_without_full_no_body_is_printed(self) -> None:
        """The default stays a table. `--full` is opt-in, not a widening."""

        done = self.run_sd("store", "list", "pp.tip")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("What it covers.", done.stdout)

    def test_full_json_carries_a_body_per_row(self) -> None:
        done = self.run_sd("store", "list", "pp.tip", "--full", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = {row["title"]: row for row in json.loads(done.stdout)}
        self.assertIn("What it covers.", rows["Kept"]["body"])
        self.assertIn("Not this one.", rows["Dropped"]["body"])

    def test_json_without_full_has_no_body_key(self) -> None:
        done = self.run_sd("store", "list", "pp.tip", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        for row in json.loads(done.stdout):
            self.assertNotIn("body", row)

    def test_each_note_is_followed_by_a_blank_line(self) -> None:
        """`pack.py`'s shape, kept deliberately.

        The routines step 9 retargets read this output as prose. A note whose
        body ends without a trailing newline would run straight into the next
        `===` header, so the separator is part of the format rather than
        incidental spacing.
        """

        # A note whose file does not end in a newline is the case that breaks
        # this: `print()` then only terminates its last line, and the next
        # header follows with no separator at all.
        (self.tips / "Ragged.md").write_text(
            "---\nstatus: approved\nscore: 7\n---\n\nNo trailing newline.",
            encoding="utf-8")
        done = self.run_sd("store", "list", "pp.tip", "--full")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("No trailing newline.\n\n", done.stdout)
        for chunk in done.stdout.split("=== ")[1:]:
            self.assertTrue(chunk.endswith("\n\n"), repr(chunk[-20:]))

    def test_full_still_honours_the_status_filter(self) -> None:
        done = self.run_sd("store", "list", "pp.tip", "--full", "--status", "approved")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("What it covers.", done.stdout)
        self.assertNotIn("Not this one.", done.stdout)

    def test_full_does_not_widen_the_fields_to_undeclared_keys(self) -> None:
        """The deliberate difference from `store get`, which reports every key.

        `get` names one note, so a field the manifest has not caught up with is
        the answer to the question asked. A listing is a table, and a row that
        grows a column per note stops being one -- so `--full` adds the body
        and nothing else.
        """

        self.note("Extra", status="approved", extra="undeclared: surprise\n")
        done = self.run_sd("store", "list", "pp.tip", "--full", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = {row["title"]: row for row in json.loads(done.stdout)}
        self.assertNotIn("undeclared", rows["Extra"])
        self.assertEqual(sorted(rows["Extra"]), ["body", "score", "status", "title"])


class VaultWideTitleTests(StoreFixture):
    """`pack.py`'s `vault_title_taken`, which the retarget would have dropped.

    A vault's titles share one namespace -- an Obsidian wikilink resolves on
    the filename alone -- so `pack.py` refuses a title held anywhere, not just
    in the kind's own base. Step 9 retargets the routine that relied on it.
    """

    def setUp(self) -> None:
        super().setUp()
        kind: dict[str, object] = {
            "fields": ["status", "score"],
            "initial-status": "inbox",
            "transitions": {"inbox": ["approved", "declined"]},
            "sections": {"order": ["Tip"], "template": "tip.md"},
        }
        root = self.plugin(kinds={"tip": kind}, register=False)
        (root / "tip.md").write_text("\n## Tip\n", encoding="utf-8")
        self.assertEqual(self.run_sd("plugin", "add", str(root)).returncode, 0)

    def elsewhere(self, relative: str, name: str) -> pathlib.Path:
        where = self.vault / relative
        where.mkdir(parents=True, exist_ok=True)
        path = where / f"{name}.md"
        path.write_text("---\nstatus: inbox\n---\n\nSomewhere else.\n", encoding="utf-8")
        return path

    def add(self, title: str) -> subprocess.CompletedProcess[str]:
        return self.run_sd("store", "add", "pp.tip", title, "--field", "score=7")

    def test_a_title_held_in_another_directory_is_refused(self) -> None:
        self.elsewhere("Learning", "Shared name")
        done = self.add("Shared name")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("title collision", done.stderr)
        self.assertIn("Learning/Shared name.md", done.stderr)
        self.assertFalse((self.tips / "Shared name.md").exists())

    def test_a_free_title_is_written(self) -> None:
        self.elsewhere("Learning", "Something else")
        done = self.add("Shared name")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.tips / "Shared name.md").exists())

    def test_a_copy_in_a_dot_directory_does_not_count(self) -> None:
        """Obsidian's `.trash` holds deleted notes; nothing links to them.

        `pack.py` names seven dot-directories and skips all of them, so the
        rule here is the generalisation rather than the list.
        """

        self.elsewhere(".trash", "Shared name")
        done = self.add("Shared name")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.tips / "Shared name.md").exists())

    def test_the_kinds_own_base_is_still_refused(self) -> None:
        self.assertEqual(self.add("Twice").returncode, 0)
        done = self.add("Twice")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("already exists", done.stderr)

    def test_a_directory_it_cannot_read_refuses_rather_than_passing(self) -> None:
        """The one way this guard could be worse than not having it.

        `os.walk` swallows per-directory errors by default, so an unreadable
        directory hiding a colliding title would come back as "free" and the
        note would be written. macOS answers an ungranted `~/Documents` read
        the same way -- empty rather than failing -- which would make every
        collision check pass vacuously on a vault behind a missing TCC grant.
        """

        held = self.elsewhere("Locked", "Shared name")
        locked = held.parent
        locked.chmod(0o000)
        self.addCleanup(locked.chmod, 0o755)
        done = self.add("Shared name")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("cannot scan", done.stderr)
        self.assertFalse((self.tips / "Shared name.md").exists())

    def test_a_vault_root_that_is_not_there_refuses(self) -> None:
        """Refused by the driver before the scan runs, which is why the scan
        does not repeat the check: an unreachable guard is one no test reaches."""

        done = self.run_sd(
            "store", "add", "pp.tip", "Anything", "--field", "score=7",
            vault=str(self.tmp / "no-such-vault"))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("vault path does not exist", done.stderr)

    def test_the_existing_note_is_left_alone(self) -> None:
        """A refused `add` must not have written anything on its way to refusing."""

        held = self.elsewhere("Learning", "Shared name")
        before = held.read_text(encoding="utf-8")
        self.assertEqual(self.add("Shared name").returncode, 1)
        self.assertEqual(held.read_text(encoding="utf-8"), before)

    def test_add_probes_the_vault_once_and_not_once_per_use_of_the_root(self) -> None:
        """`store add` needs the vault root twice; it may only probe for it once.

        `store_root` ends in `vault_reason`, which lists the vault in a bounded
        child process. That is not a cheap call: it spawns an interpreter, and
        against an ungranted vault it is fifteen seconds of waiting. `add`
        resolves the root for the kind's base and again for the vault-wide
        title scan, and resolving it twice paid for the probe twice. This runs
        `add` in-process so the calls can be counted; every other case in this
        class runs the real command.
        """

        self.elsewhere("Learning", "Neighbour")
        sd = sd_module()
        calls: list[pathlib.Path] = []
        real = sd.vault_reason

        def counted(root: pathlib.Path) -> str:
            calls.append(root)
            return real(root)

        sd.vault_reason = counted
        self.addCleanup(setattr, sd, "vault_reason", real)
        before = {name: os.environ.get(name) for name in ("XDG_CONFIG_HOME", "OBSIDIAN_VAULT")}
        self.addCleanup(lambda: [os.environ.__setitem__(name, value) if value is not None
                                 else os.environ.pop(name, None)
                                 for name, value in before.items()])
        os.environ["XDG_CONFIG_HOME"] = str(self.config_home)
        os.environ["OBSIDIAN_VAULT"] = str(self.vault)

        self.assertEqual(sd.main(["store", "add", "pp.tip", "Fresh", "--field", "score=7"]), 0)
        self.assertEqual(len(calls), 1, f"probed the vault {len(calls)} times")
        self.assertTrue((self.tips / "Fresh.md").exists())


if __name__ == "__main__":
    unittest.main()
