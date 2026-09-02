"""`migrate-golden-corpus`: the baseline is only worth having if it catches things.

Every case here builds a throwaway vault, records it, damages it in one
specific way, and requires the damage to be named. A baseline that reports
success on a corrupted corpus is worse than no baseline, because step 11 would
be signed off against it.

`SD_GOLDEN_CORPUS` and `OBSIDIAN_VAULT` are pointed into a temporary directory
for every case, so neither the developer's vault nor a real baseline is ever
read or written. The committed root file is the one thing the tool writes
inside the repository; each case redirects it with `--root-file`-equivalent
monkeypatching of the module constant, so the tracked file is never touched.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import pathlib
import tempfile
import unittest
import unittest.mock

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "bin" / "migrate-golden-corpus"


def load_tool():
    """The tool as a module, so a case can redirect where it writes."""

    loader = importlib.machinery.SourceFileLoader("migrate_golden_corpus", str(TOOL))
    spec = importlib.util.spec_from_file_location(
        "migrate_golden_corpus", str(TOOL), loader=loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class GoldenCorpusTests(unittest.TestCase):
    """A vault of three notes across two bases, recorded and then damaged."""

    def setUp(self) -> None:
        self.tool = load_tool()
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        home = pathlib.Path(holder.name)

        self.vault = home / "vault"
        self.baseline = home / "baseline"
        self.root_file = home / "golden-corpus.root"
        self.bases_file = home / "bases.txt"
        self.tool.BASES_FILE = self.bases_file
        self.tool.ROOT_FILE = self.root_file

        for base in ("Notes", "Deep"):
            (self.vault / base).mkdir(parents=True)
        self.bases_file.write_text("# a comment\n\nNotes\nDeep\n", encoding="utf-8")
        self.write("Notes/One.md", "one\n")
        self.write("Notes/Two.md", "two\n")
        (self.vault / "Deep" / "Under").mkdir()
        self.write("Deep/Under/Three.md", "three\n")

        self.environ = {"OBSIDIAN_VAULT": str(self.vault),
                        "SD_GOLDEN_CORPUS": str(self.baseline)}
        patcher = unittest.mock.patch.dict("os.environ", self.environ, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, relative: str, text: str) -> pathlib.Path:
        path = self.vault / relative
        path.write_text(text, encoding="utf-8")
        return path

    def run_tool(self, *argv: str) -> int:
        """The tool's own reporting is swallowed; these cases assert on exit codes.

        What it prints is for an operator standing at a terminal mid-migration,
        and a suite that let it through would bury the one line that matters.
        """

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.tool.main(list(argv))
        self.reported = out.getvalue() + err.getvalue()
        return code

    def capture(self) -> None:
        self.assertEqual(self.run_tool("capture"), 0)

    # -- the recording itself ------------------------------------------------

    def test_a_capture_records_every_note_under_every_base_recursively(self) -> None:
        """`Deep/Under/Three.md` is the case: bases are scanned, not listed."""

        self.capture()
        manifest = (self.baseline / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(len(manifest.splitlines()), 3)
        self.assertIn("Deep/Under/Three.md", manifest)
        self.assertEqual(self.tool.read_root_field("notes"), "3")

    def test_the_recorded_bodies_are_the_bytes_and_not_a_rewrite(self) -> None:
        """The copy is the left-hand side of a later diff, so it must be exact."""

        self.write("Notes/One.md", "---\ncontexts:\n  - Personal\n---\n\nbody\t \n")
        self.capture()
        kept = self.baseline / "bodies" / "Notes" / "One.md"
        self.assertEqual(kept.read_bytes(), (self.vault / "Notes" / "One.md").read_bytes())

    def test_a_second_capture_refuses_rather_than_replacing_the_evidence(self) -> None:
        """Re-capturing after a bad move is exactly how a baseline stops meaning anything."""

        self.capture()
        self.assertEqual(self.run_tool("capture"), 2)
        self.assertEqual(self.run_tool("capture", "--recapture"), 0)

    # -- what verify has to catch --------------------------------------------

    def test_an_unchanged_vault_verifies(self) -> None:
        """The positive control. Without it every case below could pass by always failing."""

        self.capture()
        self.assertEqual(self.run_tool("verify"), 0)

    def test_a_single_edited_byte_is_caught_and_the_note_is_named(self) -> None:
        self.capture()
        self.write("Notes/Two.md", "two")          # the trailing newline, and nothing else
        self.assertEqual(self.run_tool("verify"), 1)
        self.assertIn("changed: Notes/Two.md", self.reported)
        self.assertNotIn("Notes/One.md", self.reported)

    def test_a_note_that_disappeared_in_the_move_is_caught(self) -> None:
        self.capture()
        (self.vault / "Notes" / "One.md").unlink()
        self.assertEqual(self.run_tool("verify"), 1)
        self.assertIn("missing: Notes/One.md", self.reported)

    def test_a_note_that_appeared_during_the_move_is_caught(self) -> None:
        """An unrecorded note is a failure too: a move that duplicates is a move that lied."""

        self.capture()
        self.write("Notes/Four.md", "four\n")
        self.assertEqual(self.run_tool("verify"), 1)
        self.assertIn("unrecorded: Notes/Four.md", self.reported)

    def test_a_base_that_stopped_existing_is_an_error_not_an_empty_result(self) -> None:
        """The loudest thing a move can do wrong, and the easiest to skip past."""

        self.capture()
        for note in (self.vault / "Deep").rglob("*.md"):
            note.unlink()
        (self.vault / "Deep" / "Under").rmdir()
        (self.vault / "Deep").rmdir()
        self.assertEqual(self.run_tool("verify"), 2)
        self.assertIn("'Deep' is not a directory", self.reported)

    def test_a_baseline_edited_to_match_a_damaged_vault_is_caught(self) -> None:
        """The tamper case, and the whole reason a root hash is committed at all.

        A manifest is a local file, so it can be rewritten to agree with
        whatever the vault now says. Rewriting it here to hold the damaged
        note's hash would make every path-by-path comparison pass. The
        committed root is checked first for that reason.
        """

        self.capture()
        self.write("Notes/Two.md", "damaged\n")
        manifest = self.baseline / "manifest.sha256"
        digest = hashlib.sha256(b"damaged\n").hexdigest()
        rewritten = [line for line in manifest.read_text(encoding="utf-8").splitlines()
                     if not line.endswith("Notes/Two.md")]
        rewritten.append(f"{digest}  Notes/Two.md")
        manifest.write_text("".join(f"{line}\n" for line in sorted(rewritten)), encoding="utf-8")
        self.assertEqual(self.run_tool("verify"), 1)
        self.assertIn("does not match the committed root", self.reported)
        # The tamper is caught *instead of* the per-note comparison, not after
        # it: an authenticated manifest is a precondition for trusting any of
        # the rows in it.
        self.assertNotIn("changed:", self.reported)

    def test_verify_before_any_capture_refuses_instead_of_passing(self) -> None:
        """An absent baseline must never read as "nothing changed"."""

        self.assertEqual(self.run_tool("verify"), 2)

    # -- the committed side ---------------------------------------------------

    def test_the_committed_root_names_no_note(self) -> None:
        """This repository is public and a note's path is its title.

        The manifest stays out of the repository for that reason, and this is
        the check that the file which does get committed did not quietly grow
        a path column.
        """

        self.capture()
        written = self.root_file.read_text(encoding="utf-8")
        for _, path in self.tool.scan(self.vault, ["Notes", "Deep"]):
            self.assertNotIn(path, written)
            self.assertNotIn(pathlib.Path(path).name, written)
        self.assertEqual(sorted(line.split()[0] for line in written.splitlines()),
                         ["bases", "captured", "notes", "root"])

    def test_the_root_is_a_hash_of_the_manifest_and_moves_when_it_does(self) -> None:
        self.capture()
        manifest = (self.baseline / "manifest.sha256").read_text(encoding="utf-8")
        self.assertEqual(self.tool.read_root_field("root"),
                         hashlib.sha256(manifest.encode("utf-8")).hexdigest())
        before = self.tool.read_root_field("root")
        self.write("Notes/One.md", "changed\n")
        self.assertEqual(self.run_tool("capture", "--recapture"), 0)
        self.assertNotEqual(self.tool.read_root_field("root"), before)

    def test_the_manifest_is_ordered_by_path_not_by_the_filesystem(self) -> None:
        """The root hash is over the manifest, so an unstable order is an unstable root."""

        self.capture()
        rows = (self.baseline / "manifest.sha256").read_text(encoding="utf-8").splitlines()
        paths = [line.split("  ", 1)[1] for line in rows]
        self.assertEqual(paths, sorted(paths))


class CommittedBaseListTests(unittest.TestCase):
    """The tracked list, checked as the data it is."""

    def test_every_line_is_a_relative_path_and_the_list_has_no_duplicates(self) -> None:
        text = (REPO_ROOT / "tests" / "fixtures" / "golden-corpus-bases.txt").read_text(
            encoding="utf-8")
        bases = [line.strip() for line in text.splitlines()
                 if line.strip() and not line.startswith("#")]
        self.assertEqual(len(bases), len(set(bases)), "a base is listed twice")
        for base in bases:
            self.assertFalse(base.startswith("/"), f"{base} is absolute")
            self.assertNotIn("..", pathlib.PurePosixPath(base).parts, f"{base} climbs out")


if __name__ == "__main__":
    unittest.main()
