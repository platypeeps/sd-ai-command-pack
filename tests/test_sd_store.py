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


if __name__ == "__main__":
    unittest.main()
