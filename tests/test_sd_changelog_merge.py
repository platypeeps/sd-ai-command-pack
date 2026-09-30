"""`sd_changelog_merge.resolve_keep_both` against real git merges (sd:2174).

`tests/test_sd_ship.py` covers the catch-up end to end. These cases pin the
blank-line handling at the hunk edges, which decides whether two entries come
out one blank line apart, run together, or two apart.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import sd_changelog_merge  # noqa: E402

BASE = "# Changelog\n\n## Unreleased\n\n### Fixed\n\n- **Old.** Kept.\n\n### Added\n\n- **Older.** Kept.\n"


class KeepBoth(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.git("init", "-q", "--initial-branch=main", ".")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "user.name", "Fixture")

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True, check=False)

    def commit(self, files: dict[str, str]) -> None:
        for name, text in files.items():
            (self.root / name).write_text(text, encoding="utf-8")
        self.git("add", "--", *files)
        self.assertEqual(self.git("commit", "-qm", "change").returncode, 0)

    def commit_bytes(self, text: str) -> None:
        """Commit CHANGELOG.md as UTF-16, which git merges as a binary file."""
        (self.root / "CHANGELOG.md").write_bytes(text.encode("utf-16"))
        self.git("add", "--", "CHANGELOG.md")
        self.assertEqual(self.git("commit", "-qm", "change").returncode, 0)

    def merge(self, ours: dict[str, str], theirs: dict[str, str], base: dict[str, str] | None = None) -> bool:
        self.commit(base or {"CHANGELOG.md": BASE})
        self.git("checkout", "-qb", "other")
        self.commit(theirs)
        self.git("checkout", "-q", "main")
        self.commit(ours)
        self.assertNotEqual(self.git("merge", "-q", "--no-edit", "other").returncode, 0, "the fixture must conflict")
        return sd_changelog_merge.resolve_keep_both(self.root)

    def resolved(self, ours: str, theirs: str) -> str:
        self.assertTrue(self.merge({"CHANGELOG.md": ours}, {"CHANGELOG.md": theirs}))
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "")
        return (self.root / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_entries_followed_by_a_blank_line_come_out_one_blank_line_apart(self):
        text = self.resolved(BASE.replace("- **Old.**", "- **A.** a.\n  a2.\n\n- **Old.**"),
                             BASE.replace("- **Old.**", "- **B.** b.\n\n- **Old.**"))
        self.assertIn("### Fixed\n\n- **A.** a.\n  a2.\n\n- **B.** b.\n\n- **Old.** Kept.\n", text)

    def test_entries_written_before_their_blank_line_come_out_one_blank_line_apart(self):
        text = self.resolved(BASE.replace("### Fixed\n\n", "### Fixed\n\n- **A.** a.\n\n"),
                             BASE.replace("### Fixed\n\n", "### Fixed\n\n- **B.** b.\n\n"))
        self.assertIn("### Fixed\n\n- **A.** a.\n\n- **B.** b.\n\n- **Old.** Kept.\n", text)

    def test_entries_at_the_end_of_a_section(self):
        text = self.resolved(BASE.replace("- **Old.** Kept.\n", "- **Old.** Kept.\n\n- **A.** a.\n"),
                             BASE.replace("- **Old.** Kept.\n", "- **Old.** Kept.\n\n- **B.** b.\n"))
        self.assertIn("- **Old.** Kept.\n\n- **A.** a.\n\n- **B.** b.\n\n### Added\n", text)

    def test_two_sections_each_resolved(self):
        ours = BASE.replace("### Fixed\n\n", "### Fixed\n\n- **A.** a.\n\n").replace(
            "### Added\n\n", "### Added\n\n- **C.** c.\n\n")
        theirs = BASE.replace("### Fixed\n\n", "### Fixed\n\n- **B.** b.\n\n").replace(
            "### Added\n\n", "### Added\n\n- **D.** d.\n\n")
        text = self.resolved(ours, theirs)
        self.assertIn("- **A.** a.\n\n- **B.** b.\n\n- **Old.**", text)
        self.assertIn("- **C.** c.\n\n- **D.** d.\n\n- **Older.**", text)
        self.assertNotIn("\n\n\n", text)

    def test_a_setext_underline_is_content_not_a_marker(self):
        base = "Changelog\n=======\n\n- **Old.** Kept.\n"
        self.assertTrue(self.merge({"CHANGELOG.md": base.replace("- **Old.**", "- **A.** a.\n\n- **Old.**")},
                                   {"CHANGELOG.md": base.replace("- **Old.**", "- **B.** b.\n\n- **Old.**")},
                                   base={"CHANGELOG.md": base}))
        self.assertEqual((self.root / "CHANGELOG.md").read_text(encoding="utf-8"),
                         "Changelog\n=======\n\n- **A.** a.\n\n- **B.** b.\n\n- **Old.** Kept.\n")

    def test_an_edit_on_both_sides_is_left_alone(self):
        self.assertFalse(self.merge({"CHANGELOG.md": BASE.replace("Kept.\n\n###", "Ours.\n\n###")},
                                    {"CHANGELOG.md": BASE.replace("Kept.\n\n###", "Theirs.\n\n###")}))
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "CHANGELOG.md\n")
        self.assertIn("<<<<<<< HEAD", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_another_unmerged_path_is_left_alone(self):
        self.assertFalse(self.merge(
            {"CHANGELOG.md": BASE.replace("### Fixed\n\n", "### Fixed\n\n- **A.** a.\n\n"), "src.py": "a = 1\n"},
            {"CHANGELOG.md": BASE.replace("### Fixed\n\n", "### Fixed\n\n- **B.** b.\n\n"), "src.py": "a = 2\n"},
            base={"CHANGELOG.md": BASE, "src.py": "a = 0\n"}))
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "CHANGELOG.md\nsrc.py\n")

    def test_a_binary_changelog_is_left_alone(self):
        # `git merge-file` exits 255 on binary input with nothing on stdout;
        # read as a conflict count, that emptied CHANGELOG.md and staged it.
        self.commit_bytes(BASE)
        self.git("checkout", "-qb", "other")
        self.commit_bytes(BASE.replace("### Fixed\n\n", "### Fixed\n\n- **B.** b.\n\n"))
        self.git("checkout", "-q", "main")
        self.commit_bytes(BASE.replace("### Fixed\n\n", "### Fixed\n\n- **A.** a.\n\n"))
        self.assertNotEqual(self.git("merge", "-q", "--no-edit", "other").returncode, 0, "the fixture must conflict")
        before = (self.root / "CHANGELOG.md").read_bytes()
        self.assertFalse(sd_changelog_merge.resolve_keep_both(self.root))
        self.assertEqual((self.root / "CHANGELOG.md").read_bytes(), before)
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "CHANGELOG.md\n")

    def stubbed_merge_file(self, answer) -> bool:
        """`merge` with `git merge-file`'s real result replaced by `answer(result)`."""
        real = sd_changelog_merge._git

        def stub(root, *args):
            result = real(root, *args)
            return answer(result) if args[0] == "merge-file" else result

        with unittest.mock.patch.object(sd_changelog_merge, "_git", stub):
            return self.merge({"CHANGELOG.md": BASE.replace("### Fixed\n\n", "### Fixed\n\n- **A.** a.\n\n")},
                              {"CHANGELOG.md": BASE.replace("### Fixed\n\n", "### Fixed\n\n- **B.** b.\n\n")})

    def assert_untouched(self):
        self.assertIn("<<<<<<< HEAD", (self.root / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertEqual(self.git("diff", "--name-only", "--diff-filter=U").stdout, "CHANGELOG.md\n")

    def test_an_error_exit_is_not_a_conflict_count(self):
        # 255 is an error, whatever stdout holds: here a hunk that would resolve.
        self.assertFalse(self.stubbed_merge_file(lambda result: subprocess.CompletedProcess(
            result.args, 255, result.stdout, b"error: Cannot merge binary files")))
        self.assert_untouched()

    def test_a_conflict_count_with_no_hunk_writes_nothing(self):
        # Resolving output with no hunk wrote an empty CHANGELOG.md and staged it.
        self.assertFalse(self.stubbed_merge_file(lambda result: subprocess.CompletedProcess(
            result.args, 1, b"", b"")))
        self.assert_untouched()

    def test_a_nested_changelog_is_not_the_root_one(self):
        (self.root / "docs").mkdir()
        path = "docs/CHANGELOG.md"
        self.assertFalse(self.merge({path: BASE.replace("### Fixed\n\n", "### Fixed\n\n- **A.** a.\n\n")},
                                    {path: BASE.replace("### Fixed\n\n", "### Fixed\n\n- **B.** b.\n\n")},
                                    base={path: BASE}))


if __name__ == "__main__":
    unittest.main()
