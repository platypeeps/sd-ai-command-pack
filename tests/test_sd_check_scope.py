"""`sd-check --base`: a declared docs-only scope runs only the docs command (sd:2072).

Real repositories and the real executable, as `test_sd_check` runs them. The
full check in every fixture fails on purpose, so a run that passes proves the
full check did not run, and a run that fails proves it did.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from tests.test_sd_check import PY, CheckFixture

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bin"))
import sd_check_scope  # noqa: E402
import sd_lib  # noqa: E402

FAILING = f"{PY} -c 'raise SystemExit(3)'"
PASSING_DOCS = ["python3", "-c", "print('docs ok')"]


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, text=True).stdout.strip()


class DocsScope(CheckFixture):
    def repo(self, docs_command: list[str] | None = None, docs_paths: list[str] | None = None,
             declare: bool = True, name: str = "repo", docs_tools: list[str] | None = None) -> pathlib.Path:
        root = self.make_repo(name)
        self.declare(root, check=FAILING)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
        (root / "docs").mkdir()
        (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
        if declare:
            (root / ".github").mkdir()
            (root / ".github" / "sd-check-scope.json").write_text(json.dumps({
                "schema_version": 1, "docs_paths": docs_paths or ["docs/**", "*.md"],
                "docs_command": docs_command or PASSING_DOCS,
                **({"docs_tools": docs_tools} if docs_tools is not None else {})}), encoding="utf-8")
        git(root, "add", "src", "docs", *([".github"] if declare else []))
        git(root, "commit", "-q", "-m", "base")
        git(root, "checkout", "-q", "-b", "topic")
        return root

    def change(self, root: pathlib.Path, path: str, text: str = "changed\n") -> None:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        git(root, "add", path)
        git(root, "commit", "-q", "-m", f"change {path}")

    def test_a_docs_only_change_runs_only_the_docs_command(self) -> None:
        root = self.repo()
        self.change(root, "docs/guide.md")
        self.change(root, "README.md")
        result = self.run_json(root, "--base", "main")
        self.assertEqual((result["_exit"], result["status"]), (0, "pass"))
        self.assertEqual(result["scope"]["mode"], "docs-only")
        rows = {row["name"]: row for row in result["checks"]}
        self.assertEqual((rows["check"]["status"], rows["check"]["reason"]), ("skipped", "docs-only scope"))
        self.assertEqual((rows["docs"]["status"], rows["docs"]["command"]), ("pass", PASSING_DOCS))
        self.assertIn("docs ok", rows["docs"]["stdout"])

    def test_the_human_report_names_the_scope(self) -> None:
        root = self.repo()
        self.change(root, "docs/guide.md")
        completed = self.run_check(root, "--base", "main")
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("scope: docs-only", completed.stdout)

    def test_a_failing_docs_command_fails_the_run(self) -> None:
        root = self.repo(docs_command=["python3", "-c", "raise SystemExit(4)"])
        self.change(root, "docs/guide.md")
        result = self.run_json(root, "--base", "main")
        self.assertEqual((result["_exit"], result["status"]), (1, "fail"))
        self.assertEqual({row["name"]: row["status"] for row in result["checks"]}["docs"], "fail")

    def test_a_code_path_in_the_range_runs_the_full_check(self) -> None:
        root = self.repo()
        self.change(root, "docs/guide.md")
        self.change(root, "src/app.py", "x = 2\n")
        result = self.run_json(root, "--base", "main")
        self.assertEqual((result["_exit"], result["scope"]["mode"]), (1, "full"))
        self.assertIn("src/app.py is not a docs path", result["scope"]["reason"])
        self.assertNotIn("docs", {row["name"] for row in result["checks"]})

    def test_a_change_to_what_decides_the_check_forces_the_full_check(self) -> None:
        """Even where every changed path matches `docs_paths`, these files decide what the check is."""
        for index, path in enumerate((".github/sd-check-scope.json", "Makefile", "sub/rules.mk", "scripts/docs.sh")):
            with self.subTest(path=path):
                root = self.repo(docs_paths=["**"], docs_command=["sh", "scripts/docs.sh"], name=f"repo{index}")
                text = (root / path).read_text(encoding="utf-8") + " " if (root / path).exists() else "x\n"
                self.change(root, path, text)
                result = self.run_json(root, "--base", "main")
                self.assertEqual((result["_exit"], result["scope"]["mode"]), (1, "full"), result["scope"])
                self.assertIn("decides what the check runs", result["scope"]["reason"])

    def test_a_rename_across_the_docs_boundary_is_not_docs_only(self) -> None:
        """Both sides of a rename count: moving code into `docs/` removes it from where the check reads it."""
        for index, (source, target) in enumerate((("docs/guide.md", "src/guide.py"), ("src/app.py", "docs/app.py"))):
            with self.subTest(source=source, target=target):
                root = self.repo(name=f"repo{index}")
                git(root, "mv", source, target)
                git(root, "commit", "-q", "-m", "move")
                self.assertEqual(self.run_json(root, "--base", "main")["scope"]["mode"], "full")

    def test_no_declaration_is_todays_behaviour(self) -> None:
        root = self.repo(declare=False)
        self.change(root, "docs/guide.md")
        result = self.run_json(root, "--base", "main")
        self.assertEqual((result["_exit"], result["scope"]["mode"]), (1, "full"))
        self.assertIn("no .github/sd-check-scope.json", result["scope"]["reason"])

    def test_without_base_the_declaration_changes_nothing(self) -> None:
        root = self.repo()
        self.change(root, "docs/guide.md")
        result = self.run_json(root)
        self.assertEqual((result["_exit"], result["scope"]["mode"]), (1, "full"))

    def test_an_empty_range_runs_the_full_check(self) -> None:
        root = self.repo()
        self.assertEqual(self.run_json(root, "--base", "main")["scope"]["mode"], "full")

    def test_a_malformed_declaration_is_a_configuration_error(self) -> None:
        root = self.repo()
        (root / ".github" / "sd-check-scope.json").write_text('{"schema_version": 1}', encoding="utf-8")
        git(root, "commit", "-q", "-am", "break it")
        completed = self.run_check(root, "--base", "main")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("sd-check-scope.json needs exactly", completed.stderr)

    def test_declared_docs_tools_reach_a_docs_only_scope(self) -> None:
        """sd:2881: `docs_tools` names every tool the docs command reaches; a hub compares those in a docs-only scope."""
        root = self.repo(docs_tools=["sh", "python3"])
        self.change(root, "docs/guide.md")
        self.assertEqual(sd_check_scope.decide(root, "main", sd_lib.detect_entrypoints(root)).tools, ("sh", "python3"))
        self.change(root, "src/app.py")
        self.assertIsNone(sd_check_scope.decide(root, "main", sd_lib.detect_entrypoints(root)).tools)
        for bad in ("sh", [""], [1], ["../tools/validator"], ["tools/validator"], ["/usr/bin/vale"], ["."], [".."]):
            with self.subTest(bad=bad):
                path = root / ".github" / "sd-check-scope.json"
                path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), "docs_tools": bad}),
                                encoding="utf-8")
                with self.assertRaisesRegex(sd_check_scope.DeclarationError, "docs_tools must be a list of bare command names"):
                    sd_check_scope.declaration(root)

    def test_base_does_not_combine_with_only_or_a_receipt(self) -> None:
        root = self.repo()
        for extra in (("--only", "check"), ("--record-receipt",)):
            with self.subTest(extra=extra):
                self.assertEqual(self.run_check(root, "--base", "main", *extra).returncode, 2)
