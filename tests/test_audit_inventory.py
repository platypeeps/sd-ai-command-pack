from __future__ import annotations

try:
    import install_test_support as _support
except ModuleNotFoundError as exc:
    if exc.name != "install_test_support":
        raise
    from . import install_test_support as _support

install = _support.install
InstallTestCase = _support.InstallTestCase
json = _support.json
mock = _support.mock
os = _support.os
subprocess = _support.subprocess
sys = _support.sys

HELPER = install.ROOT / "templates/scripts/sd-ai-command-pack-audit-inventory.py"


class AuditInventoryTests(InstallTestCase):
    def run_helper(self, root, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HELPER), "--repo", str(root), *arguments],
            cwd=install.ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def prepare_repo(self):
        root = self.make_git_repo_without_trellis()
        self.run_git(root, "config", "user.email", "audit@example.com")
        self.run_git(root, "config", "user.name", "Audit Test")
        return root

    def test_hostile_filenames_round_trip_without_executing_checkout_code(self) -> None:
        root = self.prepare_repo()
        make_marker = root / "make-ran"
        help_marker = root / "help-ran"
        provider_marker = root / "provider-ran"
        files = {
            "space name.py": b"space\n",
            "tab\tname.py": b"tab-content\n",
            "line\nbreak.py": b"newline-content-is-longer\n",
            "-leading.py": b"dash-content\n",
            "Makefile": (
                f"SIDE_EFFECT := $(shell touch {make_marker})\nall:\n\t@true\n"
            ).encode(),
            "side-effect-help.sh": (
                f"#!/usr/bin/env bash\ntouch {help_marker}\ntouch {provider_marker}\n"
            ).encode(),
        }
        for name, content in files.items():
            (root / name).write_bytes(content)
        (root / "side-effect-help.sh").chmod(0o755)
        self.run_git(root, "add", "--", ".")
        self.run_git(root, "commit", "-m", "hostile inventory fixture")

        result = self.run_helper(root, "--limit", "100", "--json")
        human_result = self.run_helper(root, "--limit", "100")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(human_result.returncode, 0, human_result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schemaVersion"], 1)
        self.assertEqual(report["measurement"], "blob-bytes")
        self.assertEqual(report["trackedRegularFiles"], len(files))
        self.assertEqual({entry["path"] for entry in report["entries"]}, set(files))
        self.assertEqual(
            [entry["bytes"] for entry in report["entries"]],
            sorted((len(content) for content in files.values()), reverse=True),
        )
        self.assertFalse(make_marker.exists())
        self.assertFalse(help_marker.exists())
        self.assertFalse(provider_marker.exists())
        self.assertIn(json.dumps("line\nbreak.py"), human_result.stdout)

    def test_empty_committed_tree_reports_visible_none(self) -> None:
        root = self.prepare_repo()
        self.run_git(root, "commit", "--allow-empty", "-m", "empty")

        json_result = self.run_helper(root, "--json")
        human_result = self.run_helper(root)

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        self.assertEqual(json.loads(json_result.stdout)["entries"], [])
        self.assertEqual(human_result.returncode, 0, human_result.stderr)
        self.assertIn("tracked regular files: 0", human_result.stdout)
        self.assertIn("largest files:\n  none", human_result.stdout)

    def test_non_regular_tree_entries_are_skipped_not_followed(self) -> None:
        root = self.prepare_repo()
        (root / "regular.txt").write_text("regular\n", encoding="utf-8")
        try:
            os.symlink("regular.txt", root / "tracked-link")
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.run_git(root, "add", "--", ".")
        self.run_git(root, "commit", "-m", "symlink inventory fixture")

        result = self.run_helper(root, "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["skippedNonRegular"], 1)
        self.assertEqual(
            [entry["path"] for entry in report["entries"]], ["regular.txt"]
        )

    def test_parser_rejects_malformed_or_unterminated_git_records(self) -> None:
        module = self.load_module_from_path(HELPER, "audit_inventory_under_test")

        for payload in (b"bad\0", b"100644 blob " + b"a" * 40 + b" 2\tfile"):
            with self.subTest(payload=payload):
                with self.assertRaises(module.AuditInventoryError):
                    module.parse_ls_tree(payload)

    def test_input_guards_reject_untrusted_inventory_shapes(self) -> None:
        module = self.load_module_from_path(HELPER, "audit_inventory_guards_test")
        valid_oid = b"a" * 40
        valid_record = b"100644 blob " + valid_oid + b" 2\tfile\0"

        with self.assertRaises(module.argparse.ArgumentTypeError):
            module.positive_limit("not-an-integer")
        with self.assertRaises(module.AuditInventoryError):
            module.parse_ls_tree("not bytes")
        with mock.patch.object(module, "MAX_TRACKED_ENTRIES", 0):
            with self.assertRaises(module.AuditInventoryError):
                module.parse_ls_tree(valid_record)
        for payload in (
            b"100644 blob invalid 2\tfile\0",
            b"100644 blob " + valid_oid + b" invalid\tfile\0",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(module.AuditInventoryError):
                    module.parse_ls_tree(payload)

        root = self.prepare_repo()
        with self.assertRaises(module.AuditInventoryError):
            module.build_report(root / "missing", limit=20)
        text_result = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
        with mock.patch.object(module, "run_command", return_value=text_result):
            with self.assertRaises(module.AuditInventoryError):
                module.build_report(root, limit=20)
        with self.assertRaises(module.AuditInventoryError):
            module.render_human(
                {
                    "measurement": "blob-bytes",
                    "trackedRegularFiles": 1,
                    "skippedNonRegular": 0,
                    "entries": ["not a mapping"],
                }
            )

    def test_git_failure_and_invalid_limit_are_controlled(self) -> None:
        root = self.prepare_repo()

        missing_head = self.run_helper(root, "--json")
        invalid_limit = self.run_helper(root, "--limit", "0")

        self.assertEqual(missing_head.returncode, 1)
        self.assertIn("error: failed to inventory committed files", missing_head.stderr)
        self.assertNotIn("Traceback", missing_head.stderr)
        self.assertEqual(invalid_limit.returncode, 2)
        self.assertIn("limit must be between 1 and 1000", invalid_limit.stderr)

    def test_build_report_invokes_only_bounded_git_inventory(self) -> None:
        root = self.prepare_repo()
        module = self.load_module_from_path(HELPER, "audit_inventory_command_test")
        completed = subprocess.CompletedProcess(
            ["git"],
            0,
            stdout=b"",
            stderr=b"",
        )

        with mock.patch.object(module, "run_command", return_value=completed) as run:
            report = module.build_report(root, limit=20)

        self.assertEqual(report["entries"], [])
        run.assert_called_once_with(
            [
                "git",
                "ls-tree",
                "-r",
                "-l",
                "-z",
                "--full-tree",
                "HEAD",
                "--",
            ],
            cwd=root.resolve(),
            check=False,
            text=False,
            context="inventory committed files for architecture audit",
        )


if __name__ == "__main__":
    _support.unittest.main()
